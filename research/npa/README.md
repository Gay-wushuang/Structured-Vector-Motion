# NPA → SVM Research Spike

Status: **public-release acquisition audited; real-output fixture blocked**.

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

## Public-release acquisition audit

As of the survey on 2026-09-10, no official source repository, checkpoint,
inference command, serialized output example, or supplemental release was found
on the CVF record, the corresponding author's publication page, the complete
public repository listing for `github.com/sjtuchenye`, or GitHub repository
searches by the exact paper title, model name, authors, and venue. The author
page exposes only the paper link for NPA. Its GitHub link resolves to
`github.com/sjtuchenye`, whose public repository list contains no NPA release.

The official paper PDF was downloaded to a temporary audit directory and
verified as SHA-256
`8eea01c3cbefb60680fd1461ccdd552abf1bb23abf124fca9a8098dfb5fc35d9`.
Its extracted text contains no NPA source-code, project-page, checkpoint, or
supplemental-release URL. The PDF is not vendored because it is already
addressed by its official URL and is not an executable upstream release.

No NPA checkout or checkpoint therefore exists in the local research
workspace: there is no authentic repository to pull. The current POP fixture
also records the upstream example name but does not include the original input
image bytes required for a same-input comparison.

Therefore this spike deliberately does **not** invent an NPA JSON schema or call
a paper-derived mock object a real fixture.

Acquisition can resume without changing this boundary when one of the authors
or the user supplies an official repository URL, source archive, checkpoint, or
raw inference-output artifact. Before execution, record its license, immutable
source identity, checkpoint hash, environment, and inference command.

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
