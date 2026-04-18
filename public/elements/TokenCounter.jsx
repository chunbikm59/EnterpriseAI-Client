export default function TokenCounter() {
  const promptTokens = props.prompt_tokens ?? 0;
  const maxTokens = props.max_tokens ?? 128000;
  const pct = Math.round((promptTokens / maxTokens) * 100);
  const color = pct >= 85 ? '#dc2626' : pct >= 70 ? '#d97706' : 'currentColor';
  const opacity = pct >= 70 ? 1 : 0.4;

  return (
    <div style={{
      fontSize: '11px',
      color,
      opacity,
      textAlign: 'right',
      fontFamily: 'ui-monospace, monospace',
      paddingTop: '6px',
      lineHeight: 1,
      userSelect: 'none',
    }}>
      {promptTokens.toLocaleString()} / {maxTokens.toLocaleString()} tokens · {pct}%
    </div>
  );
}
