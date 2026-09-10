# Camera Motion Slice v0

`presentation.camera` records finite `position`, `rotation_degrees`, and positive
uniform `scale`. Evaluation produces the outer world-to-view transform
`S(scale) × R(-rotation) × T(-position)`; it never rewrites Entity, Group, or
construction state. `svm-motion@0.6` permits numeric `linear` or `ease-in-out`
Tracks for `position.x`, `position.y`, `rotation_degrees`, and `scale`. Camera
scale remains positive. Viewport resolution and viewBox remain renderer inputs.
Perspective, depth, masks, and camera-specific easing are outside this slice.
