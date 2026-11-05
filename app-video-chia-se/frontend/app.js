// -*- coding: utf-8 -*-
let currentProjectId = "";
let currentProject = null;
let appConfig = null;
let stepsMeta = [];
let pollTimer = null;

window.addEventListener("DOMContentLoaded", async () => {
  setupDragAndDrop();
  await loadAppConfig();
  await loadQuickSourceVideos();
  await refreshProjectsList();
  startPolling();
});

async function apiGet(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function apiPost(url, body = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function loadAppConfig() {
  try {
    const res = await apiGet("/api/config");
    appConfig = res.config;
    stepsMeta = res.steps_meta || [];
  } catch (e) {
    console.error("Failed to load config:", e);
  }
}

async function refreshProjectsList(selectId = "") {
  try {
    const res = await apiGet("/api/projects");
    const list = res.projects || [];
    const sel = document.getElementById("projectSelect");
    sel.innerHTML = `<option value="">-- Chọn dự án (${list.length}) --</option>`;
    for (const p of list) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.title} [${p.id}] (${p.pipeline_status})`;
      sel.appendChild(opt);
    }
    const target = selectId || currentProjectId || (list[0] && list[0].id) || "";
    if (target) {
      sel.value = target;
      await onSelectProject(target);
    } else {
      renderEmptySidebar();
    }
  } catch (e) {
    console.error(e);
  }
}

async function onSelectProject(pid) {
  if (!pid) {
    currentProjectId = "";
    currentProject = null;
    return;
  }
  currentProjectId = pid;
  try {
    currentProject = await apiGet(`/api/projects/${encodeURIComponent(pid)}`);
    populateWorkspace(currentProject);
  } catch (e) {
    alert("Lỗi tải dự án: " + e.message);
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (!currentProjectId || !currentProject) return;
    if (currentProject.pipeline_status === "running") {
      try {
        const updated = await apiGet(`/api/projects/${encodeURIComponent(currentProjectId)}`);
        const prevGate = currentProject.waiting_gate;
        currentProject = updated;
        renderSidebarSteps(currentProject);
        renderGateBanner(currentProject);
        renderRenderProgress(currentProject);
        renderAiUsageBadge(currentProject);
        if (updated.pipeline_status !== "running" || updated.waiting_gate !== prevGate) {
          populateWorkspace(currentProject);
          if (updated.waiting_gate === "DUNG_1") switchTab("tab1");
          else if (updated.waiting_gate === "DUNG_2") switchTab("tab2");
          else if (updated.waiting_gate === "DUNG_3") switchTab("tab3");
          else if (updated.pipeline_status === "completed") switchTab("tab4");
        }
      } catch (e) {
        console.warn("Poll warning:", e);
      }
    }
  }, 1500);
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-pane").forEach((el) => {
    el.style.display = el.id === tabId ? "block" : "none";
  });
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
  });
}

let activeSidebarStep = 0;

function renderAiUsageBadge(proj) {
  const u = (proj && proj.ai_usage) || { total_calls: 0, total_images: 0 };
  const el = document.getElementById("aiUsageBadge");
  if (el) {
    el.textContent = `Agy CLI: ${u.total_calls || 0} lần gọi`;
  }
}

function renderEmptySidebar() {
  const c = document.getElementById("stepListContainer");
  c.innerHTML = `<div class="step-msg">Chưa có dự án nào được chọn. Bấm "＋ Dự án mới" hoặc chọn "Preset: Giỏ đồ / Chia sẻ" ở thanh trên để bắt đầu.</div>`;
}

function renderSidebarSteps(proj) {
  const c = document.getElementById("stepListContainer");
  if (!proj || !proj.steps) {
    renderEmptySidebar();
    return;
  }
  const presetEl = document.getElementById("inpPreset");
  const curPreset = (presetEl && presetEl.value) || (proj.settings && proj.settings.preset) || "giodo";
  const isAnhNhac = curPreset === "anh_nhac";

  const titleEl = document.getElementById("sidebarStepsTitle");
  if (titleEl) {
    titleEl.textContent = isAnhNhac ? "Tiến trình 4 bước (Ảnh + Nhạc)" : "Tiến trình 10 bước";
  }
  const lblGates = document.getElementById("lblStopAtGates");
  if (lblGates) {
    lblGates.style.display = isAnhNhac ? "none" : "flex";
  }

  const statusMap = {
    pending: `<span class="badge">Chờ</span>`,
    running: `<span class="badge info">⏳ Đang chạy</span>`,
    waiting_approval: `<span class="badge warning">★ Chờ duyệt</span>`,
    done: `<span class="badge success">✅ Xong</span>`,
    error: `<span class="badge danger">❌ Lỗi</span>`,
  };

  if (isAnhNhac) {
    const anhNhacSteps = [
      {
        uiNum: 1,
        realStep: 3,
        name: "1. Nhập Danh sách & Nhạc nền",
        runCode: "parseAndFetchAnhNhacList(false)",
        runLabel: "🔍 Nạp danh sách",
      },
      {
        uiNum: 2,
        realStep: 6,
        name: "2. Tự tìm & Gắn Hình ảnh",
        runCode: "runSingleStep(6, true)",
        runLabel: "↻ Tìm & Khung ảnh",
      },
      {
        uiNum: 3,
        realStep: 7,
        name: "3. Xem 3 Ảnh mẫu (1080×1080)",
        runCode: "rerunStep7Stills()",
        runLabel: "📸 Chụp 3 ảnh mẫu",
      },
      {
        uiNum: 4,
        realStep: 10,
        name: "4. Render & Xuất Video MP4",
        runCode: "runAutoNoGates()",
        runLabel: "🎬 Xuất Video MP4",
      },
    ];
    let html = "";
    for (const item of anhNhacSteps) {
      const i = item.realStep;
      let s = proj.steps[String(i)] || { status: "pending", message: "" };
      if (item.uiNum === 1 && s.status === "pending" && proj.steps["1"] && proj.steps["1"].status !== "pending") {
        s = proj.steps["1"];
      }
      if (item.uiNum === 4 && s.status === "pending" && proj.steps["8"] && proj.steps["8"].status !== "pending") {
        s = proj.steps["8"];
      }
      const badgeHtml = statusMap[s.status] || statusMap.pending;
      const isAct = activeSidebarStep === i || (item.uiNum === 1 && activeSidebarStep === 1) ? "active-step" : "";
      const navTarget = item.uiNum === 1 ? 1 : i;
      html += `
        <div class="step-card ${s.status} ${isAct}" id="sidebarStepCard_${navTarget}" onclick="goToStepView(${navTarget})" title="Bấm để mở màn hình ${escapeHtml(item.name)}">
          <div class="step-head">
            <span>${escapeHtml(item.name)}</span>
            ${badgeHtml}
          </div>
          ${s.message ? `<div class="step-msg">${escapeHtml(s.message)}</div>` : ""}
          <div class="step-actions" onclick="event.stopPropagation()">
            <button class="sm" onclick="event.stopPropagation(); ${item.runCode}">${item.runLabel}</button>
            <button class="sm" onclick="event.stopPropagation(); viewStepLog(${i})">📄 Log</button>
          </div>
        </div>
      `;
    }
    c.innerHTML = html;
    updateStickyActionBar(proj);
    return;
  }

  const cleanStepNames = {
    1: "1. Chuẩn bị & Chuẩn hóa CFR",
    2: "2. Phân tích Âm thanh (Whisper)",
    3: "3. Lập Danh sách cắt (cut.json)",
    4: "4. Chọn cảnh Người nghe (idle.json)",
    5: "5. Dựng Timeline & Media (1.3x)",
    6: "6. Ảnh sản phẩm & Bảng giá",
    7: "7. Chụp 3 Ảnh mẫu (DỪNG 3)",
    8: "8. Render Video MP4 (-14 LUFS)",
    9: "9. Tự kiểm toàn diện (checks.md)",
    10: "10. Xuất 1 Bản Video Hoàn Chỉnh",
  };
  let html = "";
  for (let i = 1; i <= 10; i++) {
    const s = proj.steps[String(i)] || { step: i, name: cleanStepNames[i] || `Bước ${i}`, status: "pending", message: "" };
    const dispName = cleanStepNames[i] || s.name || `Bước ${i}`;
    const badgeHtml = statusMap[s.status] || statusMap.pending;
    const isAct = activeSidebarStep === i ? "active-step" : "";
    html += `
      <div class="step-card ${s.status} ${isAct}" id="sidebarStepCard_${i}" onclick="goToStepView(${i})" title="Bấm để mở đúng màn hình kiểm tra Bước ${i}">
        <div class="step-head">
          <span>${escapeHtml(dispName)}</span>
          ${badgeHtml}
        </div>
        ${s.message ? `<div class="step-msg">${escapeHtml(s.message)}</div>` : ""}
        <div class="step-actions" onclick="event.stopPropagation()">
          <button class="sm" onclick="event.stopPropagation(); runSingleStep(${i}, true)" title="Chạy lại riêng bước ${i}">↻ Chạy bước ${i}</button>
          <button class="sm" onclick="event.stopPropagation(); viewStepLog(${i})">📄 Log</button>
        </div>
      </div>
    `;
  }
  c.innerHTML = html;
  updateStickyActionBar(proj);
}

function goToStepView(stepNum) {
  activeSidebarStep = Number(stepNum) || 1;
  document.querySelectorAll(".step-card").forEach((el) => {
    el.classList.toggle("active-step", el.id === `sidebarStepCard_${activeSidebarStep}`);
  });

  const stepMap = {
    1: { tab: "tab0", targetId: "step1Panel" },
    2: { tab: "tab1", targetId: "step2WhisperDetails", openDetails: "step2WhisperDetails" },
    3: { tab: "tab1", targetId: "step3CutPanel" },
    4: { tab: "tab2", targetId: "step4IdlePanel" },
    5: { tab: "tab3", targetId: "principle1Panel" },
    6: { tab: "tab3", targetId: "productsStep6Panel" },
    7: { tab: "tab3", targetId: "step7StillsPanel" },
    8: { tab: "tab4", targetId: "step8RenderPanel" },
    9: { tab: "tab4", targetId: "step9QaPanel", openDetails: "step9QaDetails" },
    10: { tab: "tab4", targetId: "step10ExportPanel" },
  };

  const info = stepMap[activeSidebarStep] || stepMap[1];
  switchTab(info.tab);

  if (info.openDetails) {
    const det = document.getElementById(info.openDetails);
    if (det && det.tagName === "DETAILS") {
      det.open = true;
    }
  }

  setTimeout(() => {
    const targetEl = document.getElementById(info.targetId);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
      targetEl.classList.remove("step-highlight-flash");
      void targetEl.offsetWidth;
      targetEl.classList.add("step-highlight-flash");
    }
  }, 50);
}

function updateStickyActionBar(proj) {
  const btnNext = document.getElementById("btnStickyNext");
  const btnAuto = document.getElementById("btnStickyAutoAll");
  if (!btnNext || !proj || !proj.steps) return;

  if (proj.pipeline_status === "running") {
    btnNext.disabled = true;
    btnNext.textContent = `⏳ Đang chạy Bước ${proj.current_step || "..."}`;
    if (btnAuto) btnAuto.disabled = true;
    return;
  }
  btnNext.disabled = false;
  if (btnAuto) btnAuto.disabled = false;

  if (proj.waiting_gate === "DUNG_1") {
    btnNext.textContent = "✅ Duyệt DỪNG 1 & Chạy tiếp";
    btnNext.className = "success sm";
    return;
  }
  if (proj.waiting_gate === "DUNG_2") {
    btnNext.textContent = "✅ Duyệt DỪNG 2 & Chạy tiếp";
    btnNext.className = "success sm";
    return;
  }
  if (proj.waiting_gate === "DUNG_3") {
    btnNext.textContent = "✅ Duyệt DỪNG 3 & Render (8→10)";
    btnNext.className = "success sm";
    return;
  }

  let nextStep = 0;
  for (let i = 1; i <= 10; i++) {
    const st = proj.steps[String(i)];
    if (!st || st.status !== "done") {
      nextStep = i;
      break;
    }
  }
  btnNext.className = "primary sm";
  if (nextStep > 0) {
    btnNext.textContent = `▶ Chạy Bước ${nextStep} tiếp theo`;
  } else {
    btnNext.textContent = "🎬 Render lại Video (Bước 8→10)";
  }
}

function renderGateBanner(proj) {
  const box = document.getElementById("gateBannerContainer");
  if (!proj || !proj.waiting_gate) {
    box.innerHTML = "";
    return;
  }
  const gateInfo = {
    DUNG_1: {
      title: "★ ĐANG DỪNG Ở ĐIỂM DỪNG 1 (Bước 3)",
      desc: "Mời sếp nghe thử các câu đã cắt (cut.json) và bấm Duyệt để sang Bước 4.",
      step: 3,
      btnText: "✅ Duyệt DỪNG 1 & Chạy Bước 4",
    },
    DUNG_2: {
      title: "★ ĐANG DỪNG Ở ĐIỂM DỪNG 2 (Bước 4)",
      desc: "Mời sếp xem ứng viên người nghe (idle.json) và bấm Duyệt để dựng Timeline & chụp Ảnh mẫu.",
      step: 4,
      btnText: "✅ Duyệt DỪNG 2 & Chạy Bước 5→7",
    },
    DUNG_3: {
      title: "★ ĐANG DỪNG Ở ĐIỂM DỪNG 3 (Bước 7)",
      desc: "Mời sếp xem 3 ảnh mẫu 1080×1080 (hoặc gõ Prompt sửa ngay bên dưới). Đồng ý thì bấm Duyệt để Render Video MP4.",
      step: 7,
      btnText: "✅ Duyệt DỪNG 3 & Render Video (Bước 8→10)",
    },
  }[proj.waiting_gate];

  if (!gateInfo) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = `
    <div class="gate-banner">
      <div>
        <strong style="font-size:14.5px; color:#fb923c;">${gateInfo.title}</strong>
        <div style="font-size:12.5px; color:#e2e8f0; margin-top:2px;">${gateInfo.desc}</div>
      </div>
      <div style="display:flex; gap:8px; flex-shrink:0;">
        <button onclick="goToStepView(${gateInfo.step})">👁 Mở bước này</button>
        <button class="success" onclick="approveGate('${proj.waiting_gate}')">${gateInfo.btnText}</button>
      </div>
    </div>
  `;
}

function populateWorkspace(proj) {
  if (!proj) return;
  renderAiUsageBadge(proj);
  renderSidebarSteps(proj);
  renderGateBanner(proj);

  const cfg = proj.settings || {};
  document.getElementById("inpTitle").value = proj.title || "";
  document.getElementById("inpPreset").value = cfg.preset || "giodo";
  document.getElementById("inpAskerSide").value = cfg.askerSide || "right";
  document.getElementById("inpClipA").value = proj.clip_a_source || "";
  document.getElementById("inpClipB").value = proj.clip_b_source || "";
  const auxList = proj.clip_aux_sources || [];
  document.getElementById("inpClipAux").value = auxList.length ? auxList[0].path : "";

  document.getElementById("inpStep3Provider").value = cfg.step3_provider || "agy";
  document.getElementById("inpStep4Provider").value = cfg.step4_provider || "agy";
  document.getElementById("inpStep6Provider").value = cfg.step6_provider || "agy";
  document.getElementById("inpStep9Provider").value = cfg.step9_provider || "agy";

  document.getElementById("inpMaskPrice").checked = cfg.maskPrice !== false;
  document.getElementById("inpProductDisplayMode").value = cfg.productDisplayMode || "single";
  document.getElementById("inpSummaryNote").value = cfg.summaryNote || "(Săn Sell để được giá hời)";
  document.getElementById("inpSummarySubtitle").value = cfg.summarySubtitle || "ĐỦ CHO MẸ & BÉ ĐI SINH";
  if (document.getElementById("inpBgmPath")) document.getElementById("inpBgmPath").value = cfg.bgmPath || "";
  if (document.getElementById("inpItemDurationSec")) document.getElementById("inpItemDurationSec").value = cfg.itemDurationSec || 2.4;
  if (document.getElementById("inpAnhNhacCustomRequest")) {
    document.getElementById("inpAnhNhacCustomRequest").value = proj.final_revision_notes || "";
  }

  document.getElementById("adjTitleSize").value = cfg.titleFontSize || 75;
  document.getElementById("adjTitleTop").value = cfg.titleTop ?? 110;
  document.getElementById("adjCropA").value = cfg.cropA ?? 329;
  document.getElementById("adjCropB").value = cfg.cropB ?? 325;
  document.getElementById("adjScaleA").value = cfg.scaleA ?? 1.0;
  document.getElementById("adjScaleB").value = cfg.scaleB ?? 1.06;
  document.getElementById("adjTopA").value = cfg.topA ?? 180;
  document.getElementById("adjTopB").value = cfg.topB ?? 215;

  const prodImgSz = cfg.productImageSize || 400;
  syncProdImgSizeInputs(prodImgSz);
  if (document.getElementById("adjProdLeftX")) document.getElementById("adjProdLeftX").value = cfg.productLeftCenterX ?? 270;
  if (document.getElementById("adjProdRightX")) document.getElementById("adjProdRightX").value = cfg.productRightCenterX ?? 810;
  if (document.getElementById("adjProdCardTop")) document.getElementById("adjProdCardTop").value = cfg.productCardTop ?? 610;
  if (document.getElementById("adjProdNameSize")) document.getElementById("adjProdNameSize").value = cfg.productNameFontSize ?? 50;
  if (document.getElementById("adjProdPriceSize")) document.getElementById("adjProdPriceSize").value = cfg.productPriceFontSize ?? 105;

  const tFont = cfg.titleFont || "Anton";
  const sFont = cfg.subFont || "Anton";
  if (document.getElementById("inpTitleFont")) document.getElementById("inpTitleFont").value = tFont;
  if (document.getElementById("adjTitleFont")) document.getElementById("adjTitleFont").value = tFont;
  if (document.getElementById("inpSubFont")) document.getElementById("inpSubFont").value = sFont;
  if (document.getElementById("adjSubFont")) document.getElementById("adjSubFont").value = sFont;
  updateFontPreview();

  onPresetChange();

  // Load kich_ban.md via file endpoint
  fetch(`/api/projects/${encodeURIComponent(proj.id)}/file?path=text/kich_ban.md`)
    .then((r) => (r.ok ? r.text() : ""))
    .then((txt) => {
      document.getElementById("inpScript").value = txt;
      onScriptInputChanged(false);
    });

  document.getElementById("inpChiaSeItems").value = (proj.chia_se_items || []).join("\n");

  const tImgWrap = document.getElementById("tableImgPreviewWrap");
  const tImg = document.getElementById("tableImgPreview");
  if (tImgWrap && tImg) {
    if (proj.table_image_rel) {
      tImg.src = `/api/projects/${encodeURIComponent(proj.id)}/file?path=${encodeURIComponent(proj.table_image_rel)}&t=${Date.now()}`;
      tImgWrap.style.display = "flex";
    } else {
      tImgWrap.style.display = "none";
    }
  }

  renderBangTable(proj.bang || { items: [], tong: 0 });
  renderStep2Transcripts(proj);
  renderCutEditor(proj);
  renderIdleEditor(proj);
  renderPrinciple1Table(proj);
  renderStillsSection(proj);
  renderProductCards(proj);
  renderRenderProgress(proj);
  renderExportsAndChecks(proj);
}

function parseScriptOutlineJS(rawText, fallbackTitle = "") {
  const lines = String(rawText || "")
    .split(/\r?\n/)
    .map((ln) => ln.trim())
    .filter(Boolean);
  let detectedTitle = (fallbackTitle || "").trim();
  let hasExplicitTitle = false;
  let detectedSubtitle = "";
  let bodyLines = lines.slice();

  if (bodyLines.length > 0) {
    const first = bodyLines[0];
    const mNumTitle = first.match(/^(?:#+\s*)?\d+[\.\)\-\:]\s+(.+)$/);
    if (mNumTitle) {
      const restHasNumbered = bodyLines.slice(1).some((ln) => /^\d+[\.\)\-\:]\s+/.test(ln));
      if (!restHasNumbered) {
        detectedTitle = mNumTitle[1].trim().toUpperCase();
        hasExplicitTitle = true;
        bodyLines = bodyLines.slice(1);
      }
    } else if (
      first.startsWith("#") ||
      (first === first.toUpperCase() && bodyLines.length >= 3) ||
      /^(TOP\s+\d+|DANH\s+SÁCH|GIỎ\s+ĐỒ|BỆNH\s+VIỆN|KÊNH|ĐỒ\s+XÀI|CHIA\s+SẺ)/i.test(first)
    ) {
      const cleanedFirst = first.replace(/^[#*\-\d\.\)\s]+/, "").trim();
      if (cleanedFirst) {
        detectedTitle = cleanedFirst.toUpperCase();
        hasExplicitTitle = true;
      }
      bodyLines = bodyLines.slice(1);
    }
  }

  if (bodyLines.length >= 2) {
    const candSub = bodyLines[0];
    if (
      !candSub.startsWith("-") &&
      !candSub.startsWith("•") &&
      !candSub.startsWith("*") &&
      !candSub.startsWith("+") &&
      (candSub.includes(" - ") || candSub.includes(" – ")) &&
      bodyLines.slice(1).some((ln) => ln.startsWith("-") || ln.startsWith("•") || ln.startsWith("*"))
    ) {
      detectedSubtitle = candSub.trim();
      bodyLines = bodyLines.slice(1);
    }
  }

  const hasSubBullets = bodyLines.some(
    (ln) => ln.startsWith("-") || ln.startsWith("•") || ln.startsWith("*") || ln.startsWith("+")
  );
  const entries = [];
  if (hasSubBullets) {
    let cur = null;
    for (const ln of bodyLines) {
      if (ln.startsWith("-") || ln.startsWith("•") || ln.startsWith("*") || ln.startsWith("+")) {
        const bText = ln.replace(/^[\-\•\*\+\s]+/, "").trim();
        if (cur && bText) cur.bullets.push(bText);
      } else {
        const hClean = ln.replace(/^\d+[\.\)\-\:]\s*/, "").trim();
        if (!hClean) continue;
        cur = { heading: hClean, bullets: [] };
        entries.push(cur);
      }
    }
  } else {
    for (const ln of bodyLines) {
      const hClean = ln.replace(/^[\d\.\)\-\•\*\s]+/, "").trim();
      if (!hClean || hClean.length < 2) continue;
      if (detectedTitle && hClean.toUpperCase() === detectedTitle.toUpperCase()) continue;
      entries.push({ heading: hClean, bullets: [] });
    }
  }

  return {
    title: detectedTitle,
    hasExplicitTitle,
    subtitle: detectedSubtitle,
    entries,
    count: entries.length,
  };
}

function onScriptInputChanged(syncBangIfAnhNhac = true) {
  const inpScript = document.getElementById("inpScript");
  const previewBox = document.getElementById("scriptAnalysisPreviewBox");
  if (!inpScript || !previewBox) return;

  const rawText = inpScript.value || "";
  if (!rawText.trim()) {
    previewBox.style.display = "none";
    return;
  }

  const curTitleInput = document.getElementById("inpTitle");
  const outline = parseScriptOutlineJS(rawText, curTitleInput ? curTitleInput.value : "");

  // Auto-sync title input if script contains an explicit header line (e.g. "6. KÊNH BÁC SĨ", "7. BỆNH VIỆN ĐI SINH")
  if (outline.hasExplicitTitle && outline.title && curTitleInput) {
    if (curTitleInput.value.trim().toUpperCase() !== outline.title.toUpperCase()) {
      curTitleInput.value = outline.title.toUpperCase();
      updateFontPreview();
    }
  }

  // Render live analysis preview box right under #inpScript
  previewBox.style.display = "block";
  const badgesHtml = outline.entries
    .map((ent, idx) => {
      const bCount = ent.bullets.length > 0 ? ` <span style="color:#94a3b8;">(${ent.bullets.length} ý)</span>` : "";
      return `<span style="display:inline-block; padding:2px 8px; margin:2px 4px 2px 0; border-radius:999px; background:rgba(56,189,248,0.14); border:1px solid rgba(56,189,248,0.35); color:#e0f2fe; font-size:11.5px;"><b>${idx + 1}.</b> ${escapeHtml(ent.heading)}${bCount}</span>`;
    })
    .join("");
  const subHtml = outline.subtitle
    ? `<div style="margin-top:3px; color:#fde68a;">✨ Phụ đề: <b>${escapeHtml(outline.subtitle)}</b></div>`
    : "";

  previewBox.innerHTML = `
    <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px;">
      <div>📌 Tiêu đề nhận diện: <b style="color:#38bdf8;">${escapeHtml(outline.title || "(Chưa có tiêu đề)")}</b></div>
      <div>📋 Tổng số mục: <b style="color:#4ade80; font-size:13px;">${outline.count} mục</b></div>
    </div>
    ${subHtml}
    <div style="margin-top:5px;">${badgesHtml || '<span style="color:#94a3b8;">(Chưa nhận diện được danh sách mục)</span>'}</div>
  `;

  // When in Preset Ảnh + Nhạc and user edits script, sync #bangTableBody immediately so stale items (e.g. 7 old rows when script has 6) are replaced right away
  const presetEl = document.getElementById("inpPreset");
  const isAnhNhac = presetEl && presetEl.value === "anh_nhac";
  if (syncBangIfAnhNhac && isAnhNhac && outline.count > 0) {
    const existingRows = collectBangFromTable().items || [];
    const existingByCleanName = {};
    for (const r of existingRows) {
      const cleanKey = String(r.ten || "")
        .replace(/^\d+[\.\)\-\:]\s*/, "")
        .trim()
        .toUpperCase();
      if (cleanKey) existingByCleanName[cleanKey] = r;
    }
    const newItems = outline.entries.map((ent, idx0) => {
      const idx = idx0 + 1;
      const cleanHeading = ent.heading.trim();
      const prev = existingByCleanName[cleanHeading.toUpperCase()] || {};
      const bulletStr =
        ent.bullets && ent.bullets.length > 0
          ? ent.bullets.join(" | ")
          : prev.ghi_chu || "";
      return {
        i: idx,
        nhom: 1,
        ten: cleanHeading,
        display_name: cleanHeading.toUpperCase(),
        sl: 1,
        dv: "Mục",
        gia: 0,
        no_price: true,
        is_scene_photo: true,
        ghi_chu: bulletStr,
        bullets: ent.bullets && ent.bullets.length > 0 ? ent.bullets : prev.bullets || [],
        custom_image_path: prev.custom_image_path || "",
      };
    });
    renderBangTable({ items: newItems, tong: 0 });
  }
}

function onPresetChange() {
  const preset = document.getElementById("inpPreset").value;
  const isAnhNhac = preset === "anh_nhac";
  const isTableMode = preset === "giodo" || isAnhNhac;
  document.getElementById("presetBConfigBox").style.display = isTableMode ? "block" : "none";
  document.getElementById("presetAConfigBox").style.display = preset === "chiase" ? "block" : "none";
  document.getElementById("productsStep6Panel").style.display = isTableMode ? "block" : "none";
  const anhNhacBox = document.getElementById("presetAnhNhacBox");
  if (anhNhacBox) anhNhacBox.style.display = isAnhNhac ? "block" : "none";
  const dropTbl = document.getElementById("dropTableImage");
  if (dropTbl) dropTbl.style.display = isAnhNhac ? "none" : "block";

  // Hide irrelevant voice / 2-person inputs & tabs when in simple Ảnh + Nhạc mode
  const boxAsker = document.getElementById("boxAskerSide");
  if (boxAsker) boxAsker.style.display = isAnhNhac ? "none" : "block";
  const clipsGrid = document.getElementById("sourceClipsGrid");
  if (clipsGrid) clipsGrid.style.display = isAnhNhac ? "none" : "grid";
  const cliGrid = document.getElementById("cliProvidersGrid");
  if (cliGrid) cliGrid.style.display = isAnhNhac ? "none" : "grid";
  const p1Panel = document.getElementById("principle1Panel");
  if (p1Panel) p1Panel.style.display = isAnhNhac ? "none" : "block";

  // Simplify table columns & price controls in Ảnh + Nhạc mode
  const lblHdr = document.getElementById("lblBangTableHeader");
  if (lblHdr) {
    lblHdr.textContent = isAnhNhac
      ? "🖼️ Danh sách mục & Hình ảnh (Tự động nạp từ kịch bản)"
      : "🛒 Bảng sản phẩm (bang.json) & Tuỳ chọn giá";
  }
  const lblMask = document.getElementById("lblMaskPriceOpt");
  if (lblMask) lblMask.style.display = isAnhNhac ? "none" : "inline-flex";
  const selDispMode = document.getElementById("inpProductDisplayMode");
  if (selDispMode) selDispMode.style.display = isAnhNhac ? "none" : "inline-block";
  const boxTotal = document.getElementById("boxTotalGia");
  if (boxTotal) boxTotal.style.display = isAnhNhac ? "none" : "block";
  document.querySelectorAll(".col-price-only").forEach((el) => {
    el.style.display = isAnhNhac ? "none" : "";
  });

  // Hide Top Voice/Listener Tabs in Ảnh + Nhạc mode
  const tabBtn0 = document.querySelector('.tab-btn[data-tab="tab0"]');
  const tabBtn1 = document.querySelector('.tab-btn[data-tab="tab1"]');
  const tabBtn2 = document.querySelector('.tab-btn[data-tab="tab2"]');
  const tabBtn3 = document.querySelector('.tab-btn[data-tab="tab3"]');
  const tabBtn4 = document.querySelector('.tab-btn[data-tab="tab4"]');
  if (tabBtn1) tabBtn1.style.display = isAnhNhac ? "none" : "";
  if (tabBtn2) tabBtn2.style.display = isAnhNhac ? "none" : "";
  if (tabBtn0) tabBtn0.textContent = isAnhNhac ? "1. Danh sách & Nhạc" : "0. Nguồn & Kịch bản";
  if (tabBtn3) tabBtn3.textContent = isAnhNhac ? "2. Hình ảnh & 3 Ảnh mẫu" : "3. Ảnh SP & Mẫu (Bước 5–7)";
  if (tabBtn4) tabBtn4.textContent = isAnhNhac ? "3. Xuất Video MP4" : "4. Xuất Video (Bước 8–10)";

  const btnGioDo = document.getElementById("btnTopPresetGioDo");
  const btnChiaSe = document.getElementById("btnTopPresetChiaSe");
  const btnAnhNhac = document.getElementById("btnTopPresetAnhNhac");
  if (btnGioDo) btnGioDo.classList.toggle("active", preset === "giodo");
  if (btnChiaSe) btnChiaSe.classList.toggle("active", preset === "chiase");
  if (btnAnhNhac) btnAnhNhac.classList.toggle("active", isAnhNhac);

  if (currentProject) {
    renderSidebarSteps(currentProject);
  }
}

async function selectPresetQuick(preset) {
  const sel = document.getElementById("inpPreset");
  if (sel) {
    sel.value = preset;
    onPresetChange();
  }
  switchTab("tab0");
  if (currentProjectId) {
    await saveProjectSettings();
  } else {
    createNewBlankProject(preset);
  }
}

function swapAskerSide() {
  const sel = document.getElementById("inpAskerSide");
  sel.value = sel.value === "right" ? "left" : "right";
}

const CSS_FONT_MAP = {
  Anton: "'Anton', sans-serif",
  BarlowCondensed: "'Barlow Condensed', sans-serif",
  BeVietnamPro: "'Be Vietnam Pro', sans-serif",
  Montserrat: "'Montserrat', sans-serif",
  Oswald: "'Oswald', sans-serif",
  Baloo2: "'Baloo 2', cursive",
  PaytoneOne: "'Paytone One', sans-serif",
  Bangers: "'Bangers', cursive",
  Phudu: "'Phudu', sans-serif",
  Coiny: "'Coiny', cursive",
  Kanit: "'Kanit', sans-serif",
  ChakraPetch: "'Chakra Petch', sans-serif",
  Mali: "'Mali', cursive",
  PatrickHand: "'Patrick Hand', cursive",
  Lexend: "'Lexend', sans-serif",
};

function onFontSelectChange(role, val) {
  if (role === "title") {
    if (document.getElementById("inpTitleFont")) document.getElementById("inpTitleFont").value = val;
    if (document.getElementById("adjTitleFont")) document.getElementById("adjTitleFont").value = val;
  } else {
    if (document.getElementById("inpSubFont")) document.getElementById("inpSubFont").value = val;
    if (document.getElementById("adjSubFont")) document.getElementById("adjSubFont").value = val;
  }
  updateFontPreview();
}

function updateFontPreview() {
  const tKey = (document.getElementById("inpTitleFont") && document.getElementById("inpTitleFont").value) || "Anton";
  const sKey = (document.getElementById("inpSubFont") && document.getElementById("inpSubFont").value) || "Anton";
  const tEl = document.getElementById("previewTitleFontText");
  const sEl = document.getElementById("previewSubFontText");
  const titleVal = (document.getElementById("inpTitle") && document.getElementById("inpTitle").value.trim()) || "GIỎ ĐỒ ĐI SINH 1 TR";
  if (tEl) {
    tEl.style.fontFamily = CSS_FONT_MAP[tKey] || "'Anton', sans-serif";
    tEl.textContent = titleVal.toUpperCase();
  }
  if (sEl) {
    sEl.style.fontFamily = CSS_FONT_MAP[sKey] || "'Anton', sans-serif";
  }
}

function renderBangTable(bang) {
  const tbody = document.getElementById("bangTableBody");
  document.getElementById("inpTotalGia").value = bang.tong || 0;
  const isAnhNhac = document.getElementById("inpPreset") && document.getElementById("inpPreset").value === "anh_nhac";
  const priceStyle = isAnhNhac ? 'display:none;' : '';
  const items = bang.items || [];
  tbody.innerHTML = items
    .map(
      (it, idx) => {
        const rowNum = it.i || idx + 1;
        return `
    <tr data-custom-img="${escapeHtml(it.custom_image_path || "")}">
      <td><input type="number" class="bang-i" value="${rowNum}" style="padding:4px;" /></td>
      <td><input type="text" class="bang-ten" value="${escapeHtml(it.ten || "")}" style="padding:4px;" /></td>
      <td><input type="text" class="bang-disp" value="${escapeHtml(it.display_name || it.ten || "")}" placeholder="VD: TỪ DŨ / DOOMI BABY" style="padding:4px;" /></td>
      <td class="col-price-only" style="${priceStyle}"><input type="number" class="bang-sl" value="${it.sl ?? 1}" style="padding:4px;" /></td>
      <td class="col-price-only" style="${priceStyle}"><input type="text" class="bang-dv" value="${escapeHtml(it.dv || "Cái")}" style="padding:4px;" /></td>
      <td class="col-price-only" style="${priceStyle}"><input type="number" class="bang-gia" value="${it.gia ?? 0}" style="padding:4px;" /></td>
      <td><input type="text" class="bang-note" value="${escapeHtml(it.ghi_chu || it.brand || "")}" placeholder="Mô tả / Ghi chú..." style="padding:4px;" /></td>
      <td style="text-align:center;">
        <div style="display:flex; gap:4px; justify-content:center;">
          <button class="sm ${it.custom_image_path ? "success" : ""}" onclick="pickRowProductImage(this)" title="${escapeHtml(it.custom_image_path || "Chọn ảnh có sẵn trên máy cho mục này")}">
            ${it.custom_image_path ? "✅ Ảnh" : "🖼 Chọn"}
          </button>
          <button class="sm primary" onclick="openDoctorImageEditorModal(${rowNum})" title="Tải ảnh có sẵn & Cắt/Tách nền lấy mỗi hình Bác Sĩ cho mục #${rowNum}">
            ✂️ Lấy BS
          </button>
        </div>
      </td>
      <td><button class="sm danger" onclick="this.closest('tr').remove()">✕</button></td>
    </tr>
  `;
      }
    )
    .join("");
}

function addProductRow() {
  const tbody = document.getElementById("bangTableBody");
  const idx = tbody.querySelectorAll("tr").length + 1;
  const isAnhNhac = document.getElementById("inpPreset") && document.getElementById("inpPreset").value === "anh_nhac";
  const priceStyle = isAnhNhac ? 'display:none;' : '';
  const tr = document.createElement("tr");
  tr.setAttribute("data-custom-img", "");
  tr.innerHTML = `
    <td><input type="number" class="bang-i" value="${idx}" style="padding:4px;" /></td>
    <td><input type="text" class="bang-ten" value="" placeholder="Tên mục" style="padding:4px;" /></td>
    <td><input type="text" class="bang-disp" value="" placeholder="Tên hiện trên hình" style="padding:4px;" /></td>
    <td class="col-price-only" style="${priceStyle}"><input type="number" class="bang-sl" value="1" style="padding:4px;" /></td>
    <td class="col-price-only" style="${priceStyle}"><input type="text" class="bang-dv" value="Cái" style="padding:4px;" /></td>
    <td class="col-price-only" style="${priceStyle}"><input type="number" class="bang-gia" value="0" style="padding:4px;" /></td>
    <td><input type="text" class="bang-note" value="" placeholder="Mô tả / Ghi chú" style="padding:4px;" /></td>
    <td style="text-align:center;">
      <div style="display:flex; gap:4px; justify-content:center;">
        <button class="sm" onclick="pickRowProductImage(this)" title="Chọn ảnh riêng cho mục này">🖼 Chọn</button>
        <button class="sm primary" onclick="openDoctorImageEditorModal(${idx})" title="Tải ảnh & Cắt/Tách nền lấy mỗi hình Bác Sĩ">✂️ Lấy BS</button>
      </div>
    </td>
    <td><button class="sm danger" onclick="this.closest('tr').remove()">✕</button></td>
  `;
  tbody.appendChild(tr);
}

function collectBangFromTable() {
  const rows = Array.from(document.querySelectorAll("#bangTableBody tr"));
  const origItems = (currentProject && currentProject.bang && currentProject.bang.items) || [];
  const items = rows.map((r, idx) => {
    const customImg = r.getAttribute("data-custom-img") || "";
    const noteEl = r.querySelector(".bang-note");
    const iVal = Number(r.querySelector(".bang-i").value) || idx + 1;
    const matchOrig = origItems.find((o) => Number(o.i) === iVal);
    const scaleInputEl = document.getElementById(`prodScaleInput_${iVal}`);
    let imgScale = matchOrig && matchOrig.image_scale ? Number(matchOrig.image_scale) : 1.0;
    if (scaleInputEl) {
      const pctVal = parseFloat(scaleInputEl.value);
      if (!isNaN(pctVal) && pctVal > 10) {
        imgScale = Number((pctVal / 100.0).toFixed(2));
      }
    }
    const obj = {
      i: iVal,
      nhom: 1,
      ten: r.querySelector(".bang-ten").value.trim(),
      display_name: r.querySelector(".bang-disp").value.trim(),
      sl: Number(r.querySelector(".bang-sl").value) || 1,
      dv: r.querySelector(".bang-dv").value.trim(),
      gia: Number(r.querySelector(".bang-gia").value) || 0,
      ghi_chu: noteEl ? noteEl.value.trim() : "",
      image_scale: imgScale,
    };
    if (customImg) obj.custom_image_path = customImg;
    else if (matchOrig && matchOrig.custom_image_path) obj.custom_image_path = matchOrig.custom_image_path;
    if (matchOrig) {
      if (matchOrig.no_price) obj.no_price = true;
      if (matchOrig.is_scene_photo) obj.is_scene_photo = true;
      if (matchOrig.is_doctor_cutout) obj.is_doctor_cutout = true;
      if (matchOrig.raw_image_path) obj.raw_image_path = matchOrig.raw_image_path;
      if (matchOrig.doctor_edit_mode) obj.doctor_edit_mode = matchOrig.doctor_edit_mode;
      if (matchOrig.doctor_crop_box) obj.doctor_crop_box = matchOrig.doctor_crop_box;
      if (matchOrig.bullets) obj.bullets = matchOrig.bullets;
      if (matchOrig.search_query) obj.search_query = matchOrig.search_query;
      if (matchOrig.web_image_query) obj.web_image_query = matchOrig.web_image_query;
      if (matchOrig.web_candidate_index !== undefined) obj.web_candidate_index = matchOrig.web_candidate_index;
      if (matchOrig.web_image_source) obj.web_image_source = matchOrig.web_image_source;
    }
    return obj;
  });
  const tong = Number(document.getElementById("inpTotalGia").value) || items.reduce((a, b) => a + b.gia, 0);
  const prevSubtitle = (currentProject && currentProject.bang && currentProject.bang.subtitle) || "";
  return {
    tieu_de: document.getElementById("inpTitle").value.trim(),
    subtitle: prevSubtitle,
    tong,
    items,
  };
}

async function clearBangTable() {
  if (!confirm("Xóa trắng bảng sản phẩm và kịch bản hiện tại để nhập dữ án mới?")) return;
  document.getElementById("bangTableBody").innerHTML = "";
  document.getElementById("inpTotalGia").value = 0;
  document.getElementById("inpScript").value = "";
  if (currentProjectId) {
    await saveProjectSettings();
  }
}

async function pickRowProductImage(btn) {
  const tr = btn.closest("tr");
  const ten = tr.querySelector(".bang-ten").value || "Sản phẩm";
  const res = await apiPost("/api/system/pick-file", {
    title: `Chọn ảnh tách nền cho: ${ten}`,
    filter: "Ảnh sản phẩm (*.png;*.webp;*.jpg;*.jpeg)|*.png;*.webp;*.jpg;*.jpeg|Tất cả file (*.*)|*.*",
    initial_dir: "H:\\source\\san pham",
  });
  if (res.path) {
    tr.setAttribute("data-custom-img", res.path);
    btn.className = "sm success";
    btn.textContent = "✅ Ảnh";
    btn.title = res.path;
    if (currentProjectId) {
      const bang = collectBangFromTable();
      currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/bang`, {
        bang,
        run_step6: true,
      });
      populateWorkspace(currentProject);
    }
  }
}

