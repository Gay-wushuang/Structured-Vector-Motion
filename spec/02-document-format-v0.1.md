# SVM Document Format v0.1

Status: normative interchange format for the v0.1 reference implementation.

## 1. Serialization

An SVM Document is UTF-8 JSON. Object member order has no meaning. Array order
has meaning only where this specification says it does, notably the render
stack and construction scheduling hints.

Every document declares:

```json
{
  "schema_version": "0.1",
  "semantics_version": "svm-core-0.1",
  "document_id": "document:example"
}
```

`schema_version` describes representation. `semantics_version` selects the
meaning of registered operation types.

## 2. Identifiers

IDs are non-empty strings scoped by kind:

- `document:*` — Document identity;
- `entity:*` — persistent semantic entities;
- `op:*` — construction operations;
- `artifact:*` — accepted external artifacts.

An output slot is addressed as `<operation-id>.<output-name>`. A materialized
immutable value is not serialized into an output binding; it is identified at
runtime by `sha256:<canonical-content-hash>`.

## 3. Top-level members

### `references`

Accepted external inputs. Each reference includes `id`, `uri`, `content_hash`,
`media_type`, and `import_metadata`. The URI is a locator and may drift; the
hash identifies the accepted bytes.

### `entities`

Persistent semantic objects. Each entity has `id` and `name`; `parent_id` is
optional. Entity order has no semantic meaning. Parent relations must be
acyclic and parent IDs must resolve.

### `construction.operations`

A list of pure computation nodes. Each operation has:

```json
{
  "id": "op:head_path",
  "type": "ConvertToPath",
  "inputs": {"geometry": "op:head_base.geometry"},
  "parameters": {}
}
```

Input slot references define graph dependencies. The graph must be acyclic.
Input and output names and Value types are defined by the selected semantics
version's Operation Registry. See `06-operation-registry.md`.

### `construction.output_bindings`

Bindings associate an entity property with a logical output slot. The tuple
`(entity, property)` must be unique.

### `construction.refinement_stages`

Ordered names used to classify refinement. Stage order is independent of
semantic hierarchy and render order.

### `presentation.render_stack`

Back-to-front Entity IDs that currently contribute to presentation. Semantic
parent entities need not occur in the stack when their children represent the
rendered decomposition.

### `presentation.styles`

Styles are independent presentation records keyed by Entity ID. v0.1 supports
`fill`, `stroke`, `stroke_width`, and `opacity`. Colors are `none`, six-digit hex,
or eight-digit hex. Missing Entity styles use Renderer fallback options.

Style identity does not define Entity identity, semantic hierarchy, refinement
stage, or geometry Value identity.

### Control and animation collections

`constraints`, `evaluation_policies`, and `edit_permissions` are separate
collections. `animation.content` and
`animation.construction_scheduling_hints` remain separate time systems.

## 4. Structural split semantics

`SplitEntity` is the first v0.1 structural operation. Acceptance occurs through
one atomic transaction that:

1. preserves the source entity as a semantic parent;
2. creates new child Entity IDs;
3. appends one `SplitEntity` construction operation;
4. binds each child to a distinct output slot;
5. replaces the rendered source occurrence with the children in declared order.

The source geometry binding remains attached to the source entity. It is not
silently transferred to a child. Loading the parent revision restores the exact
pre-split Document.

The reference `SplitEntity` evaluator creates deterministic derived geometry
values using recorded `bounds_fraction` selectors. Each selector is an
axis-aligned rectangle expressed as normalized fractions of source geometry
bounds. Evaluation produces Clip geometry and does not claim to perform semantic
image segmentation. New children inherit the source presentation Style when one
exists. Geometry values do not contain Entity IDs; ownership and semantic
identity remain in entity-to-output bindings, allowing multiple entities to
share identical immutable geometry values.

## 5. Canonicalization

Revision and value hashes use JSON encoded with sorted keys, no insignificant
whitespace, UTF-8, and preserved array order. Runtime caches, evaluation state,
editor state, and stale values are excluded from the Document.

## 6. Validation requirements

A conforming validator rejects at least:

- missing or unsupported versions;
- duplicate Entity or Operation IDs;
- dangling entity parents, input slots, bindings, or render entries;
- unregistered Operation types, invalid parameters, or signature mismatches;
- references to output names not declared by static or dynamic signatures;
- duplicate bindings for one entity property;
- cyclic construction or entity graphs;
- malformed accepted-reference hashes.
