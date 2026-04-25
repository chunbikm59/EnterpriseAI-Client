"""
偵錯/測試用 API：模擬 Chainlit on_message、取得 JSONL、查看 session 狀態。
掛載於 /api/debug（僅限開發環境使用）。
"""
import asyncio
import json
import os
import pathlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from chainlit.session import WebsocketSession, ws_sessions_id
from chainlit.context import init_ws_context
from chainlit.chat_context import chat_context
import chainlit as cl

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────

def _find_session_by_thread(thread_id: str) -> WebsocketSession | None:
    """找到目前持有指定 thread_id 的 WebsocketSession。"""
    for sess in list(ws_sessions_id.values()):
        if sess.thread_id == thread_id:
            return sess
    return None


def _jsonl_path(user_id: str, conversation_id: str) -> pathlib.Path:
    return _PROJECT_ROOT / "user_profiles" / user_id / "conversations" / conversation_id / "history.jsonl"


# ── 1. 列出所有 active sessions ──────────────────────────────────────────

@router.get("/sessions")
async def list_sessions():
    """列出所有目前 active 的 WebsocketSession。"""
    result = []
    for sess in ws_sessions_id.values():
        uid = sess.user.identifier if sess.user else None
        result.append({
            "session_id": sess.id,
            "thread_id": sess.thread_id,
            "user": uid,
        })
    return result


# ── 2. 取得 JSONL 內容 ───────────────────────────────────────────────────

@router.get("/jsonl/{user_id}/{conversation_id}")
async def get_jsonl(user_id: str, conversation_id: str):
    """回傳指定對話的 JSONL，每行解析成 JSON 物件。"""
    path = _jsonl_path(user_id, conversation_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"JSONL not found: {path}")
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    records.append({"_raw": line})
    return {"path": str(path), "count": len(records), "records": records}


# ── 3. 取得 session 的 user_session 變數 ─────────────────────────────────

@router.get("/session-state/{thread_id}")
async def get_session_state(thread_id: str):
    """回傳指定 thread_id 的 user_session 關鍵變數。"""
    sess = _find_session_by_thread(thread_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"No active session for thread_id={thread_id!r}")

    init_ws_context(sess)
    return {
        "session_id": sess.id,
        "thread_id": thread_id,
        "session_file": cl.user_session.get("session_file"),
        "conversation_id": cl.user_session.get("conversation_id"),
        "msg_id_to_jsonl_uuid": cl.user_session.get("msg_id_to_jsonl_uuid", {}),
        "user_message_count": cl.user_session.get("user_message_count", 0),
        "message_history_len": len(cl.user_session.get("message_history", [])),
    }


# ── 4. 取得 chat_context messages（Chainlit 內部狀態）────────────────────

@router.get("/chat-context/{thread_id}")
async def get_chat_context(thread_id: str):
    """回傳指定 thread 的 chat_context message list（id + content 摘要）。"""
    sess = _find_session_by_thread(thread_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"No active session for thread_id={thread_id!r}")

    init_ws_context(sess)
    messages = chat_context.get()
    return {
        "thread_id": thread_id,
        "count": len(messages),
        "messages": [
            {
                "id": m.id,
                "type": getattr(m, "type", None),
                "content": (m.content or "")[:80],
            }
            for m in messages
        ],
    }


# ── 5. 發送訊息到指定對話（模擬 on_message）────────────────────────────

class SendMessageRequest(BaseModel):
    content: str

@router.post("/send/{thread_id}")
async def send_message(thread_id: str, req: SendMessageRequest):
    """對指定 thread 的 active session 發送訊息，觸發 on_message。"""
    sess = _find_session_by_thread(thread_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"No active session for thread_id={thread_id!r}")

    from chainlit.config import config
    init_ws_context(sess)

    msg = cl.Message(content=req.content)
    # 模擬 process_message 的流程：先 send（取得 id），再呼叫 on_message
    await msg.send()

    if config.code.on_message:
        await config.code.on_message(msg)

    return {"sent_message_id": msg.id, "content": req.content}


# ── 6. 模擬編輯訊息（核心測試目標）────────────────────────────────────

class EditMessageRequest(BaseModel):
    message_id: str   # 要編輯的原始 message id（JSONL uuid 或 step id）
    new_content: str

@router.post("/edit/{thread_id}")
async def edit_message(thread_id: str, req: EditMessageRequest):
    """
    模擬 Chainlit edit_message socket event：
    1. 在 chat_context 找到 message_id
    2. 把它後面的訊息全部 remove
    3. 更新內容
    4. 呼叫 on_message
    回傳偵測到的 is_edit 結果（從 session_file 驗證）。
    """
    sess = _find_session_by_thread(thread_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"No active session for thread_id={thread_id!r}")

    from chainlit.config import config
    init_ws_context(sess)

    messages = chat_context.get()
    orig_message = None
    removed_ids = []

    for m in messages:
        if orig_message is not None:
            removed_ids.append(m.id)
            await m.remove()
        if m.id == req.message_id:
            m.content = req.new_content
            await m.update()
            orig_message = m

    if orig_message is None:
        return {
            "error": "message_id not found in chat_context",
            "chat_context_ids": [m.id for m in messages],
            "requested_id": req.message_id,
        }

    result: dict[str, Any] = {
        "found": True,
        "orig_message_id": orig_message.id,
        "removed_count": len(removed_ids),
        "removed_ids": removed_ids,
    }

    if config.code.on_message:
        await config.code.on_message(orig_message)

    # 讀取 JSONL 確認是否有寫入 message_edit
    session_file = cl.user_session.get("session_file")
    if session_file and os.path.exists(session_file):
        with open(session_file, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        edit_records = [r for r in lines if r.get("record_type") == "message_edit"]
        result["message_edit_records_in_jsonl"] = edit_records
    else:
        result["message_edit_records_in_jsonl"] = []

    return result
