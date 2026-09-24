# Explicit Multi-Object Raster Scene Recovery v0 (S11C)

Status: integration acceptance contract. This slice changes no production
schema, policy, Adapter, Change authority, identity rule or transform semantics.
Synthetic Scene Recovery v1, S11A and S11B remain frozen. Governing invariants:
INV-REF-001, INV-TIME-010, INV-PROP-001/002 and INV-TXN-001.

## Reused boundaries

S10A already isolates compensation by Temporal Identity, makes Motion Target
Bindings explicit and exclusive, and includes evidence, binding, Group, property
and timebase in deterministic Track identity. Authoring verifies the expected
animation state and accepts through Proposal/ChangeAuthority transactions.
S11A supplies verified component occurrences and measured S4; S11B supplies
verified measured Camera hypotheses and strict measured consensus. Their
production interfaces contain no single-target assumption. Single-target
constants in S11B's integration fixture are test orchestration only.

The executable proof composes these existing primitives. It adds no batch API,
MultiObjectRasterRecoveryAdapter, raster Track authoring or new matrix model.

## Input and explicit role declarations

Example 037 contains checked-in 1200 x 900, 8-bit opaque grayscale PNGs at
ticks 0, 12, 24 and 36. Four separated black components remain visible without
overlap or antialiasing: two world-static asymmetric anchors and two different
asymmetric moving targets. Each target belongs to a distinct Group with a fixed
off-center origin. Unrendered companion Entities retain the existing Group
fixture convention. Anchors have no Tracks and belong to no animated Group.

Recovery consumes only PNG bytes, ticks, the static registered Recovery Document,
explicit per-tick component selectors, anchor declarations and target bindings.
`selectors.json` maps each role to an analysis-local component ID. Component
numbers change order between frames; neither their order nor area, position or
appearance assigns a semantic role. Component IDs are not Temporal or Entity IDs.

`ground-truth.json` is read only for final assertions after all Tracks have been
accepted. Its points and sampled transforms never enter inference. Tests never
regenerate PNGs. The static geometry already registered in the Recovery Document
is the authoring baseline, as in S11B; observations come exclusively from pixels.
`verification.json` is a recorded output report, never an inference input.

## Independent lineages and one shared Camera

Each of the four explicitly selected roles independently traverses accepted
OpenCV analysis, RasterGeometryObservationAdapter, R0 correspondence, explicit
R1 Temporal Identity, S0 displacement and RasterObservedSimilarityMotionAdapter.
All four Temporal Identities and their observation occurrences must be distinct.
Adjacent pairs reuse the same occurrence at their shared tick under frozen S10B
semantics. Sharing a PNG/analysis/mask across roles is valid; sharing a selected
component occurrence across independent roles is not.

Anchor A/B each produce one verified measured Camera hypothesis. Exactly one
measured consensus C is accepted from both hypotheses. Compensated A references
exactly C, A's S0 and A's S4; Compensated B references exactly C, B's S0 and B's
S4. These target outputs are distinct. Targets do not contribute to Camera
agreement and neither target causes a second consensus to be constructed.

The frozen shared policies remain:

- `svm-controlled-raster-similarity-policy@0.1`
- `svm-static-anchor-camera-similarity@0.2`
- `svm-controlled-raster-camera-agreement@0.1`

There are no target-specific measurement tolerances, fitting, averaging, voting
or outlier removal. S11B's canonical representative and fail-closed agreement
checks remain authoritative.

## Explicit authoring and isolation

Caller binds A's Temporal Identity to Group A and B's to Group B. Each target
uses GeometryTranslationTracksAdapter, ObservedRotationTracksAdapter and
ObservedScaleTracksAdapter on its own compensated similarity. Geometry-correct
translation reconstructs absolute world similarity from the recorded baseline
and decomposes it at the existing fixed Group origin:

```text
group_translation = b - o + A @ o
```

This is the existing authoring contract, not a new S11C transform convention.
R0/S0 bounds-center displacement remains observation evidence. Raster landmark
centroid displacement likewise is not an authored Group translation. The fixture
explicitly checks that legacy displacement differs from recovered translation.

Author A first, then four Camera Tracks once, then author B. B must initially
have no Tracks; authoring B must preserve all A and Camera Tracks byte-for-byte
as serialized definitions. Final Track counts are A=4, B=4, Camera=4, total 12
unique IDs, despite shared properties, ticks and timebase. Preview must leave
accepted Document/Revision state unchanged. Rejection must preserve HEAD,
Document and revision count atomically.

Target provenance closes through its binding and compensated evidence to its
own S0/S4, correspondence, Temporal Identity, selected raster occurrences,
component analysis, mask and PNG. Shared Camera provenance closes through both
anchor hypotheses and both anchor pixel lineages. Sharing Camera evidence must
not import the other target's motion evidence or occurrences.

## Executable acceptance and limits

`tests/test_multi_object_raster_recovery.py` runs complete independent recovery
twice and compares observation/identity/evidence/consensus/binding identities,
authoring Proposals, all Track definitions, final Revision and sampled Documents.
At all four ticks it checks recovered A/B and Camera against Ground Truth:

| Quantity | Target limit | Camera limit |
| --- | ---: | ---: |
| Euclidean translation/position, pixels | 1 | 1 |
| Rotation, degrees | 0.2 | 0.2 |
| Scale, absolute ratio | 0.005 | 0.003 |

Actual MotionEvaluator -> SVGRenderer path vertices and nested transforms are
compared in view coordinates to PNG-derived landmarks for all four roles at
every tick. Symmetric nearest-vertex distance, with equal vertex counts, must
be at most 2 pixels. No SVG string or PNG byte equality is required.

Camera holds from tick 12 to 24. Both anchor geometries remain identical and
Camera relative similarity is exactly identity, while both targets continue
independent translation/rotation/scale. Target motion must not enter Camera.

Required rejection cases cover mixed A-S0/B-S4 compensation, both directions of
crossed evidence/bindings (all three Group authoring adapters), compensated
Temporal Identity forgery, a one-tick A/B selector swap, A Track ID colliding
with existing B, A provenance referencing B's occurrence and B claiming another
PNG. An animated anchor Group and a checked-in disagreeing anchor observation
retain S11B fail-closed behavior.

This proof validates explicit selected lineages, not automatic object identity.
Similar silhouettes selected incorrectly can still be compatible with local
evidence; rejecting the deliberately incompatible swap does not solve the
same-shape association problem. There is no global assignment or automatic
identity merging. Only observed ticks are geometrically verified; interpolation
between them retains existing linear authoring semantics. Small contours,
quantization, long chains or ambiguous landmarks can still abstain under the
unchanged raster policy. The fixture's initial B contour exceeded the 0.75-pixel
RMS cap in one interval; a vertex was changed for a stable controlled fixture,
without widening the cap or changing production code.

No occlusion, missing target, partial visibility, RGB, photographs, optical flow,
neural tracking, perspective, deformation, non-uniform scale, uncertainty model,
RANSAC, optimizer, video ingestion or Camera replacement is introduced. S11D is
outside this slice.
