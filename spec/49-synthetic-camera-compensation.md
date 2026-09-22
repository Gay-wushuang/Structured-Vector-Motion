# Synthetic Camera Compensation v0 (Golden S9B)

## Scope

S9B separates a renderer-observed similarity into Camera-induced view motion
and target world motion. It supports one explicitly selected, provably static
anchor and one explicitly bound target across one contiguous tick sequence.
Only translation, uniform scale, and rotation are supported.

Camera evidence is external evidence, not Camera Document state. Accepting it
does not create or modify a Camera Track. Compensated motion evidence is also
not Track authority; the existing explicit Motion Target Binding and observed
translation, scale, and rotation CREATE adapters remain the authoring boundary.

## Coordinate convention

The renderer applies the outer world-to-view similarity
`V = S(camera.scale) × R(-camera.rotation) × T(-camera.position)` after each
Group transform. For consecutive frames, the static anchor identifies
`A = V1 × inverse(V0)`. Given the target's observed view-space relative
similarity `B`, target world-relative motion is:

```text
W = inverse(V1) × B × V0
```

Translation is not obtained by subtracting two translation fields. Source and
target observed centers are independently mapped through `inverse(V0)` and
`inverse(V1)`. Scale is the uniform scale of `W`; rotation is its signed
shortest interval angle and remains unwrapped when the existing authoring
adapter accumulates absolute values.

## Evidence boundaries

`svm-observed-camera-similarity-0.1` records the explicit anchor, source S4
evidence, and verified relative/absolute view similarities. The v0 fixture
requires an identity Camera baseline at the first tick. Later view transforms
are accumulated only from anchor observations.

`svm-camera-compensated-translation-motion-0.1` and
`svm-camera-compensated-similarity-motion-0.1` record both target evidence
lineages, Camera evidence, exact tick pairing, compensation policy, source
Revision, and target Temporal Identity. ChangeAuthority rederives all bytes
before acceptance.

The anchor must be an explicit Recovery Document Entity. It may not have an
Entity Track or belong to a Group with a Track. This is the currently provable
static-anchor subset; automatic anchor discovery and indirect hierarchy
analysis are outside S9B.

## Exclusions

Camera Track authoring, non-identity initial Camera recovery, automatic anchor
or target discovery, perspective, skew, non-uniform scale, easing inference,
raster/video input, occlusion, deformation, and multi-object optimization are
outside this slice.
