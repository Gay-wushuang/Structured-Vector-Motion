# LayerD Raster Layer Evidence Adapter v0.1

## Status

Golden Test L is normative. The Adapter consumes an immutable snapshot of a
LayerD run. It never imports or executes LayerD, BiRefNet, LaMa, CUDA, or model
checkpoints.

## Boundary

```text
ReferenceArtifact source
+ canonical LayerD manifest
+ canonical layer-analysis evidence
+ content-addressed RGBA PNG layers
        -> Proposal preview
        -> explicit acceptance
        -> neutral, non-rendered Entities
```

The manifest records the upstream repository and full Git commit, both model
checkpoint hashes, seed, runtime, device, source Artifact, and an ordered list
of layer Artifacts. Run, bundle, and consumer Adapter identities are independent:

```text
svm-layerd-run@0.1
svm-layerd-output@0.1
svm-layerd-output-adapter@0.1
```

The accepted RGBA subset is non-interlaced 8-bit RGBA PNG with filter-0
scanlines, identity `svm-png-rgba8-filter0@0.1`. The verifier derives alpha
bounds and non-transparent pixel count from Artifact bytes and compares them to
the canonical layer-analysis Artifact. It does not rerun a research model.

## Semantics

LayerD sequence is recorded only as source evidence:

```json
{"index": 1, "semantics": "background-then-top-to-bottom-extraction"}
```

It does not create Render Stack entries, Entity hierarchy, structural relations,
construction operations, styles, or animation. Each accepted layer becomes a
neutral addressable Entity tagged `region`, `research-layer`, and
`layerd-output`. RGBA pixels remain Artifacts.

`text`, `vector`, `image`, and `unknown` are classification candidates in the
analysis Artifact and Proposal notes only. They are not copied into Entity names,
semantic tags, hierarchy, or render semantics.

`source_layer` is the cross-Adapter evidence binding and contains producer
family, bundle Artifact, run identity, layer ID, layer Artifact, and explicit
order evidence. Its dimensions remain orthogonal to hierarchy and presentation.

## Acceptance authority

`ImportRasterLayerEvidenceChange` is a registered Core Change primitive. Its
trusted verifier reconstructs the complete Change from resolved Artifact bytes
and requires exact equality before transaction execution. Generic or unregistered
Changes cannot write `source_layer`.

Golden L is accepted only through the Change Authority Registry. Adding this
second research Adapter must not modify `svm/proposals.py`; the test pins its
post-registry-refactor SHA-256 to make that constraint executable.

## Golden L

Golden L proves deterministic Proposal identity, immutable base Revision,
previewable RGBA/analysis evidence, exact acceptance-time reconstruction,
neutral non-rendered Entities, and stable evidence order. It rejects unsupported
classification, forged Change semantics, malformed provenance, inconsistent
hashes or analysis, reordered layers, invalid PNG structure, and mixed runs.
