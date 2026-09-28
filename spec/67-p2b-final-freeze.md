# P2B — Final Freeze

Status: **FINAL / FROZEN**. Documentation and status record only. It adds no
semantics, changes no contract, modifies no implementation, test or fixture, and
begins no further Phase 2 slice.

Phase 1 remains FINAL / FROZEN (`spec/62-phase1-final-freeze.md`); P2A remains
FINAL / FROZEN (`spec/65-p2a-final-freeze.md`).

## Frozen baseline

```text
c3f46cec21ea67726f427921e3f970f2548e03ad
```

Normative contract: `spec/66-p2b-primitive-observation-assembly.md`.
Charter: `spec/63-phase2-charter.md`.

P2B lineage: `1cfc515` defined the contract; `c3f46ce` implements it (adapter,
registered Change, fixture, focused tests). The baseline is the implementation
commit above; a later documentation-only commit, including this freeze record,
is not part of the implementation baseline.

## Frozen capability

```text
accepted P2A evidence A
+ accepted P2A evidence B
from the same manifest
-> deterministic assembly
-> svm-primitive-observations-0.2
-> frozen R0 consumes unchanged
```

P2B removes per-frame caller-supplied component selection and manual observation
assembly.

Residual authority remains: the caller chooses **which two accepted P2A frame
evidences** form the interval. That frame-pair choice is not removed by P2B.

## Frozen semantics

- Exactly two P2A evidence artifacts are consumed.
- Both must come from the same exact accepted manifest / source-video authority.
- Distinct occurrences with strictly increasing `occurrence_id`, `frame_index`
  and `tick`.
- Only `SUPPORTED` evaluations materialize.
- `UNCERTAIN` / `REJECTED` remain audit-only and are never materialized.
- Zero `SUPPORTED` in either frame fails the whole assembly closed.
- Every `SUPPORTED` evaluation materializes exactly once.
- No best-match; no deduplication; multiplicity is preserved.
- The canonical P2A evaluation order is preserved.
- `bounds` / `fill` / landmarks are re-derived from the verified lineage, not
  trusted from the caller.
- Observation identity is `observation:p2b:<64 lowercase hex sha256>`.
- The observation Artifact is imported as kind `REFERENCE`.
- The assembly evidence Artifact is imported as kind `DERIVED`.
- Acceptance re-derives the exact observation and assembly evidence bytes.
- Only the produced outputs are appended to the Document.
- The existing `attach_analysis` authority is reused; no new policy action.

## No temporal inference

P2B explicitly does not know: correspondence, match / unmatched, identity,
deletion, appearance / disappearance, occlusion, split / merge, temporal
aggregation, Camera, Group, Track, or role.

A primitive that appears in only one frame means only that the primitive exists
in that frame. Nothing more is inferred.

## Golden / acceptance

Fixture `examples/041-primitive-observation-assembly/` contains two checked-in
AVI fixtures:

- `scene.avi` — a 320 × 240 FFV1 source; P2B is evaluated with sampling frame
  indices `(1, 2)` at 12 ticks/second, i.e. ticks 12 and 24;
- `zero-supported.avi` — a second source whose selected frame has zero
  `SUPPORTED` evaluations.

Actual `scene.avi` content, decoded read-only (each frame has four components):

| component | frame 1 bounds | size | area | notes |
| --- | --- | --- | --- | --- |
| `candidate:component-0001` | `[30, 30, 101, 71]` | 71 × 41 | 2491 | `SUPPORTED` |
| `candidate:component-0002` | `[150, 30, 221, 71]` | 71 × 41 | 2491 | `SUPPORTED`, identical digest to 0001 |
| `candidate:component-0003` | `[30, 120, 51, 181]` | 21 × 61 | 671 | `UNCERTAIN` |
| `candidate:component-0004` | `[30, 210, 47, 227]` | 17 × 17 | 153 | `REJECTED` (`AREA_BELOW_256`) |

