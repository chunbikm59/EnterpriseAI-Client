"""檔案處理純工具函數：偵測類型、編碼圖片、掃描資料夾狀態。"""

import asyncio
import base64
import io
import mimetypes
import os

import aiofiles
from PIL import Image
from pygments.lexers import get_lexer_for_filename
from pygments.util import ClassNotFound

_MAX_IMAGE_SIDE = 1280
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


def _resize_image_bytes(data: bytes, mime: str | None = None) -> bytes:
    """若圖片最長邊 > _MAX_IMAGE_SIDE，以等比縮放壓縮後回傳新 bytes；否則原樣回傳。"""
    img = Image.open(io.BytesIO(data))
    w, h = img.size
    if max(w, h) <= _MAX_IMAGE_SIDE:
        return data
    scale = _MAX_IMAGE_SIDE / max(w, h)
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    fmt = img.format or ("PNG" if (mime or "").endswith("png") else "JPEG")
    img.save(buf, format=fmt)
    return buf.getvalue()


async def encode_image(image_path, mime: str | None = None):
    """非同步編碼圖片為 base64，超過 1024px 的圖片會先等比縮放。"""
    async with aiofiles.open(image_path, "rb") as image_file:
        image_data = await image_file.read()
    image_data = await asyncio.to_thread(_resize_image_bytes, image_data, mime)
    result = await asyncio.to_thread(base64.b64encode, image_data)
    return result.decode('utf-8')


async def get_files_state(folder_path):
    """取得資料夾中所有檔案的狀態（檔案名稱和修改時間）

    Returns:
        dict: {filename: mtime}
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
