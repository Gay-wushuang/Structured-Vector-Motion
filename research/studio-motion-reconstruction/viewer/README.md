# Inspect a reconstruction candidate

From the repository root, point the viewer at the original AVI/FFV1 clip and
the candidate JSON previously produced by the reconstruction experiment.
Use a new output file and an existing parent directory.

```powershell
python -B -m research.studio-motion-reconstruction.viewer `
  --input build/studio-reconstruction-v3/synthetic.avi `
  --candidate build/studio-reconstruction-v3/candidate.json `
  --synthetic --output build/studio-reconstruction-v3/preview.html
```

Open the generated HTML in a browser. It works offline as a standalone file.
Scrub the recorded frame indices, click the subject rows to inspect individual
ticks, or play the clip at its recorded frame cadence. The vector panel draws
the subject's rectangle runs at its observed translation. A striped cell
marks an unknown observation, including visible losses caused by occlusion
in the synthetic fixture. The viewer displays the algorithm's stated cause
and leaves that subject out of the candidate frame.

Use **导出当前帧 SVG** to prepare a download and show the SVG source for the
observed geometry. Import the still SVG separately in Studio to edit its shapes. The
file carries neither motion nor accepted identity. Export is disabled when
every subject is unknown at the current tick.

For a raw candidate, select a subject and an observed tick after an evidence
gap. Click the subject in the original frame, or enter its zero-based source
pixel coordinates. **重新锚定** queues a point for review. For the synthetic
fixture, choose `amber` at tick 68 and pixel `(141, 66)`. Export the queued
hash-bound decisions with **导出复核 JSON**. Save the file as `reanchors.json`
and replay the decisions through the research verifier.

```powershell
python -B -m research.studio-motion-reconstruction.anchors `
  --candidate build/studio-reconstruction-v3/candidate.json `
  --reanchors build/studio-reconstruction-v3/reanchors.json `
  --output build/studio-reconstruction-v3/reviewed.json
```

Build another preview from `reviewed.json` to inspect the verified research
decisions. Reviewed inputs display the resulting observations and do not
offer additional anchors. Pending points never change the raw candidate.

Use **选择可编辑的平移片段** to pick one subject and exact start and end
ticks. The viewer rejects gaps and exports a hash-bound selection. The
[segment authoring command](../README.md#author-an-editable-segment) then
replays the source and creates an editable project only after confirmation.

The viewer checks the candidate profile, AVI digest, decoded frame digests,
and time mapping before embedding PNGs. It requires the existing OpenCV
analysis extra and refuses to overwrite a result. The page is a read-only
research artifact classified as `experimental-only-not-svm-evidence`.

```powershell
python -B -m unittest research.studio-motion-reconstruction.viewer.test_viewer -v
```
