import pathlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from utils.artifact_publisher import get_published_html_path, get_published_artifact_record

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


@router.get("/p/{token}/files/{rel_path:path}")
async def serve_published_resource(token: str, rel_path: str):
    """公開存取已發布 artifact 的附屬資源（影片、音訊、圖片、下載檔等）。

    安全保護：
    - token 格式驗證（32 位 hex）
    - DB 查詢確認 token 存在且有 conversation_folder
    - rel_path 只允許 uploads/ 或 artifacts/ 開頭，拒絕含 .. 的路徑
    - resolve() 後確認路徑在 conversation_folder 範圍內（防 path traversal）
    """
    if not token or len(token) != 32 or not all(c in "0123456789abcdef" for c in token):
        raise HTTPException(status_code=404)

    record = get_published_artifact_record(token)
    if record is None or not record.conversation_folder:
        raise HTTPException(status_code=404)

    pure = pathlib.PurePosixPath(rel_path)
    if not pure.parts or pure.parts[0] not in ("uploads", "artifacts"):
        raise HTTPException(status_code=403)
    if ".." in pure.parts:
        raise HTTPException(status_code=403)

    conv_dir = pathlib.Path(record.conversation_folder).resolve()
    file_path = (conv_dir / rel_path).resolve()
    try:
        file_path.relative_to(conv_dir)
    except ValueError:
        raise HTTPException(status_code=403)

    if not file_path.is_file():
        raise HTTPException(status_code=404)

    return FileResponse(
        file_path,
        headers={"Cache-Control": "public, max-age=86400"},
    )
