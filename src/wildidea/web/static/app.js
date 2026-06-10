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
};

const DRAW_CARD_DELAY_MS = 210;
const SEARCH_LAUNCH_MIN_MS = 940;

const $ = (id) => document.getElementById(id);

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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

function renderShell() {
  const booting = !state.authReady;
  const loggedIn = Boolean(state.user);
  const isAdmin = isAdminUser();
  const adminViewActive = loggedIn && isAdmin && state.adminOpen;
  if (!isAdmin) state.adminOpen = false;
  if (!loggedIn || adminViewActive) state.historyDrawerOpen = false;
  document.body.classList.toggle("app-logged-in", loggedIn);
  document.body.classList.toggle("admin-view-open", adminViewActive);
  $("authPanel").classList.toggle("hidden", booting || loggedIn);
  $("userPanel").classList.toggle("hidden", !loggedIn);
  $("historyPanel").classList.toggle("hidden", !loggedIn);
  $("historyDrawerBtn").classList.toggle("hidden", !loggedIn || adminViewActive);
  $("historyDrawerBtn").setAttribute("aria-expanded", String(state.historyDrawerOpen));
  $("historyBackdrop").classList.toggle("hidden", !state.historyDrawerOpen);
  document.body.classList.toggle("history-drawer-open", state.historyDrawerOpen);
  $("workspace").classList.toggle("hidden", !loggedIn || adminViewActive);
  $("adminPanel").classList.toggle("hidden", !adminViewActive);
  $("emptyState").classList.toggle("hidden", booting || loggedIn);
  $("toolbarTitle").textContent = adminViewActive ? "管理员后台" : "生成工作台";
  $("toolbarSubtitle").textContent = adminViewActive
    ? "查看队列、用户、邀请码、反馈和导出数据。"
    : (isAdmin ? "管理员无限配额；系统失败会自动恢复任务状态。" : "每张卡片消耗 1 积分；系统失败会自动退回本次扣除。");
  $("statusPill").textContent = statusPillText(booting, loggedIn, isAdmin, adminViewActive);
  $("statusPill").disabled = !isAdmin;
  $("statusPill").classList.toggle("is-admin-action", isAdmin);
  $("statusPill").setAttribute("aria-pressed", String(adminViewActive));
  $("statusPill").title = isAdmin ? (adminViewActive ? "返回生成工作台" : "打开管理员后台") : "";
  $("brandHomeBtn").classList.toggle("is-clickable", loggedIn);
  $("brandHomeBtn").setAttribute("aria-label", loggedIn ? "发起新的 WildIdea 搜索" : "WildIdea");
  if (loggedIn) {
    $("userEmail").textContent = state.user.email;
    $("creditBalance").textContent = isAdmin ? "管理员" : `${state.user.credit_balance} 积分`;
  }
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
  const count = Math.max(1, Math.min(10, Number($("slotCount")?.value || 10)));
  $("runSubmit").textContent = isAdminUser() ? `生成 ${count} 张卡` : `消耗 ${count} 积分生成`;
}

function renderWorkspaceMode() {
  const loggedIn = Boolean(state.user);
  const showSearch = loggedIn && !state.adminOpen && state.searchOpen && !state.launchingSearch;
  $("workspace").classList.toggle("search-open", showSearch);
  $("workspace").classList.toggle("result-open", loggedIn && !state.adminOpen && !showSearch);
  $("workspace").classList.toggle("launching", Boolean(state.launchingSearch));
  $("runForm").classList.toggle("hidden", loggedIn && !showSearch && !state.launchingSearch);
  $("resultSection").classList.toggle("hidden", !loggedIn || (showSearch && !state.launchingSearch));
  $("launchGhost").classList.toggle("hidden", !state.launchingSearch);
}

function openSearchPage() {
  if (!state.user) return;
  stopWatching();
  state.currentRunId = null;
  state.searchOpen = true;
  state.launchingSearch = false;
  state.adminOpen = false;
  state.historyDrawerOpen = false;
  state.animatedProgressCards.clear();
  $("problem").value = "";
  $("forbidTerms").value = "";
  $("slotCount").value = "10";
  updateRunCostLabel();
  renderRuns();
  renderCurrentRun(null);
  renderShell();
  setTimeout(() => $("problem").focus(), 0);
}

