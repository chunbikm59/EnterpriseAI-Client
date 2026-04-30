import re
import os
import io
import time
import asyncio
import json
import base64
from contextvars import ContextVar
from mcp.server.fastmcp import FastMCP
import requests
import argparse
from markitdown import MarkItDown
from utils.pdf_converter import PyMuPdfConverter
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
from pydub import AudioSegment
from pydantic import Field, BaseModel
import asyncio
import aiofiles
import subprocess
import shutil
import uuid
from utils.llm_client import get_llm_client, get_model_setting
from utils.user_profile import get_user_profile_dir, get_user_memory_dir, get_conversation_artifacts_dir
from utils.signed_url import rewrite_artifact_paths
from utils.memory_manager import (
    write_memory_file, write_memory_index,
    load_memory_file, load_memory_index, list_memory_files,
    validate_memory_path,
)

mcp = FastMCP(name="buildin_tools", json_response=False, stateless_http=False)

# ── 全域 MarkItDown 單例（避免每次呼叫重新初始化 requests.Session / magika.Magika）──
_md = MarkItDown(enable_plugins=True)
_md.register_converter(PyMuPdfConverter(), priority=-1.0)  # 優先於 pdfminer（priority 越小越先執行），修正 CJK 亂碼

# ── Session Context (contextvars，取代 FastMCP Context) ──
_session_ctx: ContextVar[dict] = ContextVar(
    "buildin_session_ctx",
    default={"session_id": "", "user_id": "", "conversation_id": "", "conversation_folder": ""}
)

# ── AgentSkills session registry ──
# 因為 buildin MCP server 是 in-process（同進程 HTTP transport），
# 無法透過 env var 傳遞資料，改用 module-level dict 按 Chainlit session_id 儲存技能目錄。
_session_skill_catalogs: dict[str, str] = {}

# ── 動態表單等待機制 ──
# key: Chainlit session_id（cl.user_session.get('id')，不是 conversation_id）
# value: {"form_id": str, "event": asyncio.Event, "result": dict,
#         "elem_id": str|None, "msg_id": str|None, "original_props": dict}
_pending_forms: dict[str, dict] = {}

# ── HTML Render 暫存機制 ──
# key: Chainlit session_id，value: {"artifact_id": str, "html_code": str, "title": str}
_pending_renders: dict[str, dict] = {}

# ── PPTX Render 暫存機制 ──
# key: Chainlit session_id，value: {"pptx_id": str, "pptx_script": str, "title": str, "slide_count": int}
_pending_pptx_renders: dict[str, dict] = {}

# ── Markdown Render 暫存機制 ──
# key: Chainlit session_id，value: {"md_id": str, "markdown_content": str, "title": str, "file_path": str}
_pending_md_renders: dict[str, dict] = {}


def register_session_skills(session_id: str, skills_json: str):
    """在 on_chat_start 時將該 session 的技能目錄（JSON）註冊進來。"""
    _session_skill_catalogs[session_id] = skills_json


def unregister_session_skills(session_id: str):
    """在 on_chat_end 時清除該 session 的技能資料。"""
    _session_skill_catalogs.pop(session_id, None)

def register_mcp_tool(func_name: str, describe: str, return_string, namespace=None):
    # 預設註冊到目前全域空間
    if namespace is None:
        namespace = globals()

    # 驗證函數名稱（支援中英文）
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', func_name):
        raise ValueError("函數名稱不合法，請使用英文、數字、底線組合，且不得以數字開頭")

    # 處理字串內容，避免注入（repr 會自動加上引號和跳脫）
    safe_return = repr(return_string)

    # 組成function
    func_code = f'''
@mcp.tool()
def {func_name}():
    """{describe}"""
    return {safe_return}
'''

    # 執行代碼並註冊到 namespace（預設為全域）
    exec(func_code, namespace)

    return namespace[func_name]

def _check_path_in_allowed_roots(abs_path: str, allowed_roots: list[str]) -> bool:
    """檢查 abs_path 是否位於 allowed_roots 中的任何一個根目錄下（含根目錄本身）。
    所有路徑參數皆應已經過 os.path.realpath 解析。
    """
    return any(
        abs_path.startswith(r + os.sep) or abs_path == r
        for r in allowed_roots
    )

@mcp.tool()
async def list_files(
    directory: str = Field(default="conversation", description=(
        "要列出的目錄：\n"
        "- 'conversation'（預設）：本次對話資料夾（展開 uploads/ 與 artifacts/ 兩個子資料夾）\n"
        "- 'memory'：使用者長期記憶目錄（含 type/description，供判斷哪個需更新）"
    )),
):
    """列出指定目錄中的檔案。conversation 模式會分區顯示 uploads/ 和 artifacts/ 的內容。"""
    if directory == "memory":
        user_id = _session_ctx.get()["user_id"]
        files = list_memory_files(user_id)
        if not files:
            return "記憶目錄目前沒有任何檔案。"
        lines = [
            f"- {f['filename']} [{f.get('type', '')}] — {f.get('description', '（無描述）')} ({f['size_bytes']} bytes)"
            for f in files
        ]
        return "記憶目錄檔案清單：\n" + "\n".join(lines)
    root_folder = get_conversation_folder()
    return await _list_conversation_files(root_folder)

# @mcp.tool()
async def transcription(
    filename: str = Field(description="要轉錄的影音檔案名稱（支援 mp3, mp4, wav, m4a, webm, ogg 等格式）")
):
    '''將本次對話資料夾中的影音檔轉錄成文字稿'''
    root_folder = get_conversation_folder()

    # 構建完整檔案路徑，並做 realpath 驗證防路徑穿越
    file_path = os.path.join(root_folder, filename)
    abs_path = os.path.realpath(file_path)
    if not _check_path_in_allowed_roots(abs_path, [os.path.realpath(root_folder)]):
        return "存取拒絕：只能存取對話資料夾中的檔案。"

    # 用非同步執行同步阻塞 I/O 檢查檔案是否存在
    file_exists = await asyncio.to_thread(os.path.exists, abs_path)
    if not file_exists:
        return f"檔案不存在: {filename}"
    
    # 檢查檔案是否為支援的音訊格式
    supported_formats = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.ogg']
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in supported_formats:
        return f"不支援的檔案格式: {file_ext}。支援的格式: {', '.join(supported_formats)}"
    
    # 音頻壓縮處理（等效於 ffmpeg -i audio.mp3 -vn -map_metadata -1 -ac 1 -c:a libopus -b:a 12k -application voip audio.ogg）
    artifacts_dir = get_conversation_artifacts_dir(root_folder)
    os.makedirs(artifacts_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(filename))[0]
    compressed_filename = f"{base_name}_compressed.ogg"
    compressed_path = os.path.join(artifacts_dir, compressed_filename)

    try:
        # 音頻檔載入與轉換（同步，包在 to_thread 裡）
        def compress_audio():
            audio = AudioSegment.from_file(abs_path)
            audio = audio.set_channels(1)
            audio.export(
                compressed_path,
                format="ogg",
                codec="libopus",
                bitrate="16k",
                parameters=["-application", "voip"]
            )

        await asyncio.to_thread(compress_audio)
        
        # 獲取大小比較壓縮率
        original_size = await asyncio.to_thread(os.path.getsize, abs_path)
        compressed_size = await asyncio.to_thread(os.path.getsize, compressed_path)
        compression_ratio = (1 - compressed_size / original_size) * 100

        print(f"音頻壓縮完成: {filename} -> {compressed_filename}")
        print(f"原始大小: {original_size:,} bytes")
        print(f"壓縮後大小: {compressed_size:,} bytes")
        print(f"壓縮率: {compression_ratio:.1f}%")
        
        # 使用壓縮後的檔案進行轉錄
        transcription_file = compressed_path
        
    except Exception as compress_error:
        print(f"音頻壓縮失敗，使用原始檔案: {str(compress_error)}")
        # 如果壓縮失敗，使用原始檔案
        transcription_file = abs_path
    
    # 非同步讀取檔案並包成 BytesIO，因為 API 需要 file-like object
    async with aiofiles.open(transcription_file, 'rb') as f:
        audio_bytes = await f.read()
    audio_file_obj = io.BytesIO(audio_bytes)
    audio_file_obj.name = os.path.basename(transcription_file)  # 必須有檔名屬性
    
    # 初始化 OpenAI 客戶端
    client = get_llm_client(provider='openai', api_key=os.getenv('LLM_API_KEY'), base_url=os.getenv('BASE_URL', 'https://api.openai.com/v1'))
    
    # 呼叫 Whisper API（非同步）
    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file_obj,
        response_format="text"
    )
    # 生成轉錄檔案名稱
    transcript_filename = f"{base_name}_transcript.txt"
    transcript_path = os.path.join(artifacts_dir, transcript_filename)
    
    # 保存轉錄結果到檔案
    async with aiofiles.open(transcript_path, 'w', encoding='utf-8') as f:
        await f.write(transcript)

    return transcript
    
