from utils.llm_client import get_llm_client, get_model_setting
from utils.mcp_servers_config import get_mcp_servers_config
from utils.user_profile import ensure_profile_exists
from utils.skills_manager import discover_skills, build_skill_catalog_json, skills_to_json
from mcp_servers.buildin import register_session_skills, unregister_session_skills
import chainlit as cl
from chainlit.input_widget import Select, Switch
from typing import Dict, Any, List, Optional, Literal
from mcp.types import CallToolResult, TextContent
import os
import json
import base64
import io
from markitdown import MarkItDown
import datetime
import time
import asyncio
import httpx
import re
from utils.mcp_manager_legacy import MCPConnectionManager
from chainlit_app.overseer import render_overseer_for_user, run_overseer
from foobar_provider import FooBarProvider
from inject_custom_auth import add_custom_oauth_provider

add_custom_oauth_provider("foobar", FooBarProvider())

@cl.oauth_callback
def oauth_callback(
  provider_id: str,
  token: str,
  raw_user_data: Dict[str, str],
  default_user: cl.User,
) -> Optional[cl.User]:
  return default_user  

async def encode_image(image_path):
    """非同步編碼圖片為 base64，使用 aiofiles 進行非同步檔案讀取"""
    import aiofiles
    async with aiofiles.open(image_path, "rb") as image_file:
        image_data = await image_file.read()
        result = await asyncio.to_thread(base64.b64encode, image_data)
    return result.decode('utf-8')

async def get_files_state(folder_path):
    """取得資料夾中所有檔案的狀態（檔案名稱和修改時間）
    
    Args:
        folder_path: 資料夾路徑
        
    Returns:
        dict: {filename: mtime} 格式的字典，記錄每個檔案的修改時間
    """
    files_state = {}
    if folder_path and await asyncio.to_thread(os.path.exists, folder_path):
        file_list = await asyncio.to_thread(os.listdir, folder_path)
        for filename in file_list:
            file_path = os.path.join(folder_path, filename)
            if await asyncio.to_thread(os.path.isfile, file_path):
                mtime = await asyncio.to_thread(os.path.getmtime, file_path)
                files_state[filename] = mtime
    return files_state

async def check_and_process_new_files(existing_files, append_to_history=False):
    """檢查並處理工具生成的新檔案（包括圖片和其他檔案）
    
    Args:
        existing_files: dict，格式為 {filename: mtime}，記錄執行工具前的檔案狀態
        append_to_history: bool，是否將圖片加入對話歷史
    """
    file_folder = cl.user_session.get('file_folder')
    if not file_folder or not await asyncio.to_thread(os.path.exists, file_folder):
        return
    
    # 支援的圖片格式
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
    
    # 取得當前檔案狀態
    current_files = await get_files_state(file_folder)
    
    # 找出新檔案或被修改的檔案
    new_or_modified_files = []
    for filename, current_mtime in current_files.items():
        if filename not in existing_files or existing_files[filename] != current_mtime:
            new_or_modified_files.append(filename)
    
    if not new_or_modified_files:
        return
    
    # 分類新檔案或被修改的檔案
    new_images = []
    other_files = []
    
    for f in new_or_modified_files:
        filename, extension = await asyncio.to_thread(os.path.splitext, f.lower())
        if extension in image_extensions:
            new_images.append(f)
        else:
            other_files.append(f)
    
    # 準備所有元素
    all_elements = []
    image_content = []
    
    # 處理圖片檔案
    for image_file in new_images:
        image_path = os.path.join(file_folder, image_file)
        filename, extension = await asyncio.to_thread(os.path.splitext, image_file.lower())

        # 其他圖片格式使用原有的 path 方式
        image_element = cl.Image(
            name=image_file,
            path=image_path,
            display="inline"
        )
        all_elements.append(image_element)
        
        # 將圖片加入到內容中
        image_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{await encode_image(image_path)}",
                "detail": "high"
            }
        })
    
    # 處理其他檔案
    for file_name in other_files:
        file_path = os.path.join(file_folder, file_name)
        
        # 創建檔案元素供下載
        file_element = cl.File(
            name=file_name,
            path=file_path,
            display="inline",
        )
        all_elements.append(file_element)

    # 一次發送所有元素到 UI
    if all_elements:
        content_parts = []
        if new_images:
            content_parts.append(f"🖼️ 產生了 {len(new_images)} 個圖片檔案")
        if other_files:
            content_parts.append(f"📁 產生了 {len(other_files)} 個檔案可供下載")
        
        content = "、".join(content_parts) if content_parts else ""
        
        await cl.Message(
            content=content,
            elements=all_elements
        ).send()
        
        # 將圖片加入到 message_history 中（只有圖片需要加入對話歷史）
        if append_to_history and image_content:
            message_history = cl.user_session.get("message_history", [])
            image_message = {
                "role": "assistant",
                "content": image_content
            }
            message_history.append(image_message)
            # 更新 session 中的 message_history
            cl.user_session.set("message_history", message_history)
    
