export default function MarkdownRenderer() {
  const historyData = props.history_data || [];
  const historyMeta = props.history      || [];
  const initialIndex = typeof props.current_index === "number" ? props.current_index : 0;

  const [currentIndex, setCurrentIndex] = React.useState(initialIndex);
  const [renderedHtml, setRenderedHtml] = React.useState("");
  const [copied, setCopied]             = React.useState(false);

  // 當最新版 md_id 變更時，自動跳回最新版
  const latestMdId = historyData[0] && historyData[0].md_id;
  const prevLatestIdRef = React.useRef(latestMdId);
  React.useEffect(() => {
    if (prevLatestIdRef.current !== latestMdId) {
      prevLatestIdRef.current = latestMdId;
      setCurrentIndex(0);
    }
  }, [latestMdId]);

  const currentItem = historyData[currentIndex] || {
    md_id:            props.md_id    || "init",
    markdown_content: props.markdown_content || null,
    title:            props.title    || "文件",
  };

  const partial = props.markdown_content_partial || null;
  const isStreaming = currentItem.markdown_content === null && !!partial;

  // 從不完整 JSON 前綴中抽取 content 欄位的已知部分（對齊 PptxRenderer.extractPartialScript）
  function extractPartialContent(raw) {
    if (!raw) return "";
    const match = raw.match(/"content"\s*:\s*"([\s\S]*)/);
    if (!match) return "";
    let extracted = match[1];
    if (extracted.length > 8000) extracted = extracted.slice(0, 8000);
    // 逆轉義常見 JSON string 轉義序列
    extracted = extracted
      .replace(/\\n/g, "\n")
      .replace(/\\t/g, "\t")
      .replace(/\\r/g, "\r")
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, "\\");
    return extracted;
  }

  // ready 狀態時用 marked.js 渲染 markdown
  React.useEffect(() => {
    if (isStreaming || !currentItem.markdown_content) return;
    const md = currentItem.markdown_content;

    function doRender() {
      try {
        const html = window.marked.parse(md, { gfm: true, breaks: true });
        setRenderedHtml(html);
      } catch (e) {
        setRenderedHtml("<pre>" + md.replace(/</g, "&lt;") + "</pre>");
      }
    }

    if (window.marked) {
      doRender();
      return;
    }
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/marked/marked.min.js";
    s.onload = doRender;
    s.onerror = () => setRenderedHtml("<pre>" + md.replace(/</g, "&lt;") + "</pre>");
    document.head.appendChild(s);
  }, [currentItem.md_id, currentItem.markdown_content, isStreaming]);

  // 注入 CSS（僅一次）
  React.useEffect(() => {
    if (document.getElementById("md-renderer-style")) return;
    const s = document.createElement("style");
    s.id = "md-renderer-style";
    s.textContent = `
      @keyframes md-pulse { 0%,100%{opacity:1} 50%{opacity:0.45} }
      .md-prose { font-size:14px; line-height:1.75; color:var(--foreground,#111); padding:0 2px; }
      .md-prose h1,.md-prose h2,.md-prose h3,.md-prose h4 { font-weight:700; margin:1em 0 0.4em; line-height:1.3; }
      .md-prose h1 { font-size:1.5em; }
      .md-prose h2 { font-size:1.25em; }
      .md-prose h3 { font-size:1.1em; }
      .md-prose p  { margin:0.6em 0; }
      .md-prose ul,.md-prose ol { padding-left:1.5em; margin:0.5em 0; }
      .md-prose li { margin:0.25em 0; }
      .md-prose code { background:var(--muted,#f3f4f6); padding:2px 5px; border-radius:4px; font-size:12px; font-family:monospace; }
      .md-prose pre  { background:var(--muted,#f3f4f6); border-radius:6px; padding:10px 12px; overflow-x:auto; margin:0.75em 0; }
      .md-prose pre code { background:none; padding:0; font-size:12px; }
      .md-prose table { border-collapse:collapse; width:100%; margin:0.75em 0; font-size:13px; }
      .md-prose th,.md-prose td { border:1px solid var(--border,#e5e7eb); padding:5px 10px; text-align:left; }
      .md-prose th { background:var(--muted,#f3f4f6); font-weight:600; }
      .md-prose blockquote { border-left:3px solid var(--border,#e5e7eb); margin:0.75em 0; padding:4px 12px; color:var(--muted-foreground,#6b7280); }
      .md-prose a { color:var(--primary,#6366f1); text-decoration:underline; }
      .md-prose hr { border:none; border-top:1px solid var(--border,#e5e7eb); margin:1em 0; }
      .md-stream-cursor { animation:md-pulse 0.9s ease-in-out infinite; display:inline-block; }
    `;
    document.head.appendChild(s);
  }, []);

  // ── 工具函數 ──
  function execCommandCopy(text, onSuccess) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;top:0;left:0;width:2em;height:2em;opacity:0;border:none;outline:none;";
    document.body.appendChild(ta);
    ta.focus();
    ta.setSelectionRange(0, ta.value.length);
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) {}
    document.body.removeChild(ta);
    if (ok) onSuccess();
  }

  function copyToClipboard(text, onSuccess) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(onSuccess).catch(() => execCommandCopy(text, onSuccess));
    } else {
      execCommandCopy(text, onSuccess);
    }
  }

  function handleCopy() {
    const md = currentItem.markdown_content || extractPartialContent(partial);
    copyToClipboard(md, () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  // ── 樣式常數 ──
  const btnStyle = {
    padding:     "3px 10px",
    fontSize:    "11px",
    borderRadius:"6px",
    border:      "1px solid var(--border, #e5e7eb)",
    background:  "transparent",
    color:       "var(--muted-foreground, #6b7280)",
    cursor:      "pointer",
    lineHeight:  "1.6",
    whiteSpace:  "nowrap",
  };

  // ── 串流狀態 UI ──
  const partialText = isStreaming ? extractPartialContent(partial) : "";
  const charCount   = partial ? partial.length : 0;

  return React.createElement(
    "div",
    {
      style: {
        display:       "flex",
        flexDirection: "column",
        height:        "100%",
        minHeight:     "520px",
        overflow:      "hidden",
      },
    },

    // ── 工具列 ──
    React.createElement(
      "div",
      {
        style: {
          display:        "flex",
          alignItems:     "center",
          justifyContent: "space-between",
          padding:        "6px 10px",
          borderBottom:   "1px solid var(--border, #e5e7eb)",
          background:     "var(--card, #fff)",
          flexShrink:     0,
          gap:            "8px",
        },
      },

      // 左側：標題 + 版本選單
      React.createElement(
        "div",
        { style: { display: "flex", alignItems: "center", gap: "6px", minWidth: 0, flex: 1 } },

        React.createElement(
          "span",
          {
            style: {
              fontSize:     "12px",
              fontWeight:   600,
              color:        "var(--foreground, #111)",
              overflow:     "hidden",
              textOverflow: "ellipsis",
              whiteSpace:   "nowrap",
              maxWidth:     "180px",
            },
          },
          isStreaming ? (props.title || "文件 — 生成中…") : currentItem.title
        ),

        !isStreaming && historyMeta.length > 1 &&
          React.createElement(
            "select",
            {
              value:    currentIndex,
              onChange: (e) => setCurrentIndex(Number(e.target.value)),
              style: {
                fontSize:     "11px",
                padding:      "2px 4px",
                borderRadius: "5px",
                border:       "1px solid var(--border, #e5e7eb)",
                background:   "var(--muted, #f9fafb)",
                color:        "var(--muted-foreground, #6b7280)",
                cursor:       "pointer",
                maxWidth:     "150px",
              },
            },
            ...historyMeta.map((h, idx) =>
              React.createElement(
                "option",
                { key: h.md_id, value: idx },
                idx === 0
                  ? `v${historyMeta.length}（最新）`
                  : `v${historyMeta.length - idx} — ${h.title.slice(0, 12)}`
              )
            )
          )
      ),

      // 右側：按鈕群
      React.createElement(
        "div",
        { style: { display: "flex", gap: "5px", flexShrink: 0 } },
        React.createElement("button", { onClick: handleCopy, style: btnStyle }, copied ? "✓ 已複製" : "複製")
      )
    ),

    // ── 內容區 ──
    React.createElement(
      "div",
      {
        style: {
          flex:       1,
          overflowY:  "auto",
          padding:    "14px 16px",
          background: "var(--background, #fff)",
        },
      },

      // 串流狀態：顯示部分原文 + 游標
      isStreaming && React.createElement(
        "div",
        null,
        React.createElement(
          "div",
          {
            style: {
              fontSize:     "11px",
              color:        "var(--muted-foreground, #6b7280)",
              marginBottom: "10px",
              display:      "flex",
              alignItems:   "center",
              gap:          "6px",
            },
          },
          React.createElement(
            "span",
            { style: { animation: "md-pulse 0.9s ease-in-out infinite", display: "inline-block" } },
            "●"
          ),
          `正在生成… 已接收 ${charCount} 字元`
        ),
        partialText && React.createElement(
          "pre",
          {
            ref: (el) => { if (el) el.scrollTop = el.scrollHeight; },
            style: {
              whiteSpace:   "pre-wrap",
              wordBreak:    "break-word",
              fontFamily:   "monospace",
              fontSize:     "13px",
              lineHeight:   "1.6",
              color:        "var(--foreground, #111)",
              background:   "var(--muted, #f3f4f6)",
              borderRadius: "6px",
              padding:      "10px 12px",
              margin:       0,
            },
          },
          partialText,
          React.createElement("span", { className: "md-stream-cursor" }, "▌")
        )
      ),

      // ready 狀態：完整 markdown 渲染
      !isStreaming && React.createElement(
        "div",
        {
          key:                    currentItem.md_id,
          className:              "md-prose",
          dangerouslySetInnerHTML:{ __html: renderedHtml },
        }
      )
    )
  );
}
