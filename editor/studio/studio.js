const $ = (id) => document.getElementById(id);
const maxTick = 1_000_000;
const maxImportBytes = 512 * 1024;
const svgNS = "http://www.w3.org/2000/svg";
const svgTags = new Set(["svg", "defs", "clipPath", "g", "ellipse", "rect", "path"]);
const svgAttrs = new Set([
  "width", "height", "viewBox", "data-svm-entity", "transform", "fill", "stroke",
  "stroke-width", "opacity", "d", "cx", "cy", "rx", "ry", "x", "y", "id", "clip-path", "fill-rule",
]);
const parameterNames = {
  x: "X", y: "Y", cx: "中心 X", cy: "中心 Y",
  rx: "半径 X", ry: "半径 Y", width: "宽度", height: "高度",
  "translate.x": "位移 X", "translate.y": "位移 Y", "position.x": "位置 X", "position.y": "位置 Y",
  rotation_degrees: "旋转角度", scale: "缩放", opacity: "不透明度", fill: "填色",
};
const shapeNames = { CreateRectangle: "矩形", CreateEllipse: "椭圆" };
const cameraSelection = "camera:presentation";
let state;
let selection;
let selectedTrack;
let savedRevision;
let requestedTick = 0;
let timelineStart = 0;
let timelineEnd = 96;
let comparing = false;
let selectedOnly = false;
let reading = false;
let editing = false;
let editSequence = 0;
let playing = false;
let drag;
let showPreviewBase = false;
let segmentPreview;
let segmentBusy = false;

function element(tag, label, className) {
  const node = document.createElement(tag);
  node.textContent = label;
  if (className) node.className = className;
  return node;
}

function button(label, title, className, run) {
  const node = element("button", label, className);
  node.type = "button";
  node.title = title;
  node.setAttribute("aria-label", title);
  node.addEventListener("click", run);
  return node;
}

function report(message, error = false) {
  $("status").textContent = message;
  $("status").dataset.error = String(error);
}

async function request(url, options) {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `请求失败 (${response.status})`);
  return result;
}

