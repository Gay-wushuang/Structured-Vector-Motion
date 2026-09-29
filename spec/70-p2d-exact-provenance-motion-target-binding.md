# P2D — Exact-Provenance Motion Target Binding Selection (normative contract)

Status: **SPECIFIED / NOT IMPLEMENTED**. This document defines a normative contract
only. It adds no implementation, no test, no fixture and no executable behaviour.

Phase 1 remains FINAL / FROZEN (`spec/62`); P2A is FINAL / FROZEN (`spec/65`);
P2B is FINAL / FROZEN (`spec/67`); P2C is FINAL / FROZEN (`spec/69`).

P2D solves exactly one thing:

```text
accepted temporal identity
<-> exact structural / provenance correspondence
<-> existing Document Group
```

P2D v0 performs **no geometric inference of any kind**.

## 0. Blocker assessment

The contract was written after a read-only inspection of the frozen code. The
following assumptions were checked, and are **confirmed** rather than assumed.

| # | Question | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Is transformed Group membership unique per Entity? | **YES, guaranteed by Document validation** | `_validate_groups` rejects any Entity that appears in more than one Group carrying a `transform` (`document.py:392-401`) |
| 2 | How does an SVG observation recover `shape_id`? | From the accepted observation artifact's `import_metadata.provenance["shape_id"]` | `svg_geometry_observation_provenance` (`svg_geometry_observations.py:249-276`) |
| 3 | Does `shape_id` resolve exactly to a Document Entity? | **YES** — the renderer emits `data-svm-entity = entity.entity_id`, and the SVG producer selects that exact attribute | `renderers/svg.py:61`; `_extract_rendered_entity_polygon` (`svg_geometry_observations.py:337-345`) |
| 4 | How is raster component provenance recovered? | Exact tuple `(analysis_artifact_id, component_id, component_digest)` from the verified P2A / P2B lineage | P2A per-evaluation provenance (`raster_primitive_observation_proposal.py:257-280`); P2B observation provenance `source_p2a_evidence_artifact_ids` (`primitive_observation_assembly.py:248-254`) |
| 5 | Can PromotedComponent Entity provenance be matched exactly? | **YES** — `{type: "PromotedComponent", artifact_id, candidate_id, component_digest, bounds}` | `PromotedComponent.to_entity` (`revisions.py:1786-1793`) |
| 6 | Frozen binding one-to-one / stale / conflict semantics | Enforced by `BindTemporalMotionTargetChange.apply` **and** by Document validation | `revisions.py:1142-1186`; `document.py:210-213` |
| 7 | Can the frozen binding Change be fully delegated? | **YES** — `TemporalMotionTargetBindingAdapter` is a pure `propose(request, artifacts)` | `temporal_motion_target_binding.py:33-100` |

**No implementation blocker exists.** Three limitations are, however, frozen as
part of the contract and must not be silently worked around (§12, §13):

1. frozen binding exposes **no separate artifact verifier** — its endpoint, stale
   and conflict validation lives inside `BindTemporalMotionTargetChange.apply`
   and in Document validation (`change_authority.py` registers it with
   `source_revision_resolver=_source_revision` and no `artifact_verifier`);
2. P2D re-derives correspondence from **already-accepted, already-verified**
   upstream artifacts, and does not re-verify upstream observation production;
3. the raster lineage only resolves when the Document already contains a
   `PromotedComponent` Entity promoted from the **same** analysis artifact.

## 1. Authority boundary

P2D v0 may know:

- the accepted Document and its accepted Artifact references;
- every `temporal_identities` entry and its promotion provenance;
- every Group Definition and its `transform` / `members` / `provenance`;
- every Entity id and its `provenance`;
- the accepted R0 evidence, observation, P2A/P2B or SVG lineage artifacts that
  those references resolve to.

