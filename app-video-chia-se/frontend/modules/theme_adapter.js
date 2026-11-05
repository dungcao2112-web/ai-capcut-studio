// -*- coding: utf-8 -*-
// Theme Adapter: app.js / index.html có rất nhiều style inline màu tối (thiết kế cho Dark mode).
// Module này đọc màu inline ĐÃ CHUẨN HOÁ (rgb) qua CSSOM, tính độ sáng rồi gắn class phân loại:
//   sp-bg-dark | sp-bd-dark | sp-fg-text | sp-fg-muted | sp-fg-blue | sp-fg-green | sp-fg-amber | sp-fg-red
// CSS (studio_pro.css) chỉ áp các class này khi html[data-theme="beige"] => Dark mode giữ nguyên 100%.
(function () {
  "use strict";
  const CLASSES = ["sp-bg-dark", "sp-bd-dark", "sp-fg-text", "sp-fg-muted", "sp-fg-blue", "sp-fg-green", "sp-fg-amber", "sp-fg-red"];

  function parseRgb(str) {
    const m = String(str || "").match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/);
    if (!m) return null;
    return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  }
  function luminance({ r, g, b }) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }
  function hueSat({ r, g, b }) {
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    const sat = mx === 0 ? 0 : d / mx;
    let h = 0;
    if (d) {
      if (mx === r) h = ((g - b) / d) % 6;
      else if (mx === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60; if (h < 0) h += 360;
    }
    return { h, sat };
  }

  function classifyText(c) {
    if (!c || c.a < 0.4) return "";
    const L = luminance(c);
    if (L < 0.32) return ""; // đã đủ tối để đọc trên nền be
    const { h, sat } = hueSat(c);
    if (sat < 0.18) return L > 0.55 ? "sp-fg-text" : "sp-fg-muted";
    if (h >= 185 && h < 260) return "sp-fg-blue";
    if (h >= 90 && h < 185) return "sp-fg-green";
    if (h >= 25 && h < 90) return "sp-fg-amber";
    if (h < 25 || h >= 300) return "sp-fg-red";
    return "sp-fg-blue";
  }

  function classify(el) {
    const st = el.style;
    if (!st || !st.length) {
      if (el.classList && el.classList.contains("sp-adapted")) CLASSES.forEach((c) => el.classList.remove(c));
      return;
    }
    const want = new Set();
    const bg = parseRgb(st.backgroundColor) || parseRgb(st.background);
    if (bg && bg.a >= 0.45 && luminance(bg) < 0.06) want.add("sp-bg-dark");
    const bd = parseRgb(st.borderColor) || parseRgb(st.border) || parseRgb(st.borderLeftColor);
    if (bd && luminance(bd) < 0.12) want.add("sp-bd-dark");
    const fgCls = classifyText(parseRgb(st.color));
    if (fgCls) want.add(fgCls);
    const hasAny = want.size > 0;
    if (!hasAny && !el.classList.contains("sp-adapted")) return;
    CLASSES.forEach((c) => el.classList.toggle(c, want.has(c)));
    el.classList.toggle("sp-adapted", hasAny);
  }

  function scan(root) {
    if (!root || root.nodeType !== 1) return;
    if (root.hasAttribute && root.hasAttribute("style")) classify(root);
    root.querySelectorAll("[style]").forEach(classify);
  }

  let pending = new Set();
  let scheduled = false;
  function schedule(node) {
    pending.add(node);
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      const nodes = Array.from(pending);
      pending = new Set();
      nodes.forEach(scan);
    });
  }

  function init() {
    scan(document.body);
    const mo = new MutationObserver((muts) => {
      for (const m of muts) {
        if (m.type === "attributes") schedule(m.target);
        else m.addedNodes.forEach((n) => { if (n.nodeType === 1) schedule(n); });
      }
    });
    mo.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["style"] });
    window.rescanStudioTheme = () => scan(document.body);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
