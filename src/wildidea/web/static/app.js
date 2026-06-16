const state = {
  token: localStorage.getItem("wildidea_token") || "",
  authReady: !localStorage.getItem("wildidea_token"),
  user: null,
  runs: [],
  currentRunId: null,
  watchTimer: null,
  eventSource: null,
  watchRefreshTimer: null,
  runtimeTimer: null,
  authMode: "login",
  adminOpen: false,
  searchOpen: true,
  launchingSearch: false,
  animatedProgressCards: new Set(),
  emailCodeTimer: null,
  emailCodeRemaining: 0,
  bootFinished: false,
  runListSignature: "",
  historyDrawerOpen: false,
  historyQuery: "",
  posterCandidate: null,
  suppressProgressAnimationRunId: null,
  launchTimers: [],
  userInviteOpen: false,
  adminCardLogPage: 1,
};

const DRAW_CARD_DELAY_MS = 210;
const LAUNCH_CARD_DELAY_MS = 115;
const LAUNCH_PRINT_START_MS = 680;
const LAUNCH_CARD_LAND_MS = 1180;
const LAUNCH_PRINTER_EXIT_MS = 620;
const DEFAULT_SLOT_COUNT = 9;
const MAX_SLOT_COUNT = 9;

const $ = (id) => document.getElementById(id);
const FIT_TEXT_SELECTOR = "[data-fit-text]";

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function scheduleFitText(root = document) {
  window.requestAnimationFrame(() => {
    fitTextInCards(root);
    window.requestAnimationFrame(() => fitTextInCards(root));
    window.setTimeout(() => fitTextInCards(root), 160);
  });
}

function fitTextInCards(root = document) {
  const scope = root?.querySelectorAll ? root : document;
  const cards = new Set();
  if (root?.matches?.(".candidate")) cards.add(root);
  scope.querySelectorAll?.(".candidate").forEach((card) => cards.add(card));
  cards.forEach((card) => fitTextInCard(card));
}

function fitTextInCard(card) {
  if (!card || !card.querySelector) return;
  const items = Array.from(card.querySelectorAll(FIT_TEXT_SELECTOR)).filter((item) => item.offsetParent !== null);
  if (!items.length) return;
  items.forEach(resetFitTextItem);
  shrinkTextUntilFits(card, items, 44);
  card.querySelectorAll("[data-fit-container]").forEach((container) => {
    const localItems = Array.from(container.querySelectorAll(FIT_TEXT_SELECTOR)).filter((item) => item.offsetParent !== null);
    shrinkTextUntilFits(container, localItems, 40);
  });
}

function resetFitTextItem(item) {
  const computed = getComputedStyle(item);
  if (!item.dataset.fitBaseSize) {
    const size = Number.parseFloat(computed.fontSize) || 12;
    const lineHeight = Number.parseFloat(computed.lineHeight) || size * 1.25;
    item.dataset.fitBaseSize = String(size);
    item.dataset.fitLineRatio = String(lineHeight / size);
  }
  const baseSize = Number.parseFloat(item.dataset.fitBaseSize) || 12;
  const ratio = Number.parseFloat(item.dataset.fitLineRatio) || 1.25;
  item.style.setProperty("font-size", `${baseSize}px`);
  item.style.setProperty("line-height", `${baseSize * ratio}px`);
  item.style.setProperty("display", "block", "important");
  item.style.setProperty("-webkit-line-clamp", "unset", "important");
  item.style.setProperty("-webkit-box-orient", "initial", "important");
}

function shrinkTextUntilFits(container, items, maxSteps) {
  if (!container || !items.length) return;
  for (let step = 0; step < maxSteps && fitTargetOverflows(container, items); step += 1) {
    let changed = false;
    items.forEach((item) => {
      const minSize = Number.parseFloat(item.dataset.fitMin || "6.8");
      const current = Number.parseFloat(item.style.fontSize || getComputedStyle(item).fontSize) || minSize;
      if (current <= minSize) return;
      const next = Math.max(minSize, current - 0.5);
      const ratio = Number.parseFloat(item.dataset.fitLineRatio) || 1.25;
      item.style.fontSize = `${next}px`;
      item.style.lineHeight = `${next * ratio}px`;
      changed = true;
    });
    if (!changed) break;
  }
}

function fitTargetOverflows(container, items) {
  return containerOverflows(container) || items.some(textItemOverflows);
}

function containerOverflows(container) {
  return container.scrollHeight > container.clientHeight + 1 || container.scrollWidth > container.clientWidth + 1;
}

function textItemOverflows(item) {
  return item.scrollHeight > item.clientHeight + 1 || item.scrollWidth > item.clientWidth + 1;
}

async function withMinimumDelay(promise, ms) {
  const [value] = await Promise.all([promise, delay(ms)]);
  return value;
}

function finishBoot() {
  if (state.bootFinished) return;
  state.bootFinished = true;
  window.requestAnimationFrame(() => {
    document.body.classList.remove("app-booting");
    document.body.classList.add("app-ready");
    window.setTimeout(() => {
      document.body.classList.add("app-boot-finished");
    }, 720);
  });
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 3200);
}

function promptAuthRequired() {
  showToast("请先登录或注册，再开始打印灵感卡");
  $("email")?.focus();
}

function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  return fetch(path, { ...options, headers }).then(async (res) => {
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) {
      const detail = data.detail || data;
      throw new Error(detail.message || detail.error || res.statusText);
    }
    return data;
  });
}

function setAuthMode(mode) {
  state.authMode = mode;
  $("loginTab").classList.toggle("active", mode === "login");
  $("registerTab").classList.toggle("active", mode === "register");
  $("emailCodeWrap").classList.toggle("hidden", mode !== "register");
  $("inviteAtRegisterWrap").classList.toggle("hidden", mode !== "register");
  $("improvementConsentWrap").classList.toggle("hidden", mode !== "register");
  $("improvementConsent").required = mode === "register";
  $("authSubmit").textContent = mode === "login" ? "登录" : "注册并获得 30 积分";
  $("password").autocomplete = mode === "login" ? "current-password" : "new-password";
}

function isAdminUser() {
  return Boolean(state.user && state.user.role === "admin");
}

function ensureAdminPanel() {
  let panel = $("adminPanel");
  if (panel) return panel;
  panel = document.createElement("section");
  panel.id = "adminPanel";
  panel.className = "admin-panel hidden";
  panel.innerHTML = `
    <div class="panel-head">
      <strong>管理员后台</strong>
      <button id="refreshAdminBtn" class="ghost" type="button">刷新</button>
    </div>
    <div id="metrics" class="metrics"></div>
    <div id="queueStatus" class="queue-status"></div>
    <form id="inviteForm" class="invite-create">
      <input id="inviteCode" type="text" placeholder="邀请码，留空自动生成">
      <input id="inviteBonus" type="number" value="20" min="1">
      <input id="inviteMax" type="number" placeholder="最大兑换次数">
      <button type="submit">创建邀请码</button>
    </form>
    <div class="admin-columns">
      <div>
        <h2>邀请码</h2>
        <div id="inviteList" class="admin-list"></div>
      </div>
      <div>
        <h2>用户</h2>
        <div id="userList" class="admin-list"></div>
      </div>
    </div>
  `;
  const emptyState = $("emptyState");
  emptyState.parentNode.insertBefore(panel, emptyState);
  bindAdminPanelEvents(panel);
  return panel;
}

function removeAdminPanel() {
  $("adminPanel")?.remove();
}

function bindAdminPanelEvents(panel) {
  panel.querySelector("#refreshAdminBtn")?.addEventListener("click", loadAdmin);
  panel.querySelector("#exportFeedbackBtn")?.addEventListener("click", downloadFeedbackExcel);
  panel.querySelector("#inviteForm")?.addEventListener("submit", handleInviteSubmit);
}

function renderShell() {
  const booting = !state.authReady;
  const loggedIn = Boolean(state.user);
  const isAdmin = isAdminUser();
  const adminViewActive = loggedIn && isAdmin && state.adminOpen;
  if (!isAdmin) state.adminOpen = false;
  if (!isAdmin) removeAdminPanel();
  if (!loggedIn || adminViewActive) state.historyDrawerOpen = false;
  if (!loggedIn) state.userInviteOpen = false;
  document.body.classList.toggle("app-logged-in", loggedIn);
  document.body.classList.toggle("admin-view-open", adminViewActive);
  $("authPanel").classList.toggle("hidden", booting || loggedIn);
  $("userPanel").classList.toggle("hidden", !loggedIn);
  $("historyPanel").classList.toggle("hidden", !loggedIn);
  $("historyDrawerBtn").classList.toggle("hidden", !loggedIn || adminViewActive);
  $("historyDrawerBtn").setAttribute("aria-expanded", String(state.historyDrawerOpen));
  $("historyBackdrop").classList.toggle("hidden", !state.historyDrawerOpen);
  document.body.classList.toggle("history-drawer-open", state.historyDrawerOpen);
  $("workspace").classList.toggle("hidden", booting || adminViewActive);
  const adminPanel = adminViewActive ? ensureAdminPanel() : $("adminPanel");
  adminPanel?.classList.toggle("hidden", !adminViewActive);
  $("emptyState").classList.add("hidden");
  $("toolbarTitle").textContent = adminViewActive ? "管理员后台" : "生成工作台";
  $("toolbarSubtitle").textContent = adminViewActive
    ? "查看队列、用户、邀请码、反馈和导出数据。"
    : (!loggedIn ? "登录或注册后即可输入问题，打印跨域灵感卡。" : (isAdmin ? "管理员无限配额；系统失败会自动恢复任务状态。" : "每张卡片消耗 1 积分；系统失败会自动退回本次扣除。"));
  $("statusPill").textContent = statusPillText(booting, loggedIn, isAdmin, adminViewActive);
  $("statusPill").disabled = !isAdmin;
  $("statusPill").classList.toggle("is-admin-action", isAdmin);
  $("statusPill").setAttribute("aria-pressed", String(adminViewActive));
  $("statusPill").title = isAdmin ? (adminViewActive ? "返回生成工作台" : "打开管理员后台") : "";
  $("userPanel").classList.toggle("invite-open", loggedIn && state.userInviteOpen);
  $("redeemForm").classList.toggle("hidden", !loggedIn || !state.userInviteOpen);
  $("userPanelToggle").setAttribute("aria-expanded", String(loggedIn && state.userInviteOpen));
  $("brandHomeBtn").classList.toggle("is-clickable", loggedIn);
  $("brandHomeBtn").setAttribute("aria-label", loggedIn ? "发起新的 WildIdea 搜索" : "WildIdea");
  $("brandActionHint").classList.toggle("hidden", !loggedIn || adminViewActive || state.searchOpen || state.launchingSearch);
  if (loggedIn) {
    $("userEmail").textContent = state.user.email;
  }
  ["problem", "forbidTerms", "slotCount"].forEach((id) => {
    const field = $(id);
    if (field) field.readOnly = !loggedIn;
  });
  updateRunCostLabel();
  renderWorkspaceMode();
}

function statusPillText(booting, loggedIn, isAdmin, adminViewActive) {
  if (booting) return "正在恢复登录";
  if (!loggedIn) return "未登录";
  if (isAdmin) return adminViewActive ? "返回工作台" : "管理员后台";
  return `普通用户 · ${state.user.credit_balance} 积分`;
}

function updateRunCostLabel() {
  const count = Math.max(1, Math.min(MAX_SLOT_COUNT, Number($("slotCount")?.value || DEFAULT_SLOT_COUNT)));
  if (!state.user) {
    $("runSubmit").textContent = `登录后打印 ${count} 张灵感卡`;
    return;
  }
  $("runSubmit").textContent = isAdminUser() ? `打印 ${count} 张灵感卡` : `消耗 ${count} 积分打印`;
}

function launchDurationForCount(count) {
  const safeCount = Math.max(1, Math.min(MAX_SLOT_COUNT, Number(count || DEFAULT_SLOT_COUNT)));
  return LAUNCH_PRINT_START_MS + (safeCount - 1) * LAUNCH_CARD_DELAY_MS + LAUNCH_CARD_LAND_MS + LAUNCH_PRINTER_EXIT_MS;
}

function setLaunchTiming(slotCount) {
  const safeCount = Math.max(1, Math.min(MAX_SLOT_COUNT, Number(slotCount || DEFAULT_SLOT_COUNT)));
  const workspace = $("workspace");
  workspace.style.setProperty("--launch-duration", `${launchDurationForCount(safeCount)}ms`);
  workspace.style.setProperty("--print-start-delay", `${LAUNCH_PRINT_START_MS}ms`);
  workspace.style.setProperty("--card-land-duration", `${LAUNCH_CARD_LAND_MS}ms`);
}

function setLaunchPrinterFrame() {
  const workspace = $("workspace");
  const form = $("runForm");
  if (!workspace || !form) return;
  const rect = form.getBoundingClientRect();
  workspace.style.setProperty("--launch-printer-left", `${Math.round(rect.left)}px`);
  workspace.style.setProperty("--launch-printer-top", `${Math.round(rect.top)}px`);
  workspace.style.setProperty("--launch-printer-width", `${Math.round(rect.width)}px`);
}

function clearLaunchTiming() {
  const workspace = $("workspace");
  workspace.style.removeProperty("--launch-duration");
  workspace.style.removeProperty("--print-start-delay");
  workspace.style.removeProperty("--card-land-duration");
  workspace.style.removeProperty("--launch-printer-left");
  workspace.style.removeProperty("--launch-printer-top");
  workspace.style.removeProperty("--launch-printer-width");
}

function clearLaunchTimers({ softLayer = false } = {}) {
  state.launchTimers.forEach((timer) => window.clearTimeout(timer));
  state.launchTimers = [];
  if (softLayer) {
    settleLaunchPlaceholders();
    fadePrinterDrawLayer();
  } else {
    clearPrinterDrawLayer();
  }
}

function renderWorkspaceMode() {
  const loggedIn = Boolean(state.user);
  const showSearch = !state.adminOpen && state.searchOpen && !state.launchingSearch;
  $("workspace").classList.toggle("search-open", showSearch);
  $("workspace").classList.toggle("logged-out-preview", !loggedIn);
  $("workspace").classList.toggle("result-open", loggedIn && !state.adminOpen && !showSearch);
  $("workspace").classList.toggle("launching", Boolean(state.launchingSearch));
  $("runForm").classList.toggle("hidden", !showSearch && !state.launchingSearch);
  $("resultSection").classList.toggle("hidden", !loggedIn || (showSearch && !state.launchingSearch));
}

function openSearchPage() {
  if (!state.user) return;
  stopWatching();
  state.currentRunId = null;
  state.searchOpen = true;
  state.launchingSearch = false;
  state.adminOpen = false;
  state.historyDrawerOpen = false;
  state.suppressProgressAnimationRunId = null;
  clearLaunchTimers();
  clearLaunchTiming();
  state.animatedProgressCards.clear();
  $("problem").value = "";
  $("forbidTerms").value = "";
  $("slotCount").value = String(DEFAULT_SLOT_COUNT);
  updateRunCostLabel();
  renderRuns();
  renderCurrentRun(null);
  renderShell();
  setTimeout(() => $("problem").focus(), 0);
}

function fillExampleProblem(text) {
  if (!state.user) {
    promptAuthRequired();
    return;
  }
  if (!text) return;
  $("problem").value = text;
  $("problem").focus();
  $("problem").dispatchEvent(new Event("input", { bubbles: true }));
}

function beginSearchLaunch(problemText, slotCount) {
  setLaunchPrinterFrame();
  state.searchOpen = false;
  state.launchingSearch = true;
  clearLaunchTimers();
  setLaunchTiming(slotCount);
  $("currentRunTitle").textContent = "生成工作台";
  $("currentRunMeta").textContent = "正在打印卡片";
  $("progressLog").innerHTML = '<div class="progress-item">卡片正在落位，落下后会直接接入生成进度。</div>';
  renderLaunchLandingCards(slotCount, problemText);
  renderShell();
  schedulePrinterDrawCards();
}

