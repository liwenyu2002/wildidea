const STORAGE_KEY = "wildidea:card-design-lab:formal-v5";
const previewFrame = document.getElementById("previewFrame");
const previewCard = document.getElementById("previewCard");
const zoneEls = {
  source: document.querySelector('[data-lab-zone="source"]'),
  idea: document.querySelector('[data-lab-zone="idea"]'),
  advantage: document.querySelector('[data-lab-zone="advantage"]'),
  feedback: document.querySelector('[data-lab-zone="feedback"]'),
};
const zoneTextSelectors = {
  source: "#sourceText",
  idea: "#ideaText",
  advantage: "#advantageText",
  feedback: "#feedbackText",
};
const defaultDesign = {
  card: {
    cardWidth: 321,
    cardHeight: 492,
    radius: 27,
    outerStroke: 4,
    pixelOutline: 3,
    cardPad: 17,
  },
  zones: {
    source: { x: -1, y: 0, w: 0, h: 0, pad: 0, labelX: -10, labelY: -13, font: 13, minFont: 6.8 },
    idea: { x: -1, y: 0, w: 0, h: 0, pad: 0, labelX: -11, labelY: -13, font: 15.5, minFont: 6.8 },
    advantage: { x: 0, y: 0, w: 0, h: 0, pad: 0, labelX: -11, labelY: -13, font: 13.5, minFont: 6.8 },
    feedback: { x: 0, y: 0, w: 0, h: 0, pad: 0, labelX: 0, labelY: 0, font: 0, minFont: 7 },
  },
  text: {
    titleText: "可撤回灵感缓冲器",
    sourceText: "Undo Send 给用户短暂撤回窗口，降低误操作带来的心理压力。",
    ideaText: "在相册 app 中给每次批量删除、公开分享和隐私移动加入 8 秒“可撤回缓冲层”。用户操作后不是立刻生效，而是进入一个可视化缓冲条；系统先展示影响范围、可恢复路径和隐私风险提示。若用户没有撤回，动作再正式提交。",
    advantageText: "这种方案的优势在于，让高风险操作变得可控，减少用户误删、误分享后的焦虑。",
    feedbackText: "这张卡有启发吗？",
  },
};

let design = loadDesign();
let selectedZone = "idea";
let dragState = null;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function mergeDesign(base, extra) {
  return {
    card: { ...base.card, ...(extra.card || {}) },
    zones: {
      source: { ...base.zones.source, ...(extra.zones?.source || {}) },
      idea: { ...base.zones.idea, ...(extra.zones?.idea || {}) },
      advantage: { ...base.zones.advantage, ...(extra.zones?.advantage || {}) },
      feedback: { ...base.zones.feedback, ...(extra.zones?.feedback || {}) },
    },
    text: { ...base.text, ...(extra.text || {}) },
  };
}

function loadDesign() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved?.card && saved?.zones) return mergeDesign(defaultDesign, saved);
  } catch {
    return clone(defaultDesign);
  }
  return clone(defaultDesign);
}

function saveDesign() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(design));
}

