# Motion Authoring v0.1

## Status

Editor Vertical Slice 03 is normative for the first persistent creation of
Motion semantics from an existing static Document.

## Changes

`CreateTrackChange(track_id, operation_id, parameter, ticks_per_second)` creates
one numeric, linear Track with stable identity. It may also establish
`svm-motion@0.1` and the Document timebase when the Document has no Tracks.
Existing timebase and target uniqueness are fail-closed.
The target must occur in the active Operation Definition's explicit
`animatable_parameters`; being a finite numeric parameter is necessary but not
sufficient.

`AddKeyframeChange(track_id, keyframe_id, tick, value)` inserts one finite
numeric Keyframe in tick order. Keyframe IDs and ticks must be unique within the
Track.

Motion v0.1 requires every accepted Track to contain at least one Keyframe.
Therefore initial authoring is one atomic Transaction:

```text
CreateTrackChange
+ AddKeyframeChange @ tick 0
-> validate once
-> Revision R1
```

An empty Track can exist only inside an unfinished Transaction candidate; it
can never become an accepted Document or Revision.

The closed-world Change Authority impacts are:

| Change | Action | Target | Parameter |
| --- | --- | --- | --- |
| `CreateTrackChange` | `create_track` | Operation ID | parameter name |
| `AddKeyframeChange` | `add_keyframe` | Track ID | new Keyframe ID |

Untrusted Editor input crosses `ProposalAcceptor`. Structural Motion authoring
creates a fresh `MotionEvaluator`; selective cache transition remains reserved
for stable-structure Keyframe value edits.

## Vertical Slice 03

The first UI path is intentionally narrow:

```text
select an untracked parameter declared animatable by the Operation Registry
-> Add Track + initial Keyframe at tick 0
-> Add a second Keyframe at an explicit tick
-> preview and edit its value
-> play deterministic linear Motion
```

The browser never invents a private JS Track. Every displayed Track and
Keyframe comes back from the accepted SVM Document projection.