@mcp.tool()
async def read_file(
    filename: str = Field(description=(
        "要讀取的檔案名稱或路徑。支援：\n"
        "- 對話 artifacts 檔案：artifacts/output.md（需含 artifacts/ 前綴）\n"
        "- 對話上傳檔案：uploads/file.pdf（需含 uploads/ 前綴）\n"
        "- 記憶檔案：memory/filename.md\n"
        "- 支援格式：PDF, PowerPoint, Word, Excel, Images, HTML, CSV, JSON, XML, ZIP, EPub 等"
    )),
    start_line: int = Field(1, description="從第幾行開始讀取（從 1 起算，預設 1）"),
    end_line: int = Field(2000, description="讀到第幾行結束（預設 2000；0 表示讀到 start_line+1999）"),
):
    '''將檔案轉成 markdown 格式，預設回傳第 1–2000 行，可自行指定範圍，無行數上限。支援對話資料夾內的檔案，以及自己的 user_profiles 技能資源。'''

    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    conversation_folder = get_conversation_folder()

    norm = filename.replace("\\", "/").lstrip("/")
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if norm.startswith("memory/"):
        # 簡短格式 memory/filename.md → 自動對應至當前使用者的 memory 目錄
        memory_dir_abs = os.path.realpath(get_user_memory_dir(user_id))
        file_path = os.path.join(memory_dir_abs, norm[len("memory/"):])
    elif norm.startswith("user_profiles/"):
        file_path = os.path.join(_PROJECT_ROOT, norm)  # 明確以專案根目錄為 base
    else:
        file_path = os.path.join(conversation_folder, filename)

    # 存取控制：防路徑穿越 & 跨用戶（邏輯不變）
    abs_path = os.path.realpath(file_path)
    allowed_roots = [os.path.realpath(conversation_folder)]
    if user_id:
        allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))

    if not _check_path_in_allowed_roots(abs_path, allowed_roots):
        return "存取拒絕：只能讀取自己的資料夾。"

    # 路徑存在性驗證
    if not await asyncio.to_thread(os.path.exists, abs_path):
        return f"檔案不存在：{filename}"

    # 100 MB 上限）
    FILE_SIZE_LIMIT = 100 * 1024 * 1024
    file_size = await asyncio.to_thread(os.path.getsize, abs_path)
    if file_size > FILE_SIZE_LIMIT:
        size_mb = file_size / (1024 * 1024)
        return (
            f"檔案過大（{size_mb:.1f} MB），超過 50 MB 上限，無法讀取。\n"
            f"建議：若為文字檔案，請使用其他方式分段傳入內容。"
        )

    # 非同步轉換（避免阻塞事件迴圈）+ 轉換失敗捕獲
    try:
        result = await asyncio.to_thread(_md.convert, abs_path, extract_pages=True)
    except FileNotFoundError:
        return f"檔案不存在：{filename}"
    except Exception as e:
        return f"檔案轉換失敗：{str(e)}"

    full_text = result.text_content
    lines = full_text.splitlines()
    total = len(lines)
    total_chars = len(full_text)

    # 空檔案處理
    if total == 0:
        return f"[檔案內容為空]\n\n{filename} 轉換後沒有任何文字內容。"

    # 大型檔案：超過 2000 行或 50,000 字元時自動寫檔
    LARGE_LINE_THRESHOLD = 2000
    LARGE_CHAR_THRESHOLD = 50_000
    persist_note = ""
    if total > LARGE_LINE_THRESHOLD or total_chars > LARGE_CHAR_THRESHOLD:
        base_name = os.path.splitext(os.path.basename(abs_path))[0]
        _artifacts = get_conversation_artifacts_dir(conversation_folder)
        os.makedirs(_artifacts, exist_ok=True)
        saved_path = os.path.join(_artifacts, f"{base_name}_converted.md")
        if not await asyncio.to_thread(os.path.exists, saved_path):
            def _write():
                with open(saved_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
            await asyncio.to_thread(_write)
        persist_note = (
            f"[完整轉換結果已儲存至：{os.path.basename(saved_path)}（共 {total} 行，{total_chars:,} 字元）]\n"
            f"可使用 read_file 指定 start_line/end_line 分段讀取。\n\n"
        )

    # 計算實際範圍
    actual_start = max(1, start_line)
    if end_line <= 0:
        actual_end = actual_start + 1999
    elif end_line < actual_start:
        actual_end = actual_start + 1999  # end_line < start_line → 自動修正
    else:
        actual_end = end_line
    actual_end = min(actual_end, total)

    # start_line 超限提示
    if actual_start > total:
        return (
            f"start_line={start_line} 超過檔案總行數（共 {total} 行）。\n"
            f"請使用 start_line=1 到 start_line={total} 之間的值。"
        )

    # 行號前綴（cat -n 格式，方便 LLM 引用具體行數）
    numbered_lines = [
        f"{lineno}\t{line}"
        for lineno, line in enumerate(lines[actual_start - 1 : actual_end], start=actual_start)
    ]
    chunk = "\n".join(numbered_lines)

    # 單次回傳字元數上限（50,000 字元），超過時截斷並提示
    OUTPUT_CHAR_LIMIT = 50_000
    truncated = False
    if len(chunk) > OUTPUT_CHAR_LIMIT:
        chunk = chunk[:OUTPUT_CHAR_LIMIT]
        # 在換行符邊界截斷，找出最後一個完整行
        last_nl = chunk.rfind('\n')
        if last_nl > OUTPUT_CHAR_LIMIT * 0.5:
            chunk = chunk[:last_nl]
        # 從截斷後的內容推算實際讀到哪一行
        actual_end = actual_start + chunk.count('\n')
        truncated = True

    header = f"{persist_note}[第 {actual_start}–{actual_end} 行，共 {total} 行]\n\n"
    footer = ""
    if truncated:
        footer = f"\n\n（輸出已達 50,000 字元上限，截斷於第 {actual_end} 行。請使用 start_line={actual_end + 1} 繼續讀取）"
    elif actual_end < total:
        footer = f"\n\n（若想閱讀更多內容，請使用 start_line={actual_end + 1} 繼續讀取）"

    return header + chunk + footer

async def download_youtube_sync(
    url: str = Field(description="YouTube 影片網址"),
    content_type: str = Field(
        description="要下載的內容類型：\n"
                   "- 'subtitle'（預設）：僅下載字幕文字內容，用於文字分析、摘要、翻譯等文字處理任務\n"
                   "- 'audio'：下載音訊檔案（mp3格式），用於語音轉錄、音訊分析等需要聲音內容的任務\n"
                   "- 'video'：下載完整影片檔案（mp4格式），用於影片編輯、完整內容保存等需要視覺內容的任務",
        default='subtitle'
    )
):
    """下載 YouTube 影片成音訊、影片或字幕"""
    output_dir = get_conversation_folder()

    # 確保資料夾存在
    os.makedirs(output_dir, exist_ok=True)

    # 組合輸出檔案路徑格式
    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
    quiet = True
    if content_type == 'audio':
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '1',  # 最低品質
            }],
            'quiet': quiet,
        }
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
    elif content_type == 'video':
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'quiet': quiet,
        }
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
    elif content_type == 'subtitle':
        # 字幕下載配置
        subtitle_template = os.path.join(output_dir, '%(title)s.%(ext)s')
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': False,
            'subtitleslangs': ['zh-TW', 'zh-Hant', 'zh-CN', 'zh-Hans', 'zh', 'en'],  # 優先順序：繁中 > 簡中 > 中文 > 英文
            'subtitlesformat': 'srt',  # 使用 SRT 格式
            'outtmpl': subtitle_template,
            'skip_download': True,  # 只下載字幕，不下載影片
            'quiet': quiet,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            # 先獲取影片資訊
            print("Starting: 取影片資訊")
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', 'Unknown')
            
            # 下載字幕
            ydl.download([url])
            
            # 尋找下載的字幕檔案
            subtitle_content = ""
            possible_extensions = ['.zh-TW.srt', '.zh-CN.srt', '.zh-Hant.srt', '.zh-Hans.srt', '.zh.srt', '.en.srt', '.srt']
            
            for ext in possible_extensions:
                subtitle_file = os.path.join(output_dir, f"{video_title}{ext}")
                if os.path.exists(subtitle_file):
                    try:
                        with open(subtitle_file, 'r', encoding='utf-8') as f:
                            subtitle_content = f.read()
                        break
                    except UnicodeDecodeError:
                        # 嘗試其他編碼
                        try:
                            with open(subtitle_file, 'r', encoding='utf-8-sig') as f:
                                subtitle_content = f.read()
                            break
                        except:
                            continue
            
            if subtitle_content:
                return subtitle_content
            else:
                return f"執行完成，但無法讀取字幕內容。請檢查資料夾中的字幕檔案。"
    else:
        raise ValueError("content_type 只能是 'audio'、'video' 或 'subtitle'")
    
    return "done"

