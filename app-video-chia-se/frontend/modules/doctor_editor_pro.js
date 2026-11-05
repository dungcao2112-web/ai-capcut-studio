// -*- coding: utf-8 -*-
// Doctor Editor Pro: nâng cấp Modal "Cắt & Tách hình Bác Sĩ" (openDoctorImageEditorModal) mà không sửa app.js:
//  • Zoom lăn chuột & kéo dịch ảnh (Alt/Space + kéo, hoặc chuột phải/giữa) trong khung cắt
//  • Màu nền thẻ: Trong suốt | Trắng kem #FFFDF9 | Be ấm #F6EFE6 | Xanh y khoa #F0F7FF
//  • ✨ Tự làm nét & cân bằng sáng (CLAHE + Unsharp + khử nhiễu) + tông ấm, độ mạnh tuỳ chỉnh
//  • ⚡ Tách nền & Làm nét Hàng Loạt cho toàn bộ ảnh đã tải lên (POST /batch-process-images)
// Tuỳ chọn được gắn vào các request edit/upload-doctor-image hiện có (route cũ nhận thêm tham số tuỳ chọn).
(function () {
  "use strict";
  const OPT_KEY = "vdcs.doc.opts";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, t, ms) => (window.showToast ? window.showToast(m, t, ms) : null);
  const cur = () => (window.studioCurrent ? window.studioCurrent() : { pid: "" });
  const SWATCHES = [["transparent", "Trong suốt (PNG)"], ["#FFFDF9", "Trắng kem #FFFDF9"], ["#F6EFE6", "Be ấm #F6EFE6"], ["#F0F7FF", "Xanh y khoa #F0F7FF"]];

  const opts = Object.assign({ enhance: true, enhance_strength: 1.0, warm_tone: true, card_bg: "transparent" },
    (() => { try { return JSON.parse(localStorage.getItem(OPT_KEY) || "{}"); } catch (e) { return {}; } })());
  const saveOpts = () => { try { localStorage.setItem(OPT_KEY, JSON.stringify(opts)); } catch (e) { /* bỏ qua */ } };
  function requestOpts() {
    const o = { enhance: !!opts.enhance, enhance_strength: Number(opts.enhance_strength) || 1, warm_tone: !!opts.warm_tone };
    if (opts.card_bg && opts.card_bg !== "transparent") o.card_bg = opts.card_bg;
    return o;
  }
  window.DoctorEditorPro = { options: opts, requestOpts };

  // ---- Gắn tuỳ chọn vào request cũ ----
  const isDocUrl = (u) => /\/api\/projects\/[^/]+\/(edit-doctor-image|upload-doctor-image)(\?|$)/.test(String(u));
  function wrapNetwork() {
    const origPost = window.apiPost;
    if (typeof origPost === "function" && !origPost.__dp) {
      window.apiPost = async function (url, body = {}) {
        if (isDocUrl(url)) body = Object.assign({}, requestOpts(), body);
        const res = await origPost.call(this, url, body);
        if (isDocUrl(url) && res && res.result) showMetrics(res.result);
        return res;
      };
      window.apiPost.__dp = true;
    }
    const origFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      if (typeof input === "string" && isDocUrl(input) && input.includes("upload-doctor-image?")) {
        const q = new URLSearchParams(requestOpts()).toString();
        input = `${input}&${q}`;
      }
      return origFetch(input, init);
    };
  }

  function showMetrics(r) {
    const el = $("dpMetrics");
    if (!el || !r) return;
    const eng = r.engine === "fallback" ? "Dự phòng (không cần model AI)" : "AI u2net";
    let sharp = "";
    if (r.sharpness_before && r.sharpness_after) {
      const gain = Math.round(((r.sharpness_after - r.sharpness_before) / Math.max(1, r.sharpness_before)) * 100);
      sharp = ` • Độ nét: <b>${Math.round(r.sharpness_before)} → ${Math.round(r.sharpness_after)}</b> (${gain >= 0 ? "+" : ""}${gain}%)`;
    }
    el.innerHTML = `⚙️ Tách nền: <b>${eng}</b>${sharp}${r.card_bg ? ` • Nền thẻ <b>${esc(r.card_bg)}</b>` : ""}`;
  }

  // ---- Zoom / Pan trong khung cắt ----
  const zp = { z: 1, x: 0, y: 0, panning: false, sx: 0, sy: 0, ox: 0, oy: 0, space: false, src: "" };
  function applyZoom() {
    const layer = $("docCropZoomLayer");
    const stage = $("docCropStage");
    if (!layer || !stage) return;
    const w = stage.clientWidth, h = stage.clientHeight;
    zp.x = Math.min(0, Math.max(w - w * zp.z, zp.x));
    zp.y = Math.min(0, Math.max(h - h * zp.z, zp.y));
    layer.style.transform = `translate(${zp.x}px, ${zp.y}px) scale(${zp.z})`;
    const lab = $("dpZoomLabel");
    if (lab) lab.textContent = `${Math.round(zp.z * 100)}%`;
  }
  function zoomAt(factor, cx, cy) {
    const nz = Math.max(1, Math.min(6, zp.z * factor));
    zp.x = cx - ((cx - zp.x) * nz) / zp.z;
    zp.y = cy - ((cy - zp.y) * nz) / zp.z;
    zp.z = nz;
    applyZoom();
  }
  window.docZoomBy = (f) => { const s = $("docCropStage"); if (s) zoomAt(f, s.clientWidth / 2, s.clientHeight / 2); };
  window.docZoomReset = () => { zp.z = 1; zp.x = 0; zp.y = 0; applyZoom(); };

  function mountZoom() {
    const stage = $("docCropStage");
    const img = $("docModalRawImg");
    const rect = $("docCropRect");
    if (!stage || !img || $("docCropZoomLayer")) return;
    const layer = document.createElement("div");
    layer.id = "docCropZoomLayer";
    stage.insertBefore(layer, img);
    layer.appendChild(img);
    if (rect) layer.appendChild(rect);
    window.docZoomReset();
    img.addEventListener("load", () => { const base = img.src.split("&t=")[0]; if (base !== zp.src) { zp.src = base; window.docZoomReset(); } });
    stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = stage.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    stage.addEventListener("contextmenu", (e) => e.preventDefault());
    // Capture ở phần tử cha để chặn thao tác khoanh vùng gốc khi đang kéo ảnh
    stage.parentElement.addEventListener("mousedown", (e) => {
      if (!stage.contains(e.target)) return;
      const pan = e.altKey || zp.space || e.button === 1 || e.button === 2;
      if (!pan) return;
      e.stopPropagation(); e.preventDefault();
      Object.assign(zp, { panning: true, sx: e.clientX, sy: e.clientY, ox: zp.x, oy: zp.y });
      stage.classList.add("dp-panning");
    }, true);
  }
  window.addEventListener("mousemove", (e) => { if (!zp.panning) return; zp.x = zp.ox + e.clientX - zp.sx; zp.y = zp.oy + e.clientY - zp.sy; applyZoom(); });
  window.addEventListener("mouseup", () => { if (zp.panning) { zp.panning = false; $("docCropStage")?.classList.remove("dp-panning"); } });
  window.addEventListener("keydown", (e) => { if (e.code === "Space" && $("docCropStage") && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "")) { zp.space = true; e.preventDefault(); } });
  window.addEventListener("keyup", (e) => { if (e.code === "Space") zp.space = false; });

  // ---- Thanh công cụ Pro trong Modal ----
  function toolbarHtml() {
    return `<div class="dp-toolbar" id="dpToolbar">
      <div class="dp-group"><b>🎨 Nền thẻ:</b>${SWATCHES.map(([v, t]) => `<button type="button" class="dp-swatch ${v === "transparent" ? "transparent" : ""} ${opts.card_bg === v ? "on" : ""}" data-bg="${v}" title="${t}" style="${v !== "transparent" ? `background:${v} !important;` : ""}"></button>`).join("")}</div>
      <div class="dp-group"><label style="margin:0; display:inline-flex; gap:5px; align-items:center;"><input type="checkbox" id="dpEnhance" style="width:auto;" ${opts.enhance ? "checked" : ""}/> ✨ Tự làm nét & cân bằng sáng</label>
        <input type="range" id="dpStrength" min="0.4" max="1.6" step="0.1" value="${opts.enhance_strength}" style="width:90px;" title="Độ mạnh làm nét"/>
        <label style="margin:0; display:inline-flex; gap:5px; align-items:center;"><input type="checkbox" id="dpWarm" style="width:auto;" ${opts.warm_tone ? "checked" : ""}/> 🌤 Tông ấm</label></div>
      <div class="dp-group dp-zoom" title="Lăn chuột để zoom • Alt/Space + kéo (hoặc chuột phải) để dịch ảnh">🔍
        <button type="button" class="sm" onclick="docZoomBy(1/1.25)">−</button><span id="dpZoomLabel">100%</span>
        <button type="button" class="sm" onclick="docZoomBy(1.25)">＋</button><button type="button" class="sm" onclick="docZoomReset()">⟲</button></div>
      <button type="button" class="sm success" onclick="batchProcessAllDoctorImages()">⚡ Tách nền & Làm nét Hàng Loạt</button>
      <div class="dp-metrics" id="dpMetrics" style="width:100%;">💡 Lăn chuột trên ảnh gốc để phóng to • Giữ <b>Alt</b> hoặc <b>Space</b> rồi kéo để dịch ảnh • Kéo chuột thường để khoanh vùng Bác Sĩ</div>
    </div>`;
  }

  function mountToolbar() {
    const stage = $("docCropStage");
    if (!stage || $("dpToolbar")) return;
    const grid = stage.closest(".grid-2");
    if (!grid) return;
    grid.insertAdjacentHTML("beforebegin", toolbarHtml());
    const tb = $("dpToolbar");
    const changed = () => { saveOpts(); if (typeof window.refreshDocModalPreview === "function") window.refreshDocModalPreview(true); };
    tb.querySelectorAll(".dp-swatch").forEach((b) => b.addEventListener("click", () => {
      opts.card_bg = b.dataset.bg;
      tb.querySelectorAll(".dp-swatch").forEach((x) => x.classList.toggle("on", x === b));
      const prev = $("docModalPreviewImg")?.parentElement;
      if (prev) prev.style.backgroundColor = b.dataset.bg === "transparent" ? "#f3ead8" : b.dataset.bg;
      changed();
    }));
    $("dpEnhance").addEventListener("change", (e) => { opts.enhance = e.target.checked; changed(); });
    $("dpWarm").addEventListener("change", (e) => { opts.warm_tone = e.target.checked; changed(); });
    $("dpStrength").addEventListener("change", (e) => { opts.enhance_strength = Number(e.target.value); changed(); });
  }

  // ---- ⚡ Xử lý hàng loạt ----
  window.batchProcessAllDoctorImages = async function () {
    const { pid } = cur();
    if (!pid) { toast("Hãy chọn dự án trước.", "warning"); return; }
    const modeEl = $("docModalModeSelect") || $("selDoctorEditMode");
    const mode = (modeEl && modeEl.value) || "cutout";
    const status = $("doctorBatchStatusMsg");
    const t = toast("⏳ Đang tách nền & làm nét <b>toàn bộ ảnh</b>...", "info", 0);
    if (status) { status.style.display = "block"; status.innerHTML = "⏳ Đang tách nền &amp; làm nét hàng loạt..."; }
    try {
      if (typeof window.saveProjectSettings === "function") await window.saveProjectSettings();
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(pid)}/batch-process-images`, Object.assign({ mode }, requestOpts()));
      if (res.project) {
        currentProject = res.project; // biến `let` toàn cục của app.js
        window.populateWorkspace(res.project);
      }
      const ts = Date.now();
      const cards = (res.results || []).map((r) => {
        const gain = r.sharpness_before ? Math.round(((r.sharpness_after - r.sharpness_before) / r.sharpness_before) * 100) : null;
        return `<div class="dp-r"><img src="/api/projects/${encodeURIComponent(pid)}/file?path=${encodeURIComponent(r.edited_rel)}&t=${ts}" alt=""/><div><b>#${r.i}</b> ${esc(r.name)}</div><div>${gain !== null ? `Độ nét ${gain >= 0 ? "+" : ""}${gain}%` : ""} ${r.engine === "fallback" ? "• dự phòng" : ""}</div></div>`;
      }).join("");
      const skipped = (res.skipped || []).map((s) => `#${s.i} ${esc(s.name)}: ${esc(s.reason)}`).join(" • ");
      const html = `✅ Đã xử lý <b>${res.processed_count}</b> ảnh trong ${res.elapsed_sec}s${skipped ? `<br>⏭️ Bỏ qua: ${skipped}` : ""}${res.step6_warning ? `<br>⚠️ ${esc(res.step6_warning)}` : ""}<div class="dp-batch-report">${cards}</div>`;
      if (status) status.innerHTML = html;
      if ($("dpMetrics")) $("dpMetrics").innerHTML = `✅ Hàng loạt: ${res.processed_count} ảnh • ${res.elapsed_sec}s`;
      if ($("docModalItemSelect") && typeof window.refreshDocModalPreview === "function") window.refreshDocModalPreview(true);
      toast(`⚡ Đã tách nền & làm nét <b>${res.processed_count}</b> ảnh${(res.skipped || []).length ? ` (bỏ qua ${res.skipped.length})` : ""}.`, "success", 4200);
    } catch (e) {
      if (status) status.innerHTML = `<span style="color:var(--sp-bad)">❌ ${esc(e.message)}</span>`;
      toast("Lỗi xử lý hàng loạt: " + esc(e.message), "error", 6000);
    } finally {
      t && t.remove();
    }
  };

  function mountMainButton() {
    const box = $("doctorUploadAndEditBox");
    const ref = box && box.querySelector('button[onclick="applyDoctorExtractToAllItems()"]');
    if (!ref || $("dpMainBatchBtn")) return;
    ref.insertAdjacentHTML("afterend", `<button id="dpMainBatchBtn" class="sm success" onclick="batchProcessAllDoctorImages()" title="Tách nền + làm nét + đóng khung đồng bộ cho mọi ảnh đã tải lên">⚡ Tách nền &amp; Làm nét Hàng Loạt</button>`);
  }

  function wrapModal() {
    const orig = window.openDoctorImageEditorModal;
    if (typeof orig !== "function" || orig.__dp) return;
    window.openDoctorImageEditorModal = async function (...args) {
      const p = orig.apply(this, args);
      mountToolbar();
      mountZoom();
      return p;
    };
    window.openDoctorImageEditorModal.__dp = true;
  }

  function init() { wrapNetwork(); wrapModal(); mountMainButton(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