function cleanSvg(node) {
  if (node.namespaceURI !== svgNS || !svgTags.has(node.localName)) return null;
  const output = document.createElementNS(svgNS, node.localName);
  for (const { name, value } of node.attributes) {
    if (!svgAttrs.has(name)) continue;
    if (["fill", "stroke"].includes(name) && !/^#[0-9a-f]{3,8}$|^[a-z]+$/i.test(value)) continue;
    if (name === "clip-path" && !/^url\(#svm-clip-\d+\)$/.test(value)) continue;
    output.setAttribute(name, value);
  }
  for (const child of node.children) {
    const safeChild = cleanSvg(child);
    if (safeChild) output.append(safeChild);
  }
  return output;
}

function elements() {
  const doc = state.document;
  const ordered = [...doc.presentation.render_stack];
  const order = [...new Set([...ordered.reverse(), ...doc.entities.map((entry) => entry.id)])];
  const byId = new Map(doc.entities.map((entry) => [entry.id, entry]));
  return order.map((id) => byId.get(id)).filter(Boolean);
}

function operation(id) {
  const doc = state.document;
  const binding = doc.construction.output_bindings.find(
    (entry) => entry.entity === id && entry.property === "geometry",
  );
  return doc.construction.operations.find((op) => binding?.slot === `${op.id}.geometry`);
}

function tracks() {
  return state.document.animation?.content ?? [];
}

function groups() {
  return state.document.groups ?? [];
}

function displayName(id) {
  if (id === cameraSelection) return "相机";
  const group = groups().find((entry) => entry.id === id);
  if (group) return group.name || `对象组 ${groups().indexOf(group) + 1}`;
  const entity = state.document.entities.find((entry) => entry.id === id);
  return (entity?.name || id).replace(/^entity:/, "");
}

function trackOwner(track) {
  const { group, camera, entity, operation: op } = track.target;
  if (group) return group;
  if (camera) return cameraSelection;
  if (entity) return entity;
  return elements().find((layer) => operation(layer.id)?.id === op)?.id ?? op;
}

function trackLabel(track) {
  const property = track.target.parameter ?? track.target.property;
  return parameterNames[property] ?? property;
}

function selectedKeys() {
  const track = tracks().find((item) => item.id === selectedTrack);
  return track?.keyframes ?? [];
}

function nearbyKey(direction) {
  const keys = selectedKeys().filter((key) => key.tick >= timelineStart && key.tick <= timelineEnd);
  return direction < 0
    ? keys.findLast((key) => key.tick < state.tick)
    : keys.find((key) => key.tick > state.tick);
}

function timebase() {
  return state.document.animation?.timebase?.ticks_per_second ?? 24;
}

function fitArtboard() {
  if (!state) return;
  const [, , width, height] = state.viewBox;
  const stage = $("stage");
  const style = getComputedStyle(stage);
  const availableWidth = stage.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const availableHeight = stage.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
  const sourceVisible = comparing && state.source;
  const panelWidth = sourceVisible ? (availableWidth - parseFloat(style.columnGap)) / 2 : availableWidth;
  const panelHeight = availableHeight - (sourceVisible ? $("render-caption").offsetHeight + 7 : 0);
  const dimensions = (node, frameWidth, frameHeight) => {
    const scale = Math.min(panelWidth / frameWidth, panelHeight / frameHeight, 1040 / frameWidth);
    node.style.width = `${Math.max(1, frameWidth * scale)}px`;
    node.style.height = `${Math.max(1, frameHeight * scale)}px`;
  };
  dimensions($("artboard"), width, height);
  if (sourceVisible) dimensions($("reference-image"), state.source.width, state.source.height);
}

function highlight() {
  const group = groups().find((item) => item.id === selection);
  const selectedEntities = new Set(group?.members ?? [selection]);
  for (const item of $("artboard").querySelectorAll("[data-svm-entity]")) {
    item.classList.toggle("selected", selectedEntities.has(item.dataset.svmEntity));
  }
}

function renderReference() {
  const source = state.source;
  const enabled = Boolean(comparing && source);
  $("compare").hidden = !source;
  $("compare").setAttribute("aria-pressed", String(enabled));
  $("reference-view").hidden = !enabled;
  $("render-caption").hidden = !enabled;
  $("stage").classList.toggle("comparing", enabled);
  $("artboard").classList.toggle("reference-background", Boolean(source));
  $("fit").disabled = Boolean(source);
  $("fit").title = source ? "视频工程使用原片坐标范围" : "适合画布";
  if (!enabled) return;
  const image = $("reference-image");
  if (image.getAttribute("src") !== source.url) {
    image.classList.add("loading");
    image.setAttribute("src", source.url);
  }
  const frame = source.ticks.indexOf(source.tick) + 1;
  const frameLabel = frame ? `原片 · 第 ${frame} 帧` : "原片";
  $("reference-caption").textContent = source.tick === state.tick
    ? `${frameLabel}（Tick ${source.tick}）`
    : `${frameLabel}（保持 Tick ${source.tick}）`;
  const caption = state.preview ? (showPreviewBase ? "修改前" : "候选预览") : "SVM 渲染";
  $("render-caption").textContent = `${caption} · Tick ${state.tick}`;
}

function renderCanvas() {
  const rendered = showPreviewBase ? state.svg : state.preview?.svg ?? state.svg;
  const raw = new DOMParser().parseFromString(rendered, "image/svg+xml").documentElement;
  const svg = cleanSvg(raw);
  if (!svg) throw new Error("无法显示 SVG 画面");
  $("artboard").replaceChildren(svg);
  $("artboard").classList.toggle("preview-frame", Boolean(state.preview && !showPreviewBase));
  const [, , width, height] = state.viewBox;
  $("canvas-meta").textContent = `${Number(width.toFixed(2))} × ${Number(height.toFixed(2))}`;
  renderReference();
  fitArtboard();
  highlight();
}

function select(id, trackId) {
  const previous = selection;
  selection = id;
  const owned = tracks().filter((track) => trackOwner(track) === id);
  if (trackId) selectedTrack = trackId;
  else if (!owned.some((track) => track.id === selectedTrack)) selectedTrack = owned[0]?.id;
  for (const item of $("layer-list").querySelectorAll("button")) {
    item.setAttribute("aria-pressed", String(item.dataset.entity === id));
  }
  highlight();
  renderInspector();
  if (selectedOnly && id !== previous) renderTimeline();
  renderTrackSelection();
}

function renderLayers() {
  const layers = elements();
  const list = $("layer-list");
  const styles = new Map(state.document.presentation.styles.map((entry) => [entry.entity, entry]));
  $("layer-count").textContent = String(layers.length);
  list.replaceChildren();
  for (const id of [
    ...groups().map((group) => group.id),
    ...(state.document.presentation.camera ? [cameraSelection] : []),
  ]) {
    const row = button("", displayName(id), "layer motion-layer", () => select(id));
    row.dataset.entity = id;
    row.setAttribute("aria-pressed", String(selection === id));
    const group = groups().find((entry) => entry.id === id);
    if (group) row.title = `${displayName(id)} · ${group.members.map(displayName).join(" + ")}`;
    const glyph = element("span", id === cameraSelection ? "▣" : "▦", "layer-icon");
    glyph.setAttribute("aria-hidden", "true");
    row.append(glyph, element("span", displayName(id)));
    list.append(row);
  }
  for (const layer of layers) {
    const row = button("", layer.name || layer.id, "layer", () => select(layer.id));
    row.dataset.entity = layer.id;
    row.setAttribute("aria-pressed", String(selection === layer.id));
    const kind = operation(layer.id)?.type;
    const glyph = element("span", kind === "CreateEllipse" ? "◯" : kind === "CreateRectangle" ? "□" : "◇", "layer-icon");
    glyph.setAttribute("aria-hidden", "true");
    const swatch = element("span", "", "swatch");
    const paint = styles.get(layer.id);
    swatch.style.backgroundColor = paint?.fill === "none" ? paint.stroke : paint?.fill ?? "";
    row.append(glyph, element("span", layer.name || layer.id), swatch);
    list.append(row);
  }
  if (!layers.length) list.append(element("p", "添加图形或导入 SVG 开始编辑。", "empty"));
}

function renderMotionInspector(panel, owned) {
  const camera = selection === cameraSelection;
  const group = groups().find((entry) => entry.id === selection);
  const members = group?.members.map(displayName).join(" + ");
  panel.append(element("h3", displayName(selection)));
  panel.append(element("p", camera ? "相机运动" : members || "对象组运动", "op-type"));
  for (const track of owned) {
    const key = track.keyframes.find((item) => item.tick === state.tick);
    const label = trackLabel(track);
    const form = element("form", "", "field track-field");
    form.dataset.track = track.id;
    const input = document.createElement("input");
    input.type = track.value_type === "number" ? "number" : "text";
    input.step = "any";
    input.id = `track-value-${owned.indexOf(track)}`;
    const value = key?.value ?? state.motionValues?.[track.id];
    input.value = value ?? "";
    input.readOnly = !key || track.value_type !== "number";
    const caption = element("label", label);
    caption.htmlFor = input.id;
    const commit = () => {
      if (input.readOnly || !input.reportValidity() || !Number.isFinite(input.valueAsNumber)) return;
      const next = input.valueAsNumber;
      if (next === key.value) return;
      const preview = group && ["translate.x", "translate.y"].includes(track.target.property)
        && track.keyframes.length > 1;
      perform(preview ? "preview-keyframe" : "track-keyframe", { track: track.id, value: next },
        preview ? `正在预览 ${label}` : `已更新 ${label} 关键帧`);
    };
    form.addEventListener("focusin", () => {
      selectedTrack = track.id;
      renderTrackSelection();
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      commit();
    });
    const save = button(key ? "◆" : "◇", `应用 ${label} 关键帧值`, "outline keyed", commit);
    save.disabled = input.readOnly;
    form.append(caption, input, save);
    panel.append(form);
  }
  panel.append(element("p", owned.length
    ? "◆ 是已记录的关键帧，可直接更改。◇ 显示播放头处的采样值。"
    : "当前没有运动轨道。", "help"));
}

function renderInspector() {
  const panel = $("inspector");
  panel.replaceChildren();
  if (selection === cameraSelection || groups().some((group) => group.id === selection)) {
    renderMotionInspector(panel, tracks().filter((track) => trackOwner(track) === selection));
    return;
  }
  const layer = state.document.entities.find((entry) => entry.id === selection);
  const op = operation(selection);
  if (!layer) {
    panel.append(element("p", "选择图层查看属性。", "empty"));
    return;
  }
  panel.append(element("h3", layer.name || layer.id));
  if (op) panel.append(element("p", shapeNames[op.type] || op.type, "op-type"));
  const numeric = Object.entries(op?.parameters ?? {}).filter(([, value]) => typeof value === "number");
  if (!numeric.length) {
    panel.append(element("p", "此图层没有可编辑的数值参数。", "help"));
    return;
  }
  const group = [...$("artboard").querySelectorAll("[data-svm-entity]")]
    .find((item) => item.dataset.svmEntity === layer.id);
  for (const [name, value] of numeric) {
    const label = parameterNames[name] || name;
    const track = tracks().find((item) => item.target.operation === op.id && item.target.parameter === name);
    const key = track?.keyframes.find((item) => item.tick === state.tick);
    const field = element("form", "", "field");
    if (track) {
      field.dataset.track = track.id;
      field.addEventListener("focusin", () => {
        selectedTrack = track.id;
        renderTrackSelection();
      });
    }
    const input = document.createElement("input");
    const caption = element("label", label);
    input.type = "number";
    input.step = "any";
    input.id = `parameter-${name}`;
    const sampled = group?.firstElementChild?.getAttribute(name);
    input.value = key?.value ?? (track ? sampled : null) ?? value;
    caption.htmlFor = input.id;
    const apply = (action) => {
      if (!input.reportValidity() || input.value === "") return;
      perform(action, { operation: op.id, property: name, value: input.valueAsNumber },
        action === "keyframe" ? `已记录 ${label} 关键帧` : `已更新 ${label} 基础值`);
    };
    field.addEventListener("submit", (event) => {
      event.preventDefault();
      apply("parameter");
    });
    const base = button("✓", `应用 ${label} 基础值`, "outline", () => apply("parameter"));
    const diamond = button(key ? "◆" : "◇", `设置 ${label} 关键帧`, `outline ${key ? "keyed" : ""}`, () => apply("keyframe"));
    diamond.disabled = !(state.animatable[op.id] || []).includes(name);
    field.append(caption, input, base, diamond);
    panel.append(field);
  }
  panel.append(element("p", "✓ 提交基础值。◇ 在当前 Tick 记录关键帧。", "help"));
}

function renderTimeline() {
  const target = $("tracks");
  const all = tracks();
  const items = selectedOnly ? all.filter((track) => trackOwner(track) === selection) : all;
  const last = all.reduce((latest, item) => Math.max(latest, item.keyframes.at(-1)?.tick ?? 0), 0);
  timelineStart = state.source?.firstTick ?? 0;
  timelineEnd = state.source?.lastTick ?? state.authoredEndTick ?? Math.max(timebase() * 4, last, state.tick);
  const extent = Math.max(1, timelineEnd - timelineStart);
  $("timeline-range").min = timelineStart;
  $("timeline-range").max = timelineEnd;
  $("tick").min = timelineStart;
  $("tick").max = state.source?.lastTick ?? state.authoredEndTick ?? maxTick;
  $("selected-tracks").setAttribute("aria-pressed", String(selectedOnly));
  target.replaceChildren();
  for (const track of items) {
    const owner = trackOwner(track);
    const label = `${displayName(owner)} · ${trackLabel(track)}`;
    const row = element("div", "", "track");
    row.dataset.track = track.id;
    const caption = button(label, label, "track-caption", () => select(owner, track.id));
    const strip = document.createElement("div");
    for (const key of track.keyframes) {
      if (key.tick < timelineStart || key.tick > timelineEnd) continue;
      const marker = button("◆", `${label} / Tick ${key.tick}`, "keymark", () => {
        select(owner, track.id);
        seek(key.tick);
      });
      marker.style.left = `${100 * (key.tick - timelineStart) / extent}%`;
      marker.dataset.tick = key.tick;
      marker.setAttribute("aria-current", String(key.tick === state.tick));
      strip.append(marker);
    }
    row.append(caption, strip);
    target.append(row);
  }
  if (!items.length) {
    target.append(element("p", selectedOnly ? "所选图层没有轨道。" : "从属性面板添加关键帧。", "empty"));
  }
  renderTrackSelection();
}

function renderTrackSelection() {
  for (const row of $("tracks").querySelectorAll("[data-track]")) {
    row.dataset.selected = String(row.dataset.track === selectedTrack);
    row.querySelector(".track-caption").setAttribute("aria-pressed", row.dataset.selected);
  }
  for (const form of $("inspector").querySelectorAll("[data-track]")) {
    form.classList.toggle("active", form.dataset.track === selectedTrack);
  }
  $("previous-key").disabled = !nearbyKey(-1);
  $("next-key").disabled = !nearbyKey(1);
}

function renderClock() {
  if (state.tick > timelineEnd) renderTimeline();
  $("timeline-range").value = state.tick;
  $("time-label").textContent = `${(state.tick / timebase()).toFixed(2)} 秒`;
  $("timebase").textContent = `${timebase()} ticks/s`;
  $("tick").value = state.tick;
  const extent = Math.max(1, timelineEnd - timelineStart);
  $("tracks").style.setProperty("--playhead", `${100 * (state.tick - timelineStart) / extent}%`);
  for (const key of $("tracks").querySelectorAll(".keymark")) {
    key.setAttribute("aria-current", String(Number(key.dataset.tick) === state.tick));
  }
  renderTrackSelection();
}

function renderProject() {
  const layers = elements();
  if (selection !== cameraSelection
    && ![...layers, ...groups()].some((entry) => entry.id === selection)) {
    selection = state.source ? groups()[0]?.id ?? layers[0]?.id : layers[0]?.id;
  }
  const owned = tracks().filter((track) => trackOwner(track) === selection);
  if (!owned.some((track) => track.id === selectedTrack)) selectedTrack = owned[0]?.id;
  $("project-title").textContent = {
    "document:orbital-study": "轨道研究",
    "document:untitled": "未命名工程",
    "document:explicit-multi-object-raster-recovery": "受控视频恢复",
  }[state.document.document_id] ?? state.document.document_id;
  $("revision").textContent = state.revision.slice(0, 21);
  $("revision").title = state.revision;
  $("undo").disabled = !state.undo;
  $("redo").disabled = !state.redo;
  $("preview-controls").hidden = !state.preview;
  for (const id of ["import", "rect", "ellipse", "fill"]) {
    $(id).disabled = Boolean(state.source);
    $(id).title = state.source ? "视频示例支持运动关键帧编辑" : "";
  }
  $("recovery").disabled = !state.recoveryAvailable && !state.canPrepareRecovery;
  $("recovery").title = state.recoveryAvailable ? "打开受控视频恢复包"
    : state.canPrepareRecovery ? "从仓库原片生成受控视频示例" : "启动时配置已生成的 Phase 1 恢复包";
  renderLayers();
  renderCanvas();
  renderInspector();
  renderTimeline();
  renderClock();
}

function stop() {
  playing = false;
  $("play").textContent = "▶";
  $("play").setAttribute("aria-label", "播放");
}

async function drainFrames() {
  if (reading || editing || !state) return;
  reading = true;
  const sequence = editSequence;
  try {
    while (requestedTick !== state.tick && !editing && sequence === editSequence) {
      const next = await request(`/api/state?tick=${requestedTick}`);
      if (editing || sequence !== editSequence) break;
      const sameProject = state.revision === next.revision;
      state = next;
      if (!sameProject) {
        renderProject();
      } else {
        renderCanvas();
        renderClock();
        if (!playing) renderInspector();
      }
    }
  } catch (error) {
    if (sequence === editSequence) {
      stop();
      requestedTick = state.tick;
      report(error.message, true);
    }
  } finally {
    reading = false;
    if (sequence !== editSequence) void drainFrames();
  }
}

function seek(value, keepPlaying = false) {
  if (!state || editing || drag || !Number.isInteger(value) || value < 0 || value > maxTick) return;
  if ((state.source || state.authoredEndTick !== null && state.authoredEndTick !== undefined)
    && (value < timelineStart || value > timelineEnd)) {
    $("tick").value = state.tick;
    return;
  }
  if (!keepPlaying) stop();
  requestedTick = value;
  void drainFrames();
}

function togglePlay() {
  if (!state || editing || drag) return;
  if (playing) {
    stop();
    renderInspector();
    return;
  }
  playing = true;
  const start = performance.now();
  const offset = (state.tick >= timelineEnd ? timelineStart : state.tick) - timelineStart;
  $("play").textContent = "Ⅱ";
  $("play").setAttribute("aria-label", "暂停");
  function frame(now) {
    if (!playing) return;
    seek(timelineStart + (offset + Math.floor((now - start) * timebase() / 1000))
      % (timelineEnd - timelineStart + 1), true);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

async function perform(action, fields = {}, message = "已更新工程") {
  if (!state || editing) return;
  const replacement = ["new", "demo", "open", "recovery", "accept-segment"].includes(action);
  if (replacement && savedRevision !== state.revision && !confirm("当前工程有未保存的更改。继续打开其他工程？")) return;
  stop();
  requestedTick = state.tick;
  editing = true;
  editSequence += 1;
  if (action === "recovery" && !state.recoveryAvailable) report("正在生成受控视频示例…");
  try {
    state = await request("/api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-SVM-Editor-Request": "1" },
      body: JSON.stringify({ action, revision: state.revision, tick: state.tick, ...fields }),
    });
    if (["preview-keyframe", "clear-preview", "accept-preview"].includes(action) || !state.preview) {
      showPreviewBase = false;
      $("preview-base").setAttribute("aria-pressed", "false");
      $("preview-base").textContent = "查看修改前";
    }
    requestedTick = state.tick;
    if (replacement) {
      selection = undefined;
      selectedTrack = undefined;
      comparing = Boolean(state.source);
      selectedOnly = false;
      savedRevision = action === "accept-segment" ? undefined : state.revision;
    } else if (action === "shape") {
      selection = elements()[0]?.id;
    }
    renderProject();
    report(message);
    return true;
  } catch (error) {
    renderProject();
    report(error.message, true);
  } finally {
    editing = false;
  }
}

function fileBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("读取本机文件失败"));
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.readAsDataURL(file);
  });
}

