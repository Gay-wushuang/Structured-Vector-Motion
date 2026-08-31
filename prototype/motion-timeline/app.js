const frameTicks = [0, 250, 500, 750, 1000];
const state = {
  committedRevision: "R0",
  committedMiddleValue: 300,
  previewMiddleValue: null,
  currentTick: 500,
  cache: new Map(frameTicks.map((tick) => [tick, "clean"])),
  playing: false,
};

const elements = {
  block: document.querySelector("#moving-block"),
  revisionStatus: document.querySelector("#revision-status"),
  canvasBadge: document.querySelector("#canvas-badge"),
  tickReadout: document.querySelector("#tick-readout"),
  valueReadout: document.querySelector("#value-readout"),
  inputLabel: document.querySelector("#input-value-label"),
  valueInput: document.querySelector("#keyframe-value"),
  previewPanel: document.querySelector("#change-preview"),
  previewValue: document.querySelector("#preview-value"),
  commit: document.querySelector("#commit-button"),
  undo: document.querySelector("#undo-button"),
  reset: document.querySelector("#reset-button"),
  play: document.querySelector("#play-button"),
  stop: document.querySelector("#stop-button"),
  timecode: document.querySelector("#timecode"),
  playhead: document.querySelector("#playhead"),
  middleKeyframe: document.querySelector("#middle-keyframe"),
  curvePath: document.querySelector("#curve-path"),
  timeline: document.querySelector("#timeline"),
  cacheCells: document.querySelector("#cache-cells"),
  cacheSummary: document.querySelector("#cache-summary"),
  toast: document.querySelector("#toast"),
};

function activeMiddleValue() {
  return state.previewMiddleValue ?? state.committedMiddleValue;
}

function sampleAt(tick, middleValue = activeMiddleValue()) {
  if (tick <= 500) return 100 + ((middleValue - 100) * tick) / 500;
  return middleValue + ((500 - middleValue) * (tick - 500)) / 500;
}

