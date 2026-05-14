// 範例 07: Tornado Chart
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide07)
// 重點: 左右對稱橫條（龍捲風圖），用負值 + valueBarColors + barGrouping: "stacked" + invertedColors 實現

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

let slide = prs.addSlide();

slide.addChart(prs.charts.BAR, [
  { name: "High", labels: ["London","Munich","Tokyo"], values: [ 0.2,  0.32,  0.41] },
  { name: "Low",  labels: ["London","Munich","Tokyo"], values: [-0.11, -0.22, -0.29] },
], {
  x: 0.5, y: 0.5, w: "90%", h: "90%",
  chartArea: { fill: { color: "F1F1F1", transparency: 50 } },
  valAxisMaxVal: 1,
  barDir: "bar",
  axisLabelFormatCode: "#%",
  catGridLine: { color: "D8D8D8", style: "dash", size: 1, cap: "round" },
  valGridLine: { color: "D8D8D8", style: "dash", size: 1, cap: "square" },
  catAxisLineShow: false,
  valAxisLineShow: false,
  barGrouping: "stacked",
  catAxisLabelPos: "low",
  valueBarColors: true,
  shadow: { type: "none" },
  chartColors:    ["0077BF","4E9D2D","ECAA00","5FC4E3","DE4216","154384","7D666A","A3C961","EF907B","9BA0A3"],
  invertedColors: ["0065A2","428526","C99100","51A7C1","BD3813","123970","6A575A","8BAB52","CB7A69","84888B"],
  barGapWidthPct: 25,
  valAxisMajorUnit: 0.2,
});

window.__pptxDone(prs);
