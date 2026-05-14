// 範例 16: Radar Chart - 3 Styles (standard / marker / filled)
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide16)
// 重點: 雷達圖三種樣式（radarStyle: "standard" | "marker" | "filled"）+ 細節控制（marker 顏色/大小/邊框、valAxis 線寬）

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_RYGU = ["FF0000","F2AF00","7AB800","4472C4","672C7E","A9A9A9"];

const arrDataRegions = [
  { name: "Region 1", labels: ["Jun","Jul","Aug","Sep"], values: [20, 18, 15, 10] },
];
const arrDataStudents = [
  { name: "Student 1", labels: ["Logic","Coding","Results","Comments","Runtime"], values: [3, 1, 3, 3, 4] },
  { name: "Student 2", labels: ["Logic","Coding","Results","Comments","Runtime"], values: [1, 2, 2, 3, 2] },
  { name: "Student 3", labels: ["Logic","Coding","Results","Comments","Runtime"], values: [2, 3, 3, 4, 3] },
];

let slide = prs.addSlide();

// TOP-ROW: 三種 radarStyle 對比 ---------------------------------------
// TOP-L: standard
let optsChartRadar1 = {
  x: 0.5, y: 0.6, w: 4.0, h: 3.0,
  chartArea: { fill: { color: "F9F9F9" } },
  radarStyle: "standard",
  showTitle: true,
  titleColor: "7F7F7F",
  titleFontFace: "Segoe UI",
  titleFontSize: 12,
  title: "radarStyle: 'standard'",
  lineDataSymbol: "none",
};
slide.addChart(prs.charts.RADAR, arrDataRegions, optsChartRadar1);

// TOP-C: marker
let optsChartRadar2 = {
  x: 4.65, y: 0.6, w: 4.0, h: 3.0,
  chartArea: { fill: { color: "F9F9F9" } },
  radarStyle: "marker",
  showTitle: true,
  titleColor: "7F7F7F",
  titleFontFace: "Segoe UI",
  titleFontSize: 12,
  title: "radarStyle: 'marker'",
};
slide.addChart(prs.charts.RADAR, arrDataRegions, optsChartRadar2);

// TOP-R: filled
let optsChartRadar3 = {
  x: 8.8, y: 0.6, w: 4.0, h: 3.0,
  chartArea: { fill: { color: "F9F9F9" } },
  radarStyle: "filled",
  showTitle: true,
  titleColor: "7F7F7F",
  titleFontFace: "Segoe UI",
  titleFontSize: 12,
  title: "radarStyle: 'filled'",
};
slide.addChart(prs.charts.RADAR, arrDataRegions, optsChartRadar3);

// BTM-ROW: marker/line/filled 進階控制 ---------------------------------
// BTM-L: marker 樣式細節控制
let optsChartRadar10 = {
  x: 0.5, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "F1F1F1" } },
  radarStyle: "marker",
  catAxisLabelColor: "0088CC",
  catAxisLabelFontFace: "Courier",
  catAxisLabelFontSize: 11,
  chartColors: COLORS_RYGU,
  lineDataSymbol: "diamond",       // 標記類型 ('circle'|'dash'|'diamond'|'dot'|'none'|'square'|'triangle')
  lineDataSymbolLineColor: "0088CC", // 標記邊框色
  lineDataSymbolLineSize: 2,
  lineDataSymbolSize: 12,
  lineSize: 3,
  valAxisLineColor: "D9D9D9",      // valAxis 是雷達中心的 N-S、W-E 主軸線
  valAxisLineSize: 2,
  showLegend: true,
  legendPos: "l",
  showTitle: true,
  title: "Line/Marker Options",
  titleColor: "7F7F7F",
  titleFontFace: "Helvetica Neue",
  titleFontSize: 12,
};
slide.addChart(prs.charts.RADAR, arrDataStudents, optsChartRadar10);

// BTM-R: filled 樣式
let optsChartRadar11 = {
  x: 6.83, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "F1F1F1" } },
  radarStyle: "filled",
  chartColors: COLORS_RYGU,
  chartColorsOpacity: 25,
  catAxisLabelColor: "404040",
  catAxisLabelFontFace: "Segoe UI",
  catAxisLabelFontSize: 10,
  catAxisLineShow: false,
  lineDataSymbolSize: 2,
  lineSize: 1,
  valAxisLabelFontFace: "Segoe UI",
  valAxisLabelFontSize: 10,
  showLegend: true,
  legendPos: "r",
  legendColor: "404040",
  titleColor: "404040",
  titleFontFace: "Helvetica Neue",
  titleFontSize: 12,
  showTitle: true,
  title: "Filled/Axis Options",
};
slide.addChart(prs.charts.RADAR, arrDataStudents, optsChartRadar11);

window.__pptxDone(prs);
