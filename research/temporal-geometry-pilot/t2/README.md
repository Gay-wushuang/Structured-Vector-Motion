# T2-P1 — Method C: Author-Anchored Group Motion

Status: **IMPLEMENTED / RESULT: STOP / RESEARCH-ONLY / NOT SVM EVIDENCE / NOT FROZEN**.

This directory is the T2-P1 implementation of Method C, run against the
[T2-P0A protocol freeze](../T2-P0A-PROTOCOL-FREEZE.md) (committed at
`111ac6b`, branch `research/t2-p0a-protocol-freeze`). T2-P0A supersedes the
earlier [T2-P0 design](../T2-GROUP-ANCHOR-EXPERIMENT.md) wherever they differ.

| Field | Value |
| --- | --- |
| Work order | T2-P1 — Method C implementation and evaluation |
| Repository | `Gay-wushuang/Structured-Vector-Motion` |
| Baseline HEAD at run | `111ac6b` (`research/t2-p0a-protocol-freeze`) |
| T1 canonical reference | `40b5f65` — T1.1 canonical snapshot (**UNCHANGED**) |
| Protocol | T2-P0A §3–§8; thresholds frozen before the first run |
| Runtime | Python 3.12.5, NumPy 2.5.4, OpenCV 4.14.0 (wheel 4.14.0.94) |
| Aggregate decision | **STOP** — F2 B control abstained under the frozen LK gate |
| Authority | None: no Document, Revision, Entity, Group, Track, Keyframe, TemporalIdentity, MotionTargetBinding, ChangeAuthority, schema, or spec change |

The independent verification of the statement above is in the
[canonical manifest](runs/t2-canonical/canonical-manifest.json), which lists
every artifact hash, the T1 hash check, the environment wheel hashes, and the
full aggregate decision.

---

## 1. What is implemented

| Path | Purpose |
| --- | --- |
| [`generate_fixtures.py`](generate_fixtures.py) | deterministic five-fixture generator, primary/witness assignment, `--check` mode |
| [`fixtures/`](fixtures) | 20 PNG frames + 5 `ground-truth.json` files (checked in) |
| `experiment-f1.json` … `experiment-f5.json` | closed runtime configs with frozen limits, budgets, and gates |
| [`runtime.py`](runtime.py) | isolated, **GT-free** Method B/C worker; validity, conflict, bounds, abstention |
| [`gt_eval.py`](gt_eval.py) | offline GT validation, metrics, fail-closed/quality evaluation, decision grammar, overlays |
| [`run_t2.py`](run_t2.py) | orchestrator: two isolated full runs per fixture, raw-before-GT ordering, manifests, canonical snapshot |
| [`tests/test_t2_contract.py`](tests/test_t2_contract.py) | 15 focused contract tests |
| `runs/` | five v1 run directories plus the canonical snapshot |

Method C remains exactly the T2-P0A contract:

1. one explicit **primary anchor** and at least one independent **witness**;
2. labels, membership, and anchor points are author inputs at frame 0;
3. per-anchor LK tracking and one similarity fit per anchor;
4. per-anchor validity: valid count/ratio, median LK error, spread/planarity,
   affine residual, finite/non-reflected matrix, and scale/rotation/translation
   bounds;
5. primary/witness conflict on RMS, rotation, and scale ratio;
6. the primary transform is the only pose source; witnesses are veto-only;
7. the cumulative transform is composed and applied to every member's frozen
   frame-0 geometry; no per-member refinement, averaging, failover, or re-anchor;
8. any failure abstains the whole group with the frozen precedence and makes
   the remainder sticky.

Method B is a new multi-member run on the same fixtures: per-member boundary
sampling at 8 px, per-member LK and similarity fit, step application to current
geometry, and group status `SUPPORTED` only when every member is supported;
otherwise `ABSTAINED / MEMBER_LOST`, sticky. T1-B numbers are not used.

### 1.1 Runtime / GT separation

