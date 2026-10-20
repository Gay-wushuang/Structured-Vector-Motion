# Temporal Geometry Pilot — Offline Research Experiment

Status: **T1 A/B IMPLEMENTED / RESEARCH-ONLY / NOT SVM EVIDENCE / NOT FROZEN**.

T0 began as a docs-only planning artifact. T1 now implements the authorized
offline A/B experiment entirely inside this directory. It deliberately changes no
Core code, frozen specification, `ChangeAuthority` registration, schema, Golden
fixture, or production/CLI path. All emitted files are explicitly classified as
experimental outputs, never accepted SVM Evidence.

- Date: 2026-10-20.
- **Checked-out HEAD:** `e46bd5d` (`codex/ci-o1-o2`), matching the remote branch.
  This branch is **not** the integration line: remote
  `integration/w2-g3-baseline` is `6931e17`, while remote default `main` is
  `cf48153` (checked 2026-10-20).
- G3 producer code landed in `01170ed`; the G3 doc record landed on
  `integration/w2-g3-baseline` (`55df2e8`).
- Adjacent non-normative spike: [research/npa](../npa/README.md).

---

## 1. Goal and non-goals

### Goal

Establish, as a bounded and reproducible experiment, whether a **per-frame
temporal geometry** extraction can be produced from video / rendered frames and
recorded as immutable SVM **observation evidence**, so that later, separately
authorized slices can consume it through the existing Proposal / Revision path
without any automatic identity inference.

### Non-goals (explicit)

The pilot does **not**:

- create Entities, Groups, Tracks, Keyframes, TemporalIdentities, or
  `motionTargetBindings`;
- promote, reconcile, or match primitives across frames;
- infer correspondence, ownership, or "same physical object" claims;
- modify `svm/`, `schema/`, `spec/`, Golden fixtures, or CI;
- add `CoTracker3` / `SAM2.1` as in-repo dependencies (see §5, §8).

---

## 2. Current-state review (read-only)

### 2.1 Spec82 G-gates

| Gate | Meaning | Status at baseline |
| --- | --- | --- |
| G1 | Authored-group dialect + additive schema | **IMPLEMENTED / NOT FROZEN** (`46bf27b`) |
| G1.5 | `RevisionStore` dialect upgrade, trusted-history + final-validation | **IMPLEMENTED / NOT FROZEN** (`9d3b8a4`) |
| G2 | `AssembleAuthoredGroupChange` + independent verifier | **IMPLEMENTED / NOT FROZEN** (`86a308e`) |
| G3 | `AuthoredGroupAssemblyAdapter` production Producer | **IMPLEMENTED / ACCEPTANCE PENDING** (`01170ed`, CI `e46bd5d`) |
| G4 | Golden 047 + freeze record | **NOT DONE** (no `examples/047-*`) |

G4 and the Spec82 freeze are the nearest outstanding Spec82 work. The pilot is
**orthogonal** to G4: G4 closes *authored Group assembly*; the pilot studies
*geometry extraction from frames*. See §11 for the exact seam.

Status is read from the code on the checked-out HEAD **plus** the recorded
Spec82 §15 table on `integration/w2-g3-baseline`; the checked-out branch itself
does not carry that progress record.

### 2.2 Relevant authorities and their statuses

| Subsystem | Contract | Status |
| --- | --- | --- |
| Primitive Observation (P2A) | [spec/64](../../spec/64-p2a-raster-primitive-observation-proposal.md) | **FINAL / FROZEN** |
| Observation Assembly (P2B) | [spec/66](../../spec/66-p2b-primitive-observation-assembly.md) | **FINAL / FROZEN** |
| Temporal Identity Selection (P2C) | [spec/68](../../spec/68-p2c-temporal-identity-selection.md) | **FINAL / FROZEN** |
| Temporal Correspondence (R0) | [spec/35](../../spec/35-temporal-correspondence.md) | **FROZEN baseline** |
| Temporal Identity Promotion (R1) | [spec/36](../../spec/36-temporal-identity-promotion.md) | **FROZEN** |
| Exact-provenance target binding (P2D) | [spec/70](../../spec/70-p2d-exact-provenance-motion-target-binding.md) | **SPECIFIED / NOT IMPLEMENTED**; **P2D-B BLOCKED** |
| Stable artwork correspondence | [spec/71](../../spec/71-stable-artwork-representation-correspondence.md) | **DESIGN / NOT FROZEN** (bounded §12 mode frozen via spec/80) |
| Present-time certification | [spec/80](../../spec/80-present-time-representation-certification.md) | **FROZEN (bounded v0.1 profile)** |
| Versioned target consumer | [spec/81](../../spec/81-versioned-representation-target-consumer-contract.md) | **FROZEN (bounded v0.1 profile)** |
| Construction-derived Group authority | [spec/72](../../spec/72-construction-derived-group-authority.md) | **IMPLEMENTED / NOT FROZEN** |
| SVG two-part Group construction | [spec/73](../../spec/73-svg-two-part-group-construction.md) | **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN** |
| SVG import subset | [spec/10](../../spec/10-svg-import-adapter.md) | strict subset, fail-closed |
| Group transform / motion | [spec/30](../../spec/30-group-transform.md), [spec/31](../../spec/31-group-transform-motion.md) | evaluation-time composition; authored Tracks |
| POP output / structure / geometry | [spec/26](../../spec/26-pop-output-adapter.md), [spec/27](../../spec/27-pop-structure-reconciliation.md), [spec/42](../../spec/42-pop-geometry-observations.md) | Golden P/Q/S4.1 normative |