P2D v0 must **not** know or use: `temporal_identity_id` supplied by a caller;
`group_id`; `entity_id`; role; anchor / target; threshold; geometry tolerance;
baseline tick; Camera; Track; Ground Truth; and any geometric similarity signal.

**Forbidden correspondence signals.** P2D must not use, as correspondence
evidence: nearest Group; largest overlap; centroid distance; bounds similarity;
current rendered bounds matching; color / fill similarity; first Group wins;
render-stack order wins; caller-supplied thresholds; an implicit
raster-pixel == Document-space assumption; Camera compensation.

If no exact provenance path exists, P2D **abstains**. Coverage must not be
improved by introducing a heuristic.

## 2. Exact allowed correspondence paths

P2D v0 permits exactly two lineages. Both are re-derivable from accepted
artifacts alone. Any other producer is "no allowed path".

### 2.1 Path A — raster component lineage

```text
temporal_identity
-> provenance[*].evidence_artifact_id                    (accepted R0 evidence)
-> R0 payload.source_artifact_id                        (accepted observation artifact)
-> observation provenance, dispatched on its recorded producer:
   (a) P2B producer  : provenance.source_p2a_evidence_artifact_ids
                       -> P2A evidence payload.evaluations[*]
                       -> per-evaluation provenance
                          {analysis_artifact_id, component_id, component_digest}
   (b) frozen raster geometry producer
                     : provenance.source_occurrences[*]
                       {analysis_artifact_id, component_id, component_digest}
-> Entity whose provenance is
   {type: "PromotedComponent", artifact_id, candidate_id, component_digest}
   matching (analysis_artifact_id, component_id, component_digest)
-> unique eligible transformed Group containing that Entity
```

Exact tuple, normative:

```text
PromotedComponent.provenance.artifact_id      == lineage.analysis_artifact_id
PromotedComponent.provenance.candidate_id     == lineage.component_id
PromotedComponent.provenance.component_digest == lineage.component_digest
```

For the P2B producer, the specific evaluation that produced a given
`observation:p2b:<sha256>` primitive is recovered by **re-deriving** that
observation id over its normative inputs (spec/66 §7) — never by ordinal, by
list position, or by hash prefix matching.

### 2.2 Path B — rendered SVG lineage

```text
temporal_identity
-> provenance[*].evidence_artifact_id                    (accepted R0 evidence)
-> R0 payload.source_artifact_id                        (accepted observation artifact)
-> observation provenance.shape_id                      (rendered SVG producer only)
-> Document Entity whose id == shape_id
-> unique eligible transformed Group containing that Entity
```

`shape_id` is accepted only when the observation provenance records a rendered
SVG producer and the value resolves to **exactly one** existing Document Entity.
A `shape_id` that resolves to zero Entities is rejected; one that resolves to
more than one is a Document-validation failure upstream and is rejected.

### 2.3 Producers explicitly outside the allowed set

`observation:pop:` observations record no `shape_id` and no analysis component
provenance (`pop_geometry_observations.py:263-343`). They therefore yield **no
allowed path** and a `REJECTED` correspondence. This is not a bug: a POP-lineage
identity is not related to a Document Entity by provenance in v0.

## 3. Request authority

P2D is **document-scoped with no caller selection**.

- scope must be empty or `("document",)`;
- `options` must be empty — any option key rejects;
- the caller must not supply `temporal_identity_id`, `group_id`, `entity_id`,
  role, anchor / target, threshold, baseline tick, geometry tolerance, Camera,
  Track or Ground Truth;
- the caller must not supply `artifact_ids`; the required verification closure is
  derived by P2D itself from the accepted Document (§10).

P2D auto-enumerates eligible identities from the Document (§4). The residual
frame/interval scheduling authority belongs to orchestration, not to P2D.

Confirmed feasible: `AdapterRequest.from_store(store, revision, ("document",))`
already carries only the revision, the Document snapshot and an
`ArtifactResolver`, which is sufficient (this is the shape P2C already uses).

