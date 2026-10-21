# T2-P0A — Protocol Freeze: Method C vs B Acceptance Contract

Status: **FROZEN / RESEARCH-ONLY / NOT SVM EVIDENCE / NOT A GOLDEN**.

| Field | Value |
| --- | --- |
| Baseline HEAD | `24441f1` (`codex/primitive-toolchain`) |
| T1 canonical reference | `40b5f65` |
| Date | 2026-10-21 |
| Scope | docs-only protocol freeze; no Method C implementation |
| Supersedes | ambiguous B/C, anchor, threshold, and runtime/GT rules in [T2-GROUP-ANCHOR-EXPERIMENT.md](T2-GROUP-ANCHOR-EXPERIMENT.md) |
| Decision | Protocol: **GO**; T2-P1 implementation: **CONDITIONAL GO**; Core/authority: **STOP** |

---

## 1. Purpose and precedence

This document closes the protocol ambiguities left by T2-P0 before any Method C
implementation or experiment run. It is the acceptance contract for T2-P1.

Rules of precedence:

1. This freeze wins over the T2-P0 design wherever the two differ.
2. The frozen five-fixture set and the research-only boundary remain in force.
3. Nothing here authorizes a Document, Revision, Group, Track, Keyframe,
   `TemporalIdentity`, `MotionTargetBinding`, `ChangeAuthority`, schema, spec,
   CI, or Golden change.
4. A T2 result is never SVM Evidence and never establishes Group or
   TemporalIdentity authority.

The five fixtures remain exactly the five scenarios already defined:

| Fixture | Scenario | Primary purpose |
| --- | --- | --- |
| F1 | coherent translation | quality comparison |
| F2 | rotation + uniform scale | quality/rigidity comparison |
| F3 | low-texture / straight edge | fail-closed behavior |
| F4 | temporary occlusion | fail-closed behavior |
| F5 | conflicting anchor motion | conflict detection |

---

## 2. Baseline verification

### 2.1 Repository state

At the start of this freeze:

- Branch: `codex/primitive-toolchain`
- HEAD: `24441f1`
- Tracked working tree: clean (`git status --porcelain` has no tracked entries)
- `T2-GROUP-ANCHOR-EXPERIMENT.md`: **untracked** at the start of this task
- `40b5f65` is an ancestor of `HEAD`

Because the T2-P0 design was untracked, this freeze commit tracks both documents:
the T2-P0 design (as the historical design) and this frozen protocol. No other
file is part of the commit.

Eight unreadable `pip-*` directories exist in the repository root as environment
artifacts. They are outside the experiment read set and are not touched.

### 2.2 T1 canonical snapshot

The T1.1 canonical snapshot at `40b5f65` is unchanged:

- `git diff 40b5f65 -- research/temporal-geometry-pilot` is empty for tracked
  T1 content.
- The seven files listed by
  [the canonical manifest](runs/t1-controlled-raster-ab-v1-canonical/canonical-manifest.json)
  still match their SHA-256 values:

| File | SHA-256 prefix |
| --- | --- |
| `raw/method-a.json` | `0cd54a3c…b78a19aa` |
| `raw/method-b.json` | `72ee8bea…97194ba6` |
| `metrics.json` | `2e51cf62…0601f0af` |
| `costs.json` | `502e5bb6…b8f4aa91` |
| `reproducibility.json` | `e537dcca…de2c0382` |
| `comparison.avi` | `9757c2a7…e1567a1` |
| `run-manifest.json` | `05e2013a…2f07eee` |

- The v1 snapshot remains preserved, untouched, and `CONDITIONAL`.
- No T2 run may overwrite, rewrite, or append to `runs/t1-*`.
- T1-B is a single-primitive run on `035-controlled-raster-recovery`; it is not
  T2-B and is not a comparison baseline for T2 (see §3.1).

### 2.3 Golden 047 / Spec 83

At `24441f1`:

- `examples/047-fogleman-primitive-toolchain/` exists;
- `spec/83-fogleman-primitive-toolchain.md` exists.

Consequences:

- T2 adds **no Golden** and **no spec**.
- This freeze does not migrate, rename, or reuse 047 or 83.
- The Spec 82 G4 Golden remains a separate, pending G4 Gate. If authorized
  later, it starts at `examples/048-*` unless the primitive-toolchain owner
  deliberately renames its example.
- A future T2-adjacent normative spec starts at `spec/84` only after separate
  authorization.

