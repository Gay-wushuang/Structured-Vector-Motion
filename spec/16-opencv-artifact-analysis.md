# OpenCV Artifact Analysis v0.1

## Status

This specification defines deterministic raster analysis through OpenCV without
claiming vector geometry or Entity identity. Golden Test H is normative.

## Pipeline and boundary

```text
PNG ReferenceArtifact
-> OpenCVAnalysisAdapter
-> DerivedArtifact(binary mask PNG)
-> DerivedArtifact(component analysis JSON)
-> StructuralCandidatePreview
-> explicit Proposal acceptance
-> Artifact references only
```

The Adapter MUST NOT create Entities, Operations, output bindings, Styles, or
Render Stack entries. A structural candidate is analysis evidence, not an
Entity. Converting or matching a candidate requires a later explicit Proposal.

## Input semantics

The v0.1 subset accepts one opaque PNG up to 32 MiB and 16 megapixels. The PNG
signature and IHDR dimensions are checked before OpenCV decoding. Alpha and PNG
transparency are rejected.

Recorded parameters are:

- integer threshold in `[0, 255]`;
- foreground polarity `dark` or `light`;
- connectivity, fixed to `8` in v0.1;
- `svm-opencv-components@0.1` analysis identity;
- `svm-binary-mask-png@0.1` mask encoding identity;
- exact `opencv-python-headless` distribution version and OpenCV runtime version.

Dark foreground means `gray <= threshold`; light foreground means
`gray >= threshold`. The mask is 0 for background and 255 for foreground.

## Component analysis

OpenCV `connectedComponentsWithStats` supplies labels, pixel area, bounds, and
centroid. Background label 0 is excluded. Candidates are sorted by
`(min_y, min_x, max_y, max_x, pixel_area, centroid)` and assigned analysis-local
IDs `candidate:component-0001`, etc.

Bounds are half-open pixel coordinates `[min_x, min_y, max_x, max_y]`.
Centroids are canonical `.12g` numbers. The canonical JSON media type is
`application/vnd.svm.component-analysis+json`.

The binary mask uses an SVM-owned deterministic grayscale PNG encoder with
filter 0 scanlines and stored DEFLATE blocks. Its text chunk records
`SVMArtifact=binary-mask-v0.1` plus the source content hash. This avoids
platform encoder drift and distinguishes derived evidence from byte-identical
source PNG content while retaining a normal decodable PNG.

## Acceptance

The Proposal exposes both Derived Artifacts through `preview_artifacts` and all
components through `ProposalPreview.structural_candidates`. Acceptance uses
`AppendReferencesChange` with the `attach_analysis` policy action and attaches
the source plus both Derived Artifact references atomically. Artifact bytes and
descriptors MUST resolve before commit.

## Golden Test H

Golden H contains two components and proves:

1. exact threshold, 8-connectivity, bounds, pixel area, and centroid;
2. byte-stable mask PNG and canonical analysis JSON;
3. content-addressed Derived Artifacts with complete provenance;
4. preview does not mutate the Revision;
5. acceptance adds only Artifact references and no Entity claim;
6. invalid PNG, alpha, size, options, stale Proposal, missing Artifact, and
   `attach_analysis` permission fail closed.
