export default function HtmlRenderer() {
  const historyData  = props.history_data || [];
  const historyMeta  = props.history      || [];
  const initialHtml  = props.html_code    || "";
  const initialTitle = props.title        || "Artifact";

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

  function handleCopy() {
    navigator.clipboard.writeText(currentItem.html_code).then(() => {
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
    navigator.clipboard.writeText(publishedUrl).then(() => {
      setUrlCopied(true);
      setTimeout(() => setUrlCopied(false), 2000);
    });
  }

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

    // ── iframe 渲染區 ──
    React.createElement("iframe", {
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
