// Skill 管理 — 選單注入 + 三欄式 Modal（Skill 列表 / 目錄樹 / 檔案編輯器）
// 後端 API: /api/skills/*  (Chainlit JWT cookie 驗證)

(function () {
  "use strict";

  const API_BASE = "/api/skills";
  const MENU_ITEM_ID = "skill-manager-menu-item";
  const MODAL_ID = "skill-manager-modal";

  // ─── API ─────────────────────────────────────────────────────────────────────

  async function apiFetch(path, method, body) {
    const opts = {
      method: method || "GET",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return res.json();
  }

  async function apiUploadZip(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(API_BASE + "/upload-zip", {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return res.json();
  }

  const api = {
    list:        ()                     => apiFetch("/list"),
    createSkill: (name)                 => apiFetch("/skill", "POST", { skill_name: name }),
    deleteSkill: (name)                 => apiFetch(`/skill/${encodeURIComponent(name)}`, "DELETE"),
    tree:        (name)                 => apiFetch(`/skill/${encodeURIComponent(name)}/tree`),
    readFile:    (name, path)           => apiFetch(`/skill/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`),
    writeFile:   (name, path, content)  => apiFetch(`/skill/${encodeURIComponent(name)}/file`, "POST", { path, content }),
    deleteFile:  (name, path)           => apiFetch(`/skill/${encodeURIComponent(name)}/file`, "DELETE", { path }),
    createDir:   (name, path)           => apiFetch(`/skill/${encodeURIComponent(name)}/dir`, "POST", { path }),
    deleteDir:   (name, path)           => apiFetch(`/skill/${encodeURIComponent(name)}/dir`, "DELETE", { path }),
    uploadZip:   (file)                 => apiUploadZip(file),
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

  function btn(text, primary, danger) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    Object.assign(b.style, {
      padding: "5px 13px",
      border: primary ? "none" : `1px solid ${danger ? "#ef4444" : "#e5e7eb"}`,
      borderRadius: "5px", fontSize: "12px", fontWeight: "600", cursor: "pointer",
      background: primary ? "hsl(var(--primary,220 90% 56%))" : "transparent",
      color: primary ? "#fff" : danger ? "#ef4444" : "#6b7280",
      fontFamily: "inherit", flexShrink: "0",
    });
    return b;
  }

  function sourceBadge(source) {
    const isUser = source === "user";
    const s = el("span", {
      background: isUser ? "#dbeafe" : "#f3f4f6",
      color: isUser ? "#1e40af" : "#6b7280",
      borderRadius: "3px", padding: "1px 6px", fontSize: "10px", fontWeight: "700",
      whiteSpace: "nowrap", letterSpacing: "0.03em",
    }, isUser ? "user" : "system");
    return s;
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

  // 輕量 Markdown → HTML
  function inlineMd(text) {
    return text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code style='background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:12px;font-family:monospace'>$1</code>");
  }

  function renderMd(md) {
    if (!md) return "";
    const lines = md.split("\n");
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      // 表格：收集連續以 | 開頭（或含 |）的行，第二行為分隔行（---|---）
      if (/^\|/.test(line) && i + 1 < lines.length && /^\|[-| :]+\|/.test(lines[i + 1])) {
        const headerCells = line.split("|").slice(1, -1).map(c => c.trim());
        const alignLine = lines[i + 1].split("|").slice(1, -1).map(c => c.trim());
        const aligns = alignLine.map(a => {
          if (/^:.*:$/.test(a)) return "center";
          if (/^:/.test(a))    return "left";
          if (/:$/.test(a))    return "right";
          return "left";
        });
        const thead = "<thead><tr>" +
          headerCells.map((h, idx) =>
            `<th style='padding:6px 10px;border:1px solid #e5e7eb;background:#f9fafb;font-weight:700;text-align:${aligns[idx] || "left"}'>${inlineMd(h)}</th>`
          ).join("") + "</tr></thead>";
        i += 2;
        const bodyRows = [];
        while (i < lines.length && /^\|/.test(lines[i])) {
          const cells = lines[i].split("|").slice(1, -1).map(c => c.trim());
          bodyRows.push("<tr>" +
            cells.map((c, idx) =>
              `<td style='padding:5px 10px;border:1px solid #e5e7eb;text-align:${aligns[idx] || "left"}'>${inlineMd(c)}</td>`
            ).join("") + "</tr>");
          i++;
        }
        out.push(`<table style='border-collapse:collapse;width:100%;margin:10px 0;font-size:12px'>${thead}<tbody>${bodyRows.join("")}</tbody></table>`);
        continue;
      }
      if (/^[-*] /.test(line)) {
        const items = [];
        while (i < lines.length && /^[-*] /.test(lines[i])) {
          items.push("<li style='margin:3px 0'>" + inlineMd(lines[i].replace(/^[-*] /, "")) + "</li>");
          i++;
        }
        out.push("<ul style='margin:6px 0;padding-left:20px;list-style-type:disc'>" + items.join("") + "</ul>");
        continue;
      }
      if (/^\d+\. /.test(line)) {
        const items = [];
        while (i < lines.length && /^\d+\. /.test(lines[i])) {
          items.push("<li style='margin:3px 0'>" + inlineMd(lines[i].replace(/^\d+\. /, "")) + "</li>");
          i++;
        }
        out.push("<ol style='margin:6px 0;padding-left:20px;list-style-type:decimal'>" + items.join("") + "</ol>");
        continue;
      }
      if (/^### /.test(line)) { out.push("<h3 style='margin:12px 0 4px;font-size:14px;font-weight:700'>" + inlineMd(line.slice(4)) + "</h3>"); i++; continue; }
      if (/^## /.test(line))  { out.push("<h2 style='margin:14px 0 5px;font-size:15px;font-weight:700'>" + inlineMd(line.slice(3)) + "</h2>"); i++; continue; }
      if (/^# /.test(line))   { out.push("<h1 style='margin:16px 0 6px;font-size:17px;font-weight:700'>" + inlineMd(line.slice(2)) + "</h1>"); i++; continue; }
      if (line.trim() === "") { out.push("<br>"); i++; continue; }
      out.push("<p style='margin:2px 0'>" + inlineMd(line) + "</p>");
      i++;
    }
    return out.join("");
  }

  // ─── State ───────────────────────────────────────────────────────────────────

  let state = {
    skills: [],
    selectedSkill: null,   // {name, source, ...}
    tree: null,
    selectedFile: null,    // {path, content}
    expandedDirs: {},      // {relPath: true}
    viewMode: "preview",   // "preview" | "edit"
    fileContent: "",       // 編輯器目前內容
    fileDirty: false,
  };

  let overlay, modal, skillListPane, treePane, editorPane;

  // ─── Build Modal ──────────────────────────────────────────────────────────────

  function buildModal() {
    if (document.getElementById(MODAL_ID)) return;

    overlay = el("div", {
      position: "fixed", top: "0", left: "0", width: "100vw", height: "100vh",
      background: "rgba(0,0,0,0.6)", zIndex: "2147483646",
      display: "flex", alignItems: "center", justifyContent: "center",
    });
    overlay.id = MODAL_ID;
    overlay.addEventListener("click", e => { if (e.target === overlay) closeModal(); });

    modal = el("div", {
      width: "min(97vw,1200px)", height: "min(93vh,800px)",
      background: "#ffffff", borderRadius: "12px",
      border: "1px solid #e5e7eb",
      boxShadow: "0 12px 48px rgba(0,0,0,0.22)",
      display: "flex", flexDirection: "column", overflow: "hidden",
      position: "relative", zIndex: "2147483647",
    });

    // Header
    const titleSpan = el("span", { fontSize: "15px", fontWeight: "700", color: "#111827" }, "Skill 管理");
    const addSkillBtn = btn("新增 Skill", true, false);
    addSkillBtn.addEventListener("click", openNewSkillForm);
    const uploadZipBtn = btn("上傳 ZIP", false, false);
    uploadZipBtn.addEventListener("click", () => triggerZipUpload());
    const closeBtn = btn("✕", false, false);
    closeBtn.style.padding = "4px 10px";
    closeBtn.addEventListener("click", closeModal);
    const headerRight = el("div", { display: "flex", alignItems: "center", gap: "8px" });
    headerRight.append(addSkillBtn, uploadZipBtn, closeBtn);
    const header = el("div", {
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "13px 18px", borderBottom: "1px solid #e5e7eb", flexShrink: "0",
      background: "#ffffff",
    }, titleSpan, headerRight);

    // Three-column body
    skillListPane = el("div", {
      width: "190px", minWidth: "170px", flexShrink: "0",
      borderRight: "1px solid #e5e7eb",
      display: "flex", flexDirection: "column", overflow: "hidden",
      background: "#fafafa",
    });

    treePane = el("div", {
      width: "250px", minWidth: "220px", flexShrink: "0",
      borderRight: "1px solid #e5e7eb",
      display: "flex", flexDirection: "column", overflow: "hidden",
      background: "#ffffff",
    });

    editorPane = el("div", {
      flex: "1", display: "flex", flexDirection: "column", overflow: "hidden",
      background: "#ffffff",
    });

    const body = el("div", { display: "flex", flex: "1", overflow: "hidden" });
    body.append(skillListPane, treePane, editorPane);
    modal.append(header, body);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  }

  // ─── Skill List Pane ──────────────────────────────────────────────────────────

  function renderSkillList() {
    skillListPane.innerHTML = "";
    const label = el("div", {
      fontSize: "10px", fontWeight: "700", color: "#9ca3af",
      textTransform: "uppercase", letterSpacing: "0.06em",
      padding: "10px 12px 6px",
    }, "Skills");
    skillListPane.appendChild(label);

    const list = el("div", { flex: "1", overflowY: "auto" });
    skillListPane.appendChild(list);

    if (state.skills.length === 0) {
      list.appendChild(el("div", {
        padding: "16px 12px", fontSize: "12px", color: "#9ca3af", textAlign: "center",
      }, "尚無 Skill"));
      return;
    }

    // 系統在後、用戶在前
    const userSkills = state.skills.filter(s => s.source === "user");
    const sysSkills  = state.skills.filter(s => s.source === "system");

    function addSection(title, skills) {
      if (skills.length === 0) return;
      const secLabel = el("div", {
        fontSize: "10px", fontWeight: "600", color: "#d1d5db",
        padding: "8px 12px 3px", textTransform: "uppercase", letterSpacing: "0.05em",
      }, title);
      list.appendChild(secLabel);
      for (const sk of skills) {
        const sel = state.selectedSkill && state.selectedSkill.name === sk.name;
        const row = el("div", {
          padding: "7px 12px", cursor: "pointer",
          background: sel ? "#eff6ff" : "transparent",
          borderLeft: sel ? "3px solid hsl(var(--primary,220 90% 56%))" : "3px solid transparent",
          position: "relative",
        });
        row.dataset.skillName = sk.name;

        const topRow = el("div", {
          display: "flex", alignItems: "center", justifyContent: "space-between",
          marginBottom: "2px",
        });
        const nameEl = el("div", {
          fontSize: "13px", fontWeight: sel ? "700" : "500",
          color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          flex: "1", minWidth: "0",
        }, sk.name);
        topRow.appendChild(nameEl);

        if (sk.source === "user") {
          const delBtn = el("span", {
            flexShrink: "0", color: "#d1d5db", cursor: "pointer",
            fontSize: "12px", padding: "0 3px", opacity: "0", transition: "opacity 0.1s",
          }, "✕");
          delBtn.title = "刪除此 Skill";
          let confirmDel = false;
          delBtn.addEventListener("click", e => {
            e.stopPropagation();
            if (!confirmDel) {
              confirmDel = true;
              delBtn.textContent = "確認?"; delBtn.style.color = "#ef4444"; delBtn.style.opacity = "1";
              setTimeout(() => {
                confirmDel = false;
                delBtn.textContent = "✕"; delBtn.style.color = "#d1d5db";
                delBtn.style.opacity = row.matches(":hover") ? "1" : "0";
              }, 2500);
            } else {
              handleDeleteSkill(sk);
            }
          });
          topRow.appendChild(delBtn);
          row.addEventListener("mouseenter", () => { delBtn.style.opacity = "1"; });
          row.addEventListener("mouseleave", () => { if (!confirmDel) delBtn.style.opacity = "0"; });
        }

        row.appendChild(topRow);
        row.appendChild(sourceBadge(sk.source));

        row.addEventListener("click", () => selectSkill(sk));
        row.addEventListener("mouseenter", () => { if (!sel) row.style.background = "#f9fafb"; });
        row.addEventListener("mouseleave", () => { if (!sel) row.style.background = "transparent"; });
        list.appendChild(row);
      }
    }

    addSection("個人", userSkills);
    addSection("系統", sysSkills);
  }

  function updateSkillListSelection() {
    for (const row of skillListPane.querySelectorAll("[data-skill-name]")) {
      const sel = state.selectedSkill && row.dataset.skillName === state.selectedSkill.name;
      row.style.background = sel ? "#eff6ff" : "transparent";
      row.style.borderLeft = sel ? "3px solid hsl(var(--primary,220 90% 56%))" : "3px solid transparent";
      const nameEl = row.querySelector("div");
      if (nameEl) nameEl.style.fontWeight = sel ? "700" : "500";
    }
  }

  // ─── Tree Pane ────────────────────────────────────────────────────────────────

  function renderTreePane() {
    treePane.innerHTML = "";

    if (!state.selectedSkill) {
      treePane.appendChild(el("div", {
        flex: "1", display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "12px", color: "#9ca3af", padding: "24px", textAlign: "center",
      }, "選擇左側 Skill 後\n顯示檔案結構"));
      return;
    }

    const label = el("div", {
      fontSize: "10px", fontWeight: "700", color: "#9ca3af",
      textTransform: "uppercase", letterSpacing: "0.06em",
      padding: "10px 12px 6px", borderBottom: "1px solid #f3f4f6",
      display: "flex", alignItems: "center", justifyContent: "space-between",
    });
    label.appendChild(el("span", null, state.selectedSkill.name));
    label.appendChild(sourceBadge(state.selectedSkill.source));
    treePane.appendChild(label);

    const treeScroll = el("div", { flex: "1", overflowY: "auto", padding: "4px 0" });
    treePane.appendChild(treeScroll);

    const isSystem = state.selectedSkill.source === "system";

    if (state.tree) {
      renderTreeNode(treeScroll, state.tree, 0);
    } else {
      treeScroll.appendChild(el("div", {
        padding: "16px", fontSize: "12px", color: "#9ca3af", textAlign: "center",
      }, "載入中..."));
    }

  }

  function renderTreeNode(container, node, depth) {
    if (node.type === "file") {
      const row = el("div", {
        padding: `5px 10px 5px ${12 + depth * 16}px`,
        cursor: "pointer", fontSize: "12px", color: "#374151",
        display: "flex", alignItems: "center", gap: "5px",
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      });
      const icon = el("span", { flexShrink: "0", fontSize: "11px" }, "📄");
      const name = el("span", {
        overflow: "hidden", textOverflow: "ellipsis",
        color: state.selectedFile && state.selectedFile.path === node.path ? "#2563eb" : "#374151",
        fontWeight: state.selectedFile && state.selectedFile.path === node.path ? "700" : "400",
      }, node.name);
      row.append(icon, name);

      const isSystem = state.selectedSkill && state.selectedSkill.source === "system";

      if (!isSystem) {
        const delBtn = el("span", {
          marginLeft: "auto", flexShrink: "0", color: "#d1d5db", cursor: "pointer",
          fontSize: "12px", padding: "0 3px",
        }, "✕");
        delBtn.title = "刪除檔案";
        let confirmDel = false;
        delBtn.addEventListener("click", e => {
          e.stopPropagation();
          if (!confirmDel) {
            confirmDel = true; delBtn.textContent = "確認?"; delBtn.style.color = "#ef4444";
            setTimeout(() => { confirmDel = false; delBtn.textContent = "✕"; delBtn.style.color = "#d1d5db"; }, 2500);
          } else {
            handleDeleteFile(node.path);
          }
        });
        row.appendChild(delBtn);
        row.addEventListener("mouseenter", () => { delBtn.style.color = "#9ca3af"; });
        row.addEventListener("mouseleave", () => { if (!confirmDel) delBtn.style.color = "#d1d5db"; });
      }

      row.addEventListener("click", () => openFile(node.path));
      container.appendChild(row);
    } else {
      const isExpanded = !!state.expandedDirs[node.path];
      const row = el("div", {
        padding: `5px 10px 5px ${12 + depth * 16}px`,
        cursor: "pointer", fontSize: "12px", color: "#374151",
        display: "flex", alignItems: "center", gap: "5px",
        fontWeight: "600",
      });
      const arrow = el("span", { flexShrink: "0", fontSize: "10px", color: "#9ca3af", width: "12px" }, isExpanded ? "▼" : "▶");
      const icon = el("span", { flexShrink: "0", fontSize: "11px" }, "📁");
      const nameSpan = el("span", {}, node.path ? node.name : node.name + "/");
      row.append(arrow, icon, nameSpan);

      const isSystem = state.selectedSkill && state.selectedSkill.source === "system";

      // 右側 action 群組（hover 才顯示）
      const actions = el("div", {
        marginLeft: "auto", display: "flex", alignItems: "center", gap: "2px",
        opacity: "0", transition: "opacity 0.1s",
      });

      if (!isSystem) {
        // ＋檔案
        const addFileBtn = document.createElement("span");
        addFileBtn.title = "在此目錄新增檔案";
        Object.assign(addFileBtn.style, {
          cursor: "pointer", display: "flex", alignItems: "center",
          padding: "1px 3px", borderRadius: "3px", color: "#6b7280", lineHeight: "1",
        });
        addFileBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M9 15h6"/><path d="M12 12v6"/></svg>`;
        addFileBtn.addEventListener("click", e => {
          e.stopPropagation();
          promptNewFileIn(node.path);
        });

        // ＋目錄
        const addDirBtn = document.createElement("span");
        addDirBtn.title = "在此目錄新增子目錄";
        Object.assign(addDirBtn.style, {
          cursor: "pointer", display: "flex", alignItems: "center",
          padding: "1px 3px", borderRadius: "3px", color: "#6b7280", lineHeight: "1",
        })
        addDirBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/><path d="M9 15h6"/><path d="M12 12v6"/></svg>`;
        addDirBtn.addEventListener("click", e => {
          e.stopPropagation();
          promptNewDirIn(node.path);
        });

        actions.append(addFileBtn, addDirBtn);

        // 刪除（根目錄不顯示）
        if (node.path) {
          const delBtn = el("span", {
            cursor: "pointer", fontSize: "12px", color: "#d1d5db",
            padding: "0 3px",
          }, "✕");
          delBtn.title = "刪除目錄";
          let confirmDel = false;
          delBtn.addEventListener("click", e => {
            e.stopPropagation();
            if (!confirmDel) {
              confirmDel = true; delBtn.textContent = "確認?"; delBtn.style.color = "#ef4444";
              setTimeout(() => { confirmDel = false; delBtn.textContent = "✕"; delBtn.style.color = "#d1d5db"; }, 2500);
            } else {
              handleDeleteDir(node.path);
            }
          });
          actions.appendChild(delBtn);
        }
      }

      row.appendChild(actions);

      row.addEventListener("mouseenter", () => { actions.style.opacity = "1"; });
      row.addEventListener("mouseleave", () => { actions.style.opacity = "0"; });
      row.addEventListener("click", () => toggleDir(node.path));
      container.appendChild(row);

      if (isExpanded && node.children) {
        const childrenWrap = el("div", {});
        for (const child of node.children) {
          renderTreeNode(childrenWrap, child, depth + 1);
        }
        container.appendChild(childrenWrap);
      }
    }
  }

  function toggleDir(path) {
    state.expandedDirs[path] = !state.expandedDirs[path];
    renderTreePane();
  }

  // ─── Editor Pane ──────────────────────────────────────────────────────────────

  function renderEditorPane() {
    editorPane.innerHTML = "";

    if (!state.selectedSkill) {
      editorPane.appendChild(el("div", {
        flex: "1", display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "13px", color: "#9ca3af", height: "100%",
      }, "選擇左側 Skill，再點擊檔案進行編輯"));
      return;
    }

    if (!state.selectedFile) {
      const isSystem = state.selectedSkill.source === "system";
      editorPane.appendChild(el("div", {
        flex: "1", display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "13px", color: "#9ca3af", height: "100%",
      }, isSystem ? "點擊中欄檔案以預覽" : "點擊中欄檔案以編輯，或新增檔案"));
      return;
    }

    const { path, content } = state.selectedFile;
    const isSystem = state.selectedSkill.source === "system";
    const isMd = path.endsWith(".md");

    // Breadcrumb header
    const breadcrumb = el("div", {
      padding: "10px 16px", borderBottom: "1px solid #f3f4f6",
      fontSize: "12px", color: "#6b7280", display: "flex", alignItems: "center",
      gap: "4px", flexShrink: "0", background: "#fafafa",
    });
    const parts = path.split("/");
    parts.forEach((p, i) => {
      breadcrumb.appendChild(el("span", {
        color: i === parts.length - 1 ? "#111827" : "#9ca3af",
        fontWeight: i === parts.length - 1 ? "600" : "400",
      }, p));
      if (i < parts.length - 1) breadcrumb.appendChild(el("span", { color: "#d1d5db" }, " / "));
    });
    editorPane.appendChild(breadcrumb);

    // Toolbar（.md 檔才有預覽/編輯切換；系統 Skill 不顯示儲存）
    const toolbar = el("div", {
      padding: "8px 16px", borderBottom: "1px solid #f3f4f6",
      display: "flex", alignItems: "center", gap: "8px", flexShrink: "0",
    });

    if (isMd) {
      const previewBtn = btn("預覽", state.viewMode === "preview", false);
      const editBtnEl  = btn("編輯", state.viewMode === "edit",    false);
      previewBtn.addEventListener("click", () => { state.viewMode = "preview"; renderEditorPane(); });
      editBtnEl.addEventListener("click",  () => {
        if (isSystem) { toast("系統 Skill 不可編輯", true); return; }
        state.viewMode = "edit"; renderEditorPane();
      });
      toolbar.append(previewBtn, editBtnEl);
    }

    if (!isSystem) {
      const saveBtn = btn("儲存", true, false);
      saveBtn.style.marginLeft = "auto";
      saveBtn.addEventListener("click", handleSaveFile);
      const discardBtn = btn("放棄", false, false);
      discardBtn.addEventListener("click", () => {
        state.fileContent = state.selectedFile.content;
        state.fileDirty = false;
        renderEditorPane();
      });
      toolbar.append(saveBtn, discardBtn);
    }
    editorPane.appendChild(toolbar);

    // Content area
    const contentArea = el("div", {
      flex: "1", overflow: "auto", padding: "16px",
    });

    const showPreview = isMd && state.viewMode === "preview";
    if (showPreview) {
      contentArea.style.fontSize = "13px";
      contentArea.style.lineHeight = "1.7";
      contentArea.style.color = "#111827";
      contentArea.innerHTML = renderMd(state.fileContent);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = state.fileContent;
      textarea.readOnly = isSystem;
      Object.assign(textarea.style, {
        width: "100%", height: "100%",
        border: "1px solid #e5e7eb", borderRadius: "6px",
        padding: "10px 12px", fontSize: "13px", lineHeight: "1.55",
        fontFamily: "ui-monospace,Menlo,monospace",
        resize: "none", outline: "none",
        background: isSystem ? "#fafafa" : "#fff",
        color: "#111827", boxSizing: "border-box",
      });
      textarea.addEventListener("input", () => {
        state.fileContent = textarea.value;
        state.fileDirty = true;
      });
      contentArea.appendChild(textarea);
    }

    editorPane.appendChild(contentArea);
  }

  // ─── Actions ─────────────────────────────────────────────────────────────────

  async function loadSkills() {
    try {
      const { skills } = await api.list();
      state.skills = skills || [];
    } catch (e) {
      console.error("[skill] 載入失敗:", e.message);
      state.skills = [];
    }
  }

  async function selectSkill(sk) {
    if (state.fileDirty) {
      if (!confirm("有未儲存的變更，確定切換？")) return;
    }
    state.selectedSkill = sk;
    state.selectedFile = null;
    state.fileContent = "";
    state.fileDirty = false;
    state.tree = null;
    state.expandedDirs = {};
    state.viewMode = "preview";
    updateSkillListSelection();
    renderTreePane();
    renderEditorPane();

    try {
      const { tree } = await api.tree(sk.name);
      state.tree = tree;
      // 根節點本身也要展開（path 為空字串），再展開第一層子目錄
      state.expandedDirs[""] = true;
      if (tree.children) {
        for (const child of tree.children) {
          if (child.type === "dir") state.expandedDirs[child.path] = true;
        }
      }
      renderTreePane();
      // 自動開啟根目錄下的 SKILL.md
      const skillMd = tree.children && tree.children.find(
        n => n.type === "file" && /^skill\.md$/i.test(n.name)
      );
      if (skillMd) await openFile(skillMd.path);
    } catch (e) {
      toast("載入目錄樹失敗：" + e.message, true);
    }
  }

  async function openFile(path) {
    if (state.fileDirty) {
      if (!confirm("有未儲存的變更，確定切換？")) return;
    }
    try {
      const { content } = await api.readFile(state.selectedSkill.name, path);
      state.selectedFile = { path, content };
      state.fileContent = content;
      state.fileDirty = false;
      state.viewMode = "preview";
      renderTreePane();
      renderEditorPane();
    } catch (e) {
      toast("讀取檔案失敗：" + e.message, true);
    }
  }

  async function handleSaveFile() {
    const { path } = state.selectedFile;
    try {
      await api.writeFile(state.selectedSkill.name, path, state.fileContent);
      state.selectedFile = { path, content: state.fileContent };
      state.fileDirty = false;
      toast("已儲存", false);
      renderEditorPane();
    } catch (e) {
      toast("儲存失敗：" + e.message, true);
    }
  }

  async function handleDeleteFile(path) {
    try {
      await api.deleteFile(state.selectedSkill.name, path);
      if (state.selectedFile && state.selectedFile.path === path) {
        state.selectedFile = null;
        state.fileContent = "";
        state.fileDirty = false;
      }
      await reloadTree();
      toast("已刪除檔案", false);
    } catch (e) {
      toast("刪除失敗：" + e.message, true);
    }
  }

  async function handleDeleteDir(path) {
    try {
      await api.deleteDir(state.selectedSkill.name, path);
      if (state.selectedFile && state.selectedFile.path.startsWith(path + "/")) {
        state.selectedFile = null;
        state.fileContent = "";
        state.fileDirty = false;
      }
      delete state.expandedDirs[path];
      await reloadTree();
      toast("已刪除目錄", false);
    } catch (e) {
      toast("刪除失敗：" + e.message, true);
    }
  }

  async function reloadTree() {
    try {
      const { tree } = await api.tree(state.selectedSkill.name);
      state.tree = tree;
    } catch {}
    renderTreePane();
    renderEditorPane();
  }

  function promptNewFileIn(dirPath) {
    const hint = dirPath ? `在 ${dirPath}/ 內` : "在根目錄";
    const name = prompt(`${hint}新增檔案（含副檔名，如 foo.py）:`);
    if (!name || !name.trim()) return;
    const filename = name.trim().replace(/^\/+/, "");
    const relPath = dirPath ? dirPath + "/" + filename : filename;
    if (dirPath) state.expandedDirs[dirPath] = true;
    api.writeFile(state.selectedSkill.name, relPath, "").then(async () => {
      await reloadTree();
      await openFile(relPath);
      toast("已建立檔案", false);
    }).catch(e => toast("建立失敗：" + e.message, true));
  }

  function promptNewDirIn(dirPath) {
    const hint = dirPath ? `在 ${dirPath}/ 內` : "在根目錄";
    const name = prompt(`${hint}新增子目錄（名稱）:`);
    if (!name || !name.trim()) return;
    const dirname = name.trim().replace(/^\/+/, "");
    const relPath = dirPath ? dirPath + "/" + dirname : dirname;
    api.createDir(state.selectedSkill.name, relPath).then(async () => {
      if (dirPath) state.expandedDirs[dirPath] = true;
      state.expandedDirs[relPath] = true;
      await reloadTree();
      toast("已建立目錄", false);
    }).catch(e => toast("建立失敗：" + e.message, true));
  }

  // ─── 上傳 ZIP ─────────────────────────────────────────────────────────────────

  function triggerZipUpload() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".zip";
    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      const uploadBtn = modal.querySelector('button[data-zip-upload]');
      try {
        toast("上傳中...", false);
        const { skill_name } = await api.uploadZip(file);
        await loadSkills();
        renderSkillList();
        const sk = state.skills.find(s => s.name === skill_name);
        if (sk) await selectSkill(sk);
        toast(`已匯入 Skill「${skill_name}」`, false);
      } catch (e) {
        toast("上傳失敗：" + e.message, true);
      }
    });
    input.click();
  }

  // ─── 新增 Skill 表單 ──────────────────────────────────────────────────────────

  function openNewSkillForm() {
    editorPane.innerHTML = "";
    state.selectedSkill = null;
    state.selectedFile = null;
    state.fileContent = "";
    state.fileDirty = false;
    state.tree = null;
    updateSkillListSelection();
    renderTreePane();

    const wrap = el("div", {
      display: "flex", flexDirection: "column", height: "100%",
      alignItems: "center", justifyContent: "center", padding: "32px",
    });
    wrap.appendChild(el("h3", {
      fontSize: "15px", fontWeight: "700", color: "#111827", marginBottom: "16px",
    }, "新增 Skill"));

    wrap.appendChild(el("div", {
      fontSize: "11px", fontWeight: "700", color: "#6b7280",
      textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px",
      alignSelf: "flex-start",
    }, "Skill 名稱"));

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "例：my-skill（英文小寫、連字號）";
    Object.assign(nameInput.style, {
      width: "100%", padding: "8px 10px",
      border: "1px solid #e5e7eb", borderRadius: "6px",
      fontSize: "13px", background: "#fff", color: "#111",
      outline: "none", boxSizing: "border-box", marginBottom: "12px",
      fontFamily: "inherit",
    });
    wrap.appendChild(nameInput);

    const errArea = el("div", {
      display: "none", padding: "7px 12px", background: "#fee2e2",
      color: "#991b1b", borderRadius: "6px", fontSize: "13px", marginBottom: "10px",
    });
    wrap.appendChild(errArea);

    const actions = el("div", { display: "flex", gap: "8px" });
    const createBtn = btn("建立", true, false);
    createBtn.addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) { nameInput.focus(); return; }
      errArea.style.display = "none";
      createBtn.disabled = true; createBtn.textContent = "建立中...";
      try {
        const { skill_name } = await api.createSkill(name);
        await loadSkills();
        renderSkillList();
        const sk = state.skills.find(s => s.name === skill_name);
        if (sk) await selectSkill(sk);
        toast(`已建立 Skill「${skill_name}」`, false);
      } catch (e) {
        errArea.textContent = "建立失敗：" + e.message;
        errArea.style.display = "block";
        createBtn.disabled = false; createBtn.textContent = "建立";
      }
    });

    const cancelBtn = btn("取消", false, false);
    cancelBtn.addEventListener("click", () => renderEditorPane());
    actions.append(createBtn, cancelBtn);
    wrap.appendChild(actions);
    editorPane.appendChild(wrap);
  }

  // 刪除整個 Skill（在 skill list 右鍵或雙擊觸發——此處用獨立函式備用）
  async function handleDeleteSkill(sk) {
    if (!confirm(`確定要刪除 Skill「${sk.name}」及其所有檔案？`)) return;
    try {
      await api.deleteSkill(sk.name);
      if (state.selectedSkill && state.selectedSkill.name === sk.name) {
        state.selectedSkill = null;
        state.selectedFile = null;
        state.fileContent = "";
        state.fileDirty = false;
        state.tree = null;
      }
      await loadSkills();
      renderSkillList();
      renderTreePane();
      renderEditorPane();
      toast(`已刪除 Skill「${sk.name}」`, false);
    } catch (e) {
      toast("刪除失敗：" + e.message, true);
    }
  }

  // ─── Open / Close ─────────────────────────────────────────────────────────────

  async function openModal() {
    buildModal();
    overlay.style.display = "flex";
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";

    state.skills = [];
    state.selectedSkill = null;
    state.selectedFile = null;
    state.fileContent = "";
    state.fileDirty = false;
    state.tree = null;
    state.expandedDirs = {};
    state.viewMode = "preview";

    renderSkillList();
    renderTreePane();
    renderEditorPane();

    await loadSkills();
    renderSkillList();
  }

  function closeModal() {
    if (overlay) overlay.style.display = "none";
    document.documentElement.style.overflow = "";
    document.body.style.overflow = "";
  }

  window.__openSkillManager = openModal;

  // ─── Menu injection ───────────────────────────────────────────────────────────

  function createMenuItem() {
    const item = document.createElement("button");
    item.id = MENU_ITEM_ID;
    item.type = "button";
    item.textContent = "Skill 管理";
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
      const trigger = document.getElementById("user-nav-button");
      if (trigger) trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      setTimeout(openModal, 80);
    });
    return item;
  }

  function tryInjectMenu() {
    const trigger = document.getElementById("user-nav-button");
    if (!trigger || trigger.getAttribute("aria-expanded") !== "true") return;
    const menu = document.querySelector('[role="menu"]');
    if (!menu || menu.querySelector("#" + MENU_ITEM_ID)) return;

    // 插入在「記憶管理」之後（如果存在），否則插在最前
    const memoryItem = menu.querySelector("#memory-manager-menu-item");
    if (memoryItem && memoryItem.nextSibling) {
      menu.insertBefore(createMenuItem(), memoryItem.nextSibling);
    } else if (memoryItem) {
      menu.appendChild(createMenuItem());
    } else {
      menu.insertBefore(createMenuItem(), menu.firstElementChild);
    }
  }

  function startObserver() {
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
