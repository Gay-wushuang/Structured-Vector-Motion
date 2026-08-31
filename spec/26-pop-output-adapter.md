# Primitive Operation Painter Output Adapter v0.2

## Status

Golden Test P is normative. The Adapter consumes one immutable snapshot of a
Primitive Operation Painter (POP) result. It never imports or executes PyTorch,
the upstream repository, or model weights.

## Boundary

```text
POP model run
-> canonical DerivedArtifact
-> POPOutputAdapter
-> ordered primitive SceneFragment Proposal
-> ProposalAcceptor dry run
-> preview
-> explicit acceptance
-> one atomic Revision
```

The output Artifact media type is `application/vnd.svm.pop-output+json`; its
schema is `svm-pop-output-0.2`. The operation-prefix Artifact uses
`application/vnd.svm.pop-token-prefix+json` and
`svm-pop-token-prefix-0.1`. Run, output, and consumer identities are independent:

```text
svm-pop-generation-config@0.1
svm-pop-output@0.2
svm-pop-output-adapter@0.2
```

POP is an operation-prefix continuation model, not prompt-to-image. The
`generation_context` therefore contains only an exact prefix Artifact ID and
content hash, prefix length, and target step count. Optional `user_intent` lives
under the separate top-level `annotations` record and MUST NOT be represented as
model input.

The recorded producer includes the exact upstream repository and Git commit,
model ID, checkpoint SHA-256, seed, decoding configuration,
`pop/geometrize_256_v1` token layout,
`pop/geometrize-256-quantization@0.1` quantization,
`pop/decode-tokens-to-render-data@d5489b0` decoder, and
`pop/matplotlib-half-alpha@d5489b0` renderer identity. Golden P defines two
explicit generation profiles:

```text
greedy
  policy = pop/argmax-lowest-token@0.1
  configuration = {tie_break: lowest-token-id}

field-aware-sampling
  policy = pop/gpt-sampling-config@d5489b0
  configuration = {schedule: upstream-default}
```

The second profile records the release's field-specific temperature/top-k
schedule and seeded multinomial sampling. Generation may therefore be
stochastic. Its seed and sampling-policy identity are provenance; Core and the
Adapter never rerun sampling.

`generation_config_identity` hashes the prefix identity, producer, seed,
sampling policy, and canvas. It identifies a generation configuration, not a
concrete execution result, and deliberately excludes `raw_tokens`. Two
environmentally nondeterministic executions may therefore share this identity
while producing different output Artifacts. The output Artifact ID and content
hash identify the concrete recorded token result.

Annotations are also deliberately excluded. Changing `user_intent`, a future
experiment name, or an author note changes the complete Artifact bytes but not
the generation configuration identity. Only fields capable of changing upstream
model execution may participate in `generation_config_identity`.

Accepting `field-aware-sampling` provenance proves only that the Artifact makes
a valid, internally consistent provenance assertion. It is not proof that the
upstream checkpoint was re-executed with that policy. End-to-end execution
truth belongs to a separately tested POPRunner boundary.

The output retains the complete raw nine-token sequence. Decoded canonical
geometry must equal an independent decoding of those tokens, and its leading
tokens must equal the complete prefix Artifact. Thus neither model-input nor
token-to-geometry semantics are implicit in Adapter code or prose provenance.
Determinism is required only after the immutable output Artifact boundary:

```text
possibly stochastic POP run
-> immutable raw-token Artifact
-> deterministic Adapter / Proposal / acceptance
```

## Accepted output subset

The upstream 256 layout fixes a 256×256 canvas. Quantization uses two coordinate
bins per pixel, three angle bins per degree, four size bins per pixel, and 128
RGB bins decoded by multiplication by two. Each ordered primitive contains:

```text
index, x, y, angle_degrees, width, height, shape_type, RGB
```

`index` is the contiguous generation/draw order. `x` and `y` are the primitive
center in canvas coordinates. Positive angles use the accepted affine Transform
semantics. v0.2 accepts only `ellipse` and `rotated_rectangle`, matching the
recorded POP capability; it does not invent paths, Boolean operations,
duplication, semantic labels, hierarchy, or animation.

`POPTokenExporter` converts a captured raw model continuation and its prefix to
the two canonical content-addressed Artifacts. It does not run the model.

Every primitive becomes a neutral Entity backed by one Create operation and
one Transform operation. POP's native renderer uses 0.5 primitive opacity, so
the accepted Style records 0.5; the background remains opaque. The background
is an explicit first rectangle. Render
Stack order is background followed by primitive index. POP order is construction
and rendering evidence only; it is not content-animation time and does not
create one Revision per token.

## Acceptance authority

`ImportPrimitiveSequenceChange` is a registered Core Change. Its Artifact-bound
verifier resolves the exact output Artifact, reruns deterministic normalization,
and requires exact Change equality. A handcrafted SceneFragment therefore
cannot claim POP provenance or bypass the reviewed import semantics.

The accepted Document stores only normal SVM Entities, Operations, bindings,
styles, Render Stack entries, and the immutable Artifact reference. It remains
valid and evaluable without POP installed.

## Golden P

Golden P proves:

1. equivalent base, prefix/output Artifacts, namespace, producer identity, and decoding record
   produce the same Proposal;
2. proposal construction and dry-run preview do not mutate the base Revision;
3. background, ellipse, and rotated rectangle map only to existing Core
   operations;
4. POP primitive order is preserved exactly in the Render Stack;
5. acceptance creates one atomic Revision whose primitives remain separately
   editable;
6. accepted Documents reload, evaluate, and render without an Artifact Store or
   POP installation;
7. one accepted primitive can be edited in a later Revision without invoking
   POP or changing unrelated primitive Values;
8. forged Changes, raw/decoded disagreement, malformed fields, unsupported
   shapes, provenance drift, ID collisions, and missing Artifacts fail closed.
