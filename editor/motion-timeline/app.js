const state = { data: null, tick: 500, previewValue: null, playing: false, request: 0 };
const elements = Object.fromEntries([
  "revision-id","revision-label","document-id","canvas-badge","svg-host","tick-readout","value-readout",
  "track-id","keyframe-id","operation-id","keyframe-value","edit-value","preview-copy","change-record",
  "commit-button","checkout-button","play-button","stop-button","timecode","timebase","track-title",
  "track-semantics","curve-path","keyframes","playhead","cache-cells","delta-copy","toast",
].map((id) => [id.replaceAll("-", "_"), document.querySelector(`#${id}`)]));

function formatTime(tick, ticksPerSecond) {
  const wholeSeconds = Math.floor(tick / ticksPerSecond);
  const minutes = Math.floor(wholeSeconds / 60);
  const seconds = wholeSeconds % 60;
  const subticks = tick % ticksPerSecond;
  return `${String(minutes).padStart(2,"0")}:${String(seconds).padStart(2,"0")}.${String(subticks).padStart(String(ticksPerSecond - 1).length,"0")}`;
}

async function api(path, payload = null) {
  const options = payload ? { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) } : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

async function loadTick(tick) {
  const request = ++state.request;
  const data = await api(`/api/state?tick=${tick}`);
  if (request !== state.request) return;
  state.tick = tick;
  state.data = data;
  render();
}

async function preview(value) {
  const request = ++state.request;
  const data = await api("/api/preview", { value:Number(value), tick:state.tick });
  if (request !== state.request) return;
  state.data = data;
  state.previewValue = data.preview.active ? Number(value) : null;
  render();
}

function selectedKeyframe() {
  return state.data.track.keyframes.find((keyframe) => keyframe.id === state.data.target.keyframe_id);
}

function curveY(value) { return 166 - ((value - 100) / 400) * 130; }
function cssY(value) { return 36 + (curveY(value) / 190) * 166; }

function renderCurve() {
  const keyframes = state.data.track.keyframes;
  const values = keyframes.map((keyframe) => keyframe.id === state.data.target.keyframe_id && state.previewValue !== null ? state.previewValue : keyframe.value);
  elements.curve_path.setAttribute("d", `M0 ${curveY(values[0])} L500 ${curveY(values[1])} L1000 ${curveY(values[2])}`);
  elements.keyframes.innerHTML = keyframes.map((keyframe, index) => {
    const x = index === 0 ? "15px" : index === keyframes.length - 1 ? "calc(100% - 15px)" : `${(keyframe.tick / 1000) * 100}%`;
    const value = values[index];
    const fixed = keyframe.id === state.data.target.keyframe_id ? "selected" : "fixed";
    return `<button class="keyframe ${fixed}" data-keyframe="${keyframe.id}" style="left:${x};top:${cssY(value)}px" aria-label="${keyframe.id}, value ${value}"><i></i><span>${value}</span></button>`;
  }).join("");
  const middle = document.querySelector(`.keyframe[data-keyframe="${state.data.target.keyframe_id}"]`);
  let drag = null;
  middle.addEventListener("pointerdown", (event) => { drag={y:event.clientY,value:Number(elements.keyframe_value.value)}; middle.setPointerCapture(event.pointerId); });
  middle.addEventListener("pointermove", (event) => { if (drag) elements.keyframe_value.value=String(Math.max(180,Math.min(420,Math.round(drag.value+(drag.y-event.clientY)*2)))); if (drag) schedulePreview(elements.keyframe_value.value); });
  middle.addEventListener("pointerup", () => { drag=null; });
  middle.addEventListener("pointercancel", () => { drag=null; });
}

