# C-MVP v0.1 — Pipeline and Interface Contract

Status: **DRAFT** — interface contract for the C track. It defines what the
practice and CI lines must implement and verify; it does not implement repair.

Contract identity: `c-video-repair-contract@0.1`.

This contract is intentionally outside the `svm` package. It does not extend
the public `svm` CLI, does not add a Core Operation, and does not add a Document
schema field. The external entry point is a demo/tool script owned by the
practice line.

## 1. Roles and commands

| Role | Responsibility | Reads | Writes |
| --- | --- | --- | --- |
| Fixture builder | generate clean/degraded controlled clips | SVM Document / fixture parameters | `eval/` reference data, degraded input bundles |
| Ingest | normalize a source into the canonical bundle | source video/PNG bundle | canonical `input/` bundle |
| Repair | local repair, flicker/ghost suppression | canonical input, masks, config | `output/frames-repaired/`, repair manifest |
| Export | encode MP4s and comparison | repaired frames, input frames | `before.mp4`, `after.mp4`, `comparison.mp4` |
| Evaluate | reference-based scoring | repair output, `eval/` reference | `metrics.json` |
| Verify | independent acceptance | all of the above | `acceptance-report.json` |

The reference-based `evaluate` and `verify` commands are separate processes.
They are the only commands allowed to read `eval/`. The repair process MUST NOT
receive an `eval/` path.

## 2. Proposed external CLI

The exact executable path is owned by the practice line. This contract fixes
the subcommand names, arguments, exit codes, and file effects. A proposed entry
point is:

```text
python demo/005-controlled-video-repair/cvr.py <subcommand> ...
```

The `svm` console script MUST NOT gain any of these subcommands in v0.1.

### 2.1 `ingest`

```text
cvr.py ingest --source <path> --output <bundle-dir> \
  [--decoder-profile <profile-id>] [--drop-audio]
```

- Accepts a canonical PNG bundle or a single MP4.
- Verifies dimensions, frame count, frame rate, pixel format, and silence.
- Writes the canonical `input/` layout from §3 and a normalized
  `video-manifest.json`.
- Rejects audio unless `--drop-audio` is explicitly supplied; records the drop.
- Rejects variable frame rate, rotation metadata, and non-24-frame sources.
- Never overwrites a non-empty output directory.

### 2.2 `repair`

```text
cvr.py repair --input <bundle-dir> --masks <mask-dir> \
  --config <config.json> --output <run-dir>
```

- Reads only the canonical input bundle, masks, and config.
- Writes `frames-repaired/`, `run-manifest.json`, and `run.log`.
- Does not encode MP4 and does not compute reference-based metrics.
- Fails closed if any input digest, mask digest, or config field is invalid.

### 2.3 `export`

```text
cvr.py export --run <run-dir> --encoder <ffmpeg-path> [--ffprobe <path>]
```

- Encodes `before.mp4`, `after.mp4`, and `comparison.mp4`.
- Verifies the encoded files with `ffprobe` and a full decode pass.
- Updates the run manifest with media digests and encoder identity.
- A missing or failing encoder is a hard failure (`EXIT_TOOL_FAILURE`), not a
  skipped step.

### 2.4 `evaluate`

```text
cvr.py evaluate --run <run-dir> --reference <eval-dir> --output <metrics.json>
```

- Reads the sealed repair output and the evaluation-only reference.
- Verifies every output digest before scoring.
- Computes the metrics in `acceptance-criteria-v0.1.md`.
- Writes a metrics report with formula identities, ROI identities, input values,
  output values, relative improvements, thresholds, and pass/fail flags.
- MUST NOT modify repair frames.

### 2.5 `verify`

```text
cvr.py verify --run <run-dir> --reference <eval-dir> \
  --contract <contract-version> --output <acceptance-report.json>
```

- Independently re-checks input validation, output validity, metrics,
  determinism, and export properties.
- Exits `0` only if every required check passes.
- Writes a machine-readable report with one row per check.

