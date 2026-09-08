# Group Transform Motion Slice v0.1

## Status

This Authoring Motion Slice is normative. It is not Golden Q v4. Golden Q ends
with static Group Transform; this slice connects that accepted definition to
content animation and then stops Core expansion before the first authored Demo.

## Recorded semantics

`svm-motion@0.3` extends Motion v0.2 with a second explicit Track target shape:

```json
{"group": "group:...", "property": "translate.x"}
```

The only supported Group properties are:

```text
translate.x
translate.y
rotation_degrees
scale
```

Every value is a finite scalar sampled with the existing integer Timebase and
linear interpolation contract. `scale` must remain positive at every recorded
Keyframe. Linear interpolation between positive endpoints therefore remains
positive. `origin` is static and cannot be a Track target in this slice.

Operation-parameter Tracks remain valid under v0.3 and retain the explicit
animatability rules of Motion v0.2. Recorded v0.1 and v0.2 Documents retain
their original meaning and cannot contain Group targets.

## Evaluation

Sampling creates an ephemeral Document snapshot, writes sampled values only
into its copied `Group.transform`, then uses the Golden Q v3 evaluation rule:

```text
sample(t)
-> effective Group.transform at t
-> GroupTransform x EntityLocalGeometry
-> Evaluated Scene
-> Frame
```

The accepted Document, Group identity, member records, local geometry,
construction Operations, Styles, Render Stack, and geometry Value IDs do not
change. Static construction Values remain reusable across Group-motion Frames.

## Authoring

`CreateGroupTransformTrackChange` creates one numeric linear Track for an
existing transformed Group and one supported property. Initial creation still
requires an `AddKeyframeChange` in the same atomic Transaction. Further
Keyframes and value edits reuse the existing Motion authoring Changes.

Its closed-world intent is:

```text
action    = create_group_transform_track
target    = Group ID
parameter = Group Transform property
```

The minimal executable Document is
`examples/023-group-transform-motion.svm.json`.

Camera motion, member-local Track synthesis, animated origin, path deformation,
frame difference, optical flow, and recovery semantics are outside this slice.
