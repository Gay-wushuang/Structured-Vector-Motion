# LayerD Raster Layer Evidence Adapter v0.4

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
checkpoint hashes, seed, runtime, device, source Artifact, execution parameters,
analysis-pipeline identity/configuration, and an ordered list of layer Artifacts.
Every recorded input that may affect RGBA pixels, layer count/order, element
bounds, or classification participates in run identity. Run, bundle, and
consumer Adapter identities are independent:

```text
svm-layerd-run@0.4
svm-layerd-output@0.4
svm-layerd-output-adapter@0.4
```

The v0.4 execution contract records `max_iterations`, `kernel_scale`,
`matting_process_size`, `use_unblend`, `fg_refine`,
`fg_refine_num_colors`, `bg_refine`, and `bg_refine_num_colors`. The analysis
contract independently records a fixed element-extractor identity and its
`overlap_threshold`, an OCR identity/configuration, and the fixed
`entropy-labeler@0.1` identity with its `threshold`. Changing any recorded field
changes run identity and prevents cross-run bundle mixing.

Golden L deliberately accepts only `ocr_identity = disabled@0.1` with empty OCR
parameters. Outputs produced with EAST, GOT-OCR2, or any other enabled OCR
backend are outside this profile and fail closed. Supporting one requires a new
profile/run identity that also records its model and evidence contract.

Golden L likewise rejects `GradientAwareLabeler` and every classifier other than
`entropy-labeler@0.1`. Gradient-aware classification has a distinct two-parameter
contract (`entropy_threshold` and `gradient_threshold`) and cannot be represented
by this profile's single `threshold`. Supporting it requires a separately
versioned profile that records both parameters.

The accepted RGBA subset is non-interlaced 8-bit RGBA PNG with filter-0
scanlines, identity `svm-png-rgba8-filter0@0.1`. The verifier derives alpha
bounds and non-transparent pixel count from Artifact bytes and compares them to
the canonical layer-analysis Artifact. It does not rerun a research model.

## Semantics

LayerD sequence is recorded only as source evidence:

```json
{"index": 1, "semantics": "svm-order:layerd-extraction@0.1"}
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
order evidence. Core accepts any versioned `svm-order:*@major.minor` identity;
the Artifact verifier decides which identity belongs to a producer. Its
dimensions remain orthogonal to hierarchy and presentation.

## Acceptance authority

`ImportRasterLayerEvidenceChange` is a registered Core Change primitive. Its
trusted verifier reconstructs the complete Change from resolved Artifact bytes
and requires exact equality before transaction execution. Generic or unregistered
Changes cannot write `source_layer`.

Golden L is accepted only through the Change Authority Registry. Adding this
second research Adapter must not modify `svm/proposals.py`; the test pins its
post-registry-refactor SHA-256 to make that constraint executable. This is a
frozen blob baseline rather than a distinct pre-LayerD Git commit baseline.

## Golden L

Golden L proves deterministic Proposal identity, immutable base Revision,
previewable RGBA/analysis evidence, exact acceptance-time reconstruction,
neutral non-rendered Entities, and stable evidence order. It rejects unsupported
classification, forged Change semantics, malformed provenance, inconsistent
hashes or analysis, legal-label tampering, enabled OCR, unsupported classifier
profiles, reordered layers, invalid PNG structure, and mixed runs.
