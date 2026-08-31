const state = {
  data: null,
  tick: 0,
  previewValue: null,
  selectedEntityId: null,
  selectedTrackId: null,
  selectedKeyframeId: null,
  playing: false,
  request: 0,
};

const elements = Object.fromEntries([
  "revision-id","revision-label","document-id","canvas-badge","svg-host","tick-readout","value-label","value-readout",
  "entity-count","structure-document-id","entity-list","inspector-title","entity-id","binding-slot","parameter-list","motion-editor",
  "track-id","keyframe-id","operation-id","keyframe-value","edit-value","preview-copy","change-record",
  "commit-button","checkout-button","play-button","stop-button","timecode","timebase","track-title",
  "track-semantics","track-meta-name","track-meta-target","curve-path","keyframes","playhead","ruler","timeline-empty","cache-cells","delta-copy","toast",
  "project-name","project-path","canvas-title","track-list",
  "authoring-editor","author-parameter","author-timebase","add-track-button",
  "new-keyframe-tick","new-keyframe-value","add-keyframe-button",
  "anchored-editor","scope-cx","scope-cy","generate-candidates-button","candidate-list",
  "accept-candidate-button","revision-graph",
].map((id) => [id.replaceAll("-", "_"), document.querySelector(`#${id}`)]));

function textElement(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function renderCoreSvg(svgText) {
  const parsed = new DOMParser().parseFromString(svgText, "image/svg+xml");
  const root = parsed.documentElement;
  if (root.localName !== "svg" || parsed.querySelector("parsererror, script, foreignObject")) {
    throw new Error("Core Renderer returned an unsafe or invalid SVG Frame.");
  }
  for (const element of [root, ...root.querySelectorAll("*")]) {
    for (const attribute of element.attributes) {
      if (attribute.name.toLowerCase().startsWith("on")) {
        throw new Error("Core Renderer returned an unsafe SVG event attribute.");
      }
    }
  }
  elements.svg_host.replaceChildren(document.importNode(root, true));
}

function formatTime(tick, ticksPerSecond) {
  const totalMilliseconds = Math.round((tick * 1000) / ticksPerSecond);
  const wholeSeconds = Math.floor(totalMilliseconds / 1000);
  const minutes = Math.floor(wholeSeconds / 60);
  const seconds = wholeSeconds % 60;
  const milliseconds = totalMilliseconds % 1000;
  return `${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}.${String(milliseconds).padStart(3,"0")}`;
}

async function api(path, payload = null) {
  const options = payload ? { method:"POST", headers:{"Content-Type":"application/json","X-SVM-Editor-Request":"1"}, body:JSON.stringify(payload) } : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

function activeTrack() {
  return state.data?.tracks.find((track) => track.id === state.selectedTrackId) ?? null;
}

function selectedKeyframe() {
  return activeTrack()?.keyframes.find((keyframe) => keyframe.id === state.selectedKeyframeId) ?? null;
}

function durationTick() {
  return Math.max(0, ...state.data.tracks.flatMap((track) => track.keyframes.map((keyframe) => keyframe.tick)));
}

function previewMatches(track, keyframe) {
  return Boolean(
    state.data.preview.active
    && state.data.preview.target?.track_id === track?.id
    && state.data.preview.target?.keyframe_id === keyframe?.id
  );
}

async function selectTrack(trackId) {
  if (state.data.preview.active && state.data.preview.target?.track_id !== trackId) {
    state.data = await api("/api/clear-preview", {tick:state.tick});
  }
  state.selectedTrackId = trackId;
  state.selectedKeyframeId = null;
  state.previewValue = null;
  ensureSelections();
  render();
}

function ensureSelections() {
  if (!state.data.structure.some((entity) => entity.id === state.selectedEntityId)) {
    state.selectedEntityId = state.data.structure[0]?.id ?? null;
  }
  if (!state.data.tracks.some((track) => track.id === state.selectedTrackId)) {
    const selectedEntity = state.data.structure.find((entity) => entity.id === state.selectedEntityId);
    state.selectedTrackId = selectedEntity?.track_ids[0] ?? state.data.tracks[0]?.id ?? null;
  }
  const track = activeTrack();
  if (!track?.keyframes.some((keyframe) => keyframe.id === state.selectedKeyframeId)) {
    state.selectedKeyframeId = track?.keyframes[Math.floor(track.keyframes.length / 2)]?.id ?? null;
  }
}

async function loadTick(tick) {
  const request = ++state.request;
  const data = await api(`/api/state?tick=${tick}`);
  if (request !== state.request) return;
  state.tick = data.frame.tick;
  state.data = data;
  state.previewValue = data.preview.active ? data.preview.value : null;
  render();
}

async function preview(value) {
  const track = activeTrack();
  const keyframe = selectedKeyframe();
  if (!track || !keyframe) return;
  const request = ++state.request;
  const data = await api("/api/preview", {
    track_id:track.id,
    keyframe_id:keyframe.id,
    value:Number(value),
    tick:state.tick,
  });
  if (request !== state.request) return;
  state.data = data;
  state.previewValue = data.preview.active ? Number(value) : null;
  render();
}

function render() {
  ensureSelections();
  const data = state.data;
  elements.revision_id.textContent = data.revision.id;
  elements.revision_label.textContent = data.revision.label;
  elements.document_id.textContent = data.document_id;
  elements.project_name.textContent = data.document_id;
  elements.project_path.textContent = `${data.structure.length} Entities · ${data.tracks.length} Motion Tracks`;
  elements.canvas_title.textContent = data.tracks.length ? "Animated SVM Document" : "Static SVM Document";
  elements.structure_document_id.textContent = data.document_id;
  elements.canvas_badge.className = `state-badge ${data.preview.active ? "preview" : "committed"}`;
  elements.canvas_badge.textContent = data.preview.active
    ? `${data.preview.kind === "anchored" ? `Proposal ${data.preview.candidate_id}` : "Preview"} · ${data.revision.label} unchanged`
    : `Committed · ${data.revision.label}`;
  renderCoreSvg(data.frame.svg);
  elements.tick_readout.textContent = data.frame.tick;
  elements.checkout_button.disabled = !data.revision.can_checkout_parent;
  renderStructure();
  renderInspector();
  renderTimeline();
  renderAnchoredRegeneration();
  highlightSelectedEntity();
}

function renderAnchoredRegeneration() {
  const anchored = state.data.anchored_regeneration;
  elements.anchored_editor.classList.toggle("hidden", !anchored.available);
  if (!anchored.available) return;
  if (anchored.scope.length) {
    elements.scope_cx.checked = anchored.scope.includes("cx");
    elements.scope_cy.checked = anchored.scope.includes("cy");
  }
  elements.candidate_list.replaceChildren(...anchored.candidates.map((candidate) => {
    const button = document.createElement("button");
    const selected = candidate.id === anchored.selected_candidate_id;
    button.className = `candidate-card${selected ? " selected" : ""}${candidate.accepted_revision_id ? " accepted" : ""}`;
    button.disabled = Boolean(candidate.accepted_revision_id);
    const impact = candidate.impacts.map((item) => `${item.parameter}=${item.value}`).join(" · ");
    button.append(
      textElement("strong", `Candidate ${candidate.id}`),
      textElement("code", impact),
      textElement("small", candidate.accepted_revision_id ? "ACCEPTED" : "PREVIEW")
    );
    button.addEventListener("click", async () => {
      try {
        state.data = await api("/api/anchored/preview", {candidate_id:candidate.id,tick:0});
        state.tick = 0;
        render();
      } catch(error) { showError(error); }
    });
    return button;
  }));
  elements.accept_candidate_button.disabled = !anchored.selected_candidate_id;
  elements.revision_graph.replaceChildren(...state.data.revision_graph.map((revision) => {
    const row = document.createElement("div");
    const isBase = revision.id === anchored.base_revision_id;
    row.className = `revision-node${revision.current ? " current" : ""}${isBase ? " anchor-base" : ""}`;
    const parent = revision.parent_ids.length
      ? state.data.revision_graph.find((item) => item.id === revision.parent_ids[0])?.label ?? "parent"
      : "root";
    row.append(
      textElement("span", revision.label),
      textElement("small", isBase ? "ANCHOR BASE" : `from ${parent}`),
      textElement("em", revision.candidate_id ? `Candidate ${revision.candidate_id}` : revision.current ? "CURRENT" : "")
    );
    return row;
  }));
}

function renderStructure() {
  elements.entity_count.textContent = String(state.data.structure.length);
  const renderOrder = (entity) => entity.render_index === null ? Number.POSITIVE_INFINITY : entity.render_index;
  const rows = [...state.data.structure].sort((a,b) => renderOrder(a)-renderOrder(b)).map((entity) => {
    const button = document.createElement("button");
    button.className = `entity-row${entity.id===state.selectedEntityId?" selected":""}`;
    button.dataset.entity = entity.id;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(entity.id===state.selectedEntityId));
    const copy = document.createElement("span");
    copy.className = "entity-copy";
    copy.append(textElement("strong", entity.name), textElement("code", entity.id));
    button.append(textElement("span", "□", "entity-icon"), copy);
    if (entity.track_ids.length) button.append(textElement("span", "TRACK", "entity-track"));
    button.addEventListener("click", async () => {
      try {
        state.selectedEntityId = entity.id;
        if (entity.track_ids.length) {
          await selectTrack(entity.track_ids[0]);
          return;
        }
        if (state.data.preview.active) {
          state.data = await api("/api/clear-preview", {tick:state.tick});
          state.previewValue = null;
        }
        state.selectedTrackId = null;
        state.selectedKeyframeId = null;
        render();
      } catch(error) {
        showError(error);
      }
    });
    return button;
  });
  elements.entity_list.replaceChildren(...rows);
}

function renderInspector() {
  const entity = state.data.structure.find((item) => item.id===state.selectedEntityId);
  if (!entity) {
    elements.inspector_title.textContent = "No selection";
    elements.entity_id.textContent = "—";
    elements.operation_id.textContent = "—";
    elements.binding_slot.textContent = "—";
    elements.parameter_list.replaceChildren();
    elements.motion_editor.classList.add("hidden");
    elements.authoring_editor.classList.add("hidden");
    return;
  }
  const operation = entity.operation;
  const track = activeTrack();
  const animatedParameter = entity.track_ids.includes(track?.id) ? track.target.parameter : null;
  elements.inspector_title.textContent = entity.name;
  elements.entity_id.textContent = entity.id;
  elements.operation_id.textContent = operation?.id || "—";
  elements.binding_slot.textContent = entity.binding?.slot || "—";
  const parameters = Object.entries(operation?.parameters || {}).map(([name,value]) => {
    const row = document.createElement("div");
    row.className = `parameter${name===animatedParameter?" animated":""}`;
    row.append(textElement("span", `${name}${name===animatedParameter?" · track":""}`), textElement("strong", value));
    return row;
  });
  elements.parameter_list.replaceChildren(...parameters);
  renderAuthoringControls(operation);
  const isMotionTarget = Boolean(animatedParameter && selectedKeyframe());
  elements.motion_editor.classList.toggle("hidden",!isMotionTarget);
  if (!isMotionTarget) return;
  const keyframe = selectedKeyframe();
  const values = track.keyframes.map((item) => Number(item.value));
  const span = Math.max(Math.max(...values)-Math.min(...values),1);
  elements.track_id.textContent = track.id;
  elements.keyframe_id.textContent = keyframe.id;
  elements.keyframe_value.min = String(Math.floor(Math.min(...values)-span/2));
  elements.keyframe_value.max = String(Math.ceil(Math.max(...values)+span/2));
  elements.keyframe_value.disabled = false;
  const matchesPreview = previewMatches(track, keyframe);
  const editorValue = matchesPreview ? state.data.preview.value : keyframe.value;
  elements.keyframe_value.value = String(editorValue);
  elements.edit_value.textContent = String(editorValue);
  elements.preview_copy.textContent = matchesPreview ? `Preview only. ${state.data.revision.label} remains committed in the real RevisionStore.` : "Move the selected Keyframe to create an isolated Core preview.";
  elements.change_record.classList.toggle("hidden", !matchesPreview);
  elements.commit_button.disabled = !matchesPreview;
  const lastTick = Math.max(...track.keyframes.map((item) => item.tick));
  const suggestedTick = lastTick + state.data.timebase.ticks_per_second;
  if (track.keyframes.some((item) => item.tick === Number(elements.new_keyframe_tick.value))) {
    elements.new_keyframe_tick.value = String(suggestedTick);
  }
  elements.new_keyframe_value.value = String(keyframe.value);
}

function renderAuthoringControls(operation) {
  const tracked = new Set(
    state.data.tracks
      .filter((track) => track.target.operation === operation?.id)
      .map((track) => track.target.parameter)
  );
  const declared = new Set(
    state.data.structure.find((entity) => entity.id === state.selectedEntityId)?.animatable_parameters || []
  );
  const available = Object.entries(operation?.parameters || {})
    .filter(([name]) => declared.has(name) && !tracked.has(name));
  elements.authoring_editor.classList.toggle("hidden", available.length === 0);
  const existingTimebase = state.data.timebase?.ticks_per_second;
  elements.author_timebase.value = String(existingTimebase ?? 24);
  elements.author_timebase.disabled = existingTimebase !== undefined;
  elements.author_parameter.replaceChildren(...available.map(([name]) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    return option;
  }));
  elements.add_track_button.disabled = available.length === 0;
}

