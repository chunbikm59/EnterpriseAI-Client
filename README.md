# EnterpriseAI-Client

🎯 **為企業打造的 AI Client，支援 MCP 協定、文件與圖片解析，完美解決企業對公有 AI 工具的安全疑慮。**

---

## 📘 專案簡介

許多企業因隱私與資安政策，禁止使用 ChatGPT、Claude 等公有 AI 平台，僅允許使用內部符合公司政策的 LLM 與 AI 工具。然而這些工具有些功能有限，甚至缺乏檔案上傳、圖片辨識、多媒體處理與企業內其他系統工具整合能力。

**EnterpriseAI-Client** 的目標是示範如何建立一個 AI Client，支援在企業實務應用中所需的基本功能，並透過 **MCP（Model Context Protocol）** 協定，連結公司內部系統與工具，讓企業能快速導入並持續堆疊 LLM 的能力，實際處理內部業務流程。符合企業對資安、可控性與擴充性的需求。

---

## 🧠 主要功能

- ✅ **支援 MCP（Model Context Protocol）**  
  將 LLM 與企業內部系統整合，實現雙向溝通。支援 Streamable HTTP 與 stdio 兩種連線方式，支援 MCP 的 Tool、Roots、Elicitation。

- ✅ **圖片與文件解析**  
  支援 `.pdf`, `.docx`, `.pptx`, `.xlsx` 等企業文書常見格式，自動轉為 Markdown 供 AI 理解。

- ✅ **自定義 Prompt 動態註冊成 MCP Tool**（現已推薦使用 Agent Skills 取代）
  透過 `user_custom_prompt.py` 讓使用者可以動態註冊自定義的 prompt 成為 MCP 工具，模型可根據情境自動選擇相關的 prompt 來理解複雜流程。

- ✅ **Agent Skills — 新增自定義流程管理**
  現為推薦的流程自動化方式，取代舊有的自定義 Prompt 機制。透過 Anthropic Agent Skills 標準，以結構化方式定義複雜的多步驟流程，讓模型能根據情境自動選用對應的 Skill 並執行任務。詳見 [system_skills/](system_skills/) 與 [user_profiles/](user_profiles/) 目錄。

- ✅ **影片轉錄與多媒體語音轉文字（STT）**  
  支援語音/影片檔案內容自動轉錄，適用於會議錄影、影音檔案等多媒體資料。

- ✅ **第三方登入（OAuth）範例**  
  提供 OAuth 登入範例，協助企業整合內部 SSO 或第三方認證機制。

---

## 🏢 使用情境


- 🧪 **圖像辨識與解釋 — 從缺陷分析到自動通報**  
  上傳產品瑕疵報告或化學成分圖表後，多模態 AI 模型提取圖表數值、紀錄到資料庫，也可選擇呼叫內部的分析工具得出可能成因與負責單位。再透過連結任務發派系統通報負責該製程的生產站點人員進行調查與處理。這一切過程都在同個App中完成，使用者隨時可以介入調整流程。


- 🎤 **會議影音摘要（開發中）— 從摘要到任務追蹤**  
  AI 轉錄影片後，會自動從內容中抓出決策與行動項，使用者此時可選擇介入修改任務內容或是調整執行人員，接著連結企業人資資料庫對照實際員工身份，再透過連結團隊慣用的任務追蹤工具進行任務發布與通知。

- 📝 **自定義流程自動化 — 從簡短指令到複雜流程執行**  
  透過自定義 Prompt 功能，使用者可以用簡短的命令（如「幫我請假」）觸發模型自主查看相關 prompt，了解完整的請假流程並自動執行，包括系統操作、表單填寫、截圖確認等步驟。

## 🛠️ 技術架構

- **前端介面**：Chainlit
- **後端服務**：FastAPI
- **檔案處理**：`markitdown`, `docling`
- **語音處理（規劃中）**：`ffmpeg`, `whisper`, `faster-whisper`

---

## 🗺️ Roadmap

| 功能項目                             | 狀態    |
|----------------------------------|---------|
| ✅ MCP 協定支援（含 Tool, Roots, Elicitation） | 已完成 |
| ✅ 檔案解析（PDF/Office → Markdown） | 已完成 |
| ✅ 支援圖片上傳                | 已完成 |
| ✅ 可自訂Prompt動態註冊成mcp tool讓模型自主取得相關的prompt（已由 Agent Skills 取代）|已完成|
| ✅ Agent Skills 支援（新增自定義流程管理）| 已完成 |
| ✅ 影片轉錄與多媒體語音轉文字（STT） | 已完成 |
---

## 🔧 MCP 工具開發

### 支援 Tool、Roots、Elicitation

本專案支援 MCP 協定下的 Tool、Roots、Elicitation 功能：
- **Tool**：可註冊自定義 prompt、API、或內部工具，讓模型根據需求自動選用。
- **Roots**： 主要用於獲得當前對話的資料夾路徑，方便掌握本次對話所上傳、生成的檔案狀況。
- **Elicitation**：可主動詢問使用者、在AI進行敏感操作前(如寫入或修改)讓人類使用者可以做最後確認。

### 自定義 Prompt 動態註冊

`mcp_servers/user_custom_prompt.py` 提供了一個強大的功能，讓您可以動態註冊自定義的 prompt 成為 MCP 工具：

#### 主要特色
- **動態註冊**：透過 `register_mcp_tool()` 函數動態創建 MCP 工具
- **情境感知**：模型可根據使用者的問題自動選擇相關的 prompt
- **流程自動化**：用簡短指令觸發複雜的多步驟流程

#### 使用範例
```python
# 註冊一個請假流程的 prompt
register_mcp_tool(
    func_name="prompt_1", 
    describe="請假流程",  # 這會影響模型是否能根據情境選擇正確的prompt
    return_string='''
        1. 先到myHR系統(http:myhr)點擊請假，未指定就預設選擇特休假
        2. 保存假單->送簽
        3. 截圖確認已送出的假單
        4. 到部門行事曆標記請假並截圖確認
    ''')
```

當使用者輸入「幫我請假」時，模型會自動：
1. 識別這是請假相關的需求
2. 載入對應的 prompt 了解完整流程
3. 按步驟執行請假操作
4. 提供截圖確認每個步驟

---

## 🔧 安裝與執行

> 本專案使用 Python 3.13 開發測試

```bash
# 2. 安裝
pip install -r requirements.txt

# 3. 啟動服務
python main.py
