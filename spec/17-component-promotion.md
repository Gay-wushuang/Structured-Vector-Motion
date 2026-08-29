# Component Promotion v0.1

## Status

This specification defines the explicit promotion of accepted analysis evidence
into neutral, addressable SVM Entities. Golden Test I is normative.

## Boundary

```text
accepted DerivedArtifact(component-analysis v0.2)
-> ComponentPromotionAdapter
-> selected candidate IDs
-> ProposalPreview
-> explicit acceptance
-> neutral Region Entities
-> Revision
```

The Adapter MUST consume only
`application/vnd.svm.component-analysis+json` bytes already referenced by the
base Document as a `DerivedArtifact`. It MUST NOT open the source PNG, resolve
the binary mask pixels, import OpenCV, rerun connected-components analysis, or
infer real-world semantics.

Analysis, interpretation, and Document mutation are separate stages. Merely
attaching analysis evidence creates no Entity. Merely previewing promotion
creates no Revision.

## Input validation

The Artifact descriptor MUST identify `svm-opencv-components@0.2` provenance
and `derived_type=component-analysis`. Its bytes MUST be canonical JSON with
schema `svm-component-analysis-0.2`.

The Promotion Adapter validates the complete fail-closed v0.2 evidence
contract, including:

- accepted source and binary-mask Artifact references;
- image, threshold, polarity, and 8-connectivity fields;
- canonical sequential candidate IDs;
- half-open in-image bounds, positive area, finite in-bounds centroid;
- SHA-256 component digest;
- canonical component ordering.

The user MUST provide a non-empty unique candidate selection. Unknown,
duplicate, malformed, or already-promoted candidates fail closed. Selection is
emitted in canonical evidence order, not caller argument order.

## Promoted semantics

Each selected candidate creates one deterministic neutral Entity:

```json
{
  "id": "entity:region-<stable digest>",
  "name": "Region 0001",
  "semantic_tags": ["region", "promoted-component"],
  "provenance": {
    "type": "PromotedComponent",
    "artifact_id": "artifact:<analysis hash>",
    "candidate_id": "candidate:component-0001",
    "component_digest": "sha256:<pixel-set digest>"
  }
}
```

Promotion means only that a user accepted an evidence region as an independent,
addressable semantic object. It does not claim `Hair`, `Face`, or any other
recognized class. v0.1 creates no geometry Operation, output binding, Style, or
Render Stack entry because component-analysis does not contain accepted vector
geometry.

Entity IDs are derived from the promotion identity, analysis Artifact ID,
candidate ID, and component digest. An optional safe namespace changes the ID
namespace but not the evidence provenance.

## Transaction and policy

`PromoteComponentsChange` atomically appends all selected Entities and requires
the exact component-analysis reference to already exist in the base Document.
Its policy intent is `promote_components` on `document`. The Proposal requires
that Artifact descriptor and bytes again at acceptance, so content or descriptor
drift fails closed.

`ProposalPreview.entity_diffs` exposes every proposed Entity ID and candidate
bounds. Confidence is `None`: deterministic interpretation is not semantic
classification confidence.

## Golden Test I

Golden I promotes both candidates from Golden H and proves:

1. preview leaves the base Revision unchanged;
2. explicit acceptance atomically creates two neutral Entities;
3. no PNG or OpenCV processing occurs in the Promotion Adapter;
4. no Operations, bindings, Styles, or Render Stack entries are created;
5. accepted Artifact identity, schema, provenance, candidates, and policy are
   validated fail closed;
6. candidate order and Entity IDs are deterministic;
7. stale, duplicate, and repeated promotion are rejected.