function renderTimeline() {
  const track = activeTrack();
  const hasMotion = Boolean(track && state.data.timebase);
  elements.timeline_empty.classList.toggle("hidden", hasMotion);
  elements.play_button.disabled = !hasMotion;
  elements.stop_button.disabled = !hasMotion;
  elements.playhead.disabled = !hasMotion;
  if (!hasMotion) {
    elements.track_title.textContent = "No Motion";
    elements.track_meta_name.textContent = "Static Document";
    elements.track_meta_target.textContent = "No animation.content";
    elements.track_list.replaceChildren();
    elements.track_semantics.textContent = "static Document";
    elements.timebase.textContent = "No timebase";
    elements.timecode.textContent = "—";
    elements.value_label.textContent = "frame";
    elements.value_readout.textContent = "static";
    elements.curve_path.setAttribute("d", "");
    elements.keyframes.replaceChildren();
    elements.ruler.replaceChildren();
    elements.cache_cells.replaceChildren();
    elements.delta_copy.textContent = "Evaluated once through the static Core Evaluator";
    return;
  }
  const ticksPerSecond = state.data.timebase.ticks_per_second;
  const duration = durationTick();
  elements.track_title.textContent = `${track.target.operation} · ${track.target.parameter}`;
  elements.track_meta_name.textContent = track.id;
  elements.track_meta_target.textContent = `${track.target.operation}.${track.target.parameter}`;
  elements.track_semantics.textContent = `${track.interpolation} · ${track.value_type}`;
  elements.timebase.textContent = `${ticksPerSecond} ticks/s`;
  elements.timecode.textContent = formatTime(state.data.frame.tick,ticksPerSecond);
  elements.playhead.max = String(duration);
  elements.playhead.value = String(state.data.frame.tick);
  elements.value_label.textContent = `${track.target.parameter} @ tick`;
  elements.value_readout.textContent = state.data.frame.effective_parameters[track.target.operation][track.target.parameter];
  const rulerTicks = [0,.25,.5,.75,1].map((ratio) => Math.round(duration*ratio));
  elements.ruler.replaceChildren(...rulerTicks.map((tick) => textElement("span", `${(tick/ticksPerSecond).toFixed(2)}s`)));
  elements.cache_cells.replaceChildren(...state.data.cache.map((cell) => textElement("span", `${cell.tick} · ${cell.status}`, `cache-cell ${cell.status}`)));
  elements.delta_copy.textContent = state.data.temporal_deltas.length ? state.data.temporal_deltas.map((delta) => `${delta.start_tick}…${delta.end_tick} invalidated by ${delta.keyframe_id}`).join(" · ") : "Motion cache primed from Document Keyframes and interval midpoints";
  elements.track_list.replaceChildren(...state.data.tracks.map((item) => {
    const button = document.createElement("button");
    button.className = `track-row${item.id === track.id ? " selected" : ""}`;
    button.append(textElement("strong", item.target.parameter), textElement("code", item.id));
    button.addEventListener("click", () => selectTrack(item.id).catch(showError));
    return button;
  }));
  renderCurve(track,duration);
}

