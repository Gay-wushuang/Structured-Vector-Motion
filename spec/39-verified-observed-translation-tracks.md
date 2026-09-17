# Verified Observed Translation Tracks v0.1

Status: normative Golden S2.

## Boundary

S2 is the first explicit evidence-to-animation authoring boundary:

```text
accepted S0 Observed Motion Evidence
+ accepted S1 Motion Target Binding
-> Translation Track Proposal and Preview
-> explicit Accept
-> Group translate.x / translate.y Tracks and Keyframes
```

Evidence never mutates a Document by itself. A Temporal Identity is not an
Animation target, and S2 never guesses a Group. The caller selects one existing
binding and one accepted S0 Artifact. Only linear `translate.x` and
`translate.y` Tracks are in scope.

## Values and time

Observation ticks become integer Motion ticks under the explicitly requested
positive `ticks_per_second`. The first source tick records the bound Group's
current static translation. Each subsequent target value is that baseline plus
the cumulative verified displacement of one ordered, contiguous interval chain.
The resulting values are absolute Group Transform Track values, matching
existing `MotionEvaluator` semantics.

## Acceptance and stale inputs

The Proposal contains ordinary `CreateGroupTransformTrackChange` and
`AddKeyframeChange` records. A registered verification Change binds the exact
accepted evidence reference, S1 binding snapshot, current Group snapshot,
authoritative Proposal base Revision, and complete expected Track definitions.
It verifies the final transaction result before commit. Forged targets,
Keyframes, values, evidence, or provenance fail atomically.

Accepted Tracks carry narrow `ObservedTranslationTrack` provenance binding the
authoring policy, exact S0 Artifact, accepted Motion Target Binding, and source
Revision. Golden S3 uses this metadata solely to prove ownership before an
explicit replacement; target equality alone never grants overwrite authority.

Pending Proposal validation is distinct from persistent S1 semantics. A Group
may legally evolve after its binding was accepted; a new S2 Proposal uses that
current Group as its baseline. If the binding or Group changes after that S2
Proposal is created, the pending Proposal is stale. The accepted binding itself
continues to follow stable IDs and is not invalidated.

Rotation, scale, smoothing, extrapolation, easing, style, camera, deformation,
target inference, automatic acceptance, and video recovery are outside S2.
