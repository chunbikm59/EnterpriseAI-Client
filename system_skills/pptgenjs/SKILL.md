---
name: pptgenjs
description: 使用 pptxgenjs 生成 PowerPoint 簡報（.pptx）。當使用者要求製作簡報、投影片、PPT、presentation 時啟用。呼叫 render_pptx 工具執行腳本，結果會在 sidebar 顯示預覽並提供下載按鈕。
license: MIT
metadata:
  author: system
  version: "2.0"
---

# PptxGenJS Skill — 生成 PowerPoint 簡報

本 skill 負責撰寫 **pptxgenjs** JavaScript 腳本，並透過 `render_pptx` 工具在 sidebar 中渲染投影片預覽與下載按鈕。

## render_pptx 工具規格

| 參數 | 類型 | 說明 |
|------|------|------|
| `pptx_script` | string | 完整 pptxgenjs JS 程式碼（不含 `<script>` 標籤），最後必須呼叫 `window.__pptxDone(prs)` |
| `title` | string | 簡報標題（顯示於 sidebar 頂部，建議 20 字以內） |
| `slide_count` | int | 預計投影片張數（用於 sidebar 佔位顯示） |

> **CDN bundle** 全域建構函式為 `PptxGenJS`（注意大小寫），由瀏覽器端自動載入：
> `https://cdn.jsdelivr.net/gh/gitbrent/pptxgenjs/dist/pptxgen.bundle.js`

## 腳本必要規則

1. **建構函式**：`new PptxGenJS()`（瀏覽器端，不是 Node.js 的 `new pptxgen()`）
2. **結尾必須呼叫** `window.__pptxDone(prs);`，否則無法觸發下載
3. 腳本上限 **200KB**，精簡資料即可，不需嵌入大型圖片

## 基本結構

```javascript
let prs = new PptxGenJS();
prs.layout = "LAYOUT_16x9";  // LAYOUT_16x9 | LAYOUT_16x10 | LAYOUT_4x3 | LAYOUT_WIDE
prs.title = "簡報標題";

let slide = prs.addSlide();
slide.addText("Hello World!", { x: 0.5, y: 0.5, fontSize: 36, color: "363636" });

window.__pptxDone(prs);
```

## 版面尺寸

| 版面 | 尺寸（英吋） |
|------|------------|
| `LAYOUT_16x9` | 10 × 5.625（預設） |
| `LAYOUT_16x10` | 10 × 6.25 |
| `LAYOUT_4x3` | 10 × 7.5 |
| `LAYOUT_WIDE` | 13.3 × 7.5 |

座標原點在左上角，x / y / w / h 均以英吋為單位，也可用 `"50%"` 百分比字串。

---

## 文字

```javascript
slide.addText("標題文字", {
  x: 0.5, y: 0.3, w: 9, h: 0.8,
  fontSize: 28, bold: true,
  color: "1e293b",              // hex，不加 #
  align: "center",              // left | center | right
  valign: "middle",             // top | middle | bottom
  fontFace: "微軟正黑體",
  margin: 0,                    // 與形狀對齊時設 0 消除內邊距
});

// 字元間距
slide.addText("SPACED", { x: 1, y: 1, w: 8, h: 1, charSpacing: 6 });

// Rich text（混合樣式）
slide.addText([
  { text: "粗體 ", options: { bold: true } },
  { text: "斜體", options: { italic: true } },
], { x: 1, y: 2, w: 8, h: 1 });

// 多行（需加 breakLine）
slide.addText([
  { text: "第一行", options: { breakLine: true } },
  { text: "第二行", options: { breakLine: true } },
  { text: "第三行" },
], { x: 0.5, y: 0.5, w: 8, h: 2 });
```

---

## 清單與項目符號

```javascript
// ✅ 正確：用 bullet: true，搭配 breakLine
slide.addText([
  { text: "第一項", options: { bullet: true, breakLine: true } },
  { text: "第二項", options: { bullet: true, breakLine: true } },
  { text: "第三項", options: { bullet: true } },
], { x: 0.5, y: 1, w: 8, h: 3 });

// ❌ 錯誤：禁止直接用 "•" unicode，會產生雙重符號
slide.addText("• 項目", { ... });

// 縮排子項目
{ text: "子項目", options: { bullet: true, indentLevel: 1, breakLine: true } }

// 數字清單
{ text: "第一點", options: { bullet: { type: "number" }, breakLine: true } }
```

---

## 形狀

