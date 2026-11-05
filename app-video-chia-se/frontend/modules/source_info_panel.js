// -*- coding: utf-8 -*-
// 📚 Thông tin lấy từ link nguồn — tổng hợp THEO MẪU CÂU MÔ TẢ sếp đặt ở mục ③ (không thêm câu tự do):
//  • Mỗi mục: "Mô tả theo mẫu" (đã điền từ link) — dòng nào nguồn không có thông tin thì đã bị bỏ
//  • "Xem thông tin gốc" (thu gọn): địa chỉ/giá/hotline/câu trong link để sếp đối chiếu, chỉ xem
//  • ➕ Dùng mô tả này (thay mô tả của mục trong ô Kịch bản) / ➕ Điền theo mẫu cho mục chưa có mô tả
// Dữ liệu: POST /api/projects/<pid>/source-info-preview {template} (đọc cache link, không tải ảnh).
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, t, ms) => (window.showToast ? window.showToast(m, t, ms) : null);
  const cur = () => (window.studioCurrent ? window.studioCurrent() : { pid: "", project: null });
  const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/[^a-z0-9]+/g, " ").trim();
  const ICON = { address: "📍", price: "💰", phone: "📞", hours: "🕘" };
  const P = { rows: [], template: "", open: true, timer: null, seq: 0 };

  function scriptEntry(name) {
    const o = window.parseScriptOutlineJS ? window.parseScriptOutlineJS($("inpScript")?.value || "", "") : { entries: [] };
    return (o.entries || []).find((e) => norm(e.heading) === norm(name)) || null;
  }

  // Đặt mô tả cho đúng mục trong ô Kịch bản (giữ định dạng kịch bản của sếp) rồi đồng bộ phân tích & xem trước
  function setScriptBullets(name, bullets) {
    const ta = $("inpScript");
    if (!ta || !window.serializeStudioOutline) return false;
    const raw = ta.value;
    const o = window.parseScriptOutlineJS(raw, "");
    const info = window.studioFirstLineInfo(raw);
    const model = { prefix: info.prefix, title: o.hasExplicitTitle ? info.title || o.title : "", subtitle: o.subtitle || "",
      format: o.format || "list", entries: (o.entries || []).map((e) => ({ heading: e.heading, bullets: (e.bullets || []).slice() })) };
    const ent = model.entries.find((e) => norm(e.heading) === norm(name));
    if (!ent) return false;
    ent.bullets = bullets.slice();
    ta.value = window.serializeStudioOutline(model);
    if (typeof window.onScriptInputChanged === "function") window.onScriptInputChanged(true);
    if (window.LivePreview9x16) window.LivePreview9x16.render();
    return true;
  }

  async function saveAfter() {
    try { if (cur().pid && typeof window.saveProjectSettings === "function") await window.saveProjectSettings(); } catch (e) { /* bỏ qua */ }
  }

  async function refresh() {
    const { pid, project } = cur();
    const links = (project && project.settings && project.settings.sourceLinks) || [];
    if (!pid || !links.length) { P.rows = []; render(); return; }
    const seq = ++P.seq;
    try {
      const tpl = window.MediaSetup ? window.MediaSetup.state.template : "";
      const res = await window.apiPost(`/api/projects/${encodeURIComponent(pid)}/source-info-preview`, { template: tpl });
      if (seq !== P.seq) return;
      P.rows = (res.items || []).filter((r) => r.template_bullets.length || r.facts.length || r.snippets.length);
      P.template = res.template;
      render();
    } catch (e) { /* chưa có dự án / chưa đọc link */ }
  }
  const refreshSoon = () => { clearTimeout(P.timer); P.timer = setTimeout(refresh, 500); };

  function render() {
    const host = $("siPanel");
    if (!host) return;
    if (!P.rows.length) { host.style.display = "none"; host.innerHTML = ""; return; }
    host.style.display = "flex";
    host.innerHTML = `<div class="si2-head"><b>📚 Thông tin từ link — tổng hợp theo mẫu câu mô tả</b> <span class="badge info">${P.rows.length} mục</span>
        <span style="margin-left:auto; display:flex; gap:6px;"><button type="button" class="sm success" id="si2All">➕ Điền theo mẫu cho mục chưa có mô tả</button>
        <button type="button" class="sm" id="si2Toggle">${P.open ? "Thu gọn ▲" : "Xem ▼"}</button></span></div>
      ${P.template ? "" : '<div class="step-msg">Chưa đặt mẫu ở mục ③ — app đang tự chọn: địa chỉ, giá, hotline, giờ mở cửa (hoặc 1 câu tóm tắt).</div>'}
      ${P.open ? `<div class="si2-list">${P.rows.map((r) => {
        const ent = scriptEntry(r.name);
        const now = ent && ent.bullets && ent.bullets.length ? ent.bullets : [];
        const same = now.length && now.join("|") === r.template_bullets.join("|");
        const facts = (r.facts || []).map((f) => `<span class="badge">${ICON[f.key] || "•"} ${esc(f.label)}: ${esc(f.text)}</span>`).join(" ");
        const snips = (r.snippets || []).map((s) => `<li>${esc(s.text)}</li>`).join("");
        return `<div class="si2-item"><div class="si2-name">#${r.i} ${esc(r.name)}
            ${same ? '<span class="badge success">✓ Đã có trong kịch bản</span>' : now.length ? '<span class="badge">Đang có mô tả riêng</span>' : '<span class="badge warning">Chưa có mô tả</span>'}
            ${r.template_bullets.length && !same ? `<button type="button" class="sm primary" data-use="${r.i}" style="margin-left:auto;">➕ Dùng mô tả này</button>` : ""}</div>
          ${r.template_bullets.length ? `<ul class="si2-tpl">${r.template_bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`
            : '<div class="si2-none">⚠ Link chưa có thông tin cho các dòng trong mẫu — giữ nguyên mô tả hiện tại.</div>'}
          ${facts || snips ? `<details class="si2-ref"><summary>Xem thông tin gốc trong link (chỉ để đối chiếu)</summary>${facts ? `<div class="si2-facts">${facts}</div>` : ""}${snips ? `<ul class="si2-snips">${snips}</ul>` : ""}</details>` : ""}</div>`;
      }).join("")}</div>` : ""}`;
    $("si2Toggle").onclick = () => { P.open = !P.open; render(); };
    $("si2All").onclick = async () => {
      let n = 0;
      for (const r of P.rows) {
        const ent = scriptEntry(r.name);
        if (ent && !(ent.bullets || []).length && r.template_bullets.length && setScriptBullets(r.name, r.template_bullets)) n++;
      }
      toast(n ? `📚 Đã điền mô tả theo mẫu cho <b>${n}</b> mục.` : "Không có mục nào chưa có mô tả (hoặc link chưa có thông tin theo mẫu).", n ? "success" : "info");
      if (n) { await saveAfter(); render(); }
    };
    host.querySelectorAll("[data-use]").forEach((b) => (b.onclick = async () => {
      const r = P.rows.find((x) => String(x.i) === b.dataset.use);
      if (r && setScriptBullets(r.name, r.template_bullets)) {
        toast(`Đã dùng mô tả theo mẫu cho <b>${esc(r.name)}</b>.`, "success");
        await saveAfter();
        render();
      } else toast("Không tìm thấy mục này trong ô Kịch bản.", "warning");
    }));
  }

  function mount() {
    const anchor = $("msPanel");
    if (!anchor || $("siPanel")) return;
    anchor.insertAdjacentHTML("afterend", `<div id="siPanel" class="ms-panel si2-panel" style="display:none;"></div>`);
  }

  function init() {
    const orig = window.populateWorkspace;
    if (typeof orig === "function" && !orig.__si2) {
      window.populateWorkspace = function (...a) { const r = orig.apply(this, a); setTimeout(() => { mount(); refreshSoon(); }, 0); return r; };
      window.populateWorkspace.__si2 = true;
    }
    document.addEventListener("studio:projectloaded", () => { mount(); refreshSoon(); });
    document.addEventListener("studio:mediasettings", refreshSoon);
    mount();
    refreshSoon();
  }
  window.SourceInfoPanel = { refresh, render, setScriptBullets };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
