# Phase 2 Charter — First Inference Slice (P2A)

Status: charter. The slice chosen here is P2A, Raster Primitive Observation
Proposal. Its detailed normative contract lives in
`spec/64-p2a-raster-primitive-observation-proposal.md`; this charter does not
duplicate it. P2B and subsequent slices remain planning only.

This charter modifies no frozen Phase 1 contract. Phase 1 remains FINAL / FROZEN
(`spec/62-phase1-final-freeze.md`, implementation baseline
`0caae5b8061bfd12901bdb0898f171d4ad5d48a4`).

Implementation: `svm/adapters/raster_primitive_observation_proposal.py`, with
focused Golden coverage in `tests/test_raster_primitive_observation_proposal.py`
and the checked-in `examples/040-raster-primitive-observation-proposal/scene.avi`.
The implementation first landed at `e527a74` and was hardened at `420176e`; it
now conforms to the detailed normative contract in `spec/64`, including full
candidate/evaluation hashes, occurrence-authority identity inputs, fixed reason
and verification-reference ordering, and the normative three-component Golden
fixture.

## 1. What Phase 1 actually assumes

This section is grounded in the frozen code and specs, not in the non-goal list.
The pipeline is:

```text
pixels / video
-> observations
-> correspondence
-> motion evidence
-> camera compensation
-> binding
-> tracks
-> editable SVM
```

### 1.1 Stage-by-stage authority

| Stage | Input authority (caller must supply) | Comes from real pixels | Comes from config / fixture | Fail-closed boundary |
| --- | --- | --- | --- | --- |
| Video ingestion (`svm/video_ingestion.py`) | `source_reference` (immutable AVI `REFERENCE`), `VideoSampling(frame_indices, ticks_per_second, source_fps?)` | decoded frame bytes, canonical PNGs | which frames, ticks/sec, optional exact FPS assertion | container/codec/timing/dimension/drop checks (`video_ingestion.py:125-224`) |
| OpenCV analysis (`svm/adapters/opencv_analysis.py`) | exactly one PNG artifact; options `threshold`, `foreground`, `connectivity` | mask, connected components, bounds, pixel_area, centroid, component_digest | threshold/polarity/connectivity | scope, 8-bit opaque grayscale, 32 MiB / 16 MP (`:66-67`, `:195-196`) |
| Component enumeration | — (automatic) | **component count and IDs** | — | — |
| Raster geometry observation (`svm/adapters/raster_geometry_observations.py`) | `options["occurrences"]` = exactly two `{analysis_artifact_id, component_id, tick}` (`:38-43`, `:118-138`) | contour, ordered landmarks, fill level, bounds (`:193-255`) | **explicit `component_id` per occurrence**, tick | single hole-free nondegenerate contour, area ≥ 256, 3–32 vertices, min edge ≥ 8 px, longest-edge margin > 4 px (`:277-295`) |
| Temporal correspondence R0 (`svm/adapters/temporal_correspondence.py`) | one accepted observation artifact (2 frames); **no options** (`:39`) | — | the *pairing of the two frames* was already declared upstream | scope/artifact checks (`:43`, `:131-164`) |
| Cross-frame matching evidence | — (automatic) | pairwise scores and `SUPPORTED/UNCERTAIN/REJECTED` | — | thresholds `0.75 / 0.08 / 0.35` (`:272-276`) |
| Identity promotion R1 (`svm/adapters/temporal_identity_promotion.py`) | R0 artifact + **explicit `inference_ids`** (`:58-69`) | — | which candidates become identity | only `SUPPORTED`; conflict → `TEMPORAL_IDENTITY_CONFLICT` (`:94-97`, `:115-118`) |
| Translation/similarity evidence S0/S4 (`svm/adapters/observed_translation_motion.py`, `observed_similarity_motion.py`) | options exactly `{temporal_identity_id, inference_ids}` (`:57`, `:78`) | displacement, rotation/scale fit | identity + which inferences | identity/provenance checks (`:92-98`, `:127-133`) |
| Camera hypothesis / consensus (`svm/adapters/camera_consensus.py`) | `anchor_entity_ids` (≥ 2 distinct, `:52-61`) | relative/source/target view transforms per anchor | **which entities are anchors**; agreement policy | measured pairwise limits; disagreement rejects (`spec/57`) |
| Camera compensation (`svm/adapters/camera_compensation.py`) | consensus + target S0/S4; anchor statics | world-relative compensation | anchor/target declarations | static-anchor checks: entity exists, no Track, no animated Group, identity camera (`:464-478`) |
| Motion Target Binding (`svm/adapters/temporal_motion_target_binding.py`) | **exactly `{temporal_identity_id, group_id}`** (`:37-42`) | — | identity → Group target | unique identity, static Group transform (`:45-58`) |
| Track authoring (`geometry_translation_tracks.py`, `observed_rotation_tracks.py`, `observed_scale_tracks.py`, `observed_camera_tracks.py`) | `{motion_target_binding_id, ticks_per_second}` (camera: `{camera_target, ticks_per_second}`) | derived Keyframe transforms | binding id, timebase, base Document Group `transform`/`origin` | identity/baseline/ownership checks |
| POP group candidates (`svm/adapters/pop_group_candidates.py`) | document; 2 Q v0 artifacts; **no options** (`:40-52`) | pairwise hypothesis | — | `SUPPORTED/UNCERTAIN/REJECTED` (`:251-255`) |
| Group promotion (`svm/adapters/pop_group_promotion.py`) | **explicit `candidate_ids`** (`:35-44`) | — | which candidates are promoted | only `SUPPORTED`; stale → `STALE_CANDIDATE` (`:57-70`) |
| D1 bundle / D2 projection | completed D1 bundle | — | — | projection-only (`spec/61`, `spec/62`) |