## 3. Directory layout

A run directory is self-contained and immutable after sealing:

```text
<run-dir>/
  input/                         # symlink/copy of the canonical bundle, read-only
    video-manifest.json
    frames/frame-0000.png ... frame-0023.png
  masks/
    mask-manifest.json
    frame-0000.png ... frame-0023.png   # or constant.png
  config.json
  frames-repaired/
    frame-0000.png ... frame-0023.png
  before.mp4
  after.mp4
  comparison.mp4
  run-manifest.json
  metrics.json
  acceptance-report.json
  run.log
```

`<run-dir>` MUST be created atomically. The repair process writes to
`<run-dir>.tmp-<run_id>/` and renames it only after the manifest is sealed. A
failed run MAY leave a `FAILED` manifest and diagnostics, but MUST NOT leave a
`SUCCESS` manifest.

## 4. Canonical input bundle

### 4.1 `video-manifest.json`

```json
{
  "contract_version": "c-video-repair-contract@0.1",
  "scenario_kind": "synthetic-controlled",
  "clip_id": "S3-ghost",
  "width": 256,
  "height": 256,
  "pixel_format": "RGB8",
  "color_space": "sRGB",
  "frame_count": 24,
  "fps": {"numerator": 12, "denominator": 1},
  "timebase_ticks_per_second": 12,
  "frame_ticks": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
  "duration_seconds": "2.0",
  "endpoint_rule": "left-closed-right-open",
  "frames": [
    {
      "index": 0,
      "file": "frames/frame-0000.png",
      "file_sha256": "sha256:<hex>",
      "pixel_sha256": "sha256:<hex>"
    }
  ],
  "bundle_digest": "sha256:<hex>",
  "provenance": {
    "generator": "<fixture-builder-id>",
    "generator_version": "<version>",
    "seed": 0,
    "clean_reference_in_input": false
  }
}
```

Rules:

- `frame_ticks[i] == i` in v0.1.
- `bundle_digest` is the SHA-256 of canonical JSON containing the contract
  version, dimensions, timing, color-space declaration, and the ordered list of
  `file_sha256` and `pixel_sha256` values. It does not include paths, timestamps,
  or the `provenance.seed` field.
- `frames` MUST be sorted by `index` and contain exactly 24 entries.
- The manifest MUST NOT reference `eval/`, ground truth, or a clean reference.
- `provenance.seed` is recorded, not part of the bundle identity; the degraded
  pixels are the identity.

### 4.2 PNG requirements

- PNG color type 2 (truecolor), bit depth 8, no alpha, no palette, no
  interlacing.
- No `iCCP`, `gAMA`, `cHRM`, or `sRGB` chunk that changes decoded samples.
- Dimensions exactly 256 × 256.
- File names are zero-padded to four digits.
- `pixel_sha256` is computed over raw RGB8 bytes, row-major, top-left origin,
  with no row padding.

### 4.3 MP4 ingest profile

When the source is MP4:

```text
container: MP4
video codec: H.264
pixel format: yuv420p
frame count: 24
frame rate: 12/1 constant
size: 256x256
audio: none (or explicitly dropped and recorded)
color: BT.709 matrix, TV range (recorded; conversion is explicit)
```

The ingest command records the FFmpeg/ffprobe versions and the exact command.
The resulting PNG bundle is canonical; the MP4 file hash is recorded only as
`source_media_file_sha256`, never as the Video Artifact identity.

## 5. Mask bundle

### 5.1 `mask-manifest.json`

```json
{
  "contract_version": "c-video-repair-contract@0.1",
  "mask_kind": "per-frame",
  "width": 256,
  "height": 256,
  "values": [0, 255],
  "repair_roi": [64, 64, 192, 192],
  "evaluation_roi": [64, 64, 192, 192],
  "feather_px": 1,
  "support_pixels": 4096,
  "frames": [
    {
      "index": 0,
      "file": "masks/frame-0000.png",
      "file_sha256": "sha256:<hex>",
      "pixel_sha256": "sha256:<hex>",
      "support_pixels": 4096
    }
  ]
}
```