## 4. Eligible identity enumeration

P2D considers exactly the identities in `document["temporal_identities"]` that
are **not** an endpoint of any existing `document["motion_target_bindings"]`
entry, in the Document's canonical identity order (identities are sorted by id;
`document.py:329-330`).

Every considered identity receives exactly one evaluation entry. **Silent
omission of a considered identity is forbidden.**

An identity whose promotion provenance is empty, malformed, or references a
missing accepted artifact is still enumerated and receives `UNCERTAIN` or
`REJECTED` — it is never dropped.

## 5. Candidate semantics

Statuses are conservative and never resolved by a best-pick.

**SUPPORTED** — all of:

- every provenance record of the identity resolves through one allowed exact
  path (§2), with no unresolved record;
- no two records resolve to contradictory Entities or Groups;
- every resolved Entity maps to **exactly one** eligible transformed Group, and
  all of them are **the same** Group;
- the identity is currently unbound;
- the Group is currently unbound;
- the Group is not contended by another considered identity (§7).

**UNCERTAIN** — exact object correspondence cannot be uniquely proven:

- provenance is only partly resolvable (some records resolve, some do not);
- records resolve to more than one Group;
- provenance is internally contradictory (different Entities, different Groups);
- the Group is contended by another considered identity.

**REJECTED** — no usable correspondence exists:

- no allowed exact provenance path for any record;
- every resolved Entity has no eligible transformed Group;
- a resolved endpoint is structurally invalid;
- the provenance is explicitly incompatible with the allowed paths;
- the identity or the Group is already bound (`ALREADY_BOUND`, see below).

**UNCERTAIN must never be resolved by picking a best candidate**, and a
`REJECTED` or `UNCERTAIN` correspondence carries **no** deletion, occlusion,
background, foreground, static, moving or lifecycle meaning.

### 5.1 Already-bound endpoints

An identity already participating in a `motion_target_bindings` entry, or a
Group already so bound, is **not selected**. P2D classifies it as `REJECTED`
with reason `ALREADY_BOUND` at proposal time rather than relying on the frozen
Change's idempotent / conflict behaviour at acceptance.

Rationale: P2D's authority is "select the pairs to submit". An already-bound
endpoint is not a new selection; submitting it would add nothing, and would let
an already-bound pair mask a genuine one-to-one conflict. Keeping it `REJECTED`
also makes the acceptance verifier's expected selected set well defined.

## 6. Group eligibility

A Group is **eligible** for an Entity iff:

- it is a Group Definition (`kind == "explicit-group"`, id `group:<64hex>`);
- it carries a `transform` (`transform is not None`); Document validation
  guarantees `transform` is either absent or a legal transform;
- the resolved Entity is one of its `members`.

Uniqueness is **guaranteed by the Document, not inferred by P2D**: validation
rejects an Entity that belongs to more than one transformed Group
(`document.py:392-401`). Therefore "the eligible transformed Group of an Entity"
is at most one, and P2D must fail closed rather than choose if it ever observes
more than one.

A Group with no `transform` is not eligible. An Entity with no eligible
transformed Group yields `REJECTED` for the identity's record.

## 7. Global selection authority

P2D selects **ALL globally unambiguous `SUPPORTED` pairs** in one proposal —
never one, never a best pair.

- `I1 -> G1` and `I2 -> G2`, both SUPPORTED and distinct: **both are selected**.
- `I1 -> G1` and `I2 -> G1` (two identities contending for one Group): this is a
  **global one-to-one contention**. P2D must not let the first win.

Contention handling, normative: **the whole proposal abstains.** P2D raises a
deterministic domain error, produces no evidence artifact, selects no pair and
mutates nothing. Each contending identity is nevertheless classified `UNCERTAIN`
with reason `GROUP_CONTENTION` in the derivation, and zero identities are
silently dropped.

