---
name: whisper-transcription
description: 呼叫本地 LLM Proxy 的 Whisper 音訊轉錄端點（POST /audio/transcriptions），支援串流與非串流模式、多種輸出格式（json/text/srt/vtt）、指定語言、提示詞、Cluster 等參數。當使用者需要轉錄音訊檔案、測試 Whisper API、或診斷轉錄問題時使用。
---

## 概覽

本 skill 負責呼叫 `POST /audio/transcriptions` 端點，將音訊檔案送交本地 whisper.cpp 進行語音辨識，並取回轉錄結果。

端點與 OpenAI Audio Transcriptions API 相容，支援串流輸出（NDJSON）與一次性完整輸出兩種模式。

## 端點資訊

- **URL**: `${BASE_URL}/audio/transcriptions`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`

## 參數

所有參數（包含檔案）統一透過 `http_request` 的 `form_fields` 以 JSON 傳入：

| 欄位 | 類型 | 預設 | 說明 |
|------|------|------|------|
| `file` | file | 必填 | 音訊檔案路徑（對話資料夾內的檔名，或完整絕對路徑） |
| `model` | string | `whisper-1` | 模型名稱（固定為 whisper-1） |
| `language` | string | null | 語言代碼（例如 `zh`、`en`、`ja`）；省略則自動偵測 |
| `prompt` | string | null | 提示詞，引導辨識風格或專有詞彙 |
| `response_format` | string | `json` | 輸出格式：`json` / `text` / `srt` / `vtt` |
| `temperature` | float | `0.0` | 取樣溫度（0.0 = 貪婪解碼） |
| `stream` | bool | `false` | 串流模式（NDJSON，每行一個 segment） |
| `cluster` | string | null | 指定 Whisper Cluster 名稱；省略則使用預設 cluster |

## 使用步驟

> **本 skill 透過 `http_request` MCP 工具發送請求。目標 URL 符合 `LLM_BASE_URL` 前綴時，系統自動注入 Authorization，無需手動填寫 API Key。**

### 步驟 1：串流轉錄（標準用法）

```
url:          ${BASE_URL}/audio/transcriptions
method:       POST
form_fields:  {"file": "audio.wav", "model": "whisper-1", "stream": "true"}
stream:       true
```

> `form_fields` 中值為存在的檔案路徑時，會自動以二進位上傳；其他值當普通字串傳入。
> `http_request` 的 `stream: true` 讓回應 chunk 即時顯示於 UI 子步驟中。

**串流回應（NDJSON，每行一個 segment）：**
```
{"text": "[00:00:00.000 --> 00:00:03.500]  第一段辨識文字"}
{"text": "[00:00:03.500 --> 00:00:07.200]  第二段辨識文字"}
```

### 步驟 2：指定語言與其他參數

```
url:          ${BASE_URL}/audio/transcriptions
method:       POST
form_fields:  {"file": "audio.wav", "model": "whisper-1", "language": "zh", "response_format": "text", "stream": "true"}
stream:       true
```
