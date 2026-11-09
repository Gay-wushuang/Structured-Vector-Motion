# C-MVP v0.1 — Integration Boundary and Capability Inventory

Status: **DRAFT** — verified against baseline commit
`cf4815357909f4e462f26619d33e6bfcb1e16236` (`main`, 2026-11-09). This document
records what exists, what is partial, what is specification-only, and what is
missing. It does not propose a Core change.

Contract identity: `c-video-repair-contract@0.1`.

## 1. Why this document exists

C-MVP introduces video frames, ROI masks, repair algorithms, metrics, and MP4
export. None of those may silently become SVM Core semantics. This document
maps every C-MVP component to an existing SVM boundary from
`spec/05-system-boundaries.md` and identifies the gaps that must remain outside
Core.

The governing rule is:

> Adapters propose changes. Backends execute accepted definitions.

C-MVP v0.1 proposes no Document change, so it is not an Adapter. It processes
external evidence, so it is an **Artifact Processor**; it packages media, so it
also uses an **Exporter/MediaEncoder** capability. It never executes an
accepted SVM Operation and never receives Revision Store authority.

## 2. Verified capability inventory

Status values:

- **implemented** — executable code and tests exist;
- **partial** — a narrow or external path exists, but not as a Core capability;
- **specified** — a normative role is defined, but no implementation exists;
- **missing** — no code, test, specification, or dependency exists.

| Capability | Status | Evidence |
| --- | --- | --- |
| Document validation / evaluation / revisions | implemented | `svm/document.py`, `svm/evaluator.py`, `svm/revisions.py`; Golden A/B in `tests/test_golden_a.py`, `tests/test_golden_b.py` |
| Motion sampling at integer ticks | implemented | `svm/motion.py:370-435` (`MotionEvaluator`, `evaluate`, `sample_document`); `spec/21-motion-semantics.md` |
| SVG rendering of an Evaluated Scene | implemented | `svm/renderers/svg.py:24-74`; `spec/08-svg-renderer.md`; Golden D/E/F frames |
| Content-addressed Artifact store | implemented (in-memory) | `svm/artifacts.py:111-167` (`ArtifactStore.import_bytes`, SHA-256 identity); no persistent store |
| Proposal acceptance / atomic Transaction | implemented | `svm/proposals.py:185-253`; `svm/revisions.py:2079-2130`; `svm/change_authority.py:60` |
| OpenCV raster analysis | implemented (grayscale only) | `svm/adapters/opencv_analysis.py:186-200`; `spec/16-opencv-artifact-analysis.md` |
| Controlled raster geometry observations | implemented (grayscale binary stills) | `svm/adapters/raster_geometry_observations.py`; `spec/56-controlled-raster-observations.md` |
| Controlled raster camera recovery | implemented (grayscale binary stills) | `spec/57-controlled-raster-camera-recovery.md`; `spec/58-explicit-multi-object-raster-recovery.md`; `examples/035`, `examples/036`, `examples/037` |
| Temporal correspondence evidence | implemented (frozen primitive artifacts) | `svm/adapters/temporal_correspondence.py`; `spec/35-temporal-correspondence.md`; Golden R0 |
| RGB raster rendering | missing in Core | no raster renderer in `svm/renderers/`; `svm/renderers/svg.py` only |
| Headless rasterization for demos | partial (external, local browser) | `demo/004-real-pop-animation/build_demo.py:258-281`; `demo/001-group-motion/build_demo.py:269-303` |
| MP4 encoding | missing in Core | no `MediaEncoder` class; demos shell out to FFmpeg at `demo/004-real-pop-animation/build_demo.py:282-303` and `demo/001-group-motion/build_demo.py:247-267` |
| Video decoding / frame extraction | missing | no video code or test; no FFmpeg/OpenCV video dependency in `pyproject.toml:11-35`; `svm/cli.py:677-823` has no video command |
| Video Artifact type | missing | no video media type or manifest schema |
| User ROI / repair mask type | missing | OpenCV produces a derived binary mask (`spec/16`), but there is no user repair-mask contract |
| Local video repair algorithm | missing | no code or test |
| Flicker / ghost / appearance algorithms | missing | no code or test |
| Video metrics / comparison / acceptance report | missing | no code or test |
| Export profile for C-MVP | missing | `spec/05-system-boundaries.md:296-308` defines the Exporter role only |
| C-MVP tests | missing | `tests/` has no `test_video_repair_*` module |

