# Multi-Anchor Camera Consensus v0 (S10C)

Status: normative evidence-of-evidence extension.

## Frozen contracts and shared boundary

S9B's `ObservedCameraSimilarityAdapter`, `svm-observed-camera-similarity-0.1`,
and `svm-static-anchor-camera-similarity@0.1` remain single-anchor contracts.
S10B occurrence identity, S0 bounds-center displacement, S4 similarity, and
`svm-geometry-correct-translation-authoring@0.1` mathematics remain unchanged.

The governing boundaries are INV-PROP-001/002, INV-TXN-001, INV-REF-001, and
INV-TIME-010: external evidence is content-addressed, proposals are previewable,
acceptance is atomic, and Camera remains an outer world-to-view transform.

The single-anchor-specific payload fields are `anchor_entity_id`,
`source_similarity_artifact_id`, and each interval's
`source_similarity_interval_id`. Their provenance identifies one S4 lineage.
Compensation previously selected exactly the single-anchor Camera media type;
the Camera authoring reader and geometry-translation source reader did likewise.

The minimal shared boundary is `read_camera_evidence` / `one_camera_evidence`:
accepted single-anchor or consensus evidence yields the existing Camera interval
fields. The original single-anchor reader is retained. No Camera matrices are
converted into a new convention and no compensation or decomposition math is
duplicated.

## Consensus input and identity

`MultiAnchorCameraConsensusAdapter` requires explicit `anchor_entity_ids` and
one already accepted single-anchor Camera Artifact per selected Entity. At least
two distinct anchors and evidence IDs are required. Duplicates reject; no input
is silently deduplicated. The exact source set must match the selected anchors.

Each hypothesis retains its independent S4 and geometry lineage. The adapter
resolves those accepted dependencies and reuses the existing single-anchor
verifier to reproduce the original Camera evidence. It does not estimate Camera
motion again from raw observations or copy one anchor's hypothesis to another.

Anchors are sorted lexicographically by Entity ID; evidence IDs and provenance
are ordered by their corresponding anchor. Dependencies are sorted by Artifact
ID. The sorted first hypothesis is the canonical representative, independent of
caller ordering. Source Revision remains part of evidence identity, as in S9B.
Equivalent hypotheses at the same Recovery Revision produce identical evidence,
interval IDs, Proposal content, provenance, and downstream Track IDs.

## Strict agreement

All hypotheses must cover exactly the same ordered, contiguous tick chain.
Identity/hold intervals are legal. There is no resampling or partial coverage.
Each source is a verified positive-scale uniform similarity with an identity
initial Camera baseline under the existing S9C validation contract.

For every interval and all six coefficients of each matrix:

* `relative_view_transform`
* `source_view_transform`
* `target_view_transform`

the maximum minus minimum across hypotheses MUST be at most `1e-8` (absolute;
no relative tolerance). This tiny, versioned bound accommodates deterministic
SVG/S4 rounding. It is not a noisy-input fitting threshold. Agreement across all
hypotheses is required, not merely agreement with one favored input.

After verification, copy the canonical representative's matrices exactly.
Do not average, vote, weight, remove an outlier, or otherwise fit a new matrix.
Any disagreement rejects before importing a consensus output Artifact. Rejecting
preserves the meaning that every explicitly selected anchor supports the result.

## New evidence contract

Media type: `application/vnd.svm.camera-consensus+json;version=0.1`

Schema: `svm-camera-consensus-0.1`

Identity: `svm-camera-consensus@0.1`

Policy: `svm-strict-multi-anchor-camera-consensus@0.1`

Canonical payload fields:

* `schema_version`, `identity`, `policy_identity`, `source_revision_id`;
* `anchor_entity_ids` and corresponding `source_camera_evidence_artifact_ids`;
* `supporting_hypotheses`: ordered `{anchor_entity_id, camera_evidence_artifact_id}`;
* `representative`: the first supporting hypothesis;
* `agreement_absolute_tolerance`: exactly `1e-8`;
* `intervals`: ticks, the three verified matrices, ordered supporting Camera
  interval IDs, supporting hypotheses, policy, and deterministic interval ID.

