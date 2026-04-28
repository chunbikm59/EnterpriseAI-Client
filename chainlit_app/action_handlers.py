import asyncio
import os
import pathlib

import aiofiles
import chainlit as cl

from mcp_servers.buildin import _pending_forms
from chainlit_app.agent import _handle_render_html, _handle_render_pptx, _handle_render_markdown, ENABLE_SESSION_HISTORY
from utils.conversation_storage import append_ui_event
from utils.user_profile import get_conversation_artifacts_dir
from utils.artifact_publisher import publish_artifact
from utils.signed_url import rewrite_relative_paths_in_md

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent


async def _do_open_file_preview(files: list):
    sidebar_elements = []
    sidebar_record_elements = []
    for file_info in files:
        fp = file_info["path"]
        lang = file_info.get("lang")
        name = file_info["name"]
        if os.path.exists(fp):
            async with aiofiles.open(fp, 'r', encoding='utf-8', errors='replace') as fh:
                file_content = await fh.read()
            file_content = rewrite_relative_paths_in_md(file_content, fp)
            text_content = f"```{lang}\n{file_content}\n```" if lang else file_content
            sidebar_elements.append(cl.Text(name=name, content=text_content))
            sidebar_record_elements.append({
                "kind": "text",
                "name": name,
                "content": file_content[:5000],
                "lang": lang,
            })
    if sidebar_elements:
        await cl.ElementSidebar.set_title("檔案預覽")
        await cl.ElementSidebar.set_elements(sidebar_elements)
        if ENABLE_SESSION_HISTORY:
            sf = cl.user_session.get('session_file')
            if sf:
                await asyncio.to_thread(append_ui_event, sf, "sidebar_update", {
                    "title": "檔案預覽",
                    "elements": sidebar_record_elements,
                })


@cl.action_callback("open_file_preview_element")
async def on_open_file_preview_element(action: cl.Action):
    await _do_open_file_preview(action.payload.get("files", []))


@cl.action_callback("open_file_preview")
async def on_open_file_preview(action: cl.Action):
    await _do_open_file_preview(action.payload.get("files", []))



@cl.action_callback("reopen_artifact")
async def on_reopen_artifact(action: cl.Action):
    """重新開啟 sidebar 顯示指定的 artifact（HTML / PPTX / Markdown）。"""
    artifact_id = action.payload.get("artifact_id")
    pptx_id = action.payload.get("pptx_id")
    md_id = action.payload.get("md_id")

    # ── Markdown artifact ──
    if md_id:
        md_history: list = cl.user_session.get("md_history", [])
        payload = next((h for h in md_history if h["md_id"] == md_id), None)

        # 找不到（重新整理後 session 重置）→ 從 ArtifactChip payload 的 file_path 直接讀磁碟
        if not payload:
            file_path = action.payload.get("file_path", "")
            if file_path and os.path.exists(file_path):
                async with aiofiles.open(file_path, encoding="utf-8") as f:
                    markdown_content = await f.read()
                payload = {
                    "md_id":            md_id,
                    "markdown_content": markdown_content,
                    "title":            action.payload.get("title", md_id),
                    "file_path":        file_path,
                }

        if payload:
            await _handle_render_markdown(payload, send_message=False)
        return

    # ── PPTX artifact ──
    if pptx_id:
        pptx_history: list = cl.user_session.get("pptx_history", [])
        payload = next((h for h in pptx_history if h["pptx_id"] == pptx_id), None)

        # 找不到（重新整理後 session 重置）→ 從磁碟讀回腳本
        if not payload:
            conversation_folder = cl.user_session.get("file_folder", "")
            if conversation_folder:
                js_path = os.path.join(
                    get_conversation_artifacts_dir(conversation_folder),
                    f"pptx_{pptx_id}.js",
                )
                if os.path.exists(js_path):
                    async with aiofiles.open(js_path, encoding="utf-8") as f:
                        pptx_script = await f.read()
                    payload = {"pptx_id": pptx_id, "pptx_script": pptx_script, "title": pptx_id, "slide_count": 1}

        if payload:
            await _handle_render_pptx(payload, send_message=False)
        return

    # ── HTML artifact ──
    if not artifact_id:
        return

    # 先從 session history 找（正常對話中）
    history: list = cl.user_session.get("artifact_history", [])
    payload = next((h for h in history if h["artifact_id"] == artifact_id), None)

    # 找不到（重新整理後 session 重置）→ 從磁碟讀回
    if not payload:
        conversation_folder = cl.user_session.get("file_folder", "")
        if conversation_folder:
            html_path = os.path.join(
                get_conversation_artifacts_dir(conversation_folder),
                f"artifact_{artifact_id}.html",
            )
            if os.path.exists(html_path):
                async with aiofiles.open(html_path, encoding="utf-8") as f:
                    html_code = await f.read()
                payload = {"artifact_id": artifact_id, "html_code": html_code, "title": artifact_id}

    if payload:
        await _handle_render_html(payload, send_message=False)


@cl.action_callback("publish_artifact")
async def on_publish_artifact(action: cl.Action):
    """將 HTML artifact 複製到公開目錄並回傳可公開存取的 URL。"""
    artifact_id = action.payload.get("artifact_id")
    title = action.payload.get("title", "Artifact")
    if not artifact_id:
        return

    conversation_folder = cl.user_session.get("file_folder", "")
    if not conversation_folder:
        return

    html_path = os.path.join(
        get_conversation_artifacts_dir(conversation_folder),
        f"artifact_{artifact_id}.html",
    )
    if not os.path.exists(html_path):
        return

    user = cl.user_session.get("user")
    user_id = user.identifier if user else "unknown"

    token = await asyncio.to_thread(publish_artifact, artifact_id, title, user_id, html_path)
    base_url = os.getenv("CHAINLIT_URL", "http://localhost:8000")
    public_url = f"{base_url}/p/{token}"

    history: list = cl.user_session.get("artifact_history", [])
    for h in history:
        if h["artifact_id"] == artifact_id:
            h["published_url"] = public_url
            break
    cl.user_session.set("artifact_history", history)

    return {"published_url": public_url}


@cl.action_callback("submit_dynamic_form")
async def on_submit_dynamic_form(action: cl.Action):
    """處理 DynamicForm 元件的提交或取消。"""
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
