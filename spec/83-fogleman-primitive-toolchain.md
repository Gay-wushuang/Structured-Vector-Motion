# fogleman/primitive External Toolchain v0.1

Status: P0 implemented and golden verified. This profile is intentionally an
external Adapter toolchain, not a Core Operation, Geometry Backend, Renderer,
or new identity-inference system.

## 1. Goal and boundary

The bounded chain is:

```text
real PNG bytes
-> ReferenceArtifact snapshot
-> pinned fogleman/primitive executable
-> raw SVG + native PNG snapshots
-> strict producer-specific SVG normalization
-> existing SVGImportAdapter Proposal
-> existing AppendSceneFragmentChange authority
-> ProposalAcceptor
-> one Revision
-> FINAL Evaluator / Evaluated Scene / SVGRenderer
```

The executor and producer-specific conversion code are isolated from Core.
They receive no `RevisionStore`, never call `RevisionStore.commit()`, do not
insert Runtime Values, and do not extend the SVG Import subset. The only
Document mutation remains the registered `AppendSceneFragmentChange` produced
by `SVGImportAdapter` and accepted through `ProposalAcceptor`.

## 2. Producer pin and execution record

Each run records:

- repository `https://github.com/fogleman/primitive`;
- caller-supplied exact lowercase 40-hex Git commit;
- SHA-256 of the executed binary;
- complete bounded parameters: shape count, mode and mode ID, alpha, input and
  output size, and worker count;
- a normalized argument vector with no shell execution;
- source, raw SVG, native PNG, normalized SVG, Document, and rendered SVG
  byte hashes;
- Proposal, Transaction, and Revision IDs;
- observed execution and total wall durations.

The executable has no version command, so the asserted Git commit cannot be
cryptographically derived from the binary. The binary hash identifies the
exact executable actually run. Building that binary from the asserted source
commit remains a production supply-chain responsibility.

## 3. Randomness boundary

Upstream commit `0373c216458be1c4b40655b796a3aefedf8b7d23` calls
`rand.Seed(time.Now().UTC().UnixNano())`, and every Worker creates another
clock-seeded `rand.Rand`. It exposes no seed parameter. Worker count one reduces
scheduling variance but does not make fitting replayable.

Therefore:

- SVM MUST NOT claim that a new Primitive execution reproduces prior geometry;
- the concrete raw SVG and native PNG MUST be snapshotted and hashed;
- deterministic replay begins at the frozen raw SVG;
- accepted Documents remain evaluable without Primitive installed.

This satisfies the Artifact boundary: nondeterministic external execution is
made immutable before its result crosses into accepted construction semantics.

## 4. Why direct SVG import is rejected

Primitive's native SVG uses fields outside `spec/10`:

- root `version`, `width`, and `height` attributes;
- one global `scale(...) translate(...)` group;
- nested translate/rotate/scale groups for rotated shapes;
- `<polygon>` leaves;
- `fill-opacity` or `stroke-opacity`;
- quadratic paths in the producer's exact textual form.

`SVGImportAdapter` correctly rejects these. Core is not widened for this tool.

## 5. Minimal restricted normalizer

`svm-fogleman-primitive-svg-normalization@0.1` accepts only the exact output
grammar emitted by the pinned producer:

| Producer output | Strict SVG Import output |
| --- | --- |
| background rectangle | `<rect>` |
| axis-aligned rectangle | transformed `<rect>` |
| axis-aligned ellipse or circle | transformed `<ellipse>` |
| triangle or polygon | closed `<path>` |
| rotated rectangle | four-corner closed `<path>` |
| rotated ellipse | two-arc closed `<path>` |
| quadratic stroke | transformed quadratic `<path>` |
| `fill-opacity` / `stroke-opacity` | leaf `opacity` |

The normalizer bakes the producer's transforms into geometry, scales stroke
width, emits unitless finite numbers, assigns deterministic leaf IDs, emits only
six-digit hex colors or `none`, and records the output canvas as `viewBox`.

Unknown elements, attributes, namespaces, transform forms, path syntax,
non-finite values, invalid opacity, non-positive dimensions, DTD/entity input,
empty fits, and files over the SVG import limit fail closed. Approximation is
not used to admit unknown producer output.

## 6. Artifact and acceptance semantics

The source PNG is a ReferenceArtifact. Raw SVG and the native PNG preview are
DerivedArtifacts. The normalized SVG is presented to the existing importer as
a ReferenceArtifact whose provenance records the source Artifact, raw SVG
Artifact, native preview Artifact, producer, parameters, runner identity, and
normalization identity.

Only the normalized SVG reference enters the accepted Document because it is
the complete external resource needed to audit the imported construction. The
run bundle retains the complete source and intermediate closure. Acceptance
uses the unchanged `import_scene` action for `adapter:svg-import`; existing deny
permissions therefore block this toolchain without a special case.

Each normalized leaf becomes one independently addressable Entity, registered
Create Operation, output binding, Style, and Render Stack entry. Background and
fitted shapes retain producer draw order. No semantic label, hierarchy, Group,
animation, temporal identity, or motion target is inferred.

## 7. Evidence bundle and replay

`import-primitive` writes a new directory containing:

```text
source.png
primitive.svg
primitive.png
normalized.svg
accepted.svm.json
svm.svg
run-manifest.json
```

`run-manifest.json` is canonical JSON under schema
`svm-fogleman-primitive-run-0.1`. `replay-primitive` verifies every file hash,
reruns normalization from `primitive.svg`, reconstructs the exact normalized
Artifact descriptor, submits the same Proposal through `ProposalAcceptor`, and
requires byte-identical accepted Document and SVM SVG plus identical Proposal
and Revision IDs. The replay path never invokes Primitive.

## 8. Golden 047

`examples/047-fogleman-primitive-toolchain/` records one real execution against
the checked-in 256x256 PNG from Golden P. The run uses the upstream commit above,
12 combo-mode shapes, alpha 128, input size 128, output size 256, and one worker.
The bundle retains source, native result, normalized geometry, accepted
Document, Revision evidence, deterministic SVG, and a rasterized SVM comparison
image. The focused test suite covers all producer shape classes, exact replay,
permission denial, tamper rejection, malformed input, and producer-vocabulary
drift.

## 9. Deliberate exclusions and production blocker

This P0 does not implement Animosaics, video tracking, AI segmentation, Spec82
changes, semantic grouping, identity reconciliation, or new Core SVG syntax.

The upstream clock-only RNG and unverifiable commit-to-binary claim are the two
production boundary blockers. Production use requires either a reviewed fork
with an explicit recorded seed and deterministic worker seeding, or a signed
reproducible binary provenance system. Neither blocker weakens the immutable
post-run Artifact, replay, Proposal, or Revision semantics implemented here.
