# ── 標準庫 ──
import asyncio
import logging
import os
import shutil
from typing import Dict, Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 第三方套件 ──
import chainlit as cl

# ── 註冊自定義 data layer（必須在 app 載入時 import，才能讓 @cl.data_layer 生效）──
import chainlit_app.data_layer  # noqa: F401


# ── 本專案：工具函數 ──
from mcp_servers.buildin import unregister_session_skills
from utils.conversation_storage import (
    finalize_conversation_file,
    init_conversation_file,
    append_entry,
    append_ui_event,
    append_message_edit,
    load_conversation_full,
    load_resume_data,
    read_title,
    _uuid_exists_in_jsonl,
)
import utils.conversation_manager as conversation_manager
from utils.user_profile import get_conversation_artifacts_dir

# ── 本專案：Chainlit app 子模組 ──
from chainlit_app.agent import run as agent, ENABLE_SESSION_HISTORY
from chainlit_app.conversation_history import (
    generate_conversation_title,
)
from chainlit_app.file_handler import process_uploaded_elements
from chainlit_app.session_state import _init_session_state
from chainlit.context import context as cl_context

from utils.llm_client import get_all_model_configs, get_model_config

# ── Action handlers（side effect: @cl.action_callback 登記）──
import chainlit_app.action_handlers  # noqa: F401

# ── Auth：OAuth provider 由 oauth_setup.py 根據環境變數自動載入 ──
import chainlit_app.oauth_setup  # noqa: F401

logger = logging.getLogger(__name__)

_THINKING_BUDGET_MAP = {"low": 1024, "medium": 8192, "max": -1}

async def _setup_modes():
    configs = get_all_model_configs()
    model_mode = cl.Mode(
        id="model",
        name="Model",
        options=[
            cl.ModeOption(id=name, name=cfg["display_name"], default=(i == 0))
            for i, (name, cfg) in enumerate(configs.items())
        ],
    )
    modes = [model_mode]
    if get_model_config(None).get("thinking_budget_tokens_enabled"):
        modes.append(cl.Mode(
            id="thinking_budget",
            name="思考深度",
            options=[
                cl.ModeOption(id="low",    name="Low",    description="快速回答"),
                cl.ModeOption(id="medium", name="Medium", description="均衡思考", default=True),
                cl.ModeOption(id="max",    name="Max",    description="無限制"),
            ],
        ))
    await cl.context.emitter.set_modes(modes)


@cl.on_chat_resume
async def on_chat_resume(thread):
    """Chainlit 資料持久化恢復時，自動載入最近一次的歷史對話（等同使用者手動 /resume 選第一筆）。"""
    userinfo = cl.user_session.get('user')
    await _init_session_state(userinfo)
    await _setup_modes()

    if not ENABLE_SESSION_HISTORY:
        return

    user_id = userinfo.identifier
    conv_id = thread.get("id", "")
    if not conv_id:
        return

    file_path = os.path.join(
        _PROJECT_ROOT, "user_profiles", user_id, "conversations", conv_id, "history.jsonl"
    )
    if not os.path.exists(file_path):
        return

    conversation_folder = os.path.join(_PROJECT_ROOT, 'user_profiles', user_id, 'conversations', conv_id)

    (restored_history, session_title, artifact_history), _, _ = await asyncio.gather(
        asyncio.to_thread(load_resume_data, file_path, conversation_folder),
        asyncio.to_thread(os.makedirs, os.path.join(conversation_folder, 'uploads'), exist_ok=True),
        asyncio.to_thread(os.makedirs, get_conversation_artifacts_dir(conversation_folder), exist_ok=True),
    )

    if not restored_history:
        return

    cl.user_session.set('conversation_id', conv_id)
    cl.user_session.set('file_folder', conversation_folder)
    cl.user_session.set('message_history', restored_history)
    cl.user_session.set('session_file', file_path)

    # msg_id_to_jsonl_uuid 無法從 JSONL 重建（Chainlit step id 未持久化），保持空 dict
    cl.user_session.set("msg_id_to_jsonl_uuid", {})

    title_str = f"「{session_title}」" if session_title else ""

    if artifact_history:
        cl.user_session.set("artifact_history", artifact_history)

    # UI 由框架的 emitter.resume_thread(thread) 透過 get_thread 傳回的 steps/elements 重建
    await cl.Message(content=f"已恢復對話{title_str}，可繼續對話。").send()


