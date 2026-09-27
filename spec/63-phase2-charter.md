# Phase 2 Charter — First Inference Slice (P2A)

Status: P2A v0.1 implemented under the contract below. P2B and subsequent slices
remain planning only. This does not modify any frozen Phase 1 contract. Phase 1 remains
FINAL / FROZEN (`spec/62-phase1-final-freeze.md`, implementation baseline
`0caae5b8061bfd12901bdb0898f171d4ad5d48a4`).

The purpose of this charter is to pick exactly one first Phase 2 slice (P2A) that
adds the **minimum new inference authority** while removing the **single most
artificial Phase 1 precondition**, and to specify it precisely enough to
implement as an independent evidence-only adapter.

Implementation: `svm/adapters/raster_primitive_observation_proposal.py`, with
focused Golden coverage in `tests/test_raster_primitive_observation_proposal.py`.
The checked-in `examples/040-raster-primitive-observation-proposal/scene.avi`
is a 240×180 grayscale AVI/FFV1 with two identical frames at 1 fps. Selecting
frame 1 gives one supported asymmetric triangle, one uncertain square, a rejected
holed component and a rejected small component. Selecting both frames proves
the required duplicate-occurrence rejection. Forged lineage is tested separately;
it aborts the whole proposal rather than becoming a component classification.
The request supplies only the accepted analysis and manifest IDs, with no options.
PNG, mask, source video and all manifest-selected frames must have exact accepted
references, so acceptance can reproduce both the analysis and the full manifest.

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

- **Input**: an already-accepted OpenCV component-analysis artifact, its accepted
  source canonical PNG and binary mask, and one accepted video-frame manifest
  artifact with exactly one matching occurrence. No `component_id`, no free
  `tick`.
- **New inference authority**: deciding which automatically detected components
  are candidate primitive observations (subject candidacy / eligibility).
- **Output**: an observation-proposal evidence artifact listing candidate
  primitive observations, each with a deterministic candidate id, measurements
  and status. No cross-frame identity.
- **Status**: `SUPPORTED` = satisfies every frozen observation-eligibility
  condition; `UNCERTAIN` = topology/area/vertex-count are valid and the
  minimum edge is ≥ 8 px, but the longest-edge margin is ≤ 4 px; `REJECTED` =
  every other failed eligibility condition (holes, multiple contours, degenerate,
  area < 256, canonicalization failure, vertex count outside 3..32, minimum edge
  < 8 px).
- **Provenance**: manifest id, occurrence id, frame index, tick, source PNG id,
  analysis id, mask id, component id + digest, recorded analysis options,
  tolerance, policy identity, adapter identity/version.
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

- one accepted OpenCV component-analysis artifact (already produced by the frozen
  `OpenCVAnalysisAdapter`);
- that analysis's accepted source canonical PNG artifact
  (`analysis.source_artifact_id`) and its accepted binary-mask artifact;
- one accepted video-frame manifest artifact whose occurrence lineage verifies
  under the existing video ingestion authority.

The request selects that one exact accepted manifest as the authority for this
inference. P2A does not scan other accepted manifests and defines no repository-
global uniqueness rule. If another valid accepted manifest gives the same PNG a
different temporal meaning, using it is a separate inference authority and its
different manifest/occurrence lineage produces different identities.

P2A v0.1 does **not** accept a free, unverifiable `tick`. The tick is obtained
from the manifest occurrence, never supplied independently:

- the manifest must already be accepted;
- exactly one manifest occurrence must satisfy
  `occurrence["raster_artifact_id"] == analysis.source_artifact_id`; zero or more
  than one matching occurrence fails closed;
- the manifest/source lineage must reproduce under the existing
  `verify_video_manifest` authority (`svm/video_ingestion.py:301-331`), including
  canonical bytes, provenance and canonical frame bytes;
- `occurrence_id`, `frame_index`, `source_timestamp` and `tick` are read from that
  verified occurrence.

If the analysis source PNG is not derived from an accepted, verifying video-frame
manifest, P2A v0.1 fails closed. P2A v0.1 defines no generic still-image time
semantics; that remains out of scope for this version.

### Forbidden input authority

To prove generalization, P2A must **not** be given: any `component_id` or
`selectors.json`; any role / anchor / target / object count; any correspondence,
pairing or identity; any Camera, binding, Group or Track information; any Ground
Truth; or any independently supplied `tick`. The subject set and the timing both
come from evidence alone.

### Output

A single accepted evidence artifact containing, for the frame:

- an **ordered evaluation entry for every component** reported by the accepted
  OpenCV analysis, in the canonical component ordering already produced by
  component-analysis v0.2. Each entry binds the original `component_id`, its
  `component_digest`, a deterministic evaluation identity, the exact measured
  eligibility values, the status, the reason code(s) and provenance;
- `proposed_candidates`: exactly the `SUPPORTED` and `UNCERTAIN` evaluation
  entries. A `REJECTED` component is never a proposal candidate and can never be
  promoted;
- the counts per status and the exact policy/adapter identity.

Rejection is never expressed by silently omitting a component. Every detected
component is represented, and `REJECTED` entries remain in the evidence artifact
for auditability.

No Entity, Track, Group, identity, Document geometry or Render Stack entry is
created or changed.

### Identity

Candidate observation identity is deterministic, content-addressed and
path-free:

```text
candidate:primitive-observation:<32 lowercase hex>

where the suffix is the SHA-256 prefix of canonical bytes of {
  policy_identity, adapter_id, adapter_version,
  manifest_artifact_id, occurrence_id, frame_index, tick,
  source_png_artifact_id, analysis_artifact_id, binary_mask_artifact_id,
  component_id, component_digest, contour_tolerance_pixels
}
```

The suffix is exactly the first 32 lowercase hexadecimal characters of SHA-256
over `canonical_bytes` of that mapping (128 identifier bits). Evaluation ids use
the same fixed-width suffix over those inputs plus status and ordered reason
codes:

```text
evaluation:primitive-observation:<32 lowercase hex>
```

Every detected component also receives a deterministic evaluation identity over
the same inputs plus its status and reason codes, so `REJECTED` entries are
auditable and stable too. Equivalent recorded inputs produce identical ids; a
different occurrence, frame, component, digest, status or policy produces a
different id. No filesystem path participates.

### Provenance

Every evaluation entry, including rejected ones, binds: the accepted manifest
artifact id; `occurrence_id`, `frame_index`, `tick` and `source_timestamp` read
from the verified occurrence; the source PNG artifact id
(`analysis.source_artifact_id`, equal to the occurrence `raster_artifact_id`), the
analysis artifact id and the binary-mask artifact id; `component_id` and
`component_digest`; the analysis options (`threshold`/`foreground`/`connectivity`)
exactly as recorded in the accepted analysis; `contour_tolerance_pixels`; the
policy identity; and the adapter identity/version. Provenance contains no role, no
identity, no pairing, no Camera and no filesystem path.

### Status

P2A v0.1 introduces no new distance threshold. The eligibility constants are
exactly the frozen controlled raster geometry constants
(`svm/adapters/raster_geometry_observations.py:277-295`).

Before component evaluation begins, the source frame must satisfy the frozen
flat-background / solid-foreground controlled-raster precondition. Failure aborts
the entire derivation: no evidence, evaluations or candidates are produced. This
is a frame-level input precondition, not a component rejection reason.

- **SUPPORTED** — satisfies the complete frozen controlled raster geometry
  eligibility contract: exactly one hole-free nondegenerate contour; contour area
  ≥ 256; simplified vertex count 3..32; minimum polygon edge ≥ 8 px;
  longest-edge margin > 4 px.
- **UNCERTAIN** — contour topology, area and vertex count are valid, and the
  minimum polygon edge is ≥ 8 px, but the longest-edge margin
  is ≤ 4 px. The primitive geometry is plausible, but the frozen canonical
  landmark-origin choice is ambiguous. Such a component is proposed as uncertain,
  never silently dropped, and cannot be promoted without explicit review.
- **REJECTED** — every other failed eligibility condition, including: no contour
  or multiple contours; a hole; a degenerate or zero-area contour; area < 256;
  canonicalization failure; vertex count outside 3..32; or minimum polygon edge
  < 8 px.

Reason codes are an enumerable, fixed set — not free text — so Golden assertions
are exact:

```text
NO_CONTOUR                   -> REJECTED
MULTIPLE_CONTOURS            -> REJECTED
HAS_HOLE                     -> REJECTED
DEGENERATE_CONTOUR           -> REJECTED
AREA_BELOW_256               -> REJECTED
CANONICALIZATION_FAILED      -> REJECTED
VERTEX_COUNT_OUT_OF_RANGE    -> REJECTED
MIN_EDGE_BELOW_8             -> REJECTED
AMBIGUOUS_LANDMARK_ORIGIN    -> UNCERTAIN
```

Reason lists use the order shown above, with
`AMBIGUOUS_LANDMARK_ORIGIN` last when applicable. When an earlier failure makes a
later measurement undefined, the later consequence reason is not manufactured.
In particular, `CANONICALIZATION_FAILED` does not also imply
`VERTEX_COUNT_OUT_OF_RANGE`, and edge measurements remain undefined.

