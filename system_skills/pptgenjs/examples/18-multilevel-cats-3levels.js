// 範例 18: Multi-Level Category Axes (3 Levels)
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide18)
// 重點: 多層類別軸 3 層 — labels 為 3D 陣列（Q1-Q4 細項 / Apple-Banana 群組 / 2024-2025 年份）

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

// labels 為 3 層：
//   Level 0: Q1-Q4
//   Level 1: Apple / Banana
//   Level 2: 2024 / 2025
// 群組標籤後面填 "" 代表沿用前一個非空標籤
const arrDataRegions = [
  {
    name: "Fruits",
    labels: [
      ["Q1","Q2","Q3","Q4","Q1","Q2","Q3","Q4","Q1","Q2","Q3","Q4","Q1","Q2","Q3","Q4"],
      ["Apple","","","","Banana","","","","Apple","","","","Banana","","",""],
      ["2024","","","","","","","","2025","","","","","","",""],
    ],
    values: [734, 465, 656, 176, 434, 165, 613, 359, 279, 660, 307, 270, 539, 142, 554, 405],
  },
];

let slide = prs.addSlide();

const opts1 = {
  x: 0.5, y: 0.6, w: 12.3, h: 6.5,
  chartArea: { fill: { color: "F1F1F1" }, roundedCorners: false },
  catAxisMultiLevelLabels: true,
  chartColors: ["C0504D","C0504D","C0504D","C0504D","FFC000","FFC000","FFC000","FFC000"],
};

slide.addChart(prs.charts.BAR, arrDataRegions, opts1);

window.__pptxDone(prs);
