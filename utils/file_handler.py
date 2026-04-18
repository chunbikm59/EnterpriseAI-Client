"""檔案處理純工具函數：偵測類型、編碼圖片、掃描資料夾狀態。"""

import asyncio
import base64
import mimetypes
import os

import aiofiles
from pygments.lexers import get_lexer_for_filename
from pygments.util import ClassNotFound

TEXT_PREVIEW_SIZE_LIMIT = 500_000  # 500 KB 以內才側邊欄預覽，超過仍走下載
_NO_FENCE_ALIASES = frozenset({'text', 'markdown', 'md'})  # 這些別名不加 code fence，直接讓 Chainlit 渲染 markdown


def _get_text_file_info(filename: str) -> tuple[bool, str | None]:
    """偵測檔案是否為文字/代碼，並回傳 code fence 語言別名（None 表示無需包裹）。"""
    try:
        lexer = get_lexer_for_filename(filename)
        alias = lexer.aliases[0] if lexer.aliases else None
        if alias in _NO_FENCE_ALIASES:
            alias = None
        return True, alias
    except ClassNotFound:
        mime = mimetypes.guess_type(filename)[0] or ''
        return mime.startswith('text/'), None


async def encode_image(image_path):
    """非同步編碼圖片為 base64，使用 aiofiles 進行非同步檔案讀取"""
    async with aiofiles.open(image_path, "rb") as image_file:
        image_data = await image_file.read()
        result = await asyncio.to_thread(base64.b64encode, image_data)
    return result.decode('utf-8')


async def get_files_state(folder_path):
    """取得資料夾中所有檔案的狀態（檔案名稱和修改時間）

    Args:
        folder_path: 資料夾路徑

    Returns:
        dict: {filename: mtime} 格式的字典，記錄每個檔案的修改時間
    """
    files_state = {}
    if folder_path and await asyncio.to_thread(os.path.exists, folder_path):
        file_list = await asyncio.to_thread(os.listdir, folder_path)
        for filename in file_list:
            file_path = os.path.join(folder_path, filename)
            if await asyncio.to_thread(os.path.isfile, file_path):
                mtime = await asyncio.to_thread(os.path.getmtime, file_path)
                files_state[filename] = mtime
    return files_state
