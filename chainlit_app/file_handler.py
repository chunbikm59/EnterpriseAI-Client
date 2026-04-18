"""Chainlit 檔案處理：掃描新檔案並更新 UI、處理上傳元素、文件轉 Markdown。"""

import asyncio
import mimetypes
import os

import aiofiles
import chainlit as cl
from markitdown import MarkItDown

from utils.file_handler import encode_image, get_files_state, _get_text_file_info, TEXT_PREVIEW_SIZE_LIMIT
from utils.llm_client import get_llm_client
from utils.pdf_converter import PyMuPdfConverter


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

    # 處理其他檔案（文字/代碼 → 側邊欄預覽；二進位或超大檔 → 下載）
    text_preview_files: list[tuple[str, str | None]] = []  # (filename, lang_alias)
    download_only_files: list[str] = []
    for file_name in other_files:
        is_text, lang = _get_text_file_info(file_name)
        fp = os.path.join(file_folder, file_name)
        fsize = await asyncio.to_thread(os.path.getsize, fp)
        if is_text and fsize <= TEXT_PREVIEW_SIZE_LIMIT:
            text_preview_files.append((file_name, lang))
        else:
            download_only_files.append(file_name)

    if text_preview_files:
        sidebar_elements = []
        for file_name, lang in text_preview_files:
            fp = os.path.join(file_folder, file_name)
            async with aiofiles.open(fp, 'r', encoding='utf-8', errors='replace') as fh:
                file_content = await fh.read()
            text_content = f"```{lang}\n{file_content}\n```" if lang else file_content
            sidebar_elements.append(cl.Text(name=file_name, content=text_content))
        await cl.ElementSidebar.set_title("檔案預覽")
        await cl.ElementSidebar.set_elements(sidebar_elements)

    for file_name, _ in text_preview_files:
        fp = os.path.join(file_folder, file_name)
        mime = mimetypes.guess_type(file_name)[0] or 'text/plain'
        all_elements.append(cl.File(name=file_name, path=fp, display="inline", mime=mime))

    for file_name in download_only_files:
        fp = os.path.join(file_folder, file_name)
        mime = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        all_elements.append(cl.File(name=file_name, path=fp, display="inline", mime=mime))

    # 一次發送所有元素到 UI
    if all_elements or text_preview_files:
        content_parts = []
        if new_images:
            content_parts.append(f"🖼️ 產生了 {len(new_images)} 個圖片檔案")
        if text_preview_files:
            content_parts.append(f"📄 產生了 {len(text_preview_files)} 個文字檔案（側邊欄預覽 / 可下載）")
        if download_only_files:
            content_parts.append(f"📁 產生了 {len(download_only_files)} 個檔案可供下載")

        content = "、".join(content_parts) if content_parts else ""

        actions = []
        if text_preview_files:
            actions.append(cl.Action(
                name="open_file_preview",
                label="🔍 開啟預覽",
                payload={
                    "files": [
                        {"path": os.path.join(file_folder, fn), "lang": lang, "name": fn}
                        for fn, lang in text_preview_files
                    ]
                }
            ))

        await cl.Message(
            content=content,
            elements=all_elements,
            actions=actions or None,
        ).send()

        # 將圖片加入到 message_history 中（只有圖片需要加入對話歷史）
        if append_to_history and image_content:
            message_history = cl.user_session.get("message_history", [])
            image_message = {
                "role": "assistant",
                "content": image_content
            }
            message_history.append(image_message)
            cl.user_session.set("message_history", message_history)


async def process_uploaded_elements(elements, use_vision_model: bool = False) -> list[dict]:
    """將 Chainlit 上傳的 elements 轉換為 message content parts（text/image_url）。

    Returns:
        list of content part dicts，可直接 extend 到 message['content']。
    """
    supported_docs = {'.pdf', '.ppt', '.pptx', '.xls', '.xlsx', '.doc', '.docx'}
    images = [f for f in elements if "image" in (f.mime or "")]
    handled_files: set[str] = set()
    parts: list[dict] = []

    # 文件轉 markdown
    for file in elements:
        ext = os.path.splitext(file.name)[1].lower()
        if ext in supported_docs:
            content = await convert_to_markdown(file.path, use_vision_model=use_vision_model)
            parts.append({"type": "text", "text": content})
            handled_files.add(file.name)

    # 圖片轉 base64
    for image in images:
        parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{await encode_image(image.path)}",
                "detail": "high"
            }
        })
        handled_files.add(image.name)

    # 其他未處理格式：加入文字備注
    for file in elements:
        if file.name not in handled_files:
            parts.append({
                "type": "text",
                "text": f"（已收到檔案：{os.path.basename(file.path)}）"
            })

    return parts


@cl.step(name="檔案文本提取")
async def convert_to_markdown(file_path, model="gpt-4o-mini", use_vision_model=False):
    # 根據設定決定是否使用視覺語言模型
    if use_vision_model:
        client = get_llm_client(mode="sync")
        md = MarkItDown(enable_plugins=True, llm_client=client, llm_model=model)
    else:
        md = MarkItDown(enable_plugins=True)
    md.register_converter(PyMuPdfConverter(), priority=-1.0)  # 優先於 pdfminer（priority 越小越先執行），修正 CJK 亂碼

    # 將同步的 md.convert 包裝成非同步呼叫
    result = await asyncio.to_thread(md.convert, file_path, extract_pages=True)

    return result.text_content
