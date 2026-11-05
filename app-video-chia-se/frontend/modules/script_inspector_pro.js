// -*- coding: utf-8 -*-
// Script Inspector Pro: sửa trực tiếp tiêu đề / tên mục / dòng mô tả ngay trong #scriptAnalysisPreviewBox,
// đổi thứ tự (↑/↓ hoặc kéo-thả), thêm/xoá mục, cảnh báo & "Tự động chuẩn hoá" 1 chạm, đồng bộ ngược vào #inpScript.
// Bọc onScriptInputChanged (giữ nguyên hành vi cũ). Hỗ trợ tiêu đề phụ (có/không) — đổi qua lại mục <-> tiêu đề phụ.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, t, ms) => (window.showToast ? window.showToast(m, t, ms) : null);
  let model = null; // { prefix, title, subtitle, format, entries:[{heading, bullets[]}] }
  let editing = false;
  let undoText = null;

  // Luật phân tích & ghi ngược nằm ở modules/script_outline_js.js (cùng luật với backend)
  function buildModel(raw) {
    const o = window.parseScriptOutlineJS(raw, "");
    const info = window.studioFirstLineInfo(raw);
    return {
      prefix: info.prefix,
      title: o.hasExplicitTitle ? info.title || o.title : "",
      subtitle: o.subtitle || "",
      format: o.format || "list",
      entries: (o.entries || []).map((e) => ({ heading: e.heading, bullets: (e.bullets || []).slice() })),
    };
  }
  const serialize = (m) => window.serializeStudioOutline(m);
  const FORMAT_LABEL = { blocks: "Khối cách dòng trống", bullets: "Gạch đầu dòng", list: "Mỗi dòng 1 mục" };

  // Cảnh báo — đồng bộ với backend services/qa_validator.outline_warnings
  function titleNumber(title) {
    const m = String(title || "").match(/^(?:TOP\s+)?(\d+)\s+\S/i);
    return m ? Number(m[1]) : null;
  }
  function warnings(m) {
    const w = [];
    const n = m.entries.length;
    if (!n) { w.push({ level: "error", code: "empty", message: "Chưa nhận diện được mục nào trong kịch bản." }); return w; }
    const tn = titleNumber(m.title);
    if (tn !== null && tn !== n) w.push({ level: "error", code: "title_count", message: `Tiêu đề ghi "${tn}" nhưng danh sách thực tế có ${n} mục.`, fix: true });
    const withB = m.entries.filter((e) => e.bullets.length).length;
    if (withB && withB < n) {
      const miss = m.entries.map((e, k) => (e.bullets.length ? null : k + 1)).filter(Boolean);
      w.push({ level: "warning", code: "missing_bullets", message: `Mục ${miss.join(", ")} thiếu dòng mô tả/địa chỉ (các mục khác đều có).` });
    }
    const seen = new Map();
    m.entries.forEach((e, k) => { const key = e.heading.trim().toLowerCase(); if (seen.has(key)) w.push({ level: "warning", code: "duplicate", message: `Mục ${seen.get(key)} và ${k + 1} trùng tên "${e.heading}".` }); else seen.set(key, k + 1); });
    m.entries.forEach((e, k) => { if (e.heading.length > 38) w.push({ level: "warning", code: "long_name", message: `Tên mục ${k + 1} dài ${e.heading.length} ký tự — video sẽ tự co chữ.` }); });
    m.entries.forEach((e, k) => e.bullets.forEach((b) => { if (b.length > 70) w.push({ level: "warning", code: "long_bullet", message: `Mô tả mục ${k + 1} dài ${b.length} ký tự — nên rút gọn ≤ 70 ký tự.` }); }));
    return w;
  }

  function normalizeModel(m) {
    const n = m.entries.length;
    m.entries = m.entries.map((e) => ({ heading: e.heading.replace(/\s+/g, " ").trim(), bullets: e.bullets.map((b) => b.replace(/^[\-\•\*\+\s]+/, "").replace(/\s+/g, " ").trim()).filter(Boolean) })).filter((e) => e.heading);
    if (titleNumber(m.title) !== null) m.title = m.title.replace(/^(TOP\s+)?\d+/i, (all, top) => `${top || ""}${m.entries.length || n}`);
    m.title = m.title.replace(/\s+/g, " ").trim().toLocaleUpperCase("vi");
    return m;
  }

  // Chạy hàm gốc (đồng bộ tiêu đề + bảng mục) nhưng cho nó ghi vào 1 khung tạm để không phá trình sửa đang gõ
  function runOriginalSilently() {
    const box = $("scriptAnalysisPreviewBox");
    if (!box) return origOnChanged(true);
    box.id = "scriptAnalysisPreviewBox__live";
    const dummy = document.createElement("div");
    dummy.id = "scriptAnalysisPreviewBox";
    dummy.hidden = true;
    document.body.appendChild(dummy);
    try { origOnChanged(true); } finally { dummy.remove(); box.id = "scriptAnalysisPreviewBox"; box.style.display = "block"; }
  }

  function commit(opts = {}) {
    const ta = $("inpScript");
    if (!ta || !model) return;
    if (opts.undoable) undoText = ta.value;
    ta.value = serialize(model);
    editing = true;
    try { runOriginalSilently(); } finally { editing = false; }
    if (opts.rerender) renderEditor();
    else refreshWarnings();
    if (window.LivePreview9x16) window.LivePreview9x16.render();
  }

  function entryHtml(e, k, n, missing) {
    return `<div class="si-entry" data-sp-entry="${k}" data-k="${k}">
      <div class="si-num" title="Kéo để đổi thứ tự • Bấm để xem slide ${k + 1}" data-act="goto">${k + 1}</div>
      <div class="si-fields">
        <input class="si-heading" data-f="heading" value="${esc(e.heading)}" placeholder="Tên mục (VD: BS Dương M. Tuấn)" />
        <textarea data-f="bullets" rows="${Math.max(1, e.bullets.length)}" class="${missing ? "si-missing" : ""}" placeholder="Mỗi dòng 1 ý mô tả / địa chỉ (để trống nếu không có)">${esc(e.bullets.join("\n"))}</textarea>
      </div>
      <div class="si-actions">
        <button class="sm" data-act="up" ${k === 0 ? "disabled" : ""} title="Đưa lên">↑</button>
        <button class="sm" data-act="down" ${k === n - 1 ? "disabled" : ""} title="Đưa xuống">↓</button>
        <button class="sm" data-act="tosub" title="Đặt dòng này làm Tiêu đề phụ (không phải mục)">⤴</button>
        <button class="sm danger" data-act="del" title="Xoá mục">×</button>
      </div></div>`;
  }

  function warningsHtml(m) {
    return warnings(m).map((w) => `<div class="si-warn ${w.level}"><span>${w.level === "error" ? "⛔" : "⚠️"} ${esc(w.message)}</span>${w.fix ? '<button class="sm warning" data-act="normalize">🔧 Tự động chuẩn hoá kịch bản</button>' : ""}</div>`).join("");
  }

  function renderEditor() {
    const box = $("scriptAnalysisPreviewBox");
    const ta = $("inpScript");
    if (!box || !ta) return;
    if (!ta.value.trim()) { model = null; return; }
    model = buildModel(ta.value);
    const n = model.entries.length;
    const anyBullets = model.entries.some((e) => e.bullets.length);
    box.style.display = "block";
    box.innerHTML = `<div class="si-box">
      <div class="si-head"><label style="margin:0;">📌 Tiêu đề chính (sửa trực tiếp)</label>
        <span>📋 Tổng số mục: <b class="si-count" style="color:var(--sp-ok)">${n} mục</b></span></div>
      <input class="si-title-input" data-f="title" value="${esc(model.title)}" placeholder="VD: 6 KÊNH BÁC SĨ SẢN NHI" />
      <div class="si-head"><input data-f="subtitle" value="${esc(model.subtitle)}" placeholder="✨ Tiêu đề phụ (không bắt buộc) — VD: Chất lượng - Xài bền - Kinh tế" style="flex:1; min-width:200px;" />
        ${model.subtitle ? '<button class="sm" data-act="subtoitem" title="Đây không phải tiêu đề phụ — chuyển thành mục 1">⤵ Thành mục</button>' : ""}
        <span class="badge" title="Định dạng kịch bản nhận diện được">${FORMAT_LABEL[model.format] || ""}</span></div>
      <div class="si-warnings">${warningsHtml(model)}</div>
      <div class="si-list">${model.entries.map((e, k) => entryHtml(e, k, n, anyBullets && !e.bullets.length)).join("")}</div>
      <div class="si-foot"><span>✏️ Sửa ở đây sẽ tự cập nhật ô Kịch bản & Xem trước 9:16</span>
        <span><button class="sm" data-act="undo" ${undoText === null ? "disabled" : ""}>↶ Hoàn tác</button>
        <button class="sm" data-act="normalize">🧹 Chuẩn hoá</button>
        <button class="sm success" data-act="add">＋ Thêm mục</button></span></div></div>`;
  }

  function refreshWarnings() {
    const box = $("scriptAnalysisPreviewBox");
    if (!box || !model) return;
    const wEl = box.querySelector(".si-warnings");
    if (wEl) wEl.innerHTML = warningsHtml(model);
    const c = box.querySelector(".si-count");
    if (c) c.textContent = `${model.entries.length} mục`;
  }

  function onBoxInput(e) {
    const t = e.target;
    if (!model || !t.dataset.f) return;
    const row = t.closest(".si-entry");
    if (t.dataset.f === "title") model.title = t.value;
    else if (t.dataset.f === "subtitle") model.subtitle = t.value;
    else if (row) {
      const ent = model.entries[Number(row.dataset.k)];
      if (t.dataset.f === "heading") ent.heading = t.value;
      else ent.bullets = t.value.split("\n");
    }
    commit({});
  }

  function onBoxClick(e) {
    const btn = e.target.closest("[data-act]");
    if (!btn || !model) return;
    const row = btn.closest(".si-entry");
    const k = row ? Number(row.dataset.k) : -1;
    const act = btn.dataset.act;
    const E = model.entries;
    if (act === "goto") { if (window.livePreviewGoTo) window.livePreviewGoTo(k); return; }
    if (act === "up" && k > 0) [E[k - 1], E[k]] = [E[k], E[k - 1]];
    else if (act === "down" && k < E.length - 1) [E[k + 1], E[k]] = [E[k], E[k + 1]];
    else if (act === "del") { const name = E[k].heading; E.splice(k, 1); toast(`Đã xoá mục <b>${esc(name)}</b> — bấm ↶ Hoàn tác nếu nhầm.`, "warning"); }
    else if (act === "tosub") {
      const it = E.splice(k, 1)[0];
      model.subtitle = [it.heading, ...it.bullets].join(" - ");
      toast(`Đã đặt "<b>${esc(model.subtitle)}</b>" làm tiêu đề phụ.`, "success");
    } else if (act === "subtoitem") {
      E.unshift({ heading: model.subtitle.trim(), bullets: [] });
      model.subtitle = "";
      toast("Đã chuyển tiêu đề phụ thành mục 1.", "info");
    }
    else if (act === "add") E.push({ heading: `Mục mới ${E.length + 1}`, bullets: E.some((x) => x.bullets.length) ? ["Mô tả / địa chỉ"] : [] });
    else if (act === "normalize") { normalizeModel(model); toast("Đã chuẩn hoá kịch bản: tiêu đề khớp số mục, đánh số lại 1..N, làm sạch dòng mô tả.", "success"); }
    else if (act === "undo") {
      if (undoText === null) return;
      $("inpScript").value = undoText; undoText = null; runOriginalSilently(); renderEditor();
      if (window.LivePreview9x16) window.LivePreview9x16.render();
      return;
    } else return;
    commit({ rerender: true, undoable: true });
    if (act === "add") { const inputs = $("scriptAnalysisPreviewBox").querySelectorAll(".si-heading"); inputs[inputs.length - 1]?.select(); }
  }

  // Kéo-thả để đổi thứ tự (chỉ khi cầm vào ô số thứ tự)
  let dragFrom = -1;
  function wireDrag(box) {
    box.addEventListener("mousedown", (e) => { const h = e.target.closest(".si-num"); const row = e.target.closest(".si-entry"); if (row) row.draggable = !!h; });
    box.addEventListener("dragstart", (e) => { const row = e.target.closest(".si-entry"); if (!row) return; dragFrom = Number(row.dataset.k); row.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
    box.addEventListener("dragover", (e) => { const row = e.target.closest(".si-entry"); if (dragFrom < 0 || !row) return; e.preventDefault(); box.querySelectorAll(".drop-target").forEach((x) => x.classList.remove("drop-target")); row.classList.add("drop-target"); });
    box.addEventListener("dragend", () => { dragFrom = -1; box.querySelectorAll(".dragging,.drop-target").forEach((x) => x.classList.remove("dragging", "drop-target")); });
    box.addEventListener("drop", (e) => {
      const row = e.target.closest(".si-entry");
      if (dragFrom < 0 || !row || !model) return;
      e.preventDefault();
      const to = Number(row.dataset.k);
      if (to !== dragFrom) { const [it] = model.entries.splice(dragFrom, 1); model.entries.splice(to, 0, it); commit({ rerender: true, undoable: true }); }
      dragFrom = -1;
    });
  }

  // Preset Ảnh + Nhạc: kịch bản là chuẩn => khi lưu, mô tả (bullets) của từng mục lấy theo ô Kịch bản
  // (collectBangFromTable gốc lấy bullets từ dữ liệu cũ nên mô tả mới thêm không lên video)
  const normName = (x) => String(x || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/[^a-z0-9]+/g, " ").trim();
  function wrapCollect() {
    const orig = window.collectBangFromTable;
    if (typeof orig !== "function" || orig.__si) return;
    window.collectBangFromTable = function (...a) {
      const bang = orig.apply(this, a);
      try {
        if ($("inpPreset")?.value === "anh_nhac" && $("inpScript")?.value.trim()) {
          const by = new Map((window.parseScriptOutlineJS($("inpScript").value, "").entries || []).map((e) => [normName(e.heading), e]));
          (bang.items || []).forEach((it) => {
            const e = by.get(normName(it.ten)) || by.get(normName(it.display_name));
            if (e && e.bullets && e.bullets.length) { it.bullets = e.bullets.slice(); it.ghi_chu = e.bullets.join(" | "); }
          });
        }
      } catch (err) { /* giữ nguyên kết quả gốc */ }
      return bang;
    };
    window.collectBangFromTable.__si = true;
  }

  let origOnChanged = function () {};
  function init() {
    wrapCollect();
    const box = $("scriptAnalysisPreviewBox");
    origOnChanged = window.onScriptInputChanged;
    if (typeof origOnChanged !== "function" || !box) return;
    window.onScriptInputChanged = function (...args) {
      const r = origOnChanged.apply(this, args);
      if (!editing) renderEditor();
      return r;
    };
    box.addEventListener("input", onBoxInput);
    box.addEventListener("click", onBoxClick);
    box.addEventListener("focusin", (e) => { const row = e.target.closest(".si-entry"); if (row && window.livePreviewGoTo) window.livePreviewGoTo(Number(row.dataset.k)); });
    wireDrag(box);
    if ($("inpScript")?.value.trim()) window.onScriptInputChanged(false);
  }
  window.ScriptInspectorPro = { warnings: () => (model ? warnings(model) : []), serialize: () => (model ? serialize(model) : ""), render: renderEditor };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
