"""動態相關記憶預取模組（層 2）。

在 agent 開始時啟動非同步任務，用小模型從記憶檔的
description frontmatter 中選出最相關的最多 5 個，在工具執行後
注入 message_history。

預算：
- 每個記憶檔最大 4KB（由 memory_manager 保證）
- 每回合注入合計最大 20KB
- 整個 session 注入合計最大 60KB
"""
import json
import asyncio
import logging
from utils.memory_manager import list_memory_files, load_memory_file
from utils.llm_client import get_llm_client, get_model_setting

logger = logging.getLogger(__name__)

SELECT_MEMORIES_SYSTEM_PROMPT = (
    "你是記憶選擇器。根據使用者的查詢，從記憶檔清單中選出最相關的最多 5 個。\n\n"
    "回傳 JSON：{\"selected_memories\": [\"file1.md\", \"file2.md\"]}\n\n"
    "規則：\n"
    "- 只選「明確有用」的記憶，若不確定則不選，寧缺勿濫\n"
    "- 若無相關記憶，回傳空陣列\n"
    "- 若清單中有最近正在使用的工具的參考文件，不選（除非含 gotcha/已知問題）"
)

# 每回合注入上限
MAX_TURN_BYTES = 20 * 1024   # 20KB
MAX_SESSION_BYTES = 60 * 1024  # 60KB


async def prefetch_relevant_memories(
    user_id: str,
    user_message: str,
    already_surfaced: set | None = None,
) -> list[dict]:
    """非同步選出最相關記憶並讀取完整內容。

    Args:
        user_id: 使用者 ID
        user_message: 使用者訊息純文字（供選擇器判斷相關性）
        already_surfaced: 本 session 已注入過的 filename set（避免重複）

    Returns:
        list of {"filename": str, "content": str}，合計最大 20KB。
        若無相關記憶或發生錯誤，回傳 []。
    """
    if already_surfaced is None:
        already_surfaced = set()

    # 取得所有記憶檔的 description（已讀 frontmatter）
    all_files = list_memory_files(user_id)
    # 過濾已注入過的
    candidates = [f for f in all_files if f["filename"] not in already_surfaced]
    logger.debug(
        "[memory_prefetch] 開始預取 | user=%s 記憶檔總數=%d 候選數=%d query=%.80r",
        user_id, len(all_files), len(candidates), user_message,
    )
    if not candidates:
        logger.debug("[memory_prefetch] 無候選記憶，跳過")
        return []

    # 組 manifest 字串：每行 「filename: description」
    manifest_lines = [
        f"- {f['filename']}: {f['description'] or '（無描述）'}"
        for f in candidates
    ]
    manifest = "\n".join(manifest_lines)

    # 用小模型選擇相關記憶
    selected_filenames = await _select_relevant_memories(user_message, manifest, candidates)
    logger.debug("[memory_prefetch] LLM 選出記憶檔：%s", selected_filenames)
    if not selected_filenames:
        logger.debug("[memory_prefetch] 無相關記憶，不注入")
        return []

    # 讀取選出記憶的完整內容，累計不超過 20KB
    result = []
    total_bytes = 0
    for filename in selected_filenames[:5]:
        content = load_memory_file(user_id, filename)
        if not content:
            logger.debug("[memory_prefetch] 讀取記憶檔失敗或空白：%s", filename)
            continue
        b = len(content.encode("utf-8"))
        if total_bytes + b > MAX_TURN_BYTES:
            logger.debug("[memory_prefetch] 累計超過 20KB 上限，停止讀取（已載入 %d bytes）", total_bytes)
            break
        result.append({"filename": filename, "content": content})
        total_bytes += b

    logger.debug("[memory_prefetch] 注入 %d 個記憶檔，共 %d bytes", len(result), total_bytes)
    return result


async def _select_relevant_memories(
    query: str,
    manifest: str,
    candidates: list[dict],
) -> list[str]:
    """呼叫 LLM 從 manifest 中選出相關記憶的 filename 清單。"""
    valid_filenames = {f["filename"] for f in candidates}

    try:
        llm = get_llm_client(mode="async")
        model_setting = get_model_setting()

        response = await llm.chat.completions.create(
            model=model_setting["model"],
            messages=[
                {"role": "system", "content": SELECT_MEMORIES_SYSTEM_PROMPT},
                {"role": "user", "content": f"Query: {query}\n\nAvailable memories:\n{manifest}"},
            ],
            max_tokens=256,
            temperature=0,
            response_format={"type": "json_object"},
        )

        text = response.choices[0].message.content or ""
        parsed = json.loads(text)
        selected = parsed.get("selected_memories", [])
        # 過濾非法 filename
        return [f for f in selected if isinstance(f, str) and f in valid_filenames]

    except Exception:
        logger.debug("[memory_prefetch] _select_relevant_memories 失敗，靜默降級", exc_info=True)
        return []


def format_memories_for_injection(relevant_memories: list[dict]) -> str:
    """將選出的記憶格式化為注入 message_history 的字串。"""
    if not relevant_memories:
        return ""
    parts = [
        f"<memory file='{m['filename']}'>\n{m['content']}\n</memory>"
        for m in relevant_memories
    ]
    body = "\n\n".join(parts)
    return f"<system-reminder>\n以下為與本次查詢相關的記憶：\n\n{body}\n</system-reminder>"
