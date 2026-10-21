# T2-P0 — Author-Anchored Group Motion (Method C) Experiment Design

Status: **DESIGN ONLY / NOT IMPLEMENTED / NOT SVM EVIDENCE / NOT FROZEN**.

> **Protocol status (T2-P0A):** the ambiguous parts of this design are frozen by
> [T2-P0A-PROTOCOL-FREEZE.md](T2-P0A-PROTOCOL-FREEZE.md). Where this document and
> the freeze differ, the freeze wins. This document remains design history.

| Field | Value |
| --- | --- |
| Work order | T2-P0 — Group Anchor Experiment Design |
| Repository | `Gay-wushuang/Structured-Vector-Motion` |
| Checked-out HEAD | `24441f1` (`codex/primitive-toolchain`) |
| T1 reference | `40b5f65` — T1.1 canonical snapshot (`GO`) |
| T1 experiment source | `f56cee1` (recorded in the canonical manifest) |
| Date | 2026-10-21 |
| Scope | docs-only; one new file in `research/temporal-geometry-pilot/` |
| Recommendation | **CONDITIONAL GO** for a bounded T2 implementation (see §11) |

---

## 1. Decision summary

T2 studies **Method C: first-frame group geometry propagated by an explicitly
author-supplied anchor set**. Method C is Method B with exactly one added
constraint: the transform used for every member is estimated from one
author-chosen group anchor, not from each member independently.

The design is deliberately narrow:

- one group, `N >= 2` members, four frames, five controlled fixtures;
- the only new author input is **membership + one anchor point set** (both
  explicit, both frame-0, both validated);
- no inferred membership, no automatic anchor selection, no identity, no
  persisted Group, no `TemporalIdentity`, no `ChangeAuthority`, no Core change;
- the only runtime dependency is the existing `analysis` extra (OpenCV), with
  the exact version already pinned by `pyproject.toml`.

The experiment is designed to **falsify** the hypothesis

> On controlled raster footage, one author-anchored group transform produces
> lower temporal jitter, lower cumulative drift, and no more abstention than
> per-member optical-flow propagation (B), without silently producing a wrong
> result when the anchor is unusable or conflicting.

A T2 PASS would be **bounded research evidence**, not SVM Evidence, not proof of
a general method, and not authority for P2D-A/P2D-B, a Group, a Track, or a
TemporalIdentity.

---

## 2. Baseline audit

### 2.1 Repository state at the start of this design

Verified with `git rev-parse`, `git branch --show-current`, `git status
--porcelain=v1`, `git log --oneline`, and `git diff`:

| Fact | Result |
| --- | --- |
| Branch | `codex/primitive-toolchain` |
| HEAD | `24441f1` — `feat: 实现 fogleman/primitive 外部工具链…` |
| Tracked working tree | clean (`git status --porcelain` produced no entries) |
| Commit after T1 | exactly one: `24441f1` on top of `40b5f65` |
| Tracked T1 pilot content | unchanged against `40b5f65` and against `HEAD` |

There are eight unreadable `pip-*` directories in the repository root
(`pip-build-tracker-*`, `pip-ephem-wheel-cache-*`, `pip-install-*`,
`pip-target-*`). They are environment artifacts of a concurrent Python
installation, not experiment inputs. `git status` cannot open them (Windows
permission denied), so they do not appear as untracked entries. They are
**outside the experiment read set** and must not be deleted, moved, or repaired
by T2 work. If they make a future `git status` noisy, that is an environment
issue, not a T2 issue.

### 2.2 T1 canonical snapshot verification

The T1.1 canonical snapshot is committed at `40b5f65`. Three independent checks
were run:

1. `git diff --stat 40b5f65 -- research/temporal-geometry-pilot` — **empty**.
2. `git diff --stat HEAD -- research/temporal-geometry-pilot` — **empty**.
3. SHA-256 of every file listed in
   [`runs/t1-controlled-raster-ab-v1-canonical/canonical-manifest.json`](runs/t1-controlled-raster-ab-v1-canonical/canonical-manifest.json)
   was recomputed and compared with the manifest:

| File | Recomputed SHA-256 | Matches manifest |
| --- | --- | --- |
| `raw/method-a.json` | `0cd54a3c…b78a19aa` | yes |
| `raw/method-b.json` | `72ee8bea…97194ba6` | yes |
| `metrics.json` | `2e51cf62…0601f0af` | yes |
| `costs.json` | `502e5bb6…b8f4aa91` | yes |
| `reproducibility.json` | `e537dcca…de2c0382` | yes |
| `comparison.avi` | `9757c2a7…e1567a1` | yes |
| `run-manifest.json` | `05e2013a…2f07eee` | yes |

Hashes are truncated for display; the manifest carries the full 64-hex values.
The canonical manifest records `worktree_dirty: true` with the note that the only
uncommitted changes were under `svm/` (the primitive-toolchain work-in-progress)
and were outside the experiment's read set. At this design baseline that work is
committed as `24441f1`, and the tracked tree is clean.
The v1 snapshot (`runs/t1-controlled-raster-ab-v1`) is preserved and remains
**CONDITIONAL** (OpenCV 4.10.0); the canonical re-run under 4.14.0.94 is **GO**,
and the manifest records that only the decision fields differ. The snapshot is
untouched; the canonical manifest records that its input/output hash integrity
was re-verified `PASS` during T1.1. `40b5f65` is an ancestor of `HEAD`
(`git merge-base --is-ancestor 40b5f65 HEAD` → yes).

The canonical T1.1 result (declared runtime: Python 3.12.5, NumPy 2.5.4,
OpenCV 4.14.0.94):

| Metric | Method A | Method B |
| --- | ---: | ---: |
| mean IoU | 1.000000 | 0.980505 |
| mean GT vertex RMSE | 0.2524 px | 1.9863 px |
| final GT vertex RMSE | 0.3127 px | 3.7104 px |
| final centroid drift | 0.1212 px | 0.9517 px |
| step-transform jitter (mean) | N/A | 1.5800 |
| abstention rate | 0.0 | 0.0 |
| decision | — | **GO** |

The canonical manifest records `Ran 5 tests in 0.641s OK` for
`python -m unittest discover -s research/temporal-geometry-pilot/tests -v`.
Those tests were not re-executed for this docs-only design; the committed
manifest is the T1 record and the hashes above are byte-level evidence that it
has not changed.

### 2.3 Golden 047 / Spec 83 collision (task item 7)

`24441f1` added:

- [`examples/047-fogleman-primitive-toolchain/`](../../examples/047-fogleman-primitive-toolchain)
- [`spec/83-fogleman-primitive-toolchain.md`](../../spec/83-fogleman-primitive-toolchain.md)

The T1 README (authored before that commit; its header records `e46bd5d` as the
then-checked-out HEAD) still says:

> G4 | Golden 047 + freeze record | **NOT DONE** (no `examples/047-*`)

That statement was true at its authoring baseline but is stale at `HEAD`:
**`examples/047-*` is now occupied by the primitive-toolchain work**. This is a
real naming collision for any future Spec 82 G4 Golden, not a T2 defect.

Consequences for T2:

- T2 is research-only and **adds no Golden**; it never proposes
  `examples/047-*`.
- T2 must not use `spec/83` either; a future T2-adjacent normative spec, if
  separately authorized, starts at `spec/84`.