async function saveProjectSettings() {
  if (!currentProjectId) return;
  const auxPath = document.getElementById("inpClipAux").value.trim();
  const clip_aux_sources = auxPath ? [{ who: "B", path: auxPath, label: "ClipPhu" }] : [];

  const body = {
    title: document.getElementById("inpTitle").value.trim(),
    clip_a_source: document.getElementById("inpClipA").value.trim(),
    clip_b_source: document.getElementById("inpClipB").value.trim(),
    clip_aux_sources,
    script_text: document.getElementById("inpScript").value,
    chia_se_items: document
      .getElementById("inpChiaSeItems")
      .value.split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
    bang: collectBangFromTable(),
    settings: {
      preset: document.getElementById("inpPreset").value,
      askerSide: document.getElementById("inpAskerSide").value,
      maskPrice: document.getElementById("inpMaskPrice").checked,
      productDisplayMode: document.getElementById("inpProductDisplayMode").value,
      summaryNote: document.getElementById("inpSummaryNote").value.trim(),
      summarySubtitle: document.getElementById("inpSummarySubtitle").value.trim(),
      step3_provider: document.getElementById("inpStep3Provider").value,
      step4_provider: document.getElementById("inpStep4Provider").value,
      step6_provider: document.getElementById("inpStep6Provider").value,
      step9_provider: document.getElementById("inpStep9Provider").value,
      titleFont: (document.getElementById("inpTitleFont") && document.getElementById("inpTitleFont").value) || "Anton",
      subFont: (document.getElementById("inpSubFont") && document.getElementById("inpSubFont").value) || "Anton",
      titleFontSize: Number(document.getElementById("adjTitleSize").value) || 75,
      titleTop: Number(document.getElementById("adjTitleTop").value) || 110,
      cropA: Number(document.getElementById("adjCropA").value) || 329,
      cropB: Number(document.getElementById("adjCropB").value) || 325,
      scaleA: Number(document.getElementById("adjScaleA").value) || 1.0,
      scaleB: Number(document.getElementById("adjScaleB").value) || 1.06,
      topA: Number(document.getElementById("adjTopA").value) || 180,
      topB: Number(document.getElementById("adjTopB").value) || 215,
      productImageSize: Number((document.getElementById("adjProdImgSize") && document.getElementById("adjProdImgSize").value) || 400),
      productLeftCenterX: Number((document.getElementById("adjProdLeftX") && document.getElementById("adjProdLeftX").value) || 270),
      productRightCenterX: Number((document.getElementById("adjProdRightX") && document.getElementById("adjProdRightX").value) || 810),
      productCardTop: Number((document.getElementById("adjProdCardTop") && document.getElementById("adjProdCardTop").value) || 610),
      productNameFontSize: Number((document.getElementById("adjProdNameSize") && document.getElementById("adjProdNameSize").value) || 50),
      productPriceFontSize: Number((document.getElementById("adjProdPriceSize") && document.getElementById("adjProdPriceSize").value) || 105),
      bgmPath: (document.getElementById("inpBgmPath") && document.getElementById("inpBgmPath").value.trim()) || "",
      itemDurationSec: Number((document.getElementById("inpItemDurationSec") && document.getElementById("inpItemDurationSec").value) || 2.4),
    },
  };
  currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/settings`, body);
  populateWorkspace(currentProject);
}

async function saveAndStartStep1() {
  await saveProjectSettings();
  await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/run`, {
    start_step: 1,
    stop_at_gates: true,
    single_step_only: false,
  });
  currentProject.pipeline_status = "running";
  renderSidebarSteps(currentProject);
}

