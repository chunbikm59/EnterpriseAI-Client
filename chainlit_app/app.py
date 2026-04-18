# ── 標準庫 ──
import asyncio
import datetime
import json
import logging
import os
import uuid
from typing import Dict, Optional

# ── 第三方套件 ──
import aiofiles
import chainlit as cl
from chainlit.input_widget import Switch
from chainlit.types import CommandDict

# ── 本專案：MCP ──
from mcp_servers.buildin import register_session_skills, unregister_session_skills
from utils.mcp_manager_legacy import MCPConnectionManager
from utils.mcp_servers_config import get_mcp_servers_config

# ── 本專案：記憶 / 技能 / 會話 ──
from utils.memory_manager import load_memory_index, MEMORY_MANAGEMENT_INSTRUCTIONS
from utils.skills_manager import discover_skills, build_skill_catalog_json, skills_to_json
from utils.session_storage import (
    init_session,
    append_entry,
    finalize_session,
    load_session,
    list_user_sessions,
    append_title,
    read_title,
)
from utils.user_profile import ensure_profile_exists
from utils.llm_client import get_llm_client, get_model_setting

# ── 本專案：Chainlit app 子模組 ──
from chainlit_app.mcp_callbacks import (
    on_mcp_connect,
    on_disconnect,
    on_mcp_progress,
    on_mcp_elicit,
)
from chainlit_app.overseer import run_overseer
from chainlit_app.agent import run as agent, ENABLE_SESSION_HISTORY
from chainlit_app.file_handler import process_uploaded_elements

from foobar_provider import FooBarProvider
from inject_custom_auth import add_custom_oauth_provider

logger = logging.getLogger(__name__)

SESSION_PAGE_SIZE = 10

add_custom_oauth_provider("foobar", FooBarProvider())


@cl.oauth_callback
def oauth_callback(
  provider_id: str,
  token: str,
  raw_user_data: Dict[str, str],
  default_user: cl.User,
) -> Optional[cl.User]:
  return default_user


