"""Chainlit 檔案處理：掃描新檔案並更新 UI、處理上傳元素、文件轉 Markdown。"""

import asyncio
import mimetypes
import os

import aiofiles
import chainlit as cl
from markitdown import MarkItDown

from utils.file_handler import encode_image, get_files_state, _get_text_file_info, TEXT_PREVIEW_SIZE_LIMIT
from utils.pdf_converter import PyMuPdfConverter
from utils.permanent_storage import move_to_permanent
from utils.conversation_storage import append_ui_event, append_ui_message
from utils.signed_url import user_file_url, rewrite_relative_paths_in_md

ENABLE_SESSION_HISTORY = os.environ.get("ENABLE_SESSION_HISTORY", "true").lower() in ("1", "true", "yes")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_IGNORED_FILES = {'history.jsonl', '.DS_Store', 'Thumbs.db'}
_IGNORED_EXTENSIONS = {'.tmp', '.lock', '.log'}


async def check_and_process_new_files(existing_files, append_to_history=False):
    """檢查並處理工具生成的新檔案（包括圖片和其他檔案）"""
    _base_folder = cl.user_session.get('file_folder')

    if not _base_folder:
        return
    file_folder = os.path.join(_base_folder, "artifacts")
    if not await asyncio.to_thread(os.path.exists, file_folder):
        return

    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}

    current_files = await get_files_state(file_folder)

    new_or_modified_files = []
    for filename, current_mtime in current_files.items():
        ext = os.path.splitext(filename)[1].lower()
        if filename in _IGNORED_FILES or ext in _IGNORED_EXTENSIONS:
            continue
        if filename not in existing_files or existing_files[filename] != current_mtime:
            new_or_modified_files.append(filename)

    if not new_or_modified_files:
        return

    new_images = []
    other_files = []

    for f in new_or_modified_files:
        filename, extension = await asyncio.to_thread(os.path.splitext, f.lower())
        if extension in image_extensions:
            new_images.append(f)
        else:
            other_files.append(f)

    all_elements = []
    image_content = []

    image_count = len(new_images)
    image_size = "large" if image_count == 1 else "medium" if image_count <= 3 else "small"
    for image_file in new_images:
        image_path = os.path.join(file_folder, image_file)
        all_elements.append(cl.Image(name=image_file, url=user_file_url(image_path), display="inline", size=image_size))
        img_mime = mimetypes.guess_type(image_file)[0] or "image/jpeg"
        image_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img_mime};base64,{await encode_image(image_path, img_mime)}",
                "detail": "high"
            }
        })

    text_preview_files: list[tuple[str, str | None]] = []
    download_only_files: list[str] = []
    for file_name in other_files:
        is_text, lang = _get_text_file_info(file_name)
        fp = os.path.join(file_folder, file_name)
        fsize = await asyncio.to_thread(os.path.getsize, fp)
        if is_text and fsize <= TEXT_PREVIEW_SIZE_LIMIT:
            text_preview_files.append((file_name, lang))
        else:
            download_only_files.append(file_name)

    sidebar_record_elements = []
    if text_preview_files:
        sidebar_elements = []
        for file_name, lang in text_preview_files:
            fp = os.path.join(file_folder, file_name)
            async with aiofiles.open(fp, 'r', encoding='utf-8', errors='replace') as fh:
                file_content = await fh.read()

            file_content = rewrite_relative_paths_in_md(file_content, fp)
            text_content = f"```{lang}\n{file_content}\n```" if lang else file_content
            sidebar_elements.append(cl.Text(name=file_name, content=text_content))
            sidebar_record_elements.append({
                "kind": "text",
                "name": file_name,
                "content": file_content[:5000],
                "lang": lang,
            })
        await cl.ElementSidebar.set_title("檔案預覽")
        await cl.ElementSidebar.set_elements(sidebar_elements)

    for file_name, _ in text_preview_files:
        fp = os.path.join(file_folder, file_name)
        mime = mimetypes.guess_type(file_name)[0] or 'text/plain'
        all_elements.append(cl.File(name=file_name, url=user_file_url(fp), display="inline", mime=mime))

    for file_name in download_only_files:
        fp = os.path.join(file_folder, file_name)
        mime = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        all_elements.append(cl.File(name=file_name, url=user_file_url(fp), display="inline", mime=mime))

    if text_preview_files:
        file_chip_props = {
            "action": "open_file_preview_element",
            "payload": {
                "files": [
                    {"path": os.path.join(file_folder, fn), "lang": lang, "name": fn}
                    for fn, lang in text_preview_files
                ]
            },
            "title": f"預覽 {len(text_preview_files)} 個檔案" if len(text_preview_files) > 1 else text_preview_files[0][0],
            "icon": "📄",
        }
        all_elements.append(cl.CustomElement(name="ArtifactChip", props=file_chip_props, display="inline"))

    if not all_elements:
        return

    content_parts = []
    if new_images:
        content_parts.append(f"🖼️ 產生了 {len(new_images)} 個圖片檔案")
    if text_preview_files:
        content_parts.append(f"📄 產生了 {len(text_preview_files)} 個文字檔案（側邊欄預覽 / 可下載）")
    if download_only_files:
        content_parts.append(f"📁 產生了 {len(download_only_files)} 個檔案可供下載")

    content = "、".join(content_parts)

    msg = await cl.Message(
        content=content,
        elements=all_elements,
    ).send()

    if append_to_history and image_content:
        message_history = cl.user_session.get("message_history", [])
        message_history.append({"role": "assistant", "content": image_content})
        cl.user_session.set("message_history", message_history)

    if ENABLE_SESSION_HISTORY:
        sf = cl.user_session.get('session_file')
        if sf:
            el_records = []
            for img_file in new_images:
                img_path = os.path.join(file_folder, img_file)
                rel = os.path.relpath(img_path, _PROJECT_ROOT).replace("\\", "/")
                el_records.append({"kind": "image", "name": img_file, "permanent_path": rel})
            if text_preview_files:
                el_records.append({
                    "kind": "custom",
                    "name": "ArtifactChip",
                    "display": "inline",
                    "props": file_chip_props,
                })
            for fn, lang in text_preview_files:
                fp = os.path.join(file_folder, fn)
                rel = os.path.relpath(fp, _PROJECT_ROOT).replace("\\", "/")
                mime = mimetypes.guess_type(fn)[0] or 'text/plain'
                el_records.append({"kind": "file", "name": fn, "permanent_path": rel, "mime": mime, "lang": lang})
            for fn in download_only_files:
                fp = os.path.join(file_folder, fn)
                rel = os.path.relpath(fp, _PROJECT_ROOT).replace("\\", "/")
                mime = mimetypes.guess_type(fn)[0] or 'application/octet-stream'
                el_records.append({"kind": "file", "name": fn, "permanent_path": rel, "mime": mime})

            await asyncio.to_thread(
                append_ui_message, sf, content,
                msg_id=msg.id if msg else None,
                elements=el_records,
            )
            if sidebar_record_elements:
                await asyncio.to_thread(append_ui_event, sf, "sidebar_update", {
                    "title": "檔案預覽",
                    "elements": sidebar_record_elements,
                })


