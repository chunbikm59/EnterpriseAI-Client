"""對話記錄持久化模組。

將 Chainlit 的 message_history 以 JSONL 格式即時寫入：
    user_profiles/{employee_id}/sessions/{session_id}.jsonl

JSONL 格式：
  第一行 - session_meta：會話元資料（started_at、ended_at 等）
  中間行 - message：每條對話訊息
  最後行 - session_end：會話結束標記
"""
import copy
import datetime
import glob
import json
import os
import uuid
from typing import Any, Dict, List, Optional

from utils.user_profile import get_user_sessions_dir


def _now_iso() -> str:
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz=tz).isoformat()


def _safe_session_id(session_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)


def get_session_file_path(employee_id: str, session_id: str) -> str:
    """取得 JSONL 檔案的絕對路徑。"""
    sessions_dir = get_user_sessions_dir(employee_id)
    safe_sid = _safe_session_id(session_id)
    return os.path.join(sessions_dir, f"{safe_sid}.jsonl")


def init_session(employee_id: str, session_id: str) -> tuple:
    """建立 JSONL 檔案並寫入 session_meta 記錄。

    若檔案已存在（例如頁面重整），直接回傳路徑不覆寫。
    回傳 (file_path, is_new)：is_new=False 代表檔案已存在，呼叫方應跳過初始訊息寫入。
    """
    sessions_dir = get_user_sessions_dir(employee_id)
    os.makedirs(sessions_dir, exist_ok=True)

    file_path = get_session_file_path(employee_id, session_id)

    if os.path.exists(file_path):
        return file_path, False

    meta = {
        "record_type": "session_meta",
        "session_id": session_id,
        "employee_id": employee_id,
        "started_at": _now_iso(),
        "ended_at": None,
        "title": None,
    }
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")

    return file_path, True


def _sanitize_content(content: Any) -> Any:
    """將 content 中的 base64 圖片 URL 替換為占位符（不修改原物件）。"""
    if content is None or isinstance(content, str):
        return content

    if isinstance(content, list):
        result = []
        for item in content:
            if (
                isinstance(item, dict)
                and item.get("type") == "image_url"
                and isinstance(item.get("image_url"), dict)
                and str(item["image_url"].get("url", "")).startswith("data:")
            ):
                item = copy.deepcopy(item)
                item["image_url"]["url"] = "[IMAGE_BASE64_OMITTED]"
            result.append(item)
        return result

    return content


def append_entry(
    file_path: str,
    session_id: str,
    employee_id: str,
    role: str,
    content: Any,
    tool_calls: Optional[List[Dict]] = None,
    tool_call_id: Optional[str] = None,
) -> str:
    """將一條訊息寫入 JSONL 檔案。

    回傳此記錄的 uuid。
    """
    record = {
        "record_type": "message",
        "uuid": str(uuid.uuid4()),
        "session_id": session_id,
        "employee_id": employee_id,
        "timestamp": _now_iso(),
        "role": role,
        "content": _sanitize_content(content),
    }
    if tool_calls is not None:
        record["tool_calls"] = tool_calls
    if tool_call_id is not None:
        record["tool_call_id"] = tool_call_id

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

    return record["uuid"]


def finalize_session(file_path: str, session_id: str, total_messages: int) -> None:
    """更新第一行的 ended_at，標記會話結束。"""
    if not os.path.exists(file_path):
        return

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return

    try:
        meta = json.loads(lines[0])
        meta["ended_at"] = _now_iso()
        lines[0] = json.dumps(meta, ensure_ascii=False) + "\n"
    except (json.JSONDecodeError, KeyError):
        return

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def load_session(file_path: str) -> List[Dict]:
    """載入 JSONL 檔案，回傳可直接用於 LLM API 的 message_history 格式。

    跳過 session_meta 和 session_end，只回傳 message 記錄。
    """
    if not os.path.exists(file_path):
        return []

    history = []
    seen_system = False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if record.get("record_type") != "message":
                    continue

                role = record["role"]

                # 頁面重整可能造成 JSONL 中有多組 system/assistant 初始訊息，只保留第一組
                if role == "system":
                    if seen_system:
                        continue  # 跳過重複的 system prompt
                    seen_system = True

                entry: Dict[str, Any] = {
                    "role": role,
                    "content": record.get("content"),
                }
                if "tool_calls" in record:
                    entry["tool_calls"] = record["tool_calls"]
                if "tool_call_id" in record:
                    entry["tool_call_id"] = record["tool_call_id"]

                history.append(entry)
    except Exception:
        return []

    return history


