# Phase 2 Charter — First Inference Slice (P2A)

Status: planning charter only. This document adds no implementation, no tests and
no new inference. It does not modify any frozen Phase 1 contract. Phase 1 remains
FINAL / FROZEN (`spec/62-phase1-final-freeze.md`, implementation baseline
`0caae5b8061bfd12901bdb0898f171d4ad5d48a4`).

The purpose of this charter is to pick exactly one first Phase 2 slice (P2A) that
adds the **minimum new inference authority** while removing the **single most
artificial Phase 1 precondition**, and to specify it precisely enough to
implement later.

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
`selectors.json`; Phase 2's first slice should answer it from evidence.

## 2. Candidate Phase 2 slices

Each candidate adds exactly one primary inference authority.

### Candidate A — Raster Primitive Observation Proposal

- **Input**: an already-accepted OpenCV analysis artifact for one canonical
  frame, its source PNG artifact, and the frame's tick. No `component_id`.
- **New inference authority**: deciding which automatically detected components
  are candidate primitive observations (subject candidacy / eligibility).
- **Output**: an observation-proposal evidence artifact listing candidate
  primitive observations, each with a deterministic candidate id, measurements
  and status. No cross-frame identity.
- **Status**: `SUPPORTED` = satisfies every frozen observation-eligibility
  condition; `UNCERTAIN` = geometrically plausible primitive but a secondary
  condition is near its boundary (ambiguous landmark origin, near-floor edge);
  `REJECTED` = clearly outside the frozen subset (holes, multiple contours,
  degenerate, area < 256, vertex count outside 3–32, non-flat region).
- **Provenance**: source PNG id, analysis id, mask id, component id + digest,
  tick, recorded analysis options, tolerance, policy identity, adapter
  identity/version.
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

Proposed policy/schema identity (new, versioned, not reusing Phase 1 identities):

- adapter id: `adapter:raster-primitive-observation-proposal`
- adapter version: `0.1`
- policy identity: `svm-raster-primitive-observation-proposal@0.1`
- schema: `svm-raster-primitive-observation-proposal-0.1`
- media: `application/vnd.svm.raster-primitive-observation-proposal+json;version=0.1`

### Input authority

The system is allowed to know only:

- one accepted OpenCV analysis artifact (already produced by the frozen
  `OpenCVAnalysisAdapter`) for one canonical PNG frame;
- that analysis's source PNG artifact and binary-mask artifact;
- the integer `tick` of that frame.

### Forbidden input authority

To prove generalization, P2A must **not** be given: any `component_id` or
`selectors.json`; any role / anchor / target / object count; any correspondence,
pairing or identity; any Camera, binding, Group or Track information; any
Ground Truth. The subject set must be derived from evidence alone.

### Output

A single accepted evidence artifact containing, for the frame:

- the ordered list of candidate primitive observations (one per detected
  component that is not `REJECTED`), each with status, measurements and
  provenance;
- the counts per status and the exact policy/adapter identity.

No Entity, Track, Group, identity, Document geometry or Render Stack entry is
created or changed.

### Identity

Candidate observation identity is deterministic, content-addressed and
path-free:

```text
candidate:primitive-observation:<sha256-prefix of canonical bytes of {
  policy_identity, adapter_id, adapter_version,
  source_png_artifact_id, analysis_artifact_id, binary_mask_artifact_id,
  component_id, component_digest, tick, contour_tolerance_pixels
}>
```

Equivalent recorded inputs produce identical candidate IDs; a different frame,
component, digest, tick or policy produces a different ID.

### Provenance

Every candidate binds: source PNG artifact id, analysis artifact id, binary mask
artifact id, `component_id`, `component_digest`, `tick`, the analysis options
(`threshold`/`foreground`/`connectivity`) exactly as recorded in the accepted
analysis, `contour_tolerance_pixels`, the policy identity and the adapter
identity/version. Provenance contains no role, no identity, no pairing, no
Camera and no filesystem path.

### Status

- **SUPPORTED** — satisfies every frozen observation-eligibility condition:
  exactly one hole-free nondegenerate contour, contour area ≥ 256, 3–32
  simplified vertices, minimum polygon edge ≥ 8 px, and longest-edge margin > 4 px
  (unambiguous landmark origin). A SUPPORTED candidate is exactly what the frozen
  `contour_landmarks` contract accepts.
