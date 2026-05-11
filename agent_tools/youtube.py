import os
import re
import asyncio
from pydantic import Field
from yt_dlp import YoutubeDL
from agent_tools._context import mcp, _session_ctx, get_conversation_folder, _list_files_internal
from utils.user_profile import get_conversation_artifacts_dir


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
    """下載 YouTube 影片成音訊、影片或字幕"""
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

        if subtitle_lang:
            subtitles_langs = [subtitle_lang]
        else:
            subtitles_langs = ['zh-TW', 'zh-Hant', 'zh-CN', 'zh-Hans', 'zh', 'en']

        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
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
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'ignore_no_formats_error': True,
        }

        def extract_subtitles_info():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info

        info = await asyncio.to_thread(extract_subtitles_info)

        video_title = info.get('title', 'Unknown')
        video_duration = info.get('duration', 0)

        result = f"🎬 YouTube 影片字幕列表\n"
        result += f"{'='*50}\n"
        result += f"影片標題: {video_title}\n"
        result += f"影片時長: {video_duration // 60} 分 {video_duration % 60} 秒\n"
        result += f"{'='*50}\n\n"

        subtitles = info.get('subtitles', {})
        automatic_captions = info.get('automatic_captions', {})

        if subtitles:
            result += "📝 官方字幕 (Manually Created Subtitles):\n"
            result += "-" * 50 + "\n"
            for lang_code in subtitles.keys():
                result += f"  • {lang_code}\n"
            result += "\n"
        else:
            result += "📝 官方字幕: 無\n\n"

        if automatic_captions:
            result += "🤖 自動產生的字幕 (Auto-generated Captions):\n"
            result += "-" * 50 + "\n"
            for lang_code in automatic_captions.keys():
                result += f"  • {lang_code}\n"
            result += "\n"
        else:
            result += "🤖 自動產生的字幕: 無\n\n"

        total_subtitles = len(subtitles) + len(automatic_captions)
        result += "=" * 50 + "\n"
        result += f"總計: {len(subtitles)} 個官方字幕 + {len(automatic_captions)} 個自動字幕\n"
        result += f"共 {total_subtitles} 個字幕軌道\n"

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
