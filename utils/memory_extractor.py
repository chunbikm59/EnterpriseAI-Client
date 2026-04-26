"""背景記憶萃取 Agent 模組（層 3）。

每回合 LLM 最終回應結束後 fire-and-forget 呼叫 extract_memories_background()。
若主 LLM 本回合已寫入記憶（互斥），則跳過。
節流：每 TURNS_BETWEEN_EXTRACTIONS 個回合才真正執行一次。
游標：只分析自上次萃取以來的新訊息。

設計要點：
- 真正 fork 主對話：傳入完整 message_history（含 system message）+ 完整 tools，
  與主對話 token 序列前綴完全相同，最大化 KV cache 命中率。
- 預掃描記憶目錄並注入 manifest，省去 agent 的 list_files turn
- 萃取 user message 包含完整記憶類型定義、examples、不應保存清單、保存流程
- 游標以訊息數量 index 實作

工具限制（事後攔截）：
- prompt 中已指明只能使用 write_file / read_file / list_files / delete_file
- 若 LLM 回傳非 ALLOWED_TOOLS 的 tool_call，在執行前攔截並回傳錯誤訊息
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from utils.llm_client import get_llm_client, get_model_setting
from utils.buildin_tool_runner import call_buildin_tool
from utils.memory_manager import list_memory_files, WHAT_NOT_TO_SAVE_SECTION

logger = logging.getLogger(__name__)

# 最多工具迴圈次數
MAX_TURNS = 5

# 節流：每幾個回合才執行一次萃取（預設 1，每回合都執行）
TURNS_BETWEEN_EXTRACTIONS = 1
# 允許萃取 Agent 使用的工具
ALLOWED_TOOLS = {"write_file", "read_file", "list_files", "delete_file"}


def _format_memory_manifest(memory_files: list[dict]) -> str:
    """將 list_memory_files() 結果格式化為 manifest 字串。

    輸出注入到萃取任務 user message，省去 agent 自行呼叫 list_files 的 turn。
    """
    lines = []
    for m in memory_files:
        tag = f"[{m['type']}] " if m.get("type") else ""
        ts = datetime.fromtimestamp(m["mtime"], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        desc = m.get("description", "").strip()
        if desc:
            lines.append(f"- {tag}{m['filename']} ({ts}): {desc}")
        else:
            lines.append(f"- {tag}{m['filename']} ({ts})")
    return "\n".join(lines)


def _build_extract_user_message(new_message_count: int, existing_memories: str) -> str:
    """建立萃取任務 user message。

    設計要點：
    - opener 精簡，效率指引直接
    - <description> 做主要過濾，<when_to_save> 保持簡單
    - 不應保存清單精準且短，最後一句是關鍵守門句
    - 不用複雜規則測試，靠清晰邊界定義來過濾
    """
    manifest_section = ""
    if existing_memories:
        manifest_section = (
            "\n\n## 現有記憶檔案\n\n"
            + existing_memories
            + "\n\n寫入前先檢查此清單 — 優先更新現有檔案，不要新建重複記憶。"
        )

    return f"""\
[以下是系統注入任務，非出自使用者]
你現在作為記憶萃取子代理。分析以上最近 {new_message_count} 條新訊息，判斷如有維護現有記憶的必要才使用工具更新記憶檔案。若判斷無須新增或更新現有記憶檔案則不做任何事情。

可用工具：write_file、read_file、list_files、delete_file（僅限記憶目錄）

你有有限的 turn 預算。高效策略：turn 1 — 並行發出所有 read_file 呼叫（一次讀取你確定要更新的所有檔案）；turn 2 — 並行發出所有 write_file 呼叫。不要跨多個回合交錯讀寫。Manifest 已注入，不需要呼叫 list_files。

你只能使用以上訊息中的內容更新記憶。不要試圖查驗或研究對話以外的資訊。{manifest_section}

## 記憶類型

