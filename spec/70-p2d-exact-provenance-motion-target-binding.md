# P2D — Exact-Provenance Motion Target Binding Selection (normative contract)

Status: **SPECIFIED / NOT IMPLEMENTED**. This document defines a normative contract
for executable P2D acceptance, which is not implemented. P2D-A supplies only the
pure derivation function `derive_motion_target_binding_selection(document,
artifacts)` and focused tests. It creates no Proposal, evidence Artifact or
registered Change; base authentication and acceptance remain future work.

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
following repository capabilities were checked. They do not, by themselves,
prove completeness of a P2D selection at acceptance.

| # | Question | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Is transformed Group membership unique per Entity? | **YES, guaranteed by Document validation** | `_validate_groups` rejects any Entity that appears in more than one Group carrying a `transform` (`document.py:392-401`) |
| 2 | How does an SVG observation recover `shape_id`? | From the accepted observation artifact's `import_metadata.provenance["shape_id"]` | `svg_geometry_observation_provenance` (`svg_geometry_observations.py:249-276`) |
| 3 | Does SVG observation provenance prove rendered Entity origin? | **NO** — `_extract_polygon` also accepts an ordinary path id; both branches record the same producer/provenance shape. Entity-name equality is insufficient. | `svg_geometry_observations.py`: `_extract_polygon`, `_extract_rendered_entity_polygon`, `svg_geometry_observation_provenance` |
| 4 | How is raster component provenance recovered? | Exact tuple `(analysis_artifact_id, component_id, component_digest)` from the verified P2A / P2B lineage | P2A per-evaluation provenance (`raster_primitive_observation_proposal.py:257-280`); P2B observation provenance `source_p2a_evidence_artifact_ids` (`primitive_observation_assembly.py:248-254`) |
| 5 | Can PromotedComponent Entity provenance be matched exactly? | **YES** — `{type: "PromotedComponent", artifact_id, candidate_id, component_digest, bounds}` | `PromotedComponent.to_entity` (`revisions.py:1786-1793`) |
| 6 | Frozen binding one-to-one / stale / conflict semantics | Enforced by `BindTemporalMotionTargetChange.apply` **and** by Document validation | `revisions.py:1142-1186`; `document.py:210-213` |
| 7 | Can the frozen binding Change be fully delegated? | **YES** — `TemporalMotionTargetBindingAdapter` is a pure `propose(request, artifacts)` | `temporal_motion_target_binding.py:33-100` |

The original artifact-verifier-only design had a **completeness blocker**:
`ArtifactVerifier(change, resolved_artifacts)` receives no accepted Document.
Unlike P2C, P2D cannot reconstruct its candidate universe from one R0 artifact.
Omitting an identity together with its entire artifact closure could therefore
pass a verifier that only checked the supplied subset.

The revised design resolves that architectural gap at specification level using
a **full base-Document snapshot authenticated by the existing Revision content
hash**, the existing `source_revision_resolver` hook, and a pre-mutation snapshot
guard in the composite Change (§10–11). No verifier-interface or ProposalAcceptor
change is required. This is a design feasibility conclusion, not implemented or
tested acceptance evidence. The future implementation must prove the attacks in
§16 fail closed before claiming conformance.

Three additional limitations remain part of the contract (§12, §13):

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

P2D v0 permits exactly two lineages. Both are re-derivable from the exact base
Document and its accepted artifacts: Entity and Group membership come from the
Document, not from artifacts alone. Any other producer is "no allowed path".

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

**P2D-A feasibility clarification:** the frozen SVG producer's rendered-Entity
and ordinary-path branches emit indistinguishable provenance formats. An ordinary
`path id` can equal an existing Entity id. Neither that equality nor the producer
identity proves rendered origin. Under the strict rendered-origin requirement,
P2D-A therefore rejects current SVG observations with
`UNPROVEN_RENDERED_ORIGIN`, even when `shape_id` matches. It does not re-parse
source SVG or add a producer field. Path B remains specified but unavailable
until a separately authorized provenance contract supplies this proof.

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
  derived by P2D itself from the accepted Document (§11.1).

P2D auto-enumerates every temporal identity from the Document (§4). The residual
frame/interval scheduling authority belongs to orchestration, not to P2D.

