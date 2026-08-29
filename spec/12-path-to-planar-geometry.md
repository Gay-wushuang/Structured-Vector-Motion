# Path to Planar Geometry Semantics v0.1

Status: implemented normative semantics with Golden D coverage.

## 1. Purpose

`path_data` is authored curve geometry. `polygon_set` is planar filled-area
geometry. They are not interchangeable and a Geometry Backend must not silently
convert one while executing another Operation.

The explicit construction chain is:

```text
CreatePath
    |
path_data
    |
PathToPolygon(tolerance, fill_rule)
    |
canonical polygon_set
    |
BooleanGeometry
```

`PathToPolygon` is a pure structural Operation. It does not allocate Entities,
change render order, mutate its input, read viewport state, or create a Revision.

## 2. Registry signature

```text
PathToPolygon
inputs:
  path: geometry            # runtime kind must be path_data
parameters:
  tolerance: number         # finite and greater than zero
  fill_rule: nonzero | evenodd
outputs:
  geometry: geometry        # runtime kind is polygon_set
quality_sensitive: false
```

Both parameters are recorded in the Document. No Adapter, Backend, Renderer, or
process-wide preference may supply an unrecorded default.

The Operation rejects geometry wrappers and non-path inputs in v0.1. An author
must place transformations or other structural operations deliberately in the
Construction Graph.

## 3. Coordinate space and tolerance

`tolerance` is measured in the coordinate system of the input `path_data`. It is
independent of pixels, DPI, viewport, zoom, export resolution, and evaluation
Quality. Consequently `PathToPolygon` is not Quality-sensitive.

For a quadratic or cubic Bézier segment, v0.1 uses recursive de Casteljau
subdivision at `t = 0.5`. A segment is accepted as flat when the maximum
perpendicular Euclidean distance from each interior control point to the chord
is less than or equal to `tolerance`. If the chord has zero length, distance is
measured to the common chord endpoint. Accepted segments emit only their final
endpoint; traversal is left half before right half.

Subdivision depth is limited to 32. Failure to meet the criterion within that
depth is an evaluation error, never permission to emit a coarser result.

This definition makes tolerance an algorithmic flatness threshold rather than a
screen-space visual hint. Changing tolerance must change the evaluation key.
The output Value ID changes only when canonical output content changes.

## 4. Supported path syntax

The v0.1 semantic subset accepts SVG path commands:

- `M/m`, `L/l`, `H/h`, `V/v`;
- `C/c`, `S/s` cubic Béziers;
- `Q/q`, `T/t` quadratic Béziers;
- `Z/z` closure.

Relative coordinates and smooth commands are first expanded into absolute
segments with explicit control points. Elliptical arcs (`A/a`) are rejected in
v0.1 because arc-to-Bézier conversion requires a separate normative contract.
Malformed data or non-finite coordinates are evaluation errors.

## 5. Closed filled paths

Every non-empty subpath must end with an explicit `Z/z`. Although SVG painting
normally treats open subpaths as implicitly closed for filling, SVM v0.1 rejects
them. This stricter rule prevents a missing closure from being silently repaired
during a structural conversion.

Closure adds the final straight segment to the subpath start when the current
point differs. A close command following an already coincident endpoint does not
add a duplicate edge.

## 6. Multiple subpaths and fill rules

All flattened subpaths participate in one planar arrangement. They are not
independently converted and then guessed to be exterior rings or holes.

- `nonzero`: a bounded face is inside when its signed winding number across all
  directed subpaths is non-zero.
- `evenodd`: a bounded face is inside when the number of crossings across all
  subpaths is odd.

Nested subpaths therefore become either filled islands or holes according to
their combined direction and the recorded fill rule. Input subpath order must
not affect the selected planar area.

## 7. Self-intersection and topology

Self-intersecting closed subpaths are supported. The flattened segments are
noded at every proper crossing and overlap endpoint before bounded faces are
classified by `fill_rule`. The implementation must not pass an invalid
self-intersecting ring directly to a polygon constructor and rely on implicit
repair such as `buffer(0)` or `make_valid`.

Coincident edges contribute separately to winding/parity classification.
Topology repair heuristics are outside v0.1 semantics.

## 8. Degenerate input

The following rules apply before planar face classification:

- zero-length segments and consecutive duplicate vertices are removed;
- each subpath must retain at least three distinct vertices;
- each subpath must contain at least one non-collinear vertex triple;
- non-finite coordinates are rejected;
- a final result with no positive-area bounded face is rejected.

A degenerate subpath causes the whole Operation to fail. It is not silently
dropped, because doing so could change nonzero/evenodd results for other
coincident subpaths.

## 9. Canonical polygon_set

The result uses the shared SVM canonical `polygon_set` representation:

```text
polygon_set
|- polygons[]
|  |- exterior: closed coordinate ring
|  `- holes[]: closed coordinate rings
`- bounds: [min_x, min_y, max_x, max_y]
```

Canonicalization is content semantics, not renderer behavior:

1. normalize negative zero to positive zero;
2. remove consecutive duplicates and redundant collinear interior vertices;
3. close every ring with exactly one repeated first coordinate;
4. orient exterior rings clockwise and holes counter-clockwise;
5. rotate each ring to its lexicographically smallest coordinate, breaking a
   repeated-minimum tie with the lexicographically smallest remaining sequence;
6. sort holes by their canonical coordinate sequence;
7. sort polygons by exterior sequence followed by hole sequences;
8. derive bounds from the canonical coordinates.

No engine name, tolerance, fill rule, or provenance is embedded in geometry
content. Those belong to the Operation and Runtime evaluation context.

Shapely Boolean output and Path conversion both use the same canonicalizer; no
second Backend-specific polygon dialect is accepted.

## 10. Semantics and execution identity

The parsing, command expansion, subdivision rule, degeneracy rules, fill
classification, and canonicalization above belong to `svm-core-0.1` semantics.
An implementation may optimize execution but must produce equivalent canonical
content.

The concrete implementation/engine ID and algorithm version are recorded in the
Runtime execution context and participate in the evaluation key. They do not
replace the Document parameters and do not permit different observable meaning.

The initial algorithm identity is reserved as:

```text
svm-path-planar:0.1
```

## 11. Golden D contract

Golden D covers the complete deterministic chain:

```text
two closed cubic SVG paths
-> SVGImportAdapter
-> CreatePath
-> PathToPolygon(tolerance=0.5, fill_rule=nonzero)
-> canonical polygon_set
-> BooleanGeometry(union)
-> Shapely GeometryBackend
-> canonical polygon_set
-> SVGRenderer
```

The checked-in contract fixtures define the accepted Document, source Artifact,
intermediate deterministic assertions, and final byte-for-byte SVG result.

Implemented assertions are:

- equivalent Documents and execution context produce identical canonical
  intermediate and final polygon sets;
- changing either `PathToPolygon.tolerance` changes that node's evaluation key
  and transitively reevaluates the Boolean result;
- a Value ID changes only if canonical output content changes;
- open paths, arcs, invalid fill rules, non-positive tolerances, degenerate
  subpaths, and empty results fail explicitly.
