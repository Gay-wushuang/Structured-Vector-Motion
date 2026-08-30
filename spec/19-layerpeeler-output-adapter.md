# LayerPeeler Research Output Adapter v0.1

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
order. Every SVG is independently content-addressed and must carry matching
DerivedArtifact provenance. Paths are accepted only through the existing strict
SVG import subset. No model name, tensor, checkpoint, prompt, or private layer
graph becomes Core Document semantics.

The Adapter identity is `svm-layerpeeler-output@0.1`; the manifest media type is
`application/vnd.svm.layerpeeler-output+json` and its schema identity is
`svm-layerpeeler-output-0.1`.

## Golden K

Golden K proves that a fixed two-layer research output bundle produces stable
Artifacts, Proposal identity, Entity and Operation IDs, back-to-front Render
Stack order, and final SVG after explicit acceptance. Missing, reordered,
hash-mismatched, non-canonical, or provenance-inconsistent output fails before
Revision creation. Proposal construction does not mutate the base Revision.