async function saveAndStartAutoAll() {
  if (!currentProjectId) return;
  await saveProjectSettings();
  await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/run`, {
    start_step: 1,
    stop_at_gates: false,
    single_step_only: false,
  });
  currentProject.pipeline_status = "running";
  currentProject.waiting_gate = null;
  renderGateBanner(currentProject);
  renderSidebarSteps(currentProject);
}

// ------------------------------------------------------------------------
// TAB 1: STEP 2 TRANSCRIPTS & STOP GATE 1 (CUT.JSON)
// ------------------------------------------------------------------------
function renderStep2Transcripts(proj) {
  document.getElementById("txtPhienAmA").textContent = proj.phien_am_A || "(Chưa chạy Bước 2)";
  document.getElementById("txtPhienAmB").textContent = proj.phien_am_B || "(Chưa chạy Bước 2)";
  document.getElementById("txtEnergyA").textContent = proj.energy_A || "";
  document.getElementById("txtEnergyB").textContent = proj.energy_B || "";
}

function renderCutEditor(proj) {
  const cut = proj.cut || { turns: [], dropped: [], unsure: [] };
  const container = document.getElementById("cutTurnsContainer");
  const joinedPlayer = document.getElementById("joinedAudioPlayer");
  joinedPlayer.src = `/api/projects/${encodeURIComponent(proj.id)}/file?path=media/voice_preview.wav&t=${Date.now()}`;

  if (!cut.turns || !cut.turns.length) {
    container.innerHTML = `<div class="step-msg">Chưa có dữ liệu cut.json. Hãy chạy Bước 3 trước.</div>`;
    return;
  }

  let html = "";
  cut.turns.forEach((turn, ti) => {
    const who = turn.who || "A";
    const roleLabel = who === "A" ? "Người HỎI (A)" : "Người ĐÁP (B)";
    html += `
      <div class="turn-box who-${who}" data-turn="${ti}">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <div>
            <strong>Lượt ${ti + 1}:</strong>
            <select class="turn-who" style="width:160px; display:inline-block; margin-left:6px;">
              <option value="A" ${who === "A" ? "selected" : ""}>Người HỎI (A)</option>
              <option value="B" ${who === "B" ? "selected" : ""}>Người ĐÁP (B)</option>
            </select>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="sm" onclick="addPieceToTurn(${ti})">＋ Thêm câu (piece)</button>
            <button class="sm danger" onclick="removeTurn(${ti})">✕ Xóa lượt</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width:95px;">Start (s)</th>
              <th style="width:95px;">End (s)</th>
              <th>Lời thoại thật (Ấn <strong>Enter</strong> để tách xuống dòng mới; sửa chữ xong bấm <strong>🔍 Dò giây</strong>)</th>
              <th style="width:75px;">Item #</th>
              <th style="width:270px;">Công cụ sửa Voice &amp; Nghe thử</th>
              <th style="width:40px;"></th>
            </tr>
          </thead>
          <tbody>
            ${(turn.pieces || [])
              .map(
                (p, pi) => `
              <tr class="piece-row" data-orig-start="${p.start}" data-orig-end="${p.end}" data-orig-text="${escapeHtml(p.text || "")}">
                <td><input type="number" step="0.05" class="p-start" value="${p.start}" title="Giảm 0.1–0.2s nếu bị cụt chữ đầu" /></td>
                <td><input type="number" step="0.05" class="p-end" value="${p.end}" title="Tăng 0.1–0.2s nếu bị cụt chữ cuối" /></td>
                <td><input type="text" class="p-text" value="${escapeHtml(p.text || "")}" onkeydown="onPieceTextKeyDown(event, ${ti}, ${pi})" title="Đặt con trỏ vào chỗ muốn ngắt rồi nhấn phím Enter để tách xuống dòng mới" /></td>
                <td><input type="number" class="p-item" value="${p.item ?? ""}" placeholder="-" /></td>
                <td>
                  <div style="display:flex; gap:4px; flex-wrap:wrap;">
                    <button class="sm primary" onclick="playOrRegeneratePieceAudio(this, ${ti}, ${pi}, '${p.preview_wav || ""}')" title="Nghe thử (Nếu vừa sửa Chữ hoặc Start/End sẽ tự cắt lại tiếng mới rồi phát)">
                      ▶ Nghe (${(p.end - p.start).toFixed(2)}s)
                    </button>
                    <button class="sm" onclick="matchPieceTimeFromText(${ti}, ${pi}, this)" title="Dò chính xác từng chữ bằng AI Whisper (Nếu xóa chữ ở giữa câu sẽ tự tách thành 2 dòng bỏ khúc lặp!)">
                      🔍 Dò giây
                    </button>
                    <button class="sm" onclick="splitPieceFromButton(${ti}, ${pi}, this)" title="Tách câu này xuống dòng mới (hoặc đặt con trỏ trong ô chữ rồi nhấn phím Enter)">
                      ↵ Xuống dòng
                    </button>
                    <button class="sm" onclick="openTranscriptPickerModal(${ti}, ${pi}, '${who}')" title="Mở danh sách toàn bộ các câu trong video gốc để chọn lại câu/take khác">
                      📋 Chọn take
                    </button>
                  </div>
                </td>
                <td><button class="sm danger" onclick="this.closest('tr').remove()">✕</button></td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  });
  html += `<button onclick="addNewTurn()">＋ Thêm Lượt Hội Thoại Mới</button>`;
  container.innerHTML = html;

  // Dropped list
  const droppedBox = document.getElementById("droppedListContainer");
  const dropped = cut.dropped || [];
  if (!dropped.length) {
    droppedBox.innerHTML = `<div class="step-msg">Không có đoạn bị bỏ nào được ghi nhận (hoặc đã lọc sạch từ Energy).</div>`;
  } else {
    droppedBox.innerHTML = `
      <table>
        <thead><tr><th>Người</th><th>Mốc giây</th><th>Lý do bỏ / Nội dung</th><th>Nghe &amp; Khôi phục</th></tr></thead>
        <tbody>
          ${dropped
            .map(
              (d, di) => `
            <tr>
              <td><strong>${escapeHtml(d.who || "")}</strong></td>
              <td>${d.start}s – ${d.end}s</td>
              <td>${escapeHtml(d.why || "")}</td>
              <td style="display:flex; gap:6px;">
                ${
                  d.preview_wav
                    ? `<button class="sm primary" onclick="playPreviewAudio('${d.preview_wav}')">▶ Nghe</button>`
                    : `<button class="sm" onclick="playClipRangeAudio('${d.who || "B"}', ${d.start}, ${d.end})">▶ Nghe gốc</button>`
                }
                <button class="sm success" onclick="restoreDroppedPiece(${di})" title="Đưa đoạn này lên bảng câu cắt">＋ Lấy lại câu này</button>
              </td>
            </tr>
          `
            )
            .join("")}
        </tbody>
      </table>
    `;
  }

  // Unsure list
  const unsureBox = document.getElementById("unsureListContainer");
  const unsure = cut.unsure || [];
  unsureBox.innerHTML = unsure.length
    ? `<ul>${unsure.map((u) => `<li>${escapeHtml(String(u))}</li>`).join("")}</ul>`
    : `<div class="step-msg">Không có mục phân vân (unsure = []).</div>`;
}

let activePreviewAudio = null;
function playPreviewAudio(relPath) {
  if (!currentProjectId) return;
  if (activePreviewAudio) {
    activePreviewAudio.pause();
  }
  const url = `/api/projects/${encodeURIComponent(currentProjectId)}/file?path=${encodeURIComponent(relPath)}&t=${Date.now()}`;
  activePreviewAudio = new Audio(url);
  activePreviewAudio.play();
}

function collectCutFromDOM() {
  const cut = (currentProject && currentProject.cut) || { turns: [], idle: { A: [], B: [] }, dropped: [], unsure: [] };
  const turnBoxes = Array.from(document.querySelectorAll("#cutTurnsContainer .turn-box"));
  const turns = turnBoxes.map((tb, ti) => {
    const who = tb.querySelector(".turn-who").value;
    const rows = Array.from(tb.querySelectorAll("tbody tr.piece-row"));
    const origPieces = (cut.turns && cut.turns[ti] && cut.turns[ti].pieces) || [];
    const pieces = rows.map((r, pi) => {
      const origP = origPieces[pi] || {};
      const itemRaw = r.querySelector(".p-item").value.trim();
      const newStart = parseFloat(r.querySelector(".p-start").value) || 0;
      const newEnd = parseFloat(r.querySelector(".p-end").value) || 0;
      const origStart = parseFloat(r.getAttribute("data-orig-start")) || 0;
      const origEnd = parseFloat(r.getAttribute("data-orig-end")) || 0;
      const startEdited = Math.abs(newStart - origStart) > 0.005;
      const endEdited = Math.abs(newEnd - origEnd) > 0.005;
      const updated = {
        ...origP,
        start: newStart,
        end: newEnd,
        text: r.querySelector(".p-text").value.trim(),
        item: itemRaw === "" ? null : parseInt(itemRaw, 10),
      };
      if (startEdited || endEdited) {
        updated.custom_pad = true;
        if (startEdited) updated.pad_in = 0.01;
        if (endEdited) updated.pad_out = 0.01;
      }
      return updated;
    });
    return { who, pieces };
  });
  return {
    ...cut,
    turns,
  };
}

function addPieceToTurn(ti) {
  const c = collectCutFromDOM();
  if (c.turns[ti]) {
    const last = c.turns[ti].pieces[c.turns[ti].pieces.length - 1] || { end: 10.0 };
    c.turns[ti].pieces.push({
      start: Number((last.end + 0.5).toFixed(2)),
      end: Number((last.end + 2.5).toFixed(2)),
      text: "Câu mới...",
      item: null,
    });
    currentProject.cut = c;
    renderCutEditor(currentProject);
  }
}

function onPieceTextKeyDown(event, ti, pi) {
  if (event.key === "Enter") {
    event.preventDefault();
    splitOrInsertPieceAtCursor(ti, pi, event.target);
  }
}

function splitPieceFromButton(ti, pi, btn) {
  const tr = btn.closest("tr");
  const inp = tr ? tr.querySelector(".p-text") : null;
  splitOrInsertPieceAtCursor(ti, pi, inp);
}

function splitOrInsertPieceAtCursor(ti, pi, inpEl) {
  const fullVal = inpEl ? inpEl.value : "";
  const selStart = inpEl && typeof inpEl.selectionStart === "number" ? inpEl.selectionStart : fullVal.length;
  const selEnd = inpEl && typeof inpEl.selectionEnd === "number" ? inpEl.selectionEnd : selStart;

  const c = collectCutFromDOM();
  const turn = c.turns[ti];
  if (!turn || !turn.pieces[pi]) return;
  const curP = turn.pieces[pi];
  const s0 = Number(curP.start) || 0;
  const e0 = Number(curP.end) || (s0 + 2.0);

  let textBefore = fullVal.slice(0, selStart).trim();
  let textAfter = fullVal.slice(selEnd).trim();

  // If user clicked the button without placing cursor inside the text, try splitting at a natural mid-point or repeat
  if (!textBefore || !textAfter) {
    if (textBefore && !textAfter) {
      // Cursor at the very end -> insert a new row right below with the same candidate time window so user can type/paste & 🔍 Dò giây
      const newPiece = {
        start: s0,
        end: e0,
        text: "",
        item: null,
        custom_pad: true,
        pad_in: 0.01,
        pad_out: 0.01,
      };
      turn.pieces.splice(pi + 1, 0, newPiece);
      currentProject.cut = c;
      renderCutEditor(currentProject);
      focusPieceInput(ti, pi + 1);
      return;
    }
  }

  // Cursor is inside the text -> split into 2 rows (textBefore on pi, textAfter on pi + 1)
  const ratio = Math.max(0.15, Math.min(0.85, textBefore.length / Math.max(1, textBefore.length + textAfter.length)));
  const midTime = Number((s0 + (e0 - s0) * ratio).toFixed(2));
  const origItem = curP.item ?? null;
  const firstHasBracket = textBefore.includes("[");
  const secondHasBracket = textAfter.includes("[");

  const piece1 = {
    ...curP,
    start: s0,
    end: midTime,
    text: textBefore,
    item: secondHasBracket && !firstHasBracket ? null : origItem,
    custom_pad: true,
    pad_in: curP.pad_in ?? 0.08,
    pad_out: 0.01,
    preview_wav: "",
  };
  const piece2 = {
    start: midTime,
    end: e0,
    text: textAfter,
    item: secondHasBracket && !firstHasBracket ? origItem : null,
    custom_pad: true,
    pad_in: 0.01,
    pad_out: curP.pad_out ?? 0.12,
    preview_wav: "",
  };

  turn.pieces.splice(pi, 1, piece1, piece2);
  currentProject.cut = c;
  renderCutEditor(currentProject);
  focusPieceInput(ti, pi + 1);
}

function focusPieceInput(ti, pi) {
  setTimeout(() => {
    const turnBox = document.querySelector(`#cutTurnsContainer .turn-box[data-turn="${ti}"]`);
    if (!turnBox) return;
    const rows = turnBox.querySelectorAll("tbody tr.piece-row");
    const targetRow = rows[pi];
    if (targetRow) {
      const inp = targetRow.querySelector(".p-text");
      if (inp) {
        inp.focus();
        inp.setSelectionRange(0, 0);
      }
    }
  }, 30);
}

function removeTurn(ti) {
  const c = collectCutFromDOM();
  c.turns.splice(ti, 1);
  currentProject.cut = c;
  renderCutEditor(currentProject);
}

function addNewTurn() {
  const c = collectCutFromDOM();
  c.turns.push({
    who: "A",
    pieces: [{ start: 0.0, end: 2.0, text: "Câu hỏi mới...", item: null }],
  });
  currentProject.cut = c;
  renderCutEditor(currentProject);
}

async function saveCutJsonOnly() {
  if (!currentProjectId) return;
  const cut = collectCutFromDOM();
  currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/cut`, {
    cut,
    regenerate_previews: true,
  });
  renderCutEditor(currentProject);
  alert("Đã lưu cut.json và trích xuất lại file nghe thử!");
}

async function playOrRegeneratePieceAudio(btn, ti, pi, relPath) {
  if (!currentProjectId) return;
  const tr = btn.closest("tr");
  const curStart = parseFloat(tr.querySelector(".p-start").value) || 0;
  const curEnd = parseFloat(tr.querySelector(".p-end").value) || 0;
  const curText = (tr.querySelector(".p-text").value || "").trim();
  const origStart = parseFloat(tr.getAttribute("data-orig-start")) || 0;
  const origEnd = parseFloat(tr.getAttribute("data-orig-end")) || 0;
  const origText = (tr.getAttribute("data-orig-text") || "").trim();

  const timeChanged = Math.abs(curStart - origStart) > 0.005 || Math.abs(curEnd - origEnd) > 0.005;
  const textChanged = normalizeVNCompare(curText) !== normalizeVNCompare(origText);

  if (textChanged && !timeChanged) {
    await matchPieceTimeFromText(ti, pi, btn);
    return;
  }

  if (!relPath || timeChanged) {
    btn.disabled = true;
    btn.textContent = "⏳ Đang cắt lại...";
    const cut = collectCutFromDOM();
    currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/cut`, {
      cut,
      regenerate_previews: true,
    });
    renderCutEditor(currentProject);
    const updatedP = currentProject.cut?.turns?.[ti]?.pieces?.[pi];
    if (updatedP && updatedP.preview_wav) {
      playPreviewAudio(updatedP.preview_wav);
    }
    return;
  }
  playPreviewAudio(relPath);
}

