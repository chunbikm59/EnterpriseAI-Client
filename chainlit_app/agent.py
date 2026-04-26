"""Agent 核心模組：工具執行與 LLM 對話迴圈。"""

import asyncio
import base64
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
from utils.file_handler import get_files_state, _resize_image_bytes
from utils.llm_client import get_llm_client, get_model_setting
from utils.memory_extractor import extract_memories_background
from utils.memory_injection import consume_memory_prefetch
from utils.memory_prefetch import prefetch_relevant_memories
from utils.conversation_storage import append_entry, append_ui_event, append_ui_message
from utils.tool_formatter import (
    format_calltoolresult_content,
    format_tools_for_openai,
    maybe_persist_large_tool_result,
)
from chainlit_app.file_handler import check_and_process_new_files
from utils.signed_url import StreamingPathRewriter
from mcp_servers.buildin import _pending_renders, _pending_pptx_renders

logger = logging.getLogger(__name__)

ENABLE_SESSION_HISTORY = os.environ.get("ENABLE_SESSION_HISTORY", "true").lower() in ("1", "true", "yes")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _to_rel_path(p: str) -> str:
    from pathlib import Path
    try:
        return Path(p).resolve().relative_to(Path(_PROJECT_ROOT).resolve()).as_posix()
    except ValueError:
        return Path(p).as_posix()


async def _handle_render_html(payload: dict, send_message: bool = True):
    """將 render_html 工具的 payload 推送到 ElementSidebar。
    send_message=False 時只更新 sidebar，不送通知訊息（用於重開已存在的 artifact）。
    """
    artifact_id = payload["artifact_id"]
    html_code   = payload["html_code"]
    title       = payload["title"]

    history: list = cl.user_session.get("artifact_history", [])
    if send_message:
        # 新 artifact：插入 history（去重後再插）
        history = [h for h in history if h["artifact_id"] != artifact_id]
        history.insert(0, payload)
        if len(history) > 10:
            history = history[:10]
        cl.user_session.set("artifact_history", history)
    # send_message=False（重開）時不修改 history，直接用現有的

    history_meta = [{"artifact_id": h["artifact_id"], "title": h["title"]} for h in history]

    elem = cl.CustomElement(
        name="HtmlRenderer",
        props={
            "html_code":    html_code,
            "title":        title,
            "artifact_id":  artifact_id,
            "history":      history_meta,
            "history_data": history,
            "current_index": 0,
            "published_url": payload.get("published_url"),
        },
        display="side",
    )
    await cl.ElementSidebar.set_title(f"Artifacts — {title}")
    await cl.ElementSidebar.set_elements([elem])

    if not send_message:
        return

    # 在對話中送出一條帶 ArtifactChip 的通知訊息（inline CustomElement，重整後自動還原）
    notif_content = f"🎨 **{title}** 已渲染至右側 sidebar"
    chip_props = {
        "action": "reopen_artifact",
        "payload": {"artifact_id": artifact_id},
        "title": title,
        "icon": "🎨",
    }
    chip = cl.CustomElement(name="ArtifactChip", props=chip_props, display="inline")
    await cl.Message(content=notif_content, elements=[chip]).send()

    # 持久化：記錄 custom element 供 build_thread_steps_from_jsonl 重建
    if ENABLE_SESSION_HISTORY:
        sf = cl.user_session.get("session_file")
        if sf:
            await asyncio.to_thread(
                append_ui_message, sf, notif_content,
                elements=[{
                    "kind": "custom",
                    "name": "ArtifactChip",
                    "props": chip_props,
                    "display": "inline",
                }],
            )


def _resolve_img_paths(script: str, user_id: str, conversation_id: str) -> str:
    """將 addImage data/path 欄位中的相對路徑替換成 /api/user-files/ 可存取的完整路徑。"""
    safe_uid  = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
    safe_conv = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id)
    base = f"/api/user-files/user_profiles/{safe_uid}/conversations/{safe_conv}"

    def _replace(m):
        key   = m.group(1)   # "data" or "path"
        quote = m.group(2)
        rel   = m.group(3).replace("\\", "/").lstrip("./")
        return f"{key}: {quote}{base}/{rel}{quote}"

    return re.sub(
        r"(data|path)\s*:\s*(['\"])((?:uploads|artifacts)/[^'\"]+)\2",
        _replace,
        script,
    )


