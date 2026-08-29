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
chains, duplicate scope IDs, and scoped Entities with any non-geometry output
binding. The v0.1 reconciler owns only geometry; it MUST NOT delete or guess how
to migrate mask, material, anchor, or other properties.

Scoped Entities MUST occupy one contiguous interval in the accepted Render
Stack. Core acceptance rejects a non-contiguous scope before mutation because
collapsing separated slots into one replacement fragment would reorder external
Entities. Cross-layer reconciliation requires a future preserve-slot or render-
anchor contract.

## Matching v0.3

The matcher identity is `svm-multifeature-greedy@0.3`. Every old/new pair
receives four independently reviewable scores in `[0, 1]`:

- `iou`: axis-aligned canonical path-bounds intersection-over-union;
- `centroid`: sampled fill-rule-aware area centroid distance normalized by the union
  bounds diagonal;
- `area`: smaller/larger sampled fill-rule-aware area ratio;
- `contour`: translation/scale-normalized symmetric Chamfer similarity.

The descriptor receives the accepted old and proposed new `PathToPolygon.fill_rule`.
For the supported non-intersecting trace contour-tree subset, sampled rings are
combined according to `nonzero` or `evenodd` fill semantics. Area and centroid
therefore describe filled shape rather than raw path winding.

Every scoped and proposed path MUST remain a forest of closed, simple rings
whose pairs are either strictly nested or disjoint. Self-intersection, crossing
or touching rings, open subpaths, and topology that cannot be verified fail
closed before matching. General authored path topology requires future analysis
of evaluated canonical `polygon_set` values and is outside this matcher version.

Filled-area analysis samples each subpath at 128 equally spaced arc-length
positions. Contour comparison samples the whole compound path at 128 equally
spaced arc-length positions, independent of SVG segment boundaries. Descriptor
construction rejects paths above 10,000 segments. These limits and sampling
counts are part of matcher semantics.

Exact pairwise topology verification is bounded to 512 segments. Individual
`Line`, `QuadraticBezier`, and `CubicBezier` segments use analytic injectivity
and self-intersection tests; other curve types fail closed because their
simplicity is not proven. A larger path is rejected rather than entering an
unbounded quadratic check. The limit is recorded in generator provenance.

The fixed area-degeneracy epsilon is `1e-12` square document units. The fixed
endpoint-parameter comparison epsilon used by topology validation is `1e-12`.
Both constants are recorded in generator provenance and belong to
`svm-multifeature-greedy@0.3` semantics.

Contour normalization translates the bounds center to the origin and divides
both axes by the same `max(width, height)` scale. It removes translation and
uniform size while preserving aspect ratio; X and Y MUST NOT be normalized
independently.

The composite score is:

```text
0.35 * iou + 0.20 * centroid + 0.15 * area + 0.30 * contour
```

Weights, sampling limits, matcher identity, and `match_score_threshold` MUST be
recorded in generator provenance. The default threshold is `0.65`; the old
`match_iou_threshold` option fails with a migration error because its IoU-only
meaning is not equivalent to a composite-score threshold. The
matcher removes pairs below the composite threshold, then greedily selects
disjoint pairs by `(descending composite, old Entity ID, proposed component
index)`.

The four feature scores are canonicalized before the displayed composite is
computed and canonicalized, so the preview is exactly reproducible from its
displayed components. All five scores MUST appear in `ProposalPreview`. This matcher remains a
conservative geometric heuristic, not semantic recognition or proof that two
shapes denote the same object.

## Identity and diff status

- `unchanged`: matched; path parameters and planar parameters are equivalent.
- `changed`: matched; Entity ID and both Operation IDs are preserved while
  recorded geometry or planar parameters change.
- `added`: unmatched proposed component; receives a new content-derived ID.
- `removed`: unmatched scoped Entity; its owned chain is removed on acceptance.

Every Proposal MUST contain `ProposalPreview.entity_diffs` with status, old and
proposed Entity IDs, the four feature scores plus composite score when
applicable, and before/after bounds. The preview MUST also expose the proposed
fragment Render Stack.

Matching preserves Entity metadata and Style. Acceptance replaces the scoped
fragment atomically and appends the new Artifact reference. Operations owned by
the scope MUST NOT have consumers or bindings outside the scope; such a Proposal
fails rather than deleting external dependencies.

Proposal and Transaction IDs are derived from canonical proposal content. The
digest includes the base Revision, Adapter ID/version, tracer engine/version,
matcher identity, recorded options, required Artifact identity, and complete
replacement Change. A generator or matcher identity change therefore cannot
reuse the ID of a semantically different Proposal.

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
