# S11C: explicit multi-object raster recovery

Four checked-in observations at ticks 0, 12, 24 and 36 contain two static
asymmetric anchors and two independently moving asymmetric targets. Canvas:
1200 x 900; opaque 8-bit grayscale, black foreground/white background,
non-antialiased, separated and fully visible. No test generates these PNGs.

`recovery-base.svm.json` registers four static paths and two identity-transform
Groups, with unrendered companion Entities. Target A's origin is (470,545),
Target B's (135,545); neither is its bounds center. Anchors have no Group or
Track. All motion Tracks are recovered through existing accepted Proposals.

| Tick | A translation / angle / scale | B translation / angle / scale | Camera position / angle / scale |
| --- | --- | --- | --- |
| 0 | (0,0) / 0 / 1 | (0,0) / 0 / 1 | (0,0) / 0 / 1 |
| 12 | (8,-4) / 4 / 1.04 | (-6,-8) / -3 / 0.98 | (6,-4) / 2 / 1.025 |
| 24 | (16,-8) / 8 / 1.08 | (-13,-14) / -7 / 1.03 | (6,-4) / 2 / 1.025 |
| 36 | (24,-12) / 12 / 1.02 | (-20,-19) / -11 / 1.01 | (12,-7) / 4 / 1.05 |

Angles are degrees. Camera uses SVM's existing world-to-view convention, not
Group rotation semantics. Frames were prepared offline with SVM's
`_group_transform_matrix`, `_camera_transform_matrix`, `_compose` and `_point`,
then NumPy `rint` to integer vertices and OpenCV `fillPoly(..., LINE_8)` on a
white uint8 canvas. The corresponding final-assertion samples and presented
vertices are in `ground-truth.json`. Recovery never reads that file until all
twelve Tracks have been accepted.

`selectors.json` is the caller's explicit per-tick role selection. A/B component
numbers switch between frames; no runtime matching by component order, area or
position is allowed. Every role follows its own accepted pixel lineage and
Temporal Identity. Two anchor hypotheses produce exactly one consensus, shared
by both target compensations and by Camera Track authoring.

`disagree_012.png` changes only Anchor B's world position by +10 pixels in x at
tick 12. Inserting this frame into the otherwise unchanged sequence makes the
two Camera hypotheses disagree. It is a negative fixture, not a tolerated motion
or an alternate anchor selection.

`verification.json` records complete observed Temporal Identity IDs, Camera
hypotheses, the single consensus, separate compensated S0/S4 IDs and binding IDs,
all twelve Track IDs with their targets, and measured errors. It is a report
generated after recovery, not an input or expected-ID shortcut in the tests.

| Recovered quantity | A max error | B max error | Camera max error |
| --- | ---: | ---: | ---: |
| Translation/position, Euclidean pixels | 0.678731 | 0.369452 | 0.624717 |
| Rotation, degrees | 0.085919 | 0.081817 | 0.077883 |
| Scale, absolute ratio | 0.003163 | 0.001756 | 0.000978 |

Presented-geometry maximum errors against raster landmarks: Anchor A 0.479816,
Anchor B 1.434876, Target A 0.585029, Target B 0.931734 pixels. All satisfy the
unchanged S11B limits (target position 1 pixel, angle 0.2 degrees, scale 0.005;
Camera position 1 pixel, angle 0.2 degrees, scale 0.003; geometry 2 pixels).

Camera holds over 12..24 while both targets keep moving. Authoring B preserves
all previously authored A and Camera definitions. Existing evidence verifiers
reject cross-wired identities, bindings, pixel provenance and Track collisions
atomically. See `tests/test_multi_object_raster_recovery.py` and
`spec/58-explicit-multi-object-raster-recovery.md` for the full acceptance proof.

The first trial B contour used (330,590) for its rightmost vertex. Contour
approximation at tick 24 shifted a landmark enough to give 0.796-pixel RMS in
the last interval, correctly exceeding the frozen 0.75-pixel measurement limit.
The final controlled contour uses (330,600). No policy or threshold was changed.
This demonstrates the narrow controlled measurement domain, not robustness to
arbitrary silhouettes or natural images. Similar-shape association, visibility
loss, unobserved-time accuracy and video ingestion are outside this fixture.