---

## 3. Frozen B/C contract

### 3.1 T2-B must be a new multi-member run

T2-B is **not** the T1-B result and **must not** reuse T1-B numbers.

| Rule | Requirement |
| --- | --- |
| Fixture set | T2-B runs on the same five multi-member fixtures as T2-C |
| Frame set | ticks 0/12/24/36 on the fixture's 512×512 frames |
| Member geometry | the exact frozen frame-0 member vertices used by C |
| Boundary sampling | per member, 8.0 px spacing, start-inclusive/end-exclusive |
| Tracking | per member, opencv LK with the §4.2 parameters |
| Transform | per member, one similarity from that member's valid tracks |
| Application | step transform applied to the member's current geometry |
| Group status | `SUPPORTED` only if **every** member is `SUPPORTED`; otherwise group `ABSTAINED / MEMBER_LOST` and sticky |
| Anchors | B uses none |
| GT | never used by B runtime |

Any table, report, or comparison that substitutes T1-B single-primitive metrics
for T2-B is **invalid**. T1-B may appear only as historical context, clearly
labelled as a different fixture and different member set.

### 3.2 T2-C contract

C receives:

- the same frozen frame-0 member vertices;
- exactly one **Primary Anchor**;
- at least one **Independent Witness Anchor**;
- no per-member flow, no automatic anchor selection, no GT.

C runtime:

1. tracks the primary and every witness;
2. validates every anchor;
3. estimates one similarity per anchor;
4. checks primary/witness conflict;
5. uses the primary transform as the pose;
6. applies the cumulative transform to every member's frame-0 geometry;
7. never refines per-member geometry.

C may be `SUPPORTED` only when all of §4 is true for every declared anchor and
every member. Otherwise it abstains and remains sticky.

C never averages anchors, never chooses a successful anchor, never falls back
from a failed primary to a witness, and never refines a member independently.
Those are different methods and are out of scope.

### 3.3 Shared observation inputs

| Input | Frozen value |
| --- | --- |
| Frames | 512×512, 8-bit grayscale, values exactly `{0, 255}` |
| Ticks | 0, 12, 24, 36; 12 ticks/s |
| Foreground | pixels `<= 127` |
| Member geometry | explicit frame-0 vertex lists from the fixture |
| Runtime input | frames + frame-0 members + anchors only |
| GT input | offline metric phase only; never available to B/C runtime |
| Rasterization | `cv2.fillPoly`, `LINE_8`, integer-rounded vertices, no antialiasing |

### 3.4 Shared LK and affine parameters

B and C must use exactly the same values. A B/C difference may not come from a
different parameter.

| Parameter | Frozen value |
| --- | ---: |
| `lk_window` | `[31, 31]` |
| `lk_pyramid_max_level` | `3` |
| `lk_max_iterations` | `30` |
| `lk_epsilon` | `0.01` |
| `lk_min_eigen_threshold` | `0.0001` |
| `affine_estimator` | `LMEDS` |
| `affine_refine_iterations` | `10` |
| `boundary_sample_spacing_px` | `8.0` |
| `max_median_lk_error_px` | `8.0` |
| `max_median_affine_residual_px` | `2.0` |

### 3.5 Transform computation

For a set of tracked point pairs `(p_i, q_i)`, B and C use
`cv2.estimateAffinePartial2D(..., method=cv2.LMEDS, refineIters=10)`.

The matrix is interpreted as:

```text
q = [[a, b, tx], [c, d, ty]] · [x, y, 1]^T
scale = sqrt(a² + c²)
rotation_degrees = atan2(c, a)
translation = (tx, ty)
```

Required checks on every estimated step transform:

- finite entries;
- `det = a*d - b*c > 0` (no reflection);
- `0.5 <= scale <= 2.0`;
- `|rotation_degrees| <= 15.0`;
- `sqrt(tx² + ty²) <= 64.0`.

B applies the step to current member points. C composes the step onto a
cumulative transform and applies the cumulative transform to frame-0 member
points. Both are deterministic and recorded.

### 3.6 Irreducible confounds

These cannot be eliminated by the protocol and must be reported with every
result:

- different runner CPU, OS image, and runner image version;
- Python/OpenCV/NumPy version differences;
- one run per environment, no repeated-measures distribution;
- rasterization/rounding at integer vertices;
- author choice of anchor points and witness placement;
- synthetic flat-fill frames with no texture;
- one group, one subject, no multi-group or cross-subject case;
- no member deformation, camera, video, or semantic recognition;
- B and C differ by construction in what they can represent: B can follow
  per-member motion, C is rigid by construction.