### 2.1 What the existing raster path actually supports

The existing OpenCV/raster path is not a video path:

- It accepts only an 8-bit opaque grayscale PNG, color type 0, no alpha, no
  palette, no transparency (`spec/16-opencv-artifact-analysis.md:25-30`;
  `svm/adapters/opencv_analysis.py:186-200`).
- It requires exactly two sample values (one background, one foreground) and no
  gradients or antialiasing for controlled raster recovery
  (`spec/56-controlled-raster-observations.md:20-26`).
- It consumes a fixed set of stills at explicit ticks; it does not decode a
  container or a frame sequence (`spec/58-explicit-multi-object-raster-recovery.md:24-41`).
- It explicitly excludes RGB, photographs, optical flow, neural tracking,
  perspective, deformation, non-uniform scale, optimizer, and video ingestion
  (`spec/58-explicit-multi-object-raster-recovery.md:139-141`).

Therefore C-MVP MUST NOT describe `spec/56`–`spec/58` as existing video repair
capability. They are controlled grayscale still-image recovery contracts.

### 2.2 What the existing Motion path actually supports

Motion is a Document definition with integer ticks and sampling
(`spec/21-motion-semantics.md:15-19`, `:36-43`). It does not ingest video and
does not produce a raster frame. `MotionEvaluator.evaluate(tick)` returns a
`MotionFrame` whose scene can be rendered by `SVGRenderer`
(`svm/motion.py:387-435`). A C-MVP frame is an external raster frame, not an
SVM Motion Frame.

### 2.3 What the existing export path actually supports

There is no Core exporter. The demo builders run a local browser screenshot and
FFmpeg:

- `demo/004-real-pop-animation/build_demo.py:258-281` selects
  `msedge.exe` or `chrome.exe` and uses `--headless --screenshot`;
- `demo/004-real-pop-animation/build_demo.py:282-303` invokes `ffmpeg` with
  `libx264` and `yuv420p`;
- `demo/001-group-motion/build_demo.py:247-303` follows the same pattern.

These are Windows-local demo conveniences, not a portable C-MVP exporter. The
C-MVP contract requires an explicit encoder path and version, and a decoded
frame check, rather than relying on a hard-coded browser path.

## 3. Boundary classification of C-MVP components

| Component | Classification | Why |
| --- | --- | --- |
| MP4/PNG frame reader | Artifact Processor | transforms external bytes into normalized frames; no Document change |
| ROI/mask reader | Artifact Processor | consumes explicit user evidence; no Document change |
| Temporal repair | Artifact Processor | derives new raster evidence; no Operation execution, no Revision |
| Flicker/ghost/appearance correction | Artifact Processor | derives new raster evidence; no Document change |
| Raster frame writer | Renderer | converts a visual result to pixels; does not evaluate Document semantics |
| MP4 encoder | Exporter / MediaEncoder | packages raster frames; does not define animation semantics |
| Metrics / comparison | Exporter / report | packages evaluation results; not a Runtime Value |
| A future Entity from repair | Adapter + Proposal + registered Change | would change the accepted Document; not in v0.1 |

None of these is a Backend: a Backend executes an already accepted Operation
definition, and C-MVP has no such Operation. None is an Adapter in v0.1: an
Adapter proposes a Document change, and C-MVP proposes none.

## 4. Prohibited coupling

The following are hard prohibitions for C-MVP v0.1:

1. No new `svm` CLI subcommand, Operation, Schema field, Change type, policy, or
   `spec/` number.
2. No filesystem, network, clock, locale, or UI read inside SVM Operation
   evaluation (`INV-EVAL-003`).
3. No call to `RevisionStore.commit()` from the repair tool, an Adapter, or a
   plugin. `commit()` is trusted internal infrastructure, not an external
   acceptance API (`spec/05-system-boundaries.md:212-216`).
4. No mutation of an accepted Document. A future change must use
   `ProposalAcceptor.accept()` (`svm/proposals.py:185-204`).
5. No presentation of repaired frames as SVM Immutable Values, Entity geometry,
   FINAL evaluation output, or editable SVM content. This follows the
   Artifact/Value distinction in `spec/05-system-boundaries.md:160-182`.