@cl.step(name="檔案文本提取")
async def convert_to_markdown(file_path, model="gpt-4o-mini", use_vision_model=False):
    # 根據設定決定是否使用視覺語言模型
    if use_vision_model:
        client = get_llm_client(mode="sync")
        md = MarkItDown(enable_plugins=True, llm_client=client, llm_model=model)
    else:
        md = MarkItDown(enable_plugins=True)
    
    # 將同步的 md.convert 包裝成非同步呼叫
    result = await asyncio.to_thread(md.convert, file_path)
    
    return result.text_content


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
    cl.user_session.set('skills', skills)  # 供後續使用

    # 根據技能清單動態組合 system prompt
    skills_section = ""
    if skills:
        catalog_json = build_skill_catalog_json(skills)
        skills_section = (
            f"\n\n以下為你可以使用的技能清單：\n{catalog_json}"
            "\n\n當使用者的任務符合某個技能的描述時，請呼叫 activate_skill 工具並傳入技能名稱，以載入完整的技能指引。"
        )
    system_content = (
        "You are a helpful 台灣繁體中文 AI assistant. You can access tools. "
        "當你準備好讓使用者繼續操作（完成任務、遇到阻礙、或需要使用者提供資訊）時，必須呼叫 attempt_completion 工具來結束你的回合，否則使用者無法輸入。"
        + skills_section
    )

    cl.user_session.set(
        "message_history",
        [
            {
                "role": "system",
                "content": system_content,
            },
            {
                "role": "assistant",
                "content": f"現在時間是 {datetime.datetime.now()}，以下為使用者登入資訊:{userinfo.to_json()}",
            }
        ],
    )
    # 建立設定選項
    settings_widgets = []
    
    # 新增視覺語言模型設定選項
    settings_widgets.append(
        Switch(
            id="use_vision_model",
            label="使用視覺語言模型描述檔案中的圖片",
            initial=False,
            description='啟用後，在解析檔案如PDF、PPT時 MarkItDown 將使用 GPT-4o-mini 等視覺語言模型來分析和描述檔案中的圖片內容，提供更詳細的圖片說明。但會增加額外的處理時間與 Token 費用'
        )
    )
    # playwright 設定
    mcp_config = get_mcp_servers_config(file_folder)
    if "playwright" in mcp_config:
        mcp_config['playwright']['args'] += [f"--output-dir={file_folder}"]
    
    if 'filesystem' in mcp_config:
        mcp_config.get('filesystem')['args'].append(file_folder)

    if 'buildin' in mcp_config:
        if not mcp_config['buildin'].get('env'):
            mcp_config['buildin']['env'] = {}
        mcp_config['buildin']['env']['ROOT_FOLDER'] = file_folder

    # 新增 MCP 伺服器設定選項
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

    # 確保每個會話都有唯一的 MCP 管理器實例
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

    # 將技能目錄註冊到 buildin MCP server 的 session registry，供 activate_skill 工具使用
    if skills:
        register_session_skills(session_id, skills_to_json(skills))

    # 根據初始設定連線已啟用的伺服器
    for server_name, config in mcp_config.items():
        setting_key = f"mcp_{server_name}"
        if settings.get(setting_key, config.get('enabled', False)):
            # await cl.Message(content=f"⏳ 正在連線到 MCP 伺服器: {server_name}").send()
            await mcp_manager.add_connection(server_name, config, headers={"X-Session-Id": session_id, "X-User-Id": user_id})