function renderLaunchLandingCards(slotCount, problemText) {
  const count = Math.max(1, Math.min(MAX_SLOT_COUNT, Number(slotCount || DEFAULT_SLOT_COUNT)));
  const grid = $("candidateGrid");
  grid.classList.add("launch-landing-grid", "compact-card-grid");
  grid.innerHTML = Array.from({ length: count }, (_, index) => `
    <article class="candidate progress-card launch-progress-card launch-card-placeholder" data-launch-index="${index}" style="--draw-delay:${LAUNCH_PRINT_START_MS + index * LAUNCH_CARD_DELAY_MS}ms">
      <div class="candidate-top" data-fit-container>
        <div class="candidate-title-block">
          <div class="candidate-meta-row">
            <span class="candidate-index">方案 ${String(index + 1).padStart(2, "0")}</span>
            <span class="progress-status-badge pending">等待中</span>
          </div>
          <h3 data-fit-text data-fit-min="10">等待他山之石</h3>
          <span class="muted">正在接入流水线</span>
        </div>
        <span class="slot"><span class="slot-code">?</span><span class="slot-field">待抽取</span></span>
      </div>
      <div class="progress-track"><span style="width:12%"></span></div>
      <p>卡片已落位，等待接入生成流水线。</p>
      <div class="slot-stats">
        <span><small>耗时</small><strong>--</strong></span>
        <span><small>重抽</small><strong>0</strong></span>
        <span><small>API</small><strong>准备中</strong></span>
      </div>
      <div class="card-stream">
        <div>&gt; card landed</div>
        <div>&gt; waiting for source slot</div>
        <div>&gt; connecting pipeline</div>
        <div class="stream-cursor">▌</div>
      </div>
      <div class="step-row">
        <span>抽取</span>
        <span>生成</span>
        <span>校验</span>
        <span>完成</span>
      </div>
    </article>
  `).join("");
  scheduleFitText(grid);
}

function schedulePrinterDrawCards() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      renderPrinterDrawLayer();
    });
  });
}

function renderPrinterDrawLayer() {
  const workspace = $("workspace");
  const mouth = document.querySelector(".printer-mouth span") || document.querySelector(".printer-mouth");
  const targets = Array.from(document.querySelectorAll(".launch-card-placeholder"));
  if (!workspace || !mouth || !targets.length) return;

  const mouthRect = mouth.getBoundingClientRect();
  const liftY = Number.parseFloat(getComputedStyle(workspace).getPropertyValue("--printer-lift-y")) || 0;
  const sourceY = mouthRect.top + liftY + mouthRect.height * 0.55;
  const layer = getPrinterDrawLayer();
  layer.innerHTML = "";

  targets.forEach((target, index) => {
    const rect = target.getBoundingClientRect();
    const targetX = rect.left + rect.width / 2;
    const targetY = rect.top;
    const laneX = clamp(targetX, mouthRect.left + 18, mouthRect.right - 18);
    const sourceX = laneX;
    const fromX = sourceX - targetX;
    const fromY = sourceY - targetY;
    const card = document.createElement("article");
    card.className = "printer-draw-card";
    card.innerHTML = printerDrawCardMarkup(index);
    card.style.left = `${Math.round(rect.left)}px`;
    card.style.top = `${Math.round(rect.top)}px`;
    card.style.width = `${Math.round(rect.width)}px`;
    card.style.height = `${Math.round(rect.height)}px`;
    card.style.setProperty("--draw-delay", `${LAUNCH_PRINT_START_MS + index * LAUNCH_CARD_DELAY_MS}ms`);
    setLaunchVector(card, fromX, fromY);
    layer.appendChild(card);
    state.launchTimers.push(window.setTimeout(() => {
      target.classList.add("launch-card-settled");
    }, LAUNCH_PRINT_START_MS + index * LAUNCH_CARD_DELAY_MS + LAUNCH_CARD_LAND_MS - 120));
  });

  const removeDelay = LAUNCH_PRINT_START_MS + (targets.length - 1) * LAUNCH_CARD_DELAY_MS + LAUNCH_CARD_LAND_MS + 260;
  state.launchTimers.push(window.setTimeout(fadePrinterDrawLayer, removeDelay));
}

function getPrinterDrawLayer() {
  let layer = $("printerDrawLayer");
  if (!layer) {
    layer = document.createElement("div");
    layer.id = "printerDrawLayer";
    layer.className = "printer-draw-layer";
    layer.setAttribute("aria-hidden", "true");
    document.body.appendChild(layer);
  }
  return layer;
}

function clearPrinterDrawLayer() {
  const layer = $("printerDrawLayer");
  if (layer) layer.remove();
}

function fadePrinterDrawLayer() {
  const layer = $("printerDrawLayer");
  if (!layer) return;
  layer.classList.add("is-exiting");
  window.setTimeout(() => {
    if (layer.classList.contains("is-exiting")) layer.remove();
  }, 360);
}

function settleLaunchPlaceholders() {
  document.querySelectorAll(".launch-card-placeholder").forEach((card) => {
    card.classList.add("launch-card-settled");
  });
}

