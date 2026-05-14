// 範例 17: Multi-Level Category Axes (2 Levels)
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide17)
// 重點: 多層類別軸 catAxisMultiLevelLabels: true，labels 改為 2D 陣列（第 1 維是細項、第 2 維是群組）
//       同樣資料展示 4 種圖表類型（AREA、BAR、BAR3D、LINE）

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

// labels 為 2D 陣列：
//   第 0 列為實際細項標籤
//   第 1 列為群組標籤（在細項下方加一層分組）
//   群組標籤後面填 "" 代表該欄沿用前一個非空的群組
const arrDataLabels = [
  ["Gear","Bearing","Motor","Switch","Plug","Cord","Fuse","Bulb","Pump","Leak","Seals"],
  ["Mechanical","","","Electrical","","","","","Hydraulic","",""],
];
const arrDataRegions = [
  { name: "Mechanical", labels: arrDataLabels, values: [11, 8, 3, 0, 0, 0, 0, 0, 0, 0, 0] },
  { name: "Electrical", labels: arrDataLabels, values: [0, 0, 0, 19, 12, 11, 3, 2, 0, 0, 0] },
  { name: "Hydraulic",  labels: arrDataLabels, values: [0, 0, 0, 0, 0, 0, 0, 0, 4, 3, 1] },
];

let slide = prs.addSlide();

const opts1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  catAxisMultiLevelLabels: true,
  catAxisLabelFontFace: "Helvetica Neue Thin",
};

const opts2 = {
  x: 6.8, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  catAxisMultiLevelLabels: true,
  catAxisLabelFontFace: "Helvetica Neue Thin",
  barDir: "col",
  barGapWidthPct: 0,
};

const opts3 = {
  x: 0.5, y: 4.0, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  catAxisMultiLevelLabels: true,
  barDir: "col",
  v3DRAngAx: true,
};

const opts4 = {
  x: 6.8, y: 4.0, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  catAxisMultiLevelLabels: true,
};

slide.addChart(prs.charts.AREA,  arrDataRegions, opts1);
slide.addChart(prs.charts.BAR,   arrDataRegions, opts2);
slide.addChart(prs.charts.BAR3D, arrDataRegions, opts3);
slide.addChart(prs.charts.LINE,  arrDataRegions, opts4);

window.__pptxDone(prs);