async def on_mcp_connect(name, tools=[]):
    mcp_config = get_mcp_servers_config(cl.user_session.get('file_folder'))
    await cl.Message(content=f'🔗 已連線 `{mcp_config[name]['name']}`').send()
    
    # 在設定介面中更新該MCP的選項描述
    chat_setting = cl.user_session.get('chat_setting', [])
    for element in chat_setting:
        if element.id == f"mcp_{name}":
            element.description = ', '.join([f"{t['name']}" for t in tools])
            break
        
    cl.user_session.set('chat_setting', chat_setting)
    settings = await cl.ChatSettings(chat_setting).send()

async def on_disconnect(name):
    await cl.Message(content=f"🔌 已斷線 MCP 伺服器: {name}").send()

@cl.on_chat_end
async def end():
    # 清除 AgentSkills session registry
    session_id = cl.user_session.get('id')
    unregister_session_skills(session_id)

    mcp_manager = cl.user_session.get('mcp_manager')
    if mcp_manager:
        await mcp_manager.shutdown()
        
@cl.on_settings_update
async def on_settings_update(settings):
    """處理設定變更，連線或斷線 MCP 伺服器"""
    print("設定已更新:", settings)
    
    # 先取得舊的設定值用於比較
    previous_settings = cl.user_session.get('current_settings', {})
    
    # 儲存當前設定到 session 中
    cl.user_session.set('current_settings', settings)
    
    mcp_manager = cl.user_session.get('mcp_manager')
    if not mcp_manager:
        return
    
    chat_setting = cl.user_session.get('chat_setting')
    for element in chat_setting:
        element.initial = settings.get(element.id, False)

    # 處理視覺語言模型設定變更
    use_vision_model = settings.get("use_vision_model", False)
    previous_use_vision_model = previous_settings.get("use_vision_model", False)
    
    # 只有在設定真正改變時才發送通知
    if use_vision_model != previous_use_vision_model:
        if use_vision_model:
            await cl.Message(content="已啟用視覺語言模型來描述檔案中的圖片").send()
        else:
            await cl.Message(content="已停用檔案解析的圖片描述功能").send()

    # 處理每個 MCP 伺服器的設定變更
    mcp_config = get_mcp_servers_config(cl.user_session.get('file_folder'))
    for server_name, config in mcp_config.items():
        setting_key = f"mcp_{server_name}"
        is_enabled = settings.get(setting_key, False)
        is_connected = mcp_manager.is_connected(server_name)
        
        if is_enabled and not is_connected:
            # 需要連線但尚未連線
            await mcp_manager.add_connection(server_name, config, headers={"X-Session-Id": cl.user_session.get('id'), "X-User-Id": cl.user_session.get('user').identifier})
            await cl.Message(content=f"⏳ 正在連線到 MCP 伺服器: {server_name}").send()
            
        elif not is_enabled and is_connected:
            # 需要斷線但仍在連線中
            await mcp_manager.remove_connection(server_name)
            await cl.Message(content=f"🔌 已斷線 MCP 伺服器: {server_name}").send()
    
    # 更新工具列表
    await mcp_manager.update_tools()