@mcp.tool()
async def download_youtube(
    url: str,
    content_type: str = Field(
        description="要下載的內容類型：\n"
                   "- 'subtitle'（預設）：僅下載字幕文字內容，用於文字分析、摘要、翻譯等文字處理任務\n"
                   "- 'audio'：下載音訊檔案（mp3格式），用於語音轉錄、音訊分析等需要聲音內容的任務\n"
                   "- 'video'：下載完整影片檔案（mp4格式），用於影片編輯、完整內容保存等需要視覺內容的任務",
        default='subtitle'
    ),
    subtitle_lang: str = Field(
        description="指定要下載的字幕語言代碼（例如：'zh-TW', 'zh-CN', 'en', 'ja'）。\n"
                   "僅在 content_type='subtitle' 時有效。\n"
                   "可使用 list_youtube_subtitles 工具查看可用的字幕語言",
        default=''
    )
):
    output_dir = get_conversation_artifacts_dir(get_conversation_folder())
    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
    quiet = True

    if content_type == 'audio':
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'restrictfilenames': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '1',
            }],
            'quiet': quiet,
        }
        ydl = await asyncio.to_thread(YoutubeDL, ydl_opts)
        await asyncio.to_thread(ydl.download, [url])

    elif content_type == 'video':
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'merge_output_format': 'mp4',
            'restrictfilenames': True,
            'quiet': quiet,
        }
        ydl = await asyncio.to_thread(YoutubeDL, ydl_opts)
        await asyncio.to_thread(ydl.download, [url])

    elif content_type == 'subtitle':
        subtitle_template = os.path.join(output_dir, '%(title)s.%(ext)s')
        
        # 根據是否指定語言來設定字幕語言列表
        if subtitle_lang:
            # 如果指定了語言，只下載該語言
            subtitles_langs = [subtitle_lang]
        else:
            # 未指定則使用預設優先順序
            subtitles_langs = ['zh-TW', 'zh-Hant', 'zh-CN', 'zh-Hans', 'zh', 'en']
        
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,  # 同時支援自動產生的字幕
            'subtitleslangs': subtitles_langs,
            'subtitlesformat': 'srt',
            'outtmpl': subtitle_template,
            'restrictfilenames': True,
            'skip_download': True,
            'quiet': quiet,
        }
        ydl = YoutubeDL(ydl_opts)
        print("Starting: 取影片資訊")

        info = await asyncio.to_thread(ydl.extract_info, url, download=False)
        raw_title = info.get('title', 'Unknown')
        video_title = re.sub(r'[^\w\-.]', '_', raw_title)

        await asyncio.to_thread(ydl.download, [url])

        subtitle_content = ""
        
        # 根據指定的語言或預設順序尋找字幕檔案
        if subtitle_lang:
            possible_extensions = [f'.{subtitle_lang}.srt']
        else:
            possible_extensions = ['.zh-TW.srt', '.zh-CN.srt', '.zh-Hant.srt', '.zh-Hans.srt', '.zh.srt', '.en.srt', '.srt']

        for ext in possible_extensions:
            subtitle_file = os.path.join(output_dir, f"{video_title}{ext}")
            if os.path.exists(subtitle_file):
                try:
                    with open(subtitle_file, 'r', encoding='utf-8') as f:
                        subtitle_content = f.read()
                    break
                except UnicodeDecodeError:
                    try:
                        with open(subtitle_file, 'r', encoding='utf-8-sig') as f:
                            subtitle_content = f.read()
                        break
                    except:
                        continue
        
        if subtitle_content:
            return subtitle_content
    else:
        raise ValueError("content_type 只能是 'audio'、'video' 或 'subtitle'")
    
    files_list = await _list_files_internal(output_dir)
    # 將檔案列表每行加上 artifacts/ 前綴，避免 Agent 誤用純檔名當路徑
    prefixed_lines = []
    for line in files_list.splitlines():
        stripped = line.lstrip()
        if stripped and not stripped.startswith("[") and not stripped.startswith("（") and not stripped.startswith("檔案列表"):
            indent = line[: len(line) - len(stripped)]
            prefixed_lines.append(f"{indent}artifacts/{stripped}")
        else:
            prefixed_lines.append(line)
    return f"下載完成，檔案路徑（相對於對話資料夾）：\n" + "\n".join(prefixed_lines)

@mcp.tool()
async def list_youtube_subtitles(
    url: str = Field(description="YouTube 影片網址")
):
    '''列出 YouTube 影片所有可用的字幕（包含官方字幕和自動產生的字幕）'''
    
    try:
        # 配置 ydl_opts 以獲取字幕信息
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,  # 只獲取信息，不下載
            'ignore_no_formats_error': True,
        }
        
        # 使用 asyncio.to_thread 在執行緒中執行同步操作
        def extract_subtitles_info():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        
        info = await asyncio.to_thread(extract_subtitles_info)
        
        video_title = info.get('title', 'Unknown')
        video_duration = info.get('duration', 0)
        
        # 構建結果字符串
        result = f"🎬 YouTube 影片字幕列表\n"
        result += f"{'='*50}\n"
        result += f"影片標題: {video_title}\n"
        result += f"影片時長: {video_duration // 60} 分 {video_duration % 60} 秒\n"
        result += f"{'='*50}\n\n"
        
        # 提取字幕信息
        subtitles = info.get('subtitles', {})
        automatic_captions = info.get('automatic_captions', {})
        
        # 處理官方字幕
        if subtitles:
            result += "📝 官方字幕 (Manually Created Subtitles):\n"
            result += "-" * 50 + "\n"
            for lang_code in subtitles.keys():
                result += f"  • {lang_code}\n"
            result += "\n"
        else:
            result += "📝 官方字幕: 無\n\n"
        
        # 處理自動產生的字幕
        if automatic_captions:
            result += "🤖 自動產生的字幕 (Auto-generated Captions):\n"
            result += "-" * 50 + "\n"
            for lang_code in automatic_captions.keys():
                result += f"  • {lang_code}\n"
            result += "\n"
        else:
            result += "🤖 自動產生的字幕: 無\n\n"
        
        # 統計信息
        total_subtitles = len(subtitles) + len(automatic_captions)
        result += "=" * 50 + "\n"
        result += f"總計: {len(subtitles)} 個官方字幕 + {len(automatic_captions)} 個自動字幕\n"
        result += f"共 {total_subtitles} 個字幕軌道\n"
        
        # 建議
        result += "\n💡 使用建議:\n"
        result += "• 使用 'download_youtube' 工具下載字幕，可指定 subtitle_lang 參數選擇語言\n"
        result += "• 設定 content_type='subtitle' 來下載字幕內容\n"
        
        return result
        
    except Exception as e:
        return f"❌ 獲取字幕列表失敗: {str(e)}\n\n可能原因:\n" \
               f"• 影片網址無效\n" \
               f"• 影片不存在或已被移除\n" \
               f"• 網路連接有問題\n" \
               f"• 影片沒有任何字幕"

# @mcp.tool()
async def attempt_completion():
    '''呼叫此工具才能讓使用者輸入或操作，不然你將永遠只能自言自語。無論是完成、受阻或需要補充資訊，都必須透過此工具回覆。'''
    return

