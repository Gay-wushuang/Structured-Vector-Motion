# Verified Observed Camera Track Authoring v0 (Golden S9C)

## Scope

S9C explicitly authors the four existing Camera motion properties from one
accepted `svm-observed-camera-similarity-0.1` Artifact:

```text
position.x
position.y
rotation_degrees
scale
```

Evidence acceptance remains separate from Camera authority. Invoking
`ObservedCameraTracksAdapter` with `camera_target = presentation` is the
explicit authoring intent. All four linear Tracks, their Keyframes, and trusted
provenance are created in one Transaction. S9C is CREATE-only.

## Camera recovery

For the renderer's absolute view transform `V = [A | t]`:

```text
A = scale × R(-camera.rotation)
t = -A × camera.position
```

The authoring adapter therefore recovers:

```text
camera.scale = uniform_scale(A)
camera.rotation = -view_rotation(A)
camera.position = -inverse(A) × t
```

Absolute rotation samples are unwrapped against the preceding sample using the
unique shortest signed step, with the positive 180-degree tie retained. A
wrapped `170 → -170` decomposition consequently authors `170 → 190`.

S9C retains S9B's identity-baseline restriction: the first evidence transform
and the static Recovery Camera must both be position `[0, 0]`, rotation `0`,
and scale `1`. Matrices must be finite, invertible, positive-scale uniform
similarities and intervals must form one exact contiguous chain.

## Authority and provenance

Track IDs bind the authoring policy, Camera evidence Artifact, target,
property, and timebase. Keyframe IDs bind Track identity and tick. Every Track
records `ObservedCameraTrack`, the authoring identity, evidence Artifact,
source Revision, Camera target, and property.

`VerifyObservedCameraTracksSourceChange` is artifact-bound ChangeAuthority. It
re-reads canonical accepted Camera evidence, rederives every absolute sample,
reconstructs all Track and Keyframe identities, verifies the captured identity
Camera baseline and complete animation result, and attaches provenance only
after all checks succeed. Failure leaves the Document unchanged.

## Exclusions

Camera Track replacement, non-identity initial Camera, easing inference,
automatic anchor discovery, multiple anchors, smoothing, perspective, raster
or video input, and target auto-binding remain outside this slice.
