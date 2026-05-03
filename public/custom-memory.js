// 記憶管理 — 菜單注入 + 完整 Modal UI
// 後端 API: /api/memory/*  (Chainlit JWT cookie 驗證)

(function () {
  "use strict";

  const API_BASE = "/api/memory";
  const MENU_ITEM_ID = "memory-manager-menu-item";
  const MODAL_ID = "memory-manager-modal";

  const TYPE_OPTIONS = [
    { value: "user",      label: "使用者資料 (User)",    bg: "#dbeafe", color: "#1e40af" },
    { value: "feedback",  label: "工作回饋 (Feedback)",  bg: "#dcfce7", color: "#15803d" },
    { value: "project",   label: "專案資訊 (Project)",   bg: "#fef9c3", color: "#854d0e" },
    { value: "reference", label: "參考來源 (Reference)", bg: "#f3e8ff", color: "#7e22ce" },
  ];

  // ─── API ─────────────────────────────────────────────────────────────────────

  async function apiFetch(path, opts = {}) {
    const res = await fetch(API_BASE + path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return res.json();
  }

  const api = {
    list:   ()        => apiFetch("/list"),
    read:   (f)       => apiFetch(`/file/${encodeURIComponent(f)}`),
    create: (data)    => apiFetch("", { method: "POST", body: JSON.stringify(data) }),
    update: (f, data) => apiFetch(`/file/${encodeURIComponent(f)}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (f)       => apiFetch(`/file/${encodeURIComponent(f)}`, { method: "DELETE" }),
  };

  // ─── DOM helpers ─────────────────────────────────────────────────────────────

  function el(tag, styleObj, ...children) {
    const e = document.createElement(tag);
    if (styleObj) Object.assign(e.style, styleObj);
    for (const c of children) {
      if (c == null) continue;
      e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return e;
  }

  function badge(type) {
    const t = TYPE_OPTIONS.find(o => o.value === type) || { bg: "#f3f4f6", color: "#374151" };
    const s = el("span", {
      background: t.bg, color: t.color, borderRadius: "4px",
      padding: "1px 7px", fontSize: "11px", fontWeight: "600",
      letterSpacing: "0.02em", whiteSpace: "nowrap", flexShrink: "0",
    }, type || "—");
    return s;
  }

  function labelDiv(text) {
    return el("div", {
      fontSize: "11px", fontWeight: "700", color: "var(--muted-foreground,#6b7280)",
      textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "3px",
    }, text);
  }

  function inputField(placeholder, value = "") {
    const i = document.createElement("input");
    i.type = "text";
    i.placeholder = placeholder;
    i.value = value;
    Object.assign(i.style, {
      width: "100%", padding: "7px 10px",
      border: "1px solid var(--border,#e5e7eb)", borderRadius: "6px",
      fontSize: "13px", background: "var(--background,#fff)",
      color: "var(--foreground,#111)", outline: "none",
      boxSizing: "border-box", marginBottom: "8px", fontFamily: "inherit",
    });
    return i;
  }

  function btn(text, primary, danger) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    Object.assign(b.style, {
      padding: "6px 16px",
      border: primary ? "none" : `1px solid ${danger ? "#ef4444" : "#e5e7eb"}`,
      borderRadius: "6px", fontSize: "13px", fontWeight: "600", cursor: "pointer",
      background: primary ? "hsl(var(--primary))" : "transparent",
      color: primary ? "hsl(var(--primary-foreground,0 0% 100%))" : danger ? "#ef4444" : "#6b7280",
      fontFamily: "inherit", flexShrink: "0",
    });
    return b;
  }

  // 輕量 Markdown → HTML（處理標題、粗體、斜體、程式碼、清單、換行）
  function renderMd(md) {
    if (!md) return "";
    // 先按行處理，再組合
    const lines = md.split("\n");
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      // 無序清單：收集連續的 "- " 或 "* " 行
      if (/^[-*] /.test(line)) {
        const items = [];
        while (i < lines.length && /^[-*] /.test(lines[i])) {
          items.push("<li style='margin:3px 0'>" + inlineMd(lines[i].replace(/^[-*] /, "")) + "</li>");
          i++;
        }
        out.push("<ul style='margin:6px 0;padding-left:20px;list-style-type:disc'>" + items.join("") + "</ul>");
        continue;
      }
      // 有序清單：收集連續的 "N. " 行
      if (/^\d+\. /.test(line)) {
        const items = [];
        while (i < lines.length && /^\d+\. /.test(lines[i])) {
          items.push("<li style='margin:3px 0'>" + inlineMd(lines[i].replace(/^\d+\. /, "")) + "</li>");
          i++;
        }
        out.push("<ol style='margin:6px 0;padding-left:20px;list-style-type:decimal'>" + items.join("") + "</ol>");
        continue;
      }
      // 標題
      if (/^### /.test(line)) { out.push("<h3 style='margin:12px 0 4px;font-size:14px;font-weight:700'>" + inlineMd(line.slice(4)) + "</h3>"); i++; continue; }
      if (/^## /.test(line))  { out.push("<h2 style='margin:14px 0 5px;font-size:15px;font-weight:700'>" + inlineMd(line.slice(3)) + "</h2>"); i++; continue; }
      if (/^# /.test(line))   { out.push("<h1 style='margin:16px 0 6px;font-size:17px;font-weight:700'>" + inlineMd(line.slice(2)) + "</h1>"); i++; continue; }
      // 空行
      if (line.trim() === "") { out.push("<br>"); i++; continue; }
      // 普通行
      out.push("<p style='margin:2px 0'>" + inlineMd(line) + "</p>");
      i++;
    }
    return out.join("");
  }

  function inlineMd(text) {
    return text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code style='background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:12px;font-family:monospace'>$1</code>");
  }

  function toast(msg, isError) {
    const t = el("div", {
      position: "fixed", top: "24px", left: "50%", transform: "translateX(-50%)",
      background: isError ? "#fee2e2" : "#dcfce7",
      color: isError ? "#991b1b" : "#15803d",
      padding: "7px 18px", borderRadius: "6px", fontSize: "13px", fontWeight: "600",
      boxShadow: "0 2px 8px rgba(0,0,0,0.15)", zIndex: "2147483647",
      pointerEvents: "none", whiteSpace: "nowrap",
    }, msg);
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2500);
  }

  // ─── State ───────────────────────────────────────────────────────────────────

  let state = { files: [], selectedFile: null, mode: "empty", listLoading: false };
  let overlay, modal, listPane, detailPane;

  // ─── Build Modal ──────────────────────────────────────────────────────────────

  function buildModal() {
    if (document.getElementById(MODAL_ID)) return;

    // Overlay — 插入 <body> 最末，position:fixed 從 viewport 原點開始
    overlay = el("div", {
      position: "fixed", top: "0", left: "0", width: "100vw", height: "100vh",
      background: "rgba(0,0,0,0.6)",
      zIndex: "2147483646",
      display: "flex", alignItems: "center", justifyContent: "center",
    });
    overlay.id = MODAL_ID;
    overlay.addEventListener("click", e => { if (e.target === overlay) closeModal(); });

    // Modal card
    modal = el("div", {
      width: "min(96vw,1060px)", height: "min(92vh,760px)",
      background: "#ffffff",
      borderRadius: "12px",
      border: "1px solid #e5e7eb",
      boxShadow: "0 12px 48px rgba(0,0,0,0.22)",
      display: "flex", flexDirection: "column", overflow: "hidden", position: "relative",
      zIndex: "2147483647",
    });

    // Header
    const titleSpan = el("span", {
      fontSize: "15px", fontWeight: "700", color: "#111827",
    }, "記憶管理");

    const addBtn = btn("新增", true, false);
    addBtn.addEventListener("click", () => openNewForm());

    const closeBtn = btn("✕", false, false);
    closeBtn.style.padding = "4px 10px";
    closeBtn.addEventListener("click", closeModal);

    const headerRight = el("div", { display: "flex", alignItems: "center", gap: "8px" });
    headerRight.append(addBtn, closeBtn);

    const header = el("div", {
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "13px 18px", borderBottom: "1px solid #e5e7eb", flexShrink: "0",
      background: "#ffffff",
    }, titleSpan, headerRight);

    // List pane
    listPane = el("div", {
      width: "290px", minWidth: "260px", flexShrink: "0",
      borderRight: "1px solid #e5e7eb",
      display: "flex", flexDirection: "column", height: "100%", overflow: "hidden",
      background: "#ffffff",
    });

    // Detail pane
    detailPane = el("div", {
      flex: "1", overflow: "hidden", display: "flex", flexDirection: "column",
      background: "#ffffff",
    });

    const body = el("div", { display: "flex", flex: "1", overflow: "hidden" });
    body.append(listPane, detailPane);

    modal.append(header, body);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  }

  // ─── List Pane ───────────────────────────────────────────────────────────────

  // itemsEl 提升為 closure 變數，讓 updateListSelection 也能存取
  let itemsEl = null;

  function renderList() {
    listPane.innerHTML = "";

    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "搜尋記憶...";
    Object.assign(searchInput.style, {
      width: "100%", padding: "7px 10px",
      border: "1px solid #e5e7eb", borderRadius: "6px",
      fontSize: "13px", background: "#fff", color: "#111",
      outline: "none", boxSizing: "border-box", fontFamily: "inherit",
    });
    const searchWrap = el("div", { padding: "10px 12px", borderBottom: "1px solid #e5e7eb" });
    searchWrap.appendChild(searchInput);
    listPane.appendChild(searchWrap);

    itemsEl = el("div", { flex: "1", overflowY: "auto", padding: "4px 0" });
    listPane.appendChild(itemsEl);

    function renderItems(q) {
      itemsEl.innerHTML = "";
      q = (q || "").toLowerCase();
      const filtered = state.files.filter(f =>
        f.name.toLowerCase().includes(q) ||
        (f.description || "").toLowerCase().includes(q) ||
        (f.type || "").toLowerCase().includes(q)
      );

      if (state.listLoading) {
        itemsEl.appendChild(el("div", { padding: "24px", textAlign: "center", color: "#6b7280", fontSize: "13px" }, "載入中..."));
        return;
      }
      if (filtered.length === 0) {
        itemsEl.appendChild(el("div", { padding: "24px", textAlign: "center", color: "#6b7280", fontSize: "13px" },
          q ? "無符合結果" : "尚無記憶檔案"));
        return;
      }
      for (const f of filtered) {
        const sel = state.selectedFile && state.selectedFile.filename === f.filename;
        const row = el("div", {
          padding: "9px 14px", cursor: "pointer",
          background: sel ? "#f3f4f6" : "transparent",
          borderLeft: sel ? "3px solid var(--primary,#6366f1)" : "3px solid transparent",
        });
        row.dataset.filename = f.filename;
        row.addEventListener("click", () => selectFile(f.filename));
        row.addEventListener("mouseenter", () => { if (row.dataset.selected !== "1") row.style.background = "#f9fafb"; });
        row.addEventListener("mouseleave", () => { if (row.dataset.selected !== "1") row.style.background = "transparent"; });
        if (sel) row.dataset.selected = "1";

        const topRow = el("div", { display: "flex", alignItems: "center", gap: "6px", marginBottom: "2px" });
        topRow.appendChild(el("span", { fontWeight: "600", fontSize: "13px", color: "#111827", flex: "1", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, f.name));
        topRow.appendChild(badge(f.type));
        row.appendChild(topRow);

        if (f.description) {
          row.appendChild(el("div", { fontSize: "11px", color: "#6b7280", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, f.description));
        }
        itemsEl.appendChild(row);
      }
    }

    searchInput.addEventListener("input", () => renderItems(searchInput.value));
    renderItems("");
  }

  // 只更新選中狀態樣式，不重建 DOM，scrollTop 不受影響
  function updateListSelection(filename) {
    if (!itemsEl) return;
    for (const row of itemsEl.querySelectorAll("[data-filename]")) {
      const isSel = row.dataset.filename === filename;
      row.dataset.selected = isSel ? "1" : "";
      row.style.background = isSel ? "#f3f4f6" : "transparent";
      row.style.borderLeft = isSel ? "3px solid var(--primary,#6366f1)" : "3px solid transparent";
    }
  }

  // ─── Detail: Empty ───────────────────────────────────────────────────────────

  function renderEmpty() {
    detailPane.innerHTML = "";
    const wrap = el("div", {
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", height: "100%", gap: "12px", color: "#6b7280",
    });
    wrap.appendChild(el("div", { fontSize: "14px", fontWeight: "600" }, "選擇記憶檔案或新增記憶"));
    const nb = btn("新增記憶", true, false);
    nb.addEventListener("click", () => openNewForm());
    wrap.appendChild(nb);
    detailPane.appendChild(wrap);
  }

  // ─── Detail: View ────────────────────────────────────────────────────────────

  function renderView(mem) {
    detailPane.innerHTML = "";
    const wrap = el("div", {
      display: "flex", flexDirection: "column", height: "100%",
      padding: "18px 22px", overflowY: "auto", boxSizing: "border-box",
    });

    const titleRow = el("div", { display: "flex", alignItems: "flex-start", gap: "10px", marginBottom: "6px" });
    const titleWrap = el("div", { flex: "1" });
    titleWrap.appendChild(el("h3", { margin: "0 0 3px", fontSize: "15px", fontWeight: "700", color: "#111827" }, mem.name));
    if (mem.description) titleWrap.appendChild(el("div", { fontSize: "13px", color: "#6b7280" }, mem.description));
    titleRow.append(titleWrap, badge(mem.type));
    wrap.appendChild(titleRow);
    wrap.appendChild(el("div", { fontSize: "11px", color: "#9ca3af", marginBottom: "14px", fontFamily: "monospace" }, mem.filename));

    // 渲染 Markdown
    const mdView = el("div", {
      flex: "1", background: "#f9fafb", border: "1px solid #e5e7eb",
      borderRadius: "8px", padding: "14px 16px", fontSize: "13px", lineHeight: "1.7",
      overflow: "auto", color: "#111827", margin: "0 0 16px", minHeight: "80px",
      wordBreak: "break-word",
    });
    if (mem.content) {
      mdView.innerHTML = renderMd(mem.content);
    } else {
      mdView.appendChild(el("span", { color: "#9ca3af" }, "（無內容）"));
    }
    wrap.appendChild(mdView);

    const actions = el("div", { display: "flex", gap: "8px", flexWrap: "wrap" });
    const editBtn = btn("編輯", true, false);
    editBtn.addEventListener("click", () => openEditForm(mem));

    const delBtn = btn("刪除", false, true);
    let confirmMode = false;
    delBtn.addEventListener("click", () => {
      if (!confirmMode) {
        confirmMode = true;
        delBtn.textContent = "確定刪除？";
        delBtn.style.background = "#ef4444";
        delBtn.style.color = "#fff";
        setTimeout(() => {
          confirmMode = false;
          delBtn.textContent = "刪除";
          delBtn.style.background = "transparent";
          delBtn.style.color = "#ef4444";
        }, 3000);
      } else {
        handleDelete(mem.filename);
      }
    });

    actions.append(editBtn, delBtn);
    wrap.appendChild(actions);
    detailPane.appendChild(wrap);
  }

  // ─── Detail: Form ────────────────────────────────────────────────────────────

  function renderForm(mem, isNew) {
    detailPane.innerHTML = "";
    const wrap = el("div", {
      display: "flex", flexDirection: "column", height: "100%",
      padding: "18px 22px", overflowY: "auto", boxSizing: "border-box",
    });

    wrap.appendChild(el("h3", {
      margin: "0 0 14px", fontSize: "14px", fontWeight: "700", color: "#111827",
    }, isNew ? "新增記憶" : "編輯記憶"));

    wrap.appendChild(labelDiv("名稱 *"));
    const nameInput = inputField("記憶名稱（必填）", mem.name || "");
    wrap.appendChild(nameInput);

    wrap.appendChild(labelDiv("描述"));
    const descInput = inputField("一行簡短描述，幫助 AI 判斷相關性", mem.description || "");
    wrap.appendChild(descInput);

    wrap.appendChild(labelDiv("類型"));
    const typeSelect = document.createElement("select");
    Object.assign(typeSelect.style, {
      width: "100%", padding: "7px 10px",
      border: "1px solid #e5e7eb", borderRadius: "6px",
      fontSize: "13px", background: "#fff", color: "#111",
      outline: "none", boxSizing: "border-box", marginBottom: "8px",
      cursor: "pointer", fontFamily: "inherit",
    });
    for (const t of TYPE_OPTIONS) {
      const opt = document.createElement("option");
      opt.value = t.value; opt.textContent = t.label;
      if (t.value === (mem.type || "user")) opt.selected = true;
      typeSelect.appendChild(opt);
    }
    wrap.appendChild(typeSelect);

    wrap.appendChild(labelDiv("內容（Markdown）"));
    const textarea = document.createElement("textarea");
    textarea.placeholder = "記憶內容，支援 Markdown 格式...";
    textarea.value = mem.content || "";
    Object.assign(textarea.style, {
      width: "100%", padding: "9px 10px",
      border: "1px solid #e5e7eb", borderRadius: "6px",
      fontSize: "13px", background: "#fff", color: "#111",
      outline: "none", boxSizing: "border-box", marginBottom: "4px",
      resize: "vertical", minHeight: "180px", flex: "1",
      fontFamily: "ui-monospace,monospace", lineHeight: "1.55",
    });
    wrap.appendChild(textarea);

    const byteCounter = el("div", {
      fontSize: "11px", textAlign: "right", marginBottom: "12px", color: "#6b7280",
    });
    function updateCounter() {
      const bytes = new TextEncoder().encode(textarea.value).length;
      const over = bytes > 4096;
      byteCounter.textContent = `${bytes} / 4096 bytes${over ? "  超過上限" : ""}`;
      byteCounter.style.color = over ? "#ef4444" : "#6b7280";
      textarea.style.borderColor = over ? "#ef4444" : "#e5e7eb";
    }
    textarea.addEventListener("input", updateCounter);
    updateCounter();
    wrap.appendChild(byteCounter);

    const errorArea = el("div", {
      display: "none", padding: "7px 12px", background: "#fee2e2",
      color: "#991b1b", borderRadius: "6px", fontSize: "13px", marginBottom: "10px",
    });
    wrap.appendChild(errorArea);

    const actions = el("div", { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" });
    const saveBtn = btn("儲存", true, false);
    saveBtn.addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) { nameInput.focus(); return; }
      const bytes = new TextEncoder().encode(textarea.value).length;
      if (bytes > 4096) {
        errorArea.textContent = "內容超過 4096 bytes 上限";
        errorArea.style.display = "block";
        return;
      }
      errorArea.style.display = "none";

      let filename = mem.filename;
      if (isNew) filename = name.toLowerCase().replace(/\s+/g, "_").replace(/[^\w\-]/g, "") + ".md";

      saveBtn.disabled = true; saveBtn.style.opacity = "0.6"; saveBtn.textContent = "儲存中...";
      try {
        const payload = { filename, name, description: descInput.value.trim(), type: typeSelect.value, content: textarea.value };
        if (isNew) await api.create(payload);
        else await api.update(filename, payload);

        state.selectedFile = await api.read(filename);
        await loadFiles();
        state.mode = "view";
        renderList();
        renderView(state.selectedFile);
        toast(isNew ? "已新增記憶" : "已更新記憶", false);
      } catch (e) {
        errorArea.textContent = "儲存失敗：" + e.message;
        errorArea.style.display = "block";
        saveBtn.disabled = false; saveBtn.style.opacity = "1"; saveBtn.textContent = "儲存";
      }
    });

    const cancelBtn = btn("取消", false, false);
    cancelBtn.addEventListener("click", () => {
      if (state.selectedFile) { state.mode = "view"; renderView(state.selectedFile); }
      else { state.mode = "empty"; renderEmpty(); }
    });

    actions.append(saveBtn, cancelBtn);
    wrap.appendChild(actions);
    detailPane.appendChild(wrap);
  }

  // ─── Actions ─────────────────────────────────────────────────────────────────

  async function loadFiles() {
    state.listLoading = true;
    try {
      const { files } = await api.list();
      state.files = files || [];
    } catch (e) {
      console.error("[memory] 載入記憶列表失敗:", e.message);
      state.files = [];
    } finally {
      state.listLoading = false;
    }
  }

  async function selectFile(filename) {
    try {
      state.selectedFile = await api.read(filename);
      state.mode = "view";
      updateListSelection(filename);  // 只更新樣式，不重建 DOM
      renderView(state.selectedFile);
    } catch (e) {
      toast("讀取失敗：" + e.message, true);
    }
  }

  function openNewForm()       { state.mode = "new";  renderForm({}, true); }
  function openEditForm(mem)   { state.mode = "edit"; renderForm(mem, false); }

  async function handleDelete(filename) {
    try {
      await api.delete(filename);
      state.selectedFile = null; state.mode = "empty";
      await loadFiles(); renderList(); renderEmpty();
      toast("已刪除記憶", false);
    } catch (e) {
      toast("刪除失敗：" + e.message, true);
    }
  }

  // ─── Open / Close ─────────────────────────────────────────────────────────────

  async function openModal() {
    buildModal();
    overlay.style.display = "flex";
    // 鎖定所有捲動層
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";

    state.selectedFile = null; state.mode = "empty";
    await loadFiles();
    renderList();
    renderEmpty();
  }

  function closeModal() {
    if (overlay) overlay.style.display = "none";
    document.documentElement.style.overflow = "";
    document.body.style.overflow = "";
  }

  window.__openMemoryManager = openModal;

  // ─── Menu injection ───────────────────────────────────────────────────────────

  function createMenuItem() {
    const item = document.createElement("button");
    item.id = MENU_ITEM_ID;
    item.type = "button";
    const lang = document.documentElement.lang || navigator.language || "en";
    item.textContent = lang.startsWith("zh") ? "記憶管理" : "Memory";
    Object.assign(item.style, {
      display: "flex", alignItems: "center", width: "100%",
      padding: "8px 12px", background: "transparent", border: "none",
      borderRadius: "4px", fontSize: "14px", fontWeight: "500",
      color: "var(--foreground,#111)", cursor: "pointer",
      whiteSpace: "nowrap", fontFamily: "inherit",
    });
    item.addEventListener("mouseenter", () => { item.style.background = "var(--accent,#f3f4f6)"; });
    item.addEventListener("mouseleave", () => { item.style.background = "transparent"; });
    item.addEventListener("click", e => {
      e.preventDefault(); e.stopPropagation();
      // 用 Escape 關閉 Radix UI 選單，再開 modal
      const trigger = document.getElementById("user-nav-button");
      if (trigger) trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      // 等選單動畫結束後再開 modal，避免選單殘留攔截點擊
      setTimeout(openModal, 80);
    });
    return item;
  }

  function tryInjectMenu(mutations) {
    // 只在有新節點加入時才檢查，且 user-nav-button 必須是展開狀態
    const trigger = document.getElementById("user-nav-button");
    if (!trigger || trigger.getAttribute("aria-expanded") !== "true") return;
    const menu = document.querySelector('[role="menu"]');
    if (!menu || menu.querySelector("#" + MENU_ITEM_ID)) return;
    menu.insertBefore(createMenuItem(), menu.firstElementChild);
  }

  function startObserver() {
    // 找 user-nav-button 的父層來縮小監聽範圍；找不到才 fallback 到 body
    const trigger = document.getElementById("user-nav-button");
    const root = (trigger && trigger.closest("header, nav, [data-testid]")) || document.body;
    const observer = new MutationObserver(tryInjectMenu);
    observer.observe(root, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver);
  } else {
    startObserver();
  }

})();
