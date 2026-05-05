import asyncio
import datetime
import os
import uuid

import chainlit as cl
from chainlit.input_widget import Switch, Tab
from chainlit.types import CommandDict

from mcp_servers.buildin import register_session_skills
from utils.mcp_manager_legacy import MCPConnectionManager
from utils.mcp_servers_config import get_mcp_servers_config
from utils.memory_manager import load_memory_index, MEMORY_MANAGEMENT_INSTRUCTIONS
from utils.skills_manager import discover_skills, build_skill_catalog_json, skills_to_json
from utils.user_profile import ensure_profile_exists, get_conversation_artifacts_dir
from chainlit_app.mcp_callbacks import on_mcp_connect, on_disconnect, on_mcp_elicit, on_mcp_progress
from chainlit_app.agent import ENABLE_SESSION_HISTORY

ASK_USER_FORM_INSTRUCTIONS = (
    "\n\nIf you do not understand why the user has denied a tool call, use the ask_user_question to ask them."
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def _init_session_state(userinfo):
    """初始化（或重新初始化）一個 Chainlit session 所需的全部狀態。
    供 on_chat_start 與 on_chat_resume 共用，避免重複程式碼。
    """
    user_id = userinfo.identifier

    # Chainlit 暫存目錄
    chainlit_tmp = os.path.join(os.getcwd(), '.files', cl.user_session.get('id'))
    await asyncio.to_thread(os.makedirs, chainlit_tmp, exist_ok=True)

    # conversation_id 與 conversation_folder
    # 優先使用 Chainlit 框架的 session.thread_id，使 URL 的 thread id 與 DB 的 conversation id 一致
    conversation_id = cl.context.session.thread_id or str(uuid.uuid4())
    cl.user_session.set('conversation_id', conversation_id)
    conversation_folder = os.path.join(
        _PROJECT_ROOT, 'user_profiles', user_id, 'conversations', conversation_id
    )
    cl.user_session.set('file_folder', conversation_folder)

    # AgentSkills + Memory：三個獨立 I/O 並行
    _, skills, memory_index = await asyncio.gather(
        asyncio.to_thread(ensure_profile_exists, user_id),
        asyncio.to_thread(discover_skills, user_id),
        asyncio.to_thread(load_memory_index, user_id),
    )
    cl.user_session.set('skills', skills)

    from utils.buildin_tool_runner import get_buildin_tool_schemas
    buildin_schemas = await get_buildin_tool_schemas()

    skills_section = ""
    if skills:
        catalog_json = build_skill_catalog_json(skills)
        skills_section = (
            "\n\n<agent_skills>\n"
            f"以下為你可以使用的技能清單：\n{catalog_json}"
            "\n\n當使用者的任務符合某個技能的描述時，請呼叫 activate_skill 工具並傳入技能名稱，以載入完整的技能指引。"
            "\n</agent_skills>"
        )

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
        + ASK_USER_FORM_INSTRUCTIONS
        + MEMORY_MANAGEMENT_INSTRUCTIONS
    )
    cl.user_session.set("message_history", [{"role": "system", "content": system_content}])
    cl.user_session.set("msg_id_to_jsonl_uuid", {})

    cl.user_session.set('session_file', None)
    if ENABLE_SESSION_HISTORY:
        cl.user_session.set('conversation_id_pending', conversation_id)
        cl.user_session.set('user_id_pending', user_id)

    # ChatSettings
    mcp_config = get_mcp_servers_config(conversation_folder)
    if "playwright" in mcp_config:
        mcp_config['playwright']['args'] += [f"--output-dir={conversation_folder}"]
    if 'filesystem' in mcp_config:
        mcp_config.get('filesystem')['args'].append(conversation_folder)
    if 'buildin' in mcp_config:
        if not mcp_config['buildin'].get('env'):
            mcp_config['buildin']['env'] = {}
        mcp_config['buildin']['env']['ROOT_FOLDER'] = conversation_folder

    mcp_tab_inputs = [
        Switch(id=f"mcp_{name}", label=f"MCP - {cfg['name']}", initial=cfg['enabled'])
        for name, cfg in mcp_config.items()
    ]
    buildin_tab_inputs = [
        Switch(id=f"buildin_{s['name']}", label=s['name'], description=s['description'], initial=True)
        for s in buildin_schemas
    ]
    system_skill_inputs = [
        Switch(id=f"skill_{skill.name}", label=skill.name, description=skill.description, initial=True)
        for skill in skills if skill.source == "system"
    ]
    user_skill_inputs = [
        Switch(id=f"skill_{skill.name}", label=skill.name, description=skill.description, initial=True)
        for skill in skills if skill.source == "user"
    ]

    tabs = [
        Tab(id="tab_mcp",         label="MCP 伺服器",  inputs=mcp_tab_inputs),
        Tab(id="tab_buildin",     label="內建工具",     inputs=buildin_tab_inputs),
        Tab(id="tab_sys_skill",   label="系統 Skill",  inputs=system_skill_inputs),
        Tab(id="tab_user_skill",  label="個人 Skill",  inputs=user_skill_inputs),
    ]

    settings = await cl.ChatSettings(tabs).send()

    all_widgets = mcp_tab_inputs + buildin_tab_inputs + system_skill_inputs + user_skill_inputs
    cl.user_session.set('chat_setting', all_widgets)
    cl.user_session.set('current_settings', settings)
    cl.user_session.set('disabled_buildin_tools', set())
    cl.user_session.set('disabled_skills', set())

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
            asyncio.ensure_future(
                mcp_manager.add_connection(server_name, config, headers={"X-Session-Id": session_id, "X-User-Id": user_id})
            )

    await cl.context.emitter.set_commands([])
