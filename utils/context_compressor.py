"""自動上下文壓縮：偵測 token 剩餘空間不足時，Fork 對話生成摘要並重建歷史。"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# 剩餘空間低於此值時觸發壓縮（代表 LLM 輸出所需的最小緩衝，與模型無關）
COMPRESS_REMAINING_TOKENS = int(os.getenv("COMPRESS_REMAINING_TOKENS", "20000"))
# 模型上下文窗口大小（切換模型時只需改此值）
CONTEXT_WINDOW_SIZE = int(os.getenv("CONTEXT_WINDOW_SIZE", "128000"))
# 壓縮後保留對話輪數的最大上限（防止極端情況保留過多）
COMPRESS_KEEP_RECENT = int(os.getenv("COMPRESS_KEEP_RECENT", "10"))

# ack message "好的，我已載入對話摘要，繼續我們的工作。" 的估算 token 數
_ACK_TOKENS = 30


def should_compress(prompt_tokens: int) -> bool:
    remaining = CONTEXT_WINDOW_SIZE - prompt_tokens
    return remaining < COMPRESS_REMAINING_TOKENS


def _estimate_system_tokens(system_msg: dict | None) -> int:
    """粗估 system message 的 token 數（唯一需要估算的訊息）。"""
    if not system_msg:
        return 0
    content = system_msg.get("content") or ""
    return max(50, len(content) // 3)


def _select_recent_by_checkpoints(
    body: list,
    token_checkpoints: list,
    budget: int,
    usage_prompt_tokens: int = 0,
) -> tuple[list, int, int]:
    """
    以對話輪為單位，從最新輪往前貪婪選入，直到累計 token 超出 budget 為止。

    token_checkpoints: [{"msg_len": int, "tokens": int}, ...]
        - msg_len: 該輪結束時 message_history 的長度（含 system）
        - tokens:  該輪結束時的累計 prompt_tokens（API 精確值）
    usage_prompt_tokens: 觸發壓縮時的完整 prompt token 數，
        用於計算「尾端」（最後一個 checkpoint 之後的未記錄訊息）的真實 token 成本。

    回傳 (recent_messages, kept_turns_count, accumulated_tokens)
    """
    # 尾端：body 中在最後一個 checkpoint 之後的訊息（當前未記錄的輪）
    # 這些訊息之前沒有被計入 budget，需要先預扣其成本
    if token_checkpoints and usage_prompt_tokens:
        tail_start_in_body = min(token_checkpoints[-1]["msg_len"] - 1, len(body))
        tail_tokens = max(0, usage_prompt_tokens - token_checkpoints[-1]["tokens"])
    elif usage_prompt_tokens:
        # 沒有 checkpoint：整個 body 就是當前未記錄的輪
        tail_start_in_body = 0
        tail_tokens = usage_prompt_tokens
    else:
        tail_start_in_body = 0
        tail_tokens = 0

    # 尾端本身就超出 budget：無法保留任何訊息
    if tail_tokens > budget:
        logger.info(
            "[compressor] 當前輪 token 成本（%d）超出 budget（%d），不保留任何訊息",
            tail_tokens, budget,
        )
        return [], 0, 0

    if not token_checkpoints:
        keep = min(COMPRESS_KEEP_RECENT, len(body))
        return (body[-keep:] if keep > 0 else []), 0, tail_tokens

    # 先預扣尾端成本，再用剩餘 budget 貪婪選取前面的 checkpoint 輪
    accumulated = tail_tokens
    kept_start_body_idx = tail_start_in_body  # 最少保留：尾端
    kept_turns = 0

    for i in range(len(token_checkpoints) - 1, -1, -1):
        cp = token_checkpoints[i]
        # i == 0 時前一個 token 基線設為 0（略微高估第一輪成本，屬於保守估算）
        prev_tokens = token_checkpoints[i - 1]["tokens"] if i > 0 else 0
        turn_cost = max(0, cp["tokens"] - prev_tokens)

        if accumulated + turn_cost > budget:
            break

        accumulated += turn_cost

        # 此輪在 body 中的起始索引：
        # body = message_history[1:]，所以 body_idx = msg_len - 1
        # 此輪的起點 = 前一個 checkpoint 的 msg_len
        prev_msg_len = token_checkpoints[i - 1]["msg_len"] if i > 0 else 1
        kept_start_body_idx = prev_msg_len - 1

        kept_turns += 1
        if kept_turns >= COMPRESS_KEEP_RECENT:
            break

    if kept_turns == 0:
        logger.info("[compressor] 所有舊對話輪均超出 budget，僅保留尾端訊息")

    return body[kept_start_body_idx:], kept_turns, accumulated


def _build_compress_system_addition() -> str:
    return (
        "\n\n重要限制：接下來的任務是生成對話摘要。"
        "你必須只以純文字回應，禁止呼叫任何工具。"
        "工具呼叫將被拒絕，請直接以 <analysis> 和 <summary> 標籤回應。"
    )


def _build_compress_user_message() -> str:
    return """\
