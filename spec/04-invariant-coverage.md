# SVM v0.1 Invariant Coverage

Status values:

- **covered** — exercised by an automated semantic test;
- **fail-closed** — positive functionality is pending, but unsupported input is
  rejected rather than accepted without enforcement;
- **specified** — normative behavior exists but does not yet have full runtime
  coverage.

| Invariant | Status | Coverage |
| --- | --- | --- |
| INV-ID-001 | covered | Golden A preserves Head identity across geometry reevaluation. |
| INV-ID-002 | covered | Golden A preserves Operation and Output Slot identity. |
| INV-ID-003 | covered | Repeated equivalent evaluation produces the same Value hash. |
| INV-ID-004 | covered | Golden B allocates new Face and Hair Entity IDs. |
| INV-ID-005 | specified | Revision snapshots preserve prior entities; explicit tombstone records are not implemented. |
| INV-EVAL-001 | covered | Evaluation produces new immutable payloads and never mutates inputs. |
| INV-EVAL-002 | covered | Golden A/A.1 cover deterministic context and Quality; Geometry Backend tests cover engine identity in capability evaluation. |
| INV-EVAL-003 | specified | Current operations have no clock, network, UI, or unrecorded randomness access. |
| INV-EVAL-004 | covered | Golden A verifies isolated transitive invalidation. |
| INV-EVAL-005 | covered | Golden A preserves stale output separately; A.1 rejects PREVIEW equivalence for FINAL. |
| INV-EVAL-006 | specified | Runtime has BLOCKED state; explicit failure-chain test remains pending. |
| INV-EVAL-007 | covered | Evaluator runtime is reconstructed from the Document in tests. |
| INV-DOC-001 | covered | Validator requires both versions. |
| INV-DOC-002 | specified | Separate schema and semantics fields are defined. |
| INV-REF-001 | covered | Artifact Store and SVG Import tests verify byte-only SHA-256 identity, resolver verification, and accepted references. |
| INV-REF-002 | covered | Artifact tests keep content identity separate from URI/provenance locators. |
| INV-REF-003 | covered | Golden P snapshots a real stochastic POP continuation before acceptance; Golden Q consumes only its immutable accepted result. |
| INV-REL-001 | covered | Example Documents keep hierarchy, render stack, and stages separate. |
| INV-TIME-001 | covered | Golden M samples content animation without interpreting DAG order as time. |
| INV-TIME-002 | covered | Golden M uses only `animation.content`; construction scheduling remains a separate untouched collection. |
| INV-TIME-003 | covered | Golden M verifies integer Timebase, rational seconds, linear samples, and byte-stable SVG Frames. |
| INV-TIME-004 | covered | Golden M preserves Entity, Operation, Track, and Keyframe IDs across samples and edits. |
| INV-TIME-005 | covered | Golden M edits the middle Keyframe and retains cached neighbor Frames outside the affected tick interval. |
| INV-TIME-006 | covered | Golden M proves a static Operation Value ID and evaluation cache entry are reused at three times. |
| INV-TXN-001 | covered | Golden B verifies atomic success and failure. |
| INV-PROP-001 | covered | Adapter snapshot isolation and explicit acceptance are tested. |
| INV-PROP-002 | covered | Base conflicts plus supported Constraints and Edit Permissions are enforced by acceptance tests. |
| INV-CTRL-001 | covered | Document Schema stores the three control systems separately. |
| INV-CTRL-002 | covered | Actor/action/target deny rules are enforced; unsupported policy definitions fail validation. |

This file must be updated when an invariant gains, loses, or changes executable
coverage. A baseline may contain `specified` entries, but code must not claim
that all normative invariants are fully implemented while they remain.

Additional semantic validation coverage in `tests/test_operations.py` verifies
registered type dispatch, exact input signatures, parameter rules, static and
dynamic output signatures, Value-type compatibility, binding resolution, and
atomic parameter mutation.

`tests/test_path_to_polygon_contract.py` implements Golden D without skips. It
covers SVG-to-CreatePath evidence, deterministic intermediate/final polygon
Values, tolerance-key invalidation, fill rules, self-intersection, explicit
rejections, shared canonicalization, and byte-stable SVG rendering.

`tests/test_component_promotion_adapter.py` implements Golden I. It verifies
that an accepted Derived analysis Artifact can feed a later interpretation
Adapter without reopening raster input, that preview is non-mutating, and that
explicit acceptance atomically creates provenance-linked neutral Entities under
artifact, schema, revision, and permission enforcement.

`tests/test_structural_relations.py` implements Golden J. It covers canonical
evidence-backed `derived-from` and immediate `bounds-contains`, batch/incremental
convergence, relation validation, and orthogonality from hierarchy, Render
Stack, construction, and animation.

`tests/test_motion.py` implements Golden M. It covers integer Timebase, stable
Track/Keyframe identity, exact linear samples, temporal cache invalidation,
cross-time static Value reuse, and checked-in deterministic SVG Frames.

`tests/test_motion_revision.py` implements Golden N. It covers persistent
Keyframe Change authority, atomic Revision creation, revision-local temporal
invalidation, old-snapshot evaluation, shared immutable Values, and Undo.

`tests/test_anchored_regeneration.py` implements Golden O. It covers exact
ChangeAuthority-derived impact, protected and allowlisted targets, non-mutating
pending Proposals, sibling Revision branches, policy composition, malicious
wrapper rejection, atomic failure, identity preservation, and deterministic
Revision content.

`tests/test_pop_structure_adapter.py` implements Golden Q. It covers exact
accepted-POP source reconstruction, deterministic normal/X-Ray renders, full
and visible mask evidence, topmost occlusion attribution and conservation,
non-mutating preview, evidence-only atomic acceptance, and fail-closed source
drift.
