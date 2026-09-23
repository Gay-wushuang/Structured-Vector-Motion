# S10B repeated-frame occurrences

`ground-truth.svm.json` is a hold → move → hold scene sampled at ticks
0, 12, 24, 36 (12 ticks/second). Its asymmetric Group has fixed origin [37, 43],
rotation 10, 10, 25, 25 and scale 1, 1, 1.2, 1.2. Translation moves from [0, 0]
to [6, -2]; the shared Camera also holds, moves, then holds.

Render with viewBox [0, 0, 200, 120]. Frames 0/12 have identical bytes, as do
24/36. Import those bytes without modifying them: each pair shares one Artifact
ID. Select the explicit SVG occurrence producer policy @0.2 to distinguish ticks.

`tests/test_repeated_frame_occurrences.py` verifies this fixture against its
construction, then exercises accepted observation → R0 → R1 → S0/S4 → Camera
compensation → explicit binding → Group and Camera Track authoring. It also
tests an all-static variant, which reuses one SVG blob across all four ticks.
