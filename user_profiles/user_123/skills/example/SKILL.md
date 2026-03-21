---
name: example
description: 文字統計示範技能。當使用者要求「統計文字」、「分析字數」、「測試 example skill」時啟用。
license: MIT
compatibility: Requires Python 3.8+
metadata:
  author: user_123
  version: "1.0"
---

# Example Skill — 文字統計工具

這個技能示範完整的 AgentSkills 資料夾結構，實際功能是統計輸入文字的字數、行數與字元數。

## 使用方式

當使用者提供一段文字並要求統計時：

1. 將文字存成暫存檔（或直接用 stdin）
2. 執行 `scripts/count.py`
3. 將結果格式化後回傳給使用者

```bash
python user_profiles/user_123/skills/example/scripts/count.py "你好，世界！Hello World."
```

## 輸出格式

```
字元數（含空白）: 24
字元數（不含空白）: 21
單字數（英文）: 2
行  數: 1
```

## 邊界條件

- 空字串 → 全部回傳 0
- 純中文文字 → 英文單字數為 0，字元數正常計算
- 多行文字 → 以 `\n` 計算行數

詳細技術說明請參考 [references/REFERENCE.md](references/REFERENCE.md)。
範例輸入請參考 [assets/sample.txt](assets/sample.txt)。
