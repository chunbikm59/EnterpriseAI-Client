// 範例 03: Bar Chart Options - Axis, DataLabel, Grid
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide03)
// 重點: 軸與格線樣式變化（catAxisHidden、valGridLine dash、barOverlapPct、displayUnit）

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_ACCENT = ["4472C4","ED7D31","FFC000","70AD47"];

const arrDataRegions = [
  { name: "Region 1", labels: ["May","June","July","August"], values: [26, 53, 100, 75] },
  { name: "Region 2", labels: ["May","June","July","August"], values: [43.5, 70.3, 90.1, 80.05] },
];
const arrDataHighVals = [
  { name: "California", labels: ["Apartment","Townhome","Duplex","House","Big House"], values: [2000, 2800, 3200, 4000, 5000] },
  { name: "Texas",      labels: ["Apartment","Townhome","Duplex","House","Big House"], values: [1400, 2000, 2500, 3000, 3800] },
];

let slide = prs.addSlide();

// TOP-LEFT: 橫條，valGridLine dash + catAxisHidden
let optsChartBar1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 3.0,
  barDir: "bar",
  plotArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_ACCENT,
  catAxisLabelColor: "CC0000",
  catAxisLabelFontFace: "Helvetica Neue",
  catAxisLabelFontSize: 14,
  catGridLine: { style: "none" },
  catAxisHidden: true,
  valGridLine: { color: "cc6699", style: "dash", size: 1 },
  valAxisLineColor: "44AA66",
  valAxisLineSize: 1,
  valAxisLineStyle: "dash",
  showLegend: true,
  showTitle: true,
  title: "catAxisHidden:true, valGridLine/valAxisLine:dash",
  titleColor: "a9a9a9",
  titleFontFace: "Helvetica Neue",
  titleFontSize: 11,
};
slide.addChart(prs.charts.BAR, arrDataRegions, optsChartBar1);

// TOP-RIGHT: 直條 + 隱藏軸 + dataLabel
let optsChartBar2 = {
  x: 7.0, y: 0.6, w: 6.0, h: 3.0,
  barDir: "col",
  plotArea: { fill: { color: "E1F1FF" } },
  dataBorder: { pt: 1, color: "F1F1F1" },
  dataLabelColor: "696969",
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 11,
  dataLabelPosition: "outEnd",
  dataLabelFormatCode: "#.0",
  showValue: true,
  catAxisHidden: true,
  catGridLine: { style: "none" },
  valAxisHidden: true,
  valAxisDisplayUnitLabel: true,
  valGridLine: { style: "none" },
  showLegend: true,
  legendPos: "b",
  showTitle: false,
};
slide.addChart(prs.charts.BAR, arrDataRegions, optsChartBar2);

// BTM-LEFT: 橫條 + barOverlapPct + 紅框 plotArea
let optsChartBar3 = {
  x: 0.5, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "F1F1F1" } },
  plotArea: { border: { pt: 3, color: "CF0909" }, fill: { color: "F1C1C1" } },
  barDir: "bar",
  barOverlapPct: -50,
  catAxisLabelColor: "CC0000",
  catAxisLabelFontFace: "Helvetica Neue",
  catAxisLabelFontSize: 10,
  catAxisOrientation: "maxMin",
  catAxisTitle: "Housing Type",
  catAxisTitleColor: "696969",
  catAxisTitleFontSize: 10,
  showCatAxisTitle: true,
  catGridLine: { color: "cc6699", style: "dash", size: 1 },
  valGridLine: { style: "none" },
  valAxisOrientation: "maxMin",
  valAxisHidden: true,
  valAxisDisplayUnitLabel: true,
  titleColor: "33CF22",
  titleFontFace: "Helvetica Neue",
  titleFontSize: 16,
  showTitle: true,
  title: "Sales by Region",
};
slide.addChart(prs.charts.BAR, arrDataHighVals, optsChartBar3);

// BTM-RIGHT: 直條 + 雙色 + valAxis 範圍
let optsChartBar4 = {
  x: 7.0, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "F1F1F1" } },
  plotArea: { fill: { color: "FFFFFF" } },
  barDir: "col",
  barGapWidthPct: 25,
  chartColors: ["0088CC", "99FFCC"],
  chartColorsOpacity: 50,
  valAxisMinVal: 1000,
  valAxisMaxVal: 5000,
  catAxisLabelColor: "0000CC",
  catAxisLabelFontFace: "Times",
  catAxisLabelFontSize: 11,
  catAxisLabelFrequency: 1,
  catAxisOrientation: "minMax",
  dataBorder: { pt: 1, color: "F1F1F1" },
  dataLabelColor: "696969",
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 10,
  dataLabelPosition: "inEnd",
  showValue: true,
  valAxisHidden: true,
  catAxisTitle: "Housing Type",
  showCatAxisTitle: true,
  showLegend: false,
  showTitle: false,
};
slide.addChart(prs.charts.BAR, arrDataHighVals, optsChartBar4);

window.__pptxDone(prs);
