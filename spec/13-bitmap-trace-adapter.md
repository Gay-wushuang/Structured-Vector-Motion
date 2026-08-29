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

The v0.1 media subset is PNG only. Both the Artifact media type and decoded
format signature MUST identify PNG. The Adapter opens the image header, verifies
the format and dimensions, and enforces the 16-megapixel limit before decoding
pixel storage. Inputs above 32 MiB, invalid images, empty traces, and unknown
options fail closed.

PNG alpha/transparency is unsupported in v0.1. Images with an alpha band or a
PNG transparency declaration MUST be rejected before decoding. The accepted
preprocessing semantics are opaque PNG decoding followed by Pillow `L` mode
conversion and optional inversion. A future compositing rule requires an
explicit versioned parameter; Pillow defaults are not SVM semantics.

`alpha_max`, `optimization_tolerance`, and `path_tolerance` MUST be finite and
greater than zero. NaN and positive or negative infinity are invalid.

Potrace coordinates are first normalized to finite canonical `.12g` numbers.
The accepted `CreatePath.d` is produced from those coordinates. Its bounds MUST
then be computed from the final canonical path data by the shared
`canonical_path_bounds` implementation. Bounds are the true axis-aligned bounds
of the Bézier geometry, including derivative extrema in the open interval, not
the bounds of its control hull. Final bounds numbers are normalized to `.12g`.

## Capability and license boundary

`BitmapTracer` is a replaceable Adapter-side capability. The reference
`PotracerEngine` is installed only by the `trace` optional dependency and uses
the third-party `potracer` distribution, which is GPL-2.0-or-later. SVM does not
copy that implementation and Core does not import it. Distributors enabling the
extra are responsible for reviewing the third-party license obligations.

The engine and preprocessing identity MUST be recorded in
`GeneratorProvenance`. The reference identity includes the potracer package
version, Pillow package version, and `svm-bitmap-preprocess@0.1`. Accepted
Documents contain ordinary SVM Operations and remain evaluable without the
tracing engine.

The reference identity also records the svgpathtools version used for exact
path bounds and `svm-path-bounds@0.1`.

Namespace allocation MUST check every generated Entity and Operation ID before
constructing the Proposal. A collision is resolved deterministically inside the
Adapter rather than deferred to Transaction acceptance.

For an automatically generated namespace, the hash seed MUST include Artifact
content hash, Adapter ID and version, tracer engine name and version, and the
canonical trace options. Equivalent input identity, generator identity, and
parameters therefore produce equivalent generated IDs; a generator identity
change produces a different namespace.

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