- A future Spec 82 G4 Golden starts at `examples/048-*` unless the
  primitive-toolchain example is deliberately renamed by its owner; T2 does not
  touch it.
- The stale T1 README line is left unchanged: T1 is a recorded baseline, and
  editing its historical statement would weaken the audit trail.

### 2.4 What this design does not change

- No `svm/`, `schema/`, `spec/`, `examples/`, `.github/`, or `demo/` change.
- No change to the T1 `experiment.json`, `run_experiment.py`, tests, or any file
  under `runs/`.
- No change to any tracked file other than adding this document.
- No new `ChangeAuthority` registration, no transaction, no Revision, no
  Document field, no schema version.

### 2.5 AGENTS.md constraints applied

`AGENTS.md` is unchanged at `HEAD` and governs this design:

- The v0.1 core loop remains the priority; T2 is research and claims nothing
  about the interchange contract, Document semantics, or a production renderer.
- Do not add PySide6, diffvg, AI models, video tooling, or research repositories
  to prove core behavior. T2 adds no dependency beyond the existing `analysis`
  extra (OpenCV) and no external model, GPU, or checkpoint.
- External optimizers and AI adapters produce Proposals, never accepted
  Documents. T2 produces no Proposal and no Document change at all.
- Structural operations that create semantic objects must allocate new Entity
  IDs; automatic identity is forbidden. T2 creates no Entity, Group, Track,
  Binding, or Identity and fixes `identity_claim: none`.
- If code and an invariant disagree, the invariant wins. T2 touches no
  invariant-bearing code.
- Scope discipline: no speculative abstraction. T2 is a bounded experiment on
  five fixtures and may legitimately end in STOP.

---

## 3. T1 harness facts T2 reuses

T2 is an **isolated extension**: it reuses T1's conventions and, read-only, its
helper code, but it does not modify T1 and does not call T1's single-primitive
loader or output format.

### 3.1 T1 protocol and schemas

| Item | T1 value |
| --- | --- |
| Config schema | `temporal-geometry-ab-experiment-config-0.1` |
| Raw output schema | `temporal-geometry-ab-experiment-output-0.1` |
| Metrics schema | `temporal-geometry-ab-metrics-0.1` |
| Manifest schema | `temporal-geometry-ab-run-manifest-0.1` |
| Reproducibility schema | `temporal-geometry-ab-reproducibility-0.1` |
| Classification | `experimental-only-not-svm-evidence` |
| Runner identity | `svm-research/temporal-geometry-ab@0.1` |
| Fixture | `examples/035-controlled-raster-recovery` |
| Frames | `tick_000`, `tick_012`, `tick_024`, `tick_036` (512×512) |
| Evaluation window | frame indices 0–3, drift reference frame 0 |

### 3.2 The experimental geometry format

A T1 raw method output is a single ordered polygon per frame, not an SVM
Document and not an SVM observation envelope:

```json
{
  "schema_version": "temporal-geometry-ab-experiment-output-0.1",
  "artifact_classification": "experimental-only-not-svm-evidence",
  "method": "B-first-frame-primitive-opencv-lk-propagation",
  "identity_metrics_applicability": "diagnostic-only",
  "frames": [
    {
      "frame_index": 0,
      "tick": 0,
      "status": "SUPPORTED",
      "primitive_id": "experimental-propagated-primitive:0",
      "points": [[170.0, 150.0], [300.0, 155.0], [325.0, 220.0], [230.0, 285.0], [160.0, 230.0]],
      "flow": null
    }
  ]
}
```

On B transitions, `flow` is an object with `valid_track_count`,
`valid_track_ratio`, `inlier_count`, `median_lk_error`,
`median_affine_residual_px`, and `step_affine`.

Key properties, all of which T2 keeps:

- `points` is an **ordered vertex list in pixels**; it is not an Entity, Group,
  Track, or Identity.
- `status` is `SUPPORTED` or `ABSTAINED`; abstention carries a stable `reason`.
- `flow` is optional diagnostic data, present on B transitions.
- `step_affine` is the 2×3 similarity-affine matrix for that transition
  (`[[a, b, tx], [c, d, ty]]`); it is diagnostic, not accepted geometry.
- The whole artifact is explicitly classified as non-SVM-evidence.

### 3.3 Method B mechanics (the control for T2)

At frame 0, B freezes the authored polygon. It samples the closed boundary at
`boundary_sample_spacing_pixels = 8.0` (start-inclusive, end-exclusive per edge),
tracks those samples frame-to-frame with `cv2.calcOpticalFlowPyrLK`, and fits a
partial affine (similarity: rotation + uniform scale + translation) with
`cv2.estimateAffinePartial2D(method=cv2.LMEDS)`.

Fixed T1 B budget:

| Parameter | Value |
| --- | --- |
| `lk_window` | `[31, 31]` |
| `lk_pyramid_max_level` | `3` |
| `lk_max_iterations` | `30` |
| `lk_epsilon` | `0.01` |
| `lk_min_eigen_threshold` | `0.0001` |
| `minimum_valid_track_count` | `10` |
| `minimum_valid_track_ratio` | `0.75` |
| `affine_estimator` | `LMEDS` |
| `affine_refine_iterations` | `10` |

Each transition applies its step transform to the **current** polygon. Failure
is sticky: if a transition abstains, all later frames are
`ABSTAINED / PREVIOUS_TRANSITION_ABSTAINED`.

### 3.4 Metrics and decision grammar

T1 computes, per method:

- per-frame mask IoU and pixel MAE against the controlled source mask;
- per-frame bounds L2 and centroid L2 against ground truth;
- ordered vertex RMSE (min over cyclic shifts and both orientations);
- GT centroid-motion error;
- final centroid drift and a linear drift slope;
- step-transform second-difference jitter (translation, angle, scale);
- motion-compensated temporal error (B only);
- abstention count/rate and reasons;
- wall time, tracemalloc peak, process peak working set, GPU VRAM (`null`).

T1's decision grammar is `GO` / `CONDITIONAL` / `NO-GO`. `NO-GO` is checked
first; `GO` requires every declared gate; otherwise `CONDITIONAL` names the
failed gates. T2 keeps the same grammar but uses T2-specific thresholds (§8) and
adds a `STOP` outcome for fail-open behavior.

### 3.5 Determinism and isolation

T1 runs each method in a fresh subprocess (`--worker A|B`), serializes canonical
bytes, records input/output SHA-256, and re-runs metric/render derivation on the
frozen raw data. T2 keeps this structure:

- isolated worker per method;
- full 64-hex SHA-256, canonical JSON (`sort_keys`, compact separators, UTF-8);
- input, config, runner, and T1-runner hashes in the manifest;
- repeated frozen-raw derivation must be byte-identical.

T2 additionally records the **T1 runner and config hashes** in every T2
manifest, so a T2 run is invalid if the T1 helper code changed underneath it.

---

## 4. Method C — author-anchored group motion

### 4.1 Definition

> Method C estimates **one** similarity transform per transition from an
> explicitly author-supplied anchor point set, then applies the cumulative
> transform to every member's frozen frame-0 geometry.

Method C makes the group rigid by construction. It cannot represent member
deformation; recovering deformation is Method D's job and is out of scope.

C v0.1 is the **strict rigid** reading of "B + anchor constraints": the anchor
replaces per-member fitting rather than blending with it. A later `C-blend`
variant could blend each member's B transform with the group transform; it is
not part of this comparison matrix.

