// -*- coding: utf-8 -*-
// 🖼️ Khung & Ghép ảnh cho từng mục — mở bằng cách BẤM VÀO ẢNH trên khung Xem trước, nút "🖼️ Khung" ở bảng mục,
// hoặc nút trên thẻ ảnh Bước 3. Tab 1: Chọn khung hình (cắt theo ý, chọn tỉ lệ). Tab 2: Ghép nhiều ảnh (collage_builder.js).
// API: openImageFramer(itemIndex, tab = "frame" | "collage")
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, t, ms) => (window.showToast ? window.showToast(m, t, ms) : null);
  const cur = () => (window.studioCurrent ? window.studioCurrent() : { pid: "", project: null });
  const ASPECTS = [["free", "Tự do", null], ["4:3", "4:3", 4 / 3], ["3:2", "3:2", 1.5], ["16:9", "16:9", 16 / 9], ["1:1", "1:1", 1], ["3:4", "3:4 dọc", 3 / 4]];
  const S = { pid: "", idx: 1, info: null, tab: "frame", aspect: "free", cropper: null };

  function items() {
    const p = cur().project;
    return ((p && p.bang && p.bang.items) || []).map((it) => ({ i: Number(it.i), name: it.display_name || it.ten || "" }));
  }

  function applyProject(proj) {
    if (!proj) return;
    currentProject = proj; // biến `let` toàn cục của app.js
    window.populateWorkspace(proj);
  }

  async function load(idx) {
    const res = await fetch(`/api/projects/${encodeURIComponent(S.pid)}/item-media?item_index=${idx}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    S.idx = idx;
    S.info = data;
    S.aspect = data.aspect || "free";
    return data;
  }

  function shell() {
    const list = items();
    const opts = list.map((it) => `<option value="${it.i}" ${it.i === S.idx ? "selected" : ""}>Mục #${it.i}: ${esc(it.name)}</option>`).join("");
    $("modalTitle").textContent = "🖼️ Khung hình & Ghép ảnh cho từng mục";
    $("modalBody").innerHTML = `<div class="fr-wrap">
      <div class="fr-top">
        <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
          <button class="sm" id="frPrev">◀</button><select id="frItem" style="width:auto; min-width:240px; font-weight:700;">${opts}</select><button class="sm" id="frNext">▶</button>
        </div>
        <div class="fr-tabs"><button class="sm ${S.tab === "frame" ? "on" : ""}" data-tab="frame">🖼️ Chọn khung hình</button>
          <button class="sm ${S.tab === "collage" ? "on" : ""}" data-tab="collage">🧩 Ghép nhiều ảnh (2 · 3 · 4 · 6)</button></div>
      </div>
      <div id="frBody"></div></div>`;
    $("frItem").onchange = (e) => switchItem(Number(e.target.value));
    $("frPrev").onclick = () => stepItem(-1);
    $("frNext").onclick = () => stepItem(1);
    document.querySelectorAll(".fr-tabs button").forEach((b) => (b.onclick = () => { S.tab = b.dataset.tab; shell(); body(); }));
  }

  async function switchItem(idx) {
    try { await load(idx); shell(); body(); if (window.livePreviewGoTo) window.livePreviewGoTo(idx - 1); } catch (e) { toast(esc(e.message), "error"); }
  }
  function stepItem(d) {
    const list = items();
    const k = list.findIndex((it) => it.i === S.idx);
    const next = list[k + d];
    if (next) switchItem(next.i);
  }

  function body() {
    if (S.tab === "collage") { if (window.StudioCollage) window.StudioCollage.render($("frBody")); return; }
    const info = S.info;
    if (!info.source_url) {
      $("frBody").innerHTML = `<div class="fr-empty">📭 Mục này chưa có ảnh. Hãy tải ảnh lên, hoặc dùng <b>🔍 Tự tìm &amp; Gắn Hình Ảnh</b> ở Bước 1.
        <div style="margin-top:10px;"><input type="file" id="frUpload" accept="image/*" style="display:none;"/><button class="success" onclick="document.getElementById('frUpload').click()">📤 Tải ảnh cho mục này</button></div></div>`;
      $("frUpload").onchange = (e) => uploadSource(e.target.files[0]);
      return;
    }
    $("frBody").innerHTML = `
      <div class="fr-aspects"><b>📐 Tỉ lệ khung:</b>${ASPECTS.map(([k, t]) => `<button class="sm ${S.aspect === k ? "on" : ""}" data-a="${k}">${t}</button>`).join("")}
        <span class="step-msg">Kéo khung để dịch • kéo góc để co giãn • lăn chuột để phóng/thu</span></div>
      <div class="fr-grid">
        <div class="fr-col"><div class="fr-label">1. Ảnh gốc ${info.source_size ? `(${info.source_size[0]}×${info.source_size[1]})` : ""}</div><div id="frCropHost"></div></div>
        <div class="fr-col"><div class="fr-label">2. Kết quả trên video</div><div class="fr-result"><canvas id="frResult"></canvas></div>
          <div class="step-msg" id="frCropInfo"></div></div>
      </div>
      <div class="fr-foot"><span><input type="file" id="frUpload" accept="image/*" style="display:none;"/>
          <button class="sm" onclick="document.getElementById('frUpload').click()">📤 Đổi ảnh khác</button>
          <button class="sm" id="frReset">↺ Lấy toàn ảnh</button></span>
        <span><button onclick="closeModal()">Đóng</button>
          <button class="primary" id="frApply">💾 Áp dụng khung này</button>
          <button class="success" id="frApplyNext">✅ Áp dụng &amp; Qua mục sau</button></span></div>`;
    const ratio = (ASPECTS.find((a) => a[0] === S.aspect) || [])[2] || null;
    S.cropper = window.StudioCropper.mount($("frCropHost"), info.source_url, {
      aspect: ratio,
      crop: info.crop_box,
      onChange: (c, nat) => {
        const out = $("frResult");
        const ar = (c[2] * nat.natW) / Math.max(1, c[3] * nat.natH);
        window.StudioCropper.drawCrop(out, S.cropper && S.cropper.image, c, 480, Math.round(480 / Math.max(0.5, Math.min(2.2, ar))));
        $("frCropInfo").innerHTML = `Vùng chọn: <b>${Math.round(c[2] * nat.natW)}×${Math.round(c[3] * nat.natH)}px</b> • tỉ lệ ${ar.toFixed(2)}`;
      },
    });
    document.querySelectorAll(".fr-aspects button").forEach((b) => (b.onclick = () => {
      S.aspect = b.dataset.a;
      document.querySelectorAll(".fr-aspects button").forEach((x) => x.classList.toggle("on", x === b));
      S.cropper.setAspect((ASPECTS.find((a) => a[0] === S.aspect) || [])[2] || null);
    }));
    $("frReset").onclick = () => S.cropper.reset();
    $("frApply").onclick = () => applyFrame(false);
    $("frApplyNext").onclick = () => applyFrame(true);
    $("frUpload").onchange = (e) => uploadSource(e.target.files[0]);
  }

  async function applyFrame(goNext) {
    const t = toast("⏳ Đang đóng khung ảnh & cập nhật video...", "info", 0);
    try {
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(S.pid)}/item-frame`, { item_index: S.idx, crop_box: S.cropper.getCrop(), aspect: S.aspect });
      applyProject(res.project);
      toast(`🖼️ Đã áp dụng khung hình cho mục #${S.idx}.${res.step6_warning ? " ⚠️ " + esc(res.step6_warning) : ""}`, "success");
      if (goNext) stepItem(1); else await switchItem(S.idx);
    } catch (e) { toast("Lỗi đóng khung: " + esc(e.message), "error", 6000); } finally { t && t.remove(); }
  }

  async function uploadSource(file) {
    if (!file) return;
    const t = toast("⏳ Đang tải ảnh lên...", "info", 0);
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(S.pid)}/upload?role=product&item_index=${S.idx}&filename=${encodeURIComponent(file.name)}`, { method: "POST", body: file });
      const data = await r.json();
      if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
      applyProject(data.project);
      S.info = null;
      await switchItem(S.idx);
      toast("Đã tải ảnh mới — hãy chọn khung hình rồi bấm Áp dụng.", "success");
    } catch (e) { toast("Lỗi tải ảnh: " + esc(e.message), "error"); } finally { t && t.remove(); }
  }

  window.openImageFramer = async function (idx = 1, tab = "frame") {
    S.pid = cur().pid;
    if (!S.pid) { toast("Hãy chọn dự án trước.", "warning"); return; }
    S.tab = tab;
    try {
      await load(Number(idx) || 1);
      shell();
      $("modalBackdrop").classList.add("open");
      body();
    } catch (e) { toast("Không mở được khung ảnh: " + esc(e.message), "error"); }
  };
  window.StudioFramer = { state: S, applyProject, reload: () => switchItem(S.idx), esc, toast };

  // ---- Điểm mở: thẻ ảnh Bước 3, bảng mục Bước 1, khung xem trước ----
  function wrapAfter(name, fn) {
    const orig = window[name];
    if (typeof orig !== "function" || orig.__fr) return;
    window[name] = function (...a) { const r = orig.apply(this, a); try { fn(); } catch (e) { /* bỏ qua */ } return r; };
    window[name].__fr = true;
  }
  function decorateCards() {
    document.querySelectorAll('.product-card[id^="prodCard_"]').forEach((card) => {
      if (card.querySelector(".fr-card-btn")) return;
      const i = Number(card.id.replace("prodCard_", ""));
      card.insertAdjacentHTML("afterbegin", `<div class="fr-card-btn"><button class="sm primary" onclick="openImageFramer(${i})">🖼️ Khung</button><button class="sm" onclick="openImageFramer(${i}, 'collage')">🧩 Ghép</button></div>`);
    });
  }
  function decorateRows() {
    document.querySelectorAll("#bangTableBody tr").forEach((tr, k) => {
      const cell = tr.querySelector('button[onclick^="openDoctorImageEditorModal"]');
      if (!cell || tr.querySelector(".fr-row-btn")) return;
      const i = Number(tr.querySelector(".bang-i")?.value) || k + 1;
      cell.insertAdjacentHTML("afterend", `<button class="sm fr-row-btn" onclick="openImageFramer(${i})" title="Chọn khung hình / Ghép nhiều ảnh cho mục #${i}">🖼️ Khung</button>`);
    });
  }
  function hookPreview() {
    const cv = $("lpCanvas");
    if (!cv || cv.__fr) return;
    cv.__fr = true;
    const hit = (e) => {
      const r = window.LivePreviewRender && window.LivePreviewRender.lastImageRect;
      if (!r) return null;
      const x = (e.offsetX / cv.clientWidth) * cv.width, y = (e.offsetY / cv.clientHeight) * cv.height;
      return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h ? r : null;
    };
    cv.addEventListener("mousemove", (e) => { cv.style.cursor = hit(e) ? "pointer" : "default"; cv.title = hit(e) ? "Bấm để chọn khung hình / ghép ảnh cho mục này" : ""; });
    cv.addEventListener("click", (e) => { const r = hit(e); if (r) window.openImageFramer(r.item); });
    const tools = document.querySelector(".lp-tools");
    if (tools) tools.insertAdjacentHTML("beforeend", `<button class="sm" id="lpFrameBtn" title="Chọn khung hình / ghép ảnh cho slide đang xem">🖼️ Khung &amp; Ghép ảnh</button>`);
    const b = $("lpFrameBtn");
    if (b) b.onclick = () => { const st = window.LivePreview9x16 && window.LivePreview9x16.state; window.openImageFramer(((st && st.idx) || 0) + 1); };
  }
  function init() {
    wrapAfter("renderProductCards", decorateCards);
    wrapAfter("renderBangTable", decorateRows);
    decorateCards(); decorateRows(); hookPreview();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
