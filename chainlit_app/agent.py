"""Agent 核心模組：工具執行與 LLM 對話迴圈。"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict

import chainlit as cl

from utils.buildin_tool_runner import call_buildin_tool, get_buildin_tool_schemas
from utils.buildin_tool_runner import _FUNC_MAP as _BUILDIN_FUNC_MAP
from utils.context_compressor import (
    COMPRESS_KEEP_RECENT,
    CONTEXT_WINDOW_SIZE,
    compress_conversation,
    should_compress,
)
from utils.file_handler import get_files_state
from utils.llm_client import get_llm_client, get_model_setting
from utils.memory_extractor import extract_memories_background
from utils.memory_injection import consume_memory_prefetch
from utils.memory_prefetch import prefetch_relevant_memories
from utils.session_storage import append_entry
from utils.tool_formatter import (
    format_calltoolresult_content,
    format_tools_for_openai,
    maybe_persist_large_tool_result,
)
from chainlit_app.file_handler import check_and_process_new_files

logger = logging.getLogger(__name__)

ENABLE_SESSION_HISTORY = os.environ.get("ENABLE_SESSION_HISTORY", "true").lower() in ("1", "true", "yes")


async def _persist_entry(role, content, tool_calls=None, tool_call_id=None):
    """持久化一條對話記錄到 JSONL，若未啟用 session history 則直接返回。"""
    if not ENABLE_SESSION_HISTORY:
        return
    sf = cl.user_session.get('session_file')
    if not sf:
        return
    await asyncio.to_thread(
        append_entry, sf, cl.context.session.id,
        cl.user_session.get('user').identifier,
        role, content, tool_calls, tool_call_id,
    )


@cl.step(type="tool", name="工具", show_input=True)
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    if cl.context.current_step:
        cl.context.current_step.name = f"工具: {tool_name}"
        await cl.context.current_step.update()

    # buildin 工具：直接呼叫 Python 函數（不走 MCP HTTP）
    if tool_name in _BUILDIN_FUNC_MAP:
        session_id = cl.user_session.get('id')
        user_id = cl.user_session.get('user').identifier
        conversation_folder = cl.user_session.get('file_folder')
        return await call_buildin_tool(tool_name, tool_input, session_id, user_id, conversation_folder)

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


async def _run_compress(message_history: list, llm_client, base_model_setting: dict, prompt_tokens: int) -> list:
    """執行自動壓縮並透過 Chainlit Step 顯示進度。回傳新的 message_history。"""
    token_checkpoints = cl.user_session.get("token_checkpoints", [])
    async with cl.Step(name="自動壓縮對話歷史", type="run") as step:
        step.input = (
            f"上下文已使用 {prompt_tokens:,} tokens，剩餘空間不足，正在壓縮..."
        )
        new_history, summary, post_tokens = await compress_conversation(
            message_history, llm_client, base_model_setting, token_checkpoints, prompt_tokens
        )
        step.output = (
            f"壓縮完成：{len(message_history)} 條 → {len(new_history)} 條"
            f"（估算壓縮後 {post_tokens:,} tokens）\n\n{summary}"
        )
    # 壓縮後 message_history 已重建，舊 checkpoints 失效，清空讓下一輪重新累積
    cl.user_session.set("token_checkpoints", [])
    return new_history


async def run(message_history, initial_msg=None):
    """
    處理 LLM 回答與遞迴工具呼叫，沒有工具呼叫時停止迴圈。
    """
    # ── Memory 層 2：動態相關記憶預取（非同步，不阻塞主流程）──
    user_id = cl.user_session.get('user').identifier
    session_id = cl.user_session.get('id')
    conversation_folder = cl.user_session.get('file_folder', '')
    already_surfaced: set = cl.user_session.get("memory_surfaced_paths", set())

    # 提取使用者訊息純文字
    _last_msg = message_history[-1] if message_history else {}
    _user_text = ""
    if isinstance(_last_msg.get("content"), list):
        _user_text = " ".join(
            p.get("text", "") for p in _last_msg["content"] if p.get("type") == "text"
        )
    elif isinstance(_last_msg.get("content"), str):
        _user_text = _last_msg["content"]

    # 多於單詞才預取（對應 CC：single-word prompts lack enough context）
    memory_prefetch_task = None
    if _user_text and len(_user_text.split()) > 1:
        memory_prefetch_task = asyncio.ensure_future(
            prefetch_relevant_memories(user_id, _user_text, already_surfaced)
        )

    memory_injected_this_turn = False   # 每回合只注入一次相關記憶
    main_wrote_memory = False            # 追蹤主 LLM 是否呼叫 write_file 寫記憶（互斥用）
    _compressed_this_turn = False        # 每回合最多壓縮一次，防止連鎖觸發

    llm_client = get_llm_client(mode="async")

    # buildin 工具 schema（直接從 FastMCP 取，不走 HTTP）
    buildin_schemas = await get_buildin_tool_schemas()
    # 外部 MCP 工具 schema（stdio transport 等）
    mcp_tools = cl.user_session.get("mcp_manager").tools
    all_tools = list(buildin_schemas)
    for connection_tools in mcp_tools.values():
        all_tools.extend(connection_tools)

    base_model_setting = get_model_setting()
    chat_params = dict(base_model_setting)
    chat_params["stream_options"] = {"include_usage": True}  # 串流結束時取得 token 用量
    if all_tools:
        openai_tools = await format_tools_for_openai(all_tools)
        chat_params["tools"] = openai_tools
        chat_params["tool_choice"] = "auto"

    # 用於 streaming 回覆
    msg_obj = initial_msg or cl.Message(content="")

    MAX_ITERATIONS = 20  # 最大工具呼叫迴圈次數，防止無限迴圈
    iteration = 0
    while iteration < MAX_ITERATIONS:
        iteration += 1
        stream = await llm_client.chat.completions.create(
            messages=message_history, **chat_params
        )

        response_text = ""
        tool_calls = []
        has_streamed_content = False
        usage_prompt_tokens: int | None = None

        thinking = False
        thinking_step = None
        start = time.time()

        async for chunk in stream:
            # 捕獲最終用量 chunk（stream_options.include_usage=True 會在串流末尾附帶）
            if hasattr(chunk, "usage") and chunk.usage and hasattr(chunk.usage, "prompt_tokens"):
                usage_prompt_tokens = chunk.usage.prompt_tokens
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
            await _persist_entry("assistant", response_text)

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
            await _persist_entry("assistant", None, tool_calls_formatted)

            # 追蹤主 LLM 是否呼叫 write_file 寫記憶（供背景萃取互斥判斷）
            if any(tc["name"] == "write_file" for tc in tool_calls):
                main_wrote_memory = True

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
                    tool_result_content = await maybe_persist_large_tool_result(
                        tool_name, tool_call_id, tool_result_content, file_folder
                    )

                except asyncio.CancelledError:
                    # 用戶斷線或手動停止，必須重新拋出讓上層處理
                    raise

                except Exception as e:
                    error_detail = repr(e) if not str(e) else str(e)
                    error_msg = f"Error executing tool {tool_name}: {type(e).__name__}: {error_detail}"
                    logger.exception("Tool execution failed: %s", tool_name)
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
                    await _persist_entry("tool", tool_result_content, tool_call_id=tool_call_id)

                # 檢查是否有新的檔案產生（ask_user_form / read_file 不觸發下載流程）
                _NO_FILE_SCAN_TOOLS = {"ask_user_form", "read_file"}
                if tool_name not in _NO_FILE_SCAN_TOOLS:
                    await check_and_process_new_files(existing_files)

            # ── Memory 層 2：工具執行後注入相關記憶（若預取已完成且尚未注入）──
            memory_injected_this_turn, already_surfaced, message_history = await consume_memory_prefetch(
                memory_prefetch_task, memory_injected_this_turn, already_surfaced, message_history
            )
            if memory_injected_this_turn:
                cl.user_session.set("message_history", message_history)
                cl.user_session.set("memory_surfaced_paths", already_surfaced)

            # ── 自動上下文壓縮（工具執行後，下次 LLM 呼叫前）──
            if not _compressed_this_turn and usage_prompt_tokens and should_compress(usage_prompt_tokens):
                _compressed_this_turn = True
                message_history = await _run_compress(
                    message_history, llm_client, base_model_setting, usage_prompt_tokens
                )
                cl.user_session.set("message_history", message_history)
                await _persist_entry("system", f"[AUTO-COMPACT] prompt_tokens={usage_prompt_tokens}")

            # 有 tool call，繼續 while loop（再丟給 LLM）
            # 並用新的 cl.Message 物件做 streaming
            msg_obj = cl.Message(content="")
            continue

        # 沒有 tool call，停止迴圈
        # ── 自動上下文壓縮（對話結束時，為下一回合預先壓縮）──
        if not _compressed_this_turn and usage_prompt_tokens and should_compress(usage_prompt_tokens):
            _compressed_this_turn = True
            message_history = await _run_compress(
                message_history, llm_client, base_model_setting, usage_prompt_tokens
            )
            cl.user_session.set("message_history", message_history)
            await _persist_entry("system", f"[AUTO-COMPACT] prompt_tokens={usage_prompt_tokens}")

        # ── 記錄對話輪 checkpoint（每輪使用者+agent停止為單位）──
        # 壓縮後 checkpoints 已在 _run_compress 中清空，此處記錄的是壓縮後的新基線
        if not _compressed_this_turn and usage_prompt_tokens:
            _checkpoints = cl.user_session.get("token_checkpoints", [])
            _checkpoints.append({"msg_len": len(message_history), "tokens": usage_prompt_tokens})
            cl.user_session.set("token_checkpoints", _checkpoints)

        # 顯示 token 用量（附加到最後一條 AI 訊息底部）
        if usage_prompt_tokens and response_text.strip():
            msg_obj.elements = [cl.CustomElement(
                name="TokenCounter",
                props={"prompt_tokens": usage_prompt_tokens, "max_tokens": CONTEXT_WINDOW_SIZE},
                display="inline",
            )]
            await msg_obj.update()
        break

    # 如果達到最大迴圈次數限制
    if iteration >= MAX_ITERATIONS:
        await cl.Message(content="已達最大工具呼叫次數限制（20 次），對話終止。").send()

    # 更新 session message history
    cl.user_session.set("message_history", message_history)

    # ── Memory 層 3：背景記憶萃取（fire-and-forget）──
    _extraction_cursor = cl.user_session.get("memory_extraction_cursor", 0)
    _turns_since = cl.user_session.get("memory_turns_since_extraction", 0)
    logger.debug(
        "[memory_extractor] 回合結束，啟動背景記憶萃取 | user=%s session=%s "
        "main_wrote_memory=%s cursor=%d turns_since=%d",
        user_id, session_id, main_wrote_memory, _extraction_cursor, _turns_since,
    )

    async def _run_and_update_cursor():
        new_cursor, new_turns = await extract_memories_background(
            user_id=user_id,
            recent_messages=message_history,
            main_wrote_memory=main_wrote_memory,
            session_id=session_id,
            conversation_folder=conversation_folder,
            cursor=_extraction_cursor,
            turns_since_extraction=_turns_since,
        )
        cl.user_session.set("memory_extraction_cursor", new_cursor)
        cl.user_session.set("memory_turns_since_extraction", new_turns)
        logger.debug(
            "[memory_extractor] 游標更新 %d→%d turns_since→%d",
            _extraction_cursor, new_cursor, new_turns,
        )

    asyncio.ensure_future(_run_and_update_cursor())
