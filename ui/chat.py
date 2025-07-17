from openai import AsyncOpenAI, OpenAI
import chainlit as cl
from chainlit.input_widget import Select, Switch
from typing import Dict, Any, List, Optional
from mcp.types import CallToolResult, TextContent
import os
import json
import base64
import io
from markitdown import MarkItDown
import datetime
from dotenv import load_dotenv
from utils.mcp_manager import MCPConnectionManager
load_dotenv()

# 可替換成本地模型，比如使用 LM Studio 的 API
BASE_URL = None # "http://localhost:1234/v1"
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_SETTING = {
    "model": "gpt-4o-mini",
    "temperature": 1,
    "stream": True,
}
# MCP 伺服器配置 實際從資料庫中取得
MCP_SERVERS_CONFIG = {
    "weather_http": {
        "type": "http",
        "url": "http://localhost:8000/mcp-weather/mcp/",
        # "url": "http://localhost:8123/mcp/",
        "enabled": True,
        "description": "天氣查詢 HTTP MCP 伺服器範例" 
    },
    "sequentialthinking": {
        "type": "stdio", 
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "enabled": False,
        "description": "將複雜問題分解為可管理的步驟，隨著理解的加深，修改並完善想法。"
    },
    "playwright": {
        "type": "stdio", 
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest", "--isolated"],
        "enabled": True,
        "description": "一個使用Playwright提供瀏覽器自動化功能的模型上下文協定 (MCP) 伺服器。該伺服器使 LLM 能夠透過結構化的可訪問性快照與網頁進行交互，而無需使用螢幕截圖或視覺調整的模型。"
    },
    # "filesystem": {
    #     "type": "stdio", 
    #     "command": "npx",
    #     "args": ["-y", "@modelcontextprotocol/server-filesystem"],
    #     "enabled": True,
    #     "description": "Node.js server implementing Model Context Protocol (MCP) for filesystem operations."
    # },
    
}

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

async def check_and_process_new_images(existing_files):
    """檢查並處理工具生成的新圖片檔案"""
    file_folder = cl.user_session.get('file_folder')
    if not file_folder or not os.path.exists(file_folder):
        return
    
    # 支援的圖片格式
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
    
    # 取得當前檔案列表
    current_files = set(os.listdir(file_folder))
    new_files = current_files - existing_files
    
    # 篩選出新的圖片檔案
    new_images = [f for f in new_files if os.path.splitext(f.lower())[1] in image_extensions]
    
    if not new_images:
        return
    
    # 準備圖片元素和內容
    image_elements = []
    image_content = []
    
    for image_file in new_images:
        image_path = os.path.join(file_folder, image_file)
        
        try:
            # 創建圖片元素
            image_element = cl.Image(
                name=image_file,
                path=image_path,
                display="inline"
            )
            image_elements.append(image_element)
            
            # 將圖片加入到內容中
            image_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encode_image(image_path)}",
                    "detail": "high"
                }
            })
            
        except Exception as e:
            print(f"處理圖片 {image_file} 時發生錯誤: {str(e)}")
    
    # 一次發送所有圖片到 UI
    if image_elements:
        await cl.Message(
            content='',
            elements=image_elements
        ).send()
        
        # 將所有圖片加入到 message_history 的同一個訊息中
        message_history = cl.user_session.get("message_history", [])
        image_message = {
            "role": "user",
            "content": image_content
        }
        message_history.append(image_message)
        
        # 更新 session 中的 message_history
        cl.user_session.set("message_history", message_history)
    
@cl.step(name="檔案解析")
async def convert_to_markdown(file_path, model="gpt-4o-mini", use_vision_model=False):
    # 根據設定決定是否使用視覺語言模型
    if use_vision_model:
        client = OpenAI(base_url=BASE_URL, api_key=API_KEY)  # 使用同步客戶端
        md = MarkItDown(enable_plugins=True, llm_client=client, llm_model=model)
    else:
        md = MarkItDown(enable_plugins=True)
    
    result = md.convert(file_path)    
    
    return result.text_content


