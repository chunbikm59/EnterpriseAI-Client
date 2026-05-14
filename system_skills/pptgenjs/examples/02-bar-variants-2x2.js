// 範例 02: Bar Chart Various Designs (2x2 grid)
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide02)
// 重點: 2×2 grid 對比 bar/col 各種樣式（chartArea/plotArea 配色、tickMark、dataLabel、border）

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_ACCENT = ["4472C4","ED7D31","FFC000","70AD47"];
const COLORS_SPECTRUM = ["56B4E4","126CB0","672C7E","E92A31","F06826","E9AF1F","51B747","189247"];

const arrDataRegions = [
  { name: "Region 1", labels: ["May","June","July","August"], values: [26, 53, 100, 75] },
  { name: "Region 2", labels: ["May","June","July","August"], values: [43.5, 70.3, 90.1, 80.05] },
];
const arrDataSersCats = [
  { name: "Series 1", labels: ["Category 1","Category 2","Category 3","Category 4"], values: [4.3, 2.5, 3.5, 4.5] },
  { name: "Series 2", labels: ["Category 1","Category 2","Category 3","Category 4"], values: [2.4, 4.4, 1.8, 2.8] },
  { name: "Series 3", labels: ["Category 1","Category 2","Category 3","Category 4"], values: [2, 2, 3, 5] },
];
const dataChartBar3Series = [
  { name: "Americas", labels: ["Phones","Laptops","Tablets","Desktops"], values: [1400,2000,2500,3000] },
  { name: "Asia",     labels: ["Phones","Laptops","Tablets","Desktops"], values: [2000,2800,3200,5000] },
  { name: "Europe",   labels: ["Phones","Laptops","Tablets","Desktops"], values: [1400,2000,3000,3800] },
];

let slide = prs.addSlide();

// TOP-LEFT: 橫條（H/bar）
let optsChartBar1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { border: { color: COLORS_SPECTRUM[0], pt: 1 } },
  plotArea: { fill: { color: "DAE3F3" } },
  chartColors: COLORS_SPECTRUM,
  objectName: "bar chart (top L)",
  altText: "this is the alt text content",
  barDir: "bar",
  catAxisLabelColor: COLORS_ACCENT[0],
  catAxisLabelFontFace: "Helvetica Neue",
  catAxisLabelFontSize: 12,
  catAxisOrientation: "maxMin",
  catAxisMajorTickMark: "in",
  catAxisMinorTickMark: "cross",
  valAxisMajorTickMark: "cross",
  valAxisMinorTickMark: "out",
};
slide.addChart(prs.charts.BAR, arrDataSersCats, optsChartBar1);

// TOP-RIGHT: 直條（V/col），含 dataLabel
let optsChartBar2 = {
  x: 7.0, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { border: { color: COLORS_SPECTRUM[0], pt: 1 } },
  plotArea: { fill: { color: "DAE3F3" } },
  chartColors: COLORS_SPECTRUM,
  objectName: "bar chart (top R)",
  barDir: "col",
  catAxisLabelColor: COLORS_ACCENT[0],
  catAxisLabelFontFace: "Arial",
  catAxisLabelFontSize: 11,
  catAxisOrientation: "minMax",
  catAxisMajorTickMark: "none",
  catAxisMinorTickMark: "none",
  dataBorder: { pt: 1, color: "F1F1F1" },
  dataLabelColor: COLORS_ACCENT[0],
  dataLabelFontFace: "Courier",
  dataLabelFontSize: 10,
  dataLabelPosition: "outEnd",
  dataLabelFormatCode: "#.0",
  showValue: true,
  valAxisLabelColor: COLORS_ACCENT[0],
  valAxisOrientation: "maxMin",
  valAxisMajorTickMark: "none",
  valAxisMinorTickMark: "none",
  showLegend: false,
  showTitle: false,
};
slide.addChart(prs.charts.BAR, arrDataRegions, optsChartBar2);

// BTM-LEFT: 橫條 + 標題 + Legend
let optsChartBar3 = {
  x: 0.5, y: 3.8, w: 6.0, h: 3.5,
  barDir: "bar",
  chartArea: { fill: { color: "F1F1F1" }, border: { color: "A5A5A5", pt: 2 } },
  plotArea: { fill: { color: "F2F9FC" } },
  catAxisLabelColor: "CC0000",
  catAxisLabelFontFace: "Helvetica Neue",
  catAxisLabelFontSize: 14,
  catAxisOrientation: "minMax",
  titleColor: "33CF22",
  titleFontFace: "Helvetica Neue",
  titleFontSize: 16,
  showTitle: true,
  title: "Sales by Region",
};
slide.addChart(prs.charts.BAR, dataChartBar3Series, optsChartBar3);

// BTM-RIGHT: 直條 + 透明度 + 標題
let optsChartBar4 = {
  x: 7.0, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "F1F1F1" } },
  plotArea: { fill: { color: "404040" } },
  barDir: "col",
  barGapWidthPct: 25,
  chartColors: COLORS_ACCENT,
  chartColorsOpacity: 50,
  catAxisLabelColor: COLORS_ACCENT[0],
  catAxisLabelFontFace: "Calibri",
  catAxisLabelFontSize: 11,
  catAxisOrientation: "maxMin",
  valAxisMaxVal: 5000,
  valAxisLabelColor: COLORS_ACCENT[0],
  dataBorder: { pt: 1, color: "4472C4" },
  dataLabelColor: "FFFFFF",
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 10,
  dataLabelPosition: "inEnd",
  showValue: true,
  showLegend: false,
  legendPos: "b",
  legendColor: COLORS_ACCENT[1],
  showTitle: true,
  title: "Device Prices",
  titleColor: COLORS_ACCENT[0],
};
slide.addChart(prs.charts.BAR, dataChartBar3Series, optsChartBar4);

window.__pptxDone(prs);