function printerDrawCardMarkup(index) {
  return `
    <div class="printer-draw-card-head">
      <strong>方案 ${String(index + 1).padStart(2, "0")}</strong>
      <span>待抽取</span>
    </div>
    <div class="printer-draw-card-face">
      <span>WildIdea</span>
      <i></i>
    </div>
    <div class="printer-draw-card-line"></div>
  `;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function setLaunchVector(card, fromX, fromY) {
  card.style.setProperty("--launch-from-x", `${Math.round(fromX)}px`);
  card.style.setProperty("--launch-from-y", `${Math.round(fromY)}px`);
}

function cancelSearchLaunch() {
  state.launchingSearch = false;
  state.searchOpen = true;
  clearLaunchTimers();
  clearLaunchTiming();
  renderShell();
}

function statusLabel(status) {
  const labels = {
    queued: "排队中",
    running: "生成中",
    succeeded: "已完成",
    failed: "失败",
    deleted: "已删除",
  };
  return labels[status] || status;
}

function progressStatusText(status) {
  const labels = {
    pending: "等待中",
    working: "生成中",
    checking: "校验中",
    done: "已完成",
    failed: "已保底",
  };
  return labels[status] || status;
}

function renderRuns() {
  const list = $("runList");
  const query = normalizeHistoryQuery(state.historyQuery);
  const visibleRuns = query ? state.runs.filter((run) => runMatchesHistoryQuery(run, query)) : state.runs;
  const signature = `${query}::${visibleRuns.map((run) => `${run.id}:${run.status}:${run.created_at}`).join("|")}`;
  const shouldAnimate = signature !== state.runListSignature;
  state.runListSignature = signature;
  list.classList.remove("run-list-arrive", "run-list-loading");
  list.innerHTML = "";
  if (!state.runs.length) {
    list.innerHTML = '<div class="muted">暂无历史任务</div>';
    if (shouldAnimate) requestAnimationFrame(() => list.classList.add("run-list-arrive"));
    return;
  }
  if (!visibleRuns.length) {
    list.innerHTML = '<div class="muted">没有匹配的历史任务</div>';
    if (shouldAnimate) requestAnimationFrame(() => list.classList.add("run-list-arrive"));
    return;
  }
  visibleRuns.forEach((run, index) => {
    const row = document.createElement("div");
    row.className = "run-row";
    row.style.setProperty("--run-delay", `${Math.min(index, 8) * 42}ms`);
    const btn = document.createElement("button");
    btn.className = `run-item ${run.id === state.currentRunId ? "active" : ""}`;
    btn.type = "button";
    btn.innerHTML = `<strong>${escapeHtml(run.problem)}</strong>${runHistoryMetaMarkup(run)}`;
    btn.addEventListener("click", () => selectRun(run.id));
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "run-delete";
    deleteBtn.type = "button";
    deleteBtn.title = "从历史中移除";
    deleteBtn.textContent = "删除";
    deleteBtn.addEventListener("click", () => deleteRun(run));
    row.append(btn, deleteBtn);
    list.appendChild(row);
  });
  if (shouldAnimate) requestAnimationFrame(() => list.classList.add("run-list-arrive"));
}

function runHistoryMetaMarkup(run) {
  const createdAt = run.created_at ? new Date(run.created_at).toLocaleString() : "";
  const isRunning = ["running", "queued"].includes(run.status);
  const statusText = run.status === "succeeded" ? "" : statusLabel(run.status);
  const text = [statusText, createdAt].filter(Boolean).join(" · ");
  return `
    <span class="run-meta muted">
      ${isRunning ? '<span class="run-spinner" aria-hidden="true"></span>' : ""}
      <span>${escapeHtml(text || createdAt)}</span>
    </span>
  `;
}

function normalizeHistoryQuery(value) {
  return String(value || "").trim().toLowerCase();
}

function runMatchesHistoryQuery(run, query) {
  const createdAt = run.created_at ? new Date(run.created_at).toLocaleString() : "";
  const haystack = [
    run.problem,
    run.problem_type,
    run.status,
    statusLabel(run.status),
    createdAt,
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query);
}

async function deleteRun(run) {
  if (!confirm(`删除这条历史任务？\n\n${run.problem}`)) return;
  try {
    await api(`/api/runs/${run.id}`, { method: "DELETE" });
    if (state.currentRunId === run.id) {
      state.currentRunId = null;
      state.searchOpen = true;
      stopWatching();
      renderCurrentRun(null);
      renderShell();
    }
    await loadRuns();
    showToast("已从历史中删除");
  } catch (err) {
    showToast(err.message);
  }
}

function progressLine(run) {
  if (!run) return "";
  if (run.status === "failed") return `任务失败：${run.error || "未知错误"}。积分已自动退回。`;
  if (run.status === "succeeded") {
    const refund = latestRefundEvent(run.events || []);
    const refundText = refund ? `未通过质量上限的卡已退回 ${refund.credits} 积分。` : "";
    return `生成完成，共 ${run.candidates?.length || 0} 条候选。${refundText}`;
  }
  if (run.status === "queued") return queuedSummary(run);
  if (run.status === "running") return runningSummary(run.events || [], run.config_snapshot || {});
  return "任务已提交，等待执行。";
}

function queuedSummary(run) {
  const queue = run.queue || {};
  const waitText = run.created_at ? formatChineseDuration(elapsedMs(Date.parse(run.created_at))) : "--";
  const usersAhead = Number(queue.users_ahead || 0);
  const tasksAhead = Number(queue.tasks_ahead || 0);
  const runningAhead = Number(queue.running_ahead || 0);
  const queuedAhead = Number(queue.queued_ahead || 0);
  const cardsAhead = Number(queue.cards_ahead || 0);
  const runningCards = Number(queue.running_cards || 0);
  const queuedAheadCards = Number(queue.queued_ahead_cards || 0);
  const requestedCards = Number(queue.requested_cards || 0);
  const cardCapacity = Number(queue.card_capacity || 50);
  const estimateText = formatQueueEstimate(queueRemainingSeconds(queue));
  const aheadText = usersAhead > 0
    ? `前面还有 ${usersAhead} 位用户、${cardsAhead} 张卡`
    : (cardsAhead > 0 ? `前面还有 ${cardsAhead} 张卡` : "前面没有其他用户");
  const detailText = tasksAhead > 0
    ? `当前生成中 ${runningCards}/${cardCapacity} 张卡，前序排队 ${queuedAheadCards} 张卡。`
    : `当前生成中 ${runningCards}/${cardCapacity} 张卡，你这次需要 ${requestedCards || "若干"} 张卡。`;
  const workerText = queue.worker_online === false ? "当前 worker 暂未上报心跳，系统会在接管后继续推进。" : "";
  return `已等待 ${waitText} · ${aheadText}。预计等待约 ${estimateText}。${detailText}${workerText}`;
}

function queueRemainingSeconds(queue = {}) {
  if (queue.estimated_wait_seconds === null || queue.estimated_wait_seconds === undefined) return null;
  const estimated = Number(queue.estimated_wait_seconds);
  if (!Number.isFinite(estimated)) return null;
  if (queue.worker_online === false) return Math.max(0, estimated);
  const calculatedAt = Date.parse(queue.calculated_at || "");
  if (!Number.isFinite(calculatedAt)) return Math.max(0, estimated);
  return Math.max(0, estimated - Math.floor(elapsedMs(calculatedAt) / 1000));
}

function formatQueueEstimate(seconds) {
  if (seconds === null || seconds === undefined) return "暂无法估计";
  if (seconds <= 30) return "不到 1 分钟";
  return formatEstimate(seconds);
}

function runningSummary(events, config = {}) {
  const target = config.slot_count || DEFAULT_SLOT_COUNT;
  const ok = events.filter((event) => ["candidate_ok", "candidate_fallback"].includes(event.event_type)).length;
  const startedAt = runStartMs(events);
  const elapsedText = startedAt ? formatChineseDuration(elapsedMs(startedAt)) : "--";
  if (config.fake_runs) {
    const fakeSeconds = Number(config.fake_run_seconds || 10);
    const estimateText = fakeSeconds < 60 ? `${Math.ceil(fakeSeconds)} 秒` : formatEstimate(fakeSeconds);
    if (!events.some((event) => event.event_type === "generating")) {
      return `已用时 ${elapsedText} · fake 测试模式正在抽取他山之石，预计共需约 ${estimateText}。`;
    }
    return `已用时 ${elapsedText} · fake 测试模式正在生成进度，已得到 ${ok}/${target} 条候选。预计共需约 ${estimateText}。`;
  }
  const maxRetries = config.max_retries || 3;
  const maxRerolls = Math.max(0, maxRetries - 1);
  const estimateText = "90 秒";
  if (!events.some((event) => event.event_type === "generating")) {
    return `已用时 ${elapsedText} · 正在抽取他山之石并准备生成，目标 ${target} 张卡片。预计共需约 ${estimateText}；并行生成，每张卡大约 90 秒。为保证质量可能重抽，触达上限仍不通过会退回该卡积分。`;
  }
  return `已用时 ${elapsedText} · 正在生成和评分，已得到 ${ok}/${target} 条候选。预计共需约 ${estimateText}；并行生成，每张卡大约 90 秒，最多重抽 ${maxRerolls} 次。系统会为了保证结果质量自动重抽，触达上限仍不通过会退回该卡积分。`;
}

function formatEstimate(seconds) {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  if (minutes < 3) return `${minutes} 分钟`;
  const rounded = Math.ceil(minutes / 5) * 5;
  return `${rounded} 分钟`;
}

function runStartMs(events) {
  const firstRuntimeEvent = events.find((event) => ["status", "type", "slots_done", "generating"].includes(event.event_type));
  return eventTimeMs(firstRuntimeEvent);
}

function latestRefundEvent(events) {
  const refund = [...events].reverse().find((event) => event.event_type === "refund" && event.payload?.reason === "partial_card_refund");
  return refund?.payload || null;
}

function renderCurrentRun(run) {
  const grid = $("candidateGrid");
  if (!run) {
    stopRuntimeTicker();
    $("currentRunTitle").textContent = "还没有选择任务";
    $("currentRunMeta").textContent = "";
    $("resultSection").dataset.activeRunStatus = "";
    $("resultSection").dataset.activeRunSnapshot = "{}";
    $("progressLog").innerHTML = "";
    grid.classList.remove("launch-landing-grid", "compact-card-grid", "result-card-grid");
    grid.innerHTML = "";
    return;
  }
  const compactGrid = run.status === "running" || run.status === "queued" || (run.status === "succeeded" && (run.candidates || []).length > 0);
  grid.classList.toggle("compact-card-grid", compactGrid);
  if (!compactGrid) grid.classList.remove("launch-landing-grid");
  const section = $("resultSection");
  const prevRunId = section.dataset.activeRunId || "";
  const prevStatus = section.dataset.activeRunStatus || "";
  $("currentRunTitle").textContent = run.problem;
  $("currentRunMeta").textContent = `${statusLabel(run.status)} · ${run.problem_type || "待判断"} · ${new Date(run.created_at).toLocaleString()}`;
  section.dataset.activeRunId = String(run.id);
  section.dataset.activeRunStatus = run.status || "";
  section.dataset.activeRunSnapshot = JSON.stringify(run.config_snapshot || {});
  $("progressLog").innerHTML = `<div class="progress-item" id="runProgressSummary">${escapeHtml(progressLine(run))}</div>`;
  const summary = $("runProgressSummary");
  if (summary) {
    summary.dataset.events = JSON.stringify(run.events || []);
    summary.dataset.queue = JSON.stringify(run.queue || {});
    summary.dataset.runCreatedAt = run.created_at || "";
  }
  if (run.status === "running" || run.status === "queued") {
    ensureRuntimeTicker();
  } else {
    stopRuntimeTicker();
  }
  if (run.status === "succeeded" && (run.candidates || []).length) {
    const watchedToCompletion = prevRunId === String(run.id) && (prevStatus === "running" || prevStatus === "queued");
    renderCandidates(run.candidates || [], run.events || [], { celebrate: watchedToCompletion });
  } else {
    renderSlotProgress(run.events || [], run.config_snapshot?.slot_count || DEFAULT_SLOT_COUNT, run.candidates || []);
  }
}

function renderSlotProgress(events, target, candidates = []) {
  const grid = $("candidateGrid");
  const slotsDone = events.find((event) => event.event_type === "slots_done");
  const slots = slotsDone?.payload?.slots || [];
  if (!slots.length) {
    grid.classList.remove("result-card-grid");
    if (state.suppressProgressAnimationRunId === state.currentRunId && grid.querySelector(".launch-progress-card")) {
      return;
    }
    grid.innerHTML = "";
    delete grid.dataset.progressRun;
    renderDrawStage(grid, target, events);
    return;
  }
  grid.classList.remove("launch-landing-grid");
  const states = buildSlotStates(slots, events, candidates);
  const hasLiveResults = states.some((item) => item.candidate);
  grid.classList.toggle("result-card-grid", hasLiveResults);
  const isHandoffRender = state.suppressProgressAnimationRunId === state.currentRunId;
  const runKey = String(state.currentRunId || "draft");
  const hasPlaceholders = Boolean(grid.querySelector(".launch-card-placeholder"));
  if (grid.dataset.progressRun !== runKey && !(hasPlaceholders && isHandoffRender)) {
    grid.innerHTML = "";
  }
  grid.dataset.progressRun = runKey;
  grid.querySelectorAll(":scope > :not(.candidate):not(.pixel-frame)").forEach((el) => el.remove());
  const existing = gridCardChildren(grid);
  const existingBySlot = new Map();
  existing.forEach((card) => {
    if (card.dataset.slotId) existingBySlot.set(card.dataset.slotId, card);
  });
  const used = new Set();

  states.forEach((item, index) => {
    const slotKey = item.slot_id || `slot-${index}`;
    const animationKey = `${state.currentRunId || "draft"}:${item.slot_id || index}`;
    const current = existingBySlot.get(slotKey) || existing[index];
    if (item.candidate) {
      const card = renderLiveResultCard(item, index, current);
      used.add(card);
      placeCardAtIndex(grid, card, index);
      return;
    }
    if (current && current.classList.contains("progress-card")) {
      const adopting = current.classList.contains("launch-card-placeholder");
      current.dataset.slotId = slotKey;
      state.animatedProgressCards.add(animationKey);
      morphProgressCard(current, item, adopting ? Math.min(index, 9) * 70 : 0);
      used.add(current);
      placeCardAtIndex(grid, current, index);
      return;
    }
    const card = document.createElement("article");
    card.className = `candidate progress-card ${item.status}`;
    card.dataset.slotId = slotKey;
    if (isHandoffRender) {
      state.animatedProgressCards.add(animationKey);
    } else if (!state.animatedProgressCards.has(animationKey)) {
      state.animatedProgressCards.add(animationKey);
      const drawDelay = Math.min(index, 9) * DRAW_CARD_DELAY_MS;
      card.classList.add("draw-enter");
      card.style.setProperty("--draw-delay", `${drawDelay}ms`);
      window.setTimeout(() => card.classList.remove("draw-enter"), drawDelay + 2950);
    }
    card.innerHTML = progressCardMarkup(item, index);
    card.dataset.slotSig = formatSlotBadge(item.slot, item.domain);
    const stats = card.querySelector(".slot-stats");
    if (stats) stats.dataset.sig = slotStatsSignature(item);
    const stream = card.querySelector(".card-stream");
    if (stream) stream.dataset.sig = streamSignature(item);
    if (current) current.replaceWith(card);
    else grid.appendChild(card);
    used.add(card);
    placeCardAtIndex(grid, card, index);
  });

  existing.forEach((card) => {
    if (!used.has(card)) card.remove();
  });
  scheduleFitText(grid);
}

function placeCardAtIndex(grid, card, index) {
  const cards = gridCardChildren(grid).filter((item) => item !== card);
  const anchor = cards[index] || null;
  if (card.parentElement !== grid) {
    grid.insertBefore(card, anchor);
  } else if (anchor && anchor.previousElementSibling !== card) {
    grid.insertBefore(card, anchor);
  }
}

function gridCardChildren(grid) {
  return Array.from(grid.querySelectorAll(":scope > .candidate, :scope > .pixel-frame"));
}

function liveResultSignature(item, index) {
  const candidate = item.candidate || {};
  return JSON.stringify([
    index,
    candidate.id || "",
    candidate.name || "",
    candidate.source || "",
    candidate.proto || "",
    candidate.advantage || "",
    candidate.desc || "",
    candidate.quality_status || "",
    candidate.refund_credit || false,
    candidate.feedback?.label || "",
    candidate.feedback?.comment || "",
    item.finishedAt || "",
    item.rerollCount || 0,
  ]);
}

function renderLiveResultCard(item, index, current) {
  const slotKey = item.slot_id || `slot-${index}`;
  const candidate = {
    ...item.candidate,
    index: index + 1,
    slot: item.candidate?.slot || item.slot,
    reroll_count: item.candidate?.reroll_count ?? item.rerollCount ?? 0,
  };
  const slotInfo = {
    ...(item.slotInfo || {}),
    domain: item.domain || item.slotInfo?.domain || "",
    source: item.source || item.slotInfo?.source || "",
    rerollCount: item.rerollCount || 0,
  };
  const signature = liveResultSignature({ ...item, candidate }, index);
  const currentCard = current?.classList.contains("pixel-frame")
    ? current.querySelector(":scope > .result-card")
    : current;
  if (currentCard?.classList.contains("result-card") && currentCard.dataset.resultSig === signature) {
    current.dataset.slotId = slotKey;
    current.dataset.resultSig = signature;
    currentCard.dataset.slotId = slotKey;
    return current;
  }
  const card = renderCandidateArticle(candidate, slotInfo, {
    feedback: Boolean(candidate.id),
    featured: false,
    index: index + 1,
    runtime: runtimeMeta(item),
  });
  card.dataset.slotId = slotKey;
  card.dataset.resultSig = signature;
  card.classList.add("partial-result-card");
  const frame = document.createElement("div");
  frame.className = "pixel-frame partial-result-frame";
  frame.dataset.slotId = slotKey;
  frame.dataset.resultSig = signature;
  frame.appendChild(card);
  if (!currentCard?.classList.contains("result-card")) {
    card.classList.add("result-reveal");
    card.style.setProperty("--reveal-delay", "0ms");
    frame.classList.add("result-reveal");
    frame.style.setProperty("--reveal-delay", "0ms");
  }
  if (current) current.replaceWith(frame);
  return frame;
}

function progressCardMarkup(item, index) {
  const previewSlotLabel = formatSlotBadge(item.slot, item.domain);
  const previewSource = item.source || item.title || item.domain || "等待他山之石";
  return `
    <div class="slot-preview" aria-hidden="true">
      <span>${escapeHtml(previewSlotLabel)}</span>
      <strong>${escapeHtml(previewSource)}</strong>
    </div>
    <div class="candidate-top" data-fit-container>
      <div class="candidate-title-block">
        <div class="candidate-meta-row">
          <span class="candidate-index">方案 ${String(index + 1).padStart(2, "0")}</span>
          <span class="progress-status-badge ${item.status}">${progressStatusText(item.status)}</span>
        </div>
        <h3 data-fit-text data-fit-min="10">${escapeHtml(item.title)}</h3>
        <span class="muted">${escapeHtml(item.domain)}</span>
      </div>
      ${slotBadgeMarkup(item.slot, item.domain)}
    </div>
    <div class="progress-track"><span style="width:${item.percent}%"></span></div>
    <p data-fit-text data-fit-min="7.4">${escapeHtml(item.message)}</p>
    ${slotStatsMarkup(item)}
    <div class="card-stream">${streamMarkup(item)}</div>
    <div class="step-row">
      <span class="${item.step >= 1 ? "done" : ""}">抽取</span>
      <span class="${item.step >= 2 ? "done" : ""}">生成</span>
      <span class="${item.step >= 3 ? "done" : ""}">校验</span>
      <span class="${item.step >= 4 ? "done" : ""}">完成</span>
    </div>
  `;
}

function streamMarkup(item) {
  const cursor = item.status === "working" || item.status === "checking" ? '<div class="stream-cursor">▌</div>' : "";
  return `${item.stream.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}${cursor}`;
}

function streamSignature(item) {
  return `${item.stream.join("¦")}|${item.status === "working" || item.status === "checking" ? "cursor" : ""}`;
}

function slotStatsSignature(item) {
  return `${item.startedAt || ""}|${item.finishedAt || ""}|${Number(item.rerollCount || 0)}|${item.apiStep || ""}`;
}

function swapText(el, text, delayMs = 0, animate = true) {
  if (!el) return;
  const next = String(text);
  if (el.textContent === next) return;
  el.textContent = next;
  el.classList.remove("text-swap");
  if (!animate) return;
  if (delayMs) el.style.setProperty("--swap-delay", `${delayMs}ms`);
  else el.style.removeProperty("--swap-delay");
  void el.offsetWidth;
  el.classList.add("text-swap");
}

function morphProgressCard(card, item, staggerMs = 0) {
  const animate = !card.classList.contains("draw-enter");
  card.classList.remove("launch-progress-card", "launch-card-placeholder", "launch-card-settled", "pending", "working", "checking", "done", "failed");
  card.classList.add(item.status);
  const badge = card.querySelector(".progress-status-badge");
  if (badge) {
    badge.classList.remove("pending", "working", "checking", "done", "failed");
    badge.classList.add(item.status);
    swapText(badge, progressStatusText(item.status), staggerMs, animate);
  }
  swapText(card.querySelector(".candidate-title-block h3"), item.title, staggerMs, animate);
  swapText(card.querySelector(".candidate-title-block > .muted"), item.domain, staggerMs, animate);
  const slotSig = formatSlotBadge(item.slot, item.domain);
  if (card.dataset.slotSig !== slotSig) {
    card.dataset.slotSig = slotSig;
    const top = card.querySelector(".candidate-top");
    const existingSlot = top?.querySelector(".slot");
    const markup = slotBadgeMarkup(item.slot, item.domain).trim();
    if (markup && top) {
      const tpl = document.createElement("template");
      tpl.innerHTML = markup;
      const next = tpl.content.firstElementChild;
      if (animate) {
        if (staggerMs) next.style.setProperty("--swap-delay", `${staggerMs}ms`);
        next.classList.add("text-swap");
      }
      if (existingSlot) existingSlot.replaceWith(next);
      else top.appendChild(next);
    } else if (existingSlot) {
      existingSlot.remove();
    }
  }
  const track = card.querySelector(".progress-track span");
  if (track) track.style.width = `${item.percent}%`;
  card.querySelector(":scope > p.proto")?.remove();
  swapText(card.querySelector(":scope > p"), item.message, staggerMs, animate);
  const stats = card.querySelector(".slot-stats");
  if (stats) {
    const sig = slotStatsSignature(item);
    if (stats.dataset.sig !== sig) {
      stats.dataset.sig = sig;
      stats.innerHTML = slotStatsInner(item);
    }
  }
  const stream = card.querySelector(".card-stream");
  if (stream) {
    const sig = streamSignature(item);
    if (stream.dataset.sig !== sig) {
      stream.dataset.sig = sig;
      stream.innerHTML = streamMarkup(item);
    }
  }
  card.querySelectorAll(".step-row span").forEach((span, stepIndex) => {
    span.classList.toggle("done", item.step >= stepIndex + 1);
  });
}

function renderDrawStage(grid, target, events) {
  const typeEvent = events.find((event) => event.event_type === "type");
  const running = events.find((event) => event.event_type === "status" && event.payload?.status === "running");
  const stage = document.createElement("section");
  stage.className = "draw-stage";
  stage.innerHTML = `
    <div class="draw-deck" aria-hidden="true">
      <span></span>
      <span></span>
      <span></span>
    </div>
    <div class="draw-copy">
      <span class="eyebrow">抽卡中</span>
      <strong>正在从卡池里抽取 ${target} 张灵感卡</strong>
      <p>${escapeHtml(typeEvent ? `已识别为 ${typeEvent.payload?.value || "product"} 类型，正在洗牌匹配他山之石。` : (running ? "模型工人已启动，正在抽槽位。" : "任务已进入队列，准备发牌。"))}</p>
      <div class="draw-slots">
        ${Array.from({ length: target }, (_, index) => `<i style="--draw-delay:${Math.min(index, 9) * DRAW_CARD_DELAY_MS}ms"></i>`).join("")}
      </div>
    </div>
  `;
  grid.appendChild(stage);
}

function buildSlotStates(slots, events, candidates = []) {
  const byId = new Map();
  const slotsDoneAt = eventTimeMs(events.find((event) => event.event_type === "slots_done"));
  const persistedByIndex = new Map();
  const persistedByName = new Map();
  candidates.forEach((candidate) => {
    persistedByIndex.set(Number(candidate.index), candidate);
    persistedByName.set(candidate.name, candidate);
  });
  slots.forEach((slot) => {
    byId.set(slot.slot_id, {
      slot_id: slot.slot_id,
      slot: slot.slot,
      domain: slot.domain,
      source: slot.source,
      title: slot.source || slot.domain || "待开始",
      slotInfo: {
        domain: slot.domain,
        source: slot.source,
        sourcePhenomenon: slot.source_phenomenon || slot.source,
      },
      status: "pending",
      step: 1,
      percent: 18,
      message: "槽位已抽取，等待开始生成。",
      startedAt: slotsDoneAt,
      finishedAt: null,
      attempt: 0,
      rerollCount: 0,
      apiStep: "等待生成",
      history: [],
      stream: [
        "> slot picked",
        `> source: ${slot.domain || slot.slot || "-"}`,
        "> waiting for worker",
      ],
    });
  });

  const nameToSlotId = new Map();
  events.forEach((event) => {
    const payload = event.payload || {};
    if (["candidate_ok", "candidate_fallback"].includes(event.event_type) && payload.name && payload.slot_id) {
      nameToSlotId.set(payload.name, payload.slot_id);
    }
    const id = payload.slot_id || nameToSlotId.get(payload.name);
    if (!id || !byId.has(id)) return;
    const item = byId.get(id);
    const eventAt = eventTimeMs(event);
    if (event.event_type === "generating") {
      item.status = "working";
      item.step = 2;
      item.percent = 45;
      item.startedAt = item.startedAt || eventAt;
      item.attempt = Number(payload.attempt || item.attempt || 1);
      item.apiStep = "生成 API";
      item.message = `正在分析中${waitingDots()}`;
      const recentHistory = item.history.slice(-3);
      item.stream = [
        ...recentHistory,
        "> worker attached",
        "> source mechanism locked",
        "> mapping to your photo app problem",
        `> model thinking${waitingDots()}`,
      ];
    } else if (event.event_type === "invalid") {
      item.status = "checking";
      item.step = 3;
      item.percent = 62;
      item.apiStep = "基础校验";
      item.message = `结构校验未通过，正在重试。${(payload.errors || []).join("；")}`;
      item.history.push("> validation failed, retrying");
      item.stream = [
        "> draft received",
        "> validation failed",
        ...((payload.errors || []).slice(0, 2).map((err) => `> ${err}`)),
        "> retrying",
      ];
    } else if (["candidate_ok", "candidate_fallback"].includes(event.event_type)) {
      const isFallback = event.event_type === "candidate_fallback" || payload.quality_status === "fallback_refunded";
      item.status = isFallback ? "failed" : "done";
      item.step = 4;
      item.percent = 100;
      item.title = payload.name || item.title;
      item.finishedAt = eventAt;
      item.attempt = Number(payload.attempt || item.attempt || 1);
      item.rerollCount = Number(payload.reroll_count ?? item.rerollCount ?? 0);
      item.apiStep = isFallback ? "已退款" : "已通过";
      item.message = isFallback ? "已展示均分最高版本；未通过质量阈值，已退回该卡积分。" : "候选已通过基础校验和评分阈值。";
      const liveCandidate = {
        index: payload.index || payload.done,
        name: payload.name || item.title,
        slot: payload.slot || item.slot,
        source: payload.source || "",
        proto: payload.proto || "",
        advantage: payload.advantage || "",
        desc: payload.desc || "",
        fail: payload.fail || "",
        reroll_count: payload.reroll_count ?? item.rerollCount ?? 0,
        quality_status: payload.quality_status || (isFallback ? "fallback_refunded" : "passed"),
        refund_credit: Boolean(payload.refund_credit || isFallback),
        quality_note: payload.quality_note || "",
        score_average: payload.score_average,
        search: payload.search || {},
        scores: payload.scores || {},
      };
      const persisted = persistedByIndex.get(Number(liveCandidate.index)) || persistedByName.get(liveCandidate.name);
      item.candidate = persisted ? {
        ...liveCandidate,
        ...persisted,
        scores: persisted.scores || liveCandidate.scores,
        reroll_count: persisted.reroll_count ?? liveCandidate.reroll_count,
      } : liveCandidate;
      item.stream = [
        ...item.history.slice(-2),
        "> draft received",
        "> structure check passed",
        isFallback ? "> quality gate not passed" : "> quality gate passed",
        ...(isFallback ? ["> best available draft shown", "> this card credit refunded"] : []),
        `> candidate: ${payload.name || "ready"}`,
      ];
    } else if (event.event_type === "judging") {
      item.status = "checking";
      item.step = 3;
      item.percent = 72;
      item.title = payload.name || item.title;
      item.startedAt = item.startedAt || eventAt;
      item.attempt = Number(payload.attempt || item.attempt || 1);
      item.apiStep = "评分 API";
      item.message = "候选已进入独立评分，正在检查结构分、新颖度和可用性。";
      item.stream = [
        `> candidate: ${payload.name || item.title}`,
        "> judge scoring",
        `> evaluating structural depth${waitingDots()}`,
        `> evaluating novelty${waitingDots()}`,
        `> evaluating applicability${waitingDots()}`,
      ];
    } else if (event.event_type === "judged") {
      item.status = payload.pass === false ? "checking" : "done";
      item.step = payload.pass === false ? 3 : 4;
      item.percent = payload.pass === false ? 78 : 96;
      item.title = payload.name || item.title;
      item.apiStep = payload.pass === false ? "评分未过" : "评分通过";
      item.message = payload.pass === false
        ? `评分未过阈值：结构 ${payload.sd ?? "-"}/${payload.sd_threshold ?? "-"} · 新颖 ${payload.nv ?? "-"}/${payload.novelty_threshold ?? "-"} · 可用 ${payload.ap ?? "-"}/${payload.applicability_threshold ?? "-"}`
        : `评分通过：结构 ${payload.sd ?? "-"} · 新颖 ${payload.nv ?? "-"} · 可用 ${payload.ap ?? "-"}`;
      item.stream = [
        `> candidate: ${payload.name || item.title}`,
        `> structural depth: ${payload.sd ?? "-"} / ${payload.sd_threshold ?? "-"}`,
        `> novelty: ${payload.nv ?? "-"} / ${payload.novelty_threshold ?? "-"}`,
        `> applicability: ${payload.ap ?? "-"} / ${payload.applicability_threshold ?? "-"}`,
        payload.pass === false ? "> below gate, reroll queued" : "> quality gate passed",
      ];
    } else if (event.event_type === "threshold_rejected") {
      item.status = "checking";
      item.step = 3;
      item.percent = 66;
      item.title = payload.name || item.title;
      item.rerollCount = Math.max(Number(item.rerollCount || 0) + 1, Number(payload.attempt || 0));
      item.attempt = Number(payload.attempt || item.attempt || 1);
      item.apiStep = "重抽排队";
      item.message = `评分未过阈值，正在重抽。已重抽 ${item.rerollCount} 次。结构 ${payload.sd ?? "-"}/${payload.sd_threshold ?? "-"} · 新颖 ${payload.nv ?? "-"}/${payload.novelty_threshold ?? "-"} · 可用 ${payload.ap ?? "-"}/${payload.applicability_threshold ?? "-"}`;
      item.history.push(`> reroll ${item.rerollCount}: SD ${payload.sd ?? "-"} / ${payload.sd_threshold ?? "-"} · NV ${payload.nv ?? "-"} / ${payload.novelty_threshold ?? "-"} · AP ${payload.ap ?? "-"} / ${payload.applicability_threshold ?? "-"}`);
      item.stream = [
        `> rejected: ${payload.name || item.title}`,
        `> structural depth ${payload.sd ?? "-"} / ${payload.sd_threshold ?? "-"}`,
        `> novelty ${payload.nv ?? "-"} / ${payload.novelty_threshold ?? "-"}`,
        `> applicability ${payload.ap ?? "-"} / ${payload.applicability_threshold ?? "-"}`,
        "> reroll queued",
      ];
    } else if (event.event_type === "judge_fail") {
      item.status = "checking";
      item.step = 3;
      item.percent = 64;
      item.apiStep = "评分重试";
      item.message = `评分失败，正在重试。${payload.error || ""}`;
      item.history.push("> judge failed, retrying");
      item.stream = [
        `> candidate: ${payload.name || item.title}`,
        "> judge failed",
        `> ${payload.error || "retrying"}`,
      ];
    } else if (event.event_type === "gen_fail") {
      item.status = "failed";
      item.step = 3;
      item.percent = 100;
      item.finishedAt = eventAt;
      item.apiStep = "已停止";
      item.message = "该卡已触达重抽上限，仍未通过质量阈值；最终结算时会退回这张卡的 1 积分。";
      item.stream = [
        "> reroll limit reached",
        "> quality gate still not passed",
        "> this card credit will be refunded",
      ];
    }
  });

  return Array.from(byId.values()).map((item) => ({
    ...item,
    elapsedMs: elapsedMs(item.startedAt, item.finishedAt),
  }));
}

function waitingDots() {
  return ".".repeat((Math.floor(Date.now() / 700) % 3) + 1);
}

function eventTimeMs(event) {
  const parsed = Date.parse(event?.created_at || "");
  return Number.isFinite(parsed) ? parsed : null;
}

function elapsedMs(start, finish = null) {
  if (!start) return null;
  return Math.max(0, (finish || Date.now()) - start);
}

function formatDuration(ms) {
  if (ms === null || ms === undefined) return "--";
  const seconds = Math.max(0, Math.floor(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

function formatChineseDuration(ms) {
  if (ms === null || ms === undefined) return "--";
  const seconds = Math.max(0, Math.floor(ms / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes} 分 ${String(rest).padStart(2, "0")} 秒`;
}

function runtimeMeta(item) {
  return {
    start: item.startedAt,
    finish: item.finishedAt,
    elapsedText: formatDuration(item.elapsedMs),
    apiStep: item.apiStep || "已通过",
  };
}

function slotStatsInner(item) {
  const runtime = runtimeMeta(item);
  return `
    <span><small>耗时</small><strong class="runtime-value" data-start-ms="${runtime.start || ""}" data-finish-ms="${runtime.finish || ""}">${escapeHtml(runtime.elapsedText)}</strong></span>
    <span><small>重抽</small><strong>${Number(item.rerollCount || 0)}</strong></span>
    <span><small>API</small><strong>${escapeHtml(item.apiStep || "等待生成")}</strong></span>
  `;
}

function slotStatsMarkup(item) {
  return `<div class="slot-stats">${slotStatsInner(item)}</div>`;
}

function updateRuntimeLabels() {
  document.querySelectorAll(".runtime-value[data-start-ms]").forEach((node) => {
    const start = Number(node.dataset.startMs || 0);
    const finish = Number(node.dataset.finishMs || 0);
    if (!start) return;
    node.textContent = formatDuration(elapsedMs(start, finish || null));
  });
  updateRunProgressTimer();
}

function updateRunProgressTimer() {
  const summary = $("runProgressSummary");
  if (!summary) return;
  const status = $("resultSection").dataset.activeRunStatus;
  try {
    if (status === "running") {
      const events = JSON.parse(summary.dataset.events || "[]");
      const config = JSON.parse($("resultSection").dataset.activeRunSnapshot || "{}");
      summary.textContent = runningSummary(events, config);
    } else if (status === "queued") {
      const queue = JSON.parse(summary.dataset.queue || "{}");
      const createdAt = summary.dataset.runCreatedAt || "";
      summary.textContent = queuedSummary({ status: "queued", queue, created_at: createdAt });
    }
  } catch {
    return;
  }
}

function ensureRuntimeTicker() {
  if (state.runtimeTimer) return;
  state.runtimeTimer = setInterval(updateRuntimeLabels, 1000);
}

function stopRuntimeTicker() {
  if (!state.runtimeTimer) return;
  clearInterval(state.runtimeTimer);
  state.runtimeTimer = null;
}

function renderCandidateArticle(candidate, slotInfo = {}, options = {}) {
  const field = slotInfo.domain || candidate.source;
  const sourcePhenomenon = sourcePhenomenonText(slotInfo, candidate);
  const index = options.index ?? candidate.index ?? 1;
  const showFeedback = options.feedback !== false && candidate.id;
  const rerollCount = Number(candidate.reroll_count ?? candidate.rerollCount ?? slotInfo.rerollCount ?? 0);
  const qualityStatus = candidate.quality_status || candidate.search?.quality_status || "passed";
  const isFallback = Boolean(candidate.refund_credit || candidate.search?.refund_credit || qualityStatus === "fallback_refunded");
  const qualityNote = candidate.quality_note || candidate.search?.quality_note || "这张卡未通过质量阈值，系统已退回该卡积分。";
  const runtime = options.runtime || {};
  const fallbackBadgeText = rerollCount > 0 ? `重抽 ${rerollCount} 次 · 已退款` : "未达标 · 已退款";
  const showRuntimeBadge = Boolean(runtime.elapsedText && !isFallback);
  const advantage = normalizeAdvantage(candidate.advantage);
  const sourceCopyText = [
    "他山之石",
    sourcePhenomenon,
    "",
    "抽象方法",
    candidate.source,
    candidate.proto,
  ].filter((line) => line !== null && line !== undefined).join("\n").trim();
  const ideaCopyText = ["落地方案", candidate.desc].filter(Boolean).join("\n").trim();
  const advantageCopyText = advantage ? ["优势", advantage].join("\n").trim() : "";
  const sourceHoverText = [
    `他山之石：${sourcePhenomenon}`,
    candidate.source ? `抽象方法：${candidate.source}` : "",
    candidate.proto ? candidate.proto : "",
  ].filter(Boolean).join("\n\n").trim();
  const ideaHoverText = String(candidate.desc || "").trim();
  const advantageHoverText = String(advantage || "").trim();
  const posterContext = {
    ...candidate,
    index,
    field,
    sourcePhenomenon,
    slotLabel: formatSlotBadge(candidate.slot, field),
    reroll_count: rerollCount,
    quality_status: qualityStatus,
    refund_credit: isFallback,
    quality_note: qualityNote,
    advantage,
    runProblem: $("currentRunTitle")?.textContent || "",
    runMeta: $("currentRunMeta")?.textContent || "",
  };
  const card = document.createElement("article");
  card.className = `candidate result-card${isFallback ? " quality-fallback" : ""}${options.featured ? " featured-card" : ""}`;
  card.innerHTML = `
    <div class="candidate-top" data-fit-container>
      <div class="candidate-title-block">
        <div class="candidate-meta-row">
          <span class="candidate-index">方案 ${String(index).padStart(2, "0")}</span>
          ${isFallback ? `<span class="quality-badge">${escapeHtml(fallbackBadgeText)}</span>` : ""}
          ${!isFallback && rerollCount > 0 ? `<span class="reroll-badge">重抽 ${rerollCount} 次</span>` : ""}
          ${showRuntimeBadge ? `<span class="runtime-badge"><span class="runtime-value" data-start-ms="${runtime.start || ""}" data-finish-ms="${runtime.finish || ""}">${escapeHtml(runtime.elapsedText)}</span> · ${escapeHtml(runtime.apiStep || "已通过")}</span>` : ""}
        </div>
        <h3>${escapeHtml(candidate.name)}</h3>
        ${field ? `<span class="muted" data-fit-text data-fit-min="7.2">源自 ${escapeHtml(field)}</span>` : ""}
      </div>
      ${slotBadgeMarkup(candidate.slot, field)}
    </div>
    <div class="result-card-body">
      <section class="candidate-section source-section copyable-section" data-fit-container data-copy-text="${escapeHtml(sourceCopyText)}" data-full-text="${escapeHtml(sourceHoverText)}" role="button" tabindex="0" aria-label="将他山之石和抽象方法放入剪贴板">
        <div class="section-label">他山之石</div>
        <p class="source-phenomenon" data-fit-text data-fit-min="6.8">${escapeHtml(sourcePhenomenon)}</p>
        <div class="source-method">
          <span>抽象方法</span>
          <strong>${escapeHtml(candidate.source)}</strong>
        </div>
        <p class="proto">${escapeHtml(candidate.proto)}</p>
      </section>
      <section class="candidate-section idea-section copyable-section" data-fit-container data-copy-text="${escapeHtml(ideaCopyText)}" data-full-text="${escapeHtml(ideaHoverText)}" role="button" tabindex="0" aria-label="将落地方案放入剪贴板">
        <div class="section-label">落地方案</div>
        <p class="desc" data-fit-text data-fit-min="6.8">${escapeHtml(candidate.desc)}</p>
      </section>
      ${advantage ? `
        <section class="candidate-section advantage-section copyable-section" data-fit-container data-copy-text="${escapeHtml(advantageCopyText)}" data-full-text="${escapeHtml(advantageHoverText)}" role="button" tabindex="0" aria-label="将优势放入剪贴板">
          <div class="section-label">优势</div>
          <p class="advantage" data-fit-text data-fit-min="6.8">${escapeHtml(advantage)}</p>
        </section>
      ` : ""}
      <details class="mobile-card-details">
        <summary>更多细节</summary>
        <div>
          <span>抽象方法</span>
          <strong>${escapeHtml(candidate.source)}</strong>
          <p>${escapeHtml(candidate.proto)}</p>
        </div>
      </details>
    </div>
    ${!showFeedback ? `
      <div class="candidate-actions">
        <button type="button" class="share-card-button" data-action="poster" aria-label="分享该卡" title="分享该卡">
          <span class="share-logo-glyph" aria-hidden="true"></span>
        </button>
      </div>
    ` : ""}
    ${showFeedback ? `
      <div class="card-response-row">
        <div class="feedback-block">
          <div class="feedback-prompt">
            <strong>这张卡有启发吗？</strong>
            <span>点一下反馈，下一轮抽卡会更懂你</span>
          </div>
          <div class="feedback-row">
            <button type="button" class="feedback-useful" data-label="useful" aria-pressed="false">有用</button>
            <button type="button" class="feedback-weak" data-action="show-weak" aria-expanded="false">没用</button>
          </div>
          <div class="weak-feedback hidden">
            <button type="button" data-label="weak_obscure" aria-pressed="false">晦涩难懂</button>
            <button type="button" data-label="weak_off_topic" aria-pressed="false">不够相关</button>
            <button type="button" data-label="weak_too_common" aria-pressed="false">太常规</button>
            <button type="button" data-label="weak_unusable" aria-pressed="false">不可落地</button>
            <form class="weak-other-form">
              <input type="text" name="comment" placeholder="其他原因">
              <button type="submit">其他提交</button>
            </form>
          </div>
        </div>
        <button type="button" class="share-card-button" data-action="poster" aria-label="分享该卡" title="分享该卡">
          <span class="share-logo-glyph" aria-hidden="true"></span>
        </button>
      </div>
    ` : ""}
  `;
  if (showFeedback) {
    card.dataset.feedbackPanelKey = String(candidate.id);
  }
  bindCopyableSections(card);
  card.querySelector('button[data-action="poster"]').addEventListener("click", () => openPoster(posterContext));
  if (showFeedback) {
    bindFeedbackControls(card, candidate);
  }
  return card;
}

function bindCopyableSections(card) {
  card.querySelectorAll(".copyable-section[data-copy-text]").forEach((section) => {
    section.addEventListener("mouseenter", (event) => showFullTextTooltip(section, event));
    section.addEventListener("mousemove", (event) => positionFullTextTooltip(event));
    section.addEventListener("mouseleave", hideFullTextTooltip);
    section.addEventListener("focus", () => showFullTextTooltip(section));
    section.addEventListener("blur", hideFullTextTooltip);
    section.addEventListener("click", (event) => {
      if (event.target.closest("button, input, textarea, a, summary")) return;
      if (window.getSelection?.().toString()) return;
      copySectionText(section);
    });
    section.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      copySectionText(section);
    });
  });
}

function getFullTextTooltip() {
  let tooltip = $("fullTextTooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.id = "fullTextTooltip";
    tooltip.className = "full-text-tooltip hidden";
    tooltip.setAttribute("role", "tooltip");
    document.body.appendChild(tooltip);
  }
  return tooltip;
}

function showFullTextTooltip(section, event = null) {
  const text = (section.dataset.fullText || section.dataset.copyText || "").trim();
  if (!text) return;
  const tooltip = getFullTextTooltip();
  tooltip.textContent = text;
  tooltip.classList.remove("hidden");
  if (event) {
    positionFullTextTooltip(event);
  } else {
    positionFullTextTooltipForElement(section);
  }
}

function hideFullTextTooltip() {
  const tooltip = $("fullTextTooltip");
  if (tooltip) tooltip.classList.add("hidden");
}

function positionFullTextTooltip(event) {
  const tooltip = $("fullTextTooltip");
  if (!tooltip || tooltip.classList.contains("hidden")) return;
  placeFullTextTooltip(event.clientX + 14, event.clientY + 14);
}

function positionFullTextTooltipForElement(element) {
  const rect = element.getBoundingClientRect();
  placeFullTextTooltip(rect.left + Math.min(20, rect.width / 2), rect.bottom + 10);
}

function placeFullTextTooltip(left, top) {
  const tooltip = $("fullTextTooltip");
  if (!tooltip) return;
  const margin = 12;
  const rect = tooltip.getBoundingClientRect();
  const maxLeft = window.innerWidth - rect.width - margin;
  const maxTop = window.innerHeight - rect.height - margin;
  tooltip.style.left = `${Math.max(margin, Math.min(left, maxLeft))}px`;
  tooltip.style.top = `${Math.max(margin, Math.min(top, maxTop))}px`;
}

async function copySectionText(section) {
  const text = section.dataset.copyText || section.innerText.trim();
  if (!text) return;
  const ok = await writeClipboardText(text);
  if (!ok) {
    showToast("未能写入剪贴板，请手动选择文字");
    return;
  }
  flashCopiedSection(section);
  showToast("已放入剪贴板");
}

async function writeClipboardText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy copy path.
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.left = "-9999px";
  input.style.top = "0";
  document.body.appendChild(input);
  input.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  input.remove();
  return copied;
}

function flashCopiedSection(section) {
  window.clearTimeout(section.__copyTimer);
  section.classList.add("copied", "copy-pressed");
  section.__copyTimer = window.setTimeout(() => {
    section.classList.remove("copied", "copy-pressed");
  }, 950);
}

function candidateScoreAverage(candidate) {
  const explicitAverage = Number(candidate.score_average ?? candidate.search?.score_average);
  if (Number.isFinite(explicitAverage)) return explicitAverage;
  const scores = candidate.scores || {};
  const values = [
    scores.structural_depth,
    scores.domain_distance,
    scores.novelty,
    scores.applicability,
  ].map(Number).filter(Number.isFinite);
  if (!values.length) return Number.NEGATIVE_INFINITY;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function candidateApplicability(candidate) {
  const value = Number(candidate.scores?.applicability);
  return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY;
}

function featuredCandidateKey(candidates) {
  let best = null;
  candidates.forEach((candidate, index) => {
    if (candidate.refund_credit || candidate.search?.refund_credit) return;
    const average = candidateScoreAverage(candidate);
    const applicability = candidateApplicability(candidate);
    if (!Number.isFinite(average) && !Number.isFinite(applicability)) return;
    const contender = { candidate, index, average, applicability };
    if (!best
      || contender.average > best.average
      || (contender.average === best.average && contender.applicability > best.applicability)) {
      best = contender;
    }
  });
  if (!best) return "";
  return best.candidate.id || `${best.index}:${best.candidate.name || ""}`;
}

function renderCandidates(candidates, events = [], options = {}) {
  const grid = $("candidateGrid");
  grid.classList.remove("launch-landing-grid");
  grid.classList.add("compact-card-grid", "result-card-grid");
  grid.innerHTML = "";
  if (!candidates.length) return;
  const candidateSlots = buildCandidateSlotMap(events);
  const featuredKey = featuredCandidateKey(candidates);
  candidates.forEach((candidate, index) => {
    const slotInfo = candidateSlots.get(candidate.name) || {};
    const candidateKey = candidate.id || `${index}:${candidate.name || ""}`;
    const isFeatured = candidateKey === featuredKey;
    const card = renderCandidateArticle(candidate, slotInfo, { feedback: true, featured: isFeatured });
    if (options.celebrate) {
      card.classList.add("result-reveal");
      card.style.setProperty("--reveal-delay", `${Math.min(index, 9) * 70}ms`);
    }
    const frame = document.createElement("div");
    frame.className = `pixel-frame${isFeatured ? " featured-frame" : ""}`;
    if (options.celebrate) {
      frame.classList.add("result-reveal");
      frame.style.setProperty("--reveal-delay", `${Math.min(index, 9) * 70}ms`);
    }
    frame.appendChild(card);
    grid.appendChild(frame);
  });
  scheduleFitText(grid);
}

function bindFeedbackControls(card, candidate) {
  card.querySelector('button[data-action="show-weak"]').addEventListener("click", () => {
    toggleWeakFeedback(card, card.querySelector(".weak-feedback")?.classList.contains("hidden"), { remember: true });
  });
  card.querySelectorAll('button[data-label]').forEach((btn) => {
    btn.addEventListener("click", () => submitFeedback(candidate, btn.dataset.label, card));
  });
  card.querySelector(".weak-other-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const comment = new FormData(event.currentTarget).get("comment");
    submitFeedback(candidate, "weak_other", card, String(comment || "").trim());
  });
  applyFeedbackState(card, candidate.feedback?.label);
}

function buildCandidateSlotMap(events) {
  const slotsById = new Map();
  const slotsByName = new Map();
  const rerollsBySlotId = new Map();
  const slotsDone = events.find((event) => event.event_type === "slots_done");
  (slotsDone?.payload?.slots || []).forEach((slot) => {
    slotsById.set(slot.slot_id, slot);
  });
  events.forEach((event) => {
    if (event.event_type === "threshold_rejected" && event.payload?.slot_id) {
      const slotId = event.payload.slot_id;
      rerollsBySlotId.set(slotId, (rerollsBySlotId.get(slotId) || 0) + 1);
      return;
    }
    if (!["candidate_ok", "candidate_fallback"].includes(event.event_type)) return;
    const payload = event.payload || {};
    if (!payload.name) return;
    const slot = slotsById.get(payload.slot_id);
    slotsByName.set(payload.name, {
      domain: slot?.domain || payload.source || "",
      source: slot?.source || payload.source || "",
      sourcePhenomenon: slot?.source_phenomenon || slot?.source || "",
      rerollCount: payload.reroll_count ?? rerollsBySlotId.get(payload.slot_id) ?? 0,
    });
  });
  return slotsByName;
}

function sourcePhenomenonText(slotInfo, candidate) {
  const value = slotInfo.sourcePhenomenon || slotInfo.source || "";
  if (value && !looksTruncatedSource(value)) return value;
  return candidate.source || value || "";
}

function looksTruncatedSource(value) {
  const text = String(value || "").trim();
  if (text.length < 80) return false;
  const lastWord = text.split(/\s+/).pop() || "";
  return /^[A-Za-z]{1,2}$/.test(lastWord);
}

function formatSlotBadge(slot, field) {
  const { code, label } = slotBadgeParts(slot, field);
  if (!code) return label || "";
  if (/^P\d+$/i.test(code) || !label || label === code) return code;
  return `${code} ${label}`;
}

function slotBadgeMarkup(slot, field) {
  const { code, label } = slotBadgeParts(slot, field);
  if (!code && !label) return "";
  const main = code || label;
  const sub = code && label && label !== code ? label : "";
  return `
    <span class="slot">
      <span class="slot-code">${escapeHtml(main)}</span>
      ${sub ? `<span class="slot-field">${escapeHtml(sub)}</span>` : ""}
    </span>
  `;
}

function slotBadgeParts(slot, field) {
  const rawSlot = String(slot || "").trim();
  return {
    code: displaySlotCode(rawSlot),
    label: displaySlotField(rawSlot, field),
  };
}

function displaySlotCode(slot) {
  const normalized = String(slot || "").trim().toUpperCase();
  if (normalized === "MAO") return "D6";
  if (normalized === "RANDOM_WORD") return "D7";
  return slot || "";
}

function displaySlotField(slot, field) {
  const normalized = String(slot || "").trim().toUpperCase();
  if (normalized === "MAO") return "毛选";
  if (normalized === "RANDOM_WORD") return "随机组词";
  const value = String(field || "").trim();
  if (value) return value;
  const fallback = {
    D1: "算法",
    D2: "学术",
    D3: "艺术",
    D4: "产品",
  };
  return fallback[normalized] || "";
}

function applyFeedbackState(card, label) {
  const weakSelected = isWeakFeedbackLabel(label);
  const usefulSelected = label === "useful";
  const weakToggle = card.querySelector('button[data-action="show-weak"]');
  if (weakToggle) {
    weakToggle.classList.toggle("selected", weakSelected);
    weakToggle.setAttribute("aria-pressed", weakSelected ? "true" : "false");
    weakToggle.setAttribute("aria-expanded", weakSelected ? "true" : "false");
  }
  card.querySelectorAll("button[data-label]").forEach((btn) => {
    const selected = btn.dataset.label === label;
    btn.classList.toggle("selected", selected);
    btn.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  const usefulButton = card.querySelector('button[data-label="useful"]');
  if (usefulButton) {
    usefulButton.classList.toggle("selected", usefulSelected);
    usefulButton.setAttribute("aria-pressed", usefulSelected ? "true" : "false");
  }
  const weakOtherInput = card.querySelector('.weak-other-form input[name="comment"]');
  if (weakOtherInput && label === "weak_other") {
    weakOtherInput.value = card.__lastWeakOtherComment || weakOtherInput.value;
  }
  toggleWeakFeedback(card, weakSelected && weakFeedbackPanelPreference(card) !== "closed");
}

function isWeakFeedbackLabel(label) {
  return Boolean(label && label !== "useful");
}

function weakFeedbackPanelPreference(card) {
  const key = card.dataset.feedbackPanelKey;
  if (!key) return "";
  try {
    return localStorage.getItem(`wildidea:weak-feedback-panel:${key}`) || "";
  } catch {
    return "";
  }
}

function rememberWeakFeedbackPanel(card, show) {
  const key = card.dataset.feedbackPanelKey;
  if (!key) return;
  try {
    localStorage.setItem(`wildidea:weak-feedback-panel:${key}`, show ? "open" : "closed");
  } catch {
    return;
  }
}

function toggleWeakFeedback(card, show, options = {}) {
  const weakPanel = card.querySelector(".weak-feedback");
  if (!weakPanel) return;
  weakPanel.classList.toggle("hidden", !show);
  if (options.remember) rememberWeakFeedbackPanel(card, show);
  const weakToggle = card.querySelector('button[data-action="show-weak"]');
  if (weakToggle) {
    weakToggle.setAttribute("aria-expanded", show ? "true" : "false");
    weakToggle.textContent = show ? "收起" : "没用";
  }
}

async function submitFeedback(candidate, label, card, comment = "") {
  if (label === "weak_other" && !comment) {
    showToast("请填写其他原因");
    return;
  }
  if (candidate.feedback?.label === label && (label !== "weak_other" || candidate.feedback?.comment === comment)) {
    showToast("这个反馈已记录");
    return;
  }
  const rating = label === "useful" ? 5 : 2;
  const buttons = Array.from(card.querySelectorAll("button, input"));
  buttons.forEach((btn) => { btn.disabled = true; });
  try {
    const data = await api(`/api/candidates/${candidate.id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ rating, label, comment }),
    });
    candidate.feedback = data.feedback;
    card.__lastWeakOtherComment = data.feedback?.comment || "";
    applyFeedbackState(card, data.feedback?.label);
    showToast("反馈已更新");
  } finally {
    buttons.forEach((btn) => { btn.disabled = false; });
  }
}

async function loadMe() {
  if (!state.token) {
    state.authReady = true;
    renderShell();
    finishBoot();
    return;
  }
  try {
    const data = await api("/api/me");
    state.user = data.user;
    state.searchOpen = true;
    state.launchingSearch = false;
    state.authReady = true;
    renderShell();
    finishBoot();
    renderRunsLoading();
    loadRuns().catch((err) => {
      $("runList").innerHTML = `<div class="muted">历史任务加载失败：${escapeHtml(err.message)}</div>`;
    });
  } catch (err) {
    localStorage.removeItem("wildidea_token");
    state.token = "";
    state.user = null;
    state.authReady = true;
    renderShell();
    finishBoot();
  }
}

async function loadRuns() {
  const data = await api("/api/runs");
  state.runs = data.runs;
  renderRuns();
}

function renderRunsLoading() {
  if (!$("runList") || !state.user) return;
  $("runList").classList.add("run-list-loading");
  $("runList").innerHTML = '<div class="muted history-loading">正在载入历史任务...</div>';
}

async function refreshMeOnly() {
  const data = await api("/api/me");
  state.user = data.user;
  renderShell();
}

async function selectRun(runId, options = {}) {
  stopWatching();
  state.currentRunId = runId;
  state.searchOpen = false;
  state.launchingSearch = false;
  clearLaunchTimers({ softLayer: Boolean(options.fromLaunch) });
  clearLaunchTiming();
  state.suppressProgressAnimationRunId = options.fromLaunch ? runId : null;
  state.adminOpen = false;
  state.historyDrawerOpen = false;
  const runSummary = state.runs.find((item) => item.id === runId);
  renderRuns();
  renderShell();
  renderRunTransition(runSummary, options);
  try {
    const data = await withMinimumDelay(api(`/api/runs/${runId}`), 320);
    renderCurrentRun(data.run);
    if (!options.fromLaunch) animateResultArrival();
    if (!["succeeded", "failed", "deleted"].includes(data.run.status)) watchRun(runId);
  } catch (err) {
    $("resultSection").classList.remove("result-switching");
    $("progressLog").innerHTML = `<div class="progress-item danger">${escapeHtml(err.message)}</div>`;
    showToast(err.message);
  }
}

function renderRunTransition(run, options = {}) {
  const section = $("resultSection");
  section.classList.remove("result-arrive");
  section.classList.toggle("result-switching", !options.fromLaunch);
  $("currentRunTitle").textContent = run?.problem || "正在调取记录";
  $("currentRunMeta").textContent = options.fromLaunch
    ? "任务已建立 · 正在接入实时进度"
    : (run ? `${statusLabel(run.status)} · 正在打开历史任务` : "正在打开历史任务");
  $("resultSection").dataset.activeRunStatus = "";
  $("resultSection").dataset.activeRunSnapshot = "{}";
  $("progressLog").innerHTML = `<div class="progress-item history-loading">${options.fromLaunch ? "正在接入抽卡流水线。" : "正在调取这次发散记录。"}</div>`;
  if (!options.fromLaunch) {
    $("candidateGrid").classList.remove("launch-landing-grid", "compact-card-grid", "result-card-grid");
    $("candidateGrid").innerHTML = `
      <div class="history-result-skeleton">
        <strong>正在整理卡片</strong>
        <span></span>
        <span></span>
        <span></span>
      </div>
    `;
  }
}

function animateResultArrival() {
  const section = $("resultSection");
  section.classList.remove("result-switching", "result-arrive");
  void section.offsetWidth;
  window.requestAnimationFrame(() => {
    section.classList.add("result-arrive");
    window.setTimeout(() => section.classList.remove("result-arrive"), 1040);
  });
}

function stopWatching() {
  if (state.watchTimer) {
    clearInterval(state.watchTimer);
    state.watchTimer = null;
  }
  if (state.watchRefreshTimer) {
    clearTimeout(state.watchRefreshTimer);
    state.watchRefreshTimer = null;
  }
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  stopRuntimeTicker();
}

function scheduleRunRefresh(runId, delay = 120) {
  if (state.watchRefreshTimer) clearTimeout(state.watchRefreshTimer);
  state.watchRefreshTimer = setTimeout(() => refreshRunView(runId), delay);
}

async function refreshRunView(runId) {
  try {
    const data = await api(`/api/runs/${runId}`);
    if (state.currentRunId === runId) {
      renderCurrentRun(data.run);
    }
    const terminal = ["succeeded", "failed", "deleted"].includes(data.run.status);
    await loadRuns();
    if (terminal) {
      stopWatching();
      await refreshMeOnly();
    }
  } catch (err) {
    stopWatching();
  }
}

function watchRun(runId) {
  stopWatching();
  ensureRuntimeTicker();
  if (window.EventSource && state.token) {
    const source = new EventSource(`/api/runs/${runId}/events?token=${encodeURIComponent(state.token)}`);
    state.eventSource = source;
    source.onmessage = () => scheduleRunRefresh(runId);
    source.onerror = () => {
      if (state.eventSource === source) {
        source.close();
        state.eventSource = null;
        startPollingRun(runId);
      }
    };
    return;
  }
  startPollingRun(runId);
}

function startPollingRun(runId) {
  if (state.watchTimer) clearInterval(state.watchTimer);
  state.watchTimer = setInterval(async () => {
    try {
      await refreshRunView(runId);
    } catch (err) {
      stopWatching();
    }
  }, 2500);
}

async function loadAdmin() {
  if (!isAdminUser()) return;
  ensureAdminPanel();
  const [metrics, queue, invites, users, cardLogs] = await Promise.all([
    api("/api/admin/metrics"),
    api("/api/admin/queue"),
    api("/api/admin/invite-codes"),
    api("/api/admin/users"),
    api(`/api/admin/card-logs?page=${state.adminCardLogPage}&page_size=20`),
  ]);
  $("metrics").innerHTML = `
    <div class="metric"><span class="muted">用户</span><strong>${metrics.users}</strong></div>
    <div class="metric"><span class="muted">反馈</span><strong>${metrics.feedback}</strong></div>
    <div class="metric"><span class="muted">邀请码</span><strong>${invites.invite_codes.length}</strong></div>
    <div class="metric"><span class="muted">任务</span><strong>${Object.values(metrics.runs_by_status || {}).reduce((a, b) => a + b, 0)}</strong></div>
  `;
  renderQueueStatus(queue.queue, cardLogs);
  $("inviteList").innerHTML = invites.invite_codes.map((item) => `
    <div class="admin-row">
      <strong>${escapeHtml(item.code)}</strong>
      <span class="muted">${item.bonus_credits} 积分 · ${item.redeemed_count}/${item.max_redemptions ?? "不限"} · ${escapeHtml(item.status)}</span>
    </div>
  `).join("") || '<div class="muted">暂无邀请码</div>';
  $("userList").innerHTML = users.users.map((item) => `
    <div class="admin-row">
      <strong>${escapeHtml(item.email)}</strong>
      <span class="muted">${escapeHtml(adminUserLabel(item))}</span>
    </div>
  `).join("");
}

function renderQueueStatus(queue, cardLogs = { items: [], page: 1, total_pages: 1, total: 0 }) {
  const counts = queue?.counts || {};
  const workers = queue?.workers || [];
  const logs = cardLogs?.items || [];
  const executorText = queue?.executor === "worker" ? "Worker 队列" : "本进程后台";
  const activeWorkers = workers.filter((worker) => worker.active).length;
  const oldestQueued = queue?.oldest_queued_at ? new Date(queue.oldest_queued_at).toLocaleString() : "无";
  const page = Number(cardLogs?.page || 1);
  const totalPages = Number(cardLogs?.total_pages || 1);
  $("queueStatus").innerHTML = `
    <div class="queue-head">
      <div>
        <span class="eyebrow">系统运行</span>
        <strong>${escapeHtml(executorText)}</strong>
        <p class="muted">排队 ${Number(queue?.queued || 0)} 个任务/${Number(queue?.queued_cards || 0)} 张卡 · 生成中 ${Number(queue?.running || 0)} 个任务/${Number(queue?.running_cards || 0)}/${Number(queue?.card_capacity || 50)} 张卡 · 活跃 worker ${activeWorkers}/${workers.length}</p>
      </div>
      <div class="queue-chips">
        <span>Queued ${counts.queued || 0}</span>
        <span>Running ${counts.running || 0}</span>
        <span>Cards ${Number(queue?.running_cards || 0)}/${Number(queue?.card_capacity || 50)}</span>
        <span>Done ${counts.succeeded || 0}</span>
        <span>Failed ${counts.failed || 0}</span>
      </div>
    </div>
    <div class="queue-meta">
      <span>最早排队 ${escapeHtml(oldestQueued)}</span>
      <span>轮询 ${escapeHtml(queue?.worker_poll_seconds ?? "-")}s</span>
      <span>卡片容量 ${escapeHtml(queue?.card_capacity ?? "-")}</span>
      <span>单用户上限 ${escapeHtml(queue?.user_run_card_limit ?? "-")} 张</span>
      <span>可用容量 ${escapeHtml(queue?.available_cards ?? "-")}</span>
    </div>
    <div class="queue-workers">
      ${workers.map((worker) => `
        <div class="queue-worker ${worker.active ? "active" : "stale"}">
          <strong>${escapeHtml(worker.id)}</strong>
          <span>${escapeHtml(workerLabel(worker.status))} · ${worker.age_seconds ?? "-"}s 前</span>
          ${worker.current_run_id ? `<small>Run ${escapeHtml(worker.current_run_id)}</small>` : "<small>空闲</small>"}
        </div>
      `).join("") || '<div class="muted">暂无 worker 心跳</div>'}
    </div>
    <div class="queue-logs">
      <div class="queue-log-title">
        <strong>最近日志</strong>
        <div class="queue-log-actions">
          <span class="muted">每页 20 张卡 · 第 ${page}/${totalPages} 页 · 共 ${Number(cardLogs?.total || 0)} 条</span>
          <button id="exportFeedbackBtn" class="ghost" type="button">导出 Excel</button>
        </div>
      </div>
      ${logs.map((log) => adminCardLogRow(log)).join("") || '<div class="muted">暂无卡片结果</div>'}
      <div class="admin-pagination">
        <button id="cardLogPrevBtn" class="ghost" type="button" ${page <= 1 ? "disabled" : ""}>上一页</button>
        <button id="cardLogNextBtn" class="ghost" type="button" ${page >= totalPages ? "disabled" : ""}>下一页</button>
      </div>
    </div>
  `;
  $("cardLogPrevBtn")?.addEventListener("click", () => changeAdminCardLogPage(page - 1, totalPages));
  $("cardLogNextBtn")?.addEventListener("click", () => changeAdminCardLogPage(page + 1, totalPages));
  $("exportFeedbackBtn")?.addEventListener("click", downloadFeedbackExcel);
}

function adminCardLogRow(item) {
  const feedback = item.feedback || null;
  const label = feedback ? (item.feedback_label_text || feedbackLabel(feedback.label)) : "未反馈";
  const comment = feedback?.comment ? ` · ${feedback.comment}` : "";
  const statusClass = feedback ? "has-feedback" : "no-feedback";
  const average = item.score_average ? `均分 ${item.score_average}` : "";
  const usability = item.score_applicability ? `可用 ${item.score_applicability}` : "";
  const scoreText = [average, usability].filter(Boolean).join(" · ");
  const meta = [
    item.user_email || "-",
    item.run_problem || "-",
    item.candidate_slot || "-",
    item.candidate_domain || item.candidate_source || "-",
  ].filter(Boolean).join(" · ");
  const result = item.candidate_desc || item.candidate_advantage || item.candidate_source_phenomenon || "";
  const time = item.candidate_created_at ? new Date(item.candidate_created_at).toLocaleString() : "-";
  return `
    <div class="queue-log-row card-log-row ${statusClass}" title="${escapeHtml(result)}">
      <span>${escapeHtml(time)}</span>
      <div>
        <strong>
          <b>${escapeHtml(formatAdminIndex(item.candidate_index))}. ${escapeHtml(item.candidate_name || "-")}</b>
          <em>${escapeHtml(`反馈：${label}${comment}`)}</em>
        </strong>
        <small>${escapeHtml(`${meta} · 结果：${compactText(result, 72) || "-"}${scoreText ? ` · ${scoreText}` : ""}`)}</small>
      </div>
    </div>
  `;
}

function compactText(value, maxLength = 80) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
}