function beginSearchLaunch(problemText) {
  state.searchOpen = false;
  state.launchingSearch = true;
  $("launchGhostText").textContent = problemText;
  $("currentRunTitle").textContent = "生成工作台";
  $("currentRunMeta").textContent = "正在提交任务";
  $("progressLog").innerHTML = '<div class="progress-item">正在把问题送入抽卡流水线。</div>';
  $("candidateGrid").innerHTML = "";
  renderShell();
}

function cancelSearchLaunch() {
  state.launchingSearch = false;
  state.searchOpen = true;
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
    btn.innerHTML = `<strong>${escapeHtml(run.problem)}</strong><span class="muted">${statusLabel(run.status)} · ${new Date(run.created_at).toLocaleString()}</span>`;
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
  const target = config.slot_count || 10;
  const ok = events.filter((event) => ["candidate_ok", "candidate_fallback"].includes(event.event_type)).length;
  const maxRetries = config.max_retries || 3;
  const maxRerolls = Math.max(0, maxRetries - 1);
  const rerolls = events.filter((event) => event.event_type === "threshold_rejected").length;
  const estimateSeconds = Math.max(90, (target + rerolls) * 90);
  const estimateText = formatEstimate(estimateSeconds);
  const startedAt = runStartMs(events);
  const elapsedText = startedAt ? formatChineseDuration(elapsedMs(startedAt)) : "--";
  if (!events.some((event) => event.event_type === "generating")) {
    return `已用时 ${elapsedText} · 正在抽取源现象并准备生成，目标 ${target} 张卡片。每张卡大约 90 秒；为保证质量可能重抽，触达上限仍不通过会退回该卡积分。`;
  }
  return `已用时 ${elapsedText} · 正在生成和评分，已得到 ${ok}/${target} 条候选。预计共需约 ${estimateText}；每张卡大约 90 秒，最多重抽 ${maxRerolls} 次。系统会为了保证结果质量自动重抽，触达上限仍不通过会退回该卡积分。`;
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
  if (!run) {
    stopRuntimeTicker();
    $("currentRunTitle").textContent = "还没有选择任务";
    $("currentRunMeta").textContent = "";
    $("resultSection").dataset.activeRunStatus = "";
    $("resultSection").dataset.activeRunSnapshot = "{}";
    $("progressLog").innerHTML = "";
    $("candidateGrid").innerHTML = "";
    return;
  }
  $("currentRunTitle").textContent = run.problem;
  $("currentRunMeta").textContent = `${statusLabel(run.status)} · ${run.problem_type || "待判断"} · ${new Date(run.created_at).toLocaleString()}`;
  $("resultSection").dataset.activeRunStatus = run.status || "";
  $("resultSection").dataset.activeRunSnapshot = JSON.stringify(run.config_snapshot || {});
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
    renderCandidates(run.candidates || [], run.events || []);
  } else {
    renderSlotProgress(run.events || [], run.config_snapshot?.slot_count || 10, run.candidates || []);
  }
}