@cl.on_chat_start
async def start():
    userinfo = cl.user_session.get('user')
    await cl.Message(content=f'### 你好 {userinfo.identifier}，歡迎回來!　ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧').send()
    file_folder = await asyncio.to_thread(os.path.join, os.getcwd(), '.files', cl.user_session.get('id'))
    if not await asyncio.to_thread(os.path.exists, file_folder):
        await asyncio.to_thread(os.mkdir, file_folder)
    cl.user_session.set('file_folder', file_folder)

    # ── AgentSkills：建立使用者 profile 並發現已安裝的技能 ──
    user_id = userinfo.identifier
    await asyncio.to_thread(ensure_profile_exists, user_id)
    skills = await asyncio.to_thread(discover_skills, user_id)
    cl.user_session.set('skills', skills)

    # 根據技能清單動態組合 system prompt
    skills_section = ""
    if skills:
        catalog_json = build_skill_catalog_json(skills)
        skills_section = (
            f"\n\n以下為你可以使用的技能清單：\n{catalog_json}"
            "\n\n當使用者的任務符合某個技能的描述時，請呼叫 activate_skill 工具並傳入技能名稱，以載入完整的技能指引。"
        )

    # ── Memory 層 1：載入 MEMORY.md 索引注入 system prompt ──
    memory_index = await asyncio.to_thread(load_memory_index, user_id)
    memory_section = ""
    if memory_index:
        memory_section = (
            "\n\n## 使用者記憶索引（MEMORY.md）\n"
            + memory_index
            + "\n（呼叫 read_file(user_profiles/{user_id}/memory/filename.md) 取得完整記憶內容）"
        )
    cl.user_session.set("memory_surfaced_paths", set())

    system_content = (
        "You are a helpful 台灣繁體中文 AI assistant. You can access tools. "
        f"\n\n現在時間是 {datetime.datetime.now()}，以下為使用者登入資訊:{userinfo.to_json()}"
        + skills_section
        + memory_section
        + MEMORY_MANAGEMENT_INSTRUCTIONS
    )

    cl.user_session.set(
        "message_history",
        [{"role": "system", "content": system_content}],
    )

    # 對話持久化：延遲到第一則訊息才建立 JSONL
    cl.user_session.set('session_file', None)
    if ENABLE_SESSION_HISTORY:
        cl.user_session.set('session_id_pending', cl.context.session.id)
        cl.user_session.set('user_id_pending', user_id)

    # 建立設定選項
    settings_widgets = []
    settings_widgets.append(
        Switch(
            id="use_vision_model",
            label="使用視覺語言模型描述檔案中的圖片",
            initial=False,
            description='啟用後，在解析檔案如PDF、PPT時 MarkItDown 將使用 GPT-4o-mini 等視覺語言模型來分析和描述檔案中的圖片內容，提供更詳細的圖片說明。但會增加額外的處理時間與 Token 費用'
        )
    )

    mcp_config = get_mcp_servers_config(file_folder)
    if "playwright" in mcp_config:
        mcp_config['playwright']['args'] += [f"--output-dir={file_folder}"]
    if 'filesystem' in mcp_config:
        mcp_config.get('filesystem')['args'].append(file_folder)
    if 'buildin' in mcp_config:
        if not mcp_config['buildin'].get('env'):
            mcp_config['buildin']['env'] = {}
        mcp_config['buildin']['env']['ROOT_FOLDER'] = file_folder

    for server_name, config in mcp_config.items():
        settings_widgets.append(
            Switch(
                id=f"mcp_{server_name}",
                label=f"MCP - {config['name']}",
                initial=config['enabled']
            )
        )

    settings = await cl.ChatSettings(settings_widgets).send()
    cl.user_session.set('chat_setting', settings_widgets)
    cl.user_session.set('current_settings', settings)

    session_id = cl.user_session.get('id')
    mcp_manager = MCPConnectionManager(
        id=session_id,
        config=mcp_config,
        on_connect=on_mcp_connect,
        on_disconnect=on_disconnect,
        on_elicit=on_mcp_elicit,
        on_progress=on_mcp_progress
    )
    cl.user_session.set('mcp_manager', mcp_manager)

    if skills:
        register_session_skills(session_id, skills_to_json(skills))

    for server_name, config in mcp_config.items():
        if server_name == "buildin":
            continue
        setting_key = f"mcp_{server_name}"
        if settings.get(setting_key, config.get('enabled', False)):
            await mcp_manager.add_connection(server_name, config, headers={"X-Session-Id": session_id, "X-User-Id": user_id})

    if ENABLE_SESSION_HISTORY:
        await cl.context.emitter.set_commands([
            CommandDict(id="resume", description="載入歷史對話", icon="history", button=True, persistent=False)
        ])
    else:
        await cl.context.emitter.set_commands([])


@cl.on_chat_end
async def end():
    from chainlit.context import context as cl_context
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
            _session_id = cl.user_session.get('id')
            await asyncio.to_thread(finalize_session, session_file, _session_id, len(message_history))


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

    use_vision_model = settings.get("use_vision_model", False)
    previous_use_vision_model = previous_settings.get("use_vision_model", False)
    if use_vision_model != previous_use_vision_model:
        if use_vision_model:
            await cl.Message(content="已啟用視覺語言模型來描述檔案中的圖片").send()
        else:
            await cl.Message(content="已停用檔案解析的圖片描述功能").send()

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


@cl.action_callback("open_file_preview")
async def on_open_file_preview(action: cl.Action):
    """重新開啟側邊欄顯示文字檔案內容。"""
    files = action.payload.get("files", [])
    sidebar_elements = []
    for file_info in files:
        fp = file_info["path"]
        lang = file_info.get("lang")
        name = file_info["name"]
        if os.path.exists(fp):
            async with aiofiles.open(fp, 'r', encoding='utf-8', errors='replace') as fh:
                file_content = await fh.read()
            text_content = f"```{lang}\n{file_content}\n```" if lang else file_content
            sidebar_elements.append(cl.Text(name=name, content=text_content))
    if sidebar_elements:
        await cl.ElementSidebar.set_title("檔案預覽")
        await cl.ElementSidebar.set_elements(sidebar_elements)