Consequences: a T2 PASS is descriptive evidence on five controlled fixtures,
not a general claim and not a causal Python/OS comparison. A T2 B/C difference
cannot be generalized beyond these fixtures.

---

## 4. Anchor contract

### 4.1 Declarations

Every C run must declare:

| Field | Requirement |
| --- | --- |
| `primary_anchor_id` | exactly one; defines the pose |
| `witness_anchor_ids` | at least one; veto only |
| `primary.member_id` | one of the declared members |
| `witness.member_id` | a different member from the primary |
| `points` | frame-0 pixel coordinates, at least 8, distinct, inside canvas |
| predeclaration | fixed in the config before the first run; never edited afterward |

Witness independence:

- it must be on a different member than the primary;
- its point set must not share exact coordinates with the primary;
- at least 50% of its points must be at least 8 px away from every primary
  point;
- it must be declared at frame 0, not discovered later.

A witness never becomes a second pose source. It can only veto.

Frozen fixture assignments:

| Fixture | Primary | Independent witness |
| --- | --- | --- |
| F1 | body boundary | sat-a boundary |
| F2 | body boundary | sat-a boundary |
| F3 | body bottom edge | sat-a bottom edge |
| F4 | body boundary | sat-a boundary |
| F5 | body boundary | decoy boundary |

The fixture generator must emit the exact primary and witness point lists into
`ground-truth.json`; the runtime config copies those exact lists.

### 4.2 Per-anchor validity

At each transition, for every declared anchor:

| Check | Threshold | Failure reason |
| --- | ---: | --- |
| valid tracked points | `>= 8` | `INSUFFICIENT_VALID_ANCHOR_TRACKS` |
| valid ratio | `>= 0.75` | `INSUFFICIENT_VALID_ANCHOR_TRACKS` |
| median LK error | `<= 8.0 px` | `LK_QUALITY_TOO_LOW` |
| median affine residual | `<= 2.0 px` | `ANCHOR_RESIDUAL_TOO_HIGH` |
| anchor spread `sqrt(λ2)` | `>= 4.0 px` | `ANCHOR_DEGENERATE` |
| anchor planarity `λ2 / λ1` | `>= 0.02` | `ANCHOR_DEGENERATE` |
| matrix finite | required | `ANCHOR_FIT_FAILED` |
| determinant | `> 0` | `ANCHOR_FIT_FAILED` |
| scale | `[0.5, 2.0]` | `TRANSFORM_OUT_OF_BOUNDS` |
| step rotation | `<= 15.0°` | `TRANSFORM_OUT_OF_BOUNDS` |
| step translation | `<= 64.0 px` | `TRANSFORM_OUT_OF_BOUNDS` |

`λ1 >= λ2 >= 0` are the eigenvalues of the 2×2 covariance of the anchor
points. `sqrt(λ2)` measures 2D spread; `λ2/λ1` measures non-collinearity.
A perfectly straight edge has `λ2 = 0` and is degenerate by definition.

Frame 0 is emitted as identity without a tracking step. Anchor spread and
planarity are therefore evaluated on the first transition, using the tracked
points; a collinear anchor fails closed there rather than being silently used.

### 4.3 Conflict detection

For each witness `w` and the primary `p`, both step transforms are evaluated on
the frozen frame-0 member vertex set `V0`:

```text
RMS(p, w) = sqrt( mean_{v in V0} || T_p(v) - T_w(v) ||² )
```

Conflict exists if **any** of:

```text
RMS(p, w) > 2.0 px
|rotation(T_p) - rotation(T_w)| > 2.0°
|scale(T_p)/scale(T_w) - 1| > 0.02
```

The thresholds are frozen at `conflict_rms_px = 2.0`,
`conflict_rotation_deg = 2.0`, and `conflict_scale_ratio = 0.02`.

Conflict is a group-level abstention. It is not a vote, not an identity claim,
and not evidence that one anchor is the "real" one.

### 4.4 Abstention precedence

When several conditions fail on the same transition, the reported reason follows
this fixed order:

