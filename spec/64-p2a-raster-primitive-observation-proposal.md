# P2A — Raster Primitive Observation Proposal (normative contract)

Status: normative contract for Phase 2 slice P2A. Evidence-only; it adds no
Entity, Track, Group, identity, Camera or binding authority. Phase 1 remains
FINAL / FROZEN (`spec/62-phase1-final-freeze.md`).

Charter and slice selection: `spec/63-phase2-charter.md`. This document is the
detailed normative contract for the slice chosen there.

## Conformance status

The P2A implementation, Golden fixtures and focused tests conform to this
contract. Candidate/evaluation identities use full SHA-256 and bind the complete
§6 occurrence authority, reasons and verification references use their normative
orders, and the primary Golden fixture is the three-component 320×240 scene
defined in §10.

## 1. Eligibility parity with the frozen Phase 1 contract

P2A must not modify, weaken or reinterpret the frozen Phase 1 code:

- `svm/adapters/raster_geometry_observations.py` (in particular
  `contour_landmarks()` and `CONTOUR_TOLERANCE`).

Parity is defined as:

- **SUPPORTED** iff the frozen contour eligibility would succeed;
- **UNCERTAIN** iff every earlier eligibility condition holds and the minimum
  polygon edge is ≥ 8 px, but the frozen `contour_landmarks()` ultimately rejects
  *only* because of the longest-edge margin (`≤ 4 px`);
- **REJECTED** otherwise.

P2A may re-measure the same contour / topology / area / canonical-polygon / edge
quantities in its own new module to produce diagnostic reason codes, but it must
not modify or change frozen Phase 1 behaviour.

The reason codes are a **Phase 2 diagnostic classification**. They do not claim
that Phase 1 originally exposed these fine-grained error semantics.

## 2. Frame-level flat/solid precondition

The frozen flat-background / solid-foreground checks are a **frame-level
occurrence precondition**, not a per-component property.

P2A v0.1 therefore requires: if the source raster does not satisfy the frozen
flat-background / solid-foreground controlled-raster precondition, then

- the **entire** P2A inference fails closed;
- no evidence artifact is produced;
- no evaluation is produced;
- no candidate is produced;
- the Document and Revision count do not change.

`NON_FLAT_SOLID_RASTER` is **not** a component reason code and must not appear in
the component reason taxonomy. A focused adversarial case must verify this
whole-inference abort.

## 3. Fixed component diagnostic reason taxonomy

Components are evaluated in the canonical component order already produced by
component-analysis v0.2. The reason code set is fixed and ordered:

```text
NO_CONTOUR
HAS_HOLE
MULTIPLE_CONTOURS
DEGENERATE_CONTOUR
AREA_BELOW_256
CANONICALIZATION_FAILED
VERTEX_COUNT_OUT_OF_RANGE
MIN_EDGE_BELOW_8
```

`AMBIGUOUS_LANDMARK_ORIGIN` is the **only** reason for `UNCERTAIN`, and is
emitted after the set above (a component that is `UNCERTAIN` has no other
reason).

Rules:

- The normative order above is fixed. If several measurable conditions fail,
  reasons are output in exactly this order.
- Reasons are an **ordered list**, never a set.
- If an earlier failure makes a later measurement impossible to compute safely,
  the later reason must **not** be fabricated. In particular, a
  `CANONICALIZATION_FAILED` does not also imply `VERTEX_COUNT_OUT_OF_RANGE`, and
  the edge measurements remain undefined.
- Silent omission of a component is forbidden.

Topology distinctions:

- zero contour → `NO_CONTOUR`;
- the hierarchy contains a child/parent hole relationship → `HAS_HOLE`;
- more than one outer contour that is not a hole relationship →
  `MULTIPLE_CONTOURS`;
- zero / non-finite / non-usable contour area → `DEGENERATE_CONTOUR`;
- a positive area below 256 → `AREA_BELOW_256`;
- any polygon canonicalization or geometry-backend failure →
  `CANONICALIZATION_FAILED`.

