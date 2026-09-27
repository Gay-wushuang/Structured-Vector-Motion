# P2B — Primitive Observation Assembly (normative contract)

Status: normative contract for Phase 2 slice P2B. Evidence-only; it adds no
correspondence, identity, tracking, Entity, Group, Track, Camera or binding
authority. Phase 1 remains FINAL / FROZEN (`spec/62-phase1-final-freeze.md`) and
P2A remains FINAL / FROZEN (`spec/65-p2a-final-freeze.md`).

P2B is the slice named Primitive Observation Assembly. It is **not** Temporal
Identity Proposal and **not** Camera Reference Proposal.

## 1. Purpose

P2A already turns one accepted frame into candidate evidence:

```text
single accepted frame
-> automatic component enumeration
-> SUPPORTED / UNCERTAIN / REJECTED
-> candidate evidence
```

The downstream frozen R0 (`svm/adapters/temporal_correspondence.py`) consumes a
`svm-primitive-observations-0.2` Artifact. In Phase 1 that Artifact still depends
on explicit occurrences, a caller-supplied `component_id`, an explicit tick, and
`selectors.json` role selection.

P2B has exactly one goal:

```text
accepted P2A evidence for two occurrences
-> deterministic primitive observation assembly
-> existing svm-primitive-observations-0.2
```

so that the frozen R0 can be presented with genuine multi-primitive frames without
any per-tick component selector.

P2B does not solve correspondence or identity.

## 2. Authority boundary

P2B v0.1 may know:

- exactly two accepted P2A evidence artifacts;
- each P2A evidence's exact verified manifest occurrence;
- the accepted P2A verification closure: manifest, source video, canonical
  raster, analysis, mask;
- the P2A evaluation status;
- the P2A `candidate_id`;
- the P2A `ordered_landmarks` for `SUPPORTED` evaluations;
- the canonical analysis component ordering.

The P2B caller may choose only **which two accepted P2A evidence artifacts form
this observation interval**. That is the residual frame-pair authority.

The P2B caller must **not** provide: `component_id`, `observation_id`, `tick`,
`frame_index`, `bounds`, `fill`, landmarks, source/target primitive pairing, role,
Entity, Group, temporal identity, anchor / target, Camera, Track, or Ground
Truth. Tick, frame index and provenance must come from the P2A evidence lineage.

## 3. Same-video / interval lineage

P2B v0.1 is deliberately conservative. The two P2A evidence artifacts must come
from:

- the same exact accepted video-frame manifest;
- therefore the same source video authority;
- two distinct manifest occurrences;
- strictly increasing `frame_index`;
- strictly increasing `tick`.

Forbidden: cross-manifest assembly, cross-video assembly, duplicate occurrence,
duplicate tick, and the same frame represented through aliases.

Rationale: P2B is assembly only. It must not manufacture an interval by letting
the caller pick different time authorities. Supporting cross-manifest assembly
later is a new slice / contract extension, not a P2B option.

## 4. Which evaluations become primitives

P2B v0.1 materializes a primitive **only** for P2A evaluations whose
`status == "SUPPORTED"`.

- `UNCERTAIN` evaluations must not be materialized; P2B must not synthesize
  landmarks for them; they remain auditable in the assembly evidence.
- `REJECTED` evaluations must not be materialized; they remain auditable.

P2B must never select a "best" candidate, deduplicate visually identical
primitives, require uniqueness, or compare primitives across frames. Every
`SUPPORTED` evaluation in each selected frame becomes exactly one primitive, and
multiplicity is preserved.

## 5. Zero-SUPPORTED behavior

If **either** selected frame contains zero `SUPPORTED` evaluations, the entire
P2B proposal fails closed:

- no observation artifact;
- no assembly evidence;
- no Revision change.

R0 requires meaningful two-frame primitive input, and v0.1 must not silently
introduce an empty-frame lifecycle meaning. Zero `SUPPORTED` must not be
interpreted as deletion, disappearance, occlusion, or an empty scene. It only
means P2B abstains.

## 6. Re-derive primitive fields

P2B must not trust caller-supplied geometry. For every `SUPPORTED` evaluation:

- `component_id` and `component_digest` come from the verified P2A evidence;
- the accepted analysis + PNG + mask lineage is re-opened and re-verified;
- `bounds` is taken from the exact matching accepted analysis component (the
  half-open `[x, y, x + width, y + height]` bounds);
