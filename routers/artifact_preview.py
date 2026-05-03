import pathlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from chainlit.auth.jwt import decode_jwt
from chainlit.auth.cookie import get_token_from_cookies
from utils.user_profile import get_conversation_artifacts_dir

router = APIRouter()
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent


@router.get("/api/artifact-preview/{artifact_id}")
async def serve_artifact_preview(artifact_id: str, conversation_id: str, request: Request):
    """以登入使用者身份 serve artifact HTML，讓新分頁中的圖片/影片等資源可正常帶 cookie。"""
    token = get_token_from_cookies(request.cookies)
    if not token:
        raise HTTPException(status_code=401)
    try:
        user = decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401)

    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in user.identifier)

    # path traversal 防護：conversation_id 只允許 hex + hyphen
    if not all(c in "0123456789abcdefABCDEF-" for c in conversation_id):
        raise HTTPException(status_code=400)

    conversation_folder = str(
        _PROJECT_ROOT / "user_profiles" / safe_uid / "conversations" / conversation_id
    )
    html_path = pathlib.Path(get_conversation_artifacts_dir(conversation_folder)) / f"artifact_{artifact_id}.html"

    # path traversal 防護：確認最終路徑在 project root 內
    try:
        html_path.resolve().relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=403)

    if not html_path.is_file():
        raise HTTPException(status_code=404)

    from utils.signed_url import rewrite_html_img_paths
    html = html_path.read_text(encoding="utf-8")
    html = rewrite_html_img_paths(html, user.identifier, conversation_id)

    return HTMLResponse(content=html)