`AdapterRequest.from_store(store, revision, ("document",))` supplies the base
revision id and Document snapshot; the Artifact resolver is a separate argument
to `propose`. The request does **not** contain the Revision metadata needed to
authenticate that snapshot. This differs from P2C's artifact-defined universe.

For future P2D construction, orchestration additionally provides a detached copy
of `store.revisions[request.base_revision_id]` as a `base_revision` constructor
argument to the new P2D adapter. Its ordinary `propose(request, artifacts)` method
remains unchanged in shape. This is a Revision commitment witness (§10.1), not
caller selection or a new request option; it is verified, never trusted merely
because it was supplied. No mutable RevisionStore is passed to the adapter, and
no change to `AdapterRequest`, existing adapters, or provider infrastructure is
required. A missing or inconsistent witness fails closed.

## 4. Complete identity enumeration

P2D enumerates **every** identity in `document.get("temporal_identities", [])`,
in canonical identity-id order, including identities already participating in
`motion_target_bindings`. An absent collection means an empty universe.

Every Document temporal identity receives **exactly one** evaluation entry.
"Considered identities" means this entire universe; it never means only unbound,
resolvable or selected identities. **Silent omission of any identity is
forbidden.** Selection eligibility is a classification result, not an enumeration
filter. "Eligible Group" retains its separate structural meaning in §6.

An identity whose promotion provenance is empty, malformed, or references a
missing accepted artifact is still evaluated as `UNCERTAIN` or `REJECTED` under
§5. An already-bound identity is always `REJECTED / ALREADY_BOUND` under §5.1,
including when its lineage cannot be resolved. Neither case removes it from the
evaluation universe, evidence counts, or completeness verification.

## 5. Candidate semantics

Statuses are conservative and never resolved by a best-pick. Already-bound
identity precedence is defined by §5.1; the remaining rules classify unbound
identities.

**SUPPORTED** — all of:

- every provenance record of the identity resolves through one allowed exact
  path (§2), with no unresolved record;
- no two records resolve to contradictory Entities or Groups;
- every resolved Entity maps to **exactly one** eligible transformed Group, and
  all of them are **the same** Group;
- the identity is currently unbound;
- the Group is currently unbound;
- the Group is not contended by another unbound identity that satisfies all
  preceding SUPPORTED conditions (§7).

**UNCERTAIN** — exact object correspondence cannot be uniquely proven:

- provenance is only partly resolvable (some records resolve, some do not);
- records resolve to more than one Group;
- provenance is internally contradictory (different Entities, different Groups);
- the Group is contended by another unbound identity that satisfies all
  non-contention SUPPORTED conditions (§7).

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

An identity already participating in `motion_target_bindings` is still enumerated
and receives exactly one `REJECTED` evaluation with reason `ALREADY_BOUND`.
This classification takes precedence over unresolved lineage and contention;
there is no selection for that identity. Its evaluation records the existing
binding id and Group id from the base Document, so the exclusion is auditable.

For an unbound identity, if provenance otherwise resolves to one unique eligible
Group but that Group is already bound, the identity also receives
`REJECTED / ALREADY_BOUND`, with the existing binding recorded. A structurally
eligible Group (§6) need not be available for a new binding.

Already-bound identities and pairs rejected because their Group is already
bound do not participate in new-pair contention. The existing binding remains
visible in the complete base binding state and evaluation. Other contradictory
or partially resolved lineage retains the §5 classification; no arbitrary Group
is chosen in order to attach `ALREADY_BOUND`.

P2D does not delegate these excluded pairs merely to obtain frozen idempotency
or conflict behaviour. Frozen binding semantics remain unchanged for the pairs
that are selected.

### 5.2 Derivation reason vocabulary (P2D-A)

The pure result uses these centralized tokens; SUPPORTED has no reason codes:

