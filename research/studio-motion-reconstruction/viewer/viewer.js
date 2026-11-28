const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const data = JSON.parse($("data").textContent);
const { source, settings, frames, geometry } = data.candidate;
const sourcePngs = data.sourcePngBase64;
const reasons = {
  no_exact_shape: "找不到完整匹配，可能有遮挡或形变",
  ambiguous_shape: "有多个几何匹配",
  frame_edge: "对象触及画面边界",
  translation_budget: "位移超出匹配范围",
  needs_reanchor: "证据中断后需要用户重新锚定",
};
let index = 0;
let playback;
let exportUrl;
let anchorUrl;
let segmentUrl;
const pending = [];

function tag(name, value, className) {
  const element = document.createElement(name);
  if (className) element.className = className;
  element.textContent = value;
  return element;
}

function observedGeometry(record) {
  const groups = [];
  for (const item of geometry) {
    const observation = record.subjects[item.id];
    if (observation.status !== "OBSERVED") continue;
    const [dx, dy] = observation.translation_xy;
    const [anchorX, anchorY] = item.anchor_bounds_xywh;
    const fill = "#" + [...item.bgr24].reverse().map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const group = document.createElementNS(NS, "g");
    group.setAttribute("id", item.id);
    group.setAttribute("fill", fill);
    for (const [x, y, width, height] of item.geometry_rectangles_xywh) {
      const shape = document.createElementNS(NS, "rect");
      shape.setAttribute("x", anchorX + dx + x);
      shape.setAttribute("y", anchorY + dy + y);
      shape.setAttribute("width", width);
      shape.setAttribute("height", height);
      group.append(shape);
    }
    groups.push(group);
  }
  return groups;
}

function reviewWindow(subject) {
  if (data.candidate.identity_review || frames[index].subjects[subject]?.status !== "OBSERVED") return;
  const unknownBefore = frames.slice(0, index).findLastIndex((frame) => frame.subjects[subject].status === "UNKNOWN");
  if (unknownBefore < 0) return;
  const unknownAfter = frames.findIndex((frame, position) => position > index && frame.subjects[subject].status === "UNKNOWN");
  const start = frames[unknownBefore + 1].tick;
  const end = frames[unknownAfter < 0 ? frames.length - 1 : unknownAfter - 1].tick;
  return { start, end };
}

function refreshAnchor() {
  if (data.candidate.identity_review) return;
  const subject = $("anchor-subject").value;
  const candidateWindow = reviewWindow(subject);
  const chosen = candidateWindow && pending.find((entry) => entry.subject === subject
    && entry.tick >= candidateWindow.start && entry.tick <= candidateWindow.end);
  const active = Boolean(candidateWindow && !chosen);
  $("original").dataset.anchorable = String(active);
  $("anchor-add").disabled = !active;
  $("anchor-x").disabled = !active;
  $("anchor-y").disabled = !active;
  $("anchor-status").textContent = active
    ? "在原始帧中点击该对象，或输入该对象的像素坐标。"
    : chosen
      ? `这段观察已在 Tick ${chosen.tick} 记录待复核点。`
      : "请选择该对象在未知区间之后重新可见的帧。";
  const onFrame = chosen?.tick === frames[index].tick;
  $("anchor-marker").toggleAttribute("hidden", !onFrame);
  if (onFrame) {
    const circle = $("anchor-marker").firstElementChild;
    circle.setAttribute("cx", chosen.point_xy[0] + 0.5);
    circle.setAttribute("cy", chosen.point_xy[1] + 0.5);
  }
}

function refreshDecisions() {
  if (anchorUrl) {
    URL.revokeObjectURL(anchorUrl);
    anchorUrl = undefined;
    $("anchor-result").hidden = true;
  }
  $("anchor-decisions").replaceChildren();
  for (const entry of pending) {
    const text = `${entry.subject} · Tick ${entry.tick} · (${entry.point_xy.join(", ")})`;
    const item = tag("li", "");
    const jump = tag("button", text);
    jump.type = "button";
    jump.onclick = () => {
      $("anchor-subject").value = entry.subject;
      seek(frames.findIndex((frame) => frame.tick === entry.tick));
    };
    const remove = tag("button", "移除");
    remove.type = "button";
    remove.setAttribute("aria-label", `移除 ${text}`);
    remove.onclick = () => {
      pending.splice(pending.indexOf(entry), 1);
      refreshDecisions();
    };
    item.append(jump, remove);
    $("anchor-decisions").append(item);
  }
  $("export-anchors").disabled = pending.length === 0;
  refreshAnchor();
}

