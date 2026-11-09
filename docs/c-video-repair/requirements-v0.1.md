# C-MVP v0.1 — Controlled Video Repair Requirements

Status: **DRAFT** — product requirements for the C track. This document defines a
contract; it does not claim that any video repair capability is implemented in
this repository. See `integration-boundary.md` for the verified capability
inventory.

Contract identity: `c-video-repair-contract@0.1`.

## 1. Purpose and scope

C-MVP v0.1 is a minimal, controlled video repair product contract for:

- local picture repair inside an explicit user mask;
- flicker suppression;
- trailing/ghost improvement;
- appearance stability;
- deterministic frame, manifest, and MP4 export;
- a playable before/after comparison.

The first round is a **synthetic controlled experiment**, not a general video
restoration claim. The clean reference and all ground-truth degradation
parameters exist only for fixture generation and offline scoring. They MUST NOT
be visible to the repair process.

The current repository has no video ingestion, raster video renderer, or media
exporter. The reference SVG path is
`Document -> FINAL Evaluator -> Evaluated Scene -> SVGRenderer -> SVG`
(`README.md` "The reference SVG path"), and the existing demo exports use a
local headless browser plus FFmpeg outside the `svm` package
(`demo/004-real-pop-animation/build_demo.py:258-303`,
`demo/001-group-motion/build_demo.py:247-303`). C-MVP therefore lives outside
SVM Core as an external experiment tool.

## 2. Fixed controlled scenario

The first acceptance round SHALL use exactly this scenario:

| Property | Value |
| --- | --- |
| Duration | 2.0 seconds |
| Frame rate | 12 fps, rational `12/1`, constant frame rate |
| Frame count | 24 |
| Frame indices | `0..23` |
| Resolution | 256 × 256 |
| Pixel format | RGB8, 3 channels, no alpha |
| Color space | sRGB, no color-management conversion |
| Background | one fixed, static background region |
| Subject | one small moving object |
| Repair region | one known local ROI with explicit mask |
| Degradation controls | luma flicker and trailing ghost, independently and combined |
| Audio | none |
| Camera | fixed |

Frame timing is normative:

```text
tick(i) = i, for i in 0..23
ticks_per_second = 12
seconds(i) = i / 12
frame i covers [i/12, (i+1)/12)
duration = 24 / 12 = 2.0 seconds
last frame PTS = 23/12 seconds
```

The interval is left-closed and right-open. There is no frame at `t = 2.0 s`.
The same rule applies to PNG sequences and to the MP4 PTS. This follows SVM's
integer-tick Motion model (`spec/21-motion-semantics.md`, "Timebase" and
"Evaluation at time") without adding time to any static Operation key.

### 2.1 Required clips

Each clip is 24 frames and uses the same clean base scene:

| Clip | Degradation | Primary requirement |
| --- | --- | --- |
| `C0` | none (clean reference only) | evaluation reference, never repair input |
| `S1` | local occlusion/damage inside the ROI | local repair |
| `S2` | controllable luma flicker inside the ROI | flicker suppression |
| `S3` | controllable trailing ghost inside the ROI | ghost improvement |
| `S4` | slow local appearance/color drift inside the ROI | appearance stability |
| `S5` | S1 + S2 + S3 + S4 combined | all four improvements |

The clean clip and all degradation parameters are stored in an evaluation-only
directory. The repair command receives only the degraded frames, the explicit
mask/ROI, frame timing, and a versioned configuration.

### 2.2 Synthetic disclosure

Every manifest and report SHALL declare:

```json
{
  "scenario_kind": "synthetic-controlled",
  "real_video": false,
  "generalization_claimed": false
}
```

A successful C-MVP result supports only the statement "the controlled synthetic
clip improved under the frozen metrics". It MUST NOT be presented as evidence of
natural-video robustness, automatic object association, occlusion recovery, or
editable SVM content.

## 3. Functional requirements

Normative keywords: MUST, MUST NOT, SHOULD, MAY.

### CVR-F-01 — Video Artifact input

The canonical C-MVP Video Artifact is a lossless frame-sequence bundle:

```text
video/
  video-manifest.json
  frames/frame-0000.png
  ...
  frames/frame-0023.png
```

Requirements:

1. The bundle MUST contain exactly 24 PNG frames named contiguously from
   `frame-0000.png` to `frame-0023.png`.
