// -*- coding: utf-8 -*-
// Studio Pro UI: Công tắc Theme Tối <-> Be Ấm, Toast, Phím tắt, Bộ duyệt & lọc dự án ở cột trái.
// Chỉ BỔ SUNG — mọi hàm global cũ trong app.js giữ nguyên tên & hành vi.
(function () {
  "use strict";
  const THEME_KEY = "vdcs.studio.theme";
  const PB_FILTER_KEY = "vdcs.studio.pbFilter";
  const safeLS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* bỏ qua */ } },
  };
  // currentProjectId / currentProject là biến `let` trong app.js (không gắn vào window) => đọc qua binding toàn cục
  window.studioCurrent = function () {
    return {
      pid: typeof currentProjectId !== "undefined" ? currentProjectId : "",
      project: typeof currentProject !== "undefined" ? currentProject : null,
    };
  };
  const curPid = () => window.studioCurrent().pid;
  const curProj = () => window.studioCurrent().project;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------- Toast ----------------
  function showToast(message, type = "info", ms = 3200) {
    let stack = document.getElementById("spToastStack");
    if (!stack) {
      stack = document.createElement("div");
      stack.id = "spToastStack";
      stack.className = "sp-toast-stack";
      stack.setAttribute("role", "status");
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    const icons = { success: "✅", warning: "⚠️", error: "❌", info: "💡" };
    const el = document.createElement("div");
    el.className = `sp-toast ${type}`;
    el.innerHTML = `<span>${icons[type] || icons.info}</span><div>${message}</div><button class="sp-toast-x" title="Đóng">✕</button>`;
    const close = () => { el.classList.add("leaving"); setTimeout(() => el.remove(), 230); };
    el.querySelector(".sp-toast-x").onclick = close;
    stack.appendChild(el);
    while (stack.children.length > 5) stack.firstChild.remove();
    if (ms > 0) setTimeout(close, ms);
    return el;
  }
  window.showToast = showToast;

  // ---------------- Theme ----------------
  function applyTheme(theme) {
    const t = theme === "beige" ? "beige" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    safeLS.set(THEME_KEY, t);
    document.querySelectorAll(".sp-theme-switch button").forEach((b) => b.classList.toggle("on", b.dataset.theme === t));
    document.dispatchEvent(new CustomEvent("studio:themechange", { detail: { theme: t } }));
    return t;
  }
  window.setStudioTheme = applyTheme;
  window.toggleStudioTheme = function () {
    const next = document.documentElement.getAttribute("data-theme") === "beige" ? "dark" : "beige";
    applyTheme(next);
    showToast(next === "beige" ? "Đã chuyển sang <b>Warm Beige Studio</b> (#F6EFE6 / #FFFDF9)" : "Đã chuyển sang <b>Dark Studio</b>", "success", 1800);
  };

  function mountHeader() {
    const actions = document.querySelector(".top-actions");
    if (!actions || document.getElementById("spThemeSwitch")) return;
    const sw = document.createElement("div");
    sw.id = "spThemeSwitch";
    sw.className = "sp-theme-switch";
    sw.title = "Đổi giao diện Tối / Be ấm (Ctrl+Shift+L)";
    sw.innerHTML = `<button data-theme="dark" onclick="setStudioTheme('dark')">🌙 Tối</button><button data-theme="beige" onclick="setStudioTheme('beige')">☀️ Be ấm</button>`;
    const cfgBtn = actions.querySelector('button[onclick="openConfigModal()"]');
    actions.insertBefore(sw, cfgBtn || null);
    applyTheme(document.documentElement.getAttribute("data-theme") || safeLS.get(THEME_KEY, "dark"));

    const cmdBar = document.getElementById("stickyCommandBar");
    if (cmdBar && !document.getElementById("spShortcutStrip")) {
      const strip = document.createElement("div");
      strip.id = "spShortcutStrip";
      strip.className = "sp-shortcut-strip";
      strip.innerHTML = [
        ["Ctrl+Enter", "Phân tích kịch bản & Chạy bước tiếp"],
        ["Ctrl+S", "Lưu kịch bản & Yêu cầu thiết kế"],
        ["Ctrl+K", "Tìm dự án"],
        ["Ctrl+Shift+L", "Đổi theme"],
        ["Alt+← / →", "Chuyển slide xem trước"],
      ].map(([k, t]) => `<span><span class="sp-kbd">${k}</span> ${t}</span>`).join("");
      const navRow = cmdBar.querySelector(".sticky-nav-row");
      if (navRow) navRow.insertAdjacentElement("afterend", strip);
    }
    fetch("/api/system/environment").then((r) => (r.ok ? r.json() : null)).then((env) => {
      if (!env || !env.cloud_mode) return;
      const brand = document.querySelector(".topbar .brand");
      if (brand && !document.getElementById("spEnvBadge")) {
        brand.insertAdjacentHTML("beforeend", `<span id="spEnvBadge" class="badge warning sp-env-badge" title="Đang chạy trên Linux/Cloud: dùng dữ liệu mẫu & bộ tách nền dự phòng">☁️ Cloud Demo</span>`);
      }
    }).catch(() => {});
  }

  // ---------------- Phân tích kịch bản ngay (server) ----------------
  window.analyzeScriptOutlineNow = async function () {
    const txt = document.getElementById("inpScript")?.value || "";
    if (typeof window.onScriptInputChanged === "function") window.onScriptInputChanged(true);
    if (!txt.trim()) { showToast("Chưa có kịch bản để phân tích.", "warning"); return null; }
    try {
      const res = await window.apiPost("/api/script/analyze", { text: txt, title: document.getElementById("inpTitle")?.value || "" });
      const o = res.outline || {};
      const warns = o.warnings || [];
      showToast(`📋 <b>${esc(o.title || "")}</b> — ${o.count || 0} mục${warns.length ? `<br>⚠️ ${warns.map((w) => esc(w.message)).join("<br>⚠️ ")}` : " • Không có cảnh báo"}`, warns.length ? "warning" : "success", 4200);
      return o;
    } catch (e) {
      showToast("Lỗi phân tích kịch bản: " + esc(e.message), "error");
      return null;
    }
  };

  // Ctrl+S: Lưu kịch bản + yêu cầu thiết kế (visual_prompt)
  window.studioSaveAll = async function () {
    if (!curPid()) { showToast("Hãy chọn hoặc tạo dự án trước.", "warning"); return; }
    try {
      await window.saveProjectSettings();
      const vp = document.getElementById("inpAnhNhacCustomRequest")?.value?.trim() || "";
      if (vp) {
        await window.apiPost(`/api/projects/${encodeURIComponent(curPid())}/visual-prompt`, { text: vp, apply: true });
      }
      showToast(`Đã lưu kịch bản${vp ? " & yêu cầu thiết kế" : ""} cho <b>${esc(curProj()?.title || curPid())}</b>`, "success");
      if (typeof window.reloadProjectBrowser === "function") window.reloadProjectBrowser();
    } catch (e) {
      showToast("Lỗi lưu: " + esc(e.message), "error", 5000);
    }
  };

  function onKeyDown(e) {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && !e.shiftKey && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      window.studioSaveAll();
    } else if (mod && e.key === "Enter" && !e.defaultPrevented) {
      if (document.getElementById("modalBackdrop")?.classList.contains("open")) return;
      e.preventDefault();
      (async () => {
        await window.analyzeScriptOutlineNow();
        if (curPid() && typeof window.runNextStepOrApprove === "function") {
          await window.saveProjectSettings();
          await window.runNextStepOrApprove();
          showToast("▶ Đã chạy bước tiếp theo.", "info", 2000);
        }
      })();
    } else if (mod && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      const inp = document.getElementById("spProjectSearch");
      if (inp) { inp.focus(); inp.select(); }
    } else if (mod && e.shiftKey && (e.key === "l" || e.key === "L")) {
      e.preventDefault();
      window.toggleStudioTheme();
    }
  }

  function init() {
    mountHeader();
    document.addEventListener("keydown", onKeyDown);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