function segmentStatus(message, error = false) {
  $("segment-status").textContent = message;
  $("segment-status").dataset.error = String(error);
}

function resetSegment() {
  segmentPreview = undefined;
  $("segment-preview").hidden = true;
}

function segmentRequest(action, fields) {
  return request("/api/action", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-SVM-Editor-Request": "1"},
    body: JSON.stringify({action, revision: state.revision, tick: state.tick, ...fields}),
  });
}

function presentSegment(result) {
  segmentPreview = result.segment;
  for (const [id, frame] of [["segment-first", segmentPreview.firstSvg], ["segment-last", segmentPreview.lastSvg]]) {
    const parsed = new DOMParser().parseFromString(frame, "image/svg+xml").documentElement;
    $(id).replaceChildren(cleanSvg(parsed));
  }
  $("segment-preview").hidden = false;
  const summary = segmentPreview.report;
  segmentStatus(`${segmentPreview.synthetic ? "合成示例 · " : ""}${summary.selection.subject} · 源 Tick ${summary.selection.start_tick}–${summary.selection.end_tick} · ${summary.rectangle_count} 个图元 · ${summary.track_count} 条轨道`);
}

async function guidedTask(message, handle) {
  if (segmentBusy || editing) return;
  resetSegment();
  segmentBusy = true;
  $("segment-close").disabled = true;
  $("guided-control").inert = true;
  $("segment-form").inert = true;
  segmentStatus(message);
  try {
    await handle();
  } catch (error) {
    segmentStatus(error.message, true);
  } finally {
    segmentBusy = false;
    $("segment-close").disabled = false;
    $("guided-control").inert = false;
    $("segment-form").inert = false;
  }
}

