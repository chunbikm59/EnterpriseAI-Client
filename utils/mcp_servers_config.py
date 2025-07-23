import os
from dotenv import load_dotenv

load_dotenv()

def get_mcp_servers_config(file_folder: str):
    """
    回傳 MCP_SERVERS_CONFIG dict，根據 file_folder 動態調整部分內容。
    """
    config = {
        "user_custom_prompt": {
            "name": '我自訂的提示詞',
            "transport": "stdio", 
            "command": "./.venv/Scripts/python.exe",
            "args": ["./mcp_servers/user_custom_prompt.py"],
            "enabled": True,
            "description": ""
        },
        "buildin": {
            "name": '內建工具組',
            "transport": "http",
            "command": "./.venv/Scripts/python.exe",
            "args": ["./mcp_servers/buildin_http.py"],
            "url": "http://localhost:8000/mcp-buildin/mcp/",
            "enabled": True,
            "description": "",
            "env": {
                "ROOT_FOLDER": file_folder
            }
        },
        "sequentialthinking": {
            "name": "Sequential Thinking",
            "transport": "stdio", 
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
            "enabled": False,
            "description": "將複雜問題分解為可管理的步驟，隨著理解的加深，修改並完善想法。"
        },
        "playwright": {
            "name": "瀏覽器自動化",
            "transport": "stdio", 
            "command": "npx",
            "args": [
                "-y", "@playwright/mcp@latest", "--isolated", "--headless", "--viewport-size=1920, 1080",
                f"--output-dir={file_folder}"
            ],
            "enabled": True,
            "description": "一個使用Playwright提供瀏覽器自動化功能的模型上下文協定 (MCP) 伺服器。該伺服器使 LLM 能夠透過結構化的可訪問性快照與網頁進行交互，而無需使用螢幕截圖或視覺調整的模型。"
        },
        "tavily": {
            "name": "網路搜尋",
            "transport": "stdio", 
            "command": "npx",
            "args": ["-y", "tavily-mcp@0.1.3"],
            "env": {
                "TAVILY_API_KEY": os.getenv('TAVILY_API_KEY')
            },
            "enabled": True,
            "description": "一個使用Playwright提供瀏覽器自動化功能的模型上下文協定 (MCP) 伺服器。該伺服器使 LLM 能夠透過結構化的可訪問性快照與網頁進行交互，而無需使用螢幕截圖或視覺調整的模型。"
        }
    }
    return config
