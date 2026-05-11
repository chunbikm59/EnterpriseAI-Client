import os
import re
import json
import asyncio
import uuid
import aiofiles
from pydantic import Field
from agent_tools._context import mcp, _session_ctx, _pending_forms, _pending_renders, _pptx_upload_events, get_conversation_folder
from agent_tools._path_utils import _resolve_file_path, _check_path_in_allowed_roots
from utils.user_profile import get_user_profile_dir, get_conversation_artifacts_dir


@mcp.tool()
async def ask_user_question(
    form_schema: str = Field(
        description=(
            "問卷表單的 JSON 字串。格式範例：\n"
            '{"title": "標題", "description": "說明（可選）", "questions": [\n'
            '  {"id": "q1", "question": "完整問題？", "header": "短標籤",\n'
            '   "type": "single_choice",\n'
            '   "options": [{"label": "選項", "description": "說明（可選）"}],\n'
            '   "required": true, "other_option": true},\n'
            '  {"id": "q2", "question": "多選題？", "header": "Q2",\n'
            '   "type": "multi_choice",\n'
            '   "options": [{"label": "A"}, {"label": "B"}],\n'
            '   "required": false, "other_option": false},\n'
            '  {"id": "q3", "question": "選擇日期？", "header": "日期",\n'
            '   "type": "date", "required": true, "other_option": false}\n'
            "]}\n"
            "type 可為以下四種：\n"
            "  - single_choice：單選按鈕列表，建議 2–5 個選項\n"
            "  - multi_choice：多選 checkbox 列表，限制在 2–5 個選項（選項少、需一眼看清時使用）\n"
            "  - multi_select_dropdown：多選下拉選單，選項超過 5 個時使用（節省空間）\n"
            "  - date：日期選擇器（不需要 options）\n"
            "other_option 為 true 時會自動附加「其他」自由輸入框。\n"
            "required 為 true 時使用者必須填寫才能提交。"
        )
    )
) -> str:
    """
    Use this tool when you need to ask the user questions during execution. This allows you to:
    1. Gather user preferences or requirements
    2. Clarify ambiguous instructions
    3. Get decisions on implementation choices as you work
    4. Offer choices to the user about what direction to take.

    Usage notes:
    - Users will always be able to select "Other" to provide custom text input
    - Use multi_choice type to allow multiple answers to be selected for a question
    - If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label
    - 在 Chainlit 介面顯示動態互動表單，等待使用者填寫後回傳 JSON 字串
    """
    import chainlit as cl

    try:
        schema = json.loads(form_schema)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"form_schema 不是有效的 JSON：{e}"}, ensure_ascii=False)

    if not isinstance(schema.get("questions"), list) or not schema["questions"]:
        return json.dumps({"error": "questions 不能為空"}, ensure_ascii=False)

    ctx = _session_ctx.get()
    session_id = ctx.get("session_id", "")
    if not session_id:
        return json.dumps({"error": "無法取得 session_id，工具必須在 Chainlit session 中執行"}, ensure_ascii=False)

    if session_id in _pending_forms:
        return json.dumps({"error": "目前已有一個表單等待回應，請先完成或取消現有表單"}, ensure_ascii=False)

    form_id = str(uuid.uuid4())[:8]
    event = asyncio.Event()
    result_holder: dict = {"data": None, "cancelled": False}

    original_props = {
        **schema,
        "form_id": form_id,
        "submitted": False,
    }

    _pending_forms[session_id] = {
        "form_id": form_id,
        "event": event,
        "result": result_holder,
        "elem_id": None,
        "msg_id": None,
        "original_props": original_props,
    }

    try:
        elem = cl.CustomElement(
            name="DynamicForm",
            props=original_props,
            display="inline",
        )
        msg = await cl.Message(content="", elements=[elem]).send()

        _pending_forms[session_id]["elem_id"] = elem.id
        _pending_forms[session_id]["msg_id"] = msg.id

        try:
            await asyncio.wait_for(event.wait(), timeout=600.0)
        except asyncio.TimeoutError:
            return json.dumps({"error": "timeout", "message": "表單等待逾時（10 分鐘）"}, ensure_ascii=False)

        if result_holder["cancelled"]:
            return json.dumps({"cancelled": True, "message": "使用者取消了表單"}, ensure_ascii=False)

        return json.dumps({
            "cancelled": False,
            "answers": result_holder["data"],
        }, ensure_ascii=False, indent=2)

    finally:
        _pending_forms.pop(session_id, None)