### 4.2 Difference from B

| | B (control) | C (treatment) |
| --- | --- | --- |
| Pose source | each member's own boundary samples | one author anchor set |
| Transforms per transition | one per member | one per group |
| Member propagation | independent, current geometry | shared, from frame-0 geometry |
| Anchor input | none | explicit points, frame 0 |
| Group conflict detection | none | yes (`ANCHOR_CONFLICT`) |
| Occlusion response | per-member partial tracking | whole-group abstention |
| Identity claim | none | none |
| Authority | none | none |

The only experimental variable is **the source of the transform**. Everything
else (frames, frame-0 geometry, LK parameters, metric code, evaluation window)
is held identical.

### 4.3 Minimum author-provided input

The minimum is exactly two things:

1. **Membership** — an ordered list of at least two research primitive IDs and
   their frozen frame-0 vertex lists.
2. **One anchor set at frame 0** — at least eight author-chosen points in pixels.

Everything else has a fixed default and is not required:

| Input | Required | Default | Meaning |
| --- | --- | --- | --- |
| `group_label` | no | `experimental-group:0` | research label only; must match `experimental-group:[a-z0-9-]+` |
| `members` | **yes** | — | `[{primitive_id, frame_zero_points}]`, `N >= 2`, distinct IDs |
| `anchor_sets` | **yes** | — | `[{anchor_id, frame_index: 0, points}]`, `>= 1`, `>= 8` points each |
| `transform_model` | no | `similarity` | `similarity` (4 DOF) or `translation` (2 DOF) |
| `anchor_policy` | no | `strict` | `strict` only in v0.1 |
| `limits.min_valid_anchor_points` | no | `8` | below this, the anchor is invalid |
| `limits.min_valid_anchor_ratio` | no | `0.75` | below this, the anchor is invalid |
| `limits.max_anchor_residual_px` | no | `2.0` | median LK/affine residual ceiling |
| `limits.conflict_rms_px` | no | `2.0` | pairwise anchor-transform disagreement ceiling |
| `reanchor` | no | `null` | v0.1 supports no re-anchor (see §4.8) |
| `identity_claim` | fixed | `none` | not a user option |

Additional anchor sets are optional. They are **veto-only**: C v0.1 uses the
first anchor as the pose source and treats every other anchor as a consistency
check. C v0.1 never averages compatible anchors; averaging is a later variant.

What is explicitly **not** input: inferred membership, automatic anchor
selection, `group_id` in SVM form (`group:<64hex>`), `entity_id`,
`temporal_identity_id`, `binding_id`, `track_id`, confidence targets, or any
"which object is this" label.

### 4.4 Closed input validation

The T2 config loader must fail closed on all of the following, before reading
any frame:

- unknown top-level or per-group fields;
- `members` with fewer than two entries, duplicate `primitive_id`, non-finite
  or non-`[x,y]` points;
- an anchor with fewer than eight points, a non-zero `frame_index`, points
  outside `[0, canvas)`, duplicate points, or an ID that repeats;
- a `group_label` that looks like an SVM ID (must not start with `group:`);
- `transform_model` outside `{similarity, translation}`;
- `anchor_policy` outside `{strict}`;
- limits that are non-finite, negative, or inconsistent
  (`min_valid_anchor_points > anchor point count`, `min_valid_anchor_ratio > 1`);
- `identity_claim` missing or not `none`;
- any field that would claim an Entity, Group, Track, Binding, or Identity.

### 4.5 Per-transition algorithm (v0.1)

Frame 0 is emitted as `SUPPORTED` with identity group transform and an
`initial` anchor diagnostic.

For each transition `t-1 -> t`:

1. **Track** every anchor point set with the T1 LK budget
   (`31×31`, 3 levels, 30 iterations, `1e-2` epsilon, `1e-4` min eigen).
2. **Validate** each anchor: valid count and ratio; if below the limits, mark
   that anchor `INVALID`.
3. **Estimate** a per-anchor similarity with `estimateAffinePartial2D(LMEDS)`
   from its valid points; reject non-finite matrices, non-positive scale, and
   reflected matrices (`det <= 0`).
4. **Residual gate**: if the anchor's median affine residual exceeds
   `max_anchor_residual_px`, mark it `INVALID`.
5. **Conflict gate**: if there are two or more *valid* anchors, apply each
   anchor's step transform to the frozen frame-0 member vertices and compute
   the pairwise RMS displacement. If the maximum pairwise RMS exceeds
   `conflict_rms_px`, abstain with `ANCHOR_CONFLICT`.
6. **Pose selection**: under `strict`, if **any** declared anchor is invalid,
   abstain with that anchor's reason (`INSUFFICIENT_VALID_ANCHOR_TRACKS`,
   `ANCHOR_RESIDUAL_TOO_HIGH`, or `ANCHOR_FIT_FAILED`); if no declared anchor is
   usable, `ANCHOR_LOST`. No failover to a secondary anchor in v0.1 — failover
   would be a hidden selection rule.
7. **Compose** the step transform onto the cumulative group transform
   (`P_t = P_{t-1} ∘ S_t`) and apply `P_t` to every member's frame-0 vertices.
8. **Validate** the result: finite points, positive scale, no member ID changed.
9. **Emit** `SUPPORTED` with members, `step_affine`, `cumulative_affine`,
   decomposed transform, and anchor diagnostics.

If any transition abstains, all later frames are
`ABSTAINED / PREVIOUS_TRANSITION_ABSTAINED` (sticky, matching B).

### 4.6 Group transform representation

C reports, per frame:

```text
step_affine:        [[a, b, tx], [c, d, ty]]       (2×3, this transition)
cumulative_affine:  [[a, b, tx], [c, d, ty]]       (2×3, frame 0 -> t)
decomposed:         {translation: [tx, ty], rotation_degrees, scale}
```

The decomposed values use the same parameterization as T1's jitter vector:
`scale = sqrt(a² + c²)`, `rotation_degrees = atan2(c, a)`, `translation = (tx, ty)`.
The matrix is authoritative; the decomposed values are diagnostics.

This is a similarity, so it is *representable* by the existing SVM Group
transform semantics (translate, rotate, uniform scale, fixed origin), but T2
does **not** write a Document Group, a Track, or a Keyframe. The representation
is research data only.

### 4.7 Failure and abstention reasons

| Reason | Boundary |
| --- | --- |
| `INSUFFICIENT_VALID_ANCHOR_TRACKS` | valid count or ratio below limits |
| `ANCHOR_LOST` | no anchor point set has enough valid points |
| `ANCHOR_FIT_FAILED` | non-finite matrix, non-positive scale, reflected matrix, or fit returned `None` |
| `ANCHOR_RESIDUAL_TOO_HIGH` | median affine residual above the ceiling |
| `ANCHOR_CONFLICT` | two valid anchors disagree above `conflict_rms_px` |
| `PREVIOUS_TRANSITION_ABSTAINED` | sticky abstention after an earlier failure |
| `INVALID_MEMBER_GEOMETRY` | result is non-finite or otherwise illegal |

Every reason is recorded per frame; the summary counts them.

### 4.8 Non-goals (v0.1)

C v0.1 does **not**:

- infer membership or select members automatically;
- select anchors automatically, or prefer anchors by texture score;
- average compatible anchors (first anchor is the pose source);
- fail over to a secondary anchor when the primary is lost;
- re-anchor, interpolate, or hold the last transform after occlusion;
- refine member geometry per frame (that is D);
- create, persist, or claim a Group, TemporalIdentity, Binding, Track, or
  any other SVM authority;
- use CoTracker3, SAM 2.1, a GPU, or any external model.

Temporary occlusion is therefore tested as **fail-closed abstention**, not as
recovery. Recovery would require an author re-pose/re-anchor input and is a
separate later arm.

---

## 5. T2 experimental profile (proposed, research-local)

### 5.1 Config schema

Proposed: `t2-group-anchor-experiment-config-0.1`.

```json
{
  "schema_version": "t2-group-anchor-experiment-config-0.1",
  "experiment_id": "t2-f1-translation-v1",
  "artifact_classification": "experimental-only-not-svm-evidence",
  "fixture_root": "research/temporal-geometry-pilot/t2/fixtures/f1-translation",
  "ground_truth": "ground-truth.json",
  "frames": [
    {"index": 0, "tick": 0, "path": "tick_000.png", "ground_truth_key": "tick_0"},
    {"index": 1, "tick": 12, "path": "tick_012.png", "ground_truth_key": "tick_12"},
    {"index": 2, "tick": 24, "path": "tick_024.png", "ground_truth_key": "tick_24"},
    {"index": 3, "tick": 36, "path": "tick_036.png", "ground_truth_key": "tick_36"}
  ],
  "timebase": {"ticks_per_second": 12},
  "evaluation_window": {"first_frame_index": 0, "last_frame_index": 3, "drift_reference_frame_index": 0},
  "group": {
    "group_label": "experimental-group:0",
    "members": [
      {"primitive_id": "member:body", "frame_zero_points": [[180.0, 190.0], [320.0, 200.0], [350.0, 270.0], [250.0, 330.0], [170.0, 280.0]]},
      {"primitive_id": "member:sat-a", "frame_zero_points": [[70.0, 140.0], [120.0, 135.0], [125.0, 185.0], [75.0, 190.0]]},
      {"primitive_id": "member:sat-b", "frame_zero_points": [[390.0, 240.0], [440.0, 235.0], [445.0, 285.0], [395.0, 290.0]]}
    ],
    "anchor_sets": [
      {"anchor_id": "anchor:body", "frame_index": 0, "points": [[180.0, 190.0], [250.0, 195.0], [320.0, 200.0], [335.0, 235.0], [350.0, 270.0], [300.0, 300.0], [250.0, 330.0], [210.0, 305.0]]}
    ],
    "transform_model": "similarity",
    "anchor_policy": "strict",
    "limits": {
      "min_valid_anchor_points": 8,
      "min_valid_anchor_ratio": 0.75,
      "max_anchor_residual_px": 2.0,
      "conflict_rms_px": 2.0
    },
    "reanchor": null
  },
  "method_b_budget": {
    "boundary_sample_spacing_pixels": 8.0,
    "lk_window": [31, 31],
    "lk_pyramid_max_level": 3,
    "lk_max_iterations": 30,
    "lk_epsilon": 0.01,
    "lk_min_eigen_threshold": 0.0001,
    "minimum_valid_track_count": 10,
    "minimum_valid_track_ratio": 0.75,
    "affine_estimator": "LMEDS",
    "affine_refine_iterations": 10
  },
  "method_c_budget": {
    "lk_window": [31, 31],
    "lk_pyramid_max_level": 3,
    "lk_max_iterations": 30,
    "lk_epsilon": 0.01,
    "lk_min_eigen_threshold": 0.0001,
    "affine_estimator": "LMEDS",
    "affine_refine_iterations": 10
  },
  "decision_thresholds": {
    "go": {},
    "conditional": {},
    "stop": {}
  }
}
```

Notes:

- The anchor example lists 8 of the 16 points for readability; the real config
  lists all 16 exactly as emitted by the fixture generator and stored in
  `ground-truth.json` (see §6.7). The config must contain the **exact** list,
  not a sampling rule, at run time.
- `decision_thresholds` is filled with the §8 values and frozen before the
  first run.
- Unknown fields are rejected by the loader.

### 5.2 Raw output schema

Proposed: `t2-group-anchor-experiment-output-0.1`.

```json
{
  "schema_version": "t2-group-anchor-experiment-output-0.1",
  "artifact_classification": "experimental-only-not-svm-evidence",
  "method": "C-author-anchored-group-similarity",
  "identity_claim": "none",
  "group_label": "experimental-group:0",
  "frames": [
    {
      "frame_index": 0,
      "tick": 0,
      "status": "SUPPORTED",
      "members": [
        {"primitive_id": "member:body", "points": [[180.0, 190.0], [320.0, 200.0], [350.0, 270.0], [250.0, 330.0], [170.0, 280.0]]}
      ],
      "group_transform": {
        "step_affine": null,
        "cumulative_affine": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        "decomposed": {"translation": [0.0, 0.0], "rotation_degrees": 0.0, "scale": 1.0}
      },
      "anchor": {
        "sets": [
          {
            "anchor_id": "anchor:body",
            "valid_count": 16,
            "valid_ratio": 1.0,
            "median_lk_error": null,
            "median_affine_residual_px": null,
            "step_affine": null
          }
        ],
        "conflict_rms_px": null
      },
      "reason": null
    }
  ]
}
```

For B, the same top-level shape is used with `method:
"B-per-member-opencv-lk-propagation"`, per-member `points`, and
`group_transform: null` (B has no group transform; T2 derives a diagnostic one
only inside metrics).

The output is deliberately **not** the T1 raw schema: T2 has multiple members,
an explicit group transform, and anchor diagnostics. It is also deliberately
**not** an SVM schema, media type, Artifact, or Document.

### 5.3 Classification and naming

- `artifact_classification` is always
  `experimental-only-not-svm-evidence`.
- `identity_claim` is always `none`.
- Member IDs are research labels (`member:body`, `member:sat-a`, …), not Entity
  IDs and not stable cross-run identity claims.
- The group label is research-local and must not look like `group:<64hex>`.
- No `TemporalIdentity`, `MotionTargetBinding`, `Track`, `Keyframe`, or
  `Group` field appears in the output.

### 5.4 Determinism

- No randomness, timestamps, absolute paths, or environment-dependent IDs in
  raw output.
- Canonical bytes are used for hashing and comparison.
- The fixture generator is deterministic: fixed vertices, fixed transforms,
  fixed draw order, no antialiasing, no metadata.
- Two full runs in the same declared environment must produce byte-identical
  `raw/method-b.json`, `raw/method-c.json`, and `metrics.json`; `costs.json` and
  `run-manifest.json` may differ only in measured timing and commit metadata.

---

## 6. Fixtures

### 6.1 Common profile

| Property | Value |
| --- | --- |
| Canvas | 512×512, 8-bit grayscale |
| Values | `{0, 255}` only (background 255, members 0) |
| Frames | 4: ticks 0, 12, 24, 36; 12 ticks/s |
| Draw order | body, sat-a, sat-b (and decoy in F5); occluder last in F4 |
| Rasterization | `cv2.fillPoly(..., lineType=cv2.LINE_8)`, integer-rounded vertices |
| No antialiasing | required |
| PNG | no metadata, no alpha |
| Transform convention | `p' = O + s·R(θ)·(p − O) + t`, `O = (256, 256)` |
| GT | exact float points per member per frame, same cyclic order as frame 0 |