@mcp.tool()
async def query_employee(
    employee_id: str = Field(description="員工工號（純數字字串，例如：'10001'）", default=''),
    name: str = Field(description="員工姓名", default=''),
    department: str = Field(description="部門名稱", default=''),
    job_level: str = Field(description="職級（例如：'工程師', '資深工程師', '主任'）", default=''),
) -> str:
    """查詢員工或部門資訊（測試用）。可依工號、姓名、部門、職級進行篩選，不填的條件則不限制。"""
    # 測試用假資料
    employees = [
        {"employee_id": "10001", "name": "王小明", "department": "研發部", "job_level": "資深工程師"},
        {"employee_id": "10002", "name": "李美華", "department": "人資部", "job_level": "主任"},
        {"employee_id": "10003", "name": "張志豪", "department": "研發部", "job_level": "工程師"},
        {"employee_id": "10004", "name": "陳雅婷", "department": "財務部", "job_level": "專員"},
        {"employee_id": "10005", "name": "林建宏", "department": "業務部", "job_level": "業務經理"},
        {"employee_id": "10006", "name": "黃怡君", "department": "研發部", "job_level": "工程師"},
    ]

    results = []
    for emp in employees:
        if employee_id and emp["employee_id"] != employee_id:
            continue
        if name and name not in emp["name"]:
            continue
        if department and department not in emp["department"]:
            continue
        if job_level and job_level not in emp["job_level"]:
            continue
        results.append(emp)

    if not results:
        return "查無符合條件的員工資料。"

    lines = [f"共找到 {len(results)} 筆資料："]
    for emp in results:
        lines.append(
            f"工號: {emp['employee_id']}  姓名: {emp['name']}  部門: {emp['department']}  職級: {emp['job_level']}"
        )
    return "\n".join(lines)


# ── HTTP 請求工具 ──

# ── 內部服務憑證白名單 ──
# URL 前綴（從環境變數取得）對應要自動注入的 headers
# key 明文只在此函式內部存在，不對外暴露
def _get_internal_auth_rules() -> list[tuple[str, dict]]:
    rules = []
    llm_base = os.getenv("BASE_URL", "").rstrip("/")
    if llm_base:
        rules.append((llm_base, {"Authorization": f"Bearer {os.getenv('LLM_API_KEY', '')}"}))
    return rules

@mcp.tool()
async def http_request(
    url: str = Field(description="請求目標 URL"),
    method: str = Field(description="HTTP 方法（GET/POST/PUT/PATCH/DELETE），預設 GET", default="GET"),
    headers: str = Field(description='請求 headers，JSON 格式字串，例如：{"Content-Type": "application/json"}。可省略', default=""),
    body: str = Field(description="請求 body，純文字字串。若要送 JSON 請在 headers 指定 Content-Type: application/json。指定 form_fields 時此欄位會被忽略。可省略", default=""),
    stream: bool = Field(description="是否啟用串流模式，逐 chunk 推送到 UI 子步驟，且回應內容一定會寫入對話資料夾檔案。預設 False", default=False),
    stream_save_filename: str = Field(description="串流模式下儲存回應內容的檔名（僅檔名，不含路徑）。若省略，系統自動以 http_stream_<timestamp>.txt 命名。", default=""),
    form_fields: str = Field(
        description=(
            "multipart/form-data 欄位，JSON 格式。值若為存在的檔案路徑則自動以二進位上傳，否則當普通字串。\n"
            "例如：{\"file\": \"audio.mp3\", \"model\": \"whisper-1\", \"language\": \"zh\"}\n"
            "指定後，body 參數會被忽略。檔案必須位於對話資料夾或使用者 user_profiles 目錄內。可省略。"
        ),
        default=""
    ),
) -> str:
    """發送 HTTP 請求。支援串流回應，串流內容會即時顯示在 UI 子步驟中（最新 200 字元）。
    可透過 form_fields 以 multipart/form-data 方式上傳檔案並附帶其他欄位。
    目標 URL 若符合內部服務白名單，系統自動注入 Authorization header，key 明文不對外暴露。"""
    import aiohttp

    ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    STREAM_DISPLAY_LIMIT = 200

    method = method.upper()
    if method not in ALLOWED_METHODS:
        return f"錯誤：不支援的 HTTP 方法 '{method}'，請使用 {', '.join(sorted(ALLOWED_METHODS))} 之一。"

    # 解析 headers
    parsed_headers: dict = {}
    if headers.strip():
        try:
            parsed_headers = json.loads(headers)
        except json.JSONDecodeError as e:
            return f"錯誤：headers 不是有效的 JSON 格式：{e}"

    # 自動注入內部服務憑證（依 URL 前綴比對白名單）
    for base_url, inject_headers in _get_internal_auth_rules():
        if url.startswith(base_url):
            # 防止 Agent 自帶 Authorization 覆蓋內部憑證
            if any(k.lower() == "authorization" for k in parsed_headers):
                return "錯誤：存取內部服務時，headers 不得自帶 Authorization 欄位。"
            parsed_headers.update(inject_headers)
            break

    # 解析 body
    request_kwargs: dict = {}
    if body.strip():
        request_kwargs["data"] = body

    # multipart/form-data 模式
    if form_fields.strip():
        try:
            parsed_form = json.loads(form_fields)
        except json.JSONDecodeError as e:
            return f"錯誤：form_fields 不是有效的 JSON 格式：{e}"

        ctx_data = _session_ctx.get()
        user_id = ctx_data["user_id"]
        conversation_folder = get_conversation_folder()
        allowed_roots = [os.path.realpath(conversation_folder)]
        if user_id:
            allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))

        upload_form = aiohttp.FormData()
        for field_name, field_value in parsed_form.items():
            if field_name == "file":
                candidate = str(field_value)
                if os.path.isabs(candidate):
                    src_abs = os.path.realpath(candidate)
                else:
                    src_abs = os.path.realpath(os.path.join(conversation_folder, candidate))
                if not _check_path_in_allowed_roots(src_abs, allowed_roots):
                    return "存取拒絕：file 的檔案路徑只能指向自己的對話資料夾或 user_profiles 目錄。"
                if not os.path.isfile(src_abs):
                    return f"上傳失敗：檔案不存在：{field_value}"
                upload_form.add_field(
                    field_name,
                    open(src_abs, "rb"),
                    filename=os.path.basename(src_abs),
                )
            else:
                upload_form.add_field(field_name, str(field_value))

        request_kwargs = {"data": upload_form}

    # 讀取 proxy 設定
    if url.startswith("https://"):
        proxy = os.getenv("TOOL_HTTPS_PROXY") or os.getenv("TOOL_HTTP_PROXY") or None
    else:
        proxy = os.getenv("TOOL_HTTP_PROXY") or os.getenv("TOOL_HTTPS_PROXY") or None

    # 取得目前的 cl.step（供串流子步驟使用）
    parent_step = None
    if stream:
        try:
            import chainlit as cl
            parent_step = cl.context.current_step
        except Exception:
            pass

    full_text = ""
    try:
        timeout = aiohttp.ClientTimeout(connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url,
                headers=parsed_headers or None,
                proxy=proxy,
                **request_kwargs
            ) as response:
                status_line = f"HTTP {response.status} {response.reason}"
                # 擷取關鍵 response headers（最多 5 個）
                key_headers = list(response.headers.items())[:5]
                header_lines = "\n".join(f"{k}: {v}" for k, v in key_headers)

                if stream:
                    async for chunk in response.content.iter_chunked(1024):
                        decoded = chunk.decode("utf-8", errors="replace")
                        full_text += decoded
                        if parent_step:
                            parent_step.output = full_text[-STREAM_DISPLAY_LIMIT:]
                            await parent_step.update()
                else:
                    full_text = await response.text()

        saved_file_info = ""
        if stream:
            import time as _time
            artifacts_dir = get_conversation_artifacts_dir(get_conversation_folder())
            os.makedirs(artifacts_dir, exist_ok=True)
            if stream_save_filename.strip():
                save_name = os.path.basename(stream_save_filename.strip())
            else:
                save_name = f"http_stream_{int(_time.time())}.txt"
            save_abs = os.path.join(artifacts_dir, save_name)
            with open(save_abs, "w", encoding="utf-8") as _f:
                _f.write(full_text)
            saved_file_info = f"\n[串流內容已寫入檔案：{save_name}]"

        return f"{status_line}\n{header_lines}\n\n{full_text}{saved_file_info}"

    except aiohttp.ClientError as e:
        error_detail = repr(e) if not str(e) else str(e)
        return f"HTTP 請求失敗：{type(e).__name__}: {error_detail}"