@mcp.tool()
async def render_html(
    file_path: str = Field(
        description=(
            "已存在的 HTML 檔案路徑。請先用 write_file 將 HTML 寫入後再呼叫此 tool。\n"
            "- 相對路徑：以對話資料夾為 base（例如 artifacts/demo.html）\n"
            "- 絕對路徑：需在自己的對話資料夾或使用者 profile 目錄內\n"
            "HTML 支援：\n"
            "- 純 HTML + CSS（含 <style> 標籤）\n"
            "- JavaScript（含 <script> 標籤）\n"
            "- CDN 引入（如 Chart.js、D3.js、Tailwind CSS、Mermaid.js 等）\n"
            "- SVG 圖形\n"
            "請盡量使用 CDN 引入函式庫，不要依賴本地資源。\n"
            "推薦 CDN 來源：https://cdn.jsdelivr.net、https://cdnjs.cloudflare.com、https://unpkg.com\n"
            "嵌入 YouTube 影片：\n"
            "- 使用 https://www.youtube-nocookie.com/embed/{VIDEO_ID} 格式\n"
            "- 時間戳跳轉：用 JS 修改 iframe src 的 ?start={秒數} 參數，例如：\n"
            "  document.querySelector('iframe').src = 'https://www.youtube-nocookie.com/embed/VIDEO_ID?start=120'\n"
            "- enablejsapi=1 需在有真實 origin 的環境才能運作（sidebar 預覽為 null origin，不支援；"
            "新分頁開啟模式有真實 origin，支援）\n"
            "嵌入使用者上傳的影片（.mp4 / .mkv / .webm 等）：\n"
            "- 使用 <video> 標籤，src 寫相對路徑 ../uploads/影片檔名\n"
            "- 例如：<video src=\"../uploads/video.mkv\" controls style=\"width:100%\"></video>\n"
            "- 系統會自動將相對路徑轉換為完整 API URL\n"
            "只接受 .html 檔案，大小限制 500KB。"
        )
    ),
    title: str = Field(
        default="Artifact",
        description="此 artifact 的標題，顯示在 sidebar 頂部，建議 20 字以內。"
    ),
) -> str:
    """在 Chainlit sidebar 中以沙盒 iframe 渲染 HTML/SVG/JavaScript 內容。
    適合用來展示：資訊視覺化、互動式 UI、圖表、SVG 圖形、靜態網頁、儀表板等。
    渲染後會顯示在右側 sidebar 供使用者即時查看，並支援版本歷史切換。
    使用前請先用 write_file 將 HTML 寫入檔案，再以 file_path 指定路徑呼叫此 tool。
    """
    ctx = _session_ctx.get()
    session_id = ctx.get("session_id", "")
    if not session_id:
        return "錯誤：無法取得 session_id，render_html 只能在 Chainlit session 中使用。"

    if not file_path or not file_path.strip():
        return "錯誤：file_path 不能為空，請先用 write_file 寫入 .html 檔案後再呼叫。"

    MAX_HTML_SIZE = 500 * 1024

    user_id = ctx.get("user_id", "")
    conv_folder = get_conversation_folder()

    abs_path = _resolve_file_path(file_path, conv_folder)
    allowed_roots = [os.path.realpath(conv_folder)]
    if user_id:
        allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))
    if not _check_path_in_allowed_roots(abs_path, allowed_roots):
        return "存取拒絕：只能讀取自己的對話資料夾或使用者目錄。"

    if not os.path.isfile(abs_path):
        return f"檔案不存在：{file_path}"
    if not abs_path.lower().endswith(".html"):
        return f"不支援的格式：只接受 .html 檔案。"

    file_size = os.path.getsize(abs_path)
    if file_size > MAX_HTML_SIZE:
        return f"檔案過大（{file_size / 1024:.1f} KB），超過 500KB 上限。"

    async with aiofiles.open(abs_path, "r", encoding="utf-8") as f:
        html_code = await f.read()

    if not html_code.strip():
        return "錯誤：HTML 檔案內容為空。"

    artifact_id = f"art_{uuid.uuid4().hex[:8]}"
    safe_title = (title or "Artifact").strip()

    CSP_META = (
        '<meta http-equiv="Content-Security-Policy" content="'
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data: "
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://unpkg.com https://d3js.org https://code.highcharts.com "
        "https://fonts.googleapis.com https://fonts.gstatic.com "
        "https://esm.sh https://esm.run "
        "https://www.youtube.com https://www.youtube-nocookie.com "
        "https://i.ytimg.com; "
        "media-src 'self' blob: data: http: https:; "
        "frame-src https://www.youtube.com https://www.youtube-nocookie.com;"
        '">'
    )
    if "<head" in html_code.lower() and "content-security-policy" not in html_code.lower():
        html_code = re.sub(
            r'(<head[^>]*>)',
            r'\1\n  ' + CSP_META,
            html_code,
            count=1,
            flags=re.IGNORECASE,
        )

    conversation_folder = ctx.get("conversation_folder", "")
    if conversation_folder:
        artifacts_dir = get_conversation_artifacts_dir(conversation_folder)
        os.makedirs(artifacts_dir, exist_ok=True)
        html_path = os.path.join(artifacts_dir, f"artifact_{artifact_id}.html")
        try:
            async with aiofiles.open(html_path, "w", encoding="utf-8") as f:
                await f.write(html_code)
        except Exception:
            pass

    _pending_renders[session_id] = {
        "artifact_id": artifact_id,
        "html_code": html_code,
        "title": safe_title,
    }

    return f"[RENDER_HTML_OK] artifact_id={artifact_id} title={safe_title}"


