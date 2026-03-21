import re
import os
import io
import time
import asyncio
import json
from mcp.server.fastmcp import Context, FastMCP
import requests
import argparse
from markitdown import MarkItDown
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
from pydub import AudioSegment
from pydantic import Field, BaseModel
import asyncio
import aiofiles
from utils.llm_client import get_llm_client, get_model_setting

mcp = FastMCP(name="buildin_tools", json_response=False, stateless_http=False)

# ── AgentSkills session registry ──
# 因為 buildin MCP server 是 in-process（同進程 HTTP transport），
# 無法透過 env var 傳遞資料，改用 module-level dict 按 session_id 儲存技能目錄。
_session_skill_catalogs: dict[str, str] = {}


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

@mcp.tool()
async def download_file_with_url(
    ctx: Context,
    url: str = Field(description="要下載的檔案網址連結")
):
    '''下載網路上的檔案連結到本次對話所屬資料夾'''
    root_folder = await get_conversation_folder(ctx)
    try:
        # 發送 GET 請求下載檔案
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # 從 URL 或 Content-Disposition header 中獲取檔案名稱
        filename = None
        if 'Content-Disposition' in response.headers:
            content_disposition = response.headers['Content-Disposition']
            if 'filename=' in content_disposition:
                filename = content_disposition.split('filename=')[1].strip('"')
        
        if not filename:
            # 從 URL 中提取檔案名稱
            filename = url.split('/')[-1]
            if '?' in filename:
                filename = filename.split('?')[0]
            if not filename or '.' not in filename:
                filename = 'downloaded_file'
        
        # 確保檔案路徑在 get_conversation_folder(ctx) 中
        file_path = os.path.join(root_folder, filename)
        
        # 確保目錄存在
        os.makedirs(root_folder, exist_ok=True)
        
        # 寫入檔案
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return f"檔案已成功下載到: {filename}"
    
    except requests.exceptions.RequestException as e:
        return f"下載失敗: {str(e)}"
    except Exception as e:
        return f"發生錯誤: {str(e)}"

@mcp.tool()
async def list_files(ctx: Context):
    '''列出本次對話資料夾中檔案'''
    root_folder = await get_conversation_folder(ctx)
    return await _list_files_internal(root_folder)

@mcp.tool()
async def transcription(
    ctx: Context,
    filename: str = Field(description="要轉錄的影音檔案名稱（支援 mp3, mp4, wav, m4a, webm, ogg 等格式）")
):
    '''將本次對話資料夾中的影音檔轉錄成文字稿'''
    root_folder = await get_conversation_folder(ctx)

    # 構建完整檔案路徑
    file_path = os.path.join(root_folder, filename)
    
    # 用非同步執行同步阻塞 I/O 檢查檔案是否存在
    file_exists = await asyncio.to_thread(os.path.exists, file_path)
    if not file_exists:
        return f"檔案不存在: {filename}"
    
    # 檢查檔案是否為支援的音訊格式
    supported_formats = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.ogg']
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in supported_formats:
        return f"不支援的檔案格式: {file_ext}。支援的格式: {', '.join(supported_formats)}"
    
    # 音頻壓縮處理（等效於 ffmpeg -i audio.mp3 -vn -map_metadata -1 -ac 1 -c:a libopus -b:a 12k -application voip audio.ogg）
    base_name = os.path.splitext(filename)[0]
    compressed_filename = f"{base_name}_compressed.ogg"
    compressed_path = os.path.join(root_folder, compressed_filename)
    
    try:
        # 音頻檔載入與轉換（同步，包在 to_thread 裡）
        def compress_audio():
            audio = AudioSegment.from_file(file_path)
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
        original_size = await asyncio.to_thread(os.path.getsize, file_path)
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
        transcription_file = file_path
    
    # 非同步讀取檔案並包成 BytesIO，因為 API 需要 file-like object
    async with aiofiles.open(transcription_file, 'rb') as f:
        audio_bytes = await f.read()
    audio_file_obj = io.BytesIO(audio_bytes)
    audio_file_obj.name = os.path.basename(transcription_file)  # 必須有檔名屬性
    
    # 初始化 OpenAI 客戶端
    client = get_llm_client(provider='openai', api_key=os.getenv('LLM_API_KEY'), base_url='https://api.openai.com/v1')
    
    # 呼叫 Whisper API（非同步）
    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file_obj,
        response_format="text"
    )
    # 生成轉錄檔案名稱
    transcript_filename = f"{base_name}_transcript.txt"
    transcript_path = os.path.join(root_folder, transcript_filename)
    
    # 保存轉錄結果到檔案
    async with aiofiles.open(transcript_path, 'w', encoding='utf-8') as f:
        await f.write(transcript)

    return transcript
    