### 1.2 What is pre-known today

Phase 1 is **told**, explicitly and before any pixels are processed:

- the **frame selection and tick mapping** (`frame_indices`, `ticks`, `ticks_per_second`);
- the **OpenCV threshold / polarity / connectivity**;
- **which component is which role, per tick** — `selectors.json`, consumed via
  `RecoveryConfig.selector(tick, role)` (`svm/recovery_orchestration.py:57-67`,
  `:190-208`), e.g. `{"0": {"entity:target-a": "candidate:component-0004", ...}}`;
- the **role list**: which lineages are anchors and which are targets
  (`anchors`, `targets`, `groups`);
- that the base Document already contains the Entities, the identity Groups
  (with `transform`/`origin`) and an identity Camera;
- which R0 inference candidates are promoted to identity (`inference_ids`);
- which Entity is an anchor for Camera (`anchor_entity_ids`);
- the identity → Group binding (`temporal_identity_id`, `group_id`);
- the timebase and the binding id for authoring.

### 1.3 Where automatic inference currently ends

Automatic, evidence-producing stages already exist and stop at **evidence**:
component enumeration + statistics (analysis), pairwise cross-frame matching (R0),
pairwise similarity/scale/rotation fit (S4), pairwise POP group hypotheses, and
Camera agreement/consensus. None of them *select*, *promote*, *bind* or *author*.

Every **selection / promotion / binding / authoring** step is explicit, closed
world, atomic and fail-closed. There are no placeholders, no nearest/largest
guesses and no silent identity.

### 1.4 The first hard stop

> Give the system a structurally simple short video, but stop telling it who the
> objects are — where does it first get stuck?

It gets stuck **immediately at raster geometry observation**. The analysis stage
already discovers the components and their count automatically
(`candidate:component-%04d`, `opencv_analysis.py:226-238`), but the next stage
cannot proceed without an explicit `component_id` per occurrence
(`raster_geometry_observations.py:38-43`). `RecoveryConfig.selector()` raises
`Missing explicit selector for tick ... role ...` as the very first thing
`recover_role_lineage` needs (`recovery_orchestration.py:60-68`, `:190-208`).

So the first missing authority is not tracking, not camera, not binding — it is:

**"which of the automatically detected components is a subject worth observing at
all?"**

Everything downstream (pairing, matching, promotion, camera, binding, tracks)
requires that a component was first named. Phase 1 answers this question with
`selectors.json`; Phase 2's first slice answers it from evidence.

## 2. Candidate Phase 2 slices

Each candidate adds exactly one primary inference authority.

### Candidate A — Raster Primitive Observation Proposal

- **Input**: an already-accepted OpenCV component-analysis artifact, its accepted
  source canonical PNG and binary mask, and one accepted video-frame manifest
  artifact with exactly one matching occurrence. No `component_id`, no free
  `tick`.
- **New inference authority**: deciding which automatically detected components
  are candidate primitive observations (subject candidacy / eligibility).
- **Output**: an observation-proposal evidence artifact listing an evaluation for
  every component, plus candidates for the non-rejected ones. No cross-frame
  identity.
- **Status**: `SUPPORTED` / `UNCERTAIN` / `REJECTED` (see `spec/64` §3).
- **Provenance**: manifest id, occurrence id, frame index, tick, source timestamp,
  source PNG id, analysis id, mask id, component id + digest, recorded analysis
  options, tolerance, policy identity, adapter identity/version.
- **Forbidden side effects**: no Entity, no Track, no Group, no identity, no
  Document geometry/Render Stack change.
- **Fixture difficulty**: **low** — deterministic pixels, exact numeric
  assertions, no model output.
- **Generalization gain**: **high for the first step** — removes the per-tick
  per-role component selection entirely; the system finds subjects itself.
