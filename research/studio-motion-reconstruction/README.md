# Guided vector motion observations

The experiment asks whether a user can identify a rigid flat-color object by
clicking the first frame, then reuse its first-frame geometry across the clip.
The output is a research candidate JSON with primitive geometry, sampled
translations, and explicit unknown intervals. Its classification is
`experimental-only-not-svm-evidence`. The runner never opens the SVM Revision
Store or authors a Document.

## Input profile

- One local RIFF AVI/FFV1 stream, constant frame rate, exact integer mapping
  onto the requested SVM tick rate, up to 120 frames, 921,600 pixels per frame,
  and 8 MiB encoded input. The runner reuses the repository's bounded AVI
  metadata parser. OpenCV's bundled FFmpeg backend supplies BGR24 pixels.
- One or two first-frame pixel clicks and stable user-provided labels. Two
  selected subjects must have distinct exact BGR colors. The full component
  must be visible on the first frame. Selected geometry is bounded to 32,768
  pixels in its bounding box and 128 rectangles.
- Motion is restricted to integer-pixel translations. Rotation, scaling,
  gradients, antialiasing, compressed color variation, and camera compensation
  remain outside this profile.

## Candidate and evidence

OpenCV finds the clicked 8-connected component by exact color. A run-length
rectangle decomposition stores its pixel geometry in local integer
coordinates. The search records a translation only when exactly one shape
matches throughout the full frame, remains away from the frame edge, and
satisfies the motion budget from the last observation. The runner records
`UNKNOWN` on ambiguous or absent geometry and performs no interpolation
through an unknown interval. A match after a gap is explicitly labeled.
An indistinguishable decoy can still produce a unique match when the original
is absent. The recorded label represents the user selection and an association
hypothesis confined to this profile.

The candidate binds the exact source bytes, decoded frame pixel digest, frame
index and rational time, integer tick, user clicks, OpenCV build, wheel, NumPy
version and runner SHA-256. Replay compares the entire candidate byte for byte
in the recorded environment. The independent evaluator opens synthetic ground
truth after candidate generation. The candidate runner accepts only the AVI
and click settings.

## Replay

Use the repository's Python analysis environment with bundled FFmpeg support.
Run the commands from the repository root. A run name must be fresh. The
generator creates that directory. Candidate publishing requires a filesystem
that supports same-directory hard links. It rejects an existing output.

```powershell
New-Item -ItemType Directory -Force build | Out-Null
$run = 'build/studio-reconstruction-local'
python -B -m research.studio-motion-reconstruction.fixture generate $run
python -B -m research.studio-motion-reconstruction.run --input "$run/synthetic.avi" --seeds "$run/seeds.json" --output "$run/candidate.json"
python -B -m research.studio-motion-reconstruction.run --input "$run/synthetic.avi" --seeds "$run/seeds.json" --verify "$run/candidate.json"
python -B -m research.studio-motion-reconstruction.fixture evaluate "$run/fixture.json" "$run/candidate.json" "$run/metrics.json"
python -B -m unittest research.studio-motion-reconstruction.test_reconstruction -v
```

Use the [offline candidate viewer](viewer/README.md) to step through the source
and reconstructed geometry together and inspect unknown intervals.

## Measured scope

The 4-second `SYNTHETIC` example has two flat-color objects, 48 frames at 12 FPS,
and one occluder. On Python 3.12 with OpenCV 4.14.0
(`opencv-python-headless` 4.14.0.94) and NumPy 2.5.2:

| Metric | First-frame hold | Translation observations |
| --- | ---: | ---: |
| Visible mean position error | 55.25 px | 0 px |
| Visible max position error | 141 px | 0 px |
| Occluded occurrences reported as visible | 17/17 | 0/17 |
| Fully visible occurrences observed | 79/79 | 79/79 |

The template geometry achieved mask IoU 1.0 for both subjects. Decoded hashes
matched all 48 independently generated pixel arrays. The candidate replay was
byte-identical. The command took 1.39 seconds, including interpreter startup,
on the development machine. These results cover controlled lossless inputs.
They establish neither natural-video recovery nor a formal
admission for geometry, identity, or Motion Tracks.

## Failure probes