Members are non-overlapping in every frame. The fixture generator asserts this
and aborts if a transform causes overlap or an out-of-canvas point.

Anchor points are **author-selected frame-0 points**. The default selection rule
(used by the generator) is 16 points equally spaced by arc length along the
body boundary, with the body's frame-0 vertices as the closed polyline. F3 uses
a different, explicit rule (below). The generator writes the exact resulting
points into `ground-truth.json`; the config copies that exact list.

### 6.2 F1 — coherent translation

**Members (frame 0):**

| Member | Points |
| --- | --- |
| body | `[[180,190],[320,200],[350,270],[250,330],[170,280]]` |
| sat-a | `[[70,140],[120,135],[125,185],[75,190]]` |
| sat-b | `[[390,240],[440,235],[445,285],[395,290]]` |

**GT transform:** `θ = 0`, `s = 1`, `t(k) = (12k, -6k)` for `k = 0..3`.

**Anchor:** body boundary, 16 points at arc-length fractions `i/16`
(`i = 0..15`) along the closed polyline.

**What it isolates:** the simplest case. B must pass (control validity); C is
expected to be steadier because all three members share one transform. This is
the primary falsification fixture: if C cannot beat B here, the method is not
worth further work.

### 6.3 F2 — rotation + uniform scale

**Members:** same as F1.

**GT transform (defined cumulatively):** at `k`, `θ = 8k°`, `s = 1.04^k`,
`t = (4k, -2k)`. At `k = 3`:
`θ = 24°`, `s = 1.124864`, `t = (12, -6)`.

**Anchor:** body boundary, 16 points.

**What it isolates:** rotation and scale. A per-member similarity fit can
disagree on rotation/scale under noise; C applies one fit to every member. The
fixture is sized to stay inside the canvas and to keep members disjoint.

### 6.4 F3 — low-texture / straight-edge regions

**Members (frame 0):**

| Member | Points |
| --- | --- |
| body | `[[190,210],[310,210],[310,290],[190,290]]` |
| sat-a | `[[100,150],[145,150],[145,195],[100,195]]` |
| sat-b | `[[365,240],[410,240],[410,285],[365,285]]` |

**GT transform:** same as F1.

**Anchor:** 16 points on the body's **bottom edge only**:
`(190 + 8i, 290)` for `i = 0..15`.

**What it isolates:** the aperture problem. A long straight edge has only one
observable gradient direction; LK's minimum-eigenvalue gate rejects most points,
and the similarity fit is ill-conditioned. This is the low-texture failure mode
that T1 already documents for flat vector-like frames.

**Expected:** C abstains (most likely
`INSUFFICIENT_VALID_ANCHOR_TRACKS` or `ANCHOR_LOST`); B likely abstains or
degrades for the same reason. A **supported** result with group IoU below 0.90
is a fail-open event and a STOP, not a success.

### 6.5 F4 — temporary occlusion

**Members and motion:** F1.

**Occluder:** a background-colored (255) rectangle `(230,175)–(360,345)` drawn
only at `k = 1` (tick 12), after the members. It covers the body's right side and
at least 8 of the 16 anchor points (the generator asserts this count).

**Anchor:** F1's body anchor.

**What it isolates:** anchor loss. C must abstain for the whole group at the
occluded transition and stay abstained (sticky) at the later frames; it must not
fabricate a transform from the surviving points of a partially hidden anchor.
B may still partially track individual members; that is the comparison.

**No recovery claim:** v0.1 has no re-anchor. A later, separately specified
`C-reanchor` arm may add an explicit author re-pose; it is not part of this
matrix.

### 6.6 F5 — conflicting anchor motion

**Members (frame 0):** F1's three members plus a decoy:

| Member | Points |
| --- | --- |
| decoy | `[[400,360],[450,355],[455,400],[405,405]]` |

**GT motion:**

- body, sat-a, sat-b: `t(k) = (12k, -6k)`, `θ = 0`, `s = 1`;
- decoy: `t(k) = (-10k, 8k)`, `θ = 0`, `s = 1`.

**Anchors:** two sets, both declared as group anchors:

- `anchor:body` — 16 points on the body boundary;
- `anchor:decoy` — 16 points on the decoy boundary.

**What it isolates:** the author's group hypothesis is wrong. The two anchors
disagree by `(22, -14)` px per transition, which is an RMS of about 26 px over
the member vertices — far above the 2.0 px conflict ceiling. C must abstain with
`ANCHOR_CONFLICT` at the first transition and stay abstained. A supported frame
while the two anchors disagree is a fail-open event and a STOP.

B, which ignores anchors, tracks each of the four members independently; it will
likely produce a "reasonable" per-member result but a large group-rigidity
error. That contrast is the point: B has no group claim to violate; C does.

### 6.7 Ground truth and generation rules

Each fixture directory contains:

```text
t2/fixtures/<fixture>/
  tick_000.png
  tick_012.png
  tick_024.png
  tick_036.png
  ground-truth.json
```

`ground-truth.json` shape:

```json
{
  "schema_version": "t2-fixture-ground-truth-0.1",
  "fixture_id": "t2-f1-translation",
  "canvas": [512, 512],
  "frames": [
    {
      "index": 0,
      "tick": 0,
      "members": [
        {"primitive_id": "member:body", "points": [[180.0, 190.0], [320.0, 200.0], [350.0, 270.0], [250.0, 330.0], [170.0, 280.0]]}
      ],
      "group_transform": {"translation": [0.0, 0.0], "rotation_degrees": 0.0, "scale": 1.0}
    }
  ],
  "anchor_sets": [
    {"anchor_id": "anchor:body", "frame_index": 0, "points": [[180.0, 190.0], [250.0, 195.0], [320.0, 200.0], [335.0, 235.0], [350.0, 270.0], [300.0, 300.0], [250.0, 330.0], [210.0, 305.0]]}
  ]
}
```

The anchor list is abridged to 8 of the 16 points for readability; the generator
emits all 16 exact points.

Generation rules:

1. Start from the fixed frame-0 member vertices.
2. For each tick, apply the fixture's exact per-member transform to every
   vertex; store the float result in GT.
3. Rasterize with `cv2.fillPoly` and `LINE_8`; do not antialias; do not add
   metadata.
4. Draw in the documented order; for F4 draw the occluder last.
5. Assert: all points inside the canvas; members pairwise disjoint in every
   frame; the F3 anchor is collinear; the F4 occluder covers at least 8/16
   anchor points; the F5 anchor transforms disagree by more than 2.0 px RMS.
6. Compute anchor points by the documented rule and store the exact list.
7. Emit `ground-truth.json` with exact floats and the per-frame transform.

No random seed is used; there is no stochastic step.

### 6.8 Why these five fixtures

| Fixture | Isolates | Primary gate |
| --- | --- | --- |
| F1 | coherent translation | C beats B (quality, jitter, drift) |
| F2 | rotation + uniform scale | C keeps group rigidity |
| F3 | low-texture / aperture | fail-closed, no confident-wrong result |
| F4 | anchor occlusion | fail-closed group abstention |
| F5 | conflicting anchors | fail-closed conflict detection |

