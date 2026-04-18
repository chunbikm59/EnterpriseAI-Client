"""MCP 事件回調函數：連線通知、斷線、進度更新、使用者確認。"""

import json
import time
from typing import Literal

import chainlit as cl

from utils.mcp_servers_config import get_mcp_servers_config


async def on_mcp_connect(name, tools=[]):
    mcp_config = get_mcp_servers_config(cl.user_session.get('file_folder'))
    await cl.Message(content=f'🔗 已連線 `{mcp_config[name]["name"]}`').send()

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
                    text_element = cl.Text(
                        name=f"text_{len(elements)}",
                        content=element["content"]
                    )
                    elements.append(text_element)

                elif element["type"] == "image":
                    data_url = f"data:image/png;base64,{element['content']}"
                    image_element = cl.Image(
                        name=f"screenshot_{len(elements)}",
                        url=data_url,
                        display="side"
                    )
                    elements.append(image_element)

            # 使用唯一的 key 更新 ElementSidebar
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
