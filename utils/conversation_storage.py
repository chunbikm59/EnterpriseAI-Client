"""對話記錄持久化模組。

將 message_history 以 JSONL 格式即時寫入：
    user_profiles/{employee_id}/conversations/{conversation_id}/history.jsonl

JSONL 記錄類型：
  session_meta - 第一行，會話元資料
  message      - LLM 對話訊息（role/content/tool_calls）
  ui_event     - UI 狀態記錄（step/message/user_upload/sidebar_update）
  title        - 自動生成標題（append-only，取最後一筆）
"""
import base64
import copy
import datetime
import json
import mimetypes
import os
import uuid
from typing import Any, Dict, List, Optional

from utils.user_profile import get_user_conversations_dir
from utils.models import PublishedArtifact
from utils.db import SessionLocal


def _now_iso() -> str:
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz=tz).isoformat()


def _safe_id(id_str: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in id_str)


def get_conversation_file_path(employee_id: str, conversation_id: str) -> str:
    """取得 JSONL 檔案的絕對路徑。"""
    conversations_dir = get_user_conversations_dir(employee_id)
    return os.path.join(conversations_dir, _safe_id(conversation_id), "history.jsonl")


def init_conversation_file(employee_id: str, conversation_id: str) -> tuple:
    """建立 JSONL 檔案並寫入 conversation_meta 記錄。

    若檔案已存在則直接回傳路徑。
    回傳 (file_path, is_new)：is_new=False 代表已存在，呼叫方應跳過初始訊息寫入。
    """
    file_path = get_conversation_file_path(employee_id, conversation_id)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    if os.path.exists(file_path):
        return file_path, False

    meta = {
        "record_type": "session_meta",
        "conversation_id": conversation_id,
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
    conversation_id: str,
    employee_id: str,
    role: str,
    content: Any,
    tool_calls: Optional[List[Dict]] = None,
    tool_call_id: Optional[str] = None,
    image_paths: Optional[List[str]] = None,
) -> str:
    """將一條 LLM 訊息寫入 JSONL，回傳此記錄的 uuid。"""
    record = {
        "record_type": "message",
        "uuid": str(uuid.uuid4()),
        "conversation_id": conversation_id,
        "employee_id": employee_id,
        "timestamp": _now_iso(),
        "role": role,
        "content": _sanitize_content(content),
    }
    if tool_calls is not None:
        record["tool_calls"] = tool_calls
    if tool_call_id is not None:
        record["tool_call_id"] = tool_call_id
    if image_paths:
        record["image_paths"] = image_paths

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

    return record["uuid"]


def append_ui_event(file_path: str, event_type: str, data: dict) -> None:
    """寫入一筆 UI 狀態記錄，用於歷史還原時重建 UI。"""
    record = {
        "record_type": "ui_event",
        "event_type": event_type,
        "timestamp": _now_iso(),
        **data,
    }
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def append_ui_message(
    file_path: str,
    content: str,
    msg_id: str | None = None,
    elements: list | None = None,
    actions: list | None = None,
) -> None:
    """寫入一筆帶 actions 的 UI 訊息記錄。

    actions 接受兩種格式：
      - cl.Action 物件（有 .name / .label / .payload 屬性）
      - dict（已含 name / label / payload 欄位）
    """
    def _serialize(a) -> dict:
        if isinstance(a, dict):
            return {"name": a.get("name", ""), "label": a.get("label", ""), "payload": a.get("payload", {})}
        return {"name": a.name, "label": a.label, "payload": a.payload}

    append_ui_event(file_path, "message", {
        "chainlit_msg_id": msg_id,
        "content": content,
        "elements": elements or [],
        "actions": [_serialize(a) for a in (actions or [])],
    })


def finalize_conversation_file(file_path: str, conversation_id: str, total_messages: int) -> None:
    """更新第一行的 ended_at，標記對話結束。"""
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

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLACEHOLDER = "[IMAGE_BASE64_OMITTED]"


