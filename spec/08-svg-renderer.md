# Evaluated Scene and SVG Renderer v0.1

Status: reference rendering contract.

## 1. Pipeline

The SVG renderer consumes an Evaluated Scene, never a mutable Document or an
external Adapter result directly.

```text
Accepted Document
        |
FINAL Evaluator
        |
Immutable Geometry Values
        |
Evaluated Scene
        |
SVGRenderer
        |
SVG document
```

`build_evaluated_scene()` resolves geometry bindings for entities in render-stack
order after FINAL evaluation. Each scene entity records its Entity ID, display
name, Geometry Value ID, and immutable geometry payload.

## 2. Evaluated Scene

An Evaluated Scene is disposable Runtime output. It is not serialized into the
SVM Document and does not create a Revision. Its entity order is exactly the
Document render stack.

Every rendered entity must have one valid geometry binding and a successfully
materialized output. Semantic parents omitted from the render stack do not appear
in the scene.

## 3. Supported geometry subset

The v0.1 renderer supports:

- ellipse;
- rectangle;
- affine transform;
- `ConvertToPath` and `RefineBezier` wrappers;
- clipping.

Ellipse-to-path lowering uses four deterministic cubic Bezier segments.
Rectangle-to-path lowering uses line commands. Transforms remain SVG groups with
matrix transforms. Clip geometry is emitted under `<defs><clipPath>`.

The current reference `RefineBezier` value is a structural wrapper and does not
yet change control points; the renderer lowers its accepted source as a path.

## 4. Structural selectors

`SplitEntity` selectors are evaluated upstream into ordinary Clip geometry. The
Renderer therefore does not own selector semantics and renders split children
through the same Clip path as any other evaluated geometry.

## 5. Determinism and provenance

Equivalent Evaluated Scenes and render options must produce equivalent SVG text.
The SVG records:

- Document ID and evaluation quality on the root;
- Entity ID, name, and Geometry Value ID on each entity group;
- render-stack order through element order.

Generated clip IDs are deterministic within one render. Numeric output uses a
stable compact representation.

## 6. Presentation limits

The Renderer applies per-Entity Document Style for fill, stroke, stroke width,
and opacity. Explicit render options provide fallbacks for entities without a
Style plus output dimensions and viewBox. These options affect export but do not
mutate the Document.

The checked-in `examples/rendered/004-styled-character.svg` is a byte-for-byte
visual golden generated from `examples/004-styled-character.svm.json`.

## 7. CLI

```powershell
svm render-svg examples/001-head-basic.svm.json `
  --output scene.svg `
  --width 1024 `
  --height 1024 `
  --view-box -2 -2 4 4
```

`render-svg` always evaluates at FINAL quality and requires an explicit output
path. It emits a JSON export summary to stdout.
