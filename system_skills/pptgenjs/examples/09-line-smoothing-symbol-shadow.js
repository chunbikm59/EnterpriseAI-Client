// 範例 09: Line Chart - Smoothing, Line Size, Symbol Size, Shadow
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide09)
// 重點: 4 種折線變化（lineSmooth、lineSize 不同粗細、lineDataSymbolSize、shadow 陰影效果）

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_RYGU = ["FF0000","F2AF00","7AB800","4472C4","672C7E","A9A9A9"];

const arrDataLineStat = [
  { name: "Red",      labels: ["Q1","Q2","Q3","Q4"], values: [1, 3, 5, 7] },
  { name: "Yellow",   labels: ["Q1","Q2","Q3","Q4"], values: [5, 26, 32, 30] },
  { name: "Green",    labels: ["Q1","Q2","Q3","Q4"], values: [7, 52, 18, 67] },
  { name: "Complete", labels: ["Q1","Q2","Q3","Q4"], values: [3, 5, 17, 1] },
];

let slide = prs.addSlide();

// TOP-LEFT: lineSize 8 + lineSmooth + legend top
let optsChartLine1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_RYGU,
  lineSize: 8,
  lineSmooth: true,
  showLegend: true,
  legendPos: "t",
  catAxisLabelPos: "high",
};
slide.addChart(prs.charts.LINE, arrDataLineStat, optsChartLine1);

// TOP-RIGHT: lineSize 16（極粗）+ legend right
let optsChartLine2 = {
  x: 7.0, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_RYGU,
  lineSize: 16,
  lineSmooth: true,
  showLegend: true,
  legendPos: "r",
};
slide.addChart(prs.charts.LINE, arrDataLineStat, optsChartLine2);

// BTM-LEFT: lineDataSymbolSize 10 + 無陰影 + legend left
let optsChartLine3 = {
  x: 0.5, y: 4.0, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_RYGU,
  lineDataSymbolSize: 10,
  shadow: { type: "none" },
  //displayBlanksAs: 'gap',
  showLegend: true,
  legendPos: "l",
};
slide.addChart(prs.charts.LINE, arrDataLineStat, optsChartLine3);

// BTM-RIGHT: 紅色外陰影 + lineDataSymbolSize 20
let shadowOpts = { type: "outer", color: "cd0011", blur: 3, offset: 12, angle: 75, opacity: 0.8 };
let optsChartLine4 = {
  x: 7.0, y: 4.0, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_RYGU,
  lineDataSymbolSize: 20,
  shadow: shadowOpts,
  showLegend: true,
  legendPos: "b",
};
slide.addChart(prs.charts.LINE, arrDataLineStat, optsChartLine4);

window.__pptxDone(prs);
