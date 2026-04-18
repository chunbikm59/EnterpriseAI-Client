export default function SessionHistory() {
  const sessions = props.sessions || [];
  const offset = props.offset ?? 0;
  const limit = props.limit ?? 10;
  const total = props.total ?? sessions.length;
  const hasMore = props.has_more ?? false;

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  const hasPrev = offset > 0;

  function formatLabel(s) {
    if (s.title) return s.title;
    const ts = s.started_at || s.last_edited_at || "";
    return ts ? ts.slice(0, 16).replace("T", " ") : "未命名對話";
  }

  function formatTime(s) {
    const ts = s.last_edited_at || s.started_at || "";
    return ts ? ts.slice(0, 16).replace("T", " ") : "";
  }

  return (
    <div className="flex flex-col gap-1 p-3 rounded-lg border border-border bg-card w-full max-w-xl">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold text-muted-foreground">歷史對話</div>
        {totalPages > 1 && (
          <div className="text-xs text-muted-foreground">第 {currentPage} / {totalPages} 頁</div>
        )}
      </div>

      {sessions.length === 0 && (
        <div className="text-sm text-muted-foreground px-1">沒有歷史對話記錄。</div>
      )}

      {sessions.map((s) => (
        <button
          key={s.session_id}
          className="flex items-center gap-2 px-3 py-2 rounded-md text-sm hover:bg-accent transition-colors text-left w-full"
          onClick={() => callAction({ name: "load_session", payload: { file_path: s.file_path } })}
        >
          <span className="flex-1 text-foreground truncate">{formatLabel(s)}</span>
          <span className="text-muted-foreground text-xs shrink-0 ml-2">{formatTime(s)}</span>
          <span className="text-muted-foreground text-xs shrink-0">{s.message_count} 則</span>
        </button>
      ))}

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-2 pt-2 border-t border-border">
          <button
            className="px-3 py-1 text-xs rounded-md border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            disabled={!hasPrev}
            onClick={() => callAction({ name: "change_session_page", payload: { offset: offset - limit } })}
          >
            上一頁
          </button>
          <span className="text-xs text-muted-foreground">共 {total} 筆</span>
          <button
            className="px-3 py-1 text-xs rounded-md border border-border hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            disabled={!hasMore}
            onClick={() => callAction({ name: "change_session_page", payload: { offset: offset + limit } })}
          >
            下一頁
          </button>
        </div>
      )}
    </div>
  );
}
