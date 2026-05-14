// 範例 20: Combo Chart - 4 Variations
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide20)
// 重點: 4 種組合圖在 2×2 grid：(TL) col+area+line、(TR) stacked+line、(BL) stacked+dot、(BR) col+bar 雙向

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

let slide = prs.addSlide();

// TOP-L: column + area + line（共用雙數值軸）---------------------------
function doColumnAreaLine() {
  let opts = {
    x: 0.6, y: 0.6, w: 6.0, h: 3.0,
    barDir: "col",
    catAxisLabelColor: "666666",
    catAxisLabelFontFace: "Arial",
    catAxisLabelFontSize: 12,
    catAxisOrientation: "minMax",
    showLegend: false,
    showTitle: false,
    valAxisMaxVal: 100,
    valAxisMajorUnit: 10,
    valAxes: [
      { showValAxisTitle: true, valAxisTitle: "Primary Value Axis" },
      { showValAxisTitle: true, valAxisTitle: "Secondary Value Axis", valGridLine: { style: "none" } },
    ],
    catAxes: [
      { catAxisTitle: "Primary Category Axis" },
      { catAxisHidden: true },
    ],
  };

  let labels = ["April","May","June","July","August"];
  let chartTypes = [
    {
      type: prs.charts.AREA,
      data: [{ name: "Current", labels: labels, values: [1, 4, 7, 2, 3] }],
      options: {
        chartColors: ["00FFFF"],
        barGrouping: "standard",
        secondaryValAxis: !!opts.valAxes,
        secondaryCatAxis: !!opts.catAxes,
      },
    },
    {
      type: prs.charts.BAR,
      data: [{ name: "Bottom", labels: labels, values: [17, 26, 53, 10, 4] }],
      options: { chartColors: ["0000FF"], barGrouping: "stacked" },
    },
    {
      type: prs.charts.LINE,
      data: [{ name: "Current", labels: labels, values: [5, 3, 2, 4, 7] }],
      options: {
        barGrouping: "standard",
        secondaryValAxis: !!opts.valAxes,
        secondaryCatAxis: !!opts.catAxes,
      },
    },
  ];
  slide.addChart(chartTypes, opts);
}

// TOP-R: stacked bar + line（無雙軸）-----------------------------------
function doStackedLine() {
  let opts = {
    x: 6.83, y: 0.6, w: 6.0, h: 3.0,
    chartArea: { fill: { color: "F1F1F1" } },
    barDir: "col",
    barGrouping: "stacked",
    catAxisLabelColor: "0000CC",
    catAxisLabelFontFace: "Arial",
    catAxisLabelFontSize: 12,
    catAxisOrientation: "minMax",
    showLegend: false,
    showTitle: false,
    valAxisMaxVal: 100,
    valAxisMajorUnit: 10,
  };

  let labels = ["Mon","Tue","Wed","Thu","Fri"];
  let chartTypes = [
    {
      type: prs.charts.BAR,
      data: [
        { name: "Bottom", labels: labels, values: [17, 26, 53, 10, 4] },
        { name: "Middle", labels: labels, values: [55, 40, 20, 30, 15] },
        { name: "Top",    labels: labels, values: [10, 22, 25, 35, 70] },
      ],
      options: { barGrouping: "stacked" },
    },
    {
      type: prs.charts.LINE,
      data: [{ name: "Current", labels: labels, values: [25, 35, 55, 10, 5] }],
      options: { barGrouping: "standard" },
    },
  ];
  slide.addChart(chartTypes, opts);
}