async def process_uploaded_elements(
    elements,
    conversation_folder: str = "",
) -> tuple[list[dict], list[dict]]:
    """將 Chainlit 上傳的 elements 轉換為 message content parts，並移動到永久位置。

    Returns:
        (parts, uploaded_file_records)
        - parts：list of content part dicts，extend 到 message['content']
        - uploaded_file_records：list of {original_name, permanent_path}
    """
    supported_docs = {'.pdf', '.ppt', '.pptx', '.xls', '.xlsx', '.doc', '.docx'}
    images = [f for f in elements if "image" in (f.mime or "")]
    handled_files: set[str] = set()
    parts: list[dict] = []
    uploaded_file_records: list[dict] = []

    # 文件轉 markdown，並移動到永久位置
    for file in elements:
        ext = os.path.splitext(file.name)[1].lower()
        if ext in supported_docs:
            # 先移動到永久位置
            if conversation_folder and os.path.exists(file.path):
                perm_path = await asyncio.to_thread(
                    move_to_permanent, file.path, conversation_folder, file.name
                )
                uploaded_file_records.append({
                    "original_name": file.name,
                    "permanent_path": perm_path,
                })
                file_path_for_convert = perm_path
            else:
                file_path_for_convert = file.path

            content = await convert_to_markdown(file_path_for_convert)
            parts.append({"type": "text", "text": content})
            handled_files.add(file.name)

    # 圖片轉 base64，並移動到永久位置
    for image in images:
        if conversation_folder and os.path.exists(image.path):
            perm_path = await asyncio.to_thread(
                move_to_permanent, image.path, conversation_folder, image.name
            )
            uploaded_file_records.append({
                "original_name": image.name,
                "permanent_path": perm_path,
            })
            img_path = perm_path
        else:
            img_path = image.path

        mime = image.mime or mimetypes.guess_type(image.name)[0] or "image/jpeg"
        parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{await encode_image(img_path, mime)}",
                "detail": "high"
            }
        })
        handled_files.add(image.name)

    # 其他未處理格式：移動後加入文字備注
    for file in elements:
        if file.name not in handled_files:
            if conversation_folder and os.path.exists(file.path):
                perm_path = await asyncio.to_thread(
                    move_to_permanent, file.path, conversation_folder, file.name
                )
                uploaded_file_records.append({
                    "original_name": file.name,
                    "permanent_path": perm_path,
                })
                rel_path = os.path.relpath(perm_path, conversation_folder).replace("\\", "/")
                parts.append({
                    "type": "text",
                    "text": f"（已收到檔案：{rel_path}）"
                })
            else:
                parts.append({
                    "type": "text",
                    "text": f"（已收到檔案：{file.name}）"
                })

    return parts, uploaded_file_records


@cl.step(name="檔案文本提取")
async def convert_to_markdown(file_path):
    md = MarkItDown(enable_plugins=True)
    md.register_converter(PyMuPdfConverter(), priority=-1.0)
    result = await asyncio.to_thread(md.convert, file_path, extract_pages=True)
    return result.text_content
