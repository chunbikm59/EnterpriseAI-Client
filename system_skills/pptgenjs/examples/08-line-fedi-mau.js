// 範例 08: Line Chart - Single Series with Title and Symbols
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide08)
// 重點: 單系列折線 + lineDataSymbol 樣式（lineSize/lineDataSymbolSize/lineDataSymbolLineColor）+ 旋轉類別軸標籤
// 註：示範資料為簡化版本（6 點），原 demo 用 18 個月份點的 Fediverse MAU 真實資料

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLOR_GRN = "7AB800";

let slide = prs.addSlide();

const OPTS_CHART = {
  x: 0.5, y: 0.6, w: "95%", h: "85%",
  plotArea: { fill: { color: "e3e3e3" } },
  showLegend: true,
  legendPos: "r",
  catAxisLabelRotate: 90,
  valAxisLabelFormatCode: "#,##0",
  lineSize: 4,
  chartColors: [COLOR_GRN],
  lineDataSymbolSize: 10,
  lineDataSymbolLineColor: "4472C4",
  lineDataSymbolLineSize: 3,
  showTitle: true,
  title: "Fediverse Statistics",
  titleColor: "0088CC",
  titleFontFace: "Arial",
  titleFontSize: 18,
};

slide.addChart(prs.charts.LINE, [
  {
    name: "Total Users by Month",
    labels: ["2024-01","2024-03","2024-06","2024-09","2024-12","2025-03"],
    values: [14058732, 13576218, 12345678, 10987413, 13158749, 14538124],
  },
], OPTS_CHART);

window.__pptxDone(prs);
