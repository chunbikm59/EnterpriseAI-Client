// 範例 06: 3D Bar Chart
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide06)
// 重點: 3D 直條圖 4 種形狀（box 預設、cylinder、pyramid、coneToMax）+ v3DRotX/Y 旋轉

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_ACCENT = ["4472C4","ED7D31","FFC000","70AD47"];
const COLORS_SPECTRUM = ["56B4E4","126CB0","672C7E","E92A31","F06826","E9AF1F","51B747","189247"];

const arrDataRegions = [
  { name: "Region 1", labels: ["Q1","Q2","Q3","Q4"], values: [26, 53, 80, 75] },
  { name: "Region 2", labels: ["Q1","Q2","Q3","Q4"], values: [43.5, 70.3, 90.01, 80.05] },
];

let slide = prs.addSlide();

// TOP-LEFT: 3D 橫條，預設 box 形狀
let optsChartBar1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1", transparency: 50 } },
  barDir: "bar",
  barGapWidthPct: 25,
  chartColors: COLORS_SPECTRUM,
  chartColorsOpacity: 80,
  v3DRotX: 20,
  v3DRotY: 10,
  v3DRAngAx: false,
  catAxisLabelColor: COLORS_SPECTRUM[1],
  catAxisLineColor: COLORS_SPECTRUM[1],
  catAxisLabelFontFace: "Arial",
  catAxisLabelFontSize: 10,
  catAxisOrientation: "maxMin",
  serAxisLabelFontFace: "Arial",
  serAxisLabelFontSize: 10,
  serAxisLabelColor: COLORS_SPECTRUM[1],
  serAxisLineColor: COLORS_SPECTRUM[1],
  valAxisLabelColor: COLORS_SPECTRUM[0],
  valAxisLineColor: COLORS_SPECTRUM[0],
  valAxisLabelFontSize: 10,
};
slide.addChart(prs.charts.BAR3D, arrDataRegions, optsChartBar1);

// TOP-RIGHT: 3D 直條，圓柱形 (cylinder)
let optsChartBar2 = {
  x: 7.0, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "F1F1F1", transparency: 50 } },
  chartColors: COLORS_SPECTRUM,
  barDir: "col",
  bar3DShape: "cylinder",
  v3DRotX: 10,
  v3DRotY: 20,
  v3DRAngAx: false,
  catAxisLabelColor: "0000CC",
  catAxisLabelFontFace: "Courier",
  catAxisLabelFontSize: 12,
  dataLabelColor: "000000",
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 11,
  dataLabelPosition: "outEnd",
  dataLabelFormatCode: "#.0",
  dataLabelBkgrdColors: true,
  showValue: true,
};
slide.addChart(prs.charts.BAR3D, arrDataRegions, optsChartBar2);

// BTM-LEFT: 3D 堆疊直條，金字塔形 (pyramid)
let optsChartBar3 = {
  x: 0.5, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "F1F1F1", transparency: 50 } },
  chartColors: COLORS_ACCENT,
  barDir: "col",
  bar3DShape: "pyramid",
  barGrouping: "stacked",
  v3DRAngAx: true,
  catAxisLabelFontFace: "Arial",
  catAxisLabelFontSize: 10,
  showValue: true,
  dataLabelBkgrdColors: true,
  showTitle: true,
  title: "Sales by Region",
  titleFontFace: "Helvetica Neue Thin",
  titleFontSize: 18,
  titleColor: COLORS_ACCENT[0],
};
slide.addChart(prs.charts.BAR3D, arrDataRegions, optsChartBar3);

// BTM-RIGHT: 3D 直條，coneToMax 圓錐
let optsChartBar4 = {
  x: 7.0, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "F1F1F1", transparency: 50 } },
  chartColors: COLORS_ACCENT,
  barDir: "col",
  bar3DShape: "coneToMax",
  v3DRAngAx: true,
  catAxisLabelColor: COLORS_ACCENT[0],
  catAxisLabelFontSize: 11,
  catAxisOrientation: "minMax",
  serAxisLabelFontFace: "Helvetica Neue Thin",
  serAxisLabelColor: COLORS_ACCENT[0],
  dataBorder: { pt: 1, color: "F1F1F1" },
  dataLabelColor: "696969",
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 10,
  dataLabelPosition: "ctr",
};
slide.addChart(prs.charts.BAR3D, arrDataRegions, optsChartBar4);

window.__pptxDone(prs);