The runtime config has **no ground-truth path** and no GT field. `runtime.py`
does not import `gt_eval`, does not define or call a GT loader, and never reads
the fixture's `ground-truth.json`. `run_t2.py` writes `raw/method-b.json` and
`raw/method-c.json` before `gt_eval.load_ground_truth()` is called. The tests
prove all four properties:

- a copied fixture with no `ground-truth.json` produces byte-identical raw output;
- a corrupted `ground-truth.json` produces byte-identical raw output;
- raw files exist before the GT loader is invoked;
- `runtime.py` contains no GT loader import or call.

---

## 2. Fixtures

All frames are 512×512 8-bit grayscale, values exactly `{0, 255}`, ticks
0/12/24/36, drawn with `cv2.fillPoly(..., LINE_8)` on integer-rounded vertices
with no antialiasing. Ground truth stores the exact float vertices.

| Fixture | Motion | Primary anchor | Witness anchor | Special condition |
| --- | --- | --- | --- | --- |
| F1 | translation `(12k, -6k)` | body boundary (16 pts) | sat-a boundary (16 pts) | none |
| F2 | cumulative rotation `8k°`, scale `1.04^k`, translation `(4k, -2k)` about `(256,256)` | body boundary (16 pts) | sat-a boundary (16 pts) | none |
| F3 | F1 translation | body bottom edge (16 pts, collinear) | sat-a bottom edge (16 pts, collinear) | aperture / low texture |
| F4 | F1 translation | body boundary (16 pts) | sat-a boundary (16 pts) | occluder `(230,175)-(360,345)` at frame 1 only; covers 10/16 primary points |
| F5 | body group `(12k, -6k)`; decoy `(-10k, 8k)` | body boundary (16 pts) | decoy boundary (16 pts) | conflicting anchor motion |

The generator asserts every fixture property the protocol requires: no
out-of-canvas points, pairwise-disjoint members in every frame, witness
independence, degeneracy of the F3 anchors, F4 coverage of at least 8/16
primary points, and F5 conflict above 2 px. `--check` regenerates every PNG and
GT byte in memory and fails on any mismatch. The generator is deterministic,
and the committed fixture bytes are canonical under the declared runtime. The
rasterization is version-sensitive: under OpenCV 4.10 one F2 frame
(`tick_012.png`) rounds one pixel differently from the declared 4.14.0.94, so
fixture byte checks and the full experiment are declared-runtime-only.

---

## 3. Frozen gates and metric definitions

All gates are copied from T2-P0A §6–§8 into every config and must exactly match
the constants in `runtime.py`; the loader rejects any edit. Config, limit,
budget, and threshold hashes are recorded in every run manifest. No threshold,
fixture, or assertion was changed after the first run.

Definitions used by the metric code:

- `group_iou`: union of predicted member masks vs union of GT member masks.
- `mean_group_vertex_rmse_px`: mean over supported frames of the mean ordered
  vertex RMSE (minimum over cyclic shifts and both orientations).
- `final_group_drift_px`: `||(pred_group_centroid_t - pred_group_centroid_0) -
  (gt_group_centroid_t - gt_group_centroid_0)||` at the final supported frame.
- `group_step_jitter_mean`: second difference of per-transition
  `[tx, ty, θ, scale]` for the group step, then mean. C uses its estimated step;
  B uses a least-squares similarity derived from member centroids (diagnostic
  only, per T2-P0 §8.1).
- `member_step_jitter_mean`: the same second difference on each member's own
  fitted step, averaged over members and transitions.
- `rigidity_error_px`: mean absolute change of pairwise predicted
  member-centroid distances relative to the frame-0 predicted geometry.
- `abstention_rate`: abstained frames / 4.

For F1/F2, the relative-to-B RMSE/drift clauses activate only when B is at or
above the declared bands (0.50 px / 0.10 px). The jitter clause uses
`0.50 × B`/`0.60 × B` when B is at or above 0.05, otherwise the absolute 0.05
fallback. A failed numeric gate's relative miss is
`(required-observed)/|required|` for lower bounds and
`(observed-required)/|required|` for upper bounds; a missing observation counts
as 1.0. This definition is in the config and is hashed.