@mcp.tool()
async def read_file(
    ctx: Context,
    filename: str = Field(description="要讀取的檔案名稱或路徑（支援 PDF, PowerPoint, Word, Excel, Images, HTML, CSV, JSON, XML, ZIP, EPub 等格式）")
):
    '''將檔案轉成 markdown 格式。支援對話資料夾內的檔案，以及自己的 user_profiles 技能資源。'''
    from utils.user_profile import get_user_profile_dir

    user_id = ctx.request_context.request.headers.get("X-User-Id", "")
    conversation_folder = await get_conversation_folder(ctx)

    norm = filename.replace("\\", "/").lstrip("/")

    if norm.startswith("user_profiles/"):
        file_path = norm  # 相對於專案根目錄
    else:
        file_path = os.path.join(conversation_folder, filename)

    # 存取控制：防路徑穿越 & 跨用戶
    abs_path = os.path.realpath(file_path)
    allowed_roots = [os.path.realpath(conversation_folder)]
    if user_id:
        allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))

    if not any(abs_path.startswith(r + os.sep) or abs_path == r for r in allowed_roots):
        return "存取拒絕：只能讀取自己的資料夾。"

    md = MarkItDown(enable_plugins=True)
    result = md.convert(abs_path)
    return result.text_content

async def download_youtube_sync(
    ctx: Context,
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
    output_dir = await get_conversation_folder(ctx)

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
            await ctx.info(f"Starting: 取影片資訊")
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
    ctx: Context,
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
    output_dir = await get_conversation_folder(ctx)
    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
    quiet = True

    if content_type == 'audio':
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
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
            'skip_download': True,
            'quiet': quiet,
        }
        ydl = YoutubeDL(ydl_opts)
        await ctx.info("Starting: 取影片資訊")

        info = await asyncio.to_thread(ydl.extract_info, url, download=False)
        video_title = info.get('title', 'Unknown')

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
    return f"下載完成，請查看資料夾中的檔案列表：\n{files_list}"

@mcp.tool()
async def list_youtube_subtitles(
    ctx: Context,
    url: str = Field(description="YouTube 影片網址")
):
    '''列出 YouTube 影片所有可用的字幕（包含官方字幕和自動產生的字幕）'''
    
    try:
        # 配置 ydl_opts 以獲取字幕信息
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,  # 只獲取信息，不下載
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

@mcp.tool()
async def attempt_completion(
    ctx: Context,
):
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


# ── AgentSkills：activate_skill 工具 ──
# 每個技能最多列出的資源檔案數，超過則截斷並提示
RESOURCES_MAX = 50

@mcp.tool()
async def activate_skill(
    ctx: Context,
    skill_name: str = Field(description="技能名稱，與可用技能清單中的 name 相同")
) -> str:
    """載入指定技能的完整指令。當任務符合某個技能的描述時呼叫此工具。"""

    session_id = ctx.request_context.request.headers.get("X-Session-Id")
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

    skill_dir_rel = os.path.relpath(skill.skill_dir, _project_root).replace("\\", "/")
    return (
        f"{body}\n\n"
        f"---\n"
        f"技能目錄: {skill_dir_rel}\n"
        f"可用資源: {json.dumps(resources_info, ensure_ascii=False)}"
    )

async def get_conversation_folder(ctx: Context):
    roots = await ctx.session.list_roots()
    conversation_folder = f'.files/{roots.roots[0].uri.host}'
    return conversation_folder

async def _list_files_internal(root_folder: str):
    """內部函數：列出指定資料夾中的檔案，供多個工具重用"""
    try:
        if not os.path.exists(root_folder):
            return "資料夾不存在"
        
        files = []
        for item in os.listdir(root_folder):
            item_path = os.path.join(root_folder, item)
            if os.path.isfile(item_path):
                # 獲取檔案大小
                size = os.path.getsize(item_path)
                size_str = f"{size:,} bytes"
                if size > 1024:
                    size_str = f"{size/1024:.1f} KB"
                if size > 1024*1024:
                    size_str = f"{size/(1024*1024):.1f} MB"
                
                files.append(f"{item} ({size_str})")
            elif os.path.isdir(item_path):
                files.append(f"{item}/ (資料夾)")
        
        if not files:
            return "資料夾是空的"
        
        return "檔案列表:\n" + "\n".join(files)
    
    except Exception as e:
        return f"列出檔案時發生錯誤: {str(e)}"

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