@cl.action_callback("load_session")
async def on_load_session(action: cl.Action):
    """處理 SessionHistory 元件的點選：載入指定 session。"""
    if not ENABLE_SESSION_HISTORY:
        return
    file_path = action.payload.get("file_path")
    user_id = cl.user_session.get('user').identifier

    restored_history = await asyncio.to_thread(load_session, file_path)
    if not restored_history:
        await cl.Message(content="載入歷史對話失敗，檔案可能已損毀。").send()
        return

    cl.user_session.set("message_history", restored_history)
    cl.user_session.set('session_file', file_path)

    started_at = ""
    session_title = None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            meta = json.loads(f.readline())
            started_at = meta.get("started_at", "")
    except Exception:
        pass
    session_title = await asyncio.to_thread(read_title, file_path)

    await _restore_session_ui(restored_history, user_id, started_at, session_title)

    label = started_at[:16].replace('T', ' ') if started_at else file_path
    await cl.Message(content=f"已載入 {label} 的歷史對話，可繼續對話。").send()


@cl.action_callback("change_session_page")
async def on_change_session_page(action: cl.Action):
    """處理 SessionHistory 元件的翻頁：就地更新元素。"""
    if not ENABLE_SESSION_HISTORY:
        return
    new_offset = action.payload.get("offset", 0)
    user_id = cl.user_session.get('user').identifier
    result = await asyncio.to_thread(list_user_sessions, user_id, new_offset, SESSION_PAGE_SIZE)

    new_props = {
        "sessions": result["sessions"],
        "offset": result["offset"],
        "limit": result["limit"],
        "total": result["total"],
        "has_more": result["has_more"],
    }

    elem_id = cl.user_session.get("session_history_elem_id")
    msg_id = cl.user_session.get("session_history_msg_id")

    if elem_id and msg_id:
        elem = cl.CustomElement(
            name="SessionHistory",
            id=elem_id,
            props=new_props,
            display="inline",
        )
        elem.for_id = msg_id
        await elem.update()
    else:
        elem = cl.CustomElement(name="SessionHistory", props=new_props, display="inline")
        msg = await cl.Message(content="", elements=[elem]).send()
        cl.user_session.set("session_history_elem_id", elem.id)
        cl.user_session.set("session_history_msg_id", msg.id)


@cl.action_callback("submit_dynamic_form")
async def on_submit_dynamic_form(action: cl.Action):
    """處理 DynamicForm 元件的提交或取消。"""
    from mcp_servers.buildin import _pending_forms

    payload = action.payload
    form_id = payload.get("form_id")
    cancelled = payload.get("cancelled", False)
    answers = payload.get("answers", {})

    session_id = cl.user_session.get('id')
    pending = _pending_forms.get(session_id)

    if not pending or pending.get("form_id") != form_id:
        return

    pending["result"]["cancelled"] = cancelled
    pending["result"]["data"] = answers if not cancelled else None

    elem_id = pending.get("elem_id")
    msg_id = pending.get("msg_id")
    if elem_id and msg_id:
        updated_props = {**pending.get("original_props", {}), "submitted": True}
        elem = cl.CustomElement(
            name="DynamicForm",
            id=elem_id,
            props=updated_props,
            display="inline",
        )
        elem.for_id = msg_id
        await elem.update()

    pending["event"].set()


@cl.on_message
async def on_message(message: cl.Message):
    # ── Resume 指令攔截 ──
    if message.command == "resume":
        await _handle_resume_command(message)
        return

    new_message = {
        "role": "user",
        "content": [{"type": "text", "text": message.content}]
    }
    if message.elements:
        current_settings = cl.user_session.get('current_settings', {})
        use_vision_model = current_settings.get("use_vision_model", False)
        extra_parts = await process_uploaded_elements(message.elements, use_vision_model=use_vision_model)
        new_message['content'].extend(extra_parts)
    message_history = cl.user_session.get("message_history", [])
    message_history.append(new_message)

    # 對話持久化：第一則訊息時才建立 JSONL
    _session_file = cl.user_session.get('session_file')
    _sid = cl.context.session.id
    _eid = cl.user_session.get('user').identifier
    if ENABLE_SESSION_HISTORY:
        if not _session_file:
            _pending_sid = cl.user_session.get('session_id_pending', _sid)
            _pending_uid = cl.user_session.get('user_id_pending', _eid)
            _session_file, is_new_session = await asyncio.to_thread(init_session, _pending_uid, _pending_sid)
            cl.user_session.set('session_file', _session_file)
            if is_new_session:
                initial_history = cl.user_session.get("message_history", [])
                for entry in initial_history:
                    if entry["role"] == "system":
                        await asyncio.to_thread(
                            append_entry,
                            _session_file, _pending_sid, _pending_uid,
                            entry["role"], entry.get("content"),
                        )
        if _session_file:
            await asyncio.to_thread(
                append_entry, _session_file, _sid, _eid,
                "user", new_message["content"],
            )

    # 第一條使用者訊息：背景生成 session 標題
    user_message_count = cl.user_session.get("user_message_count", 0) + 1
    cl.user_session.set("user_message_count", user_message_count)
    if ENABLE_SESSION_HISTORY and user_message_count == 1 and _session_file:
        existing_title = await asyncio.to_thread(read_title, _session_file)
        if not existing_title:
            asyncio.ensure_future(_generate_session_title(
                session_file=_session_file,
                session_id=cl.context.session.id,
                first_message=message.content,
            ))

    try:
        await agent(message_history)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        await cl.Message(content=f"Error: {str(e)}").send()


