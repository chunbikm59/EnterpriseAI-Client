# EnterpriseAI-Client

**為企業打造的 AI Client，示範如何在企業環境中安全部署 LLM，並透過 MCP 協定連結內部系統。**

---

## 專案定位

許多企業因資安政策禁止直接使用 ChatGPT、Claude 等公有 AI 平台，但自建的內部工具又功能有限，缺乏檔案解析、多媒體處理與系統整合能力。

**EnterpriseAI-Client** 是一個可直接部署到企業內部的 AI 對話介面，以實際解決下列問題為目標：

- 連接企業自有的 LLM（OpenAI 相容 API）或外部模型（Anthropic、OpenAI）
- 透過 MCP 協定連結公司內部系統（ERP、HR等系統）
- 生成 HTML / PPT 等文件成果，並在介面中即時渲染預覽

---

## 核心功能

### Artifact 生成與渲染

#### HTML Artifact
- AI 呼叫 `render_html` 工具生成 HTML，系統自動在側邊欄以 `<iframe>` 渲染
- 支援版本歷史：每次修改生成新版本，可在下拉選單切換回顧
- 一鍵「發布」到公開網址（`/p/{token}`），無需登入即可分享，永久連結

#### PPT Artifact
- AI 生成 PptxGenJS 腳本，前端瀏覽器本地執行腳本並產生 `.pptx` 
- 生成後自動上傳後端，由 LibreOffice 轉 PDF，再以 PyMuPDF 逐頁截圖
- 每張投影片縮圖即時顯示在對話介面中，可一鍵下載完整 `.pptx` 檔
- 串流進度條：腳本生成中即顯示佔位卡片動畫與已接收字元數

#### 工具生成圖片 / 影片截圖
- AI 呼叫工具（如PPT轉圖片、影片畫面擷取）後，系統自動偵測 `artifacts/` 目錄的新圖片
- 圖片直接 inline 嵌入對話中，同時作為視覺內容再次傳給 AI 讓後續對話可以參照

#### 文件解析與上傳

- 支援 `.pdf`, `.docx`, `.pptx`, `.xlsx` 等企業常見格式，自動轉為 Markdown 提供 AI 理解
- 支援圖片上傳，以 base64 高畫質模式傳給多模態模型
- 所有上傳/生成的檔案儲存於用戶個人目錄，透過帶簽章 URL 存取

#### MCP 協定整合

- 支援 **Streamable HTTP** 與 **stdio** 兩種連線方式
- 支援 MCP Tool / Roots / Elicitation
  - **Tool**：動態呼叫企業內部 API、資料庫查詢、系統操作等
  - **Roots**：取得對話目錄路徑，讓工具知道上傳/生成的檔案位置
  - **Elicitation**：執行敏感操作前彈出確認框，讓人類保有最終決策權

### 記憶機制

對話結束後，AI 自動在背景以獨立的 sub-agent 分析本輪對話，將值得保留的資訊（使用者偏好、專案背景、工作流程等）寫入用戶個人記憶目錄。下次對話開始時，系統根據使用者輸入的語意，用輕量模型從記憶索引中選出最相關的記憶注入上下文，讓 AI 能跨對話記住使用者。

- **萃取**：每輪結束後 fire-and-forget，fork 主對話歷史讓 sub-agent 判斷是否需要新增或更新記憶檔
- **預取**：新對話開始時，以使用者訊息語意比對記憶 description，最多注入 5 個最相關記憶（上限 20KB / 輪）
- **互斥保護**：主 LLM 若本輪已主動寫記憶，背景萃取自動跳過，避免重複

### 自動上下文壓縮

長對話 token 數接近模型上限時自動觸發：系統 fork 當前對話，呼叫 LLM 生成結構化摘要（含目標、關鍵決策、待辦事項、當前進度等），再以「摘要 + 最近 N 輪」取代完整歷史，壓縮後繼續對話而不中斷。

- 壓縮觸發閾值、保留輪數、context window 大小均可透過環境變數調整
- 每輪結束時記錄 token checkpoint，壓縮時精確計算各輪成本，動態決定保留哪幾輪最划算

### Agent Skills — 流程自動化

以結構化 Markdown 定義複雜多步驟流程，AI 根據情境自動選用對應 Skill：

```
system_skills/
  pptgenjs/            # PPT 生成流程規範
  frontend-design/     # 前端設計 HTML 生成規範
  whisper-transcription/ # 語音轉文字流程（需搭配 llm_proxy 專案）
```

