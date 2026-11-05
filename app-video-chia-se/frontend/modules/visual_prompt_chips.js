// -*- coding: utf-8 -*-
// Quick Chips Yêu Cầu Thiết Kế ngay dưới ô yêu cầu #inpAnhNhacCustomRequest (visual_prompt) + lịch sử hay dùng.
// Bấm chip = bật/tắt câu yêu cầu chuẩn trong ô. Khi "Thực hiện yêu cầu", yêu cầu được lưu & áp dụng
// qua POST /api/projects/<pid>/visual-prompt TRƯỚC khi gọi applyAnhNhacCustomRequest gốc.
(function () {
  "use strict";
  const HIST_KEY = "vdcs.vp.history";
  const MAX_HIST = 8;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, t, ms) => (window.showToast ? window.showToast(m, t, ms) : null);
  const cur = () => (window.studioCurrent ? window.studioCurrent() : { pid: "" });

  const CHIPS = [
    ["🎨", "Nền màu be ấm (#F6EFE6)", "Nền màu be ấm (#F6EFE6)", "bg"],
    ["🖼️", "Phóng to khung ảnh chính", "Phóng to khung ảnh chính"],
    ["📐", "Căn giữa địa chỉ & thông tin", "Căn giữa địa chỉ & thông tin"],
    ["👨‍⚕️", "Khung thẻ bác sĩ chuẩn y khoa", "Khung thẻ bác sĩ chuẩn y khoa"],
    ["🌸", "Tông hồng phấn Mẹ & Bé", "Nền hồng phấn Mẹ & Bé", "bg"],
    ["✨", "Bảng tổng hợp chữ to rõ", "Bảng tổng hợp chữ to rõ"],
    ["🟡", "Chữ vàng viền đậm", "Chữ vàng viền đậm"],
  ];

  const hist = {
    load() { try { return JSON.parse(localStorage.getItem(HIST_KEY) || "[]").filter((x) => typeof x === "string"); } catch (e) { return []; } },
    save(list) { try { localStorage.setItem(HIST_KEY, JSON.stringify(list.slice(0, MAX_HIST))); } catch (e) { /* bỏ qua */ } },
    push(text) {
      const t = String(text || "").trim();
      if (!t) return;
      const list = hist.load().filter((x) => x !== t);
      list.unshift(t);
      hist.save(list);
    },
    remove(text) { hist.save(hist.load().filter((x) => x !== text)); },
  };

  const parts = (v) => String(v || "").split(/\s*;\s*|\n+/).map((x) => x.trim()).filter(Boolean);
  const has = (v, snippet) => parts(v).some((p) => p.toLowerCase() === snippet.toLowerCase());

  // Chip cùng nhóm (VD: màu nền) loại trừ nhau — chọn nền hồng sẽ tự bỏ nền be
  function toggleSnippet(snippet, group) {
    const ta = $("inpAnhNhacCustomRequest");
    if (!ta) return;
    let list = parts(ta.value);
    const idx = list.findIndex((p) => p.toLowerCase() === snippet.toLowerCase());
    if (idx >= 0) list.splice(idx, 1);
    else {
      if (group) {
        const rivals = CHIPS.filter((c) => c[3] === group && c[2] !== snippet).map((c) => c[2].toLowerCase());
        list = list.filter((p) => !rivals.includes(p.toLowerCase()));
      }
      list.push(snippet);
    }
    ta.value = list.join("; ");
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    ta.focus();
  }

  function render() {
    const ta = $("inpAnhNhacCustomRequest");
    const bar = $("qcBar");
    if (!ta || !bar) return;
    bar.innerHTML = `<span class="qc-label">⚡ Thẻ yêu cầu nhanh:</span>` + CHIPS.map(([icon, label, snippet], k) =>
      `<button type="button" class="sm qc-chip ${has(ta.value, snippet) ? "on" : ""}" data-k="${k}" title="Bấm để thêm/bỏ: ${esc(snippet)}">${icon} ${esc(label)}</button>`).join("");
    const list = hist.load();
    const hb = $("qcHistory");
    hb.innerHTML = list.length ? `<span class="qc-label">🕘 Hay dùng:</span>` + list.map((t, k) =>
      `<button type="button" class="sm qc-chip" data-h="${k}" title="${esc(t)}">${esc(t.length > 46 ? t.slice(0, 44) + "…" : t)}<span class="qc-x" data-hx="${k}" title="Xoá khỏi lịch sử">✕</span></button>`).join("") : "";
  }

  async function persistVisualPrompt(text) {
    const { pid } = cur();
    if (!pid || !text.trim()) return null;
    try {
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(pid)}/visual-prompt`, { text, apply: true });
      if (res.changes && res.changes.length) toast(`🎨 Đã áp dụng thiết kế: ${res.changes.map(esc).join(" • ")}`, "success", 3600);
      return res;
    } catch (e) {
      toast("Không lưu được yêu cầu thiết kế: " + esc(e.message), "error");
      return null;
    }
  }
  window.saveVisualPromptNow = () => persistVisualPrompt($("inpAnhNhacCustomRequest")?.value || "");

  function wrapApply() {
    const orig = window.applyAnhNhacCustomRequest;
    if (typeof orig !== "function" || orig.__qc) return;
    window.applyAnhNhacCustomRequest = async function (...args) {
      const text = $("inpAnhNhacCustomRequest")?.value || "";
      if (text.trim()) {
        hist.push(text);
        render();
        await persistVisualPrompt(text);
      }
      return orig.apply(this, args);
    };
    window.applyAnhNhacCustomRequest.__qc = true;
  }

  function mount() {
    const ta = $("inpAnhNhacCustomRequest");
    if (!ta || $("qcBar")) return;
    ta.insertAdjacentHTML("afterend", `<div id="qcBar" class="qc-bar" aria-label="Thẻ yêu cầu thiết kế"></div><div id="qcHistory" class="qc-bar qc-history"></div>`);
    $("qcBar").addEventListener("click", (e) => {
      const b = e.target.closest(".qc-chip");
      if (b) toggleSnippet(CHIPS[Number(b.dataset.k)][2], CHIPS[Number(b.dataset.k)][3]);
    });
    $("qcHistory").addEventListener("click", (e) => {
      const x = e.target.closest("[data-hx]");
      const list = hist.load();
      if (x) { e.stopPropagation(); hist.remove(list[Number(x.dataset.hx)]); render(); return; }
      const b = e.target.closest("[data-h]");
      if (b) { ta.value = list[Number(b.dataset.h)] || ""; ta.dispatchEvent(new Event("input", { bubbles: true })); ta.focus(); }
    });
    ta.addEventListener("input", render);
    render();
  }

  function init() {
    mount();
    wrapApply();
    document.addEventListener("studio:projectloaded", (e) => {
      const proj = e.detail && e.detail.project;
      const ta = $("inpAnhNhacCustomRequest");
      if (ta && proj && proj.visual_prompt && !ta.value.trim()) ta.value = proj.visual_prompt;
      render();
    });
  }
  window.VisualPromptChips = { render, history: hist, chips: CHIPS };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