function applyDesign() {
  const root = document.documentElement;
  const pixelOn = Number(design.card.pixelOutline) > 0;
  root.style.setProperty("--idea-card-width", `${pixelRenderSize(design.card, "cardWidth")}px`);
  root.style.setProperty("--idea-card-height", `${pixelRenderSize(design.card, "cardHeight")}px`);
  root.style.setProperty("--flow-card-radius", `${pixelRadius(design.card)}px`);
  root.style.setProperty("--flow-card-border", `${design.card.outerStroke}px`);
  root.style.setProperty("--lab-pixel-unit", `${Math.max(1, Number(design.card.pixelOutline || 0))}px`);
  root.style.setProperty("--lab-pixel-border", `${pixelBorderSize(design.card)}px`);
  root.style.setProperty("--lab-card-pixel-clip", buildPixelClipPath(design.card));
  root.style.setProperty("--lab-frame-pixel-clip", buildFramePixelClipPath(design.card));
  previewFrame?.classList.toggle("pixel-outline", pixelOn);
  previewCard.style.padding = `${design.card.cardPad}px`;

  Object.entries(zoneEls).forEach(([key, el]) => {
    const cfg = design.zones[key];
    if (!el || !cfg) return;
    el.style.transform = cfg.x || cfg.y ? `translate(${cfg.x}px, ${cfg.y}px)` : "";
    el.style.width = cfg.w > 0 ? `${cfg.w}px` : "";
    el.style.height = cfg.h > 0 ? `${cfg.h}px` : "";
    el.style.padding = cfg.pad > 0 ? `${cfg.pad}px` : "";
    const label = el.querySelector(".section-label");
    if (label) {
      label.style.left = `${cfg.labelX}px`;
      label.style.top = `${cfg.labelY}px`;
    }
    const textEl = document.querySelector(zoneTextSelectors[key]);
    if (textEl) {
      textEl.dataset.fitMin = String(cfg.minFont);
      if (cfg.font > 0) {
        textEl.dataset.labFont = String(cfg.font);
      } else {
        delete textEl.dataset.labFont;
      }
    }
    el.classList.toggle("is-selected", key === selectedZone);
  });

  Object.entries(design.text).forEach(([id, value]) => {
    const el = document.getElementById(id);
    const input = document.querySelector(`[data-text="${id}"]`);
    if (el) el.textContent = value;
    if (input && input.value !== value) input.value = value;
  });

  syncControls();
  fitAllText();
  writeJsonBox();
  saveDesign();
}

function syncControls() {
  document.querySelectorAll("[data-control]").forEach((input) => {
    const key = input.dataset.control;
    if (key === "radius") input.disabled = false;
    input.value = design.card[key];
    setOutput(input, design.card[key], key);
  });
  document.querySelectorAll("[data-zone-control]").forEach((input) => {
    const key = input.dataset.zoneControl;
    input.value = design.zones[selectedZone][key];
    setOutput(input, design.zones[selectedZone][key], key);
  });
  document.querySelectorAll("[data-select-zone]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.selectZone === selectedZone);
  });
}

function setOutput(input, value, key = "") {
  const output = input.parentElement.querySelector("output");
  if (!output) return;
  if (key === "pixelOutline") {
    output.textContent = Number(value) === 0 ? "关闭" : `${value}px`;
    return;
  }
  if ((key === "w" || key === "h" || key === "pad" || key === "font") && Number(value) === 0) {
    output.textContent = "自动";
    return;
  }
  output.textContent = key === "x" || key === "y" ? signed(value) : value;
}

function signed(value) {
  const number = Number(value);
  return number > 0 ? `+${number}` : String(number);
}

function fitAllText() {
  if (!previewCard) return;
  const items = Array.from(previewCard.querySelectorAll("[data-fit-text]")).filter((item) => item.offsetParent !== null);
  if (!items.length) return;
  items.forEach(resetFitTextItem);
  shrinkTextUntilFits(previewCard, items, 48);
  previewCard.querySelectorAll("[data-fit-container]").forEach((container) => {
    const localItems = Array.from(container.querySelectorAll("[data-fit-text]")).filter((item) => item.offsetParent !== null);
    shrinkTextUntilFits(container, localItems, 42);
  });
}