- `fill` is derived from the canonical raster / component mask using the existing
  controlled-raster convention (flat solid foreground → one gray value →
  `#RRGGBB`, exactly as the frozen raster producer does);
- `ordered_landmarks` must equal the `SUPPORTED` P2A evaluation's verified
  landmarks;
- `primitive_type` must use the existing frozen controlled-raster primitive type
  `controlled-raster-polygon@0.1`
  (`svm/adapters/raster_geometry_observations.py:25`);
- `rotation_symmetry` must use the exact value the existing
  `svm-primitive-observations-0.2` raster contract expects — `"none"` — derived
  from the frozen producer semantics, not invented.

`fill` must be the six-digit hex `#RRGGBB` the frozen R0 validator requires.

P2B must not modify `svm/adapters/raster_geometry_observations.py`. Its output
must be accepted by the existing frozen `read_primitive_observations` / R0 path
without changing R0.

## 7. observation_id

The caller cannot supply `observation_id`. P2B defines a new deterministic
observation identity derived from:

- the P2B policy / adapter identity;
- the selected P2A evidence artifact id;
- the P2A `candidate_id`;
- the manifest artifact id;
- the occurrence id;
- the frame index;
- the tick;
- the `component_digest`.

Format:

```text
observation:p2b:<64 lowercase hex sha256>
```

The suffix is the complete SHA-256 of `canonical_bytes(...)` over the inputs
above. The `observation:` prefix and in-artifact uniqueness are required by the
frozen R0 validator (`temporal_correspondence.py:180-186`), and this format
satisfies both. If the frozen observation schema required a stricter namespace,
the minimum compatible deterministic format would be chosen and documented
exactly; no such stricter requirement exists.

Identity must **not** be based only on `candidate:component-%04d`, because the
component ordinal can reorder between frames. Filesystem paths, Python object
ids, random UUIDs and wall-clock time are forbidden.

## 8. Output artifacts

P2B produces two artifacts.

**A. One ordinary existing `svm-primitive-observations-0.2` Artifact** that R0
consumes unchanged:

```text
{
  "schema_version": "svm-primitive-observations-0.2",
  "canvas": [width, height],
  "frames": [
    {"tick": <tick>, "primitives": [<primitive>, ...]},
    {"tick": <tick>, "primitives": [<primitive>, ...]}
  ]
}
```

It is canonical JSON, media type
`application/vnd.svm.primitive-observations+json;version=0.2`, and kind
`REFERENCE` so the frozen R0 `resolve_as(..., kind=REFERENCE, ...)` accepts it.
Each primitive carries exactly `{observation_id, primitive_type, bounds, fill,
geometry}` for v0.2.

**B. One new P2B assembly evidence Artifact** carrying provenance and audit
information that does not belong in the frozen observation schema:

- adapter id `adapter:primitive-observation-assembly`, adapter version `0.1`;
- policy identity `svm-primitive-observation-assembly@0.1`;
- schema `svm-primitive-observation-assembly-0.1`;
- media `application/vnd.svm.primitive-observation-assembly+json;version=0.1`.

A companion evidence artifact is **required**: the frozen v0.2 primitive field
set is exactly `{observation_id, primitive_type, bounds, fill, geometry}`
(`temporal_correspondence.py:169-178`), so the observation schema has no
normative place for status/reason audit, manifest/occurrence provenance, or the
excluded sets. The frozen schema must not be extended just for audit fields.

The assembly evidence records:

- the exact two P2A evidence artifact ids;
- the exact manifest artifact id;
- occurrences / ticks / frame indices;
- the produced observation artifact id;
- per-frame included `SUPPORTED` evaluation ids and candidate ids;
- per-frame excluded `UNCERTAIN` / `REJECTED` evaluation ids with statuses and
  reason codes;
- deterministic counts;
- policy / adapter identity.

## 9. Proposal / acceptance

P2B uses the normal `Proposal -> ProposalAcceptor -> Revision` path and defines
one new registered Change, `AttachPrimitiveObservationAssemblyChange`.

The acceptance verifier must re-derive:

- both P2A evidences and the required accepted closure;
- the same-manifest / distinct-occurrence interval;
- the exact `SUPPORTED` inclusion set;
- the exact excluded audit set;
- `bounds` / `fill` / landmarks;
- the deterministic observation ids;
- the exact primitive observation artifact bytes;
- the exact assembly evidence bytes.

Any missing, stale, forged or tampered dependency fails closed atomically.