@cl.oauth_callback
def oauth_callback(
  provider_id: str,
  token: str,
  raw_user_data: Dict[str, str],
  default_user: cl.User,
) -> Optional[cl.User]:
  name = raw_user_data.get("name")
  if name:
    default_user.display_name = 'tester'
  return default_user


@cl.on_chat_start
async def start():
    userinfo = cl.user_session.get('user')
    await cl.Message(content=f'### 你好 {userinfo.identifier}，歡迎回來!　ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧').send()
    await _init_session_state(userinfo)
    await _setup_modes()


@cl.on_chat_end
async def end():
    session = cl_context.session
    if session and session.current_task and not session.current_task.done():
        session.current_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(session.current_task), timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    session_id = cl.user_session.get('id')
    unregister_session_skills(session_id)

    mcp_manager = cl.user_session.get('mcp_manager')
    if mcp_manager:
        await mcp_manager.shutdown()

    if ENABLE_SESSION_HISTORY:
        session_file = cl.user_session.get('session_file')
        if session_file:
            message_history = cl.user_session.get("message_history", [])
            _conv_id = cl.user_session.get('conversation_id', '')
            await asyncio.to_thread(finalize_conversation_file, session_file, _conv_id, len(message_history))
            if _conv_id:
                _total_prompt = cl.user_session.get("accumulated_prompt_tokens", 0)
                _total_completion = cl.user_session.get("accumulated_completion_tokens", 0)
                await asyncio.to_thread(
                    conversation_manager.finalize_conversation,
                    _conv_id, len(message_history),
                    _total_prompt, _total_completion
                )

    # 清除 Chainlit 暫存上傳目錄
    chainlit_tmp = os.path.join(os.getcwd(), '.files', cl.user_session.get('id'))
    if os.path.exists(chainlit_tmp):
        await asyncio.to_thread(shutil.rmtree, chainlit_tmp, ignore_errors=True)


@cl.on_settings_update
async def on_settings_update(settings):
    """處理設定變更，連線或斷線 MCP 伺服器"""
    print("設定已更新:", settings)

    previous_settings = cl.user_session.get('current_settings', {})
    cl.user_session.set('current_settings', settings)

    mcp_manager = cl.user_session.get('mcp_manager')
    if not mcp_manager:
        return

    chat_setting = cl.user_session.get('chat_setting')
    for element in chat_setting:
        element.initial = settings.get(element.id, False)

    from utils.mcp_servers_config import get_mcp_servers_config
    mcp_config = get_mcp_servers_config(cl.user_session.get('file_folder'))
    for server_name, config in mcp_config.items():
        if server_name == "buildin":
            continue
        setting_key = f"mcp_{server_name}"
        is_enabled = settings.get(setting_key, False)
        is_connected = mcp_manager.is_connected(server_name)

        if is_enabled and not is_connected:
            await mcp_manager.add_connection(server_name, config, headers={"X-Session-Id": cl.user_session.get('id'), "X-User-Id": cl.user_session.get('user').identifier})
            await cl.Message(content=f"⏳ 正在連線到 MCP 伺服器: {server_name}").send()
        elif not is_enabled and is_connected:
            await mcp_manager.remove_connection(server_name)
            await cl.Message(content=f"🔌 已斷線 MCP 伺服器: {server_name}").send()

    await mcp_manager.update_tools()


