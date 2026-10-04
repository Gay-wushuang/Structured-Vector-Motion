# P2S-E1A — Bounded Authored Multipart Raster Production

Status: **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN**.
Inspection baseline: `d7bf71be5643be98bbbb1c2d191ddb488cbde910`.
This supplies E1's production prerequisite, not spec/74 Multipart Subject Evidence.
P2S-E1 is **READY TO RETRY / NOT IMPLEMENTED**. Multipart Subject Evidence runtime
is **NOT IMPLEMENTED**; whole-subject TemporalIdentity is **OPEN**; P2D-B remains
**BLOCKED**. Ordinary-video ownership inference and single-Entity targeting are
not solved. No Group, construction receipt, TemporalIdentity, representation
correspondence or MotionTargetBinding is produced.

## 1. Capability inspection and source decision

Spec/74 §15 correctly records the missing executable bridge at its baseline.
The inspected existing capabilities are:

| Capability | Finding and use |
| --- | --- |
| Spec/10, `svg_import.py`, `path_bounds.py`, `operations.py` | Explicit SVG `g` and `path` syntax already supported; closed straight-line paths have exact bounds and existing `CreatePath` geometry. `PathToPolygon` also exists, but curve flattening/Boolean geometry is unnecessary for triangles |
| `evaluator.py`, `scene.py`, `renderers/svg.py` | Existing paths evaluate and render; no general binary renderer exists. This slice does not change evaluation or route through SVG screenshots |
| Spec/73, `svg_group_construction.py` | Its exact rectangle/ellipse authority remains unchanged and inapplicable. Neither its parser nor its Group authority is reused |
| Spec/27, `pop_structure.py` | Integer/pixel-center coverage is numeric precedent only. No POP private helper or POP authority is imported |
| Examples 036/037/038; `test_video_ingestion.py` | Controlled polygon rasters, offline FFV1 encoding, and canonical decode comparison are practical existing precedents. Their source-ground-truth notes do not supply this slice's ownership proof |
| Spec/59, `video_ingestion.py` | Pinned complete AVI/FFV1 decode, canonical binary PNG and exact timing already executable; reused unchanged |
| Spec/64, `raster_primitive_observation_proposal.py` | Frozen area, edge, vertex and landmark-origin gates; reused unchanged |
| Spec/66, `primitive_observation_assembly.py` | Complete supported observations and replayed lineage; reused unchanged |
| `opencv_analysis.py` | Full-frame label matrix can be recomputed, so exact contribution equality is possible; bbox-relative digest alone is not the mapping proof |
| `artifacts.py`, `revisions.py` | Exact accepted descriptors, content hashes and existing revision snapshots; bytes in a resolver alone do not establish accepted source authority |

The selected source is an existing **SVG assembly**, with two triangular path
leaves inside its sole explicit `g`. This uses SVG's authored containment, not
the flattened importer's Entity list or pixel-derived labels. It narrows existing
SVG syntax; it does not invent an ownership sidecar or reinterpret arbitrary
SVM Entity membership. Source subject means exactly this recorded assembly,
not a recognized physical object or a whole-subject temporal identity.

The positive geometry was selected analytically **before** P2A measurement:
right triangles with side lengths 60/80/100 and 54/72/90, areas 2400 and 1944,
and unique-longest-edge margins 20 and 18. All exceed the frozen minimum area
256, minimum edge 8 and margin >4 with ample separation. The source itself
contains this asymmetry. Pixel measurement confirmed eligibility without changing
the geometry, thresholds, or statuses. Negative shapes are adversarial inputs,
not attempts to tune a failed positive.

## 2. Exact source grammar and acceptance

Grammar identity: `svm-svg-g-two-triangle-paths@0.1`.

The complete UTF-8 source is at most 65536 bytes, without BOM, XML declaration,
DTD, entity references, comments, CDATA or processing instructions. Only
whitespace text between elements is allowed. The tree is exactly:

```xml
<svg xmlns="http://www.w3.org/2000/svg">
  <g>
    <path id="part-a" d="M 20 20 L 100 20 L 20 80 Z"/>
    <path id="part-b" d="M 140 120 L 212 120 L 140 174 Z"/>
  </g>
</svg>
```

The displayed geometry is the Golden, not the only allowed coordinates. Root
and group attributes are exactly those shown. Each leaf has exactly `id`, `d`;
part keys must be `part-a`, then `part-b`. No other children, elements, attributes,
nesting, resources, transforms, styling or animation are allowed. Attribute order
and inter-element whitespace are immaterial to parsing; source byte identity
still changes. The `d` syntax is exactly `M x y L x y L x y Z` with single ASCII
spaces and canonical unsigned integer lexemes, no leading zeros except `0`.
Every vertex has x in [1,246] and y in [1,248]. Signed double area must be positive.
There are exactly three distinct noncollinear vertices and one closed, hole-free
filled contour per leaf. SVG defaults give opaque black fill and no stroke.

