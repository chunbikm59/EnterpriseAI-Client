import os
import pathlib
import re
import urllib.parse

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent

# 安全邊界字元：路徑不可能繼續延伸的字元（空白、括號、引號）
_SAFE_BOUNDARY = re.compile(r'[ \n\r\t\)\]\"\']')


def user_file_url(path: str) -> str:
    """產生 /api/user-files/ URL（由 cookie JWT 認證，無需簽名）。"""
    p = pathlib.Path(path)
    rel = p.relative_to(_PROJECT_ROOT).as_posix() if p.is_absolute() else p.as_posix()
    base_url = os.getenv("CHAINLIT_URL", "http://localhost:8000")
    return f"{base_url}/api/user-files/{rel}"


def rewrite_artifact_paths(text: str, user_id: str, conv_id: str) -> str:
    """將 LLM 回應中的相對路徑替換為完整 /api/user-files/ 路徑（不帶 host）。

    artifacts/filename → /api/user-files/user_profiles/{uid}/conversations/{cid}/artifacts/filename
    uploads/filename   → /api/user-files/user_profiles/{uid}/conversations/{cid}/uploads/filename
    """
    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
    base = f"/api/user-files/user_profiles/{safe_uid}/conversations/{conv_id}"

    text = re.sub(
        r'(?<![/\w])artifacts/([^\s\)\]"\']+)',
        lambda m: f"{base}/artifacts/{m.group(1)}",
        text,
    )
    text = re.sub(
        r'(?<![/\w])uploads/([^\s\)\]"\']+)',
        lambda m: f"{base}/uploads/{m.group(1)}",
        text,
    )
    return text


def rewrite_relative_paths_in_md(text: str, md_abs_path: str) -> str:
    """將 markdown 內容中的相對路徑替換為 /api/user-files/ URL。

    根據 md_abs_path 所在目錄解析相對路徑，只處理實際存在於磁碟的檔案。
    不影響已是絕對路徑、http(s)://、錨點或 data: URI 的連結。
    """
    md_dir = os.path.dirname(md_abs_path)

    def replace_path(m: re.Match) -> str:
        rel = m.group(1)
        if rel.startswith(("/", "http://", "https://", "#", "data:")):
            return m.group(0)
        decoded = urllib.parse.unquote(rel)
        abs_path = os.path.normpath(os.path.join(md_dir, decoded))
        if not os.path.isfile(abs_path):
            return m.group(0)
        return m.group(0).replace(rel, user_file_url(abs_path))

    def replace_autolink(m: re.Match) -> str:
        rel = m.group(1)
        if rel.startswith(("/", "http://", "https://", "#", "data:")):
            return m.group(0)
        decoded = urllib.parse.unquote(rel)
        abs_path = os.path.normpath(os.path.join(md_dir, decoded))
        if not os.path.isfile(abs_path):
            return m.group(0)
        return f"<{user_file_url(abs_path)}>"

    text = re.sub(r'!?\[[^\]]*\]\(([^)]+)\)', replace_path, text)
    text = re.sub(r'<([^>]+)>', replace_autolink, text)
    return text


def fix_md_relative_paths(content: str, md_abs_path: str) -> str:
    """修復 MD 檔案中錯誤的相對路徑前綴。

    當 MD 寫入 artifacts/ 時，LLM 有時會錯誤地加上 artifacts/ 或 uploads/ 前綴：
      artifacts/image.png  →  image.png            （同目錄圖片）
      uploads/photo.jpg    →  ../uploads/photo.jpg  （上層 uploads 目錄）
    只修復路徑實際存在於磁碟的情況，避免誤改合法連結。
    """
    md_dir = os.path.dirname(md_abs_path)
    parent_dir = os.path.dirname(md_dir)

    def fix_path(rel: str) -> str:
        if rel.startswith(("/", "http://", "https://", "#", "data:")):
            return rel
        decoded = urllib.parse.unquote(rel)
        if decoded.startswith("artifacts/") or decoded.startswith("uploads/"):
            candidate = os.path.normpath(os.path.join(parent_dir, decoded))
            if os.path.isfile(candidate):
                return os.path.relpath(candidate, md_dir).replace("\\", "/")
        return rel

    def replace_in_link(m: re.Match) -> str:
        rel = m.group(1)
        fixed = fix_path(rel)
        if fixed == rel:
            return m.group(0)
        return m.group(0).replace(rel, fixed, 1)

    return re.sub(r'!?\[[^\]]*\]\(([^)]+)\)', replace_in_link, content)


class StreamingPathRewriter:
    """在 LLM stream 過程中即時轉換路徑，等遇到安全邊界字元才 flush 輸出。

    保證：只有在路徑必定已完整（後面跟著空白/括號/引號）時才輸出，
    避免路徑被截斷後提前轉換。
    """

    def __init__(self, user_id: str, conv_id: str):
        safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
        self._base = f"/api/user-files/user_profiles/{safe_uid}/conversations/{conv_id}"
        self._buffer = ""
        self._full_output = ""

    def _rewrite(self, text: str) -> str:
        text = re.sub(
            r'(?<![/\w])artifacts/([^\s\)\]"\']+)',
            lambda m: f"{self._base}/artifacts/{m.group(1)}",
            text,
        )
        text = re.sub(
            r'(?<![/\w])uploads/([^\s\)\]"\']+)',
            lambda m: f"{self._base}/uploads/{m.group(1)}",
            text,
        )
        return text

    def feed(self, token: str) -> str:
        """送入一個 token，回傳可安全輸出的已轉換字串（可能為空）。"""
        self._buffer += token
        last_safe = -1
        for m in _SAFE_BOUNDARY.finditer(self._buffer):
            last_safe = m.end()
        if last_safe == -1:
            return ""
        chunk = self._buffer[:last_safe]
        self._buffer = self._buffer[last_safe:]
        converted = self._rewrite(chunk)
        self._full_output += converted
        return converted

    def flush(self) -> str:
        """stream 結束時強制輸出剩餘 buffer（對末尾無終止符的情況）。"""
        if not self._buffer:
            return ""
        converted = self._rewrite(self._buffer)
        self._full_output += converted
        self._buffer = ""
        return converted

    @property
    def full_output(self) -> str:
        """目前為止所有已輸出的轉換後內容，用於持久化至對話歷史。"""
        return self._full_output
