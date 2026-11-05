// -*- coding: utf-8 -*-
// Live Preview — Slide Bảng Tổng Hợp cuối video ("TOP N ..."). Dùng helper của live_preview_render.js.
(function () {
  "use strict";
  function summaryTitle(title, count) {
    const t = String(title || "").toLocaleUpperCase("vi").trim();
    if (/^TOP\s+\d+/.test(t)) return t.replace(/^TOP\s+\d+/, `TOP ${count}`);
    if (/^\d+\s+/.test(t)) return t.replace(/^\d+\s+/, `TOP ${count} `);
    return `TOP ${count} ${t}`;
  }

  function draw(ctx, H, st, redraw) {
    const h = window.LivePreviewRender.helpers;
    const { W, BODY_FONT } = h;
    const style = st.style;
    const dark = h.isDark(style);
    h.drawBackground(ctx, H, style);
    const items = st.items || [];
    const n = items.length;
    const y = h.drawTitle(ctx, H, summaryTitle(st.title, n), st.summarySubtitle || "", style) + 24;
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
      h.roundRect(ctx, x, yy, colW, rowH, 26);
      ctx.fillStyle = style.cardColor || "#FFFDF9"; ctx.fill();
      ctx.lineWidth = 3; ctx.strokeStyle = dark ? "#334155" : "#E6D8C5"; ctx.stroke();
      const thumbH = rowH - 24;
      const im = h.loadImage(it.image_url, redraw);
      let thumbW = thumbH;
      if (im) {
        const bb = h.bboxOf(it.image_url) || { x: 0, y: 0, w: im.width, h: im.height };
        thumbW = Math.min(thumbH * 1.5, thumbH * (bb.w / bb.h));
        ctx.save(); h.roundRect(ctx, x + 12, yy + 12, thumbW, thumbH, 18); ctx.clip();
        ctx.drawImage(im, bb.x, bb.y, bb.w, bb.h, x + 12, yy + 12, thumbW, thumbH); ctx.restore();
      }
      const tx = x + thumbW + 24, tw = colW - thumbW - 36;
      const nfit = h.fitText(ctx, `${it.i}. ${String(it.name || "").toLocaleUpperCase("vi")}`, BODY_FONT, "700",
        Math.round(Math.min(rowH * 0.3, 56) * big), 20, tw, 2);
      const sub = (it.bullets || [])[0] || "";
      const sfit = sub ? h.fitText(ctx, sub, BODY_FONT, "600", Math.round(Math.min(rowH * 0.18, 34) * big), 16, tw, 1) : null;
      const blockH = nfit.lines.length * nfit.size * 1.05 + (sfit ? sfit.size * 1.3 + 6 : 0);
      ctx.font = `700 ${nfit.size}px ${BODY_FONT}`;
      const ty = h.drawStrokedLines(ctx, nfit.lines, nfit.size, tx + tw / 2, yy + (rowH - blockH) / 2,
        style.nameColor || (dark ? "#FFD54F" : "#8A4B12"), "#000", 0, 1.05);
      if (sfit) {
        ctx.font = `600 ${sfit.size}px ${BODY_FONT}`;
        h.drawStrokedLines(ctx, sfit.lines, sfit.size, tx + tw / 2, ty + 6, dark ? "#E2E8F0" : "#5C3724", "#000", 0, 1.3);
      }
    });
    if (st.summaryNote) {
      ctx.font = `700 ${H > 1500 ? 40 : 30}px ${BODY_FONT}`;
      ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
      ctx.fillStyle = dark ? "#FDE68A" : "#8A4B12";
      ctx.fillText(st.summaryNote, W / 2, H - 46);
    }
  }

  window.LivePreviewSummary = { draw, summaryTitle };
})();