@mcp.tool()
async def render_pptx(
    script_path: str = Field(
        description=(
            "已存在的 pptxgenjs JavaScript 腳本檔案路徑。\n"
            "請先用 write_file 將腳本寫入後再呼叫此 tool（建議路徑：artifacts/slides.js）。\n"
            "- 相對路徑：以對話資料夾為 base（例如 artifacts/slides.js）\n"
            "- 絕對路徑：需在自己的對話資料夾或使用者 profile 目錄內\n"
            "腳本規格：\n"
            "- 必須使用 pptxgenjs API 建立投影片，CDN bundle 暴露的全域建構函式為 PptxGenJS（注意大小寫）\n"
            "- 腳本最後必須呼叫 window.__pptxDone(prs) 傳回 PptxGenJS 實例，以便觸發下載\n"
            "- 圖片嵌入：在 addImage 的 path 欄位直接寫相對路徑（相對於對話資料夾）\n"
            "  支援 uploads/ 和 artifacts/ 下的圖片，例如：\n"
            "  slide.addImage({ path: 'uploads/photo.png', x:1, y:1, w:4, h:3 })\n"
            "範例腳本：\n"
            "  let prs = new PptxGenJS();\n"
            "  let slide = prs.addSlide();\n"
            "  slide.addText('Hello', {x:1, y:1, fontSize:36});\n"
            "  window.__pptxDone(prs);\n"
            "只接受 .js 檔案。"
        )
    ),
    title: str = Field(
        default="簡報",
        description="簡報標題，顯示在 sidebar 頂部，建議 20 字以內。"
    ),
    slide_count: int = Field(
        default=1,
        description="預計的投影片張數（用於 sidebar 佔位顯示）。"
    ),
    template_path: str = Field(
        default="",
        description=(
            "企業模板 .pptx 的路徑（相對於專案根目錄，選填）。\n"
            "啟用 pptgenjs skill 後，從可用資源清單中取得模板路徑，\n"
            "例如：system_skills/pptgenjs/assets/templates/corporate.pptx\n"
            "後端會保留模板的 slideMasters/、slideLayouts/、theme/，\n"
            "並將生成的投影片內容套入。不需要修改腳本的寫法。\n"
            "留空則使用 pptxgenjs 預設樣式，不套用模板。"
        )
    ),
) -> str:
    """在 Chainlit sidebar 中執行 pptxgenjs 腳本並顯示投影片預覽，提供 .pptx 下載按鈕。
    使用 CDN 版本的 pptxgenjs（https://cdn.jsdelivr.net/gh/gitbrent/pptxgenjs/dist/pptxgen.bundle.js）。
    使用前請先用 write_file 將腳本寫入 .js 檔案，再以 script_path 指定路徑呼叫此 tool。
    腳本需以 window.__pptxDone(prs) 傳回 PptxGenJS 實例才能觸發下載。
    """
    from agent_tools._path_utils import _PROJECT_ROOT
    from utils.user_profile import get_user_skills_dir

    ctx = _session_ctx.get()
    session_id = ctx.get("session_id", "")
    user_id = ctx.get("user_id", "")
    if not session_id:
        return "錯誤：無法取得 session_id，render_pptx 只能在 Chainlit session 中使用。"

    if not script_path or not script_path.strip():
        return "錯誤：script_path 不能為空，請先用 write_file 寫入 .js 腳本後再呼叫。"

    conv_folder = get_conversation_folder()
    abs_script_path = _resolve_file_path(script_path, conv_folder)
    allowed_roots = [os.path.realpath(conv_folder)]
    if user_id:
        allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))
    if not _check_path_in_allowed_roots(abs_script_path, allowed_roots):
        return "存取拒絕：只能讀取自己的對話資料夾或使用者目錄。"

    if not os.path.isfile(abs_script_path):
        return f"檔案不存在：{script_path}"
    if not abs_script_path.lower().endswith(".js"):
        return "不支援的格式：只接受 .js 檔案。"

    async with aiofiles.open(abs_script_path, "r", encoding="utf-8") as f:
        pptx_script = await f.read()

    if not pptx_script.strip():
        return "錯誤：腳本檔案內容為空。"

    template_abs_path = ""
    if template_path and template_path.strip():
        norm = template_path.replace("\\", "/").lstrip("/")
        _sys_skills_abs = os.path.realpath(os.path.join(_PROJECT_ROOT, "system_skills"))
        _user_skills_abs = (
            os.path.realpath(get_user_skills_dir(user_id)) if user_id else ""
        )
        candidate = os.path.realpath(os.path.join(_PROJECT_ROOT, norm))
        in_sys  = candidate.startswith(_sys_skills_abs + os.sep)
        in_user = bool(_user_skills_abs and candidate.startswith(_user_skills_abs + os.sep))
        if not (in_sys or in_user):
            return "存取拒絕：template_path 只能指向 system_skills/ 或使用者自己的 skills/ 目錄。"
        if not (os.path.isfile(candidate) and candidate.lower().endswith(".pptx")):
            return f"錯誤：模板檔案不存在或非 .pptx：{template_path}"
        template_abs_path = candidate

    pptx_id = f"pptx_{uuid.uuid4().hex[:8]}"
    safe_title = (title or "簡報").strip()

    _pptx_upload_events[pptx_id] = {
        "event":      asyncio.Event(),
        "png_event":  asyncio.Event(),
        "result":     {"success": False, "error": ""},
        "png_result": {"success": False, "error": "", "slide_count": 0},
    }

    payload = {
        "pptx_id": pptx_id,
        "pptx_script": pptx_script,
        "template_abs_path": template_abs_path,
        "title": safe_title,
        "slide_count": max(1, int(slide_count)),
    }

    from chainlit_app.agent import _handle_render_pptx
    render_error = await _handle_render_pptx(payload, send_message=True)
    if render_error:
        return render_error

    png_entry = _pptx_upload_events.get(pptx_id)
    if png_entry and "png_event" in png_entry:
        try:
            await asyncio.wait_for(png_entry["png_event"].wait(), timeout=120.0)
            if not png_entry["png_result"].get("success"):
                err = png_entry["png_result"].get("error", "未知錯誤")
                return f"PPTX 渲染失敗（PNG 轉換）：{err}"
        except asyncio.TimeoutError:
            return "PPTX 渲染失敗：PNG 轉換逾時（120 秒），請確認 LibreOffice 是否正常。"
        finally:
            _pptx_upload_events.pop(pptx_id, None)

    slide_count = png_entry["png_result"].get("slide_count", 0) if png_entry else 0
    return (
        f"[RENDER_PPTX_OK] pptx_id={pptx_id} slide_count={slide_count}\n"
        f"簡報「{safe_title}」已渲染完成，PNG 縮圖共 {slide_count} 張已就緒。\n"
        f"可呼叫 read_file(\"artifacts/{pptx_id}_slide_001.png\") 進行視覺確認。"
    )