$("segment-open").onclick = () => {
  if (!state || editing) return;
  stop();
  resetSegment();
  $("guided-control").hidden = true;
  segmentStatus("选择与同一候选对应的三个文件。");
  $("segment-dialog").showModal();
};
$("segment-close").onclick = () => $("segment-dialog").close();
$("segment-dialog").addEventListener("close", () => {
  $("guided-image").removeAttribute("src");
  $("guided-file").value = "";
  resetSegment();
  void segmentRequest("discard-segment", {}).catch(() => {});
});
$("segment-dialog").addEventListener("cancel", (event) => {
  if (segmentBusy) event.preventDefault();
});
$("segment-form").addEventListener("change", resetSegment);
$("guided-open").onclick = () => $("guided-file").click();
$("guided-file").onchange = (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  $("guided-control").hidden = true;
  $("guided-range").hidden = true;
  void guidedTask("正在检查 AVI 并解码首帧…", async () => {
    if (!file.size || file.size > 8 * 1024 ** 2) throw new Error("AVI 文件超过 8 MiB 上限或内容为空");
    const info = await segmentRequest("inspect-guided-source", {source: await fileBase64(file)});
    $("guided-image").src = info.image;
    $("guided-x").max = info.width - 1;
    $("guided-y").max = info.height - 1;
    $("guided-x").value = "";
    $("guided-y").value = "";
    $("guided-control").hidden = false;
    segmentStatus(`${info.width} × ${info.height} · ${info.frameCount} 帧，等待首帧点选。`);
  });
};
function analyzeGuided() {
  if (!$("guided-point").reportValidity()) return;
  $("guided-range").hidden = true;
  void guidedTask("正在分析点选对象…", async () => {
    const info = await segmentRequest("analyze-guided-source", {
      x: $("guided-x").valueAsNumber, y: $("guided-y").valueAsNumber,
    });
    if (info.observedTicks.length < 2) {
      segmentStatus("连续观测不足两帧，请选择其他对象。", true);
      return;
    }
    for (const id of ["guided-start", "guided-end"]) {
      $(id).replaceChildren(...info.observedTicks.map((tick) => new Option(tick, tick)));
    }
    $("guided-end").value = info.observedTicks.at(-1);
    $("guided-range").hidden = false;
    const unknown = info.unknown.map(([start, end]) => `${start}–${end}`).join("、");
    const remainder = info.observedTicks.length < info.sampleCount ? " · 证据中断后的范围不可选" : "";
    segmentStatus(`从首帧连续观测 ${info.observedTicks.length}/${info.sampleCount} 帧${remainder}${unknown ? ` · 原始缺失 Tick ${unknown}` : ""}。`);
  });
}
$("guided-point").onsubmit = (event) => { event.preventDefault(); analyzeGuided(); };
$("guided-image").onclick = (event) => {
  const image = event.currentTarget;
  const rect = image.getBoundingClientRect();
  const width = rect.width - 2 * image.clientLeft;
  const height = rect.height - 2 * image.clientTop;
  $("guided-x").value = Math.floor((event.clientX - rect.left - image.clientLeft) * image.naturalWidth / width);
  $("guided-y").value = Math.floor((event.clientY - rect.top - image.clientTop) * image.naturalHeight / height);
  analyzeGuided();
};
$("guided-range").onsubmit = (event) => {
  event.preventDefault();
  void guidedTask("正在重放所选片段…", async () => {
    presentSegment(await segmentRequest("prepare-guided-segment", {
      start: Number($("guided-start").value), end: Number($("guided-end").value),
    }));
  });
};
async function prepareSegment(demo) {
  if (segmentBusy || editing) return;
  resetSegment();
  const input = $("segment-source").files[0];
  const candidate = $("segment-candidate").files[0];
  const selection = $("segment-selection").files[0];
  if (!demo && (!input || !candidate || !selection)) return;
  if (!demo && (input.size > 8 * 1024 ** 2 || candidate.size > 4 * 1024 ** 2 || selection.size > 4096)) {
    segmentStatus("文件超限。AVI 允许 8 MiB，候选 4 MiB，选择文件 4 KiB。", true);
    return;
  }
  segmentBusy = true;
  $("segment-prepare").disabled = true;
  $("segment-demo").disabled = true;
  $("segment-close").disabled = true;
  segmentStatus("正在本机重放原片和候选观测…");
  try {
    let fields = {action: "prepare-demo-segment"};
    if (!demo) {
      const [source, observations, selected] = await Promise.all([
        fileBase64(input), fileBase64(candidate), selection.text(),
      ]);
      fields = {action: "prepare-segment", source, candidate: observations, selection: JSON.parse(selected)};
    }
    const result = await request("/api/action", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-SVM-Editor-Request": "1"},
      body: JSON.stringify({revision: state.revision, tick: state.tick, ...fields}),
    });
    presentSegment(result);
  } catch (error) {
    segmentStatus(error.message, true);
  } finally {
    segmentBusy = false;
    $("segment-prepare").disabled = false;
    $("segment-demo").disabled = false;
    $("segment-close").disabled = false;
  }
}
$("segment-form").onsubmit = (event) => {
  event.preventDefault();
  void prepareSegment(false);
};
$("segment-demo").onclick = () => prepareSegment(true);
$("segment-accept").onclick = async () => {
  if (!segmentPreview || segmentBusy || editing) return;
  if (await perform("accept-segment", {preview: segmentPreview.id}, "已创建可编辑平移工程")) {
    $("segment-dialog").close();
    resetSegment();
  } else if ($("status").dataset.error === "true") {
    segmentStatus($("status").textContent, true);
  }
};