function render() {
  const data = state.data;
  const selected = selectedKeyframe();
  elements.revision_id.textContent = data.revision.id;
  elements.revision_label.textContent = data.revision.label;
  elements.document_id.textContent = data.document_id;
  elements.canvas_badge.className = `state-badge ${data.preview.active ? "preview" : "committed"}`;
  elements.canvas_badge.textContent = data.preview.active ? `Preview · ${data.revision.label} unchanged` : `Committed · ${data.revision.label}`;
  elements.svg_host.innerHTML = data.frame.svg;
  elements.tick_readout.textContent = data.frame.tick;
  elements.value_readout.textContent = data.frame.sampled_value;
  elements.track_id.textContent = data.track.id;
  elements.keyframe_id.textContent = data.target.keyframe_id;
  elements.operation_id.textContent = `${data.track.target.operation}.${data.track.target.parameter}`;
  elements.keyframe_value.disabled = false;
  elements.keyframe_value.value = String(data.preview.active ? data.preview.value : selected.value);
  elements.edit_value.textContent = elements.keyframe_value.value;
  elements.preview_copy.textContent = data.preview.active ? `Preview only. ${data.revision.label} remains committed in the real RevisionStore.` : "Move the middle Keyframe to create an isolated Core preview.";
  elements.change_record.classList.toggle("hidden", !data.preview.active);
  elements.commit_button.disabled = !data.preview.active;
  elements.checkout_button.disabled = !data.revision.can_checkout_parent;
  elements.timebase.textContent = `${data.timebase.ticks_per_second} ticks/s`;
  elements.timecode.textContent = formatTime(data.frame.tick,data.timebase.ticks_per_second);
  elements.track_title.textContent = `${data.track.target.operation} · ${data.track.target.parameter}`;
  elements.track_semantics.textContent = `${data.track.interpolation} · ${data.track.value_type}`;
  elements.playhead.disabled = false;
  elements.playhead.value = String(data.frame.tick);
  elements.cache_cells.innerHTML = data.cache.map((cell) => `<span class="cache-cell ${cell.status}">${cell.tick} · ${cell.status}</span>`).join("");
  elements.delta_copy.textContent = data.temporal_deltas.length ? data.temporal_deltas.map((delta) => `${delta.start_tick}…${delta.end_tick} invalidated by ${delta.keyframe_id}`).join(" · ") : "Initial cache primed from Golden M";
  renderCurve();
}

let previewTimer;
function schedulePreview(value) { clearTimeout(previewTimer); elements.edit_value.textContent=value; previewTimer=setTimeout(() => preview(value).catch(showError),70); }

elements.keyframe_value.addEventListener("input", (event) => schedulePreview(event.target.value));
elements.playhead.addEventListener("input", (event) => loadTick(Number(event.target.value)).catch(showError));
elements.commit_button.addEventListener("click", async () => { try { state.data=await api("/api/commit",{value:Number(elements.keyframe_value.value),tick:state.tick}); state.previewValue=null; render(); showToast(`Committed ${state.data.revision.label} through ProposalAcceptor.`); } catch(error) { showError(error); } });
elements.checkout_button.addEventListener("click", async () => { try { state.data=await api("/api/checkout-parent",{tick:state.tick}); state.previewValue=null; render(); showToast(`Checked out parent ${state.data.revision.label}.`); } catch(error) { showError(error); } });

let animationFrame=null, playbackStart=null, lastRequested=-1;
elements.play_button.addEventListener("click", () => { if(state.playing)return; if(state.tick>=1000)state.tick=0; state.playing=true; playbackStart=performance.now()-state.tick; const step=(now)=>{ if(!state.playing)return; const tick=Math.min(1000,Math.round(now-playbackStart)); if(tick-lastRequested>=40||tick===1000){lastRequested=tick;loadTick(tick).catch(showError);} if(tick<1000)animationFrame=requestAnimationFrame(step);else state.playing=false;}; animationFrame=requestAnimationFrame(step); });
elements.stop_button.addEventListener("click",()=>{state.playing=false;if(animationFrame)cancelAnimationFrame(animationFrame);});

let toastTimer;
function showToast(message){clearTimeout(toastTimer);elements.toast.textContent=message;elements.toast.classList.add("show");toastTimer=setTimeout(()=>elements.toast.classList.remove("show"),2600);}
function showError(error){showToast(error instanceof Error?error.message:String(error));}

loadTick(500).catch(showError);
