# Observed Scale Track Re-authoring v0.1

Status: normative Golden S5B.

## Boundary

S5B explicitly replaces one existing trusted observed-scale Track with a new
Track derived from newly accepted S4 scale evidence and the same explicit
Motion Target Binding.

```text
accepted S4 scale evidence + current Binding + owned scale Track
-> REPLACE Proposal and old/new Preview
-> explicit Accept
-> one atomic scale Track replacement
```

New evidence does not automatically update the Document. Target equality is
not Track ownership. A manual, unknown, malformed, or differently owned Track
targeting the same `Group.scale` fails closed.

## Ownership and identity

The replaceable Track must have target `{group: bound_group, property: scale}`
and exact provenance type `ObservedScaleTrack`, authoring identity
`svm-verified-observed-scale-authoring@0.1`, current Binding ID, a canonical
evidence Artifact ID, and a canonical source Revision ID.

Replacement retains the S5A Track identity rule. The new evidence Artifact is
part of Track identity, so replacement creates a new Track and Keyframe IDs.
The target remains the same while authored artifact identity changes.

## Absolute scale baseline

Re-authoring always starts from the current static
`group.transform.scale`. It never starts from the old animated Track's final or
sampled value. S4 ratios remain multiplicative observations; S5 samples remain
absolute Group scale values.

Only `interval.scale.status == SUPPORTED` is required. Overall and rotation
status may remain `UNCERTAIN`. Every positive finite ratio must belong to one
ordered contiguous interval chain, exactly as in S5A.

## Atomicity, verification, and stale state

`ReplaceObservedScaleTrackChange` captures the complete existing Track,
Binding, Group, animation, source Revision, and expected replacement. Core
validates structural ownership before replacing the Track atomically. The
artifact verifier independently re-derives absolute samples and deterministic
Track identity from the new S4 Artifact and current static Group baseline.

An edited, removed, retargeted, or replaced existing Track; changed Group
baseline; incompatible Binding; changed animation; forged replacement; or stale
source Revision rejects the whole Proposal. Accepted Binding persistence does
not imply pending Proposal persistence: a Binding may remain valid across later
Group evolution, while any already-created replacement Proposal is stale.

S5B does not merge manual and inferred keyframes and does not author rotation,
non-uniform scale, easing, or interpolation beyond the existing linear Track.
