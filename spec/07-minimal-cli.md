# SVM Minimal CLI v0.1

Status: reference command contract.

The CLI exposes the v0.1 core model for validation, inspection, deterministic
evaluation, atomic parameter mutation, and incremental reevaluation. It is a
JSON-oriented diagnostic interface, not an editor or stable automation API.

Run it from the repository root as:

```powershell
python -m svm <command>
```

Successful commands emit UTF-8 JSON to stdout and exit with code `0`. Validation
or command errors emit a JSON error object to stderr and exit with code `2`.

## Validate

```powershell
python -m svm validate examples/001-head-basic.svm.json
```

Validation runs both Draft 2020-12 JSON Schema validation and Registry-backed
semantic validation, including input/output signatures and bindings.

## Inspect

```powershell
python -m svm inspect examples/001-head-basic.svm.json
```

Inspection reports entities, topologically ordered operations, dependencies,
resolved input/output Value types, quality sensitivity, bindings, and render
stack. Dynamic outputs such as `SplitEntity` are reported after resolution.

## Evaluate

```powershell
python -m svm evaluate examples/001-head-basic.svm.json --quality FINAL
```

Evaluation reports state, evaluation key, effective quality, output names, and
Value IDs. Payloads are omitted by default and may be included for diagnostics:

```powershell
python -m svm evaluate examples/001-head-basic.svm.json --include-values
```

## Mutate

```powershell
python -m svm mutate examples/001-head-basic.svm.json `
  --set op:head_base.rx=0.42 `
  --output mutated.svm.json
```

Assignment values use JSON syntax. Multiple `--set` arguments form one atomic
Transaction. The source file is never overwritten implicitly. Without
`--output`, the resulting Document is emitted to stdout.

## Reevaluate

```powershell
python -m svm reevaluate examples/001-head-basic.svm.json `
  --set op:head_base.rx=0.42
```

`reevaluate` creates one runtime, performs an initial evaluation, applies
validated changes or explicit invalidations, and lazily evaluates again. Its
report distinguishes the invalidated subgraph from operations whose Value IDs
actually changed.

It may also force reevaluation without changing the Document:

```powershell
python -m svm reevaluate examples/001-head-basic.svm.json `
  --invalidate op:head_base `
  --from-quality PREVIEW `
  --quality FINAL
```

At least one `--set` or `--invalidate` is required because Runtime State is not
persisted in an SVM Document.

## Boundary

The CLI uses the same Document validator, Operation Registry, Evaluator,
Transaction, and Revision Store as library callers. It must not implement a
second interpretation of Operation semantics.

## Render SVG

```powershell
python -m svm render-svg examples/001-head-basic.svm.json `
  --output scene.svg
```

This command performs FINAL evaluation, builds an Evaluated Scene from accepted
geometry bindings and render-stack order, then invokes the SVG Renderer. It
requires an explicit output path and returns a JSON export summary.