@cl.step(type="tool", name="MCP工具", show_input=True)
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    # 動態設定步驟名稱
    if cl.context.current_step:
        cl.context.current_step.name = f"MCP工具: {tool_name}"
    
    mcp_manager = cl.user_session.get('mcp_manager')
    print("Executing tool:", tool_name)
    print("Tool input:", tool_input)
    mcp_name = None
    mcp_tools = mcp_manager.tools

    # 找到包含此工具的 MCP 伺服器
    for conn_name, tools in mcp_tools.items():
        if any(tool["name"] == tool_name for tool in tools):
            mcp_name = conn_name
            break

    if not mcp_name:
        return {"error": f"Tool '{tool_name}' not found in any connected MCP server"}

    try:
        result = await mcp_manager.call_tool(mcp_name, tool_name, tool_input)
        return result
    except Exception as e:
        return {"error": f"Error calling tool '{tool_name}': {str(e)}"}


async def format_tools_for_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    openai_tools = []

    for tool in tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        openai_tools.append(openai_tool)

    return openai_tools


def format_calltoolresult_content(result):
    """Extract text content from a CallToolResult object.

    The MCP CallToolResult contains a list of content items,
    where we want to extract text from TextContent type items.
    """
    text_contents = []

    if isinstance(result, CallToolResult):
        for content_item in result.content:
            # This script only supports TextContent but you can implement other CallToolResult types
            if isinstance(content_item, TextContent):
                text_contents.append(content_item.text)

    if text_contents:
        return "\n".join(text_contents)
    return str(result)

