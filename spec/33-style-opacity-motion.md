# Style / Opacity Motion v0

Status: normative Presentation Motion Slice.

## 1. Scope

`svm-motion@0.5` adds explicit Entity Style Track targets for `opacity` and
`fill`. The target Entity must already have a `presentation.styles` record.
Sampling changes only the ephemeral sampled Document used to build an Evaluated
Scene; it does not rewrite accepted state, Entity identity, construction, or
geometry Values.

## 2. Opacity

Opacity is a numeric Track. Keyframe values must be finite and within `[0, 1]`.
It supports the existing `linear` and deterministic `ease-in-out` interpolation.

## 3. Fill

Fill is a discrete color Track with `value_type = color` and
`interpolation = hold`. Values use the existing Style color subset: `none`,
six-digit hex, or eight-digit hex. Sampling selects the latest Keyframe at or
before the tick, with endpoint clamping. RGB interpolation is outside this slice.

Editing a held Keyframe invalidates its own hold interval through the tick before
the next Keyframe. The first Keyframe also influences earlier clamped ticks.

## 4. Authoring authority

`CreateStyleTrackChange` creates an empty Track only inside an atomic Transaction
that also creates its required initial Keyframe. Its policy intent is:

```text
action    = create_style_track
target    = Entity ID
parameter = opacity | fill
```

Camera, Mask, palette objects, continuous color interpolation, and semantic
style inference are outside this slice.