function recordAnchor(x, y) {
  if ($("anchor-add").disabled || !Number.isInteger(x) || !Number.isInteger(y)) return;
  stop();
  const frame = frames[index];
  const subject = $("anchor-subject").value;
  const item = geometry.find((entry) => entry.id === subject);
  const [left, top] = frame.subjects[subject].bounds_xywh;
  const inside = item.geometry_rectangles_xywh.some(([rx, ry, width, height]) =>
    left + rx <= x && x < left + rx + width && top + ry <= y && y < top + ry + height);
  if (!inside) {
    $("anchor-status").textContent = "这个像素不在所选对象的候选几何内。";
    return;
  }
  pending.push({ subject, tick: frame.tick, point_xy: [x, y] });
  pending.sort((a, b) => a.tick - b.tick || a.subject.localeCompare(b.subject));
  refreshDecisions();
}

function showFrame(next) {
  if (exportUrl) {
    URL.revokeObjectURL(exportUrl);
    exportUrl = undefined;
    $("svg-result").hidden = true;
  }
  index = Math.min(frames.length - 1, Math.max(next, 0));
  const record = frames[index];
  const [numerator, denominator] = record.time_seconds;
  $("original").src = "data:image/png;base64," + sourcePngs[index];
  $("position").value = index;
  $("time").textContent = `第 ${index + 1} / ${frames.length} 帧 · Tick ${record.tick} · ${(numerator / denominator).toFixed(2)} 秒`;
  $("back").disabled = index === 0;
  $("forward").disabled = index === frames.length - 1;
  const rendered = observedGeometry(record);
  $("vector").replaceChildren(...rendered);
  $("export").disabled = !rendered.length;
  $("export").title = rendered.length ? "下载当前帧的已观察几何" : "当前帧没有已观察几何";
  $("subjects").replaceChildren();
  for (const item of geometry) {
    const observation = record.subjects[item.id];
    const unknown = observation.status !== "OBSERVED";
    const block = tag("article", "", "subject");
    block.dataset.unknown = String(unknown);
    block.append(tag("p", item.id));
    if (unknown) {
      block.append(tag("p", `未知 · ${reasons[observation.reason] || observation.reason}`));
    } else {
      const [dx, dy] = observation.translation_xy;
      const status = {
        exact_shape_after_gap: "间隔后重新匹配",
        user_reanchor: "已由用户重新锚定",
      }[observation.association] ?? "已观察";
      block.append(tag("p", `${status} · ΔX ${dx} px · ΔY ${dy} px`));
    }
    $("subjects").append(block);
  }
  for (const mark of $("rows").querySelectorAll("button")) {
    mark.setAttribute("aria-current", String(Number(mark.dataset.frame) === index));
  }
  if (!data.candidate.identity_review) {
    $("anchor-x").value = "";
    $("anchor-y").value = "";
    refreshAnchor();
  }
}

function stop() {
  clearInterval(playback);
  playback = undefined;
  $("play").textContent = "播放";
}

function seek(next) {
  stop();
  showFrame(next);
}

for (const item of geometry) {
  const row = tag("div", "", "track");
  const name = tag("span", item.id, "track-name");
  name.title = item.id;
  row.append(name);
  for (const [frameIndex, record] of frames.entries()) {
    const status = record.subjects[item.id].status === "OBSERVED" ? "已观察" : "未知";
    const mark = tag("button", "", status === "未知" ? "mark unknown" : "mark");
    mark.type = "button";
    mark.dataset.frame = frameIndex;
    mark.title = `${item.id} · Tick ${record.tick} · ${status}`;
    mark.setAttribute("aria-label", mark.title);
    mark.addEventListener("click", () => seek(frameIndex));
    row.append(mark);
  }
  $("rows").append(row);
}

