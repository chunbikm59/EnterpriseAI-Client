// 範例 14: XY Scatter Chart
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide14)
// 重點: 散佈圖 SCATTER（首個 series 為 X 軸值）+ dataLabel + lineSmooth + dataLabelFormatScatter

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_RYGU = ["FF0000","F2AF00","7AB800","4472C4","672C7E","A9A9A9"];

// SCATTER 資料格式：第 1 個物件是 X 軸值，後續物件是 Y 系列
const arrDataScatter1 = [
  { name: "X-Axis",    values: [0, 1, 2, 3, 4, 5] },
  { name: "Y-Value 1", values: [90, 80, 70, 85, 75, 92], labels: ["Jan","Feb","Mar","Apr","May","Jun"] },
  { name: "Y-Value 2", values: [21, 32, 40, 49, 31, 29], labels: ["Jan","Feb","Mar","Apr","May","Jun"] },
];
const arrDataScatter2 = [
  { name: "X-Axis",   values: [1, 2, 3, 4, 5, 6] },
  { name: "Airplane", values: [33, 20, 51, 65, 71, 75] },
  { name: "Train",    values: [99, 88, 77, 89, 99, 99] },
  { name: "Bus",      values: [21, 22, 25, 49, 59, 69] },
];
const arrDataScatterLabels = [
  { name: "X-Axis",    values: [1, 10, 20, 30, 40, 50] },
  { name: "Y-Value 1", values: [11, 23, 31, 45, 47, 35], labels: ["Red 1","Red 2","Red 3","Red 4","Red 5","Red 6"] },
  { name: "Y-Value 2", values: [21, 38, 47, 59, 51, 25], labels: ["Blue 1","Blue 2","Blue 3","Blue 4","Blue 5","Blue 6"] },
];

let slide = prs.addSlide();

// TOP-LEFT: 點散佈（lineSize: 0）+ 軸標題 + dataLabel
let optsChartScat1 = {
  x: 0.5, y: 0.6, w: "45%", h: 3,
  valAxisTitle: "Renters",
  valAxisTitleColor: "428442",
  valAxisTitleFontSize: 14,
  showValAxisTitle: true,
  lineSize: 0,
  catAxisTitle: "Last 6 Months",
  catAxisTitleColor: "428442",
  catAxisTitleFontSize: 14,
  showCatAxisTitle: true,
  showLabel: true, // 必須 true 才會顯示 labels
  dataLabelPosition: "b", // 't'|'b'|'l'|'r'|'ctr'
};
slide.addChart(prs.charts.SCATTER, arrDataScatter1, optsChartScat1);

// TOP-RIGHT: 連線 + lineSmooth + 半透明
let optsChartScat2 = {
  x: 7.0, y: 0.6, w: "45%", h: 3,
  plotArea: { fill: { color: "F1F1F1" } },
  showLegend: true,
  legendPos: "b",
  lineSize: 8,
  lineSmooth: true,
  lineDataSymbolSize: 12,
  lineDataSymbolLineColor: "FFFFFF",
  chartColors: COLORS_RYGU,
  chartColorsOpacity: 25,
};
slide.addChart(prs.charts.SCATTER, arrDataScatter2, optsChartScat2);

// BTM-LEFT: 自訂 dataLabel（dataLabelFormatScatter: "custom"）
let optsChartScat3 = {
  x: 0.5, y: 4.0, w: "45%", h: 3,
  plotArea: { fill: { color: "F2F9FC" } },
  showLegend: true,
  chartColors: ["FF0000", "0088CC"],
  showValAxisTitle: false,
  lineSize: 0,
  catAxisTitle: "Data Point Labels",
  catAxisTitleColor: "0088CC",
  catAxisTitleFontSize: 14,
  showCatAxisTitle: false,
  showLabel: true,
  dataLabelPosition: "r",
  dataLabelFormatScatter: "custom", // 'custom'(default) | 'customXY' | 'XY'
};
slide.addChart(prs.charts.SCATTER, arrDataScatterLabels, optsChartScat3);

// BTM-RIGHT: 預設樣式（極簡）
slide.addChart(prs.charts.SCATTER, arrDataScatter2, { x: 7.0, y: 4.0, w: "45%", h: 3 });

window.__pptxDone(prs);