function renderCurve(track,duration) {
  const safeDuration = Math.max(duration, 1);
  const values = track.keyframes.map((keyframe) => previewMatches(track, keyframe) ? state.data.preview.value : keyframe.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = Math.max(maximum-minimum,1);
  const curveY = (value) => 166-((value-minimum)/span)*130;
  const cssY = (value) => 36+(curveY(value)/190)*166;
  const points = track.keyframes.map((keyframe,index) => `${index?"L":"M"}${(keyframe.tick/safeDuration)*1000} ${curveY(values[index])}`);
  elements.curve_path.setAttribute("d",points.join(" "));
  elements.keyframes.replaceChildren();
  track.keyframes.forEach((keyframe,index) => {
    const value = values[index];
    const button = document.createElement("button");
    button.className = `keyframe ${keyframe.id===state.selectedKeyframeId?"selected":"fixed"}`;
    button.dataset.keyframe = keyframe.id;
    button.style.left = `${(keyframe.tick/safeDuration)*100}%`;
    button.style.top = `${cssY(value)}px`;
    button.setAttribute("aria-label",`${keyframe.id}, tick ${keyframe.tick}, value ${value}`);
    button.append(document.createElement("i"),textElement("span",value));
    button.addEventListener("click",async()=>{
      try {
        if(state.data.preview.active && !previewMatches(track,keyframe)) {
          state.data=await api("/api/clear-preview",{tick:state.tick});
        }
        state.selectedKeyframeId=keyframe.id;
        state.previewValue=null;
        render();
      } catch(error) {
        showError(error);
      }
    });
    elements.keyframes.append(button);
  });
  const selected = [...elements.keyframes.querySelectorAll(".keyframe")].find((item)=>item.dataset.keyframe===state.selectedKeyframeId);
  if (!selected) return;
  let drag=null;
  selected.addEventListener("pointerdown",(event)=>{drag={y:event.clientY,value:Number(elements.keyframe_value.value)};selected.setPointerCapture(event.pointerId);});
  selected.addEventListener("pointermove",(event)=>{if(!drag)return;const delta=(drag.y-event.clientY)*(span/100);elements.keyframe_value.value=String(Math.round(drag.value+delta));schedulePreview(elements.keyframe_value.value);});
  selected.addEventListener("pointerup",()=>{drag=null;});
  selected.addEventListener("pointercancel",()=>{drag=null;});
}

function highlightSelectedEntity() {
  elements.svg_host.querySelectorAll("[data-svm-entity]").forEach((group) => group.classList.toggle("editor-selected",group.getAttribute("data-svm-entity")===state.selectedEntityId));
}

let previewTimer;
function schedulePreview(value) {
  clearTimeout(previewTimer);
  elements.edit_value.textContent=value;
  previewTimer=setTimeout(()=>preview(value).catch(showError),70);
}

elements.keyframe_value.addEventListener("input",(event)=>schedulePreview(event.target.value));
elements.playhead.addEventListener("input",(event)=>loadTick(Number(event.target.value)).catch(showError));
elements.commit_button.addEventListener("click",async()=>{
  const track=activeTrack();const keyframe=selectedKeyframe();if(!track||!keyframe)return;
  try{state.data=await api("/api/commit",{track_id:track.id,keyframe_id:keyframe.id,value:Number(elements.keyframe_value.value),tick:state.tick});state.previewValue=null;render();showToast(`Committed ${state.data.revision.label} through ProposalAcceptor.`);}catch(error){showError(error);}
});
elements.checkout_button.addEventListener("click",async()=>{try{state.data=await api("/api/checkout-parent",{tick:state.tick});state.previewValue=null;render();showToast(`Checked out parent ${state.data.revision.label}.`);}catch(error){showError(error);}});
elements.add_track_button.addEventListener("click",async()=>{
  const entity=state.data.structure.find((item)=>item.id===state.selectedEntityId);
  if(!entity?.operation)return;
  try {
    state.data=await api("/api/create-track",{
      operation_id:entity.operation.id,
      parameter:elements.author_parameter.value,
      ticks_per_second:Number(elements.author_timebase.value),
      tick:0,
    });
    const created=state.data.tracks.find((track)=>track.target.operation===entity.operation.id&&track.target.parameter===elements.author_parameter.value);
    state.selectedTrackId=created?.id??null;
    state.selectedKeyframeId=created?.keyframes[0]?.id??null;
    state.tick=0;
    render();
    showToast(`Created ${state.selectedTrackId} in ${state.data.revision.label}.`);
  } catch(error) {showError(error);}
});
elements.add_keyframe_button.addEventListener("click",async()=>{
  const track=activeTrack();if(!track)return;
  const tick=Number(elements.new_keyframe_tick.value);
  try {
    state.data=await api("/api/add-keyframe",{track_id:track.id,tick,value:Number(elements.new_keyframe_value.value)});
    state.tick=tick;
    state.selectedKeyframeId=state.data.tracks.find((item)=>item.id===track.id)?.keyframes.find((item)=>item.tick===tick)?.id??null;
    render();
    showToast(`Added Keyframe at tick ${tick} in ${state.data.revision.label}.`);
  } catch(error) {showError(error);}
});

function selectedAnchoredScope() {
  return [elements.scope_cx.checked ? "cx" : null, elements.scope_cy.checked ? "cy" : null].filter(Boolean);
}

elements.generate_candidates_button.addEventListener("click", async () => {
  const scope = selectedAnchoredScope();
  if (!scope.length) { showError(new Error("Select at least one regeneration scope.")); return; }
  try {
    state.data = await api("/api/anchored/generate", {scope,tick:0});
    state.tick = 0;
    render();
    showToast("Generated three pending Proposals from the immutable anchor base.");
  } catch(error) { showError(error); }
});

elements.accept_candidate_button.addEventListener("click", async () => {
  const candidateId = state.data.anchored_regeneration.selected_candidate_id;
  if (!candidateId) return;
  try {
    state.data = await api("/api/anchored/accept", {candidate_id:candidateId,tick:0});
    state.tick = 0;
    render();
    showToast(`Accepted Candidate ${candidateId} as ${state.data.revision.label}.`);
  } catch(error) { showError(error); }
});

for (const checkbox of [elements.scope_cx,elements.scope_cy]) {
  checkbox.addEventListener("change", async () => {
    try {
      state.data = await api("/api/anchored/clear", {tick:0});
      state.tick = 0;
      render();
    } catch(error) { showError(error); }
  });
}

let animationFrame=null,playbackStart=null,lastRequested=-1;
elements.play_button.addEventListener("click",()=>{
  if(state.playing||!state.data.timebase)return;
  const duration=durationTick();const ticksPerSecond=state.data.timebase.ticks_per_second;
  if(state.tick>=duration)state.tick=0;
  state.playing=true;playbackStart=performance.now()-(state.tick*1000/ticksPerSecond);
  const step=(now)=>{if(!state.playing)return;const tick=Math.min(duration,Math.round((now-playbackStart)*ticksPerSecond/1000));if(tick-lastRequested>=Math.max(1,Math.round(ticksPerSecond/25))||tick===duration){lastRequested=tick;loadTick(tick).catch(showError);}if(tick<duration)animationFrame=requestAnimationFrame(step);else state.playing=false;};
  animationFrame=requestAnimationFrame(step);
});
elements.stop_button.addEventListener("click",()=>{state.playing=false;if(animationFrame)cancelAnimationFrame(animationFrame);});

let toastTimer;
function showToast(message){clearTimeout(toastTimer);elements.toast.textContent=message;elements.toast.classList.add("show");toastTimer=setTimeout(()=>elements.toast.classList.remove("show"),2600);}
function showError(error){showToast(error instanceof Error?error.message:String(error));}

loadTick(0).catch(showError);
