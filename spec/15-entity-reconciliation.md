# Trace Entity Reconciliation v0.1

## Status

This specification defines previewable reconciliation between an accepted set
of trace Entities and a newly traced bitmap. Golden Test G is normative.

## Boundary

Reconciliation is an Adapter Proposal, never an implicit evaluation behavior:

```text
accepted trace Entity scope + new content-addressed PNG
-> trace components
-> deterministic matching
-> ProposalPreview
-> explicit Accept / Reject
-> atomic ReplaceSceneFragmentChange
```

The request MUST explicitly scope the existing Entities. The Adapter MUST reject
missing Entities, shared trace Operations, non-`CreatePath -> PathToPolygon`
chains, and duplicate scope IDs.

## Matching v0.1

The matcher identity is `svm-bounds-iou-greedy@0.1`. It computes axis-aligned
canonical path-bounds intersection-over-union for every old/new pair, removes
pairs below the recorded `match_iou_threshold`, then greedily selects disjoint
pairs by `(descending score, old Entity ID, proposed component index)`.

The threshold MUST be a finite number in `[0, 1]` and MUST be recorded in
generator provenance. Bounds IoU is deliberately conservative and explainable;
it is not semantic recognition or a claim that two shapes denote the same
real-world object.

## Identity and diff status

- `unchanged`: matched; path parameters and planar parameters are equivalent.
- `changed`: matched; Entity ID and both Operation IDs are preserved while
  recorded geometry or planar parameters change.
- `added`: unmatched proposed component; receives a new content-derived ID.
- `removed`: unmatched scoped Entity; its owned chain is removed on acceptance.

Every Proposal MUST contain `ProposalPreview.entity_diffs` with status, old and
proposed Entity IDs, match score when applicable, and before/after bounds. The
preview MUST also expose the proposed fragment Render Stack.

Matching preserves Entity metadata and Style. Acceptance replaces the scoped
fragment atomically and appends the new Artifact reference. Operations owned by
the scope MUST NOT have consumers or bindings outside the scope; such a Proposal
fails rather than deleting external dependencies.

## CLI

`svm retrace-bitmap` previews by default. It writes no Document until `--accept`
is supplied; `--accept` requires `--output`. This mirrors the API's explicit
`ProposalAcceptor` boundary.

## Golden Test G

Golden G begins with Golden F's three Entities and retraces a bitmap containing:

1. one unchanged component;
2. one spatially matched but changed component;
3. one removed component;
4. one new component.

It verifies preview counts, identity preservation, atomic acceptance, removed
ownership cleanup, new identity allocation, Artifact verification, stable SVG,
stale-Proposal conflict behavior, and `reconcile_scene` Edit Permission.