function changeAdminCardLogPage(nextPage, totalPages) {
  state.adminCardLogPage = Math.max(1, Math.min(Number(totalPages || 1), Number(nextPage || 1)));
  loadAdmin();
}

function workerLabel(status) {
  const labels = {
    idle: "空闲",
    running: "执行中",
    stopped: "已停止",
  };
  return labels[status] || status || "-";
}

async function toggleAdminPanel() {
  if (!isAdminUser()) return;
  state.adminOpen = !state.adminOpen;
  state.historyDrawerOpen = false;
  renderShell();
  if (state.adminOpen) {
    await loadAdmin();
    $("adminPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function adminUserLabel(user) {
  if (user.role === "admin") return "管理员 · 无限配额";
  return `${user.role} · ${user.credit_balance} 积分`;
}

function formatAdminIndex(value) {
  if (value === null || value === undefined || value === "") return "--";
  return String(value).padStart(2, "0");
}

function adminScoreRow(scores) {
  const values = scores || {};
  return `
    <div class="admin-score-row">
      <span>结构 ${escapeHtml(values.structural_depth ?? "-")}</span>
      <span>距离 ${escapeHtml(values.domain_distance ?? "-")}</span>
      <span>新颖 ${escapeHtml(values.novelty ?? "-")}</span>
      <span>可用 ${escapeHtml(values.applicability ?? "-")}</span>
    </div>
  `;
}

async function downloadFeedbackExcel() {
  try {
    const response = await fetch("/api/admin/feedback.xlsx", {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!response.ok) {
      let message = "导出失败";
      try {
        const data = await response.json();
        message = data.detail?.message || data.detail?.error || message;
      } catch (_) {
        message = await response.text() || message;
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `wildidea-feedback-${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast("全量数据已导出");
  } catch (err) {
    showToast(err.message);
  }
}

async function handleInviteSubmit(event) {
  event.preventDefault();
  try {
    await api("/api/admin/invite-codes", {
      method: "POST",
      body: JSON.stringify({
        code: $("inviteCode").value || null,
        bonus_credits: Number($("inviteBonus").value || 20),
        max_redemptions: $("inviteMax").value ? Number($("inviteMax").value) : null,
      }),
    });
    $("inviteCode").value = "";
    $("inviteMax").value = "";
    await loadAdmin();
    showToast("邀请码已创建");
  } catch (err) {
    showToast(err.message);
  }
}

function openPoster(candidate) {
  state.posterCandidate = candidate;
  $("posterModalTitle").textContent = candidate.name || "另存为海报";
  $("posterHint").textContent = `二维码指向 ${posterSiteUrl()}`;
  $("posterModal").classList.remove("hidden");
  document.body.classList.add("poster-open");
  drawPosterCanvas($("posterCanvas"), candidate);
}

function closePoster() {
  state.posterCandidate = null;
  $("posterModal").classList.add("hidden");
  document.body.classList.remove("poster-open");
}

async function downloadPoster() {
  if (!state.posterCandidate) return;
  const button = $("posterDownloadBtn");
  const previousText = button.textContent;
  button.disabled = true;
  button.textContent = "正在生成";
  await delay(60);
  try {
    const canvas = $("posterCanvas");
    drawPosterCanvas(canvas, state.posterCandidate);
    const link = document.createElement("a");
    link.href = canvas.toDataURL("image/png");
    link.download = `wildidea-${safeFilename(state.posterCandidate.name || "poster")}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    showToast("海报已生成");
  } finally {
    button.disabled = false;
    button.textContent = previousText;
  }
}

function posterSiteUrl() {
  return window.location.origin || "https://wildidea";
}

function safeFilename(value) {
  return String(value || "poster")
    .trim()
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fa5-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 64) || "poster";
}

function drawPosterCanvas(canvas, candidate) {
  const width = 1080;
  const height = 1920;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  drawPosterBackground(ctx, width, height);

  const frame = { x: 28, y: 30, width: 1024, height: 1858 };
  const card = {
    x: frame.x + 16,
    y: frame.y + 16,
    width: frame.width - 32,
    height: frame.height - 32,
  };
  drawPosterPixelRect(ctx, frame.x, frame.y, frame.width, frame.height, 70, "#2a2a2a", null, 0);
  drawPosterPixelRect(ctx, card.x, card.y, card.width, card.height, 56, "#fffaf0", "rgba(91, 98, 104, 0.42)", 2);

  const content = {
    x: card.x + 34,
    y: card.y + 34,
    width: card.width - 68,
  };
  const cardBottom = card.y + card.height - 34;
  const headerHeight = 300;
  const sourceHeight = 318;
  const gap = 26;
  const advantageHeight = 232;
  const footerHeight = 252;
  const ideaHeight = Math.max(
    560,
    cardBottom - (content.y + headerHeight + sourceHeight + advantageHeight + footerHeight + gap * 4)
  );

  let y = content.y;
  y = drawPosterCardHeader(ctx, candidate, content.x, y, content.width, headerHeight);
  y += gap;
  drawPosterCardSection(ctx, posterCardSourceSection(candidate), content.x, y, content.width, sourceHeight);
  y += sourceHeight + gap;
  drawPosterCardSection(ctx, posterCardIdeaSection(candidate), content.x, y, content.width, ideaHeight);
  y += ideaHeight + gap;
  drawPosterCardSection(ctx, posterCardAdvantageSection(candidate), content.x, y, content.width, advantageHeight);
  y += advantageHeight + gap;
  drawPosterCardFooter(ctx, candidate, content.x, y, content.width, footerHeight);

  posterFont(ctx, 17, 900);
  ctx.fillStyle = "rgba(102, 112, 120, 0.72)";
  ctx.textAlign = "center";
  ctx.fillText(`Generated by WildIdea · ${new Date().toLocaleDateString()}`, width / 2, height - 22);
  ctx.textAlign = "left";
}

function posterCardSourceSection(candidate) {
  const sourcePhenomenon = String(candidate.sourcePhenomenon || candidate.source || "").trim();
  return {
    label: "他山之石",
    background: "#edf4f7",
    accent: "#496fae",
    labelFill: "#f7df89",
    kind: "source",
    phenomenon: sourcePhenomenon || "未记录他山之石",
    method: String(candidate.source || "").trim(),
    proto: String(candidate.proto || "").trim(),
  };
}

function posterCardIdeaSection(candidate) {
  return {
    label: "落地方案",
    background: "#fffdf7",
    accent: "#2a8a67",
    labelFill: "#6fcf97",
    kind: "idea",
    text: String(candidate.desc || "未记录落地方案").trim(),
  };
}

function posterCardAdvantageSection(candidate) {
  return {
    label: "优势",
    background: "#eaf6ea",
    accent: "#8fd7a0",
    labelFill: "#f7df89",
    kind: "advantage",
    text: normalizeAdvantage(candidate.advantage) || "未记录优势",
  };
}

function drawPosterBackground(ctx, width, height) {
  ctx.fillStyle = "#f3ecd8";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(195, 177, 130, 0.42)";
  ctx.lineWidth = 1;
  for (let x = 0; x < width; x += 22) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y < height; y += 22) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
}

function drawPosterCardHeader(ctx, candidate, x, y, width, height) {
  const { code, label } = slotBadgeParts(candidate.slot, candidate.field);
  const badgeW = 170;
  const badgeH = 104;
  drawPosterRect(ctx, x + width - badgeW, y + 6, badgeW, badgeH, 8, "#f3b17f", "#2a2a2a", 5);
  posterFont(ctx, 34, 900);
  ctx.fillStyle = "#111";
  ctx.textAlign = "center";
  ctx.fillText(code || "D?", x + width - badgeW / 2, y + 45);
  posterFont(ctx, 20, 900);
  drawPosterSingleLine(ctx, label || candidate.field || "", x + width - badgeW / 2, y + 76, badgeW - 24, 20, 12, 900, "center");
  ctx.textAlign = "left";

  drawPosterTag(ctx, x, y + 8, `方案 ${String(candidate.index || 1).padStart(2, "0")}`, "#fff4bd");
  const rerollCount = Number(candidate.reroll_count || 0);
  if (rerollCount > 0) {
    drawPosterTag(ctx, x + 112, y + 8, `重抽 ${rerollCount} 次`, "#fff1c6");
  }

  const titleWidth = width - badgeW - 32;
  posterFont(ctx, 66, 900);
  const titleLines = wrapPosterLines(ctx, candidate.name || "未命名方案", titleWidth).slice(0, 2);
  ctx.fillStyle = "#111";
  ctx.textBaseline = "top";
  titleLines.forEach((line, index) => {
    ctx.fillText(line, x, y + 74 + index * 74);
  });
  ctx.textBaseline = "alphabetic";

  const sourceLine = candidate.field ? `源自 ${candidate.field}` : "";
  if (sourceLine) {
    posterFont(ctx, 26, 900);
    ctx.fillStyle = "#667078";
    ctx.fillText(sourceLine, x, y + 240);
  }

  ctx.strokeStyle = "#2a2a2a";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(x, y + height - 6);
  ctx.lineTo(x + width, y + height - 6);
  ctx.stroke();
  return y + height;
}

function drawPosterCardSection(ctx, section, x, y, width, height) {
  if (section.kind === "idea") {
    drawPosterRect(ctx, x + 7, y + 7, width, height, 8, "rgba(42, 42, 42, 0.42)", null, 0);
  }
  drawPosterRect(ctx, x, y, width, height, 8, section.background, "#2a2a2a", section.kind === "idea" ? 5 : 4);
  if (section.kind === "idea") {
    drawPosterJokerPattern(ctx, x + 12, y + 18, width - 24, height - 36);
    ctx.fillStyle = "#d85f63";
    ctx.fillRect(x, y + 5, 10, height - 10);
    ctx.fillStyle = "#496fae";
    ctx.fillRect(x + width - 10, y + 5, 10, height - 10);
  } else {
    ctx.fillStyle = section.accent;
    ctx.fillRect(x, y + 4, 9, height - 8);
  }
  drawPosterTag(ctx, x + 18, y - 18, section.label, section.labelFill);

  if (section.kind === "source") {
    const textX = x + 32;
    const textW = width - 64;
    drawPosterFittedText(ctx, section.phenomenon, textX, y + 52, textW, 88, {
      fontSize: 31,
      minFont: 19,
      lineHeight: 1.22,
      weight: 900,
    });
    ctx.strokeStyle = "rgba(42, 42, 42, 0.52)";
    ctx.lineWidth = 3;
    ctx.setLineDash([3, 8]);
    ctx.beginPath();
    ctx.moveTo(textX, y + 154);
    ctx.lineTo(textX + textW, y + 154);
    ctx.stroke();
    ctx.setLineDash([]);
    posterFont(ctx, 24, 900);
    ctx.fillStyle = "#496fae";
    ctx.fillText("抽象方法", textX, y + 194);
    posterFont(ctx, 25, 900);
    ctx.fillStyle = "#111";
    ctx.fillText(section.method || "未记录抽象方法", textX, y + 230);
    drawPosterFittedText(ctx, section.proto || "", textX, y + 250, textW, height - 266, {
      fontSize: 22,
      minFont: 15,
      lineHeight: 1.32,
      weight: 800,
      color: "#667078",
    });
    return;
  }

  const bodyPad = section.kind === "idea" ? 42 : 32;
  const maxHeight = height - bodyPad * 2 + (section.kind === "idea" ? 8 : 0);
  drawPosterFittedText(ctx, section.text, x + bodyPad, y + bodyPad, width - bodyPad * 2, maxHeight, {
    fontSize: section.kind === "idea" ? 42 : 31,
    minFont: section.kind === "idea" ? 22 : 18,
    lineHeight: section.kind === "idea" ? 1.3 : 1.24,
    weight: 900,
    color: "#1f2528",
    centerY: true,
  });
}

function drawPosterCardFooter(ctx, candidate, x, y, width, height) {
  const qrSize = 176;
  const qrX = x + width - qrSize - 24;
  const qrY = y + 38;
  drawPosterRect(ctx, x, y, width, height, 10, "#fff7cf", "rgba(42, 42, 42, 0.68)", 3);
  ctx.setLineDash([8, 8]);
  ctx.strokeStyle = "rgba(42, 42, 42, 0.62)";
  ctx.lineWidth = 3;
  drawPosterRect(ctx, x + 8, y + 8, width - 16, height - 16, 8, null, "rgba(42, 42, 42, 0.62)", 3);
  ctx.setLineDash([]);

  const textX = x + 26;
  const textW = qrX - textX - 30;
  posterFont(ctx, 31, 900);
  ctx.fillStyle = "#111";
  ctx.fillText("扫码抽一张自己的跨域灵感卡", textX, y + 62);
  posterFont(ctx, 21, 900);
  ctx.fillStyle = "#667078";
  drawPosterWrappedText(ctx, posterSiteUrl(), textX, y + 98, textW, 30);
  const problem = posterProblemText(candidate);
  if (problem) {
    posterFont(ctx, 21, 900);
    ctx.fillStyle = "#667078";
    drawPosterFittedText(ctx, problem, textX, y + 154, textW, 74, {
      fontSize: 21,
      minFont: 14,
      lineHeight: 1.35,
      weight: 900,
      color: "#667078",
    });
  }
  drawPosterQr(ctx, posterSiteUrl(), qrX, qrY, qrSize);
}

function posterProblemText(candidate) {
  const problem = String(candidate.runProblem || "").trim();
  if (!problem || problem === "生成工作台") return "";
  return `问题：${problem}`;
}

function drawPosterLogo(ctx, x, y, size) {
  drawPosterRect(ctx, x, y, size, size, 8, "#386eea", "#2a2a2a", Math.max(3, Math.round(size / 18)));
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, size, size);
  ctx.clip();
  ctx.fillStyle = "#fff4bd";
  ctx.fillRect(x + size * 0.1, y + size * 0.18, size * 0.28, size * 0.16);
  ctx.fillStyle = "#f3b17f";
  ctx.fillRect(x + size * 0.68, y + size * 0.16, size * 0.2, size * 0.28);
  ctx.fillStyle = "#6fcf97";
  ctx.fillRect(x + size * 0.12, y + size * 0.72, size * 0.22, size * 0.16);
  ctx.fillStyle = "#55e6ff";
  ctx.fillRect(x + size * 0.64, y + size * 0.7, size * 0.26, size * 0.14);
  posterFont(ctx, Math.round(size * 0.56), 900);
  ctx.lineJoin = "round";
  ctx.lineWidth = Math.max(8, Math.round(size * 0.14));
  ctx.strokeStyle = "#fffdf0";
  ctx.fillStyle = "#1f2528";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.strokeText("W", x + size / 2, y + size * 0.58);
  ctx.fillText("W", x + size / 2, y + size * 0.58);
  ctx.restore();
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}

function drawPosterTag(ctx, x, y, text, fill) {
  posterFont(ctx, 19, 900);
  const width = Math.ceil(ctx.measureText(text).width) + 26;
  drawPosterRect(ctx, x, y, width, 38, 3, fill, "#2a2a2a", 4);
  ctx.fillStyle = "#111";
  ctx.fillText(text, x + 13, y + 26);
  return width;
}

function drawPosterFittedText(ctx, text, x, y, width, height, options = {}) {
  const {
    fontSize = 24,
    minFont = 12,
    lineHeight = 1.35,
    weight = 800,
    color = "#1f2528",
    centerY = false,
  } = options;
  let size = fontSize;
  let lines = [];
  let actualLineHeight = size * lineHeight;
  while (size >= minFont) {
    posterFont(ctx, size, weight);
    lines = wrapPosterLines(ctx, text, width);
    actualLineHeight = Math.ceil(size * lineHeight);
    if (lines.length * actualLineHeight <= height) break;
    size -= 1;
  }
  const maxLines = Math.max(1, Math.floor(height / actualLineHeight));
  if (lines.length > maxLines) {
    lines = lines.slice(0, maxLines);
    lines[lines.length - 1] = posterEllipsisLine(ctx, lines[lines.length - 1], width);
  }
  const textHeight = lines.length * actualLineHeight;
  const startY = centerY ? y + Math.max(0, (height - textHeight) / 2) : y;
  ctx.fillStyle = color;
  ctx.textBaseline = "top";
  posterFont(ctx, size, weight);
  lines.forEach((line, index) => {
    ctx.fillText(line, x, startY + index * actualLineHeight);
  });
  ctx.textBaseline = "alphabetic";
}

function drawPosterSingleLine(ctx, text, x, y, maxWidth, fontSize, minFont, weight = 900, align = "left") {
  let size = fontSize;
  while (size > minFont) {
    posterFont(ctx, size, weight);
    if (ctx.measureText(text).width <= maxWidth) break;
    size -= 1;
  }
  posterFont(ctx, size, weight);
  ctx.textAlign = align;
  ctx.fillText(text, x, y);
  ctx.textAlign = "left";
}

function posterEllipsisLine(ctx, line, maxWidth) {
  const ellipsis = "…";
  let value = String(line || "");
  while (value.length > 0 && ctx.measureText(value + ellipsis).width > maxWidth) {
    value = value.slice(0, -1);
  }
  return `${value}${ellipsis}`;
}

function drawPosterJokerPattern(ctx, x, y, width, height) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, width, height);
  ctx.clip();
  for (let row = -1; row < Math.ceil(height / 78) + 1; row += 1) {
    for (let col = -1; col < Math.ceil(width / 96) + 1; col += 1) {
      const px = x + col * 96 + (row % 2 ? 48 : 0);
      const py = y + row * 78;
      drawPosterTinyJoker(ctx, px, py, 0.72);
    }
  }
  ctx.restore();
}