Rationale: Document validation already requires one-to-one bindings
(`document.py:210-213`), so the frozen delegated binding would fail the whole
transaction anyway; abstaining earlier is stricter, keeps the frozen Change free
of tie-break responsibility, and matches the established conservative precedent
(R0 abstention, R1 conflict, P2C disjointness-violation fail-closed). Producing a
proposal that is guaranteed to be rejected at acceptance would be a worse
contract.

If **zero** pairs are `SUPPORTED` (all `UNCERTAIN` / `REJECTED`), P2D also
abstains: no Proposal, no evidence artifact, no mutation.

## 8. Evidence artifact

One new versioned evidence artifact accompanies every accepted P2D proposal.

```text
adapter id    adapter:motion-target-binding-selection
adapter ver  0.1
policy       svm-motion-target-binding-selection@0.1
schema       svm-motion-target-binding-selection-0.1
media        application/vnd.svm.motion-target-binding-selection+json;version=0.1
kind         DERIVED
```

It records:

- policy / adapter identity;
- the exact base revision id;
- every considered temporal identity, in canonical order, with its status and
  reason code(s);
- for each considered identity, every resolved provenance path: the evidence
  artifact id, the observation artifact id, the lineage producer, the resolved
  `shape_id` **or** the resolved `(analysis_artifact_id, component_id,
  component_digest)` tuple, the resolved Entity id, and the resolved eligible
  Group id (or `null`);
- the exact selected identity/group pairs, in canonical order;
- deterministic counts per status.

It must **not** record: any geometry similarity score, distance, overlap score,
semantic role, anchor / target label, Camera interpretation, or lifecycle
meaning.

The evidence adds no new score, confidence, match status, Entity, Group, Track,
Camera or identity semantics.

## 9. Frozen binding delegation

For every selected pair, P2D must call the frozen
`TemporalMotionTargetBindingAdapter` with exactly
`{"temporal_identity_id": <identity>, "group_id": <group>}` and take the exact
`BindTemporalMotionTargetChange` it produces.

P2D must **not** re-implement or copy: `motion_target_binding_id`, persistence
semantics, snapshot hashing, identity / group conflict logic, one-to-one
ownership, or Document mutation. `BindTemporalMotionTargetChange`,
`motion_target_binding_id`, `MOTION_TARGET_BINDING_POLICY_IDENTITY` and Document
binding validation stay frozen and unchanged.

P2D owns only: **which exact-provenance pairs are submitted to frozen binding.**

## 10. Trusted acceptance binding

Delegation alone is insufficient: selection evidence plus an independent set of
delegated Changes would leave "the selected set" and "the applied set" only
locally legal, exactly as in P2C.

P2D therefore defines one composite trusted Change,
`ApplyMotionTargetBindingSelectionChange`, which atomically binds:

- the exact P2D selection evidence reference;
- the ordered tuple of selected identity/group pairs;
- the exact delegated `BindTemporalMotionTargetChange` records produced by frozen
  R-binding for those pairs;
- the policy identity.

`references` must be the deterministic verification closure (§11), first-occurrence
deduplicated, ordered: selection evidence first, then the closure of every
considered identity in canonical order. `required_artifact_ids` must equal that
closure exactly.

`apply(document)` must:

1. apply every delegated `BindTemporalMotionTargetChange`, in canonical pair
   order, **without copying their logic**;
2. append the selection evidence reference **only after** all of them succeed.

Forbidden: catching `MOTION_TARGET_CONFLICT`; skipping a conflicting pair;
repairing a Group choice; partially binding; appending evidence after a partial
mutation. Atomicity is provided by `Transaction.apply`'s document copy.

### 10.1 ChangeAuthority registration

Register the composite Change with a dedicated verifier wrapper (§11). Its
allowed intents must reflect its exact composite side effects, reusing the two
existing actions `bind_motion_target` and `attach_analysis`. No new policy
vocabulary action is added and `policies.py` is not modified.

