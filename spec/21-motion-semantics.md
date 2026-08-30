# Motion Semantics v0.1

## Status

Golden Test M is normative. It is the first SVM milestone whose primary result
is motion rather than construction or external evidence integration.

## 1. Timebase

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

The v0.1 target is an existing finite numeric parameter of an accepted
Construction Operation. Animation samples an effective parameter value; it does
not mutate Entity, Operation, Track, or Keyframe identity. Style, path control,
constraints, hierarchy, and arbitrary Entity properties are deferred.

## 5. Interpolation

v0.1 supports `linear` only. Before the first and after the last Keyframe the
endpoint value is held. Interpolation is computed from exact decimal-to-rational
values and integer tick ratios, then canonicalized to an integer when exact or a
finite float otherwise.

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

Construction scheduling remains a separate time system and is not interpreted
by Motion v0.1.

## Golden M

Golden M animates `op:moving-rectangle.x` at 1000 ticks/second:

```text
tick 0    (0.0 s) -> 100
tick 500  (0.5 s) -> 300
tick 1000 (1.0 s) -> 500
```

It proves deterministic evaluation and SVG frames, stable Entity/Operation/
Track/Keyframe IDs, middle-Keyframe temporal invalidation, and cross-time cache
reuse for an independent static rectangle.
