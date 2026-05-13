# 跑版偵測除錯完整流程

`render_pptx` 回傳時，後端 PNG 縮圖已生成完畢（LibreOffice 轉換在回傳前等待完成）。

## 命名規則

檔名使用回傳訊息中的 `pptx_id`，格式為：

```
artifacts/pptx_<id>_slide_001.png
artifacts/pptx_<id>_slide_002.png
...
```

`pptx_id` 與總張數出現在 `render_pptx` 的回傳訊息開頭（格式：`[RENDER_PPTX_OK] pptx_id=pptx_a1b2c3d4 slide_count=N`）。

可直接用 `read_file` 開啟對應 PNG 進行視覺確認，無須使用者手動截圖：

```
read_file("artifacts/pptx_a1b2c3d4_slide_001.png")
```

## 視覺確認 3 步驟

當使用者回報**跑版、文字截斷、元素位置錯誤**等問題時，標準流程：

1. 從 `[RENDER_PPTX_OK]` 訊息取得 `pptx_id`
2. 呼叫 `read_file("artifacts/pptx_<id>_slide_NNN.png")` 確認版面
3. 根據圖片判斷問題後針對性修正腳本，重新呼叫 `render_pptx`

> 若不確定頁碼，可先用 `list_files("artifacts/")` 列出所有已生成的 PNG 檔名。
