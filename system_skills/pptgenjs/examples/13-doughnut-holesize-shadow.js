// 範例 13: Doughnut Chart - holeSize and Shadow
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide13)
// 重點: 甜甜圈圖 (DOUGHNUT) holeSize 控制中空大小、inner shadow 內陰影

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_RYGU = ["FF0000","F2AF00","7AB800","4472C4","672C7E","A9A9A9"];
const COLORS_VIVID = ["ff595e","F38940","ffca3a","8ac926","1982c4","5FBDE1","6a4c93"];

const dataChartPieStat = [
  { name: "Project Status", labels: ["Red","Yellow","Green","Complete","Cancelled","Unknown"], values: [25, 5, 5, 5, 5, 5] },
];
const dataChartPieLocs = [
  { name: "Sales by Location", labels: ["CN","DE","GB","MX","JP","IN","US"], values: [69, 35, 40, 85, 38, 99, 101] },
];

let slide = prs.addSlide();

// LEFT: 甜甜圈 holeSize 70（中空大）+ showPercent + legend bottom
let optsChartPie1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 6.4,
  chartArea: { fill: { color: "F1F1F1" } },
  holeSize: 70,
  showLabel: false,
  showValue: false,
  showPercent: true,
  showLegend: true,
  legendPos: "b",
  chartColors: COLORS_RYGU,
  dataBorder: { pt: "2", color: "F1F1F1" },
  dataLabelColor: "FFFFFF",
  dataLabelFontSize: 14,
  showTitle: false,
  title: "Project Status",
  titleColor: "33CF22",
  titleFontFace: "Helvetica Neue",
  titleFontSize: 24,
};
slide.addChart(prs.charts.DOUGHNUT, dataChartPieStat, optsChartPie1);

// RIGHT: 深色背景 + 內陰影 + showLabel + showValue + showPercent
let optsChartPie2 = {
  x: 6.83, y: 0.6, w: 6.0, h: 6.4,
  chartArea: { fill: { color: "404040" } },
  chartColors: COLORS_VIVID,
  dataBorder: { pt: "1", color: "F1F1F1" },
  dataLabelColor: "FFFFFF",
  showLabel: true,
  showValue: true,
  showPercent: true,
  showLegend: true,
  legendPos: "b",
  legendColor: "F1F1F1",
  legendFontSize: 12,
  showTitle: false,
  title: "Resource Totals by Location",
  shadow: {
    type: "inner",
    offset: 20,
    blur: 20,
  },
};
slide.addChart(prs.charts.DOUGHNUT, dataChartPieLocs, optsChartPie2);

window.__pptxDone(prs);
