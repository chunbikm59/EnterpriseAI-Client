"""上傳檔案永久儲存工具（純檔案操作，無 DB）。"""
import os
import re
import shutil
from datetime import datetime, timezone, timedelta


def make_safe_filename(name: str) -> str:
    """去除路徑分隔符，保留中文、英數、底線、點、連字號，截 100 字元。"""
    name = os.path.basename(name.replace("\\", "/"))
    safe = re.sub(r'[^\w.\-\u4e00-\u9fff\u3400-\u4dbf\u20000-\u2a6df]', '_', name)
    return safe[:100] if safe else "unnamed"


def _timestamp() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y%m%dT%H%M%S")


def get_upload_path(conversation_folder: str, original_name: str) -> str:
    """回傳永久上傳路徑：{conversation_folder}/uploads/{timestamp}_{safe_name}"""
    safe = make_safe_filename(original_name)
    ts = _timestamp()
    return os.path.join(conversation_folder, "uploads", f"{ts}_{safe}")


def move_to_permanent(src: str, conversation_folder: str, original_name: str) -> str:
    """將 src 檔案複製到永久位置，回傳 permanent_path（絕對路徑）。

    保留原始暫存檔讓 Chainlit 能繼續提供即時預覽；暫存檔由 on_chat_end 統一清除。
    """
    dst = get_upload_path(conversation_folder, original_name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return dst
