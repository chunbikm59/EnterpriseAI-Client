// 範例 11: Area Chart and Stacked Area Chart
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide11)
// 重點: 區域圖（單系列）+ 堆疊區域圖（barGrouping: "stacked"）+ chartColorsOpacity 半透明
// 註：示範資料為簡化版本，原 demo 用 12 個月份點與 CEO Pay Ratio 資料

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const MONS_SHORT = ["Q1","Q2","Q3","Q4"];

let slide = prs.addSlide();

// TOP-LEFT: 單系列區域圖（CEO 薪酬比示意）
let optsChartArea1 = {
  x: 0.5, y: 0.6, w: "45%", h: 3,
  chartArea: { fill: { color: "e9e9e9" } },
  plotArea: { fill: { color: "f2f9fc" } },
  dataBorder: { pt: 1, color: "F1F1F1" },
  showTitle: true,
  title: "CEO-to-worker compensation ratio",
  titleFontSize: 11,
  titleColor: "fc0000",
  valAxisLabelFormatCode: "#-1",
  valAxisLabelFontSize: 10,
  valAxisLabelColor: "494949",
  catAxisLabelFontSize: 10,
  catAxisLabelColor: "494949",
  catAxisLabelRotate: 45,
  chartColors: ["EF423E"],
  chartColorsOpacity: 25,
};
slide.addChart(prs.charts.AREA, [
  { name: "CEO Pay Ratio",
    labels: ["2000","2005","2010","2015","2020"],
    values: [318.5, 326.6, 271.6, 293.3, 351.1] },
], optsChartArea1);

// TOP-RIGHT: 堆疊區域圖
let arrDataTimeline2ser = [
  { name: "Actual Sales", labels: MONS_SHORT, values: [4600, 7855, 12102, 15121] },
  { name: "Proj Sales",   labels: MONS_SHORT, values: [4000, 7000, 10500, 13000] },
];
let optsChartArea2 = {
  x: 7, y: 0.6, w: "45%", h: 3,
  plotArea: { fill: { color: "D1E1F1" } },
  chartColors: ["0088CC", "99FFCC"],
  chartColorsOpacity: 25,
  valAxisLabelRotate: 5,
  dataBorder: { pt: 2, color: "FFFFFF" },
  showValue: false,
  barGrouping: "stacked",
};
slide.addChart(prs.charts.AREA, arrDataTimeline2ser, optsChartArea2);

// BTM-LEFT: 區域圖 50% 不透明 + K 格式碼
let optsChartArea3 = {
  x: 0.5, y: 4.0, w: "45%", h: 3,
  chartColors: ["0088CC", "99FFCC"],
  chartColorsOpacity: 50,
  valAxisLabelFormatCode: "#,K",
};
slide.addChart(prs.charts.AREA, arrDataTimeline2ser, optsChartArea3);

// BTM-RIGHT: 區域圖 75% 不透明
let optsChartArea4 = { x: 7, y: 4.0, w: "45%", h: 3, chartColors: ["CC8833", "CCFF69"], chartColorsOpacity: 75 };
slide.addChart(prs.charts.AREA, arrDataTimeline2ser, optsChartArea4);

window.__pptxDone(prs);