2. Each PNG MUST be 8-bit truecolor RGB (PNG color type 2), 256 × 256, no alpha,
   no palette, no interlacing, and no embedded color-management chunk that
   would change decoded samples (`iCCP`, `gAMA`, `cHRM`, `sRGB`).
3. The decoded sample value MUST be the pixel value. The ingest step performs no
   gamma, profile, or palette conversion.
4. `video-manifest.json` MUST record:
   - `contract_version`;
   - `scenario_kind`, `clip_id`;
   - `width`, `height`, `pixel_format`;
   - `frame_count`, `fps` as `{"numerator": 12, "denominator": 1}`;
   - `timebase_ticks_per_second`, `frame_ticks`, `duration_seconds`;
   - `color_space`;
   - per-frame `file_sha256` and `pixel_sha256`;
   - `bundle_digest`;
   - input provenance and the clean-reference isolation declaration.
5. `file_sha256` is the SHA-256 of the PNG bytes. `pixel_sha256` is the SHA-256
   of canonical raw RGB8 bytes in row-major order, top-left origin.
6. A single MP4 is not the canonical input identity. An MP4 MAY be accepted by
   an explicit `ingest` step only when it is H.264, `yuv420p`, constant frame
   rate, 24 frames, 256 × 256, 12 fps, and silent; the ingest step MUST record
   the decoder identity and produce the canonical PNG bundle above. The decoded
   bundle, not the MP4 file hash, becomes the Video Artifact identity.
7. Audio, variable frame rate, rotation metadata, interlacing, and non-RGB
   canonical frames MUST be rejected or explicitly converted and recorded. They
   MUST NOT be silently discarded.
8. The original input MUST be preserved. The repair command MUST open inputs
   read-only and MUST NOT overwrite, rename, or delete them.

### CVR-F-02 — Frame decode and metadata

The decode/ingest step MUST:

1. verify the file signature, IHDR dimensions, bit depth, color type, and
   absence of alpha before decoding;
2. decode all 24 frames and verify the per-frame `pixel_sha256`;
3. reject missing, duplicate, out-of-order, or extra frames;
4. record the decoder name, version, platform, and the exact command used;
5. write a normalized manifest before any repair work begins;
6. fail closed on any hash or metadata mismatch.

For an MP4 ingest, the step MUST also record the container codec, profile,
pixel format, color matrix/range, average frame rate, and `nb_frames`. H.264
decoding is lossy and decoder-version dependent; that is why the decoded PNG
bundle, not the MP4 bytes, is the canonical artifact.

### CVR-F-03 — ROI and mask format

Coordinates follow the repository's existing raster convention:

- origin at the upper-left pixel, x to the right, y downward;
- integer pixel coordinates identify pixel samples; there is no half-pixel
  shift and no Y flip;