function resetFitTextItem(item) {
  item.style.fontSize = "";
  item.style.lineHeight = "";
  const manual = Number.parseFloat(item.dataset.labFont || "0");
  if (manual > 0) {
    item.style.fontSize = `${manual}px`;
    item.style.lineHeight = `${manual * 1.25}px`;
  }
  const computed = getComputedStyle(item);
  const size = manual || Number.parseFloat(computed.fontSize) || 12;
  const lineHeight = Number.parseFloat(computed.lineHeight) || size * 1.25;
  item.dataset.fitBaseSize = String(size);
  item.dataset.fitLineRatio = String(lineHeight / size);
  item.style.setProperty("font-size", `${size}px`);
  item.style.setProperty("line-height", `${lineHeight}px`);
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

function writeJsonBox() {
  document.getElementById("jsonBox").value = JSON.stringify(design, null, 2);
}

function buildPixelClipPath(card) {
  return buildRasterRoundedRectClip({
    width: pixelRenderSize(card, "cardWidth"),
    height: pixelRenderSize(card, "cardHeight"),
    radius: pixelRadius(card),
    unit: Number(card.pixelOutline || 0),
  });
}

function buildFramePixelClipPath(card) {
  const stroke = pixelBorderSize(card);
  return buildRasterRoundedRectClip({
    width: pixelRenderSize(card, "cardWidth") + stroke * 2,
    height: pixelRenderSize(card, "cardHeight") + stroke * 2,
    radius: pixelRadius(card) + stroke,
    unit: Number(card.pixelOutline || 0),
  });
}

function pixelRenderSize(card, key) {
  const fallback = defaultDesign.card[key] || 1;
  const size = Math.max(1, Number(card[key] || fallback));
  const unit = Number(card.pixelOutline || 0);
  if (unit <= 0) return size;
  const safeUnit = Math.max(1, unit);
  return Math.ceil(size / safeUnit) * safeUnit;
}

function pixelRadius(card) {
  const radius = Math.max(0, Number(card.radius || 0));
  const unit = Number(card.pixelOutline || 0);
  if (unit <= 0 || radius <= 0) return radius;
  const safeUnit = Math.max(1, unit);
  return Math.ceil(radius / safeUnit) * safeUnit;
}

function pixelBorderSize(card) {
  const unit = Number(card.pixelOutline || 0);
  const stroke = Math.max(0, Number(card.outerStroke || 0));
  if (unit <= 0) return stroke;
  return Math.max(unit, Math.ceil(stroke / unit) * unit);
}

function buildRasterRoundedRectClip({ width, height, radius, unit }) {
  const safeWidth = Math.max(1, width);
  const safeHeight = Math.max(1, height);
  const rawUnit = Number(unit || 0);
  if (rawUnit <= 0) return "none";
  const safeUnit = Math.max(1, rawUnit);
  const maxRadius = Math.floor(Math.min(safeWidth, safeHeight) / 2);
  const safeRadius = Math.max(0, Math.min(Number(radius || 0), maxRadius));
  if (safeRadius <= 0) {
    return `polygon(0 0, ${formatPx(safeWidth)} 0, ${formatPx(safeWidth)} ${formatPx(safeHeight)}, 0 ${formatPx(safeHeight)})`;
  }

  const xEdges = buildGridEdges(safeWidth, safeUnit);
  const yEdges = buildGridEdges(safeHeight, safeUnit);
  const cols = xEdges.length - 1;
  const rows = yEdges.length - 1;
  const filled = Array.from({ length: rows }, () => Array(cols).fill(false));

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const x = (xEdges[col] + xEdges[col + 1]) / 2;
      const y = (yEdges[row] + yEdges[row + 1]) / 2;
      filled[row][col] = pointInRoundedRect(x, y, safeWidth, safeHeight, safeRadius);
    }
  }

  const polygon = traceFilledGrid(filled, xEdges, yEdges);
  if (!polygon.length) return "none";
  return `polygon(${polygon.map((point) => `${formatPx(point.x)} ${formatPx(point.y)}`).join(", ")})`;
}

function buildGridEdges(size, unit) {
  const edges = [0];
  for (let value = unit; value < size; value += unit) {
    edges.push(Math.round(value * 100) / 100);
  }
  edges.push(size);
  return edges;
}

function pointInRoundedRect(x, y, width, height, radius) {
  const cx = clampNumber(x, radius, width - radius);
  const cy = clampNumber(y, radius, height - radius);
  const dx = x - cx;
  const dy = y - cy;
  return dx * dx + dy * dy <= radius * radius;
}