`metrics.json` deliberately does **not** contain the aggregate decision: the
cost gate uses measured wall time, while `metrics.json` must be byte-identical
across repeated runs. The aggregate decision is written to
`run-manifest.json` and the canonical manifest.

---

## 4. Result: STOP

### 4.1 Aggregate decision

```json
{
  "outcome": "STOP",
  "stop_reasons": [
    "F2-ROTATION-SCALE_B_CONTROL_ABSTAINED",
    "F2-ROTATION-SCALE_QUALITY_STOP"
  ],
  "conditional_reasons": ["F4-OCCLUSION_CONDITIONAL"],
  "unresolved_limits": ["F3_INCONCLUSIVE", "F4_ABSTENTION_REASON_DIFFERS"],
  "cost_ratio_c_over_b": 0.7543074569042967,
  "full_run_byte_identical": true,
  "environment_ok": true
}
```

STOP is evaluated first and overrides GO/CONDITIONAL. The primary cause is the
frozen control rule in T2-P0A §7/§8: **B abstained on F2**, so the F2 control is
invalid and C cannot be credited on rotation/scale. F2 therefore also fails its
quality gates. Independently, F4 is `CONDITIONAL` (fail-closed, but not with one
of the two accepted F4 reasons), which would also block GO. F3 is
`INCONCLUSIVE` because both B and C abstained on the hard frame; the protocol
allows GO with an inconclusive F3, but the result is reported as an unresolved
limit. F5 passes its fail-closed gate.

The full decision object, per-gate checks, and hashes are in
[`runs/t2-canonical/canonical-manifest.json`](runs/t2-canonical/canonical-manifest.json)
and each run's `run-manifest.json`.

### 4.2 Per-fixture outcome

| Fixture | B supported | C supported | B first reason | C first reason | B gate | C gate | Fixture outcome |
| --- | ---: | ---: | --- | --- | --- | --- | --- |
| F1 translation | 4/4 | 4/4 | — | — | control valid | all quality gates pass | **PASS** |
| F2 rotation+scale | 1/4 | 1/4 | `MEMBER_LOST` | `LK_QUALITY_TOO_LOW` | **invalid control** | quality STOP | **STOP** |
| F3 low texture | 1/4 | 1/4 | `MEMBER_LOST` | `PRIMARY_ANCHOR_LOST` | measured only | fail-closed | **INCONCLUSIVE** |
| F4 occlusion | 1/4 | 1/4 | `MEMBER_LOST` | `LK_QUALITY_TOO_LOW` | measured only | fail-closed, wrong reason | **CONDITIONAL** |
| F5 conflict | 4/4 | 1/4 | — | `ANCHOR_CONFLICT` | measured only | fail-closed | **PASS** |

"Supported 1/4" means only the identity frame 0 was supported; the metric means
for those methods are frame-0-only and are **not** sequence quality evidence.
They are retained in `metrics.json` with `supported_frame_count` for
transparency, not reported as a C win.

### 4.3 F1: gates pass, but the comparative hypothesis is not supported

F1 is the only fixture where both methods ran all four frames. All eight frozen
C quality gates pass. The measured values, however, do **not** show the
T2-P0 hypothesis that one anchored group transform gives lower error, drift,
and jitter than per-member propagation:

| Metric | B (control) | C (treatment) | Frozen gate | Gate result |
| --- | ---: | ---: | --- | --- |
| mean group IoU | 1.000000 | 1.000000 | C ≥ 0.990 | pass |
| mean member IoU | 1.000000 | 1.000000 | C ≥ 0.985 | pass |
| mean group vertex RMSE | 0.0000687 px | 0.0008004 px | C ≤ 0.75 px (B < 0.50, relative clause inactive) | pass |
| final group drift | 0.0000462 px | 0.0011950 px | C ≤ 0.30 px (B < 0.10, relative clause inactive) | pass |
| group step jitter | 0.0002198 | 0.0083580 | B < 0.05 → C ≤ 0.05 | pass |
| rigidity error | 0.0000292 px | 0.0008641 px | C ≤ 0.10 px | pass |
| abstention | 0/4 | 0/4 | C = 0 | pass |
| tracked points/transition | 123 | 32 | — | — |

On this fixture B is already essentially exact: the frozen relative clauses do
not activate because B is far below 0.50 px RMSE, 0.10 px drift, and 0.05
jitter. As a result the gate pass does not establish "C beats B"; on the raw
numbers B is better on RMSE (≈11.6×), drift (≈25.9×), and group jitter (≈38×).
C still produces accurate geometry (sub-0.001 px RMSE, IoU 1.0) with roughly a
quarter of the tracked points, but the experiment cannot claim a quality
benefit. This is a substantive result independent of the F2 control failure.

### 4.4 F2: the frozen LK quality gate invalidates the control

At the first transition:

| Method/member | valid tracks | median LK error | result |
| --- | ---: | ---: | --- |
| B body | 67/67 | 9.655 | `LK_QUALITY_TOO_LOW` |
| B sat-a | 28/28 | 10.399 | `LK_QUALITY_TOO_LOW` |
| B sat-b | 28/28 | 10.594 | `LK_QUALITY_TOO_LOW` |
| C body anchor | 16/16 | 9.588 | `LK_QUALITY_TOO_LOW` |
| C sat-a anchor | 16/16 | 10.122 | `LK_QUALITY_TOO_LOW` |

The frozen ceiling is `max_median_lk_error_px = 8.0` (T2-P0A §3.4/§6). Both
methods therefore abstain. B's whole-group `MEMBER_LOST` makes the control
invalid under §7/§8; C's own abstention is fail-closed but cannot be scored as
a quality win. The gate is not adjusted after the fact. Note the frozen field
is named `_px`, while the value used here is the raw OpenCV LK patch error
(the same field T1 recorded as `median_lk_error`); that unit ambiguity is a
protocol limitation recorded in §9.

### 4.5 F3/F4/F5 fail-closed behavior

- **F3 (low texture).** C's primary anchor retains only 4/16 valid tracks
  (`PRIMARY_ANCHOR_LOST`); the witness is collinear and fails
  `ANCHOR_DEGENERATE` (spread `4.1e-5`, planarity `6.6e-12`). B loses its body
  member (`MEMBER_LOST`). Both methods abstain on the hard frame, so the
  protocol says **INCONCLUSIVE**, not a C success.
- **F4 (occlusion).** The occluder covers 10/16 primary anchor points, but LK
  reports 15/16 tracks `valid`; the median LK error is 27.29 px, so the
  occlusion is caught by `LK_QUALITY_TOO_LOW` rather than the count gate. The
  group abstains at frame 1 and stays sticky, which is fail-closed. Because the
  reason is not `PRIMARY_ANCHOR_LOST` or `INSUFFICIENT_VALID_ANCHOR_TRACKS`,
  the frozen protocol classifies F4 as **CONDITIONAL**, and it blocks GO.
- **F5 (conflicting anchors).** The primary body and witness decoy disagree by
  RMS 26.076 px (rotation difference ≈0.0001°, scale ratio ≈1.1e-7), far above
  the 2.0 px / 2.0° / 0.02 thresholds. C abstains with `ANCHOR_CONFLICT` at
  frame 1 and stays sticky. **PASS**. B, which has no anchor or group claim,
  tracks all four members independently (group IoU 1.0) while its group
  rigidity error is 10.353 px and its derived group jitter is 0.284; that is
  the expected contrast, not a B failure.

### 4.6 Cost

