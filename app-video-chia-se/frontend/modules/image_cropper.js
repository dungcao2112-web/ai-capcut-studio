// -*- coding: utf-8 -*-
// Khung cắt ảnh tương tác (dùng chung cho 🖼️ Chọn khung hình & từng ô 🧩 Ghép nhiều ảnh):
//  • Kéo bên trong khung = dịch vùng chọn • Kéo 4 góc = co giãn • Lăn chuột = phóng/thu vùng chọn
//  • Khoá tỉ lệ (4:3, 1:1, 3:4, 16:9, 3:2) hoặc Tự do • Kết quả crop chuẩn hoá [x, y, w, h] (0..1)
// API: const c = StudioCropper.mount(containerEl, imgUrl, {aspect, crop, onChange}); c.setAspect(r); c.getCrop(); c.reset()
(function () {
  "use strict";
  const MIN = 0.06;

  function mount(container, url, opts = {}) {
    container.innerHTML = `<div class="cr-stage"><img class="cr-img" alt="Ảnh gốc" draggable="false"/>
      <div class="cr-box"><span class="cr-h nw" data-h="nw"></span><span class="cr-h ne" data-h="ne"></span>
      <span class="cr-h sw" data-h="sw"></span><span class="cr-h se" data-h="se"></span>
      <span class="cr-grid"></span></div></div>`;
    const stage = container.querySelector(".cr-stage");
    const img = container.querySelector(".cr-img");
    const box = container.querySelector(".cr-box");
    let ratio = opts.aspect || null; // tỉ lệ rộng/cao THEO PIXEL, null = tự do
    let crop = Array.isArray(opts.crop) && opts.crop.length === 4 ? opts.crop.map(Number) : null;
    let natW = 1, natH = 1;
    let drag = null;

    const toNormRatio = () => (ratio ? ratio * (natH / natW) : null); // tỉ lệ trong hệ toạ độ chuẩn hoá

    function clamp(c) {
      let [x, y, w, h] = c;
      w = Math.max(MIN, Math.min(1, w));
      h = Math.max(MIN, Math.min(1, h));
      const nr = toNormRatio();
      if (nr) {
        if (w / h > nr) w = h * nr; else h = w / nr;
        if (w > 1) { w = 1; h = w / nr; }
        if (h > 1) { h = 1; w = h * nr; }
      }
      x = Math.max(0, Math.min(1 - w, x));
      y = Math.max(0, Math.min(1 - h, y));
      return [x, y, w, h];
    }

    function fullCrop() {
      const nr = toNormRatio();
      if (!nr) return [0, 0, 1, 1];
      const w = nr >= 1 ? 1 : nr, h = nr >= 1 ? 1 / nr : 1;
      const c = clamp([0, 0, Math.min(1, w), Math.min(1, h)]);
      return clamp([(1 - c[2]) / 2, (1 - c[3]) / 2, c[2], c[3]]);
    }

    function paint() {
      if (!crop) return;
      const [x, y, w, h] = crop;
      Object.assign(box.style, { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` });
      if (opts.onChange) opts.onChange(crop.slice(), { natW, natH });
    }

    img.onload = () => {
      natW = img.naturalWidth || 1;
      natH = img.naturalHeight || 1;
      crop = crop ? clamp(crop) : fullCrop();
      paint();
    };
    img.src = url;

    function pt(e) {
      const r = img.getBoundingClientRect();
      return [(e.clientX - r.left) / Math.max(1, r.width), (e.clientY - r.top) / Math.max(1, r.height)];
    }
    stage.addEventListener("mousedown", (e) => {
      if (!crop || e.button !== 0) return;
      e.preventDefault();
      const handle = e.target.dataset && e.target.dataset.h;
      const [px, py] = pt(e);
      const inside = px >= crop[0] && px <= crop[0] + crop[2] && py >= crop[1] && py <= crop[1] + crop[3];
      drag = { mode: handle || (inside ? "move" : "new"), sx: px, sy: py, start: crop.slice() };
    });
    const onMove = (e) => {
      if (!img.isConnected) { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); return; }
      if (!drag) return;
      const [px, py] = pt(e);
      const dx = px - drag.sx, dy = py - drag.sy;
      let [x, y, w, h] = drag.start;
      if (drag.mode === "move") { x += dx; y += dy; }
      else if (drag.mode === "new") { x = Math.min(drag.sx, px); y = Math.min(drag.sy, py); w = Math.abs(dx); h = Math.abs(dy); }
      else {
        const ax = drag.mode.includes("w") ? x + w : x; // điểm neo đối diện
        const ay = drag.mode.includes("n") ? y + h : y;
        const bx = Math.max(0, Math.min(1, drag.mode.includes("w") ? x + dx : x + w + dx));
        const by = Math.max(0, Math.min(1, drag.mode.includes("n") ? y + dy : y + h + dy));
        w = Math.abs(bx - ax); h = Math.abs(by - ay);
        const nr = toNormRatio();
        if (nr) { if (w / h > nr) h = w / nr; else w = h * nr; }
        x = drag.mode.includes("w") ? ax - w : ax;
        y = drag.mode.includes("n") ? ay - h : ay;
      }
      if (drag.mode === "new" && (w < MIN || h < MIN)) return;
      crop = clamp([x, y, w, h]);
      paint();
    };
    const onUp = () => { drag = null; };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    stage.addEventListener("wheel", (e) => {
      if (!crop) return;
      e.preventDefault();
      const f = e.deltaY < 0 ? 0.92 : 1.08;
      const [x, y, w, h] = crop;
      const cx = x + w / 2, cy = y + h / 2;
      const nw = Math.max(MIN, Math.min(1, w * f)), nh = Math.max(MIN, Math.min(1, h * f));
      crop = clamp([cx - nw / 2, cy - nh / 2, nw, nh]);
      paint();
    }, { passive: false });

    return {
      getCrop: () => (crop ? crop.map((v) => Number(v.toFixed(4))) : null),
      setAspect(r) { ratio = r || null; if (crop) { const [x, y, w, h] = crop; crop = clamp([x, y, w, h]); paint(); } },
      reset() { crop = fullCrop(); paint(); },
      image: img,
      natural: () => ({ w: natW, h: natH }),
    };
  }

  // Vẽ thử kết quả cắt lên canvas (xem trước tức thì, không cần gọi server)
  function drawCrop(canvas, img, crop, outW, outH) {
    const g = canvas.getContext("2d");
    canvas.width = outW; canvas.height = outH;
    if (!img || !img.naturalWidth || !crop) { g.clearRect(0, 0, outW, outH); return; }
    const [x, y, w, h] = crop;
    const sw = w * img.naturalWidth, sh = h * img.naturalHeight;
    const sc = Math.max(outW / sw, outH / sh); // cover
    const cw = outW / sc, ch = outH / sc;
    g.drawImage(img, x * img.naturalWidth + (sw - cw) / 2, y * img.naturalHeight + (sh - ch) / 2, cw, ch, 0, 0, outW, outH);
  }

  window.StudioCropper = { mount, drawCrop };
})();