function traceFilledGrid(filled, xEdges, yEdges) {
  const rows = filled.length;
  const cols = filled[0]?.length || 0;
  const edges = new Map();
  const key = (x, y) => `${formatNumber(x)},${formatNumber(y)}`;
  const addEdge = (startX, startY, endX, endY) => {
    edges.set(key(startX, startY), { x: endX, y: endY });
  };
  const isFilled = (row, col) => row >= 0 && row < rows && col >= 0 && col < cols && filled[row][col];

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      if (!filled[row][col]) continue;
      const x0 = xEdges[col];
      const x1 = xEdges[col + 1];
      const y0 = yEdges[row];
      const y1 = yEdges[row + 1];
      if (!isFilled(row - 1, col)) addEdge(x0, y0, x1, y0);
      if (!isFilled(row, col + 1)) addEdge(x1, y0, x1, y1);
      if (!isFilled(row + 1, col)) addEdge(x1, y1, x0, y1);
      if (!isFilled(row, col - 1)) addEdge(x0, y1, x0, y0);
    }
  }

  if (!edges.size) return [];
  const startKey = Array.from(edges.keys()).sort((a, b) => {
    const [ax, ay] = a.split(",").map(Number);
    const [bx, by] = b.split(",").map(Number);
    return ay - by || ax - bx;
  })[0];
  const [startX, startY] = startKey.split(",").map(Number);
  const points = [{ x: startX, y: startY }];
  let cursor = startKey;
  const maxSteps = edges.size + 2;

  for (let i = 0; i < maxSteps; i += 1) {
    const next = edges.get(cursor);
    if (!next) break;
    const nextKey = key(next.x, next.y);
    if (nextKey === startKey) break;
    points.push({ x: next.x, y: next.y });
    cursor = nextKey;
  }

  return simplifyPolygon(points);
}

function simplifyPolygon(points) {
  if (points.length <= 2) return points;
  const simplified = [];
  const count = points.length;
  for (let index = 0; index < count; index += 1) {
    const prev = points[(index - 1 + count) % count];
    const current = points[index];
    const next = points[(index + 1) % count];
    const sameVertical = nearlyEqual(prev.x, current.x) && nearlyEqual(current.x, next.x);
    const sameHorizontal = nearlyEqual(prev.y, current.y) && nearlyEqual(current.y, next.y);
    if (!sameVertical && !sameHorizontal) simplified.push(current);
  }
  return simplified;
}