@cl.on_chat_start
async def start():
    file_folder = os.path.join(os.getcwd(), '.files', cl.user_session.get('id'))
    os.mkdir(file_folder)
    cl.user_session.set('file_folder', file_folder)
    cl.user_session.set(
        "message_history",
        [
            {
                "role": "system",
                "content": "You are a helpful 台灣繁體中文 AI assistant. You can access tools using MCP servers.",
            },
            {
                "role": "assistant",
                "content": f"現在時間是 {datetime.datetime.now()}",
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

    if "playwright" in MCP_SERVERS_CONFIG:
        MCP_SERVERS_CONFIG.get('playwright')['args'] += [f"--output-dir={file_folder}"] # f"--storage-state={file_folder}", 
    if 'filesystem' in MCP_SERVERS_CONFIG:
        MCP_SERVERS_CONFIG.get('filesystem')['args'].append(file_folder)

    # 新增 MCP 伺服器設定選項
    for server_name, config in MCP_SERVERS_CONFIG.items():
        settings_widgets.append(
            Switch(
                id=f"mcp_{server_name}",
                label=f"MCP - {server_name}",
                initial=config['enabled']
            )
        )
    
    settings = await cl.ChatSettings(settings_widgets).send()
    cl.user_session.set('chat_setting', settings_widgets)

    mcp_manager = MCPConnectionManager(config=MCP_SERVERS_CONFIG, on_connect=on_mcp_connect)
    cl.user_session.set('mcp_manager', mcp_manager)
    
    # 根據初始設定連線已啟用的伺服器
    for server_name, config in MCP_SERVERS_CONFIG.items():
        setting_key = f"mcp_{server_name}"
        if settings.get(setting_key, config.get('enabled', False)):
            await mcp_manager.add_connection(server_name, config)

async def on_mcp_connect(name, tools=[]):
    await cl.Message(content=f'✅️ 已連線 MCP Server: {name} ').send()
    
    # 在設定介面中更新該MCP的選項描述
    chat_setting = cl.user_session.get('chat_setting', [])
    for element in chat_setting:
        if element.id == f"mcp_{name}":
            element.description = ', '.join([f"{t['name']}" for t in tools])
            break
        
    cl.user_session.set('chat_setting', chat_setting)
    settings = await cl.ChatSettings(chat_setting).send()
    
@cl.on_chat_end
async def end():
    mcp_manager = cl.user_session.get('mcp_manager')
    if mcp_manager:
        await mcp_manager.shutdown()
        
@cl.on_settings_update
async def setup_agent(settings):
    """處理設定變更，連線或斷線 MCP 伺服器"""
    print("設定已更新:", settings)
    
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
    if use_vision_model:
        await cl.Message(content="✅ 已啟用視覺語言模型來描述檔案中的圖片").send()
    else:
        await cl.Message(content="❌ 已停用檔案解析的圖片描述功能").send()

    # 處理每個 MCP 伺服器的設定變更
    for server_name, config in MCP_SERVERS_CONFIG.items():
        setting_key = f"mcp_{server_name}"
        is_enabled = settings.get(setting_key, False)
        is_connected = mcp_manager.is_connected(server_name)
        
        if is_enabled and not is_connected:
            # 需要連線但尚未連線
            await mcp_manager.add_connection(server_name, config)
            await cl.Message(content=f"🔗 正在連線到 MCP 伺服器: {server_name}").send()
            
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
        # 使用我們的 MCP 連線管理器呼叫工具
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
    處理 LLM 回答與遞迴工具呼叫，直到沒有 tool call 為止。
    """
    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
    mcp_tools = cl.user_session.get("mcp_manager").tools
    all_tools = []
    for connection_tools in mcp_tools.values():
        all_tools.extend(connection_tools)

    chat_params = {**MODEL_SETTING}
    if all_tools:
        openai_tools = await format_tools_for_openai(all_tools)
        chat_params["tools"] = openai_tools
        chat_params["tool_choice"] = "auto"
        print("Tools passed:", openai_tools)

    # 用於 streaming 回覆
    msg_obj = initial_msg or cl.Message(content="")

    while True:
        stream = await client.chat.completions.create(
            messages=message_history, **chat_params
        )

        response_text = ""
        tool_calls = []

        async for chunk in stream:
            delta = chunk.choices[0].delta
            print(delta)

            if token := delta.content or "":
                response_text += token
                await msg_obj.stream_token(token)

            if delta.tool_calls:
                for tool_call in delta.tool_calls:
                    tc_id = tool_call.index
                    if tc_id >= len(tool_calls):
                        tool_calls.append({"name": "", "arguments": ""})

                    if tool_call.function.name:
                        tool_calls[tc_id]["name"] = tool_call.function.name

                    if tool_call.function.arguments:
                        tool_calls[tc_id]["arguments"] += tool_call.function.arguments

        # 如果有 assistant 回覆內容，加入歷史
        if response_text.strip():
            message_history.append({"role": "assistant", "content": response_text})

        # 如果有 tool call，執行工具並將結果加入歷史，然後 loop 再丟給 LLM
        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                # 記錄工具執行前的檔案狀態
                file_folder = cl.user_session.get('file_folder')
                existing_files = set()
                if file_folder and os.path.exists(file_folder):
                    existing_files = set(os.listdir(file_folder))                
                try:
                    tool_args = json.loads(tool_call["arguments"])

                    # Add the tool call to message history
                    message_history.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call_{len(message_history)}",
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": tool_call["arguments"],
                                    },
                                }
                            ],
                        }
                    )

                    # Execute the tool in a step
                    tool_result = await execute_tool(tool_name, tool_args)

                    # Format the tool result content
                    tool_result_content = format_calltoolresult_content(tool_result)

                    # Add the tool result to message history
                    message_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": f"call_{len(message_history)-1}",
                            "content": tool_result_content,
                        }
                    )
                    # 檢查是否有新的圖片檔案產生
                    await check_and_process_new_images(existing_files)
                except Exception as e:
                    error_msg = f"Error executing tool {tool_name}: {str(e)}"
                    error_message = cl.Message(content=error_msg)
                    await error_message.send()
            # 有 tool call，繼續 while loop（再丟給 LLM）
            # 並用新的 cl.Message 物件做 streaming
            msg_obj = cl.Message(content="")
        
            continue
        else:
            # 沒有 tool call，結束
            break

    # 更新 session message history
    cl.user_session.set("message_history", message_history)

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
    
    # 取得視覺語言模型設定
    current_settings = cl.user_session.get('current_settings', {})
    use_vision_model = current_settings.get("use_vision_model", False)
    
    file_content = [await convert_to_markdown(file.path, use_vision_model=use_vision_model) for file in message.elements if os.path.splitext(file.path)[1] in ['.pdf', '.ppt', '.pptx', '.xls', '.xlsx', '.doc', '.docx']]

    for content in file_content:
        new_message['content'].append(
            {
                "type": "text",
                "text": content
            }
        )
    for image in images:
        new_message['content'].append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encode_image(image.path)}",
                    "detail": "high"
                }
            }
        )
    message_history = cl.user_session.get("message_history", [])
    message_history.append(new_message)
    try:
        await process_llm_response(message_history)
    except Exception as e:
        error_message = f"Error: {str(e)}"
        await cl.Message(content=error_message).send()

if __name__ == '__main__':
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
