# NPA → SVM Research Spike

Status: **contract survey complete; real-output fixture blocked**.

The target is Ye Chen et al., *Editable Image Geometric Abstraction via Neural
Primitive Assembly* (ICCV 2023), DOI `10.1109/ICCV51070.2023.02149`.

## Verified model boundary

The paper describes image-to-set prediction, not a drawing sequence. Each
predicted element contains:

- a primitive assignment over triangle, rectangle, circle, and semicircle;
- seven affine parameters: rotation, x/y scale, x/y translation, x/y shear;
- point-wise offsets with `2t` values for a primitive with `t` parametric points;
- an RGB color;
- primitive-type probabilities during training, with highest-probability type
  selected during inference.

This is complementary to Golden P: NPA predicts an unordered geometric
assembly, while the integrated POP baseline records ordered primitive
construction.

Primary source: [ICCV 2023 paper](https://openaccess.thecvf.com/content/ICCV2023/papers/Chen_Editable_Image_Geometric_Abstraction_via_Neural_Primitive_Assembly_ICCV_2023_paper.pdf).

## Missing release evidence

As of the survey on 2026-09-10, no official source repository, checkpoint,
inference command, serialized output example, or supplemental release was found
on the CVF record, the authors' public pages, or indexed code listings. No NPA
checkout or checkpoint exists in the local research workspace. The current POP
fixture also records the upstream example name but does not include the original
input image bytes required for a same-input comparison.

Therefore this spike deliberately does **not** invent an NPA JSON schema or call
a paper-derived mock object a real fixture.

## Candidate SVM mapping (not yet normative)

| NPA evidence | Existing SVM destination | Status |
| --- | --- | --- |
| circle | `CreateEllipse` | exact subset |
| rectangle | `CreateRectangle` + `Transform` | likely |
| triangle | `CreatePath` | requires output coordinate contract |
| semicircle | `CreatePath` | requires arc/point-offset contract |
| affine parameters | `Transform.matrix` | requires order/normalization contract |
| RGB | `presentation.styles.fill` | likely |
| type probabilities | Artifact evidence only | do not materialize as semantics |
| point offsets | Artifact evidence or explicit path | unresolved |
| set order | no implied Render Stack | unresolved |

## Fixture admission gate

A future frozen fixture must contain the exact input-image Artifact, producer
commit, checkpoint hash, environment/configuration, raw unmodified output,
coordinate convention, primitive ordering/compositing rule, and deterministic
render evidence. Until those exist, an `NPAOutputAdapter` would encode guesses
and must not be added.