<types>
<type>
    <name>user</name>
    <description>關於使用者的角色、目標、責任與知識。良好的 user 記憶讓你能根據使用者的背景量身調整回應方式。目標是了解使用者是誰，以便提供最有價值的協助。避免寫下對使用者帶有負面判斷意味的記憶，或與協助使用者完成工作無關的個人資訊。</description>
    <when_to_save>當你了解到使用者的角色、偏好、責任或知識的具體細節時</when_to_save>
    <how_to_use>當你的回應應考慮使用者的背景時。例如向專業人士解釋概念的深度與方式，應與向初學者解釋不同。</how_to_use>
    <examples>
    user: 我是一個行銷主管，正在研究如何用 AI 分析客戶回饋
    assistant: [saves user memory: 使用者是行銷主管，目前關注以 AI 分析客戶回饋的應用]

    user: 我有十年的財務工作經驗，但這是我第一次用 AI 工具做報表
    assistant: [saves user memory: 財務領域深厚背景，AI 工具新手 — 解釋時連結熟悉的財務概念]
    </examples>
</type>
<type>
    <name>feedback</name>
    <description>使用者給你的工作指引 — 包括要避免的和要保持的。這是最重要的記憶類型之一，讓你在未來的對話中保持一致。成功和失敗都要記：只記錯誤會讓你過度謹慎，也會忘記哪些做法已獲認可。</description>
    <when_to_save>任何時候使用者糾正你的做法（「不要這樣」、「不對」、「停止 X」），或確認某個非顯而易見的做法奏效（「對，就是這樣」、「完美，繼續這樣做」，或接受不尋常的選擇而未反對）。糾正容易注意到；確認比較安靜 — 要留意。加入 *why* 以便日後判斷邊界案例。</when_to_save>
    <how_to_use>讓這些記憶引導你的行為，使用者不需要給相同的指引兩次。</how_to_use>
    <body_structure>以規則本身開頭，再加 **Why:** 行（使用者給的理由）和 **How to apply:** 行（此指引適用的時機/場合）。</body_structure>
    <examples>
    user: 回答不要太長，我只需要重點，不要廢話
    assistant: [saves feedback memory: 使用者偏好簡短直接的回應，省略鋪陳和總結。Why: 使用者明確表示不需要冗長說明。How to apply: 每次回應都保持精簡，直接給結論]

    user: 對，用條列式整理就對了，比段落文字清楚多了
    assistant: [saves feedback memory: 使用者偏好條列式格式，勝過段落文字。Why: 使用者確認這個非顯而易見的格式選擇有效。How to apply: 有多個項目時優先用條列式]
    </examples>
</type>
<type>
    <name>project</name>
    <description>關於正在進行的工作、目標、計畫、問題的資訊，這些資訊無法從公開或一般背景推導出來。Project 記憶幫助你理解使用者請求背後更廣泛的脈絡與動機。</description>
    <when_to_save>當你了解到誰在做什麼、為什麼、截止日期時。這些狀態變化較快，盡量保持更新。相對日期轉為絕對日期（例如「下週五」→「2026-04-17」）。</when_to_save>
    <how_to_use>用這些記憶更全面理解使用者請求的細節與脈絡，提出更合適的建議。</how_to_use>
    <body_structure>以事實或決策開頭，再加 **Why:** 行（動機，通常是限制、截止日期或利害關係人的要求）和 **How to apply:** 行（這應如何影響你的建議）。</body_structure>
    <examples>
    user: 我們下週要對客戶做簡報，現在在趕這份提案
    assistant: [saves project memory: 使用者正在準備客戶提案，截止日期 2026-04-17。Why: 有時間壓力的交付任務。How to apply: 優先考慮效率，建議以最快能完成的方式處理]

    user: 這個活動要辦給長輩參加，所以操作要很簡單
    assistant: [saves project memory: 活動目標對象為長輩，操作簡單是核心需求。Why: 目標受眾限制。How to apply: 所有建議都以最低技術門檻為優先]
    </examples>