`Change.apply` appends the minimum references needed so the frozen R0 can consume
the produced observation. Because R0 requires the primitive-observation artifact
to be an accepted `REFERENCE`, it is appended explicitly. The P2B assembly
evidence is also appended for auditability. Verification-only dependencies are not
automatically appended.

P2B reuses the existing `attach_analysis` policy action. No new policy action is
added.

## 10. Existing schema compatibility

P2B must not modify `temporal_correspondence.py`, `read_primitive_observations`,
`raster_geometry_observations.py`, P2A, R1, S0 / S4, Camera, binding, tracks,
`ProposalAcceptor`, or the policy vocabulary.

Completion requires that the frozen R0 consumes the produced observation
artifact unchanged. This compatibility is a primary acceptance criterion.

## 11. P2B does not compare frames

This is the most important semantic boundary. P2B must not compute: centroid
distance across frames, shape similarity across frames, color similarity across
frames, mutual best, correspondence score, identity probability, temporal
aggregation, or transitivity. It only assembles two frames.

All pairwise comparison remains frozen R0 authority. P2B therefore cannot output
`SUPPORTED match` / `UNCERTAIN match` / `REJECTED match`; those belong downstream.

## 12. Match failure is impossible at P2B

P2B has no concept of match, unmatched, deletion, appearance / disappearance,
occlusion, split, or merge. A component present in only one frame is simply a
primitive in that frame; nothing more is inferred.

## 13. Golden P2B

Deterministic fixture `examples/041-primitive-observation-assembly/`, using one
source AVI and one manifest:

- 320 × 240, FFV1, fps `1/1`, `ticks_per_second = 12`, 3 frames;
- frame 0: blank / setup;
- frame 1: a controlled multi-component scene;
- frame 2: the same controlled scene with at least one `SUPPORTED` component
  translated by a fixed integer amount.

P2A evidences are selected for frame 1 → tick 12 and frame 2 → tick 24. Each
selected frame must contain at least one `SUPPORTED` evaluation.

Golden assertions:

- exactly 2 frames in the observation artifact;
- ticks 12 / 24;
- the primitives in each frame equal exactly all `SUPPORTED` P2A evaluations;
- canonical primitive ordering is deterministic;
- `bounds` / `fill` / landmarks are exact;
- full deterministic observation ids;
- `UNCERTAIN` / `REJECTED` are absent from primitives;
- `UNCERTAIN` / `REJECTED` are present in the assembly audit;
- identical-looking `SUPPORTED` primitives are not deduplicated;
- repeated derivation is byte-identical;
- the frozen R0 accepts the observation artifact unchanged.

A specific R0 identity result must not be required as part of P2B correctness,
except as a compatibility smoke test. P2B Golden proves assembly, not
correspondence.

## 14. Adversarial cases

At minimum:

- P2A evidence from different manifests → fail closed;
- the same occurrence twice → fail closed;
- duplicate / non-increasing tick → fail closed;
- zero `SUPPORTED` in either frame → fail closed;
- forged P2A evidence `candidate_id` → fail closed;
- forged P2A landmarks → fail closed;
- forged analysis bounds → fail closed;
- forged raster / fill → fail closed;
- a missing accepted dependency → fail closed;
- a stale proposal → fail closed;
- a malformed / non-finite payload → fail closed;
- a policy mismatch → fail closed;
- atomic rejection leaves HEAD / Revision count / Document unchanged.

Also: two identical `SUPPORTED` primitives in one frame must produce two distinct
primitives, with no silent deduplication.

## 15. Completion definition

P2B is complete when:

- a normative spec exists;
- input and forbidden authority are frozen;
- the same-manifest interval rule is frozen;
- the zero-`SUPPORTED` behavior is frozen;
- deterministic observation identity is frozen;
- exact inclusion / exclusion behavior is frozen;
- audit provenance is frozen;
- the Proposal / Accept verifier is defined;
- the Golden fixture is deterministic;
- the adversarial cases are defined;
- the frozen R0 consumes the output unchanged;
- no Phase 1 / P2A regression;
- no temporal comparison is added.

## 16. Phase boundary

After P2B, the next remaining semantic authority is expected to be Temporal
Identity Proposal / correspondence aggregation, but it is not designed here.

P2B does not remove frame-pair selection. P2B removes per-frame manual component
selection and observation assembly. Any attempt to infer which primitive
corresponds to which belongs to the later slice.