function clampNumber(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function nearlyEqual(a, b) {
  return Math.abs(a - b) < 0.01;
}

function formatPx(value) {
  const rounded = Math.round(value * 100) / 100;
  return `${rounded}px`;
}

function formatNumber(value) {
  return String(Math.round(value * 100) / 100);
}

function zoneCss(selector, cfg, textSelector) {
  const lines = [
    `${selector} {`,
    cfg.x || cfg.y ? `  transform: translate(${cfg.x}px, ${cfg.y}px);` : "",
    cfg.w > 0 ? `  width: ${cfg.w}px;` : "",
    cfg.h > 0 ? `  height: ${cfg.h}px;` : "",
    cfg.pad > 0 ? `  padding: ${cfg.pad}px;` : "",
    "}",
    `${selector} .section-label { left: ${cfg.labelX}px; top: ${cfg.labelY}px; }`,
    cfg.font > 0 ? `${selector} ${textSelector} { font-size: ${cfg.font}px; line-height: ${cfg.font * 1.25}px; }` : "",
  ];
  return lines.filter(Boolean).join("\n");
}

function cssVariables() {
  const z = design.zones;
  return `:root {
  --idea-card-width: ${pixelRenderSize(design.card, "cardWidth")}px;
  --idea-card-height: ${pixelRenderSize(design.card, "cardHeight")}px;
  --flow-card-radius: ${pixelRadius(design.card)}px;
  --flow-card-border: ${design.card.outerStroke}px;
  --lab-pixel-border: ${pixelBorderSize(design.card)}px;
  --idea-card-inner-padding: ${design.card.cardPad}px;
  --idea-card-frame-width: calc(var(--idea-card-width) + (var(--lab-pixel-border) * 2));
  --idea-card-frame-height: calc(var(--idea-card-height) + (var(--lab-pixel-border) * 2));
  --idea-card-max-row: calc((var(--idea-card-frame-width) * 3) + (var(--idea-card-gap) * 2));
  --lab-card-pixel-clip: ${buildPixelClipPath(design.card)};
  --lab-frame-pixel-clip: ${buildFramePixelClipPath(design.card)};
}

.compact-card-grid.result-card-grid .result-card {
  padding: var(--idea-card-inner-padding);
}

${design.card.pixelOutline > 0 ? `.compact-card-grid.result-card-grid .result-card {
  border: 0 !important;
  border-radius: 0 !important;
  box-shadow:
    inset 0 0 0 1px rgba(91, 98, 104, 0.30),
    inset 1px 1px 0 rgba(255, 255, 255, 0.62),
    inset -2px -2px 0 rgba(42, 42, 42, 0.10) !important;
  clip-path: var(--lab-card-pixel-clip) !important;
}

.pixel-frame {
  --b: ${pixelBorderSize(design.card)}px;
  background: var(--line);
  clip-path: var(--lab-frame-pixel-clip);
  flex: 0 0 var(--idea-card-frame-width);
  height: var(--idea-card-frame-height);
  max-width: var(--idea-card-frame-width);
  overflow: hidden;
  padding: var(--b);
  position: relative;
  transition:
    filter 140ms ease,
    transform 140ms ease;
  width: var(--idea-card-frame-width);
}

.pixel-frame:hover {
  filter: brightness(1.01);
  transform: translate(1px, 1px);
}

.pixel-frame::before {
  display: none;
}

.pixel-frame > .result-card {
  --card-shell-bg: #fffaf0;
  background: var(--card-shell-bg) !important;
  height: var(--idea-card-height);
  max-height: var(--idea-card-height);
  min-height: var(--idea-card-height);
  padding: var(--idea-card-inner-padding);
  position: relative;
  transform: none !important;
  width: var(--idea-card-width);
  z-index: 1;
}

.pixel-frame > .result-card:hover {
  box-shadow:
    inset 0 0 0 1px rgba(91, 98, 104, 0.30),
    inset 1px 1px 0 rgba(255, 255, 255, 0.62),
    inset -2px -2px 0 rgba(42, 42, 42, 0.10) !important;
  transform: none !important;
}

.pixel-frame:hover > .result-card {
  box-shadow:
    inset 0 0 0 1px rgba(91, 98, 104, 0.30),
    inset 1px 1px 0 rgba(255, 255, 255, 0.62),
    inset -2px -2px 0 rgba(42, 42, 42, 0.10) !important;
  transform: none !important;
}

.candidate-grid.compact-card-grid > .candidate,
.candidate-grid.compact-card-grid.result-card-grid > .candidate {
  flex: 0 0 var(--idea-card-frame-width);
  max-width: var(--idea-card-frame-width);
  width: var(--idea-card-frame-width);
}

.printer-draw-card,
.candidate-grid.compact-card-grid > .candidate {
  --card-shell-bg: #fffaf0;
  background: var(--line) !important;
  border: 0 !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  clip-path: var(--lab-frame-pixel-clip) !important;
  height: var(--idea-card-frame-height);
  max-height: var(--idea-card-frame-height);
  min-height: var(--idea-card-frame-height);
  overflow: hidden;
  padding: calc(var(--lab-pixel-border) + var(--idea-card-inner-padding));
  isolation: isolate;
}

.printer-draw-card::before,
.candidate-grid.compact-card-grid > .candidate::before {
  background: var(--card-shell-bg);
  box-shadow:
    inset 0 0 0 1px rgba(91, 98, 104, 0.30),
    inset 1px 1px 0 rgba(255, 255, 255, 0.62),
    inset -2px -2px 0 rgba(42, 42, 42, 0.10);
  clip-path: var(--lab-card-pixel-clip);
  content: "";
  inset: var(--lab-pixel-border);
  pointer-events: none;
  position: absolute;
  z-index: 0;
}

.printer-draw-card > *,
.candidate-grid.compact-card-grid > .candidate > :not(.slot-preview) {
  position: relative;
  z-index: 1;
}

.progress-card.draw-enter .slot-preview {
  clip-path: var(--lab-card-pixel-clip);
  inset: var(--lab-pixel-border);
}` : ""}

${zoneCss(".compact-card-grid.result-card-grid .result-card .source-section", z.source, ".source-phenomenon")}

${zoneCss(".compact-card-grid.result-card-grid .result-card .idea-section", z.idea, ".desc")}

${zoneCss(".compact-card-grid.result-card-grid .result-card .advantage-section", z.advantage, ".advantage")}

${zoneCss(".compact-card-grid.result-card-grid .result-card .card-response-row", z.feedback, ".feedback-prompt strong")}`;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(toast.__timer);
  toast.__timer = window.setTimeout(() => { toast.hidden = true; }, 1800);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(`${label} 已复制`);
  } catch {
    document.getElementById("jsonBox").value = text;
    showToast(`${label} 已放到文本框`);
  }
}

