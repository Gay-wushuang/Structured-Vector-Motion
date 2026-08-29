# Bitmap Trace Adapter v0.1

## Status

This specification defines the deterministic `BitmapTraceAdapter` boundary and
Golden Test E. It does not make bitmap bytes or Potrace objects part of SVM Core.

## Pipeline

```text
content-addressed PNG ReferenceArtifact
-> BitmapTraceAdapter
-> Proposal(CreatePath + PathToPolygon)
-> explicit acceptance
-> Revision
-> GeometryBackend
-> canonical polygon_set
```

The Adapter MUST NOT mutate a Revision. Its Proposal MUST bind the resulting
Entity to `PathToPolygon.geometry`; flattening MUST NOT be hidden in the tracer
or BooleanGeometry.

## Recorded semantics

The following parameters affect the Proposal and MUST be recorded in generator
provenance: `threshold`, `invert`, `turd_size`, `turn_policy`, `alpha_max`,
`optimize_curve`, `optimization_tolerance`, `path_tolerance`, and `fill_rule`.
`path_tolerance` and `fill_rule` MUST also be explicit `PathToPolygon` Document
parameters. Coordinates are bitmap pixel coordinates and do not depend on DPI,
viewport, or zoom.

The v0.1 media subset is PNG only. Inputs above 32 MiB, decoded images above 16
megapixels, invalid images, empty traces, and unknown options fail closed.

## Capability and license boundary

`BitmapTracer` is a replaceable Adapter-side capability. The reference
`PotracerEngine` is installed only by the `trace` optional dependency and uses
the third-party `potracer` distribution, which is GPL-2.0-or-later. SVM does not
copy that implementation and Core does not import it. Distributors enabling the
extra are responsible for reviewing the third-party license obligations.

The engine name and version MUST be recorded in `GeneratorProvenance`. Accepted
Documents contain ordinary SVM Operations and remain evaluable without the
tracing engine.

## Golden Test E

Golden E proves:

1. a PNG Artifact produces an isolated Proposal;
2. acceptance atomically adds the Artifact reference, Entity, `CreatePath`, and
   explicit `PathToPolygon`;
3. Shapely evaluation produces canonical `polygon_set` content;
4. SVG rendering is stable;
5. equal bytes and recorded options produce equal path data;
6. changing `path_tolerance` changes the `PathToPolygon` evaluation key even
   when the traced path is unchanged.
