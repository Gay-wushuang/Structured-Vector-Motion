# C-MVP v0.1 — Acceptance Criteria

Status: **DRAFT** — thresholds are PROPOSED until the C planning line freezes
them before holdout evaluation. A failed holdout MUST be reported as a failure;
thresholds MUST NOT be lowered afterwards.

Contract identity: `c-video-repair-contract@0.1`.

## 1. Acceptance principles

1. Acceptance is about the controlled synthetic clip, not general video repair.
2. The repair process never sees the clean reference. Scoring is a separate
   process.
3. Every metric has a fixed region, formula, unit, aggregation, and
   zero-denominator rule. Regions are declared before the run.
4. Lower temporal error alone is not success. Spatial fidelity, silhouette,
   motion, and unauthorized-region checks must also pass.
5. Lossless PNG comparisons are authoritative. MP4 is checked for playability
   and synchronization, not used for pixel metrics.
6. A `PARTIAL` run is a failure for acceptance, even if some frames improved.
7. No skipped video check may be reported as a pass. A missing encoder or
   decoder is a failure, not a skip.

## 2. Roles

| Role | Responsibility |
| --- | --- |
| User / C planning | confirm the visible result, the controlled-scope disclosure, and the final sign-off |
| Practice line | produce the run and its manifest |
| CI line | independently validate inputs, outputs, metrics, and export |
| Review line | inspect code, media, metrics, and boundary compliance |
| Docs line | freeze this contract and record the acceptance result |

CI MUST NOT import the practice implementation's scoring functions as its
oracle. CI implements the formulas below independently.

## 3. User acceptance conditions

A user-facing acceptance requires all of the following:

| ID | Condition |
| --- | --- |
| U1 | `before.mp4`, `after.mp4`, and `comparison.mp4` are playable and synchronized |
| U2 | The designated degradation is visibly reduced in the declared ROI in its single-degradation clip |
| U3 | The combined clip visibly improves in all four dimensions without a new visible artifact |
| U4 | The moving object keeps its silhouette and trajectory; no freeze, jump, or time shift |
| U5 | Pixels outside the declared protection domain are unchanged |
| U6 | The run is reproducible on the frozen environment |
| U7 | The report states "synthetic controlled experiment", lists limitations, and does not claim general video repair |
| U8 | The repair input does not contain the clean reference or ground truth |

Visual inspection is necessary but not sufficient; the metric and guard checks
below are also required.

## 4. Input format validation

The ingest/repair commands MUST validate the following before doing any work.

| ID | Check | Failure |
| --- | --- | --- |
| V01 | `contract_version == c-video-repair-contract@0.1` | `CVR-E001`, exit 2 |
| V02 | exactly 24 frames, contiguous `0000..0023` | `CVR-E002` / `CVR-E005`, exit 2 |
| V03 | every frame is 256 × 256 | `CVR-E003`, exit 2 |
| V04 | rational fps is exactly `12/1` | `CVR-E004`, exit 2 |
| V05 | RGB8, no alpha, no palette, no interlace | `CVR-E006`, exit 2 |
| V06 | every `file_sha256` and `pixel_sha256` matches | `CVR-E013`, exit 3 |
| V07 | no missing, duplicate, extra, or out-of-order frame | `CVR-E005`, exit 2 |
| V08 | masks are 256 × 256 grayscale8 with values `{0,255}` | `CVR-E008`, exit 2 |
| V09 | mask support is non-empty | `CVR-E009`, exit 2 |
| V10 | mask support is strictly smaller than the full frame | `CVR-E009`, exit 2 |
| V11 | mask support is contained in `repair_roi` | `CVR-E010`, exit 2 |
| V12 | `repair_roi` and `evaluation_roi` are valid half-open rectangles | `CVR-E007`, exit 2 |
| V13 | `feather_px` is an integer in `[0,8]` | `CVR-E011`, exit 2 |
| V14 | `clean_reference_in_input == false` and no eval path is reachable | `CVR-E014`, exit 3 |
| V15 | audio is absent or explicitly dropped and recorded | `CVR-E016`, exit 4 |
| V16 | frame rate is constant; no rotation metadata | `CVR-E017`, exit 4 |
| V17 | config has no unknown field or unsupported mode | `CVR-E018`, exit 4 |
| V18 | `spatial_fallback` is `null` | `CVR-E019`, exit 4 |
| V19 | the output directory does not contain a sealed run | `CVR-E012`, exit 2 |

