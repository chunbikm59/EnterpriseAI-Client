import os
import asyncio
from contextvars import ContextVar
from mcp.server.fastmcp import FastMCP
from markitdown import MarkItDown
from utils.pdf_converter import PyMuPdfConverter

mcp = FastMCP(name="buildin_tools", json_response=False, stateless_http=False)

# ── 全域 MarkItDown 單例（避免每次呼叫重新初始化 requests.Session / magika.Magika）──
_md = MarkItDown(enable_plugins=True)
_md.register_converter(PyMuPdfConverter(), priority=-1.0)  # 優先於 pdfminer（priority 越小越先執行），修正 CJK 亂碼

# ── Session Context (contextvars，取代 FastMCP Context) ──
_session_ctx: ContextVar[dict] = ContextVar(
    "buildin_session_ctx",
    default={"session_id": "", "user_id": "", "conversation_id": "", "conversation_folder": ""}
)

# ── AgentSkills session registry ──
# 因為 buildin MCP server 是 in-process（同進程 HTTP transport），
# 無法透過 env var 傳遞資料，改用 module-level dict 按 Chainlit session_id 儲存技能目錄。
_session_skill_catalogs: dict[str, str] = {}

# ── 動態表單等待機制 ──
# key: Chainlit session_id（cl.user_session.get('id')，不是 conversation_id）
# value: {"form_id": str, "event": asyncio.Event, "result": dict,
#         "elem_id": str|None, "msg_id": str|None, "original_props": dict}
_pending_forms: dict[str, dict] = {}

# ── HTML Render 暫存機制 ──
# key: Chainlit session_id，value: {"artifact_id": str, "html_code": str, "title": str}
_pending_renders: dict[str, dict] = {}

# ── PPTX 上傳等待機制 ──
# key: pptx_id（全域唯一），value: {
#   "event":      asyncio.Event(),   # .pptx 已存檔
#   "png_event":  asyncio.Event(),   # PNG 全部生成完畢
#   "result":     {"success": bool, "error": str},
#   "png_result": {"success": bool, "error": str, "slide_count": int},
# }
_pptx_upload_events: dict[str, dict] = {}

# ── Markdown Render 暫存機制 ──
# key: Chainlit session_id，value: {"md_id": str, "markdown_content": str, "title": str, "file_path": str}
_pending_md_renders: dict[str, dict] = {}


def get_conversation_folder() -> str:
    return _session_ctx.get()["conversation_folder"]


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size:,} bytes"


async def _list_conversation_files(root_folder: str) -> str:
    """列出對話資料夾下 uploads/ 與 artifacts/ 的所有檔案，分區顯示。"""
    sections = []
    for subdir in ("uploads", "artifacts"):
        subdir_path = os.path.join(root_folder, subdir)
        if not os.path.isdir(subdir_path):
            sections.append(f"{subdir}/ (不存在)")
            continue
        items = sorted(f for f in os.listdir(subdir_path)
                       if os.path.isfile(os.path.join(subdir_path, f)))
        if not items:
            sections.append(f"{subdir}/ (空)")
            continue
        lines = [f"{subdir}/ ({len(items)} 個檔案):"]
        for name in items:
            size = os.path.getsize(os.path.join(subdir_path, name))
            lines.append(f"  {subdir}/{name} ({_format_size(size)})")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


async def _list_files_internal(root_folder: str, offset: int = 0, limit: int = 200):
    """內部函數：列出指定資料夾中的檔案，供多個工具重用"""
    try:
        if not os.path.exists(root_folder):
            return "資料夾不存在"

        all_items = sorted(os.listdir(root_folder))
        total = len(all_items)
        page_items = all_items[offset:] if limit <= 0 else all_items[offset: offset + limit]

        if not page_items:
            return "資料夾是空的" if total == 0 else f"沒有更多項目（共 {total} 個）"

        files = []
        for item in page_items:
            item_path = os.path.join(root_folder, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                size_str = f"{size:,} bytes"
                if size > 1024:
                    size_str = f"{size/1024:.1f} KB"
                if size > 1024*1024:
                    size_str = f"{size/(1024*1024):.1f} MB"
                files.append(f"{item} ({size_str})")
            elif os.path.isdir(item_path):
                files.append(f"{item}/ (資料夾)")

        end = offset + len(page_items)
        header = f"[第 {offset + 1}–{end} 個，共 {total} 個]\n\n"
        result = header + "檔案列表:\n" + "\n".join(files)
        if end < total:
            result += f"\n\n（還有更多項目，可使用 offset={end} 繼續列出）"
        return result

    except Exception as e:
        return f"列出檔案時發生錯誤: {str(e)}"