// BTM-L: stacked bar + 純標記折線（lineSize:0 + lineDataSymbolSize 大）---
function doStackedDot() {
  let opts = {
    x: 0.5, y: 4.0, w: 6.0, h: 3.0,
    chartArea: { fill: { color: "F1F1F1" } },
    barDir: "col",
    barGrouping: "stacked",
    catAxisLabelColor: "999999",
    catAxisLabelFontFace: "Arial",
    catAxisLabelFontSize: 14,
    catAxisOrientation: "minMax",
    showLegend: false,
    showTitle: false,
    valAxisMaxVal: 100,
    valAxisMinVal: 0,
    valAxisMajorUnit: 20,
    lineSize: 0,
    lineDataSymbolSize: 20,
    lineDataSymbolLineSize: 2,
    lineDataSymbolLineColor: "FF0000",
    valAxes: [
      { showValAxisTitle: true, valAxisTitle: "Primary Value Axis" },
      {
        showValAxisTitle: true,
        valAxisTitle: "Secondary Value Axis",
        catAxisOrientation: "maxMin",
        valAxisMajorUnit: 1,
        valAxisMaxVal: 10,
        valAxisMinVal: 1,
        valGridLine: { style: "none" },
      },
    ],
    catAxes: [{ catAxisTitle: "Primary Category Axis" }, { catAxisHidden: true }],
  };

  let labels = ["Q1","Q2","Q3","Q4","OT"];
  let chartTypes = [
    {
      type: prs.charts.BAR,
      data: [
        { name: "Bottom", labels: labels, values: [17, 26, 53, 10, 4] },
        { name: "Middle", labels: labels, values: [55, 40, 20, 30, 15] },
        { name: "Top",    labels: labels, values: [10, 22, 25, 35, 70] },
      ],
      options: { barGrouping: "stacked" },
    },
    {
      type: prs.charts.LINE,
      data: [{ name: "Current", labels: labels, values: [5, 3, 2, 4, 7] }],
      options: {
        barGrouping: "standard",
        secondaryValAxis: !!opts.valAxes,
        secondaryCatAxis: !!opts.catAxes,
        chartColors: ["FFFF00"],
      },
    },
  ];
  slide.addChart(chartTypes, opts);
}

// BTM-R: stacked col + bar 雙向（barDir 主圖 col，副圖 bar）------------
function doBarCol() {
  let opts = {
    x: 6.83, y: 4.0, w: 6.0, h: 3.0,
    chartArea: { fill: { color: "F1F1F1" } },
    barDir: "col",
    barGrouping: "stacked",
    catAxisLabelColor: "999999",
    catAxisLabelFontFace: "Arial",
    catAxisLabelFontSize: 14,
    catAxisOrientation: "minMax",
    showLegend: false,
    showTitle: false,
    valAxisMaxVal: 100,
    valAxisMinVal: 0,
    valAxisMajorUnit: 20,
    valAxes: [
      { showValAxisTitle: true, valAxisTitle: "Primary Value Axis" },
      {
        showValAxisTitle: true,
        valAxisTitle: "Secondary Value Axis",
        catAxisOrientation: "maxMin",
        valAxisMajorUnit: 1,
        valAxisMaxVal: 10,
        valAxisMinVal: 1,
        valGridLine: { style: "none" },
      },
    ],
    catAxes: [{ catAxisTitle: "Primary Category Axis" }, { catAxisHidden: true }],
  };

  let labels = ["Q1","Q2","Q3","Q4","OT"];
  let chartTypes = [
    {
      type: prs.charts.BAR,
      data: [
        { name: "Bottom", labels: labels, values: [17, 26, 53, 10, 4] },
        { name: "Middle", labels: labels, values: [55, 40, 20, 30, 15] },
        { name: "Top",    labels: labels, values: [10, 22, 25, 35, 70] },
      ],
      options: { barGrouping: "stacked" },
    },
    {
      type: prs.charts.BAR,
      data: [{ name: "Current", labels: labels, values: [5, 3, 2, 4, 7] }],
      options: {
        barDir: "bar",
        barGrouping: "standard",
        chartColors: ["0077BF","4E9D2D","ECAA00","5FC4E3","DE4216","154384"],
        secondaryValAxis: !!opts.valAxes,
        secondaryCatAxis: !!opts.catAxes,
      },
    },
  ];
  slide.addChart(chartTypes, opts);
}

doColumnAreaLine();
doStackedLine();
doStackedDot();
doBarCol();

window.__pptxDone(prs);
