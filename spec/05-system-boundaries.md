# SVM System Boundaries v0.1

Status: normative architectural boundary specification.

This document defines where product meaning lives and how external capabilities
may participate in Structured Vector Motion. It supplements the core model and
the Adapter/Proposal boundary.

## 1. Governing rule

> Adapters propose changes. Backends execute accepted definitions.

This rule prevents two forms of architectural contamination:

1. an external algorithm mutating an accepted Document without review,
   validation, or revision history;
2. an execution backend acquiring product semantics that belong in the SVM
   Document or operation-semantics version.

## 2. System map

```text
                       Structured Vector Motion
                                 |
          +----------------------+----------------------+
          |                                             |
       SVM Core                                  External Adapters
          |                                             |
 +--------+---------+                      +------------+------------+
 |        |         |                      |                         |
Document Revision  Runtime             Deterministic             AI / Research
Model    Model     Evaluator            Analysis                   Inference
 |        |         |                      |                         |
Entity   Revision  Immutable Values      OpenCV                     LayerPeeler
Operation Transaction Cache              Potrace                    SemLayer
Animation Proposal                        SVG analysis               LayerTracer
          |                                   |                         ...
          |                                   +------------+
          |                                                |
          +--------- Proposal Acceptor <---- Proposal + Artifacts
                         |
                     Transaction
                         |
                     New Revision

                 Document + Animation + time
                              |
                           Evaluator
                              |
                       Evaluated Scene
                              |
            +-----------------+-----------------+
            |                 |                 |
         Geometry          Rendering         Optimization
         Backends          Backends          Backends
            |                 |                 |
         Shapely          SVG Renderer         SciPy
      svgpathtools       Raster Renderer       diffvg
                        diffvg rasterizer
                              |
                           Renderer
                              |
                    +---------+---------+
                    |                   |
                   SVG             Raster Frames
                                            |
                                          FFmpeg
                                            |
                                   MP4 / WebM / GIF
```

Named third-party projects in this diagram are examples of implementations, not
dependencies required by SVM Core.

## 3. SVM Core

SVM Core owns the semantics required to interpret an accepted project.

```text
SVM Core
|- Document Model
|  |- Entity
|  |- Operation
|  `- Animation Definition
|- Revision Model
|  |- Revision
|  `- Transaction
|- Change Boundary
|  |- Proposal
|  `- Proposal Acceptor
`- Runtime
   |- Evaluator
   |- Immutable Values
   `- Cache
```

Core must remain usable without any particular research model, hosted service,
or third-party adapter. Removing an adapter must not make an already accepted
core Document uninterpretable, unless the Document explicitly declares a
separately versioned operation-semantics extension.

## 4. Adapter

An Adapter analyzes references or a Document snapshot and proposes a change to
the accepted program.

An Adapter may:

- inspect an isolated revision snapshot;
- consume content-addressed Artifacts;
- run deterministic analysis, optimization, or model inference;
- produce derived Artifacts for evidence and preview;
- return a Proposal containing one atomic Transaction.

An Adapter must not:

- receive authority to mutate a Revision Store;
- write directly into an accepted Document;
- insert Runtime Values into the evaluator cache;
- bypass constraints, permissions, or Proposal acceptance;
- make its private data format part of core Document semantics;
- rely on an unrecorded remote response after acceptance.

Examples include contour extraction, tracing import, layer decomposition, and
video-to-animation inference. Deterministic behavior does not turn an Adapter
into a Backend; its architectural role is determined by whether it proposes a
Document change or executes an already accepted definition.

## 5. Artifact

An Artifact is content-addressed external evidence or input. It is not an SVM
Runtime Value.

### 5.1 ReferenceArtifact

An accepted input snapshot, for example:

- source image or video;
- imported SVG;
- mask supplied by a user;
- fixed model output accepted as a new reference.

### 5.2 DerivedArtifact

An analysis or preview product, for example:

- contour set;
- segmentation mask;
- embedding;
- layer preview;
- optimizer checkpoint;
- rasterized Proposal preview.

Artifacts carry a content hash, media type, provenance, and optional locator.
The locator is not identity. A DerivedArtifact does not become part of the
accepted construction program merely because it exists.

## 6. Immutable Value

An Immutable Value is the formal result of SVM Evaluator execution against an
accepted Document under a recorded evaluation context.

```text
Accepted Operation
+ accepted inputs
+ semantics version
+ evaluation context
        |
        v