Validation is fail-fast and atomic. A failed validation leaves no repaired
frames and no `SUCCESS` manifest.

## 5. Metric definitions

### 5.1 Notation

- `T = 24`, frames `t = 0..23`.
- `ref_t`, `in_t`, `out_t` are RGB8 frames.
- `c` ranges over `R, G, B`.
- `E` is the fixed `evaluation_roi` rectangle.
- `B` is the fixed static-background sample mask.
- `G` is the fixed declared trailing region.
- `I_t` is the fixed target-interior mask from the reference.
- `O_t` is the reference object silhouette.
- All means iterate `t` ascending, then `y` ascending, then `x` ascending, then
  `c` in `R,G,B` order. This fixed order is part of deterministic reporting.
- `|R|` denotes the number of pixels in a region `R`; `|I_t|` is the per-frame
  target-interior support.
- Units are 8-bit code values in `[0,255]`.
- Report each value with 6 decimal places.

### 5.2 M1 — ROI mean absolute error (local repair)

```text
MAE(X) = (1 / (T * |E| * 3)) * sum_t sum_{p in E} sum_c |X_t(p,c) - ref_t(p,c)|
I1     = 1 - MAE(out) / MAE(in)
```

- Primary clip: `S1`.
- Threshold: `I1 >= 0.30`.
- Zero-denominator rule: if `MAE(in) < 0.5`, the metric is `METRIC_UNDEFINED`
  and acceptance fails.
- The region `E` is fixed before the run and must cover the repaired area. It
  must not be cropped to easy pixels after seeing the result.

### 5.3 M2 — Flicker temporal error

The flicker metric measures the temporal variation of the reference error on a
static background sample set. It does not measure true object motion because
`B` excludes the moving object.

```text
e_t(X) = (1 / (|B| * 3)) * sum_{p in B} sum_c |X_t(p,c) - ref_t(p,c)|
F(X)   = (1 / (T - 1)) * sum_{t=1..23} |e_t(X) - e_{t-1}(X)|
I2     = 1 - F(out) / F(in)
```

- Primary clip: `S2`.
- Threshold: `I2 >= 0.30`.
- Zero-denominator rule: if `F(in) < 0.2`, the metric is `METRIC_UNDEFINED` and
  acceptance fails.
- Also report the full `e_t` series and `max_t |e_t - e_{t-1}|`. A lower mean
  does not excuse a single large spike.
- `B` must exclude the moving object and the ghost region by at least 2 pixels.

### 5.4 M3 — Ghost residual energy

The residual-energy metric ignores a 1-code-value rounding floor and measures
the remaining trailing error inside a pre-declared region.

```text
residual(X) = (1 / (T * |G| * 3)) * sum_t sum_{p in G} sum_c max(0, |X_t(p,c) - ref_t(p,c)| - 1)
I3          = 1 - residual(out) / residual(in)
```

- Primary clip: `S3`.
- Threshold: `I3 >= 0.30`.
- Zero-denominator rule: if `residual(in) < 1.0`, the metric is
  `METRIC_UNDEFINED` and acceptance fails.
- `|G|` is the number of pixels in `G`; the same region is used for input and
  output.
- Also report `max residual` and the count of pixels with residual greater
  than 8 code values.
- `G` is fixed by the fixture before the run and is not selected from the output.

### 5.5 M4 — Appearance temporal stability

```text
m_t,c(X) = mean_{p in I_t} X_t(p,c)
A(X)     = (1/3) * sum_c std_t(m_t,c(X))       # population std, denominator T
I4       = 1 - A(out) / A(in)

S(X)     = mean_t [ (1 / (|I_t| * 3)) * sum_{p in I_t} sum_c |X_t(p,c) - ref_t(p,c)| ]
Ee(X)    = mean edge-energy magnitude inside the object bounding box
```

