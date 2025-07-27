import json
from typing import Any, Dict, List, Optional
from utils.llm_client import get_llm_client, get_model_setting

OVERSEER_SYSTEM_PROMPT = """你是一個元認知監督者（Overseer LLM）。
你的工作：在每個工具鏈（tool chain）結束後，審視目前的任務進度、已嘗試的方法與結果、是否有遺漏子任務，並提出下一步策略或終止建議。
請務必以 JSON 輸出，遵守我提供的 schema。"""

OVERSEER_USER_PROMPT = """任務目標（使用者最初需求）：
{goal}

目前的行動紀錄（含 LLM 思考、工具呼叫與結果，按時間序，已截斷至安全長度）：
{trace}

請務必輸出 JSON，遵守以下鍵：
status: "continue" | "need_user_input" | "terminate"
progress_summary: 對目前進度的精簡總結
missing_or_interrupted_subtasks: 尚未完成/被遺忘的子任務列表
tried_paths: 列出已嘗試方法、結果（success/fail/partial）、以及原因
next_actions: 若 status=continue，請列出建議的下一步行動（可含應呼叫的 tool 與其 args）
loop_or_blocker_detected: 是否偵測到卡住/重複嘗試的循環，以及建議
ask_user: 需要用戶提供哪些資訊（若 status=need_user_input）
final_recommendation_to_user: 若 status=terminate 時，請對使用者提出明確的下一步建議
範例:
{{
  "status": "continue | need_user_input | terminate",
  "progress_summary": "string",
  "missing_or_interrupted_subtasks": ["string", "..."],
  "tried_paths": [
    {{"approach": "string", "result": "success | fail | partial", "why": "string"}}
  ],
  "next_actions": [
    {{
      "rationale": "string",
      "proposed_tool": "string|null",
      "proposed_args": {{}},
      "expected_outcome": "string"
    }}
  ],
  "loop_or_blocker_detected": {{
    "detected": true,
    "reason": "string",
    "suggestion": "string"
  }},
  "ask_user": "null | string (需要使用者提供的精確資料或決策)",
  "final_recommendation_to_user": "null | string (若 status=terminate 時給使用者的下一步指示)"
}}
請只輸出單一 JSON，且不得包含多餘文字。"""

def get_overseer_model_setting():
    params = get_model_setting()
    # 使用較便宜或擅長推理/長上下文的模型
    params.update({
        "model": "gpt-4o-mini",   # 舉例，請換成你實際要用的
        "temperature": 0.2,
    })
    # Overseer 我們一般不需要 streaming
    params.pop("stream", None)
    return params

def build_tool_trace(message_history: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    """
    從 message_history 中擷取包含：
    - 使用者原始目標（可從 system / user 開頭第一則取出）
    - 每個 assistant -> tool_calls
    - 每個 tool 的結果
    並壓縮到 max_chars 內。
    """
    # 你也可以明確只擷取 role in ['assistant','tool'] 的片段
    buf = []
    for msg in message_history:
        role = msg.get("role")
        if role == "user":
            buf.append(f"[user] {msg.get('content','')}")
        elif role == "assistant":
            # 如果這是一般回答
            if msg.get("content"):
                buf.append(f"[assistant] {msg['content']}")
            # 如果包含 tool_calls，可記錄名稱 & 引數（避免太長，必要可截斷）
            if "tool_calls" in msg and msg["tool_calls"]:
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    args = tc["function"]["arguments"]
                    buf.append(f"[assistant->tool_call] {name}({args})")
        elif role == "tool":
            tcid = msg.get("tool_call_id", "")
            content = msg.get("content", "")
            if len(content) > 1000:
                content = content[:1000] + "...[truncated]"
            buf.append(f"[tool#{tcid}] {content}")
    trace = "\n".join(buf)
    if len(trace) > max_chars:
        trace = trace[-max_chars:]  # 保留最後一段最貼近現況
    return trace

async def run_overseer(goal: str, message_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    llm_client = get_llm_client(mode="async")  # 你原本的取用方式
    params = get_overseer_model_setting()

    trace = build_tool_trace(message_history)

    messages = [
        {"role": "system", "content": OVERSEER_SYSTEM_PROMPT},
        {"role": "user", "content": OVERSEER_USER_PROMPT.format(goal=goal, trace=trace)},
    ]

    resp = await llm_client.chat.completions.create(
        messages=messages,
        **params,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content 
    try:
        return json.loads(content)
    except Exception:
        # 後備：若 LLM 沒有回傳合法 JSON，嘗試簡單修復或回傳 fallback
        return {
            "status": "terminate",
            "progress_summary": "Overseer 回傳非 JSON，無法解析。",
            "missing_or_interrupted_subtasks": [],
            "tried_paths": [],
            "next_actions": [],
            "loop_or_blocker_detected": {"detected": True, "reason": "invalid_json", "suggestion": "請重新嘗試"},
            "ask_user": None,
            "final_recommendation_to_user": "請求使用者或系統重試 Overseer 程序。"
        }
    

def render_overseer_for_user(r: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"🔎 Overseer 狀態：{r.get('status')}")
    if r.get("progress_summary"):
        lines.append(f"📌 進度總結：{r['progress_summary']}")
    if r.get("missing_or_interrupted_subtasks"):
        lines.append("🧭 尚未完成/遺漏的子任務：")
        for s in r["missing_or_interrupted_subtasks"]:
            lines.append(f"  - {s}")
    if r.get("tried_paths"):
        lines.append("🧪 已嘗試方法：")
        for p in r["tried_paths"]:
            lines.append(f"  - {p['approach']} → {p['result']}（原因：{p.get('why','')}）")
    if r.get("next_actions"):
        lines.append("➡️ 建議的下一步：")
        for a in r["next_actions"]:
            lines.append(f"  - {a['rationale']} | tool: {a.get('proposed_tool')} args: {a.get('proposed_args')}")
    if (lp := r.get("loop_or_blocker_detected")) and lp.get("detected"):
        lines.append(f"⚠️ 阻塞/死循環偵測：{lp.get('reason')} → 建議：{lp.get('suggestion')}")
    if r.get("ask_user"):
        lines.append(f"🙋 需要使用者補充：{r['ask_user']}")
    if r.get("final_recommendation_to_user"):
        lines.append(f"🧭 給使用者的最終建議：{r['final_recommendation_to_user']}")
    return "\n".join(lines)