請為以上對話生成一份詳盡的摘要。

先在 <analysis> 標籤中整理你的分析思路，確保涵蓋所有重要資訊。
然後在 <summary> 標籤中提供結構化摘要，包含以下部分（如適用）：

1. **主要請求與意圖**：用戶明確請求的內容，以及可推斷的最終目標
2. **關鍵技術概念**：重要技術術語、框架、架構決策、設計模式
3. **重要資源與參考資訊**：對話中提及的文件、連結、資料來源、具體數據或重要細節
4. **錯誤與修復**：遇到的問題以及如何解決
5. **解決方案進展**：問題解決過程，包括已嘗試的方法
6. **用戶訊息摘要**：用戶提出的所有重要問題和明確指令
7. **待處理任務**：尚未完成或被要求但未執行的事項
8. **當前工作狀態**：任務進行到哪個階段，目前焦點為何
9. **建議下一步（選擇性）**：若對話中途中斷，建議的後續行動

重要：只以純文字回應，以 <analysis> 開始，以 </summary> 結束。禁止呼叫工具。"""


def _extract_summary(raw_response: str) -> str:
    result = re.sub(r"<analysis>[\s\S]*?</analysis>", "", raw_response, flags=re.DOTALL)
    summary_match = re.search(r"<summary>([\s\S]*?)</summary>", result, flags=re.DOTALL)
    if summary_match:
        return summary_match.group(1).strip()
    result = re.sub(r"<[^>]+>", "", result)
    return result.strip() or raw_response.strip()


async def compress_conversation(
    message_history: list,
    llm_client,
    model_setting: dict,
    token_checkpoints: list,
    usage_prompt_tokens: int = 0,
) -> tuple[list, str, int]:
    """
    壓縮對話歷史。回傳 (new_history, summary_text, estimated_post_tokens)。
    失敗時回傳原始 message_history、空字串、0。

    token_checkpoints: 每輪對話結束時記錄的 {"msg_len", "tokens"} 清單。
    用於精確計算各輪 token 成本，動態決定壓縮後保留多少輪。
    """
    system_msg = message_history[0] if message_history[0].get("role") == "system" else None
    body = message_history[1:] if system_msg else list(message_history)

    if not body:
        logger.warning("[compressor] body 為空，跳過壓縮")
        return message_history, "", 0

    # 修改 system message，追加禁止工具的指令
    if system_msg:
        compress_system = {
            "role": "system",
            "content": (system_msg.get("content") or "") + _build_compress_system_addition(),
        }
        compress_input = [
            compress_system,
            *body,
            {"role": "user", "content": _build_compress_user_message()},
        ]
    else:
        compress_input = [
            *body,
            {"role": "user", "content": _build_compress_user_message()},
        ]

    compress_params = {
        k: v for k, v in model_setting.items()
        if k not in ("tools", "tool_choice", "stream_options")
    }
    compress_params["stream"] = False

    try:
        response = await llm_client.chat.completions.create(
            messages=compress_input, **compress_params
        )
        raw_summary = (response.choices[0].message.content or "") if response.choices else ""
        summary = _extract_summary(raw_summary)
        # completion_tokens 是摘要輸出的精確 token 數（含 <analysis>，作為保守上界）
        summary_tokens = (
            response.usage.completion_tokens
            if response.usage and response.usage.completion_tokens
            else max(len(summary) // 3, 100)
        )
    except Exception:
        logger.exception("[compressor] 壓縮 LLM 呼叫失敗，保留原始歷史")
        return message_history, "", 0

    if not summary:
        logger.warning("[compressor] 摘要內容為空，保留原始歷史")
        return message_history, "", 0

    # 計算可用於保留近期對話輪的 token 預算
    system_est = _estimate_system_tokens(system_msg)
    budget = CONTEXT_WINDOW_SIZE - COMPRESS_REMAINING_TOKENS - system_est - summary_tokens - _ACK_TOKENS

    recent_messages, kept_turns, kept_tokens = _select_recent_by_checkpoints(body, token_checkpoints, budget, usage_prompt_tokens)

    new_history: list = []
    if system_msg:
        new_history.append(system_msg)
    new_history.append({"role": "user", "content": f"# 對話摘要（自動壓縮）\n\n{summary}"})
    new_history.append({"role": "assistant", "content": "好的，我已載入對話摘要，繼續我們的工作。"})
    new_history.extend(recent_messages)

    estimated_post_tokens = system_est + summary_tokens + _ACK_TOKENS + kept_tokens
    logger.info(
        "[compressor] 壓縮完成：%d 條 → %d 條（保留最近 %d 輪，估算壓縮後 %d tokens）",
        len(message_history), len(new_history), kept_turns, estimated_post_tokens,
    )
    return new_history, summary, estimated_post_tokens