async def _handle_render_pptx(payload: dict, send_message: bool = True):
    """將 render_pptx 工具的 payload 推送到 ElementSidebar。
    send_message=False 時只更新 sidebar，不送通知訊息（用於重開已存在的 pptx）。
    """
    pptx_id     = payload["pptx_id"]
    pptx_script = payload["pptx_script"]
    title       = payload["title"]
    slide_count = payload.get("slide_count", 1)

    # 儲存至 session pptx_history（供 reopen_artifact 重開使用）
    if send_message:
        pptx_history: list = cl.user_session.get("pptx_history", [])
        pptx_history = [h for h in pptx_history if h["pptx_id"] != pptx_id]
        pptx_history.insert(0, payload)
        if len(pptx_history) > 10:
            pptx_history = pptx_history[:10]
        cl.user_session.set("pptx_history", pptx_history)

        # 腳本持久化到磁碟，供重新整理後從磁碟讀回
        conversation_folder = cl.user_session.get("file_folder", "")
        if conversation_folder:
            import aiofiles as _aio
            from utils.user_profile import get_conversation_artifacts_dir as _get_arts_dir
            _arts = _get_arts_dir(conversation_folder)
            os.makedirs(_arts, exist_ok=True)
            _js_path = os.path.join(_arts, f"pptx_{pptx_id}.js")
            try:
                async with _aio.open(_js_path, "w", encoding="utf-8") as _f:
                    await _f.write(pptx_script)
            except Exception:
                pass

    # 替換腳本中的相對圖片路徑為完整 URL
    user = cl.user_session.get("user")
    conversation_id = cl.user_session.get("conversation_id", "")
    if user and conversation_id:
        pptx_script = _resolve_img_paths(pptx_script, user.identifier, conversation_id)

    elem = cl.CustomElement(
        name="PptxRenderer",
        props={
            "pptx_id":         pptx_id,
            "pptx_script":     pptx_script,
            "title":           title,
            "slide_count":     slide_count,
            "conversation_id": conversation_id,
        },
        display="side",
    )
    await cl.ElementSidebar.set_title(f"簡報 — {title}")
    await cl.ElementSidebar.set_elements([elem])

    if not send_message:
        return

    notif_content = f"📊 **{title}** 已在右側 sidebar 渲染"
    chip_props = {
        "action": "reopen_artifact",
        "payload": {"pptx_id": pptx_id},
        "title": title,
        "icon": "📊",
    }
    chip = cl.CustomElement(name="ArtifactChip", props=chip_props, display="inline")
    await cl.Message(content=notif_content, elements=[chip]).send()

    if ENABLE_SESSION_HISTORY:
        sf = cl.user_session.get("session_file")
        if sf:
            await asyncio.to_thread(
                append_ui_message, sf, notif_content,
                elements=[{
                    "kind": "custom",
                    "name": "ArtifactChip",
                    "props": chip_props,
                    "display": "inline",
                }],
            )


async def _inject_image_files(
    image_files: dict,
    message_history: list,
    label_prefix: str = "圖片",
):
    """讀取圖片路徑 dict，轉 base64 後以 assistant 訊息插入 message_history，並持久化。

    image_files: {label: abs_path}
    """
    img_content: list = []
    for label, abs_path in image_files.items():
        try:
            with open(abs_path, "rb") as _f:
                raw = _f.read()
            ext = os.path.splitext(abs_path)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            raw = _resize_image_bytes(raw, mime)
            b64 = base64.b64encode(raw).decode("utf-8")
            img_content.append({"type": "text", "text": f"{label_prefix}: {label}"})
            img_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        except Exception as _e:
            img_content.append({"type": "text", "text": f"{label_prefix} {label} 圖片讀取失敗：{_e}"})

    if not img_content:
        return

    message_history.append({"role": "assistant", "content": img_content})
    cl.user_session.set("message_history", message_history)

    rel_paths = [_to_rel_path(p) for p in image_files.values()]
    await _persist_entry("assistant", img_content, image_paths=rel_paths)

    if ENABLE_SESSION_HISTORY:
        sf = cl.user_session.get('session_file')
        if sf:
            event_files = [
                {"permanent_path": p, "original_name": os.path.basename(p)}
                for p in rel_paths
            ]
            await asyncio.to_thread(
                append_ui_event, sf, "assistant_image", {"files": event_files}
            )


async def _persist_entry(role, content, tool_calls=None, tool_call_id=None, image_paths=None):
    """持久化一條對話記錄到 JSONL，若未啟用 session history 則直接返回。"""
    if not ENABLE_SESSION_HISTORY:
        return
    sf = cl.user_session.get('session_file')
    if not sf:
        return
    conv_id = cl.user_session.get('conversation_id', '')
    await asyncio.to_thread(
        append_entry, sf, conv_id,
        cl.user_session.get('user').identifier,
        role, content, tool_calls, tool_call_id, image_paths,
    )