Rules:

- `mask_kind` is `constant` or `per-frame`.
- For `constant`, `frames` has one entry and the same mask applies to all 24
  frames; `support_pixels` is the constant support.
- Mask PNGs are grayscale 8-bit, 256 × 256, values only `0` and `255`.
- Support MUST be non-empty, contained in `repair_roi`, and strictly smaller
  than the full frame.
- `repair_roi` and `evaluation_roi` are half-open `[x0, y0, x1, y1]`.
- `feather_px` is in `[0, 8]`. The protection domain is `repair_roi` expanded
  by `feather_px` and clipped to the frame. It is not a repair mask dilation.
- The manifest MUST record a `mask_semantics` string:
  `"255=repair-allowed,0=preserve"`.

## 6. Configuration

### 6.1 `config.json`

```json
{
  "contract_version": "c-video-repair-contract@0.1",
  "clip_id": "S3-ghost",
  "repair": {
    "mode": "temporal-median",
    "window_radius": 2,
    "minimum_observations": 2,
    "max_changed_fraction": 0.25,
    "spatial_fallback": null
  },
  "photometric": {
    "enabled": true,
    "model": "integer-luma-offset",
    "roi": "repair_roi",
    "static_sample_mask": "masks/static-sample.png",
    "max_abs_offset": 32,
    "max_abs_channel_offset": 16
  },
  "ghost": {
    "enabled": true,
    "search_radius_px": 4,
    "min_clean_observations": 2,
    "max_ghost_roi_fraction": 0.25
  },
  "appearance": {
    "metric_only": true
  },
  "determinism": {
    "rounding": "round-half-to-even",
    "random_seed": null
  }
}
```

Rules:

- Unknown top-level fields, unknown `contract_version`, and unknown `mode`
  values MUST fail closed (`EXIT_UNSUPPORTED`).
- `spatial_fallback` MUST be `null` in v0.1. Any non-null value is
  `EXIT_UNSUPPORTED`.
- `random_seed` MUST be `null` in v0.1. A non-null seed is allowed only if a
  later contract revision explicitly adds a stochastic algorithm.
- `photometric.roi` is either `"repair_roi"` or an explicit half-open rectangle
  contained in the protection domain.
- `static_sample_mask` is an explicit grayscale mask that excludes the moving
  object and ghost by at least 2 pixels. It is a user/fixture input, not inferred
  from the clean reference.
- `max_changed_fraction` is the maximum fraction of `repair_roi` pixels that may
  change. Exceeding it fails the run.

## 7. Processing stages

The repair command performs these stages in order:

### Stage A — validation

1. Verify the input bundle digest and every frame hash.
2. Verify the mask manifest and every mask hash.
3. Verify config schema and supported domain.
4. Verify `clean_reference_in_input == false`.
5. Verify the output directory is new or empty.

Any failure is terminal; no repair frame is written.

### Stage B — photometric stabilization

1. Build the static sample set from `static_sample_mask`.
2. Estimate a per-frame integer luma offset and, if enabled, per-channel
   integer offsets, using only the degraded frames.
3. Reject if the offset exceeds the configured bound.
4. Apply the correction only inside the declared photometric ROI.
5. Record the per-frame offsets in the run manifest.

This stage is deterministic integer arithmetic. It does not use the clean
reference.

### Stage C — temporal evidence repair

1. For each masked pixel, collect co-located observations from neighboring
   frames within `window_radius`.
2. Exclude frames where the pixel is outside the mask support or marked
   unreliable.
3. Require at least `minimum_observations` valid observations.
4. Replace the pixel with the per-channel temporal median of valid observations.
5. Leave the pixel unchanged if the requirement is not met; mark it
   `UNRESOLVED`.
6. Record changed-pixel counts and unresolved counts.

