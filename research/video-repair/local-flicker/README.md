# Local Flicker Candidate Preview

Status: **research-only; experimental-only-not-svm-evidence**.
This standalone prototype does not import SVM, create a Proposal, call
`ProposalAcceptor`, or modify a Document or Revision. A preview is not an
accepted repair. Real-video validation is `NOT_RUN` until a separately reviewed
real sample and reference/quality protocol are available.

## Requirements and input boundary

Python 3.12 with NumPy and OpenCV (`cv2`), plus `ffmpeg` and `ffprobe` on PATH.
FFmpeg must support FFV1 and libx264. No model, GPU, paid API, or installation
is performed by this prototype.

Input must have a single video stream, optional audio streams, even dimensions
within 1280×720 pixels, 2–120 frames and at most 256 MiB of decoded BGR bytes.
It must be zero-start constant frame rate with each decoded PTS exactly equal to
`frame_index / fps` as a rational number. VFR, missing/rounded timestamps,
multiple video or other auxiliary streams, rotation metadata, HDR and unknown,
high-bit-depth or alpha pixel formats fail closed. Supported 8-bit opaque color
pixel formats are enumerated in `pipeline.py`. This is a deliberately bounded
research input profile, not a general media importer.

The static mask is a same-size single-channel PNG containing only 0 and 255.
At least 256 pixels must be selected and the feathered interior must contain at
least 128 pixels. No tracking or identity inference occurs.

FFmpeg converts input to BGR24. Corrections operate in encoded BGR space, not
linear light. Candidate and comparison outputs are lossy H.264/yuv420p, CRF 18;
the report separates their decode error from the exact BGR pre-encode check.
Output audio is **always dropped**. The manifest records input audio streams,
the explicit drop and decoded output streams. Color metadata is recorded but
not guaranteed to be preserved; HDR and alpha are rejected.

## Run

From the repository root, with an already existing parent output directory:

```powershell
python -B research/video-repair/local-flicker/main.py synthetic --output build/flicker-new-run
```

For an independently supplied video and static mask:

```powershell
python -B research/video-repair/local-flicker/main.py preview `
  --input path/to/short-video.mp4 --mask path/to/binary-mask.png `
  --output build/flicker-new-run
```

Choose a new output directory every time: `mkdir` fails if it already exists.
Existing output files are never intentionally replaced, even by the internal
worker. A failed run can leave a partial newly created directory, without a
final `experiment-manifest.json`; do not treat it as a completed result.
The input and mask hashes are checked again after the worker finishes.

Default candidate B is selected before evaluation. Use
`--method C_low_frequency` to inspect C instead. Parameters are `--radius`
(frames, default 2), `--feather` (pixels, default 6), `--max-gain` (default
1.3), and `--sigma` (pixels, default 6). Gain limits, ROI darkness/clipping and
the global scene-cut check are conservative fail-closed limits, not quality
guarantees.

## Algorithms and evaluation

- A: original decoded frames, no correction.
- B: per-frame ROI median luminance, corrected toward a local temporal median
  with bounded gain and inside-mask feathering.
- C: compare Gaussian low-frequency luminance fields in the temporal window;
  apply a bounded local gain and the same feathering.

Each method applies gain to the current frame only: neighboring frame textures
are never substituted or blended. Both B and C can still respond to motion,
occlusion, a moving object changing ROI statistics, low light or genuine
illumination changes. C can modify object edges as the blurred field moves.
The scene-cut heuristic and short temporal window do not establish motion
compensation or general flicker detection.

Synthetic mode generates a deterministic textured, colored scene with a moving
object, static mask, injected local exposure flicker and separate clean GT.
The worker receives only source and mask paths. A separate evaluator runs after
the worker exits and reads GT; this is process/data-flow separation, not OS
filesystem isolation. Preview mode has no GT input and does not emit PSNR/SSIM.

`metrics.json` compares all three BGR pre-encode outputs, including ROI median
luminance variation, color statistics, outside-mask max difference, boundary
gradient, texture Laplacian error and object-edge IoU. GT-only PSNR/SSIM and
errors apply only to synthetic input. Object-edge IoU is a Canny-edge proxy in
a GT silhouette neighborhood, not an identity or segmentation metric.
`candidate_encoding` compares decoded H.264 against the candidate's pre-encode
pixels; nonzero values there do not imply the repair modified pixels outside
the ROI. Worker peak RSS includes its native allocations but excludes FFmpeg
child processes; wall time is one observation, not a benchmark.

`comparison.mp4` places original preview on the left and selected candidate on
the right. `mask_preview.png` shows the static ROI. The manifest records input
codec/pixel format/dimensions/FPS/time base/PTS/audio/color, versions,
parameters, hashes, decode checks and classification. Intermediate `.npy`
arrays and synthetic GT remain in the output for offline reproducibility.

## Tests

```powershell
python -B -m unittest discover -s research/video-repair/local-flicker/tests -v
```

Tests create temporary videos and audio, run the research-only prototype, and
verify no-flicker behavior, ROI improvement, feathering, outside-ROI equality,
replay, GT data-flow isolation, explicit audio drop, no-GT metrics, output
decode/time mapping, and refusal to overwrite. They do not establish results for
ordinary real videos or formal SVM acceptance.