function setSelectedZone(zone) {
  if (!zoneEls[zone]) return;
  selectedZone = zone;
  applyDesign();
}

function bindControls() {
  document.querySelectorAll("[data-control]").forEach((input) => {
    input.addEventListener("input", () => {
      design.card[input.dataset.control] = Number(input.value);
      applyDesign();
    });
  });
  document.querySelectorAll("[data-zone-control]").forEach((input) => {
    input.addEventListener("input", () => {
      design.zones[selectedZone][input.dataset.zoneControl] = Number(input.value);
      applyDesign();
    });
  });
  document.querySelectorAll("[data-select-zone]").forEach((btn) => {
    btn.addEventListener("click", () => setSelectedZone(btn.dataset.selectZone));
  });
  document.querySelectorAll("[data-text]").forEach((input) => {
    input.addEventListener("input", () => {
      design.text[input.dataset.text] = input.value;
      applyDesign();
    });
  });
}

function bindDragging() {
  Object.entries(zoneEls).forEach(([key, el]) => {
    el.addEventListener("pointerdown", (event) => {
      if (event.target.closest("button, input, textarea, a, summary")) return;
      setSelectedZone(key);
      el.setPointerCapture(event.pointerId);
      dragState = {
        zone: key,
        startX: event.clientX,
        startY: event.clientY,
        originX: design.zones[key].x,
        originY: design.zones[key].y,
      };
    });
    el.addEventListener("pointermove", (event) => {
      if (!dragState || dragState.zone !== key) return;
      const nextX = dragState.originX + event.clientX - dragState.startX;
      const nextY = dragState.originY + event.clientY - dragState.startY;
      const cfg = design.zones[key];
      cfg.x = clamp(Math.round(nextX), -40, 40);
      cfg.y = clamp(Math.round(nextY), -40, 40);
      applyDesign();
    });
    el.addEventListener("pointerup", () => {
      dragState = null;
    });
    el.addEventListener("pointercancel", () => {
      dragState = null;
    });
  });
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

document.getElementById("copyJsonBtn").addEventListener("click", () => copyText(JSON.stringify(design, null, 2), "JSON"));
document.getElementById("copyCssBtn").addEventListener("click", () => copyText(cssVariables(), "CSS 变量"));
document.getElementById("resetBtn").addEventListener("click", () => {
  design = clone(defaultDesign);
  applyDesign();
});
document.getElementById("longTextBtn").addEventListener("click", () => {
  design.text.ideaText = "在一个面向高频使用的相册产品里，将所有高风险行为拆成“预览影响、短暂缓冲、可撤回确认、最终提交”四段。用户删除、公开分享、移动到隐私空间或批量改标签时，系统先把受影响照片聚合成一张临时任务卡，展示影响数量、涉及人物、关联回忆和恢复路径；随后进入 8 秒缓冲状态，允许一键撤回或调整范围。这样既保留操作速度，也避免用户在误操作后承担不可逆后果。";
  design.text.sourceText = "Gmail Undo Send 在发送后保留短暂取消窗口，用户可撤回误发邮件，降低不可逆操作造成的心理压力。";
  design.text.advantageText = "这种方案的优势在于，把不可逆操作变成可反悔流程，用户会更敢整理照片，也更信任系统。";
  design.text.feedbackText = "这张卡有启发吗？";
  applyDesign();
});
document.getElementById("jsonBox").addEventListener("change", (event) => {
  try {
    design = mergeDesign(defaultDesign, JSON.parse(event.currentTarget.value));
    applyDesign();
    showToast("JSON 已导入");
  } catch {
    showToast("JSON 格式不对");
  }
});

bindControls();
bindDragging();
applyDesign();
window.addEventListener("resize", fitAllText);
