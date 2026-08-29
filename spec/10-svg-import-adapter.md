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
range is `>=1.7.2,<2` in the optional `svg` extra. svgpathtools is MIT licensed
and is an Adapter implementation dependency, not a Core abstraction. Core
validation and evaluation remain importable without it.

Accepted `CreatePath` Operations contain SVG path data plus recorded bounds, so
an accepted Document remains evaluable and renderable without rerunning the
Adapter or accessing the source file.

Path bounds are computed by the shared `canonical_path_bounds` implementation
from the accepted `d` string. They are true axis-aligned curve bounds rather
than control-hull bounds and are normalized to `.12g` numbers.

## 3. Artifact Store

The reference in-memory Artifact Store imports immutable bytes and assigns:

```text
content_hash = sha256:<digest>
artifact_id  = artifact:<digest>
```

Artifact identity is derived from bytes only. The Store keeps the immutable
`ArtifactBlob` separately from one or more `ArtifactDescriptor` interpretations.
Kind, media type, provenance, and locator belong to the descriptor and do not
participate in identity. Repeated equivalent imports therefore deduplicate the
bytes without making the first descriptor authoritative. ID-only resolution
fails when multiple interpretations are present; resolving an accepted Document
Reference selects and verifies the exact descriptor and content hash.

`AdapterRequest` carries Artifact IDs, never caller-supplied byte snapshots. An
Adapter resolves those IDs through an `ArtifactResolver`; the reference Store
only returns accepted entries and verifies their hashes during resolution.

When accepted, the Artifact contributes a Document Reference containing its ID,
hash, media type, locator, kind, and provenance. Artifact bytes are not embedded
in the v0.1 Document. The Proposal declares the corresponding Artifact ID as
required. The Proposal Acceptor resolves the exact reference and verifies the
required-ID/reference set before policy enforcement or atomic commit.

## 4. Supported SVG subset

The Adapter supports:

- flat or nested `<g>` containers;
- `<rect>` without rounded corners;
- `<ellipse>`;
- `<path>`;
- inherited `fill`, `stroke`, and `stroke-width` presentation attributes;
- leaf-shape `opacity`;
- `none`, six-digit hex, and eight-digit hex colors;
- unitless numeric attributes.

The Adapter preserves source element order as render-stack order. Element IDs
become display names. SVM Entity and Operation IDs are deterministic from the
Artifact namespace and element index.

SVG initial values are preserved for supported style properties: `fill` is
black, `stroke` is `none`, `stroke-width` is `1`, and `opacity` is `1`.

## 5. Explicit rejections

The v0.1 Adapter rejects rather than approximates:

- DTD or entity declarations;
- documents larger than 5 MiB;
- transforms;
- CSS `style` attributes or stylesheets;
- unsupported elements;
- every attribute outside the explicit per-element whitelist;
- `opacity` on `<svg>` or `<g>` (group compositing is not leaf opacity);
- rounded rectangles;
- zero or negative rectangle dimensions and ellipse radii;
- units and unsupported color syntax;
- malformed or empty paths;
- non-Reference Artifacts and unsupported media types.

This is deliberate: a smaller honest import is preferable to a visually
plausible import with unrecorded semantic loss.

An accepted root `viewBox` is validated and recorded in Reference import
metadata. It is not silently discarded or treated as an Entity transform.

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