function drawPosterTinyJoker(ctx, x, y, scale = 1) {
  const unit = 7 * scale;
  ctx.save();
  ctx.globalAlpha = 0.075;
  ctx.fillStyle = "#2a2a2a";
  ctx.fillRect(x + unit * 3, y, unit * 2, unit * 1);
  ctx.fillRect(x + unit * 2, y + unit, unit * 4, unit * 1);
  ctx.fillRect(x, y + unit * 2, unit * 8, unit * 1);
  ctx.fillRect(x + unit * 2, y + unit * 4, unit * 1.5, unit * 1);
  ctx.fillRect(x + unit * 4.5, y + unit * 4, unit * 1.5, unit * 1);
  ctx.fillRect(x + unit * 2, y + unit * 6, unit * 4, unit * 1);
  ctx.fillRect(x + unit * 1, y + unit * 8, unit * 6, unit * 1);
  ctx.fillRect(x, y + unit * 9, unit * 8, unit * 1);
  ctx.fillRect(x + unit * 1, y + unit * 10, unit * 2, unit * 1);
  ctx.fillRect(x + unit * 5, y + unit * 10, unit * 2, unit * 1);
  ctx.restore();
}

function drawPosterPixelRect(ctx, x, y, width, height, radius, fill, stroke, lineWidth) {
  posterPixelRectPath(ctx, x, y, width, height, radius);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke && lineWidth) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }
}

