// -*- coding: utf-8 -*-
// Bước 1 — Thiết lập ẢNH cho tất cả mục TRƯỚC khi bấm "🔍 Tự tìm & Gắn Hình Ảnh":
//  ① 🧩 Mẫu ghép ảnh chung (1 ảnh / 2 / 3 / 4 / 6 ảnh) + Nền + Viền  => app tự tìm đủ ảnh & tự ghép từng mục
//  ② 🔗 Link nguồn: dán bao nhiêu link cũng được, tự nhận diện mỗi lần dán; có link => ưu tiên ảnh & thông tin
//     từ link; không có link => tự tìm web như bình thường.
// Lưu vào settings: collageLayout, collageStyle, sourceLinks, autoInfoFromSources (POST /media-settings).
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, t, ms) => (window.showToast ? window.showToast(m, t, ms) : null);
  const cur = () => (window.studioCurrent ? window.studioCurrent() : { pid: "", project: null });
  const URL_RE = /https?:\/\/[^\s<>"'`]+/gi;
  const LAYOUTS = [
    ["1", "1 ảnh", 4 / 3, [[0, 0, 1, 1]]],
    ["2-ngang", "2 ngang", 1.6, [[0, 0, 0.5, 1], [0.5, 0, 0.5, 1]]],
    ["2-doc", "2 dọc", 1, [[0, 0, 1, 0.5], [0, 0.5, 1, 0.5]]],
    ["3-1lon2nho", "1 lớn + 2", 1.5, [[0, 0, 0.62, 1], [0.62, 0, 0.38, 0.5], [0.62, 0.5, 0.38, 0.5]]],
    ["3-ngang", "3 ngang", 1.8, [[0, 0, 1 / 3, 1], [1 / 3, 0, 1 / 3, 1], [2 / 3, 0, 1 / 3, 1]]],
    ["4-luoi", "4 lưới", 4 / 3, [[0, 0, 0.5, 0.5], [0.5, 0, 0.5, 0.5], [0, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5]]],
    ["4-1lon3nho", "1 lớn + 3", 4 / 3, [[0, 0, 1, 0.62], [0, 0.62, 1 / 3, 0.38], [1 / 3, 0.62, 1 / 3, 0.38], [2 / 3, 0.62, 1 / 3, 0.38]]],
    ["6-luoi", "6 lưới", 1.5, [0, 1, 2, 3, 4, 5].map((k) => [(k % 3) / 3, Math.floor(k / 3) / 2, 1 / 3, 0.5])],
  ];
  const BGS = [["cream", "Kem"], ["beige", "Be ấm"], ["white", "Trắng"], ["transparent", "Trong suốt"]];
  const BORDERS = [["white", "Trắng"], ["brown", "Nâu"], ["gold", "Vàng"], ["none", "Không"]];
  const KIND_ICON = { facebook: "📘", tiktok: "🎵", shopee: "🛍️", lazada: "🛒", youtube: "▶️", instagram: "📸", tiki: "🛒", image: "🖼️", web: "🌐" };
  const M = { layout: "1", style: { bg: "cream", border: "white" }, links: [], autoInfo: false, status: {}, timer: null };

  const kindOf = (u) => {
    const h = (() => { try { return new URL(u).hostname; } catch (e) { return ""; } })();
    for (const k of ["facebook", "tiktok", "shopee", "lazada", "youtube", "instagram", "tiki"]) if (h.includes(k)) return k;
    return /\.(jpe?g|png|webp|bmp)(\?|$)/i.test(u) ? "image" : "web";
  };
  const shortUrl = (u) => { try { const x = new URL(u); return (x.hostname.replace(/^www\./, "") + x.pathname).slice(0, 46); } catch (e) { return u.slice(0, 46); } };
  const diagram = (l) => `<span class="cb-diag" style="width:46px;height:${Math.round(46 / l[2])}px;">${l[3].map(([x, y, w, h]) =>
    `<i style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%;"></i>`).join("")}</span>`;

  function render() {
    const box = $("msPanel");
    if (!box) return;
    const many = M.layout !== "1";
    box.innerHTML = `
      <div class="ms-step"><b>① 🧩 Mẫu ảnh cho mỗi mục</b> <span class="step-msg">— chọn trước, app tự tìm đủ ảnh &amp; tự ghép cho tất cả mục</span></div>
      <div class="ms-layouts">${LAYOUTS.map((l) => `<button type="button" class="sm cb-lay ${l[0] === M.layout ? "on" : ""}" data-l="${l[0]}" title="${l[1]}">${diagram(l)}<small>${l[1]}</small></button>`).join("")}</div>
      ${many ? `<div class="cb-styles"><b>🎨 Nền:</b>${BGS.map(([k, t]) => `<button type="button" class="sm ${M.style.bg === k ? "on" : ""}" data-bg="${k}">${t}</button>`).join("")}
        <b style="margin-left:8px;">🖼️ Viền ảnh:</b>${BORDERS.map(([k, t]) => `<button type="button" class="sm ${M.style.border === k ? "on" : ""}" data-border="${k}">${t}</button>`).join("")}</div>` : ""}
      <div class="ms-step" style="margin-top:8px;"><b>② 🔗 Link nguồn tìm ảnh &amp; thông tin</b> <span class="step-msg">— không bắt buộc. Không dán link thì app tự tìm trên web như bình thường.</span></div>
      <textarea id="msLinkInput" rows="2" placeholder="Dán link vào đây (Facebook, TikTok, Shopee, web, link ảnh...) — dán bao nhiêu cũng được, mỗi lần dán app tự nhận diện"></textarea>
      <div class="ms-links">${M.links.length ? M.links.map((u, k) => {
        const st = M.status[u];
        const badge = !st ? '<span class="badge">⏳ đang đọc</span>' : st.ok ? `<span class="badge success">✓ ${st.images} ảnh</span>` : `<span class="badge danger" title="${esc(st.error)}">⚠ không đọc được</span>`;
        return `<span class="ms-link" title="${esc(st && st.title ? st.title + " — " + u : u)}">${KIND_ICON[kindOf(u)] || "🌐"} <a href="${esc(u)}" target="_blank" rel="noopener">${esc(shortUrl(u))}</a> ${badge}<button type="button" class="sm" data-del="${k}" title="Bỏ link">✕</button></span>`;
      }).join("") : '<span class="step-msg">Chưa có link nào.</span>'}</div>
      <div class="ms-foot"><label style="margin:0; display:inline-flex; gap:6px; align-items:center;"><input type="checkbox" id="msAutoInfo" style="width:auto;" ${M.autoInfo ? "checked" : ""}/> 📝 Mục chưa có mô tả thì lấy 1 câu thông tin từ nguồn</label>
        <span>${M.links.length ? `<span class="badge info">${M.links.length} link</span> <button type="button" class="sm" id="msClear">Xoá hết link</button>` : ""}
          <button type="button" class="sm primary" id="msApplyNow" title="Áp dụng mẫu ảnh & nguồn cho các mục đã có ảnh (không tìm lại từ đầu)">🧩 Áp dụng cho các mục hiện có</button></span></div>`;
    box.querySelectorAll("[data-l]").forEach((b) => (b.onclick = () => { M.layout = b.dataset.l; saveSoon(); render(); }));
    box.querySelectorAll("[data-bg]").forEach((b) => (b.onclick = () => { M.style.bg = b.dataset.bg; saveSoon(); render(); }));
    box.querySelectorAll("[data-border]").forEach((b) => (b.onclick = () => { M.style.border = b.dataset.border; saveSoon(); render(); }));
    box.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { M.links.splice(Number(b.dataset.del), 1); saveSoon(); render(); }));
    const inp = $("msLinkInput");
    inp.addEventListener("paste", () => setTimeout(() => absorb(inp), 0));
    inp.addEventListener("input", () => { if (/\s$/.test(inp.value) || inp.value.includes("\n")) absorb(inp); });
    inp.addEventListener("blur", () => absorb(inp));
    $("msAutoInfo").onchange = (e) => { M.autoInfo = e.target.checked; saveSoon(); };
    if ($("msClear")) $("msClear").onclick = () => { M.links = []; saveSoon(); render(); };
    $("msApplyNow").onclick = applyNow;
  }

  // Tự nhận diện link mỗi lần dán: tách mọi URL, bỏ trùng, giữ phần chữ không phải link trong ô
  function absorb(inp) {
    const found = inp.value.match(URL_RE) || [];
    if (!found.length) return;
    let added = 0;
    for (let u of found) {
      u = u.replace(/[.,;:!?)\]}>…]+$/, "");
      if (!M.links.includes(u)) { M.links.push(u); added++; }
    }
    inp.value = inp.value.replace(URL_RE, "").replace(/\s{2,}/g, " ").trim();
    if (added) { toast(`🔗 Đã nhận diện <b>${added}</b> link mới (tổng ${M.links.length}).`, "success", 2200); saveSoon(true); }
    render();
    $("msLinkInput")?.focus();
  }

  function saveSoon(inspect = false) {
    clearTimeout(M.timer);
    M.timer = setTimeout(() => save(inspect), 350);
  }

  async function save(inspect = false) {
    clearTimeout(M.timer);
    M.timer = null;
    const { pid } = cur();
    if (!pid) return;
    try {
      await window.apiPost(`/api/projects/${encodeURIComponent(pid)}/media-settings`,
        { collageLayout: M.layout, collageStyle: M.style, sourceLinks: M.links, autoInfoFromSources: M.autoInfo });
      const proj = cur().project;
      if (proj) Object.assign(proj.settings = proj.settings || {}, { collageLayout: M.layout, collageStyle: { ...M.style }, sourceLinks: M.links.slice(), autoInfoFromSources: M.autoInfo });
      if (inspect) inspectLinks();
    } catch (e) { toast("Không lưu được thiết lập ảnh: " + esc(e.message), "error"); }
  }
  window.saveMediaSetupNow = save;

  async function inspectLinks() {
    const { pid } = cur();
    const todo = M.links.filter((u) => !M.status[u]);
    if (!todo.length || !pid) return;
    try {
      const res = await window.apiPost("/api/sources/inspect", { links: todo, project_id: pid });
      (res.sources || []).forEach((s) => { M.status[s.url] = s; });
      render();
    } catch (e) { todo.forEach((u) => { M.status[u] = { ok: false, error: e.message }; }); render(); }
  }

  async function applyNow() {
    const { pid } = cur();
    if (!pid) return;
    await save(false);
    const t = toast("⏳ Đang áp dụng mẫu ảnh &amp; nguồn cho tất cả mục...", "info", 0);
    try {
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(pid)}/auto-media`, {});
      currentProject = res.project; // biến `let` toàn cục của app.js
      window.populateWorkspace(res.project);
      const r = res.report || {};
      const src = (r.items || []).reduce((a, x) => a + (x.from_sources || 0), 0);
      const notes = (r.items || []).filter((x) => x.note).map((x) => `#${x.i} ${esc(x.name)}: ${esc(x.note)}`);
      toast(`🧩 Xong ${(r.items || []).length} mục — ${src} ảnh lấy từ link nguồn.${notes.length ? "<br>ℹ️ " + notes.slice(0, 4).join("<br>ℹ️ ") : ""}${r.step6_warning ? " ⚠️ " + esc(r.step6_warning) : ""}`, notes.length ? "warning" : "success", 7000);
    } catch (e) { toast("Lỗi áp dụng: " + esc(e.message), "error", 6000); } finally { t && t.remove(); }
  }

  function loadFromProject(proj) {
    const s = (proj && proj.settings) || {};
    M.layout = s.collageLayout || "1";
    M.style = Object.assign({ bg: "cream", border: "white" }, s.collageStyle || {});
    M.links = Array.isArray(s.sourceLinks) ? s.sourceLinks.slice() : [];
    M.autoInfo = !!s.autoInfoFromSources;
    M.status = {};
    render();
    if (M.links.length) inspectLinks();
  }

  function mount() {
    const host = $("presetAnhNhacBox");
    if (!host || $("msPanel")) return;
    const first = host.firstElementChild;
    const panel = document.createElement("div");
    panel.id = "msPanel";
    panel.className = "ms-panel";
    if (first) first.insertAdjacentElement("afterend", panel); else host.prepend(panel);
    render();
  }

  function wrapFetch() {
    const orig = window.parseAndFetchAnhNhacList;
    if (typeof orig !== "function" || orig.__ms) return;
    window.parseAndFetchAnhNhacList = async function (...a) {
      if (M.timer) await save(false); // đảm bảo mẫu ảnh & link vừa chọn đã được lưu trước khi tự tìm
      if (M.layout !== "1" || M.links.length) toast(`🔍 Đang tìm ảnh${M.links.length ? ` (ưu tiên ${M.links.length} link nguồn)` : ""}${M.layout !== "1" ? " & tự ghép theo mẫu đã chọn" : ""}...`, "info", 4000);
      return orig.apply(this, a);
    };
    window.parseAndFetchAnhNhacList.__ms = true;
  }

  function init() {
    mount();
    wrapFetch();
    document.addEventListener("studio:projectloaded", (e) => loadFromProject(e.detail && e.detail.project));
    if (cur().project) loadFromProject(cur().project);
  }
  window.MediaSetup = { state: M, render, save };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
