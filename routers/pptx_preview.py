"""
POST /api/pptx-preview
接收前端瀏覽器產生的 .pptx base64，存檔後用 LibreOffice 轉 PNG 縮圖，回傳縮圖 URL 清單。
"""
import asyncio
import base64
import os
import pathlib
import shutil
import subprocess
import uuid

import fitz  # pymupdf
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chainlit.auth.jwt import decode_jwt
from chainlit.auth.cookie import get_token_from_cookies
from utils.user_profile import get_conversation_artifacts_dir

router = APIRouter()
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent

MAX_PPTX_BYTES = 20 * 1024 * 1024  # 20 MB


class PptxPreviewRequest(BaseModel):
    pptx_b64: str
    pptx_id: str
    conversation_id: str


@router.post("/api/pptx-preview")
async def pptx_preview(req: PptxPreviewRequest, request: Request):
    # ── 驗證 JWT ──
    token = get_token_from_cookies(request.cookies)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        user = decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = user.identifier
    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
    safe_conv = "".join(c if c.isalnum() or c in "-_" else "_" for c in req.conversation_id)
    safe_pptx_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in req.pptx_id)

    # ── 解碼 base64 ──
    try:
        pptx_bytes = base64.b64decode(req.pptx_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64")

    if len(pptx_bytes) > MAX_PPTX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    # ── 存放路徑：user_profiles/{uid}/conversations/{conv_id}/artifacts/ ──
    artifacts_dir = _PROJECT_ROOT / "user_profiles" / safe_uid / "conversations" / safe_conv / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    pptx_path = artifacts_dir / f"{safe_pptx_id}.pptx"
    pptx_path.write_bytes(pptx_bytes)

    # ── LibreOffice 轉 PDF（暫存子目錄）──
    soffice = shutil.which("soffice") or shutil.which("soffice.bin")
    if not soffice:
        raise HTTPException(status_code=500, detail="LibreOffice not found on server")

    tmp_dir = artifacts_dir / f"_pptx_tmp_{safe_pptx_id}"
    tmp_dir.mkdir(exist_ok=True)

    def _run_soffice():
        cmd = [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmp_dir), str(pptx_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stderr

    try:
        returncode, stderr = await asyncio.to_thread(_run_soffice)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="LibreOffice conversion timeout")

    if returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"LibreOffice failed: {stderr[-200:]}")

    pdf_path = tmp_dir / f"{safe_pptx_id}.pdf"
    if not pdf_path.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="PDF not generated")

    # ── pymupdf 逐頁轉 PNG ──
    def _render_pages():
        doc = fitz.open(str(pdf_path))
        paths = []
        mat = fitz.Matrix(1.5, 1.5)  # 1.5x ≈ 144dpi，縮圖夠清楚且不過大
        for i in range(doc.page_count):
            dst = artifacts_dir / f"{safe_pptx_id}_slide_{i+1:03d}.png"
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            pix.save(str(dst))
            paths.append(dst)
        doc.close()
        return paths

    try:
        png_paths = await asyncio.to_thread(_render_pages)
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"PNG render failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── 回傳縮圖 URL（走現有 /api/user-files/ 路由，已有 JWT 驗證）──
    slide_urls = [
        f"/api/user-files/user_profiles/{safe_uid}/conversations/{safe_conv}/artifacts/{p.name}"
        for p in png_paths
    ]

    return JSONResponse({"slide_urls": slide_urls})
