import re
import os
import io
import time
import asyncio
import json
from fastmcp import Context, FastMCP
import requests
import argparse
from markitdown import MarkItDown
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
from pydub import AudioSegment
from pydantic import Field
import asyncio
import aiofiles
from openai import AsyncOpenAI

mcp = FastMCP(name="buildin_tools", json_response=False, stateless_http=False)

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
    # 初始化 OpenAI 客戶端
    client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
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
    
    # 初始化 OpenAI 客戶端
    client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # 非同步讀取檔案並包成 BytesIO，因為 API 需要 file-like object
    async with aiofiles.open(transcription_file, 'rb') as f:
        audio_bytes = await f.read()
    audio_file_obj = io.BytesIO(audio_bytes)
    audio_file_obj.name = os.path.basename(transcription_file)  # 必須有檔名屬性

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

    # 清理壓縮檔案（可選）
    if transcription_file == compressed_path:
        try:
            await asyncio.to_thread(os.remove, compressed_path)
            print(f"已清理臨時壓縮檔案: {compressed_filename}")
        except Exception:
            pass

    return transcript
    
@mcp.tool()
async def read_file(
    ctx: Context,
    filename: str = Field(description="要轉換的檔案名稱（支援 PDF, PowerPoint, Word, Excel, Images, HTML, CSV, JSON, XML, ZIP, EPub 等格式）")
):
    '''將本次對話資料夾中檔案轉成markdown格式。支援PDF, PowerPoint, Word, Excel, Images, HTML Text-based formats (CSV, JSON, XML), ZIP files (iterates over contents), EPubs'''
    md = MarkItDown(enable_plugins=True)
    file_path = os.path.join(await get_conversation_folder(ctx), filename)
    result = md.convert(file_path)    

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
                return f"字幕下載完成，但無法讀取字幕內容。請檢查資料夾中的字幕檔案。"
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
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': False,
            'subtitleslangs': ['zh-TW', 'zh-Hant', 'zh-CN', 'zh-Hans', 'zh', 'en'],
            'subtitlesformat': 'srt',
            'outtmpl': subtitle_template,
            'skip_download': True,
            'quiet': quiet,
        }
        ydl = YoutubeDL(ydl_opts)
        await ctx.info("Starting: 取影片資訊")

        info = await asyncio.to_thread(ydl.extract_info, url, False)
        video_title = info.get('title', 'Unknown')

        await asyncio.to_thread(ydl.download, [url])

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
async def sleep_10second():
    await asyncio.sleep(10) # 保持原樣，讓我們的執行器來處理同步阻塞
    return "woke up"

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