def append_title(file_path: str, session_id: str, title: str) -> None:
    """追加 title entry 到 JSONL 末尾（append-only，可多次更新，讀取時取最後一筆）。"""
    record = {
        "record_type": "title",
        "session_id": session_id,
        "title": title,
        "generated_at": _now_iso(),
    }
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def read_title(file_path: str) -> Optional[str]:
    """從 JSONL 讀取最後一筆 title entry。"""
    if not os.path.exists(file_path):
        return None
    last_title = None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("record_type") == "title":
                    last_title = record.get("title")
    except Exception:
        return None
    return last_title


def list_user_sessions(
    employee_id: str,
    offset: int = 0,
    limit: int = 10,
) -> Dict:
    """列出用戶歷史會話摘要，依 mtime 降序排列，支援分頁。

    採用兩階段策略：
    1. 先用 os.scandir() 取所有 .jsonl 的 mtime（不開檔），排序後取當頁範圍
    2. 只對當頁的少數檔案做完整讀取

    回傳格式：
    {
        "sessions": [...],
        "total": int,
        "offset": int,
        "limit": int,
        "has_more": bool,
    }
    """
    sessions_dir = get_user_sessions_dir(employee_id)
    if not os.path.exists(sessions_dir):
        return {"sessions": [], "total": 0, "offset": offset, "limit": limit, "has_more": False}

    # 階段一：stat-only 掃描，取 mtime 排序
    candidates = []
    try:
        with os.scandir(sessions_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith(".jsonl"):
                    try:
                        candidates.append((entry.path, entry.stat().st_mtime))
                    except OSError:
                        continue
    except OSError:
        return {"sessions": [], "total": 0, "offset": offset, "limit": limit, "has_more": False}

    # 依 mtime 降序排列
    candidates.sort(key=lambda x: x[1], reverse=True)
    total = len(candidates)

    # 取當頁範圍
    page_candidates = candidates[offset: offset + limit]

    # 階段二：只讀當頁的檔案
    results = []
    for file_path, _ in page_candidates:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                continue

            meta = json.loads(lines[0])
            if meta.get("record_type") != "session_meta":
                continue

            message_count = 0
            last_edited_at = meta.get("started_at", "")
            title = None
            if len(lines) > 1:
                try:
                    for l in lines:
                        if '"record_type": "message"' in l or '"record_type":"message"' in l:
                            message_count += 1
                    # 從後往前：取最後一條 message 的 timestamp，以及最後一筆 title entry
                    for l in reversed(lines):
                        l = l.strip()
                        if not l:
                            continue
                        try:
                            rec = json.loads(l)
                        except json.JSONDecodeError:
                            continue
                        rec_type = rec.get("record_type")
                        if title is None and rec_type == "title":
                            title = rec.get("title")
                        if last_edited_at == meta.get("started_at", "") and rec_type == "message" and rec.get("timestamp"):
                            last_edited_at = rec["timestamp"]
                        if title is not None and last_edited_at != meta.get("started_at", ""):
                            break
                except Exception:
                    pass

            results.append({
                "session_id": meta.get("session_id", ""),
                "file_path": file_path,
                "started_at": meta.get("started_at", ""),
                "ended_at": meta.get("ended_at"),
                "last_edited_at": last_edited_at,
                "title": title,
                "message_count": message_count,
            })
        except Exception:
            continue

    return {
        "sessions": results,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total,
    }
