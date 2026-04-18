"""工具 schema 格式化與 tool result 處理工具函數。"""

import asyncio
import os
from typing import Any, Dict, List

from mcp.types import CallToolResult, TextContent

TOOL_RESULT_SIZE_THRESHOLD = 50_000  # 字元數閾值


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


def format_calltoolresult_content(result) -> str:
    """Extract text content from a CallToolResult object.

    The MCP CallToolResult contains a list of content items,
    where we want to extract text from TextContent type items.
    Also accepts plain strings (returned by buildin direct calls).
    """
    if isinstance(result, str):
        return result

    text_contents = []

    if isinstance(result, CallToolResult):
        for content_item in result.content:
            if isinstance(content_item, TextContent):
                text_contents.append(content_item.text)

    if text_contents:
        return "\n".join(text_contents)
    return str(result)


async def maybe_persist_large_tool_result(
    tool_name: str,
    tool_call_id: str,
    content: str,
    file_folder: str,
) -> str:
    """若 tool result 超過閾值，寫入檔案並返回摘要；否則原樣返回。
    read_file 工具永不持久化（避免循環）。
    """
    if tool_name == "read_file":
        return content
    if len(content) <= TOOL_RESULT_SIZE_THRESHOLD:
        return content

    # 寫入檔案
    result_dir = os.path.join(file_folder, "tool_results")
    await asyncio.to_thread(os.makedirs, result_dir, exist_ok=True)
    filepath = os.path.join(result_dir, f"{tool_call_id}.txt")

    def _write():
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    await asyncio.to_thread(_write)

    # 生成預覽（2000 字元，在換行符邊界截斷）
    preview_raw = content[:2000]
    last_nl = preview_raw.rfind('\n')
    preview = preview_raw[:last_nl] if last_nl > 1000 else preview_raw
    has_more = len(content) > len(preview)

    summary = (
        f"<tool-result-too-large>\n"
        f"輸出過大（{len(content):,} 字元）。完整結果已儲存至：{filepath}\n\n"
        f"預覽（前 2000 字元）：\n"
        f"{preview}"
    )
    if has_more:
        summary += "\n..."
    summary += "\n</tool-result-too-large>"
    return summary
