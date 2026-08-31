const state = {
  color: "red",
  strictRevision: false,
  candidates: [],
  selectedCandidate: null,
  acceptedBranches: [],
};

const irisColors = { red: "#D83B3B", orange: "#F47A32" };

const candidateRecipes = [
  { id: "A", name: "Soft glint", highlight: { x: 132, y: 82, r: 17 }, shadow: { opacity: 0.12, y: 4 } },
  { id: "B", name: "Warm focus", highlight: { x: 142, y: 73, r: 12 }, shadow: { opacity: 0.2, y: 7 } },
  { id: "C", name: "Sharp spark", highlight: { x: 151, y: 88, r: 9 }, shadow: { opacity: 0.3, y: 10 } },
];

const elements = {
  mainEye: document.querySelector("#main-eye"),
  status: document.querySelector("#revision-status"),
  strictCopy: document.querySelector("#strict-edit-copy"),
  generate: document.querySelector("#generate-button"),
  reset: document.querySelector("#reset-button"),
  allowHighlight: document.querySelector("#allow-highlight"),
  allowShadow: document.querySelector("#allow-shadow"),
  candidateSection: document.querySelector("#candidate-section"),
  candidateGrid: document.querySelector("#candidate-grid"),
  impactSummary: document.querySelector("#impact-summary"),
  accept: document.querySelector("#accept-button"),
  branchGraph: document.querySelector("#branch-graph"),
  toast: document.querySelector("#toast"),
};

function eyeSvg(options = {}) {
  const color = irisColors[options.color || state.color];
  const highlight = options.highlight || { x: 136, y: 78, r: 14 };
  const shadow = options.shadow || { opacity: 0.12, y: 4 };
  const shadowEnabled = options.shadowEnabled ?? false;
  return `
    <svg viewBox="0 0 320 190" role="img" aria-label="Stylized eye">
      <defs>
        <radialGradient id="irisGlow" cx="40%" cy="34%">
          <stop offset="0" stop-color="#fff" stop-opacity=".32" />
          <stop offset=".35" stop-color="${color}" />
          <stop offset="1" stop-color="#5A1F10" />
        </radialGradient>
        <linearGradient id="skin" x1="0" y1="0" x2="0" y2="1">
          <stop stop-color="#EECAB1" />
          <stop offset="1" stop-color="#C99578" />
        </linearGradient>
        <clipPath id="eyeClip"><path d="M28 99 Q83 30 160 38 Q239 34 294 95 Q242 157 159 153 Q78 158 28 99Z" /></clipPath>
      </defs>
      <path d="M4 96 Q78 0 163 16 Q254 8 316 92 Q255 178 158 174 Q65 180 4 96Z" fill="url(#skin)" opacity=".82" />
      <path d="M28 99 Q83 30 160 38 Q239 34 294 95 Q242 157 159 153 Q78 158 28 99Z" fill="#F7F1E8" stroke="#2A1B18" stroke-width="7" stroke-linejoin="round" />
      ${shadowEnabled ? `<ellipse cx="160" cy="${105 + shadow.y}" rx="61" ry="58" fill="#2D140C" opacity="${shadow.opacity}" clip-path="url(#eyeClip)" />` : ""}
      <circle cx="161" cy="96" r="53" fill="url(#irisGlow)" stroke="#38140D" stroke-width="6" />
      <circle cx="161" cy="97" r="24" fill="#160C0A" />
      <circle cx="${highlight.x}" cy="${highlight.y}" r="${highlight.r}" fill="#FFF" opacity=".94" />
      <circle cx="181" cy="117" r="6" fill="#FFCBA5" opacity=".65" />
      <path d="M29 98 Q85 27 161 37 Q239 32 294 94" fill="none" stroke="#241512" stroke-width="10" stroke-linecap="round" />
      <path d="M33 101 Q84 158 159 153 Q240 157 290 98" fill="none" stroke="#6B3F32" stroke-width="4" stroke-linecap="round" />
    </svg>`;
}

function renderMainEye(options) {
  elements.mainEye.innerHTML = eyeSvg(options);
}

function applyStrictColor(color) {
  if (color === state.color) return;
  state.color = color;
  document.querySelectorAll(".color-button").forEach((button) => {
    button.classList.toggle("selected", button.dataset.color === color);
  });
  if (color === "orange") {
    state.strictRevision = true;
    elements.status.textContent = "Revision R1 · Orange eyes";
    elements.strictCopy.textContent = "Committed: Iris fill changed. Eye and Face geometry stayed identical.";
    elements.generate.disabled = false;
    showToast("Strict edit committed as R1. Regeneration has not started yet.");
  } else {
    state.strictRevision = false;
    state.candidates = [];
    state.selectedCandidate = null;
    state.acceptedBranches = [];
    elements.status.textContent = "Revision R0 · Red eyes";
    elements.strictCopy.textContent = "Choose Orange to commit the confirmed edit as Revision R1.";
    elements.generate.disabled = true;
    elements.candidateSection.classList.add("hidden");
  }
  renderMainEye({ color });
  renderBranches();
}