1. `PRIMARY_ANCHOR_LOST` — primary below the valid count/ratio floor;
2. `WITNESS_ANCHOR_LOST` — any witness below the valid count/ratio floor;
3. `ANCHOR_DEGENERATE` — primary or witness fails spread/planarity;
4. `LK_QUALITY_TOO_LOW` — any anchor above the LK error ceiling;
5. `ANCHOR_RESIDUAL_TOO_HIGH` — any anchor above the residual ceiling;
6. `ANCHOR_FIT_FAILED` — non-finite/reflected fit;
7. `ANCHOR_CONFLICT` — witness disagreement above any conflict threshold;
8. `TRANSFORM_OUT_OF_BOUNDS` — step outside the frozen bounds;
9. `PREVIOUS_TRANSITION_ABSTAINED` — sticky abstention after an earlier failure.

`MEMBER_LOST` is the B-group reason when one of its members fails; it is not a C
reason. `INVALID_MEMBER_GEOMETRY` is used only if the frozen frame-0 member
geometry itself is invalid.

### 4.5 No silent success branch

If **any** declared anchor is invalid, degenerate, or in conflict, the group is
`ABSTAINED`. C may not:

- ignore an invalid witness and publish the primary result;
- ignore a failed primary and use a witness;
- average a conflicting witness with the primary;
- pick whichever anchor produces the nicer result;
- re-anchor, interpolate, or hold the last transform;
- use GT, IoU, expected fixture labels, or "which case is this" to decide
  `SUPPORTED`.

The only accepted failure behavior is a recorded abstention with the exact
reason and a sticky remainder of the sequence.

---

## 5. Runtime quality vs GT evaluation

This separation is mandatory and testable.

### 5.1 Runtime phase

Runtime input is limited to:

- decoded frames;
- frozen frame-0 member vertices;
- frozen primary/witness point lists;
- frozen LK/anchor thresholds;
- previous runtime state.

Runtime may not receive:

- `ground-truth.json` or any GT points;
- expected fixture label/outcome;
- IoU, RMSE, drift, or any metric calculated from GT;
- a "target answer" or reference geometry.

`SUPPORTED` means only: the declared runtime quality gates and anchor rules
passed. It does not mean the geometry is correct.

### 5.2 GT phase

GT evaluation runs only after the raw method output is complete and hashed:

```text
frames -> B/C runtime -> raw output hash -> GT metrics -> decision
```

GT metrics may include IoU, vertex RMSE, centroid error, drift, rigidity, and
abstention. They may never feed back into runtime, alter a transform, select an
anchor, or change `SUPPORTED`.

### 5.3 Enforcement

T2-P1 tests must include:

- a runtime worker that is given frames and config but **no GT path**;
- a check that deleting/hiding `ground-truth.json` does not change raw runtime
  output;
- a check that GT metrics are computed only after the raw bytes are written;
- a check that runtime `SUPPORTED` is unchanged when GT is corrupted;
- a check that no runtime module imports the GT loader.

If runtime reads GT, the run is **invalid** and the protocol is violated.

---

## 6. Frozen thresholds

All values are frozen before the first T2 run. They are copied into every
`t2-...` config and hashed in the run manifest. Any change requires a new
`t2-p0a` version, not an edit after seeing results.

| Group | Parameter | Frozen value |
| --- | --- | ---: |
| B | `min_valid_member_tracks` | 10 |
| B | `min_valid_member_ratio` | 0.75 |
| B | `max_member_median_residual_px` | 2.0 |
| B | `max_median_lk_error_px` | 8.0 |
| C | `min_valid_anchor_points` | 8 |
| C | `min_valid_anchor_ratio` | 0.75 |
| C | `max_median_lk_error_px` | 8.0 |
| C | `max_median_affine_residual_px` | 2.0 |
| C | `min_anchor_spread_px` | 4.0 |
| C | `min_anchor_planarity` | 0.02 |
| B/C | `min_scale` | 0.5 |
| B/C | `max_scale` | 2.0 |
| B/C | `max_step_rotation_deg` | 15.0 |
| B/C | `max_step_translation_px` | 64.0 |
| C | `conflict_rms_px` | 2.0 |
| C | `conflict_rotation_deg` | 2.0 |
| C | `conflict_scale_ratio` | 0.02 |
| B | `boundary_sample_spacing_px` | 8.0 |
| B/C | `lk_window` | `[31, 31]` |
| B/C | `lk_pyramid_max_level` | 3 |
| B/C | `lk_max_iterations` | 30 |
| B/C | `lk_epsilon` | 0.01 |
| B/C | `lk_min_eigen_threshold` | 0.0001 |
| B/C | `affine_refine_iterations` | 10 |