Every delegated record's `source_revision_id` must equal the proposal base
revision; the composite verifier enforces this, because the frozen
`source_revision_resolver` hook only observes top-level transaction Changes and
the delegated records are embedded fields of the composite.

## 11. Acceptance verifier

The dedicated verifier `_verify_motion_target_binding_selection` must, from the
resolved exact artifacts and the accepted Document:

1. re-resolve every considered identity's provenance through §2;
2. re-enumerate the eligible identities and their order (§4);
3. re-derive each resolved Entity (§2) and each unique eligible transformed Group
   (§6);
4. re-derive each identity's status and reason code(s) (§5);
5. re-derive ALL selected `SUPPORTED` pairs, in canonical order (§7);
6. require the composite Change's pair set to equal that set **exactly** — no
   subset, no superset, no reorder, no duplicate, no omitted identity;
7. require the delegated records to map one-to-one onto the expected pairs, with
   an exact per-pair match of the embedded identity and Group records;
8. require every delegated record's `source_revision_id` to equal the accepted
   base revision (§10.1);
9. re-canonically derive the selection evidence and require exact byte equality
   against the resolved artifact, including media type, kind and provenance;
10. reject any global contention or zero-`SUPPORTED` composite, since those must
    never have produced a Proposal (§7).

Endpoint existence, static-transform, snapshot-hash, stale and one-to-one
conflict validation are **not** re-implemented: they remain the frozen
`BindTemporalMotionTargetChange.apply` and Document-validation duties, executed
inside the same transaction.

Every rejection must leave HEAD, Revision count and Document unchanged, and must
append no evidence.

## 12. Trust boundary

P2D validates the accepted canonical R0 evidence, observation provenance, P2A/P2B
lineage and PromotedComponent entity provenance. It does **not** recompute R0
scoring, re-verify observation production, or re-parse the upstream SVG. This is
the same trust model P2C states in `spec/69 §13`.

A future "full observation -> acceptance-time upstream re-derivation" is an
independent hardening slice, not P2D polish.

## 13. Raster / geometric limitation (frozen)

**P2D v0 does not solve generic raster-to-Document geometric correspondence.**

If a P2A / P2B / P2C raster identity cannot be resolved to an existing Document
Entity through the exact provenance of §2.1, P2D **abstains**. This is a
documented limitation, not a bug.

To make a Golden pass, P2D must never:

- assume raster-pixel coordinates equal Document coordinates;
- introduce a tolerance;
- compare centroid, bounds or rendered geometry;
- fall back to the nearest Group.

Solving calibrated geometric correspondence is a **separate semantic slice** that
must explicitly own a calibration authority. It is not P2D.

## 14. Camera boundary

P2D handles the **target side only**: `temporal identity -> Group`.

It does not handle: `temporal identity -> anchor Entity`, anchor role,
static / background inference, Camera Reference, Camera consensus or Camera
compensation.

The anchor side retains its own identity <-> Entity authority: the frozen Camera
path still requires an explicit `anchor_entity_id` (`camera_consensus.py:52-62`,
`spec/57`). Completing P2D does **not** mean Camera is solved, and P2D must not be
described as solving it.

## 15. Multi-interval boundary

Multi-interval identity continuation is already solved by the frozen P2B
observation identity plus frozen R1 owner reuse, and is not P2D's authority.

P2D must not implement: transitivity, identity merge, cross-interval aggregation
or lineage repair. Per-interval scheduling is orchestration, not P2D semantic
authority.

## 16. Golden contract

The Golden must use an **exact provenance** path (rendered SVG lineage and/or
PromotedComponent lineage). A geometry-distance Golden is forbidden.

Minimum cases:

- **one identity -> one unique eligible Group -> `SUPPORTED`**: exactly one
  selected pair; the frozen delegated binding is produced; the accepted Document
  gains exactly one `motion_target_bindings` entry with the frozen
  `policy_identity`; **no Track is created**;
