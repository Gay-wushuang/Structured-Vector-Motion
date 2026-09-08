# Group Motion Authoring Demo 001

This is a hand-authored 6-second SVM animation, not a Golden test or a new Core
milestone. It uses a fixed camera, eleven existing primitives, three explicitly
confirmed Groups, and only the frozen Group Transform Track channels.

```text
Group A: translate x/y + rotate + uniform scale
Group B: translate x/y + rotate + uniform scale
Signal Group: translate y + rotate + uniform scale
```

Fill and opacity are static authored styles. No camera animation, mask,
deformation, optical flow, recovery, or additional interpolation semantics are
used.

## Rebuild

From the repository root:

```powershell
python demo/001-group-motion/build_demo.py
```

The script validates and writes `scene.svm.json`, samples ticks `0..144` at 24
ticks per second, renders 145 deterministic SVG frames, rasterizes matching PNG
frames through a local headless browser, and encodes `demo.mp4` and `demo.gif`
with FFmpeg.

## First authoring observations

1. Rigid Group motion is sufficient to establish composition, collision,
   counter-motion, and scale accents without losing primitive identity.
2. Linear interpolation is continuous but velocity changes are visible at
   tightly spaced Keyframes. Easing is a more immediate motion-quality limit
   than Camera or Mask in this fixed shot.
3. The Group boundary is adequate for the two rigid figures and signal pair.
   The first visual limitation is the absence of a small style/opacity rhythm;
   organic Shape deformation would matter after that. This Demo does not by
   itself justify adding either capability to Core.