</type>
<type>
    <name>reference</name>
    <description>儲存可在外部系統或資源中找到資訊的指標。這些記憶讓你記住去哪裡查找最新資訊。</description>
    <when_to_save>當你了解到外部資源及其用途時。例如特定的文件連結、常用的參考資料、固定查詢的管道。</when_to_save>
    <how_to_use>當使用者提到某個外部系統或需要查找特定資源時。</how_to_use>
    <examples>
    user: 我們公司的請假規定都在內部 Wiki 的 HR 頁面，你以後可以叫我去那裡查
    assistant: [saves reference memory: 請假規定位於公司內部 Wiki 的 HR 頁面]

    user: 這個產品的規格文件在 Google Drive 的「2026 產品規劃」資料夾
    assistant: [saves reference memory: 產品規格文件位於 Google Drive「2026 產品規劃」資料夾]
    </examples>
</type>
</types>

{WHAT_NOT_TO_SAVE_SECTION}

## 如何更新記憶（兩步驟）

**步驟 1** — 用 write_file 將記憶寫入獨立檔案（例如 `user_profiles/{{user_id}}/memory/user_role.md`），格式如下：

```
---
name: 記憶名稱
description: 一行具體描述（用於未來判斷相關性，請具體）
type: user|feedback|project|reference
---

記憶內容（feedback/project 類型請包含 **Why:** 和 **How to apply:** 行）
```

**步驟 2(如有必要才做)** — 用 write_file 更新 `user_profiles/{{user_id}}/memory/MEMORY.md` 索引，新增一行：
`- [名稱](file.md) — 一行鉤子（約 150 字元）`
MEMORY.md 不含 frontmatter，不直接寫記憶內容。只在 description 真正改變時才更新索引。

