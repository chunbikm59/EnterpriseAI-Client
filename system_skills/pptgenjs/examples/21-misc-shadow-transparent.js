// 範例 21: Misc Options - Shadow and Transparent Colors
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide21)
// 重點: 多種 shadow 效果（outer 不同顏色/角度）、chartColors 中的 "transparent" 透明系列

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const dataChartPieStat = [
  { name: "Project Status", labels: ["Red","Yellow","Green","Complete","Cancelled","Unknown"], values: [25, 5, 5, 5, 5, 5] },
];

const arrDataRegions = [
  { name: "Region 2", labels: ["April","May","June","July","August"], values: [0, 30, 53, 10, 25] },
  { name: "Region 3", labels: ["April","May","June","July","August"], values: [17, 26, 53, 100, 75] },
  { name: "Region 4", labels: ["April","May","June","July","August"], values: [55, 43, 70, 90, 80] },
  { name: "Region 5", labels: ["April","May","June","July","August"], values: [55, 43, 70, 90, 80] },
];
const arrDataHighVals = [
  { name: "California", labels: ["Apartment","Townhome","Duplex","House","Big House"], values: [2000, 2800, 3200, 4000, 5000] },
  { name: "Texas",      labels: ["Apartment","Townhome","Duplex","House","Big House"], values: [1400, 2000, 2500, 3000, 3800] },
];
const single = [
  { name: "Texas", labels: ["Apartment","Townhome","Duplex","House","Big House"], values: [1400, 2000, 2500, 3000, 3800] },
];

let slide = prs.addSlide();

// TOP-LEFT: 大藍色陰影
let optsChartBar1 = {
  x: 0.5, y: 0.6, w: 6.0, h: 3.0,
  showTitle: true,
  title: "Large blue shadow",
  barDir: "bar",
  barGrouping: "standard",
  dataLabelColor: "FFFFFF",
  showValue: true,
  shadow: {
    type: "outer",
    blur: 10,
    offset: 5,
    angle: 45,
    color: "0059B1",
    opacity: 1,
  },
};

// TOP-RIGHT: 圓餅 + 旋轉青色陰影
let pieOptions = {
  x: 7.0, y: 0.6, w: 6.0, h: 3.0,
  showTitle: true,
  title: "Rotated cyan shadow",
  dataLabelColor: "FFFFFF",
  /* 預設不顯示標籤；如需可開啟下列選項：
  dataLabelFontSize: 9,
  showLabel: true,
  showValue: true,
  showPercent: true,
  */
  shadow: {
    type: "outer",
    blur: 10,
    offset: 5,
    angle: 180,
    color: "00FFFF",
    opacity: 1,
  },
};

// BTM-LEFT: 透明 chartColors（用 "transparent" 製造間隔效果）
let optsChartBar3 = {
  x: 0.5, y: 3.8, w: 6.0, h: 3.5,
  showTitle: true,
  title: "No shadow, transparent colors",
  barDir: "bar",
  barGrouping: "stacked",
  chartColors: ["transparent", "5DA5DA", "transparent", "FAA43A"],
  shadow: { type: "none" },
};

// BTM-RIGHT: 紅色光暈陰影 + 粗體標題
let optsChartBar4 = {
  x: 7.0, y: 3.8, w: 6.0, h: 3.5,
  barDir: "col",
  barGrouping: "stacked",
  showTitle: true,
  title: "Red glowing shadow",
  titleBold: true,
  titleFontFace: "Times",
  catAxisLabelColor: "0000CC",
  catAxisLabelFontFace: "Times",
  catAxisLabelFontSize: 12,
  catAxisOrientation: "minMax",
  chartColors: ["5DA5DA", "FAA43A"],
  shadow: {
    type: "outer",
    blur: 20,
    offset: 1,
    angle: 90,
    color: "A70000",
    opacity: 1,
  },
};

slide.addChart(prs.charts.BAR, single,            optsChartBar1);
slide.addChart(prs.charts.PIE, dataChartPieStat,  pieOptions);
slide.addChart(prs.charts.BAR, arrDataRegions,    optsChartBar3);
slide.addChart(prs.charts.BAR, arrDataHighVals,   optsChartBar4);

window.__pptxDone(prs);