6. No use of stale or PREVIEW SVM results as a substitute for FINAL
   (`INV-EVAL-005`; `spec/04-invariant-coverage.md`).
7. No extension of the OpenCV/raster support domain to RGB video. The existing
   contract is grayscale-only and still-image-only (`spec/16`, `spec/56`–`spec/58`).
8. No claim that a synthetic controlled success generalizes to natural video,
   occlusion, multiple objects, or automatic masks.

## 5. Recommended data flow

```text
SVM Document + MotionEvaluator + SVGRenderer
        |
        v
clean SVG frames (fixture-only)
        |
        v
external rasterization (fixture-only)
        |
        v
clean RGB frames  ---------------------------> eval/ reference (scoring only)
        |
        v
offline degradation generator (recorded seed/parameters)
        |
        v
degraded input frames + explicit ROI/mask + config
        |
        v
C-MVP repair tool (Artifact Processor)
        |
        v
repaired PNG frames + run-manifest.json
        |
        +--> FFmpeg exporter --> before/after/comparison MP4
        |
        +--> separate evaluate process --> metrics.json
        |
        +--> separate verify process --> acceptance-report.json
```

The clean reference branch and the degraded input branch MUST be physically
separate directories. The repair command receives only the degraded branch.

## 6. Isolation enforcement

Isolation is a testable property, not a code comment:

1. The repair command's argument surface has no `--reference`, `--clean`, or
   `--ground-truth` option.
2. The input bundle manifest contains `"clean_reference_in_input": false`.
3. The repair manifest is checked for any path or digest that resolves to the
   evaluation directory; a hit is `CVR-E014`.
4. CI moves or deletes the `eval/` directory and reruns repair. The repaired
   frames must be identical to the original run.
5. CI also runs repair with a read-only input bundle; success proves the input
   is not overwritten.
6. Scoring code lives in a separate module/process from repair code. CI must
   not import the repair implementation's scoring helper as its oracle.

## 7. Future path if a repair result must become SVM content

If a later round requires a repaired region to become an SVM Entity or
geometry, the following is the only allowed path:

```text
ReferenceArtifact (source frame or region evidence)
+ DerivedArtifact (mask / analysis / metrics)
-> Adapter Proposal
-> registered Change (Change Authority Registry)
-> atomic Transaction
-> ProposalAcceptor.accept()
-> new Revision
```

Requirements for that future round:

- the Change type must be registered in `svm/change_authority.py`;
- the Proposal must target an exact base Revision;
- the Proposal must declare required Artifact IDs and preview Artifacts;
- `ProposalAcceptor` must validate base, permissions, constraints, and Artifact
  identity;
- the Transaction must be atomic;
- the old Revision must remain evaluable;
- no Adapter-specific branch may be added to `ProposalAcceptor`
  (`spec/05-system-boundaries.md:200-216`).

This is explicitly **not** part of C-MVP v0.1. The v0.1 deliverable is external
frames, media, and reports.

## 8. Interface ownership

| Interface | Docs line owns | Practice line owns | CI line owns |
| --- | --- | --- | --- |
| Contract version and thresholds | yes | consumes | validates |
| CLI subcommand names and exit codes | yes | implements | invokes |
| Input/mask/config/manifest field names | yes | implements | parses |
| Metric formulas and regions | yes | consumes | implements independently |
| MP4 profile and ffprobe checks | yes | implements export | verifies |
| Fixture generation and seeds | no | implements | consumes frozen fixtures |
| Independent scoring code | no | no | implements |
| Acceptance report | no | no | implements |
| Review findings | no | no | no (review line owns) |

The practice line MUST NOT edit this contract, the acceptance thresholds, or
CI's scoring code. The CI line MUST NOT edit the repair implementation to make a
test pass.

## 9. Open issues and decisions for the C planning line

