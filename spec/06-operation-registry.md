# Operation Registry and Signatures v0.1

Status: normative operation-semantics dispatch model.

## 1. Purpose

JSON Schema defines the representation of an Operation record. The Operation
Registry defines what that Operation means under one `semantics_version`.

The Registry is the single source of truth for:

- supported Operation type names;
- required input names and Value types;
- static or dynamically derived output names and Value types;
- parameter validation;
- quality sensitivity;
- reference evaluation implementation.

The Evaluator must not duplicate type dispatch in an `if/elif` chain.

## 2. Definition model

Each registered definition provides:

```text
OperationDefinition
|- type_name
|- input signature
|- output signature or output resolver
|- parameter validator
|- quality_sensitive
`- executor
```

An input signature maps logical input names to Value types. An output signature
maps logical output names to Value types. The v0.1 registry currently defines
the `geometry` Value type.

## 3. Static and dynamic outputs

Most operations have a static output signature:

```text
CreateEllipse
inputs:  {}
outputs: {geometry: geometry}
```

`SplitEntity` demonstrates a dynamic but still explicit signature. Its output
names are deterministically derived from validated `parameters.parts`:

```text
SplitEntity
inputs:  {geometry: geometry}
outputs: {
  face_geometry: geometry,
  hair_geometry: geometry
}
```

Dynamic does not mean unknown. Once an Operation record is validated, every
legal output slot is enumerable before evaluation.

Each v0.1 Split part also declares a `bounds_fraction` selector with normalized
`x`, `y`, `width`, and `height`. The selector must lie inside source bounds.
Evaluation converts it to explicit Clip geometry, so a downstream Renderer does
not need to interpret structural selection metadata.

## 4. Semantic validation

For every Operation, semantic validation verifies:

1. its type is registered for the active semantics version;
2. input names exactly match the input signature;
3. parameters satisfy the definition;
4. dynamic output names are valid and unique;
5. every referenced upstream output exists;
6. upstream output and downstream input Value types match;
7. every Entity output binding names an existing declared output.

Consequently, a reference such as `op:foo.nonexistent` is invalid even when
`op:foo` itself exists.

## 5. Evaluation

After validation, the Evaluator resolves dependencies and delegates execution
through the Registry. A definition's executor must return exactly the output
names declared by its resolved signature. Missing or additional results are an
evaluation error.

Quality sensitivity is declared by the definition. Requested quality enters the
evaluation key only for operations whose semantics depend on quality. A changed
quality-sensitive Value naturally invalidates downstream evaluation keys through
their input Value IDs.

## 6. Mutation

Parameter mutation must validate the complete resulting Operation before it is
accepted or invalidation begins. Invalid mutation is reverted atomically.
Multi-record Document changes remain the responsibility of Transactions.

## 7. Backend boundary

The Registry owns SVM operation meaning. A future capability Backend may replace
the reference executor implementation, but it must satisfy the same registered
input/output contract and active semantics version. A Backend may not register
private product meaning implicitly.

Semantics extensions must be explicitly versioned and must remain distinguishable
from third-party package identity.

## 8. Registered v0.1 operations

| Operation | Inputs | Outputs | Quality-sensitive |
| --- | --- | --- | --- |
| `BooleanGeometry` | `left`, `right` | `geometry` | no |
| `CreateEllipse` | none | `geometry` | no |
| `CreatePath` | none | `geometry` | no |
| `CreateRectangle` | none | `geometry` | no |
| `PathToPolygon` | `path` | `geometry` | no |
| `Transform` | `geometry` | `geometry` | no |
| `ConvertToPath` | `geometry` | `geometry` | no |
| `RefineBezier` | `geometry` | `geometry` | yes |
| `Clip` | `content`, `clip` | `geometry` | no |
| `SplitEntity` | `geometry` | derived from parts | no |

`CreateEllipse` requires finite `cx`, `cy`, `rx`, and `ry`; both radii must be
greater than zero. `CreateRectangle` requires finite `x`, `y`, `width`, and
`height`; both dimensions must be greater than zero. Degenerate primitives are
rejected at semantic validation rather than materialized as invisible geometry.

`BooleanGeometry.operator` is one of `union`, `intersection`, `difference`, or
`xor`. It declares the `geometry` capability; its accepted meaning belongs to
the Registry while execution is delegated through `GeometryBackend`.

`PathToPolygon` is registered under `12-path-to-planar-geometry.md`. Its finite,
positive `tolerance` and `nonzero | evenodd` fill rule are exact Document
parameters. Its algorithm identity is `svm-path-planar:0.1` and participates in
the evaluation context.
