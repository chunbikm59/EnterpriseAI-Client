export default function PptxRenderer() {
  const pptxId     = props.pptx_id             || "";
  const script     = props.pptx_script          || null;
  const partial    = props.pptx_script_partial  || null;
  const title      = props.title                || "簡報";
  const slideCount = props.slide_count          || 1;
  const convId     = props.conversation_id      || "";

  // status: "streaming" | "loading" | "rendering" | "ready" | "error"
  const initialStatus = script ? "loading" : "streaming";
  const [status,     setStatus]     = React.useState(initialStatus);
  const [pptxB64,    setPptxB64]    = React.useState(null);
  const [slideUrls,  setSlideUrls]  = React.useState([]);
  const [errMsg,     setErrMsg]     = React.useState("");
  const [downloaded, setDownloaded] = React.useState(false);

  // 從 partial JSON 前綴抽取 pptx_script 值的已知部分
  function extractPartialScript(raw) {
    if (!raw) return "";
    const match = raw.match(/"pptx_script"\s*:\s*"([\s\S]*)/);
    if (!match) return raw.slice(0, 800);
    let extracted = match[1];
    if (extracted.length > 1200) extracted = extracted.slice(0, 1200);
    try {
      extracted = JSON.parse('"' + extracted.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\\\\n/g, "\\n").replace(/\\\\t/g, "\\t") + '"');
    } catch (_) {}
    return extracted;
  }

  // 上傳 base64 pptx 到後端取縮圖
  async function fetchPreview(b64) {
    if (!convId) return;
    setStatus("rendering");
    try {
      const res = await fetch("/api/pptx-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pptx_b64: b64, pptx_id: pptxId, conversation_id: convId }),
        credentials: "include",
      });
      if (!res.ok) {
        const err = await res.text();
        setErrMsg(`縮圖生成失敗：${err}`);
        setStatus("ready");
        return;
      }
      const data = await res.json();
      setSlideUrls(data.slide_urls || []);
      setStatus("ready");
    } catch (e) {
      setErrMsg(`縮圖生成失敗：${String(e)}`);
      setStatus("ready");
    }
  }

  // 腳本執行
  React.useEffect(() => {
    if (!script) return;
    setStatus("loading");
    let cancelled = false;

    function runScript() {
      try {
        window.__pptxDone = async (prs) => {
          if (cancelled) return;
          try {
            const b64 = await prs.write({ outputType: "base64" });
            if (!cancelled) {
              setPptxB64(b64);
              await fetchPreview(b64);
            }
          } catch (e) {
            if (!cancelled) { setErrMsg(String(e)); setStatus("error"); }
          }
        };
        new Function(script)();
      } catch (e) {
        if (!cancelled) { setErrMsg(String(e)); setStatus("error"); }
      }
    }

    if (window.PptxGenJS) {
      runScript();
    } else {
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/gh/gitbrent/pptxgenjs/dist/pptxgen.bundle.js";
      s.onload = () => { if (!cancelled) runScript(); };
      s.onerror = () => {
        if (!cancelled) { setErrMsg("pptxgenjs CDN 載入失敗。"); setStatus("error"); }
      };
      document.head.appendChild(s);
    }
    return () => { cancelled = true; };
  }, [pptxId, script]);

  // CSS 動畫（只注入一次）
  React.useEffect(() => {
    if (document.getElementById("pptx-style")) return;
    const s = document.createElement("style");
    s.id = "pptx-style";
    s.textContent = `
      @keyframes pptx-pulse { 0%,100%{opacity:1} 50%{opacity:0.45} }
      @keyframes pptx-spin  { to{transform:rotate(360deg)} }
    `;
    document.head.appendChild(s);
  }, []);

  function handleDownload() {
    if (!pptxB64) return;
    const bytes = atob(pptxB64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: "application/vnd.openxmlformats-officedocument.presentationml.presentation" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${title}.pptx`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    setDownloaded(true);
    setTimeout(() => setDownloaded(false), 3000);
  }

  // ── 樣式 ──
  const btnBase = { padding:"3px 10px", fontSize:"11px", borderRadius:"6px", border:"1px solid var(--border,#e5e7eb)", background:"transparent", color:"var(--muted-foreground,#6b7280)", cursor:"pointer", lineHeight:"1.6", whiteSpace:"nowrap" };
  const dlBtn   = { ...btnBase, padding:"5px 14px", fontSize:"12px", fontWeight:600, borderColor:"var(--primary,#6366f1)", color: downloaded?"#fff":"var(--primary,#6366f1)", background: downloaded?"var(--primary,#6366f1)":"transparent", transition:"all 0.2s" };
  const spinner = React.createElement("div", { style:{ width:"28px", height:"28px", border:"3px solid var(--border,#e5e7eb)", borderTopColor:"var(--primary,#6366f1)", borderRadius:"50%", animation:"pptx-spin 0.8s linear infinite" } });

  // ── 工具列 ──
  const toolbar = React.createElement("div", {
    style:{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"6px 10px", borderBottom:"1px solid var(--border,#e5e7eb)", background:"var(--card,#fff)", flexShrink:0, gap:"8px" },
  },
    React.createElement("span", { style:{ fontSize:"12px", fontWeight:600, color:"var(--foreground,#111)", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:"220px" } }, title),
    (status==="ready"||status==="rendering") && pptxB64 &&
      React.createElement("button", { onClick:handleDownload, style:dlBtn }, downloaded?"✓ 已下載":"⬇ 下載 .pptx"),
  );

  // ── 佔位卡片 ──
  function PlaceholderCards({ animate }) {
    return React.createElement("div", { style:{ display:"flex", flexWrap:"wrap", gap:"8px", padding:"8px 0" } },
      ...Array.from({ length: Math.min(slideCount, 4) }, (_, i) =>
        React.createElement("div", {
          key: i,
          style:{ width:"120px", height:"80px", borderRadius:"6px", flexShrink:0, border:"1px solid var(--border,#e5e7eb)", background:animate?"var(--muted,#f3f4f6)":"var(--card,#fff)", display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:"6px", animation:animate?`pptx-pulse 1.4s ease-in-out ${i*0.15}s infinite`:"none", boxShadow:"0 1px 3px rgba(0,0,0,0.08)" },
        },
          React.createElement("div", { style:{ width:"60px", height:"8px", borderRadius:"4px", background:"var(--border,#e5e7eb)" } }),
          React.createElement("div", { style:{ width:"40px", height:"6px", borderRadius:"4px", background:"var(--muted,#f3f4f6)" } }),
          !animate && React.createElement("div", { style:{ fontSize:"10px", color:"var(--muted-foreground,#9ca3af)" } }, `第 ${i+1} 張`),
        )
      ),
    );
  }

  // ════════════ 串流中 ════════════
  if (status === "streaming") {
    const displayScript = extractPartialScript(partial);
    const charCount = partial ? partial.length : 0;
    return React.createElement("div", { style:{ display:"flex", flexDirection:"column", height:"100%", overflow:"hidden" } },
      toolbar,
      React.createElement("div", { style:{ padding:"12px", overflowY:"auto", flex:1 } },
        React.createElement("div", { style:{ fontSize:"11px", color:"var(--muted-foreground,#6b7280)", marginBottom:"10px", display:"flex", alignItems:"center", gap:"6px" } },
          React.createElement("span", { style:{ width:"8px", height:"8px", borderRadius:"50%", background:"var(--primary,#6366f1)", display:"inline-block", animation:"pptx-pulse 1s ease-in-out infinite" } }),
          `腳本生成中… 已接收 ${charCount} 字元`,
        ),
        React.createElement(PlaceholderCards, { animate: true }),
        displayScript && React.createElement("div", { style:{ marginTop:"10px", borderRadius:"8px", border:"1px solid var(--border,#e5e7eb)", overflow:"hidden" } },
          React.createElement("div", { style:{ padding:"3px 10px", background:"var(--muted,#f3f4f6)", fontSize:"10px", color:"var(--muted-foreground,#9ca3af)", borderBottom:"1px solid var(--border,#e5e7eb)" } }, "pptxgenjs script"),
          React.createElement("pre", {
            ref: (el) => { if (el) el.scrollTop = el.scrollHeight; },
            style:{ margin:0, padding:"10px", fontSize:"10px", lineHeight:"1.6", color:"var(--foreground,#374151)", background:"var(--card,#fafafa)", overflowX:"auto", maxHeight:"220px", overflowY:"auto", whiteSpace:"pre-wrap", wordBreak:"break-all" },
          }, displayScript + "▌"),
        ),
      ),
    );
  }

  // ════════════ 執行腳本中 ════════════
  if (status === "loading") {
    return React.createElement("div", { style:{ display:"flex", flexDirection:"column", height:"100%", overflow:"hidden" } },
      toolbar,
      React.createElement("div", { style:{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:"12px", color:"var(--muted-foreground,#6b7280)", fontSize:"13px" } },
        spinner, "正在執行腳本並生成 .pptx…",
      ),
    );
  }

  // ════════════ 生成縮圖中 ════════════
  if (status === "rendering") {
    return React.createElement("div", { style:{ display:"flex", flexDirection:"column", height:"100%", overflow:"hidden" } },
      toolbar,
      React.createElement("div", { style:{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:"12px", color:"var(--muted-foreground,#6b7280)", fontSize:"13px" } },
        spinner, "正在生成投影片預覽…",
        React.createElement("div", { style:{ fontSize:"11px" } }, "（已完成 .pptx 生成，可點上方按鈕下載）"),
      ),
    );
  }

  // ════════════ 錯誤 ════════════
  if (status === "error") {
    return React.createElement("div", { style:{ display:"flex", flexDirection:"column", height:"100%", overflow:"hidden" } },
      toolbar,
      React.createElement("div", { style:{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:"10px", padding:"24px" } },
        React.createElement("div", { style:{ fontSize:"28px" } }, "⚠️"),
        React.createElement("div", { style:{ fontSize:"13px", fontWeight:600, color:"var(--destructive,#ef4444)" } }, "腳本執行失敗"),
        React.createElement("pre", { style:{ fontSize:"11px", color:"var(--muted-foreground,#6b7280)", background:"var(--muted,#f9fafb)", border:"1px solid var(--border,#e5e7eb)", borderRadius:"6px", padding:"10px", maxWidth:"100%", overflowX:"auto", whiteSpace:"pre-wrap", wordBreak:"break-all" } }, errMsg),
      ),
    );
  }

  // ════════════ 完成（ready）════════════
  return React.createElement("div", { style:{ display:"flex", flexDirection:"column", height:"100%", overflow:"hidden" } },
    toolbar,
    React.createElement("div", { style:{ padding:"12px", overflowY:"auto", flex:1, display:"flex", flexDirection:"column", gap:"10px" } },

      // 縮圖：縱向列出所有投影片
      slideUrls.length > 0
        ? slideUrls.map((url, i) =>
            React.createElement("div", { key: url, style:{ display:"flex", flexDirection:"column", gap:"4px" } },
              React.createElement("div", { style:{ fontSize:"10px", color:"var(--muted-foreground,#9ca3af)" } }, `第 ${i+1} 張`),
              React.createElement("img", {
                src: url,
                alt: `第 ${i+1} 張投影片`,
                style:{ width:"100%", height:"auto", display:"block", borderRadius:"4px", border:"1px solid var(--border,#e5e7eb)", boxShadow:"0 1px 4px rgba(0,0,0,0.08)" },
              }),
            )
          )
        : React.createElement("div", null,
            errMsg && React.createElement("div", { style:{ fontSize:"11px", color:"var(--muted-foreground,#9ca3af)", marginBottom:"8px" } }, errMsg),
            React.createElement(PlaceholderCards, { animate: false }),
          ),

      // 底部資訊
      React.createElement("div", { style:{ fontSize:"11px", color:"var(--muted-foreground,#9ca3af)", marginTop:"2px" } },
        `共 ${slideUrls.length || slideCount} 張投影片　格式：.pptx（PowerPoint 相容）`,
      ),
    ),
  );
}