No motion compensation, optical flow, warping, or subpixel alignment is used in
v0.1. A moving-object interior is outside the guaranteed domain.

### Stage D — ghost handling

Ghost handling is a declared application of Stage C inside a ghost ROI:

1. The ghost ROI/mask is explicit.
2. The temporal window must contain at least `min_clean_observations` frames in
   which the ghost is absent.
3. If the ghost is present in every frame, or overlaps the object, or the
   changed fraction exceeds the bound, fail closed.
4. Record residual energy before/after as an output diagnostic; reference-based
   scoring happens only in `evaluate`.

### Stage E — sealing

1. Re-read every output frame and compute `file_sha256` and `pixel_sha256`.
2. Verify that pixels outside `protection_domain` are bit-identical to the input.
3. Write `run-manifest.json` with status and per-frame results.
4. Rename the temporary directory to the final run directory.

If Stage E fails, the run is `FAILED` and no success manifest is written.

## 8. Output manifest

### 8.1 `run-manifest.json`

```json
{
  "contract_version": "c-video-repair-contract@0.1",
  "run_id": "run:<hex>",
  "status": "SUCCESS",
  "exit_code": 0,
  "scenario": {
    "kind": "synthetic-controlled",
    "clip_id": "S3-ghost",
    "frame_count": 24,
    "width": 256,
    "height": 256,
    "pixel_format": "RGB8",
    "fps": {"numerator": 12, "denominator": 1},
    "timebase_ticks_per_second": 12,
    "frame_ticks": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
    "duration_seconds": "2.0",
    "endpoint_rule": "left-closed-right-open"
  },
  "input": {
    "bundle_digest": "sha256:<hex>",
    "video_manifest_sha256": "sha256:<hex>",
    "mask_manifest_sha256": "sha256:<hex>",
    "config_sha256": "sha256:<hex>",
    "clean_reference_in_input": false
  },
  "scope": {
    "repair_roi": [64, 64, 192, 192],
    "evaluation_roi": [64, 64, 192, 192],
    "feather_px": 1,
    "protection_domain": [63, 63, 193, 193],
    "mask_semantics": "255=repair-allowed,0=preserve",
    "photometric_roi": [64, 64, 192, 192]
  },
  "algorithm": {
    "id": "cvr-temporal-median@0.1",
    "implementation": "<module/function>",
    "parameters": {"window_radius": 2, "minimum_observations": 2},
    "random_seed": null,
    "tool_versions": {
      "python": "3.12.x",
      "png_codec": "cvr-png-rgb8-filter0@0.1",
      "ffmpeg": "<version or null>"
    },
    "code_commit": "<git sha>"
  },
  "output": {
    "frames": [
      {
        "index": 0,
        "file": "frames-repaired/frame-0000.png",
        "file_sha256": "sha256:<hex>",
        "pixel_sha256": "sha256:<hex>",
        "status": "REPAIRED",
        "changed_pixels": 1234,
        "unresolved_pixels": 0
      }
    ],
    "media": {
      "before_mp4": {"file_sha256": "sha256:<hex>", "role": "presentation-only"},
      "after_mp4": {"file_sha256": "sha256:<hex>", "role": "presentation-only"},
      "comparison_mp4": {"file_sha256": "sha256:<hex>", "role": "presentation-only"}
    }
  },
  "metrics": {"file": "metrics.json", "file_sha256": "sha256:<hex>"},
  "determinism": {
    "class": "D0",
    "platform": "<os-arch>",
    "mp4_byte_identity_claimed": false
  },
  "errors": []
}
```

Rules:

- `run_id = "run:" + sha256(canonical JSON of contract version, bundle digest,
  mask manifest digest, config digest, algorithm id, and code commit)`.
- `status` is `SUCCESS`, `PARTIAL`, or `FAILED`.
- `exit_code` must match the process exit code.
- `output.frames` contains exactly 24 entries in index order.
- Per-frame `status` is `UNCHANGED`, `REPAIRED`, `UNRESOLVED`, or `SKIPPED`.
- `output.media` is present only after a successful `export`.
- `metrics` is present only after a successful `evaluate`.
- An `execution` block MAY contain timestamps, durations, host names, and log
  paths. It is excluded from `semantic_digest`.