Cost is measured inside each isolated worker after frame loading. The frozen
gate is aggregate `C/B` wall time over all five fixtures (the operationalization
chosen before the run; T2-P0A does not specify aggregate vs per-fixture):

| Fixture | B seconds | C seconds | C/B |
| --- | ---: | ---: | ---: |
| F1 | 0.021610 | 0.020190 | 0.934 |
| F2 | 0.014511 | 0.012042 | 0.830 |
| F3 | 0.013672 | 0.010731 | 0.785 |
| F4 | 0.014361 | 0.011810 | 0.822 |
| F5 | 0.025743 | 0.013036 | 0.506 |
| **total** | **0.089897** | **0.067810** | **0.754** |

The aggregate passes `≤ 1.00 × B`. In this run C is also cheaper on F1 (0.934),
where both methods run all four frames. Timing is a single measurement on one
machine with visible run-to-run variation, and C's early abstention on F2–F5
reduces the work it performs; this is an indicative cost, not a benchmark.

### 4.7 Determinism and reproducibility

- Two isolated full runs per fixture: `raw/method-b.json`,
  `raw/method-c.json`, and `metrics.json` are byte-identical for all five
  fixtures.
- Downstream metric derivation, rendered frames, and decoded comparison video
  are identical in both runs.
- The canonical snapshot copies the first run of each fixture; every file hash
  is listed in the canonical manifest and was re-verified.
- T1 canonical files match their recorded SHA-256 values; no `t1-*` path was
  written. The manifest records `t1_snapshot: UNCHANGED` for every run.

---

## 5. A/B/C comparison scope

The task asked for A/B/C. The frozen protocol explicitly does **not** run
Method A for T2 (T2-P0 §7.1; T2-P0A §3.1 says T2-B must be a new multi-member
run and cannot reuse T1-B). Method A in T1 is a single five-vertex primitive on
`examples/035-controlled-raster-recovery`; the T2 fixtures are multi-member
scenes. Substituting T1-A numbers would be invalid, and adding an A arm on T2
fixtures would be a new method definition outside the frozen protocol.

For historical context only, the T1.1 canonical result is:

| T1 method | mean IoU | mean GT vertex RMSE | final drift | abstention | fixture |
| --- | ---: | ---: | ---: | ---: | --- |
| A (per-frame independent primitive) | 1.000000 | 0.2524 px | 0.1212 px | 0.0 | single primitive, `035` |
| B (first-frame LK propagation) | 0.980505 | 1.9863 px | 0.9517 px | 0.0 | single primitive, `035` |

These numbers are **not comparable** to T2's B/C numbers and are not presented
as a T2 result. A proper A/B/C comparison would require a separately authorized
T2-A arm and a new experiment ID.

---

## 6. Verification commands

Run from the repository root, with the declared wheels unpacked outside the
repository and selected through `PYTHONPATH`
(`numpy-2.5.4` SHA-256 `a7b1b635…3fa223a`, `opencv-python-headless-4.14.0.94`
SHA-256 `cbed6541…1dc64b`, both recorded in the canonical manifest and the T1.1
manifest):

```powershell
python research/temporal-geometry-pilot/t2/generate_fixtures.py --check
python research/temporal-geometry-pilot/t2/run_t2.py --all --force
python -m unittest discover -s research/temporal-geometry-pilot/t2/tests -v
python -m unittest discover -s research/temporal-geometry-pilot/tests -v
```

Measured:

- T2 contract tests: `Ran 15 tests ... OK` (declared runtime, ≈9 s in the
  recorded run). Outside the declared runtime the two frozen-LK outcome tests
  are skipped and fixture byte comparison is limited to in-memory determinism,
  because rasterization and LK numerics are version-sensitive.
- T1 pilot tests: `Ran 5 tests ... OK` (0.750 s, declared runtime); also pass
  under the default 4.10.0 runtime.
- Fixture `--check`: all five fixtures byte-identical and generator-deterministic.
- Full run: five fixtures, two isolated runs each, canonical snapshot written.

---