- **Coupling risk**: **low–medium** — must not modify the frozen eligibility code
  in `contour_landmarks`; the classification must reuse the same constants and be
  asserted parity-equal to the frozen contract.

### Candidate B — Temporal Identity Proposal

- **Input**: a set of accepted observations across several frames, without a
  pre-declared correspondence or frame pairing.
- **New inference authority**: grouping observations across frames into
  identities (multi-frame grouping, and possibly transitivity).
- **Output**: identity candidates with status; promotion still explicit.
- **Status**: reuse R0's `SUPPORTED/UNCERTAIN/REJECTED` vocabulary per pair, plus
  an aggregation rule for groups.
- **Provenance**: R0 evidence ids, observation ids, frames/ticks.
- **Forbidden side effects**: no Tracks, no binding, no Entity.
- **Fixture difficulty**: **medium–high** — needs multi-frame ambiguity,
  permutation and transitivity cases.
- **Generalization gain**: high, but it is a *second* gate; it does not unblock
  anything until subjects are first observed.
- **Coupling risk**: **high** — the frozen R0 already emits matching *evidence*;
  B would add a new selection/aggregation authority over it and risks implying
  identity. It also needs frame pairing that Phase 1 deliberately leaves explicit.

### Candidate C — Anchor / Camera Reference Proposal

- **Input**: accepted observations (already selected) over several frames.
- **New inference authority**: proposing which observed lineages are candidate
  static/background anchors.
- **Output**: anchor candidates with status; Camera consensus/compensation remain
  explicit and downstream.
- **Status**: `SUPPORTED/UNCERTAIN/REJECTED` over stationarity/agreement.
- **Provenance**: observation ids, S0/S4 evidence ids, ticks.
- **Forbidden side effects**: no Camera Track, no consensus mutation, no
  compensation.
- **Fixture difficulty**: **medium** (needs a moving-subject counterexample and a
  partially-moving candidate).
- **Generalization gain**: medium — removes `anchor_entity_ids`, but only after
  observations and identity already exist.
- **Coupling risk**: **medium–high** — touches the Camera path that
  `spec/57` freezes with strict tolerances.

Repository evidence also shows that a **group-candidate** slice is *not*
available as new work: conservative, abstaining group inference already exists
(`spec/28`, `svm/adapters/pop_group_candidates.py`) with explicit promotion
(`pop_group_promotion.py`). That authority is already spent.

## 3. Chosen P2A

**P2A = Candidate A, Raster Primitive Observation Proposal.**

Selection rationale (maximum useful generalization, minimum new semantic
authority):

1. It removes the **first and most artificial** precondition — the hand-authored
   per-tick per-role `component_id` selection — and does so without introducing
   identity, tracking, camera, binding or authoring.
2. It is the **smallest** authority: a deterministic eligibility classification
   over data the system already computes. It cannot silently assign identity
   because it never compares two frames.
3. It fits the required pipeline exactly: `Evidence -> Candidate -> Proposal ->
   explicit acceptance`.
4. It has the **lowest coupling risk**: it consumes the analysis artifact and adds
   a new evidence artifact; it does not touch R0/R1, S0/S4, Camera, Binding,
   authoring, `MotionEvaluator` or `SVGRenderer`.
5. It is cheaply and exactly testable (deterministic pixels, numeric assertions).

It deliberately does not: complete video recovery, solve
segmentation + identity + tracking together, create semantic Entities, author
Tracks, mutate Render Stack, infer hierarchy, treat match failure as deletion, or
rewrite Phase 1 evidence.

## 4. P2A contract

The detailed normative contract — eligibility parity, the frame-level flat/solid
precondition, the fixed reason taxonomy, evaluation/candidate identity,
deterministic reasons and numeric bytes, manifest authority, acceptance-time
manifest verification closure, policy action, revision staleness, the Golden
fixture and Golden acceptance requirements, and the closed scope — is specified in:

`spec/64-p2a-raster-primitive-observation-proposal.md`

Summary: P2A consumes one accepted component-analysis artifact, its accepted
source canonical PNG and binary mask, and one accepted video-frame manifest whose
single matching occurrence supplies the timing. It emits one evidence artifact
containing a deterministic evaluation for every detected component and candidates
for the non-rejected ones, crosses the ordinary `Proposal -> ProposalAcceptor ->
RevisionStore` boundary, and appends evidence only. It never creates an Entity,
Group, Track or identity, never compares frames, and never modifies Phase 1.

## 5. Phase 2 boundary

Any new inference capability beyond the frozen Phase 1 contracts belongs to
Phase 2 and must be introduced through new evidence/provider/acceptance
boundaries rather than silently extending Phase 1 adapters. This charter selects
one such boundary (P2A, detailed in `spec/64`) and designs no further Phase 2
architecture.
