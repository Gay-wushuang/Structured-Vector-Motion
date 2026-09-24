# Controlled Raster Geometry and Recovery v0 (S11A)

Status: normative controlled-input contract; acceptance closure is S11A.1.

## Boundary and reuse

PNG Reference Artifacts are analyzed by the existing OpenCVAnalysisAdapter v0.2.
Its Proposal is accepted before RasterGeometryObservationAdapter consumes the
analysis, mask and source references. The raster frontend ends at observation
evidence: it creates no Entity, Group, Temporal Identity, binding or Track.
Both stages use Proposal/ChangeAuthority acceptance and atomic transactions.

The frontend reuses `analyze_png`, component ordering/pixel-set digests and the
existing deterministic mask encoder. Acceptance reconstructs the existing
OpenCV producer's bytes and descriptors, including engine versions. There is no
second threshold/component algorithm, Document import, SVG round trip, or
parallel recovery pipeline. Contour extraction uses the existing optional OpenCV
capability and shared `canonicalize_polygon_set`; no dependency is added.

## Controlled input and selection

The input contract is the existing opaque grayscale PNG subset: PNG IHDR color
type 0, bit depth 8, no transparency, at most 32 MiB / 16 megapixels. The frontend
additionally requires exactly two sample values, one uniform background value
and one uniform foreground value under the recorded analysis threshold/polarity.
Gradients and antialiasing are not accepted by this subset.

The caller supplies exactly two occurrence records containing
`analysis_artifact_id`, `component_id` and nonnegative integer `tick`; ticks must
increase. The request lists the distinct analysis IDs exactly once. Component IDs
are exact analysis-local IDs, e.g. `candidate:component-0001`, not Entity IDs.
Lists, absent IDs and ambiguous selectors fail; there is no largest/nearest
component selection. Empty masks or missing selections fail without a primitive
or placeholder. This is not a sparse recovery policy.

The selected component must have one hole-free, nondegenerate contour, contour
area at least 256 square pixels, and 3–32 simplified vertices. Closed
Douglas–Peucker approximation uses epsilon 1 pixel. Every polygon edge must be
at least 8 pixels; the longest edge must exceed the runner-up by more than 4
pixels. This conservative margin rejects ambiguous landmark origins. Shapes
outside this subset fail rather than assert an arbitrary orientation.

## Coordinates and canonical geometry

Coordinates use image origin at the upper left, x right, y down. Integer `(x,y)`
is the pixel sample location, matching OpenCV centroids and contour coordinates;
no half-pixel shift, DPI conversion or y flip is applied. Analysis bounds remain
half-open `[min_x,min_y,max_x+1,max_y+1]`. Contour points describe boundary pixel
centers, so their maxima differ from the exclusive analysis bounds.

The shared polygon canonicalizer removes closing/consecutive duplicates and
collinear vertices, fixes winding, and normalizes the cyclic sequence. The
unique longest directed edge then defines landmark zero, preserving the winding
and giving a rotation-independent start for this subset. The frontend records
`ordered-landmarks` with `rotation_symmetry: none`; unequal landmark counts or
inconsistent geometry still abstain downstream. This is not arbitrary silhouette
tracking or an assurance that every rasterized polygon retains its topology.

## Observation contract and identities

The schema remains `svm-primitive-observations-0.2`; media type remains
`application/vnd.svm.primitive-observations+json;version=0.2`.
Primitive type is `controlled-raster-polygon@0.1`; producer/policy identity is
`svm-controlled-raster-geometry@0.1`. It retains bounds and grayscale fill as R0
evidence, alongside the ordered geometry.

The PNG Artifact ID hashes bytes only. Occurrence ID is `observation:raster:`
plus SHA-256 of canonical source PNG ID, tick, explicit component ID, raster
policy identity and recorded analysis options. The same PNG at different ticks
therefore has one blob identity and different occurrence IDs; a shared endpoint
in adjacent requests has the same occurrence ID. This follows S10B's content vs
occurrence distinction without changing its SVG producer.

Provenance records each source PNG, mask and analysis ID, component ID/digest,
tick, analysis options/engine provenance and contour policy. Equivalent recorded
inputs produce identical mask, analysis, observations, R0, motion evidence and
authored Track IDs. Identity is not based on a filesystem path.

## Explicit raster measurement policy

`svm-geometry-similarity-observation-policy@0.1` remains frozen, including its
normalized support threshold `1e-6`. It still returns UNCERTAIN for the checked-in
13-degree pixel-quantized rotation (RMS approximately 0.359 pixels).

RasterObservedSimilarityMotionAdapter explicitly selects
`svm-controlled-raster-similarity-policy@0.1`. It uses the same S4 similarity
fit and representation, with BOTH support requirements:

- normalized RMS <= 0.01;
- absolute RMS <= 0.75 pixels.

The existing normalized 0.02 uncertainty ceiling remains; the raster policy
does not turn unsupported geometry or symmetry into supported rotation.
Pixel rounding and one-pixel contour approximation motivate these two limits;
the absolute limit prevents large geometry from hiding large pixel residuals.
The policy is not a general noisy fitting or photographic recovery capability.

S11A.1 requires an exact registered AttachRasterSimilarityEvidenceChange carrying
the complete accepted PNG/mask/analysis closure. Both proposal generation and
acceptance reconstruct raster observations from that closure. Copying raster
type/policy strings onto vector points is insufficient. Omitted/forged sources,
geometry, ticks, policies or descriptors reject atomically. The legacy exact S4
Change and its identity/serialization remain unchanged.

## Recovery and numerical acceptance

The formal sequence is `examples/035-controlled-raster-recovery/tick_000.png`,
`tick_012.png`, `tick_024.png`, `tick_036.png`, static Camera, one explicit target.
Recovery reads PNG bytes, ticks, recovery Document and explicit selectors/binding.
Ground-truth transforms/points are read only for final assertions.

The accepted frontend feeds existing R0, explicit R1 promotion, S0 and raster S4,
explicit Motion Target Binding, GeometryTranslationTracksAdapter, rotation/scale
authoring, and MotionEvaluator. Four Group Tracks target translate.x,
translate.y, rotation_degrees and scale. No Camera recovery is involved.

S0/R0 displacement remains bounds-center observation displacement. It is not
authored Group translation. Geometry-correct translation continues to compose
similarities from the recorded baseline and decompose around the fixed Group
origin using the frozen authoring policy.

Fixture acceptance limits (not a universal accuracy guarantee) are:

| Quantity | Maximum error |
| --- | ---: |
| Group translation, Euclidean | 1 pixel |
| Rotation | 0.5 degrees |
| Uniform scale, absolute ratio | 0.01 |
| Transformed vertex, Euclidean | 1.5 pixels |

These small pixel-scale limits allow rounding/contour error and its propagation
around the fixed pivot; they do not reuse vector tolerances. The checked-in
sequence's measured maxima are 0.166022 pixels, 0.059408 degrees, 0.000469 scale,
and 0.204809 pixels respectively. Combined-pair maxima are 0.305979 pixels,
0.027443 degrees, 0.000788 scale, and 0.336113 pixels. Translation-only and the
1.2 scale fixture recover exactly with their integer-aligned raster geometry.

`tests/test_raster_recovery_acceptance.py` is the formal acceptance test, using
production Adapters and Accept at each stage. The direct pixel/S4 test remains
only a low-level quantization regression. Legacy SVG, bitmap/OpenCV and Synthetic
Scene Recovery suites remain required. This contract does not add RGB, video,
multi-object raster association, raster Camera recovery or missing-frame policy.