使用情境：使用者輸入「幫我整理這份會議錄音重點並做成簡報」，AI 自動串接 STT → 摘要 → PPT 生成三個流程。

> **注意**：`whisper-transcription` Skill 的串流轉錄功能（NDJSON 逐段回傳）需搭配另一個專案 **llm_proxy**，該 Proxy 負責提供與 OpenAI Audio Transcriptions API 相容的 Whisper 端點並支援串流輸出。本專案直接對接其 `/audio/transcriptions`，不需修改 Skill 本身。

### 語音 / 影片轉錄 × 圖文報告生成

這是幾個工具串接起來才能達成的複合場景，也是本專案最能展示「AI 工作流程」的功能：

1. **轉錄**：上傳線上會議錄影（或貼上影片路徑），AI 呼叫 Whisper 轉錄，取回帶時間戳的逐段文字（SRT / NDJSON 格式）
2. **分析**：AI 閱讀全文，找出重要決策、關鍵畫面對應的時間點
3. **截圖**：AI 呼叫內建的 `video_screenshot` 工具，對這些時間點用 ffmpeg 逐一截圖，圖片自動嵌入對話上下文
4. **生成成果**：AI 看著截圖 + 摘要，輸出圖文並茂的 Markdown 會議紀錄，或直接呼叫 PPT 工具，把截圖嵌入對應投影片

關鍵技術細節：
- 截圖後系統偵測到 `artifacts/` 新圖片，自動 inline 顯示並以 base64 重新注入對話歷史，AI 即可「看到」畫面
- PPT 生成走 PptxGenJS 腳本路線，截圖路徑以 base64 直接寫入腳本，生成完整帶圖的 `.pptx`
- 整個流程在同一個對話中完成，使用者可隨時介入調整截圖時間點或修改摘要

---

## Harness 與上下文工程

Context 空間是稀缺資源，本專案的核心設計原則是：**記憶只注入最相關的、工具結果超大就截短、壓縮時以真實 token 成本而非訊息數量決定保留什麼。**

### 多層記憶系統

預取（Prefetch）→ 注入（Inject）→ 萃取（Extract）三層完全解耦：

- **預取**：每輪開始時，以使用者訊息語意呼叫輕量 LLM（JSON mode），從記憶索引的 `description` frontmatter 中選出最相關的最多 5 個檔案，單輪上限 20KB、整個 session 上限 60KB；以 `already_surfaced` set 防止同 session 重複注入
- **注入**：工具執行完、下次 LLM 呼叫前才注入，以 `<system-reminder>` 標籤與原始 system prompt 邊界隔開，每輪只注入一次
- **萃取**：回合結束後 fire-and-forget，fork 完整對話歷史讓 sub-agent 判斷是否要寫記憶；主 LLM 若本輪已寫過記憶則互斥跳過；游標只分析新訊息，避免重複分析舊對話

### Token Checkpoint + 精確 Budget 壓縮

- 每輪結束時記錄 `{"msg_len": int, "tokens": int}` checkpoint（API 精確值，非估算）
- 觸發壓縮時，以 checkpoint 還原各輪的真實 token 成本，從最新輪往前貪婪選取直到超出 budget
- Budget 計算：`context window - 觸發閾值 - system tokens - 摘要 tokens - ack tokens`，最後才分配給「保留幾輪」；壓縮後清空 checkpoint 重新累積

### Fork-based 子任務隔離

壓縮和記憶萃取都以 fork 主對話前綴的方式執行：子任務繼承原始 system prompt、前綴與主對話相同（可命中 prompt cache）、工具集被明確限制（萃取只允許檔案操作、壓縮完全禁止工具），無法污染主流程。

萃取 fork 另一個效率設計：manifest 預先掃描並注入到 user message，sub-agent 第一輪即可並行 read 所有需要更新的記憶檔，省掉一個額外的 `list_files` turn。

### 工具結果大小控制

工具結果超過 50,000 字元時不內聯，改為寫檔並回傳「摘要 + 前 2000 字預覽 + 路徑」，以 `<tool-result-too-large>` 標籤標記，讓 LLM 知道可以去讀完整內容。`read_file` 本身永遠不觸發此機制（避免遞迴）。

### 圖片的上下文注入

工具回傳圖片時只帶路徑，不直接內嵌 base64，由 agent 在工具結果處理後讀檔轉 base64 再注入上下文，避免圖片資料在上下文中重複佔用 token。

---

## 使用者資料夾結構