### 2.3 Revision acceptance path (as implemented)

A new evidence-producing adapter reaches a Revision only through this chain:

```text
Adapter.propose(request, artifacts) -> Proposal
  -> ProposalAcceptor._validate()
       base exists -> head/stale check -> exact registered Change types
       -> artifact resolution -> artifact-bound verifier -> policy -> apply
  -> Transaction.apply()  (all Changes, then validate_document(dialect))
  -> RevisionStore._commit_verified()  (Trusted Core only)
```

Governing points, verbatim-relevant:

- The accepted Change type set is **closed-world**; an unregistered `Change` is
  rejected outright ([svm/proposals.py](../../svm/proposals.py), `_validate`).
- Artifact-bound verifiers receive `(change, resolved_artifacts)` and must
  re-derive content; a valid-looking but forged artifact cannot cross acceptance
  ([svm/change_authority.py](../../svm/change_authority.py)).
- `RevisionStore.commit()` is **not** an adapter acceptance API; adapters must
  never receive a mutable store.
- Evidence append uses `AppendReferencesChange` / `attach_analysis` authority;
  `Change.apply` appends **only** accepted references.

The G3 producer ([svm/adapters/authored_group_assembly.py](../../svm/adapters/authored_group_assembly.py))
is the reference adapter shape: a deterministic `propose()` returning a `Proposal`
with recorded `GeneratorProvenance`, `adapter_id`, `adapter_version`, and a
proposal/transaction ID derived from canonical bytes (no randomness/time).

### 2.4 The existing observation evidence envelope

The frozen primitive-observation envelope any pilot evidence should reuse:

```text
artifact media : application/vnd.svm.primitive-observations+json;version=0.2
schema         : svm-primitive-observations-0.2   (kind REFERENCE)
shape          : { schema_version, canvas:[w,h], frames:[ {tick, primitives:[...]} ] }
primitive      : { observation_id, primitive_type, bounds, fill, geometry }
```

R0 scoring (`svm-bounds-correspondence-policy@0.1`) uses only bounds, fill and
primitive type: `0.45·centroid + 0.20·size + 0.20·color + 0.15·type`; SUPPORTED
requires mutual-best, total ≥ 0.75 and both margins ≥ 0.08; < 0.35 is REJECTED,
otherwise UNCERTAIN. R0 explicitly does **not** consume v0.2 landmark geometry.

### 2.5 The Primitive Observation → legal Entity gap (unresolved)

There is currently **no registered path** that turns a pilot primitive
observation into a legal Entity. This is a real architectural gap:

- P2A/P2B are **evidence-only** and may not create an Entity, Group, Track or
  identity ([spec/64 §12](../../spec/64-p2a-raster-primitive-observation-proposal.md)).
- Component Promotion creates neutral, **non-rendered** `PromotedComponent`
  Regions, and only from accepted OpenCV component-analysis evidence
  ([spec/17](../../spec/17-component-promotion.md)). A pilot video primitive is
  not that evidence.
- POP import (`ImportPrimitiveSequenceChange`) creates renderable Entities only
  from a validated POP token sequence ([spec/26](../../spec/26-pop-output-adapter.md)).
- SVG import creates Entities only from the strict SVG subset
  ([spec/10](../../spec/10-svg-import-adapter.md)).

So "promote the primitive to an Entity" is **not** an operation the pilot can
invoke. Any structural creation would require a **new, separately authorized**
Change that allocates fresh Entity IDs (AGENTS.md: structural operations that
create semantic objects must allocate new Entity IDs). Until such a gate exists the
pilot ends at evidence, and the §11 G3 seam cannot be exercised end-to-end.

