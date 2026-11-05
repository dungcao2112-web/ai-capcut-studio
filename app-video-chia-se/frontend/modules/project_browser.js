// -*- coding: utf-8 -*-
// Bộ duyệt dự án ở cột trái: tìm kiếm tức thì (Ctrl+K), lọc theo preset, badge số mục / preset / 2 người.
// Bổ sung hàm global selectProject(pid). Bọc refreshProjectsList & onSelectProject (giữ nguyên hành vi cũ).
(function () {
  "use strict";
  const PB_FILTER_KEY = "vdcs.studio.pbFilter";
  const safeLS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* bỏ qua */ } },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const curPid = () => (window.studioCurrent ? window.studioCurrent().pid : "");
  const curProj = () => (window.studioCurrent ? window.studioCurrent().project : null);

  // ---------------- Bộ duyệt dự án (cột trái) ----------------
  let pbProjects = [];
  const PB_FILTERS = [["all", "Tất cả"], ["anh_nhac", "Ảnh + Nhạc"], ["chiase", "Chia sẻ"], ["giodo", "Giỏ đồ"]];

  function mountProjectBrowser() {
    const side = document.querySelector("aside.sidebar");
    if (!side || document.getElementById("spProjectBrowser")) return;
    const box = document.createElement("div");
    box.id = "spProjectBrowser";
    box.className = "sp-project-browser";
    box.innerHTML = `
      <div class="sp-pb-head"><span>📁 Dự án <span id="spPbCount" class="badge">0</span></span>
        <button class="sm" onclick="refreshProjectsList(currentProjectId)" title="Tải lại danh sách">↻</button></div>
      <div class="sp-pb-search"><input type="search" id="spProjectSearch" placeholder="Tìm nhanh dự án (Ctrl+K)..." autocomplete="off" /></div>
      <div class="sp-pb-filters" id="spPbFilters">${PB_FILTERS.map(([k, t]) => `<button class="sm" data-f="${k}">${t}</button>`).join("")}</div>
      <div class="sp-pb-list" id="spPbList"><div class="sp-pb-empty">Đang tải danh sách dự án...</div></div>`;
    side.insertBefore(box, side.firstChild);
    const inp = box.querySelector("#spProjectSearch");
    inp.addEventListener("input", renderProjectBrowser);
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const first = box.querySelector(".sp-pb-card");
        if (first) first.click();
      } else if (e.key === "Escape") { inp.value = ""; renderProjectBrowser(); inp.blur(); }
    });
    box.querySelectorAll("#spPbFilters button").forEach((b) => b.addEventListener("click", () => {
      safeLS.set(PB_FILTER_KEY, b.dataset.f);
      renderProjectBrowser();
    }));
  }

  function highlight(text, q) {
    const safe = esc(text);
    if (!q) return safe;
    const idx = String(text).toLowerCase().indexOf(q.toLowerCase());
    if (idx < 0) return safe;
    return esc(text.slice(0, idx)) + `<mark class="sp-hl">${esc(text.slice(idx, idx + q.length))}</mark>` + esc(text.slice(idx + q.length));
  }

  function renderProjectBrowser() {
    const list = document.getElementById("spPbList");
    if (!list) return;
    const q = (document.getElementById("spProjectSearch")?.value || "").trim();
    const f = safeLS.get(PB_FILTER_KEY, "all");
    document.querySelectorAll("#spPbFilters button").forEach((b) => b.classList.toggle("on", b.dataset.f === f));
    const ql = q.toLowerCase();
    const rows = pbProjects.filter((p) => {
      if (f !== "all" && p.preset !== f) return false;
      if (!ql) return true;
      const hay = `${p.title} ${p.id} ${p.preset_label || ""} ${p.item_count || 0} mục ${p.people_label || ""}`.toLowerCase();
      return ql.split(/\s+/).every((tok) => hay.includes(tok));
    });
    document.getElementById("spPbCount").textContent = `${rows.length}/${pbProjects.length}`;
    if (!rows.length) {
      list.innerHTML = `<div class="sp-pb-empty">Không có dự án khớp "${esc(q)}".</div>`;
      return;
    }
    const cur = curPid();
    const statusBadge = (p) => {
      if (p.waiting_gate) return `<span class="badge warning">⏸ ${esc(p.waiting_gate)}</span>`;
      if (p.pipeline_status === "running") return `<span class="badge info">⏳ Đang chạy</span>`;
      if (p.pipeline_status === "completed") return `<span class="badge success">✔ Xong</span>`;
      if (p.pipeline_status === "error") return `<span class="badge danger">Lỗi</span>`;
      return "";
    };
    list.innerHTML = rows.map((p) => `
      <button class="sp-pb-card ${p.id === cur ? "active" : ""}" data-pid="${esc(p.id)}" title="${esc(p.id)}">
        <div class="sp-pb-title">${highlight(p.title || p.id, q)}</div>
        <div class="sp-pb-meta">
          <span class="badge info">${Number(p.item_count || 0)} mục</span>
          <span class="badge">${esc(p.preset_label || p.preset)}</span>
          <span class="badge">${esc(p.people_label || "")}</span>
          ${p.is_demo ? '<span class="badge warning">Mẫu</span>' : ""}${statusBadge(p)}
        </div>
      </button>`).join("");
    list.querySelectorAll(".sp-pb-card").forEach((btn) => btn.addEventListener("click", () => window.selectProject(btn.dataset.pid)));
  }

  async function loadProjectBrowser() {
    try {
      const res = await fetch("/api/projects");
      const data = await res.json();
      pbProjects = data.projects || [];
    } catch (e) {
      pbProjects = [];
    }
    renderProjectBrowser();
  }
  window.renderProjectBrowser = renderProjectBrowser;

  // selectProject(pid): hàm global chuẩn (CLAUDE.md) — chọn dự án từ bất kỳ đâu
  window.selectProject = async function (pid) {
    const sel = document.getElementById("projectSelect");
    if (sel) sel.value = pid;
    await window.onSelectProject(pid);
    renderProjectBrowser();
  };

  function wrapGlobals() {
    const origRefresh = window.refreshProjectsList;
    if (typeof origRefresh === "function" && !origRefresh.__sp) {
      window.refreshProjectsList = async function (...args) {
        const r = await origRefresh.apply(this, args);
        await loadProjectBrowser();
        return r;
      };
      window.refreshProjectsList.__sp = true;
    }
    const origSelect = window.onSelectProject;
    if (typeof origSelect === "function" && !origSelect.__sp) {
      window.onSelectProject = async function (...args) {
        const r = await origSelect.apply(this, args);
        renderProjectBrowser();
        document.dispatchEvent(new CustomEvent("studio:projectloaded", { detail: { project: curProj() } }));
        return r;
      };
      window.onSelectProject.__sp = true;
    }
  }

  window.reloadProjectBrowser = loadProjectBrowser;

  function init() {
    mountProjectBrowser();
    wrapGlobals();
    loadProjectBrowser();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