function download(content, mime, extension) {
  if (!state) return;
  const stem = state.document.document_id.replace(/^document:/, "").replace(/[^a-z0-9_-]/gi, "-");
  const source = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = document.createElement("a");
  link.href = source;
  link.download = `${stem || "project"}${extension}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(source), 1000);
}

function fileInput(input, handle) {
  $(input).addEventListener("change", async (event) => {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file) return;
    try {
      if (file.size > maxImportBytes) throw new Error("请选择不超过 512 KiB 的文件。");
      await handle(await file.text());
    } catch (error) {
      report(error.message, true);
    }
  });
}

$("new").onclick = () => perform("new", {}, "已创建工程");
$("demo").onclick = () => perform("demo", {}, "已打开轨道研究");
$("recovery").onclick = () => perform("recovery", {}, "已打开受控视频恢复示例");
$("open").onclick = () => $("project-file").click();
$("import").onclick = () => $("svg-file").click();
$("undo").onclick = () => perform("undo", {}, "已撤销");
$("redo").onclick = () => perform("redo", {}, "已重做");
$("clear-preview").onclick = () => perform("clear-preview", {}, "已取消预览");
$("preview-base").onclick = () => {
  if (!state.preview) return;
  showPreviewBase = !showPreviewBase;
  $("preview-base").setAttribute("aria-pressed", String(showPreviewBase));
  $("preview-base").textContent = showPreviewBase ? "查看候选" : "查看修改前";
  renderCanvas();
};
$("accept-preview").onclick = () => perform("accept-preview",
  { preview: state.preview?.id }, "已接受运动修改");
$("fit").onclick = () => perform("fit", {}, "已调整画布范围");
$("compare").onclick = () => {
  comparing = !comparing;
  renderReference();
  fitArtboard();
};
$("reference-image").addEventListener("load", (event) => event.currentTarget.classList.remove("loading"));
$("reference-image").addEventListener("error", () => report("无法加载原始视频帧", true));
$("selected-tracks").onclick = () => {
  selectedOnly = !selectedOnly;
  renderTimeline();
};
function jumpToKey(direction) {
  const key = nearbyKey(direction);
  if (key) seek(key.tick);
}
$("previous-key").onclick = () => jumpToKey(-1);
$("next-key").onclick = () => jumpToKey(1);
$("rect").onclick = () => perform("shape", { kind: "CreateRectangle", name: "矩形", fill: $("fill").value }, "已添加矩形");
$("ellipse").onclick = () => perform("shape", { kind: "CreateEllipse", name: "椭圆", fill: $("fill").value }, "已添加椭圆");
$("save").onclick = () => {
  if (!state) return;
  download(JSON.stringify(state.document, null, 2) + "\n", "application/json", ".svm.json");
  savedRevision = state.revision;
  report("已发起工程下载");
};
$("export").onclick = () => {
  if (!state) return;
  download(state.svg, "image/svg+xml", `-tick-${state.tick}.svg`);
  report(state.preview ? "已发起已接受画面的 SVG 下载" : `已发起 Tick ${state.tick} 的 SVG 下载`);
};
$("play").onclick = togglePlay;
$("tick").onchange = (event) => seek(event.target.valueAsNumber);
$("timeline-range").oninput = (event) => seek(event.target.valueAsNumber);
const artboard = $("artboard");
artboard.addEventListener("pointerdown", (event) => {
  if (!state || editing || reading || drag || event.button !== 0) return;
  const group = event.target.closest("[data-svm-entity]");
  if (!group) return;
  const id = group.dataset.svmEntity;
  const owner = groups().find((entry) => entry.members.includes(id)
    && tracks().some((track) => track.target.group === entry.id));
  if (owner) {
    select(owner.id);
    return;
  }
  select(id);
  if (state.source) return;
  const op = operation(id);
  const shape = event.target;
  const names = op?.type === "CreateEllipse" && shape.localName === "ellipse" ? ["cx", "cy"]
    : op?.type === "CreateRectangle" && shape.localName === "rect" ? ["x", "y"] : null;
  if (!names || shape.parentElement !== group) return;
  const matrix = group.getScreenCTM();
  if (!matrix) return;
  stop();
  const inverse = matrix.inverse();
  drag = {
    pointer: event.pointerId, group, operation: op.id, inverse,
    start: new DOMPoint(event.clientX, event.clientY).matrixTransform(inverse),
    x: Number(shape.getAttribute(names[0])), y: Number(shape.getAttribute(names[1])),
    screenX: event.clientX, screenY: event.clientY, dx: 0, dy: 0, moved: false,
  };
  artboard.setPointerCapture(event.pointerId);
});
artboard.addEventListener("pointermove", (event) => {
  if (!drag || drag.pointer !== event.pointerId) return;
  if (!drag.moved && Math.hypot(event.clientX - drag.screenX, event.clientY - drag.screenY) < 3) return;
  const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(drag.inverse);
  drag.dx = point.x - drag.start.x;
  drag.dy = point.y - drag.start.y;
  drag.moved = true;
  drag.group.setAttribute("transform", `translate(${drag.dx} ${drag.dy})`);
});
function finishDrag(event) {
  if (!drag || drag.pointer !== event.pointerId) return;
  const { group, operation, x, y, dx, dy, moved } = drag;
  drag = undefined;
  group.removeAttribute("transform");
  if (moved && event.type === "pointerup") {
    perform("move", { operation, x: x + dx, y: y + dy }, "已移动图形");
  }
}
for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) {
  artboard.addEventListener(event, finishDrag);
}
fileInput("project-file", (data) => perform("open", { document: JSON.parse(data) }, "已打开工程"));
fileInput("svg-file", (data) => perform("import", { svg: data }, "已导入 SVG，新增图层可撤销"));
new ResizeObserver(fitArtboard).observe($("stage"));
window.addEventListener("beforeunload", (event) => {
  if (state && savedRevision !== state.revision) event.preventDefault();
});
document.addEventListener("keydown", (event) => {
  if (event.target.closest("input, button") || event.repeat) return;
  if (event.code === "Space") {
    event.preventDefault();
    togglePlay();
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && state) {
    event.preventDefault();
    if (event.shiftKey && state.redo) perform("redo", {}, "已重做");
    else if (!event.shiftKey && state.undo) perform("undo", {}, "已撤销");
  }
});

try {
  state = await request("/api/state?tick=0");
  savedRevision = state.revision;
  renderProject();
  report("就绪");
} catch (error) {
  report(error.message, true);
}
