// 範例 10: Line Chart - lineDataSymbol 7 Types
// 原始 demo: https://github.com/gitbrent/PptxGenJS/blob/master/demos/modules/demo_chart.mjs (genSlide10)
// 重點: 用 forEach 在 3×3 grid 展示 7 種 lineDataSymbol（circle、dash、diamond、dot、none、square、triangle）

let prs = new PptxGenJS();
prs.layout = "LAYOUT_WIDE";

const COLORS_VIVID = ["ff595e","F38940","ffca3a","8ac926","1982c4","5FBDE1","6a4c93"];

const arrDataLineStat = [
  { name: "Red",      labels: ["Q1","Q2","Q3","Q4"], values: [1, 3, 5, 7] },
  { name: "Yellow",   labels: ["Q1","Q2","Q3","Q4"], values: [5, 26, 32, 30] },
  { name: "Green",    labels: ["Q1","Q2","Q3","Q4"], values: [7, 52, 18, 67] },
  { name: "Complete", labels: ["Q1","Q2","Q3","Q4"], values: [3, 5, 17, 1] },
];

const intWgap = 4.25;
const opts_lineDataSymbol = ["circle","dash","diamond","dot","none","square","triangle"];

let slide = prs.addSlide();

opts_lineDataSymbol.forEach((opt, idx) => {
  slide.addChart(prs.charts.LINE, arrDataLineStat, {
    x: (idx < 3 ? idx * intWgap : idx < 6 ? (idx - 3) * intWgap : (idx - 6) * intWgap) + 0.3,
    y: idx < 3 ? 0.5 : idx < 6 ? 2.85 : 5.1,
    w: 4.25,
    h: 2.25,
    lineCap: "round",
    lineDataSymbol: opt,
    lineDataSymbolSize: idx === 5 ? 9 : idx === 6 ? 12 : null,
    chartColors: COLORS_VIVID,
    title: opt,
    showTitle: true,
  });
});

window.__pptxDone(prs);