# ── 輔助函式（使用 cl 但無裝飾器，僅供本模組內的 @cl 函式呼叫）──

async def _handle_resume_command(message: cl.Message):
    """顯示 SessionHistory 元件供選擇。"""
    if not ENABLE_SESSION_HISTORY:
        await cl.Message(content="歷史對話功能已停用。").send()
        return
    user_id = cl.user_session.get('user').identifier
    result = await asyncio.to_thread(list_user_sessions, user_id, 0, SESSION_PAGE_SIZE)
    if not result["sessions"]:
        await cl.Message(content="目前沒有任何歷史對話記錄。").send()
        return

    elem = cl.CustomElement(
        name="SessionHistory",
        props={
            "sessions": result["sessions"],
            "offset": result["offset"],
            "limit": result["limit"],
            "total": result["total"],
            "has_more": result["has_more"],
        },
        display="inline",
    )
    msg = await cl.Message(content="", elements=[elem]).send()
    cl.user_session.set("session_history_elem_id", elem.id)
    cl.user_session.set("session_history_msg_id", msg.id)


async def _restore_session_ui(restored_history: list, user_id: str, started_at: str, title: str = None):
    """將歷史 message_history 渲染到 Chainlit 聊天畫面。"""
    steps = []
    thread_id = cl.context.session.thread_id or cl.context.session.id
    for entry in restored_history:
        role = entry.get("role")
        entry_content = entry.get("content")

        if role in ("system", "tool"):
            continue
        if role == "assistant" and entry_content is None:
            continue

        if role == "user":
            step_type = "user_message"
            output_text = (
                entry_content if isinstance(entry_content, str)
                else "\n".join(
                    item["text"] for item in entry_content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            )
        else:
            step_type = "assistant_message"
            output_text = entry_content if isinstance(entry_content, str) else ""

        if not output_text:
            continue

        steps.append({
            "id": str(uuid.uuid4()),
            "threadId": thread_id,
            "type": step_type,
            "output": output_text,
            "createdAt": started_at,
            "start": started_at,
            "end": started_at,
            "name": user_id if role == "user" else "Assistant",
            "metadata": {},
            "streaming": False,
        })

    thread_dict = {
        "id": thread_id,
        "createdAt": started_at,
        "name": title or started_at[:16].replace('T', ' '),
        "userId": user_id,
        "userIdentifier": user_id,
        "tags": [],
        "metadata": {},
        "steps": steps,
        "elements": [],
    }
    await cl.context.emitter.resume_thread(thread_dict)


async def _generate_session_title(session_file: str, session_id: str, first_message: str) -> None:
    """用 LLM 生成 session 標題並 append 到 JSONL。在背景執行，不阻塞主流程。"""
    try:
        text = first_message.strip()[:500]
        client = get_llm_client(mode="async")
        model_setting = get_model_setting()
        response = await client.chat.completions.create(
            model=model_setting["model"],
            temperature=0.3,
            stream=False,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一個對話標題生成助手。"
                        "根據使用者的第一條訊息，生成一個簡短的繁體中文標題（5到15個字）。"
                        "只輸出標題本身，不要加任何標點符號、引號或解釋。"
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        title = response.choices[0].message.content.strip()
        if title:
            await asyncio.to_thread(append_title, session_file, session_id, title)
    except Exception:
        pass


if __name__ == '__main__':
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