function formatNumber(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function formatTime(tick) {
  return `00:00.${String(tick).padStart(3, "0")}`;
}

function valueToCurveY(value) {
  return 166 - ((value - 100) / 400) * 130;
}

function renderCurve() {
  const middleValue = activeMiddleValue();
  const middleY = valueToCurveY(middleValue);
  elements.curvePath.setAttribute("d", `M0 154 L500 ${middleY} L1000 24`);
  const points = [
    [document.querySelector('.keyframe[data-tick="0"]'), "15px", 171],
    [elements.middleKeyframe, "50%", 36 + (middleY / 190) * 166],
    [document.querySelector('.keyframe[data-tick="1000"]'), "calc(100% - 15px)", 57],
  ];
  points.forEach(([element, x, y]) => {
    element.style.setProperty("--kf-x", x);
    element.style.setProperty("--kf-y", `${y}px`);
  });
  elements.middleKeyframe.querySelector("span").textContent = formatNumber(middleValue);
  elements.middleKeyframe.setAttribute("aria-label", `Keyframe at tick 500, value ${formatNumber(middleValue)}`);
}

function renderCanvas() {
  const sampled = sampleAt(state.currentTick);
  elements.block.setAttribute("transform", `translate(${sampled} 0)`);
  elements.tickReadout.textContent = String(state.currentTick);
  elements.valueReadout.textContent = formatNumber(sampled);
  elements.timecode.textContent = formatTime(state.currentTick);
  elements.playhead.value = String(state.currentTick);
  if (state.previewMiddleValue !== null) {
    elements.canvasBadge.className = "canvas-badge preview";
    elements.canvasBadge.textContent = `Preview · R${state.committedRevision.slice(1)} unchanged`;
  } else {
    elements.canvasBadge.className = "canvas-badge committed";
    elements.canvasBadge.textContent = `Committed · ${state.committedRevision}`;
  }
  if (state.cache.has(state.currentTick) && state.cache.get(state.currentTick) === "invalid") {
    state.cache.set(state.currentTick, "evaluated");
  }
}

function renderInspector() {
  const value = activeMiddleValue();
  elements.valueInput.value = String(value);
  elements.inputLabel.textContent = formatNumber(value);
  elements.previewValue.textContent = formatNumber(value);
  elements.previewPanel.classList.toggle("hidden", state.previewMiddleValue === null);
  elements.commit.disabled = state.previewMiddleValue === null;
  elements.undo.disabled = state.committedRevision === "R0";
  elements.revisionStatus.textContent = `Committed ${state.committedRevision} · middle value ${formatNumber(state.committedMiddleValue)}`;
}

function renderCache() {
  elements.cacheCells.innerHTML = frameTicks.map((tick) => `<span class="cache-cell ${state.cache.get(tick)}">${tick} · ${state.cache.get(tick)}</span>`).join("");
  const invalid = [...state.cache.values()].filter((value) => value === "invalid").length;
  const evaluated = [...state.cache.values()].filter((value) => value === "evaluated").length;
  elements.cacheSummary.textContent = invalid ? `${invalid} invalid · endpoints reused` : evaluated ? `${evaluated} reevaluated · static subtree reused` : "5 clean · static subtree reused";
}

function render() {
  renderCurve();
  renderCanvas();
  renderInspector();
  renderCache();
}

function previewValue(value) {
  const numericValue = Math.round(Number(value));
  state.previewMiddleValue = numericValue === state.committedMiddleValue ? null : numericValue;
  render();
}

function commitPreview() {
  if (state.previewMiddleValue === null) return;
  state.committedMiddleValue = state.previewMiddleValue;
  state.previewMiddleValue = null;
  state.committedRevision = state.committedRevision === "R0" ? "R1" : `R${Number(state.committedRevision.slice(1)) + 1}`;
  state.cache = new Map([[0, "clean"], [250, "invalid"], [500, "invalid"], [750, "invalid"], [1000, "clean"]]);
  showToast(`SetKeyframeValueChange committed as ${state.committedRevision}. Ticks 250–750 invalidated.`);
  render();
}

function undo() {
  state.committedRevision = "R0";
  state.committedMiddleValue = 300;
  state.previewMiddleValue = null;
  state.cache = new Map(frameTicks.map((tick) => [tick, "clean"]));
  showToast("Undo restored R0 and the original sampled motion.");
  render();
}

function reset() {
  stopPlayback();
  state.currentTick = 500;
  undo();
}

let animationFrame = null;
let playbackStart = null;
function play() {
  if (state.playing) return;
  state.playing = true;
  playbackStart = performance.now() - state.currentTick;
  const step = (now) => {
    if (!state.playing) return;
    state.currentTick = Math.min(1000, Math.round(now - playbackStart));
    renderCanvas();
    renderCache();
    if (state.currentTick >= 1000) {
      state.playing = false;
      return;
    }
    animationFrame = requestAnimationFrame(step);
  };
  animationFrame = requestAnimationFrame(step);
}

function stopPlayback() {
  state.playing = false;
  if (animationFrame) cancelAnimationFrame(animationFrame);
  state.currentTick = 0;
  renderCanvas();
  renderCache();
}

let dragStart = null;
elements.middleKeyframe.addEventListener("pointerdown", (event) => {
  dragStart = { y: event.clientY, value: activeMiddleValue() };
  elements.middleKeyframe.setPointerCapture(event.pointerId);
});
elements.middleKeyframe.addEventListener("pointermove", (event) => {
  if (!dragStart) return;
  previewValue(Math.max(180, Math.min(420, dragStart.value + (dragStart.y - event.clientY) * 2)));
});
elements.middleKeyframe.addEventListener("pointerup", () => { dragStart = null; });
elements.middleKeyframe.addEventListener("pointercancel", () => { dragStart = null; });
elements.valueInput.addEventListener("input", (event) => previewValue(event.target.value));
elements.playhead.addEventListener("input", (event) => { state.currentTick = Number(event.target.value); renderCanvas(); renderCache(); });
elements.commit.addEventListener("click", commitPreview);
elements.undo.addEventListener("click", undo);
elements.reset.addEventListener("click", reset);
elements.play.addEventListener("click", play);
elements.stop.addEventListener("click", stopPlayback);

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  toastTimer = setTimeout(() => elements.toast.classList.remove("show"), 2600);
}

render();