# ── AgentSkills：activate_skill 工具 ──
# 每個技能最多列出的資源檔案數，超過則截斷並提示
RESOURCES_MAX = 50

@mcp.tool()
async def activate_skill(
    skill_name: str = Field(description="技能名稱，與可用技能清單中的 name 相同")
) -> str:
    """載入指定技能的完整指令。當任務符合某個技能的描述時呼叫此工具。"""

    session_id = _session_ctx.get()["session_id"]
    print('session_id', session_id)

    # 從 session registry 取出該 session 的技能目錄
    skills_json = _session_skill_catalogs.get(session_id, "")
    if not skills_json:
        return "錯誤：此 session 無可用技能。"

    # 動態 import（避免在模組初始化時觸發 sys.path 競態）
    import sys as _sys, os as _os
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _project_root not in _sys.path:
        _sys.path.insert(0, _project_root)
    from utils.skills_manager import skills_from_json, get_skill_content

    skills = skills_from_json(skills_json)
    body = get_skill_content(skill_name, skills)

    if body is None:
        available = ", ".join(s.name for s in skills)
        return f"錯誤：找不到技能 '{skill_name}'。可用技能：{available}"

    skill_map = {s.name: s for s in skills}
    skill = skill_map[skill_name]

    # 列出技能資料夾中的資源檔案（scripts/, references/, assets/）
    resources = []
    truncated = False
    for subdir in ("scripts", "references", "assets"):
        subdir_path = os.path.join(skill.skill_dir, subdir)
        if os.path.isdir(subdir_path):
            for fname in os.listdir(subdir_path):
                if os.path.isfile(os.path.join(subdir_path, fname)):
                    if len(resources) >= RESOURCES_MAX:
                        truncated = True
                        break
                    abs_file = os.path.join(subdir_path, fname)
                    rel_path = os.path.relpath(abs_file, _project_root).replace("\\", "/")
                    resources.append(rel_path)
        if truncated:
            break

    resources_info = {"files": resources}
    if truncated:
        resources_info["note"] = f"listing truncated, {RESOURCES_MAX}+ files in directory"

    # 替換 SKILL.md 中的環境變數占位符。
    # 只替換明確白名單的 key，避免 {任意key} 被用來探測其他環境變數。
    _SKILL_ENV_WHITELIST = ["BASE_URL"]
    for _key in _SKILL_ENV_WHITELIST:
        _val = os.getenv(_key, "")
        body = body.replace(f"${{{_key}}}", _val)

    skill_dir_rel = os.path.relpath(skill.skill_dir, _project_root).replace("\\", "/")
    return (
        f"{body}\n\n"
        f"---\n"
        f"技能目錄: {skill_dir_rel}\n"
        f"可用資源: {json.dumps(resources_info, ensure_ascii=False)}"
    )

def get_conversation_folder() -> str:
    return _session_ctx.get()["conversation_folder"]


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size:,} bytes"


async def _list_conversation_files(root_folder: str) -> str:
    """列出對話資料夾下 uploads/ 與 artifacts/ 的所有檔案，分區顯示。"""
    sections = []
    for subdir in ("uploads", "artifacts"):
        subdir_path = os.path.join(root_folder, subdir)
        if not os.path.isdir(subdir_path):
            sections.append(f"{subdir}/ (不存在)")
            continue
        items = sorted(f for f in os.listdir(subdir_path)
                       if os.path.isfile(os.path.join(subdir_path, f)))
        if not items:
            sections.append(f"{subdir}/ (空)")
            continue
        lines = [f"{subdir}/ ({len(items)} 個檔案):"]
        for name in items:
            size = os.path.getsize(os.path.join(subdir_path, name))
            lines.append(f"  {subdir}/{name} ({_format_size(size)})")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)

async def _list_files_internal(root_folder: str, offset: int = 0, limit: int = 200):
    """內部函數：列出指定資料夾中的檔案，供多個工具重用"""
    try:
        if not os.path.exists(root_folder):
            return "資料夾不存在"

        all_items = sorted(os.listdir(root_folder))
        total = len(all_items)
        page_items = all_items[offset:] if limit <= 0 else all_items[offset: offset + limit]

        if not page_items:
            return "資料夾是空的" if total == 0 else f"沒有更多項目（共 {total} 個）"

        files = []
        for item in page_items:
            item_path = os.path.join(root_folder, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                size_str = f"{size:,} bytes"
                if size > 1024:
                    size_str = f"{size/1024:.1f} KB"
                if size > 1024*1024:
                    size_str = f"{size/(1024*1024):.1f} MB"
                files.append(f"{item} ({size_str})")
            elif os.path.isdir(item_path):
                files.append(f"{item}/ (資料夾)")

        end = offset + len(page_items)
        header = f"[第 {offset + 1}–{end} 個，共 {total} 個]\n\n"
        result = header + "檔案列表:\n" + "\n".join(files)
        if end < total:
            result += f"\n\n（還有更多項目，可使用 offset={end} 繼續列出）"
        return result

    except Exception as e:
        return f"列出檔案時發生錯誤: {str(e)}"

@mcp.tool()
async def write_file(
    path: str = Field(description=(
        "寫入路徑：\n"
        "- 對話 artifacts 資料夾：artifacts/output.md（必須含 artifacts/ 前綴）\n"
        "- 記憶目錄：memory/filename.md\n"
        "  記憶目錄規則：只允許 .md 副檔名；內容檔上限 4KB；MEMORY.md 索引上限 25KB/200行"
    )),
    content: str = Field(description="寫入的完整內容"),
) -> str:
    """在對話 artifacts/ 資料夾或使用者記憶目錄中寫入或覆蓋檔案。
    對話資料夾寫入時，路徑必須以 artifacts/ 開頭（例如 artifacts/output.md）。
    記憶目錄寫入：
    - memory/MEMORY.md：更新記憶索引（每行：- [標題](file.md) — 一行摘要）
    - memory/filename.md：記憶內容檔（含 YAML frontmatter: name/description/type）
    - 新建記憶檔後需同步更新 MEMORY.md；保存前先 list_files(directory="memory") 確認是否有可更新的現有記憶

    嵌入圖片時請使用相對路徑（相對於本次寫入的檔案本身的位置），對話資料夾結構如下：
      {conversation_folder}/
      ├── artifacts/   ← write_file 輸出位置
      └── uploads/     ← 使用者上傳檔案
    範例（檔案寫到 artifacts/report.md）：
      - 引用 artifacts/ 的圖片：![圖](frame_001.png)        ← 同目錄，只寫檔名
      - 引用 uploads/ 的圖片：  ![圖](../uploads/photo.jpg) ← 上層目錄再進 uploads/
    """
    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    session_id = ctx_data.get("session_id", "")
    conversation_folder = get_conversation_folder()

    norm = path.replace("\\", "/").lstrip("/")
    memory_dir_abs = os.path.realpath(get_user_memory_dir(user_id))
    conv_abs = os.path.realpath(conversation_folder)

    artifacts_dir = get_conversation_artifacts_dir(conversation_folder)
    artifacts_abs = os.path.realpath(artifacts_dir)

    # 解析輸入路徑為絕對路徑
    if os.path.isabs(path):
        target_abs = os.path.realpath(path)
    elif norm.startswith("memory/"):
        # 簡短格式 memory/filename.md → 自動對應至當前使用者的 memory 目錄
        target_abs = os.path.realpath(os.path.join(memory_dir_abs, norm[len("memory/"):]))
    elif norm.startswith("user_profiles/"):
        target_abs = os.path.realpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), norm
        ))
    else:
        # 路徑以 conversation_folder 為 base，artifacts/xxx 會正確解析至 artifacts/ 子目錄
        target_abs = os.path.realpath(os.path.join(conversation_folder, norm))

    # Memory 目錄寫入
    if target_abs.startswith(memory_dir_abs + os.sep) or target_abs == memory_dir_abs:
        filename = os.path.basename(target_abs)
        if filename == "MEMORY.md":
            return write_memory_index(user_id, content)
        return write_memory_file(user_id, filename, content)

    # 跨用戶存取保護
    if "user_profiles" in norm and not target_abs.startswith(memory_dir_abs):
        return "存取拒絕：不能存取其他使用者的目錄。"

    # 對話資料夾寫入（限 artifacts/ 子目錄）
    if not target_abs.startswith(artifacts_abs + os.sep):
        return "存取拒絕：只能寫入自己的對話 artifacts/ 資料夾或記憶目錄。"
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    if target_abs.endswith(".md"):
        from utils.signed_url import fix_md_relative_paths
        content = fix_md_relative_paths(content, target_abs)
    with open(target_abs, "w", encoding="utf-8") as f:
        f.write(content)

    # .md 寫入後觸發 sidebar 串流渲染
    if target_abs.endswith(".md") and session_id:
        md_id = f"md_{uuid.uuid4().hex[:8]}"
        safe_title = os.path.splitext(os.path.basename(target_abs))[0]
        _pending_md_renders[session_id] = {
            "md_id":            md_id,
            "markdown_content": content,
            "title":            safe_title,
            "file_path":        target_abs,
        }
        return f"已寫入：{os.path.basename(target_abs)} [RENDER_MARKDOWN_OK] md_id={md_id} title={safe_title}"

    return f"已寫入：{os.path.basename(target_abs)}"


