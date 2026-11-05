// -*- coding: utf-8 -*-
// Bộ phân tích dàn ý phía trình duyệt — CÙNG LUẬT với backend/services/script_outline.py:
//  • Tiêu đề: "7. BỆNH VIỆN" -> "BỆNH VIỆN" (số series); "6 KÊNH..." giữ số 6
//  • Tiêu đề phụ (có hoặc không): ghi rõ "Tiêu đề phụ: ..." hoặc tự nhận khối 1 dòng có " - ", "•", "|"
//    đứng riêng ngay sau tiêu đề (VD: "Chất lượng - Xài bền - Kinh tế")
//  • Định dạng khối: các mục cách nhau bằng dòng trống — dòng đầu là tên mục, các dòng sau là mô tả
// Bọc parseScriptOutlineJS gốc của app.js; cung cấp studioOutlineTitle / studioFirstLineInfo / serializeStudioOutline.
(function () {
  "use strict";
  const SUB_MARKER = /^\s*(?:tiêu\s*đề\s*phụ|phụ\s*đề|dòng\s*phụ|sub(?:title)?)\s*[:：]\s*(.+)$/i;
  const BULLET = /^\s*[\-\*\•\+]\s+/;
  const NUMBERED = /^\s*\d+[\.\)\-:]\s*/;
  const SEPARATOR = /\s[\-–—|•]\s|\s•|•\s/;

  function firstLineInfo(raw) {
    const rawLines = String(raw || "").split(/\r?\n/);
    const lines = rawLines.map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return { title: "", prefix: "" };
    const first = lines[0];
    const second = lines[1] || "";
    const mHead = first.match(/^(\d+)[\.\)\-:]\s*(.+)$/);
    const secondIsNum2 = /^2[\.\)\-:]\s+/.test(second);
    const followedByBlank = rawLines.length > 1 && !rawLines[1].trim(); // giống raw_lines[1] của Python
    const isCaps = first === first.toLocaleUpperCase("vi") && /\p{L}/u.test(first);
    if (mHead && (isCaps || Number(mHead[1]) !== 1 || followedByBlank || !secondIsNum2)) {
      return { title: mHead[2].trim().toLocaleUpperCase("vi"), prefix: first.slice(0, first.length - mHead[2].length) };
    }
    if (lines.length >= 2 && (isCaps || followedByBlank) && !BULLET.test(first) && !secondIsNum2) {
      return { title: first.toLocaleUpperCase("vi"), prefix: "" };
    }
    return { title: "", prefix: "" };
  }

  const looksLikeSubtitle = (s) => {
    const t = String(s || "").trim();
    return !!t && !NUMBERED.test(t) && !BULLET.test(t) && SEPARATOR.test(` ${t} `);
  };
  const cleanHeading = (s) => String(s || "").replace(NUMBERED, "").trim();
  const cleanBullet = (s) => String(s || "").replace(/^\s*[\-\*\•\+]\s*/, "").trim();

  function blocksOf(lines) {
    const out = [];
    let cur = [];
    for (const ln of lines) {
      if (ln.trim()) cur.push(ln.trim());
      else if (cur.length) { out.push(cur); cur = []; }
    }
    if (cur.length) out.push(cur);
    return out;
  }

  function extend(origParse, rawText, fallbackTitle) {
    const raw = String(rawText || "").split(/\r?\n/);
    let explicit = "";
    const kept = raw.filter((ln) => {
      const m = ln.match(SUB_MARKER);
      if (m && !explicit) { explicit = m[1].trim(); return false; }
      return true;
    });
    const text = kept.join("\n");
    const base = origParse(text, fallbackTitle);
    const info = firstLineInfo(text);
    if (base.hasExplicitTitle && info.title) base.title = info.title;
    base.format = "list";
    const firstIdx = kept.findIndex((l) => l.trim());
    if (firstIdx < 0) { if (explicit) base.subtitle = explicit; return base; }
    const body = base.hasExplicitTitle ? kept.slice(firstIdx + 1) : kept.slice(firstIdx);
    const blocks = blocksOf(body);

    if (body.some((ln) => BULLET.test(ln))) {
      base.format = "bullets";
      // Có đánh số mục => dòng có số luôn là MỤC; dòng không số trước mục đầu tiên là tiêu đề phụ (giống Python)
      const heads = body.map((l) => l.trim()).filter((t) => t && !BULLET.test(t));
      if (heads.some((h) => NUMBERED.test(h))) {
        const entries = [];
        const subParts = [];
        for (const ln of body) {
          const t = ln.trim();
          if (!t) continue;
          if (BULLET.test(t)) { if (entries.length && cleanBullet(t)) entries[entries.length - 1].bullets.push(cleanBullet(t)); }
          else if (NUMBERED.test(t) || entries.length) { if (cleanHeading(t)) entries.push({ heading: cleanHeading(t), bullets: [] }); }
          else subParts.push(t);
        }
        return Object.assign(base, { entries, count: entries.length, subtitle: explicit || subParts.join(" | ") });
      }
      if (explicit) base.subtitle = explicit;
      else if (!base.subtitle && blocks.length && blocks[0].length === 1 && looksLikeSubtitle(blocks[0][0])
        && base.entries.length && base.entries[0].heading === cleanHeading(blocks[0][0]) && !base.entries[0].bullets.length) {
        base.subtitle = blocks[0][0];
        base.entries = base.entries.slice(1);
        base.count = base.entries.length;
      }
      return base;
    }
    let subtitle = explicit;
    let rest = blocks;
    if (!subtitle && blocks.length >= 2 && blocks[0].length === 1 && looksLikeSubtitle(blocks[0][0])) {
      subtitle = blocks[0][0];
      rest = blocks.slice(1);
    }
    let entries;
    if (rest.length >= 2 && rest.some((b) => b.length >= 2)) {
      entries = rest.filter((b) => cleanHeading(b[0])).map((b) => ({ heading: cleanHeading(b[0]), bullets: b.slice(1).map(cleanBullet).filter(Boolean) }));
      base.format = "blocks";
    } else if (subtitle) {
      entries = rest.flat().map((ln) => cleanHeading(cleanBullet(ln))).filter(Boolean).map((h) => ({ heading: h, bullets: [] }));
    } else {
      return base;
    }
    return Object.assign(base, { subtitle: subtitle || "", entries, count: entries.length });
  }

  // Ghi ngược dàn ý ra văn bản — giữ đúng định dạng gốc (khối / gạch đầu dòng) để parse lại ra đúng kết quả
  function serialize(m) {
    const out = [];
    if (m.title.trim()) out.push(`${m.prefix || ""}${m.title.trim().toLocaleUpperCase("vi")}`);
    const sub = String(m.subtitle || "").trim();
    if (out.length && (sub || m.format === "blocks")) out.push("");
    if (sub) { out.push(looksLikeSubtitle(sub) ? sub : `Tiêu đề phụ: ${sub}`); out.push(""); }
    else if (out.length && m.format !== "blocks") out.push("");
    m.entries.forEach((e, k) => {
      const bullets = e.bullets.map((b) => b.trim()).filter(Boolean);
      if (m.format === "blocks") {
        const head = e.heading.trim();
        out.push(k === 0 && !bullets.length && looksLikeSubtitle(head) ? `1. ${head}` : head);
        bullets.forEach((b) => out.push(b));
        out.push("");
      } else {
        out.push(`${k + 1}. ${e.heading.trim()}`);
        bullets.forEach((b) => out.push(`- ${b}`));
      }
    });
    return out.join("\n").replace(/\n+$/, "") + "\n";
  }

  window.studioFirstLineInfo = firstLineInfo;
  window.studioOutlineTitle = (raw) => firstLineInfo(raw).title;
  window.serializeStudioOutline = serialize;
  window.studioLooksLikeSubtitle = looksLikeSubtitle;
  const origParse = window.parseScriptOutlineJS;
  if (typeof origParse === "function" && !origParse.__so) {
    window.parseScriptOutlineJS = function (rawText, fallbackTitle = "") { return extend(origParse, rawText, fallbackTitle); };
    window.parseScriptOutlineJS.__so = true;
  }
})();
