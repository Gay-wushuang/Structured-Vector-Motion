# Geometry-aware Similarity Motion Evidence v0.1

Status: normative Golden S4.

## Boundary

S4 derives conservative observed rotation and uniform-scale evidence from
frozen observation geometry belonging to an already promoted Temporal Identity.

```text
accepted R0 correspondence + Temporal Identity + frozen observation geometry
-> similarity evidence Proposal and Preview
-> explicit Accept
-> Derived Artifact reference only
```

Similarity evidence is not an Animation Track. Acceptance creates no Track or
Keyframe and changes no Group, Entity, Operation, Presentation, Render Stack,
or animation state. A Motion Target Binding is neither required nor consulted.

Temporal Identity establishes correspondence, not transform magnitude. S4 does
not perform matching and accepts only inference IDs already present in exact R1
promotion provenance.

## Observation geometry v0.2

`svm-primitive-observations-0.1` remains accepted by R0 and the translation
pipeline. Its axis-aligned bounds are insufficient similarity geometry, so S4
emits `UNCERTAIN` with `insufficient_geometry`.

`svm-primitive-observations-0.2` preserves every v0.1 field and adds:

```text
geometry:
  type: ordered-landmarks
  points: [[x0,y0], ...]       # at least three finite points
  rotation_symmetry: none | half-turn | quarter-turn | continuous
```

Landmark indices are visual correspondences asserted by the observation
provider and frozen in the content-addressed Artifact. The producer must record
visual geometry, not merely copy an authored angle. Authored orientation is not
necessarily observable orientation. In particular, a circle must declare
continuous symmetry even if its source program stores a rotation parameter.

AABB change is neither rotation evidence nor uniform-scale evidence. S4 never
derives either component from bounds width, height, area, or aspect ratio.

## Fitting policy

For equal-count, non-degenerate ordered landmarks, policy
`svm-geometry-similarity-observation-policy@0.1` fits the least-squares,
orientation-preserving transform about the source landmark centroid:

```text
target - target_centroid = scale * R(angle) * (source - source_centroid)
```

Positive angles are clockwise in the screen-coordinate convention used by
Group `rotation_degrees`. Angles are degrees and canonicalized to `[-180, 180)`
using shortest-angle semantics. The recorded origin is the source landmark
centroid. Scale is the finite positive source-to-target ratio; reflection,
non-uniform scale, shear, and deformation are unsupported.

The Artifact records both input geometries, the fitted transform, RMS error,
normalized RMS, ambiguity, and per-component status. Thresholds are:

```text
normalized RMS <= 0.000001  -> SUPPORTED fit
normalized RMS <= 0.02      -> UNCERTAIN fit
normalized RMS >  0.02      -> REJECTED as non-uniform deformation
opposite landmark chirality -> REJECTED as reflection
```

A fitted rotation is `SUPPORTED` only when the fit is supported and both
observations declare the same `none` rotation symmetry. Half-turn,
quarter-turn, continuous, mismatched, or degenerate orientation is
`UNCERTAIN`; no arbitrary angle is emitted. A symmetric shape may still carry
supported uniform-scale evidence when its ordered geometry fits consistently.

Missing v0.2 geometry, unequal landmark counts, and degenerate landmarks
abstain as `UNCERTAIN`. High numeric fit quality cannot erase declared visual
orientation ambiguity.

## Identity and verification

Each interval binds the Temporal Identity, exact observation endpoints, R0
candidate and inference IDs, R0 Artifact, source geometry Artifact, R1 promotion
policy, S4 policy, source Revision, and derived measurements. Artifact identity
is canonical content identity.

Proposal acceptance resolves and reconstructs the exact Derived Artifact from
the frozen R0 and observation Artifacts. A stale Temporal Identity or source
Revision, forged geometry, transform, residual, status, threshold, ambiguity,
or provenance fails atomically. Acceptance appends only the S4 evidence
reference.