If a detected component cannot form a complete deterministic evaluation, the
entire inference fails closed — unless that failure is already represented as a
`REJECTED` component by the fixed reasons above.

## 4. Evaluation identity vs candidate identity

Every detected component receives a deterministic `evaluation_id`. Only the
`SUPPORTED` and `UNCERTAIN` components receive a `candidate_id`.

- `REJECTED` components keep their evaluation, have **no** `candidate_id`, are
  absent from `proposed_candidates`, and downstream consumers must never treat an
  `evaluation_id` as a `candidate_id`.
- The absence of a `candidate_id` is expressed as JSON `null` (fixed choice, not
  an omitted field).

Namespaces use the full SHA-256, 64 lowercase hexadecimal characters:

```text
candidate:primitive-observation:<64 hex sha256>
evaluation:primitive-observation:<64 hex sha256>
```

The suffix is the complete SHA-256 of `canonical_bytes(...)`. Undefined-length
"sha256-prefix" is not permitted.

## 5. Deterministic reasons and numeric bytes

- `reasons` is an ordered list, never a set, using the fixed order in §3.
- All identity hash inputs are canonicalized with `canonical_bytes`.
- All numeric values must be finite. Floating-point measurements use the
  repository's existing canonical numeric convention (`_canonical_number` in
  `svm/adapters/opencv_analysis.py`).
- `NaN` and `Infinity` are never permitted.
- A boolean is never accepted where an integer is required.
- `contour_tolerance_pixels` is the frozen constant `1.0`
  (`svm/adapters/raster_geometry_observations.py:26`), not a request option.
- P2A v0.1 has **no** caller-configurable inference options.

## 6. Manifest authority semantics

No repository-global uniqueness is required. The P2A request explicitly selects
**one exact accepted video-frame manifest** as the inference authority for this
proposal.

The tick is not independently supplied. Candidate and evaluation identity bind:

- manifest artifact id;
- occurrence id;
- frame index;
- tick;
- source timestamp;
- source PNG artifact id.

The tick is read from the selected manifest's occurrence, never passed in
separately. Multiple different accepted manifests may give the same PNG
different legitimate temporal meanings; they produce different P2A identities
because the manifest id / occurrence differ. This is not a free tick.

## 7. Acceptance-time manifest verification closure

Acceptance must not merely trust a propose-time `verify_video_manifest` call. The
new Change must carry enough references that the artifact verifier can re-run the
existing `verify_video_manifest` authority at the acceptance boundary.

The verification dependency closure includes at least:

- the P2A evidence artifact;
- the selected video-frame manifest artifact;
- the manifest's source video artifact;
- every unique canonical raster artifact referenced by the manifest;
- the selected OpenCV analysis artifact;
- the selected binary mask artifact.

If the analysis source PNG is already in the raster closure, it is not duplicated.

`references` / `required_artifact_ids` must be deterministic, free of duplicates,
and match exactly the existing `ProposalAcceptor` artifact-set contract.

The reference ordering is fixed:

1. evidence;
2. manifest;
3. source video;
4. the manifest occurrence raster references, in manifest occurrence order,
   deduplicated by first occurrence;
5. analysis;
6. mask.

The acceptance verifier must:

- rebuild a read-only resolver/store from the resolved verification closure;
- call the existing `verify_video_manifest`;
- re-verify the OpenCV analysis + mask derivation against the source PNG;
- re-derive the P2A payload;
- require the evidence canonical bytes to match exactly.

`Change.apply` finally appends **only** the P2A evidence reference.
Verification-only references must not be automatically appended to the Document.
The `ProposalAcceptor` verifier signature must not be modified.

## 8. Policy action

P2A v0.1 explicitly reuses the existing `attach_analysis` Change Authority action
/ intent. No new policy action is introduced and the frozen policy vocabulary is
not modified.

