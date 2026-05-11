import os
import asyncio
import json
import uuid
import aiofiles
from pathlib import Path
from pydantic import Field
from agent_tools._context import mcp, _session_ctx, _pending_md_renders, get_conversation_folder
from agent_tools._path_utils import _resolve_file_path, _resolve_user_path, _check_path_in_allowed_roots, _PROJECT_ROOT
from agent_tools._edit_utils import _apply_edit
from agent_tools._skill_utils import _write_skill_file
from utils.user_profile import (
    get_user_profile_dir, get_user_memory_dir, get_user_skills_dir,
    get_conversation_artifacts_dir,
)
from utils.signed_url import fix_md_relative_paths
from utils.file_handler import _get_text_file_info
from utils.memory_manager import (
    write_memory_file, write_memory_index,
    validate_memory_path, list_memory_files,
)
from agent_tools._context import _md, _list_conversation_files


@mcp.tool()
async def list_files(
    directory: str = Field(default="conversation", description=(
        "要列出的目錄：\n"
        "- 'conversation'（預設）：本次對話資料夾（展開 uploads/ 與 artifacts/ 兩個子資料夾）\n"
        "- 'memory'：使用者長期記憶目錄（含 type/description，供判斷哪個需更新）"
    )),
):
    """列出指定目錄中的檔案。conversation 模式會分區顯示 uploads/ 和 artifacts/ 的內容。"""
    if directory == "memory":
        user_id = _session_ctx.get()["user_id"]
        files = list_memory_files(user_id)
        if not files:
            return "記憶目錄目前沒有任何檔案。"
        lines = [
            f"- {f['filename']} [{f.get('type', '')}] — {f.get('description', '（無描述）')} ({f['size_bytes']} bytes)"
            for f in files
        ]
        return "記憶目錄檔案清單：\n" + "\n".join(lines)
    root_folder = get_conversation_folder()
    return await _list_conversation_files(root_folder)


