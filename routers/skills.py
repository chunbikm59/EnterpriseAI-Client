import io
import os
import shutil
import zipfile
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from typing import Optional

from chainlit.auth.cookie import get_token_from_cookies
from chainlit.auth.jwt import decode_jwt

from utils.skills_manager import discover_skills, _parse_frontmatter, _find_skill_md
from utils.user_profile import get_user_skills_dir

router = APIRouter()

FILE_MAX_BYTES = 64 * 1024  # 64 KB

SKILL_MD_TEMPLATE = """\
---
name: {name}
description: 在此填寫技能描述，讓 AI 判斷何時啟用。
---

# {name}

## 使用方式

在此說明如何使用此技能。

## 注意事項

- 補充邊界條件或特殊說明
"""


def _get_user_id(request: Request) -> str:
    token = get_token_from_cookies(dict(request.cookies))
    if not token:
        raise HTTPException(status_code=401, detail="未登入（無 access_token cookie）")
    try:
        user = decode_jwt(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"token 驗證失敗：{e}")
    if not user.identifier:
        raise HTTPException(status_code=401, detail="無法取得使用者 identifier")
    return user.identifier


def _safe_skill_path(user_skills_dir: str, skill_name: str) -> str:
    """回傳 skill 目錄的絕對路徑，並確保在 user_skills_dir 範圍內。"""
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill_name)
    target = os.path.realpath(os.path.join(user_skills_dir, safe_name))
    base = os.path.realpath(user_skills_dir)
    if not target.startswith(base + os.sep) and target != base:
        raise HTTPException(status_code=400, detail="非法路徑")
    return target


def _safe_file_path(skill_dir: str, rel_path: str) -> str:
    """回傳 skill 內部檔案的絕對路徑，確保在 skill_dir 範圍內。"""
    target = os.path.realpath(os.path.join(skill_dir, rel_path))
    base = os.path.realpath(skill_dir)
    if not target.startswith(base + os.sep) and target != base:
        raise HTTPException(status_code=400, detail="非法路徑")
    return target


def _build_tree(root: str, rel: str = "") -> dict:
    """遞迴產生目錄樹節點。"""
    abs_path = os.path.join(root, rel) if rel else root
    name = os.path.basename(abs_path) if rel else os.path.basename(root)
    if os.path.isfile(abs_path):
        return {"name": name, "type": "file", "path": rel}
    children = []
    try:
        entries = sorted(os.listdir(abs_path))
    except PermissionError:
        entries = []
    # 目錄排前，再依名稱排序
    dirs = [e for e in entries if os.path.isdir(os.path.join(abs_path, e))]
    files = [e for e in entries if os.path.isfile(os.path.join(abs_path, e))]
    for d in sorted(dirs):
        child_rel = os.path.join(rel, d) if rel else d
        children.append(_build_tree(root, child_rel))
    for f in sorted(files):
        child_rel = os.path.join(rel, f) if rel else f
        children.append({"name": f, "type": "file", "path": child_rel})
    return {"name": name, "type": "dir", "path": rel, "children": children}


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateSkillRequest(BaseModel):
    skill_name: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

class FileDeleteRequest(BaseModel):
    path: str

class DirRequest(BaseModel):
    path: str


# ── Skill 層級 ────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_skills(request: Request):
    """列出用戶技能（user）+ 系統技能（system）。"""
    user_id = _get_user_id(request)
    skills = discover_skills(user_id)
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "source": s.source,
                "skill_dir": s.skill_dir,
            }
            for s in skills
        ]
    }