| Token | Existing condition represented |
| --- | --- |
| `ALREADY_BOUND` | Identity or uniquely resolved Group already bound (§5.1) |
| `GROUP_CONTENTION` | Otherwise-supported identities contend for one unbound Group |
| `NO_ALLOWED_PATH` | Unsupported observation producer/media; includes POP-only lineage |
| `UNPROVEN_RENDERED_ORIGIN` | Current SVG provenance cannot establish §2.2's rendered origin |
| `MISSING_ACCEPTED_REFERENCE` | A required lineage reference is absent from the Document |
| `INVALID_PROVENANCE` | Empty/malformed/inconsistent lineage, or no exact observation identity match |
| `INVALID_ENDPOINT` | No Document Entity matches the exact allowed provenance endpoint |
| `NO_ELIGIBLE_GROUP` | An exactly resolved Entity has no eligible transformed Group |
| `PARTIAL_PROVENANCE` | Some paths resolve to a Group and some remain unresolved |
| `CONTRADICTORY_PROVENANCE` | Exact paths resolve to different Entities or Groups |

Each endpoint path retains its own unresolved reason. Evaluation reasons are
deterministically ordered and unique; §5.1's ALREADY_BOUND takes precedence,
then contradictory resolutions, then partial resolution. Multiple Entities with
the same component provenance are not silently chosen or merged, even within
one Group. Direct inputs violating transformed membership uniqueness fail with
a domain error. Required accepted bytes that cannot be verified also fail with
a domain error; they are not reclassified as missing accepted references.

The result includes evaluations, selected pairs, total/status/selected counts,
and a detached ordered upstream reference closure. Its abstention is either
`GROUP_CONTENTION`, `ZERO_SUPPORTED`, or absent. On contention, otherwise
uncontended SUPPORTED evaluations remain visible but selected pairs are empty.
This function neither authenticates its Document input nor authorizes acceptance.

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

Contention is computed only among unbound identities whose provenance otherwise
uniquely resolves to an unbound eligible Group. Every other identity remains in
the evaluation list, including each `REJECTED / ALREADY_BOUND` entry.

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
- the exact base revision id and its authenticated full Document hash (§10.1);
- every Document temporal identity exactly once, in canonical identity-id order,
  with its status and reason code(s), including `REJECTED / ALREADY_BOUND`;
- existing binding id and Group id for each `ALREADY_BOUND` exclusion (§5.1);
- for each considered identity, every resolved provenance path: the evidence
  artifact id, the observation artifact id, the lineage producer, the resolved
  `shape_id` **or** the resolved `(analysis_artifact_id, component_id,
  component_digest)` tuple, the resolved Entity id, and the resolved eligible
  Group id (or `null`);
- the exact selected identity/group pairs, in canonical order;
- deterministic counts: total evaluated identities, each status, and selected
  pairs; total equals the complete base Document identity count, including
  already-bound and unresolved identities.

It must **not** record: any geometry similarity score, distance, overlap score,
semantic role, anchor / target label, Camera interpretation, or lifecycle
meaning.

The evidence records only P2D correspondence classifications defined here; it
adds no score, confidence, upstream R0 match status, Entity, Group, Track, Camera
or temporal-identity semantics.

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

Delegation alone is insufficient: selection evidence plus independent delegated
Changes does not bind the complete selected set to the applied set. P2D therefore
returns exactly one `ApplyMotionTargetBindingSelectionChange` in its Proposal's
Transaction. The composite carries:

- `source_revision_id`, equal to the exact Proposal base revision;
- `base_document_snapshot`, a deep copy of the **complete** base Document;
- `base_revision`, a detached existing `Revision` record used as a hash witness;
- the P2D selection evidence reference;
- the ordered upstream reference closure derived from that snapshot (§11.1);
- the ordered tuple of selected identity/Group pairs;
- the exact delegated `BindTemporalMotionTargetChange` records;
- the P2D policy identity.

The snapshot and witness are Change data, not new accepted Document fields or
Artifacts. They must not replace, strip fields from, or mutate the accepted
Document. Full-document hashing treats unrelated fields opaquely: it authorizes
no Camera, geometry or other forbidden correspondence inference.

### 10.1 Authenticate the complete candidate universe

The existing `RevisionStore._make_revision` commits to the entire Document:

```text
document_hash = "sha256:" + SHA256(canonical_bytes(document))
revision_id = "revision:" + SHA256(canonical_bytes({
    "document_hash": document_hash,
    "parent_ids": parent_ids,
    "transaction_id": transaction_id,
    "message": message
}))
```