function posterPixelRectPath(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  const step = r / 8;
  const points = [
    [x + r, y],
    [x + width - r, y],
    [x + width - r * 0.62, y + step],
    [x + width - r * 0.5, y + step * 2],
    [x + width - r * 0.37, y + step * 3],
    [x + width - r * 0.25, y + step * 4],
    [x + width - r * 0.12, y + step * 5],
    [x + width, y + r],
    [x + width, y + height - r],
    [x + width - r * 0.12, y + height - step * 5],
    [x + width - r * 0.25, y + height - step * 4],
    [x + width - r * 0.37, y + height - step * 3],
    [x + width - r * 0.5, y + height - step * 2],
    [x + width - r * 0.62, y + height - step],
    [x + width - r, y + height],
    [x + r, y + height],
    [x + r * 0.62, y + height - step],
    [x + r * 0.5, y + height - step * 2],
    [x + r * 0.37, y + height - step * 3],
    [x + r * 0.25, y + height - step * 4],
    [x + r * 0.12, y + height - step * 5],
    [x, y + height - r],
    [x, y + r],
    [x + r * 0.12, y + step * 5],
    [x + r * 0.25, y + step * 4],
    [x + r * 0.37, y + step * 3],
    [x + r * 0.5, y + step * 2],
    [x + r * 0.62, y + step],
  ];
  ctx.beginPath();
  points.forEach(([px, py], index) => {
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.closePath();
}

function drawPosterRect(ctx, x, y, width, height, radius, fill, stroke, lineWidth) {
  ctx.beginPath();
  if (radius > 0) {
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
  } else {
    ctx.rect(x, y, width, height);
  }
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke && lineWidth) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }
}