F1/F2 carry the quality hypothesis; F3/F4/F5 carry the safety hypothesis. A
method that wins F1/F2 but fails F3/F5 is not acceptable, because it is
confidently wrong exactly where the evidence is weak.

---

## 7. B/C comparison protocol

### 7.1 Arms

- **B (control):** per-member boundary sampling, per-member LK, per-member
  similarity fit, per-member step application. No anchors, no group transform.
- **C (treatment):** anchor-only LK, one group similarity per transition,
  cumulative application to frozen frame-0 member vertices.
- **C-reanchor:** not in this matrix (future arm, explicit author re-pose).
- **A:** not re-run for T2. T1's A remains the single-primitive reference; T2's
  question is B vs C, not A vs C.

### 7.2 Held constant

- identical frames, canvas, coordinate units, ticks, timebase;
- identical frame-0 member geometry;
- identical LK parameters, sample spacing (B), min track count/ratio, affine
  estimator and refine iterations;
- identical metric code and evaluation window;
- identical drift reference (frame 0);
- identical fixture-generation rules.

The only difference is the transform source: per-member flow (B) vs one
author-anchored group transform (C).

### 7.3 Run matrix

| Fixture | B | C | Repeat for determinism |
| --- | --- | --- | --- |
| F1 translation | 1 | 1 | 2 full runs |
| F2 rotation+scale | 1 | 1 | 2 full runs |
| F3 low-texture | 1 | 1 | 2 full runs |
| F4 occlusion | 1 | 1 | 2 full runs |
| F5 conflict | 1 | 1 | 2 full runs |

Each "run" executes in an isolated worker, then a separate metric/render pass on
the frozen raw output, as T1 does.

### 7.4 Procedure (proposed; not executed by this docs task)

```powershell
python research/temporal-geometry-pilot/t2/generate_fixtures.py
python research/temporal-geometry-pilot/t2/run_t2.py `
  --config research/temporal-geometry-pilot/t2/experiment-f1.json `
  --output research/temporal-geometry-pilot/t2/runs/t2-f1-v1
python -m unittest discover -s research/temporal-geometry-pilot/t2/tests -v
```

Run order per fixture: B first, then C, each in a fresh worker. Do not reuse a
worker across fixtures.

### 7.5 Artifacts per run

```text
t2/runs/t2-<fixture>-v1/
  raw/method-b.json
  raw/method-c.json
  metrics.json
  costs.json
  reproducibility.json
  comparison.avi
  run-manifest.json
```

The run manifest records: config hash, T2 runner hash, T1 runner/config hashes,
input PNG/GT hashes, environment versions, output hashes, decision, and the
authority disclaimer. The canonical T2 snapshot is copied from the deterministic
run pair, with a `canonical-manifest.json` that lists every file hash.

### 7.6 Analysis and reporting

- One table per fixture: B vs C on IoU, vertex RMSE, drift, jitter, rigidity,
  abstention, reasons, cost.
- One aggregate table: per-gate pass/fail and the final decision.
- Report every run, including abstentions and failures. No run may be dropped
  after seeing its result.
- Relative comparisons use the same metric code and the same frozen raw data.
- A difference that cannot be attributed to the transform source (because some
  other parameter changed) is not evidence.

### 7.7 What would invalidate the comparison

- B abstains on F1 or F2 (control invalid) → rebuild the fixture, do not credit
  C.
- Any LK parameter, sample spacing, or metric definition differs between B and
  C → invalid.
- A threshold is edited after seeing results → invalid; start a new
  `experiment_id`.
- The T1 helper hash changes during the T2 run → invalid.
- A fixture is regenerated between B and C → invalid.
- C uses a second anchor via failover or averaging without declaring it →
  invalid.

---

## 8. Predeclared metrics and decision thresholds

### 8.1 Metrics

All metrics are computed from the same frozen raw outputs and the fixture GT.

| Metric | Definition | Unit | Needs GT |
| --- | --- | --- | --- |
| `member_iou` | mask IoU per member (intersection over union of predicted and GT masks), `fillPoly`/`LINE_8` | ratio | yes |
| `group_iou` | mask IoU of the union of member masks vs the union of GT member masks | ratio | yes |
| `member_vertex_rmse` | ordered vertex RMSE, min over cyclic shifts and both orientations | px | yes |
| `group_vertex_rmse` | mean of per-member vertex RMSE | px | yes |
| `member_centroid_error` | Euclidean distance between predicted and GT member centroids | px | yes |
| `group_centroid_error` | Euclidean distance between the mean predicted and mean GT member centroids | px | yes |
| `rigidity_error` | mean absolute change of pairwise member-centroid distances, over all pairs `i < j` | px | yes |
| `member_step_jitter` | per member, fit similarity `t-1 -> t` from its vertices; second difference of `[tx,ty,θ,s]`; mean over members/time | mixed | no |
| `group_step_jitter` | same second difference on the group step transform (C: estimated; B: derived by least-squares fit over member centroids) | mixed | no |
| `final_group_drift` | final group centroid error vs frame 0 | px | yes |
| `drift_slope` | linear slope of group centroid error over frames | px/frame | yes |
| `abstention_rate` | abstained frames / evaluated frames | ratio | no |
| `reason_counts` | count per reason code | count | no |
| `wall_time_per_frame` | isolated worker wall time / frames | s | no |
| `peak_working_set` | process peak working set | bytes | no |
| `lk_point_count` | points tracked per transition | count | no |
| `determinism` | repeated raw/metrics canonical bytes identical | bool | no |

Notes:

- The ordered vertex RMSE is the same family as T1's
  `_ordered_vertex_rmse`: it tries both orientations and every cyclic shift and
  takes the minimum. This is a metric convention, not an identity claim.
- The group step transform for B is **derived for metrics only** by a
  least-squares similarity fit over member centroids; it is not part of B's raw
  output and is not used to propagate anything.
- `rigidity_error` is the cleanest group-coherence measure: C should be ~0 by
  construction; B's value shows how far independent per-member propagation
  drifts from group rigidity.
- Jitter uses step transforms (per transition), matching T1's second-difference
  convention, not cumulative transforms.

### 8.2 Gates

All thresholds are frozen in `decision_thresholds` **before** the first run.

#### F1 — coherent translation

| Gate | Requirement |
| --- | --- |
| B control | B abstention = 0 |
| C group IoU | `>= 0.990` |
| C mean member IoU | `>= 0.985` |
| C mean vertex RMSE | `<= 0.75 px`; if `B >= 0.50 px` also `<= 0.75 × B`; if `B < 0.50 px`, `<= 0.60 px` |
| C final group drift | `<= 0.30 px`; if `B >= 0.10 px` also `<= 0.50 × B`; if `B < 0.10 px`, `<= 0.10 px` |
| C group step jitter | if `B >= 0.05`, `<= 0.50 × B`; if `B < 0.05`, `<= 0.05` |
| C rigidity error | `<= 0.10 px` |
| C abstention | `0` |

#### F2 — rotation + uniform scale

| Gate | Requirement |
| --- | --- |
| B control | B abstention = 0 |
| C group IoU | `>= 0.975` |
| C mean member IoU | `>= 0.970` |
| C mean vertex RMSE | `<= 1.50 px`; if `B >= 0.50 px` also `<= 0.75 × B`; if `B < 0.50 px`, `<= 0.60 px` |
| C final group drift | `<= 0.75 px`; if `B >= 0.10 px` also `<= 0.50 × B`; if `B < 0.10 px`, `<= 0.10 px` |
| C group step jitter | if `B >= 0.05`, `<= 0.60 × B`; if `B < 0.05`, `<= 0.05` |
| C rigidity error | `<= 0.20 px` |
| C abstention | `0` |