---

## 3. Governing constraints (what the pilot must not break)

These are recorded as **binding pilot constraints**, derived from the frozen
contracts above. Any experiment that violates one is out of scope.

1. **No automatic identity.** R0/R1 are the only boundaries that turn an
   explicitly selected SUPPORTED inference into a stable cross-frame binding.
   The pilot must stay at the observation/evidence layer ([spec/35](../../spec/35-temporal-correspondence.md), [spec/36](../../spec/36-temporal-identity-promotion.md)).
2. **Animosaics and optical flow are outside R1.** [spec/36](../../spec/36-temporal-identity-promotion.md)
   states it directly: "Observed motion, centroid-displacement conversion, user
   overrides, editing propagation, Animosaics, optical flow, and new
   correspondence heuristics are outside R1." The pilot may develop these only as
   a **new, separately versioned evidence profile**, never by widening R1.
3. **Confidence is not authority.** [spec/71 §8](../../spec/71-stable-artwork-representation-correspondence.md):
   heuristic/CV/AI systems "may propose correspondence hypotheses, but SHALL NOT
   silently grant ownership"; "Thresholds, model labels or confidence alone do not
   satisfy §3." Model outputs are hypotheses only.
4. **Ordinary video is not P2A-eligible.** P2A requires a frame-level
   flat-background / solid-foreground precondition; otherwise the whole inference
   fails closed ([spec/64 §2](../../spec/64-p2a-raster-primitive-observation-proposal.md)).
   The pilot's frames will not generally satisfy it, so the pilot's output cannot
   claim P2A/P2B parity; it must be a distinct profile.
5. **P2D-B is BLOCKED; single-Entity Motion Target is OPEN.** No pilot result may
   be presented as motion binding, representation correspondence, or target
   ownership.
6. **Evidence-only acceptance.** Acceptance may only append verified evidence
   references; it may not create Entities/Groups/Tracks/identities
   ([spec/64 §12](../../spec/64-p2a-raster-primitive-observation-proposal.md)).
7. **Do not touch Core.** No `svm/`, `schema/`, `spec/`, Golden or CI edits in the
   pilot. Implementation, if ever authorized, is a separate gate.
8. **No Entity creation from pilot evidence.** No registered Change turns a pilot
   observation into an Entity (§2.5); creating one is a separate structural
   authority, never a pilot effect.

### 3.1 Evidence ledger — proven vs assumed vs to be measured

Legend: **[CODE]** verified in this repository; **[SPEC]** normative in a spec;
**[PAPER]** from an external paper/repo; **[ASSUMPTION]** design hypothesis, not
evidence; **[MEASURE]** must be established by the pilot experiment.

| Claim | Tag | Basis |
| --- | --- | --- |
| Frozen observation envelope v0.2 + R0 weighting | CODE / SPEC | `svm/adapters/temporal_correspondence.py`; [spec/35](../../spec/35-temporal-correspondence.md) |
| Acceptance gates (closed-world Change, independent verifier, no `commit()` from adapters) | CODE | `svm/proposals.py`, `svm/change_authority.py`, `svm/revisions.py` |
| P2A frame-level flat/solid precondition; evidence-only | SPEC | [spec/64 §2, §12](../../spec/64-p2a-raster-primitive-observation-proposal.md) |
| R1 excludes Animosaics / optical flow | SPEC | [spec/36](../../spec/36-temporal-identity-promotion.md) |
| Confidence is not authority | SPEC | [spec/71 §8](../../spec/71-stable-artwork-representation-correspondence.md) |
| G3 assembles only existing Entities; makes no identity claim | SPEC / CODE | [spec/82 §1, §3](../../spec/82-explicit-authored-group-assembly.md); `svm/adapters/authored_group_assembly.py`, `svm/document.py::_validate_groups` |
| No Entity-creation path from pilot evidence | CODE (absence) / ASSUMPTION | registered Changes in `svm/change_authority.py`; see §2.5 |
| POP is an integrated, snapshotted external producer | CODE / SPEC | `svm/adapters/pop_output.py`; [spec/26](../../spec/26-pop-output-adapter.md) |
| Primitive greedy fitting; Animosaics group motion | PAPER | Fogleman; Smith/Liu/Klein 2005 |
| CoTracker3 I/O contract and low-texture failure mode | PAPER / repo docs | `facebookresearch/co-tracker` |
| CoTracker3 license = majority CC-BY-NC | ASSUMPTION (reported) | repository + third-party reviews; **not** verified against the pinned `LICENSE` |
| SAM 2.1 per-checkpoint VRAM figures | ASSUMPTION (third-party estimate) | deployment guides (CLORE.AI / intelion.cloud); **must be measured on-device** |
| A/B/C/D quality ranking and drift / flicker trade-offs | ASSUMPTION | §10 comparison is a hypothesis |
| Method B reuses `spec/37` / `spec/41` mechanics | ASSUMPTION | transfer not yet demonstrated |
| Any A→D improvement claim | MEASURE | requires the §10 controlled protocol |

