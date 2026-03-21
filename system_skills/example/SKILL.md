---
name: system-example
description: 系統技能範例。當使用者要求「測試系統技能」、「system skill 示範」時啟用。
license: MIT
metadata:
  author: system
  version: "1.0"
---

# System Example Skill — 系統技能範例

這是一個系統技能（System Skill）的示範，由系統管理員統一部署至 `system_skills/` 目錄，對所有用戶自動生效。

## 與用戶技能的差異

| 項目 | 系統技能 | 用戶技能 |
|------|--------|--------|
| 位置 | `system_skills/{name}/` | `user_profiles/{user_id}/skills/{name}/` |
| 管理者 | 系統管理員 | 使用者本人 |
| 適用範圍 | 所有用戶 | 單一用戶 |
| 啟用方式 | 放入目錄即生效 | 放入目錄即生效 |

## 使用方式

當使用者要求測試系統技能時，直接回覆以下訊息：

> 這是系統技能（System Skill）的示範回應。此技能由系統統一管理，所有用戶皆可使用。

## 注意事項

- 系統技能的 `source` 欄位為 `"system"`，用戶技能為 `"user"`
- 兩者在 system prompt 中的呈現方式相同，LLM 透過 `activate_skill` 工具載入