The verifier must reproduce the base Revision using the snapshot and the
witness's `parent_ids`, `transaction_id`, and `message`, reusing the existing pure
Revision construction/hash routine. It must require exact equality to the
witness, including `document_hash` and `revision_id`, and require that revision
id to equal `change.source_revision_id`. No alternative Revision/hash format is
introduced. An id or hash supplied alongside an unauthenticated snapshot is not
sufficient.

Register the composite with the **existing**
`source_revision_resolver=_source_revision`. Before the artifact verifier runs,
ProposalAcceptor already checks this id against `proposal.base_revision_id`,
which must name an existing Revision (and the current HEAD for ordinary
acceptance). Therefore the reproduced snapshot commitment is pinned to the
actual accepted base, not a Revision invented by the proposal. No history walk,
store access inside the verifier, or proof of parent contents is necessary.

Under the repository's existing SHA-256 content-identity assumption, forging
both a reduced snapshot and its witness cannot retain that accepted Revision id.
A self-consistent witness for a different Revision is rejected by the source
revision hook. This is the completeness anchor missing from the original spec.

**Alternatives evaluated:**

- A projection of identities/Groups/Entities/references/bindings would contain
  the data needed for selection, but the current Revision hash commits to the
  whole Document, not independently verifiable projections. A caller's projected
  hash is therefore insufficient. P2D chooses the full snapshot; no Merkle proof
  system or new Core projection authority is added.
- Comparing a snapshot or hash only in `apply(document)` is insufficient to prove
  the *original* base: an adversarial preceding Change could alter the transaction
  copy to match a reduced snapshot. The authenticated Revision witness closes
  that gap even for a forged multi-Change Transaction.
- Passing Document/RevisionStore into every artifact verifier would require
  infrastructure changes. The authenticated snapshot fits the existing
  `verifier(change, resolved_artifacts)` interface and is the narrower design.

### 10.2 Composite apply guard and delegation

Before any delegated mutation, `apply(document)` must require canonical byte
equality between its incoming transaction Document and the authenticated
`base_document_snapshot`. A mismatch raises a deterministic P2D base-snapshot
error. This guard prevents earlier Changes in a forged transaction from changing
the selection inputs after artifact verification. It neither re-derives binding
ids nor duplicates endpoint-specific stale/conflict semantics.

Only after that guard succeeds:

1. apply every exact delegated `BindTemporalMotionTargetChange` in canonical
   pair order, without copying its logic;
2. append a deep copy of the selection evidence reference only after all succeed
   (and only if that exact reference is not already present).

Forbidden: catching `MOTION_TARGET_CONFLICT`, skipping a pair, repairing a Group
choice, or appending evidence after partial mutation. Transaction.apply's copy
and subsequent Document validation preserve atomicity. Passing the artifact
verifier alone is not acceptance: the apply guard and all frozen delegated
validations must also succeed.

### 10.3 ChangeAuthority registration

Use the existing actions `bind_motion_target` and `attach_analysis`. Derive the
binding intents from the exact delegated records and include the document-level
attach intent. No new action or `policies.py` change is required.

Register both the dedicated artifact verifier (§11) and the existing
`source_revision_resolver` (§10.1) on the composite. The verifier must additionally
require every embedded binding Change's `source_revision_id` to equal the
composite's authenticated source revision: the existing hook only examines
top-level Changes. Frozen binding Changes and their registry entries stay intact.

## 11. Acceptance verification through the existing interface

`_verify_motion_target_binding_selection(change, resolved_artifacts)` receives
**no live Document**. It must first authenticate the complete snapshot under
§10.1 and then derive the selection from that snapshot and accepted artifacts.
It must not treat a supplied identity list, group list, reference list or evidence
count as the candidate universe.

### 11.1 Exact accepted artifact closure

Starting with **every** authenticated snapshot identity in canonical id order,
visit its promotion provenance in recorded canonical order. For each record,
visit its R0 evidence, its observation artifact, then the producer-specific P2A
artifacts in their recorded order when required by §2. Resolve any further
artifact only if its contents are actually required for the allowed provenance
path; do not decode pixels, re-parse SVG or reproduce upstream inference.