async def process_llm_response(message_history, initial_msg=None):
    """
    處理 LLM 回答與遞迴工具呼叫，直到呼叫 attempt_completion 工具為止。
    """
    llm_client = get_llm_client(mode="async")
    mcp_tools = cl.user_session.get("mcp_manager").tools
    all_tools = []
    for connection_tools in mcp_tools.values():
        all_tools.extend(connection_tools)

    chat_params = get_model_setting()
    if all_tools:
        openai_tools = await format_tools_for_openai(all_tools)
        chat_params["tools"] = openai_tools
        chat_params["tool_choice"] = "auto"

    # 用於 streaming 回覆
    msg_obj = initial_msg or cl.Message(content="")

    while True:
        stream = await llm_client.chat.completions.create(
            messages=message_history, **chat_params
        )

        response_text = ""
        tool_calls = []
        has_streamed_content = False

        thinking = False
        thinking_step = None
        start = time.time()

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if token := delta.content or "":
                if token == "<think>":
                    thinking = True
                    thinking_step = cl.Step(name="Thinking")
                    await thinking_step.__aenter__()
                    continue

                if token == "</think>":
                    thinking = False
                    if thinking_step is not None:
                        thought_for = round(time.time() - start)
                        thinking_step.name = f"Thought for {thought_for}s"
                        await thinking_step.update()
                        await thinking_step.__aexit__(None, None, None)
                    continue

                if thinking and thinking_step is not None:
                    await thinking_step.stream_token(token)
                else:
                    response_text += token
                    if token.strip() or has_streamed_content:
                        await msg_obj.stream_token(token)
                        has_streamed_content = True

            if delta.tool_calls:
                for tool_call in delta.tool_calls:
                    tc_id = tool_call.index
                    if tc_id >= len(tool_calls):
                        tool_calls.append({"name": "", "arguments": ""})

                    if tool_call.function.name:
                        tool_calls[tc_id]["name"] = tool_call.function.name

                    if tool_call.function.arguments:
                        tool_calls[tc_id]["arguments"] += tool_call.function.arguments

        # 若有 tool call，清除末尾可能殘留的 markdown 列表標記（如 "\n- "）
        if tool_calls and has_streamed_content:
            cleaned = re.sub(r'[\s\-\*#]+$', '', response_text)
            if cleaned != response_text:
                msg_obj.content = cleaned
                await msg_obj.update()
                response_text = cleaned

        # 如果有 assistant 回覆內容，加入歷史
        if response_text.strip():
            message_history.append({"role": "assistant", "content": response_text})
            cl.user_session.set("message_history", message_history)

        # 如果有 tool call，執行工具並將結果加入歷史，然後 loop 再丟給 LLM
        if tool_calls:
            # 生成一致的 tool_call_id 基礎值
            base_call_id = len(message_history)
            
            # 先將 assistant 的 tool_calls 訊息加入歷史
            tool_calls_formatted = []
            for i, tool_call in enumerate(tool_calls):
                tool_call_id = f"call_{base_call_id}_{i}"
                tool_calls_formatted.append({
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                    },
                })
            
            # 先加入 assistant 訊息（包含所有 tool_calls）
            message_history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_formatted,
            })
            cl.user_session.set("message_history", message_history)
            
            # 檢查是否呼叫了 attempt_completion 工具
            called_attempt_completion = False
            
            # 執行每個工具並加入對應的 tool 回應
            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call["name"]
                tool_call_id = f"call_{base_call_id}_{i}"
                
                # 記錄工具執行前的檔案狀態（包含修改時間）
                file_folder = cl.user_session.get('file_folder')
                existing_files = await get_files_state(file_folder)
                
                tool_result_content = None
                
                try:
                    tool_args = json.loads(tool_call["arguments"])

                    # Execute the tool in a step
                    tool_result = await execute_tool(tool_name, tool_args)
                    
                    # Format the tool result content
                    tool_result_content = format_calltoolresult_content(tool_result)
                    
                    # 檢查是否呼叫了 attempt_completion 工具
                    if tool_name == "attempt_completion":
                        called_attempt_completion = True
                    
                except asyncio.CancelledError:
                    # 用戶主動中斷，加入中斷訊息到歷史中
                    tool_result_content = f"Tool {tool_name} was cancelled by user"

                except Exception as e:
                    error_msg = f"Error executing tool {tool_name}: {str(e)}"
                    error_message = cl.Message(content=error_msg)
                    await error_message.send()
                    
                    # 設定錯誤訊息作為工具回應內容
                    tool_result_content = error_msg

                # 確保每個 tool_call_id 只對應一個 tool 回應訊息
                if tool_result_content is not None:
                    message_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": tool_result_content,
                    })
                    cl.user_session.set("message_history", message_history)
                    
                # 檢查是否有新的檔案產生
                await check_and_process_new_files(existing_files)
            
            # 如果呼叫了 attempt_completion 工具，則停止迴圈
            if called_attempt_completion:
                break
                    
            # 有 tool call，繼續 while loop（再丟給 LLM）
            # 並用新的 cl.Message 物件做 streaming
            msg_obj = cl.Message(content="")
        
            continue
        
        # 如果沒有 tool call，繼續迴圈等待 LLM 可能呼叫工具
        # 只有在呼叫 attempt_completion 工具時才會真正停止
        msg_obj = cl.Message(content="")
    # 更新 session message history
    cl.user_session.set("message_history", message_history)

@cl.step(type="tool", name="反思", show_input=False)
async def overse(message_history):
    # ====== 在這裡啟動 Overseer ======
    goal = cl.user_session.get("task_goal") or "（未提供明確任務目標，建議在入場時就保存）"
    overseer_report = await run_overseer(goal, message_history)

    # 把 overseer 的結果存起來，下一輪可供主 Agent 參考
    cl.user_session.set("overseer_report", overseer_report)
    # 也可以把它 append 回 message_history，作為下一輪提示
    message_history.append({
        "role": "assistant",
        "name": "overseer",
        "content": json.dumps(overseer_report, ensure_ascii=False)
    })
    cl.user_session.set("message_history", message_history)

    # 視需求把結果回饋給使用者（可用更人性化渲染）
    # human_friendly = render_overseer_for_user(overseer_report)
    # await cl.Message(content=human_friendly).send()

    # 你可以依據 overseer 的 status 做後續控制：
    status = overseer_report.get("status")
    if status == "continue":
        # 將 overseer 建議的 next_actions（如果有）轉成下一輪提示，或直接讓主 Agent 接手
        # 這邊你可以把 next_actions 作為「system or user message」提示給主 Agent
        pass
    elif status == "need_user_input":
        # 引導使用者提供 overseer_report["ask_user"] 的資訊
        pass
    else:  # "terminate"
        # 明確對使用者說明終止原因 & 建議
        pass
    return overseer_report
    
