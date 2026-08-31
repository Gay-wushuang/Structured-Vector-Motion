# Motion × Revision v0.1

## Status

Golden Test N is normative. It connects accepted Motion definitions to SVM's
Transaction and Revision model without adding interpolation types.

## Persistent Keyframe edit

`SetKeyframeValueChange(track_id, keyframe_id, value)` is the v0.1 persistent
Motion value-edit primitive. It changes exactly one finite numeric value.
Track, Keyframe, Operation, and Entity identities remain stable. Missing
identities, invalid target values, and canonically equivalent no-ops fail before
a Revision is created.

The Change is registered in the closed-world Change Authority Registry with
policy intent:

```text
action    = set_keyframe_value
target    = Track ID
parameter = Keyframe ID
```

Edit Permission v0.1 continues to match the action and Track target. The exact
Keyframe parameter additionally supports narrower Anchored Regeneration scope.

Editors and Adapters must use Proposal acceptance where the input is untrusted;
`RevisionStore.commit()` remains a trusted lower-level Core mechanism.
Structural Motion creation is specified separately in
`spec/24-motion-authoring.md`.

## Revision transition

Each `MotionEvaluator` owns an isolated Document snapshot. Transitioning to a
new Revision creates a new evaluator; the old evaluator continues to sample the
old Revision. v0.1 transition comparison requires stable animation semantics,
Track structure, Keyframe IDs, and Keyframe ticks. Structural animation edits
and all non-Keyframe Document changes fail closed until they receive explicit
cache-transition semantics. A caller handling a broader Revision must create a
fresh runtime instead of inheriting Frame entries.

For every changed Keyframe value, Core computes the same temporal influence
interval as Motion v0.1 runtime invalidation. The successor runtime:

- shares immutable content-addressed Value cache entries;
- retains cached Frames only at unaffected ticks;
- drops affected Frame entries and lazily reevaluates them;
- preserves static subtree Value IDs across all ticks.

Frames have sampled-content identity, not Revision identity, so an unaffected
cached Frame may be reused by the successor when its Motion semantics are
equivalent at that tick.

## Golden N

The middle Keyframe changes from `300` to `350`:

```text
Revision N                 Revision N+1
0    -> 100                0    -> 100   reusable
250  -> 200                250  -> 225   invalidated
500  -> 300                500  -> 350   invalidated
750  -> 400                750  -> 425   invalidated
1000 -> 500                1000 -> 500   reusable
```

It proves atomic persistence, stable identities, old/new snapshot independence,
selective temporal invalidation, static Value reuse, policy enforcement, and
Undo restoration.