- bounds are half-open `[min_x, min_y, max_x, max_y]`, matching
  `spec/16-opencv-artifact-analysis.md` ("Bounds are half-open pixel
  coordinates").

Requirements:

1. `repair_roi` MUST be a half-open integer rectangle inside the 256 × 256
   frame with `0 <= x0 < x1 <= 256` and `0 <= y0 < y1 <= 256`.
2. `evaluation_roi` MUST be a fixed half-open rectangle declared before the run.
   It MUST NOT be chosen after looking at results.
3. A mask MUST be an 8-bit grayscale PNG of exactly 256 × 256 with values only
   `0` (preserve) and `255` (repair allowed). Anti-aliased or intermediate
   values are unsupported in v0.1.
4. Mask support MUST be non-empty, MUST be contained in `repair_roi`, and MUST
   NOT cover the entire frame. Empty and full-frame masks are rejected.
5. A constant mask across all 24 frames and a per-frame mask set are both
   allowed. If per-frame masks are used, every frame MUST have a mask; there is
   no implicit temporal propagation.
6. `feather_px` MUST be an integer in `[0, 8]` and is applied symmetrically
   around `repair_roi` only for the protection-domain check. It is not an
   implicit mask dilation for repair.
7. `protection_domain = repair_roi expanded by feather_px, clipped to the
   frame`. Pixels outside `protection_domain` MUST remain bit-identical to the
   input after decoding, for lossless PNG output.
8. Masks are explicit user input and MUST be disclosed in the manifest. C-MVP
   v0.1 does not infer masks from the clean reference or from degradation
   parameters.

### CVR-F-04 — Local repair input and output

Input to the repair stage:

```text
degraded frames (24, RGB8)
+ explicit masks/ROI
+ frame timing (frame index, tick, fps)
+ versioned configuration
+ algorithm identity and parameters
```

The repair stage MUST NOT open, read, hash, or receive any path to the clean
reference, ground-truth motion, degradation parameters, or scoring output.

Output:

```text
repaired frames (24, RGB8, lossless PNG)
+ per-frame status
+ per-frame changed-pixel count
+ per-frame unresolved-pixel count
+ output manifest
```

Applicability conditions:

1. The camera is fixed and the background inside the ROI is static.
2. The repair target is background, not the interior of a moving object. A
   moving-object interior is outside the guaranteed domain unless the object is
   static for the whole repair window; otherwise the tool MUST fail closed with
   `OBJECT_REPAIR_UNSUPPORTED`.
3. At least two valid neighboring observations of the same background pixel are
   available. If not, the frame/pixel is marked `UNRESOLVED`; the tool MUST NOT
   invent content.
4. The repair is a deterministic evidence replacement from observed pixels
   (for example, a temporal median or trimmed mean) or a deterministic spatial
   fallback that is explicitly configured. Generative models, neural
   inpainting, optical flow, and arbitrary texture synthesis are out of scope.
5. v0.1 MUST NOT claim recovery of detail that was never observed in any frame.
   If a pixel is unobserved or inconsistent, it remains unchanged and is
   reported as `UNRESOLVED`.

### CVR-F-05 — Flicker suppression boundary

Flicker suppression is a bounded photometric correction, not a general color
grade:

1. The correction is estimated only from a declared static sample mask that
   excludes the moving object and the ghost region by at least 2 pixels.
2. v0.1 uses a per-frame luma offset in integer code values:
   `y' = clamp(y + delta_t, 0, 255)`.
3. `delta_t` is estimated from the declared sample mask, anchored to a temporal
   reference derived from the degraded sequence itself. The clean reference
   MUST NOT be used.
4. `abs(delta_t)` MUST be at most 32 code values. A larger estimate is
   `FLICKER_OUT_OF_RANGE` and MUST fail the run; it MUST NOT be silently
   clamped.
5. The correction SHALL be applied only inside the declared photometric ROI.
   Pixels outside `protection_domain` MUST NOT change.
6. v0.1 does not restore clipped highlights, clipped shadows, or missing
   texture. A global offset cannot recover information destroyed by clipping;
   this limitation MUST be reported.

### CVR-F-06 — Trailing/ghost improvement applicability and failure

Ghost improvement applies only when:

1. the camera is fixed and the background is static;
2. the ghost is transient: the underlying background is observable in at least
   two frames without the ghost;
3. the ghost region is declared by the explicit mask or a declared ghost ROI;
4. the ghost does not overlap the true moving object's silhouette;
5. the ghost displacement between frames is within the declared search window
   (v0.1: at most 4 pixels per frame).

The tool MUST fail closed with `GHOST_OUT_OF_DOMAIN` when:

- the ghost is present in every frame (no clean observation exists);
- the ghost overlaps the true object;
- the background itself changes (illumination or geometry) faster than the
  observation window;
- the estimated correction would change more than the configured fraction of
  the ROI (default 0.25);
- the ghost and object colors are not separable under the declared threshold.

The tool MUST NOT promise complete removal. Acceptance measures residual energy
reduction inside a pre-declared trailing region, not the absence of all ghost
pixels.

### CVR-F-07 — Appearance stability

Appearance stability is a measured outcome, not a license to alter arbitrary
colors:

1. The primary metric is the temporal standard deviation of the per-frame mean
   color inside the target interior, reported per channel and for luma.
2. A spatial error term MUST be reported at the same time, so that blurring or
   flattening cannot lower the temporal metric without penalty.
3. v0.1 may apply a bounded per-channel offset correction inside the
   photometric ROI when the configured clip requires it. The correction MUST be
   recorded, MUST be integer-valued, and MUST be at most ±16 code values.
4. Gain, gamma, hue rotation, local color grading, and generative appearance
   synthesis are out of scope.
5. The target interior mask used for the metric is fixed by the fixture before
   the run. For a future real input it MUST be an explicit user mask.

### CVR-F-08 — Export: frame sequence, manifest, MP4

A successful run MUST produce:

```text
output/
  frames-repaired/frame-0000.png ... frame-0023.png
  before.mp4
  after.mp4
  comparison.mp4
  run-manifest.json
  metrics.json
  run.log
```

Requirements:

1. Repaired frames MUST be lossless RGB8 PNGs, 256 × 256, 24 frames, matching
   the input naming and timing.
2. `before.mp4` and `after.mp4` MUST be H.264, `yuv420p`, 256 × 256, 12 fps,
   24 frames, 2.0 seconds, silent, with `faststart` enabled.
3. `comparison.mp4` MUST be 512 × 256, 12 fps, 24 frames, 2.0 seconds, silent,
   H.264/`yuv420p`; left half is before, right half is after, with no labels,
   borders, or padding. The layout MUST be declared in the comparison manifest
   or in `run-manifest.json`.
4. `run-manifest.json` MUST record at least:
   - `contract_version`, `run_id`, `status`, `exit_code`;
   - input bundle/mask/config digests;
   - frame index to tick mapping, rational fps, frame count, duration, endpoint
     rule;
   - algorithm identity, parameters, random seed, tool versions, code commit;
   - output frame digests and media file digests;
   - `scenario_kind: "synthetic-controlled"`;
   - `clean_reference_in_input: false`;
   - determinism class and platform;
   - errors and per-frame statuses.
5. `metrics.json` MUST be produced by the separate evaluation command, not by
   the repair command. It MUST record the reference hashes and the metric
   formulas and thresholds.
6. Absolute paths, wall-clock timestamps, hostnames, and run durations MUST NOT
   participate in semantic identity. They MAY appear in `run.log` or in an
   explicit `execution` block excluded from the semantic digest.
7. A failed run MUST NOT leave a manifest with `status: "SUCCESS"`. Partial
   output MUST be marked `PARTIAL` and MUST fail acceptance.

### CVR-F-09 — Before/after comparison

The comparison deliverable is:

- `before.mp4` — presentation encoding of the degraded input frames;
- `after.mp4` — presentation encoding of the repaired frames;
- `comparison.mp4` — synchronized side-by-side playback;
- decoded PNG frames for both sides, retained for pixel checks.

Requirements:

1. All three MP4s MUST have identical frame count, frame rate, duration, and
   PTS range.
2. The comparison MUST be generated from the same decoded frames and the same
   encoder profile as `before.mp4` and `after.mp4`.
3. The comparison is a viewing aid, not a scoring source. Acceptance metrics
   MUST be computed from lossless PNG frames.
4. The comparison MUST NOT crop, zoom, retime, or mask difficult regions.

### CVR-F-10 — External algorithm and SVM boundary

The repair tool is an external experiment tool:

- it is an **Artifact Processor** (external evidence in, derived frames/evidence
  out), not an SVM Backend or Adapter;
- it MUST NOT add filesystem, network, clock, or UI reads inside SVM Operation
  evaluation;
- it MUST NOT modify `svm/`, `schema/`, or any accepted Document;
- it MUST NOT call `RevisionStore.commit()` directly;
- it MUST NOT claim that repaired frames are SVM Immutable Values, Entity
  geometry, or editable SVM content.

If a future round decides that a repair result must become an SVM Document
change, the only allowed path is:

```text
Derived Artifact(s)
-> Adapter Proposal
-> registered Change in Change Authority Registry
-> atomic Transaction
-> ProposalAcceptor.accept()
-> new Revision
```

`RevisionStore.commit()` remains a trusted internal mechanism, not an external
acceptance API (`spec/05-system-boundaries.md`, "Proposal and Proposal
Acceptor"). No such change is proposed in v0.1.

## 4. Non-destructive and evidence rules

### 4.1 Input preservation

- The input bundle and masks MUST be treated as read-only.
- Hashes MUST be verified before repair and again before export.
- Outputs MUST be written to a new run directory. A successful run directory
  MUST NOT be overwritten by a later run.
- Original files MUST remain retrievable after the run.

### 4.2 No clean-reference leakage

- The repair process MUST NOT receive the clean reference directory or a path
  to it.
- The repair manifest MUST contain `"clean_reference_in_input": false`.
- The evaluation process MAY read the clean reference only after the repair
  output is sealed.
- CI MUST verify isolation by moving or deleting the evaluation directory and
  rerunning repair; the output must be identical.

### 4.3 No fabricated detail

- A repaired pixel MUST come from an observed degraded pixel in the declared
  temporal window or from a declared deterministic fallback.
- Unobserved or inconsistent pixels remain unchanged and are reported as
  `UNRESOLVED`.
- The tool MUST NOT use a generative model, a learned prior, or a clean
  reference to synthesize texture.
- The report MUST distinguish "changed from observed evidence" from "not
  repaired".

### 4.4 Artifact classification

| Product | Classification | Requires Proposal? |
| --- | --- | --- |
| Degraded input frames | ReferenceArtifact (external evidence) | No |
| User mask/ROI | ReferenceArtifact (explicit user input) | No |
| Clean reference frames | Evaluation-only reference; never a repair input | No |
| Repaired frames | DerivedArtifact (non-destructive external result) | No |
| `run-manifest.json`, `metrics.json` | DerivedArtifact/report | No |
| `before.mp4`, `after.mp4`, `comparison.mp4` | Derived presentation artifacts | No |
| A future SVM Entity/geometry created from a repair result | Document change | Yes — Artifact -> Proposal -> registered Change -> ProposalAcceptor -> Revision |

Repaired frames do not become part of the accepted construction program merely
because they exist. This follows the Artifact/Immutable Value distinction in
`spec/05-system-boundaries.md`.

## 5. Determinism and non-determinism boundaries

### 5.1 D0 — deterministic within one frozen environment

Given identical input bytes, masks, configuration, algorithm build, and
platform, two runs MUST produce:

- identical decoded PNG pixels for every frame;
- identical `pixel_sha256` values;
- identical semantic manifest digest;
- identical metrics within `1e-9`.

### 5.2 D1 — deterministic across platforms

- PNG pixels and `pixel_sha256` MUST be identical across platforms.
- Semantic manifest fields MUST be identical.
- Metrics MUST agree within `1e-9`.
- MP4 bytes are NOT required to be identical. Decoded MP4 frames MUST agree
  within the frozen tolerance (proposed: MAE <= 2.0 code values, PSNR >= 40 dB)
  and MUST have identical frame count, dimensions, frame rate, and duration.

### 5.3 D2 — not deterministic

The following are explicitly outside semantic identity:

- MP4 byte hashes;
- encoder metadata and CPU-specific encoder decisions;
- headless-browser rasterization, if a future round uses it;
- wall-clock time, absolute paths, hostnames, locale, and logs.

The reference demos use a local browser and FFmpeg
(`demo/004-real-pop-animation/build_demo.py:258-303`); that path is not a
cross-platform guarantee and MUST NOT be used as the C-MVP determinism claim.

### 5.4 Required recorded versions

Every run MUST record:

- C-MVP contract version;
- algorithm identity and version;
- PNG decoder/encoder identity and version;
- MP4 encoder identity and version;
- FFmpeg/ffprobe version, if used;
- Python version, OS, and code commit SHA;
- random seed, or `null` if no randomness is used.

## 6. Out of scope and explicit non-claims

C-MVP v0.1 does not support and MUST NOT claim:

- natural video, photographs, or arbitrary camera motion;
- multiple objects, automatic object association, or automatic masks;
- occlusion recovery, de-occlusion, or missing-frame synthesis;
- neural models, learned priors, generative fill, or optical flow;
- super-resolution, denoising, stabilization, or frame interpolation;
- non-uniform scale, perspective, deformation, or 3D;
- audio, variable frame rate, rotation metadata, or color-managed video;
- editable SVM Documents, Entities, Tracks, or geometry created from repair
  results;
- general recovery from `spec/56`–`spec/58`: those specifications define a
  controlled, opaque grayscale, binary-polygon raster observation domain, not
  RGB video repair. `spec/58-explicit-multi-object-raster-recovery.md` explicitly
  excludes "RGB, photographs, optical flow, neural tracking, perspective,
  deformation, non-uniform scale, uncertainty model, RANSAC, optimizer, video
  ingestion".

## 7. Acceptance handoff

The measurable acceptance contract is in `acceptance-criteria-v0.1.md`. The
file-level interface, manifest fields, CLI, and error codes are in
`pipeline-contract-v0.1.md`. The repository capability inventory and the
Core/Revision boundary are in `integration-boundary.md`.

All numeric thresholds in v0.1 are **PROPOSED** until the C planning line
freezes them before holdout evaluation. A threshold MUST NOT be lowered after a
holdout failure; a failed holdout is reported as a failure.
