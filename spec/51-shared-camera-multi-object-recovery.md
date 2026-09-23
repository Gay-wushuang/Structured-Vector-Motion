# Shared-Camera Multi-Object Synthetic Recovery v0 (Golden S10A)

## Scope

S10A is an integration and isolation proof for one explicit static anchor, one
moving Camera, and two independently moving Groups. It adds no motion property,
batch adapter, replacement mode, association algorithm, or raster/video input.

The Ground Truth Document is used only to render four frozen SVG observations
at ticks `0`, `12`, `24`, and `36`, and to assert the recovered result. The
Recovery Document contains the same static construction, two explicit Groups,
and an identity Camera, but starts with no animation Tracks. Recovery consumes
only the frozen SVGs through the existing geometry, correspondence, identity,
translation, and similarity evidence pipelines.

## Shared Camera evidence

The explicit static anchor produces exactly one accepted
`svm-observed-camera-similarity-0.1` Artifact. Both targets independently pass
that same Artifact, their own accepted translation evidence, their own accepted
similarity evidence, and their own Temporal Identity to
`CameraCompensatedMotionAdapter`.

The resulting compensated Artifact pairs must differ. Each pair records its
target Temporal Identity and the exact shared Camera and target source Artifact
IDs. Reusing Camera evidence grants no authority to author object Tracks;
compensation and an explicit Motion Target Binding remain mandatory.

## Independent authoring

Temporal Identity A binds only to Group A and Temporal Identity B binds only to
Group B. The existing translation, scale, and rotation Track adapters run once
per binding. `ObservedCameraTracksAdapter` runs once for the shared Camera
evidence. The final Recovery Document therefore contains exactly twelve Tracks:

```text
Group A: translate.x, translate.y, rotation_degrees, scale
Group B: translate.x, translate.y, rotation_degrees, scale
Camera:  position.x, position.y, rotation_degrees, scale
```

Deterministic object Track identity includes the binding, evidence Artifact,
Group, property, and timebase. Equal properties and keyframe ticks across A and
B therefore cannot collide. Authoring B must leave A's four Track definitions
byte-for-byte unchanged.

## Acceptance and isolation

The accepted result must numerically reproduce both Group transforms and the
Camera transform at every frozen tick. Rendering that one recovered Document
and re-observing Anchor, Target A, and Target B must reproduce all frozen polygon
landmarks within the existing synthetic tolerance.

Cross-wired translation/similarity sources, evidence paired with the other
target's identity or binding, forged compensated identity, duplicate identity
binding, and a forged colliding Track ID fail closed. Failed acceptance is
atomic. Track provenance for A names only A's compensated evidence and Binding;
B is equivalent, while Camera Track provenance names only the single Camera
evidence Artifact.

Multi-anchor consensus, automatic association, occlusion, uncertainty recovery,
Camera replacement, raster input, and real video remain out of scope.