`attach_analysis` here means "append a verified analysis/evidence reference"; it
does not assert that P2A is the Phase 1 OpenCV analysis.

## 9. Revision staleness

- Phase 1 implementation and contracts are not modified.
- P2A does not mutate existing evidence bytes.
- Accepting P2A creates a new Revision and appends evidence to the Document
  references.
- Any existing candidate bound to an older Revision / whole-Document hash may
  become STALE under the existing stale semantics. This is existing Revision
  behaviour, not a Phase 1 regression.
- Phase 1 hash semantics must not be changed in order to keep old candidates
  valid.

An integration acceptance case must verify: an existing revision-bound candidate,
then accept P2A, then the old candidate may become STALE according to the
existing rules. Only existing behaviour is verified; it is not modified.

## 10. Golden P2A fixture

Deterministic fixture (proposed `examples/040-raster-primitive-observation-proposal`).

PNG: 320 × 240, 8-bit grayscale, background 255, foreground 0, `LINE_8`. It
contains exactly **three** real pixel components, in canonical component order:

| # | Role | Vertices | Expected |
| --- | --- | --- | --- |
| A | SUPPORTED | `(30,30) (100,30) (80,70) (30,70)` | area 2390.0, 4 vertices, min edge 40, longest-edge margin 20 → `SUPPORTED` |
| B | UNCERTAIN | `(30,120) (30,180) (50,120)` | area 600.0, 3 vertices, min edge 20, longest-edge margin ≈ 3.24555320 → `UNCERTAIN`, reason `AMBIGUOUS_LANDMARK_ORIGIN` |
| C | REJECTED | `(30,210) (46,210) (30,226)` | area 128.0, 3 vertices, min edge 16, longest-edge margin ≈ 6.627417 → `REJECTED`, reason `AREA_BELOW_256` |

Component B must not violate any other rejection condition. The canonical
component order is SUPPORTED, UNCERTAIN, REJECTED.

Video: a 2-frame FFV1 AVI, 320 × 240, fps `1/1`.

- frame 0: blank white;
- frame 1: the three-component scene.

Sampling: `frame_indices = (1,)`, `ticks_per_second = 12`. The selected
occurrence is `frame_index = 1`, `tick = 12`, `source_timestamp = [1, 1]`.

Adversarial lineage cases are independent tamper variants, **not** a fourth pixel
component. The charter's earlier "exactly four components" wording is superseded:
the fixture has exactly three components.

The independent `repeated.avi` adversarial fixture contains the same scene in both
frames. Sampling `(0, 1)` proves duplicate matching occurrences fail closed;
sampling either frame separately provides two valid manifest authorities with
different occurrence timing for identity-binding coverage.

## 11. Golden acceptance requirements

At minimum:

- exactly 3 evaluation entries;
- statuses exactly `SUPPORTED` / `UNCERTAIN` / `REJECTED`;
- only the first two have a non-null `candidate_id`;
- `proposed_candidates` contains exactly the first two;
- the rejected evaluation remains auditable in the evidence;
- deterministic full 64-hex ids;
- exact manifest occurrence provenance (`occurrence_id`, `frame_index`, `tick`);
- a frame-level flat/solid failure aborts the whole inference;
- zero manifest match rejects;
- duplicate matching occurrence rejects;
- a tampered manifest rejects;
- a forged analysis rejects;
- a forged mask rejects;
- a malformed / non-finite payload rejects;
- a stale base rejects through ordinary acceptance;
- acceptance failure leaves HEAD / Revision count / Document unchanged;
- P2A acceptance may stale older revision-bound evidence according to existing
  semantics.

## 12. Closed scope

P2A remains evidence-only and must not:

- create an Entity;
- create a Group;
- author a Track;
- infer identity;
- compare frames;
- infer Camera;
- bind a Motion Target;
- change the Render Stack;
- promote a component;
- modify a Phase 1 adapter or Phase 1 evidence bytes.

Acceptance may only append verified P2A evidence.
