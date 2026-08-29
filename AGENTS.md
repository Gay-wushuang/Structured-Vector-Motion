# AGENTS.md

This file defines repository-level instructions for contributors and coding
agents working on Structured Vector Motion (SVM).

## Project purpose

SVM is a deterministic, non-destructive 2D construction computation model.
Its primary artifact is a computable construction program, not an SVG, scene
graph, editor UI, or animation timeline.

The v0.1 objective is to prove this loop:

```text
Document
-> validate
-> evaluate
-> immutable content-addressed outputs
-> mutate an upstream parameter
-> invalidate only transitive dependants
-> lazy reevaluate
-> preserve entity identity
```

Do not expand the project into a general vector editor before this core loop,
transactions, revisions, and structural identity changes are well specified and
tested.

## Sources of truth

Read these files before changing core behavior:

1. `spec/01-invariants.md` — normative requirements.
2. `spec/00-svm-core-model.md` — architectural model and boundaries.
3. `spec/05-system-boundaries.md` — system roles and prohibited coupling.
4. `spec/06-operation-registry.md` — Operation semantic signatures and dispatch.
5. `spec/07-minimal-cli.md` — reference CLI contract.
6. `spec/08-svg-renderer.md` — Evaluated Scene and SVG rendering contract.
7. `spec/09-policy-enforcement.md` — supported Proposal policy subset.
8. `spec/10-svg-import-adapter.md` — deterministic external Adapter contract.
9. `spec/11-geometry-backend.md` — deterministic Geometry Backend contract.
10. `spec/12-path-to-planar-geometry.md` — PathToPolygon normative contract.
11. `spec/13-bitmap-trace-adapter.md` — deterministic bitmap tracing boundary.
12. `spec/14-structured-trace-components.md` — deterministic component decomposition.
13. `spec/15-entity-reconciliation.md` — previewable re-trace identity matching.
14. `spec/16-opencv-artifact-analysis.md` — deterministic raster analysis evidence.
15. `examples/001-head-basic.svm.json` — current example Document.
16. `tests/test_golden_a.py` — executable expectations.

If code and an invariant disagree, preserve the invariant or explicitly update
the specification and tests in the same change. Do not silently reinterpret an
invariant in implementation code.

## Architectural boundaries

Keep these layers separate:

```text
SVM Project
|- Document          portable artistic intent
|- Revision Store    transactions, proposals, branches
|- Runtime State     evaluation state, cache, materialized values
`- Editor State      selection, viewport, panels, temporary tools
```

Only `Document` is part of the v0.1 interchange contract. Runtime and editor
state must not define document meaning and must be safe to discard.

Do not collapse these concepts:

- Document is not the entire project state.
- Edit Log is not the Construction Program.
- Revision Graph is not Undo/Redo.
- Operation DAG order is not presentation time.
- Entity ID is not geometry identity.
- Output Slot ID is not Immutable Value ID.
- Constraint, Evaluation Policy, and Edit Permission are distinct systems.
- Semantic hierarchy, render order, and refinement stage are orthogonal.
- Construction animation and content animation are distinct.
- Artifact is external evidence; Immutable Value is an accepted evaluation
  result.
- Adapter proposes Document changes; Backend executes accepted definitions.
- Animation is a Document definition; Frame is a sampled render result.

## Core invariants for implementation

- Operation evaluation must be pure and must not mutate input values.
- Equivalent recorded inputs and semantics must produce equivalent outputs.
- A quality-sensitive operation must include requested quality in its evaluation
  key. PREVIEW output must not satisfy a FINAL request.
- Record randomness, quality, engine/semantics version, and external artifacts
  whenever they can affect a result.
- Accepted external resources must be content-addressed. A path or URI is only a
  locator.
- Entity identity must survive geometry, style, render-order, and evaluation
  changes.
- Structural operations that create semantic objects must allocate new Entity
  IDs. Never silently reuse an existing ID for a split result.
- Operation IDs and Output Slot IDs remain stable across reevaluation.
- Immutable Value IDs are canonical content hashes.
- Invalidating one operation must affect only that operation and its transitive
  dependants.
- A stale previous result may be displayed but must never be represented as
  current or used for final export.
- User-visible multi-record intent must eventually commit as one atomic
  transaction.
- External optimizers and AI adapters produce Proposals; they do not directly
  mutate an accepted Document.

## Evaluation model

The current runtime states are:

```text
UNEVALUATED
CLEAN
DIRTY
EVALUATING
FAILED
BLOCKED
```

A dirty node may retain a stale last-successful value. Treat stale result
availability separately from the requirement to reevaluate.

Supported quality levels are:

```text
INTERACTIVE
PREVIEW
FINAL
```

Evaluation should be lazy. Interactive editing must not require eager full-graph
or final-quality recomputation.

## Development workflow

Use the standard library unless a dependency provides clear value required by a
current milestone. Do not add PySide6, diffvg, AI models, video tooling, or
research repositories to prove a core-model behavior.

For every core semantic change:

1. Identify the governing invariant.
2. Add or update a minimal example Document.
3. Add a focused executable test.
4. Implement the smallest behavior that satisfies it.
5. Run the full test suite.
6. Update the specification when public semantics changed.

Prefer small vertical slices over broad scaffolding. Keep the reference
evaluator readable and intentionally small; it exists to expose specification
problems, not to become a production renderer prematurely.

## Commands

Run all tests from the repository root:

```powershell
python -m unittest discover -s tests -v
```

Run formatting, lint, and type checks before completing a code change:

```powershell
python -m ruff format --check .
python -m ruff check .
python -m pyright
```

Install declared development tooling with:

```powershell
python -m pip install -e ".[dev,geometry,svg,trace,analysis]"
```

Do not weaken Ruff or Pyright configuration to hide a local error. Narrow types
or correct the implementation. Pyright checks the production `svm` package;
tests are behavior-checked by the full unittest suite.

Compile-check Python sources when appropriate:

```powershell
python -m compileall -q svm tests
```

Generated `__pycache__` and `*.pyc` files are ignored and must not be committed.

## Code conventions

- Target the Python version already available in the workspace; currently the
  code is compatible with Python 3.12.
- Use type hints for public functions and core data structures.
- Prefer dataclasses and enums for explicit runtime concepts.
- Keep serialized names stable and human-readable.
- Canonicalize serialized content before hashing it.
- Avoid global mutable evaluator state.
- Raise explicit document/validation errors instead of relying on assertions for
  user-provided data.
- Keep operation implementations deterministic and isolated.
- Do not bind core entities to UI framework objects.
- Do not introduce filesystem, network, clock, or UI reads inside operation
  evaluation.

## Testing requirements

Tests must verify externally meaningful semantics, not implementation details.
At minimum, preserve Golden Test A:

- changing `op:head_base.rx` dirties only the head-dependent chain;
- the independent shield remains clean and retains its Value ID;
- a stale head result remains available until reevaluation;
- reevaluation produces a new head Value ID;
- the Head Entity ID remains unchanged;
- repeated equivalent evaluation produces the same content hash.

Golden Test B is implemented and must remain preserved:

```text
SplitEntity(Head) -> Head parent + new Face + new Hair
```

It exercises structural identity, atomic transactions, revisions, render stack
changes, bindings, undo, and loading the old revision. Do not regress
`SplitEntity` into an in-place geometry mutation.

## Near-term roadmap

Work in this order unless the user explicitly changes priorities:

Completed baseline:

1. `02-document-format-v0.1.md`.
2. `schema/svm-document-v0.1.schema.json`.
3. Transaction and Revision Store minimum model.
4. `SplitEntity` semantics and Golden Test B.
5. Adapter/Proposal boundary and optimistic acceptance.

Next milestones:

1. Extend Style beyond flat fill/stroke only when a concrete rendering use case
   requires it.
2. Add geometry-aware constraints such as bounds preservation through explicit
   evaluated semantics.
3. Introduce the first deterministic external Adapter without allowing its data
   model into Core. SVG Import now proves this boundary; future Adapters must
   follow the same Artifact/Proposal/Transaction pattern.
4. Introduce the first deterministic capability Backend. Shapely-backed planar
   Boolean geometry now proves accepted Operation execution without Proposal or
   Revision coupling.
5. Implement Path-to-planar conversion only through explicit `PathToPolygon`.
   Golden D now covers Bézier flattening, canonical polygon output, Boolean
   topology, tolerance invalidation, and final SVG. Future path work must retain
   its explicit Document parameters and fail-closed subset.
6. Bitmap Trace Adapter and Golden E now prove PNG Artifact -> Proposal ->
   CreatePath -> PathToPolygon -> canonical polygon_set -> stable SVG. Keep
   third-party tracing engines optional and outside Core.
7. Structured Trace Components and Golden F now split disconnected filled
   components into independent Entities while retaining nested hole contours in
   their owning Entity. Do not confuse this topology with semantic recognition.
8. Trace Entity Reconciliation and Golden G now preview and atomically apply
   unchanged, changed, added, and removed components while preserving matched
   Entity and Operation identity. The v0.2 matcher exposes IoU, centroid, area,
   contour, and composite scores; matching remains explicit and conservative.
9. OpenCV Artifact Analysis and Golden H now accept only 8-bit opaque grayscale
   PNGs and produce provenance-free content-addressed binary masks, canonical
   component statistics/digests, and structural candidates without creating
   Entities. Candidate promotion remains a later explicit Proposal.

UI, automatic vectorization, diffvg optimization, AI adapters, and video support
come after the core computation and revision models are proven.

## Scope discipline

When a requested feature conflicts with the current model, surface the conflict
and update the specification deliberately. Do not hide architectural exceptions
behind adapters or convenience fields.

Avoid speculative abstractions. Add an operation, field, state, or subsystem only
when a documented use case or executable test requires it.