- **two identities -> two Groups -> both selected** in one proposal, canonical
  order, one atomic Revision;
- **unresolved provenance -> abstain / `UNCERTAIN`**: partly resolvable lineage;
- **one identity resolving to conflicting Groups -> `UNCERTAIN`**;
- **no eligible transformed Group -> `REJECTED`** (Entity absent, untransformed
  Group only, or POP-lineage observation);
- **two identities competing for one Group -> global contention -> whole
  proposal abstains**, no evidence appended, Document unchanged, no first-wins;
- **already-bound endpoint -> `REJECTED` / `ALREADY_BOUND`**, not re-selected;
- **stale Group snapshot** — Group transform / membership changed after the
  proposal → frozen `STALE_GROUP` at acceptance;
- **stale identity provenance** — identity snapshot changed after the proposal →
  frozen `STALE_TEMPORAL_IDENTITY`;
- **tampered selection evidence** → reject on exact bytes / provenance;
- **selected subset attack** (evidence lists one pair, Change binds two) →
  reject;
- **extra delegated binding attack** → reject;
- **duplicate / reordered pair attack** (order is normative) → reject;
- **deterministic rerun**: two independent runs give identical proposal ids,
  evidence bytes, Revision ids and Documents;
- **no Track creation** in every positive case;
- every rejection asserts HEAD, Revision count and Document are unchanged.

## 17. Frozen boundaries

P2D must not change the semantics of: P2A; P2B; R0; P2C; R1;
`TemporalMotionTargetBindingAdapter`; `BindTemporalMotionTargetChange`;
`motion_target_binding_id`; `MOTION_TARGET_BINDING_POLICY_IDENTITY`; the Camera
adapters; S0 / S4; Track authoring; `ProposalAcceptor`; `policies.py`; Document
validation semantics.

P2D may, when implemented later, add: a new adapter, a new evidence schema, the
new composite Change, a new ChangeAuthority verifier wrapper, tests and the
Golden fixture. Nothing in this document is implemented by this document.

## 18. Expected implementation (future, not this slice)

- new `svm/adapters/motion_target_binding_selection.py`
  (`adapter:motion-target-binding-selection`, version `0.1`, policy
  `svm-motion-target-binding-selection@0.1`, schema
  `svm-motion-target-binding-selection-0.1`, media
  `application/vnd.svm.motion-target-binding-selection+json;version=0.1`);
- `svm/revisions.py`: the `ApplyMotionTargetBindingSelectionChange` composite
  Change;
- `svm/change_authority.py`: register it with the dedicated verifier wrapper and
  the two existing intents;
- fixture `examples/043-motion-target-binding-selection/`;
- test `tests/test_motion_target_binding_selection.py`;
- README link.

Proposal construction: (1) enumerate eligible identities; (2) resolve each
identity's exact provenance path; (3) derive Entity and unique eligible
transformed Group; (4) classify; (5) detect global contention; (6) on zero
`SUPPORTED` or contention, abstain; (7) create the selection evidence artifact;
(8) call the frozen binding adapter per selected pair; (9) wrap the exact
returned records and the evidence in the composite Change; (10) return a P2D-owned
Proposal whose `required_artifact_ids` are exactly the composite Change's
references. Do not widen the closure unnecessarily.

## Feasibility verdict

**P2D_FEASIBILITY: STRONG.** The slice is a read-only correspondence derivation
over already-accepted provenance, one evidence artifact, one composite
acceptance-binding Change, and full delegation of the existing frozen binding
Change. It removes the caller's identity and Group selection on the target side,
keeps every frozen semantic untouched, adds no policy action, and needs no
geometric inference. Its hard precondition — an exact provenance path from the
observed lineage to an existing Document Entity — is satisfied by the rendered
SVG lineage and by the PromotedComponent lineage, and is honestly absent
otherwise, in which case P2D abstains.