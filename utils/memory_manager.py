"""使用者記憶管理模組。

負責每位使用者的長期記憶檔案讀寫，路徑安全驗證與大小限制。

目錄結構：
    user_profiles/{user_id}/memory/
        ├── MEMORY.md           ← 索引（200行/25KB，無 frontmatter）
        ├── user_role.md        ← type: user
        ├── feedback_style.md   ← type: feedback
        └── project_notes.md   ← type: project

記憶檔格式（YAML frontmatter）：
    ---
    name: 名稱
    description: 一行描述（供相關性選擇器使用）
    type: user|feedback|project|reference
    ---
    記憶內容...
"""
import os
import re

# 專案根目錄
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USER_PROFILES_ROOT = os.path.join(_PROJECT_ROOT, "user_profiles")

# 大小限制
MEMORY_INDEX_MAX_LINES = 200
MEMORY_INDEX_MAX_BYTES = 25 * 1024   # 25KB
MEMORY_FILE_MAX_BYTES  = 4 * 1024    # 4KB


# ─────────────────────────────────────────────
# 記憶系統：共用排除規則 & 主 LLM 指示
# ─────────────────────────────────────────────

# 共用排除規則（主 system prompt 和萃取 prompt 都引用同一份，確保 fork 後規則一致）
WHAT_NOT_TO_SAVE_SECTION = """\
## 不應保存到記憶

- 一般知識或事實 — 這些隨時可重新查詢
- 一次性的任務細節、暫時狀態或當前對話的臨時上下文
- 敏感個資（密碼、憑證、身分證號等）
- 任何對使用者帶有負面判斷意味的資訊
- 與協助使用者完成工作無關的個人資訊

這些排除規則即使在使用者明確要求保存時也適用。如果使用者要求保存活動摘要或清單，請詢問其中哪部分是令人意外或非顯而易見的 — 那才是值得長期保留的部分。"""


def build_memory_management_instructions() -> str:
    """建立主 LLM 的記憶管理指示。

    排除規則從 WHAT_NOT_TO_SAVE_SECTION 引用，
    確保與萃取 agent fork 進來的規則完全一致，避免兩套指示衝突。
    """
    return f"""
## auto memory

你擁有一個持久化的檔案式記憶系統，位於使用者的 memory 目錄中。隨著時間累積，你應建立並維護這套記憶系統，讓未來的對話能了解使用者是誰、他們希望如何與你合作、哪些行為要避免或重複，以及工作背景。

如果使用者明確要求記住某事，立刻保存為最合適的類型。如果要忘記某事，找到並移除相關記憶。

## 記憶類型

**user**：使用者角色、目標、責任與知識。目標：了解使用者是誰，量身打造未來回答。
- 何時保存：學到使用者角色、偏好、責任、專業知識的具體細節，且這些資訊有助於未來提供更好的協助。

**feedback**：工作指引（成功和失敗都記）。格式：規則本身 + **Why:** + **How to apply:**
- 何時保存：使用者糾正做法（「不要這樣」）**或**確認某非顯而易見的做法奏效（「對，就是這樣」，或接受不尋常選擇而未反對）。

**project**：無法從 code/git 推導的進行中工作、目標、決策。格式：事實/決策 + **Why:** + **How to apply:**
- 何時保存：學到誰在做什麼、為什麼、截止日期時。相對日期轉絕對日期。

**reference**：外部系統指標（Jira、Slack、監控看板等）。
- 何時保存：學到外部系統資源及其用途時。

{WHAT_NOT_TO_SAVE_SECTION}

## 如何保存記憶（兩步驟）

記憶目錄路徑：`user_profiles/{{user_id}}/memory/`（`{{user_id}}` 替換為使用者的實際 ID）

**Step 1** — 呼叫 `write_file(path, content)` 寫記憶檔（例如路徑 `user_profiles/{{user_id}}/memory/user_role.md`）。
格式（YAML frontmatter）：
```
---
name: 記憶名稱
description: 一行具體描述（用於未來判斷相關性）
type: user|feedback|project|reference
---
記憶內容...
```

**Step 2** — 呼叫 `write_file("user_profiles/{{user_id}}/memory/MEMORY.md", ...)` 在索引中新增指標。
每行格式：`- [標題](file.md) — 一行鉤子`（約 150 字元）。不在 MEMORY.md 中寫記憶內容。

MEMORY.md 索引已注入 system prompt，可直接參考，無需呼叫 list_files。
更新現有檔時，只在 description 真的變了才需要同步更新 MEMORY.md。
更新現有檔時，只追加與該檔案主題直接相關的內容；若屬於不同主題，建立新檔案。
刪除記憶時呼叫 `delete_file(path)` 並同步更新 MEMORY.md。

## 存取記憶的時機

- 記憶看起來相關，或使用者提到先前對話的工作時
- 使用者明確要求查看、回憶、記住某事時
- 即將根據記憶中的聲明回答前，先驗證記憶是否仍然正確

## 記憶的時效性

記憶是當時觀察的快照，可能已過期。若對話資訊與記憶衝突，信任現在觀察到的，並更新或移除過期記憶，而非根據舊記憶行動。"""


