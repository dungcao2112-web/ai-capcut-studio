// -*- coding: utf-8 -*-
// Bộ vẽ Canvas cho Live Preview: Slide từng mục (1..N) + Bảng Tổng Hợp cuối video.
// Khung 1080x1920 (9:16) hoặc 1080x1080 (1:1 — đúng khung Remotion hiện tại). Mọi chữ thông tin căn giữa tuyệt đối.
(function () {
  "use strict";
  const W = 1080;
  const TITLE_FONT = "Anton, 'Be Vietnam Pro', sans-serif";
  const BODY_FONT = "'Barlow Condensed', 'Be Vietnam Pro', sans-serif";
  const imgCache = new Map();

  function loadImage(url, onReady) { // cache ảnh + vẽ lại khi tải xong
    if (!url) return null;
    let rec = imgCache.get(url);
    if (!rec) {
      rec = { im: new Image(), ok: false, waiters: [] };
      rec.im.onload = () => { rec.ok = true; rec.bbox = contentBox(rec.im); rec.waiters.splice(0).forEach((f) => f()); };
      rec.im.onerror = () => { rec.failed = true; };
      rec.im.src = url;
      imgCache.set(url, rec);
    }
    if (!rec.ok && onReady && !rec.failed) rec.waiters.push(onReady);
    return rec.ok ? rec.im : null;
  }

  // Vùng có nội dung của ảnh (alpha > 24) — giống services/image_layout.py để ảnh lấp đầy khung như Remotion
  function contentBox(im) {
    try {
      const k = Math.min(1, 200 / Math.max(im.width, im.height));
      const w = Math.max(1, Math.round(im.width * k)), h = Math.max(1, Math.round(im.height * k));
      const c = document.createElement("canvas"); c.width = w; c.height = h;
      const g = c.getContext("2d"); g.drawImage(im, 0, 0, w, h);
      const d = g.getImageData(0, 0, w, h).data;
      let x1 = w, y1 = h, x2 = -1, y2 = -1;
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (d[(y * w + x) * 4 + 3] > 24) { if (x < x1) x1 = x; if (x > x2) x2 = x; if (y < y1) y1 = y; if (y > y2) y2 = y; }
      if (x2 < 0) return null;
      return { x: (x1 / w) * im.width, y: (y1 / h) * im.height, w: ((x2 - x1 + 1) / w) * im.width, h: ((y2 - y1 + 1) / h) * im.height };
    } catch (e) { return null; }
  }
  const bboxOf = (url) => (imgCache.get(url) || {}).bbox || null;

  function wrapLines(ctx, text, maxW, maxLines) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    const lines = [];
    let cur = "";
    for (const w of words) {
      const test = cur ? `${cur} ${w}` : w;
      if (ctx.measureText(test).width <= maxW || !cur) cur = test;
      else { lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    if (lines.length > maxLines) {
      const head = lines.slice(0, maxLines - 1);
      head.push(lines.slice(maxLines - 1).join(" "));
      return head;
    }
    return lines;
  }

  // Co chữ thông minh: giảm cỡ cho tới khi vừa maxLines dòng trong maxW (giống autoFitFontSize của Remotion)
  function fitText(ctx, text, family, weight, maxSize, minSize, maxW, maxLines) {
    for (let size = maxSize; size >= minSize; size -= 2) {
      ctx.font = `${weight} ${size}px ${family}`;
      const lines = wrapLines(ctx, text, maxW, maxLines);
      if (lines.length <= maxLines && lines.every((ln) => ctx.measureText(ln).width <= maxW)) return { size, lines };
    }
    ctx.font = `${weight} ${minSize}px ${family}`;
    return { size: minSize, lines: wrapLines(ctx, text, maxW, maxLines) };
  }

  function roundRect(ctx, x, y, w, h, r) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }

  function drawStrokedLines(ctx, lines, size, cx, y, fill, stroke, strokeW, lineH) {
    ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.lineJoin = "round";
    lines.forEach((ln, k) => {
      const yy = y + k * size * lineH;
      if (strokeW > 0) { ctx.strokeStyle = stroke; ctx.lineWidth = strokeW; ctx.strokeText(ln, cx, yy); }
      ctx.fillStyle = fill; ctx.fillText(ln, cx, yy);
    });
    return y + lines.length * size * lineH;
  }

  const isDark = (style) => style.bgTheme === "dark";
  function drawBackground(ctx, H, style) {
    const base = style.bgColor || "#F6EFE6";
    const g = ctx.createRadialGradient(W / 2, H * 0.35, 40, W / 2, H * 0.35, H * 0.85);
    if (isDark(style)) { g.addColorStop(0, "#1E293B"); g.addColorStop(1, base); }
    else { g.addColorStop(0, "#FFFDF9"); g.addColorStop(0.58, base); g.addColorStop(1, shade(base, -0.08)); }
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }

  function shade(hex, amt) {
    const m = String(hex).replace("#", "").match(/^([0-9a-f]{6})$/i);
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    const f = (v) => Math.max(0, Math.min(255, Math.round(v + 255 * amt)));
    return `rgb(${f((n >> 16) & 255)}, ${f((n >> 8) & 255)}, ${f(n & 255)})`;
  }

  function drawTitle(ctx, H, title, subtitle, style) {
    const dark = isDark(style);
    const tall = H > 1500;
    const fit = fitText(ctx, String(title || "").toLocaleUpperCase("vi"), TITLE_FONT, "400", tall ? 104 : 82, 46, 960, 2);
    ctx.font = `400 ${fit.size}px ${TITLE_FONT}`;
    let y = drawStrokedLines(ctx, fit.lines, fit.size, W / 2, tall ? 120 : 54, dark ? "#FFFFFF" : "#4A2C1D",
      dark ? "#000" : "#FFFFFF", Math.round(fit.size * 0.13), 1.08);
    if (subtitle) {
      const sfit = fitText(ctx, subtitle, BODY_FONT, "700", tall ? 40 : 32, 22, 860, 1);
      ctx.font = `700 ${sfit.size}px ${BODY_FONT}`;
      const tw = ctx.measureText(sfit.lines[0]).width + 56;
      roundRect(ctx, W / 2 - tw / 2, y + 14, tw, sfit.size + 22, 999);
      ctx.fillStyle = dark ? "rgba(0,0,0,0.45)" : "rgba(74,44,29,0.10)"; ctx.fill();
      drawStrokedLines(ctx, sfit.lines, sfit.size, W / 2, y + 25, dark ? "#FDE68A" : "#5C3724", "#000", 0, 1);
      y += sfit.size + 40;
    }
    return y;
  }

  function drawPills(ctx, bullets, y, style, sizeBase, measureOnly = false) {
    const dark = isDark(style);
    const single = bullets.length === 1;
    bullets.slice(0, 4).forEach((b, k) => {
      const text = single ? `📍 ${b}` : `• ${b}`;
      const fit = fitText(ctx, text, BODY_FONT, "700", sizeBase - (bullets.length >= 3 ? 4 : 0), 22, 860, 2);
      ctx.font = `700 ${fit.size}px ${BODY_FONT}`;
      const tw = Math.max(...fit.lines.map((ln) => ctx.measureText(ln).width)) + 76;
      const th = fit.lines.length * fit.size * 1.22 + 26;
      const left = style.centerInfoPills === false ? 110 : W / 2 - tw / 2;
      if (measureOnly) { y += th + 14; return; }
      roundRect(ctx, left, y, tw, th, single ? 999 : 24);
      ctx.fillStyle = dark ? "rgba(15,23,42,0.78)" : "rgba(255,252,245,0.97)";
      ctx.shadowColor = dark ? "rgba(0,0,0,0.45)" : "rgba(110,82,55,0.16)";
      ctx.shadowBlur = 18; ctx.shadowOffsetY = 6; ctx.fill();
      ctx.shadowColor = "transparent"; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
      ctx.lineWidth = 3; ctx.strokeStyle = dark ? "rgba(255,255,255,0.22)" : "#DECBB1"; ctx.stroke();
      drawStrokedLines(ctx, fit.lines, fit.size, left + tw / 2, y + 13, dark ? "#F8FAFC" : "#3B281E", "#000", 0, 1.22);
      y += th + 14;
    });
    return y;
  }

  function drawItemSlide(ctx, H, st, item, redraw) {
    const style = st.style;
    const dark = isDark(style);
    const tall = H > 1500;
    drawBackground(ctx, H, style);
    const top = drawTitle(ctx, H, st.title, st.subtitle, style) + (tall ? 40 : 14);
    // Đo khối chữ trước => ảnh lấp đầy phần còn lại (giống Remotion: không còn khoảng trống thừa)
    const nameTxt = `${item.i}. ${String(item.name || "").toLocaleUpperCase("vi")}`;
    const nfit = fitText(ctx, nameTxt, BODY_FONT, "700", tall ? 92 : 70, 40, 940, 2);
    const pillsH = drawPills(ctx, item.bullets || [], 0, style, tall ? 46 : 34, true);
    const textH = (tall ? 44 : 20) + nfit.lines.length * nfit.size * 1.06 + (tall ? 26 : 14) + pillsH;
    const scale = Math.max(0.8, Math.min(1.5, Number(style.heroImageScale) || 1));
    const im = loadImage(item.image_url, redraw);
    const bb = im ? bboxOf(item.image_url) || { x: 0, y: 0, w: im.width, h: im.height } : null;
    const aspect = bb ? bb.w / bb.h : 4 / 3;
    const inset = style.doctorCardFrame ? 24 : 0;
    const maxH = Math.max(240, H - (tall ? 70 : 24) - top - textH);
    const maxW = Math.min(1000, 900 * scale);
    const boxW = Math.min(maxW, (maxH - inset) * aspect + inset);
    const boxH = (boxW - inset) / aspect + inset;
    const cx = (W - boxW) / 2;
    const y0 = top + Math.max(0, (H - (tall ? 70 : 24) - top - textH - boxH) / 2);
    if (style.doctorCardFrame || !im) {
      roundRect(ctx, cx, y0, boxW, boxH, 40);
      ctx.fillStyle = style.cardColor || "#FFFDF9"; ctx.fill();
      ctx.lineWidth = style.doctorCardFrame ? 6 : 3;
      ctx.strokeStyle = style.doctorCardFrame ? style.accent || "#1C64B8" : dark ? "#334155" : "#E6D8C5"; ctx.stroke();
    }
    if (im) {
      ctx.drawImage(im, bb.x, bb.y, bb.w, bb.h, cx + inset / 2, y0 + inset / 2, boxW - inset, boxH - inset);
    } else {
      ctx.fillStyle = dark ? "#94A3B8" : "#B6A08A";
      ctx.font = `700 46px ${BODY_FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(item.image_url ? "⏳ Đang tải ảnh..." : "🖼️ Chưa có ảnh — bấm để chọn", W / 2, y0 + boxH / 2);
    }
    window.LivePreviewRender.lastImageRect = { x: cx, y: y0, w: boxW, h: boxH, H, item: item.i };
    if (style.doctorCardFrame) {
      ctx.font = `700 34px ${BODY_FONT}`;
      const lw = ctx.measureText("✚ BÁC SĨ").width + 40;
      roundRect(ctx, cx + 20, y0 + 16, lw, 50, 999);
      ctx.fillStyle = style.accent || "#1C64B8"; ctx.fill();
      ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("✚ BÁC SĨ", cx + 20 + lw / 2, y0 + 41);
    }
    ctx.font = `700 ${nfit.size}px ${BODY_FONT}`;
    const strokeW = Math.round(nfit.size * (style.nameStrokeBold ? 0.16 : 0.1));
    let y = drawStrokedLines(ctx, nfit.lines, nfit.size, W / 2, y0 + boxH + (tall ? 44 : 20),
      style.nameColor || (dark ? "#FFD54F" : "#8A4B12"), dark ? "#000" : "#FFFFFF", strokeW, 1.06);
    return drawPills(ctx, item.bullets || [], y + (tall ? 26 : 14), style, tall ? 46 : 34);
  }

  window.LivePreviewRender = {
    W,
    draw(canvas, st, slideIdx, redraw) {
      const H = st.aspect === "1:1" ? 1080 : 1920;
      if (canvas.width !== W) canvas.width = W;
      if (canvas.height !== H) canvas.height = H;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, W, H);
      const n = (st.items || []).length;
      if (!n) {
        drawBackground(ctx, H, st.style);
        drawTitle(ctx, H, st.title || "CHƯA CÓ KỊCH BẢN", "Dán danh sách mục vào ô Kịch bản", st.style);
        return;
      }
      window.LivePreviewRender.lastImageRect = null;
      if (slideIdx >= n) window.LivePreviewSummary.draw(ctx, H, st, redraw);
      else drawItemSlide(ctx, H, st, st.items[slideIdx], redraw);
    },
    // Dùng chung cho live_preview_summary.js
    helpers: { W, BODY_FONT, loadImage, bboxOf, fitText, roundRect, drawStrokedLines, drawBackground, drawTitle, isDark },
  };
})();