@mcp.tool()
async def delete_file(
    path: str = Field(description=(
        "要刪除的檔案路徑：\n"
        "- 對話 artifacts 檔案：artifacts/output.md（需含 artifacts/ 前綴）\n"
        "- 記憶檔案：memory/filename.md\n"
        "  刪除記憶檔後需同步更新 MEMORY.md 移除對應條目"
    )),
) -> str:
    """刪除對話資料夾或記憶目錄中的指定檔案。"""
    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    conversation_folder = get_conversation_folder()

    norm = path.replace("\\", "/").lstrip("/")
    memory_dir_abs = os.path.realpath(get_user_memory_dir(user_id))
    conv_abs = os.path.realpath(conversation_folder)

    # 解析輸入路徑為絕對路徑
    if os.path.isabs(path):
        target_abs = os.path.realpath(path)
    elif norm.startswith("memory/"):
        # 簡短格式 memory/filename.md → 自動對應至當前使用者的 memory 目錄
        target_abs = os.path.realpath(os.path.join(memory_dir_abs, norm[len("memory/"):]))
    elif norm.startswith("user_profiles/"):
        target_abs = os.path.realpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), norm
        ))
    else:
        target_abs = os.path.realpath(os.path.join(conversation_folder, norm))

    # Memory 目錄
    if target_abs.startswith(memory_dir_abs + os.sep) or target_abs == memory_dir_abs:
        filename = os.path.basename(target_abs)
        filepath, err = validate_memory_path(user_id, filename)
        if err:
            return f"存取拒絕：{err}"
        if not os.path.exists(filepath):
            return f"記憶檔案不存在：{filename}"
        os.remove(filepath)
        return f"已刪除記憶檔案：{filename}（請記得更新 MEMORY.md）"

    # 跨用戶存取保護
    if "user_profiles" in norm and not target_abs.startswith(memory_dir_abs):
        return "存取拒絕：不能存取其他使用者的目錄。"

    # 對話資料夾刪除
    if not target_abs.startswith(conv_abs + os.sep):
        return "存取拒絕：只能刪除自己的對話資料夾或記憶目錄中的檔案。"
    if not os.path.exists(target_abs):
        return f"檔案不存在：{os.path.basename(target_abs)}"
    os.remove(target_abs)
    return f"已刪除：{os.path.basename(target_abs)}"