@router.post("/skill")
async def create_skill(request: Request, body: CreateSkillRequest):
    """新增用戶 skill 目錄，並自動建立 SKILL.md 範本。"""
    user_id = _get_user_id(request)
    user_skills_dir = get_user_skills_dir(user_id)
    os.makedirs(user_skills_dir, exist_ok=True)

    skill_dir = _safe_skill_path(user_skills_dir, body.skill_name)
    safe_name = os.path.basename(skill_dir)

    if os.path.exists(skill_dir):
        raise HTTPException(status_code=409, detail=f"Skill「{safe_name}」已存在")

    os.makedirs(skill_dir)
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_md_path, "w", encoding="utf-8") as f:
        f.write(SKILL_MD_TEMPLATE.format(name=safe_name))

    return {"message": f"已建立 Skill「{safe_name}」", "skill_name": safe_name}


@router.post("/upload-zip")
async def upload_zip(request: Request, file: UploadFile = File(...)):
    """上傳 ZIP 壓縮檔以建立新 Skill；ZIP 頂層目錄名稱即為 skill_name。"""
    user_id = _get_user_id(request)
    user_skills_dir = get_user_skills_dir(user_id)
    os.makedirs(user_skills_dir, exist_ok=True)

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="只接受 .zip 檔案")

    data = await file.read()
    if len(data) > 20 * 1024 * 1024:  # 20 MB
        raise HTTPException(status_code=400, detail="ZIP 檔案超過 20 MB 上限")

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="無效的 ZIP 檔案")

    # 找出 ZIP 頂層目錄（過濾 macOS __MACOSX 等雜訊目錄）
    names = [n for n in zf.namelist() if not n.startswith("__MACOSX") and not os.path.basename(n).startswith(".")]
    if not names:
        raise HTTPException(status_code=400, detail="ZIP 內容為空")

    top_dirs = {n.split("/")[0] for n in names if "/" in n or not n.endswith("/")}
    if len(top_dirs) == 1:
        skill_name_raw = top_dirs.pop()
        strip_prefix = skill_name_raw + "/"
    else:
        # 沒有單一頂層目錄 → 用 ZIP 檔名（去掉 .zip）
        skill_name_raw = os.path.splitext(os.path.basename(file.filename))[0]
        strip_prefix = ""

    skill_dir = _safe_skill_path(user_skills_dir, skill_name_raw)
    safe_name = os.path.basename(skill_dir)

    if os.path.exists(skill_dir):
        raise HTTPException(status_code=409, detail=f"Skill「{safe_name}」已存在")

    os.makedirs(skill_dir)
    try:
        for member in zf.infolist():
            mname = member.filename
            if mname.startswith("__MACOSX") or os.path.basename(mname).startswith("."):
                continue
            # 去掉頂層目錄前綴
            rel = mname[len(strip_prefix):] if strip_prefix and mname.startswith(strip_prefix) else mname
            if not rel or rel.endswith("/"):
                continue  # 純目錄 entry

            abs_path = _safe_file_path(skill_dir, rel)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with zf.open(member) as src, open(abs_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
    except Exception as e:
        shutil.rmtree(skill_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"解壓縮失敗：{e}")

    return {"message": f"已從 ZIP 建立 Skill「{safe_name}」", "skill_name": safe_name}


@router.delete("/skill/{skill_name}")
async def delete_skill(request: Request, skill_name: str):
    """刪除整個用戶 skill 目錄（遞迴）。"""
    user_id = _get_user_id(request)
    user_skills_dir = get_user_skills_dir(user_id)
    skill_dir = _safe_skill_path(user_skills_dir, skill_name)

    if not os.path.exists(skill_dir):
        raise HTTPException(status_code=404, detail="Skill 不存在")

    shutil.rmtree(skill_dir)
    return {"message": f"已刪除 Skill「{skill_name}」"}


# ── Skill 內部操作 ─────────────────────────────────────────────────────────────

def _resolve_skill_dir(request: Request, skill_name: str) -> tuple[str, str, bool]:
    """
    解析 skill 目錄，回傳 (user_id, skill_dir, is_system)。
    先找用戶技能，再找系統技能；找不到則 404。
    """
    user_id = _get_user_id(request)
    skills = discover_skills(user_id)
    matched = next((s for s in skills if s.name == skill_name), None)
    if matched is None:
        raise HTTPException(status_code=404, detail=f"Skill「{skill_name}」不存在")
    return user_id, matched.skill_dir, matched.source == "system"


@router.get("/skill/{skill_name}/tree")
async def get_skill_tree(request: Request, skill_name: str):
    """回傳 skill 目錄樹 JSON。"""
    _, skill_dir, _ = _resolve_skill_dir(request, skill_name)
    tree = _build_tree(skill_dir)
    # 路徑分隔符統一為 /（前端顯示用）
    def normalize(node: dict) -> dict:
        node["path"] = node["path"].replace("\\", "/")
        for child in node.get("children", []):
            normalize(child)
        return node
    return {"tree": normalize(tree)}


@router.get("/skill/{skill_name}/file")
async def read_skill_file(request: Request, skill_name: str, path: str = Query(...)):
    """讀取 skill 內部檔案（文字）。"""
    _, skill_dir, _ = _resolve_skill_dir(request, skill_name)
    abs_path = _safe_file_path(skill_dir, path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="檔案不存在")
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"讀取失敗：{e}")
    return {"path": path, "content": content}


