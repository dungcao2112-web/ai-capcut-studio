// -*- coding: utf-8 -*-
// Auto-QA Panel: nút "🛡️ Kiểm tra & Tự sửa lỗi bố cục (Auto-QA)" trên thanh lệnh + khung kiểm định ở tab Xuất Video.
// GET /api/projects/<pid>/qa-check (10 tiêu chí) • POST /api/projects/<pid>/qa-autofix (tự sửa 1 chạm)
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, t, ms) => (window.showToast ? window.showToast(m, t, ms) : null);
  const cur = () => (window.studioCurrent ? window.studioCurrent() : { pid: "" });
  const ICON = { pass: "✅", warn: "⚠️", fail: "⛔" };
  let last = null;
  let lastFix = null;

  function scoreClass(sc) { return sc >= 90 ? "good" : sc >= 70 ? "mid" : "bad"; }

  function reportHtml(r, fix) {
    if (!r) return '<div class="step-msg">Chưa kiểm tra. Bấm <b>🛡️ Kiểm tra ngay</b>.</div>';
    const c = r.counts || {};
    const countLine = [["Kịch bản", c.script], ["Bảng mục", c.bang], ["Storyboard", c.storyboard], ["Timeline", c.timeline], ["Bảng Tổng Hợp", c.summary]]
      .map(([k, v]) => `<span class="badge ${v === null || v === undefined ? "" : v === c.script ? "success" : "danger"}">${k}: ${v ?? "—"}</span>`).join(" ");
    const rows = (r.checks || []).map((ch, k) => `<div class="qa-row ${ch.status}"><span>${ICON[ch.status] || "•"}</span>
      <div><b>${k + 1}. ${esc(ch.name)}</b><div class="qa-detail">${esc(ch.detail)}</div></div>
      <span>${ch.fixable ? '<span class="badge warning">Tự sửa được</span>' : ""}</span></div>`).join("");
    const fixHtml = fix ? `<div class="qa-fixlog">${(fix.fixes || []).length ? "🔧 Đã sửa: " + fix.fixes.map(esc).join(" • ") : "🔧 Không có gì cần sửa tự động."}
      ${(fix.warnings || []).map((w) => `<div style="color:var(--sp-warn)">⚠️ ${esc(w)}</div>`).join("")}</div>` : "";
    return `<div class="qa-head">
        <div><div class="qa-score ${scoreClass(r.score)}">${r.score}/100</div>
          <div class="step-msg">${r.passed} đạt • ${r.warnings} cảnh báo • ${r.failed} lỗi — preset <b>${esc(r.preset)}</b></div></div>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <button class="sm" onclick="runAutoQaCheck(true)">↻ Kiểm tra lại</button>
          <button class="sm warning" onclick="runAutoQaFix()" ${r.fixable_count ? "" : "disabled"}>🔧 Tự sửa lỗi 1 chạm (${r.fixable_count})</button>
        </div></div>
      <div style="margin-top:6px; display:flex; gap:4px; flex-wrap:wrap;">${countLine}</div>
      ${fixHtml}<div class="qa-list">${rows}</div>`;
  }

  function renderAll() {
    const inline = $("qaInlineBody");
    if (inline) inline.innerHTML = reportHtml(last, lastFix);
    const modalBody = $("qaModalBody");
    if (modalBody) modalBody.innerHTML = reportHtml(last, lastFix);
    const badge = $("qaScoreBadge");
    if (badge) {
      badge.textContent = last ? `${last.score}/100` : "—";
      badge.className = `badge ${!last ? "" : last.failed ? "danger" : last.warnings ? "warning" : "success"}`;
    }
  }

  window.runAutoQaCheck = async function (notify = false) {
    const { pid } = cur();
    if (!pid) { if (notify) toast("Hãy chọn dự án trước.", "warning"); return null; }
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(pid)}/qa-check`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      last = data;
      renderAll();
      if (notify) toast(`🛡️ Auto-QA: <b>${data.score}/100</b> — ${data.failed ? `${data.failed} lỗi cần sửa` : data.warnings ? `${data.warnings} cảnh báo` : "Đạt chuẩn xuất video!"}`, data.failed ? "error" : data.warnings ? "warning" : "success");
      return data;
    } catch (e) {
      if (notify) toast("Lỗi Auto-QA: " + esc(e.message), "error");
      return null;
    }
  };

  window.runAutoQaFix = async function () {
    const { pid } = cur();
    if (!pid) return;
    const t = toast("⏳ Đang tự sửa lỗi bố cục & dựng lại Storyboard...", "info", 0);
    try {
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(pid)}/qa-autofix`, { rerun_steps: true });
      lastFix = res;
      last = res.after;
      if (res.project) {
        currentProject = res.project; // biến `let` toàn cục của app.js
        window.populateWorkspace(res.project);
      }
      renderAll();
      toast(`🔧 Đã tự sửa ${res.fixes.length} mục — điểm QA: <b>${res.before.score} → ${res.after.score}</b>`, res.after.failed ? "warning" : "success", 5000);
    } catch (e) {
      toast("Lỗi tự sửa: " + esc(e.message), "error", 6000);
    } finally {
      t && t.remove();
    }
  };

  window.openAutoQaModal = async function () {
    if (!cur().pid) { toast("Hãy chọn dự án trước.", "warning"); return; }
    $("modalTitle").textContent = "🛡️ Kiểm Định Chất Lượng Tự Động (Auto-QA) — 10 tiêu chí trước khi xuất video";
    $("modalBody").innerHTML = `<div id="qaModalBody" class="qa-panel" style="margin-top:0;">⏳ Đang kiểm tra...</div>`;
    $("modalBackdrop").classList.add("open");
    lastFix = null;
    await window.runAutoQaCheck(false);
    renderAll();
  };

  function mount() {
    const bar = document.querySelector(".sticky-quick-actions");
    if (bar && !$("btnStickyAutoQa")) {
      bar.insertAdjacentHTML("afterbegin", `<button class="sm" id="btnStickyAutoQa" onclick="openAutoQaModal()" title="Kiểm tra & Tự sửa lỗi bố cục (Auto-QA)">🛡️ Auto-QA <span id="qaScoreBadge" class="badge">—</span></button>`);
    }
    const anchor = $("step8RenderPanel");
    if (anchor && !$("qaInlinePanel")) {
      anchor.insertAdjacentHTML("beforebegin", `<div class="panel" id="qaInlinePanel">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
          <h2 style="margin:0;">🛡️ Kiểm tra & Tự sửa lỗi bố cục (Auto-QA) trước khi Render</h2>
          <button class="sm primary" onclick="runAutoQaCheck(true)">🛡️ Kiểm tra ngay</button></div>
        <div id="qaInlineBody" class="qa-panel"></div></div>`);
    }
    renderAll();
  }

  function init() {
    mount();
    document.addEventListener("studio:projectloaded", () => { last = null; lastFix = null; renderAll(); window.runAutoQaCheck(false); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