## 7. Limitations

1. **F2 control failure is a real STOP signal**, not a C quality result. The
   frozen LK error gate (8.0) is exceeded by both methods on the rotation+scale
   fixture. No threshold or fixture was edited to avoid this.
2. **The LK error unit is ambiguous.** T2-P0A names the field
   `max_median_lk_error_px`; the implementation uses OpenCV's raw LK patch
   error, matching T1's `median_lk_error`. A future protocol must define this
   precisely before use.
3. **F1 does not support the comparative hypothesis.** Gates pass only because
   B is already below the relative-clause bands; C is worse on RMSE, drift, and
   group jitter, though all values are far below the absolute ceilings.
4. **F4 abstains for a different reason than the one accepted by the frozen
   F4 gate** (`LK_QUALITY_TOO_LOW` vs `PRIMARY_ANCHOR_LOST` /
   `INSUFFICIENT_VALID_ANCHOR_TRACKS`), so the protocol classifies it
   CONDITIONAL even though the behavior is fail-closed.
5. **F3 is INCONCLUSIVE**: both methods lose the low-texture frame.
6. **Cost is measured, not benchmarked**: aggregate C/B is 0.754 (F1-only
   0.934). Single-run timings vary visibly between repeats, and C abstains
   early on F2–F5, reducing its work; no stable performance claim is made.
7. **Descriptive only**: five synthetic fixtures, one group, four frames, no
   random seed, no confidence intervals; no general or causal claim.
8. **Rasterization and LK numerics are OpenCV-version-sensitive.** The committed
   fixtures are canonical under the declared 4.14.0.94 runtime; OpenCV 4.10
   rounds one F2 frame differently. The frozen-LK outcome tests are skipped
   outside the declared runtime.
9. **No SVM Evidence and no authority**: these are offline experimental
   outputs. They do not create or modify a Document, Revision, Entity, Group,
   Track, Keyframe, TemporalIdentity, MotionTargetBinding, ChangeAuthority,
   schema, Golden, or frozen specification.

---

## 8. What STOP means

`STOP` is the protocol-required outcome when the F2 control is invalid. It
means:

- Method C is **not** credited with a rotation/scale result;
- the frozen experiment cannot produce a GO or CONDITIONAL "C works" claim;
- the F1 result is independently informative: the anchored group transform is
  accurate but not better than per-member propagation on these frames;
- the fail-closed behavior on F3/F4/F5 is safe but does not establish
  correctness or recovery.

Any follow-up requires a **new versioned protocol** (new experiment ID), not an
edit to T2-P0A or these runs. Candidate directions, listed as open questions
rather than approved fixes:

- define the LK quality gate in an unambiguous geometric unit;
- add a textured or antialiased rotation+scale fixture;
- authorize a T2-A arm on the same fixtures;
- separately specify re-anchoring (currently a STOP condition, not a feature).

Do not tune thresholds, fixtures, or assertions after seeing these results.

---

## 9. Artifacts

| Artifact | Description |
| --- | --- |
| [`runs/t2-canonical/canonical-manifest.json`](runs/t2-canonical/canonical-manifest.json) | canonical decision, environment/wheel hashes, T1 check, every file hash |
| `runs/t2-f1-translation-v1/` | F1 raw B/C, metrics, costs, reproducibility, comparison video, manifest |
| `runs/t2-f2-rotation-scale-v1/` | F2 (control-invalid) artifacts |
| `runs/t2-f3-low-texture-v1/` | F3 (inconclusive) artifacts |
| `runs/t2-f4-occlusion-v1/` | F4 (conditional) artifacts |
| `runs/t2-f5-conflicting-anchors-v1/` | F5 (conflict pass) artifacts |
| `runs/t2-canonical/` | byte-for-byte copies of the five first runs |

Each `comparison.avi` is a lossless FFV1 1536×512 three-panel overlay: source/GT,
B, and C, with GT outlines, predicted member outlines, and status/reason labels.