The continuous triangles must be strictly separated by a separating axis from
their edges; overlap and touching reject before rasterization. The complete
source part set is never pruned. P2A eligibility is additionally checked for both
parts in both occurrences. Any non-SUPPORTED result rejects production with
`AUTHORED_PARTS_NOT_P2A_ELIGIBLE`; no shape repair or profile fallback occurs.

Source selection enumerates the existing source revision's full Document
references: exactly one SVG ReferenceArtifact candidate (`image/svg+xml` or
`application/svg+xml`), whose actual media type must be `image/svg+xml`. Derived
SVGs are not candidates. Resolve the exact accepted descriptor and content hash.
Zero/multiple sources, resolver-only sources and mismatches reject. Caller lists
of Entity IDs, part selectors and arbitrary source selectors are not inputs.

The trusted host supplies an existing `RevisionStore`; this utility is not an
Adapter acceptance API. `reproduce_source` reads an existing accepted source
revision and verifies its snapshot against its revision witness. The verifier
requires that source revision to be an ancestor of the explicit current base,
the identical sole source descriptor to remain accepted there, and the video
reference to be absent from the earlier source revision. This establishes the
recorded source-before-video workflow, not a claim about wall-clock creation
of external files. No caller-authored revision witness substitutes for the store.

Subject identity is `{source_artifact_id, subject_path: [0]}`. Each part identity
is `{subject, part_key}`. Complete source bytes supply both geometry and membership
before raster/video production; neither observation order nor the video supplies
them. A byte-different source is a different source subject.

## 3. Fixed production policy

Policy identity: `svm-authored-two-triangle-raster-production@0.1`.
There are no options. The identity binds this grammar, all following raster/timing
semantics, and the bounded video verification route. A semantic change needs a
new version and review.

- Canvas: 256×256; x right, y down; origin at the upper-left pixel corner.
- Pixel `(x,y)` samples `(x+1/2,y+1/2)`. Double source coordinates and sample at
  odd integer coordinates. A sample is inside iff all three directed edge cross
  products are >=0. Thus edge equality is inside. All coverage arithmetic is
  repository-controlled Python integer arithmetic; no floating raster rounding.
- Whole frames are opaque gray8: foreground 0, background 255. No antialiasing,
  alpha, stroke, filters, Camera, clipping or external raster backend exists.
- Contribution masks are full-canvas gray8: included pixels 255, absent pixels 0.
  They are generated from each source path before union, not segmented from video.
- Occurrence 0 translates both parts by `(0,0)`; occurrence 1 by `(8,6)`.
  No part-relative motion, rotation, scale, deformation or occlusion exists.
  Coordinate bounds keep complete geometry inside both canvases.
- Exactly two complete video frames at FPS 1/1, frame indices `[0,1]`, timestamps
  `[0,1]` and `[1,1]`, ticks `[0,12]`, 12 ticks/second. Manifest sampling must
  explicitly assert `source_fps: [1,1]`; larger streams/subsets reject.
- `canonical_frame_png` uses spec/59's existing canonical PNG encoding unchanged
  for whole frames and contribution masks.

For each occurrence, reproduce both masks, reject intersection, and form the
whole foreground by their union. No independently authored whole-frame drawing
or unexplained pixel is permitted. A later component replay must also prove a
bijection, so adjacency that merges the parts into one component is ineligible.

## 4. Video and observation verification

`tools/build_authored_raster_fixture.py` is an offline fixture encoder, not an
authority or runtime encoder option. It uses the existing pinned OpenCV FFmpeg
backend with FFV1, grayscale 256×256 and FPS 1. It immediately checks exact decode
equivalence. There is no CairoSVG, browser, matplotlib, external executable or
fallback. Encoding byte identity is **not** an acceptance requirement: one
immutable AVI is accepted and its canonical decoded frames are compared.

Replay order is mandatory:

1. Reproduce all expected frames and contributions from the accepted source.
2. Resolve the current accepted exact video/manifest descriptors. Independently
   `verify_video_manifest` under unchanged spec/59, with complete two-frame/timing
   checks. Require canonical decoded PNG bytes equal expected PNG bytes exactly.
   Both decoded frame descriptors must also be accepted.
3. Reproduce unchanged P2B from the two accepted P2A artifacts in a scratch
   repository. Existing P2B replay independently checks P2A and its complete
   analysis/video closure. Require accepted P2B observation and audit bytes,
   kinds, media and provenance to match the reproduced outputs.
4. Require both occurrences to belong to the verified manifest in increasing
   order, each with exactly two SUPPORTED evaluations and two included P2B
   observations, no exclusions. Freeze analysis at its existing defaults:
   threshold 128, dark foreground, 8-connectivity. P2A semantics are unchanged.
5. Recompute the complete full-frame OpenCV labels. For each production mask,
   search **all** nonzero labels for exact equality at every canvas pixel. Require
   one match per part and two distinct labels. No nearest, first, bbox order,
   similarity, or digest-only choice is permitted. Verify matched labels exhaust
   the whole foreground.
