# Deterministic SVG Import Adapter v0.1

Status: first external Adapter integration and reference Artifact pipeline.

## 1. Purpose

This milestone proves the full external change boundary:

```text
SVG bytes
   |
ReferenceArtifact + SHA-256
   |
SVGImportAdapter
   |
Proposal + AppendSceneFragmentChange
   |
Proposal Acceptor + policies
   |
Transaction -> Revision
   |
Registry -> Evaluator -> EvaluatedScene -> SVGRenderer
```

The Adapter never mutates the base Document or writes Runtime Values. Accepted
geometry is represented only through registered SVM Operations.

## 2. External dependency

The Adapter uses [svgpathtools](https://pypi.org/project/svgpathtools/) to parse
and validate SVG path data and calculate path bounds. The declared compatibility
range is `>=1.7.2,<2`. svgpathtools is MIT licensed and is an Adapter
implementation dependency, not a Core abstraction.

Accepted `CreatePath` Operations contain SVG path data plus recorded bounds, so
an accepted Document remains evaluable and renderable without rerunning the
Adapter or accessing the source file.

## 3. Artifact Store

The reference in-memory Artifact Store imports immutable bytes and assigns:

```text
content_hash = sha256:<digest>
artifact_id  = artifact:<digest>
```

Snapshots carry kind, media type, bytes, and provenance. Repeated equivalent
imports deduplicate by content identity. Retrieval verifies the content hash.

When accepted, the Artifact contributes a Document Reference containing its ID,
hash, media type, locator, kind, and provenance. Artifact bytes are not embedded
in the v0.1 Document.

## 4. Supported SVG subset

The Adapter supports:

- flat or nested `<g>` containers;
- `<rect>` without rounded corners;
- `<ellipse>`;
- `<path>`;
- inherited `fill`, `stroke`, `stroke-width`, and `opacity` presentation
  attributes;
- `none`, six-digit hex, and eight-digit hex colors;
- unitless numeric attributes.

The Adapter preserves source element order as render-stack order. Element IDs
become display names. SVM Entity and Operation IDs are deterministic from the
Artifact namespace and element index.

## 5. Explicit rejections

The v0.1 Adapter rejects rather than approximates:

- DTD or entity declarations;
- documents larger than 5 MiB;
- transforms;
- CSS `style` attributes or stylesheets;
- unsupported elements;
- rounded rectangles;
- units and unsupported color syntax;
- malformed or empty paths;
- non-Reference Artifacts and unsupported media types.

This is deliberate: a smaller honest import is preferable to a visually
plausible import with unrecorded semantic loss.

## 6. Scene Fragment transaction

`AppendSceneFragmentChange` atomically appends imported Entities, Operations,
Bindings, render entries, Styles, and accepted References. Validation occurs on
the complete candidate Document before Revision commit.

Its policy intent is:

```text
action = import_scene
target = document
```

Edit Permissions may therefore deny SVG import for a specific Adapter actor or
for all actors.

## 7. CLI

```powershell
svm import-svg examples/005-empty-canvas.svm.json `
  examples/assets/001-import-source.svg `
  --namespace golden `
  --output imported.svm.json
```

The output is a new accepted-style Document snapshot; the source base Document
is not overwritten. It can be rendered through the ordinary command:

```powershell
svm render-svg imported.svm.json `
  --output imported.svg `
  --view-box 0 0 200 160
```

## 8. Golden artifacts

- `examples/assets/001-import-source.svg` — external input Artifact;
- `examples/imported/006-imported-source.svm.json` — accepted SVM Document;
- `examples/rendered/006-imported-source.svg` — SVM-rendered result.

Tests reproduce both accepted Document content and rendered SVG byte-for-byte.