### Acceptance

`ProposalAcceptor` may attach the proposal as evidence through a new registered
Change (proposed `AttachRasterPrimitiveObservationProposalChange`) that appends
references and the evidence artifact to a new Revision. Acceptance may only add
evidence. It must reproduce and verify the exact candidate bytes, provenance,
statuses and identities from the accepted analysis lineage; any mismatch, missing
dependency, stale base or forged policy rejects the whole transaction atomically.

Acceptance creates a new Revision and appends only the P2A evidence reference. It
does not alter Phase 1 code or evidence bytes. An existing candidate bound to an
older Revision or whole-Document hash may become `STALE` under the existing
Revision semantics; P2A does not promise that such older candidates remain valid,
and does not change Phase 1 hashing or promotion semantics.

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

A minimal deterministic fixture (`examples/040-...`) is a 240×180, two-identical-
frame AVI/FFV1 at 1 fps. Golden sampling selects frame index 1 at 12 ticks per
second, giving `frame_index = 1`, `tick = 12` and `source_timestamp = [1, 1]`.
Its canonical opaque grayscale PNG frame, accepted component-analysis, accepted
mask and accepted manifest contain exactly four pixel components:

1. **SUPPORTED** — a solid asymmetric polygon meeting every eligibility condition
   → exactly one `SUPPORTED` evaluation with exact ordered landmarks and no reason
   code.
2. **UNCERTAIN** — a solid polygon whose longest-edge margin is ≤ 4 px while every
   other condition holds → exactly one `UNCERTAIN` evaluation with reason code
   `AMBIGUOUS_LANDMARK_ORIGIN`.
3. **REJECTED** — a component with a hole → a retained `REJECTED` evaluation with
   `HAS_HOLE`.
4. **REJECTED** — a component with area < 256 → a retained `REJECTED` evaluation
   with `AREA_BELOW_256`.

Adversarial lineage/manifest cases are independent test variants, not pixel
components: a forged or absent `component_digest`; an analysis artifact whose
bytes do not re-derive from the PNG; an unregistered policy identity; a manifest
occurrence whose `raster_artifact_id` does not equal the analysis
`source_artifact_id` (or matches more than one occurrence); or a forged occurrence
tick inside a manifest whose canonical bytes/provenance do not verify. The
proposal fails closed, attaches no evidence, leaves HEAD/Document/Revision count
unchanged, and creates no candidate. Selecting both identical frames with
`frame_indices = (0, 1)` is one such variant: the same canonical PNG matches two
distinct occurrences, so P2A fails closed.

Assertions are exact and machine-checkable:

- the exact evaluation count — every detected component is represented;
- exact status counts: one `SUPPORTED`, one `UNCERTAIN`, two `REJECTED`;
- the exact status and reason code(s) for every component;
- the rejected component is still present in the evaluation evidence;
- `proposed_candidates` equals exactly the SUPPORTED and UNCERTAIN entries and
  excludes `REJECTED`;
- each deterministic evaluation/candidate id (recomputed twice and compared);
- the exact `occurrence_id`, `frame_index` and `tick` provenance read from the
  manifest;
- atomic rejection of every adversarial case.

No visual judgement, no randomness, no natural video.

**Removed manual authority vs Phase 1**: the fixture supplies **no
`selectors.json`** — no per-tick, per-role `component_id` mapping, no role,
anchor or target list — and no independently supplied tick. Phase 1 required a
human to name which component was the subject at each tick; Golden P2A requires
the system to propose the subject observations from the frame and its analysis
alone, with timing taken from the verified manifest occurrence.

## 6. P2A completion definition

P2A is complete when:

- a normative spec defines the adapter, policy/schema/media identities, input and
  forbidden-input authority, output, status semantics, provenance and acceptance,
  and the forbidden effects above;
- candidate evidence and candidate identity are deterministic and
  content-addressed (equivalent inputs → identical ids; repeated runs →
  byte-identical output);
- every detected component is represented by an evaluation entry, with `REJECTED`
  entries retained for audit and `proposed_candidates` limited to `SUPPORTED` and
  `UNCERTAIN`;
- provenance binds the exact source artifacts, the verified manifest occurrence
  (`occurrence_id`, `frame_index`, `tick`, `source_timestamp`), the component,
  analysis options, policy and adapter version, with no filesystem paths;
- the tick comes only from a verified manifest occurrence, and a non-verifying or
  ambiguous occurrence fails closed;
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