function drawPosterWrappedText(ctx, text, x, y, maxWidth, lineHeight) {
  const lines = wrapPosterLines(ctx, text, maxWidth);
  lines.forEach((line, index) => {
    ctx.fillText(line, x, y + index * lineHeight);
  });
  return y + lines.length * lineHeight;
}

function wrapPosterLines(ctx, text, maxWidth) {
  const tokens = tokenizePosterText(String(text || "").replace(/\s+/g, " ").trim());
  const lines = [];
  let line = "";
  tokens.forEach((token) => {
    const next = line ? `${line}${token}` : token.trimStart();
    if (!line || ctx.measureText(next).width <= maxWidth) {
      line = next;
      return;
    }
    if (ctx.measureText(token).width > maxWidth) {
      if (line) lines.push(line.trimEnd());
      line = "";
      Array.from(token).forEach((char) => {
        const charNext = line + char;
        if (line && ctx.measureText(charNext).width > maxWidth) {
          lines.push(line);
          line = char;
        } else {
          line = charNext;
        }
      });
      return;
    }
    lines.push(line.trimEnd());
    line = token.trimStart();
  });
  if (line) lines.push(line.trimEnd());
  return lines.length ? lines : [""];
}

function tokenizePosterText(text) {
  const tokens = [];
  let buffer = "";
  const flush = () => {
    if (buffer) {
      tokens.push(buffer);
      buffer = "";
    }
  };
  Array.from(text).forEach((char) => {
    if (/[\u3400-\u9fff，。、“”‘’；：！？（）《》]/.test(char)) {
      flush();
      tokens.push(char);
    } else if (/\s/.test(char)) {
      flush();
      tokens.push(" ");
    } else {
      buffer += char;
    }
  });
  flush();
  return tokens;
}

