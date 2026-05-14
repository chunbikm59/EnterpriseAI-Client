// 範例 05: Bar Chart - Data Series Colors, majorUnits, and valAxisLabelFormatCode
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide05)
// 重點: 每根 bar 不同顏色（chartColors 陣列 > 系列數）、Excel 日期格式 catLabelFormatCode、百分比格式碼

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

let slide = prs.addSlide();

// TOP-LEFT: 多色 bar + Excel 日期 (yyyy-mm)
slide.addChart(prs.charts.BAR, [
  { name: "Excel Date Values", labels: [37987, 38018, 38047, 38078, 38108, 38139], values: [20, 30, 10, 25, 15, 5] },
], {
  x: 0.5, y: 0.6, w: "45%", h: 3,
  chartArea: { fill: { color: "404040" } },
  barDir: "bar",
  chartColors: ["0077BF","4E9D2D","ECAA00","5FC4E3","DE4216","154384"],
  catAxisLabelColor: "F1F1F1",
  catLabelFormatCode: "yyyy-mm",
  valAxisHidden: true,
  showTitle: true,
  title: "Categories can be Multi-Color",
  titleColor: "0088CC",
  titleFontSize: 14,
});

// TOP-RIGHT: 多色 bar + 百分比格式 (mmm-yy, #%)
slide.addChart(prs.charts.BAR, [
  { name: "Too Many Colors Series", labels: [37987, 38018, 38047, 38078, 38108, 38139], values: [0.2, 0.3, 0.1, 0.25, 0.15, 0.05] },
], {
  x: 7, y: 0.6, w: "45%", h: 3,
  chartArea: { fill: { color: "404040" } },
  catAxisLabelColor: "F1F1F1",
  valAxisLabelColor: "F1F1F1",
  valAxisLineColor: "7F7F7F",
  valGridLine: { color: "7F7F7F" },
  dataLabelColor: "B7B7B7",
  valAxisMaxVal: 1,
  barDir: "bar",
  catAxisLineShow: false,
  showValue: true,
  catLabelFormatCode: "mmm-yy",
  dataLabelPosition: "outEnd",
  dataLabelFormatCode: "#%",
  valAxisLabelFormatCode: "#%",
  valAxisMajorUnit: 0.2,
  chartColors: ["0077BF","4E9D2D","ECAA00","5FC4E3","DE4216","154384","7D666A","A3C961","EF907B","9BA0A3"],
  barGapWidthPct: 25,
});

// BTM-LEFT: 直條含正負值 + 百分比格式
slide.addChart(prs.charts.BAR, [
  { name: "Two Color Series", labels: ["Jan","Feb","Mar","Apr","May","Jun"], values: [0.2, -0.3, -0.1, 0.25, 0.15, 0.05] },
], {
  x: 0.5, y: 4.0, w: "45%", h: 3,
  chartArea: { fill: { color: "404040" } },
  plotArea: { fill: { color: "202020" } },
  catAxisLabelColor: "F1F1F1",
  valAxisLabelColor: "F1F1F1",
  valAxisLineColor: "7F7F7F",
  valGridLine: { color: "7F7F7F" },
  dataLabelColor: "B7B7B7",
  valAxisHidden: true,
  barDir: "col",
  showValue: true,
  dataLabelPosition: "outEnd",
  dataLabelFormatCode: "#%",
  valAxisLabelFormatCode: "0.#0",
  chartColors: ["0077BF","4E9D2D","ECAA00","5FC4E3","DE4216","154384","7D666A","A3C961","EF907B","9BA0A3"],
  valAxisMaxVal: 0.4,
  barGapWidthPct: 50,
  showLegend: true,
  legendPos: "r",
  legendColor: "F1F1F1",
});

// BTM-RIGHT: 雙系列橫條，valAxis 控制範圍與單位
slide.addChart(prs.charts.BAR, [
  { name: "EV",  labels: ["Jan","Feb","Mar","Apr","May","Jun"], values: [102, 103, 121, 125, 135, 155] },
  { name: "ICE", labels: ["Jan","Feb","Mar","Apr","May","Jun"], values: [150, 153, 151, 125, 115, 105] },
], {
  x: 7, y: 4, w: "45%", h: 3,
  chartArea: { fill: { color: "202020" } },
  barDir: "bar",
  catAxisLabelColor: "F1F1F1",
  valAxisLabelColor: "F1F1F1",
  valAxisLineColor: "7F7F7F",
  valGridLine: { color: "7F7F7F" },
  dataLabelColor: "B7B7B7",
  chartColorsOpacity: 75,
  chartColors: ["0077BF","4E9D2D","ECAA00","5FC4E3","DE4216","154384","7D666A","A3C961","EF907B","9BA0A3"],
  barGapWidthPct: 25,
  catAxisOrientation: "maxMin",
  valAxisOrientation: "maxMin",
  valAxisMaxVal: 200,
  valAxisMajorUnit: 25,
});

window.__pptxDone(prs);
