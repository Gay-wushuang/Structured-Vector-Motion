# Motion Semantics v0.1 and v0.2

## Status

Golden Test M is normative. It is the first SVM milestone whose primary result
is motion rather than construction or external evidence integration.

## 1. Timebase

Every Document with content Tracks records an explicit Motion semantics
identity. Validation fails closed for a missing or unknown identity. This
versions temporal meaning independently from Construction semantics without
adding time to static evaluation keys.

Content animation uses non-negative integer ticks and an explicit positive
`ticks_per_second`. Recorded semantics never depend on wall-clock time, display
refresh rate, locale, floating-point seconds, or export FPS. Seconds are a
derived rational value `tick / ticks_per_second`.

## 2. Track

A Track is a stable `track:*` identity and one typed mapping from time to one
animatable target. v0.1 permits at most one Track for an Operation parameter.
Track array order has no evaluation meaning.

## 3. Keyframe

A Keyframe has a stable `keyframe:*` identity, integer tick, and finite numeric
value. IDs and ticks are unique within a Track; records are strictly increasing
by tick. Editing a value does not rename the Keyframe or Track.

## 4. Animatable parameter

Motion v0.1 accepts any existing finite numeric Operation parameter. This legacy
rule is retained so a recorded `svm-motion@0.1` Document never changes validity
when a newer Runtime is installed.

Motion v0.2 additionally requires the target to be explicitly listed in the
Operation Definition's `animatable_parameters`. Numeric representation alone
never grants linear animation semantics. Both Track creation and v0.2 Document
validation consult this same Registry contract. New Editor authoring produces
v0.2.

Both identities sample an effective parameter value; neither mutates Entity,
Operation, Track, or Keyframe identity. Style, path control, constraints,
hierarchy, and arbitrary Entity properties are deferred.

## 5. Interpolation

v0.1 supports `linear` only. Before the first and after the last Keyframe the
endpoint value is held. Interpolation is computed from exact decimal-to-rational
values and integer tick ratios. Every exit—including exact and held
Keyframes—is canonicalized to an integer when mathematically integral or a
finite float otherwise. Thus `100` and `100.0` sample to identical content.

## 6. Evaluation at time

Sampling produces an ephemeral effective Document, evaluates its accepted
Construction Graph, and materializes an Evaluated Scene. A Frame is a sampled
result, never stored animation meaning.

Time is absent from an Operation evaluation key. Only the sampled parameter and
ordinary dependency Value IDs participate. Therefore a static subtree has the
same evaluation key and immutable Values at every tick and is reusable from the
shared content-addressed runtime cache.

Changing one Keyframe value invalidates cached Frames whose sampled value can
change. For an interior Keyframe this is the integer-tick interval strictly
inside its two unchanged neighboring Keyframes; those neighbor ticks themselves
remain valid. Endpoint edits include their held range. Within affected Frames,
ordinary Construction dependency invalidation is still determined by changed
sampled parameters.

`MotionEvaluator.set_keyframe_value()` exists only as a v0.1 runtime invalidation
harness. It is not persistent Document mutation authority and MUST NOT be used
by an Editor to save changes. Persistent Keyframe edits use
`SetKeyframeValueChange`, an atomic Transaction, and a new Revision. A
canonically equivalent no-op edit creates no Revision and invalidates no Frames.

Construction scheduling remains a separate time system and is not interpreted
by Motion v0.1.

## Golden M

Golden M remains the legacy v0.1 fixture and animates
`op:moving-rectangle.x` at 1000 ticks/second:

```text
tick 0    (0.0 s) -> 100
tick 250  (0.25 s) -> 200
tick 500  (0.5 s) -> 300
tick 750  (0.75 s) -> 400
tick 1000 (1.0 s) -> 500
```

It proves deterministic evaluation and SVG frames, stable Entity/Operation/
Track/Keyframe IDs, middle-Keyframe temporal invalidation, and cross-time cache
reuse for an independent static rectangle. A separate `0 -> 1` over three ticks
case proves non-integral rational interpolation, while `100` versus `100.0`
proves endpoint numeric canonicalization.

Golden N extends this model across immutable Revision snapshots; see
`22-motion-revisions.md`.
