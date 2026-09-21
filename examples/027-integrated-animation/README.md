# Demo 002 — Integrated Hand-authored Animation

This directory contains a six-second, hand-authored SVM animation. The
Document is the ground truth; every SVG under `frames/` is produced by the
normal `MotionEvaluator.evaluate(tick) -> SVGRenderer.render(scene)` pipeline.

- Timebase: 12 ticks per second
- Duration: 72 ticks / 6 seconds
- Key snapshots: ticks 0, 12, 24, 36, 48, 60, and 72
- Group members: `entity:demo-body` and `entity:demo-accent`
- Group motion: eased horizontal translation, linear vertical translation,
  eased absolute rotation, and eased uniform scale
- Style motion: eased accent opacity plus discrete held body fill
- Camera motion: linear horizontal pan plus eased uniform zoom

The static reference ellipse makes the camera and object motion visually
distinguishable. The background, construction graph, entity identities, Group
membership, authored geometry, and render-stack order remain unchanged while
the animation is sampled.