```javascript
// 矩形
slide.addShape(prs.shapes.RECTANGLE, {
  x: 0.5, y: 0.8, w: 1.5, h: 3.0,
  fill: { color: "4f46e5" },
  line: { color: "000000", width: 2 },
});

// 橢圓
slide.addShape(prs.shapes.OVAL, { x: 4, y: 1, w: 2, h: 2, fill: { color: "0ea5e9" } });

// 線條
slide.addShape(prs.shapes.LINE, {
  x: 1, y: 3, w: 5, h: 0,
  line: { color: "94a3b8", width: 2, dashType: "dash" },
});

// 透明度
slide.addShape(prs.shapes.RECTANGLE, {
  x: 1, y: 1, w: 3, h: 2,
  fill: { color: "0088CC", transparency: 50 },
});

// 陰影（每次呼叫都要傳新物件，不可共用！）
const makeShadow = () => ({ type: "outer", color: "000000", blur: 6, offset: 2, angle: 135, opacity: 0.15 });
slide.addShape(prs.shapes.RECTANGLE, {
  x: 1, y: 1, w: 3, h: 2,
  fill: { color: "ffffff" },
  shadow: makeShadow(),
});
```

### 陰影參數

| 屬性 | 說明 |
|------|------|
| `type` | `"outer"` 或 `"inner"` |
| `color` | 6 碼 hex（不加 `#`，不用 8 碼） |
| `blur` | 0–100 pt |
| `offset` | 0–200 pt（**必須非負數**，負值會損毀檔案） |
| `angle` | 0–359 度（270 = 向上投影） |
| `opacity` | 0.0–1.0 |

---

## 圖片

> ⚠️ **長寬比規則：不知道圖片原始尺寸時，必須使用 `sizing: { type: "contain" }`，絕對不要隨意填 `w` 和 `h`，否則圖片會變形。**

```javascript
// ✅ 正確：不知道尺寸時，用 contain 保持比例
slide.addImage({
  path: "https://example.com/image.png",
  x: 1, y: 1, w: 6, h: 4,                   // 定義「容器」大小
  sizing: { type: "contain", w: 6, h: 4 },   // 圖片自動縮放到容器內，不裁切、不變形
});

// ✅ 正確：填滿容器（可能裁切，但不變形）
slide.addImage({
  path: "image.png",
  x: 0, y: 0, w: 10, h: 5.625,
  sizing: { type: "cover", w: 10, h: 5.625 },
});

// ✅ 正確：已知原始尺寸時才手動計算等比
const origW = 1978, origH = 923, maxH = 3.0;
const calcW = maxH * (origW / origH);
slide.addImage({ path: "img.png", x: (10 - calcW) / 2, y: 1.2, w: calcW, h: maxH });

// ❌ 錯誤：不知道尺寸卻直接填 w/h，圖片必然變形
slide.addImage({ path: "image.png", x: 1, y: 1, w: 5, h: 3 });
```

### sizing 模式

| 模式 | 說明 |
|------|------|
| `contain` | 等比縮放到容器內，不裁切（最常用） |
| `cover` | 等比縮放填滿容器，超出部分裁切 |
| `crop` | 裁取指定區域：`{ type: "crop", x, y, w, h }` |

```javascript
// base64 圖片同樣需要 sizing
slide.addImage({
  data: "image/png;base64,iVBORw0KGgo...",
  x: 1, y: 1, w: 5, h: 3,
  sizing: { type: "contain", w: 5, h: 3 },
});

// 其他選項
slide.addImage({
  path: "image.png", x: 1, y: 1, w: 5, h: 3,
  sizing: { type: "contain", w: 5, h: 3 },
  rotate: 45, rounding: true, transparency: 50,
});
```

---

## 背景

```javascript
slide.background = { color: "F1F1F1" };
slide.background = { path: "https://example.com/bg.jpg" };
slide.background = { data: "image/png;base64,iVBORw0KGgo..." };
```

---

## 表格

```javascript
slide.addTable([
  ["標題一", "標題二", "標題三"],
  ["資料 A", "資料 B", "資料 C"],
], {
  x: 0.5, y: 1, w: 9,
  border: { pt: 1, color: "e2e8f0" },
  fill: { color: "f8fafc" },
  fontSize: 14,
});

// 進階：樣式化標題列 + 合併儲存格
let tableData = [
  [
    { text: "項目", options: { fill: { color: "4f46e5" }, color: "ffffff", bold: true } },
    { text: "說明", options: { fill: { color: "4f46e5" }, color: "ffffff", bold: true } },
  ],
  [{ text: "合併跨欄", options: { colspan: 2 } }],
];
slide.addTable(tableData, { x: 0.5, y: 1.5, w: 9, colW: [3, 6] });
```

