import os
import re
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from chainlit.auth.cookie import get_token_from_cookies
from chainlit.auth.jwt import decode_jwt

from utils.memory_manager import (
    list_memory_files,
    load_memory_file,
    write_memory_file,
    write_memory_index,
    validate_memory_path,
    load_memory_index,
    get_user_memory_dir,
    MEMORY_FILE_MAX_BYTES,
)

router = APIRouter()


def _get_user_id(request: Request) -> str:
    """從 Chainlit JWT cookie 解碼取得 user.identifier。

    Chainlit 登入後把 JWT 存在 access_token cookie，
    解碼後的 User.identifier 即 user_profiles/ 的目錄名。
    """
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


class WriteMemoryRequest(BaseModel):
    filename: str
    name: str
    description: str
    type: str
    content: str


class WriteIndexRequest(BaseModel):
    content: str


def _build_memory_content(name: str, description: str, mem_type: str, content: str) -> str:
    """組合 YAML frontmatter + Markdown 內容。"""
    frontmatter = f"---\nname: {name}\ndescription: {description}\ntype: {mem_type}\n---\n"
    return frontmatter + content


def _parse_frontmatter_from_content(content: str) -> dict:
    """從完整記憶檔案內容解析 frontmatter。"""
    if not content.startswith("---"):
        return {"content": content}
    end = content.find("\n---", 3)
    if end == -1:
        return {"content": content}
    fm_text = content[3:end].strip()
    result = {}
    for line in fm_text.splitlines():
        m = re.match(r"^(\w+)\s*:\s*(.+)$", line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip()
    body_start = end + 4  # skip "\n---"
    result["content"] = content[body_start:].lstrip("\n")
    return result


def _rebuild_index(user_id: str) -> None:
    """重建 MEMORY.md 索引（根據現有記憶檔案）。"""
    files = list_memory_files(user_id)
    if not files:
        write_memory_index(user_id, "# Memory Index\n")
        return
    # 先讀取現有索引，嘗試保留既有條目順序（按名稱字母排序）
    lines = ["# Memory Index\n"]
    for f in sorted(files, key=lambda x: x["name"].lower()):
        filename = f["filename"]
        name = f["name"] or filename
        description = f["description"] or ""
        hook = f"- [{name}]({filename})"
        if description:
            hook += f" — {description}"
        lines.append(hook)
    write_memory_index(user_id, "\n".join(lines) + "\n")


@router.get("/list")
async def list_memories(request: Request):
    """列出使用者所有記憶檔案。"""
    user_id = _get_user_id(request)
    files = list_memory_files(user_id)
    # 按名稱字母順序排序
    files.sort(key=lambda x: x["name"].lower())
    return {"files": files}


@router.get("/index")
async def get_memory_index(request: Request):
    """讀取 MEMORY.md 索引內容。"""
    user_id = _get_user_id(request)
    content = load_memory_index(user_id)
    return {"content": content}


@router.get("/file/{filename}")
async def read_memory(request: Request, filename: str):
    """讀取單一記憶檔案並解析 frontmatter。"""
    user_id = _get_user_id(request)
    _, error = validate_memory_path(user_id, filename)
    if error:
        raise HTTPException(status_code=400, detail=error)
    raw = load_memory_file(user_id, filename)
    if raw is None:
        raise HTTPException(status_code=404, detail="記憶檔案不存在")
    parsed = _parse_frontmatter_from_content(raw)
    return {
        "filename": filename,
        "name": parsed.get("name", filename),
        "description": parsed.get("description", ""),
        "type": parsed.get("type", ""),
        "content": parsed.get("content", ""),
        "raw": raw,
    }


@router.post("")
async def create_memory(request: Request, body: WriteMemoryRequest):
    """新增記憶檔案。"""
    user_id = _get_user_id(request)

    filename = body.filename
    if not filename.endswith(".md"):
        filename += ".md"
    # 清理檔名：只允許字母、數字、底線、連字號
    filename = re.sub(r"[^\w\-.]", "_", filename)

    _, error = validate_memory_path(user_id, filename)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # 確認不覆蓋已存在的檔案
    memory_dir = get_user_memory_dir(user_id)
    if os.path.exists(os.path.join(memory_dir, filename)):
        raise HTTPException(status_code=409, detail=f"檔案 {filename} 已存在")

    full_content = _build_memory_content(body.name, body.description, body.type, body.content)
    result = write_memory_file(user_id, filename, full_content)
    if result.startswith("錯誤"):
        raise HTTPException(status_code=400, detail=result)

    _rebuild_index(user_id)
    return {"message": "已新增記憶檔案", "filename": filename}


@router.put("/file/{filename}")
async def update_memory(request: Request, filename: str, body: WriteMemoryRequest):
    """更新記憶檔案。"""
    user_id = _get_user_id(request)
    _, error = validate_memory_path(user_id, filename)
    if error:
        raise HTTPException(status_code=400, detail=error)

    full_content = _build_memory_content(body.name, body.description, body.type, body.content)
    result = write_memory_file(user_id, filename, full_content)
    if result.startswith("錯誤"):
        raise HTTPException(status_code=400, detail=result)

    _rebuild_index(user_id)
    return {"message": "已更新記憶檔案", "filename": filename}


@router.delete("/file/{filename}")
async def delete_memory(request: Request, filename: str):
    """刪除記憶檔案。"""
    user_id = _get_user_id(request)
    abs_path, error = validate_memory_path(user_id, filename)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="記憶檔案不存在")

    try:
        os.remove(abs_path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"刪除失敗：{e}")

    _rebuild_index(user_id)
    return {"message": "已刪除記憶檔案", "filename": filename}