- Primary clip: `S4`.
- Threshold: `I4 >= 0.30`.
- Zero-denominator rule: if `A(in) < 0.5`, the metric is `METRIC_UNDEFINED` and
  acceptance fails.
- Spatial guard: for `S4`, `S(out) <= 0.90 * S(in)`. For every other clip,
  `S(out) <= 1.05 * S(in)`.
- Blur guard: `Ee(out) / Ee(in) >= 0.90` inside the object bounding box.
  Edge energy is the mean forward-difference gradient magnitude:
  `sqrt((I(x+1,y)-I(x,y))^2 + (I(x,y+1)-I(x,y))^2)` with clamped borders.
- These two guards exist so that blurring or flat-filling cannot lower `A`.

### 5.6 Combined clip

For `S5`, all four metrics MUST improve:

```text
I1 >= 0.20, I2 >= 0.20, I3 >= 0.20, I4 >= 0.20
```

All four values MUST be strictly positive even if one is below the combined
threshold; a single non-improving dimension fails the combined clip.

### 5.7 Threshold table

| Clip | Metric | Threshold | Status |
| --- | --- | ---: | --- |
| `S1` | `I1` ROI MAE improvement | >= 0.30 | PROPOSED |
| `S2` | `I2` flicker temporal improvement | >= 0.30 | PROPOSED |
| `S3` | `I3` ghost residual improvement | >= 0.30 | PROPOSED |
| `S4` | `I4` appearance stability improvement | >= 0.30 | PROPOSED |
| `S5` | `I1..I4` each | >= 0.20 | PROPOSED |
| all | `S(out)` spatial error | per §5.5 | PROPOSED |
| all | `Ee` edge-energy ratio | >= 0.90 | PROPOSED |

The 30% single-degradation target comes from the C planning dispatch. The 20%
combined target and the spatial/edge guards are proposals until G1 freeze.

## 6. Spatial-quality tests

| ID | Check | Threshold | Notes |
| --- | --- | --- | --- |
| Q1 | unauthorized-region exact equality | 0 differing pixels | decoded RGB equality outside `protection_domain` |
| Q2 | silhouette IoU per frame | `>= 0.98` for every `t` | output object mask derived by the fixture's fixed color rule |
| Q3 | object centroid error | `<= 0.5 px` per frame | Euclidean distance |
| Q4 | frame-index match | best-match lag `0` for every frame | prevents time shift |
| Q5 | edge-energy ratio | `>= 0.90` in the object bbox | prevents blur |
| Q6 | spatial error `S(out)` | per §5.5 | prevents flat-fill |
| Q7 | changed pixels inside mask support and feather | reported, not hidden | required transparency |
| Q8 | changed pixels outside mask support but inside `protection_domain` | only allowed for declared photometric correction | must be reported |
| Q9 | pixels outside `protection_domain` | exactly equal to input | lossless PNG only |
| Q10 | no global frame replacement | changed fraction in `repair_roi <= max_changed_fraction` | default 0.25 |

`Q1` and `Q9` are the same check from two directions: decoded output pixels
outside the protection domain must be identical to the decoded input. PNG file
bytes may differ because of re-encoding; pixel equality is authoritative.

## 7. Temporal-consistency tests

| ID | Check | Threshold |
| --- | --- | --- |
| T1 | no added flicker in the static background | `std_t(mean_B(out)) <= std_t(mean_B(in)) + 0.2` |
| T2 | no new alternating pattern in `B` | `max_t mean_B(|out_t - out_{t-1}|) <= max_t mean_B(|in_t - in_{t-1}|) + 1.0` |
| T3 | no object time shift | centroid trajectory best-match lag `0`; per-frame centroid error `<= 0.5 px` |
| T4 | no freeze | per-frame object centroid is not constant across all 24 frames unless the reference is constant |
| T5 | no frame reordering | output frame `t` must not match reference `t-1` or `t+1` better than `t` under `E` MAE |
| T6 | flicker metric does not mistake motion for flicker | `B` is static and excludes the object/ghost by at least 2 px |
| T7 | first/last frame handling | frame 0 and frame 23 are either repaired with at least two valid observations or marked `UNRESOLVED`; no silent fallback |

