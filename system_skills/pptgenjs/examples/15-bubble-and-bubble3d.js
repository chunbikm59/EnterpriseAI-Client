// 範例 15: Bubble Chart and Bubble3D
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide15)
// 重點: 氣泡圖（BUBBLE / BUBBLE3D），系列除了 values 還要有 sizes 控制氣泡大小

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_ACCENT = ["4472C4","ED7D31","FFC000","70AD47"];
const COLORS_RYGU = ["FF0000","F2AF00","7AB800","4472C4","672C7E","A9A9A9"];

// BUBBLE 資料格式：第 1 個物件是 X 軸；後續物件除了 values 還要有 sizes
const arrDataBubble1 = [
  { name: "X-Axis",    values: [0.3, 0.6, 0.9, 1.2, 1.5, 1.7] },
  { name: "Y-Value 1", values: [1.3, 9, 7.5, 2.5, 7.5, 3], sizes: [1, 4, 2, 3, 7, 4] },
  { name: "Y-Value 2", values: [5.0, 3, 2.0, 7.0, 2.0, 9], sizes: [9, 7, 9, 2, 4, 8] },
];
const arrDataBubble2 = [
  { name: "X-Axis",   values: [1, 2, 3, 4, 5, 6] },
  { name: "Airplane", values: [33, 20, 51, 65, 71, 75], sizes: [10, 10, 12, 12, 15, 20] },
  { name: "Train",    values: [99, 88, 77, 89, 99, 99], sizes: [20, 20, 22, 22, 25, 30] },
  { name: "Bus",      values: [21, 25, 32, 49, 59, 69], sizes: [11, 11, 13, 13, 16, 21] },
];

let slide = prs.addSlide();

// TOP-LEFT: 標準氣泡圖 + 顯示系列名 + leaderLine
let optsChartBubble1 = {
  x: 0.5, y: 0.6, w: "45%", h: 3,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_ACCENT,
  chartColorsOpacity: 40,
  dataBorder: { pt: 1, color: "FFFFFF" },
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 10,
  dataLabelColor: "363636",
  dataLabelPosition: "r",
  showSerName: true,
  showLeaderLines: true,
};
slide.addChart(prs.charts.BUBBLE, arrDataBubble1, optsChartBubble1);

// TOP-RIGHT: 半透明氣泡 + lineSmooth + legend
let optsChartBubble2 = {
  x: 7.0, y: 0.6, w: "45%", h: 3,
  plotArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_RYGU,
  chartColorsOpacity: 25,
  showLegend: true,
  legendPos: "b",
  lineSize: 8,
  lineSmooth: true,
  lineDataSymbolSize: 12,
  lineDataSymbolLineColor: "FFFFFF",
};
slide.addChart(prs.charts.BUBBLE, arrDataBubble2, optsChartBubble2);

// BTM-LEFT: 深色背景氣泡 + showValue
let optsChartBubble3 = {
  x: 0.5, y: 4.0, w: "45%", h: 3,
  chartArea: { fill: { color: "404040" } },
  plotArea: { fill: { color: "202020" } },
  catAxisLabelColor: "F1F1F1",
  catAxisLabelFontSize: 10,
  catAxisOrientation: "maxMin",
  showCatAxisTitle: false,
  valAxisLabelColor: "F1F1F1",
  valAxisLabelFontSize: 10,
  valAxisMinVal: 0,
  valAxisOrientation: "maxMin",
  showValAxisTitle: false,
  dataBorder: { pt: 2, color: "e1e1e1" },
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 10,
  dataLabelColor: "e1e1e1",
  showValue: true,
};
slide.addChart(prs.charts.BUBBLE, arrDataBubble1, optsChartBubble3);

// BTM-RIGHT: BUBBLE3D 立體氣泡
let optsChartBubble4 = { x: 7.0, y: 4.0, w: "45%", h: 3, lineSize: 0, chartColors: COLORS_RYGU };
slide.addChart(prs.charts.BUBBLE3D, arrDataBubble2, optsChartBubble4);

window.__pptxDone(prs);