function posterFont(ctx, size, weight = 700) {
  ctx.font = `${weight} ${size}px "Courier New", "SF Mono", Menlo, Monaco, "PingFang SC", "Microsoft YaHei", monospace`;
}

function drawPosterQr(ctx, text, x, y, size) {
  let matrix;
  try {
    matrix = createQrMatrix(text);
  } catch (_) {
    matrix = createQrMatrix(posterSiteUrl().split("?")[0].slice(0, 80));
  }
  drawPosterRect(ctx, x - 10, y - 10, size + 20, size + 20, 6, "#fff", "#2a2a2a", 3);
  const count = matrix.length;
  const cell = Math.floor(size / count);
  const realSize = cell * count;
  const offset = (size - realSize) / 2;
  ctx.fillStyle = "#111";
  matrix.forEach((row, rowIndex) => {
    row.forEach((dark, colIndex) => {
      if (dark) ctx.fillRect(x + offset + colIndex * cell, y + offset + rowIndex * cell, cell, cell);
    });
  });
}

const QR_L_TABLE = [
  null,
  { data: 19, ecc: 7 },
  { data: 34, ecc: 10 },
  { data: 55, ecc: 15 },
  { data: 80, ecc: 20 },
  { data: 108, ecc: 26 },
];

function createQrMatrix(text) {
  const bytes = Array.from(new TextEncoder().encode(text));
  const version = QR_L_TABLE.findIndex((item, index) => index > 0 && bytes.length + 2 <= item.data);
  if (version < 1) throw new Error("QR data is too long");
  const dataCodewords = qrDataCodewords(bytes, version);
  const ecc = reedSolomonRemainder(dataCodewords, QR_L_TABLE[version].ecc);
  const codewords = dataCodewords.concat(ecc);
  const size = 17 + version * 4;
  const modules = Array.from({ length: size }, () => Array(size).fill(false));
  const reserved = Array.from({ length: size }, () => Array(size).fill(false));
  const set = (x, y, value, reserve = true) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    modules[y][x] = Boolean(value);
    if (reserve) reserved[y][x] = true;
  };
  drawQrFunctionPatterns(version, size, set, reserved);
  placeQrDataBits(codewords, size, modules, reserved);
  drawQrFormatBits(size, set);
  return modules;
}

function qrDataCodewords(bytes, version) {
  const bits = [];
  const append = (value, length) => {
    for (let i = length - 1; i >= 0; i -= 1) bits.push((value >>> i) & 1);
  };
  append(0b0100, 4);
  append(bytes.length, version <= 9 ? 8 : 16);
  bytes.forEach((byte) => append(byte, 8));
  const capacityBits = QR_L_TABLE[version].data * 8;
  const terminator = Math.min(4, capacityBits - bits.length);
  append(0, terminator);
  while (bits.length % 8) bits.push(0);
  const codewords = [];
  for (let i = 0; i < bits.length; i += 8) {
    codewords.push(bits.slice(i, i + 8).reduce((value, bit) => (value << 1) | bit, 0));
  }
  const pads = [0xec, 0x11];
  let padIndex = 0;
  while (codewords.length < QR_L_TABLE[version].data) {
    codewords.push(pads[padIndex % 2]);
    padIndex += 1;
  }
  return codewords;
}

function drawQrFunctionPatterns(version, size, set, reserved) {
  drawQrFinder(set, 0, 0);
  drawQrFinder(set, size - 7, 0);
  drawQrFinder(set, 0, size - 7);
  for (let i = 0; i < size; i += 1) {
    if (!reserved[6][i]) set(i, 6, i % 2 === 0);
    if (!reserved[i][6]) set(6, i, i % 2 === 0);
  }
  if (version > 1) {
    const pos = 4 * version + 10;
    [[pos, pos]].forEach(([x, y]) => drawQrAlignment(set, reserved, x, y));
  }
  set(8, size - 8, true);
  for (let i = 0; i < 9; i += 1) {
    if (i !== 6) {
      reserved[8][i] = true;
      reserved[i][8] = true;
    }
  }
  for (let i = 0; i < 8; i += 1) {
    reserved[size - 1 - i][8] = true;
    reserved[8][size - 1 - i] = true;
  }
}

function drawQrFinder(set, x, y) {
  for (let dy = -1; dy <= 7; dy += 1) {
    for (let dx = -1; dx <= 7; dx += 1) {
      const xx = x + dx;
      const yy = y + dy;
      const dark = dx >= 0 && dx <= 6 && dy >= 0 && dy <= 6 &&
        (dx === 0 || dx === 6 || dy === 0 || dy === 6 || (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4));
      set(xx, yy, dark);
    }
  }
}

function drawQrAlignment(set, reserved, cx, cy) {
  if (reserved[cy]?.[cx]) return;
  for (let dy = -2; dy <= 2; dy += 1) {
    for (let dx = -2; dx <= 2; dx += 1) {
      set(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }
  }
}

function placeQrDataBits(codewords, size, modules, reserved) {
  const bits = [];
  codewords.forEach((byte) => {
    for (let i = 7; i >= 0; i -= 1) bits.push((byte >>> i) & 1);
  });
  let bitIndex = 0;
  let upward = true;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right -= 1;
    for (let vert = 0; vert < size; vert += 1) {
      const y = upward ? size - 1 - vert : vert;
      for (let dx = 0; dx < 2; dx += 1) {
        const x = right - dx;
        if (reserved[y][x]) continue;
        let bit = bitIndex < bits.length ? bits[bitIndex] : 0;
        bitIndex += 1;
        if ((x + y) % 2 === 0) bit ^= 1;
        modules[y][x] = Boolean(bit);
      }
    }
    upward = !upward;
  }
}

function drawQrFormatBits(size, set) {
  const bits = qrFormatBits(1, 0);
  const bit = (index) => ((bits >>> index) & 1) !== 0;
  for (let i = 0; i <= 5; i += 1) set(8, i, bit(i));
  set(8, 7, bit(6));
  set(8, 8, bit(7));
  set(7, 8, bit(8));
  for (let i = 9; i < 15; i += 1) set(14 - i, 8, bit(i));
  for (let i = 0; i < 8; i += 1) set(size - 1 - i, 8, bit(i));
  for (let i = 8; i < 15; i += 1) set(8, size - 15 + i, bit(i));
  set(8, size - 8, true);
}

function qrFormatBits(errorLevel, mask) {
  const data = (errorLevel << 3) | mask;
  let value = data << 10;
  for (let i = 14; i >= 10; i -= 1) {
    if (((value >>> i) & 1) !== 0) value ^= 0x537 << (i - 10);
  }
  return ((data << 10) | value) ^ 0x5412;
}

function reedSolomonRemainder(data, degree) {
  const generator = reedSolomonGenerator(degree);
  const message = data.concat(Array(degree).fill(0));
  data.forEach((_, index) => {
    const coefficient = message[index];
    if (coefficient === 0) return;
    generator.forEach((value, offset) => {
      message[index + offset] ^= gfMultiply(value, coefficient);
    });
  });
  return message.slice(data.length);
}

function reedSolomonGenerator(degree) {
  let coefficients = [1];
  for (let i = 0; i < degree; i += 1) {
    const root = gfPower(2, i);
    const next = Array(coefficients.length + 1).fill(0);
    coefficients.forEach((coefficient, index) => {
      next[index] ^= coefficient;
      next[index + 1] ^= gfMultiply(coefficient, root);
    });
    coefficients = next;
  }
  return coefficients;
}

function gfPower(value, power) {
  let result = 1;
  for (let i = 0; i < power; i += 1) result = gfMultiply(result, value);
  return result;
}

function gfMultiply(a, b) {
  let result = 0;
  let x = a;
  let y = b;
  while (y > 0) {
    if (y & 1) result ^= x;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
    y >>= 1;
  }
  return result & 0xff;
}

function feedbackLabel(label) {
  const labels = {
    useful: "有用",
    weak_obscure: "晦涩难懂",
    weak_off_topic: "不够相关",
    weak_too_common: "太常规",
    weak_unusable: "不可落地",
    weak_other: "其他",
    weak: "没用",
  };
  return labels[label] || label || "-";
}

function normalizeAdvantage(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const prefix = "这种方案的优势在于，";
  if (text.startsWith(prefix) || text.startsWith("这种方案的优势在于")) return text;
  return `${prefix}${text}`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

$("loginTab").addEventListener("click", () => setAuthMode("login"));
$("registerTab").addEventListener("click", () => setAuthMode("register"));

function setEmailCodeCountdown(seconds) {
  state.emailCodeRemaining = seconds;
  const button = $("sendEmailCodeBtn");
  if (state.emailCodeTimer) clearInterval(state.emailCodeTimer);
  const render = () => {
    if (state.emailCodeRemaining <= 0) {
      button.disabled = false;
      button.textContent = "发送验证码";
      clearInterval(state.emailCodeTimer);
      state.emailCodeTimer = null;
      return;
    }
    button.disabled = true;
    button.textContent = `${state.emailCodeRemaining}s`;
    state.emailCodeRemaining -= 1;
  };
  render();
  state.emailCodeTimer = setInterval(render, 1000);
}

$("sendEmailCodeBtn").addEventListener("click", async () => {
  const email = $("email").value.trim();
  if (!email) {
    showToast("请先填写邮箱");
    return;
  }
  $("sendEmailCodeBtn").disabled = true;
  try {
    const data = await api("/api/auth/email-code", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    setEmailCodeCountdown(Math.min(60, Number(data.expires_in_seconds || 60)));
    showToast("验证码已发送，请查看邮箱");
  } catch (err) {
    $("sendEmailCodeBtn").disabled = false;
    showToast(err.message);
  }
});

$("authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
  const payload = {
    email: $("email").value,
    password: $("password").value,
  };
  if (state.authMode === "register") {
    if (!$("improvementConsent").checked) {
      showToast("请先同意将交互数据用于改进；我们会保护你的隐私");
      $("improvementConsent").focus();
      return;
    }
    payload.invite_code = $("inviteAtRegister").value || null;
    payload.opt_in_improvement = $("improvementConsent").checked;
    payload.verification_code = $("emailCode").value.trim();
  }
  try {
    const data = await api(path, { method: "POST", body: JSON.stringify(payload) });
    state.token = data.access_token;
    state.user = data.user;
    state.currentRunId = null;
    state.userInviteOpen = false;
    state.searchOpen = true;
    state.launchingSearch = false;
    localStorage.setItem("wildidea_token", state.token);
    renderCurrentRun(null);
    renderShell();
    await loadRuns();
    showToast(state.authMode === "login" ? "登录成功" : "注册成功");
  } catch (err) {
    showToast(err.message);
  }
});

$("logoutBtn").addEventListener("click", () => {
  stopWatching();
  localStorage.removeItem("wildidea_token");
  state.token = "";
  state.user = null;
  state.runs = [];
  state.currentRunId = null;
  state.adminOpen = false;
  state.searchOpen = true;
  state.launchingSearch = false;
  state.historyDrawerOpen = false;
  state.historyQuery = "";
  state.userInviteOpen = false;
  $("historySearch").value = "";
  state.animatedProgressCards.clear();
  renderShell();
  renderRuns();
  renderCurrentRun(null);
});

function focusRedeemCode() {
  window.setTimeout(() => {
    const field = $("redeemCode");
    field?.focus();
    field?.select();
  }, 0);
}

$("userPanelToggle").addEventListener("click", (event) => {
  event.stopPropagation();
  if (!state.user) return;
  state.userInviteOpen = true;
  renderShell();
  focusRedeemCode();
});

$("userPanel").addEventListener("click", (event) => {
  event.stopPropagation();
});

document.addEventListener("click", (event) => {
  if (!state.userInviteOpen) return;
  if ($("userPanel").contains(event.target)) return;
  state.userInviteOpen = false;
  renderShell();
});

$("redeemForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/api/me/invite-code/redeem", {
      method: "POST",
      body: JSON.stringify({ code: $("redeemCode").value }),
    });
    state.user.credit_balance = data.credit_balance;
    $("redeemCode").value = "";
    state.userInviteOpen = false;
    renderShell();
    showToast(`兑换成功，增加 ${data.bonus_credits} 积分`);
  } catch (err) {
    showToast(err.message);
  }
});

$("runForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.user) {
    promptAuthRequired();
    return;
  }
  $("runSubmit").disabled = true;
  const problemText = $("problem").value.trim();
  if (!problemText) {
    showToast("请先填写问题");
    $("problem").focus();
    $("runSubmit").disabled = false;
    return;
  }
  const forbidTerms = $("forbidTerms").value.split(/\s+/).map((item) => item.trim()).filter(Boolean);
  const slotCount = Math.max(1, Math.min(MAX_SLOT_COUNT, Number($("slotCount").value || DEFAULT_SLOT_COUNT)));
  beginSearchLaunch(problemText, slotCount);
  try {
    const data = await withMinimumDelay(api("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        problem: problemText,
        slot_count: slotCount,
        forbid_terms: forbidTerms,
      }),
    }), launchDurationForCount(slotCount));
    state.user.credit_balance = data.credit_balance;
    renderShell();
    await loadRuns();
    await selectRun(data.run.id, { fromLaunch: true });
    showToast("任务已提交");
  } catch (err) {
    cancelSearchLaunch();
    showToast(err.message);
  } finally {
    $("runSubmit").disabled = false;
  }
});

$("brandHomeBtn").addEventListener("click", openSearchPage);
$("refreshRunsBtn").addEventListener("click", loadRuns);
$("statusPill").addEventListener("click", toggleAdminPanel);
$("historyDrawerBtn").addEventListener("click", () => {
  state.historyDrawerOpen = !state.historyDrawerOpen;
  renderShell();
});
$("historyCloseBtn").addEventListener("click", () => {
  state.historyDrawerOpen = false;
  renderShell();
});
$("historyBackdrop").addEventListener("click", () => {
  state.historyDrawerOpen = false;
  renderShell();
});
$("historySearch").addEventListener("input", (event) => {
  state.historyQuery = event.currentTarget.value;
  renderRuns();
});
$("slotCount").addEventListener("input", updateRunCostLabel);
["problem", "forbidTerms", "slotCount"].forEach((id) => {
  $(id)?.addEventListener("focus", () => {
    if (!state.user) promptAuthRequired();
  });
  $(id)?.addEventListener("click", () => {
    if (!state.user) promptAuthRequired();
  });
});
document.querySelectorAll(".floating-question").forEach((button) => {
  button.addEventListener("click", () => fillExampleProblem(button.dataset.exampleProblem || button.textContent.trim()));
});
$("posterCloseBtn").addEventListener("click", closePoster);
$("posterBackdrop").addEventListener("click", closePoster);
$("posterDownloadBtn").addEventListener("click", downloadPoster);
let fitResizeTimer = null;
window.addEventListener("resize", () => {
  window.clearTimeout(fitResizeTimer);
  fitResizeTimer = window.setTimeout(() => scheduleFitText($("candidateGrid")), 120);
});
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("posterModal").classList.contains("hidden")) closePoster();
});

setAuthMode("login");
updateRunCostLabel();
renderShell();
loadMe();