function parseTranscriptLines(rawTxt) {
  const lines = (rawTxt || "").split("\n");
  const out = [];
  for (const line of lines) {
    const m = line.match(/^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*\|\s*(.+)$/);
    if (m) {
      const start = parseFloat(m[1]);
      const end = parseFloat(m[2]);
      const text = m[3].trim();
      if (!text.includes("(ngắn, bỏ qua)")) {
        out.push({ start, end, text });
      }
    }
  }
  return out;
}

function normalizeVNCompare(str) {
  return (str || "")
    .toLowerCase()
    .replace(/\[[^\]]*\]/g, (m) => m.slice(1, -1))
    .replace(/[.,!?;:"'()\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function stripVNAccents(str) {
  return normalizeVNCompare(str)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d");
}

function wordsMatchFuzzy(w1, w2) {
  if (!w1 || !w2) return false;
  if (w1 === w2) return true;
  const a1 = stripVNAccents(w1);
  const a2 = stripVNAccents(w2);
  if (a1 === a2) return true;
  // Handle common Whisper Vietnamese near-homophones (e.g. đam/tam, than/khan, toan/choang)
  if (a1.length >= 3 && a2.length >= 3 && a1.slice(-2) === a2.slice(-2)) {
    return true;
  }
  return false;
}

async function matchPieceTimeFromText(ti, pi, btn = null) {
  if (!currentProject || !currentProjectId) return;
  const cut = collectCutFromDOM();
  const turn = cut.turns[ti];
  if (!turn || !turn.pieces[pi]) return;
  const who = turn.who || "B";
  const piece = turn.pieces[pi];

  const targetWords = normalizeVNCompare(piece.text).split(" ").filter(Boolean);
  if (!targetWords.length) {
    openTranscriptPickerModal(ti, pi, who);
    return;
  }

  const origBtnHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Đang dò từng chữ...";
  }

  try {
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/align-piece-text`, {
      turn_index: ti,
      piece_index: pi,
      cut,
    });
    if (res && res.project) {
      currentProject = res.project;
      renderCutEditor(currentProject);
      const updatedP = currentProject.cut?.turns?.[ti]?.pieces?.[pi];
      if (updatedP && updatedP.preview_wav) {
        playPreviewAudio(updatedP.preview_wav);
      }
      return;
    }
  } catch (err) {
    console.warn("Word-level align fallback:", err);
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnHtml || "🔍 Dò giây";
    }
    alert(`Không tự dò được mốc chữ (${err.message || err}). Mời sếp chọn câu trong danh sách gốc.`);
    openTranscriptPickerModal(ti, pi, who);
  }
}

function openTranscriptPickerModal(ti, pi, who, topMatches = null) {
  if (!currentProject) return;
  const rawTranscript = who === "A" ? currentProject.phien_am_A : currentProject.phien_am_B;
  const allLines = parseTranscriptLines(rawTranscript);
  const listToShow = topMatches && topMatches.length ? topMatches : allLines;

  let html = `
    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap;">
      <p class="step-msg" style="margin:0;">
        Danh sách câu Whisper từ clip <strong>Người ${who === "A" ? "HỎI (A)" : "ĐÁP (B)"}</strong>.
        Sếp có thể bấm <strong>✅ Chọn 1 câu</strong>, hoặc <strong>tích chọn nhiều dòng liên tiếp</strong> rồi bấm nút gộp bên phải:
      </p>
      <button class="success sm" onclick="applyCheckedTranscriptLines(${ti}, ${pi})">
        ✅ Gộp các dòng đã tích vào câu này
      </button>
    </div>
    <div style="max-height:62vh; overflow-y:auto;">
      <table>
        <thead>
          <tr>
            <th style="width:42px; text-align:center;">Tích</th>
            <th style="width:130px;">Mốc giây</th>
            <th>Nội dung Whisper nghe được</th>
            <th style="width:210px;">Thao tác</th>
          </tr>
        </thead>
        <tbody>
          ${listToShow
            .map(
              (c, idx) => `
            <tr>
              <td style="text-align:center;">
                <input type="checkbox" class="chk-trans-line" data-start="${c.start}" data-end="${c.end}" data-text="${escapeHtml(c.text)}" style="width:auto;" />
              </td>
              <td><strong>${c.start.toFixed(2)}s – ${c.end.toFixed(2)}s</strong><br/><span class="step-msg">(${(c.end - c.start).toFixed(2)}s)</span></td>
              <td>${escapeHtml(c.text)}</td>
              <td>
                <div style="display:flex; gap:6px;">
                  <button class="sm" onclick="playClipRangeAudio('${who}', ${c.start}, ${c.end})">▶ Nghe gốc</button>
                  <button class="sm success" onclick="applyTranscriptLineToPiece(${ti}, ${pi}, ${c.start}, ${c.end}, '${escapeJsStr(c.text)}')">✅ Chọn</button>
                </div>
              </td>
            </tr>
          `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
  document.getElementById("modalTitle").textContent = `Chọn / Gộp câu từ bản Phiên âm (${who})`;
  document.getElementById("modalBody").innerHTML = html;
  document.getElementById("modalBackdrop").classList.add("open");
}

async function applyCheckedTranscriptLines(ti, pi) {
  const checked = Array.from(document.querySelectorAll(".chk-trans-line:checked"));
  if (!checked.length) {
    alert("Hãy tích chọn ít nhất 1 dòng trong danh sách trước khi bấm Gộp.");
    return;
  }
  const starts = checked.map((el) => parseFloat(el.getAttribute("data-start")) || 0);
  const ends = checked.map((el) => parseFloat(el.getAttribute("data-end")) || 0);
  const texts = checked.map((el) => el.getAttribute("data-text") || "");
  const minStart = Math.min(...starts);
  const maxEnd = Math.max(...ends);
  const mergedText = texts.join(", ");
  await applyTranscriptLineToPiece(ti, pi, minStart, maxEnd, mergedText);
}

function playClipRangeAudio(who, startSec, endSec) {
  if (!currentProjectId) return;
  if (activePreviewAudio) {
    activePreviewAudio.pause();
  }
  const clipRel = who === "A" ? "nguon/A_hoi.mp4" : "nguon/B_dap.mp4";
  const url = `/api/projects/${encodeURIComponent(currentProjectId)}/file?path=${encodeURIComponent(clipRel)}`;
  activePreviewAudio = new Audio(url);
  activePreviewAudio.currentTime = Math.max(0, startSec - 0.08);
  activePreviewAudio.play();
  const stopAt = endSec + 0.08;
  const checkInterval = setInterval(() => {
    if (!activePreviewAudio || activePreviewAudio.paused || activePreviewAudio.currentTime >= stopAt) {
      if (activePreviewAudio && !activePreviewAudio.paused) activePreviewAudio.pause();
      clearInterval(checkInterval);
    }
  }, 60);
}

async function applyTranscriptLineToPiece(ti, pi, startSec, endSec, textStr) {
  closeModal();
  const cut = collectCutFromDOM();
  if (!cut.turns[ti] || !cut.turns[ti].pieces[pi]) return;
  cut.turns[ti].pieces[pi].start = Number(startSec);
  cut.turns[ti].pieces[pi].end = Number(endSec);
  cut.turns[ti].pieces[pi].text = textStr;
  currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/cut`, {
    cut,
    regenerate_previews: true,
  });
  renderCutEditor(currentProject);
  const updatedP = currentProject.cut?.turns?.[ti]?.pieces?.[pi];
  if (updatedP && updatedP.preview_wav) {
    playPreviewAudio(updatedP.preview_wav);
  }
}

async function restoreDroppedPiece(droppedIdx) {
  if (!currentProject || !currentProject.cut) return;
  const cut = collectCutFromDOM();
  const droppedList = cut.dropped || [];
  const d = droppedList[droppedIdx];
  if (!d) return;
  const targetWho = d.who || "B";
  // Find last turn with matching speaker or create one
  let targetTurn = cut.turns.find((t) => t.who === targetWho);
  if (!targetTurn) {
    targetTurn = { who: targetWho, pieces: [] };
    cut.turns.push(targetTurn);
  }
  targetTurn.pieces.push({
    start: Number(d.start),
    end: Number(d.end),
    text: (d.why || "Câu khôi phục").replace(/^Nói vấp\/lặp:\s*/i, ""),
    item: null,
  });
  targetTurn.pieces.sort((a, b) => a.start - b.start);
  droppedList.splice(droppedIdx, 1);
  cut.dropped = droppedList;
  currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/cut`, {
    cut,
    regenerate_previews: true,
  });
  renderCutEditor(currentProject);
}

async function runFineAnalyze() {
  if (!currentProjectId) return;
  const who = document.getElementById("fineWho").value;
  const t0 = parseFloat(document.getElementById("fineFrom").value) || 0;
  const t1 = parseFloat(document.getElementById("fineTo").value) || 15;
  const gap = parseFloat(document.getElementById("fineGap").value) || 0.06;
  const outPre = document.getElementById("fineAnalyzeOutput");
  outPre.style.display = "block";
  outPre.textContent = "Đang quét mịn bằng faster-whisper...";
  try {
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/fine-analyze`, {
      who,
      from: t0,
      to: t1,
      gap,
    });
    outPre.textContent = res.phien_am_text || "(Không có đoạn tiếng nào)";
  } catch (e) {
    outPre.textContent = "Lỗi: " + e.message;
  }
}

// ------------------------------------------------------------------------
// TAB 2: LISTENER CANDIDATES & STOP GATE 2
// ------------------------------------------------------------------------
function renderIdleEditor(proj) {
  const idle = proj.idle || { A: [], B: [] };
  const cands = proj.idle_candidates || { A: [], B: [], aux: [] };
  const cut = proj.cut || { turns: [] };
  const overrides = proj.turn_listener_overrides || {};

  // 1. Render Per-Turn Listener Override Table
  const tbody = document.getElementById("turnListenerOverrideBody");
  tbody.innerHTML = (cut.turns || [])
    .map((t, idx) => {
      const turnNum = idx + 1;
      const speaker = t.who;
      const listener = speaker === "A" ? "B" : "A";
      const ov = overrides[String(turnNum)] || {};
      const isCustom = Boolean(ov && (ov.start !== undefined || ov.segments));
      const srcVal = ov.source_clip || (ov.segments && ov.segments[0] && ov.segments[0].source_clip) || "";
      const startVal = ov.start ?? (ov.segments && ov.segments[0] ? ov.segments[0].start : "");
      const endVal = ov.end ?? (ov.segments && ov.segments[ov.segments.length - 1] ? ov.segments[ov.segments.length - 1].end : "");
      const reasonVal = ov.reason || (isCustom ? "Gán riêng theo lượt" : "Tự động phân bổ từ idle.json");

      return `
        <tr data-turn-num="${turnNum}" data-listener="${listener}">
          <td><strong>Lượt ${turnNum}</strong></td>
          <td><span class="badge info">Người ${speaker} NÓI (Clip gốc)</span></td>
          <td><strong>Người ${listener} NGHE</strong></td>
          <td>
            <select class="ov-mode" onchange="onToggleOverrideMode(this)">
              <option value="auto" ${!isCustom ? "selected" : ""}>Tự động từ idle.json</option>
              <option value="custom" ${isCustom ? "selected" : ""}>Gán mốc / Clip phụ riêng</option>
            </select>
          </td>
          <td>
            <input type="text" class="ov-src" value="${escapeHtml(srcVal)}" placeholder="Mặc định hoặc H:\\source\\IMG_0138.mov" ${!isCustom ? "disabled" : ""} />
          </td>
          <td><input type="number" step="0.01" class="ov-start" value="${startVal}" style="width:85px;" ${!isCustom ? "disabled" : ""} /></td>
          <td><input type="number" step="0.01" class="ov-end" value="${endVal}" style="width:85px;" ${!isCustom ? "disabled" : ""} /></td>
          <td><input type="text" class="ov-reason" value="${escapeHtml(reasonVal)}" /></td>
        </tr>
      `;
    })
    .join("");

  // 2. Render Candidate Contact Sheets for A and B (+ aux)
  renderCandidateColumn("candidatesAContainer", "A", cands.A || [], idle.A || [], proj.id);
  renderCandidateColumn(
    "candidatesBContainer",
    "B",
    [...(cands.B || []), ...(cands.aux || [])],
    idle.B || [],
    proj.id
  );
}

function onToggleOverrideMode(sel) {
  const tr = sel.closest("tr");
  const dis = sel.value !== "custom";
  tr.querySelector(".ov-src").disabled = dis;
  tr.querySelector(".ov-start").disabled = dis;
  tr.querySelector(".ov-end").disabled = dis;
}

function renderCandidateColumn(containerId, who, candList, approvedList, projId) {
  const box = document.getElementById(containerId);
  let html = `
    <div style="background:#111827; padding:10px; border-radius:8px; border:1px solid var(--border); margin-bottom:8px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <strong>Khoảng GOOD đang dùng trong idle.json (${who}):</strong>
        <button class="sm" onclick="addIdleRangeRow('${who}')">＋ Thêm khoảng</button>
      </div>
      <div id="idleRows_${who}">
        ${approvedList
          .map(
            (r) => `
          <div class="idle-range-row" style="display:flex; gap:6px; margin-bottom:6px;">
            <input type="number" step="0.01" class="ir-start" value="${r[0]}" style="width:85px;" />
            <input type="number" step="0.01" class="ir-end" value="${r[1]}" style="width:85px;" />
            <input type="text" class="ir-reason" value="${escapeHtml(r[2] || "GOOD")}" />
            <button class="sm danger" onclick="this.parentElement.remove()">✕</button>
          </div>
        `
          )
          .join("")}
      </div>
    </div>
  `;

  if (!candList.length) {
    html += `<div class="step-msg">Chưa có contact sheet ứng viên (bấm Chạy Bước 4 để trích khung 2fps).</div>`;
  } else {
    for (const c of candList) {
      const isGood = c.verdict === "GOOD";
      const sheetUrl = `/api/projects/${encodeURIComponent(projId)}/file?path=${encodeURIComponent(c.sheet_path)}&t=${Date.now()}`;
      html += `
        <div class="cand-card ${isGood ? "good" : "bad"}">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong>${escapeHtml(c.id)} (${c.start}s – ${c.end}s, dài ${c.duration}s)</strong>
            <span class="badge ${isGood ? "success" : "warning"}">${escapeHtml(c.verdict)}</span>
          </div>
          <img src="${sheetUrl}" alt="${escapeHtml(c.id)}" onclick="openImageModal('${escapeHtml(c.id)} (${c.start}s-${c.end}s)', '${sheetUrl}')" />
          <div class="step-msg">${escapeHtml(c.reason || "")} (Độ biến thiên: ${c.avg_motion})</div>
          <div style="display:flex; gap:6px;">
            <button class="sm success" onclick="useCandidateInIdle('${who}', ${c.start}, ${c.end}, '${escapeHtml(c.reason || "GOOD")}')">
              ＋ Đưa vào idle.json (${who})
            </button>
          </div>
        </div>
      `;
    }
  }
  box.innerHTML = html;
}

function addIdleRangeRow(who, s = 10.0, e = 15.0, reason = "Miệng khép, mắt nhìn người nói") {
  const wrap = document.getElementById(`idleRows_${who}`);
  const div = document.createElement("div");
  div.className = "idle-range-row";
  div.style.cssText = "display:flex; gap:6px; margin-bottom:6px;";
  div.innerHTML = `
    <input type="number" step="0.01" class="ir-start" value="${s}" style="width:85px;" />
    <input type="number" step="0.01" class="ir-end" value="${e}" style="width:85px;" />
    <input type="text" class="ir-reason" value="${escapeHtml(reason)}" />
    <button class="sm danger" onclick="this.parentElement.remove()">✕</button>
  `;
  wrap.appendChild(div);
}

function useCandidateInIdle(who, s, e, reason) {
  addIdleRangeRow(who, s, e, reason);
}

function collectIdleAndOverrides() {
  const collectWho = (who) =>
    Array.from(document.querySelectorAll(`#idleRows_${who} .idle-range-row`)).map((r) => [
      parseFloat(r.querySelector(".ir-start").value) || 0,
      parseFloat(r.querySelector(".ir-end").value) || 0,
      r.querySelector(".ir-reason").value.trim(),
    ]);

  const existingOverrides = (currentProject && currentProject.turn_listener_overrides) || {};
  const newOverrides = {};
  document.querySelectorAll("#turnListenerOverrideBody tr").forEach((tr) => {
    const turnNum = tr.getAttribute("data-turn-num");
    const listener = tr.getAttribute("data-listener");
    const mode = tr.querySelector(".ov-mode").value;
    if (mode === "custom") {
      const prev = existingOverrides[turnNum];
      const s = parseFloat(tr.querySelector(".ov-start").value);
      const e = parseFloat(tr.querySelector(".ov-end").value);
      const src = tr.querySelector(".ov-src").value.trim();
      const reason = tr.querySelector(".ov-reason").value.trim();
      // Preserve multi-segment override if unmodified
      if (prev && prev.segments && (!src || src === (prev.segments[0] && prev.segments[0].source_clip))) {
        newOverrides[turnNum] = { ...prev, reason };
      } else if (!isNaN(s) && !isNaN(e) && e > s) {
        newOverrides[turnNum] = {
          who: listener,
          source_clip: src,
          start: s,
          end: e,
          reason,
        };
      }
    }
  });

  return {
    idle: { A: collectWho("A"), B: collectWho("B") },
    turn_listener_overrides: newOverrides,
  };
}

async function saveIdleChoicesOnly() {
  if (!currentProjectId) return;
  const payload = collectIdleAndOverrides();
  currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/idle`, payload);
  renderIdleEditor(currentProject);
  alert("Đã lưu idle.json và bảng phân bổ cảnh nghe!");
}

// ------------------------------------------------------------------------
// TAB 3: PRINCIPLE #1 CHECK, PRODUCT CARDS, STILLS & STOP GATE 3
// ------------------------------------------------------------------------
function renderPrinciple1Table(proj) {
  const wrap = document.getElementById("principle1TableWrap");
  const p1 = proj.principle1_check;
  if (!p1 || !p1.rows) {
    wrap.innerHTML = `<div class="step-msg">Chưa chạy Bước 5 (Dựng Timeline).</div>`;
    return;
  }
  wrap.innerHTML = `
    <div style="margin-bottom:8px;">
      Kết luận Nguyên tắc số 1:
      <span class="badge ${p1.passed ? "success" : "danger"}">
        ${p1.passed ? "✅ ĐẠT 100% — Mọi lượt nói đều dùng clip gốc có miệng cử động" : "❌ VI PHẠM — Có lượt nói dùng clip idle!"}
      </span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Lượt</th>
          <th>Người NÓI</th>
          <th>Frame</th>
          <th>Thời lượng</th>
          <th>Clip người NÓI</th>
          <th>Loại track nói</th>
          <th>Clip người NGHE</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>
        ${p1.rows
          .map(
            (r) => `
          <tr>
            <td>Lượt ${r.turn}</td>
            <td><strong>Người ${r.speaker}</strong></td>
            <td>${r.from_frame} – ${r.to_frame}</td>
            <td>${r.duration_sec}s</td>
            <td><code>${escapeHtml((r.speaker_clips || []).join(", "))}</code></td>
            <td><span class="badge success">${escapeHtml((r.speaker_kinds || []).join(", "))}</span></td>
            <td><code>${escapeHtml((r.listener_clips || []).join(", "))}</code></td>
            <td><span class="badge ${r.verdict === "PASS" ? "success" : "danger"}">${r.verdict}</span></td>
          </tr>
        `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderStillsSection(proj) {
  const box = document.getElementById("stillsGridContainer");
  const stills = proj.stills || [];
  if (!stills.length) {
    box.innerHTML = `<div class="step-msg" style="grid-column: 1 / -1;">Chưa có ảnh mẫu (bấm "📸 Chụp lại 3 ảnh mẫu (Bước 7)" để tạo).</div>`;
    return;
  }
  box.innerHTML = stills
    .map((s) => {
      const url = `/api/projects/${encodeURIComponent(proj.id)}/file?path=${encodeURIComponent(s.file)}&t=${Date.now()}`;
      return `
        <div class="cand-card still-card">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong>${escapeHtml(s.label)}</strong>
            <span class="badge info">Frame ${s.frame} (${s.time_sec}s)</span>
          </div>
          <img src="${url}" alt="${escapeHtml(s.label)}" onclick="openImageModal('${escapeHtml(s.label)} (1080×1080)', '${url}')" />
          <div class="step-msg">Bấm vào ảnh để phóng to 100% kiểm dấu tiếng Việt</div>
        </div>
      `;
    })
    .join("");
}

function renderProductCards(proj) {
  const box = document.getElementById("productCardsContainer");
  const prep = (proj.products_prepared && proj.products_prepared.items) || [];
  if (!prep.length) {
    box.innerHTML = `<div class="step-msg">Chưa chạy Bước 6 (Ảnh sản phẩm).</div>`;
    return;
  }
  const bangItems = (proj.bang && proj.bang.items) || [];
  const maskPrice = !(proj.settings && proj.settings.maskPrice === false);
  const priceSuffix = (proj.settings && proj.settings.priceSuffix !== undefined) ? proj.settings.priceSuffix : " K";
  box.innerHTML = prep
    .map((it) => {
      const imgUrl = it.image_file
        ? `/api/projects/${encodeURIComponent(proj.id)}/file?path=${encodeURIComponent("anh/products/" + it.image_file)}&t=${Date.now()}`
        : "";
      const priceDisp = formatVNPriceJS(it.gia, maskPrice, priceSuffix);
      const bItem = bangItems.find((b) => Number(b.i) === Number(it.i));
      const curScale = Number((bItem && bItem.image_scale) || it.image_scale || 1.0);
      const curPct = Math.round(curScale * 100);
      const previewScale = Math.max(0.45, Math.min(1.45, curScale));
      return `
        <div class="product-card" id="prodCard_${it.i}"
             ondragover="event.preventDefault(); this.style.borderColor='#38bdf8';"
             ondragleave="this.style.borderColor='';"
             ondrop="onDropProductCardImage(event, ${it.i})">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <strong>#${String(it.i).padStart(2, "0")} ${escapeHtml(it.display_name || it.ten)}</strong>
            <span class="badge ${it.alpha_ok ? "success" : "warning"}">${it.alpha_ok ? "Nền trong" : "Kiểm nền"}</span>
          </div>
          <div class="checkerboard" style="overflow:hidden;">
            ${imgUrl ? `<img id="prodImg_${it.i}" src="${imgUrl}" onclick="openImageModal('#${it.i} ${escapeHtml(it.display_name)}', '${imgUrl}')" style="cursor:zoom-in; transform:scale(${previewScale}); transition:transform 0.15s ease;" />` : `<span class="badge danger">Thiếu ảnh</span>`}
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; font-size:12.5px;">
            <span>SL: <strong>${it.sl} ${escapeHtml(it.dv)}</strong></span>
            <span style="color:#f87171; font-weight:700; font-size:14px;">${priceDisp}</span>
          </div>
          <div style="margin-top:6px; padding-top:6px; border-top:1px solid rgba(255,255,255,0.08);">
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:11.5px; color:#cbd5e1; margin-bottom:4px;">
              <span>📏 Cỡ ảnh món #${it.i}:</span>
              <div style="display:flex; gap:3px; align-items:center;">
                <button class="sm" style="padding:2px 6px;" onclick="nudgeItemImageScale(${it.i}, -10)" title="Thu nhỏ 10%">−</button>
                <input type="number" id="prodScaleInput_${it.i}" min="40" max="200" step="5" value="${curPct}" style="width:58px; padding:2px 4px; text-align:center; font-weight:700; color:#38bdf8;" oninput="onItemScaleInputChange(${it.i}, this.value)" />
                <span style="font-size:11px;">%</span>
                <button class="sm" style="padding:2px 6px;" onclick="nudgeItemImageScale(${it.i}, 10)" title="Phóng to 10%">＋</button>
                <button class="sm" style="padding:2px 5px; font-size:10.5px;" onclick="onItemScaleInputChange(${it.i}, 100)" title="Về 100%">100%</button>
              </div>
            </div>
            <div style="display:flex; gap:4px; margin-top:4px; flex-wrap:wrap;">
              <button class="sm" id="btnPickProd_${it.i}" style="flex:1; justify-content:center;" onclick="pickCustomProductImage(${it.i})" title="Chọn ảnh từ máy tính">📂 Chọn file</button>
              <button class="sm success" style="flex:1; justify-content:center;" onclick="openDoctorImageEditorModal(${it.i})" title="Tải ảnh & Cắt/Tách nền lấy mỗi hình Bác Sĩ">✂️ Lấy hình BS</button>
              <button class="sm primary" id="btnWebCycle_${it.i}" style="flex:1; justify-content:center;" onclick="cycleWebImageForItem(${it.i})" title="Tự tìm & đổi sang hình ảnh khác trên Web">🔄 Ảnh Web</button>
              <button class="sm" style="padding:4px 7px;" onclick="promptSearchWebImageForItem(${it.i}, '${escapeJsStr(it.display_name || it.ten)}')" title="Nhập từ khóa tìm ảnh Web cho mục này">🔍</button>
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

function syncProdImgSizeInputs(val) {
  const px = Math.max(160, Math.min(680, Number(val) || 400));
  const rEl = document.getElementById("adjProdImgSizeRange");
  const nEl = document.getElementById("adjProdImgSize");
  const bEl = document.getElementById("adjProdImgPctBadge");
  if (rEl && Number(rEl.value) !== px) rEl.value = px;
  if (nEl && Number(nEl.value) !== px) nEl.value = px;
  if (bEl) bEl.textContent = `${Math.round((px / 400) * 100)}% (${px}px)`;
}

async function setQuickProductImageSize(px) {
  syncProdImgSizeInputs(px);
  await saveVisualAdjustmentsAndRestill();
}

function onItemScaleInputChange(itemIdx, pctVal) {
  const pct = Math.max(40, Math.min(200, Number(pctVal) || 100));
  const inp = document.getElementById(`prodScaleInput_${itemIdx}`);
  if (inp && Number(inp.value) !== pct) inp.value = pct;
  const img = document.getElementById(`prodImg_${itemIdx}`);
  if (img) {
    const sc = Math.max(0.45, Math.min(1.45, pct / 100.0));
    img.style.transform = `scale(${sc})`;
  }
}

function nudgeItemImageScale(itemIdx, deltaPct) {
  const inp = document.getElementById(`prodScaleInput_${itemIdx}`);
  const cur = inp ? Number(inp.value) || 100 : 100;
  onItemScaleInputChange(itemIdx, cur + deltaPct);
}

async function saveAllItemScalesAndRestill() {
  if (!currentProjectId) return;
  await saveProjectSettings();
  await rerunStep7Stills();
}

function formatVNPriceJS(num, mask, suffix = " K") {
  const n = Number(num) || 0;
  if (mask) {
    if (n < 10) return `${n}${suffix}`;
    if (n >= 1000) {
      const s = String(n);
      return `${s.slice(0, -3)}.${s.slice(-3, -1)}x${suffix}`;
    }
    return `${String(n).slice(0, -1)}x${suffix}`;
  }
  return n >= 1000 ? `${n.toLocaleString("vi-VN")}${suffix}` : `${n}${suffix}`;
}

async function pickCustomProductImage(itemIndex) {
  if (!currentProjectId) return;
  const btn = document.getElementById(`btnPickProd_${itemIndex}`);
  try {
    const res = await apiPost("/api/system/pick-file", {
      title: `Chọn ảnh sản phẩm cho món #${itemIndex}`,
      filter: "Ảnh sản phẩm (*.png;*.webp;*.jpg;*.jpeg)|*.png;*.webp;*.jpg;*.jpeg|Tất cả file (*.*)|*.*",
      initial_dir: "H:\\source\\san pham",
    });
    if (!res.path) return;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ Đang nạp ảnh...";
    }
    const bang = collectBangFromTable();
    // Preserve any existing custom_image_path from currentProject.bang
    const origItems = (currentProject && currentProject.bang && currentProject.bang.items) || [];
    for (const rowIt of bang.items || []) {
      if (!rowIt.custom_image_path) {
        const matchOrig = origItems.find((o) => Number(o.i) === Number(rowIt.i));
        if (matchOrig && matchOrig.custom_image_path) {
          rowIt.custom_image_path = matchOrig.custom_image_path;
        }
      }
    }
    const item = (bang.items || []).find((x) => Number(x.i) === Number(itemIndex));
    if (item) {
      item.custom_image_path = res.path;
      currentProject = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/bang`, {
        bang,
        run_step6: true,
      });
      populateWorkspace(currentProject);
    }
  } catch (e) {
    alert("Lỗi đổi ảnh sản phẩm: " + e.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = `📂 Đổi ảnh SP #${itemIndex}`;
    }
  }
}

async function onDropProductCardImage(event, itemIndex) {
  event.preventDefault();
  const card = document.getElementById(`prodCard_${itemIndex}`);
  if (card) card.style.borderColor = "";
  if (!currentProjectId) return;
  const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
  if (!file) return;
  const btn = document.getElementById(`btnPickProd_${itemIndex}`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Đang nạp ảnh...";
  }
  try {
    const resp = await fetch(
      `/api/projects/${encodeURIComponent(currentProjectId)}/upload?filename=${encodeURIComponent(file.name)}&role=product&item_index=${itemIndex}`,
      { method: "POST", body: file }
    );
    const data = await resp.json();
    if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
    if (data.project) {
      currentProject = data.project;
      populateWorkspace(currentProject);
    }
  } catch (e) {
    alert("Lỗi kéo thả ảnh sản phẩm: " + e.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = `📂 Đổi ảnh SP #${itemIndex}`;
    }
  }
}

function openProductContactSheet() {
  if (!currentProjectId) return;
  const url = `/api/projects/${encodeURIComponent(currentProjectId)}/file?path=anh/products/_contact.png&t=${Date.now()}`;
  openImageModal("Contact Sheet 14 Sản Phẩm Trên 2 Nền Sáng/Tối (_contact.png)", url);
}

async function saveVisualAdjustmentsAndRestill() {
  await saveProjectSettings();
  await rerunStep7Stills();
}

async function rerunStep7Stills() {
  await runSingleStep(7, true);
}

// ------------------------------------------------------------------------
// TAB 4: RENDER PROGRESS, QA CHECKS & EXPORT
// ------------------------------------------------------------------------
function renderRenderProgress(proj) {
  const prog = (proj && proj.render_progress) || { percent: 0, phase: "Sẵn sàng" };
  const pct = prog.percent || 0;
  document.getElementById("renderPhaseLabel").textContent = prog.phase || "Sẵn sàng";
  document.getElementById("renderPercentLabel").textContent = `${pct}%`;
  const fill = document.getElementById("renderProgressFill");
  fill.style.width = `${pct}%`;
  fill.textContent = `${pct}%`;
}

function renderExportsAndChecks(proj) {
  renderCapCutDraftCard(proj);
  renderFinalRevisionBox(proj);
  const exp = proj.exports || {};
  const expBox = document.getElementById("exportVideosBox");
  if (!exp.full_path) {
    expBox.innerHTML = `<div class="step-msg">Chưa có video xuất (cần duyệt DỪNG 3 hoặc bấm "🎬 Render Video MP4 (Bước 8)").</div>`;
  } else {
    const fullUrl = `/api/projects/${encodeURIComponent(proj.id)}/file?path=${encodeURIComponent(exp.local_full_rel || exp.full_path)}&t=${Date.now()}`;
    expBox.innerHTML = `
      <div class="turn-box" style="max-width:760px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:8px;">
          <strong>🎬 Video Thành Phẩm Hoàn Chỉnh (CRF 18 + Chuẩn âm -14 LUFS)</strong>
          <span class="badge success">${exp.full_size_mb} MB | ${exp.lufs} LUFS | TP ${exp.tp_db} dBTP</span>
        </div>
        <video src="${fullUrl}" controls style="width:100%; max-height:480px; border-radius:8px; background:#000;"></video>
        <div class="step-msg" style="margin-top:6px;">
          Đường dẫn bản duy nhất: <code>${escapeHtml(exp.full_path)}</code> (${exp.width}×${exp.height}, ${exp.fps}fps, ${exp.nb_frames} frame, ${exp.duration_sec}s)
        </div>
        <div style="display:flex; gap:8px; margin-top:10px; flex-wrap:wrap;">
          <button class="sm primary" onclick="openPathInExplorer('${escapeJsStr(exp.full_path)}')">📂 Mở vị trí file trên máy</button>
          <button class="sm danger" onclick="cleanupOldRenderedVideos(false)" title="Xóa vĩnh viễn các video _v1, _v2 cũ và bản nén _nen.mp4 khỏi ổ cứng, chỉ giữ lại đúng 1 bản hoàn chỉnh mới nhất này">
            🗑️ Xóa các video cũ (Chỉ giữ lại 1 bản hoàn chỉnh này)
          </button>
          <button class="sm" onclick="cleanupOldRenderedVideos(true)" title="Dọn sạch toàn bộ video render cũ của mọi dự án trong H:\\source và thư mục dự án">
            🧹 Dọn video cũ của mọi dự án
          </button>
        </div>
      </div>
    `;
  }

  // Render checks table & markdown
  const checksData = proj.checks_data;
  const checksTableBox = document.getElementById("checksTableContainer");
  if (!checksData || !checksData.rows) {
    checksTableBox.innerHTML = `<div class="step-msg">Chưa chạy Bước 9 (Tự kiểm).</div>`;
  } else {
    checksTableBox.innerHTML = `
      <table>
        <thead>
          <tr>
            <th style="width:170px;">Phân loại kiểm</th>
            <th style="width:240px;">Hạng mục</th>
            <th style="width:120px;">Verdict</th>
            <th>Bằng chứng / Số đo</th>
          </tr>
        </thead>
        <tbody>
          ${checksData.rows
            .map((r) => {
              const cls =
                r.verdict === "PASS"
                  ? "success"
                  : r.verdict === "FAIL"
                  ? "danger"
                  : "warning";
              return `
                <tr>
                  <td><strong>${escapeHtml(r.category)}</strong></td>
                  <td>${escapeHtml(r.item)}</td>
                  <td><span class="badge ${cls}">${escapeHtml(r.verdict)}</span></td>
                  <td>${escapeHtml(r.evidence)}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    `;
  }
  document.getElementById("checksMdViewer").textContent = proj.checks_md || "(Chưa có checks.md)";
}

async function cleanupOldRenderedVideos(cleanAllProjects = false) {
  if (!currentProjectId) return;
  const msg = cleanAllProjects
    ? "Xóa vĩnh viễn toàn bộ các video render cũ (_v1, _v2..., _nen.mp4) của TẤT CẢ dự án khỏi máy tính, chỉ giữ lại 1 bản hoàn chỉnh mới nhất cho mỗi dự án?"
    : "Xóa vĩnh viễn toàn bộ các video render cũ và bản nén của dự án này khỏi máy tính, chỉ giữ lại đúng 1 bản hoàn chỉnh mới nhất?";
  if (!confirm(msg)) return;
  try {
    const res = await apiPost(
      `/api/projects/${encodeURIComponent(currentProjectId)}/cleanup-old-renders`,
      { all_projects: Boolean(cleanAllProjects) }
    );
    currentProject = await apiGet(`/api/projects/${encodeURIComponent(currentProjectId)}`);
    populateWorkspace(currentProject);
    const count = res.deleted_count || 0;
    const mb = res.freed_mb || 0;
    const kept = res.kept_export_file || "(Bản hoàn chỉnh mới nhất)";
    if (count > 0) {
      alert(
        `🗑️ Đã xóa vĩnh viễn ${count} file video cũ khỏi máy tính (Giải phóng ${mb} MB)!\n\n` +
          `✅ Bản hoàn chỉnh duy nhất được giữ lại:\n${kept}`
      );
    } else {
      alert(
        `✅ Máy tính đã gọn sạch! Hiện chỉ có duy nhất 1 bản hoàn chỉnh:\n${kept}`
      );
    }
  } catch (e) {
    alert("Lỗi xóa video cũ: " + e.message);
  }
}

function openQaSheet(which) {
  if (!currentProjectId) return;
  const rel = which === "sheet_1fps_full" ? "final/sheet_1fps_full.jpg" : "final/sheet_2fps_listeners.jpg";
  const url = `/api/projects/${encodeURIComponent(currentProjectId)}/file?path=${encodeURIComponent(rel)}&t=${Date.now()}`;
  openImageModal(`Contact Sheet Nghiệm Thu (${rel})`, url);
}

function renderCapCutDraftCard(proj) {
  const box = document.getElementById("capcutDraftBox");
  if (!box) return;
  const ccInfo = proj && proj.capcut_draft;
  if (!ccInfo || !ccInfo.capcut_draft_path) {
    box.innerHTML = "";
    return;
  }
  const ts = ccInfo.tracks_summary || {};
  box.innerHTML = `
    <div class="turn-box" style="border-color:#27272a; background:#0d0f14;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:4px;">
        <div>
          <strong style="color:#e4e4e7; font-size:13.5px;">✂️ Bản nháp CapCut (Chỉ cập nhật khi bấm nút): <code>${escapeHtml(ccInfo.draft_name)}</code></strong>
        </div>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          <button class="sm" onclick="syncFromCapCutDraft()">🔄 Lấy từ CapCut về App</button>
          <button class="sm" onclick="exportToCapCutDraft(false)">✂️ Cập nhật lại CapCut</button>
          <button class="sm" onclick="openCapCutApp()">🚀 Mở CapCut</button>
          <button class="sm" onclick="openPathInExplorer('${escapeJsStr(ccInfo.capcut_draft_path)}')">📂 Thư mục Draft</button>
        </div>
      </div>
      <div class="step-msg">
        Đường dẫn: <code>${escapeHtml(ccInfo.capcut_draft_path)}</code> | Cập nhật lúc: ${escapeHtml(ccInfo.created_at || "")}
      </div>
    </div>
  `;
}

function renderFinalRevisionBox(proj) {
  const input = document.getElementById("finalRevisionNotesInput");
  if (input && proj && proj.final_revision_notes && !input.value.trim()) {
    input.value = proj.final_revision_notes;
  }
  const s7Input = document.getElementById("step7PromptInput");
  if (s7Input && proj && proj.final_revision_notes && !s7Input.value.trim()) {
    s7Input.value = proj.final_revision_notes;
  }
  const hist = (proj && proj.revision_history) || [];
  const s7Box = document.getElementById("step7RevisionStatusBox");
  if (s7Box && hist.length) {
    const latest = hist[0];
    s7Box.innerHTML = `
      <div style="background:rgba(15,23,42,0.75); border:1px solid var(--border); border-radius:6px; padding:6px 10px; font-size:12px;">
        <span class="badge info">${escapeHtml(latest.time || "")}</span>
        <span style="color:#e2e8f0; margin-left:6px;"><em>"${escapeHtml(latest.notes || "")}"</em></span>
        <span style="color:#34d399; margin-left:8px;">→ ${escapeHtml((latest.changes || []).join(" | "))}</span>
      </div>
    `;
  }
  const histBox = document.getElementById("finalRevisionHistoryBox");
  if (!histBox) return;
  if (!hist.length) {
    histBox.innerHTML = "";
    return;
  }
  histBox.innerHTML = `
    <div style="background:#0c0e14; border:1px solid var(--border); border-radius:6px; padding:8px 12px; font-size:12.5px;">
      <strong style="color:#93c5fd;">🕘 Lịch sử chỉnh sửa gần nhất:</strong>
      <div style="margin-top:6px; display:flex; flex-direction:column; gap:6px; max-height:140px; overflow-y:auto;">
        ${hist
          .slice(0, 5)
          .map(
            (h) => `
          <div style="border-bottom:1px dashed rgba(255,255,255,0.08); padding-bottom:4px;">
            <span class="badge info">${escapeHtml(h.time || "")}</span>
            <span style="color:#e2e8f0; margin-left:6px;"><em>"${escapeHtml(h.notes || "")}"</em></span>
            <div style="color:#34d399; margin-top:2px;">→ ${escapeHtml((h.changes || []).join(" | "))}</div>
          </div>
        `
          )
          .join("")}
      </div>
    </div>
  `;
}

function insertRevisionSnippet(snippet) {
  const input = document.getElementById("finalRevisionNotesInput");
  if (!input) return;
  const cur = input.value.trim();
  input.value = cur ? `${cur}\n${snippet}` : snippet;
  input.focus();
}

function insertStep7PromptSnippet(snippet) {
  const input = document.getElementById("step7PromptInput");
  if (!input) return;
  const cur = input.value.trim();
  input.value = cur ? `${cur}; ${snippet}` : snippet;
  input.focus();
}

async function applyStep7Prompt(startFullRender = false) {
  if (!currentProjectId) return;
  const input = document.getElementById("step7PromptInput");
  const notes = input ? input.value.trim() : "";
  if (!notes) {
    alert("Sếp hãy nhập nội dung muốn sửa vào ô Prompt trước nhé!");
    if (input) input.focus();
    return;
  }
  const useAi = Boolean(document.getElementById("chkUseAiStep7Prompt")?.checked);
  const btn = document.getElementById("btnApplyStep7Prompt");
  const statusBox = document.getElementById("step7RevisionStatusBox");
  const origBtnHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "⏳ Đang áp dụng sửa &amp; chụp lại 3 ảnh mẫu...";
  }
  if (statusBox) {
    statusBox.innerHTML = `<div style="color:#38bdf8; font-size:12.5px;">⏳ Đang cập nhật nội dung &amp; chụp lại 3 ảnh mẫu 1080×1080 (khoảng 3–6 giây)...</div>`;
  }
  try {
    const res = await apiPost(
      `/api/projects/${encodeURIComponent(currentProjectId)}/apply-final-revision`,
      {
        notes,
        use_ai: useAi,
        restill_step7: !startFullRender,
        rerender_mp4: Boolean(startFullRender),
        export_capcut: false,
        open_capcut: false,
      }
    );
    if (res.project) {
      currentProject = res.project;
      if (startFullRender) {
        currentProject.pipeline_status = "running";
      }
      populateWorkspace(currentProject);
      renderSidebarSteps(currentProject);
      renderRenderProgress(currentProject);
    }
    const changes = (res.revision && res.revision.changes) || [];
    if (statusBox && changes.length) {
      statusBox.innerHTML = `
        <div style="background:rgba(16,185,129,0.12); border:1px solid #059669; border-radius:6px; padding:6px 10px; font-size:12.5px; color:#6ee7b7;">
          ✅ <strong>Đã sửa &amp; cập nhật 3 ảnh mẫu:</strong> ${escapeHtml(changes.join(" | "))}
        </div>
      `;
    }
    if (startFullRender) {
      switchTab("tab4");
      startPolling();
    }
  } catch (e) {
    if (statusBox) {
      statusBox.innerHTML = `<div style="color:#f87171; font-size:12.5px;">❌ Lỗi: ${escapeHtml(e.message)}</div>`;
    } else {
      alert("Lỗi áp dụng Prompt Bước 7: " + e.message);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origBtnHtml || "🪄 Áp dụng Prompt &amp; Chụp lại 3 ảnh mẫu";
    }
  }
}

async function applyFinalRevision(rerenderMp4 = false, openCapCut = false, exportCapCut = false) {
  if (!currentProjectId) return;
  const input = document.getElementById("finalRevisionNotesInput");
  const notes = input ? input.value.trim() : "";
  if (!notes) {
    alert("Sếp hãy nhập nội dung cần chỉnh sửa vào ô trước nhé!");
    if (input) input.focus();
    return;
  }
  const useAi = Boolean(document.getElementById("chkUseAiRevision")?.checked);
  const shouldRerenderMp4 = Boolean(rerenderMp4);

  try {
    const res = await apiPost(
      `/api/projects/${encodeURIComponent(currentProjectId)}/apply-final-revision`,
      {
        notes,
        use_ai: useAi,
        rerender_mp4: shouldRerenderMp4,
        export_capcut: Boolean(exportCapCut || openCapCut),
        open_capcut: Boolean(openCapCut),
      }
    );
    if (res.project) {
      currentProject = res.project;
      if (shouldRerenderMp4) {
        currentProject.pipeline_status = "running";
      }
      populateWorkspace(currentProject);
      renderSidebarSteps(currentProject);
      renderRenderProgress(currentProject);
    }
    if (shouldRerenderMp4) {
      startPolling();
    }
  } catch (e) {
    alert("Lỗi áp dụng chỉnh sửa bước cuối: " + e.message);
  }
}

async function syncFromCapCutDraft() {
  if (!currentProjectId) return;
  try {
    const res = await apiPost(
      `/api/projects/${encodeURIComponent(currentProjectId)}/sync-from-capcut`,
      {}
    );
    if (res.project) {
      currentProject = res.project;
      populateWorkspace(currentProject);
    }
    const sync = res.sync || {};
    const changes = sync.changes || [];
    if (changes.length > 0) {
      alert(
        `🔄 Đã lấy thành công ${changes.length} thay đổi từ bản nháp CapCut ('${sync.draft_name}') về lại App:\n\n` +
          changes.map((c) => `• ${c}`).join("\n") +
          `\n\n(Sếp có thể sửa tiếp trên App hoặc bấm Render MP4 bất cứ lúc nào!)`
      );
    } else {
      alert(
        `🔄 Đã đọc bản nháp CapCut ('${sync.draft_name}') về App thành công!\n` +
          `Hiện tại nội dung trong CapCut và trên App đang khớp nhau 100%.`
      );
    }
  } catch (e) {
    alert("Lỗi đồng bộ từ CapCut về App: " + e.message);
  }
}

// ------------------------------------------------------------------------
// PIPELINE EXECUTION & GATE APPROVALS
// ------------------------------------------------------------------------
async function saveAllCurrentEdits() {
  if (!currentProjectId || !currentProject) return;
  await saveProjectSettings();
  const turnBoxes = document.querySelectorAll("#cutTurnsContainer .turn-box");
  if (turnBoxes.length > 0) {
    const cut = collectCutFromDOM();
    await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/cut`, {
      cut,
      regenerate_previews: false,
    });
  }
  const ovRows = document.querySelectorAll("#turnListenerOverrideBody tr");
  if (ovRows.length > 0) {
    const payload = collectIdleAndOverrides();
    await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/idle`, payload);
  }
}

async function runSingleStep(stepNum, forceRecompute = false) {
  if (!currentProjectId) return;
  if (stepNum === 1) await saveProjectSettings();
  const stopGates = Boolean(document.getElementById("chkStopAtGates")?.checked);
  await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/run`, {
    start_step: stepNum,
    stop_at_gates: stopGates,
    single_step_only: true,
    force_recompute: forceRecompute,
  });
  currentProject.pipeline_status = "running";
  renderSidebarSteps(currentProject);
}

async function runNextStepOrApprove() {
  if (!currentProjectId || !currentProject) return;
  if (currentProject.waiting_gate) {
    await approveGate(currentProject.waiting_gate);
    return;
  }
  await saveAllCurrentEdits();
  let nextStep = 0;
  for (let i = 1; i <= 10; i++) {
    const st = currentProject.steps[String(i)];
    if (!st || st.status !== "done") {
      nextStep = i;
      break;
    }
  }
  const stopGates = Boolean(document.getElementById("chkStopAtGates")?.checked);
  if (nextStep > 0) {
    await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/run`, {
      start_step: nextStep,
      stop_at_gates: stopGates,
      single_step_only: true,
      force_recompute: true,
    });
  } else {
    // All steps were done -> re-run Render & QA & Export (Steps 8->10)
    await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/run`, {
      start_step: 8,
      stop_at_gates: false,
      single_step_only: false,
      force_recompute: true,
    });
    switchTab("tab4");
  }
  currentProject.pipeline_status = "running";
  renderSidebarSteps(currentProject);
}