@router.post("/skill/{skill_name}/file")
async def write_skill_file(request: Request, skill_name: str, body: FileWriteRequest):
    """新增或覆寫 skill 內部檔案。"""
    _, skill_dir, is_system = _resolve_skill_dir(request, skill_name)
    if is_system:
        raise HTTPException(status_code=403, detail="系統 Skill 不可編輯")

    abs_path = _safe_file_path(skill_dir, body.path)
    encoded = body.content.encode("utf-8")
    if len(encoded) > FILE_MAX_BYTES:
        raise HTTPException(status_code=400, detail=f"檔案超過 {FILE_MAX_BYTES // 1024} KB 上限")

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(body.content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"寫入失敗：{e}")
    return {"message": "已儲存", "path": body.path}


@router.delete("/skill/{skill_name}/file")
async def delete_skill_file(request: Request, skill_name: str, body: FileDeleteRequest):
    """刪除 skill 內部檔案。"""
    _, skill_dir, is_system = _resolve_skill_dir(request, skill_name)
    if is_system:
        raise HTTPException(status_code=403, detail="系統 Skill 不可編輯")

    abs_path = _safe_file_path(skill_dir, body.path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="檔案不存在")
    try:
        os.remove(abs_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"刪除失敗：{e}")
    return {"message": "已刪除", "path": body.path}


@router.post("/skill/{skill_name}/dir")
async def create_skill_dir(request: Request, skill_name: str, body: DirRequest):
    """在 skill 目錄內新增子目錄。"""
    _, skill_dir, is_system = _resolve_skill_dir(request, skill_name)
    if is_system:
        raise HTTPException(status_code=403, detail="系統 Skill 不可編輯")

    abs_path = _safe_file_path(skill_dir, body.path)
    if os.path.exists(abs_path):
        raise HTTPException(status_code=409, detail="目錄已存在")
    try:
        os.makedirs(abs_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"建立失敗：{e}")
    return {"message": "已建立目錄", "path": body.path}


@router.delete("/skill/{skill_name}/dir")
async def delete_skill_dir(request: Request, skill_name: str, body: DirRequest):
    """遞迴刪除 skill 目錄內的子目錄。"""
    _, skill_dir, is_system = _resolve_skill_dir(request, skill_name)
    if is_system:
        raise HTTPException(status_code=403, detail="系統 Skill 不可編輯")

    abs_path = _safe_file_path(skill_dir, body.path)
    if not os.path.isdir(abs_path):
        raise HTTPException(status_code=404, detail="目錄不存在")
    # 防止刪除 skill 根目錄本身
    if os.path.realpath(abs_path) == os.path.realpath(skill_dir):
        raise HTTPException(status_code=400, detail="不可刪除 Skill 根目錄（請用刪除 Skill 功能）")
    try:
        shutil.rmtree(abs_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"刪除失敗：{e}")
    return {"message": "已刪除目錄", "path": body.path}
