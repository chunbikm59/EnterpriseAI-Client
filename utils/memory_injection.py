"""記憶預取消費與注入邏輯。"""

import asyncio
import logging
from typing import Optional

from utils.memory_prefetch import format_memories_for_injection

logger = logging.getLogger(__name__)


async def consume_memory_prefetch(
    memory_prefetch_task: Optional[asyncio.Future],
    memory_injected_this_turn: bool,
    memory_surfaced_paths: set,
    message_history: list,
) -> tuple[bool, set, list]:
    """消費記憶預取結果，若尚未注入且預取已完成，則注入相關記憶。

    Args:
        memory_prefetch_task: 預取任務（asyncio.Future），None 表示未啟動
        memory_injected_this_turn: 本回合是否已注入過記憶
        memory_surfaced_paths: 已曾出現過的記憶檔案路徑集合
        message_history: 當前對話歷史（會在原地 append）

    Returns:
        (injected, updated_surfaced_paths, message_history)
        - injected: 是否在本次呼叫中完成注入
        - updated_surfaced_paths: 更新後的已出現路徑集合
        - message_history: 可能已 append 記憶注入訊息的對話歷史
    """
    if (
        memory_injected_this_turn
        or memory_prefetch_task is None
        or not memory_prefetch_task.done()
    ):
        return memory_injected_this_turn, memory_surfaced_paths, message_history

    try:
        relevant_memories = memory_prefetch_task.result()
        if relevant_memories:
            injection = format_memories_for_injection(relevant_memories)
            message_history.append({"role": "user", "content": injection})
            memory_injected_this_turn = True
            for m in relevant_memories:
                memory_surfaced_paths.add(m["filename"])
            logger.debug(
                "[memory_prefetch] 注入 %d 個相關記憶：%s\n%s",
                len(relevant_memories),
                [m["filename"] for m in relevant_memories],
                injection,
            )
        else:
            logger.debug("[memory_prefetch] 預取完成，無相關記憶需注入")
    except Exception:
        logger.debug("[memory_prefetch] 預取結果讀取失敗，靜默降級", exc_info=True)

    return memory_injected_this_turn, memory_surfaced_paths, message_history