async function runAutoNoGates() {
  if (!currentProjectId || !currentProject) return;
  await saveAllCurrentEdits();
  const stopGates = Boolean(document.getElementById("chkStopAtGates")?.checked);
  let start = 1;
  for (let i = 1; i <= 10; i++) {
    const st = currentProject.steps[String(i)];
    if (!st || st.status !== "done") {
      start = i;
      break;
    }
  }
  // If all steps are already done, re-run from Step 5 (Timeline -> Products -> Stills -> Render -> QA -> Export)
  if (
    start === 1 &&
    currentProject.steps["1"]?.status === "done" &&
    currentProject.steps["10"]?.status === "done"
  ) {
    start = 5;
  }
  await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/run`, {
    start_step: start,
    stop_at_gates: stopGates,
    single_step_only: false,
    force_recompute: false,
  });
  currentProject.pipeline_status = "running";
  currentProject.waiting_gate = null;
  renderGateBanner(currentProject);
  renderSidebarSteps(currentProject);
}

async function runFromCurrentStep() {
  await runAutoNoGates();
}

async function applyEditsAndRebuild() {
  if (!currentProjectId || !currentProject) return;
  const btn = document.getElementById("btnStickyApplyEdits");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Đang lưu...";
  }
  try {
    await saveAllCurrentEdits();
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/export-capcut`, {
      rebuild_timeline: true,
      skip_capcut: true,
      open_capcut: false,
    });
    if (res.project) {
      currentProject = res.project;
      populateWorkspace(currentProject);
    }
    if (btn) {
      btn.textContent = "✅ Đã lưu & cập nhật!";
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = "💾 Lưu sửa";
      }, 2000);
    }
  } catch (e) {
    alert("Lỗi cập nhật chỉnh sửa: " + e.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "💾 Lưu sửa";
    }
  }
}