@cl.step(type="tool", name="工具", show_input=True)
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    if cl.context.current_step:
        cl.context.current_step.name = f"工具: {tool_name}"
        await cl.context.current_step.update()

    is_error = False
    result = None

    # buildin 工具：直接呼叫 Python 函數（不走 MCP HTTP）
    if tool_name in _BUILDIN_FUNC_MAP:
        session_id = cl.user_session.get('id')
        user_id = cl.user_session.get('user').identifier
        conversation_folder = cl.user_session.get('file_folder')
        conversation_id = cl.user_session.get('conversation_id', '')
        result = await call_buildin_tool(
            tool_name, tool_input, session_id, user_id, conversation_folder, conversation_id
        )
    else:
        mcp_manager = cl.user_session.get('mcp_manager')
        print("Executing tool:", tool_name)
        print("Tool input:", tool_input)
        mcp_name = None
        mcp_tools = mcp_manager.tools

        for conn_name, tools in mcp_tools.items():
            if any(tool["name"] == tool_name for tool in tools):
                mcp_name = conn_name
                break

        if not mcp_name:
            result = {"error": f"Tool '{tool_name}' not found in any connected MCP server"}
            is_error = True
        else:
            try:
                result = await mcp_manager.call_tool(mcp_name, tool_name, tool_input)
            except Exception as e:
                result = {"error": f"Error calling tool '{tool_name}': {str(e)}"}
                is_error = True

    # 記錄 ui_event:step（在 step scope 內，current_step 仍有效）
    if ENABLE_SESSION_HISTORY:
        sf = cl.user_session.get('session_file')
        if sf:
            output_str = str(result)[:2000] if result is not None else ""
            await asyncio.to_thread(append_ui_event, sf, "step", {
                "step_name": f"工具: {tool_name}",
                "step_type": "tool",
                "input": tool_input,
                "output": output_str,
                "is_error": is_error,
            })

    return result


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

    # 超過4字元才預取，相容中英文（split() 對中文無效）
    memory_prefetch_task = None
    if _user_text and len(_user_text) > 4:
        memory_prefetch_task = asyncio.ensure_future(
            prefetch_relevant_memories(user_id, _user_text, already_surfaced)
        )

    memory_injected_this_turn = False   # 每回合只注入一次相關記憶
    main_wrote_memory = False            # 追蹤主 LLM 是否呼叫 write_file 寫記憶（互斥用）
    _compressed_this_turn = False        # 每回合最多壓縮一次，防止連鎖觸發

    # 在 run() 開始時就記錄當前資料夾狀態，避免繼續舊對話時把已存在的檔案誤判為新檔案
    _file_folder_init = cl.user_session.get('file_folder')
    existing_files = await get_files_state(
        os.path.join(_file_folder_init, "artifacts") if _file_folder_init else None
    )

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
        conv_id = cl.user_session.get('conversation_id', '')
        rewriter = StreamingPathRewriter(user_id, conv_id) if conv_id else None

        thinking = False
        thinking_step = None
        start = time.time()

        async def _ws_keepalive():
            """每 10 秒送一個空 token 到 WebSocket，防止 tool call arguments 累積期間 idle 斷線。"""
            while True:
                await asyncio.sleep(10)
                try:
                    await msg_obj.stream_token("")
                except Exception:
                    break

        _keepalive_task = asyncio.create_task(_ws_keepalive())
        try:
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
                        output = rewriter.feed(token) if rewriter else token
                        if output and (output.strip() or has_streamed_content):
                            await msg_obj.stream_token(output)
                            has_streamed_content = True

                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        tc_id = tool_call.index
                        if tc_id >= len(tool_calls):
                            tool_calls.append({"name": "", "arguments": ""})

                        if tool_call.function.name:
                            tool_calls[tc_id]["name"] = tool_call.function.name

                        if tool_call.function.arguments:
                            _prev_arg_len = len(tool_calls[tc_id]["arguments"])
                            tool_calls[tc_id]["arguments"] += tool_call.function.arguments

                            # render_pptx 串流進度：每 200 字元節流推送一次 partial 給前端
                            if tool_calls[tc_id]["name"] == "render_pptx":
                                _cur_arg_len = len(tool_calls[tc_id]["arguments"])
                                if _prev_arg_len // 200 < _cur_arg_len // 200:
                                    _partial_args = tool_calls[tc_id]["arguments"]
                                    _streaming_elem = cl.CustomElement(
                                        name="PptxRenderer",
                                        props={
                                            "pptx_id":             f"pptx_streaming_{tc_id}_{_cur_arg_len}",
                                            "pptx_script":         None,
                                            "pptx_script_partial": _partial_args,
                                            "title":               "生成中…",
                                            "slide_count":         1,
                                        },
                                        display="side",
                                    )
                                    # key 帶入字元數，確保每次推送前端都視為新內容強制更新
                                    await cl.context.emitter.emit("set_sidebar_title", "簡報 — 生成中…")
                                    await cl.context.emitter.emit(
                                        "set_sidebar_elements",
                                        {"elements": [_streaming_elem.to_dict()], "key": f"pptx_stream_{_cur_arg_len}"},
                                    )
        finally:
            _keepalive_task.cancel()
        # flush rewriter 剩餘 buffer（處理末尾無終止符的情況）
        if rewriter:
            remaining = rewriter.flush()
            if remaining and (remaining.strip() or has_streamed_content):
                await msg_obj.stream_token(remaining)
                has_streamed_content = True

        # 若有 tool call，清除末尾可能殘留的 markdown 列表標記（如 "\n- "）
        if tool_calls and has_streamed_content:
            display_text = rewriter.full_output if rewriter else response_text
            cleaned_display = re.sub(r'[\s\-\*#]+$', '', display_text)
            if cleaned_display != display_text:
                msg_obj.content = cleaned_display
                await msg_obj.update()
            response_text = re.sub(r'[\s\-\*#]+$', '', response_text)

        # 如果有 assistant 回覆內容，加入歷史
        if response_text.strip():
            # rewriter 已在 stream 中即時轉換並輸出，直接取 full_output 作為持久化內容
            # 若無 rewriter（沒有 conv_id），維持原始 response_text
            if rewriter:
                response_text = rewriter.full_output
                if tool_calls:
                    response_text = re.sub(r'[\s\-\*#]+$', '', response_text)
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
            file_folder = cl.user_session.get('file_folder')

            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call["name"]
                tool_call_id = f"call_{base_call_id}_{i}"

                tool_result_content = None
                _image_files_to_inject: dict | None = None
                _image_label_prefix: str = "圖片"

                try:
                    tool_args = json.loads(tool_call["arguments"])

                    # Execute the tool in a step
                    tool_result = await execute_tool(tool_name, tool_args)

                    # 原有路徑：格式化結果
                    tool_result_content = format_calltoolresult_content(tool_result)
                    tool_result_content = await maybe_persist_large_tool_result(
                        tool_name, tool_call_id, tool_result_content, file_folder
                    )

                    # 回傳含 __image_files__ 的工具，額外插入 assistant 訊息帶圖片
                    _IMAGE_TOOLS = {
                        "capture_video_frames": "時間點",
                        "capture_ppt_slides": "投影片",
                    }
                    if tool_name in _IMAGE_TOOLS:
                        try:
                            parsed = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                            if isinstance(parsed, dict) and "__image_files__" in parsed:
                                _image_files_to_inject = parsed["__image_files__"]
                                _image_label_prefix = _IMAGE_TOOLS[tool_name]
                        except Exception:
                            pass

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

                # 讀圖片路徑轉 base64，以 assistant 訊息插入上下文
                if _image_files_to_inject:
                    await _inject_image_files(
                        _image_files_to_inject, message_history, _image_label_prefix
                    )

                # render_html 特殊後處理：取出 pending render payload 並更新 sidebar
                if tool_name == "render_html" and "[RENDER_HTML_OK]" in str(tool_result_content):
                    session_id = cl.user_session.get("id")
                    pending = _pending_renders.pop(session_id, None)
                    if pending:
                        await _handle_render_html(pending)

                # render_pptx 特殊後處理：取出 pending render payload 並更新 sidebar
                if tool_name == "render_pptx" and "[RENDER_PPTX_OK]" in str(tool_result_content):
                    session_id = cl.user_session.get("id")
                    pending = _pending_pptx_renders.pop(session_id, None)
                    if pending:
                        await _handle_render_pptx(pending)

                # 檢查是否有新的檔案產生（ask_user_form / read_file 不觸發下載流程）
                _NO_FILE_SCAN_TOOLS = {"ask_user_form", "read_file", "render_html", "render_pptx"}
                if tool_name not in _NO_FILE_SCAN_TOOLS:
                    await check_and_process_new_files(existing_files)
                    existing_files = await get_files_state(os.path.join(file_folder, "artifacts"))

                # ── Memory 層 2：每個工具執行後檢查注入（對齊 Claude Code 行為）──
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
        await asyncio.sleep(0)
        new_cursor, new_turns = await extract_memories_background(
            user_id=user_id,
            recent_messages=message_history,
            main_wrote_memory=main_wrote_memory,
            session_id=session_id,
            conversation_folder=conversation_folder,
            cursor=_extraction_cursor,
            turns_since_extraction=_turns_since,
            all_tools=chat_params.get("tools"),
        )
        cl.user_session.set("memory_extraction_cursor", new_cursor)
        cl.user_session.set("memory_turns_since_extraction", new_turns)
        logger.debug(
            "[memory_extractor] 游標更新 %d→%d turns_since→%d",
            _extraction_cursor, new_cursor, new_turns,
        )

    asyncio.ensure_future(_run_and_update_cursor())