function renderSlotProgress(events, target, candidates = []) {
  const grid = $("candidateGrid");
  grid.innerHTML = "";
  const slotsDone = events.find((event) => event.event_type === "slots_done");
  const slots = slotsDone?.payload?.slots || [];
  if (!slots.length) {
    renderDrawStage(grid, target, events);
    return;
  }
  const states = buildSlotStates(slots, events, candidates);

  states.forEach((item, index) => {
    const animationKey = `${state.currentRunId || "draft"}:${item.slot_id || index}`;
    if (item.candidate) {
      const liveCard = renderCandidateArticle(item.candidate, item.slotInfo, {
        feedback: true,
        index: item.candidate.index || index + 1,
        runtime: runtimeMeta(item),
      });
      liveCard.classList.add("live-candidate");
      if (!state.animatedProgressCards.has(animationKey)) {
        state.animatedProgressCards.add(animationKey);
        liveCard.classList.add("draw-enter");
        liveCard.style.setProperty("--draw-delay", `${Math.min(index, 9) * DRAW_CARD_DELAY_MS}ms`);
      }
      grid.appendChild(liveCard);
      return;
    }

    const card = document.createElement("article");
    card.className = `candidate progress-card ${item.status}`;
    if (!state.animatedProgressCards.has(animationKey)) {
      state.animatedProgressCards.add(animationKey);
      card.classList.add("draw-enter");
      card.style.setProperty("--draw-delay", `${Math.min(index, 9) * DRAW_CARD_DELAY_MS}ms`);
    }
    card.innerHTML = `
      <div class="candidate-top">
        <div>
          <h3>${index + 1}. ${escapeHtml(item.title)}</h3>
          <span class="muted">${escapeHtml(item.domain)}</span>
        </div>
        ${slotBadgeMarkup(item.slot, item.domain)}
      </div>
      <div class="progress-track"><span style="width:${item.percent}%"></span></div>
      <p>${escapeHtml(item.message)}</p>
      <p class="proto">${escapeHtml(item.source || "等待流水线事件")}</p>
      ${slotStatsMarkup(item)}
      <div class="card-stream">
        ${item.stream.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}
        ${item.status === "working" || item.status === "checking" ? '<div class="stream-cursor">▌</div>' : ""}
      </div>
      <div class="step-row">
        <span class="${item.step >= 1 ? "done" : ""}">抽取</span>
        <span class="${item.step >= 2 ? "done" : ""}">生成</span>
        <span class="${item.step >= 3 ? "done" : ""}">校验</span>
        <span class="${item.step >= 4 ? "done" : ""}">完成</span>
      </div>
    `;
    grid.appendChild(card);
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
      <p>${escapeHtml(typeEvent ? `已识别为 ${typeEvent.payload?.value || "product"} 类型，正在洗牌匹配源现象。` : (running ? "模型工人已启动，正在抽槽位。" : "任务已进入队列，准备发牌。"))}</p>
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

function slotStatsMarkup(item) {
  const runtime = runtimeMeta(item);
  return `
    <div class="slot-stats">
      <span><small>耗时</small><strong class="runtime-value" data-start-ms="${runtime.start || ""}" data-finish-ms="${runtime.finish || ""}">${escapeHtml(runtime.elapsedText)}</strong></span>
      <span><small>重抽</small><strong>${Number(item.rerollCount || 0)}</strong></span>
      <span><small>API</small><strong>${escapeHtml(item.apiStep || "等待生成")}</strong></span>
    </div>
  `;
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
  const scores = candidate.scores || {};
  const field = slotInfo.domain || candidate.source;
  const sourcePhenomenon = sourcePhenomenonText(slotInfo, candidate);
  const index = options.index ?? candidate.index ?? 1;
  const showFeedback = options.feedback !== false && candidate.id;
  const rerollCount = Number(candidate.reroll_count ?? candidate.rerollCount ?? slotInfo.rerollCount ?? 0);
  const qualityStatus = candidate.quality_status || candidate.search?.quality_status || "passed";
  const isFallback = Boolean(candidate.refund_credit || candidate.search?.refund_credit || qualityStatus === "fallback_refunded");
  const qualityNote = candidate.quality_note || candidate.search?.quality_note || "这张卡未通过质量阈值，系统已退回该卡积分。";
  const runtime = options.runtime || {};
  const advantage = normalizeAdvantage(candidate.advantage);
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
  card.className = `candidate${isFallback ? " quality-fallback" : ""}`;
  card.innerHTML = `
    <div class="candidate-top">
      <div class="candidate-title-block">
        <div class="candidate-meta-row">
          <span class="candidate-index">方案 ${String(index).padStart(2, "0")}</span>
          ${rerollCount > 0 ? `<span class="reroll-badge">重抽 ${rerollCount} 次</span>` : ""}
          ${isFallback ? '<span class="quality-badge">未达标 · 已退款</span>' : ""}
          ${runtime.elapsedText ? `<span class="runtime-badge"><span class="runtime-value" data-start-ms="${runtime.start || ""}" data-finish-ms="${runtime.finish || ""}">${escapeHtml(runtime.elapsedText)}</span> · ${escapeHtml(runtime.apiStep || "已通过")}</span>` : ""}
        </div>
        <h3>${escapeHtml(candidate.name)}</h3>
      </div>
      ${slotBadgeMarkup(candidate.slot, field)}
    </div>
    ${isFallback ? `
      <div class="quality-notice">
        <strong>保底答案</strong>
        <span>${escapeHtml(qualityNote)}</span>
      </div>
    ` : ""}
    <section class="candidate-section source-section">
      <div class="section-label">源现象</div>
      <p class="source-phenomenon">${escapeHtml(sourcePhenomenon)}</p>
      <div class="source-method">
        <span>抽象方法</span>
        <strong>${escapeHtml(candidate.source)}</strong>
      </div>
      <p class="proto">${escapeHtml(candidate.proto)}</p>
    </section>
    ${advantage ? `
      <section class="candidate-section advantage-section">
        <div class="section-label">优势</div>
        <p class="advantage">${escapeHtml(advantage)}</p>
      </section>
    ` : ""}
    <section class="candidate-section idea-section">
      <div class="section-label">落地方案</div>
      <p class="desc">${escapeHtml(candidate.desc)}</p>
    </section>
    <section class="candidate-section risk-section">
      <div class="section-label">失败边界</div>
      <p class="fail">${escapeHtml(candidate.fail)}</p>
    </section>
    <details class="mobile-card-details">
      <summary>更多细节</summary>
      <div>
        <span>抽象方法</span>
        <strong>${escapeHtml(candidate.source)}</strong>
        <p>${escapeHtml(candidate.proto)}</p>
      </div>
      <div>
        <span>失败边界</span>
        <p>${escapeHtml(candidate.fail)}</p>
      </div>
    </details>
    <div class="score-row">
      <span class="score-item"><small>结构</small><strong>${scores.structural_depth ?? "-"}</strong></span>
      <span class="score-item"><small>距离</small><strong>${scores.domain_distance ?? "-"}</strong></span>
      <span class="score-item"><small>新颖</small><strong>${scores.novelty ?? "-"}</strong></span>
      <span class="score-item"><small>可用</small><strong>${scores.applicability ?? "-"}</strong></span>
    </div>
    <div class="candidate-actions">
      <button type="button" data-action="poster">另存为海报</button>
    </div>
    ${showFeedback ? `
      <div class="feedback-row">
        <button type="button" data-label="useful" aria-pressed="false">有用</button>
        <button type="button" data-action="show-weak" aria-expanded="false">没用</button>
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
    ` : ""}
  `;
  card.querySelector('button[data-action="poster"]').addEventListener("click", () => openPoster(posterContext));
  if (showFeedback) {
    bindFeedbackControls(card, candidate);
  }
  return card;
}

function renderCandidates(candidates, events = []) {
  const grid = $("candidateGrid");
  grid.innerHTML = "";
  if (!candidates.length) return;
  const candidateSlots = buildCandidateSlotMap(events);
  candidates.forEach((candidate) => {
    const slotInfo = candidateSlots.get(candidate.name) || {};
    const card = renderCandidateArticle(candidate, slotInfo, { feedback: true });
    grid.appendChild(card);
  });
}

function bindFeedbackControls(card, candidate) {
  card.querySelector('button[data-action="show-weak"]').addEventListener("click", () => {
    toggleWeakFeedback(card, true);
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
  toggleWeakFeedback(card, weakSelected);
}

function isWeakFeedbackLabel(label) {
  return Boolean(label && label !== "useful");
}

function toggleWeakFeedback(card, show) {
  const weakPanel = card.querySelector(".weak-feedback");
  if (!weakPanel) return;
  weakPanel.classList.toggle("hidden", !show);
  const weakToggle = card.querySelector('button[data-action="show-weak"]');
  if (weakToggle) weakToggle.setAttribute("aria-expanded", show ? "true" : "false");
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
  state.adminOpen = false;
  state.historyDrawerOpen = false;
  const runSummary = state.runs.find((item) => item.id === runId);
  renderRuns();
  renderShell();
  renderRunTransition(runSummary, options);
  try {
    const data = await withMinimumDelay(api(`/api/runs/${runId}`), 320);
    renderCurrentRun(data.run);
    animateResultArrival();
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
  section.classList.add("result-switching");
  $("currentRunTitle").textContent = run?.problem || "正在调取记录";
  $("currentRunMeta").textContent = options.fromLaunch
    ? "任务已建立 · 正在接入实时进度"
    : (run ? `${statusLabel(run.status)} · 正在打开历史任务` : "正在打开历史任务");
  $("resultSection").dataset.activeRunStatus = "";
  $("resultSection").dataset.activeRunSnapshot = "{}";
  $("progressLog").innerHTML = `<div class="progress-item history-loading">${options.fromLaunch ? "正在接入抽卡流水线。" : "正在调取这次发散记录。"}</div>`;
  $("candidateGrid").innerHTML = `
    <div class="history-result-skeleton">
      <strong>${options.fromLaunch ? "正在接入卡片" : "正在整理卡片"}</strong>
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;
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
  const [metrics, queue, invites, users, feedback] = await Promise.all([
    api("/api/admin/metrics"),
    api("/api/admin/queue"),
    api("/api/admin/invite-codes"),
    api("/api/admin/users"),
    api("/api/admin/feedback"),
  ]);
  $("metrics").innerHTML = `
    <div class="metric"><span class="muted">用户</span><strong>${metrics.users}</strong></div>
    <div class="metric"><span class="muted">反馈</span><strong>${metrics.feedback}</strong></div>
    <div class="metric"><span class="muted">邀请码</span><strong>${invites.invite_codes.length}</strong></div>
    <div class="metric"><span class="muted">任务</span><strong>${Object.values(metrics.runs_by_status || {}).reduce((a, b) => a + b, 0)}</strong></div>
  `;
  renderQueueStatus(queue.queue);
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
  $("feedbackList").innerHTML = feedback.feedback.map((item) => `
    <div class="admin-row feedback-admin-row">
      <div class="feedback-admin-head">
        <div>
          <strong>${escapeHtml(feedbackLabel(item.label))}</strong>
          <span class="muted">${escapeHtml(item.user_email || "-")} · ${escapeHtml(item.run_problem || "-")}</span>
        </div>
        <span class="muted">${new Date(item.created_at).toLocaleString()}</span>
      </div>
      ${item.comment ? `<p class="feedback-comment">${escapeHtml(item.comment)}</p>` : ""}
      <div class="admin-card-snapshot">
        <div class="admin-card-top">
          <div>
            <span class="candidate-index">方案 ${formatAdminIndex(item.candidate_index)}</span>
            ${Number(item.candidate_reroll_count || 0) > 0 ? `<span class="reroll-badge">重抽 ${Number(item.candidate_reroll_count)} 次</span>` : ""}
            <strong>${escapeHtml(item.candidate_name || "-")}</strong>
          </div>
          ${slotBadgeMarkup(item.candidate_slot, item.candidate_domain || item.candidate_source)}
        </div>
        <div class="admin-card-block source">
          <span>源现象</span>
          <p>${escapeHtml(item.candidate_source_phenomenon || item.candidate_source || "-")}</p>
        </div>
        <div class="admin-card-block">
          <span>抽象方法</span>
          ${item.candidate_source ? `<strong>${escapeHtml(item.candidate_source)}</strong>` : ""}
          <p>${escapeHtml(item.candidate_proto || "-")}</p>
        </div>
        ${item.candidate_advantage ? `
          <div class="admin-card-block advantage">
            <span>优势</span>
            <p>${escapeHtml(normalizeAdvantage(item.candidate_advantage))}</p>
          </div>
        ` : ""}
        <div class="admin-card-block idea">
          <span>落地方案</span>
          <p>${escapeHtml(item.candidate_desc || "-")}</p>
        </div>
        <div class="admin-card-block risk">
          <span>失败边界</span>
          <p>${escapeHtml(item.candidate_fail || "-")}</p>
        </div>
        ${adminScoreRow(item.candidate_scores)}
      </div>
    </div>
  `).join("") || '<div class="muted">暂无反馈数据</div>';
}

function renderQueueStatus(queue) {
  const counts = queue?.counts || {};
  const workers = queue?.workers || [];
  const logs = queue?.recent_logs || [];
  const executorText = queue?.executor === "worker" ? "Worker 队列" : "本进程后台";
  const activeWorkers = workers.filter((worker) => worker.active).length;
  const oldestQueued = queue?.oldest_queued_at ? new Date(queue.oldest_queued_at).toLocaleString() : "无";
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
      <strong>最近日志</strong>
      ${logs.slice(0, 8).map((log) => `
        <div class="queue-log-row ${escapeHtml(log.level)}">
          <span>${escapeHtml(new Date(log.created_at).toLocaleTimeString())}</span>
          <div>
            <strong>${escapeHtml(log.message)}</strong>
            <small>${escapeHtml(log.run_problem || log.run_id || "system")}</small>
          </div>
        </div>
      `).join("") || '<div class="muted">暂无运行日志</div>'}
    </div>
  `;
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
  const minHeight = 1920;
  const pad = 46;
  const contentWidth = width - pad * 2;
  const sections = posterSections(candidate);

  canvas.width = width;
  canvas.height = 200;
  let ctx = canvas.getContext("2d");
  const headerLayout = posterHeaderLayout(ctx, candidate, contentWidth);
  const layouts = sections.map((section) => posterBlockLayout(ctx, section, contentWidth));
  const scoreHeight = 92;
  const footerHeight = 286;
  const totalSectionHeight = layouts.reduce((sum, item) => sum + item.height, 0) + Math.max(0, layouts.length - 1) * 18;
  const height = Math.max(minHeight, pad + headerLayout.height + totalSectionHeight + 18 + scoreHeight + footerHeight + pad);

  canvas.height = height;
  ctx = canvas.getContext("2d");
  drawPosterBackground(ctx, width, height);

  const paperX = 24;
  const paperY = 24;
  const paperW = width - 48;
  const paperH = height - 48;
  drawPosterRect(ctx, paperX + 5, paperY + 5, paperW, paperH, 14, "#2a2a2a", null, 0);
  drawPosterRect(ctx, paperX, paperY, paperW, paperH, 14, "#fffdf0", "#2a2a2a", 4);

  let y = pad;
  y = drawPosterHeader(ctx, candidate, pad, y, contentWidth, headerLayout);
  layouts.forEach((layout, index) => {
    drawPosterBlock(ctx, sections[index], layout, pad, y, contentWidth);
    y += layout.height + 18;
  });
  y = drawPosterScores(ctx, candidate.scores || {}, pad, y, contentWidth);
  drawPosterFooter(ctx, candidate, pad, y + 18, contentWidth, height - pad - (y + 18));
}

function posterSections(candidate) {
  const sourcePhenomenon = String(candidate.sourcePhenomenon || candidate.source || "").trim();
  return [
    {
      label: "源现象",
      text: sourcePhenomenon || "未记录源现象",
      background: "#edf4f7",
      accent: "#496fae",
      strong: true,
    },
    {
      label: "抽象方法",
      heading: candidate.source || "",
      text: candidate.proto || "未记录抽象方法",
      background: "#f2f6f8",
      accent: "#496fae",
    },
    {
      label: "优势",
      text: normalizeAdvantage(candidate.advantage),
      background: "#eaf6ea",
      accent: "#2a8a67",
      strong: true,
      floating: true,
    },
    {
      label: "落地方案",
      text: candidate.desc || "未记录落地方案",
      background: "#fff4bd",
      accent: "#2a8a67",
      large: true,
      strong: true,
      floating: true,
    },
    {
      label: "失败边界",
      text: candidate.fail || "未记录失败边界",
      background: "#fae8e3",
      accent: "#b86157",
    },
  ].filter((section) => section.text || section.heading);
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

function posterHeaderLayout(ctx, candidate, width) {
  const problem = posterProblemText(candidate);
  let problemLines = [];
  let problemHeight = 0;
  if (problem) {
    posterFont(ctx, 20, 900);
    problemLines = wrapPosterLines(ctx, problem, width - 36);
    problemHeight = 60 + problemLines.length * 30 + 18;
  }
  posterFont(ctx, 58, 900);
  const titleLines = wrapPosterLines(ctx, candidate.name || "未命名方案", width);
  const brandTop = problemHeight ? problemHeight + 24 : 0;
  const titleTop = brandTop + 150;
  const dividerTop = titleTop + titleLines.length * 68 + 36;
  return {
    problem,
    problemLines,
    problemHeight,
    brandTop,
    titleLines,
    titleTop,
    titleLineHeight: 68,
    dividerTop,
    height: dividerTop + 34,
  };
}

function drawPosterHeader(ctx, candidate, x, y, width, layout = posterHeaderLayout(ctx, candidate, width)) {
  const slotText = candidate.slotLabel || formatSlotBadge(candidate.slot, candidate.field);
  if (layout.problemLines.length) {
    drawPosterRect(ctx, x, y, width, layout.problemHeight, 8, "#edf4f7", "#2a2a2a", 3);
    drawPosterTag(ctx, x + 18, y + 18, "本次问题", "#f7df89");
    posterFont(ctx, 20, 900);
    ctx.fillStyle = "#1f2528";
    ctx.textBaseline = "top";
    layout.problemLines.forEach((line, index) => {
      ctx.fillText(line, x + 18, y + 62 + index * 30);
    });
    ctx.textBaseline = "alphabetic";
  }

  const brandY = y + layout.brandTop;
  drawPosterLogo(ctx, x, brandY, 62);
  posterFont(ctx, 28, 900);
  ctx.fillStyle = "#1f2528";
  ctx.fillText("WildIdea", x + 78, brandY + 27);
  posterFont(ctx, 16, 800);
  ctx.fillStyle = "#667078";
  ctx.fillText("帮你想出不一样的点子", x + 78, brandY + 54);

  const badgeW = 148;
  drawPosterRect(ctx, x + width - badgeW, brandY, badgeW, 88, 8, "#f3b17f", "#2a2a2a", 4);
  posterFont(ctx, 28, 900);
  ctx.fillStyle = "#111";
  ctx.textAlign = "center";
  const [slotCode, ...slotRest] = String(slotText || "").split(/\s+/);
  ctx.fillText(slotCode || "D?", x + width - badgeW / 2, brandY + 35);
  posterFont(ctx, 16, 900);
  ctx.fillText(slotRest.join(" ") || candidate.field || "", x + width - badgeW / 2, brandY + 62);
  ctx.textAlign = "left";

  const tagY = brandY + 98;
  drawPosterTag(ctx, x, tagY, `方案 ${String(candidate.index || 1).padStart(2, "0")}`, "#fff4bd");
  if (Number(candidate.reroll_count || 0) > 0) {
    drawPosterTag(ctx, x + 112, tagY, `重抽 ${Number(candidate.reroll_count)} 次`, "#fff1c6");
  }
  posterFont(ctx, 58, 900);
  ctx.fillStyle = "#111";
  ctx.textBaseline = "top";
  layout.titleLines.forEach((line, index) => {
    ctx.fillText(line, x, y + layout.titleTop + index * layout.titleLineHeight);
  });
  ctx.textBaseline = "alphabetic";

  ctx.strokeStyle = "#2a2a2a";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(x, y + layout.dividerTop);
  ctx.lineTo(x + width, y + layout.dividerTop);
  ctx.stroke();
  return y + layout.height;
}

function posterProblemText(candidate) {
  const problem = String(candidate.runProblem || "").trim();
  if (!problem || problem === "生成工作台") return "";
  return `问题：${problem}`;
}

function posterBlockLayout(ctx, section, width) {
  const pad = 24;
  const textWidth = width - pad * 2;
  posterFont(ctx, section.large ? 32 : 24, section.strong ? 900 : 700);
  const lines = wrapPosterLines(ctx, section.text || "", textWidth);
  let headingLines = [];
  if (section.heading) {
    posterFont(ctx, 22, 900);
    headingLines = wrapPosterLines(ctx, section.heading, textWidth);
  }
  const headingLineHeight = 32;
  const headingGap = headingLines.length ? 12 : 0;
  const headingHeight = headingLines.length ? headingLines.length * headingLineHeight + headingGap : 0;
  const textTop = 84;
  const lineHeight = section.large ? 50 : 40;
  return {
    lines,
    headingLines,
    headingLineHeight,
    lineHeight,
    textTop,
    height: textTop + headingHeight + lines.length * lineHeight + pad,
  };
}

function drawPosterBlock(ctx, section, layout, x, y, width) {
  const borderWidth = section.floating ? 4 : 3;
  if (section.floating) {
    drawPosterRect(ctx, x + 8, y + 8, width, layout.height, 8, "rgba(42, 42, 42, 0.72)", null, 0);
    drawPosterRect(ctx, x + 3, y + 3, width, layout.height, 8, "rgba(111, 207, 151, 0.18)", null, 0);
  }
  drawPosterRect(ctx, x, y, width, layout.height, 8, section.background, "#2a2a2a", borderWidth);
  drawPosterRect(ctx, x, y, section.floating ? 12 : 8, layout.height, 0, section.accent, null, 0);
  drawPosterTag(ctx, x + 22, y + 22, section.label, "#f7df89");
  let cursor = y + layout.textTop;
  ctx.textBaseline = "top";
  if (layout.headingLines.length) {
    posterFont(ctx, 22, 900);
    ctx.fillStyle = "#111";
    layout.headingLines.forEach((line) => {
      ctx.fillText(line, x + 22, cursor);
      cursor += layout.headingLineHeight;
    });
    cursor += 12;
  }
  posterFont(ctx, section.large ? 32 : 24, section.strong ? 900 : 700);
  ctx.fillStyle = "#1f2528";
  layout.lines.forEach((line) => {
    ctx.fillText(line, x + 22, cursor);
    cursor += layout.lineHeight;
  });
  ctx.textBaseline = "alphabetic";
}

function drawPosterScores(ctx, scores, x, y, width) {
  const items = [
    ["结构", scores.structural_depth ?? "-"],
    ["距离", scores.domain_distance ?? "-"],
    ["新颖", scores.novelty ?? "-"],
    ["可用", scores.applicability ?? "-"],
  ];
  const gap = 12;
  const cellW = (width - gap * 3) / 4;
  items.forEach(([label, value], index) => {
    const cellX = x + index * (cellW + gap);
    drawPosterRect(ctx, cellX, y, cellW, 92, 6, "#edf4f7", "#2a2a2a", 3);
    posterFont(ctx, 18, 900);
    ctx.fillStyle = "#496fae";
    ctx.fillText(label, cellX + 16, y + 30);
    posterFont(ctx, 38, 900);
    ctx.fillStyle = "#111";
    ctx.fillText(String(value), cellX + 16, y + 72);
  });
  return y + 92;
}

function drawPosterFooter(ctx, candidate, x, y, width, minHeight = 260) {
  const qrSize = 178;
  const qrX = x;
  const qrY = y + 14;
  drawPosterQr(ctx, posterSiteUrl(), qrX, qrY, qrSize);

  const textX = qrX + qrSize + 26;
  posterFont(ctx, 20, 900);
  ctx.fillStyle = "#111";
  ctx.fillText("扫码打开网站", textX, y + 48);
  posterFont(ctx, 14, 800);
  ctx.fillStyle = "#667078";
  drawPosterWrappedText(ctx, posterSiteUrl(), textX, y + 78, width - qrSize - 26, 22);

  posterFont(ctx, 17, 800);
  ctx.fillStyle = "#667078";
  drawPosterWrappedText(ctx, "WildIdea 生成结果海报", textX, y + 138, width - qrSize - 26, 24);
  posterFont(ctx, 13, 800);
  ctx.fillStyle = "#8a7d70";
  ctx.fillText(`Generated by WildIdea · ${new Date().toLocaleDateString()}`, textX, y + Math.max(192, minHeight - 18));
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
  posterFont(ctx, 16, 900);
  const width = Math.ceil(ctx.measureText(text).width) + 22;
  drawPosterRect(ctx, x, y, width, 32, 4, fill, "#2a2a2a", 3);
  ctx.fillStyle = "#111";
  ctx.fillText(text, x + 11, y + 22);
  return width;
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
  $("historySearch").value = "";
  state.animatedProgressCards.clear();
  renderShell();
  renderRuns();
  renderCurrentRun(null);
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
    renderShell();
    showToast(`兑换成功，增加 ${data.bonus_credits} 积分`);
  } catch (err) {
    showToast(err.message);
  }
});

$("runForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("runSubmit").disabled = true;
  const problemText = $("problem").value.trim();
  if (!problemText) {
    showToast("请先填写问题");
    $("problem").focus();
    $("runSubmit").disabled = false;
    return;
  }
  const forbidTerms = $("forbidTerms").value.split(/\s+/).map((item) => item.trim()).filter(Boolean);
  beginSearchLaunch(problemText);
  try {
    const slotCount = Math.max(1, Math.min(10, Number($("slotCount").value || 10)));
    const data = await withMinimumDelay(api("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        problem: problemText,
        slot_count: slotCount,
        forbid_terms: forbidTerms,
      }),
    }), SEARCH_LAUNCH_MIN_MS);
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
$("refreshAdminBtn").addEventListener("click", loadAdmin);
$("exportFeedbackBtn").addEventListener("click", downloadFeedbackExcel);
$("slotCount").addEventListener("input", updateRunCostLabel);
$("posterCloseBtn").addEventListener("click", closePoster);
$("posterBackdrop").addEventListener("click", closePoster);
$("posterDownloadBtn").addEventListener("click", downloadPoster);
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("posterModal").classList.contains("hidden")) closePoster();
});

$("inviteForm").addEventListener("submit", async (event) => {
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
});

setAuthMode("login");
updateRunCostLabel();
renderShell();
loadMe();