@cl.on_message
async def on_message(message: cl.Message):
    _eid = cl.user_session.get('user').identifier
    _conversation_folder = cl.user_session.get('file_folder', '')
    _session_file = cl.user_session.get('session_file')
    _conv_id = cl.user_session.get('conversation_id', '')

    message_history = cl.user_session.get("message_history", [])
    _msg_id_to_jsonl_uuid: dict = cl.user_session.get("msg_id_to_jsonl_uuid", {})

    # ── 偵測編輯：
    # 情況 A（本 session 新發送的訊息）：message.id 在 msg_id_to_jsonl_uuid 中
    # 情況 B（頁面重新整理後）：build_thread_steps_from_jsonl 用 JSONL uuid 當 step id，
    #   所以 message.id 本身就是 JSONL uuid，直接查 session_file 確認
    _original_jsonl_uuid: str | None = _msg_id_to_jsonl_uuid.get(message.id)
    if _original_jsonl_uuid is None and _session_file:
        # 嘗試把 message.id 當 JSONL uuid 去驗證
        _original_jsonl_uuid = await asyncio.to_thread(
            _uuid_exists_in_jsonl, _session_file, message.id
        )
    _is_edit = _original_jsonl_uuid is not None

    if _is_edit:
        if _session_file:
            await asyncio.to_thread(
                append_message_edit,
                _session_file, _conv_id, _eid,
                _original_jsonl_uuid,
                [{"type": "text", "text": message.content}],
            )
            # 從 JSONL 重建截斷後的 message_history
            message_history = await asyncio.to_thread(load_conversation_full, _session_file)

        # 清空映射表（舊的 step id 全部失效）
        cl.user_session.set("msg_id_to_jsonl_uuid", {})

        # 重算 user_message_count
        user_message_count = sum(1 for m in message_history if m.get("role") == "user")
        cl.user_session.set("user_message_count", user_message_count)
        cl.user_session.set("message_history", message_history)

    new_message = {
        "role": "user",
        "content": [{"type": "text", "text": message.content}]
    }
    uploaded_file_records = []
    if message.elements:
        extra_parts, uploaded_file_records = await process_uploaded_elements(
            message.elements,
            conversation_folder=_conversation_folder,
        )
        new_message['content'].extend(extra_parts)
    message_history.append(new_message)

    # 對話持久化：第一則訊息時才建立 JSONL
    if ENABLE_SESSION_HISTORY:
        if not _session_file:
            _pending_conv = cl.user_session.get('conversation_id_pending', _conv_id)
            _pending_uid = cl.user_session.get('user_id_pending', _eid)
            # 並行：建立 JSONL 檔 + 兩個資料夾（互不依賴）
            ((_session_file, is_new_session), _, _) = await asyncio.gather(
                asyncio.to_thread(init_conversation_file, _pending_uid, _pending_conv),
                asyncio.to_thread(os.makedirs, os.path.join(_conversation_folder, 'uploads'), exist_ok=True),
                asyncio.to_thread(os.makedirs, get_conversation_artifacts_dir(_conversation_folder), exist_ok=True),
            )
            cl.user_session.set('session_file', _session_file)
            if is_new_session:
                # 並行：寫入 system message（FS）+ 建立 DB 對話記錄（DB）
                initial_history = cl.user_session.get("message_history", [])
                system_entries = [e for e in initial_history if e["role"] == "system"]
                db_task = asyncio.to_thread(
                    conversation_manager.create_conversation, _pending_uid, _pending_conv
                )
                fs_tasks = [
                    asyncio.to_thread(
                        append_entry,
                        _session_file, _pending_conv, _pending_uid,
                        e["role"], e.get("content"),
                    )
                    for e in system_entries
                ]
                await asyncio.gather(db_task, *fs_tasks)
        if _session_file:
            _jsonl_uuid = await asyncio.to_thread(
                append_entry, _session_file, _conv_id, _eid,
                "user", new_message["content"],
            )
            # 記錄 Chainlit message id → JSONL uuid 映射
            _msg_id_to_jsonl_uuid[message.id] = _jsonl_uuid
            cl.user_session.set("msg_id_to_jsonl_uuid", _msg_id_to_jsonl_uuid)

            # 寫入 ui_event：使用者上傳
            if uploaded_file_records:
                # 轉為相對路徑儲存
                rel_records = []
                for rec in uploaded_file_records:
                    perm = rec.get("permanent_path", "")
                    rel = os.path.relpath(perm, _PROJECT_ROOT).replace("\\", "/") if perm else ""
                    rel_records.append({**rec, "permanent_path": rel})
                await asyncio.to_thread(append_ui_event, _session_file, "user_upload", {
                    "content": message.content,
                    "files": rel_records,
                })

    cl.user_session.set("message_history", message_history)

    # 第一條使用者訊息：背景生成 session 標題（編輯不重複觸發）
    if not _is_edit:
        user_message_count = cl.user_session.get("user_message_count", 0) + 1
        cl.user_session.set("user_message_count", user_message_count)
        if ENABLE_SESSION_HISTORY and user_message_count == 1 and _session_file:
            existing_title = await asyncio.to_thread(read_title, _session_file)
            if not existing_title:
                asyncio.ensure_future(generate_conversation_title(
                    conversation_file=_session_file,
                    conversation_id=_conv_id,
                    first_message=message.content,
                ))

    if message.modes:
        selected_model = message.modes.get("model")
        if selected_model:
            cl.user_session.set("selected_model", selected_model)
        thinking_level = message.modes.get("thinking_budget")
        if thinking_level:
            cl.user_session.set("thinking_budget_level", thinking_level)

    try:
        await agent(message_history)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await cl.Message(content=f"Error: {str(e)}").send()


if __name__ == '__main__':
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
