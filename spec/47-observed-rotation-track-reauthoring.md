# Observed Rotation Track Re-authoring v0.1

## Status

Golden S6C defines an explicit, accepted-evidence-only replacement path for one
trusted observed rotation Track. It does not change Golden S6B CREATE semantics.

## Inputs and authority

A replacement Proposal MUST name exactly one accepted
`svm-observed-similarity-motion-0.1` Artifact, one explicit Group Motion Target
Binding, and a positive Document timebase. The evidence temporal identity MUST
match the Binding and every consumed interval MUST have
`rotation_degrees.status == SUPPORTED`.

The target Group MUST contain exactly one `rotation_degrees` Track owned by the
observed-rotation authoring policy. Replacement authority is limited to that
captured Track. Translation, scale, style, static Group transforms, construction,
presentation, entities, and Group membership are outside this authority.

The S6B CREATE adapter MUST continue to reject any existing Group rotation Track.
Detecting a Track MUST NOT implicitly select replacement behavior.

## Numeric semantics

The replacement baseline is the captured current static Group
`rotation_degrees` value. Supported signed deltas are accumulated into absolute,
unwrapped keyframe values. Therefore a baseline of `170` followed by `+20`
produces `190`, not `-170`. Runtime state and the old Track's final keyframe are
not baseline sources.

## Identity and provenance

The replacement Track ID and Keyframe IDs are deterministic functions of the new
accepted evidence, Binding, Group, property, and timebase. A different evidence
Artifact therefore produces a different Track identity. The replacement keeps
the exact Group and `rotation_degrees` target while recording the new evidence,
Binding, and source Revision in `ObservedRotationTrack` provenance.

The replacement Change also captures the complete existing Track and animation
state. That captured authored state is part of the verified Revision transition;
old provenance is not copied onto the replacement result.

## Staleness and atomicity

Acceptance MUST verify, before the resulting Revision becomes visible:

- the accepted evidence reference and its content-addressed Artifact;
- the exact Binding and Group snapshot;
- the complete animation-before snapshot;
- ownership, target, and provenance of the existing Track;
- the rederived replacement Track and expected animation.

Any mismatch fails the transaction atomically. No old Track is removed and no
partial replacement is committed.
