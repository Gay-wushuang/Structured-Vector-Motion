# Verified Observed Rotation Track CREATE v0.1 (Golden S6B)

S6B consumes accepted S4 similarity evidence and an explicit Group Motion
Target Binding. It authors one new linear `rotation_degrees` Group Track;
replacement and re-authoring are outside this milestone.

S4 values are shortest signed interval deltas. S6B starts at the captured
static Group `rotation_degrees` baseline and cumulatively adds each contiguous,
finite, `SUPPORTED` rotation component. The resulting Track values are
absolute, unwrapped angles: `170 + 20 = 190`, never `-170`.

Rotation confidence is component-specific: supported rotation may author even
when scale is uncertain; uncertain or rejected rotation fails closed. Existing
Group rotation Tracks fail with an explicit re-authoring error.

The typed source-verification Change rederives samples, Track identity,
Keyframe identity, target, provenance, baseline, binding, evidence, and
timebase from the frozen accepted inputs. Preview is pure; acceptance mutates
only animation Track/keyframes and its motion semantics metadata. The Track
uses provenance type `ObservedRotationTrack` and authoring identity
`svm-verified-observed-rotation-authoring@0.1`.