- `semantic_digest` is computed over canonical JSON of the manifest with the
  `execution` block removed.

## 9. Metrics report

### 9.1 `metrics.json`

```json
{
  "contract_version": "c-video-repair-contract@0.1",
  "clip_id": "S3-ghost",
  "reference": {
    "reference_manifest_sha256": "sha256:<hex>",
    "frames": [{"index": 0, "pixel_sha256": "sha256:<hex>"}]
  },
  "metrics": [
    {
      "id": "ghost_residual_energy",
      "formula": "cvr-metric-ghost-residual@0.1",
      "unit": "code_value",
      "region": "declared_trailing_region",
      "input": 12.345678,
      "output": 4.567890,
      "relative_improvement": 0.630000,
      "threshold": 0.30,
      "pass": true
    }
  ],
  "guards": [
    {
      "id": "unauthorized_region_exact",
      "formula": "cvr-guard-unauthorized@0.1",
      "value": 0,
      "threshold": 0,
      "pass": true
    }
  ],
  "overall": {"pass": true}
}
```

Rules:

- Every metric row has a stable `id` and a versioned `formula`.
- `region` refers to a region declared in the fixture or mask manifest; it is
  not chosen during evaluation.
- `input` is the degraded input measured against the clean reference.
- `output` is the repaired output measured against the clean reference.
- `relative_improvement = 1 - output / input` when `input > 0`; otherwise the
  metric is `null` and `pass` is `false` with `reason: "ZERO_DENOMINATOR"`.
- `overall.pass` is true only if every required metric and guard passes.
- The report does not contain paths to the clean reference beyond hashes.

## 10. Export profile

### 10.1 Frame encoding

- Repaired PNG: color type 2, bit depth 8, filter 0, stored DEFLATE blocks.
- Encoder identity: `cvr-png-rgb8-filter0@0.1`.
- This makes PNG bytes deterministic independent of the zlib version, in the
  same spirit as the existing SVM mask encoder
  (`spec/16-opencv-artifact-analysis.md`, "binary mask" paragraph).
- File size is not a constraint for 24 frames at 256 × 256.

### 10.2 MP4 profile

```text
ffmpeg -y -hide_banner -loglevel error \
  -framerate 12 -start_number 0 -i frames/frame-%04d.png \
  -an -vf "scale=in_range=full:out_range=tv:out_color_matrix=bt709" \
  -c:v libx264 -pix_fmt yuv420p -preset medium -crf 16 \
  -g 12 -keyint_min 12 -sc_threshold 0 \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -movflags +faststart \
  output.mp4
```

- `before.mp4` uses the input frames; `after.mp4` uses the repaired frames.
- `comparison.mp4` uses `hstack` of the two frame sequences, followed by the
  same RGB-to-YUV conversion:
  `-filter_complex "[0:v][1:v]hstack=inputs=2,scale=in_range=full:out_range=tv:out_color_matrix=bt709[v]" -map "[v]"`,
  producing 512 × 256, left before, right after.
- All MP4s are silent (`-an`).
- Frame count, frame rate, duration, and PTS range must match.
- Encoder identity, version, and exact arguments are recorded in the manifest.
- MP4 bytes are not semantic identity. Decoded frames are checked in `verify`.
- If the frozen FFmpeg build does not support an option above, the run must
  record the substitute command and fail `verify` unless the decoded checks
  still pass.

### 10.3 Media verification

`verify` MUST run `ffprobe` and a full decode. Required checks:

| Check | Expected |
| --- | --- |
| video stream count | 1 |
| audio stream count | 0 |
| codec | `h264` |
| pixel format | `yuv420p` |
| width × height | 256 × 256 (comparison: 512 × 256) |
| `nb_frames` | 24 |
| `avg_frame_rate` | `12/1` |
| duration | 2.0 s ± 0.01 s |
| decode errors | 0 |
| decoded frame count | 24 |