@mcp.tool()
async def read_file(
    filename: str = Field(description=(
        "要讀取的檔案名稱或路徑。支援：\n"
        "- 對話 artifacts 檔案：artifacts/output.md（需含 artifacts/ 前綴）\n"
        "- 對話上傳檔案：uploads/file.pdf（需含 uploads/ 前綴）\n"
        "- 記憶檔案：memory/filename.md\n"
        "- 支援格式：PDF, PowerPoint, Word, Excel, Images, HTML, CSV, JSON, XML, ZIP, EPub 等"
    )),
    start_line: int = Field(1, description="從第幾行開始讀取（從 1 起算，預設 1）"),
    end_line: int = Field(2000, description="讀到第幾行結束（預設 2000；0 表示讀到 start_line+1999）"),
):
    '''將檔案轉成 markdown 格式，預設回傳第 1–2000 行，可自行指定範圍，無行數上限。支援對話資料夾內的檔案，以及自己的 user_profiles 技能資源。'''

    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    conversation_folder = get_conversation_folder()

    abs_path = _resolve_user_path(filename, user_id, conversation_folder)
    allowed_roots = [
        os.path.realpath(conversation_folder),
        os.path.realpath(os.path.join(_PROJECT_ROOT, "system_skills")),
    ]
    if user_id:
        allowed_roots.append(os.path.realpath(get_user_profile_dir(user_id)))

    if not _check_path_in_allowed_roots(abs_path, allowed_roots):
        return "存取拒絕：只能讀取自己的資料夾。"

    if not await asyncio.to_thread(os.path.exists, abs_path):
        return f"檔案不存在：{filename}"

    _IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    if os.path.splitext(abs_path)[1].lower() in _IMAGE_EXTENSIONS:
        return json.dumps(
            {"__image_files__": {os.path.basename(abs_path): abs_path}, "summary": f"圖片：{filename}"},
            ensure_ascii=False,
        )

    FILE_SIZE_LIMIT = 100 * 1024 * 1024
    file_size = await asyncio.to_thread(os.path.getsize, abs_path)
    if file_size > FILE_SIZE_LIMIT:
        size_mb = file_size / (1024 * 1024)
        return (
            f"檔案過大（{size_mb:.1f} MB），超過 50 MB 上限，無法讀取。\n"
            f"建議：若為文字檔案，請使用其他方式分段傳入內容。"
        )

    try:
        result = await asyncio.to_thread(_md.convert, abs_path, extract_pages=True)
    except FileNotFoundError:
        return f"檔案不存在：{filename}"
    except Exception as e:
        return f"檔案轉換失敗：{str(e)}"

    full_text = result.text_content
    lines = full_text.splitlines()
    total = len(lines)
    total_chars = len(full_text)

    if total == 0:
        return f"[檔案內容為空]\n\n{filename} 轉換後沒有任何文字內容。"

    LARGE_LINE_THRESHOLD = 2000
    LARGE_CHAR_THRESHOLD = 50_000
    persist_note = ""
    if total > LARGE_LINE_THRESHOLD or total_chars > LARGE_CHAR_THRESHOLD:
        base_name = os.path.splitext(os.path.basename(abs_path))[0]
        _artifacts = get_conversation_artifacts_dir(conversation_folder)
        os.makedirs(_artifacts, exist_ok=True)
        saved_path = os.path.join(_artifacts, f"{base_name}_converted.md")
        if not await asyncio.to_thread(os.path.exists, saved_path):
            def _write():
                with open(saved_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
            await asyncio.to_thread(_write)
        persist_note = (
            f"[完整轉換結果已儲存至：{os.path.basename(saved_path)}（共 {total} 行，{total_chars:,} 字元）]\n"
            f"可使用 read_file 指定 start_line/end_line 分段讀取。\n\n"
        )

    actual_start = max(1, start_line)
    if end_line <= 0:
        actual_end = actual_start + 1999
    elif end_line < actual_start:
        actual_end = actual_start + 1999
    else:
        actual_end = end_line
    actual_end = min(actual_end, total)

    if actual_start > total:
        return (
            f"start_line={start_line} 超過檔案總行數（共 {total} 行）。\n"
            f"請使用 start_line=1 到 start_line={total} 之間的值。"
        )

    numbered_lines = [
        f"{lineno}\t{line}"
        for lineno, line in enumerate(lines[actual_start - 1 : actual_end], start=actual_start)
    ]
    chunk = "\n".join(numbered_lines)

    OUTPUT_CHAR_LIMIT = 50_000
    truncated = False
    if len(chunk) > OUTPUT_CHAR_LIMIT:
        chunk = chunk[:OUTPUT_CHAR_LIMIT]
        last_nl = chunk.rfind('\n')
        if last_nl > OUTPUT_CHAR_LIMIT * 0.5:
            chunk = chunk[:last_nl]
        actual_end = actual_start + chunk.count('\n')
        truncated = True

    header = f"{persist_note}[第 {actual_start}–{actual_end} 行，共 {total} 行]\n\n"
    footer = ""
    if truncated:
        footer = f"\n\n（輸出已達 50,000 字元上限，截斷於第 {actual_end} 行。請使用 start_line={actual_end + 1} 繼續讀取）"
    elif actual_end < total:
        footer = f"\n\n（若想閱讀更多內容，請使用 start_line={actual_end + 1} 繼續讀取）"

    return header + chunk + footer


@mcp.tool()
async def write_file(
    path: str = Field(description=(
        "寫入路徑：\n"
        "- 對話 artifacts 資料夾：artifacts/output.md（必須含 artifacts/ 前綴）\n"
        "- 記憶目錄：memory/filename.md\n"
        "  記憶目錄規則：只允許 .md 副檔名；內容檔上限 4KB；MEMORY.md 索引上限 25KB/200行\n"
        "- 使用者技能目錄：skills/{name}/SKILL.md 或 skills/{name}/scripts/xxx.py 等\n"
        "  寫入 SKILL.md 時系統自動驗證格式並更新技能清單"
    )),
    content: str = Field(description="寫入的完整內容"),
) -> str:
    """在對話 artifacts/ 資料夾或使用者記憶目錄中寫入或覆蓋檔案。
    對話資料夾寫入時，路徑必須以 artifacts/ 開頭（例如 artifacts/output.md）。
    記憶目錄寫入：
    - memory/MEMORY.md：更新記憶索引（每行：- [標題](file.md) — 一行摘要）
    - memory/filename.md：記憶內容檔（含 YAML frontmatter: name/description/type）
    - 新建記憶檔後需同步更新 MEMORY.md；保存前先 list_files(directory="memory") 確認是否有可更新的現有記憶

    嵌入圖片時請使用相對路徑（相對於本次寫入的檔案本身的位置），對話資料夾結構如下：
      {conversation_folder}/
      ├── artifacts/   ← write_file 輸出位置
      └── uploads/     ← 使用者上傳檔案
    範例（檔案寫到 artifacts/report.md）：
      - 引用 artifacts/ 的圖片：![圖](frame_001.png)        ← 同目錄，只寫檔名
      - 引用 uploads/ 的圖片：  ![圖](../uploads/photo.jpg) ← 上層目錄再進 uploads/
    """
    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    session_id = ctx_data.get("session_id", "")
    conversation_folder = get_conversation_folder()

    memory_dir_abs = os.path.realpath(get_user_memory_dir(user_id))
    artifacts_dir = get_conversation_artifacts_dir(conversation_folder)
    artifacts_abs = os.path.realpath(artifacts_dir)

    target_abs = _resolve_user_path(path, user_id, conversation_folder)

    if target_abs.startswith(memory_dir_abs + os.sep) or target_abs == memory_dir_abs:
        filename = os.path.basename(target_abs)
        if filename == "MEMORY.md":
            return write_memory_index(user_id, content)
        return write_memory_file(user_id, filename, content)

    user_skills_abs = os.path.realpath(get_user_skills_dir(user_id))
    if target_abs.startswith(user_skills_abs + os.sep):
        return await _write_skill_file(target_abs, user_skills_abs, content, session_id, user_id)

    if not target_abs.startswith(artifacts_abs + os.sep):
        return "存取拒絕：只能寫入自己的對話 artifacts/ 資料夾或記憶目錄。"
    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    if target_abs.endswith(".md"):
        content = fix_md_relative_paths(content, target_abs)
    with open(target_abs, "w", encoding="utf-8") as f:
        f.write(content)

    is_text, lang = _get_text_file_info(os.path.basename(target_abs))
    if is_text and session_id:
        file_id = f"md_{uuid.uuid4().hex[:8]}"
        safe_title = os.path.basename(target_abs)
        if target_abs.endswith(".md"):
            display_content = content
        else:
            fence_lang = lang or ""
            display_content = f"```{fence_lang}\n{content}\n```"
        _pending_md_renders[session_id] = {
            "md_id":            file_id,
            "markdown_content": display_content,
            "title":            safe_title,
            "file_path":        target_abs,
        }
        return f"已寫入：{safe_title} [RENDER_MARKDOWN_OK] md_id={file_id} title={safe_title}"

    return f"已寫入：{os.path.basename(target_abs)}"


@mcp.tool()
async def grep_files(
    pattern: str = Field(description="搜尋的正則表達式（Python re 語法），例如 '## .+' 或 'TODO'"),
    path: str = Field(
        default="artifacts/",
        description=(
            "指定搜尋的檔案或目錄（與 write_file 相同前綴規則）：\n"
            "- 目錄：artifacts/、uploads/、memory/\n"
            "- 單一檔案：artifacts/report.md\n"
            "預設搜尋 artifacts/ 目錄"
        ),
    ),
    glob: str = Field(
        default="**/*",
        description="在目錄下過濾檔案的 glob pattern，例如 '*.md'、'*.py'。指定單一檔案時忽略此參數。",
    ),
    context_lines: int = Field(default=3, description="每個匹配前後顯示的行數（0–10）"),
    ignore_case: bool = Field(default=False, description="是否忽略大小寫"),
    head_limit: int = Field(default=250, description="輸出截斷行數，超過則截斷並提示（等同 | head -N）。傳 0 表示不限制。"),
    offset: int = Field(default=0, description="跳過前 N 行輸出（配合 head_limit 分頁，等同 | tail -n +N）"),
) -> str:
    """在對話資料夾或記憶目錄中用正則表達式搜尋內容，回傳匹配行號與上下文。
    適合在使用 edit_file 取代前先確認 old_string 的確切位置與內容。
    輸出超過 head_limit 行時自動截斷；用 offset 搭配 head_limit 可分頁取得剩餘結果。
    """
    import re

    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    conversation_folder = get_conversation_folder()

    context_lines = max(0, min(10, context_lines))
    offset = max(0, offset)

    target_abs = _resolve_user_path(path, user_id, conversation_folder)

    memory_dir_abs = os.path.realpath(get_user_memory_dir(user_id))
    conv_abs = os.path.realpath(conversation_folder)
    if not _check_path_in_allowed_roots(target_abs, [conv_abs, memory_dir_abs]):
        return "存取拒絕：只能搜尋對話資料夾或記憶目錄。"

    target_path = Path(target_abs)
    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        files = sorted(f for f in target_path.glob(glob) if f.is_file())
    else:
        return f"路徑不存在：{path}"

    if not files:
        return f"沒有找到符合 '{glob}' 的檔案。"

    try:
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"正則表達式錯誤：{e}"

    all_output_lines: list[str] = []
    total_matches = 0

    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = text.splitlines()
        file_match_blocks = []

        for lineno, line in enumerate(lines, start=1):
            if regex.search(line):
                total_matches += 1
                start = max(0, lineno - 1 - context_lines)
                end = min(len(lines), lineno + context_lines)
                file_match_blocks.append({
                    "match_line": lineno,
                    "start": start + 1,
                    "lines": lines[start:end],
                })

        if not file_match_blocks:
            continue

        try:
            rel = file_path.relative_to(Path(conv_abs))
        except ValueError:
            try:
                rel = file_path.relative_to(Path(memory_dir_abs).parent)
            except ValueError:
                rel = file_path

        all_output_lines.append(str(rel).replace("\\", "/"))
        prev_end = -1
        for block in file_match_blocks:
            if prev_end != -1 and block["start"] > prev_end + 1:
                all_output_lines.append("--")
            for i, ln in enumerate(block["lines"]):
                lno = block["start"] + i
                prefix = ">" if lno == block["match_line"] else " "
                all_output_lines.append(f"  {prefix}{lno:4d}: {ln}")
            prev_end = block["start"] + len(block["lines"]) - 1
        all_output_lines.append("")

    if total_matches == 0:
        return f"沒有找到符合 '{pattern}' 的內容。"

    total_lines = len(all_output_lines)
    windowed = all_output_lines[offset:]
    truncated = False
    if head_limit > 0 and len(windowed) > head_limit:
        windowed = windowed[:head_limit]
        truncated = True

    summary_parts = [f"共 {total_matches} 個匹配，輸出 {total_lines} 行"]
    if truncated:
        shown_end = offset + head_limit
        summary_parts.append(f"已截斷（顯示第 {offset + 1}–{shown_end} 行）；用 offset={shown_end} 取得後續結果")

    return "\n".join(windowed) + "\n" + "；".join(summary_parts)


@mcp.tool()
async def edit_file(
    path: str = Field(description=(
        "要編輯的檔案路徑（與 write_file 相同前綴規則）：\n"
        "- 對話 artifacts 檔案：artifacts/output.md\n"
        "- 記憶檔案：memory/filename.md\n"
        "- 使用者技能檔案：skills/{name}/SKILL.md 等\n"
        "注意：此工具只替換片段，不覆蓋整個檔案。"
    )),
    old_string: str = Field(description=(
        "要被替換的原始文字片段。必須與檔案內容完全一致（含縮排、空白）。\n"
        "建議先用 grep_files 或 read_file 確認確切內容後再填入。\n"
        "若該片段在檔案中出現多次，替換將失敗（除非設 replace_all=true）。"
    )),
    new_string: str = Field(description=(
        "替換後的新文字。可以為空字串（代表刪除 old_string）。\n"
        "縮排與換行需自行維護，系統不會自動調整。"
    )),
    replace_all: bool = Field(
        default=False,
        description="是否替換檔案中所有符合 old_string 的位置（預設 false：只替換第一個）。",
    ),
) -> str:
    """在檔案中搜尋 old_string 並替換為 new_string，無需重寫整個檔案。
    適合對大型檔案進行局部修改，節省 token 消耗。
    建議先用 grep_files 確認 old_string 的確切位置與內容。
    """
    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    session_id = ctx_data.get("session_id", "")
    conversation_folder = get_conversation_folder()

    memory_dir_abs  = os.path.realpath(get_user_memory_dir(user_id))
    artifacts_abs   = os.path.realpath(get_conversation_artifacts_dir(conversation_folder))
    user_skills_abs = os.path.realpath(get_user_skills_dir(user_id))

    target_abs = _resolve_user_path(path, user_id, conversation_folder)

    if target_abs.startswith(memory_dir_abs + os.sep) or target_abs == memory_dir_abs:
        filename = os.path.basename(target_abs)
        abs_path, err = validate_memory_path(user_id, filename)
        if err:
            return f"存取拒絕：{err}"
        if not os.path.exists(abs_path):
            return f"記憶檔案不存在：{filename}"
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        new_content, error = _apply_edit(content, old_string, new_string, replace_all)
        if error:
            return f"編輯失敗：{error}"
        if filename == "MEMORY.md":
            return write_memory_index(user_id, new_content)
        return write_memory_file(user_id, filename, new_content)

    if target_abs.startswith(user_skills_abs + os.sep):
        if not os.path.isfile(target_abs):
            return f"檔案不存在：{path}"
        with open(target_abs, "r", encoding="utf-8") as f:
            content = f.read()
        new_content, error = _apply_edit(content, old_string, new_string, replace_all)
        if error:
            return f"編輯失敗：{error}"
        return await _write_skill_file(target_abs, user_skills_abs, new_content, session_id, user_id)

    if not target_abs.startswith(artifacts_abs + os.sep):
        return "存取拒絕：只能編輯自己的對話 artifacts/ 資料夾或記憶目錄。"
    if not os.path.isfile(target_abs):
        return f"檔案不存在：{path}"

    async with aiofiles.open(target_abs, "r", encoding="utf-8") as f:
        content = await f.read()

    new_content, error = _apply_edit(content, old_string, new_string, replace_all)
    if error:
        return f"編輯失敗：{error}"

    if target_abs.endswith(".md"):
        new_content = fix_md_relative_paths(new_content, target_abs)

    async with aiofiles.open(target_abs, "w", encoding="utf-8") as f:
        await f.write(new_content)

    if target_abs.endswith(".md") and session_id:
        md_id = f"md_{uuid.uuid4().hex[:8]}"
        safe_title = os.path.splitext(os.path.basename(target_abs))[0]
        _pending_md_renders[session_id] = {
            "md_id":            md_id,
            "markdown_content": new_content,
            "title":            safe_title,
            "file_path":        target_abs,
        }
        return f"已編輯：{os.path.basename(target_abs)} [RENDER_MARKDOWN_OK] md_id={md_id} title={safe_title}"

    return f"已編輯：{os.path.basename(target_abs)}"


@mcp.tool()
async def delete_file(
    path: str = Field(description=(
        "要刪除的檔案或資料夾路徑：\n"
        "- 對話 artifacts 檔案或子目錄：artifacts/output.md、artifacts/subdir/\n"
        "- 記憶檔案：memory/filename.md\n"
        "  刪除記憶檔後需同步更新 MEMORY.md 移除對應條目\n"
        "- 使用者技能子目錄：user_profiles/{user_id}/skills/{skill_name}/\n"
        "注意：第一層直接子目錄（如 artifacts/ 本身、skills/ 本身）不可刪除"
    )),
) -> str:
    """刪除對話資料夾或記憶目錄中的指定檔案或子資料夾。第一層直接子目錄不可刪除。"""
    import shutil
    ctx_data = _session_ctx.get()
    user_id = ctx_data["user_id"]
    conversation_folder = get_conversation_folder()

    memory_dir_abs = os.path.realpath(get_user_memory_dir(user_id))
    profile_dir_abs = os.path.realpath(get_user_profile_dir(user_id))
    conv_abs = os.path.realpath(conversation_folder)

    target_abs = _resolve_user_path(path, user_id, conversation_folder)

    if target_abs.startswith(memory_dir_abs + os.sep) or target_abs == memory_dir_abs:
        if os.path.isdir(target_abs):
            return "存取拒絕：不能刪除記憶目錄本身。"
        filename = os.path.basename(target_abs)
        filepath, err = validate_memory_path(user_id, filename)
        if err:
            return f"存取拒絕：{err}"
        if not os.path.exists(filepath):
            return f"記憶檔案不存在：{filename}"
        os.remove(filepath)
        return f"已刪除記憶檔案：{filename}（請記得更新 MEMORY.md）"

    if target_abs.startswith(profile_dir_abs + os.sep):
        if not os.path.exists(target_abs):
            return f"不存在：{os.path.basename(target_abs)}"
        parent = os.path.dirname(target_abs)
        if os.path.realpath(parent) == profile_dir_abs:
            return f"存取拒絕：不能刪除第一層目錄 {os.path.basename(target_abs)}/。"
        if os.path.isdir(target_abs):
            shutil.rmtree(target_abs)
            return f"已刪除資料夾：{os.path.basename(target_abs)}/"
        os.remove(target_abs)
        return f"已刪除：{os.path.basename(target_abs)}"

    if not target_abs.startswith(conv_abs + os.sep):
        return "存取拒絕：只能刪除自己的對話資料夾或記憶目錄中的檔案。"
    if not os.path.exists(target_abs):
        return f"不存在：{os.path.basename(target_abs)}"
    parent = os.path.dirname(target_abs)
    if os.path.realpath(parent) == conv_abs:
        if os.path.isdir(target_abs):
            return f"存取拒絕：不能刪除第一層目錄 {os.path.basename(target_abs)}/。"
    if os.path.isdir(target_abs):
        shutil.rmtree(target_abs)
        return f"已刪除資料夾：{os.path.basename(target_abs)}/"
    os.remove(target_abs)
    return f"已刪除：{os.path.basename(target_abs)}"
