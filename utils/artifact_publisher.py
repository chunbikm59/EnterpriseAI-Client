import json
import pathlib
import shutil
import threading
import uuid
from datetime import datetime, timezone, timedelta

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent
_PUBLISHED_DIR = _PROJECT_ROOT / "published"
_INDEX_FILE = _PUBLISHED_DIR / "index.json"
_TZ_TAIPEI = timezone(timedelta(hours=8))
_lock = threading.Lock()


def _read_index() -> dict:
    try:
        with open(_INDEX_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_index(index: dict) -> None:
    _PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _INDEX_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_INDEX_FILE)


def publish_artifact(
    artifact_id: str,
    title: str,
    user_id: str,
    html_path: str,
) -> str:
    """將 artifact HTML 複製到公開目錄，回傳 token（重複發布回傳舊 token）。"""
    with _lock:
        index = _read_index()

        # 重複發布保護：同 artifact_id 已有 token 直接回傳
        for token, meta in index.items():
            if meta.get("artifact_id") == artifact_id:
                return token

        token = uuid.uuid4().hex
        _PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
        dest = _PUBLISHED_DIR / f"{token}.html"
        shutil.copy2(html_path, dest)

        index[token] = {
            "artifact_id": artifact_id,
            "title": title,
            "user_id": user_id,
            "published_at": datetime.now(_TZ_TAIPEI).isoformat(),
            "html_file": f"{token}.html",
        }
        _write_index(index)
        return token


def get_published_html_path(token: str) -> pathlib.Path | None:
    """給 token 回傳 published HTML 檔案的絕對路徑，不存在回傳 None。"""
    if not token or not all(c in "0123456789abcdef" for c in token) or len(token) != 32:
        return None
    path = _PUBLISHED_DIR / f"{token}.html"
    return path if path.is_file() else None
