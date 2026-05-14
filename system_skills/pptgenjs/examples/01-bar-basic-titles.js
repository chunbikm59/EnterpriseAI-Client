// 範例 01: Bar Chart with Chart Title and Cat/Val Axis Title
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide01)
// 重點: 單張 8 系列堆疊直條圖，示範完整的標題、類別軸標題、數值軸標題設定

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_CHART = ["003f5c","0077b6","084c61","177e89","3066be","00a9b5","58508d","bc5090","db3a34","ff6361","ffa600"];
const COLORS_ACCENT = ["4472C4","ED7D31","FFC000","70AD47"];

const dataChartBar8Series = [
  { name: "Strategy 1", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [100,101,140,70,54,25,100] },
  { name: "Strategy 2", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [105,140,144,152,35,100,44] },
  { name: "Strategy 3", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [120,80,160,144,20,180,60] },
  { name: "Strategy 4", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [90,79,162,170,99,79,16] },
  { name: "Strategy 5", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [118,99,137,20,181,159,13] },
  { name: "Strategy 6", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [18,199,117,120,131,109,43] },
  { name: "Strategy 7", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [92,75,127,120,21,169,33] },
  { name: "Strategy 8", labels: ["Product A","Product B","Product C","Product D","Product E","Product F","Product G"], values: [118,99,137,20,181,159,13] },
];

let slide = prs.addSlide();

let optsChart = {
  x: 0.5, y: 0.5, w: "90%", h: "90%",
  barDir: "col",
  barGrouping: "stacked",
  chartColors: COLORS_CHART,
  invertedColors: ["C0504D"],
  showLegend: true,
  //
  showTitle: true,
  title: "Chart Title",
  titleFontFace: "Helvetica Neue Thin",
  titleFontSize: 24,
  titleColor: COLORS_ACCENT[0],
  titlePos: { x: 1.5, y: 0 },
  //titleRotate: 10,
  //
  showCatAxisTitle: true,
  catAxisLabelColor: COLORS_ACCENT[1],
  catAxisTitleColor: COLORS_ACCENT[1],
  catAxisTitle: "Cat Axis Title",
  catAxisTitleFontSize: 14,
  //
  showValAxisTitle: true,
  valAxisLabelColor: COLORS_ACCENT[2],
  valAxisTitleColor: COLORS_ACCENT[2],
  valAxisTitle: "Val Axis Title",
  valAxisTitleFontSize: 14,
};

slide.addChart(prs.charts.BAR, dataChartBar8Series, optsChart);

window.__pptxDone(prs);