Nothing tagged [ASSUMPTION] may be reported as a result; nothing tagged [MEASURE]
is known until it is measured. This is the design/experiment boundary.

---

## 4. Reusable ideas from the three external systems

### 4.1 Primitive (Fogleman, 2016)

Greedy image→primitives fitting: add one shape at a time, each chosen to maximize
similarity to the residual; shapes are triangle / rectangle / ellipse; a fixed
seed makes a run reproducible.

**Reusable:** (a) deterministic greedy fitting with a *recorded* seed and an
explicit quality/step budget; (b) a ranked candidate list; (c) the per-frame
independent fitting needed by method A. **Not** reusable as a Core dependency:
the optimizer is a stochastic CPU-heavy external tool, so its output must be
snapshotted as an immutable Artifact (the POP precedent, §4.3).

### 4.2 Animosaics (Smith / Liu / Klein, SCA 2005)

Characterizes temporal coherence as **the coordinated movement of groups of
primitives**, packing 2D tiles over time via area-based centroidal Voronoi
diagrams, and rejects per-tile deform/blend/scale in favour of faithful group
motion.

**Reusable:** the core *concept* — temporal coherence is a property of primitive
**groups** whose members move together, which reduces flicker. This maps naturally
onto SVM's Group + Group-Transform model ([spec/30](../../spec/30-group-transform.md), [spec/31](../../spec/31-group-transform-motion.md)).
**Constraint:** Animosaics grouping **must not** become automatic identity. It may
only inform (i) an author-anchored grouping proposal, or (ii) evidence-only
group-motion constraints — never a persisted Group or TemporalIdentity by itself.

### 4.3 Primitive Operation Painter (POP) — already integrated

POP is an external operation-prefix continuation model already snapshotted into
SVM as Golden P/Q/S4.1 (`wonderfulearth/primitive-operation-painter`,
`doubixz/primitive-operation-painter-weight`; see [spec/26](../../spec/26-pop-output-adapter.md)).

**Reusable, and this is the closest existing template:**

- The **immutable-snapshot boundary**: a possibly stochastic upstream run →
  immutable raw-token Artifact → deterministic Adapter/Proposal/acceptance
  ([spec/26](../../spec/26-pop-output-adapter.md)).
- **Ordered primitive construction** as draw order (background + primitive index),
  not content-animation time.
- **Exact geometry / landmark derivation** with no AABB-corner substitution
  ([spec/42](../../spec/42-pop-geometry-observations.md)): a template for deriving
  ordered landmarks from primitives deterministically.
- **Provenance discipline**: model ID, checkpoint SHA-256, seed, sampling policy,
  decoder identity (`pop/decode-tokens-to-render-data@d5489b0`), renderer identity.
- **The 1.23 GB checkpoint is deliberately not in the repo** — the model posture
  the pilot should copy.

Adjacent: [research/npa](../npa/README.md) documents a *paper-only* geometric
abstraction boundary (unordered primitive assembly) whose materialization is
blocked pending an official release; it reinforces "no invented schema, no guessed
fixture".

---

## 5. External model evaluation

Both models run **offline, out-of-repo**; only their immutable outputs enter SVM.
No checkpoint is vendored.

### 5.1 CoTracker3 (any-point tracking)

- **Source:** `facebookresearch/co-tracker` (Meta AI + Oxford VGG); ICCV 2025.
- **Input:** a video (or frame sequence) plus query points — manually chosen or a
  regular grid.
- **Output:** per-point 2D trajectories over time **plus a visibility/occlusion
  flag per point per frame**; online and offline variants; supports long occlusion
  and out-of-view.
- **License (as reported; verify against the pinned `LICENSE` before use):** the
  majority is **CC-BY-NC (non-commercial)**; some portions are MIT / Apache-2.0
  inherited from other projects. Source: the repository statement plus third-party
  reviews, **not verified in this docs-only pass**. Consequences: research /
  non-commercial use only; must **not** be vendored; must **not** become a required
  runtime dependency of the shipped project.
- **Known failure mode:** featureless / low-texture surfaces (sky, water).
- **Resource note (RTX 4060 8 GB):** memory scales with `grid_size` (number of
  tracks), frame resolution, and window length; keep windows/resolution/grid
  bounded, prefer fp16. This is a structural expectation, not a measured figure.