每位使用者有獨立的隔離目錄，所有資料在本地伺服器管理：

```
user_profiles/
└── {user_id}/
    ├── memory/                          # 跨對話記憶檔
    │   ├── MEMORY.md                    # 記憶索引（預取時掃描）
    │   ├── user_role.md                 # 使用者背景記憶
    │   └── feedback_*.md                # 工作偏好記憶
    ├── skills/                          # 使用者自訂 Agent Skills
    └── conversations/
        └── {conversation_id}/
            ├── history.jsonl            # 對話紀錄（含 LLM 訊息與 UI 事件）
            ├── uploads/                 # 使用者上傳的檔案
            │   └── 20260426T103012_report.pdf
            └── artifacts/               # 工具 / AI 產出物
                ├── chart.png            # 工具生成圖片（自動 inline 嵌入對話）
                ├── slide_001.png        # PPT 投影片截圖
                └── {pptx_id}.pptx      # 生成的簡報檔
```

- `history.jsonl`：每行一筆 JSON，類型包含 `session_meta`、`message`、`ui_event`（截圖、側邊欄更新等）、`title`
- `artifacts/`：MCP 工具的輸出落地點，agent 每輪結束後自動掃描新增檔案並嵌入對話
- 所有檔案透過帶簽章 URL 存取（`/api/user-files/`），未登入無法直接存取

---

## 技術架構

| 層次 | 技術 |
|------|------|
| 對話介面 | [Chainlit](https://chainlit.io/)|
| 後端 API | FastAPI |
| 文件解析 | markitdown + PyMuPDF |
| PPT 後端渲染 | LibreOffice（headless）→ PyMuPDF 截圖 |
| PPT 前端生成 | PptxGenJS（瀏覽器執行，完整相容 PowerPoint） |
| 語音處理 | ffmpeg + whisper |
| 對話儲存 | PostgreSQL（Alembic 管理 schema） |

---

## 使用情境示範

### 圖像辨識與自動通報

上傳產品瑕疵報告或成分圖表，AI 提取數值、寫入資料庫，並透過 MCP 呼叫內部任務發派系統通報負責人員。整個流程在同一個對話介面完成，使用者隨時可以介入調整。

### 會議錄影 → 圖文並茂的簡報 / 會議紀錄

使用者上傳或輸入線上會議錄影路徑，輸入一句「幫我整理成圖文簡報」，AI 自動：

1. Whisper 轉錄影片，取得含時間戳的完整文字
2. 分析內容，找出值得截圖的關鍵時間點（決策宣布、圖表說明、白板演示）
3. 批次截圖，圖片自動嵌入對話讓 AI 確認畫面內容
4. 生成圖文 Markdown 會議紀錄，或直接輸出每頁都有截圖的 `.pptx` 簡報

→ 整個流程在同一個對話中完成，使用者可隨時介入調整截圖時間點或修改摘要。

### 會議摘要到任務追蹤

AI 轉錄影片 → 擷取決策與行動項 → 使用者可介入修改 → 連結 HR 資料庫對照員工身份 → 透過 MCP 發布任務通知。

### 簡單指令觸發複雜流程

使用者輸入「幫我請假」，AI 透過 Agent Skill 了解請假流程，自動操作 HR 系統、填寫表單，並截圖確認每個步驟。

---

## 安裝與執行

> 本專案使用 Python 3.13 開發

```bash
# 安裝相依套件
pip install -r requirements.txt

# 設定環境變數
cp .env.example .env
# 編輯 .env，填入 LLM API 金鑰等設定

# 啟動服務
python main.py
```

服務啟動後預設於 `http://localhost:8000` 提供對話介面。

---

## Roadmap

| 功能 | 狀態 |
|------|------|
| MCP 協定支援（Tool / Roots / Elicitation） | 已完成 |
| 文件解析（PDF / Office → Markdown） | 已完成 |
| 圖片上傳與多模態辨識 | 已完成 |
| HTML Artifact 生成、渲染、版本管理與發布 | 已完成 |
| PPT Artifact 生成、縮圖預覽與下載 | 已完成 |
| 工具生成圖片 inline 嵌入對話 | 已完成 |
| 影片截圖自動嵌入並回傳 AI | 已完成 |
| Agent Skills 流程自動化 | 已完成 |
| 影片 / 語音轉錄（STT） | 已完成 |
| 對話歷史持久化（PostgreSQL） | 已完成 |
| OAuth / SSO 登入範例 | 已完成 |