A temporal improvement that freezes the object, shifts time, or blurs the
silhouette fails `T3`, `T4`, `T5`, or `Q2/Q5`.

## 8. Export-validity tests

| ID | Check | Expected |
| --- | --- | --- |
| X1 | repaired PNG count and names | exactly 24, contiguous `0000..0023` |
| X2 | repaired PNG format | RGB8, 256 × 256, no alpha |
| X3 | repaired PNG digests | match manifest `file_sha256` and `pixel_sha256` |
| X4 | `before.mp4` stream | 1 video, 0 audio, `h264`, `yuv420p`, 256×256 |
| X5 | `after.mp4` stream | 1 video, 0 audio, `h264`, `yuv420p`, 256×256 |
| X6 | `comparison.mp4` stream | 1 video, 0 audio, `h264`, `yuv420p`, 512×256 |
| X7 | frame count and rate | 24 frames, `12/1`, duration `2.0 ± 0.01 s` |
| X8 | decode pass | all 24 frames decode without error |
| X9 | alignment | all three MP4s have the same frame count, PTS range, and duration |
| X10 | `before.mp4` content | decodes to the input frames within MP4 tolerance |
| X11 | `after.mp4` content | decodes to the repaired frames within MP4 tolerance |
| X12 | manifest consistency | semantic digest recomputes; output digests match |
| X13 | no stale output | `run_id` matches inputs, config, algorithm, and code commit |
| X14 | playable result | a standard decoder plays the file to the end |

MP4 tolerance is proposed as MAE `<= 2.0` code values and PSNR `>= 40 dB`
against the source PNG sequence. The actual tolerance must be frozen by CI
before the holdout run.

## 9. Reproducibility tests

| ID | Check | Expected |
| --- | --- | --- |
| R1 | repeat run in the same frozen environment | identical PNG pixels and `pixel_sha256` |
| R2 | repeat run in the same frozen environment | identical `semantic_digest` |
| R3 | repeat run in the same frozen environment | metrics agree within `1e-9` |
| R4 | cross-platform PNG comparison | identical decoded pixels and `pixel_sha256` |
| R5 | cross-platform metrics | agree within `1e-9` |
| R6 | cross-platform MP4 | not byte-identical is acceptable; decode checks pass |
| R7 | run log and timestamps | never part of semantic identity |
| R8 | moved/removed eval directory | repair output is unchanged; isolation confirmed |

If a run uses unrecorded randomness, wall-clock time, locale, or a mutable
external resource, `R1`–`R3` fail and the run is not acceptable.

## 10. Failure scenarios and expected behavior

Every failure must produce a non-zero exit code, a stable diagnostic code, and
a user-readable message. The message must name the failing file or field but
must not leak the clean reference.

| Scenario | Exit | Diagnostic | Expected behavior |
| --- | ---: | --- | --- |
| missing frame | 2 | `CVR-E005` | no repair; list the missing index |
| wrong resolution | 2 | `CVR-E003` | no repair; state expected 256×256 |
| wrong frame rate | 2 | `CVR-E004` | no repair; state expected 12/1 |
| alpha or palette PNG | 2 | `CVR-E006` | no repair; state expected RGB8 |
| input hash mismatch | 3 | `CVR-E013` | no repair; identify the frame |
| clean reference in input | 3 | `CVR-E014` | no repair; isolation violation |
| mask wrong size | 2 | `CVR-E008` | no repair; identify the mask |
| mask values not 0/255 | 2 | `CVR-E008` | no repair; list the offending value |
| empty mask | 2 | `CVR-E009` | no repair |
| full-frame mask | 2 | `CVR-E009` | no repair; local repair contract |
| mask outside ROI | 2 | `CVR-E010` | no repair; state the ROI |
| invalid ROI | 2 | `CVR-E007` | no repair; state the half-open bounds |
| feather out of range | 2 | `CVR-E011` | no repair |
| audio present | 4 | `CVR-E016` | reject unless `--drop-audio` |
| VFR or rotation metadata | 4 | `CVR-E017` | reject |
| unknown algorithm/mode | 4 | `CVR-E018` | reject |
| spatial fallback requested | 4 | `CVR-E019` | reject |
| object-interior repair | 4 | `CVR-E020` | reject |
| insufficient neighbors | 5 | `CVR-E021` | mark `UNRESOLVED`, `PARTIAL` |
| flicker offset > 32 | 5 | `CVR-E022` | fail; do not clamp silently |
| ghost out of domain | 5 | `CVR-E023` | fail; explain the condition |
| changed fraction too high | 5 | `CVR-E024` | fail; report the fraction |
| FFmpeg missing | 6 | `CVR-E025` | fail; do not skip |
| encoder non-zero | 6 | `CVR-E026` | fail; preserve the command and stderr |
| output digest mismatch | 7 | `CVR-E027` | fail; no success manifest |
| ffprobe mismatch | 7 | `CVR-E028` | fail; report the stream facts |
| unauthorized pixel changed | 7 | `CVR-E029` | fail; report the count |
| stale output | 3 | `CVR-E013` | fail; require a new run directory |
| output directory has a sealed run | 2 | `CVR-E012` | fail; do not overwrite |
| internal error | 8 | `CVR-E030` | preserve diagnostics; no success claim |

