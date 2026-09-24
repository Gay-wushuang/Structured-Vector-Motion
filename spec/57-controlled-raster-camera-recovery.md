# Controlled Raster Camera Recovery v0 (S11B)

Status: normative measured-evidence extension of S9B/S10C. S11A geometry and
measurement policies, exact S10C agreement, and authoring mathematics remain
frozen. Governing invariants are INV-REF-001, INV-TIME-010, INV-PROP-001/002 and
INV-TXN-001.

## Shared recovery boundary

Accepted PNG/OpenCV analysis produces independent, explicitly selected raster
occurrences for Anchor A, Anchor B and one Target. Each lineage goes through
existing R0, explicit R1, S0 and raster S4. Raster processing ends at evidence.
No raster Camera adapter, solver, compensation math or Track authoring is added.

ObservedCameraSimilarityAdapter consumes one accepted S4 Artifact and an explicit
`anchor_entity_id`. The Recovery Document must pass the existing static-anchor
checks: the Entity exists, has no Entity Track and belongs to no animated Group;
Camera starts at the identity baseline. The measured acceptance path repeats
static verification when applying its Change, including within a transaction.
This retains the existing conservative static-anchor subset, not a general proof
of arbitrary construction-program stationarity.

For vector evidence, geometry still declares the matching SVG `shape_id`. Raster
components have no semantic Entity identity. The caller's explicit anchor Entity
declaration associates the selected raster Temporal Identity with the static
anchor for this hypothesis; it is recorded by the Camera Artifact's anchor and
source similarity fields. It does not create a Motion Target Binding or perform
automatic association. Incorrect declarations remain the caller's responsibility;
incompatible observations fail downstream rather than being silently rebound.

## Verified measured Camera hypothesis

Single-anchor Camera media/schema/identity stay
`application/vnd.svm.observed-camera-similarity+json;version=0.1`,
`svm-observed-camera-similarity-0.1`, `svm-observed-camera-similarity@0.1`.
The measured evidence contract explicitly selects
`svm-static-anchor-camera-similarity@0.2` and records
`measurement_policy_identity: svm-controlled-raster-similarity-policy@0.1`.
The original `svm-static-anchor-camera-similarity@0.1` path is unchanged.

The measured path requires canonical accepted raster S4 and its accepted geometry,
PNG, mask and component-analysis dependency closure. Proposal and acceptance
reuse S11A's exact raster verifier, then reproduce each S4 interval's measurements,
geometry endpoints and content ID under the frozen raster measurement policy.
Copying policy/type strings onto vector evidence is insufficient. Missing pixel
dependencies or forged source descriptors, geometry, measurements or provenance
reject before any Camera evidence is accepted.

Camera matrix construction and baseline accumulation use the existing
`_camera_payload` / `_interval_matrix` / `_compose` conventions. There is no fit
against Document geometry and no Ground Truth input. Static-anchor declaration is
explicit, separate from measurement provenance and Entity identity.

## Strict measured agreement

MultiAnchorCameraConsensusAdapter gains the explicit option:

```json
{"agreement_policy": "svm-controlled-raster-camera-agreement@0.1"}
```

Omitting this option retains `svm-strict-multi-anchor-camera-consensus@0.1` and
its exact six-coefficient absolute tolerance `1e-8`. That threshold is not changed.
Unknown policies reject. Exact and measured hypotheses cannot be mixed or passed
through the other policy. Measured anchors must have distinct Temporal Identities
and disjoint observation occurrences; copying one lineage into two explicit
anchor hypotheses does not establish independent support.

Every hypothesis must have exactly the same contiguous interval chain. For each
interval, compare all unordered hypothesis pairs for all three transforms:
`relative_view_transform`, `source_view_transform`, `target_view_transform`.
Use existing `recover_camera_state` to decompose each transform under the Camera
convention, including the inverse-linear position conversion. Require all:

| Physical quantity | Pairwise limit |
| --- | ---: |
| Euclidean Camera position difference | 2.5 baseline-coordinate pixels |
| Shortest circular rotation difference | 0.2 degrees |
| `max(scale)/min(scale)-1` | 0.003 |

Position for an absolute view transform is world-space Camera position in the
pixel-aligned baseline frame; for a relative view transform it is the analogous
position parameter in that transform's coordinate system. Positive scale is
required by the existing Camera decomposition. Matrix coefficient tolerances
are not expanded.

