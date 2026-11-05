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
      rec.im.onload = () => { rec.ok = true; rec.waiters.splice(0).forEach((f) => f()); };
      rec.im.onerror = () => { rec.failed = true; };
      rec.im.src = url;
      imgCache.set(url, rec);
    }
    if (!rec.ok && onReady && !rec.failed) rec.waiters.push(onReady);
    return rec.ok ? rec.im : null;
  }

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

  function drawPills(ctx, bullets, y, style, sizeBase) {
    const dark = isDark(style);
    const single = bullets.length === 1;
    bullets.slice(0, 4).forEach((b, k) => {
      const text = single ? `📍 ${b}` : `• ${b}`;
      const fit = fitText(ctx, text, BODY_FONT, "700", sizeBase - (bullets.length >= 3 ? 4 : 0), 22, 860, 2);
      ctx.font = `700 ${fit.size}px ${BODY_FONT}`;
      const tw = Math.max(...fit.lines.map((ln) => ctx.measureText(ln).width)) + 76;
      const th = fit.lines.length * fit.size * 1.22 + 26;
      const left = style.centerInfoPills === false ? 110 : W / 2 - tw / 2;
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

  function drawImageContain(ctx, im, x, y, w, h) {
    const sc = Math.min(w / im.width, h / im.height), dw = im.width * sc, dh = im.height * sc;
    ctx.drawImage(im, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
  }

  function drawItemSlide(ctx, H, st, item, redraw) {
    const style = st.style;
    drawBackground(ctx, H, style);
    const top = drawTitle(ctx, H, st.title, st.subtitle, style) + (H > 1500 ? 40 : 14);
    const tall = H > 1500;
    const scale = Math.max(0.8, Math.min(1.5, Number(style.heroImageScale) || 1));
    const cardH = Math.round((tall ? 860 : 520) * scale);
    const cardW = Math.min(980, Math.round((tall ? 900 : 700) * scale));
    const cx = (W - cardW) / 2;
    roundRect(ctx, cx, top, cardW, cardH, 44);
    ctx.fillStyle = style.cardColor || "#FFFDF9";
    ctx.shadowColor = isDark(style) ? "rgba(0,0,0,0.5)" : "rgba(110,82,55,0.20)";
    ctx.shadowBlur = 34; ctx.shadowOffsetY = 12; ctx.fill();
    ctx.shadowColor = "transparent"; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
    ctx.lineWidth = style.doctorCardFrame ? 8 : 4;
    ctx.strokeStyle = style.doctorCardFrame ? (style.accent || "#1C64B8") : (isDark(style) ? "#334155" : "#E6D8C5");
    ctx.stroke();
    const im = loadImage(item.image_url, redraw);
    ctx.save();
    roundRect(ctx, cx + 22, top + 22, cardW - 44, cardH - 44, 30);
    ctx.clip();
    if (im) drawImageContain(ctx, im, cx + 22, top + 22, cardW - 44, cardH - 44);
    else {
      ctx.fillStyle = isDark(style) ? "#94A3B8" : "#B6A08A";
      ctx.font = `700 46px ${BODY_FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(item.image_url ? "⏳ Đang tải ảnh..." : "🖼️ Chưa có ảnh", W / 2, top + cardH / 2);
    }
    ctx.restore();
    if (style.doctorCardFrame) {
      ctx.font = `700 34px ${BODY_FONT}`;
      const label = "✚ BÁC SĨ";
      const lw = ctx.measureText(label).width + 40;
      roundRect(ctx, cx + 30, top - 24, lw, 50, 999);
      ctx.fillStyle = style.accent || "#1C64B8"; ctx.fill();
      ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(label, cx + 30 + lw / 2, top + 1);
    }
    const nameTxt = `${item.i}. ${String(item.name || "").toLocaleUpperCase("vi")}`;
    const nfit = fitText(ctx, nameTxt, BODY_FONT, "700", tall ? 92 : 70, 40, 940, 2);
    ctx.font = `700 ${nfit.size}px ${BODY_FONT}`;
    const dark = isDark(style);
    const nameColor = style.nameColor || (dark ? "#FFD54F" : "#8A4B12");
    const strokeW = Math.round(nfit.size * (style.nameStrokeBold ? 0.16 : 0.1));
    let y = drawStrokedLines(ctx, nfit.lines, nfit.size, W / 2, top + cardH + (tall ? 44 : 20), nameColor,
      dark ? "#000" : "#FFFFFF", strokeW, 1.06);
    y = drawPills(ctx, item.bullets || [], y + (tall ? 26 : 14), style, tall ? 46 : 34);
    return y;
  }

  function summaryTitle(title, count) {
    const t = String(title || "").toLocaleUpperCase("vi").trim();
    if (/^TOP\s+\d+/.test(t)) return t.replace(/^TOP\s+\d+/, `TOP ${count}`);
    if (/^\d+\s+/.test(t)) return t.replace(/^\d+\s+/, `TOP ${count} `);
    return `TOP ${count} ${t}`;
  }

  function drawSummarySlide(ctx, H, st, redraw) {
    const style = st.style;
    const dark = isDark(style);
    drawBackground(ctx, H, style);
    const items = st.items || [];
    const n = items.length;
    let y = drawTitle(ctx, H, summaryTitle(st.title, n), st.summarySubtitle || "", style) + 24;
    const cols = H > 1500 ? (n > 8 ? 2 : 1) : (n > 5 ? 2 : 1);
    const rows = Math.ceil(n / cols) || 1;
    const bottomPad = st.summaryNote ? 110 : 50;
    const gap = 16;
    const rowH = Math.min(H > 1500 ? 260 : 150, (H - y - bottomPad - gap * (rows - 1)) / rows);
    const colW = (W - 80 - gap * (cols - 1)) / cols;
    const big = style.summaryLargeText ? 1.22 : 1;
    items.forEach((it, k) => {
      const c = cols === 2 ? Math.floor(k / rows) : 0;
      const r = cols === 2 ? k % rows : k;
      const x = 40 + c * (colW + gap);
      const yy = y + r * (rowH + gap);
      roundRect(ctx, x, yy, colW, rowH, 26);
      ctx.fillStyle = style.cardColor || "#FFFDF9"; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = dark ? "#334155" : "#E6D8C5"; ctx.stroke();
      const thumb = rowH - 24;
      const im = loadImage(it.image_url, redraw);
      if (im) { ctx.save(); roundRect(ctx, x + 12, yy + 12, thumb, thumb, 18); ctx.clip(); drawImageContain(ctx, im, x + 12, yy + 12, thumb, thumb); ctx.restore(); }
      const tx = x + thumb + 24, tw = colW - thumb - 36;
      const nfit = fitText(ctx, `${it.i}. ${String(it.name || "").toLocaleUpperCase("vi")}`, BODY_FONT, "700",
        Math.round(Math.min(rowH * 0.3, 56) * big), 20, tw, 2);
      const sub = (it.bullets || [])[0] || "";
      const sfit = sub ? fitText(ctx, sub, BODY_FONT, "600", Math.round(Math.min(rowH * 0.18, 34) * big), 16, tw, 1) : null;
      const blockH = nfit.lines.length * nfit.size * 1.05 + (sfit ? sfit.size * 1.3 + 6 : 0);
      ctx.font = `700 ${nfit.size}px ${BODY_FONT}`;
      let ty = drawStrokedLines(ctx, nfit.lines, nfit.size, tx + tw / 2, yy + (rowH - blockH) / 2,
        style.nameColor || (dark ? "#FFD54F" : "#8A4B12"), "#000", 0, 1.05);
      if (sfit) {
        ctx.font = `600 ${sfit.size}px ${BODY_FONT}`;
        drawStrokedLines(ctx, sfit.lines, sfit.size, tx + tw / 2, ty + 6, dark ? "#E2E8F0" : "#5C3724", "#000", 0, 1.3);
      }
    });
    if (st.summaryNote) {
      ctx.font = `700 ${H > 1500 ? 40 : 30}px ${BODY_FONT}`;
      ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
      ctx.fillStyle = dark ? "#FDE68A" : "#8A4B12";
      ctx.fillText(st.summaryNote, W / 2, H - 46);
    }
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
      if (slideIdx >= n) drawSummarySlide(ctx, H, st, redraw);
      else drawItemSlide(ctx, H, st, st.items[slideIdx], redraw);
    },
    summaryTitle,
  };
})();
