# Geometry-correct Group Translation Authoring v0.1

## Boundary

`GeometryTranslationTracksAdapter` explicitly creates one linear Group
`translate.x` / `translate.y` Track pair under
`svm-geometry-correct-translation-authoring@0.1`. Inputs are one accepted S4
similarity Artifact (world-space observations with no Camera motion), or one
accepted S9B compensated similarity Artifact, an explicit Motion Target Binding,
and a positive integer timebase. No existing translation Track may be overwritten.

The governing invariants are explicit motion-target selection, INV-REL-002
(fixed-origin Group composition), INV-TXN-001 (atomic x/y authoring), and
INV-PROP-001/002 (preview and verified acceptance).

R0 displacement and S0 `translation` remain observed bounds-center displacement.
Their bytes, policies, and legacy cumulative authoring semantics are unchanged.
Bounds-center displacement is not generally a Group translation delta under
rotation or scale. S4's `translation` is instead landmark-centroid displacement
paired with its recorded centroid `origin`; neither displacement is directly
the affine matrix translation.

## Geometry-to-Group conversion

Reuse the six-component matrix convention from `scene.py` and the existing
Camera compensation composition helpers. For an S4 interval, reconstruct its
relative similarity B from the supported rotation and positive uniform scale,
source landmark centroid, and centroid displacement.

For uncompensated S4 input, W = B. For compensated input:

```text
W = inverse(V1) * B * V0
G0 = matrix(captured static Group transform)
Gnext = W * Gprevious
Group translate = b - o + A * o
```

Here `G = [A | b]` and `o` is the unchanged Group origin. The first keyframe
equals the captured static Group translation exactly. Subsequent values use
the repository's canonical 12-significant-digit number policy. Both rotation
and scale components must be SUPPORTED; origin/displacement and resulting
matrices must be finite. Intervals retain the existing contiguous-chain subset.

The static Group baseline must describe the source observation's initial pose
in the same world coordinate system. This slice does not infer initial
registration, geometry, or target selection. It authors translation only;
matching rotation and scale Tracks remain separately previewed authoring actions.
Linear interpolation is retained; observation samples do not infer easing.

## Camera evidence reuse

S9B compensated similarity v0.1 does not store the full world-relative matrix.
Its `translation` field retains its existing compensated bounds-displacement
meaning. The new authoring Change therefore resolves the exact three accepted
source Artifacts named by that compensated result: Camera, target S0, and
target S4. It rederives the complete compensated similarity bytes, verifies
target identity and exact interval pairing, validates the existing identity-
baseline Camera chain, and reconstructs W from the original S4 geometry and
Camera transforms. S0 is used to verify the existing compensation lineage;
its displacement is not used to compute the new Group translation.

No evidence schema, Camera producer, Camera Track, or compensation policy is
changed. Camera input retains S9B/S9C's restrictions, including identity initial
Camera and supported uniform similarities. The new authoring path does not
repair unrelated evidence-producer or observation-identity limitations.

## Authority, identity, and compatibility

The Proposal uses existing Group Track and Keyframe Changes plus exact-type
registered `VerifyGeometryTranslationTrackSourceChange`. Acceptance rederives
the samples, Track identities, provenance, and expected complete animation.
Evidence and compensation sources must already be accepted. Binding, Group,
source Revision, and animation checks preserve stale-safe atomic acceptance.
The existing `author_observed_translation`, Track creation, and Keyframe policy
actions continue to apply. No changes to ProposalAcceptor are needed.

Track identity hashes policy, Binding, evidence Artifact, Group ID, property,
timebase, and the complete captured static transform (including origin).
Keyframe identity hashes Track ID and tick. Persistent provenance retains
`ObservedTranslationTrack` with the new authoring identity and existing
evidence/Binding/source-Revision fields. The development Document schema adds
this identity to its explicit allowlist; sampling semantics are unchanged.

Legacy S2/S3 authoring keeps its policy and identity rules. It cannot claim
ownership of geometry-correct Tracks. This version supports CREATE only, with
no implicit migration or replacement of either legacy or new Tracks.

## Proof and exclusions

`tests/test_geometry_correct_translation.py` exercises asymmetric geometry with
an origin different from its bounds center: rotation only, scale only, combined
motion, known translation, nonidentity Group baseline, no target motion,
moving shared Camera, rendered landmark agreement, unrelated-target isolation,
determinism, preview purity, rejection, and unchanged R0/S0 displacement.
The checked-in Documents are in `examples/031-geometry-correct-translation`.

Repeated-frame identity, interval coverage extensions, multi-anchor consensus,
uncertainty/noisy fitting, raster input, automatic binding, Camera replacement,
and broad Core refactoring remain outside this slice.