async function exportToCapCutDraft(openCapCut = false) {
  if (!currentProjectId) return;
  const btn = document.getElementById("btnStickyCapCut");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Đang xuất CapCut...";
  }
  try {
    await saveAllCurrentEdits();
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/export-capcut`, {
      rebuild_timeline: false,
      skip_capcut: false,
      open_capcut: openCapCut,
    });
    if (res.project) {
      currentProject = res.project;
      populateWorkspace(currentProject);
    }
    const cc = res.capcut_draft || {};
    if (btn) {
      btn.textContent = `✅ Đã xuất: ${cc.draft_name || "CapCut"}`;
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = "✂️ Xuất CapCut (khi cần)";
      }, 2500);
    }
  } catch (e) {
    alert("Lỗi xuất CapCut Draft: " + e.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "✂️ Xuất CapCut (khi cần)";
    }
  }
}

async function openCapCutApp() {
  try {
    await apiPost("/api/system/open-capcut", {});
  } catch (e) {
    alert("Không mở được CapCut: " + e.message);
  }
}

async function approveGate(gate) {
  if (!currentProjectId) return;
  if (gate === "DUNG_1") {
    const cut = collectCutFromDOM();
    await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/cut`, {
      cut,
      regenerate_previews: false,
    });
  } else if (gate === "DUNG_2") {
    const payload = collectIdleAndOverrides();
    await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/idle`, payload);
  } else if (gate === "DUNG_3") {
    await saveProjectSettings();
  }

  await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/approve`, { gate });
  currentProject.pipeline_status = "running";
  currentProject.waiting_gate = null;
  renderGateBanner(currentProject);
  renderSidebarSteps(currentProject);
  if (gate === "DUNG_3") switchTab("tab4");
}

// ------------------------------------------------------------------------
// PROJECT CREATION & PRESETS
// ------------------------------------------------------------------------
async function loadQuickSourceVideos() {
  try {
    const res = await apiGet("/api/system/source-videos");
    const videos = res.videos || [];
    const ids = ["quickSelectClipA", "quickSelectClipB", "quickSelectClipAux"];
    for (const sid of ids) {
      const sel = document.getElementById(sid);
      if (!sel) continue;
      sel.innerHTML = `<option value="">⚡ Chọn nhanh video trong H:\\source (${videos.length} file)...</option>`;
      for (const v of videos) {
        const opt = document.createElement("option");
        opt.value = v.path;
        opt.textContent = `🎬 ${v.name} (${v.size_mb} MB)`;
        sel.appendChild(opt);
      }
    }
  } catch (e) {
    console.warn("Quick video list warning:", e);
  }
}

async function onQuickSelectVideo(inputId, badgeId, pathVal) {
  if (!pathVal) return;
  document.getElementById(inputId).value = pathVal;
  if (badgeId) {
    try {
      document.getElementById(badgeId).textContent = "Đang đọc ffprobe...";
      const res = await apiPost("/api/system/probe", { path: pathVal });
      if (res.probe) {
        const p = res.probe;
        document.getElementById(badgeId).innerHTML = `✅ <strong>${p.width}×${p.height}</strong> | ${p.avg_fps}fps | ${p.duration}s | ${p.is_vfr ? "⚠️ VFR (sẽ chuyển CFR)" : "CFR"}`;
      }
    } catch (e) {
      document.getElementById(badgeId).textContent = e.message;
    }
  }
}

function createNewBlankProject(defaultPreset = "giodo") {
  const isChiaSe = defaultPreset === "chiase";
  const isAnhNhac = defaultPreset === "anh_nhac";
  const defaultTitle = isAnhNhac
    ? "BỆNH VIỆN ĐI SINH"
    : isChiaSe
    ? "CHIA SẺ KINH NGHIỆM ĐI SINH"
    : "GIỎ ĐỒ ĐI SINH MỚI";
  document.getElementById("modalTitle").textContent = "✨ Tạo Dự Án Video Mới";
  document.getElementById("modalBody").innerHTML = `
    <div style="display:flex; flex-direction:column; gap:12px;">
      <div>
        <label>Tiêu đề hiển thị trên video (IN HOA):</label>
        <input type="text" id="newProjTitleInput" value="${defaultTitle}" placeholder="VD: BỆNH VIỆN ĐI SINH" onkeydown="if(event.key==='Enter') submitCreateNewProject()" />
      </div>
      <div>
        <label>Chọn Preset:</label>
        <select id="newProjPresetSelect">
          <option value="giodo" ${!isChiaSe && !isAnhNhac ? "selected" : ""}>Preset: Giỏ đồ</option>
          <option value="chiase" ${isChiaSe ? "selected" : ""}>Preset: Chia sẻ</option>
          <option value="anh_nhac" ${isAnhNhac ? "selected" : ""}>Preset: Ảnh + Nhạc (Không Voice — Tự tìm ảnh)</option>
        </select>
      </div>
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:6px;">
        <button onclick="closeModal()">Hủy</button>
        <button class="success" onclick="submitCreateNewProject()">✨ Tạo dự án mới</button>
      </div>
    </div>
  `;
  document.getElementById("modalBackdrop").classList.add("open");
  setTimeout(() => {
    const inp = document.getElementById("newProjTitleInput");
    if (inp) {
      inp.focus();
      inp.select();
    }
  }, 60);
}

async function submitCreateNewProject() {
  const inp = document.getElementById("newProjTitleInput");
  const sel = document.getElementById("newProjPresetSelect");
  const title = (inp ? inp.value.trim() : "") || "DỰ ÁN HỘI THOẠI MỚI";
  const preset = sel ? sel.value : "giodo";
  try {
    closeModal();
    const proj = await apiPost("/api/projects", {
      title: title.toUpperCase(),
      preset,
    });
    await refreshProjectsList(proj.id);
    switchTab("tab0");
  } catch (e) {
    alert("Lỗi tạo dự án: " + e.message);
  }
}

function openResetProjectModal() {
  if (!currentProjectId || !currentProject) {
    createNewBlankProject();
    return;
  }
  const pTitle = escapeHtml(currentProject.title || currentProjectId);
  document.getElementById("modalTitle").textContent = `🔄 Reset / Làm Mới Dự Án: ${currentProject.title || currentProjectId}`;
  document.getElementById("modalBody").innerHTML = `
    <p class="step-msg" style="margin-bottom:12px;">Sếp chọn cách Reset cho dự án <b>${pTitle}</b> (<code>${escapeHtml(currentProjectId)}</code>):</p>
    <div style="display:flex; flex-direction:column; gap:10px;">
      <div class="turn-box" style="border-color:#f59e0b; background:rgba(245, 158, 11, 0.08); display:flex; justify-content:space-between; align-items:center; gap:12px;">
        <div>
          <strong style="color:#fcd34d;">1. 🔄 Reset kết quả chạy (Giữ nguyên Video A/B &amp; Kịch bản)</strong>
          <div class="step-msg">Đưa tiến trình 10 bước về lại Bước 0 (chưa chạy) nhưng giữ nguyên đường dẫn 2 video nguồn, kịch bản và bảng sản phẩm để sếp sửa rồi bấm chạy lại từ đầu.</div>
        </div>
        <button class="warning" style="flex-shrink:0;" onclick="executeResetProject(true)">🔄 Reset bước chạy</button>
      </div>

      <div class="turn-box" style="border-color:#38bdf8; background:rgba(56, 189, 248, 0.08); display:flex; justify-content:space-between; align-items:center; gap:12px;">
        <div>
          <strong style="color:#7dd3fc;">2. 🧹 Xóa trắng toàn bộ dữ liệu dự án này (Làm lại từ con số 0)</strong>
          <div class="step-msg">Xóa sạch cả đường dẫn video nguồn, kịch bản, bảng sản phẩm và kết quả chạy của dự án hiện tại để nhập mới hoàn toàn.</div>
        </div>
        <button class="primary" style="flex-shrink:0;" onclick="executeResetProject(false)">🧹 Xóa trắng form</button>
      </div>

      <div class="turn-box" style="border-color:#ef4444; background:rgba(239, 68, 68, 0.08); display:flex; justify-content:space-between; align-items:center; gap:12px;">
        <div>
          <strong style="color:#fca5a5;">3. 🗑️ Xóa bỏ dự án này &amp; Tạo dự án mới tinh</strong>
          <div class="step-msg">Gỡ dự án này khỏi danh sách (lưu an toàn vào <code>projects/_trash</code>) và mở ngay màn hình Tạo dự án mới.</div>
        </div>
        <button class="danger" style="flex-shrink:0;" onclick="executeDeleteCurrentProject(true)">🗑️ Xóa &amp; Tạo mới</button>
      </div>
    </div>
    <div style="display:flex; justify-content:flex-end; margin-top:12px;">
      <button onclick="closeModal()">Đóng</button>
    </div>
  `;
  document.getElementById("modalBackdrop").classList.add("open");
}

