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
};

const DRAW_CARD_DELAY_MS = 170;

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
  $("authPanel").classList.toggle("hidden", booting || loggedIn);
  $("userPanel").classList.toggle("hidden", !loggedIn);
  $("historyPanel").classList.toggle("hidden", !loggedIn);
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
  const count = Math.max(1, Math.min(30, Number($("slotCount")?.value || 10)));
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
  const signature = state.runs.map((run) => `${run.id}:${run.status}:${run.created_at}`).join("|");
  const shouldAnimate = signature !== state.runListSignature;
  state.runListSignature = signature;
  list.classList.remove("run-list-arrive", "run-list-loading");
  list.innerHTML = "";
  if (!state.runs.length) {
    list.innerHTML = '<div class="muted">暂无历史任务</div>';
    if (shouldAnimate) requestAnimationFrame(() => list.classList.add("run-list-arrive"));
    return;
  }
  state.runs.forEach((run, index) => {
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
  const estimateText = formatQueueEstimate(queueRemainingSeconds(queue));
  const aheadText = usersAhead > 0
    ? `前面还有 ${usersAhead} 位用户、${tasksAhead} 个任务`
    : (tasksAhead > 0 ? `前面还有 ${tasksAhead} 个任务` : "前面没有其他用户");
  const detailText = tasksAhead > 0 ? `其中生成中 ${runningAhead} 个、排队 ${queuedAhead} 个。` : "轮到你后会自动开始抽卡。";
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
  const ok = events.filter((event) => event.event_type === "candidate_ok").length;
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
    if (event.event_type === "candidate_ok" && payload.name && payload.slot_id) {
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
      item.message = `正在等待模型返回，第 ${payload.attempt || 1} 次尝试${waitingDots()}`;
      const recentHistory = item.history.slice(-3);
      item.stream = [
        ...recentHistory,
        "> worker attached",
        `> attempt ${payload.attempt || 1}: freeze source mechanism`,
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
    } else if (event.event_type === "candidate_ok") {
      item.status = "done";
      item.step = 4;
      item.percent = 100;
      item.title = payload.name || item.title;
      item.finishedAt = eventAt;
      item.attempt = Number(payload.attempt || item.attempt || 1);
      item.rerollCount = Number(payload.reroll_count ?? item.rerollCount ?? 0);
      item.apiStep = "已通过";
      item.message = "候选已通过基础校验和评分阈值。";
      const liveCandidate = {
        index: payload.index || payload.done,
        name: payload.name || item.title,
        slot: payload.slot || item.slot,
        source: payload.source || "",
        proto: payload.proto || "",
        desc: payload.desc || "",
        fail: payload.fail || "",
        reroll_count: payload.reroll_count ?? item.rerollCount ?? 0,
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
        "> quality gate passed",
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
        `> attempt ${payload.attempt || 1}: judge scoring`,
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
        `> reroll attempt ${(payload.attempt || 1) + 1}`,
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
  const runtime = options.runtime || {};
  const card = document.createElement("article");
  card.className = "candidate";
  card.innerHTML = `
    <div class="candidate-top">
      <div class="candidate-title-block">
        <div class="candidate-meta-row">
          <span class="candidate-index">方案 ${String(index).padStart(2, "0")}</span>
          ${rerollCount > 0 ? `<span class="reroll-badge">重抽 ${rerollCount} 次</span>` : ""}
          ${runtime.elapsedText ? `<span class="runtime-badge"><span class="runtime-value" data-start-ms="${runtime.start || ""}" data-finish-ms="${runtime.finish || ""}">${escapeHtml(runtime.elapsedText)}</span> · ${escapeHtml(runtime.apiStep || "已通过")}</span>` : ""}
        </div>
        <h3>${escapeHtml(candidate.name)}</h3>
      </div>
      ${slotBadgeMarkup(candidate.slot, field)}
    </div>
    <section class="candidate-section source-section">
      <div class="section-label">源现象</div>
      <p class="source-phenomenon">${escapeHtml(sourcePhenomenon)}</p>
      <div class="source-method">
        <span>抽象方法</span>
        <strong>${escapeHtml(candidate.source)}</strong>
      </div>
      <p class="proto">${escapeHtml(candidate.proto)}</p>
    </section>
    <section class="candidate-section idea-section">
      <div class="section-label">落地方案</div>
      <p class="desc">${escapeHtml(candidate.desc)}</p>
    </section>
    <section class="candidate-section risk-section">
      <div class="section-label">失败边界</div>
      <p class="fail">${escapeHtml(candidate.fail)}</p>
    </section>
    <div class="score-row">
      <span class="score-item"><small>结构</small><strong>${scores.structural_depth ?? "-"}</strong></span>
      <span class="score-item"><small>距离</small><strong>${scores.domain_distance ?? "-"}</strong></span>
      <span class="score-item"><small>新颖</small><strong>${scores.novelty ?? "-"}</strong></span>
      <span class="score-item"><small>可用</small><strong>${scores.applicability ?? "-"}</strong></span>
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
    if (event.event_type !== "candidate_ok") return;
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

async function selectRun(runId) {
  stopWatching();
  state.currentRunId = runId;
  state.searchOpen = false;
  state.launchingSearch = false;
  state.adminOpen = false;
  const runSummary = state.runs.find((item) => item.id === runId);
  renderRuns();
  renderShell();
  renderRunTransition(runSummary);
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

function renderRunTransition(run) {
  const section = $("resultSection");
  section.classList.remove("result-arrive");
  section.classList.add("result-switching");
  $("currentRunTitle").textContent = run?.problem || "正在调取记录";
  $("currentRunMeta").textContent = run ? `${statusLabel(run.status)} · 正在打开历史任务` : "正在打开历史任务";
  $("resultSection").dataset.activeRunStatus = "";
  $("resultSection").dataset.activeRunSnapshot = "{}";
  $("progressLog").innerHTML = '<div class="progress-item history-loading">正在调取这次发散记录。</div>';
  $("candidateGrid").innerHTML = `
    <div class="history-result-skeleton">
      <strong>正在整理卡片</strong>
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
    window.setTimeout(() => section.classList.remove("result-arrive"), 900);
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
        <p class="muted">排队 ${Number(queue?.queued || 0)} · 生成中 ${Number(queue?.running || 0)} · 活跃 worker ${activeWorkers}/${workers.length}</p>
      </div>
      <div class="queue-chips">
        <span>Queued ${counts.queued || 0}</span>
        <span>Running ${counts.running || 0}</span>
        <span>Done ${counts.succeeded || 0}</span>
        <span>Failed ${counts.failed || 0}</span>
      </div>
    </div>
    <div class="queue-meta">
      <span>最早排队 ${escapeHtml(oldestQueued)}</span>
      <span>轮询 ${escapeHtml(queue?.worker_poll_seconds ?? "-")}s</span>
      <span>用户活跃任务上限 ${escapeHtml(queue?.user_active_run_limit ?? "-")}</span>
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
    const data = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        problem: problemText,
        slot_count: Number($("slotCount").value || 10),
        forbid_terms: forbidTerms,
      }),
    });
    state.user.credit_balance = data.credit_balance;
    renderShell();
    await loadRuns();
    await selectRun(data.run.id);
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
$("refreshAdminBtn").addEventListener("click", loadAdmin);
$("exportFeedbackBtn").addEventListener("click", downloadFeedbackExcel);
$("slotCount").addEventListener("input", updateRunCostLabel);

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