- 如有需要，更新或刪除已過時的記憶
- 優先更新現有檔案，不要新建重複記憶
- 更新現有檔案時，只追加與該檔案主題直接相關的內容；若屬於不同主題，建立新檔案
- 避免做出冗餘操作"""


async def extract_memories_background(
    user_id: str,
    recent_messages: list[dict],
    main_wrote_memory: bool,
    session_id: str,
    conversation_folder: str,
    cursor: int,
    turns_since_extraction: int,
    all_tools: list | None = None,
) -> tuple[int, int]:
    """背景記憶萃取 — fire-and-forget，回傳更新後的 (cursor, turns_since_extraction)。

    Args:
        user_id: 使用者 ID
        recent_messages: 完整 message_history（含 system message）
        main_wrote_memory: 主 LLM 本回合是否已呼叫 write_file 寫記憶（互斥用）
        session_id: 當前 session ID
        conversation_folder: 當前 session 的檔案資料夾
        cursor: 上次萃取時的訊息數量 index
        turns_since_extraction: 自上次萃取以來的回合數（節流用）
        all_tools: 主對話完整 tools 清單（OpenAI 格式），用於保持 KV cache 前綴一致

    Returns:
        (new_cursor, new_turns_since_extraction)
    """
    total_messages = len(recent_messages)

    # 互斥：主 LLM 本回合已寫入記憶，跳過但推進游標
    if main_wrote_memory:
        logger.debug(
            "[memory_extractor] 主 LLM 本回合已寫記憶，跳過背景萃取，推進游標 %d→%d | user=%s",
            cursor, total_messages, user_id,
        )
        return total_messages, 0

    # 節流：未達回合門檻，遞增計數後跳過
    new_turns = turns_since_extraction + 1
    if new_turns < TURNS_BETWEEN_EXTRACTIONS:
        logger.debug(
            "[memory_extractor] 節流跳過（%d/%d 回合）| user=%s",
            new_turns, TURNS_BETWEEN_EXTRACTIONS, user_id,
        )
        return cursor, new_turns

    # 游標：確認游標後有新的 user/assistant 訊息才啟動
    new_visible = [
        m for m in recent_messages[cursor:]
        if m.get("role") in ("user", "assistant")
    ]
    if not new_visible:
        logger.debug("[memory_extractor] 游標後無新訊息，跳過 | user=%s", user_id)
        return total_messages, 0

    logger.debug(
        "[memory_extractor] 背景萃取啟動 | user=%s session=%s 新訊息數=%d（游標 %d→%d）",
        user_id, session_id, len(new_visible), cursor, total_messages,
    )
    try:
        # 傳入完整 message_history（含 system message）作為 fork 前綴
        # new_message_count 只計游標後的新訊息數，讓 agent 知道要分析的範圍
        await _run_extractor(
            user_id, recent_messages, session_id, conversation_folder,
            new_message_count=len(new_visible),
            all_tools=all_tools or [],
        )
    except Exception:
        logger.debug("[memory_extractor] 萃取發生例外，靜默處理", exc_info=True)

    return total_messages, 0


async def _run_extractor(
    user_id: str,
    recent_messages: list[dict],
    session_id: str,
    conversation_folder: str,
    new_message_count: int,
    all_tools: list,
) -> None:
    """執行記憶萃取。

    以完整 message_history + 完整 tools 作為 fork 前綴，與主對話 token 序列相同，
    最大化 KV cache 命中率。工具限制改為事後攔截：ALLOWED_TOOLS 以外的 tool_call
    在執行前被攔截並回傳錯誤，不實際執行。
    """
    # 預掃描記憶目錄，注入到萃取 user message，省去 agent 自行呼叫 list_files 的 turn
    try:
        memory_files = await asyncio.to_thread(list_memory_files, user_id)
        existing_memories = _format_memory_manifest(memory_files)
        logger.debug("[memory_extractor] 預掃描 %d 個記憶檔案 | user=%s", len(memory_files), user_id)
    except Exception:
        logger.debug("[memory_extractor] 預掃描失敗，降級為無 manifest", exc_info=True)
        existing_memories = ""

    # Fork 主對話：完整 message_history 作為前綴，append 萃取任務 user message
    # System prompt 繼承自 recent_messages[0]（主對話 system message），不另傳
    fork_messages = [
        *recent_messages,
        {
            "role": "user",
            "content": _build_extract_user_message(new_message_count, existing_memories),
        },
    ]

    llm = get_llm_client(mode="async")
    model_setting = get_model_setting()

    logger.debug(
        "[memory_extractor] 開始工具迴圈 fork_messages=%d new_message_count=%d | user=%s",
        len(fork_messages), new_message_count, user_id,
    )

    # 執行工具迴圈（最多 MAX_TURNS 次）
    for _turn in range(MAX_TURNS):
        logger.debug("[memory_extractor] 第 %d 輪 LLM 呼叫", _turn + 1)
        response = await llm.chat.completions.create(
            model=model_setting["model"],
            messages=fork_messages,    # 整包傳入，含主對話 system message
            tools=all_tools,           # 與主對話相同的完整工具清單，保持 KV cache 前綴一致
            tool_choice="auto",
            max_tokens=1024,
            temperature=0,
        )

        choice = response.choices[0]
        assistant_msg = choice.message

        fork_messages.append({
            "role": "assistant",
            "content": assistant_msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in (assistant_msg.tool_calls or [])
            ] or None,
        })

        # 無工具呼叫 → 萃取完成
        if not assistant_msg.tool_calls:
            logger.debug("[memory_extractor] 第 %d 輪無工具呼叫，萃取完成", _turn + 1)
            break

        # 執行工具呼叫（只允許記憶工具）
        tool_results = []
        for tc in assistant_msg.tool_calls:
            tool_name = tc.function.name
            if tool_name not in ALLOWED_TOOLS:
                logger.debug("[memory_extractor] 拒絕不允許的工具：%s", tool_name)
                result_content = f"錯誤：工具 {tool_name} 不被允許在記憶萃取中使用"
            else:
                try:
                    tool_args = json.loads(tc.function.arguments or "{}")
                    logger.debug("[memory_extractor] 呼叫工具 %s args=%s", tool_name, tool_args)
                    result_content = await call_buildin_tool(
                        tool_name, tool_args, session_id, user_id, conversation_folder
                    )
                    logger.debug("[memory_extractor] 工具 %s 結果：%s", tool_name, result_content)
                except Exception as e:
                    logger.debug("[memory_extractor] 工具 %s 執行例外：%s", tool_name, e, exc_info=True)
                    result_content = f"工具執行錯誤：{e}"

            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_content,
            })

        fork_messages.extend(tool_results)