Run `python -B -m research.studio-motion-reconstruction.diagnose --output
build/studio-reconstruction-diagnosis-local` with a fresh output directory.
In the appearance collision, the baseline falsely associated all three frames
of a uniquely visible identical decoy after the original disappeared. In
the pose probe it left all four rotations or uniform scales unknown despite
clean masks, while correctly observing four translations. Both results replayed
byte for byte. Test a masked similarity estimator for the pose failure and
require a new user anchor or independently observable evidence at an identity
gap before attempting formal motion recovery.

### Re-anchor review

Create a second candidate that holds every subject at `UNKNOWN` after loss
of its evidence until it receives a user point on observed geometry:

```powershell
python -B -m research.studio-motion-reconstruction.anchors `
  --candidate "$run/candidate.json" --output "$run/reviewed.json"
```

Optionally pass `--reanchors` with a JSON object containing the exact
`candidate_sha256` and a `reanchors` array. Each decision is
`{"subject":"amber","tick":68,"point_xy":[141,66]}` in source pixel
coordinates. A decision applies at that occurrence and allows checks to
resume until the next evidence gap. The output keeps the decision and
the raw candidate's digest. Source footage, raw observations, and accepted
SVM state stay separate.

## Author an editable segment

The viewer exports a selection with one subject, exact source endpoints, and
the candidate SHA-256. In Studio, click **重建片段**, supply the AVI, the
candidate, and the selection, then replay and examine the two preview frames
before confirming. The same authoring workflow is available from the CLI.
The first invocation reports which observations would
become editable and returns a preview ID:

```powershell
$inputFile = "$run/synthetic.avi"
$candidate = "$run/candidate.json"
$selection = "$run/segment-selection.json"
$preview = python -B -m research.studio-motion-reconstruction.author_translation `
  --input $inputFile --candidate $candidate --selection $selection | ConvertFrom-Json
$preview
```

After reviewing the preview and corresponding source range, accept that exact
ID into a new output directory:

```powershell
python -B -m research.studio-motion-reconstruction.author_translation `
  --input $inputFile --candidate $candidate --selection $selection `
  --accept $preview.preview_id --output "$run/authored-segment"
```

Open `authored-segment/authored.svm.json` using **打开工程** in Studio.
The command replays the candidate against the exact video and authorizes a
single ordinary SVM Proposal with explicit human selection. It rebases the
range to tick zero and records the source correspondence in `receipt.json`.
Each moving rectangle axis has an ordinary editable numeric Track. Exactly
collinear samples use endpoint keys. The command rejects a range that crosses
an unknown interval or starts after an unreviewed evidence gap. Its output is
a human-authored SVM project. The source observations retain their research
classification and confer no SVM Temporal Identity or observed-track authority.

## On-device armor sample validation

Replay the first 73 frames of the user-supplied 1280 × 720, 24 fps MP4 with
the matching OpenCV FFmpeg decoder and NumPy. The source file stays on the
machine. The recorded SHA-256 in `armor-validation/labels.json` binds the
hand-marked plate and landmarks to the exact clip.

```powershell
New-Item -ItemType Directory -Force build | Out-Null
$armorVideo = Read-Host 'Path to the local armor sample MP4'
py -3.12 -B -m research.studio-motion-reconstruction.armor_validation `
  "$armorVideo" build/studio-armor-replay
```

Use a fresh output directory. The overlay in `comparison.png` shows the
hand-marked outline translated by the fitted motion and the same outline
after a +24 px edit at tick 48. Open `before.svm.json` or `after.svm.json`
with **打开工程** to inspect the editable track values and timeline. The two
SVGs show the SVM renderer's band approximation at tick 48. `report.json`
records holdout and sparse manual landmark residuals, interpolation error,
source and annotation hashes, and the revision IDs. The translation fit
uses fixed-anchor optical flow and withholds a result when the point count or
held-out residual fails the check.

This is a translation-only test on one annotated plate. The held-out points
use the same optical-flow method as the fit. Sparse hand-read landmarks at
four ticks provide a separate check on the measured geometry. The polygon IoU
compares the authored bands with the hand annotation on frame zero. This test
does not evaluate full-frame vectorization, occlusion, Group motion, video
repair, or stable identity recovery. Its outputs are tagged
`experimental-only-not-svm-evidence`.
