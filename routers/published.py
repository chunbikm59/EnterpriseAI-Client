from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from utils.artifact_publisher import get_published_html_path

router = APIRouter()


@router.get("/p/{token}")
async def serve_published(token: str):
    """公開存取已發布的 HTML artifact（無需登入）。"""
    html_path = get_published_html_path(token)
    if html_path is None:
        raise HTTPException(status_code=404)
    return FileResponse(
        html_path,
        media_type="text/html",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