async function executeResetProject(keepSources = true) {
  if (!currentProjectId) return;
  try {
    closeModal();
    const proj = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/reset`, {
      keep_sources: keepSources,
    });
    currentProject = proj;
    populateWorkspace(currentProject);
    await refreshProjectsList(currentProjectId);
    switchTab("tab0");
  } catch (e) {
    alert("Lỗi reset dự án: " + e.message);
  }
}

function deleteCurrentProjectModal() {
  if (!currentProjectId || !currentProject) {
    alert("Hiện chưa có dự án nào đang được chọn.");
    return;
  }
  const pTitle = escapeHtml(currentProject.title || currentProjectId);
  document.getElementById("modalTitle").textContent = "🗑️ Xóa Dự Án Hiện Tại";
  document.getElementById("modalBody").innerHTML = `
    <p style="font-size:14px; line-height:1.5;">
      Sếp có chắc muốn xóa dự án <b>${pTitle}</b> (<code>${escapeHtml(currentProjectId)}</code>) khỏi danh sách không?<br/>
      <span class="step-msg">(Dự án sẽ được chuyển vào thư mục lưu trữ tạm <code>projects/_trash</code> để đảm bảo an toàn, không làm mất file gốc của sếp).</span>
    </p>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:14px;">
      <button onclick="closeModal()">Hủy</button>
      <button class="danger" onclick="executeDeleteCurrentProject(false)">🗑️ Xóa khỏi danh sách</button>
      <button class="success" onclick="executeDeleteCurrentProject(true)">🗑️ Xóa &amp; Tạo dự án mới ngay</button>
    </div>
  `;
  document.getElementById("modalBackdrop").classList.add("open");
}

async function executeDeleteCurrentProject(createNewAfter = false) {
  if (!currentProjectId) return;
  const pidToDelete = currentProjectId;
  try {
    closeModal();
    const res = await apiPost(`/api/projects/${encodeURIComponent(pidToDelete)}/delete`, {});
    const remaining = res.projects || [];
    currentProjectId = "";
    currentProject = null;
    if (createNewAfter || remaining.length === 0) {
      await refreshProjectsList("");
      createNewBlankProject();
    } else {
      await refreshProjectsList(remaining[0].id);
      switchTab("tab0");
    }
  } catch (e) {
    alert("Lỗi xóa dự án: " + e.message);
  }
}

// ------------------------------------------------------------------------
// FILE PICKER, DRAG & DROP, MODALS
// ------------------------------------------------------------------------
async function pickLocalFile(inputId, title) {
  const res = await apiPost("/api/system/pick-file", {
    title,
    filter: "Video files (*.mov;*.mp4;*.mkv)|*.mov;*.mp4;*.mkv|Tất cả file (*.*)|*.*",
  });
  if (res.path) {
    document.getElementById(inputId).value = res.path;
    if (res.probe) {
      const badgeId = inputId === "inpClipA" ? "probeBadgeA" : inputId === "inpClipB" ? "probeBadgeB" : "";
      if (badgeId) {
        const p = res.probe;
        document.getElementById(badgeId).innerHTML = `✅ <strong>${p.width}×${p.height}</strong> | ${p.avg_fps}fps | ${p.duration}s | ${p.is_vfr ? "⚠️ VFR (sẽ chuyển CFR)" : "CFR"}`;
      }
    }
  }
}

function setupDragAndDrop() {
  const zones = [
    { id: "dropClipA", input: "inpClipA", role: "clip_a", badge: "probeBadgeA" },
    { id: "dropClipB", input: "inpClipB", role: "clip_b", badge: "probeBadgeB" },
    { id: "dropClipAux", input: "inpClipAux", role: "clip_aux", badge: "" },
  ];
  for (const z of zones) {
    const el = document.getElementById(z.id);
    if (!el) continue;
    el.addEventListener("dragover", (e) => {
      e.preventDefault();
      el.classList.add("dragover");
    });
    el.addEventListener("dragleave", () => el.classList.remove("dragover"));
    el.addEventListener("drop", async (e) => {
      e.preventDefault();
      el.classList.remove("dragover");
      if (!currentProjectId) {
        alert("Hãy tạo hoặc chọn dự án trước khi kéo thả file.");
        return;
      }
      const file = e.dataTransfer.files[0];
      if (!file) return;
      if (z.badge) document.getElementById(z.badge).textContent = `Đang nạp ${file.name}...`;
      const res = await fetch(
        `/api/projects/${encodeURIComponent(currentProjectId)}/upload?filename=${encodeURIComponent(file.name)}&role=${z.role}`,
        { method: "POST", body: file }
      );
      const data = await res.json();
      if (data.path) {
        document.getElementById(z.input).value = data.path;
        if (z.badge && data.probe) {
          const p = data.probe;
          document.getElementById(z.badge).innerHTML = `✅ <strong>${p.width}×${p.height}</strong> | ${p.avg_fps}fps | ${p.duration}s`;
        }
      }
    });
  }

  // Drag & Drop for Table Image OCR box (#dropTableImage)
  const tblZone = document.getElementById("dropTableImage");
  if (tblZone) {
    tblZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      tblZone.classList.add("dragover");
    });
    tblZone.addEventListener("dragleave", () => tblZone.classList.remove("dragover"));
    tblZone.addEventListener("drop", async (e) => {
      e.preventDefault();
      tblZone.classList.remove("dragover");
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith("image/")) {
        await uploadAndParseTableImageBlob(file);
      }
    });
  }

  // Global Ctrl+V paste handler for pasting table screenshot images directly on Tab 0
  window.addEventListener("paste", async (e) => {
    const items = (e.clipboardData && e.clipboardData.items) || [];
    for (const item of items) {
      if (item.type && item.type.startsWith("image/")) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (blob) {
          await uploadAndParseTableImageBlob(blob);
          return;
        }
      }
    }
  });
}

async function onSelectTableImageFile(inputEl) {
  const file = inputEl.files && inputEl.files[0];
  if (!file) return;
  await uploadAndParseTableImageBlob(file);
  inputEl.value = "";
}

async function uploadAndParseTableImageBlob(fileOrBlob) {
  if (!currentProjectId) {
    alert("Hãy tạo hoặc chọn dự án trước khi đọc bảng từ ảnh.");
    return;
  }
  const statusEl = document.getElementById("tableOcrStatus");
  const provider = document.getElementById("inpStep6Provider").value || "agy";
  if (statusEl) {
    statusEl.innerHTML = `<span style="color:#38bdf8;">⏳ Đang gửi ảnh bảng cho AI CLI (${provider}) đọc từng dòng... vui lòng chờ 10–25 giây...</span>`;
  }
  try {
    const res = await fetch(
      `/api/projects/${encodeURIComponent(currentProjectId)}/parse-table-image?provider=${encodeURIComponent(provider)}`,
      {
        method: "POST",
        headers: { "Content-Type": fileOrBlob.type || "image/jpeg" },
        body: fileOrBlob,
      }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    currentProject = data.project;
    populateWorkspace(currentProject);
    const count = (data.parsed && data.parsed.bang && data.parsed.bang.items && data.parsed.bang.items.length) || 0;
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#10b981;">✅ AI (${data.parsed.provider}) đã đọc xong <b>${count} món</b> (Tổng: <b>${data.parsed.bang.tong} K</b>) từ ảnh và tự điền vào bảng + kịch bản!</span>`;
    }
  } catch (e) {
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#ef4444;">❌ Lỗi đọc ảnh bảng: ${escapeHtml(e.message)}</span>`;
    }
    alert("Lỗi đọc ảnh bảng: " + e.message);
  }
}

async function pickTableImageViaDialog() {
  if (!currentProjectId) {
    alert("Hãy tạo hoặc chọn dự án trước.");
    return;
  }
  const pick = await apiPost("/api/system/pick-file", {
    title: "Chọn ảnh chụp Bảng sản phẩm / Kịch bản để AI đọc",
    filter: "Ảnh bảng (*.jpg;*.jpeg;*.png;*.webp)|*.jpg;*.jpeg;*.png;*.webp|Tất cả file (*.*)|*.*",
  });
  if (!pick.path) return;
  const statusEl = document.getElementById("tableOcrStatus");
  const provider = document.getElementById("inpStep6Provider").value || "agy";
  if (statusEl) {
    statusEl.innerHTML = `<span style="color:#38bdf8;">⏳ Đang đọc ảnh <code>${escapeHtml(pick.path)}</code> bằng AI CLI (${provider})...</span>`;
  }
  try {
    const data = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/parse-table-image`, {
      path: pick.path,
      provider,
    });
    currentProject = data.project;
    populateWorkspace(currentProject);
    const count = (data.parsed && data.parsed.bang && data.parsed.bang.items && data.parsed.bang.items.length) || 0;
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#10b981;">✅ AI (${data.parsed.provider}) đã đọc xong <b>${count} món</b> (Tổng: <b>${data.parsed.bang.tong} K</b>)!</span>`;
    }
  } catch (e) {
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#ef4444;">❌ Lỗi đọc ảnh bảng: ${escapeHtml(e.message)}</span>`;
    }
    alert("Lỗi đọc ảnh bảng: " + e.message);
  }
}

async function reparseCurrentTableImage() {
  if (!currentProjectId) return;
  const statusEl = document.getElementById("tableOcrStatus");
  const provider = document.getElementById("inpStep6Provider").value || "agy";
  if (statusEl) {
    statusEl.innerHTML = `<span style="color:#38bdf8;">⏳ Đang cho AI CLI (${provider}) đọc lại ảnh bảng...</span>`;
  }
  try {
    const data = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/parse-table-image`, {
      path: "",
      provider,
    });
    currentProject = data.project;
    populateWorkspace(currentProject);
    const count = (data.parsed && data.parsed.bang && data.parsed.bang.items && data.parsed.bang.items.length) || 0;
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#10b981;">✅ Đã đọc lại xong <b>${count} món</b> (Tổng: <b>${data.parsed.bang.tong} K</b>)!</span>`;
    }
  } catch (e) {
    alert("Lỗi đọc lại ảnh: " + e.message);
  }
}

function openPasteExcelModal() {
  if (!currentProjectId) {
    alert("Hãy tạo hoặc chọn dự án trước.");
    return;
  }
  document.getElementById("modalTitle").textContent = "📋 Dán nhanh bảng copy từ Excel";
  document.getElementById("modalBody").innerHTML = `
    <p class="step-msg">Sếp bôi đen các dòng trong bảng Excel (Tên món | Số lượng + Đơn vị | Giá | Ghi chú) nhấn <b>Ctrl+C</b> rồi dán (<b>Ctrl+V</b>) vào ô dưới đây:</p>
    <textarea id="pasteExcelTextarea" rows="14" placeholder="GIỎ ĐỒ ĐI SINH 5 TR\nÁo ngắn tay\t3 Cái\t60\nÁo dài tay\t2 Cái\t40\nBỉm\t1 Bịch\t150\n...\n5036" style="font-family:Consolas,monospace; font-size:13px;"></textarea>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:10px;">
      <button onclick="closeModal()">Hủy</button>
      <button class="primary" onclick="submitPasteExcelText()">⚡ Đọc vào bảng ngay (tức thì)</button>
    </div>
  `;
  document.getElementById("modalBackdrop").classList.add("open");
}

async function submitPasteExcelText() {
  const txt = document.getElementById("pasteExcelTextarea").value;
  if (!txt.trim()) return;
  try {
    const data = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/parse-table-text`, { text: txt });
    currentProject = data.project;
    populateWorkspace(currentProject);
    closeModal();
  } catch (e) {
    alert("Lỗi phân tích dữ liệu dán: " + e.message);
  }
}

async function viewStepLog(stepNum) {
  if (!currentProjectId) return;
  const res = await apiGet(`/api/projects/${encodeURIComponent(currentProjectId)}/logs/${stepNum}`);
  document.getElementById("modalTitle").textContent = `Nhật ký Bước ${stepNum}`;
  document.getElementById("modalBody").innerHTML = `<pre class="code-box" style="max-height:70vh;">${escapeHtml(res.log || "(Chưa có log)")}</pre>`;
  document.getElementById("modalBackdrop").classList.add("open");
}

function openImageModal(title, imgUrl) {
  document.getElementById("modalTitle").textContent = title;
  document.getElementById("modalBody").innerHTML = `
    <div style="text-align:center;">
      <img src="${imgUrl}" style="max-width:100%; border-radius:8px; border:1px solid var(--border);" />
    </div>
  `;
  document.getElementById("modalBackdrop").classList.add("open");
}

async function openConfigModal() {
  await loadAppConfig();
  document.getElementById("modalTitle").textContent = "⚙ Cấu hình toàn cục (config.json)";
  document.getElementById("modalBody").innerHTML = `
    <p class="step-msg">Mọi đường dẫn công cụ và giới hạn số lần gọi AI CLI đều nằm tại <code>E:\\vd chia se\\config.json</code> (không ghi cứng trong mã):</p>
    <textarea id="cfgJsonEditor" rows="22" style="font-family:Consolas,monospace; font-size:12.5px;">${escapeHtml(JSON.stringify(appConfig, null, 2))}</textarea>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:10px;">
      <button class="primary" onclick="saveGlobalConfig()">💾 Lưu config.json</button>
    </div>
  `;
  document.getElementById("modalBackdrop").classList.add("open");
}

async function saveGlobalConfig() {
  try {
    const parsed = JSON.parse(document.getElementById("cfgJsonEditor").value);
    const res = await apiPost("/api/config", parsed);
    appConfig = res.config;
    closeModal();
    alert("Đã lưu config.json!");
  } catch (e) {
    alert("JSON không hợp lệ: " + e.message);
  }
}

function closeModal() {
  document.getElementById("modalBackdrop").classList.remove("open");
}

async function openExportFolder() {
  const expDir = (appConfig && appConfig.paths && appConfig.paths.export_dir) || "H:\\source";
  await apiPost("/api/system/open-explorer", { path: expDir });
}

async function openPathInExplorer(pathStr) {
  await apiPost("/api/system/open-explorer", { path: pathStr });
}

async function loadSampleBenhVienList() {
  const sampleText = [
    "7. BỆNH VIỆN ĐI SINH",
    "",
    "Từ dũ",
    "Hùng Vương",
    "ĐH Y Dược",
    "Mê Kông",
    "Vinmec",
    "Tâm Anh",
    "Hạnh Phúc",
    "BV Quốc Tế Mỹ (AIH)",
  ].join("\n");
  document.getElementById("inpScript").value = sampleText;
  document.getElementById("inpTitle").value = "BỆNH VIỆN ĐI SINH";
  document.getElementById("inpPreset").value = "anh_nhac";
  onPresetChange();
  updateFontPreview();
  if (currentProjectId) {
    await parseAndFetchAnhNhacList(false);
  }
}

async function parseAndFetchAnhNhacList(alsoShootStills = false) {
  if (!currentProjectId) {
    alert("Hãy tạo hoặc chọn dự án trước.");
    return;
  }
  const rawText = document.getElementById("inpScript").value.trim();
  if (!rawText) {
    alert("Sếp hãy dán danh sách các mục vào ô Kịch bản / Danh sách bên trái trước nhé!");
    return;
  }
  const statusEl = document.getElementById("anhNhacStatusMsg");
  if (statusEl) {
    statusEl.innerHTML = `<span style="color:#38bdf8;">⏳ Đang phân tích danh sách &amp; tự động tìm tải hình ảnh thực tế cho từng mục trên Web... vui lòng chờ vài giây...</span>`;
  }
  try {
    const itemDur = Number((document.getElementById("inpItemDurationSec") && document.getElementById("inpItemDurationSec").value) || 2.4);
    const bgmPath = (document.getElementById("inpBgmPath") && document.getElementById("inpBgmPath").value.trim()) || "";
    const customReq = (document.getElementById("inpAnhNhacCustomRequest") && document.getElementById("inpAnhNhacCustomRequest").value.trim()) || "";
    const useAi = !!(document.getElementById("chkAnhNhacPromptAi") && document.getElementById("chkAnhNhacPromptAi").checked);
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/parse-anh-nhac-list`, {
      text: rawText,
      title: document.getElementById("inpTitle").value.trim(),
      itemDurationSec: itemDur,
      bgmPath,
      custom_request: customReq,
      use_ai: useAi,
    });
    currentProject = res.project;
    populateWorkspace(currentProject);
    const count = (res.parsed && res.parsed.count) || 0;
    const dlCount = (res.parsed && res.parsed.downloaded_count) || 0;
    const revChanges = (res.revision && res.revision.changes) || [];
    const revSuffix = revChanges.length ? ` | Đã áp dụng yêu cầu thêm: ${revChanges.join("; ")}` : "";
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#10b981;">✅ Đã tự tìm &amp; gắn xong <b>${dlCount}/${count} hình ảnh</b> cho danh sách <b>${escapeHtml(currentProject.title)}</b>${escapeHtml(revSuffix)}! Sếp có thể kiểm tra ở Bước 2 hoặc chụp 3 ảnh mẫu.</span>`;
    }
    if (alsoShootStills) {
      if (statusEl) {
        statusEl.innerHTML = `<span style="color:#38bdf8;">⏳ Đã gắn ${dlCount}/${count} ảnh! Đang chụp 3 ảnh mẫu 1080×1080 (Bước 3)...</span>`;
      }
      await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/run`, {
        start_step: 7,
        stop_at_gates: true,
        single_step_only: true,
        force_recompute: true,
      });
      currentProject.pipeline_status = "running";
      renderSidebarSteps(currentProject);
    }
  } catch (e) {
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#ef4444;">❌ Lỗi tìm ảnh: ${escapeHtml(e.message)}</span>`;
    }
    alert("Lỗi tìm & gắn hình ảnh: " + e.message);
  }
}

function insertAnhNhacRequestSnippet(snippet) {
  const el = document.getElementById("inpAnhNhacCustomRequest");
  if (!el) return;
  const cur = el.value.trim();
  el.value = cur ? `${cur}; ${snippet}` : snippet;
  el.focus();
}

async function applyAnhNhacCustomRequest(rerenderMp4 = false) {
  if (!currentProjectId) {
    alert("Hãy tạo hoặc chọn dự án trước.");
    return;
  }
  const reqEl = document.getElementById("inpAnhNhacCustomRequest");
  const notes = (reqEl && reqEl.value.trim()) || "";
  if (!notes) {
    alert("Sếp hãy nhập yêu cầu cần thực hiện vào ô nhé!");
    if (reqEl) reqEl.focus();
    return;
  }
  const useAi = !!(document.getElementById("chkAnhNhacPromptAi") && document.getElementById("chkAnhNhacPromptAi").checked);
  const statusBox = document.getElementById("anhNhacRevisionStatusBox");
  const btn = document.getElementById("btnApplyAnhNhacReq");
  if (btn) btn.disabled = true;
  if (statusBox) {
    statusBox.innerHTML = `<div class="step-msg" style="color:#38bdf8;">⏳ Đang thực hiện yêu cầu: "${escapeHtml(notes)}"...</div>`;
  }
  try {
    const curBangItems = (currentProject && currentProject.bang && currentProject.bang.items) || [];
    const rawScript = (document.getElementById("inpScript") && document.getElementById("inpScript").value.trim()) || "";
    const prevScript = ((currentProject && currentProject.kich_ban) || "").trim();
    const scriptChanged = Boolean(rawScript && (curBangItems.length === 0 || rawScript !== prevScript));
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/apply-final-revision`, {
      notes,
      script_text: rawScript,
      reparse_script: scriptChanged,
      use_ai: useAi,
      restill_step7: !rerenderMp4,
      rerender_mp4: rerenderMp4,
      export_capcut: false,
    });
    currentProject = res.project;
    populateWorkspace(currentProject);
    const changes = (res.revision && res.revision.changes) || [];
    if (statusBox) {
      statusBox.innerHTML = `
        <div style="background:rgba(16,185,129,0.12); border:1px solid #10b981; border-radius:6px; padding:8px 10px; font-size:12.5px; color:#d1fae5;">
          <strong>✅ Đã thực hiện xong yêu cầu:</strong> ${changes.map((c) => escapeHtml(c)).join(" • ")}
        </div>
      `;
    }
    if (rerenderMp4) {
      switchTab("tab4");
    } else {
      goToStepView(7);
    }
  } catch (e) {
    if (statusBox) {
      statusBox.innerHTML = `<div class="step-msg" style="color:#ef4444;">❌ Lỗi thực hiện yêu cầu: ${escapeHtml(e.message)}</div>`;
    }
    alert("Lỗi thực hiện yêu cầu: " + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function cycleWebImageForItem(itemIndex) {
  if (!currentProjectId) return;
  const btn = document.getElementById(`btnWebCycle_${itemIndex}`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Đang tìm...";
  }
  try {
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/search-item-web-image`, {
      item_index: itemIndex,
      cycle_next: true,
    });
    currentProject = res.project;
    populateWorkspace(currentProject);
  } catch (e) {
    alert("Lỗi đổi ảnh Web: " + e.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🔄 Đổi ảnh Web";
    }
  }
}

async function promptSearchWebImageForItem(itemIndex, defaultName) {
  if (!currentProjectId) return;
  const q = prompt(`Nhập từ khóa tìm ảnh Web cho mục #${itemIndex} (${defaultName}):`, `${defaultName} bệnh viện`);
  if (!q || !q.trim()) return;
  const btn = document.getElementById(`btnWebCycle_${itemIndex}`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Đang tìm...";
  }
  try {
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/search-item-web-image`, {
      item_index: itemIndex,
      custom_query: q.trim(),
      cycle_next: false,
    });
    currentProject = res.project;
    populateWorkspace(currentProject);
  } catch (e) {
    alert("Lỗi tìm ảnh theo từ khóa: " + e.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🔄 Đổi ảnh Web";
    }
  }
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeJsStr(str) {
  return String(str ?? "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

// ------------------------------------------------------------------------
// DOCTOR / SUBJECT IMAGE UPLOAD, AI CUTOUT & INTERACTIVE CROP EDITOR
// ------------------------------------------------------------------------
async function onSelectDoctorBatchFiles(inputEl) {
  const files = Array.from((inputEl && inputEl.files) || []);
  if (!files.length) return;
  await uploadDoctorFilesToItems(files, 1);
  inputEl.value = "";
}

async function onDropDoctorBatchImages(event) {
  event.preventDefault();
  const box = document.getElementById("doctorUploadAndEditBox");
  if (box) box.style.borderColor = "rgba(16, 185, 129, 0.45)";
  const files = Array.from((event.dataTransfer && event.dataTransfer.files) || []).filter((f) =>
    f.type.startsWith("image/")
  );
  if (!files.length) return;
  await uploadDoctorFilesToItems(files, 1);
}

async function uploadDoctorFilesToItems(files, startItemIdx = 1) {
  if (!currentProjectId) {
    alert("Sếp hãy chọn hoặc tạo dự án trước khi tải ảnh lên nhé!");
    return;
  }
  // Ensure current script & bang rows are saved first so bang.json has all items
  await saveProjectSettings();

  const modeEl = document.getElementById("selDoctorEditMode");
  const mode = (modeEl && modeEl.value) || "cutout";
  const statusEl = document.getElementById("doctorBatchStatusMsg");
  if (statusEl) {
    statusEl.style.display = "block";
    statusEl.innerHTML = `⏳ Đang tải lên <b>${files.length}</b> ảnh &amp; tách lấy riêng hình bác sĩ...`;
  }

  let lastRes = null;
  for (let k = 0; k < files.length; k++) {
    const file = files[k];
    const targetIdx = startItemIdx + k;
    const isLast = k === files.length - 1;
    if (statusEl) {
      statusEl.innerHTML = `⏳ Đang xử lý ảnh <b>${k + 1}/${files.length}</b> (Mục #${targetIdx}: <code>${escapeHtml(file.name)}</code>)...`;
    }
    const resp = await fetch(
      `/api/projects/${encodeURIComponent(currentProjectId)}/upload-doctor-image?item_index=${targetIdx}&mode=${encodeURIComponent(mode)}&run_step6=${isLast ? "1" : "0"}&filename=${encodeURIComponent(file.name)}`,
      { method: "POST", body: file }
    );
    const data = await resp.json();
    if (!resp.ok || data.error) {
      alert(`Lỗi xử lý ảnh mục #${targetIdx}: ` + (data.error || resp.status));
      break;
    }
    lastRes = data;
  }

  if (lastRes && lastRes.project) {
    currentProject = lastRes.project;
    populateWorkspace(currentProject);
    if (statusEl) {
      statusEl.innerHTML = `✅ Đã tải &amp; tách lấy riêng hình bác sĩ cho <b>${files.length} mục</b>! <button class="sm primary" style="margin-left:8px;" onclick="openDoctorImageEditorModal(${startItemIdx})">✂️ Xem &amp; Tinh chỉnh khung cắt từng mục</button>`;
    }
    if (files.length === 1) {
      openDoctorImageEditorModal(startItemIdx);
    }
  }
}