| # | Issue | Recommendation | Impact |
| ---: | --- | --- | --- |
| 1 | Canonical input: PNG sequence vs MP4-only | PNG sequence is canonical; MP4 is ingest-only | avoids decoder-dependent pixel identity |
| 2 | Path convention: `docs/c-video-repair/` (R1-001) vs `docs/video-repair/` (planning dispatch) | keep R1-001 path as canonical for the C track; do not duplicate | avoids two contract trees |
| 3 | Threshold freeze before holdout | freeze 30% single / 20% combined and all guards | prevents post-hoc tuning |
| 4 | MP4 cross-platform tolerance | freeze MAE <= 2.0 and PSNR >= 40 dB after a tool-environment trial | prevents byte-hash claims |
| 5 | Persistent Artifact store | keep in-memory for v0.1; record file hashes in manifest | avoids new Core storage |
| 6 | Whether repair output becomes SVM content | no for v0.1; require a separate Proposal design if needed | preserves Artifact/Value boundary |
| 7 | Browser-based rasterization | do not use in C-MVP acceptance; use an explicit rasterizer or pre-rendered fixture PNGs | removes Windows-local dependency |
| 8 | Audio / VFR handling | reject by default; explicit drop/convert with a recorded command | follows planning dispatch |

## 10. Evidence index

Repository sources used in this document:

- `AGENTS.md` — project purpose, invariants, scope discipline.
- `README.md:45-52` — reference SVG path.
- `README.md:118-131` — bitmap trace boundary.
- `README.md:287-294` — prototype is browser-only Editor State.
- `spec/00-svm-core-model.md:124-145` — time and explicit v0.1 exclusions
  (including video tracking).
- `spec/01-invariants.md` — INV-ID, INV-EVAL, INV-TIME, INV-PROP.
- `spec/04-invariant-coverage.md` — implemented/fail-closed/specified status.
- `spec/05-system-boundaries.md:102-127` — Adapter role.
- `spec/05-system-boundaries.md:129-159` — Artifact vs Immutable Value.
- `spec/05-system-boundaries.md:184-218` — Proposal and acceptance authority.
- `spec/05-system-boundaries.md:220-249` — Backend role.
- `spec/05-system-boundaries.md:296-308` — Renderer and Exporter role.
- `spec/16-opencv-artifact-analysis.md:25-30` — grayscale-only input.
- `spec/16-opencv-artifact-analysis.md:56` — half-open pixel bounds.
- `spec/16-opencv-artifact-analysis.md:60-63` — deterministic PNG encoder.
- `spec/21-motion-semantics.md:15-46` — integer Timebase, sampling, interpolation.
- `spec/35-temporal-correspondence.md:9-18` — frozen observation-artifact scope.
- `spec/35-temporal-correspondence.md:52-57` — evidence-only acceptance.
- `spec/56-controlled-raster-observations.md:20-41` — binary grayscale domain.
- `spec/58-explicit-multi-object-raster-recovery.md:139-141` — excluded video,
  RGB, optical flow, neural tracking, and occlusion.
- `svm/artifacts.py:111-167` — in-memory content-addressed store.
- `svm/proposals.py:185-253` — acceptance authority.
- `svm/revisions.py:2079-2130` — Transaction and RevisionStore.
- `svm/change_authority.py:60` — Change Authority Registry.
- `svm/motion.py:370-435` — MotionEvaluator.
- `svm/renderers/svg.py:24-74` — SVGRenderer.
- `svm/adapters/opencv_analysis.py:186-200` — grayscale PNG analysis.
- `svm/cli.py:677-823` — existing CLI; no video command.
- `demo/004-real-pop-animation/build_demo.py:258-303` — browser + FFmpeg demo.
- `demo/001-group-motion/build_demo.py:247-303` — browser + FFmpeg demo.
- `pyproject.toml:11-35` — dependencies; no video/FFmpeg dependency.
- `.github/workflows/ci.yml:31` — installed extras; no video job.
- `tests/` — no `test_video_repair_*` module.

## 11. Integration conclusion

C-MVP v0.1 is an external, non-destructive Artifact Processor plus Renderer and
Exporter. It is compatible with SVM's system boundaries only if:

- it stays outside `svm/` and `schema/`;
- it never reads the clean reference during repair;
- it never treats repaired frames as SVM Immutable Values or Document content;
- it never bypasses `ProposalAcceptor` if a future round changes the Document;
- it discloses the synthetic controlled scope and its limitations.

The current repository has enough Motion/SVG/Artifact/Revision infrastructure to
generate a controlled clean reference, but it has no video ingestion, RGB
rasterizer, repair algorithm, metrics, or media exporter. Those are C-track
work, not existing capabilities.