These are runtime thresholds. The GT gates in §7 are separate and never used
for `SUPPORTED`.

---

## 7. Per-fixture success and failure conditions

`SUPPORTED` is a runtime state. `PASS`, `CONDITIONAL`, `INCONCLUSIVE`, and
`STOP` are evaluation decisions made after GT metrics are computed.

### F1 — coherent translation

| Requirement | Frozen gate |
| --- | --- |
| B control | B `SUPPORTED` on 4/4 frames, 0 abstention |
| C runtime | C `SUPPORTED` on 4/4 frames, 0 abstention |
| C group IoU | `>= 0.990` |
| C mean member IoU | `>= 0.985` |
| C mean vertex RMSE | `<= 0.75 px`; if `B >= 0.50` also `<= 0.75 × B` |
| C final group drift | `<= 0.30 px`; if `B >= 0.10` also `<= 0.50 × B` |
| C group step jitter | if `B >= 0.05`, `<= 0.50 × B`; else `<= 0.05` |
| C rigidity error | `<= 0.10 px` |

Invalid control: B abstaining on F1 is a **STOP**, not a C success.
C missing a gate by more than 10% relative is a **STOP**; a miss within 10% is
**CONDITIONAL**.

### F2 — rotation + uniform scale

| Requirement | Frozen gate |
| --- | --- |
| B control | B `SUPPORTED` on 4/4 frames, 0 abstention |
| C runtime | C `SUPPORTED` on 4/4 frames, 0 abstention |
| C group IoU | `>= 0.975` |
| C mean member IoU | `>= 0.970` |
| C mean vertex RMSE | `<= 1.50 px`; if `B >= 0.50` also `<= 0.75 × B` |
| C final group drift | `<= 0.75 px`; if `B >= 0.10` also `<= 0.50 × B` |
| C group step jitter | if `B >= 0.05`, `<= 0.60 × B`; else `<= 0.05` |
| C rigidity error | `<= 0.20 px` |

Invalid control: B abstaining on F2 is a **STOP**.
C missing a gate by more than 25% relative is a **STOP**; a miss within 25% is
**CONDITIONAL**.

### F3 — low-texture / straight edge

| Observed behavior | Decision |
| --- | --- |
| C abstains on at least one frame with `ANCHOR_LOST`, `ANCHOR_DEGENERATE`, `INSUFFICIENT_VALID_ANCHOR_TRACKS`, `LK_QUALITY_TOO_LOW`, `ANCHOR_RESIDUAL_TOO_HIGH`, or `ANCHOR_FIT_FAILED` | PASS (fail-closed) |
| C is `SUPPORTED` on every supported frame with `group_iou >= 0.95` | PASS |
| C is `SUPPORTED` with `0.90 <= group_iou < 0.95` | CONDITIONAL |
| C is `SUPPORTED` on any frame with `group_iou < 0.90` | **STOP (fail-open)** |
| B and C both abstain | INCONCLUSIVE; report, do not call it a C win |
| B is `SUPPORTED` with `group_iou < 0.90` | record as B failure, not a C gate |

### F4 — temporary occlusion

| Observed behavior | Decision |
| --- | --- |
| C `ABSTAINED` at frame 1 (occluded) with `PRIMARY_ANCHOR_LOST` or `INSUFFICIENT_VALID_ANCHOR_TRACKS` | PASS |
| Frames 2/3 are `PREVIOUS_TRANSITION_ABSTAINED` | PASS (sticky, no recovery claimed) |
| C `SUPPORTED` while the occluder is present | **STOP (fail-open)** |
| C abstains for a different reason | CONDITIONAL; record the reason |

### F5 — conflicting anchor motion

| Observed behavior | Decision |
| --- | --- |
| C `ABSTAINED` at the first conflicting transition with `ANCHOR_CONFLICT` | PASS |
| Later frames are `PREVIOUS_TRANSITION_ABSTAINED` | PASS |
| C `SUPPORTED` while the anchors disagree beyond the conflict thresholds | **STOP (fail-open)** |
| C abstains for a reason other than `ANCHOR_CONFLICT` | CONDITIONAL; conflict rule untested |
| B is measured | no B gate; B has no anchor or group claim |

### B safety measurements

B has no group transform and no anchor. Its group status is `SUPPORTED` only if
all members are `SUPPORTED`; otherwise `MEMBER_LOST`. B on F3/F4/F5 is measured
and reported but is not a C gate. B `SUPPORTED` with group IoU below 0.90 is
recorded as a B failure, not a C success.

