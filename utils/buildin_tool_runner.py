"""
buildin 工具的 schema 提取 + 直接呼叫 executor。

使用 FastMCP 公開 API mcp.list_tools() 取得 schema（不走 HTTP），
執行時直接呼叫 Python 函數（不走 MCP 協議），
透過 contextvars 傳遞 session context（session_id, user_id, conversation_id, conversation_folder）。
"""
from typing import Any, Callable
from mcp_servers.buildin import mcp, _FUNC_MAP, _session_ctx


async def get_buildin_tool_schemas() -> list[dict[str, Any]]:
    """
    用 FastMCP 公開 API 取得所有工具 schema，轉換為 app.py 的現有格式。
    格式：{"name": ..., "description": ..., "input_schema": ...}
    """
    tools = await mcp.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": dict(tool.inputSchema),
        }
        for tool in tools
    ]


async def call_buildin_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    session_id: str,
    user_id: str,
    conversation_folder: str,
    conversation_id: str = "",
) -> str:
    """
    直接呼叫 buildin 工具函數，透過 contextvars 傳遞 session context。
    回傳純字串（與 format_calltoolresult_content 的 str 分支相容）。
    """
    func: Callable = _FUNC_MAP[tool_name]

    # 補齊未傳入的參數預設值（從 schema 取，避免 Field 物件被當成預設值傳入函數）
    schemas = await get_buildin_tool_schemas()
    schema = next((s for s in schemas if s["name"] == tool_name), None)
    if schema:
        for param, info in schema["input_schema"].get("properties", {}).items():
            if param not in tool_args and "default" in info:
                tool_args = {**tool_args, param: info["default"]}

    token = _session_ctx.set({
        "session_id": session_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "conversation_folder": conversation_folder,
    })
    try:
        result = await func(**tool_args)
        return str(result) if result is not None else ""
    finally:
        _session_ctx.reset(token)
