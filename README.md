# Structured Vector Motion

SVM is an experimental, non-destructive 2D construction computation model.
The current Document Format v0.1 is a development draft, not a frozen
compatibility contract. Until the first public format freeze, its schema may
change while `schema_version` remains `0.1`; every such change must update the
schema, specification, fixtures, and tests atomically.

The current v0.1 draft baseline contains:

- the core model, invariants, and Document Format specification;
- a Draft 2020-12 JSON Schema;
- a deliberately small deterministic reference evaluator;
- atomic Transactions and content-addressed Revision snapshots;
- `SplitEntity` and Golden Tests A/B;
- an Adapter/Proposal boundary with optimistic base-revision acceptance.
- quality-aware evaluation keys and Golden Test A.1;
- fail-closed Proposal handling for unsupported constraints and permissions;
- an explicit invariant coverage matrix.
- a formal system-boundary specification separating Adapters, Artifacts,
  Backends, Evaluator, Renderer, and Exporter.
- a semantics-versioned Operation Registry with explicit static and dynamic
  input/output signatures.
- a capability-oriented Geometry Backend boundary with deterministic Shapely
  Boolean operations and canonical polygon Values.

Run the golden test with:

```powershell
python -m unittest discover -s tests -v
```

Use the reference CLI with:

```powershell
python -m svm validate examples/001-head-basic.svm.json
python -m svm inspect examples/001-head-basic.svm.json
python -m svm evaluate examples/001-head-basic.svm.json --quality FINAL
python -m svm reevaluate examples/001-head-basic.svm.json --set op:head_base.rx=0.42
python -m svm render-svg examples/001-head-basic.svm.json --output scene.svg
```

See `spec/07-minimal-cli.md` for the command contract.

The reference SVG path is:

```text
Document -> FINAL Evaluator -> Evaluated Scene -> SVGRenderer -> SVG
```

See `spec/08-svg-renderer.md` for supported geometry and explicit limitations.

## Rendered showcase

The styled character example exercises authored presentation styles, clipping,
paths, render ordering, provenance, and deterministic SVG generation:

- `examples/004-styled-character.svm.json`
- `examples/rendered/004-styled-character.svg`

The test suite regenerates the SVG in memory and compares it byte-for-byte with
the checked-in artifact.

## Deterministic SVG import

The first external Adapter integration imports a deliberately strict SVG subset
through the Artifact and Proposal boundary:

```powershell
svm import-svg examples/005-empty-canvas.svm.json `
  examples/assets/001-import-source.svg `
  --namespace golden `
  --output imported.svm.json
```

Review the complete golden chain:

- `examples/assets/001-import-source.svg`
- `examples/imported/006-imported-source.svm.json`
- `examples/rendered/006-imported-source.svg`

See `spec/10-svg-import-adapter.md` for the supported subset and rejection rules.

## Deterministic geometry backend

The second external capability executes an accepted `BooleanGeometry` Operation
through the capability-oriented `GeometryBackend` interface:

```powershell
svm render-svg examples/007-boolean-geometry.svm.json `
  --geometry-backend shapely `
  --output boolean.svg `
  --view-box 0 0 180 140
```

The current Shapely implementation intentionally supports rectangles and
canonical polygon sets only. Review the golden result at
`examples/rendered/007-boolean-geometry.svg` and the contract in
`spec/11-geometry-backend.md`.

## Path to planar geometry

The curve-to-filled-area boundary is an explicit registered Operation:

```text
CreatePath -> path_data
PathToPolygon(tolerance, fill_rule) -> polygon_set
BooleanGeometry -> polygon_set
```

`tolerance` is recorded in Document coordinate units; open subpaths and arcs
fail closed in the initial subset; self-intersections are interpreted through
the recorded fill rule. See `spec/12-path-to-planar-geometry.md`, Golden D in
`examples/008-golden-d.svm.json`, its byte-stable rendered SVG, and
`tests/test_path_to_polygon_contract.py`.

## Deterministic bitmap trace

Golden E proves the first bitmap-to-planar vertical slice:

```powershell
svm trace-bitmap examples/005-empty-canvas.svm.json `
  examples/assets/003-bitmap-trace-source.png `
  --namespace fixture `
  --output traced.svm.json
```

The Adapter proposes an explicit `CreatePath -> PathToPolygon` chain and never
mutates the base Revision. The reference `potracer` engine is GPL-2.0-or-later
and is isolated in the optional `trace` dependency; see
`spec/13-bitmap-trace-adapter.md` for recorded parameters and license boundary.

Disconnected filled components are emitted as independent Entities and
Operation chains; nested holes remain owned by their enclosing component.
Golden F is recorded in `examples/imported/010-structured-trace.svm.json` and
`examples/rendered/010-structured-trace.svg`. See
`spec/14-structured-trace-components.md` for deterministic ordering and the
explicit limit between topology and semantic recognition.

An accepted trace can be compared with a replacement bitmap without immediate
mutation. `svm retrace-bitmap` returns a structured Entity diff by default; add
`--accept --output <document>` to commit it. Golden G demonstrates unchanged,
changed, added, and removed components while preserving matched Entity and
Operation IDs. Every proposed match exposes IoU, centroid, filled-area,
normalized contour, and composite scores. See
`spec/15-entity-reconciliation.md`.

## OpenCV artifact analysis

OpenCV analysis is intentionally separate from vectorization:

```powershell
svm analyze-bitmap examples/005-empty-canvas.svm.json source.png `
  --threshold 128 --derived-dir analysis-output
```

