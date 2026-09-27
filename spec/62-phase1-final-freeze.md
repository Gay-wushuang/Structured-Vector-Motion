# Phase 1 — Final Freeze

Status: **FINAL / FROZEN**. This is a documentation and status record. It adds no
semantics, changes no frozen contract, modifies no implementation or test code,
and begins no Phase 2 work.

Phase 1 freezes the controlled, deterministic `real video -> editable SVM ->
static showcase projection` path described by `spec/60` (D1 freeze) and `spec/61`
(D2 specification).

## Frozen implementation baseline

```text
0caae5b8061bfd12901bdb0898f171d4ad5d48a4
```

That commit contains, and is the baseline for, the whole Phase 1 implementation:

- the D1 controlled video -> editable SVM demonstrator
  (`svm/recovery_orchestration.py`, `svm/phase1_demo.py`, `svm demo-phase1`);
- safe, deterministic D1 bundle publication (private staging, rename-based
  publish, rollback);
- the D1 freeze contract (`spec/60-phase1-d1-freeze.md`);
- the corrected D2 specification (`spec/61-d2-showcase-packaging.md`);
- the minimal D2 offline showcase projection
  (`svm/phase1_showcase.py`, `svm showcase-phase1`).

The implementation baseline is the code commit above. Any later
documentation-only commit (including this freeze record) is **not** part of the
implementation baseline and does not change it.

This extends the D1 milestone baseline `ceac6dc540b26e4dac64b4a31da230982c1cc4d2`
recorded in `spec/60`; the D1 contract itself is unchanged.

## Verified Phase 1 pipeline

```text
real AVI / FFV1
-> deterministic frame ingestion
-> explicit raster observations
-> temporal correspondence evidence
-> observed translation / similarity evidence
-> multi-anchor Camera consensus
-> camera compensation
-> explicit Motion Target Binding
-> ordinary editable SVM Tracks
-> recovered SVM Document
-> normal Revision / Transaction Keyframe edit
-> edited SVM Document
-> SVG re-render
-> deterministic D1 evidence bundle
-> static offline D2 showcase projection
```

D2 adds no inference semantics. The governing boundary remains:

> **D2 is a projection of D1 evidence, not a new inference stage.**

## Verification evidence

Phase 1 was verified on the frozen implementation baseline using an isolated
project-local Python environment.

### Focused

| Test module | Result |
| --- | --- |
| `tests.test_phase1_showcase` | 4 tests — PASS |
| `tests.test_phase1_demo` | 13 tests — PASS |

### Full suite

`python -m unittest discover -s tests -v`

- 458 tests
- 0 failures
- 0 errors
- PASS

The full suite was run under an isolated project-local Python environment. No
execution time is part of this contract.

## D1 acceptance (recorded)

The D1 demonstrator is accepted and frozen with the following guarantees, each
enforced at run time and asserted by the acceptance tests:

- real AVI/FFV1 authoritative source (checked-in `scene.avi` bytes);
- deterministic frame ingestion with exact integer timing;
- an 18-file D1 evidence bundle;
- Ground Truth not required at run time;
- 12 ordinary editable Tracks for the frozen controlled fixture;
- recovered and edited SVM Documents;
- the intended Keyframe edit changes only its intended Target/tick;
- the unrelated Target remains unchanged;
- the Camera remains unchanged;
- deterministic output;
- staged publication / rollback safety;
- recovered/edited semantic parity retained across hardening (the `2e6a458`
  digest parity lock in `spec/60`);
- D1 authoritative artifacts remain byte-stable through D2 generation.

This is controlled input only; it is not arbitrary video capability.

## D2 acceptance (recorded)

The D2 showcase projection is accepted and frozen with the following properties:

- a completed D1 bundle alone is sufficient;
- output consists of exactly `index.html`, `showcase.css`, `showcase.js` and
  `projection.json`;
- static and offline;
- no CDN;
- no server;
- no `fetch`/XHR requirement;
- canonical PNG frames provide the browser-visible input preview;
- AVI/FFV1 remains the authoritative source;
- existing recovered/edited SVGs are projected;
- the D1 `report.json` is the semantic authority;
- no recovery invocation;
- no ingestion invocation;
- no renderer invocation;
- no Ground Truth dependency;
- no mutation of D1 artifacts;
- relative artifact references only;
- repeated generation is deterministic.

## Phase 1 non-claims

The final freeze preserves the conservative boundary. Phase 1 does **not**
establish, and must not be described as establishing:

- arbitrary natural-video recovery;
- automatic object discovery;
- unrestricted object tracking;
- robust occlusion handling;
- scene-cut handling;
- arbitrary topology changes;
- semantic object understanding;
- automatic hierarchy inference;
- general camera estimation;
- unconstrained raster-to-vector conversion;
- production-quality video reconstruction.

These exclusions are not weakened by this freeze.

## Phase 2 boundary

Any new inference capability beyond the frozen Phase 1 contracts belongs to
Phase 2 and must be introduced through new evidence/provider/acceptance
boundaries rather than silently extending Phase 1 adapters.

Phase 2 is not designed here.

## Freeze decision and change control

Phase 1 is FINAL / FROZEN at the implementation baseline above. After this
freeze:

- the frozen recovery adapters, their policies and tolerances, the D1
  orchestrator/demonstrator, and the D2 projection must not change silently;
- any change to recovered, edited or projected output must be an explicitly
  versioned slice with updated specifications, fixtures and tests, and must not
  weaken the D1 parity lock, the stated limits, or the Phase 1 non-claims;
- new inference capability must follow the Phase 2 boundary above.