@cl.on_message
async def on_message(message: cl.Message):
    new_message =  {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text":  message.content
            }
        ]
    }
    images = [file for file in message.elements if "image" in file.mime]
    # 支援的文件副檔名
    supported_docs = ['.pdf', '.ppt', '.pptx', '.xls', '.xlsx', '.doc', '.docx']
    # 取得視覺語言模型設定
    current_settings = cl.user_session.get('current_settings', {})
    use_vision_model = current_settings.get("use_vision_model", False)
    # 已處理的檔案集合
    handled_files = set()
    # 文件處理
    for file in message.elements:
        ext = os.path.splitext(file.name)[1].lower()
        if ext in supported_docs:
            content = await convert_to_markdown(file.path, use_vision_model=use_vision_model)
            new_message['content'].append(
                {
                    "type": "text",
                    "text": content
                }
            )
            handled_files.add(file.name)
    # 圖片處理
    for image in images:
        new_message['content'].append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{await encode_image(image.path)}",
                    "detail": "high"
                }
            }
        )
        handled_files.add(image.name)
    # 其他未處理格式註記
    for file in message.elements:
        if file.name not in handled_files:
            ext = os.path.splitext(file.name)[1].lower()
            # 註記收到的非支援格式
            new_message['content'].append(
                {
                    "type": "text",
                    "text": f"（已收到檔案：{os.path.basename(file.path)}）"
                }
            )
    message_history = cl.user_session.get("message_history", [])
    message_history.append(new_message)
    try:
        await process_llm_response(message_history)
    except Exception as e:
        error_message = f"Error: {str(e)}"
        await cl.Message(content=error_message).send()

async def on_mcp_progress(mcp_name: str, message: str, progress: int, total: int):
    mcp_manager = cl.user_session.get('mcp_manager')
    try:
        # 處理本專案自定義訊息格式顯示在側邊欄
        if mcp_manager['mcp_name'].get('use_artifact'):
            """處理 MCP 進度通知並更新 ElementSidebar"""
            # 解析 JSON 訊息
            notification_data = json.loads(message)
            
            # 準備 ElementSidebar 的元素
            elements = []
            
            # 處理每個元素
            for element in notification_data.get("elements", []):
                if element["type"] == "text":
                    # 創建文字元素
                    text_element = cl.Text(
                        name=f"text_{len(elements)}",
                        content=element["content"]
                    )
                    elements.append(text_element)
                    
                elif element["type"] == "image":
                    # 創建圖片元素
                    # 直接使用 base64 數據創建 data URL，不保存到檔案
                    
                    # 創建圖片元素，使用 data URL
                    data_url = f"data:image/png;base64,{element['content']}"
                    image_element = cl.Image(
                        name=f"screenshot_{len(elements)}",
                        url=data_url,
                        display="side"
                    )
                    elements.append(image_element)
            
            # 使用唯一的 key 更新 ElementSidebar
            import time
            unique_key = f"browser_progress_{int(time.time() * 1000)}"
            
            if elements:
                await cl.ElementSidebar.set_elements(elements, key=unique_key)
        else:
            await cl.Message(content=message).send()

    except Exception as e:
        print(f"處理進度通知時發生錯誤: {str(e)}")

async def on_mcp_elicit(elicte_param) -> Literal["accept", "decline", "cancel"]:
    res = await cl.AskActionMessage(
        content=elicte_param.get('message'),
        actions=[
            cl.Action(name="accept", payload={"value": "accept"}, label="✔️ 接受"),
            cl.Action(name="decline", payload={"value": "decline"}, label="❌ 拒絕"),
        ],
    ).send()

    return res.get("payload").get("value")
        
if __name__ == '__main__':
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
