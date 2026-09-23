# Real Asymmetric SVG Geometry Observations v0.1 (Golden S6A)

Status: normative evidence-only producer boundary.

The original producer policy @0.1 below remains supported unchanged. The explicit
@0.2 occurrence policy is specified in
[Repeated-Frame Observation Occurrences](53-repeated-frame-observation-occurrences.md).

S6A derives `svm-primitive-observations-0.2` from two frozen SVG Reference
Artifacts. It supports exactly one renderable `<path id="...">` per frame and
the closed polygonal grammar `M/m`, `L/l`, `H/h`, `V/v`, `Z/z`. Curves, arcs,
multiple subpaths, arbitrary transforms, implicit semantic matching, sampling,
and vertex reordering are rejected.

Synthetic Motion Recovery accepts the strict renderer-owned shape
`g[data-svm-role=render-stack] > g[data-svm-entity=<selector>]` containing
exactly one polygonal path, optionally inside the renderer's single Group
`matrix(...)`. The renderer-owned render-stack may additionally carry its one
Camera `matrix(...)`. Group and Camera matrices are composed in renderer order;
landmarks and bounds are deterministically converted to observed view space.
This does not enable general SVG transform support: transform lists, nested
author transforms, multiple geometries, and non-matrix syntax remain rejected.

Path command order defines landmark identity. `Z` closes the polygon but does
not add a duplicate first landmark. Source and target must have the same
selector, command topology, vertex count, positive viewBox canvas, finite
coordinates, non-zero area, and six-digit resolved fill. Bounds are computed
with the shared `canonical_path_bounds` policy for plain paths, or directly
from transformed world-space landmarks for the strict renderer-owned subset.

`rotation_symmetry = none` is emitted only after a conservative proof: every
non-zero cyclic shift of centered ordered landmarks is tested for a unit-scale
orientation-preserving rotation using deterministic normalized residual
threshold `1e-9`. Any proven non-trivial symmetry rejects the producer input;
vertex count never implies symmetry.

The typed `AttachSVGGeometryObservationsChange` binds the observation, exact
source and target SVG references, ticks, selector, and policy identity. Core
acceptance resolves both SVG bytes, reruns this exact pure derivation, and
requires byte-identical observation content and provenance. Forged landmarks,
bounds, symmetry, source references, selectors, or ticks therefore fail closed.

S6A is evidence only. Acceptance appends Artifact references and changes no
Entity, Group, Operation, Render Stack, Track, or Keyframe. R0 remains blind to
landmarks; S4 consumes the accepted v0.2 geometry and may report observed
rotation and scale evidence. Rotation Track authoring is outside this slice.
