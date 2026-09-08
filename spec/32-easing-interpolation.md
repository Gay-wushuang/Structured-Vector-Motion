# Easing Interpolation v0

## Status

This Authoring Quality Slice is normative and intentionally supports one smooth
curve. It does not introduce editable curve handles or a general easing system.

## Recorded semantics

`svm-motion@0.4` permits the existing `linear` interpolation and one new value:

```text
ease-in-out
```

For normalized segment progress `u = (tick-left)/(right-left)`, the eased
progress is the deterministic smoothstep polynomial:

```text
e(u) = 3u^2 - 2u^3
```

The calculation uses exact rational arithmetic before the existing Motion
number canonicalization. Endpoints are held exactly as before. The curve is
monotonic on `[0,1]`, so a Group scale Track with positive Keyframe endpoints
remains positive between them.

Recorded `svm-motion@0.1`, `@0.2`, and `@0.3` Documents continue to permit only
`linear`; they are not reinterpreted by a newer Runtime.

Both Operation parameter Tracks and Group Transform Tracks may record
`ease-in-out` under v0.4. `CreateTrackChange` and
`CreateGroupTransformTrackChange` accept an optional interpolation argument;
the default remains `linear`.

Bezier handles, custom curves, per-Keyframe tangents, spring physics, Style
Tracks, and Camera motion are outside this slice.