- **UNCERTAIN** — a plausible primitive whose contour topology and area are
  acceptable, but a secondary condition is near its boundary: ambiguous landmark
  origin (longest-edge margin ≤ 4 px) or a near-floor minimum edge. Such a
  component is *proposed as uncertain* rather than silently dropped, and cannot be
  promoted without explicit review.
- **REJECTED** — clearly outside the frozen subset: no contour, multiple
  contours, a hole, degenerate/zero-area contour, area < 256, vertex count outside
  3–32, or a region that is not a flat solid foreground under the recorded
  analysis options.

### Acceptance

`ProposalAcceptor` may attach the proposal as evidence through a new registered
Change (proposed `AttachRasterPrimitiveObservationProposalChange`) that appends
references and the evidence artifact to a new Revision. Acceptance may only add
evidence. It must reproduce and verify the exact candidate bytes, provenance,
statuses and identities from the accepted analysis lineage; any mismatch, missing
dependency, stale base or forged policy rejects the whole transaction atomically.

### Forbidden effects

Explicitly forbidden, at proposal and acceptance time:

- authoring a Track;
- mutating the Render Stack;
- mutating an existing Entity's geometry;
- changing hierarchy;
- silently assigning identity (no cross-frame comparison at all);
- deleting or tombstoning Entities;
- modifying Phase 1 evidence or any accepted Document outside appending this
  evidence reference.

## 5. Golden P2A

A minimal deterministic fixture (`examples/040-...`), one canonical opaque
grayscale PNG frame (plus its accepted analysis and mask), containing exactly four
components:

1. **Clear positive** — a solid asymmetric polygon meeting every condition →
   exactly one `SUPPORTED` candidate with exact ordered landmarks.
2. **Ambiguous** — a solid polygon whose longest-edge margin is ≤ 4 px (or whose
   minimum edge is near 8 px) → exactly one `UNCERTAIN` candidate, with the
   ambiguous measurement recorded.
3. **Rejected** — a component with a hole (or area < 256, or > 32 vertices) →
   `REJECTED`, absent from the proposed list.
4. **Adversarial** — a tampered lineage: a forged/absent `component_digest`, an
   analysis artifact whose bytes do not re-derive from the PNG, an unregistered
   policy identity, a wrong `tick`, or analysis not yet accepted → the proposal
   fails closed, attaches no evidence, leaves HEAD/Document/Revision count
   unchanged, and creates no candidate.

Assertions are exact and machine-checkable: the number of candidates, each
candidate's status, each candidate's deterministic id (recomputed twice and
compared), the recorded measurements, and the atomic rejection of every
adversarial case. No visual judgement, no model randomness, no natural video.

**Removed manual authority vs Phase 1**: the fixture supplies **no
`selectors.json`** — no per-tick, per-role `component_id` mapping, no role,
anchor or target list. Phase 1 required a human to name which component was the
subject at each tick; Golden P2A requires the system to propose the subject
observations from the frame and its analysis alone.

## 6. P2A completion definition

P2A is complete when:

- a normative spec defines the adapter, policy/schema/media identities, input and
  forbidden-input authority, output, status semantics, provenance and acceptance,
  and the forbidden effects above;
- candidate evidence and candidate identity are deterministic and
  content-addressed (equivalent inputs → identical ids; repeated runs →
  byte-identical output);
- provenance binds the exact source artifacts, component, tick, analysis options,
  policy and adapter version, with no filesystem paths;
- behaviour is fail-closed for every doctored, missing, stale or unregistered
  input, with atomic rejection and no partial evidence;
- the change crosses the ordinary `Proposal -> ProposalAcceptor -> RevisionStore`
  boundary and acceptance can only append evidence;
- positive, ambiguous, rejected and adversarial tests all pass and are exactly
  assertable;
- all frozen Phase 1 contracts are untouched — no recovery, identity, camera,
  binding, authoring, `MotionEvaluator` or `SVGRenderer` change — and no Phase 1
  test regresses.

## 7. Phase 2 boundary

Any new inference capability beyond the frozen Phase 1 contracts belongs to
Phase 2 and must be introduced through new evidence/provider/acceptance
boundaries rather than silently extending Phase 1 adapters. This charter selects
one such boundary (P2A) and designs no further Phase 2 architecture.