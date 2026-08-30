# Structural Relations v0.1

## Status

This specification defines evidence-backed relations that remain independent
from semantic hierarchy, Render Stack order, and construction dependencies.
Golden Test J is normative.

## Document dimension

`structural_relations` is an optional top-level Document array. Absence means no
recorded structural relations. Its order has no rendering, hierarchy, or
evaluation meaning.

v0.1 supports exactly two relation types:

```text
derived-from
  promoted Entity -> analysis Artifact candidate

contains
  container Entity -> contained Entity
  evidence: same analysis Artifact + candidate pair + bounds basis
```

Relation IDs are canonical hashes of `svm-structural-relations@0.1` and the
complete relation content. IDs, endpoints, evidence, and relation type are
validated semantically.

## Derived-from

Every newly promoted component creates one `derived-from` relation. Its subject
MUST be the promoted Entity, and its Artifact ID, candidate ID, and component
digest MUST exactly equal that Entity's validated provenance.

This relation does not replace provenance. Provenance is the Entity's origin
record; the relation is the queryable, orthogonal graph edge.

## Contains

`contains` v0.1 is a deterministic evidence relation, not semantic hierarchy.
It is created only when two promoted candidates:

- come from the same component-analysis Artifact;
- both have Proposal-Acceptor-verified half-open bounds;
- have unequal bounds; and
- the container bounds enclose the contained bounds on all four sides.

The basis is recorded as `strict-half-open-bounds@0.1`. "Strict" means the two
bounds are not equal; sharing one or more boundary coordinates is allowed.
No pixel mask is reopened and no semantic claim such as parent/child, group,
occlusion, or render precedence is implied.

Promotion computes relations against both newly promoted and previously
promoted candidates from the same Artifact. Promoting candidates together or
in separate accepted transactions therefore converges to the same relation set.

## Orthogonality

Creating or editing Structural Relations MUST NOT implicitly change:

- `Entity.parent_id` semantic hierarchy;
- `presentation.render_stack`;
- Styles;
- Operations or output bindings;
- animation timing.

## Golden Test J

Golden J analyzes an opaque grayscale PNG containing a dark outer ring and a
separate dark inner island. Promotion proves:

1. two deterministic `derived-from` relations;
2. one outer-to-inner `contains` relation;
3. identical results for batch and incremental promotion;
4. stable canonical relation IDs;
5. preview exposes all proposed relation edges;
6. hierarchy, rendering, construction, and animation remain unchanged;
7. forged endpoints, evidence, bounds, relation IDs, and unsupported relation
   types fail closed.