@mcp.tool()
async def capture_video_frames(
    video_path: str = Field(description="影片檔案路徑（相對於對話資料夾，或 artifacts/ 子路徑）"),
    timestamps: list[str] = Field(description=(
        "要截圖的時間點列表，支援格式：\n"
        "- 秒數字串：'10', '75.5'\n"
        "- HH:MM:SS 或 MM:SS：'00:01:30', '1:30'"
    )),
) -> str:
    """使用 ffmpeg 對影片指定時間點截圖，回傳 base64 編碼的圖片（儲存於 artifacts/）。

    回傳格式為 JSON：{"__image_files__": {timestamp: abs_path}, "summary": "..."}
    其中 timestamp 為輸入的時間點字串，abs_path 為截圖的絕對路徑（由 agent 自動讀入上下文）。
    """

    if not shutil.which("ffmpeg"):
        return "錯誤：找不到 ffmpeg，請確認系統已安裝 ffmpeg 並加入 PATH。"

    root_folder = get_conversation_folder()
    artifacts_dir = get_conversation_artifacts_dir(root_folder)

    # 解析影片路徑
    norm_video = video_path.replace("\\", "/").lstrip("/")
    if os.path.isabs(video_path):
        video_abs = os.path.realpath(video_path)
    else:
        video_abs = os.path.realpath(os.path.join(root_folder, norm_video))

    allowed_roots = [os.path.realpath(root_folder)]
    if not _check_path_in_allowed_roots(video_abs, allowed_roots):
        return "存取拒絕：只能存取對話資料夾中的影片。"

    if not os.path.isfile(video_abs):
        return f"影片檔案不存在：{video_path}"

    if not timestamps:
        return "錯誤：timestamps 不能為空。"

    os.makedirs(artifacts_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(video_abs))[0]

    successful_frames = []  # (timestamp, out_abs_path) 清單，用於後續 base64 讀取
    errors = []

    def _run_ffmpeg(ts: str, output_path: str):
        cmd = [
            "ffmpeg", "-y",
            "-ss", ts,
            "-i", video_abs,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return proc.returncode, proc.stderr

    for ts in timestamps:
        # 將時間點轉成安全的檔名片段（冒號換底線）
        ts_safe = ts.replace(":", "-").replace(".", "_")
        out_filename = f"{base_name}_frame_{ts_safe}.jpg"
        out_abs = os.path.join(artifacts_dir, out_filename)

        try:
            returncode, stderr = await asyncio.to_thread(_run_ffmpeg, ts, out_abs)
            if returncode == 0 and os.path.isfile(out_abs):
                successful_frames.append((ts, out_abs))
            else:
                errors.append(f"{ts}: ffmpeg 失敗 — {stderr.strip()[-200:]}")
        except subprocess.TimeoutExpired:
            errors.append(f"{ts}: 截圖逾時")
        except Exception as e:
            errors.append(f"{ts}: {str(e)}")

    # 生成摘要
    summary_lines = [f"截圖完成（{len(successful_frames)} 張）："]
    frames_paths: dict[str, str] = {}
    for ts, abs_path in successful_frames:
        summary_lines.append(f"  artifacts/{os.path.basename(abs_path)} (時間點: {ts})")
        frames_paths[ts] = abs_path
    if errors:
        summary_lines.append(f"\n失敗（{len(errors)} 筆）：")
        summary_lines.extend(f"  {e}" for e in errors)

    return json.dumps({
        "__image_files__": frames_paths,
        "summary": "\n".join(summary_lines),
    }, ensure_ascii=False)


@mcp.tool()
async def capture_ppt_slides(
    ppt_path: str = Field(description="PPT/PPTX 檔案路徑（相對於對話資料夾，例如 'uploads/slides.pptx' 或 'artifacts/report.ppt'）"),
    slides: list[int] = Field(
        default=[],
        description=(
            "要注入 LLM 上下文的投影片編號列表（從 1 開始）。\n"
            "留空（[]）表示只轉換存檔，不注入任何頁（適合先取得頁數清單再決定要看哪幾頁）。\n"
            "例如 [1, 3, 5] 表示只將第 1、3、5 張注入上下文。\n"
            "注意：所有投影片都會轉換並儲存到 artifacts/，summary 會列出完整路徑清單。"
        )
    ),
) -> str:
    """使用 soffice（LibreOffice）將 PPT/PPTX 轉為 PDF，再用 pymupdf 逐頁轉 PNG 儲存至 artifacts/。
    指定頁的圖片自動注入 LLM 上下文；summary 列出全部已生成路徑，後續看其他頁直接用 read_file 即可。

    回傳格式為 JSON：{"__image_files__": {slide_num: abs_path}, "summary": "..."}
    """
    import fitz  # pymupdf

    soffice = shutil.which("soffice") or shutil.which("soffice.bin")
    if not soffice:
        return "錯誤：找不到 soffice（LibreOffice），請確認系統已安裝 LibreOffice 並加入 PATH。"

    root_folder = get_conversation_folder()
    artifacts_dir = get_conversation_artifacts_dir(root_folder)

    norm_ppt = ppt_path.replace("\\", "/").lstrip("/")
    if os.path.isabs(ppt_path):
        ppt_abs = os.path.realpath(ppt_path)
    else:
        ppt_abs = os.path.realpath(os.path.join(root_folder, norm_ppt))

    if not _check_path_in_allowed_roots(ppt_abs, [os.path.realpath(root_folder)]):
        return "存取拒絕：只能存取對話資料夾中的 PPT 檔案。"

    if not os.path.isfile(ppt_abs):
        return f"PPT 檔案不存在：{ppt_path}"

    ext = os.path.splitext(ppt_abs)[1].lower()
    if ext not in (".ppt", ".pptx", ".odp"):
        return f"不支援的檔案格式：{ext}，請提供 .ppt、.pptx 或 .odp 檔案。"

    os.makedirs(artifacts_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(ppt_abs))[0]

    # Step 1：soffice 轉 PDF（暫存子目錄）
    tmp_dir = os.path.join(artifacts_dir, f"_ppt_tmp_{base_name}")
    os.makedirs(tmp_dir, exist_ok=True)

    def _run_soffice_pdf():
        cmd = [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp_dir, ppt_abs]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stdout, proc.stderr

    try:
        returncode, stdout, stderr = await asyncio.to_thread(_run_soffice_pdf)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return "錯誤：soffice 轉換逾時（超過 120 秒）。"
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return f"錯誤：執行 soffice 時發生例外：{str(e)}"

    if returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return f"soffice 轉換失敗（return code {returncode}）：\n{stderr.strip()[-500:]}"

    pdf_path = os.path.join(tmp_dir, f"{base_name}.pdf")
    if not os.path.isfile(pdf_path):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return f"soffice 執行成功但未找到輸出的 PDF 檔案。\nstdout: {stdout.strip()}\nstderr: {stderr.strip()}"

    # Step 2：pymupdf 逐頁轉 PNG，全部存入 artifacts/
    def _render_all_pages():
        doc = fitz.open(pdf_path)
        results: dict[int, str] = {}
        errors: list[str] = []
        mat = fitz.Matrix(2.0, 2.0)  # 2x 縮放 ≈ 192 dpi
        for i in range(doc.page_count):
            slide_num = i + 1
            dst_name = f"{base_name}_slide_{slide_num:03d}.png"
            dst_abs = os.path.join(artifacts_dir, dst_name)
            try:
                pix = doc[i].get_pixmap(matrix=mat, alpha=False)
                pix.save(dst_abs)
                results[slide_num] = dst_abs
            except Exception as e:
                errors.append(f"第 {slide_num} 張轉換失敗：{str(e)}")
        doc.close()
        return results, errors

    try:
        all_slide_map, render_errors = await asyncio.to_thread(_render_all_pages)
    except Exception as e:
        return f"錯誤：pymupdf 轉換時發生例外：{str(e)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not all_slide_map:
        return f"轉換失敗，未能產生任何投影片圖片。錯誤：{render_errors}"

    # 依 slides 參數過濾要注入上下文的頁；留空則不注入
    if slides:
        inject_map = {k: v for k, v in all_slide_map.items() if k in set(slides)}
        missing = sorted(set(slides) - set(all_slide_map.keys()))
    else:
        inject_map = {}
        missing = []

    total = len(all_slide_map)
    summary_lines = [
        f"PPT 轉換完成，共 {total} 張投影片，全部已儲存至 artifacts/。",
        "若需查看其他頁，直接用 read_file 讀取對應路徑，無需重新轉換：",
    ]
    for num, abs_path in sorted(all_slide_map.items()):
        summary_lines.append(f"  artifacts/{os.path.basename(abs_path)}")
    if missing:
        summary_lines.append(f"注意：指定頁 {missing} 超出範圍（共 {total} 張）。")
    if render_errors:
        summary_lines.extend(render_errors)
    summary_lines.append(f"已注入上下文的頁數：{sorted(inject_map.keys()) if inject_map else '（無）'}")

    return json.dumps({
        "__image_files__": {str(k): v for k, v in inject_map.items()},
        "summary": "\n".join(summary_lines),
    }, ensure_ascii=False)


@mcp.tool()
async def AskUserQuestion(
    form_schema: str = Field(
        description=(
            "問卷表單的 JSON 字串。格式範例：\n"
            '{"title": "標題", "description": "說明（可選）", "questions": [\n'
            '  {"id": "q1", "question": "完整問題？", "header": "短標籤",\n'
            '   "type": "single_choice",\n'
            '   "options": [{"label": "選項", "description": "說明（可選）"}],\n'
            '   "required": true, "other_option": true},\n'
            '  {"id": "q2", "question": "多選題？", "header": "Q2",\n'
            '   "type": "multi_choice",\n'
            '   "options": [{"label": "A"}, {"label": "B"}],\n'
            '   "required": false, "other_option": false},\n'
            '  {"id": "q3", "question": "選擇日期？", "header": "日期",\n'
            '   "type": "date", "required": true, "other_option": false}\n'
            "]}\n"
            "type 可為以下四種：\n"
            "  - single_choice：單選按鈕列表，建議 2–5 個選項\n"
            "  - multi_choice：多選 checkbox 列表，限制在 2–5 個選項（選項少、需一眼看清時使用）\n"
            "  - multi_select_dropdown：多選下拉選單，選項超過 5 個時使用（節省空間）\n"
            "  - date：日期選擇器（不需要 options）\n"
            "other_option 為 true 時會自動附加「其他」自由輸入框。\n"
            "required 為 true 時使用者必須填寫才能提交。"
        )
    )
) -> str:
    """
    Use this tool when you need to ask the user questions during execution. This allows you to:
    1. Gather user preferences or requirements
    2. Clarify ambiguous instructions
    3. Get decisions on implementation choices as you work
    4. Offer choices to the user about what direction to take.

    Usage notes:
    - Users will always be able to select "Other" to provide custom text input
    - Use multi_choice type to allow multiple answers to be selected for a question
    - If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label
    - 在 Chainlit 介面顯示動態互動表單，等待使用者填寫後回傳 JSON 字串
    """
    import chainlit as cl

    try:
        schema = json.loads(form_schema)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"form_schema 不是有效的 JSON：{e}"}, ensure_ascii=False)

    if not isinstance(schema.get("questions"), list) or not schema["questions"]:
        return json.dumps({"error": "questions 不能為空"}, ensure_ascii=False)

    ctx = _session_ctx.get()
    session_id = ctx.get("session_id", "")
    if not session_id:
        return json.dumps({"error": "無法取得 session_id，工具必須在 Chainlit session 中執行"}, ensure_ascii=False)

    if session_id in _pending_forms:
        return json.dumps({"error": "目前已有一個表單等待回應，請先完成或取消現有表單"}, ensure_ascii=False)

    form_id = str(uuid.uuid4())[:8]
    event = asyncio.Event()
    result_holder: dict = {"data": None, "cancelled": False}

    original_props = {
        **schema,
        "form_id": form_id,
        "submitted": False,
    }

    _pending_forms[session_id] = {
        "form_id": form_id,
        "event": event,
        "result": result_holder,
        "elem_id": None,
        "msg_id": None,
        "original_props": original_props,
    }

    try:
        elem = cl.CustomElement(
            name="DynamicForm",
            props=original_props,
            display="inline",
        )
        msg = await cl.Message(content="", elements=[elem]).send()

        _pending_forms[session_id]["elem_id"] = elem.id
        _pending_forms[session_id]["msg_id"] = msg.id

        try:
            await asyncio.wait_for(event.wait(), timeout=600.0)
        except asyncio.TimeoutError:
            return json.dumps({"error": "timeout", "message": "表單等待逾時（10 分鐘）"}, ensure_ascii=False)

        if result_holder["cancelled"]:
            return json.dumps({"cancelled": True, "message": "使用者取消了表單"}, ensure_ascii=False)

        return json.dumps({
            "cancelled": False,
            "answers": result_holder["data"],
        }, ensure_ascii=False, indent=2)

    finally:
        _pending_forms.pop(session_id, None)


