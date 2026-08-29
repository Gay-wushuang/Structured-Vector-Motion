# Structured Vector Motion Core Model v0.1

Status: design baseline. The normative requirements live in
`01-invariants.md`.

## 1. Purpose

Structured Vector Motion (SVM) is a deterministic, non-destructive 2D
construction system. Its primary artifact is not an SVG or a timeline. It is a
computable construction program whose intermediate and final values can be
inspected, replaced, refined, scheduled, and animated.

The v0.1 milestone proves this loop:

```text
Document -> validate -> evaluate -> immutable values
         -> mutate upstream parameter -> invalidate dependants
         -> lazy reevaluate -> preserve entity identity
```

## 2. Project boundaries

An SVM project has four distinct layers:

| Layer | Responsibility | Stability |
| --- | --- | --- |
| Document | Portable artistic intent and construction definition | Stable |
| Revision Store | Transactions, branches, proposals and history | Evolving |
| Runtime State | Evaluation states, cache and materialized values | Disposable |
| Editor State | Selection, panels, viewport and temporary tools | Disposable |

Only the Document is part of the v0.1 interchange contract. Runtime state must
be reconstructible from it.

## 3. Document model

```text
SVM Document
|- metadata (schema_version, semantics_version)
|- references (content-addressed external artifacts)
|- entities (persistent semantic identity)
|- construction
|  |- operations (pure evaluation units)
|  |- dependencies (derived from input-slot references)
|  |- output bindings (entity properties -> output slots)
|  `- refinement stages
|- presentation (render stack and styles)
|- constraints
|- evaluation policies
|- edit permissions
`- animation
   |- content animation
   `- construction scheduling hints
```

Semantic hierarchy, render order, and refinement stage are independent
relations. No single tree is authoritative for all three.

## 4. Identity and values

SVM distinguishes:

- **Entity ID**: persistent semantic identity, such as `entity:head`.
- **Operation ID**: persistent identity of a construction step.
- **Output Slot ID**: stable logical output position, such as
  `op:head_refine.geometry`.
- **Value ID**: content hash of one immutable evaluation result.

Changing an input may replace the value stored at an output slot without
changing the output slot, operation, or entity IDs.

Entities bind properties to output slots; they do not own mutable geometry.
Structural operations may create new Entity IDs. Deletion uses tombstones in
revision history so historical references remain meaningful.

## 5. Construction graph

Operations form a directed acyclic computation graph. An operation declares
parameters and input output-slot references. Its dependencies are therefore
explicit and mechanically derivable.

Operation evaluation is pure:

```text
value = evaluate(operation_type, parameters, input_values, semantics_version)
```

The reference runtime tracks these evaluation states:

- `UNEVALUATED`: no successful value exists.
- `CLEAN`: materialized values match current inputs and parameters.
- `DIRTY`: reevaluation is required.
- `EVALUATING`: evaluation is in progress.
- `FAILED`: evaluation attempted and failed.
- `BLOCKED`: an upstream dependency has no usable result.

A dirty node may retain a stale last-successful value for display. Staleness is
an attribute of a materialized result, not a separate requirement to recompute.

Invalidation propagates only to transitive dependants. Evaluation is lazy and
may run at `INTERACTIVE`, `PREVIEW`, or `FINAL` quality.

## 6. Orthogonal control systems

- **Constraints** state what results must satisfy; they may be hard or soft.
- **Evaluation policies** state how a node participates in evaluation, for
  example frozen, preview-only, or final quality.
- **Edit permissions** state which actor may change which property.

The editor may present these together as a lock control, but their document
semantics remain separate.

## 7. Time

Graph dependency order expresses required causality, not presentation time.
Construction scheduling maps a valid DAG to a construction timeline. Content
animation independently animates entity properties, constraints, or bound
geometry. A single construction graph may have multiple schedules.

## 8. Proposals and revisions

External optimizers and AI adapters do not mutate the Document. They produce a
proposal against a base revision. Acceptance validates the base, checks
permissions and constraints, and commits one atomic transaction to a new
revision.

Revision Store behavior is intentionally outside the v0.1 Document schema, but
the identity and immutability rules in this specification are designed to make
it possible.

## 9. Explicit v0.1 exclusions

- collaborative editing;
- skeleton and deformation systems;
- video tracking;
- model invocation protocols;
- plugin ABI;
- advanced paint, filters, or materials;
- binary packaging and asset libraries.