In frame 2 the first `SUPPORTED` component is translated by `+10` in x
(`[40, 30, 111, 71]`); the others are unchanged. Both `SUPPORTED` components have
fill `#000000`.

**Identical-looking multiplicity is actually verified.** In every selected frame
the two `SUPPORTED` primitives are visually identical — same bounds size
(71 × 41), same `pixel_area` (2491) and the **same `component_digest`**
(`sha256:5e3d87feb568f55e14b…`), differing only by a 120 px x translation. The
focused test asserts both materialize (`len(primitives) == 2`), with distinct
`observation:p2b:` ids, so no silent deduplication occurs.

Focused coverage (`tests/test_primitive_observation_assembly.py`, 8 tests):

- `test_happy_path_preserves_supported_order_multiplicity_and_audit` — order,
  multiplicity, audit inclusion / exclusion, fills, observation ids, canvas and
  ticks;
- `test_acceptance_appends_only_outputs_and_r0_consumes_observation` —
  acceptance appends only the two outputs, and the frozen
  `TemporalCorrespondenceAdapter` accepts the observation artifact unchanged;
- `test_reference_order_and_request_authority` — exact reference ordering, and
  rejection of a duplicated or reversed evidence selection (`fails_atomically`);
- `test_different_manifest_and_stale_proposal_reject` — cross-manifest and stale
  proposal rejection;
- `test_zero_supported_frame_rejects_whole_assembly` — the `zero-supported.avi`
  source fails the whole assembly closed;
- `test_forged_p2a_candidate_landmarks_and_malformed_values_reject_at_acceptance`
  — forged `candidate_id`, forged landmarks, `NaN`, and malformed JSON;
- `test_forged_analysis_bounds_reject_at_acceptance` — forged analysis bounds;
- `test_tampered_outputs_wrong_policy_and_missing_dependency_reject_atomically` —
  tampered observation fill, tampered evidence payload, wrong policy, forged
  raster provenance, and a missing accepted dependency.

All rejections assert atomicity (`fails_atomically` compares HEAD, revision
count and Document). No coverage is claimed beyond these tests.

**R0 compatibility:** the produced `svm-primitive-observations-0.2` Artifact is
kind `REFERENCE` and is accepted by the frozen `TemporalCorrespondenceAdapter`
unchanged; this is asserted in the focused tests.

**CI matrix:** `.github/workflows/ci.yml` defines the quality matrix as Windows
(`windows-latest`) and Ubuntu (`ubuntu-latest`) on Python `3.11` and `3.12`, and
runs `ruff format --check .`, `ruff check .`, `pyright`, the controlled AVI/FFV1
ingestion test, the full `unittest` suite and CLI smoke tests. The freeze premise
for `c3f46ce` is that this matrix is green — **CI PASS** (taken from the
established premise; the remote run was not observed from this workspace).

## Frozen non-goals

P2B does not do, and must not be described as doing: correspondence;
match / unmatched; identity; deletion; appearance / disappearance; occlusion;
split / merge; temporal aggregation; Camera; Group; Track; or role inference.

## Phase boundary

Any future change that introduces cross-frame primitive comparison, matching,
mutual-best, identity aggregation or lifecycle inference does **not** reopen
P2B. It belongs to P2C or later, introduced through a new
evidence/provider/acceptance boundary.

P2B may only reopen for a demonstrated bug.

The next remaining semantic authority after P2B is temporal
correspondence / identity proposal work. It is not designed here.

## Change control

P2B is FINAL / FROZEN at the baseline above. After this freeze, the P2B adapter,
policy / schema / media identities, the `observation:p2b:` identity rule, the
same-manifest interval rule, the zero-`SUPPORTED` rule, the inclusion / exclusion
behaviour and the audit provenance must not change silently. Any change to P2B
output must be an explicitly versioned slice with updated specifications,
fixtures and tests.