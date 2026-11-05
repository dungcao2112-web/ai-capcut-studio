// -*- coding: utf-8 -*-
// 🧩 Ghép nhiều ảnh cho 1 mục: bố cục 2 ngang / 2 dọc / 3 (1 lớn + 2 nhỏ) / 3 ngang / 4 lưới / 4 (1 lớn + 3 nhỏ) / 6 lưới.
// Mỗi ô: 📤 tải ảnh • 🖼️ dùng ảnh hiện tại • 🌐 ảnh web khác • ✂️ chọn khung riêng • ✕ bỏ. Xem trước tức thì trên canvas.
// Server ghép ra 1 ảnh (POST /item-gallery) nên Remotion, Live Preview & CapCut dùng như ảnh thường.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const F = () => window.StudioFramer;
  const imgs = new Map();
  const C = { layout: "2-ngang", slots: [], webNext: {}, editing: -1, cropper: null, host: null };

  const layoutOf = (id) => (F().state.info.layouts || []).find((l) => l.id === id) || (F().state.info.layouts || [])[0];
  function img(url, cb) {
    if (!url) return null;
    let r = imgs.get(url);
    if (!r) { r = { im: new Image(), ok: false }; r.im.onload = () => { r.ok = true; cb && cb(); }; r.im.src = url; imgs.set(url, r); }
    return r.ok ? r.im : null;
  }

  function init() {
    const info = F().state.info;
    C.layout = info.layout && info.layout !== "1" ? info.layout : "2-ngang";
    C.slots = (info.gallery || []).map((g) => ({ path: g.path, url: g.url, crop_box: g.crop_box }));
    if (!C.slots.length && info.source_path) C.slots = [{ path: info.source_path, url: info.source_url, crop_box: info.crop_box }];
    C.webNext = {};
    C.editing = -1;
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

  function drawPreview() {
    const cv = $("cbPreview");
    if (!cv) return;
    const l = layoutOf(C.layout);
    const W = 560, H = Math.round(W / l.aspect), B = 9, G = 7;
    cv.width = W; cv.height = H;
    const g = cv.getContext("2d");
    g.fillStyle = "#fff"; g.fillRect(0, 0, W, H);
    l.cells.forEach(([x, y, cw, ch], k) => {
      const iw = W - 2 * B, ih = H - 2 * B;
      const x1 = B + x * iw + (x > 0 ? G / 2 : 0), y1 = B + y * ih + (y > 0 ? G / 2 : 0);
      const x2 = B + (x + cw) * iw - (x + cw < 0.999 ? G / 2 : 0), y2 = B + (y + ch) * ih - (y + ch < 0.999 ? G / 2 : 0);
      const s = C.slots[k];
      const im = s && img(s.url, drawPreview);
      if (!im) {
        g.fillStyle = "#F6EFE6"; g.fillRect(x1, y1, x2 - x1, y2 - y1);
        g.fillStyle = "#B6A08A"; g.font = "700 22px 'Barlow Condensed', sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
        g.fillText(`Ô ${k + 1}`, (x1 + x2) / 2, (y1 + y2) / 2);
        return;
      }
      const tmp = document.createElement("canvas");
      window.StudioCropper.drawCrop(tmp, im, s.crop_box || [0, 0, 1, 1], Math.round(x2 - x1), Math.round(y2 - y1));
      g.drawImage(tmp, x1, y1);
    });
  }

  function slotsHtml() {
    const l = layoutOf(C.layout);
    const info = F().state.info;
    return l.cells.map((_, k) => {
      const s = C.slots[k];
      return `<div class="cb-slot ${C.editing === k ? "on" : ""}">
        <div class="cb-thumb">${s && s.url ? `<img src="${s.url}" alt=""/>` : `<span>Ô ${k + 1} — trống</span>`}</div>
        <div class="cb-acts">
          <button class="sm" data-act="up" data-k="${k}" title="Tải ảnh từ máy">📤</button>
          ${info.source_path ? `<button class="sm" data-act="cur" data-k="${k}" title="Dùng ảnh hiện tại của mục">🖼️</button>` : ""}
          <button class="sm" data-act="web" data-k="${k}" title="Tự tìm ảnh web khác cho ô này">🌐</button>
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
      <div class="fr-grid">
        <div class="fr-col"><div class="fr-label">Các ô ảnh (theo thứ tự trên bố cục)</div><div class="cb-slots">${slotsHtml()}</div>
          <div id="cbCropPanel"></div></div>
        <div class="fr-col"><div class="fr-label">Xem trước ảnh ghép</div><div class="fr-result"><canvas id="cbPreview"></canvas></div>
          <div class="step-msg">Ô trống sẽ để màu be nhạt. Ảnh ghép thay cho ảnh chính của mục này.</div></div>
      </div>
      <input type="file" id="cbUpload" accept="image/*" style="display:none;"/>
      <div class="fr-foot"><span class="step-msg">Mẹo: 🌐 bấm nhiều lần để đổi sang ảnh web tiếp theo.</span>
        <span><button onclick="closeModal()">Đóng</button><button class="primary" id="cbApply">💾 Áp dụng ảnh ghép</button></span></div>`;
    C.host.querySelectorAll(".cb-lay").forEach((b) => (b.onclick = () => { C.layout = b.dataset.l; C.editing = -1; render(); }));
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
        const d = await window.apiPost(`/api/projects/${encodeURIComponent(st.pid)}/item-gallery-web`, { item_index: st.idx, slot: k, candidate_index: cand });
        C.slots[k] = { path: d.path, url: d.url, crop_box: null };
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
    const n = layoutOf(C.layout).cells.length;
    const slots = Array.from({ length: n }, (_, k) => (C.slots[k] ? { path: C.slots[k].path, crop_box: C.slots[k].crop_box } : { path: "" }));
    const t = F().toast("⏳ Đang ghép ảnh & cập nhật video...", "info", 0);
    try {
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(st.pid)}/item-gallery`, { item_index: st.idx, layout: C.layout, slots });
      F().applyProject(res.project);
      F().toast(`🧩 Đã ghép ${res.filled_slots}/${res.total_slots} ảnh cho mục #${st.idx}.${res.step6_warning ? " ⚠️ " + F().esc(res.step6_warning) : ""}`, "success", 4200);
    } catch (e) { F().toast("Lỗi ghép ảnh: " + F().esc(e.message), "error", 6000); } finally { t && t.remove(); }
  }

  window.StudioCollage = { render };
})();