$("original").width = source.width;
$("original").height = source.height;
$("vector").setAttribute("width", source.width);
$("vector").setAttribute("height", source.height);
$("vector").setAttribute("viewBox", `0 0 ${source.width} ${source.height}`);
$("position").max = frames.length - 1;
$("summary").textContent = `${data.synthetic ? "合成样本 · " : ""}${source.width} × ${source.height} · ${frames.length} 帧 · ${settings.ticks_per_second} ticks/s`;
$("summary").title = `候选 SHA-256 · ${data.candidateSha256}`;
$("back").onclick = () => seek(index - 1);
$("forward").onclick = () => seek(index + 1);
$("position").oninput = () => seek($("position").valueAsNumber);
for (const item of geometry) $("segment-subject").append(tag("option", item.id));
$("segment-start").value = frames[0].tick;
$("segment-end").value = frames.at(-1).tick;
$("segment-use-start").onclick = () => { stop(); $("segment-start").value = frames[index].tick; };
$("segment-use-end").onclick = () => { stop(); $("segment-end").value = frames[index].tick; };
$("segment-form").onsubmit = (event) => {
  event.preventDefault();
  stop();
  $("segment-result").hidden = true;
  const subject = $("segment-subject").value;
  const start = $("segment-start").valueAsNumber;
  const end = $("segment-end").valueAsNumber;
  const first = frames.findIndex((frame) => frame.tick === start);
  const last = frames.findIndex((frame) => frame.tick === end);
  if (first < 0 || last < 0 || first >= last) {
    $("segment-status").textContent = "选择两个不同的已记录帧作为起止。";
    return;
  }
  let continuous = false;
  for (const [i, frame] of frames.slice(0, last + 1).entries()) {
    const obs = frame.subjects[subject];
    if (obs.status !== "OBSERVED" || obs.association === "exact_shape_after_gap") continuous = false;
    if (obs.association === "first_frame_click" || obs.association === "user_reanchor") continuous = true;
    if (i >= first && !continuous) {
      $("segment-status").textContent = `Tick ${frame.tick} 缺少连续证据。请改选片段或重新锚定并复核。`;
      return;
    }
  }
  const selection = {subject, start_tick: start, end_tick: end, candidate_sha256: data.candidateSha256};
  const json = JSON.stringify(selection, null, 2);
  if (segmentUrl) URL.revokeObjectURL(segmentUrl);
  segmentUrl = URL.createObjectURL(new Blob([json], {type: "application/json"}));
  const link = $("segment-download");
  link.href = segmentUrl;
  link.download = "segment-selection.json";
  $("segment-text").value = json;
  $("segment-result").hidden = false;
  $("segment-status").textContent = "可提交此片段供命令行重放和确认。";
};
if (!data.candidate.identity_review) {
  $("review").hidden = false;
  for (const item of geometry) {
    const option = tag("option", item.id);
    option.value = item.id;
    $("anchor-subject").append(option);
  }
  $("anchor-marker").setAttribute("viewBox", `0 0 ${source.width} ${source.height}`);
  $("anchor-x").max = source.width - 1;
  $("anchor-y").max = source.height - 1;
  $("anchor-subject").onchange = () => {
    $("anchor-x").value = "";
    $("anchor-y").value = "";
    refreshAnchor();
  };
  $("anchor-form").onsubmit = (event) => {
    event.preventDefault();
    recordAnchor($("anchor-x").valueAsNumber, $("anchor-y").valueAsNumber);
  };
  $("original").onclick = (event) => {
    const bounds = $("original").getBoundingClientRect();
    const x = Math.floor((event.clientX - bounds.left) * source.width / bounds.width);
    const y = Math.floor((event.clientY - bounds.top) * source.height / bounds.height);
    recordAnchor(x, y);
  };
  $("export-anchors").onclick = () => {
    const body = JSON.stringify({ candidate_sha256: data.candidateSha256, reanchors: pending }, null, 2) + "\n";
    if (anchorUrl) URL.revokeObjectURL(anchorUrl);
    anchorUrl = URL.createObjectURL(new Blob([body], { type: "application/json;charset=utf-8" }));
    $("anchor-download").href = anchorUrl;
    $("anchor-download").download = "reanchors.json";
    $("anchor-text").value = body;
    $("anchor-result").hidden = false;
    $("anchor-download").focus();
  };
}
$("export").onclick = () => {
  stop();
  const record = frames[index];
  const groups = observedGeometry(record);
  if (!groups.length) return;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", $("vector").getAttribute("viewBox"));
  svg.append(...groups);
  const body = new XMLSerializer().serializeToString(svg);
  if (exportUrl) URL.revokeObjectURL(exportUrl);
  exportUrl = URL.createObjectURL(new Blob([body], { type: "image/svg+xml" }));
  const download = $("svg-download");
  download.href = exportUrl;
  download.download = `research-observed-tick-${record.tick}.svg`;
  $("svg-text").value = body;
  $("svg-result").hidden = false;
  download.focus();
};
$("play").onclick = () => {
  if (playback) {
    stop();
    return;
  }
  if (index === frames.length - 1) showFrame(0);
  const [numerator, denominator] = source.source_fps;
  $("play").textContent = "暂停";
  playback = setInterval(() => {
    showFrame(index + 1);
    if (index === frames.length - 1) stop();
  }, 1000 * denominator / numerator);
};
showFrame(0);