**Pilot relevance — and a sharp caveat:** POP/controlled-raster artwork is
**flat solid fill**, which is precisely CoTracker3's documented failure mode.
CoTracker3 is therefore best suited to *photographic / textured* source footage,
not to flat vector-like frames.

### 5.2 SAM 2.1 (promptable segmentation with video memory)

- **Source:** `facebookresearch/sam2`; checkpoints `sam2.1_hiera_{tiny,small,base_plus,large}`.
- **Input:** image or video + a prompt (point / box / mask); ~1024 px input.
- **Output:** masks, propagated across frames via a streaming memory module.
- **License:** weights **Apache-2.0**; however the common `ultralytics` wrapper is
  **AGPL-3.0**, which reaches the application → run the weights outside
  `ultralytics` to keep Apache-2.0.
- **Resource note (RTX 4060 8 GB), bf16 approx VRAM — third-party estimate, not a
  first-party Meta figure.** The per-checkpoint numbers below come from third-party
  deployment guides (CLORE.AI / intelion.cloud), not from Meta's repository, and
  real usage also depends on input resolution (~1024 px), batch, video length and
  the streaming memory module. Treat them as **order-of-magnitude planning
  estimates that MUST be measured on the target device**:
  tiny ≈ 2 GB, small ≈ 3 GB, base+ ≈ 5 GB, **large ≈ 9 GB (likely exceeds 8 GB)**.
  Planning posture: use `tiny` / `small` / `base_plus`; treat `large` as out of
  budget until an on-device measurement says otherwise.

### 5.3 Resource budget summary (RTX 4060 8 GB)

All figures are **third-party estimates with stated applicability conditions**, not
measured on this machine; confirm each by an on-device peak-VRAM measurement.

| Model | Fits 8 GB? | Notes |
| --- | --- | --- |
| CoTracker3 (grid, bounded) | yes, if bounded | limit grid / resolution / window; fp16 |
| SAM 2.1 tiny / small / base+ | yes | prefer `base_plus` upper bound |
| SAM 2.1 large | **no** (~9 GB bf16, estimate) | out of budget pending on-device measurement |

---

## 6. Experiment data

Use deterministic, already-in-repo sources first, so metrics have real ground
truth:

1. **Controlled raster fixture** — `035-controlled-raster-recovery` base/translation
   frames (known geometry), reused by R0/R1/S0–S5B.
2. **POP fixtures** — the frozen Golden P snapshot (143 primitives, exact ordered
   geometry + tokens) and Golden Q masks; useful because their geometry is
   *known* and *deterministic*.
3. **Rendered SVM frames** — sample an existing animated `demo/` Document to get
   vector-truth frames with known per-Entity geometry.

Then add, for qualitative coverage only (no ground-truth claims):

4. a short **real-photo clip** (textured) — exercises CoTracker3/SAM2.1 strengths;
5. a **flat vector-like clip** — exercises the low-texture failure mode;
6. a **mixed clip**.

**Rule:** model output is a *hypothesis*, never ground truth. Metrics against model
output measure agreement, not correctness.

---

## 7. Metrics

| Group | Metric | Definition | Needs GT? |
| --- | --- | --- | --- |
| Reconstruction quality | per-frame IoU | `area(raster(primitive set) ∩ source foreground) / union` | yes |
| | pixel MAE | mean abs RGB channel error (POP precedent) | yes |
| | bounds / centroid error | L2 px vs known geometry | yes |
| Temporal flicker | transform jitter | mean `‖T_{t−1} − 2·T_t + T_{t+1}‖` (second difference) across the sequence | no |
| | reconstruction variance | std-dev of per-frame IoU / MAE over time | yes |
| | visibility flip rate | occlusion-flag toggles per primitive per frame | partly |
| Drift | cumulative error | centroid / transform error vs the frame-0 reference; report value and slope | yes |
| Identity switch | ID-switch count / rate | times a primitive's assigned identity changes, per frame | yes |
| | IDF1-style | identity F1 over the sequence | yes |
| Determinism | byte identity | repeated runs → identical Artifact and hash | no |
| Cost | time / peak VRAM | wall time per frame; peak device memory under the 8 GB budget | no |

Definitions are fixed **before** the run and identical across A/B/C/D (§10).

---

## 8. Rejection conditions (fail-closed)

Every condition below must **abstain or reject atomically**, leaving HEAD,
Revision count and stored Documents unchanged:

