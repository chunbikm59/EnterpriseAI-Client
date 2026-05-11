import os
from utils.user_profile import (
    get_user_memory_dir, get_user_skills_dir,
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _check_path_in_allowed_roots(abs_path: str, allowed_roots: list[str]) -> bool:
    """檢查 abs_path 是否位於 allowed_roots 中的任何一個根目錄下（含根目錄本身）。
    所有路徑參數皆應已經過 os.path.realpath 解析。
    """
    return any(
        abs_path.startswith(r + os.sep) or abs_path == r
        for r in allowed_roots
    )


def _resolve_file_path(path: str, base_folder: str, strip_trailing_slash: bool = False) -> str:
    """將輸入路徑正規化並解析為絕對路徑。
    - 處理反斜線、前導斜線
    - 若為相對路徑，以 base_folder 為 base
    - 若為絕對路徑，直接 realpath
    回傳值已經過 os.path.realpath 解析。
    """
    norm = path.replace("\\", "/").lstrip("/")
    if strip_trailing_slash:
        norm = norm.rstrip("/")
    if os.path.isabs(path):
        return os.path.realpath(path)
    return os.path.realpath(os.path.join(base_folder, norm))


def _resolve_user_path(path: str, user_id: str, conversation_folder: str) -> str:
    """解析支援前綴簡寫的使用者路徑為絕對路徑。
    支援前綴：memory/、skills/、system_skills/、user_profiles/，其餘以 conversation_folder 為 base。
    回傳值已經過 os.path.realpath 解析。
    """
    norm = path.replace("\\", "/").lstrip("/")
    if os.path.isabs(path):
        return os.path.realpath(path)
    if norm.startswith("memory/"):
        return os.path.realpath(os.path.join(
            get_user_memory_dir(user_id), norm[len("memory/"):]
        ))
    if norm.startswith("skills/"):
        return os.path.realpath(os.path.join(
            get_user_skills_dir(user_id), norm[len("skills/"):]
        ))
    if norm.startswith("system_skills/"):
        return os.path.realpath(os.path.join(_PROJECT_ROOT, norm))
    if norm.startswith("user_profiles/"):
        return os.path.realpath(os.path.join(_PROJECT_ROOT, norm))
    return os.path.realpath(os.path.join(conversation_folder, norm))