async function applyDoctorExtractToAllItems() {
  if (!currentProjectId) return;
  await saveProjectSettings();
  const modeEl = document.getElementById("selDoctorEditMode");
  const mode = (modeEl && modeEl.value) || "cutout";
  const statusEl = document.getElementById("doctorBatchStatusMsg");
  if (statusEl) {
    statusEl.style.display = "block";
    statusEl.innerHTML = `⏳ AI đang tách nền / cắt lấy riêng hình bác sĩ cho toàn bộ các mục...`;
  }
  try {
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/edit-doctor-image`, {
      apply_all: true,
      mode,
    });
    if (res.project) {
      currentProject = res.project;
      populateWorkspace(currentProject);
    }
    if (statusEl) {
      statusEl.innerHTML = `✅ Đã tách lấy riêng hình bác sĩ cho <b>${res.processed_count || 0} mục</b>! Sếp có thể bấm <b>✂️ Mở Khung Cắt &amp; Sửa Hình Bác Sĩ Từng Mục</b> nếu muốn chỉnh lại khung cắt bất kỳ bác sĩ nào.`;
    }
  } catch (e) {
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#f87171;">❌ Lỗi: ${escapeHtml(e.message)}</span>`;
    }
    alert("Lỗi tách hình bác sĩ: " + e.message);
  }
}

let _docEditorState = {
  itemIndex: 1,
  mode: "cutout",
  cropBox: null, // [x, y, w, h] in 0..1
  dragging: false,
  startX: 0,
  startY: 0,
};

async function openDoctorImageEditorModal(initialItemIdx = 1) {
  if (!currentProjectId) {
    alert("Sếp hãy chọn dự án trước nhé!");
    return;
  }
  const items = (currentProject && currentProject.bang && currentProject.bang.items) || collectBangFromTable().items || [];
  if (!items.length) {
    alert("Chưa có danh sách mục nào. Sếp hãy dán kịch bản vào ô Kịch bản trước nhé!");
    return;
  }
  const targetItem = items.find((x) => Number(x.i) === Number(initialItemIdx)) || items[0];
  _docEditorState.itemIndex = Number(targetItem.i || 1);
  const globalModeEl = document.getElementById("selDoctorEditMode");
  _docEditorState.mode = targetItem.doctor_edit_mode || (globalModeEl && globalModeEl.value) || "cutout";
  _docEditorState.cropBox = targetItem.doctor_crop_box || null;

  document.getElementById("modalTitle").textContent = "✂️ Tải Ảnh & Chỉnh Sửa Để Lấy Mỗi Hình Bác Sĩ / Nhân Vật";
  const itemOptionsHtml = items
    .map(
      (it) =>
        `<option value="${it.i}" ${Number(it.i) === _docEditorState.itemIndex ? "selected" : ""}>Mục #${it.i}: ${escapeHtml(
          it.display_name || it.ten || ""
        )}</option>`
    )
    .join("");

  document.getElementById("modalBody").innerHTML = `
    <div style="display:flex; flex-direction:column; gap:10px;">
      <!-- Top toolbar: Select Item + Upload File + Paste + Mode -->
      <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center; justify-content:space-between; background:#0d131f; padding:10px 12px; border-radius:8px; border:1px solid #334155;">
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <label style="margin:0; font-weight:700; color:#38bdf8;">Chọn mục:</label>
          <select id="docModalItemSelect" style="width:auto; min-width:220px; font-weight:700;" onchange="onDocModalSwitchItem(this.value)">
            ${itemOptionsHtml}
          </select>
          <input type="file" id="docModalFileInput" accept="image/*" style="display:none;" onchange="onDocModalUploadFile(this)" />
          <button class="success sm" onclick="document.getElementById('docModalFileInput').click()">
            📤 Tải ảnh từ máy cho mục này
          </button>
          <button class="sm" onclick="onDocModalPickViaDialog()" title="Mở hộp thoại Windows chọn file ảnh">
            📂 Chọn đường dẫn
          </button>
        </div>
        <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
          <label style="margin:0; font-size:12px; color:#cbd5e1;">Chế độ lấy hình:</label>
          <select id="docModalModeSelect" style="width:auto; min-width:255px; font-size:12px;" onchange="onDocModalModeChange(this.value)">
            <option value="cutout" ${_docEditorState.mode === "cutout" ? "selected" : ""}>👤 Tách nền lấy mỗi hình Bác Sĩ (Có viền trắng nổi bật)</option>
            <option value="cutout_card" ${_docEditorState.mode === "cutout_card" ? "selected" : ""}>✨ Tách nền Bác Sĩ + Đặt trên Thẻ Nền Sáng (Xóa chữ/nền rối)</option>
            <option value="crop_card" ${_docEditorState.mode === "crop_card" ? "selected" : ""}>🖼️ Cắt theo khung chọn &amp; Đóng khung thẻ (Giữ nền trong khung)</option>
            <option value="cutout_plain" ${_docEditorState.mode === "cutout_plain" ? "selected" : ""}>👤 Tách nền lấy mỗi Bác Sĩ (Nền trong suốt thuần)</option>
          </select>
        </div>
      </div>

      <div class="step-msg" style="color:#93c5fd;">
        💡 <b>Cách dùng:</b> Sếp có thể bấm <b>📤 Tải ảnh từ máy</b> (hoặc bấm <b>Ctrl+V</b> để dán ảnh chụp màn hình vào đây). Dùng chuột <b>kéo khoanh vùng quanh hình Bác Sĩ</b> ở ảnh gốc bên trái để bỏ hết chữ/khung TikTok thừa, hệ thống sẽ tự tách lấy mỗi hình Bác Sĩ ở bên phải!
      </div>

      <!-- Two-column editor: Left = Original + Drag Crop Box; Right = Extracted Doctor Result -->
      <div class="grid-2" style="gap:14px; align-items:stretch;">
        <div style="background:#0b0f17; border:1px solid #334155; border-radius:8px; padding:10px; display:flex; flex-direction:column; align-items:center;">
          <div style="width:100%; display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <strong style="font-size:12.5px; color:#e2e8f0;">1. Ảnh gốc (Dùng chuột kéo khoanh vùng Bác Sĩ)</strong>
            <button class="sm" onclick="resetDocModalCropToAuto()" title="Để AI tự động khoanh vùng lấy trọn hình bác sĩ">🎯 AI Tự khoanh vùng BS</button>
          </div>
          <div id="docCropStage" style="position:relative; display:inline-block; max-width:100%; max-height:380px; overflow:hidden; border-radius:6px; border:1px solid #475569; cursor:crosshair; user-select:none;">
            <img id="docModalRawImg" src="" alt="Ảnh gốc" draggable="false" style="display:block; max-width:100%; max-height:380px; width:auto; height:auto; pointer-events:none;" />
            <div id="docCropRect" style="display:none; position:absolute; border:2.5px dashed #34d399; background:rgba(16, 185, 129, 0.14); box-shadow:0 0 0 9999px rgba(0,0,0,0.52); pointer-events:none;"></div>
          </div>
          <div id="docCropCoordsInfo" class="step-msg" style="margin-top:6px;">Kéo chuột trên ảnh gốc để khoanh riêng vùng có Bác Sĩ</div>
        </div>

        <div style="background:#0b0f17; border:1px solid #334155; border-radius:8px; padding:10px; display:flex; flex-direction:column; align-items:center;">
          <div style="width:100%; display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <strong style="font-size:12.5px; color:#34d399;">2. Kết quả chỉ lấy hình Bác Sĩ (Hiện trên Video)</strong>
            <span id="docModalStatusBadge" class="badge success">Sẵn sàng</span>
          </div>
          <div class="checkerboard" style="width:100%; height:380px; display:flex; align-items:center; justify-content:center; border-radius:6px; overflow:hidden; background-color:#f3ead8;">
            <img id="docModalPreviewImg" src="" alt="Kết quả tách hình Bác Sĩ" style="max-width:94%; max-height:360px; object-fit:contain;" />
          </div>
          <div class="step-msg" style="margin-top:6px;">Nền màu be mô phỏng đúng nền video để sếp kiểm tra độ nét</div>
        </div>
      </div>

      <!-- Footer actions -->
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-top:4px;">
        <div style="display:flex; gap:6px;">
          <button class="sm" onclick="stepDocModalItem(-1)">◀ Mục trước</button>
          <button class="sm" onclick="stepDocModalItem(1)">Mục tiếp theo ▶</button>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <button onclick="closeModal()">Đóng</button>
          <button class="primary" onclick="saveDocModalCurrentItem(false)">💾 Lưu hình Bác Sĩ cho mục này</button>
          <button class="success" onclick="saveDocModalCurrentItem(true)">✅ Lưu &amp; Qua mục tiếp theo</button>
        </div>
      </div>
    </div>
  `;

  document.getElementById("modalBackdrop").classList.add("open");
  initDocCropMouseHandlers();
  await refreshDocModalPreview(true);
}

function initDocCropMouseHandlers() {
  const stage = document.getElementById("docCropStage");
  const rawImg = document.getElementById("docModalRawImg");
  if (!stage || !rawImg) return;

  stage.onmousedown = (e) => {
    const rect = rawImg.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) return;
    _docEditorState.dragging = true;
    _docEditorState.startX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    _docEditorState.startY = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
  };

  window.onmousemove = (e) => {
    if (!_docEditorState.dragging) return;
    const rawImgEl = document.getElementById("docModalRawImg");
    if (!rawImgEl) return;
    const rect = rawImgEl.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) return;
    const curX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const curY = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    const x = Math.min(_docEditorState.startX, curX);
    const y = Math.min(_docEditorState.startY, curY);
    const w = Math.abs(curX - _docEditorState.startX);
    const h = Math.abs(curY - _docEditorState.startY);
    if (w > 0.04 && h > 0.04) {
      _docEditorState.cropBox = [
        Number(x.toFixed(4)),
        Number(y.toFixed(4)),
        Number(w.toFixed(4)),
        Number(h.toFixed(4)),
      ];
      renderDocCropRectOverlay();
    }
  };

  window.onmouseup = async () => {
    if (!_docEditorState.dragging) return;
    _docEditorState.dragging = false;
    if (_docEditorState.cropBox) {
      await refreshDocModalPreview(true);
    }
  };
}

function renderDocCropRectOverlay() {
  const rectEl = document.getElementById("docCropRect");
  const infoEl = document.getElementById("docCropCoordsInfo");
  const box = _docEditorState.cropBox;
  if (!rectEl) return;
  if (!box || box.length !== 4) {
    rectEl.style.display = "none";
    if (infoEl) infoEl.textContent = "Đang dùng chế độ AI tự nhận diện toàn ảnh (Kéo chuột để khoanh vùng thủ công)";
    return;
  }
  const [x, y, w, h] = box;
  rectEl.style.display = "block";
  rectEl.style.left = `${(x * 100).toFixed(1)}%`;
  rectEl.style.top = `${(y * 100).toFixed(1)}%`;
  rectEl.style.width = `${(w * 100).toFixed(1)}%`;
  rectEl.style.height = `${(h * 100).toFixed(1)}%`;
  if (infoEl) {
    infoEl.innerHTML = `Khung lấy hình Bác Sĩ: Ngang <b>${Math.round(w * 100)}%</b> × Cao <b>${Math.round(h * 100)}%</b> (Kéo chuột trên ảnh để đổi vùng cắt)`;
  }
}

async function onDocModalSwitchItem(newIdxVal) {
  _docEditorState.itemIndex = Number(newIdxVal) || 1;
  const items = (currentProject && currentProject.bang && currentProject.bang.items) || [];
  const it = items.find((x) => Number(x.i) === _docEditorState.itemIndex) || {};
  _docEditorState.cropBox = it.doctor_crop_box || null;
  if (it.doctor_edit_mode) {
    _docEditorState.mode = it.doctor_edit_mode;
    const mSel = document.getElementById("docModalModeSelect");
    if (mSel) mSel.value = _docEditorState.mode;
  }
  await refreshDocModalPreview(true);
}

async function stepDocModalItem(delta) {
  const sel = document.getElementById("docModalItemSelect");
  if (!sel) return;
  const nextIdx = sel.selectedIndex + delta;
  if (nextIdx >= 0 && nextIdx < sel.options.length) {
    sel.selectedIndex = nextIdx;
    await onDocModalSwitchItem(sel.value);
  }
}

async function onDocModalModeChange(newMode) {
  _docEditorState.mode = newMode;
  const globalModeEl = document.getElementById("selDoctorEditMode");
  if (globalModeEl) globalModeEl.value = newMode;
  await refreshDocModalPreview(true);
}

async function resetDocModalCropToAuto() {
  _docEditorState.cropBox = null;
  await refreshDocModalPreview(true);
}

async function onDocModalUploadFile(inputEl) {
  const file = inputEl && inputEl.files && inputEl.files[0];
  if (!file || !currentProjectId) return;
  const badge = document.getElementById("docModalStatusBadge");
  if (badge) {
    badge.className = "badge warning";
    badge.textContent = "⏳ Đang tải & tách hình BS...";
  }
  try {
    const resp = await fetch(
      `/api/projects/${encodeURIComponent(currentProjectId)}/upload-doctor-image?item_index=${_docEditorState.itemIndex}&mode=${encodeURIComponent(_docEditorState.mode)}&run_step6=1&filename=${encodeURIComponent(file.name)}`,
      { method: "POST", body: file }
    );
    const data = await resp.json();
    if (!resp.ok || data.error) throw new Error(data.error || `HTTP ${resp.status}`);
    if (data.project) {
      currentProject = data.project;
      populateWorkspace(currentProject);
    }
    _docEditorState.cropBox = (data.result && data.result.suggested_crop_box) || null;
    await refreshDocModalPreview(true);
  } catch (e) {
    alert("Lỗi tải ảnh: " + e.message);
  } finally {
    inputEl.value = "";
  }
}

async function onDocModalPickViaDialog() {
  if (!currentProjectId) return;
  const pick = await apiPost("/api/system/pick-file", {
    title: `Chọn ảnh có sẵn cho Mục #${_docEditorState.itemIndex}`,
    filter: "Ảnh (*.png;*.jpg;*.jpeg;*.webp)|*.png;*.jpg;*.jpeg;*.webp|Tất cả (*.*)|*.*",
  });
  if (!pick.path) return;
  const badge = document.getElementById("docModalStatusBadge");
  if (badge) {
    badge.className = "badge warning";
    badge.textContent = "⏳ Đang nạp & tách hình BS...";
  }
  try {
    const data = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/upload-doctor-image`, {
      item_index: _docEditorState.itemIndex,
      mode: _docEditorState.mode,
      source_path: pick.path,
      run_step6: true,
    });
    if (data.project) {
      currentProject = data.project;
      populateWorkspace(currentProject);
    }
    _docEditorState.cropBox = (data.result && data.result.suggested_crop_box) || null;
    await refreshDocModalPreview(true);
  } catch (e) {
    alert("Lỗi nạp ảnh: " + e.message);
  }
}

async function refreshDocModalPreview(previewOnly = true) {
  if (!currentProjectId) return;
  const badge = document.getElementById("docModalStatusBadge");
  const rawImg = document.getElementById("docModalRawImg");
  const prevImg = document.getElementById("docModalPreviewImg");
  if (badge) {
    badge.className = "badge warning";
    badge.textContent = "⏳ AI đang tách lấy hình Bác Sĩ...";
  }
  try {
    const res = await apiPost(`/api/projects/${encodeURIComponent(currentProjectId)}/edit-doctor-image`, {
      item_index: _docEditorState.itemIndex,
      mode: _docEditorState.mode,
      crop_box: _docEditorState.cropBox,
      preview_only: previewOnly,
    });
    const ts = Date.now();
    if (rawImg && res.raw_rel) {
      rawImg.onload = () => renderDocCropRectOverlay();
      rawImg.src = `/api/projects/${encodeURIComponent(currentProjectId)}/file?path=${encodeURIComponent(res.raw_rel)}&t=${ts}`;
    }
    if (prevImg && res.edited_rel) {
      prevImg.src = `/api/projects/${encodeURIComponent(currentProjectId)}/file?path=${encodeURIComponent(res.edited_rel)}&t=${ts}`;
    }
    if (!_docEditorState.cropBox && res.result && res.result.suggested_crop_box) {
      _docEditorState.cropBox = res.result.suggested_crop_box;
    }
    renderDocCropRectOverlay();
    if (!previewOnly && res.project) {
      currentProject = res.project;
      populateWorkspace(currentProject);
    }
    if (badge) {
      badge.className = "badge success";
      badge.textContent = previewOnly ? "👁️ Đã cập nhật xem trước" : "✅ Đã lưu vào dự án";
    }
  } catch (e) {
    if (badge) {
      badge.className = "badge danger";
      badge.textContent = "Chưa có ảnh gốc — Hãy bấm Tải ảnh từ máy";
    }
  }
}

async function saveDocModalCurrentItem(goNext = false) {
  await refreshDocModalPreview(false);
  if (goNext) {
    const sel = document.getElementById("docModalItemSelect");
    if (sel && sel.selectedIndex + 1 < sel.options.length) {
      await stepDocModalItem(1);
    } else {
      closeModal();
    }
  }
}

// Allow Ctrl+V paste right inside the Doctor Image Editor Modal
window.addEventListener("paste", async (e) => {
  const modalOpen = document.getElementById("modalBackdrop")?.classList.contains("open");
  const docSel = document.getElementById("docModalItemSelect");
  if (!modalOpen || !docSel || !currentProjectId) return;
  const items = (e.clipboardData && e.clipboardData.items) || [];
  for (const clipIt of items) {
    if (clipIt.type && clipIt.type.startsWith("image/")) {
      e.preventDefault();
      const file = clipIt.getAsFile();
      if (!file) return;
      const badge = document.getElementById("docModalStatusBadge");
      if (badge) {
        badge.className = "badge warning";
        badge.textContent = "⏳ Đang dán ảnh & tách hình BS...";
      }
      const resp = await fetch(
        `/api/projects/${encodeURIComponent(currentProjectId)}/upload-doctor-image?item_index=${_docEditorState.itemIndex}&mode=${encodeURIComponent(_docEditorState.mode)}&run_step6=1&filename=pasted_doctor.png`,
        { method: "POST", body: file }
      );
      const data = await resp.json();
      if (data && data.project) {
        currentProject = data.project;
        populateWorkspace(currentProject);
      }
      _docEditorState.cropBox = (data.result && data.result.suggested_crop_box) || null;
      await refreshDocModalPreview(true);
      break;
    }
  }
});

