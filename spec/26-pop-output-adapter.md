# Primitive Operation Painter Output Adapter v0.1

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

The Artifact media type is `application/vnd.svm.pop-output+json`; its schema is
`svm-pop-output-0.1`. Run, output, and consumer identities are independent:

```text
svm-pop-run@0.1
svm-pop-output@0.1
svm-pop-output-adapter@0.1
```

The run records the exact generation input. The recorded producer includes the
exact upstream repository and Git commit, model ID, checkpoint SHA-256, seed,
and decoding configuration. Golden P permits
only deterministic greedy decoding with an explicit maximum step count. The
result bytes are content-addressed before the Adapter sees them.

## Accepted output subset

The canvas records positive width and height in Document coordinate units and
an opaque RGB background. Each ordered primitive contains exactly:

```text
index, x, y, angle_degrees, width, height, shape_type, RGB
```

`index` is the contiguous generation/draw order. `x` and `y` are the primitive
center in canvas coordinates. Positive angles use the accepted affine Transform
semantics. v0.1 accepts only `ellipse` and `rotated_rectangle`, matching the
recorded POP capability; it does not invent paths, Boolean operations,
duplication, semantic labels, hierarchy, or animation.

Every primitive becomes a neutral Entity backed by one Create operation and
one Transform operation. The background is an explicit first rectangle. Render
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

1. equivalent base, Artifact, namespace, producer identity, and decoding record
   produce the same Proposal;
2. proposal construction and dry-run preview do not mutate the base Revision;
3. background, ellipse, and rotated rectangle map only to existing Core
   operations;
4. POP primitive order is preserved exactly in the Render Stack;
5. acceptance creates one atomic Revision whose primitives remain separately
   editable;
6. forged Changes, malformed fields, unsupported shapes, non-canonical JSON,
   provenance drift, ID collisions, and missing Artifacts fail closed.