Additional rules:

- A run with any `UNRESOLVED` frame is `PARTIAL` and fails acceptance.
- A run whose metrics are `METRIC_UNDEFINED` fails acceptance; it must not be
  reported as "no change needed".
- A run with a missing metrics file, a missing media file, or a missing
  manifest fails acceptance.
- Error messages must be stable enough for CI to assert on the diagnostic code,
  not on prose.

## 11. Holdout protocol

1. Development clips `S1`–`S5` may be used to calibrate the algorithm and to
   validate the metric implementation.
2. Holdout clips `H1`–`H5` are generated with the same fixture builder and a
   different seed. They are not used for algorithm tuning.
3. Thresholds and region definitions are frozen before the first holdout run.
4. The holdout is run once. A failure is reported with the raw metrics; it is
   not repaired by lowering a threshold.
5. If the development data shows a threshold is unreasonable, the practice line
   submits evidence to the C planning line before freeze. After freeze, no
   change is allowed without a new contract version.
6. Holdout results support only the synthetic controlled claim. They do not
   establish natural-video robustness.

## 12. Non-regression checks

The following must pass on the candidate commit, independently of the video
acceptance:

```powershell
python -m unittest discover -s tests -v
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m compileall -q svm tests
```

Also verify:

- no change under `svm/`, `schema/`, or `spec/` caused by the C track;
- Golden A and Golden B still pass;
- no existing test is skipped to hide a video failure;
- no threshold or policy is weakened.

A video-only change that breaks an existing Golden test is a regression and
cannot be accepted.

## 13. Sign-off checklist

| # | Item | Owner | Evidence |
| ---: | --- | --- | --- |
| 1 | Contract version and thresholds frozen | C planning | this document + freeze record |
| 2 | Input bundle validates | CI | validation log |
| 3 | Repair output is non-destructive | CI | `Q1`, `Q9`, `Q10` |
| 4 | Four metrics pass on single-degradation clips | CI | `metrics.json` |
| 5 | Combined clip passes | CI | `metrics.json` |
| 6 | Fidelity guards pass | CI | `Q2`–`Q6`, `T1`–`T7` |
| 7 | MP4s are playable and aligned | CI + review | `X1`–`X14` |
| 8 | Reproductibility passes | CI | `R1`–`R8` |
| 9 | Isolation confirmed | CI | moved/removed eval directory |
| 10 | SVM boundary respected | review | diff + `integration-boundary.md` |
| 11 | Limitations disclosed | docs + review | run manifest + report |
| 12 | Final verdict recorded | C planning | PASS / CHANGES_REQUIRED / BLOCKED |

## 14. Final verdict rule

- **PASS** requires every required artifact, metric, guard, export check,
  reproducibility check, and non-regression check to pass.
- **CHANGES_REQUIRED** is used when the implementation or its evidence has a
  defect that the owner must fix.
- **BLOCKED** is used when missing media, a missing tool, or missing evidence
  makes a judgment impossible.
- A PASS for the synthetic controlled clip is not a claim of general video
  repair capability.
