# Technical Reference — Example Skill

## count.py 實作說明

`scripts/count.py` 接受一個命令列引數（字串），輸出四項統計數值。

### 統計邏輯

| 項目 | 計算方式 |
|------|----------|
| 字元數（含空白） | `len(text)` |
| 字元數（不含空白） | `len(text.replace(" ", "").replace("\n", "").replace("\t", ""))` |
| 英文單字數 | `len(text.split())` — 以空白/換行分割，適用英文 |
| 行數 | `len(text.splitlines()) or 1` |

### 中文處理

中文字符每個計為 1 個字元，`split()` 不會將中文詞切開，
因此「英文單字數」對純中文文字意義有限，僅供參考。

## 錯誤碼

| Exit code | 說明 |
|-----------|------|
| 0 | 正常執行 |
| 1 | 未提供引數 |
