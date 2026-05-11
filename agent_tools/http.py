import os
import json
import time
from pydantic import Field
from agent_tools._context import mcp, _session_ctx, get_conversation_folder
from agent_tools._path_utils import _resolve_file_path, _check_path_in_allowed_roots
from utils.user_profile import get_user_profile_dir, get_conversation_artifacts_dir


def _get_internal_auth_rules() -> list[tuple[str, dict]]:
    rules = []
    llm_base = os.getenv("BASE_URL", "").rstrip("/")
    if llm_base:
        rules.append((llm_base, {"Authorization": f"Bearer {os.getenv('LLM_API_KEY', '')}"}))
    return rules


@mcp.tool()
async def http_request(
    url: str = Field(description="請求目標 URL"),
    method: str = Field(description="HTTP 方法（GET/POST/PUT/PATCH/DELETE），預設 GET", default="GET"),
    headers: str = Field(description='請求 headers，JSON 格式字串，例如：{"Content-Type": "application/json"}。可省略', default=""),
    body: str = Field(description="請求 body，純文字字串。若要送 JSON 請在 headers 指定 Content-Type: application/json。指定 form_fields 時此欄位會被忽略。可省略", default=""),
    stream: bool = Field(description="是否啟用串流模式，逐 chunk 推送到 UI 子步驟，且回應內容一定會寫入對話資料夾檔案。預設 False", default=False),
    stream_save_filename: str = Field(description="串流模式下儲存回應內容的檔名（僅檔名，不含路徑）。若省略，系統自動以 http_stream_<timestamp>.txt 命名。", default=""),
    form_fields: str = Field(
        description=(
            "multipart/form-data 欄位，JSON 格式。值若為存在的檔案路徑則自動以二進位上傳，否則當普通字串。\n"
            "例如：{\"file\": \"audio.mp3\", \"model\": \"whisper-1\", \"language\": \"zh\"}\n"
            "指定後，body 參數會被忽略。檔案必須位於對話資料夾或使用者 user_profiles 目錄內。可省略。"
        ),
        default=""
    ),
) -> str:
    """發送 HTTP 請求。支援串流回應，串流內容會即時顯示在 UI 子步驟中（最新 200 字元）。
    可透過 form_fields 以 multipart/form-data 方式上傳檔案並附帶其他欄位。
    目標 URL 若符合內部服務白名單，系統自動注入 Authorization header，key 明文不對外暴露。"""
    import aiohttp

    ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
    STREAM_DISPLAY_LIMIT = 200

    method = method.upper()
    if method not in ALLOWED_METHODS:
        return f"錯誤：不支援的 HTTP 方法 '{method}'，請使用 {', '.join(sorted(ALLOWED_METHODS))} 之一。"

    parsed_headers: dict = {}
    if headers.strip():
        try:
            parsed_headers = json.loads(headers)
        except json.JSONDecodeError as e:
            return f"錯誤：headers 不是有效的 JSON 格式：{e}"

    for base_url, inject_headers in _get_internal_auth_rules():
        if url.startswith(base_url):
            if any(k.lower() == "authorization" for k in parsed_headers):
                return "錯誤：存取內部服務時，headers 不得自帶 Authorization 欄位。"
            parsed_headers.update(inject_headers)
            break

    request_kwargs: dict = {}
    if body.strip():
        request_kwargs["data"] = body

    if form_fields.strip():
        try:
            parsed_form = json.loads(form_fields)
        except json.JSONDecodeError as e:
            return f"錯誤：form_fields 不是有效的 JSON 格式：{e}"

        ctx_data = _session_ctx.get()
        user_id = ctx_data["user_id"]
        conversation_folder = get_conversation_folder()
        allowed_roots = [os.path.realpath(conversation_folder)]
        if user_id:
            allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))

        upload_form = aiohttp.FormData()
        for field_name, field_value in parsed_form.items():
            if field_name == "file":
                candidate = str(field_value)
                src_abs = _resolve_file_path(candidate, conversation_folder)
                if not _check_path_in_allowed_roots(src_abs, allowed_roots):
                    return "存取拒絕：file 的檔案路徑只能指向自己的對話資料夾或 user_profiles 目錄。"
                if not os.path.isfile(src_abs):
                    return f"上傳失敗：檔案不存在：{field_value}"
                upload_form.add_field(
                    field_name,
                    open(src_abs, "rb"),
                    filename=os.path.basename(src_abs),
                )
            else:
                upload_form.add_field(field_name, str(field_value))

        request_kwargs = {"data": upload_form}

    if url.startswith("https://"):
        proxy = os.getenv("TOOL_HTTPS_PROXY") or os.getenv("TOOL_HTTP_PROXY") or None
    else:
        proxy = os.getenv("TOOL_HTTP_PROXY") or os.getenv("TOOL_HTTPS_PROXY") or None

    parent_step = None
    if stream:
        try:
            import chainlit as cl
            parent_step = cl.context.current_step
        except Exception:
            pass

    full_text = ""
    try:
        timeout = aiohttp.ClientTimeout(connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url,
                headers=parsed_headers or None,
                proxy=proxy,
                **request_kwargs
            ) as response:
                status_line = f"HTTP {response.status} {response.reason}"
                key_headers = list(response.headers.items())[:5]
                header_lines = "\n".join(f"{k}: {v}" for k, v in key_headers)

                if stream:
                    async for chunk in response.content.iter_chunked(1024):
                        decoded = chunk.decode("utf-8", errors="replace")
                        full_text += decoded
                        if parent_step:
                            parent_step.output = full_text[-STREAM_DISPLAY_LIMIT:]
                            await parent_step.update()
                else:
                    full_text = await response.text()

        saved_file_info = ""
        if stream:
            artifacts_dir = get_conversation_artifacts_dir(get_conversation_folder())
            os.makedirs(artifacts_dir, exist_ok=True)
            if stream_save_filename.strip():
                save_name = os.path.basename(stream_save_filename.strip())
            else:
                save_name = f"http_stream_{int(time.time())}.txt"
            save_abs = os.path.join(artifacts_dir, save_name)
            with open(save_abs, "w", encoding="utf-8") as _f:
                _f.write(full_text)
            saved_file_info = f"\n[串流內容已寫入檔案：{save_name}]"

        return f"{status_line}\n{header_lines}\n\n{full_text}{saved_file_info}"

    except aiohttp.ClientError as e:
        error_detail = repr(e) if not str(e) else str(e)
        return f"HTTP 請求失敗：{type(e).__name__}: {error_detail}"