These are controlled measurement-agreement limits, not confidence intervals or
universal reconstruction-error guarantees. S11A contour approximation and pixel
rounding affect orientation and scale; their extrapolation to the Camera origin
amplifies position error for spatially separated anchors. The checked-in anchors
span roughly 230–270 pixels, one near x=1000. The measured maximum differences
over relative/source/target states are 2.331202 pixels, 0.101179 degrees and
0.000989 scale ratio. The stated small margins cover this quantization regime;
larger coordinates, smaller features or longer accumulated chains may abstain.
Do not widen them dynamically to make a scene pass.

After ALL checks, copy the lexicographically first anchor's matrices unchanged.
No average, fitting, weighting, voting or outlier removal is permitted. Any
disagreement rejects before a consensus output Artifact is imported. Reordering
inputs must preserve Artifact/interval/Proposal identity at the same Revision.

## Consensus representation and acceptance

Reuse the S10C consensus media/schema/identity. The new policy records
`agreement_tolerances` with `position_pixels`, `rotation_degrees`, `scale_ratio`
instead of the legacy `agreement_absolute_tolerance`. Exact field values are
verified. Canonical representative, ordered supporting hypotheses, source Camera
IDs, all supporting interval IDs and policy are retained. The measured provenance
uses producer version 0.2; exact provenance stays version 0.1.

The existing registered AttachMultiAnchorCameraEvidenceChange captures every
anchor, Groups, animation and presentation. Both Proposal and Accept resolve the
complete measured pixel closures, reverify the independent single-anchor
hypotheses and reconstruct the consensus. Extra/missing sources, mutated
thresholds, representative, matrices, source hypotheses, stale state or animated
anchors reject atomically. No new Change authority or raster-specific pipeline
is introduced.

## Compensation and authoring

The shared Camera evidence reader admits the explicit measured single-anchor and
consensus policies. Existing CameraCompensatedMotionAdapter uses its unchanged
world compensation mathematics and schemas. GeometryTranslationTracksAdapter
uses the verified Camera/source similarities and the fixed off-center Group
origin, not S0 bounds-center displacement. Rotation and scale authoring consume
the same compensated similarity; Camera authoring uses ObservedCameraTracksAdapter.
One Recovery Document contains four Target and four Camera Tracks.

Each Target Track points to compensated evidence and its explicit target binding.
Compensation points to Target S0/S4 and consensus; consensus points to BOTH Camera
hypotheses; their S4 points to raster geometry and exact PNG/analysis/mask/component
provenance. Camera Tracks point to that same consensus. No lineage is discarded.

## Executable acceptance

`examples/036-controlled-raster-camera-recovery` contains checked-in 8-bit opaque
grayscale PNGs at ticks 0,12,24,36, two separated non-symmetric static anchors,
one moving asymmetric Target with off-center origin and pan+rotation+zoom Camera.
Camera holds between 12 and 24 while the Target continues moving. Explicit
analysis-local component selectors are recorded separately. Tests do not generate
frames or read Ground Truth transforms/points during inference.

At sampled ticks, compare final state to Ground Truth only after recovery:

| Quantity | Target tolerance / measured max | Camera tolerance / measured max |
| --- | --- | --- |
| Position/translation, Euclidean pixels | 1 / 0.678731 | 1 / 0.624717 |
| Rotation, degrees | 0.2 / 0.085919 | 0.2 / 0.077883 |
| Scale, absolute ratio | 0.005 / 0.003163 | 0.003 / 0.000978 |

Additionally parse actual SVGRenderer output paths and nested transforms after
MotionEvaluator sampling. Compare presented vertices against the original
raster-observed landmarks in view/pixel coordinates using symmetric nearest-vertex
distance with matching vertex count, at every tick for all three roles. Limit:
2 pixels; measured maximum: 1.434876 pixels. This compares geometry, not SVG
strings or PNG bytes, and introduces no rasterizer. Bounds displacement remains
unchanged observation evidence.

Tests also cover repeated identical full PNGs with distinct occurrences and zero
Camera motion; canonical representative/input order; independent recovery IDs,
Tracks and samples; Camera hold; disagreement from a checked-in moving-anchor
counterexample; wrong component; animated anchor/parent; Camera-side pixel forgery;
vector evidence relabelled raster; tolerance/policy/matrix/representative forgery;
and the requirement to check every pair and each physical limit.

Only observed ticks are validated. This slice adds no automatic association,
anchor discovery, additional moving targets, raster missing-frame policy, RGB,
photography, perspective, non-uniform scale, video ingestion or Track replacement.