#### F3 — low-texture / aperture

| Requirement | Outcome |
| --- | --- |
| C abstains on at least one frame with a reason in `{INSUFFICIENT_VALID_ANCHOR_TRACKS, ANCHOR_LOST, ANCHOR_RESIDUAL_TOO_HIGH, ANCHOR_FIT_FAILED}` | pass |
| C is `SUPPORTED` on every supported frame with `group_iou >= 0.95` | pass |
| C is `SUPPORTED` with `0.90 <= group_iou < 0.95` | CONDITIONAL |
| C is `SUPPORTED` on any frame with `group_iou < 0.90` | **STOP (fail-open)** |
| B is `SUPPORTED` with `group_iou < 0.90` | record as a B failure; not a C gate |

If both B and C abstain on F3, the fixture is **inconclusive** and must be
reported as such, not as a C success.

#### F4 — temporary occlusion

| Requirement | Outcome |
| --- | --- |
| C is `ABSTAINED` at the occluded frame with `ANCHOR_LOST` or `INSUFFICIENT_VALID_ANCHOR_TRACKS` | pass |
| Later C frames are `PREVIOUS_TRANSITION_ABSTAINED` | pass (sticky, no recovery claimed) |
| C is `SUPPORTED` while the occluder is present | **STOP (fail-open)** |
| B is measured | no gate |

#### F5 — conflicting anchor motion

| Requirement | Outcome |
| --- | --- |
| C is `ABSTAINED` with `ANCHOR_CONFLICT` at the first conflicting transition | pass |
| Later C frames are `PREVIOUS_TRANSITION_ABSTAINED` | pass |
| C is `SUPPORTED` while the anchors disagree by more than `conflict_rms_px` | **STOP (fail-open)** |
| B is measured | no gate |

#### Cost and determinism

| Gate | Requirement |
| --- | --- |
| C wall time/frame | `<= 1.00 × B` for GO; `<= 1.50 × B` for CONDITIONAL; above that STOP unless quality gates fail anyway |
| C peak working set | record; no hard gate in v0.1 |
| Full-run determinism | two runs byte-identical for `raw/method-b.json`, `raw/method-c.json`, `metrics.json` |
| Downstream determinism | frozen-raw metrics/render identical (T1 pattern) |
| Environment | OpenCV exactly `4.14.0.94`; record Python/NumPy; mismatch → CONDITIONAL |

### 8.3 Aggregate decision

Evaluation order is **STOP first, then GO, then CONDITIONAL**; a STOP condition
overrides a GO, and a GO overrides a CONDITIONAL.

**GO** requires all of:

1. F1 passes every quality gate.
2. F2 passes every quality gate.
3. F3 passes its fail-closed gate or is inconclusive; an inconclusive F3 does
   not block GO but must be reported as an unresolved limit.
4. F4 passes its fail-closed gate.
5. F5 passes its fail-closed gate.
6. Full-run determinism passes.
7. Environment is the declared OpenCV wheel.
8. C wall time/frame `<= 1.00 × B`.

**CONDITIONAL** if any of:

- F1 or F2 misses one or more quality gates within the STOP bands above
  (F1 at most 10% relative, F2 at most 25% relative), and no fail-open occurred;
- C cost is `> 1.00 × B` and `<= 1.50 × B`;
- C cost is `> 1.50 × B` but F1/F2 pass with a material quality gain (report the
  cost caveat explicitly);
- F3 is CONDITIONAL (`0.90 <= group_iou < 0.95`);
- the environment differs from the declared OpenCV wheel;
- full-run determinism passes only at the downstream level (raw differs in
  timing-adjacent fields), not byte-for-byte;

**STOP** if any of:

- F1 misses a quality gate by more than 10% relative (the core hypothesis fails
  on the easiest case);
- F2 misses a quality gate by more than 25% relative (the group transform cannot
  handle rotation/scale);
- F1 or F2 has B abstention > 0 (control invalid);
- any fail-open on F3/F4/F5;
- C requires per-member independent fitting, inferred membership, or automatic
  anchor selection to pass;
- C's output is non-finite or nondeterministic;
- C cost is `> 1.50 × B` with no compensating quality gain;
- the implementation would need a Core, schema, spec, `ChangeAuthority`, Group,
  Track, Binding, or TemporalIdentity change.

### 8.4 Freeze and no-post-hoc rule

The thresholds above are design hypotheses. They are copied into each
`experiment-f*.json` and hashed in the run manifest **before** the first run.
No threshold may be changed after seeing a result. Any change starts a new
`experiment_id` (`t2-...-v2`) and is reported as a new experiment, not a tweak.

### 8.5 Statistical scope

T2 is a **descriptive, deterministic** experiment: one group, four frames, five
fixtures, no random seed. It can falsify the stated hypothesis on these cases;
it cannot establish a population-level superiority claim, produce confidence
intervals, or support a general "C is better" statement. If a later decision
needs statistical evidence, T2.1 must add seeded fixture variants and repeated
runs; that is a separate authorization.

---

## 9. Risks and STOP conditions

| ID | Risk | Trigger | Response |
| --- | --- | --- | --- |
| R1 | T1 baseline mutated | `git diff 40b5f65 -- research/temporal-geometry-pilot` non-empty, or a canonical hash mismatch | **STOP**; restore T1 before any T2 run |
| R2 | Golden/spec number collision | any `examples/047-*` or `spec/83` claim; any `examples/0xx` addition | **STOP**; T2 is research-only; future numbers start at 048/84 |
| R3 | Identity smuggling | output or config contains `entity_id`, `group_id`, `temporal_identity_id`, `binding_id`, `track_id`, or a claim of "same object" | **STOP**; remove the field and re-review |
| R4 | Automatic membership/anchor | code selects members, ranks anchors, or infers membership | **STOP**; membership and anchors must be explicit inputs |
| R5 | Threshold drift | any threshold edited after the first run | **STOP**; new experiment ID required |
| R6 | B/C confound | different LK params, sample spacing, metric code, or frame-0 geometry | **STOP**; rerun with held-constant settings |
| R7 | Broken control | B abstains on F1 or F2 | **STOP**; rebuild fixture, do not credit C |
| R8 | Fail-open | C supported with IoU < 0.90 on F3, or supported during F4 occlusion or F5 conflict | **STOP**; fail-closed must be enforced |
| R9 | Nondeterminism | repeated raw/metrics differ | **STOP**; diagnose before any claim |
| R10 | Core/authority creep | implementation needs `svm/`, `schema/`, `spec/`, `ChangeAuthority`, Group, Track, or Binding | **STOP**; T2 cannot authorize that |
| R11 | External model dependency | CoTracker3, SAM, GPU, or checkpoint added | **STOP**; out of scope |
| R12 | Automatic re-anchor | re-anchor or last-pose hold appears without an explicit author event | **STOP**; v0.1 has no recovery |
| R13 | Environment mismatch | OpenCV not `4.14.0.94` | **CONDITIONAL**; record and re-run on the declared wheel before a GO |
| R14 | Non-deterministic fixture generation | PNG/GT bytes differ between two generator runs | **STOP**; fix the generator |
| R15 | Concurrent worktree collision | overlapping edits in `research/` or `examples/047-*` appear during T2 work | **STOP**; re-read `git status` and rebase the plan, never overwrite |
| R16 | Hidden averaging/failover | C averages anchors or falls back to a secondary anchor | **STOP**; v0.1 uses one primary anchor + veto-only extras |