function generateCandidates() {
  if (!state.strictRevision) return;
  const allowHighlight = elements.allowHighlight.checked;
  const allowShadow = elements.allowShadow.checked;
  if (!allowHighlight && !allowShadow) {
    showToast("No downstream target is allowed. Enable Highlight or Eye Shadow first.");
    return;
  }
  state.candidates = candidateRecipes.map((recipe) => ({
    ...recipe,
    highlight: allowHighlight ? recipe.highlight : { x: 136, y: 78, r: 14 },
    shadow: allowShadow ? recipe.shadow : { opacity: 0.12, y: 4 },
    impacts: [
      ...(allowHighlight ? ["op:eye-highlight.cx", "op:eye-highlight.cy", "op:eye-highlight.radius"] : []),
      ...(allowShadow ? ["op:eye-shadow.opacity", "op:eye-shadow.offset"] : []),
    ],
    shadowEnabled: allowShadow,
  }));
  state.selectedCandidate = null;
  elements.accept.disabled = true;
  renderCandidates();
  renderBranches();
  elements.candidateSection.classList.remove("hidden");
  elements.candidateSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderCandidates() {
  elements.candidateGrid.innerHTML = state.candidates.map((candidate) => `
    <button class="candidate-card" data-candidate="${candidate.id}" aria-label="Select candidate ${candidate.id}">
      <div class="candidate-preview">${eyeSvg({ color: "orange", highlight: candidate.highlight, shadow: candidate.shadow, shadowEnabled: candidate.shadowEnabled })}</div>
      <div class="candidate-meta"><strong>${candidate.id} · ${candidate.name}</strong><span>${candidate.impacts.length} exact impacts</span></div>
    </button>
  `).join("");
  document.querySelectorAll(".candidate-card").forEach((card) => {
    card.addEventListener("click", () => selectCandidate(card.dataset.candidate));
  });
  renderImpactSummary();
}

function selectCandidate(candidateId) {
  state.selectedCandidate = state.candidates.find((candidate) => candidate.id === candidateId) || null;
  document.querySelectorAll(".candidate-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.candidate === candidateId);
  });
  elements.accept.disabled = !state.selectedCandidate;
  if (state.selectedCandidate) {
    renderMainEye({ color: "orange", highlight: state.selectedCandidate.highlight, shadow: state.selectedCandidate.shadow, shadowEnabled: state.selectedCandidate.shadowEnabled });
  }
  renderImpactSummary();
}

function renderImpactSummary() {
  const impacts = state.selectedCandidate?.impacts || [];
  elements.impactSummary.innerHTML = [
    '<span class="impact-chip protected">protected · eye geometry</span>',
    '<span class="impact-chip protected">protected · face</span>',
    ...impacts.map((impact) => `<span class="impact-chip">allowed · ${impact}</span>`),
  ].join("");
}

function acceptCandidate() {
  if (!state.selectedCandidate) return;
  const revisionId = `R${state.acceptedBranches.length + 2}`;
  state.acceptedBranches.push({ revisionId, candidate: state.selectedCandidate });
  elements.status.textContent = `Revision ${revisionId} · Candidate ${state.selectedCandidate.id} accepted`;
  showToast(`Candidate ${state.selectedCandidate.id} accepted as ${revisionId}, parent = R1.`);
  renderBranches();
}

function renderBranches() {
  const pending = state.candidates.length ? '<div class="branch-child">A / B / C · pending Proposals</div>' : "";
  const accepted = state.acceptedBranches.map((branch) => `<div class="branch-child accepted">${branch.revisionId} · Candidate ${branch.candidate.id} · parent R1</div>`).join("");
  elements.branchGraph.innerHTML = `
    <div class="revision-node"><strong>R0</strong><small>red eyes</small></div>
    ${state.strictRevision ? '<div class="revision-node current"><strong>R1</strong><small>orange · anchor base</small></div>' : '<div class="revision-node pending"><strong>R1</strong><small>choose orange</small></div>'}
    ${(pending || accepted) ? `<div class="branch-children">${pending}${accepted}</div>` : ""}
  `;
}

function reset() {
  state.color = "orange";
  applyStrictColor("red");
  elements.allowHighlight.checked = true;
  elements.allowShadow.checked = false;
  renderMainEye({ color: "red" });
  showToast("Prototype reset to R0.");
}

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  toastTimer = setTimeout(() => elements.toast.classList.remove("show"), 2600);
}

document.querySelectorAll(".color-button").forEach((button) => {
  button.addEventListener("click", () => applyStrictColor(button.dataset.color));
});
elements.generate.addEventListener("click", generateCandidates);
elements.accept.addEventListener("click", acceptCandidate);
elements.reset.addEventListener("click", reset);
elements.allowHighlight.addEventListener("change", () => {
  if (state.candidates.length) generateCandidates();
});
elements.allowShadow.addEventListener("change", () => {
  if (state.candidates.length) generateCandidates();
});

renderMainEye({ color: "red" });
renderBranches();