Interval IDs use `camera-consensus-interval:` plus SHA-256 of the canonical
interval content excluding its ID. Artifact identity uses the existing store.
The consensus payload has no singular `anchor_entity_id` pretending to represent
all anchors. Each supporting hypothesis explicitly retains its own singular ID.

Provenance records the adapter/version, policy, full ordered anchor list,
supporting hypotheses, and source Camera evidence IDs. Each source leads to its
S4 and geometry references. Acceptance rederives exact content and provenance;
unknown policy, forged lists, matrices, interval IDs, tolerance, representative,
source evidence, or conflicting/duplicated references reject atomically.

## Current Document and authority

Both proposal generation and Change application check every selected anchor with
S9B's `_static_anchor`: Entity exists, has no Entity Track, and belongs to no
Group with a Track. The identity static Camera baseline restriction remains.
The Change also captures exact Entities, Groups, animation, and presentation;
changed state rejects. Base Revision conflict checks remain in ProposalAcceptor.

`AttachMultiAnchorCameraEvidenceChange` is registered only for evidence attachment
(`attach_camera_compensation`). It can attach consensus or its verified compensated
evidence. It cannot create or modify Tracks, Entities, Groups, or Camera state.
Its declared source references must already be accepted. No generic unregistered
Change crosses the acceptance boundary.

## Downstream use

`CameraCompensatedMotionAdapter` retains the legacy singular `anchor_entity_id`
input for single-anchor evidence. Its explicit consensus input uses
`anchor_entity_ids` plus the target Temporal Identity. Those selections must match
the consensus exactly. Both modes use the same `_compensated_payloads()` and
existing output schemas/policy; the three source Artifact IDs identify the exact
Camera evidence contract. The plural Change checks every anchor again.

`ObservedCameraTracksAdapter` accepts the new versioned evidence through the
shared reader, retains explicit `camera_target = presentation`, and uses the same
sample recovery, four-property CREATE transaction, Track IDs, and authoring
policy. Proposal generation and the registered Track verification Change check
all consensus anchors are still static. This also rejects attempts to animate
an anchor earlier in the same transaction. Single-anchor payloads, errors, and
authoring semantics retain their existing path.

Geometry-correct Group authoring uses the shared Camera reader when resolving
compensated similarity's source evidence. Its baseline accumulation, world
compensation and fixed-origin decomposition are unchanged. Rotation and scale
authoring consume the same existing compensated outputs. Explicit target binding
and Proposal acceptance remain required.

## Executable proof and limits

`examples/033-multi-anchor-camera-consensus` contains two distinct asymmetric
static anchors at separated locations, a moving target, Camera pan+rotation+zoom,
and hold intervals at ticks 0, 12, 24, 36. Frozen identical SVG pairs retain one
Blob ID and use the S10B occurrence producer. Recovery reads frozen SVG bytes,
ticks, Recovery Document and explicit selections. Ground Truth is used only to
generate the snapshots and assert final values/geometry.

`tests/test_camera_consensus.py` checks both input orders, exact representative
selection, all four Group and Camera Tracks, and reobserved geometry for both
anchors and the target at every tick, within the existing `3e-8` fixture bound.
It covers duplicate/single/wrong anchors, duplicate evidence and two evidences for
one anchor, mismatched chains, disagreement, source and output forgery, stale
state, current anchor motion, preview isolation and atomic failure.

The static-anchor subset is unchanged; this is not a broader proof of arbitrary
construction or hierarchy stationarity. Strict consensus cannot resolve moving
anchors, missing intervals, uncertain matches, partial visibility or occlusion.
No anchor discovery, outlier rejection, confidence weighting, fitting, raster,
optical flow, Track replacement or Camera replacement is introduced. S10D remains
separate work.