- frame fails the controlled flat/solid precondition (for any P2A-parity claim);
- zero SUPPORTED primitives in a frame (mirror P2B zero-SUPPORTED abstention);
- no mutual-best match, or margins below threshold → UNCERTAIN, never forced;
- acceptance driven by confidence alone → REJECT ([spec/71 §8](../../spec/71-stable-artwork-representation-correspondence.md));
- identity conflict → `TEMPORAL_IDENTITY_CONFLICT` semantics (mirror R1);
- non-finite numbers, bool-as-int, extra/missing/unknown fields, wrong array
  lengths;
- stale base, tampered / forged artifact, missing dependency in the closure;
- a license-gated model output with no recorded model / checkpoint hash / seed /
  sampling config provenance;
- low-texture tracking failure on flat-fill frames → abstain, do not fabricate.

---

## 9. Evidence schema candidates

### 9.1 Experimental output vs accepted SVM Evidence

| | Experimental output (this pilot) | Accepted SVM Evidence |
| --- | --- | --- |
| Authority | none — producer assertions only | registered Change + independent verifier |
| Addressability | may be unhashed scratch output | immutable content-addressed Artifact |
| Location | scratch / `build/` area, not a Document | referenced by an accepted Revision |
| Reproduction | may differ between runs; failure expected | byte-reproducible from the resolved closure |
| Portability | needs the producer / model installed | valid and evaluable without the producer (POP precedent) |
| Provenance | informal | schema / media / kind + policy / adapter identity |

**Rule:** no experiment output may be called "SVM Evidence" until it has crossed
`ProposalAcceptor` into a Revision. A **design PASS is not an experiment PASS**
(§3.1).

**Do not modify `svm-primitive-observations-0.2`.** Options, in preference order:

1. **Reuse the frozen v0.2 observation + a new companion provenance Artifact**
   (the P2B pattern). The v0.2 primitive field set is exactly
   `{observation_id, primitive_type, bounds, fill, geometry}`, so audit / model
   provenance / visibility / reason codes go into a companion Artifact rather than
   extending the frozen schema. *Smallest, most compatible option.*
2. **A new versioned profile**, e.g. `svm-temporal-geometry-observations-0.1`
   (`application/vnd.svm.temporal-geometry-observations+json;version=0.1`),
   carrying per-`(tick, primitive)` geometry + optional visibility, plus a
   companion provenance Artifact. Required if the payload genuinely needs fields
   v0.2 cannot carry.
3. **Raw snapshot evidence only** (POP pattern): an immutable model-output Artifact
   consumed by a future deterministic Adapter that produces option 1 or 2.
   Used as the pilot's *first* artifact so nothing downstream is committed early.

Every candidate must bind: source raster closure, manifest occurrence, frame
index, tick, source PNG ID, model identity, checkpoint SHA-256, seed, sampling
config, decoder identity, renderer identity, and adapter/policy identity — using
full 64-hex SHA-256 and canonical bytes, exactly as P2A/P2B/POP do.

---

## 10. Four candidate methods (A / B / C / D)

Base methods for extracting per-frame geometry:

### A — Per-frame independent Primitive

Fit each frame independently (Primitive-style greedy, or POP/NPA-style
primitive assembly). Per-frame `SUPPORTED/UNCERTAIN/REJECTED` like P2A.

- **Pro:** deterministic snapshot boundary; no cross-frame dependency; simple.
- **Con:** no temporal link; flicker; per-frame primitive sets are not comparable
  by construction; correspondence is deferred entirely.

### B — A + first-frame geometry propagated by OpenCV optical flow

Author/fit geometry once on frame 0, then propagate per-frame transforms via
OpenCV optical flow (LK / dense). OpenCV is already available (analysis extra).

- **Pro:** cheap, deterministic-ish, reuses existing `spec/37`/`spec/41` observed
  translation/similarity machinery.
- **Con:** drift accumulates; flat fills give optical flow little signal;
  occlusion handled poorly.

### C — B + Animosaics anchor / Group constraints

Add Animosaics-style "coordinated movement of groups of primitives": anchor
constraints tie members so the group moves together, mapping onto the existing
Group + Group-Transform model.

- **Pro:** materially reduces flicker and per-tile divergence; directly matches
  SVM's Group semantics.
- **Con:** grouping is a *choice*, not an inference — must be author-anchored or
  evidence-only; risk of smuggling automatic identity if unconstrained.

### D — C + local geometry re-optimization

After propagation, locally re-optimize each primitive's geometry per frame
(Primitive-style local search / refinement).

- **Pro:** recovers shape fidelity under deformation the pure-transform methods
  miss.