## 11. Hashing and canonicalization

| Identity | Definition |
| --- | --- |
| `file_sha256` | SHA-256 of file bytes |
| `pixel_sha256` | SHA-256 of raw RGB8 bytes, row-major, top-left origin |
| `bundle_digest` | SHA-256 of canonical JSON of ordered frame hashes plus metadata |
| `mask_manifest_sha256` | SHA-256 of `mask-manifest.json` bytes |
| `config_sha256` | SHA-256 of `config.json` bytes |
| `run_id` | SHA-256 of canonical inputs + config + algorithm identity + code commit |
| `semantic_digest` | SHA-256 of canonical manifest JSON minus `execution` |

Canonical JSON:

- UTF-8;
- object keys sorted lexicographically;
- separators `,` and `:` with no extra whitespace;
- arrays preserve order;
- integers are written as integers; floats that affect identity are
  prohibited, except metric report values, which use `.12g`;
- a single trailing newline is appended when writing a file;
- paths, timestamps, hostnames, and durations are excluded from semantic
  identity.

## 12. Exit codes and diagnostic codes

### 12.1 Exit codes

| Code | Name | Meaning |
| ---: | --- | --- |
| 0 | `EXIT_OK` | all required work succeeded |
| 2 | `EXIT_INVALID_INPUT` | missing/invalid input, mask, ROI, config, or output directory |
| 3 | `EXIT_INPUT_DRIFT` | hash/digest mismatch, stale input, or isolation violation |
| 4 | `EXIT_UNSUPPORTED` | valid input outside the supported contract domain |
| 5 | `EXIT_INSUFFICIENT_EVIDENCE` | not enough observations; partial/unresolved result |
| 6 | `EXIT_TOOL_FAILURE` | encoder/decoder/external tool missing or failed |
| 7 | `EXIT_OUTPUT_INVALID` | output verification failed |
| 8 | `EXIT_INTERNAL` | unexpected internal error |

### 12.2 Diagnostic codes

Diagnostics are stable strings in `run-manifest.json.errors` and in stderr.

| Code | Exit | Condition |
| --- | ---: | --- |
| `CVR-E001` | 2 | unknown contract version |
| `CVR-E002` | 2 | frame count is not 24 |
| `CVR-E003` | 2 | frame size is not 256 × 256 |
| `CVR-E004` | 2 | frame rate is not 12/1 |
| `CVR-E005` | 2 | missing, extra, duplicate, or out-of-order frame |
| `CVR-E006` | 2 | invalid PNG structure, bit depth, color type, alpha, or interlace |
| `CVR-E007` | 2 | invalid ROI or ROI outside the frame |
| `CVR-E008` | 2 | mask dimensions or values are invalid |
| `CVR-E009` | 2 | empty mask or full-frame mask |
| `CVR-E010` | 2 | mask support outside `repair_roi` |
| `CVR-E011` | 2 | feather outside `[0, 8]` |
| `CVR-E012` | 2 | output directory already contains a sealed run |
| `CVR-E013` | 3 | input or mask hash mismatch |
| `CVR-E014` | 3 | clean reference present in the repair input |
| `CVR-E015` | 4 | unsupported pixel format or color space |
| `CVR-E016` | 4 | audio present without explicit drop |
| `CVR-E017` | 4 | variable frame rate or rotation metadata |
| `CVR-E018` | 4 | unsupported algorithm mode or config field |
| `CVR-E019` | 4 | spatial fallback requested |
| `CVR-E020` | 4 | moving-object interior repair requested |
| `CVR-E021` | 5 | insufficient temporal observations |
| `CVR-E022` | 5 | flicker offset exceeds the bound |
| `CVR-E023` | 5 | ghost out of domain |
| `CVR-E024` | 5 | changed-pixel fraction exceeds the bound |
| `CVR-E025` | 6 | FFmpeg/ffprobe missing |
| `CVR-E026` | 6 | encoder/decoder non-zero exit |
| `CVR-E027` | 7 | output digest or semantic digest mismatch |
| `CVR-E028` | 7 | ffprobe mismatch or decode failure |
| `CVR-E029` | 7 | unauthorized-region pixel changed |
| `CVR-E030` | 8 | internal error |