SVM Evaluator
        |
        v
Immutable Value
```

Artifacts and Immutable Values may contain identical bytes but remain different
architectural concepts. Artifact provenance comes from import or analysis;
Value provenance comes from evaluation of an accepted operation. An Adapter
must not promote an Artifact directly into the Runtime Value Store.

## 7. Proposal and Proposal Acceptor

A Proposal is an unaccepted change package tied to an exact base Revision. It
contains a Transaction, generator provenance, evaluation report, and optional
preview Artifacts.

The Proposal Acceptor is a Core service, not a passive data object. It is the
only boundary that may convert a Proposal into a committed Transaction and new
Revision. It verifies:

- base-revision compatibility;
- Document and operation semantics;
- constraints;
- Edit Permissions;
- accepted Artifact identity;
- atomic Transaction validity.

Unsupported policy semantics must fail closed.

## 8. Backend

A Backend implements a capability used while executing an already accepted SVM
definition. Its interface is capability-oriented rather than vendor-oriented.

Preferred abstractions include:

- `GeometryBackend`;
- `Rasterizer`;
- `Optimizer`;
- `MediaEncoder`.

Avoid core abstractions named after implementations such as `DiffvgBackend`.
One package may implement several capabilities—for example, diffvg may provide
both rasterization and optimization—without merging those interfaces.

A Backend may:

- execute registered Operation semantics;
- return deterministic results for a recorded context;
- use runtime caches;
- report failure or unsupported capability.

A Backend must not:

- allocate or reinterpret Entity identity;
- edit the Document or create a Revision;
- decide whether a Proposal should be accepted;
- introduce undocumented Operation meaning;
- read mutable external state not present in its evaluation context.

## 9. Evaluator

The Evaluator belongs to Runtime and orchestrates accepted Operation execution.
It resolves dependencies, selects capabilities, computes evaluation keys,
manages state and cache, and materializes Immutable Values.

The Evaluator owns orchestration semantics; a Backend owns only its capability
implementation. Backend selection must not change the meaning promised by the
active semantics version. Where implementations are not equivalent, engine and
implementation version must participate in the recorded evaluation context.

## 10. Animation and evaluated scenes

Animation is a declarative part of the Document:

```text
Animation Definition
|- Timeline
|- Tracks
|- Parameters
|- Keyframes
`- Expressions / Constraints
```

Frames are not stored animation semantics. They are sampled evaluation results:

```text
Document + Animation Definition + time t
                    |
                    v
               Evaluator(t)
                    |
                    v
             Evaluated Scene
                    |
                    v
                Renderer
                    |
                    v
                  Frame
```

Changing output frame rate changes sampling times, not the underlying Document
or the number of stored geometry copies.

## 11. Renderer and Exporter

A Renderer converts an Evaluated Scene into a visual representation such as SVG
or raster pixels. It does not evaluate animation policy, alter Entity identity,
or commit Documents.

The reference implementation of this boundary is specified in
`08-svg-renderer.md`.

An Exporter packages rendered or evaluated results for interchange. A media
encoder such as FFmpeg converts raster frames and audio into MP4, WebM, GIF, or
other media. Animation is therefore an input definition to evaluation, not an
output produced by FFmpeg.

## 12. Classifying a new dependency

Before integrating a library or repository, answer:

1. Does it propose a change to the Document? It is an **Adapter**.
2. Does it execute an accepted Operation capability? It is a **Backend**.
3. Does it convert an Evaluated Scene to a visual representation? It is a
   **Renderer**.
4. Does it package or encode results? It is an **Exporter/MediaEncoder**.
5. Does it transform external evidence without changing the Document? It is an
   **Artifact Processor**.

If its role cannot be stated unambiguously, do not integrate it yet. A single
third-party package may implement more than one role, but each role must cross a
separate capability boundary.

## 13. Initial dependency classification

| Role | Candidate implementations |
| --- | --- |
| Deterministic Adapters | OpenCV analysis, Potrace import, SVG analysis |
| AI / Research Adapters | layered_vectorization, LayerPeeler, SemLayer, LayerTracer, InternSVG |
| Geometry Backends | Shapely, svgpathtools |
| Optimization Backends | SciPy, diffvg optimizer |
| Rendering Backends | SVG renderer, raster renderer, diffvg rasterizer |
| Media encoding | FFmpeg |

This table records expected roles, not installation approval or Core
dependencies.
