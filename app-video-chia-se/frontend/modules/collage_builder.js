// -*- coding: utf-8 -*-
// 🧩 Ghép nhiều ảnh cho 1 mục: bố cục 2 ngang / 2 dọc / 3 (1 lớn + 2 nhỏ) / 3 ngang / 4 lưới / 4 (1 lớn + 3 nhỏ) / 6 lưới.
// Mỗi ô: 📤 tải ảnh • 🖼️ dùng ảnh hiện tại • 🌐 ảnh web hợp ô nhất • ✂️ chọn khung riêng • ✕ bỏ.
// Nền thẻ (Kem/Be/Trắng/Trong suốt) & Viền ảnh (Trắng/Nâu/Vàng/Không). Xem trước = ảnh server dựng thật (khớp video).
// Ảnh chưa chọn khung được cắt thông minh giữ chữ, hoặc giữ trọn ảnh trên nền mờ khi lệch tỉ lệ nhiều.
// Server ghép ra 1 ảnh (POST /item-gallery) nên Remotion, Live Preview & CapCut dùng như ảnh thường.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const F = () => window.StudioFramer;
  const C = { layout: "2-ngang", slots: [], webNext: {}, editing: -1, cropper: null, host: null,
    style: { bg: "cream", border: "white" }, infos: [], previewTimer: null, previewSeq: 0 };
  const BG_LABELS = { cream: "Kem", beige: "Be ấm", white: "Trắng", transparent: "Trong suốt" };
  const BORDER_LABELS = { white: "Trắng", brown: "Nâu", gold: "Vàng", none: "Không viền" };
  const MODE_LABELS = { smart_crop: "✂️ Cắt thông minh (giữ chữ)", contain: "🖼️ Giữ trọn ảnh", manual: "✋ Khung tự chọn" };

  const layoutOf = (id) => (F().state.info.layouts || []).find((l) => l.id === id) || (F().state.info.layouts || [])[0];
  function init() {
    const info = F().state.info;
    C.layout = info.layout && info.layout !== "1" ? info.layout : "2-ngang";
    C.slots = (info.gallery || []).map((g) => ({ path: g.path, url: g.url, crop_box: g.crop_box }));
    if (!C.slots.length && info.source_path) C.slots = [{ path: info.source_path, url: info.source_url, crop_box: info.crop_box }];
    C.webNext = {};
    C.editing = -1;
    C.style = Object.assign({ bg: "cream", border: "white" }, info.collage_style || {});
    C.infos = [];
  }

  function diagram(l, w = 64) {
    const h = Math.round(w / l.aspect);
    return `<span class="cb-diag" style="width:${w}px;height:${h}px;">${l.cells.map(([x, y, cw, ch]) =>
      `<i style="left:${x * 100}%;top:${y * 100}%;width:${cw * 100}%;height:${ch * 100}%;"></i>`).join("")}</span>`;
  }

  function cellAspect(k) {
    const l = layoutOf(C.layout);
    const c = l.cells[k];
    return c ? (c[2] * l.aspect) / c[3] : 1;
  }

  function slotsPayload() {
    const n = layoutOf(C.layout).cells.length;
    return Array.from({ length: n }, (_, k) => (C.slots[k] ? { path: C.slots[k].path, crop_box: C.slots[k].crop_box } : { path: "" }));
  }

  // Xem trước = ảnh ghép thật do server dựng (cùng thuật toán với video), có chống gọi dồn dập
  function drawPreview() {
    clearTimeout(C.previewTimer);
    C.previewTimer = setTimeout(async () => {
      const box = $("cbPreviewBox");
      if (!box) return;
      const slots = slotsPayload();
      if (!slots.some((s) => s.path)) { box.innerHTML = `<div class="step-msg">Thêm ít nhất 1 ảnh vào ô để xem trước.</div>`; return; }
      const seq = ++C.previewSeq;
      box.classList.add("loading");
      try {
        const st = F().state;
        const d = await window.apiPost(`/api/projects/${encodeURIComponent(st.pid)}/item-gallery`,
          { item_index: st.idx, layout: C.layout, slots, style: C.style, preview_only: true });
        if (seq !== C.previewSeq || !$("cbPreviewBox")) return;
        box.innerHTML = `<img src="${d.preview_url}" alt="Xem trước ảnh ghép"/>`;
        C.infos = d.slots_info || [];
        C.host.querySelectorAll(".cb-mode").forEach((el) => {
          const info = C.infos.find((x) => x.slot === Number(el.dataset.k));
          el.textContent = info && MODE_LABELS[info.mode] ? MODE_LABELS[info.mode] : "";
        });
      } catch (e) { box.innerHTML = `<div class="step-msg" style="color:var(--sp-bad)">${F().esc(e.message)}</div>`; }
      finally { box.classList.remove("loading"); }
    }, 300);
  }

  function slotsHtml() {
    const l = layoutOf(C.layout);
    const info = F().state.info;
    return l.cells.map((_, k) => {
      const s = C.slots[k];
      return `<div class="cb-slot ${C.editing === k ? "on" : ""}">
        <div class="cb-thumb">${s && s.url ? `<img src="${s.url}" alt=""/>` : `<span>Ô ${k + 1} — trống</span>`}</div>
        <div class="cb-mode" data-k="${k}"></div>
        <div class="cb-acts">
          <button class="sm" data-act="up" data-k="${k}" title="Tải ảnh từ máy">📤</button>
          ${info.source_path ? `<button class="sm" data-act="cur" data-k="${k}" title="Dùng ảnh hiện tại của mục">🖼️</button>` : ""}
          <button class="sm" data-act="web" data-k="${k}" title="Tự tìm ảnh web hợp ô nhất (ít bị cắt chữ)">🌐</button>
          <button class="sm" data-act="crop" data-k="${k}" ${s && s.url ? "" : "disabled"} title="Chọn khung riêng cho ô này">✂️</button>
          <button class="sm danger" data-act="del" data-k="${k}" ${s && s.url ? "" : "disabled"} title="Bỏ ảnh ô này">✕</button>
        </div></div>`;
    }).join("");
  }

  function render(host) {
    C.host = host || C.host;
    if (host) init();
    const info = F().state.info;
    C.host.innerHTML = `
      <div class="cb-layouts"><b>🧩 Bố cục:</b>${(info.layouts || []).filter((l) => l.id !== "1").map((l) =>
        `<button class="sm cb-lay ${l.id === C.layout ? "on" : ""}" data-l="${l.id}" title="${F().esc(l.label)}">${diagram(l)}<small>${F().esc(l.label)}</small></button>`).join("")}</div>
      <div class="cb-styles"><b>🎨 Nền:</b>${(info.styles?.bg || Object.keys(BG_LABELS)).map((k) =>
        `<button class="sm ${C.style.bg === k ? "on" : ""}" data-bg="${k}">${BG_LABELS[k] || k}</button>`).join("")}
        <b style="margin-left:10px;">🖼️ Viền ảnh:</b>${(info.styles?.border || Object.keys(BORDER_LABELS)).map((k) =>
        `<button class="sm ${C.style.border === k ? "on" : ""}" data-border="${k}">${BORDER_LABELS[k] || k}</button>`).join("")}</div>
      <div class="fr-grid">
        <div class="fr-col"><div class="fr-label">Các ô ảnh (theo thứ tự trên bố cục)</div><div class="cb-slots">${slotsHtml()}</div>
          <div id="cbCropPanel"></div></div>
        <div class="fr-col"><div class="fr-label">Xem trước ảnh ghép</div><div class="fr-result cb-preview" id="cbPreviewBox"></div>
          <div class="step-msg">Ảnh chưa chọn khung sẽ được cắt thông minh để giữ chữ; ảnh lệch tỉ lệ nhiều được giữ trọn trên nền mờ. Bấm ✂️ để tự chọn khung.</div></div>
      </div>
      <input type="file" id="cbUpload" accept="image/*" style="display:none;"/>
      <div class="fr-foot"><span class="step-msg">Mẹo: 🌐 bấm nhiều lần để đổi sang ảnh web tiếp theo.</span>
        <span><button onclick="closeModal()">Đóng</button><button class="primary" id="cbApply">💾 Áp dụng ảnh ghép</button></span></div>`;
    C.host.querySelectorAll(".cb-lay").forEach((b) => (b.onclick = () => { C.layout = b.dataset.l; C.editing = -1; render(); }));
    C.host.querySelectorAll("[data-bg]").forEach((b) => (b.onclick = () => { C.style.bg = b.dataset.bg; render(); }));
    C.host.querySelectorAll("[data-border]").forEach((b) => (b.onclick = () => { C.style.border = b.dataset.border; render(); }));
    C.host.querySelector(".cb-slots").onclick = (e) => { const b = e.target.closest("[data-act]"); if (b) act(b.dataset.act, Number(b.dataset.k)); };
    $("cbApply").onclick = apply;
    drawPreview();
    if (C.editing >= 0) openCrop(C.editing);
  }

  async function act(a, k) {
    const st = F().state;
    if (a === "up") {
      const inp = $("cbUpload");
      inp.onchange = async () => {
        const f = inp.files[0];
        if (!f) return;
        try {
          const r = await fetch(`/api/projects/${encodeURIComponent(st.pid)}/item-gallery-upload?item_index=${st.idx}&slot=${k}&filename=${encodeURIComponent(f.name)}`, { method: "POST", body: f });
          const d = await r.json();
          if (!r.ok || d.error) throw new Error(d.error || `HTTP ${r.status}`);
          C.slots[k] = { path: d.path, url: d.url, crop_box: null };
          render();
        } catch (e) { F().toast("Lỗi tải ảnh: " + F().esc(e.message), "error"); }
        inp.value = "";
      };
      inp.click();
    } else if (a === "cur") {
      C.slots[k] = { path: st.info.source_path, url: st.info.source_url, crop_box: null };
      render();
    } else if (a === "web") {
      const cand = (C.webNext[k] = (C.webNext[k] ?? k) + 1);
      const t = F().toast(`⏳ Đang tìm ảnh web #${cand} cho ô ${k + 1}...`, "info", 0);
      try {
        const d = await window.apiPost(`/api/projects/${encodeURIComponent(st.pid)}/item-gallery-web`, { item_index: st.idx, slot: k, candidate_index: cand, layout: C.layout });
        C.slots[k] = { path: d.path, url: d.url, crop_box: null };
        C.webNext[k] = Math.max(cand, (d.tried || []).reduce((m, x) => Math.max(m, x.candidate_index), cand));
        F().toast(`🌐 Ô ${k + 1}: đã chọn ảnh hợp ô nhất trong ${(d.tried || []).length} ảnh (độ hợp ${Math.round((d.fit_score || 0) * 100)}%).`, "success");
        render();
      } catch (e) { F().toast("Không tìm được ảnh web: " + F().esc(e.message), "error", 5000); } finally { t && t.remove(); }
    } else if (a === "crop") {
      C.editing = k; render();
    } else if (a === "del") {
      C.slots[k] = null; if (C.editing === k) C.editing = -1; render();
    }
  }

  function openCrop(k) {
    const s = C.slots[k];
    const panel = $("cbCropPanel");
    if (!s || !panel) return;
    panel.innerHTML = `<div class="fr-label">✂️ Khung riêng cho ô ${k + 1} (tỉ lệ ô ${cellAspect(k).toFixed(2)})</div><div id="cbCropHost"></div>
      <div style="display:flex; gap:6px; justify-content:flex-end; margin-top:6px;"><button class="sm" id="cbCropReset">↺ Toàn ảnh</button><button class="sm success" id="cbCropDone">✓ Xong</button></div>`;
    C.cropper = window.StudioCropper.mount($("cbCropHost"), s.url, {
      aspect: cellAspect(k), crop: s.crop_box,
      onChange: (c) => { s.crop_box = c; drawPreview(); },
    });
    $("cbCropReset").onclick = () => C.cropper.reset();
    $("cbCropDone").onclick = () => { C.editing = -1; render(); };
  }

  async function apply() {
    const st = F().state;
    const t = F().toast("⏳ Đang ghép ảnh & cập nhật video...", "info", 0);
    try {
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(st.pid)}/item-gallery`, { item_index: st.idx, layout: C.layout, slots: slotsPayload(), style: C.style });
      F().applyProject(res.project);
      F().toast(`🧩 Đã ghép ${res.filled_slots}/${res.total_slots} ảnh cho mục #${st.idx}.${res.step6_warning ? " ⚠️ " + F().esc(res.step6_warning) : ""}`, "success", 4200);
    } catch (e) { F().toast("Lỗi ghép ảnh: " + F().esc(e.message), "error", 6000); } finally { t && t.remove(); }
  }

  window.StudioCollage = { render };
})();
