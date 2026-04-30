export default function HtmlRenderer() {
  const historyData  = props.history_data || [];
  const historyMeta  = props.history      || [];
  const initialHtml  = props.html_code    || "";
  const initialTitle = props.title        || "Artifact";

  // 串流狀態：html_code === null 且有 partial
  const partial     = props.html_code_partial || null;
  const isStreaming = props.html_code === null && !!partial;

  // 從 JSON 前綴解析出已接收的部分 HTML
  function extractPartialHtml(raw) {
    if (!raw) return "";
    const match = raw.match(/"html_code"\s*:\s*"([\s\S]*)/);
    if (!match) return "";
    let s = match[1];
    s = s.replace(/\\\\/g, "\x00BS\x00")
         .replace(/\\n/g, "\n")
         .replace(/\\t/g, "\t")
         .replace(/\\r/g, "\r")
         .replace(/\\"/g, '"')
         .replace(/\x00BS\x00/g, "\\");
    return s;
  }

  const streamHtml = isStreaming ? extractPartialHtml(partial) : "";

  // 初始 index 由 props.current_index 決定（element remount 時保留目前選取版本）
  const initialIndex = typeof props.current_index === "number" ? props.current_index : 0;
  const [currentIndex, setCurrentIndex]       = React.useState(initialIndex);
  const [copied, setCopied]                   = React.useState(false);
  const [publishing, setPublishing]           = React.useState(false);
  const [urlCopied, setUrlCopied]             = React.useState(false);
  const [localPublishedUrls, setLocalPublishedUrls] = React.useState({});

  // 只在 history 新增版本（最新版 artifact_id 變更）時跳回最新版；首次 mount 不觸發
  const latestArtifactId = historyData[0] && historyData[0].artifact_id;
  const prevLatestIdRef = React.useRef(latestArtifactId);
  React.useEffect(() => {
    if (prevLatestIdRef.current !== latestArtifactId) {
      prevLatestIdRef.current = latestArtifactId;
      setCurrentIndex(0);
    }
  }, [latestArtifactId]);

  const currentItem = historyData[currentIndex] || {
    artifact_id: props.artifact_id || "init",
    html_code:   initialHtml,
    title:       initialTitle,
  };

  const publishedUrl =
    localPublishedUrls[currentItem.artifact_id] ||
    currentItem.published_url ||
    null;

  const iframeSandbox = [
    "allow-scripts",
    "allow-same-origin",
    "allow-forms",
    "allow-popups",
    "allow-modals",
  ].join(" ");

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
    copyToClipboard(currentItem.html_code, () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function handleOpenNew() {
    const blob = new Blob([currentItem.html_code], { type: "text/html" });
    const url  = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  async function handlePublish() {
    setPublishing(true);
    try {
      const res = await callAction({
        name: "publish_artifact",
        payload: { artifact_id: currentItem.artifact_id, title: currentItem.title },
      });
      const url = res && res.response && res.response.published_url;
      if (url) {
        setLocalPublishedUrls((prev) => ({
          ...prev,
          [currentItem.artifact_id]: url,
        }));
      }
    } finally {
      setPublishing(false);
    }
  }

  function handleCopyUrl() {
    copyToClipboard(publishedUrl, () => {
      setUrlCopied(true);
      setTimeout(() => setUrlCopied(false), 2000);
    });
  }

  // 注入串流動畫 CSS（只注入一次）
  React.useEffect(() => {
    if (document.getElementById("html-renderer-style")) return;
    const s = document.createElement("style");
    s.id = "html-renderer-style";
    s.textContent = `@keyframes html-pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }`;
    document.head.appendChild(s);
  }, []);

  // ── 樣式常數 ──
  const btnStyle = {
    padding: "3px 10px",
    fontSize: "11px",
    borderRadius: "6px",
    border: "1px solid var(--border, #e5e7eb)",
    background: "transparent",
    color: "var(--muted-foreground, #6b7280)",
    cursor: "pointer",
    lineHeight: "1.6",
    whiteSpace: "nowrap",
  };

  const publishedBtnStyle = {
    ...btnStyle,
    color: "var(--primary, #6366f1)",
    borderColor: "var(--primary, #6366f1)",
  };

  return React.createElement(
    "div",
    {
      style: {
        display:       "flex",
        flexDirection: "column",
        height:        "100%",
        minHeight:     "520px",
        overflow:      "hidden",
        position:      "relative",
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
          currentItem.title
        ),

        historyMeta.length > 1 &&
          React.createElement(
            "select",
            {
              value:    currentIndex,
              onChange: (e) => setCurrentIndex(Number(e.target.value)),
              style: {
                fontSize:    "11px",
                padding:     "2px 4px",
                borderRadius:"5px",
                border:      "1px solid var(--border, #e5e7eb)",
                background:  "var(--muted, #f9fafb)",
                color:       "var(--muted-foreground, #6b7280)",
                cursor:      "pointer",
                maxWidth:    "150px",
              },
            },
            ...historyMeta.map((h, idx) =>
              React.createElement(
                "option",
                { key: h.artifact_id, value: idx },
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

        React.createElement("button", { onClick: handleCopy,    style: btnStyle }, copied ? "✓ 已複製" : "複製"),
        React.createElement("button", { onClick: handleOpenNew, style: btnStyle }, "新分頁"),

        // 發布按鈕（未發布時顯示）
        !publishedUrl && React.createElement(
          "button",
          {
            onClick:  handlePublish,
            disabled: publishing,
            style:    { ...btnStyle, opacity: publishing ? 0.6 : 1, cursor: publishing ? "default" : "pointer" },
          },
          publishing ? "發布中…" : "發布"
        ),

        // 複製網址按鈕（已發布時顯示）
        publishedUrl && React.createElement(
          "button",
          { onClick: handleCopyUrl, style: publishedBtnStyle },
          urlCopied ? "✓ 已複製" : "複製網址"
        ),
      )
    ),

    // ── 串流狀態：顯示原始碼預覽（不用 iframe，避免重建閃爍）──
    isStreaming
      ? React.createElement(
          "div",
          {
            style: {
              flex:       1,
              display:    "flex",
              flexDirection: "column",
              overflow:   "hidden",
              background: "var(--muted, #f9fafb)",
            },
          },
          // 狀態列
          React.createElement(
            "div",
            {
              style: {
                padding:      "4px 12px",
                fontSize:     "11px",
                color:        "var(--primary, #6366f1)",
                background:   "rgba(99,102,241,0.06)",
                borderBottom: "1px solid rgba(99,102,241,0.15)",
                display:      "flex",
                alignItems:   "center",
                gap:          "6px",
                flexShrink:   0,
              },
            },
            React.createElement(
              "span",
              { style: { animation: "html-pulse 0.9s ease-in-out infinite", display: "inline-block" } },
              "●"
            ),
            `HTML 生成中… 已接收 ${partial ? partial.length : 0} 字元`
          ),
          // 原始碼預覽
          React.createElement(
            "pre",
            {
              style: {
                flex:       1,
                margin:     0,
                padding:    "12px 14px",
                fontSize:   "11px",
                lineHeight: "1.55",
                fontFamily: "monospace",
                color:      "var(--foreground, #111)",
                overflow:   "auto",
                whiteSpace: "pre-wrap",
                wordBreak:  "break-all",
              },
            },
            streamHtml,
            React.createElement("span", { style: { animation: "html-pulse 0.9s ease-in-out infinite", display: "inline-block" } }, "▌")
          )
        )

      // ── 完整版：iframe 渲染區 ──
      : React.createElement("iframe", {
          key:           currentItem.artifact_id + "_" + currentIndex,
          srcDoc:        currentItem.html_code,
          sandbox:       iframeSandbox,
          title:         currentItem.title,
          referrerPolicy:"no-referrer",
          style: {
            width:      "100%",
            flex:       1,
            border:     "none",
            background: "#fff",
            display:    "block",
            minHeight:  "460px",
          },
        })
  );
}
