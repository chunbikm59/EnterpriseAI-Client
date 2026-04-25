"""歷史對話功能：顯示清單、還原 UI、生成標題。"""
import asyncio
import json
import mimetypes
import os
import uuid
import json

import chainlit as cl

import utils.conversation_manager as conversation_manager
from utils.signed_url import user_file_url
from utils.llm_client import get_llm_client, get_model_setting
from utils.conversation_storage import append_title, list_user_conversations, _replay_records

ENABLE_SESSION_HISTORY = os.environ.get("ENABLE_SESSION_HISTORY", "true").lower() in ("1", "true", "yes")
CONVERSATION_PAGE_SIZE = 10
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_thread_steps_from_jsonl(jsonl_path: str, thread_id: str, identifier: str):
    """讀取 JSONL，回傳 (steps, elements) 供 get_thread 填入 ThreadDict。
    邏輯與 restore_session_ui 完全對應，這是唯一的重建來源。
    """
    from chainlit.step import StepDict
    from chainlit.element import ElementDict

    _image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
    steps: list[StepDict] = []
    elements: list[ElementDict] = []

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            raw_records = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return steps, elements

    _, active_messages, _ = _replay_records(raw_records)
    active_uuids = {rec["uuid"] for rec in active_messages if rec.get("uuid")}

    # 重建有效的完整 records 序列（message + 相鄰的 ui_event）
    # ui_event 只納入 active range 內（第一個 active non-system message 的 index 之後）
    first_active_idx = next(
        (i for i, r in enumerate(raw_records)
         if r.get("record_type") == "message"
         and r.get("role") != "system"
         and r.get("uuid") in active_uuids),
        len(raw_records)
    )
    active_records = []
    for i, rec in enumerate(raw_records):
        rt = rec.get("record_type")
        if rt == "message":
            if rec.get("uuid") in active_uuids:
                active_records.append(rec)
        elif rt == "ui_event" and i >= first_active_idx:
            evt = rec.get("event_type")
            if evt == "user_upload" and i > 0:
                prev = raw_records[i - 1]
                if prev.get("record_type") == "message" and prev.get("role") == "user":
                    user_uuid = prev.get("uuid")
                    if user_uuid not in active_uuids:
                        continue  # 對應的 user message 已被截斷，跳過此 upload
                    rec = dict(rec, _user_uuid=user_uuid)
            active_records.append(rec)

    queued_user_text: str | None = None
    queued_user_uuid: str | None = None

    def _new_id() -> str:
        return str(uuid.uuid4())

    def _make_element(kind: str, name: str, abs_path: str, for_id: str, mime: str | None = None) -> ElementDict | None:
        if not os.path.exists(abs_path):
            return None
        ext = os.path.splitext(name)[1].lower()
        el_type = "image" if (kind == "image" or ext in _image_exts) else "file"
        d: ElementDict = {
            "id": _new_id(),
            "threadId": thread_id,
            "type": el_type,
            "name": name,
            "display": "inline",
            "url": user_file_url(abs_path),
            "forId": for_id,
        }
        if mime:
            d["mime"] = mime
        return d

    def _flush_user(text: str, msg_uuid: str | None = None) -> str:
        """建立 user_message step，以 JSONL uuid 為 step id（使 edit_message 可直接對應）。"""
        sid = msg_uuid or _new_id()
        steps.append(StepDict(
            id=sid,
            threadId=thread_id,
            name=identifier,
            type="user_message",
            input="",
            output=text,
            createdAt="",
        ))
        return sid

    for rec in active_records:
        rec_type = rec.get("record_type")

        if rec_type == "ui_event":
            evt = rec.get("event_type")

            if evt == "step":
                if queued_user_text:
                    _flush_user(queued_user_text, queued_user_uuid)
                    queued_user_text = None
                    queued_user_uuid = None
                sid = _new_id()
                steps.append(StepDict(
                    id=sid,
                    threadId=thread_id,
                    name=rec.get("step_name", "工具"),
                    type="tool",
                    input=json.dumps(rec.get("input", {}), ensure_ascii=False)[:500],
                    output=rec.get("output", ""),
                    createdAt="",
                    showInput="json",
                ))

            elif evt == "message":
                if queued_user_text:
                    _flush_user(queued_user_text, queued_user_uuid)
                    queued_user_text = None
                    queued_user_uuid = None
                sid = _new_id()
                steps.append(StepDict(
                    id=sid,
                    threadId=thread_id,
                    name="Assistant",
                    type="assistant_message",
                    input="",
                    output=rec.get("content", ""),
                    createdAt="",
                ))
                for el_rec in rec.get("elements", []):
                    kind = el_rec.get("kind", "")
                    name = el_rec.get("name", "file")

                    # custom element（如 ArtifactChip）不需要磁碟路徑，直接從 props 重建
                    if kind == "custom":
                        elements.append(ElementDict(
                            id=_new_id(),
                            threadId=thread_id,
                            type="custom",
                            name=name,
                            display=el_rec.get("display", "inline"),
                            props=el_rec.get("props", {}),
                            forId=sid,
                        ))
                        continue

                    abs_path = os.path.join(_PROJECT_ROOT, el_rec.get("permanent_path", ""))
                    kind = kind or ("image" if os.path.splitext(name)[1].lower() in _image_exts else "file")
                    mime = el_rec.get("mime")
                    el = _make_element(kind, name, abs_path, sid, mime)
                    if el:
                        elements.append(el)

            elif evt == "user_upload":
                # 用 JSONL uuid 當 step id，使 edit_message 可對應
                sid = rec.get("_user_uuid") or queued_user_uuid or _new_id()
                queued_user_text = None
                queued_user_uuid = None
                upload_els: list[ElementDict] = []
                for f_rec in rec.get("files", []):
                    abs_path = os.path.join(_PROJECT_ROOT, f_rec.get("permanent_path", ""))
                    orig = f_rec.get("original_name", "file")
                    ext = os.path.splitext(orig)[1].lower()
                    kind = "image" if ext in _image_exts else "file"
                    mime = mimetypes.guess_type(orig)[0] or "application/octet-stream"
                    el = _make_element(kind, orig, abs_path, sid, mime)
                    if el:
                        upload_els.append(el)
                steps.append(StepDict(
                    id=sid,
                    threadId=thread_id,
                    name=identifier,
                    type="user_message",
                    input="",
                    output=rec.get("content", ""),
                    createdAt="",
                ))
                elements.extend(upload_els)

            elif evt == "sidebar_update":
                pass  # sidebar 狀態不需要重建進 steps

        elif rec_type == "message":
            role = rec.get("role")
            if role == "user":
                if queued_user_text:
                    _flush_user(queued_user_text, queued_user_uuid)
                content = rec.get("content", "")
                text = (
                    content if isinstance(content, str)
                    else " ".join(
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                )
                queued_user_text = text or None
                queued_user_uuid = rec.get("uuid") or None
            elif role == "assistant":
                if queued_user_text:
                    _flush_user(queued_user_text, queued_user_uuid)
                    queued_user_text = None
                    queued_user_uuid = None
                content = rec.get("content", "")
                if content and isinstance(content, str) and content.strip():
                    sid = _new_id()
                    steps.append(StepDict(
                        id=sid,
                        threadId=thread_id,
                        name="Assistant",
                        type="assistant_message",
                        input="",
                        output=content,
                        createdAt="",
                    ))

    if queued_user_text:
        _flush_user(queued_user_text, queued_user_uuid)

    return steps, elements


async def generate_conversation_title(conversation_file: str, conversation_id: str, first_message: str) -> None:
    """用 LLM 生成對話標題，並同步寫入 JSONL 及 DB。在背景執行，不阻塞主流程。"""
    try:
        text = first_message.strip()[:500]
        client = get_llm_client(mode="async")
        model_setting = get_model_setting()
        response = await client.chat.completions.create(
            model=model_setting["model"],
            temperature=0.3,
            stream=False,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一個對話標題生成助手。"
                        "根據使用者的第一條訊息，生成一個簡短的繁體中文標題（5到15個字）。"
                        "回傳 JSON 格式：{\"title\": \"生成的標題\"}"
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        title = data.get("title", "").strip()
        if title:
            await asyncio.to_thread(append_title, conversation_file, conversation_id, title)
            await asyncio.to_thread(
                conversation_manager.update_conversation_title, conversation_id, title
            )
    except Exception:
        pass
