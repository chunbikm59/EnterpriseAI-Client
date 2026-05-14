// 範例 04: Bar Chart - Stacked / PercentStacked / DataTable
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide04)
// 重點: barGrouping: "stacked" / "percentStacked" + 顯示資料表 (showDataTable)

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_VIVID = ["ff595e","F38940","ffca3a","8ac926","1982c4","5FBDE1","6a4c93"];
const dataChartBar3Series = [
  { name: "Americas", labels: ["Phones","Laptops","Tablets","Desktops"], values: [1400,2000,2500,3000] },
  { name: "Asia",     labels: ["Phones","Laptops","Tablets","Desktops"], values: [2000,2800,3200,5000] },
  { name: "Europe",   labels: ["Phones","Laptops","Tablets","Desktops"], values: [1400,2000,3000,3800] },
];

const arrDataRegions = [
  { name: "Region 3", labels: ["April","May","June","July","August"], values: [17, 26, 53, 100, 75] },
  { name: "Region 4", labels: ["April","May","June","July","August"], values: [55, 43, 70, 90, 80] },
];

let slide = prs.addSlide();

// TOP-LEFT: 橫條 stacked，深色背景 + 黃藍配色
let optsChartBar1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "404040" } },
  plotArea: { fill: { color: "0d0d0d" } },
  barDir: "bar",
  barGrouping: "stacked",
  chartColors: ["F2AF00", "4472C4"],
  catAxisOrientation: "maxMin",
  catAxisLabelColor: "4472C4",
  catAxisLabelFontFace: "Helvetica Neue",
  catAxisLabelFontSize: 14,
  valAxisLabelColor: "F2AF00",
  valAxisLabelFontFace: "Helvetica Neue",
  valAxisLabelFontSize: 14,
  dataLabelColor: "FFFFFF",
  showValue: true,
};
slide.addChart(prs.charts.BAR, arrDataRegions, optsChartBar1);

// TOP-RIGHT: 直條 stacked，3 系列 vivid 配色
let optsChartBar2 = {
  x: 7.0, y: 0.6, w: 6.0, h: 3.0,
  chartArea: { fill: { color: "0d0d0d" } },
  plotArea: { fill: { color: "4d4d4d" } },
  chartColors: COLORS_VIVID,
  valGridLine: { color: "141414" },
  valAxisLabelColor: "F1F1F1",
  catAxisLabelColor: "F1F1F1",
  dataLabelColor: "F1F1F1",
  barDir: "col",
  barGrouping: "stacked",
  dataLabelFontFace: "Arial",
  dataLabelFontSize: 12,
  dataLabelFontBold: true,
  showValue: true,
  catAxisLabelFontFace: "Courier",
  catAxisLabelFontSize: 12,
  catAxisOrientation: "minMax",
  showLegend: false,
  showTitle: false,
};
slide.addChart(prs.charts.BAR, dataChartBar3Series, optsChartBar2);

// BTM-LEFT: 橫條 percentStacked + 顯示資料表
let optsChartBar3 = {
  x: 0.5, y: 3.8, w: 6.0, h: 3.5,
  barDir: "bar",
  barGrouping: "percentStacked",
  chartColors: ["F2AF00", "4472C4"],
  dataBorder: { pt: 1, color: "F1F1F1" },
  catAxisHidden: true,
  valAxisHidden: true,
  valGridLine: { style: "none" },
  showTitle: false,
  layout: { x: 0.1, y: 0.1, w: 1, h: 1 },
  showDataTable: true,
  showDataTableKeys: true,
  showDataTableHorzBorder: false,
  showDataTableVertBorder: false,
  showDataTableOutline: false,
  dataTableFontSize: 10,
};
slide.addChart(prs.charts.BAR, arrDataRegions, optsChartBar3);

// BTM-RIGHT: 直條 percentStacked + 資料表貨幣格式
let optsChartBar4 = {
  x: 7.0, y: 3.8, w: 6.0, h: 3.5,
  chartArea: { fill: { color: "f1f1f1" } },
  plotArea: { fill: { color: "ffffff" } },
  chartColors: COLORS_VIVID,
  barDir: "col",
  barGrouping: "percentStacked",
  catAxisLabelFontFace: "Times",
  catAxisLabelFontSize: 12,
  catAxisOrientation: "minMax",
  showLegend: true,
  legendPos: "t",
  showDataTable: true,
  showDataTableKeys: false,
  dataTableFormatCode: "$#",
  //dataTableFormatCode: '0.00%' // @since v3.3.0
  //dataTableFormatCode: '$0.00' // @since v3.3.0
};
slide.addChart(prs.charts.BAR, dataChartBar3Series, optsChartBar4);

window.__pptxDone(prs);
