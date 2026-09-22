# Synthetic Motion Recovery v0 (Golden S9A)

## Scope

S9A proves a deterministic round trip from a hand-authored SVM animation to
frozen renderer SVG observations and back to structured Group transform Tracks.
It recovers translation, uniform scale, and absolute unwrapped rotation only.
Camera, style, easing, target discovery, raster input, and real video recovery
are outside this slice.

## Ground-truth boundary

Ground Truth and Recovery are separate Documents. Ground Truth Tracks may only
be consumed by `MotionEvaluator` and `SVGRenderer` while producing frozen SVG
frames. After rendering, recovery consumes only those SVG bytes, explicit tick
metadata, and the static Recovery Document. Ground Truth Track payloads are not
recovery inputs.

The Recovery Document contains the same static construction and explicit Group
baseline but no motion Tracks. Its Group binding remains explicit and manual.

## Formal recovery chain

Each consecutive SVG pair crosses the existing accepted boundaries:

```text
SVGGeometryObservationAdapter
→ TemporalCorrespondenceAdapter
→ TemporalIdentityPromotionAdapter
→ ObservedTranslationMotionAdapter / ObservedSimilarityMotionAdapter
→ TemporalMotionTargetBindingAdapter
→ existing translation / scale / rotation Track CREATE adapters
→ MotionEvaluator
→ SVGRenderer
```

Every Proposal is accepted through registered ChangeAuthority and artifact
verification. Translation uses accepted S0 displacement evidence. Scale and
rotation use independently SUPPORTED S4 components. Recovered Tracks retain
their normal evidence, Binding, source Revision, and authoring-policy
provenance.

## Numeric semantics

The Recovery Group's static transform is the only authoring baseline.
Successive observed deltas accumulate into absolute linear keyframes. Rotation
remains unwrapped. Comparison at observation ticks uses a small tolerance only
for renderer decimal serialization and similarity-fit arithmetic.

## Determinism and failure

Equivalent frozen frames and Recovery Document state produce the same Artifact,
Proposal, Binding, Track, and Keyframe identities. Missing Binding,
component-level unsupported rotation, forged target Group, existing CREATE
target, and stale Proposal state fail without partial Document mutation.
