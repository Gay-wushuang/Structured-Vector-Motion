# Controlled Raster Camera Recovery v0

Recovery inputs: `tick_000.png`, `tick_012.png`, `tick_024.png`, `tick_036.png`,
their explicit ticks, `recovery-base.svm.json`, and `selectors.json`.
The test explicitly declares `entity:anchor-a` and `entity:anchor-b` static and
binds `entity:recovery-target`'s Temporal Identity to the existing Group.

The three analysis-local selectors are explicit caller choices, not an ordering
heuristic in the frontend. Each role produces independent observation Artifacts
and a distinct Temporal Identity. All components are black on white and remain
separated and visible. The unrendered Group companion is not an observed role.

The 1200x900, 8-bit grayscale PNG fixtures were generated offline: transform the
baseline polygon vertices with the repository's Group and Camera conventions,
round vertex coordinates to nearest integers, and use OpenCV `fillPoly` with
default LINE_8 (no antialiasing), then PNG encoding. Source vertices and states
are recorded in `ground-truth.json` for final assertions. Recovery never reads
that file until its Document and eight Tracks are complete; tests never regenerate
PNGs. No SVG observation adapter participates in recovery.

Camera moves by pan+rotation+zoom at 0→12 and 24→36 and holds at 12→24. Target
translation, rotation and scale change in all intervals around origin [470,545].
The whole PNG changes during the Camera hold because the Target still moves;
both anchor pixel geometries remain identical. A separate repeated-PNG test
uses `tick_000.png` in four temporal slots.

`disagree_*.png` is the negative fixture: Anchor B actually moves +10 world pixels
by tick 12, holds at 24 and reaches +20 by tick 36, while the declared Recovery
Document still claims a static anchor. Its similarity fits remain supported, but
its Camera hypothesis disagrees with Anchor A and strict measured consensus
rejects. This is not an outlier-removal example.

Normative policy, coordinate conventions, tolerances and measured errors:
`spec/57-controlled-raster-camera-recovery.md`.
