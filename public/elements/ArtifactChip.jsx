export default function ArtifactChip() {
  const action  = props.action  || "reopen_artifact";
  const payload = props.payload || {};
  const title   = props.title   || "開啟";
  const icon    = props.icon    || "↗";
  const [clicked, setClicked] = React.useState(false);
  const [hovered, setHovered] = React.useState(false);

  function handleOpen() {
    setClicked(true);
    callAction({ name: action, payload });
    setTimeout(() => setClicked(false), 2000);
  }

  return React.createElement(
    "button",
    {
      onClick:      handleOpen,
      onMouseEnter: () => setHovered(true),
      onMouseLeave: () => setHovered(false),
      style: {
        display:       "inline-flex",
        flexDirection: "row",
        alignItems:    "center",
        gap:           "12px",
        padding:       "10px 14px",
        borderRadius:  "10px",
        border:        "1.5px solid " + (clicked ? "var(--primary, #6366f1)" : "var(--border, #e5e7eb)"),
        background:    hovered ? "var(--muted, #f5f5f5)" : "var(--card, #fafafa)",
        color:         "var(--foreground, #111)",
        cursor:        "pointer",
        transition:    "all 0.15s",
        textAlign:     "left",
        boxShadow:     "0 1px 4px rgba(0,0,0,0.10), 0 0 0 0.5px rgba(0,0,0,0.06)",
        minWidth:      "180px",
        maxWidth:      "280px",
      },
    },

    // 左側 icon 圓框
    React.createElement(
      "div",
      {
        style: {
          width:          "36px",
          height:         "36px",
          borderRadius:   "8px",
          background:     "var(--muted, #ededf0)",
          display:        "flex",
          alignItems:     "center",
          justifyContent: "center",
          fontSize:       "18px",
          flexShrink:     0,
        },
      },
      icon,
    ),

    // 右側文字
    React.createElement(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "2px", minWidth: 0, color: "#111" } },

      React.createElement(
        "div",
        {
          style: {
            fontSize:     "13px",
            fontWeight:   700,
            overflow:     "hidden",
            textOverflow: "ellipsis",
            whiteSpace:   "nowrap",
            color:        "#111",
          },
        },
        clicked ? "✓ " + title : title,
      ),

      React.createElement(
        "div",
        {
          style: {
            fontSize: "11px",
            color:    "#6b7280",
          },
        },
        clicked ? "側邊欄已開啟" : "點擊在側邊欄開啟",
      ),
    ),
  );
}