All upstream descriptors must equal the exact references already present in
`base_document_snapshot["references"]`, including media, kind, provenance and
locator. Being present in the resolver alone does not make an artifact accepted.
Reconstruct the expected closure from these descriptors and verified contents,
not from the Change's supplied closure. The same traversal applies to excluded
identities, including already-bound ones; their available lineage is audited
without changing `ALREADY_BOUND` precedence.

A missing accepted reference or an unsupported lineage is recorded as unresolved
under §4–5; it is not silently omitted or replaced with caller-provided bytes.
If a required accepted reference exists but cannot be resolved/verified, reject
the whole proposal rather than treating deliberate closure omission as absent
provenance. Malformed available lineage follows §5 and cannot remove an identity
from the evaluation universe.

`composite.references` must equal, first-occurrence deduplicated by artifact id:
selection evidence first, then this complete ordered upstream closure.
Conflicting descriptors for one id fail closed. No unrelated references are
added merely because the full Document snapshot contains them.
`required_artifact_ids` must be the exact ids of those references; the existing
ProposalAcceptor enforces uniqueness and set equality, while the dedicated
verifier enforces the composite's canonical reference sequence and descriptors.
The witness and snapshot do not add artifacts to this closure.

### 11.2 Re-derive and bind all evaluations

After snapshot authentication and closure reconstruction, the verifier must:

1. enumerate every base Document temporal identity exactly once (§4);
2. re-resolve its allowed provenance and Entity/eligible Group mapping (§2, §6);
3. re-derive each status and reason, including `ALREADY_BOUND` from the complete
   authenticated base binding state (§5.1), and global contention (§7);
4. derive ALL globally unambiguous SUPPORTED pairs in canonical identity order;
5. require `change.selected_pairs` to equal that tuple exactly: no subset,
   superset, reorder or duplicate;
6. require exact type `BindTemporalMotionTargetChange` for every delegated record,
   and a one-to-one ordered match to the expected pairs, with its embedded full
   identity and Group equal to the records in the authenticated snapshot; the
   embedded binding's `temporal_identity_id`, `target.kind == "group"` and
   `target.group_id` must also name that same expected pair;
7. require each delegated source revision to equal the authenticated base id;
8. re-derive canonical selection evidence bytes, complete per-identity evaluations,
   counts, media, DERIVED kind and provenance, including base revision/document
   hash; require exact equality to the resolved selection evidence;
9. reject global contention or zero SUPPORTED, since neither can yield a P2D
   Proposal (§7).

Binding id generation, endpoint/static-transform checks, binding snapshot hashes,
endpoint-specific stale checks and one-to-one conflicts remain exclusively the
frozen binding adapter/Change and Document-validation duties. P2D checks the
completeness and evidence-to-delegation relationship, not an alternative binding
implementation.

### 11.3 Completeness argument

The existing source revision hook pins the snapshot witness to the Proposal's
accepted base id. The Revision hash pins the *entire* Document to that id. That
Document determines every temporal identity, Entity, Group, existing binding,
and accepted reference. Exact accepted artifacts then determine each allowed
provenance path and classification. Consequently the verifier can enforce:

```text
selected_pairs == ALL supported pairs derivable from
                  the authenticated exact base Document and accepted artifacts
```

Omitting an identity and its closure either changes the authenticated snapshot
(and fails the Revision commitment), or leaves an identity in the snapshot whose
evaluation/required artifacts are missing (and fails re-derivation). Forging both
evidence and a partial snapshot does not bypass either check.

Every rejection, including the later apply guard or delegated failure, leaves
HEAD, Revision count and Document unchanged and appends no evidence.

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
Current P2D-A positive tests use real raster producer output and exact
PromotedComponent lineage. The rendered-SVG positive case is deferred by §2.2;
both real rendered SVG and ordinary-path output are tested as rejected until
rendered origin is provable. P2D-A adds no Golden fixture.

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
- **already-bound identity plus a separate supported identity**: both receive
  exactly one evaluation; the first is `REJECTED / ALREADY_BOUND` with its existing
  binding recorded; only the second is selected; total/status counts include both;