MEMORY_MANAGEMENT_INSTRUCTIONS = build_memory_management_instructions()


# ─────────────────────────────────────────────
# 路徑輔助
# ─────────────────────────────────────────────

def _safe_user_id(user_id: str) -> str:
    """將 user_id 中的特殊字元替換為底線，確保路徑安全（與 user_profile.py 邏輯一致）。"""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)


def get_user_memory_dir(user_id: str) -> str:
    """取得指定使用者的 memory 資料夾路徑。"""
    return os.path.join(_USER_PROFILES_ROOT, _safe_user_id(user_id), "memory")


def get_memory_index_path(user_id: str) -> str:
    """取得 MEMORY.md 的完整路徑。"""
    return os.path.join(get_user_memory_dir(user_id), "MEMORY.md")


def validate_memory_path(user_id: str, filename: str) -> tuple[str, str | None]:
    """驗證記憶檔案路徑安全性。

    Returns:
        (abs_path, error_message)。error_message 為 None 代表合法路徑。
    """
    if not filename.endswith(".md"):
        return "", "只允許 .md 格式的記憶檔案"
    if os.sep in filename or "/" in filename or "\\" in filename:
        return "", "檔案名稱不能包含路徑分隔符"
    memory_dir = get_user_memory_dir(user_id)
    abs_path = os.path.realpath(os.path.join(memory_dir, filename))
    real_memory_dir = os.path.realpath(memory_dir)
    if not (abs_path.startswith(real_memory_dir + os.sep) or abs_path == real_memory_dir):
        return "", "存取拒絕：路徑越界"
    return abs_path, None


# ─────────────────────────────────────────────
# 讀取
# ─────────────────────────────────────────────

def load_memory_index(user_id: str) -> str:
    """讀取 MEMORY.md 索引，套用截斷限制。

    Returns:
        索引內容字串；若檔案不存在回傳 ""。
    """
    index_path = get_memory_index_path(user_id)
    if not os.path.exists(index_path):
        return ""
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return ""

    if not raw.strip():
        return ""

    was_truncated = False

    # 先按位元組截斷（UTF-8 邊界）
    encoded = raw.encode("utf-8")
    if len(encoded) > MEMORY_INDEX_MAX_BYTES:
        truncated_bytes = encoded[:MEMORY_INDEX_MAX_BYTES]
        # 找最後一個完整 UTF-8 字元邊界
        raw = truncated_bytes.decode("utf-8", errors="ignore")
        # 在最後換行符截斷，避免切斷行中間
        last_nl = raw.rfind("\n")
        if last_nl > 0:
            raw = raw[:last_nl]
        was_truncated = True

    # 再按行數截斷
    lines = raw.splitlines()
    if len(lines) > MEMORY_INDEX_MAX_LINES:
        lines = lines[:MEMORY_INDEX_MAX_LINES]
        was_truncated = True

    result = "\n".join(lines)
    if was_truncated:
        result += (
            f"\n\n> WARNING: MEMORY.md 已截斷（上限 {MEMORY_INDEX_MAX_LINES} 行 / "
            f"{MEMORY_INDEX_MAX_BYTES // 1024}KB）。請清理舊記憶以保持索引精簡。"
        )
    return result