6. Join that proven label to its unique analysis component by exact bounds and
   existing component digest, then to the replayed P2A evaluation and P2B audit
   observation. Verify all measured fields and ordered landmarks against the
   independently produced contribution. Source part identity stays in this
   production report; nothing is added to the P2B schema.
7. Only after every check, publish masks and a derived diagnostic production
   report. Publishing and independent verification do not mutate a Document,
   accept evidence, advance a Revision or gain any Change authority.

`publish_verified_production` also compares the entire supplied `ProducedRaster`
against replay, so changed frames, masks, source claims or measurements cannot
self-attest. `verify_production` independently repeats the entire process and
compares complete canonical report bytes and metadata, then resolves and checks
every expected contribution artifact. A stale current base rejects. The report
is only a capability result; no generic `AppendReferencesChange` endorsement is
implied. Future E1 acceptance must add its own reviewed admission boundary.

## 5. Artifact and report contract

Report schema: `svm-authored-raster-production-0.1`.
Media: `application/vnd.svm.authored-raster-production+json;version=0.1`.
Kind: DerivedArtifact; provenance exactly `{policy_identity: <policy>}`.
IDs use the existing SHA-256 canonical bytes contract, with no truncated hashes.

The complete report fields are `schema_version`, `policy_identity`,
`source_grammar`, `canvas`, `source_revision_id`, `verification_revision_id`,
`source_reference`, `subject`, `part_identities`, `video_reference`,
`manifest_reference`, ordered `p2a_references`, `p2b_observation_reference`,
`p2b_evidence_reference`, and `occurrences`. Extra or missing fields reject by
full canonical replay comparison. Descriptor values are reproduced from accepted
input references, not trusted from the report.

Each occurrence contains the unchanged spec/59 occurrence fields (including
`raster_artifact_id`, the expected **and** verified decoded whole-frame ID),
`translation`, and exactly two ordered `parts`. Each part contains `part_key`,
`contribution_artifact_id`, `component_id`, `evaluation_id`, `observation_id`,
`status`, `reason_codes`, `measurements`, `ordered_landmarks`. The latter four
are exact unchanged P2A results. Occurrence identities remain spec/59 identities.
The source-qualified part identities remain distinct even for identical pixels
in different accepted sources.

Whole-frame PNG ReferenceArtifacts have spec/59's empty provenance. Contribution
PNGs are DerivedArtifacts with exact provenance
`{policy_identity: <policy>, role: "contribution"}`. Equal contribution bytes can
share a blob; their occurrence/source relationship belongs in the replayed report.
Neither that provenance nor the report alone proves authority. The actual accepted
source revision, current base and full dependency repository must remain available
for independent replay. Losing them does not permit trusting the report's hashes.

## 6. Golden, measurements and adversarial coverage

`examples/043-authored-raster-production/source.svg` is the independent authored
input; `scene.avi` is its immutable two-frame video. `golden.json` records the
complete reproduced report and hash. Tests replay source acceptance before video,
all production, spec/59, accepted P2A/P2B, exact contribution matching and report
verification. No Group/artwork construction or inference override occurs.

| Occurrence / part | Contour area | Vertices | Minimum edge | Longest-edge margin | Ordered landmarks |
| --- | ---: | ---: | ---: | ---: | --- |
| 0 / a | 2291.5 | 3 | 59 | 19.8008179924892 | `(20,79), (98,20), (20,20)` |
| 0 / b | 1846.5 | 3 | 53 | 17.80091115700337 | `(140,173), (210,120), (140,120)` |
| 1 / a | 2291.5 | 3 | 59 | 19.8008179924892 | `(28,85), (106,26), (28,26)` |
| 1 / b | 1846.5 | 3 | 53 | 17.80091115700337 | `(148,179), (218,126), (148,126)` |

All four are SUPPORTED with one outer contour, no holes and no reason codes.
P2B contains exactly two observations per occurrence, zero exclusions. A second
independent source swaps the two path geometries while retaining canonical keys;
the **same video** then maps `part-a` to component 2 and `part-b` to component 1.
This verifies that spatial/component order is not source ownership authority.

Negative tests cover missing/resolver-only source, changed source bytes,
omitted/extra/reordered parts, flat/nested sources, wrong/degenerate geometry,
overlap, forbidden transforms/styles, noncanonical coordinates, fake media,
real ineligible small and ambiguous triangles, changed frames/contributions,
unexplained foreground, duplicate pixel ownership, omitted occurrences, wrong
video/manifest/timing, forged P2A statuses, incomplete P2B, stale base,
post-video source revision, policy/subject/part/observation claims and corrupt
or missing contribution artifacts. Failure leaves the Revision Store unchanged.

This capability permits retrying E1. E1 still must admit its bounded ownership
evidence profile, complete universe/competing-claim rules, schema and acceptance
replay. This spec does not discharge those gates or alter spec/71, P2D, frozen
numeric tolerances, P2A/P2B semantics, or Proposal acceptance authority.