- **Con:** per-frame divergence, possible identity drift, flicker; needs an
  explicit stability budget and a "stop when unstable" rule.

### Fair-comparison conditions

A difference must be attributable to the method, not to a confound. Hold constant:

- **identical input** frames, canvas size, coordinate units, timebase and tick map;
- **identical budget** (primitive count / max steps / quality target) and, for any
  stochastic optimizer, the **same recorded seed**;
- **identical ground truth** and the **same metric code**;
- **one variable at a time**: A vs B differ only by the propagation stage, B vs C
  only by anchors / group constraints, C vs D only by the refinement stage;
- **identical evaluation window and drift reference frame**;
- report each stage's metrics **and** its fail-closed / abstention rate.

An A→D gain that cannot be isolated to the added stage is not evidence for that
stage.

### Comparison

| | Temporal link | Flicker | Deformation fidelity | Drift risk | New authority needed |
| --- | --- | --- | --- | --- | --- |
| A | none | high | high (per-frame) | n/a | none (evidence-only) |
| B | flow | medium | low | high | none |
| C | flow + anchors/group | low | low–medium | medium | author-anchored group (evidence-only) |
| D | flow + anchors + refine | low | high | medium–high | none (evidence-only) + stability budget |

The table above is a **design hypothesis** ([ASSUMPTION] in §3.1), not a measured
result; the §7 metrics under the §10 protocol decide it.

**Staged recommendation:** run **A** → **B** → **C** → **D** in order, each as a
separate, independently accepted evidence artifact. Do not jump to C/D before the
lower stage's metrics and fail-closed cases pass. Never let a stage persist
identity, membership, or motion.

---

## 11. Integration with G3 and the Revision path (design seam only)

The pilot itself writes nothing. Any **future authorized** slice would:

- implement a Producer adapter exposing `propose(request, artifacts) -> Proposal`,
  with deterministic IDs and recorded generator provenance (the
  `AuthoredGroupAssemblyAdapter` shape);
- register an **exact new Change + independent verifier** in the closed-world
  `ChangeAuthority` (a separate gate — not part of this pilot);
- route acceptance through `ProposalAcceptor.accept()` into one atomic Revision;
  never call `RevisionStore.commit()` from an adapter;
- reuse the existing `attach_analysis` policy action; append only evidence
  references.

**The G3 seam (and its limit):** G3's `AssembleAuthoredGroupChange` only *appends*
a Group that references **≥ 2 already-existing, currently legal Entity IDs**. It
creates, copies, splits, promotes and renames nothing, and it asserts **no**
identity: its provenance is `authored-group-assembly@0.1`, membership is
author-chosen, and the Group ID deliberately excludes Base/transform/metadata
([spec/82 §1, §3, §4](../../spec/82-explicit-authored-group-assembly.md)). It also
does **not** create the members. So the seam is usable only **after** a separate,
independently authorized gate has turned pilot primitives into Entities (§2.5);
only then can Group-Transform motion ([spec/30](../../spec/30-group-transform.md))
animate them. The division of labour is: **the pilot extracts geometry; a separate
structural authority creates Entities; the author assembles; nothing infers identity.**

---

## 12. Spec-conflict / boundary findings (stop-and-report)

No *blocking* conflict was found. The following tensions are recorded as
constraints; any later step that would need to widen a frozen contract must
**stop and report** rather than reinterpret it.

1. **R1 excludes Animosaics/optical flow** ([spec/36](../../spec/36-temporal-identity-promotion.md)).
   → Develop only as a new, separately versioned profile.
2. **Confidence ≠ authority** ([spec/71 §8](../../spec/71-stable-artwork-representation-correspondence.md)).
   → Pilot stays proposal/evidence-only.
3. **Ordinary video is not P2A-eligible** ([spec/64 §2](../../spec/64-p2a-raster-primitive-observation-proposal.md)).
   → Pilot output cannot claim P2A/P2B parity.
4. **P2D-B BLOCKED; single-Entity Motion Target OPEN; representation
   correspondence is the NEXT GATE** ([spec/71 §11](../../spec/71-stable-artwork-representation-correspondence.md), README).
   → No binding/correspondence claims.
5. **License:** CoTracker3 CC-BY-NC and SAM2.1-via-Ultralytics AGPL-3.0 must not be
   vendored into the repo/Core; run offline and snapshot only (POP precedent).
6. **Hardware:** SAM 2.1 large (~9 GB bf16) exceeds RTX 4060 8 GB → use
   tiny / small / base_plus; bound CoTracker3 grid/resolution/window.
7. **Evidence schema:** `svm-primitive-observations-0.2` is frozen and must not be
   extended → use a companion Artifact or a new versioned profile.