---

## 8. Aggregate decision

Evaluation order is **STOP first, then GO, then CONDITIONAL**; a STOP overrides a
GO.

Full-run determinism means two runs in the same declared environment produce
byte-identical `raw/method-b.json`, `raw/method-c.json`, and `metrics.json`.
Timing fields in `costs.json` and `run-manifest.json` may differ.

### GO

All of:

1. F1 passes every quality gate.
2. F2 passes every quality gate.
3. F3 passes its fail-closed gate or is INCONCLUSIVE.
4. F4 passes its fail-closed gate.
5. F5 passes its fail-closed gate.
6. B has 0 abstention on F1 and F2.
7. Full-run determinism passes.
8. Environment is the declared OpenCV 4.14.0.94 runtime.
9. C wall time/frame is `<= 1.00 × B`.

### CONDITIONAL

Any of:

- F1 or F2 misses one or more gates within the STOP bands (F1 at most 10%
  relative, F2 at most 25% relative), with no fail-open;
- C cost is `> 1.00 × B` and `<= 1.50 × B`;
- environment differs from the declared OpenCV wheel;
- full-run determinism passes only downstream, not byte-for-byte;
- F3 is INCONCLUSIVE or supported with `0.90 <= group_iou < 0.95`;
- F5 abstains for a reason other than `ANCHOR_CONFLICT`.

### STOP

Any of:

- F1 misses a gate by more than 10% relative;
- F2 misses a gate by more than 25% relative;
- B abstains on F1 or F2 (invalid control);
- any fail-open on F3, F4, or F5;
- a declared primary/witness is missing, changed after freeze, or not independent;
- runtime reads GT or uses GT to decide `SUPPORTED`;
- C requires per-member fitting, inferred membership, or automatic anchor
  selection to pass;
- a transform is non-finite, reflected, or nondeterministic;
- C cost is `> 1.50 × B` with no compensating quality gain;
- the implementation needs Core, schema, spec, `ChangeAuthority`, Group, Track,
  Binding, or TemporalIdentity changes;
- T1 canonical hashes or tracked content change.

---

## 9. T2-P1 implementation checklist

Before any T2-P1 code or fixture is accepted:

1. All five fixtures are regenerated with multi-member geometry and the
   primary/witness assignments in §4.1; no single-primitive fixture is used.
2. T2-B is a new run on those fixtures; T1-B numbers are not copied.
3. B and C use identical LK/affine/sample parameters; only transform source
   differs.
4. Runtime and GT code paths are separate; the runtime worker has no GT path.
5. Every C run declares one primary and at least one independent witness.
6. Every anchor validity, degeneracy, conflict, and transform-bound rule in §4
   is implemented and tested.
7. Thresholds are hashed in the config and manifest; no post-hoc edits.
8. All five fixtures and both methods run; all runs are retained.
9. Output is classified `experimental-only-not-svm-evidence`; `identity_claim`
   is `none`; no Group/TemporalIdentity/Binding/Track field appears.
10. A failed gate is reported as a failed gate; it is never relabelled as a
    success or used to establish authority.

---

## 10. Non-goals

This freeze does not:

- implement Method C or any fixture generator;
- implement Method D, per-member refinement, or deformation;
- authorize a Group, Track, Keyframe, Binding, TemporalIdentity, or Change;
- change `svm/`, `schema/`, `spec/`, `examples/`, `.github/`, `demo/`, or
  `tests/`;
- add an external model, GPU, CoTracker3, SAM, or checkpoint;
- migrate or rename Golden 047 or Spec 83;
- treat a T2 PASS as SVM Evidence or as a production performance claim.

---

## 11. Final decision

| Scope | Decision |
| --- | --- |
| T2-P0A protocol freeze | **GO** — protocol is complete and frozen |
| T2-P1 Method C implementation | **CONDITIONAL GO** — implement only under §9 |
| SVM Core / Group / TemporalIdentity / authority | **STOP** |
| T2-P1 production/performance optimization | **STOP in this gate**; measure first |

The protocol ambiguity that blocked T2-P1 is closed. The next task may implement
Method C and generate the five multi-member fixtures, but only within the
research tree and only against the frozen thresholds above. If any condition in
§8 STOP triggers, the implementation stops and reports; it does not tune
thresholds or test assertions to obtain a pass.