The v0.2 input subset is intentionally limited to 8-bit opaque grayscale PNGs,
so threshold samples do not depend on an implicit color conversion. It emits a
provenance-free content-addressed binary mask, canonical connected-component
JSON, and previewable structural candidates containing half-open pixel bounds,
pixel area, centroid, and a canonical component pixel-set digest. It creates no
Entity or Operation. Add `--accept --output` only to attach the analysis
evidence to a new Revision. See Golden H and
`spec/16-opencv-artifact-analysis.md`.

Promote selected accepted evidence regions without rerunning image analysis:

```powershell
svm promote-components examples/imported/012-opencv-analysis.svm.json `
  examples/derived/012-opencv-analysis/component-analysis.json `
  --candidate candidate:component-0001 `
  --candidate candidate:component-0002
```

The command previews deterministic neutral Region Entities. Add `--accept
--output promoted.svm.json` to create a Revision. Promotion reads only the
accepted canonical analysis JSON; it does not open the PNG, call OpenCV, create
vector geometry, or claim real-world semantic classes. See Golden I and
`spec/17-component-promotion.md`.

Accepted Promotion also materializes an independent Structural Relations graph.
Every Region gets an evidence-backed `derived-from` edge; candidates from the
same analysis get `bounds-contains` only for immediate nesting of their unequal
half-open bounds. These edges do not claim filled-region containment and do not
modify `parent_id`, Render Stack order,
construction, or animation. See Golden J and
`spec/18-structural-relations.md`.

## LayerPeeler research output

Golden K consumes a fixed, content-addressed snapshot of an external LayerPeeler
run. Its canonical manifest records the upstream commit, model identity,
checkpoint hash, seed, source Artifact, SVG hashes, and back-to-front layer
order. The Adapter never imports or executes the research model; accepted SVG
shapes are normalized through the existing SVG subset into ordinary Entities,
Operations, Styles, and Render Stack entries. See
`spec/19-layerpeeler-output-adapter.md` and
`tests/test_layerpeeler_output_adapter.py`.

## LayerD raster layer evidence

Golden L consumes a manifest-bound snapshot of LayerD's different output shape:
RGBA PNG layers plus canonical layer-analysis evidence. The Adapter records the
background/extraction sequence as evidence, not Render Stack order. It promotes
only neutral, non-rendered Region Entities; text/vector/image classifications
remain reviewable candidates in the Artifact and Proposal notes. Acceptance
reconstructs the exact Change from resolved bytes through the same Change
Authority Registry used by Golden K, without adding a LayerD branch to
`ProposalAcceptor`. See `spec/20-layerd-output-adapter.md` and
`tests/test_layerd_output_adapter.py`.

## Motion Semantics

Golden M is the first content-motion slice. A versioned Track animates
`op:moving-rectangle.x` over an integer 1000-tick-per-second Timebase, producing
checked-in deterministic SVG Frames at 0, 0.5, and 1 second. Entity, Operation,
Track, and Keyframe identity stay stable; editing the middle Keyframe invalidates
only affected sampling ticks, while an independent static rectangle reuses the
same immutable Value across time. See `spec/21-motion-semantics.md`,
`examples/017-motion-rectangle.svm.json`, and `tests/test_motion.py`.

Golden N connects Motion to persistent editing. `SetKeyframeValueChange` commits
one numeric Keyframe value as an atomic Revision without changing Track,
Keyframe, Operation, or Entity identity. Revision transition keeps unaffected
Frames and shared immutable Values, invalidates only the changed interpolation
domain, and leaves the prior Revision independently evaluable and recoverable by
Undo. See `spec/22-motion-revisions.md` and `tests/test_motion_revision.py`.

## Anchored Regeneration

Golden O treats a Proposal as a candidate future rather than accepted history.
An `AnchoredRegenerationContract` binds candidates to one immutable base
Revision, protects exact ChangeAuthority targets, and allowlists exact downstream
impacts. Core computes impact from the executable registered Changes instead of
trusting generator metadata. Multiple accepted candidates can therefore become
sibling Revision children without mutating their common base or each other. See
`spec/23-anchored-regeneration.md`,
`examples/018-anchored-regeneration.svm.json`, and
`tests/test_anchored_regeneration.py`.

Contracts are validated against their exact base snapshot. Registered actions,
Operation parameters, Entities, Tracks, and Keyframes must exist. Motion impact
uses `(set_keyframe_value, Track ID, Keyframe ID)`, allowing one Keyframe without
implicitly authorizing every Keyframe on the Track.

The first user-facing Golden O interaction study lives in
`prototype/anchored-regeneration/`. It demonstrates a strict red-to-orange edit,
locked geometry/face targets, exact Highlight and Shadow regeneration scope,
deterministic A/B/C pending candidates, impact inspection, and acceptance into a
visible child Revision. The prototype is browser-only Editor State and does not
add UI fields to the SVM Document or invoke an AI model.

## Development

Install the project and development tools in editable mode:

```powershell
python -m pip install -e ".[dev,geometry,svg,trace,analysis]"
```

Run the same checks used by CI:

```powershell
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m unittest discover -s tests -v
svm validate examples/001-head-basic.svm.json
```

CI runs this sequence on Windows and Linux with Python 3.11 and 3.12.

The implementation proves isolated DAG invalidation, lazy reevaluation,
immutable content-addressed outputs, stable and structural entity identity,
atomic revision creation, undo by parent revision, and Proposal isolation. It is
not yet an editor or production renderer.

See `spec/04-invariant-coverage.md` for the distinction between implemented,
fail-closed, and specification-only normative behavior.