---

## 圖表

```javascript
// 直條圖
slide.addChart(prs.charts.BAR, [{
  name: "營收", labels: ["Q1","Q2","Q3","Q4"], values: [4500, 5500, 6200, 7100]
}], {
  x: 0.5, y: 1, w: 9, h: 4, barDir: "col",
  chartColors: ["4f46e5"],
  chartArea: { fill: { color: "ffffff" }, roundedCorners: true },
  catAxisLabelColor: "64748b", valAxisLabelColor: "64748b",
  valGridLine: { color: "e2e8f0", size: 0.5 }, catGridLine: { style: "none" },
  showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "1e293b",
  showLegend: false,
});

// 折線圖
slide.addChart(prs.charts.LINE, [{
  name: "趨勢", labels: ["1月","2月","3月"], values: [32, 35, 42]
}], { x: 0.5, y: 1, w: 9, h: 4, lineSize: 3, lineSmooth: true });

// 圓餅圖
slide.addChart(prs.charts.PIE, [{
  name: "佔比", labels: ["A","B","其他"], values: [35, 45, 20]
}], { x: 0.5, y: 1, w: 5, h: 4, showPercent: true, chartColors: ["4f46e5","0ea5e9","e2e8f0"] });
```

### 圖表類型

| 常數 | 圖表 |
|------|------|
| `prs.charts.BAR` | 直條 / 橫條 |
| `prs.charts.LINE` | 折線 |
| `prs.charts.PIE` | 圓餅 |
| `prs.charts.DOUGHNUT` | 甜甜圈 |
| `prs.charts.SCATTER` | 散佈 |
| `prs.charts.AREA` | 區域 |
| `prs.charts.RADAR` | 雷達 |

---

## 常見錯誤（務必避免）

1. **hex 顏色不加 `#`**
   ```javascript
   color: "FF0000"   // ✅
   color: "#FF0000"  // ❌ 損毀檔案
   ```

2. **不用 8 碼 hex 表示透明度**，改用 `opacity` 屬性
   ```javascript
   shadow: { color: "00000020" }               // ❌ 損毀檔案
   shadow: { color: "000000", opacity: 0.12 }  // ✅
   ```

3. **項目符號用 `bullet: true`**，不用 `"•"` unicode（會雙重符號）

4. **多行文字用 `breakLine: true`**，不要用 `\n`

5. **陰影 `offset` 必須非負數**，向上投影用 `angle: 270` 而非負的 offset

6. **每次傳入新的選項物件**，不要共用（pptxgenjs 會就地修改物件）：
   ```javascript
   const makeShadow = () => ({ type: "outer", blur: 6, offset: 2, color: "000000", opacity: 0.15 });
   slide.addShape(prs.shapes.RECTANGLE, { shadow: makeShadow(), ... });  // ✅ 每次新物件
   ```

7. **不要對 `ROUNDED_RECTANGLE` 疊加矩形邊框**（圓角無法對齊），改用 `RECTANGLE`

8. **`bullets` 配合間距用 `paraSpaceAfter`**，不要用 `lineSpacing`（會產生過大間距）

9. **圖片不知道原始尺寸時必須加 `sizing: { type: "contain", w, h }`**，直接填 `w/h` 而不加 `sizing` 會讓圖片拉伸變形
   ```javascript
   // ❌ WRONG
   slide.addImage({ path: "img.png", x: 1, y: 1, w: 5, h: 3 });
   // ✅ CORRECT
   slide.addImage({ path: "img.png", x: 1, y: 1, w: 5, h: 3, sizing: { type: "contain", w: 5, h: 3 } });
   ```

---

## 企業模板

模板 `.pptx` 放於 `system_skills/pptgenjs/assets/templates/`，啟動此 skill 後即可從可用資源清單中看到路徑。

### 套用方式

在 `render_pptx` 中傳入 `template_path` 即可：

```
render_pptx(
  pptx_script="...",
  template_path="system_skills/pptgenjs/assets/templates/corporate.pptx",
  title="Q2 業績報告",
  slide_count=5
)
```

後端會自動保留模板的 `slideMasters/`、`slideLayouts/`、`theme/`，並將生成的投影片內容套入。

### 指定每頁的版面（Layout Hint）

在 `pptx_script` 末尾（`window.__pptxDone(prs)` 之前）設定 `window.__pptxLayoutHints`，值為每張投影片對應版面**名稱字串**的陣列，後端會套用對應的版面樣式：

