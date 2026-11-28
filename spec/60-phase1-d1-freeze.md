# Phase 1 / D1 Freeze — Controlled Video -> Editable SVM

Status: freeze record. This document states what the Phase 1 demonstrator (D1)
has actually proven and what it deliberately has not. It introduces no new
semantics, changes no frozen contract and narrows nothing that existing specs
guarantee.

Governing specs: `spec/55` (S10D sparse observations), `spec/57` (S11B Camera),
`spec/58` (S11C multi-object recovery), `spec/59` (S11D video ingestion). The
frozen S11A/S11B/S11C adapters and their policies are unchanged.

Baselines:

- Frozen baseline: `ceac6dc540b26e4dac64b4a31da230982c1cc4d2`.
- Pre-hardening baseline (parity reference): `2e6a458`, before the D1 output
  safety contract was added in `ceac6dc`.

D1 is a packaging and orchestration slice. `svm/recovery_orchestration.py` and
`svm/phase1_demo.py` sequence existing production adapters; they own no
inference (no role discovery, component association, camera estimation or raster
tracking). Explicit component selectors, anchor/target identities and Motion
Target Bindings are configuration inputs, exactly as in the frozen path.

## Proven end-to-end capability

```text
real AVI/FFV1
-> deterministic video frame ingestion (S11D)
-> explicit raster observations (S11A)
-> temporal identity evidence (R0 -> explicit R1)
-> observed translation / similarity evidence (S0 / raster S4)
-> multi-anchor Camera consensus (S11B measured policy)
-> camera compensation
-> explicit Motion Target Binding
-> ordinary editable SVM Tracks (12 Tracks, one Document)
-> Revision / Transaction Keyframe edit (SetKeyframeValueChange)
-> MotionEvaluator
-> SVG re-render
```

Every stage above is an already-frozen contract exercised through the ordinary
Proposal / Change Authority / Revision path. The demonstrator adds only the
declared configuration, the sequencing, the bundle and the report.

## D1 demonstrator guarantees

The D1 demonstrator (`svm demo-phase1`) guarantees, for the controlled fixture
and its recorded configuration, all of the following. Each is enforced at run
time and asserted by the acceptance tests; the command fails closed if any is
false.

- **Real checked-in AVI/FFV1 input.** The recovery input is the checked-in
  `examples/038-controlled-video-ingestion/scene.avi` bytes. No video is
  generated, re-encoded or synthesized at run time.
- **No Ground Truth runtime dependency.** The demo reads neither
  `ground-truth.json` nor `verification.json`. Numerical Ground Truth remains a
  post-hoc acceptance fixture only.
- **Deterministic frame mapping.** Source indices `0,1,2,3` map to ticks
  `0,12,24,36` at 12 ticks/second through exact integer timing, with the verified
  manifest joining each canonical PNG Artifact ID to its Video occurrence.
- **Ordinary SVM Document output.** Recovery yields one ordinary Document; no
  demo-only Track format, field or Change authority exists.
- **Exactly 12 Tracks for the controlled fixture.** Target A, Target B and the
  Camera each own four Tracks (`translate.x`, `translate.y`, `rotation_degrees`,
  `scale` for targets; `position.x`, `position.y`, `rotation_degrees`, `scale`
  for the Camera), each with Keyframes at ticks 0, 12, 24 and 36.
- **Recovered and edited Documents remain normal editable SVM documents.**
  Serialization, validation and evaluation use the existing v0.1 path.
- **One explicit edit only affects its intended Target/tick.** The edited state
  is a child Revision produced by one atomic `Transaction` containing one
  `SetKeyframeValueChange` (Target A `rotation_degrees`, tick 12, +5.0). No JSON
  is mutated directly.
- **Target B remains unchanged.** Target B group transforms are identical
  across recovered and edited states at every tick.
- **Camera remains unchanged.** Camera presentation state is identical across
  recovered and edited states at every tick, and the edited Target's other Track
  properties are unchanged.
- **Deterministic evidence bundle.** Running the same command twice from the
  same repository state produces byte-identical output for all 18 declared
  bundle files, including the report. No wall-clock time, temporary path, random
  filename or random ID is recorded.
- **Safe staged publication / rollback.** All recovery, editing, rendering,
  validation and writes complete in a private staging directory before
  publication. Publication renames through a private backup; a failed publish
  restores the previous output, and a failed rollback retains the original
  bundle instead of deleting it. Protected paths, links and reparse points fail
  closed.
- **Parity locked against the pre-hardening baseline.** The recovered and edited
  Document digests are recorded from `2e6a458` and must remain unchanged through
  the `ceac6dc` hardening. `tests/test_phase1_demo.py` asserts, after normalizing
  OS text newlines only:

  ```text
  recovered.svm.json  e18a3af9054161a3c72b021df2e81522bde428543425dd256944b469bf42484a
  edited.svm.json     53871073fbf8507c52861731e4b2b812e471472027f613beef5493dc815343e1
  ```

## D1 non-claims

D1 does not prove, and must not be described as proving, any of the following:

- arbitrary natural video;
- automatic object discovery;
- unrestricted tracking;
- occlusion handling;
- scene cuts;
- arbitrary topology changes;
- semantic object understanding;
- automatic hierarchy inference;
- general camera estimation;
- unconstrained video vectorization.

The demo is **controlled video input only**. Roles, component selectors, anchor
identities and Target bindings are explicit configuration. The accepted video
subset is one complete RIFF AVI container (at most 32 MiB) with a single FFV1
stream, exact integer timing, no audio and no dropped frames; decoding fails
closed with no backend fallback. Byte-exact decode is expected only with the
pinned `opencv-python-headless` wheel, and the runtime gates on the required
decoder capability rather than a version string. The command reads repository
fixtures and therefore runs from a source checkout.

## Evidence

- `tests/test_phase1_demo.py` — the documented command's production entry point,
  the 12-Track result, ordinary serialization, the single-target edit, Target B
  and Camera invariance, Ground Truth independence, byte-identical repeated
  execution, explicit replacement, and the full publication/rollback contract.
  The recovered/edited digests above are the parity lock.
- `tests/test_video_recovery.py` — real-container input through the frozen
  orchestration with PNG and Ground Truth reads forbidden during recovery,
  plus the complete input-bundle lineage.
- `tests/test_video_ingestion.py` — container/codec subset, exact timing,
  canonical frames and provenance verification.
- `tests/test_multi_object_raster_recovery.py` — the underlying S11C recovery
  accuracy limits that D1 reuses unchanged.
- `examples/039-controlled-video-editable-svm/README.md` — the demonstration,
  bundle layout, recovered Track values and the explicit edit.
- `examples/038-controlled-video-ingestion/README.md` — AVI fixture provenance
  and canonical frame digests.

## Freeze decision and change control

Phase 1 / D1 is frozen at the declared baseline. After this freeze:

- the frozen recovery adapters, their policies and tolerances, and the D1
  orchestrator/demonstrator semantics must not change silently;
- any change to recovered or edited output must be an explicitly versioned
  slice with updated specifications, fixtures and tests, and must not weaken the
  parity lock or the stated limits;
- packaging and presentation work belongs to D2 (`spec/61`), which is a
  projection of D1 evidence and must not widen or reinterpret these claims.