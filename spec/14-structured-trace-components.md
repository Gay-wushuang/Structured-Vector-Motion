# Structured Trace Components v0.1

## Status

This specification extends the deterministic Bitmap Trace Adapter with
structural decomposition. Golden Test F is normative for the v0.1 subset.

## Semantic boundary

The Adapter performs topological grouping, not semantic recognition:

```text
top-level contour-tree root -> Entity compound shape
all descendant contours    -> same Entity path (holes and nested islands)
```

It MUST NOT label components as character parts, infer object meaning, or place
Potrace objects in the Document. Semantic naming remains a later Proposal or a
user edit.

This Trace Component is a Potrace contour-tree group, not a raster connected
component. In particular, a filled island nested inside a hole is not connected
to the root filled area, but remains in the same compound-shape Entity because
both descend from the same top-level contour root. OpenCV-style raster
connectivity is a distinct future analysis concept.

Each contour-tree group MUST produce its own independent chain:

```text
Entity N
  -> CreatePath N
  -> PathToPolygon N
```

The entire set is accepted as one atomic `AppendSceneFragmentChange`.

## Deterministic grouping and order

Containment is determined from Potrace decomposition contours before Bézier
planarization. Each contour without a containing parent is a component root;
all transitive descendants remain in that component so holes and nested islands
are not incorrectly promoted to separate semantic Entities.

Components are ordered using the total key `(min_y, min_x, max_y, max_x,
canonical_d)`. Canonical path data is the final tie-break when distinct groups
have equal bounds, so third-party iteration order cannot determine IDs. This
order defines both the zero-padded component suffix and initial Render Stack
order. A multi-component import uses suffixes `-0000`, `-0001`, and so on. A
one-component result retains the Golden E unsuffixed IDs for backward
compatibility.

This allocation provides deterministic import identity, not cross-import object
tracking. Reconciliation of a later re-trace against existing Entities requires
a separate explicit Proposal and is outside this version.

## Golden Test F

Golden F proves that a bitmap containing three disconnected filled components,
one of which contains a hole:

1. produces three Entities and three independent Operation chains;
2. retains the hole inside its owning Entity;
3. has deterministic IDs and Render Stack order;
4. commits all components in one Revision;
5. reevaluating one component does not invalidate either sibling;
6. renders to a stable SVG.

Golden F.1 fixes nested-island semantics: an outer contour, its hole, and a
filled island inside that hole form one contour tree and therefore one compound
shape Entity with three path subpaths.