8. **No Entity-creation path** from pilot evidence (§2.5) → the G3 seam (§11) is
   unreachable until a separate structural gate exists.
9. **Two reported facts are unverified here:** CoTracker3's license terms and the
   SAM 2.1 VRAM figures are third-party / reported, not first-party or measured
   (§5, §3.1). Verify both before any licensing or budget claim.

---

## 13. Deliverables and proposed gates

Pilot deliverables:

- **T0** (this document) — review + plan; no runtime change.
- **T1** — offline harness + snapshotted experimental outputs for methods A and B,
  with recorded input/config/runner hashes, budgets, cost measurements, metrics,
  comparison video, reproducibility check and GO/CONDITIONAL/NO-GO decision.
- **T2** — methods C/D as separate experimental outputs, gated on T1 metrics and
  the §8 fail-closed cases.
- **T3** — a proposed observation-evidence schema (option 1/2/3 from §9) and a
  draft Change/verifier design for an *independently authorized* implementation
  gate. T3 is a design proposal only; it authorizes no code.

Each gate must produce a reproducible run manifest (exact inputs, environment,
model/checkpoint hashes, seed, output Artifact/Proposal IDs) and must leave Core,
frozen specs, `ChangeAuthority` and production paths untouched.

A design or metric PASS here is a **design** result, not proof that any method is
correct; only measured, reproduced results on the §6 fixtures count as experiment
results, and only acceptance across `ProposalAcceptor` creates SVM Evidence.

---

## 14. T1 A/B implementation and measured result

The frozen protocol is [`experiment.json`](experiment.json). It fixes the four
`035-controlled-raster-recovery` frames (`tick_000` through `tick_036`), exact GT,
512×512 canvas, ticks 0/12/24/36, frame-0 drift reference, one five-vertex polygon,
and the exact frame-0 geometry. A evaluates 29 fixed contour-approximation
candidates independently on each later frame. B samples the same frame-0 polygon
boundary and propagates it through three OpenCV pyramidal-LK transitions using a
fixed LMEDS similarity-affine fit. Neither method uses CoTracker3, SAM, a GPU, or
an external checkpoint.

Run from the repository root:

```powershell
python research/temporal-geometry-pilot/run_experiment.py
python -m unittest discover -s research/temporal-geometry-pilot/tests -v
```

The committed snapshot is under
[`runs/t1-controlled-raster-ab-v1`](runs/t1-controlled-raster-ab-v1):

- `raw/method-a.json`, `raw/method-b.json` — raw experimental geometry and flow
  diagnostics;
- `metrics.json` — reconstruction, temporal, GT motion, drift, abstention and
  identity-applicability results;
- `costs.json` — isolated per-method wall-time and memory measurements;
- `comparison.avi` — lossless FFV1 source/A/B comparison;
- `reproducibility.json` — repeated frozen-raw downstream metric/render checks;
- `run-manifest.json` — input, source, environment and output hashes plus the
  authority disclaimer.

Measured on Python 3.12.5, NumPy 2.2.6 and OpenCV 4.10.0:

| Metric | A | B |
| --- | ---: | ---: |
| Mean IoU | 1.000000 | 0.980505 |
| Mean GT vertex RMSE | 0.252 px | 1.986 px |
| Final GT vertex RMSE | 0.313 px | 3.710 px |
| Final centroid drift error | 0.121 px | 0.952 px |
| Abstention rate | 0% | 0% |
| Identity metrics | **N/A** | diagnostic fixed-label continuity only |

Frozen-raw downstream metrics, rendered frames and decoded video frames reproduced
byte-for-byte. The result is **CONDITIONAL**, not GO: all declared quality,
drift/abstention and reproducibility gates pass, but this machine has OpenCV 4.10.0
while the repository analysis extra pins 4.14.0.94. Re-run with the declared wheel
before treating the numerical result as the canonical T1 baseline. This condition
does not authorize any Core, schema, spec, ChangeAuthority or Revision change.

---

## References

- [Primitive — Michael Fogleman](https://github.com/fogleman/primitive)
- [Animosaics — Smith, Liu, Klein, SCA 2005](https://www.cs.mcgill.ca/~kaleigh/publications/animosaics/animosaics_final.pdf)
- [Primitive Operation Painter — wonderfulearth](https://github.com/wonderfulearth/primitive-operation-painter)
- [CoTracker3 — Meta AI / Oxford VGG](https://github.com/facebookresearch/co-tracker)
- [SAM 2.1 — Meta AI](https://github.com/facebookresearch/sam2)
- [NPA research spike](../npa/README.md)
