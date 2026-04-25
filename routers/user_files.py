import pathlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from chainlit.auth.jwt import decode_jwt
from chainlit.auth.cookie import get_token_from_cookies

router = APIRouter()
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent


@router.get("/{rel_path:path}")
async def serve_user_file(request: Request, rel_path: str):
    token = get_token_from_cookies(request.cookies)
    if not token:
        raise HTTPException(status_code=401)
    try:
        user = decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401)

    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in user.identifier)

    parts = pathlib.PurePosixPath(rel_path).parts
    if len(parts) < 2 or parts[0] != "user_profiles":
        raise HTTPException(status_code=403)
    if parts[1] != safe_uid:
        raise HTTPException(status_code=403)

    file_path = (_PROJECT_ROOT / rel_path).resolve()
    try:
        file_path.relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=403)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(file_path)