- **unbound identity resolving to an already-bound Group**: one
  `REJECTED / ALREADY_BOUND` evaluation; no contention selection or replacement;
- **already-bound identity with unresolved lineage**: remains enumerated and
  `REJECTED / ALREADY_BOUND`; no silent omission;
- **all identities already bound / no identities**: complete derivation followed
  by zero-SUPPORTED abstention; no Proposal, no evidence, no mutation;
- **base advanced after proposal**: ordinary acceptance rejects the stale Proposal
  base before artifact verification;
- **stale Group or identity in delegated records**: an embedded record differing
  from the authenticated base is rejected by exact record comparison; attempts to
  forge the base snapshot/witness fail its Revision commitment. Existing frozen
  `STALE_GROUP` / `STALE_TEMPORAL_IDENTITY` checks remain unchanged, but are not
  promised as the first P2D error when an earlier guard rejects;
- **tampered selection evidence**: exact bytes / provenance rejection;
- **selected subset attack**: base has two supported pairs but Change, delegated
  bindings and evidence all consistently retain only one -> reject;
- **whole-identity-and-closure omission attack**: omit a second supported identity
  or a contending identity, its evaluation and every artifact unique to its
  lineage -> reject even if remaining evidence and delegated records agree;
- **omitted already-bound or unresolved identity**: reject incomplete evaluations
  and counts even when the selected pairs happen to be unchanged;
- **forged snapshot plus forged evidence**: remove an identity, Group, Entity,
  accepted reference or existing binding and update all supplied hashes/counts ->
  cannot reproduce the actual base Revision id; reject;
- **wrong/missing Revision witness**: include another base's valid witness, or
  tamper its document hash, parent ids, transaction id or message -> reject;
- **preceding-Change attack**: a forged Transaction alters the Document to match
  a reduced snapshot before the composite -> reject via the authenticated base
  commitment or the composite's pre-mutation equality guard;
- **unaccepted artifact injection / omitted required accepted artifact / extra
  closure entry / wrong accepted descriptor**: reject, not a reduced candidate
  universe or an invented accepted reference;
- **evidence/delegated mismatch** (evidence lists one pair, Change binds two) ->
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
  the two existing intents and existing source-revision resolver;
- fixture `examples/043-motion-target-binding-selection/`;
- test `tests/test_motion_target_binding_selection.py`;
- README link.

Proposal construction: (1) obtain and verify the base Revision witness against
the complete request Document and base id; (2) enumerate every temporal identity;
(3) resolve exact provenance and structurally eligible Groups, retaining all
exclusions including already-bound identities; (4) classify and detect global
contention; (5) on zero SUPPORTED or contention, abstain; (6) create complete
selection evidence; (7) call the frozen binding adapter for every selected pair;
(8) wrap exact returned records, the authenticated base snapshot/witness and
reference closure in the composite Change; (9) return a P2D Proposal with exactly
that one Change and the exact required artifact ids. Do not widen the artifact
closure merely to authenticate the inline Document snapshot.

## Feasibility verdict

**P2D_FEASIBILITY: DESIGN RESOLVED / IMPLEMENTATION UNVERIFIED.** P2D remains
**SPECIFIED / NOT IMPLEMENTED**. The former claim that the artifact verifier can
read the accepted Document directly is withdrawn. The current interface is
sufficient only with the authenticated full-Document snapshot, Revision witness,
source-revision hook, complete closure re-derivation and apply guard defined
above. A snapshot or projection without this base commitment is insufficient.

This design adds no policy action or geometric correspondence, preserves frozen
binding semantics, and requires no ProposalAcceptor or ChangeAuthority interface
change. The extra witness comes from existing Revision metadata through the new
adapter's construction seam, not a mutable store capability. Implementation and
adversarial acceptance tests in §16 are still required to establish conformance.
P2D-A focused tests establish pure derivation behaviour only, not executable
acceptance conformance.

The independent coverage precondition remains an exact provenance path to an
existing Document Entity. Same-analysis PromotedComponent lineage can satisfy it.
Rendered SVG remains blocked by the explicit origin-proof gap in §2.2; it is not
claimed as available correspondence. P2D abstains without heuristics otherwise.
