# Proposal Policy Enforcement v0.1

Status: normative supported policy subset.

## 1. Acceptance boundary

Proposal policy enforcement belongs to the Core Proposal Acceptor. Adapters may
report expected violations, but their report is not a substitute for enforcement
against the accepted base Document.

```text
Proposal + exact base Revision
             |
      derive Change intents
             |
  Constraints + Edit Permissions
             |
       allow or reject
             |
   atomic Transaction commit
```

## 2. Change intents

Every accepted Change has policy intent derived by its exact entry in the Core
Change Authority Registry. Change objects do not self-declare acceptance policy
through reflected methods.
The v0.1 intents are:

| Change | Action | Target | Parameter |
| --- | --- | --- | --- |
| `SetOperationParameterChange` | `set_parameter` | Operation ID | parameter name |
| `SplitEntityChange` | `split_entity` | source Entity ID | none |
| `AppendSceneFragmentChange` | `import_scene` | `document` | none |
| `ReplaceSceneFragmentChange` | `reconcile_scene` | `document` and each scoped Entity ID | none |
| `AppendReferencesChange` | `attach_analysis` | `document` | none |
| `PromoteComponentsChange` | `promote_components` | `document` | none |
| `ImportLayeredSceneChange` | `import_scene` | `document` | none |
| `ImportRasterLayerEvidenceChange` | `import_scene` | `document` | none |

An unknown Change always fails closed before policy enforcement because Core
cannot prove its executable semantics or intent.

## 3. PreserveParameter Constraint

```json
{
  "id": "constraint:head-radius",
  "type": "PreserveParameter",
  "operation": "op:head_base",
  "parameter": "rx"
}
```

This constraint rejects a Transaction containing a matching
`SetOperationParameterChange`. Unrelated parameter changes and structural changes
remain eligible for acceptance.

For `ReplaceSceneFragmentChange`, Core compares every owned old/new Operation.
Removing an Operation or changing a preserved parameter is rejected. Merely
re-emitting an equivalent parameter does not violate the constraint.
Before applying the replacement, Core also requires a contiguous Render Stack
scope and rejects scoped non-geometry bindings so reconciliation cannot reorder
external content or silently discard properties outside its ownership.

## 4. Deny Edit Permission

```json
{
  "id": "permission:no-head-split",
  "actor": "adapter:layer-analysis",
  "effect": "deny",
  "actions": ["split_entity"],
  "targets": ["entity:head"]
}
```

The rule matches actor, action, and target. `actor` and entries in `targets` may
use `*` as a wildcard. v0.1 supports deny rules only; allow-list composition and
rule precedence are intentionally deferred.

## 5. Validation and failure behavior

Policy definitions are semantically validated when the Document is loaded.
Unknown constraint types, effects, actions, missing targets, duplicate policy
IDs, and dangling constrained Operation IDs are invalid.

At acceptance time:

- a stale base Revision is rejected first;
- adapter-reported unresolved violations are rejected;
- required Artifact IDs and Transaction references are resolved and verified;
- Core derives intents and enforces accepted policy definitions;
- a violation creates no Revision;
- an unrelated valid Proposal may commit normally.

## 6. Deliberate limits

The supported subset does not yet include geometry bounds, containment,
alignment, soft scoring, property-level style permissions, allow-list rules, or
policy inheritance through Entity hierarchy. These require explicit semantics
and tests before use.
