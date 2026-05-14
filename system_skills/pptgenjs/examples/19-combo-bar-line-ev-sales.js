// 範例 19: Combo Chart - Bar + Line (EV Sales 雙軸)
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide19)
// 重點: 組合圖（堆疊直條 + 折線）+ 雙數值軸（valAxes 陣列）+ 隱藏次類別軸
// 註：示範資料為簡化版本（5 年），原 demo 用 2012-2024 共 13 年的 IEA EV 銷量真實資料

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_SPECTRUM = ["56B4E4","126CB0","672C7E","E92A31","F06826","E9AF1F","51B747","189247"];

const EV_LABELS = ["2020","2021","2022","2023","2024"];

let slide = prs.addSlide();

// 組合圖屬性（套用整體版面、雙軸定義）
const comboProps = {
  x: 0.5, y: 0.6, w: 12.3, h: "85%",
  chartArea: { fill: { color: "F1F1F1" } },
  barDir: "col",
  barGrouping: "stacked",
  //
  catAxisLabelColor: "494949",
  catAxisLabelFontFace: "Arial",
  catAxisLabelFontSize: 10,
  catAxisOrientation: "minMax",
  //
  showLegend: true,
  legendPos: "b",
  //
  showTitle: true,
  titleFontFace: "Calibri Light",
  titleFontSize: 14,
  title: "Electric Vehicle Sales",
  //
  valAxes: [
    {
      showValAxisTitle: true,
      valAxisTitle: "Cars Produced (m)",
      valAxisMaxVal: 20,
      valAxisTitleColor: "1982c4",
      valAxisLabelColor: "1982c4",
    },
    {
      showValAxisTitle: true,
      valAxisTitle: "Global Market Share (%)",
      valAxisMaxVal: 20,
      valAxisTitleColor: "F38940",
      valAxisLabelColor: "F38940",
      valGridLine: { style: "none" },
    },
  ],
  //
  catAxes: [{ catAxisTitle: "Year" }, { catAxisHidden: true }],
};

// 組合圖：BAR（多區域堆疊）+ LINE（市占率 %）
const comboTypes = [
  {
    type: prs.charts.BAR,
    data: [
      { name: "China",         labels: EV_LABELS, values: [1.1, 3.3, 6.0, 8.1, 10.1] },
      { name: "Europe",        labels: EV_LABELS, values: [1.4, 2.3, 2.7, 3.2, 3.4] },
      { name: "United States", labels: EV_LABELS, values: [0.3, 0.6, 1.0, 1.4, 1.7] },
      { name: "Rest of World", labels: EV_LABELS, values: [0.2, 0.3, 0.6, 1.0, 1.4] },
    ],
    options: { chartColors: COLORS_SPECTRUM, barGrouping: "stacked" },
  },
  {
    type: prs.charts.LINE,
    data: [
      { name: "Global Market Share (%)", labels: EV_LABELS, values: [4.11, 8.57, 12, 15, 19] },
    ],
    options: { chartColors: ["F38940"], secondaryValAxis: true, secondaryCatAxis: true },
  },
];

slide.addChart(comboTypes, comboProps);

window.__pptxDone(prs);
