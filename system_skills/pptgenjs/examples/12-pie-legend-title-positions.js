// 範例 12: Pie Chart - Legend and Title Positions
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide12)
// 重點: 6 個圓餅展示 legendPos 各種位置（l/t/b）、showLabel/showValue/showPercent 組合、dataLabelPosition: "bestFit"

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_RYGU = ["FF0000","F2AF00","7AB800","4472C4","672C7E","A9A9A9"];
const COLORS_SPECTRUM = ["56B4E4","126CB0","672C7E","E92A31","F06826","E9AF1F","51B747","189247"];
const COLORS_CHART = ["003f5c","0077b6","084c61","177e89","3066be","00a9b5","58508d","bc5090","db3a34","ff6361","ffa600"];

const dataChartPieStat = [
  { name: "Project Status", labels: ["Red","Yellow","Green","Complete","Cancelled","Unknown"], values: [25, 5, 5, 5, 5, 5] },
];
const dataChartPieLocs = [
  { name: "Sales by Location", labels: ["CN","DE","GB","MX","JP","IN","US"], values: [69, 35, 40, 85, 38, 99, 101] },
];

let slide = prs.addSlide();

// TOP-LEFT: legend left + showLeaderLines + bestFit
slide.addChart(prs.charts.PIE, dataChartPieStat, {
  x: 0.5, y: 0.6, w: 4.0, h: 3.2,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_RYGU,
  dataBorder: { pt: 2, color: "F1F1F1" },
  legendPos: "l",
  legendFontFace: "Courier New",
  showLegend: true,
  showLeaderLines: true,
  showPercent: false,
  showValue: true,
  dataLabelColor: "FFFFFF",
  dataLabelFontSize: 14,
  dataLabelPosition: "bestFit", // 'bestFit' | 'outEnd' | 'inEnd' | 'ctr'
});

// TOP-MIDDLE: legend top + showPercent
slide.addChart(prs.charts.PIE, dataChartPieStat, {
  x: 4.67, y: 0.6, w: 4.0, h: 3.2,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_SPECTRUM,
  dataBorder: { pt: 1, color: "404040" },
  dataLabelColor: "f2f9fc",
  showPercent: true,
  showLegend: true,
  legendPos: "t",
});

// TOP-RIGHT: titleAlign right + titlePos {0,0}
slide.addChart(prs.charts.PIE, dataChartPieLocs, {
  x: 8.83, y: 0.6, w: 4.0, h: 3.2,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_SPECTRUM,
  dataBorder: { pt: "1", color: "F1F1F1" },
  showLegend: true,
  showPercent: true,
  legendPos: "t",
  legendFontSize: 14,
  showLeaderLines: true,
  showTitle: true,
  title: "Title Position {0,0}",
  titleAlign: "right",
  titlePos: { x: 0, y: 0 },
});

// BTM-LEFT: showValue + showLabel + showPercent 全開
slide.addChart(prs.charts.PIE, dataChartPieLocs, {
  x: 0.5, y: 4.0, w: 4.0, h: 3.2,
  chartArea: { fill: { color: "F1F1F1" } },
  chartColors: COLORS_CHART,
  dataBorder: { pt: "1", color: "F1F1F1" },
  showValue: true,
  showLabel: true,
  showPercent: true,
  dataLabelColor: "F1F1F1",
  dataLabelFontSize: 10,
});

// BTM-MIDDLE: legend bottom
slide.addChart(prs.charts.PIE, dataChartPieLocs, {
  x: 4.67, y: 4.0, w: 4.0, h: 3.2,
  chartArea: { fill: { color: "F1F1F1" } },
  dataBorder: { pt: "1", color: "F1F1F1" },
  chartColors: COLORS_SPECTRUM,
  dataLabelColor: "F1F1F1",
  showPercent: true,
  showLegend: true,
  legendPos: "b",
});

// BTM-RIGHT: title + legend + firstSliceAng 旋轉起始角度
slide.addChart(prs.charts.PIE, dataChartPieLocs, {
  x: 8.83, y: 4.0, w: 4.0, h: 3.2,
  chartArea: { fill: { color: "F1F1F1" } },
  dataBorder: { pt: "1", color: "F1F1F1" },
  showPercent: true,
  showLegend: true,
  legendPos: "b",
  showTitle: true,
  title: "Title & Legend",
  firstSliceAng: 90,
});

window.__pptxDone(prs);