```javascript
let prs = new PptxGenJS();
// ... 建立各頁投影片 ...
let slide1 = prs.addSlide();
let slide2 = prs.addSlide();
let slide3 = prs.addSlide();

// 必須在 __pptxDone 之前設定，順序與 addSlide 一致
window.__pptxLayoutHints = [
  "標題投影片",   // slide1：封面
  "空白",         // slide2：空白內容頁
  "標題及內容",   // slide3：結尾頁
];
window.__pptxDone(prs);
```

- 陣列長度不需與投影片數量完全一致，多餘的頁自動 fallback
- 某頁填 `null` 或空字串：該頁自動依位置判斷（第 1 張與最後 1 張套 title 類版面，其餘套 blank/obj 類）
- 填入不存在的名稱：自動 fallback 到位置判斷，不會報錯
- 未設定 `window.__pptxLayoutHints`：全部依位置自動判斷

### 可用版面名稱

**default.pptx**

| 版面名稱（`__layoutHint` 值） | 說明 |
|---|---|
| `標題投影片` | 封面頁 |
| `標題及內容` | 標題 + 內容區塊 |
| `章節標題` | 新章節標題頁 |
| `兩個內容` | 左右並排兩欄內容 |
| `比較` | 左右比較版面 |
| `只有標題` | 僅顯示標題 |
| `空白` | 全空白頁 |
| `含輔助字幕的內容` | 內容 + 輔助字幕 |
| `含輔助字幕的圖片` | 圖片 + 輔助字幕 |
| `全景圖片 (含輔助字幕)` | 全景圖片 + 輔助字幕 |
| `引述 (含輔助字幕)` | 引述文字 + 輔助字幕 |
| `名片` | 名片樣式 |
| `標題及直排文字` | 標題 + 直排文字 |
| `直排標題及文字` | 直排標題 + 文字 |

> **提示**：若不確定版面效果，可在生成後用 `read_file` 讀取 `artifacts/pptx_<id>_slide_001.png` 進行視覺確認，再針對性調整。

### 注意事項

- 若不指定 `template_path`，維持原有行為（使用 pptxgenjs 預設樣式，`__layoutHint` 無效）
- 使用者若在自己的 skill 目錄下有自訂模板，也可以指定該路徑
- **❌ 使用模板時不能設定 `slide.background`**（包括 `{ color: "..." }` 和 `{ path: "..." }`）。模板的每個 layout 已內建背景設計，slide 設 background 會覆蓋 layout 背景，導致模板視覺失效。

---

## 視覺檢查（跑版偵測）

`render_pptx` 執行後，後端會在對話的 `artifacts/` 目錄下產生每張投影片的預覽圖（PNG）。

**命名規則**：檔名使用後端回傳的 `pptx_id`，格式為：

```
artifacts/pptx_<id>_slide_001.png
artifacts/pptx_<id>_slide_002.png
...
```

`pptx_id` 會出現在 `render_pptx` 的回傳訊息中（格式：`[RENDER_PPTX_OK] pptx_id=pptx_a1b2c3d4`）。可直接用 `read_file` 開啟對應 PNG 進行視覺確認，無須使用者手動截圖：

```
read_file("artifacts/pptx_a1b2c3d4_slide_001.png")
```

當使用者回報**跑版、文字截斷、元素位置錯誤**等問題時，標準流程：

1. 從 `[RENDER_PPTX_OK]` 訊息取得 `pptx_id`
2. 呼叫 `read_file("artifacts/pptx_<id>_slide_NNN.png")` 確認版面
3. 根據圖片判斷問題後針對性修正腳本，重新呼叫 `render_pptx`

> 若不確定頁碼，可先用 `list_files("artifacts/")` 列出所有已生成的 PNG 檔名。

---

## 工作流程

1. 確認投影片數量、主題、需要呈現的資料
2. 若使用者希望套用企業模板，從可用資源清單中取得模板路徑
3. 規劃每張投影片的目的（封面 / 摘要 / 圖表 / 結尾）
4. 撰寫完整腳本，結尾呼叫 `window.__pptxDone(prs)`
5. 呼叫 `render_pptx(pptx_script=..., title=..., slide_count=N[, template_path=...])`
6. 回傳一句話說明簡報內容，不需逐張解說
7. 若使用者回報跑版問題，從 `[RENDER_PPTX_OK]` 取得 `pptx_id`，用 `read_file("artifacts/pptx_<id>_slide_NNN.png")` 進行視覺確認後修正
