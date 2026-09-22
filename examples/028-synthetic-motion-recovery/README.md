# Synthetic Motion Recovery v0

`ground-truth.svm.json` is a three-second, linear, hand-authored animation at
12 ticks per second. `recovery-base.svm.json` has equivalent static construction
and the same explicit Group baseline, but contains no animation Tracks.

The checked-in observation SVGs are rendered only from the Ground Truth through
`MotionEvaluator.evaluate(tick)` and `SVGRenderer`. Recovery consumes those SVG
Artifacts and tick metadata; it never reads the Ground Truth Track payload.

The integration test runs the formal SVG geometry observation, temporal
correspondence, temporal identity, translation evidence, similarity evidence,
explicit Group binding, and the three existing observed-Track CREATE adapters.
It then samples and renders the recovered Document at ticks 0, 12, 24, and 36.

Camera, style recovery, easing inference, automatic Group discovery, and
automatic target binding are intentionally outside this fixture.