@mcp.tool()
async def render_html(
    html_code: str = Field(
        description=(
            "要渲染的完整 HTML 文件字串。必須是可獨立執行的自包含文件，例如：\n"
            "<!DOCTYPE html><html><head>...</head><body>...</body></html>\n"
            "支援：\n"
            "- 純 HTML + CSS（含 <style> 標籤）\n"
            "- JavaScript（含 <script> 標籤）\n"
            "- CDN 引入（如 Chart.js、D3.js、Tailwind CSS、Mermaid.js 等）\n"
            "- SVG 圖形\n"
            "請盡量使用 CDN 引入函式庫，不要依賴本地資源。\n"
            "推薦 CDN 來源：https://cdn.jsdelivr.net、https://cdnjs.cloudflare.com、https://unpkg.com"
        )
    ),
    title: str = Field(
        default="Artifact",
        description="此 artifact 的標題，顯示在 sidebar 頂部，建議 20 字以內。"
    ),
) -> str:
    """在 Chainlit sidebar 中以沙盒 iframe 渲染 HTML/SVG/JavaScript 內容。
    適合用來展示：資訊視覺化、互動式 UI、圖表、SVG 圖形、靜態網頁、儀表板等。
    渲染後會顯示在右側 sidebar 供使用者即時查看，並支援版本歷史切換。
    """
    ctx = _session_ctx.get()
    session_id = ctx.get("session_id", "")
    if not session_id:
        return "錯誤：無法取得 session_id，render_html 只能在 Chainlit session 中使用。"

    if not html_code or not html_code.strip():
        return "錯誤：html_code 不能為空。"

    MAX_HTML_SIZE = 500 * 1024  # 500KB
    if len(html_code.encode("utf-8")) > MAX_HTML_SIZE:
        return "錯誤：HTML 內容超過 500KB 上限，請精簡後重試。"

    artifact_id = f"art_{uuid.uuid4().hex[:8]}"
    safe_title = (title or "Artifact").strip()

    # 若 html_code 缺少 CSP meta，自動注入白名單 CDN 的 CSP
    CSP_META = (
        '<meta http-equiv="Content-Security-Policy" content="'
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data: "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://unpkg.com https://d3js.org https://code.highcharts.com "
        "https://fonts.googleapis.com https://fonts.gstatic.com "
        "https://esm.sh https://esm.run;"
        '">'
    )
    if "<head" in html_code.lower() and "content-security-policy" not in html_code.lower():
        html_code = re.sub(
            r'(<head[^>]*>)',
            r'\1\n  ' + CSP_META,
            html_code,
            count=1,
            flags=re.IGNORECASE,
        )

    # 選擇性寫入磁碟，讓 Agent 後續可用 read_file 讀取並修改
    conversation_folder = ctx.get("conversation_folder", "")
    if conversation_folder:
        artifacts_dir = get_conversation_artifacts_dir(conversation_folder)
        os.makedirs(artifacts_dir, exist_ok=True)
        html_path = os.path.join(artifacts_dir, f"artifact_{artifact_id}.html")
        try:
            async with aiofiles.open(html_path, "w", encoding="utf-8") as f:
                await f.write(html_code)
        except Exception:
            pass  # 寫入失敗不影響渲染

    _pending_renders[session_id] = {
        "artifact_id": artifact_id,
        "html_code": html_code,
        "title": safe_title,
    }

    return f"[RENDER_HTML_OK] artifact_id={artifact_id} title={safe_title}"


@mcp.tool()
async def render_pptx(
    pptx_script: str = Field(
        description=(
            "完整的 pptxgenjs JavaScript 程式碼字串（不含 <script> 標籤）。\n"
            "必須使用 pptxgenjs API 建立投影片。CDN bundle 暴露的全域建構函式為 PptxGenJS（注意大小寫）。\n"
            "腳本最後必須呼叫 window.__pptxDone(prs) 傳回 PptxGenJS 實例，\n"
            "以便 element 觸發下載。\n"
            "圖片嵌入：若需嵌入對話資料夾中的圖片，在 addImage 的 path 欄位直接寫相對路徑。\n"
            "支援 uploads/ 和 artifacts/ 下的圖片，路徑相對於對話資料夾。\n"
            "例如：slide.addImage({ path: 'uploads/photo.png', x:1, y:1, w:4, h:3 })\n"
            "範例：\n"
            "  let prs = new PptxGenJS();\n"
            "  let slide = prs.addSlide();\n"
            "  slide.addText('Hello', {x:1, y:1, fontSize:36});\n"
            "  window.__pptxDone(prs);"
        )
    ),
    title: str = Field(
        default="簡報",
        description="簡報標題，顯示在 sidebar 頂部，建議 20 字以內。"
    ),
    slide_count: int = Field(
        default=1,
        description="預計的投影片張數（用於 sidebar 佔位顯示）。"
    ),
) -> str:
    """在 Chainlit sidebar 中執行 pptxgenjs 腳本並顯示投影片預覽，提供 .pptx 下載按鈕。
    使用 CDN 版本的 pptxgenjs（https://cdn.jsdelivr.net/gh/gitbrent/pptxgenjs/dist/pptxgen.bundle.js）。
    腳本需以 window.__pptxDone(prs) 傳回 PptxGenJS 實例才能觸發下載。
    """
    ctx = _session_ctx.get()
    session_id = ctx.get("session_id", "")
    if not session_id:
        return "錯誤：無法取得 session_id，render_pptx 只能在 Chainlit session 中使用。"

    if not pptx_script or not pptx_script.strip():
        return "錯誤：pptx_script 不能為空。"

    MAX_SCRIPT_SIZE = 200 * 1024  # 200KB
    if len(pptx_script.encode("utf-8")) > MAX_SCRIPT_SIZE:
        return "錯誤：pptx_script 超過 200KB 上限，請精簡腳本。"

    pptx_id = f"pptx_{uuid.uuid4().hex[:8]}"
    safe_title = (title or "簡報").strip()

    _pending_pptx_renders[session_id] = {
        "pptx_id": pptx_id,
        "pptx_script": pptx_script,
        "title": safe_title,
        "slide_count": max(1, int(slide_count)),
    }

    return f"[RENDER_PPTX_OK] pptx_id={pptx_id} title={safe_title}"


# ── 直接呼叫映射（供 buildin_tool_runner 使用，不走 MCP HTTP）──
_FUNC_MAP: dict = {
    "list_files": list_files,
    # "transcription": transcription,
    "read_file": read_file,
    "download_youtube": download_youtube,
    "list_youtube_subtitles": list_youtube_subtitles,
    # "attempt_completion": attempt_completion,
    # "query_employee": query_employee,
    "http_request": http_request,
    "activate_skill": activate_skill,
    "write_file": write_file,
    "delete_file": delete_file,
    "AskUserQuestion": AskUserQuestion,
    "capture_video_frames": capture_video_frames,
    "capture_ppt_slides": capture_ppt_slides,
    "render_html": render_html,
    "render_pptx": render_pptx,
}

if __name__ == "__main__":
    # 可以從資料庫取得使用者設定的prompt動態產生mcp tool
    # 這可以讓模型可以根據問題自動載入相關的prompt。這讓使用者可以用簡短的命令來觸發複雜的流程
    # 以下範例可以讓使用者輸入: "幫我請假" 觸發模型自主查看prompt來了解完整請假流程。
    # print(get_conversation_folder(ctx))
    # load_dotenv()

    register_mcp_tool(
        func_name="prompt_1", 
        describe="請假流程",  # 這會影響模型是否能根據情境選擇正確的prompt來閱讀
        return_string='''
            1. 先到myHR系統(http:myhr)點擊請假，未指定就預設選擇特休假，未指定日期預設為當天8點到17點。
            2. 保存假單->送簽
            3. 如果有截圖工具就到"已送出假單"的頁面中螢幕截圖給我確認
            4. 到部門的公用行事曆幫我標記請假，完成後螢幕截圖給我確認
        '''
    )
    mcp.run()
    # get_conversation_folder(ctx) = r'D:\Storage\ASUS F571GT\MyProjects\EnterpriseAI-Client\static'

    # parser = argparse.ArgumentParser(description="Run MCP Streamable HTTP based server")
    # parser.add_argument("--port", type=int, default=8123, help="Localhost port to listen on")
    # args = parser.parse_args()
    # import uvicorn
    # uvicorn.run(mcp.streamable_http_app, host="localhost", port=args.port)

    ## Test function:
    # import asyncio
    # subtitle = asyncio.run(test_download())