def _resolve_permanent_path(permanent_path: str) -> str:
    if os.path.isabs(permanent_path):
        return permanent_path
    return os.path.join(_PROJECT_ROOT, permanent_path)


def _encode_image_file(abs_path: str) -> str:
    mime = mimetypes.guess_type(abs_path)[0] or "image/jpeg"
    with open(abs_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def _restore_image_content(content: Any, image_paths: List[str]) -> Any:
    """將 content 中的佔位符依序替換為從磁碟重新編碼的 base64 data URL。"""
    if not isinstance(content, list) or not image_paths:
        return content
    result = []
    img_iter = iter(image_paths)
    for item in content:
        if (
            isinstance(item, dict)
            and item.get("type") == "image_url"
            and isinstance(item.get("image_url"), dict)
            and item["image_url"].get("url") == _PLACEHOLDER
        ):
            abs_path = next(img_iter, None)
            if abs_path and os.path.exists(abs_path):
                item = copy.deepcopy(item)
                item["image_url"]["url"] = _encode_image_file(abs_path)
            # 若檔案不存在則保留佔位符（不中斷）
        result.append(item)
    return result


def _read_raw_records(file_path: str) -> list:
    """讀取 JSONL 並回傳所有 records，供多個 load 函數共用。"""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            records = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records
    except Exception:
        return []


def _build_history_from_raw(raw_records: list) -> List[Dict]:
    """從已讀取的 raw_records 組裝 message_history。"""
    _, active_messages, upload_inheritance = _replay_records(raw_records)

    # 建立所有 user message uuid 集合（含歷史被截斷的），用於 upload_map 查找
    # upload_inheritance: 新 uuid → 舊 uuid（新訊息繼承舊訊息的 upload）
    all_relevant_uuids = {
        rec["uuid"] for rec in active_messages
        if rec.get("role") == "user" and rec.get("uuid")
    } | set(upload_inheritance.values())

    # 掃描全部 raw_records，建立 uuid → upload paths 映射
    # user_upload ui_event 緊跟在對應的 user message 之後
    upload_map: Dict[str, List[str]] = {}
    for i, rec in enumerate(raw_records):
        if (
            rec.get("record_type") == "message"
            and rec.get("role") == "user"
            and rec.get("uuid") in all_relevant_uuids
            and i + 1 < len(raw_records)
        ):
            nxt = raw_records[i + 1]
            if nxt.get("record_type") == "ui_event" and nxt.get("event_type") == "user_upload":
                paths = [
                    _resolve_permanent_path(f["permanent_path"])
                    for f in nxt.get("files", [])
                    if f.get("permanent_path")
                ]
                if paths:
                    upload_map[rec["uuid"]] = paths

    # 繼承：新 user uuid 沒有直接的 upload，但舊 uuid 有，則繼承
    for new_uid, old_uid in upload_inheritance.items():
        if new_uid not in upload_map and old_uid in upload_map:
            upload_map[new_uid] = upload_map[old_uid]

    # 組裝 message_history
    history: List[Dict] = []
    seen_system = False
    for rec in active_messages:
        role = rec.get("role")
        if role == "system":
            if seen_system:
                continue
            seen_system = True

        content = rec.get("content")
        uid = rec.get("uuid")
        if role == "user" and uid in upload_map:
            content = _restore_image_content(content, upload_map[uid])
        elif role == "assistant" and rec.get("image_paths"):
            abs_image_paths = [_resolve_permanent_path(p) for p in rec["image_paths"]]
            content = _restore_image_content(content, abs_image_paths)

        entry: Dict[str, Any] = {"role": role, "content": content}
        if "tool_calls" in rec:
            entry["tool_calls"] = rec["tool_calls"]
        if "tool_call_id" in rec:
            entry["tool_call_id"] = rec["tool_call_id"]

        history.append(entry)

    return history


def load_conversation_full(file_path: str) -> List[Dict]:
    """載入 JSONL 並還原圖片 base64，使 LLM 上下文與原始完全一致。"""
    return _build_history_from_raw(_read_raw_records(file_path))


def _uuid_exists_in_jsonl(file_path: str, target_uuid: str) -> str | None:
    """在 JSONL 中確認 uuid 存在且為 user role message，回傳該 uuid 或 None。"""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or target_uuid not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("uuid") == target_uuid and rec.get("record_type") == "message" and rec.get("role") == "user":
                    return target_uuid
    except Exception:
        pass
    return None


def append_message_edit(
    file_path: str,
    conversation_id: str,
    employee_id: str,
    edited_message_uuid: str,
    new_content: Any,
) -> None:
    """寫入 message_edit 記錄：只記被編輯訊息的 uuid 與新內容。"""
    record = {
        "record_type": "message_edit",
        "timestamp": _now_iso(),
        "conversation_id": conversation_id,
        "employee_id": employee_id,
        "edited_message_uuid": edited_message_uuid,
        "new_content": _sanitize_content(new_content),
    }
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def _replay_records(raw_records: list) -> tuple:
    """重播 JSONL records，回傳 (non_msg_recs, active_messages, upload_inheritance)。

    upload_inheritance: dict[新 uuid → 舊 uuid]
      當 message_edit 截斷了一條帶有 upload 的 user message，
      新的 user message uuid 需要繼承那個舊 uuid 的 upload 資訊。
    """
    from collections import OrderedDict
    msg_order: OrderedDict = OrderedDict()  # uuid → rec，保持插入順序
    non_msg: list = []
    # 舊 uuid（被截斷的 user message）→ 緊接在其後的新 user message uuid
    upload_inheritance: dict = {}

    i = 0
    while i < len(raw_records):
        rec = raw_records[i]
        rt = rec.get("record_type")

        if rt == "message":
            uid = rec.get("uuid")
            if uid:
                msg_order[uid] = rec
            i += 1

        elif rt == "message_edit":
            target_uuid = rec.get("edited_message_uuid")
            # 記錄被截斷的 user uuid（可能帶有 upload）
            cut_user_uuid: str | None = None
            if target_uuid and target_uuid in msg_order:
                keys = list(msg_order.keys())
                cut = keys.index(target_uuid)
                # 找到被截斷位置的 user message uuid
                for k in keys[cut:]:
                    if msg_order[k].get("role") == "user":
                        cut_user_uuid = k
                        break
                for k in keys[cut:]:
                    del msg_order[k]
            # 繼續往後加入 message records，直到下一個 message_edit
            i += 1
            first_new_user: str | None = None
            while i < len(raw_records):
                nxt = raw_records[i]
                if nxt.get("record_type") == "message_edit":
                    break
                if nxt.get("record_type") == "message":
                    uid = nxt.get("uuid")
                    if uid:
                        msg_order[uid] = nxt
                        # 新區段第一條 user message 繼承被截斷的 user upload
                        if first_new_user is None and nxt.get("role") == "user" and cut_user_uuid:
                            first_new_user = uid
                            upload_inheritance[uid] = cut_user_uuid
                else:
                    non_msg.append((i, nxt))
                i += 1

        else:
            non_msg.append((i, rec))
            i += 1

    active_messages = list(msg_order.values())
    non_msg_recs = [r for _, r in non_msg]
    return non_msg_recs, active_messages, upload_inheritance


def append_title(file_path: str, conversation_id: str, title: str) -> None:
    """追加 title entry（append-only，讀取時取最後一筆）。"""
    record = {
        "record_type": "title",
        "conversation_id": conversation_id,
        "title": title,
        "generated_at": _now_iso(),
    }
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def _build_artifacts_from_raw(raw_records: list, conversation_folder: str) -> list:
    """從已讀取的 raw_records 掃出 ArtifactChip 記錄並讀回 html。"""
    artifacts_dir = os.path.join(conversation_folder, "artifacts")
    seen = set()
    ordered = []
    try:
        for rec in raw_records:
            if rec.get("record_type") != "ui_event" or rec.get("event_type") != "message":
                continue
            for el in rec.get("elements", []):
                if el.get("kind") != "custom" or el.get("name") != "ArtifactChip":
                    continue
                props = el.get("props", {})
                artifact_id = props.get("payload", {}).get("artifact_id", "") or props.get("artifact_id", "")
                title = props.get("title", artifact_id)
                if not artifact_id or artifact_id in seen:
                    continue
                html_path = os.path.join(artifacts_dir, f"artifact_{artifact_id}.html")
                if not os.path.exists(html_path):
                    continue
                with open(html_path, encoding="utf-8") as hf:
                    html_code = hf.read()
                seen.add(artifact_id)
                ordered.append({"artifact_id": artifact_id, "html_code": html_code, "title": title})
    except Exception:
        return []
    ordered.reverse()

    if ordered:
        ids = [a["artifact_id"] for a in ordered]
        try:
            with SessionLocal() as session:
                rows = session.query(
                    PublishedArtifact.artifact_id,
                    PublishedArtifact.token,
                ).filter(PublishedArtifact.artifact_id.in_(ids)).all()
            base_url = os.getenv("CHAINLIT_URL", "http://localhost:8000")
            url_map = {r.artifact_id: f"{base_url}/p/{r.token}" for r in rows}
            for a in ordered:
                if a["artifact_id"] in url_map:
                    a["published_url"] = url_map[a["artifact_id"]]
        except Exception:
            pass

    return ordered


def _build_title_from_raw(raw_records: list) -> Optional[str]:
    """從已讀取的 raw_records 取最後一筆 title entry。"""
    last_title = None
    for rec in raw_records:
        if rec.get("record_type") == "title":
            last_title = rec.get("title")
    return last_title


def load_artifact_history(file_path: str, conversation_folder: str) -> list:
    """從 JSONL 掃出所有 ArtifactChip 記錄，按對話順序從磁碟讀回 html。
    回傳格式與 artifact_history session 一致：[{artifact_id, html_code, title}, ...]
    最新的排在 index 0。
    """
    return _build_artifacts_from_raw(_read_raw_records(file_path), conversation_folder)


def read_title(file_path: str) -> Optional[str]:
    """從 JSONL 讀取最後一筆 title entry。"""
    return _build_title_from_raw(_read_raw_records(file_path))


def load_resume_data(file_path: str, conversation_folder: str) -> tuple:
    """一次讀 JSONL，同時回傳 (message_history, title, artifact_history)。
    供 on_chat_resume 使用，避免重複讀取同一個檔案。
    """
    raw_records = _read_raw_records(file_path)
    if not raw_records:
        return [], None, []
    history = _build_history_from_raw(raw_records)
    title = _build_title_from_raw(raw_records)
    artifacts = _build_artifacts_from_raw(raw_records, conversation_folder)
    return history, title, artifacts


def list_user_conversations(
    employee_id: str,
    offset: int = 0,
    limit: int = 10,
) -> Dict:
    """列出用戶歷史對話摘要，依 mtime 降序，支援分頁。

    兩階段策略：
    1. stat-only 掃描取 mtime 排序
    2. 只對當頁少數檔案做完整讀取
    """
    conversations_dir = get_user_conversations_dir(employee_id)
    if not os.path.exists(conversations_dir):
        return {"conversations": [], "total": 0, "offset": offset, "limit": limit, "has_more": False}

    candidates = []
    try:
        with os.scandir(conversations_dir) as it:
            for conv_entry in it:
                if not conv_entry.is_dir():
                    continue
                history_path = os.path.join(conv_entry.path, "history.jsonl")
                try:
                    st = os.stat(history_path)
                    candidates.append((history_path, st.st_mtime))
                except OSError:
                    continue
    except OSError:
        return {"conversations": [], "total": 0, "offset": offset, "limit": limit, "has_more": False}

    candidates.sort(key=lambda x: x[1], reverse=True)
    total = len(candidates)
    page_candidates = candidates[offset: offset + limit]

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

            conv_id = meta.get("conversation_id", "")
            results.append({
                "conversation_id": conv_id,
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
        "conversations": results,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total,
    }
