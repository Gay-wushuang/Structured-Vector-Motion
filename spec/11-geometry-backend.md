# Deterministic Geometry Backend v0.1

Status: second deterministic external capability and first Backend integration.

## 1. Purpose and boundary

This milestone proves execution of an accepted capability-bearing Operation:

```text
Accepted BooleanGeometry Operation
        |
Evaluator selects GeometryBackend
        |
Shapely + GEOS set operation
        |
canonical polygon_set Immutable Value
        |
Evaluated Scene -> SVG Renderer
```

Unlike an Adapter, a Geometry Backend does not analyze a Reference, produce a
Proposal, edit the Document, allocate Entity IDs, or create a Revision. It only
executes semantics already declared by the active Operation Registry.

## 2. Capability interface

The public interface is capability-oriented:

```text
GeometryBackend
|- identity
`- boolean(operator, left, right) -> geometry
```

Shapely is one implementation. Its package name is not part of the Operation
type. Backend identity records both the Shapely package version and the runtime
GEOS engine version using `geometry/shapely@<version>+geos@<version>`. This full
identity participates in the Runtime evaluation key for capability-backed
Operations, while the Immutable Value ID remains the hash of canonical output
content. A GEOS version change therefore invalidates evaluation-context reuse
even when canonical output content remains identical.

If a Backend is unavailable, the Document remains structurally valid but the
operation enters `FAILED`. A missing optional package must not prevent Core from
being imported or non-geometry Documents from being evaluated.

Shapely and GEOS exceptions are translated to `GeometryBackendError` at the
capability boundary. Runtime does not depend on implementation-specific
exception classes.

## 3. BooleanGeometry

The registered Operation signature is:

```text
BooleanGeometry
inputs:
  left: geometry
  right: geometry
parameters:
  operator: union | intersection | difference | xor
output:
  geometry: geometry
capability:
  geometry
```

The operation does not allocate or merge Entities. The author chooses which
Entity output slot binds the resulting geometry.

## 4. Supported geometry subset

The Shapely implementation accepts:

- positive-dimension `rectangle` Values;
- canonical `polygon_set` Values produced by this capability.

Ellipse, Bézier/path-data, transform wrappers, clips, lines, points, and mixed
geometry collections are rejected. Curve flattening and tolerance policy must be
specified before those inputs can be supported honestly.

An empty result is rejected in v0.1 because the current geometry Value contract
has no explicit empty-geometry representation.

## 5. Canonical output

The Backend applies Shapely strict normalization before conversion. The output
is a JSON-compatible `polygon_set`:

```text
polygon_set
|- polygons[]
|  |- exterior: closed coordinate ring
|  `- holes[]: closed coordinate rings
`- bounds: [min_x, min_y, max_x, max_y]
```

Coordinates are finite floats. Rings include the repeated closing coordinate.
The SVG Renderer emits one `path` with `fill-rule="evenodd"` so holes and
multiple polygons retain filled-area semantics.

## 6. Dependency and CLI

Shapely is declared in the optional `geometry` extra:

```powershell
python -m pip install -e ".[geometry]"
```

Execution is explicit:

```powershell
svm render-svg examples/007-boolean-geometry.svm.json `
  --geometry-backend shapely `
  --output boolean.svg `
  --view-box 0 0 180 140
```

The compatibility range is `>=2.1.2,<2.2`. The implementation uses Shapely's
set-theoretic operations and strict normalization; Shapely is BSD-3-Clause and
GEOS is LGPL-2.1.

## 7. Golden artifacts

- `examples/007-boolean-geometry.svm.json` — accepted Boolean operation;
- `examples/rendered/007-boolean-geometry.svg` — canonical rendered result;
- `tests/test_geometry_backend.py` — determinism, missing capability, rejection,
  and CLI/render golden coverage.
