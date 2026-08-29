# Structured Vector Motion

SVM is an experimental, non-destructive 2D construction computation model.
The current v0.1 baseline contains:

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

## Development

Install the project and development tools in editable mode:

```powershell
python -m pip install -e ".[dev,geometry,svg]"
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
