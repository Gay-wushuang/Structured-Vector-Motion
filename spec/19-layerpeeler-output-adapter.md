# LayerPeeler Research Output Adapter v0.2

## Status

Golden Test K is normative. The Adapter consumes an immutable snapshot of a
LayerPeeler run; it does not install, import, call, or trust the research model.

## Boundary

```text
ReferenceArtifact source
+ canonical layerpeeler-output manifest
+ DerivedArtifact layer SVGs
        -> Proposal preview
        -> explicit acceptance
        -> existing Entity / Operation / Style / Render Stack records
```

The canonical manifest records the full upstream Git commit, model identity,
checkpoint SHA-256, seed, source Artifact ID, and contiguous back-to-front layer
order. These fields derive one canonical run identity. The manifest and every
SVG must repeat that identity; layer provenance must additionally match the
repository, commit, model, checkpoint, seed, layer ID, and z-index. Mixed-run
bundles therefore fail closed.

Every SVG is independently content-addressed and normalized by the public,
versioned `SVGNormalizer` capability, including its media-type, 5 MiB, XML,
attribute, numeric, and path checks. The normalizer identity and canonicalized
SceneFragment Change participate in Proposal identity. No model tensor,
checkpoint, prompt, or private layer graph becomes Core Document semantics.

Each accepted shape records the generic machine-readable `source_layer`
association: producer family, bundle Artifact, run identity, layer ID, layer
Artifact, and an explicit `{index, semantics}` order-evidence record. LayerPeeler
uses `back-to-front`; it does not give that order semantic-hierarchy meaning.
Multiple SVG shapes from one research layer therefore remain associated without
creating semantic hierarchy.

The consumer Adapter identity is `svm-layerpeeler-output-adapter@0.2`; the
independent bundle identity is `svm-layerpeeler-output@0.2`. The manifest media type is
`application/vnd.svm.layerpeeler-output+json` and its schema identity is
`svm-layerpeeler-output-0.2`. Model-run identity is independently versioned as
`svm-layerpeeler-run@0.1`, so an Adapter-only upgrade does not rename the same
recorded research run.

`source_layer` is a reserved Artifact-bound semantic field. Generic scene
changes may not introduce it. Proposal acceptance dispatches only exact built-in
Change types through a trusted verifier registry; structurally compatible
third-party classes do not acquire acceptance authority by implementing the
Protocol. The verifier reconstructs the canonical fragment from resolved bytes.
More generally, Proposal acceptance is closed-world: every executable Change
must be an exact type in the trusted Change registry. Adapters may be external,
but executable Transaction primitives are SVM-owned semantics; arbitrary Python
objects with an `apply()` method are rejected before policy or mutation.

## Golden K

Golden K proves that a fixed two-layer research output bundle produces stable
Artifacts, Proposal identity, Entity and Operation IDs, back-to-front Render
Stack order, and final SVG after explicit acceptance. Missing, reordered,
hash-mismatched, mixed-run, oversized, non-canonical, or
provenance-inconsistent output fails before Revision creation. One fixture layer
contains three shapes and proves all accepted Entities retain the same canonical
layer origin. Proposal construction does not mutate the base Revision.