def load_memory_file(user_id: str, filename: str) -> str | None:
    """讀取指定記憶檔案（上限 4KB）。

    Returns:
        檔案內容；若不存在或路徑不合法回傳 None。
    """
    abs_path, error = validate_memory_path(user_id, filename)
    if error:
        return None
    if not os.path.exists(abs_path):
        return None
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read(MEMORY_FILE_MAX_BYTES * 2)  # 多讀一點再截斷
    except OSError:
        return None

    # 按位元組截斷
    encoded = content.encode("utf-8")
    if len(encoded) > MEMORY_FILE_MAX_BYTES:
        truncated = encoded[:MEMORY_FILE_MAX_BYTES].decode("utf-8", errors="ignore")
        last_nl = truncated.rfind("\n")
        content = truncated[:last_nl] if last_nl > 0 else truncated
        content += "\n\n（內容已截斷，超過 4KB 上限）"
    return content


def list_memory_files(user_id: str) -> list[dict]:
    """列出所有記憶檔案（排除 MEMORY.md），含 frontmatter 摘要。

    Returns:
        list of {filename, name, description, type, size_bytes, mtime}
        按 mtime 降序排列（最新優先）。
    """
    memory_dir = get_user_memory_dir(user_id)
    if not os.path.isdir(memory_dir):
        return []

    results = []
    try:
        entries = list(os.scandir(memory_dir))
    except OSError:
        return []

    for entry in entries:
        if not entry.name.endswith(".md"):
            continue
        if entry.name == "MEMORY.md":
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue

        fm = _parse_frontmatter(entry.path)
        results.append({
            "filename": entry.name,
            "name": fm.get("name", entry.name),
            "description": fm.get("description", ""),
            "type": fm.get("type", ""),
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
        })

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def _parse_frontmatter(filepath: str) -> dict:
    """從記憶檔案讀取 YAML frontmatter（只讀前 1KB 以提高效率）。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            head = f.read(1024)
    except OSError:
        return {}

    if not head.startswith("---"):
        return {}

    # 找到結尾的 ---
    end = head.find("\n---", 3)
    if end == -1:
        return {}

    fm_text = head[3:end].strip()
    result = {}
    for line in fm_text.splitlines():
        m = re.match(r"^(\w+)\s*:\s*(.+)$", line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


# ─────────────────────────────────────────────
# 寫入
# ─────────────────────────────────────────────

def write_memory_file(user_id: str, filename: str, content: str) -> str:
    """寫入記憶內容檔（非 MEMORY.md）。

    Returns:
        操作結果訊息。
    """
    if filename == "MEMORY.md":
        return "請使用 write_memory_index() 寫入 MEMORY.md"

    abs_path, error = validate_memory_path(user_id, filename)
    if error:
        return f"錯誤：{error}"

    # 大小檢查
    encoded = content.encode("utf-8")
    if len(encoded) > MEMORY_FILE_MAX_BYTES:
        return (
            f"錯誤：內容超過 {MEMORY_FILE_MAX_BYTES // 1024}KB 上限"
            f"（目前 {len(encoded)} bytes）。請縮短內容後重試。"
        )

    # 確保目錄存在
    memory_dir = get_user_memory_dir(user_id)
    os.makedirs(memory_dir, exist_ok=True)

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return f"錯誤：寫入失敗 — {e}"

    return f"已儲存記憶檔案：{filename}"


def write_memory_index(user_id: str, content: str) -> str:
    """寫入 MEMORY.md 索引。

    Returns:
        操作結果訊息。
    """
    # 大小檢查
    lines = content.splitlines()
    if len(lines) > MEMORY_INDEX_MAX_LINES:
        return (
            f"錯誤：索引超過 {MEMORY_INDEX_MAX_LINES} 行上限"
            f"（目前 {len(lines)} 行）。請先清理舊記憶條目。"
        )
    encoded = content.encode("utf-8")
    if len(encoded) > MEMORY_INDEX_MAX_BYTES:
        return (
            f"錯誤：索引超過 {MEMORY_INDEX_MAX_BYTES // 1024}KB 上限"
            f"（目前 {len(encoded)} bytes）。請先清理舊記憶條目。"
        )

    memory_dir = get_user_memory_dir(user_id)
    os.makedirs(memory_dir, exist_ok=True)
    index_path = get_memory_index_path(user_id)

    try:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return f"錯誤：寫入 MEMORY.md 失敗 — {e}"

    return "已更新 MEMORY.md 記憶索引"
