// -*- coding: utf-8 -*-
// Live Preview 9:16 — Interactive Storyboard & Summary Board Canvas (xem ngay, chưa cần Remotion).
// Cập nhật tức thì khi gõ #inpScript, #inpTitle, ô Yêu cầu thiết kế #inpAnhNhacCustomRequest hoặc khi tải/sửa ảnh bác sĩ.
// API global: LivePreview9x16.goTo(i) | .next() | .prev() | .refresh() | livePreviewGoTo(i)
(function () {
  "use strict";
  const OPEN_KEY = "vdcs.lp.open";
  const ASPECT_KEY = "vdcs.lp.aspect";
  const $ = (id) => document.getElementById(id);
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* bỏ qua */ } },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cur = () => (window.studioCurrent ? window.studioCurrent() : { pid: "", project: null });

  // Bản JS tương đương backend/services/visual_prompt.py (giữ đồng bộ từ khoá)
  const DEFAULT_STYLE = { bgTheme: "beige", bgColor: "#F6EFE6", cardColor: "#FFFDF9", nameColor: "#8A4B12", accent: "#B7791F",
    heroImageScale: 1, centerInfoPills: true, doctorCardFrame: false, summaryLargeText: false, nameStrokeBold: false };
  const RULES = [
    ["Nền be ấm", ["nền màu be", "nền be", "màu be", "be ấm", "tông be", "nền kem", "#f6efe6"], { bgTheme: "beige", bgColor: "#F6EFE6", cardColor: "#FFFDF9" }],
    ["Hồng phấn Mẹ & Bé", ["hồng phấn", "nền hồng", "mẹ & bé", "mẹ và bé", "hồng pastel"], { bgTheme: "beige", bgColor: "#FCE8EC", cardColor: "#FFF8FA", accent: "#D6336C", nameColor: "#C2255C" }],
    ["Xanh y khoa", ["xanh y khoa", "nền y khoa", "xanh y tế", "#f0f7ff"], { bgTheme: "beige", bgColor: "#F0F7FF", cardColor: "#FFFFFF", accent: "#1C64B8" }],
    ["Nền tối", ["nền tối", "nền đen", "dark mode", "nền tím"], { bgTheme: "dark", bgColor: "#0F172A", cardColor: "#1E293B", nameColor: "#FFD54F" }],
    ["Ảnh to", ["phóng to khung ảnh", "ảnh to", "ảnh lớn", "phóng to ảnh", "ảnh bác sĩ to", "to rõ kịch khung"], { heroImageScale: 1.15 }],
    ["Căn giữa", ["căn giữa"], { centerInfoPills: true }],
    ["Thẻ bác sĩ", ["khung thẻ bác sĩ", "thẻ bác sĩ", "chuẩn y khoa", "phong cách bác sĩ"], { doctorCardFrame: true, accent: "#1C64B8" }],
    ["Tổng hợp chữ to", ["bảng tổng hợp chữ to", "tổng hợp chữ to", "chữ to rõ", "bảng tổng hợp to"], { summaryLargeText: true }],
    ["Chữ vàng viền đậm", ["chữ vàng", "viền đậm"], { nameColor: "#F5B700", nameStrokeBold: true }],
  ];
  function parseVisualPrompt(text) {
    const low = String(text || "").toLowerCase();
    const out = { matched: [] };
    for (const [label, keys, ch] of RULES) if (keys.some((k) => low.includes(k))) { Object.assign(out, ch); out.matched.push(label); }
    const mHex = low.match(/nền[^#\n;]{0,20}#([0-9a-f]{6})\b/);
    if (mHex) { out.bgColor = "#" + mHex[1].toUpperCase(); out.matched.push("Nền #" + mHex[1].toUpperCase()); }
    const mPct = low.match(/(?:phóng to|ảnh)[^\d\n;]{0,24}(\d{2,3})\s*%/);
    if (mPct && out.heroImageScale && +mPct[1] >= 80 && +mPct[1] <= 160) out.heroImageScale = +mPct[1] / 100;
    return out;
  }
  window.parseVisualPromptJS = parseVisualPrompt;

  const state = { server: null, idx: 0, aspect: ls.get(ASPECT_KEY, "9:16"), view: null };
  const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/[^a-z0-9]+/g, " ").trim();

  function buildView() {
    const srv = state.server || { items: [], style: {} };
    const scriptTxt = $("inpScript")?.value || "";
    const titleInp = ($("inpTitle")?.value || "").trim();
    const outline = typeof window.parseScriptOutlineJS === "function" ? window.parseScriptOutlineJS(scriptTxt, titleInp) : { entries: [] };
    const byName = new Map((srv.items || []).map((it) => [norm(it.name), it]));
    const byIdx = new Map((srv.items || []).map((it) => [Number(it.i), it]));
    let items = (outline.entries || []).map((e, k) => {
      const match = byName.get(norm(e.heading)) || byIdx.get(k + 1) || {};
      return { i: k + 1, name: e.heading, bullets: e.bullets && e.bullets.length ? e.bullets : (match.bullets || []), image_url: match.image_url || "" };
    });
    if (!items.length) items = (srv.items || []).map((it) => ({ ...it }));
    const vp = $("inpAnhNhacCustomRequest")?.value || srv.visual_prompt || "";
    const parsed = parseVisualPrompt(vp);
    const style = Object.assign({}, DEFAULT_STYLE, srv.style || {}, parsed);
    style.matched = parsed.matched.length ? parsed.matched : (srv.style && srv.style.matched) || [];
    const title = (typeof window.studioOutlineTitle === "function" ? window.studioOutlineTitle(scriptTxt) : "") || titleInp || outline.title || srv.title || "";
    return { title, subtitle: outline.subtitle || srv.subtitle || "", summarySubtitle: srv.summary_subtitle || "",
      summaryNote: srv.summary_note || "", items, style, aspect: state.aspect };
  }

  let rafPending = false;
  function render() {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      const cv = $("lpCanvas");
      if (!cv || !window.LivePreviewRender) return;
      state.view = buildView();
      const total = state.view.items.length + (state.view.items.length ? 1 : 0);
      if (state.idx >= total) state.idx = Math.max(0, total - 1);
      window.LivePreviewRender.draw(cv, state.view, state.idx, render);
      cv.style.aspectRatio = state.aspect === "1:1" ? "1 / 1" : "9 / 16";
      renderChrome(total);
    });
  }

  function renderChrome(total) {
    const v = state.view;
    const n = v.items.length;
    const isSum = n && state.idx >= n;
    $("lpLabel").innerHTML = !n ? "Chưa có mục" : isSum ? `<b>∑ Bảng Tổng Hợp</b> (${n} mục)` : `Slide <b>${state.idx + 1}</b> / ${n}`;
    $("lpPrev").disabled = state.idx <= 0;
    $("lpNext").disabled = state.idx >= total - 1;
    $("lpDots").innerHTML = v.items.map((it, k) => `<button class="lp-dot ${k === state.idx ? "on" : ""}" data-k="${k}" title="${esc(it.name)}">${k + 1}</button>`).join("")
      + (n ? `<button class="lp-dot sum ${isSum ? "on" : ""}" data-k="${n}" title="Bảng Tổng Hợp">∑</button>` : "");
    $("lpDots").querySelectorAll(".lp-dot").forEach((b) => (b.onclick = () => goTo(Number(b.dataset.k))));
    document.querySelectorAll(".lp-aspect button").forEach((b) => b.classList.toggle("on", b.dataset.a === state.aspect));
    const chips = (v.style.matched || []).map((m) => `<span class="badge info">${esc(m)}</span>`).join(" ");
    const mNum = String(v.title || "").match(/^(?:TOP\s+)?(\d+)\s+\S/i);
    const warn = mNum && n && Number(mNum[1]) !== n ? `<div class="lp-warn">⚠️ Tiêu đề ghi <b>${mNum[1]}</b> nhưng danh sách có <b>${n}</b> mục — bấm "Chuẩn hoá" trong khung Phân tích kịch bản.</div>` : "";
    $("lpInfo").innerHTML = `<div>🎨 ${chips || '<span class="badge">Mặc định: Nền be ấm</span>'}</div>${warn}`;
    document.querySelectorAll("[data-sp-entry]").forEach((el) => el.classList.toggle("sp-entry-active", Number(el.dataset.spEntry) === state.idx));
  }

  function goTo(k) { state.idx = Math.max(0, Number(k) || 0); setOpen(true); render(); }
  function step(d) { state.idx = Math.max(0, state.idx + d); render(); }

  async function fetchServer() {
    const { pid } = cur();
    if (!pid) { state.server = null; render(); return; }
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(pid)}/preview-data`);
      state.server = res.ok ? await res.json() : null;
    } catch (e) { state.server = null; }
    render();
  }
  let fetchTimer = null;
  const fetchSoon = () => { clearTimeout(fetchTimer); fetchTimer = setTimeout(fetchServer, 250); };

  function exportPng() {
    const cv = $("lpCanvas");
    if (!cv) return;
    const n = state.view ? state.view.items.length : 0;
    const name = `${cur().pid || "preview"}_${state.idx >= n ? "bang_tong_hop" : "slide_" + String(state.idx + 1).padStart(2, "0")}.png`;
    cv.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      if (window.showToast) window.showToast(`Đã xuất ảnh <b>${esc(name)}</b> (${cv.width}×${cv.height})`, "success");
    }, "image/png");
  }

  function setOpen(open, persist = false) {
    document.body.classList.toggle("lp-open", !!open);
    if (persist) ls.set(OPEN_KEY, open ? "1" : "0");
    if (open) render();
  }

  function mount() {
    if ($("lpDock")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <aside id="lpDock" class="lp-dock" aria-label="Xem trước video 9:16">
        <div class="lp-head"><b>📱 Xem trước Video</b>
          <div class="lp-aspect"><button data-a="9:16" title="Khung dọc 1080×1920">9:16</button><button data-a="1:1" title="Khung vuông 1080×1080 (Remotion hiện tại)">1:1</button></div>
          <button class="sm" id="lpClose" title="Ẩn khung xem trước">✕</button></div>
        <div class="lp-stage"><canvas id="lpCanvas" width="1080" height="1920"></canvas></div>
        <div class="lp-nav"><button class="sm" id="lpPrev">‹ Trước</button><span id="lpLabel"></span><button class="sm" id="lpNext">Sau ›</button></div>
        <div class="lp-dots" id="lpDots"></div>
        <div class="lp-tools"><button class="sm primary" id="lpPng">📸 Xuất PNG slide này</button><button class="sm" id="lpSync" title="Tải lại ảnh & cấu hình từ dự án">🔄 Đồng bộ</button></div>
        <div class="lp-info" id="lpInfo"></div>
      </aside>
      <button id="lpToggle" class="lp-toggle" title="Bật/tắt khung xem trước 9:16">📱 Xem trước 9:16</button>`);
    $("lpPrev").onclick = () => step(-1);
    $("lpNext").onclick = () => step(1);
    $("lpPng").onclick = exportPng;
    $("lpSync").onclick = fetchServer;
    $("lpClose").onclick = () => setOpen(false, true);
    $("lpToggle").onclick = () => setOpen(!document.body.classList.contains("lp-open"), true);
    document.querySelectorAll(".lp-aspect button").forEach((b) => (b.onclick = () => { state.aspect = b.dataset.a; ls.set(ASPECT_KEY, state.aspect); render(); }));
  }

  function wire() {
    const debounced = (() => { let t; return () => { clearTimeout(t); t = setTimeout(render, 120); }; })();
    ["inpScript", "inpTitle", "inpAnhNhacCustomRequest"].forEach((id) => $(id)?.addEventListener("input", debounced));
    document.addEventListener("studio:projectloaded", () => { state.idx = 0; fetchServer(); });
    document.addEventListener("studio:themechange", render);
    const origPop = window.populateWorkspace;
    if (typeof origPop === "function" && !origPop.__lp) {
      window.populateWorkspace = function (...a) { const r = origPop.apply(this, a); fetchSoon(); return r; };
      window.populateWorkspace.__lp = true;
    }
    const origSwitch = window.switchTab;
    if (typeof origSwitch === "function" && !origSwitch.__lp) {
      window.switchTab = function (tabId, ...rest) {
        const r = origSwitch.call(this, tabId, ...rest);
        const pref = ls.get(OPEN_KEY, "1") === "1";
        setOpen(pref && (tabId === "tab0" || tabId === "tab3"));
        return r;
      };
      window.switchTab.__lp = true;
    }
    document.addEventListener("keydown", (e) => {
      if (!e.altKey || !document.body.classList.contains("lp-open")) return;
      if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    });
    if (document.fonts && document.fonts.load) {
      Promise.all(["400 80px Anton", "700 60px 'Barlow Condensed'", "600 30px 'Barlow Condensed'"].map((f) => document.fonts.load(f).catch(() => null))).then(render);
    }
  }

  window.LivePreview9x16 = { goTo, next: () => step(1), prev: () => step(-1), refresh: fetchServer, render, state };
  window.livePreviewGoTo = goTo;

  function init() {
    mount();
    wire();
    setOpen(ls.get(OPEN_KEY, "1") === "1");
    fetchServer();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