---

## 10. Exact proposed file changes

### 10.1 This task (docs-only)

| Path | Change | Status |
| --- | --- | --- |
| `research/temporal-geometry-pilot/T2-GROUP-ANCHOR-EXPERIMENT.md` | add this design | **done** |
| everything else | none | — |

An optional one-line pointer in the pilot README (§13, after the T2 bullet) is
**proposed but not applied**: the T1 README is a recorded baseline, and this
task intentionally leaves it untouched.

### 10.2 Future T2 implementation (not authorized here)

All future files live under `research/temporal-geometry-pilot/t2/`:

| Path | Purpose |
| --- | --- |
| `t2/README.md` | T2 index, status, how to run, result summary |
| `t2/generate_fixtures.py` | deterministic fixture generator (§6.7) |
| `t2/fixtures/f1-translation/tick_000.png` … `tick_036.png` | F1 frames |
| `t2/fixtures/f1-translation/ground-truth.json` | F1 exact GT + anchor list |
| `t2/fixtures/f2-rotation-scale/…` | F2 frames + GT |
| `t2/fixtures/f3-low-texture/…` | F3 frames + GT |
| `t2/fixtures/f4-occlusion/…` | F4 frames + GT |
| `t2/fixtures/f5-conflicting-anchors/…` | F5 frames + GT |
| `t2/experiment-f1.json` … `experiment-f5.json` | frozen T2 configs |
| `t2/run_t2.py` | isolated B/C workers, metrics, manifests |
| `t2/tests/test_t2_contract.py` | closed config, fixture, and output invariants |
| `t2/runs/t2-<fixture>-v1/…` | raw/metrics/costs/repro/video/manifest |
| `t2/runs/t2-canonical/canonical-manifest.json` | canonical snapshot record |

The runner may import T1 helpers read-only (`canonical_bytes`, `mask_iou`,
`_ordered_vertex_rmse`, `_linear_slope`), but must not modify
`run_experiment.py`; each T2 manifest records the T1 runner/config hashes.

### 10.3 Forbidden paths

No change to:

- `svm/`, `schema/`, `spec/`, `examples/`, `.github/`, `demo/`, and the
  repository `tests/`;
- `research/temporal-geometry-pilot/experiment.json`;
- `research/temporal-geometry-pilot/run_experiment.py`;
- `research/temporal-geometry-pilot/runs/t1-*`;
- `research/temporal-geometry-pilot/tests/`;
- any `pip-*` directory in the repository root.

### 10.4 Numbering

- No Golden for T2. `examples/047-*` is occupied by
  `fogleman-primitive-toolchain`; any future Spec 82 G4 Golden starts at
  `examples/048-*` and is separately authorized.
- No T2 spec. `spec/83` is occupied by
  `fogleman-primitive-toolchain`; a future T2-adjacent spec starts at
  `spec/84` and is separately authorized.
- T2 run directories are named `runs/t2-*`, not `examples/*`.

---

## 11. GO / CONDITIONAL / STOP recommendation

**CONDITIONAL GO** — proceed to a bounded T2 implementation only under these
conditions:

1. **T1 stays frozen.** Re-run the three checks in §2.2 immediately before the
   first T2 run; any diff or hash mismatch is a STOP.
2. **Fixtures are deterministic and reviewed.** The generator, five fixtures,
   and `ground-truth.json` files are checked in; two generator runs are
   byte-identical; the §6.7 assertions pass.
3. **Research-local format only.** `t2-group-anchor-experiment-*` is a new
   research schema; no SVM schema, media type, Artifact, Document, or
   `ChangeAuthority` is touched.
4. **No numbering claim.** No Golden, no spec 83/047; future numbers 048/84 only
   after separate authorization.
5. **Thresholds frozen before the run.** The §8 values are in the configs and
   hashed; no post-hoc edits; all five fixtures and both methods are run and
   retained.
6. **Fail-closed gates enforced.** F3/F4/F5 pass only if C abstains (or is
   accurate); no auto re-anchor, no anchor averaging, no failover.
7. **Bounded claim.** Results are reported as experimental research on five
   controlled fixtures, never as SVM Evidence, identity, Group authority, or
   P2D-A/P2D-B progress.

This is **not** a GO for:

- Method D (local re-optimization);
- Core/schema/spec integration;
- P2D-A, P2D-B, representation correspondence, or target binding;
- any use of the anchor membership as a persisted Group or TemporalIdentity;
- any claim that C is generally superior to B beyond these fixtures.

**STOP** immediately if any R1–R12 or R14–R16 condition in §9 triggers.

If T2 passes, the next decision is whether a separately authorized T3 evidence
schema and Change/verifier design is warranted. That decision is out of scope
for T2 and cannot be inferred from a T2 PASS.

---

## 12. Verification log (this docs-only task)

Commands run from the repository root:

```text
git rev-parse --abbrev-ref HEAD          -> codex/primitive-toolchain
git rev-parse --short HEAD               -> 24441f1
git status --porcelain=v1                -> no tracked modifications before this file was added
git log --oneline 40b5f65..HEAD          -> only 24441f1
git merge-base --is-ancestor 40b5f65 HEAD -> yes
git diff --stat 40b5f65 -- research/temporal-geometry-pilot -> empty
git diff --stat HEAD -- research/temporal-geometry-pilot     -> empty
sha256sum <seven canonical files>        -> all match canonical-manifest.json
```

The T1 tests were not re-executed in this task; the canonical manifest records
`Ran 5 tests in 0.641s OK` in the declared environment, and the file hashes
above establish that the recorded baseline is unchanged. No T2 experiment was
executed, and no file other than this design document was added or modified.

---

## 13. References

- [T1 pilot README](README.md) — T0 design, T1 A/B implementation, measured
  result, and the T1/T2/T3 gate framing.
- [T1 protocol](experiment.json) — frozen T1 config, budgets, and thresholds.
- [T1 runner](run_experiment.py) — canonical bytes, Method A/B, metrics, decision
  grammar, manifests.
- [T1 canonical manifest](runs/t1-controlled-raster-ab-v1-canonical/canonical-manifest.json)
  — declared runtime, hashes, GO decision, reproducibility record.
- [T1 v1 snapshot](runs/t1-controlled-raster-ab-v1) — preserved, untouched.
- [spec/35 — Temporal Correspondence](../../spec/35-temporal-correspondence.md)
- [spec/36 — Temporal Identity Promotion](../../spec/36-temporal-identity-promotion.md)
- [spec/71 — Stable Artwork Representation Correspondence](../../spec/71-stable-artwork-representation-correspondence.md)
- [spec/82 — Explicit Authored Group Assembly](../../spec/82-explicit-authored-group-assembly.md)
- [Primitive toolchain example (047)](../../examples/047-fogleman-primitive-toolchain/README.md)
- [Primitive toolchain spec (83)](../../spec/83-fogleman-primitive-toolchain.md)
- [AGENTS.md](../../AGENTS.md) — repository invariants and scope discipline.