## 13. Failure and partial-output rules

1. Validation failures produce no repaired frames and no success manifest.
2. Insufficient evidence produces `status: "PARTIAL"`, `EXIT_INSUFFICIENT_EVIDENCE`,
   and a per-frame `UNRESOLVED` status. It does not satisfy acceptance.
3. A tool failure after frames are written produces `status: "FAILED"` and no
   media success claim.
4. A failed run MUST NOT leave a `SUCCESS` manifest, a `before.mp4`/`after.mp4`
   pair with a success claim, or a `metrics.json` with `overall.pass: true`.
5. Re-running with the same `run_id` into the same directory MUST fail; a new
   run uses a new directory.
6. `run.log` MAY contain absolute paths and timestamps; it is never part of
   semantic identity.

## 14. SVM Core and Revision boundary

C-MVP v0.1 does not modify SVM state. The rules are:

1. No new `svm` CLI command, Operation, Schema field, Change type, or policy.
2. No file, network, clock, or UI read inside Operation evaluation
   (`INV-EVAL-003`).
3. Repaired frames are external Derived Artifacts, not Immutable Values and not
   Entity geometry (`spec/05-system-boundaries.md`, "Immutable Value").
4. If a later round needs a Document change, it MUST go through:
   Artifact -> Adapter -> Proposal -> registered Change -> atomic Transaction
   -> `ProposalAcceptor.accept()` -> new Revision.
5. `RevisionStore.commit()` MUST NOT be called by the repair tool, an Adapter,
   or a plugin. It is a trusted internal mechanism
   (`spec/05-system-boundaries.md`, "Proposal and Proposal Acceptor";
   `svm/proposals.py:185-253`).
6. The repair tool MUST NOT present repaired frames as FINAL SVM output, and
   MUST NOT use a stale or PREVIEW SVM result as a substitute
   (`INV-EVAL-005`).

## 15. Interface table for practice and CI

| Item | Frozen by this contract | Owner |
| --- | --- | --- |
| Canonical input layout | §3, §4 | practice implements; CI fixtures |
| Mask layout and coordinates | §5 | practice implements; CI fixtures |
| Config schema | §6 | practice implements; CI validates |
| CLI subcommands and exit codes | §2, §12 | practice implements; CI invokes |
| Run manifest fields | §8 | practice emits; CI parses |
| Metrics formulas | `acceptance-criteria-v0.1.md` | CI implements independently |
| MP4 profile | §10 | practice implements; CI verifies |
| Determinism checks | §11, §12 | CI implements |
| SVM boundary | §14 | review verifies |

The practice line MUST NOT change a frozen threshold to make a failing test
pass. A proposed threshold change goes back to the C planning line before the
holdout run.

## 16. Open contract questions

These are deliberately unresolved until the C planning line freezes them:

1. Canonical input: PNG bundle (recommended) versus MP4-only. This contract
   recommends the PNG bundle because H.264 decoding is not a stable pixel
   identity across decoder versions.
2. Exact comparison layout: 512 × 256 side-by-side is proposed; labels are
   prohibited in v0.1.
3. MP4 CRF and encoder preset: `crf 16`, `preset medium` is proposed; the
   values affect only presentation, not pixel metrics.
4. Cross-platform MP4 tolerance: proposed MAE <= 2.0 code values and
   PSNR >= 40 dB; CI must freeze the actual tolerance.
5. Whether any future repair result becomes an SVM Document. The recommendation
   is "no" for v0.1; if required, it needs a separate accepted Proposal and
   Change design.
