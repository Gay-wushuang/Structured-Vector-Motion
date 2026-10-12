# P2D-B0 — Versioned Representation-Target Consumer Contract

Status: **IMPLEMENTED / GOLDEN VERIFIED / FROZEN FOR THE BOUNDED V0.1 PROFILE**.

Design baseline: `38abfde2a299a8d024cbff38b22698c48cc7f1ff`, where the bounded
present-time representation certification (spec/80 v0.1) is frozen for its
bounded profile. This document specifies the implemented consumer that turns
independently replayed Spec80 certifications into proposed frozen Motion Target
Bindings. Its bounded v0.1 profile registers one composite Change, produces one
versioned evidence Artifact, and is verified by Golden 046. It does not
reinterpret P2D-A or freeze any future P2D-B profile.

Revision r2 (design-gate revision) resolved the five gaps identified by the
P2D-B0 design gate: the historical witness contract (§7.1–§7.4), the bound-state
versus evidence-authentication ordering (§6), the bounded v0.1 selection
cardinality (§4.4), the deterministic error classification (§5) and the
idempotence / determinism distinctions (§7.6). Revision r3 closes the two
remaining gate findings: the certification return-value contract
(§3.5: `admitted_associations` returns applicable References, not decoded
records) and the ordering of transport validation versus the zero-claim
short-circuit, including the non-promise of an Acceptor-side error code
(§5.1, §5.1b, §7.3). Revision r3 (final) fixes a P0 in the first r3 draft by
adopting the single canonical stage authority **S0–S7** defined in §5.1 —
witness/base/admission authentication first (S0), then the content-free
reference-universe structure (S1) — so that a witness defect always outranks a
transport defect. No runtime behavior is added or promised by these revisions.

Revision r4 (evidence-contract revision) closes the B0-2 interface blocker: the
previously reserved selection-evidence schema/media and composite Change
identity are now fully fixed by §7.7 — the **Selection Evidence Contract v0.1** —
which is the prerequisite design gate for B0-2. It is grounded in the
implemented B0-1 result (`CertifiedTargetResult`, `IdentityEvaluation`,
`ClaimAudit`), the existing `canonical_bytes` / `ArtifactStore` /
`ArtifactDescriptor` contracts and the existing ChangeAuthority conventions. No
runtime behavior is added or promised by this revision.

This contract is deliberately versioned and separable from
[spec/70](70-p2d-exact-provenance-motion-target-binding.md) (P2D-A/P2D-B). P2D-A
keeps its exact-provenance rules, reason tokens and abstention semantics
unchanged. The consumer defined here consumes only Spec80 admitted
certifications; its classification vocabulary is a new stable namespace and
never modifies P2D-A's `Reason` values or their meanings.

## 1. Scope and single purpose

The consumer solves exactly one thing:

```text
admitted + independently replayed + currently applicable Spec80 T->G certification
<-> proposed frozen Motion Target Binding
```

At a given accepted base it:

1. enumerates the complete current representation-relevant universe;
2. acquires only genuinely admitted, fully replayed, currently applicable
   certifications;
3. classifies every temporal identity with exactly one
   `SELECTED` / `ABSTAIN` / `REJECT` outcome;
4. proposes frozen bindings for the globally unambiguous `SELECTED` pairs only;
5. materializes atomically through the existing authority boundary.

For profile v0.1 the selection cardinality is at most one `SELECTED` T→G pair
per base (§4.4); multi-target atomic binding is a future extension, not a v0.1
guarantee.

The consumer performs **no geometric inference of any kind** — no distance,
overlap, centroid, bounds similarity, render-order, first-wins, fill similarity,
tolerance, calibration or nearest-Group rule. If no applicable certification
exists, the consumer abstains or rejects per §4–§5 and never chooses a target.

## 2. Complete current enumeration (A)

The consumer SHALL enumerate from the authenticated base Document, in canonical
order, without caller filtering:

- **every** `temporal_identities` entry (canonical identity-id order), including
  identities that are already bound, unresolvable or unrelated to any
  certification;
- **every** Group definition (canonical group-id order);
- **every** existing `motion_target_bindings` entry;
- every reference carrying the reserved certification media type
  `application/vnd.svm.representation-certification+json;version=0.1`;
- every genuinely admitted certification claim: a reserved-media reference with
  a matching admission event in the authenticated ancestral history whose
  `(contract, change_identity, authority_identity)` tuple is exactly
  `svm-present-representation-certification-admission@0.1` /
  `svm.revisions.CertifyArtworkRepresentationChange@0.1` /
  `svm-present-representation-independent-verifier@0.1`.

Every temporal identity receives exactly one evaluation entry. The evaluation
total MUST equal the complete base Document identity count. Silent omission of
any identity, Group, binding or admitted claim is forbidden; a claim-level audit
list records every inspected certification and its replay outcome.

## 3. Certification acquisition (B)

Valid bytes, artifact presence, provenance, a `verified`-style flag, a
transaction message or a caller list SHALL NOT establish authority. Acquisition
is the deterministic, fail-closed pipeline of §5.1; this section defines its
evidence stages.

### 3.1 Structural classification (S2)

For every reserved-media reference in the authenticated base, match admission
events in the authenticated ancestry:

- **zero matching events** → the reference is **data**. It is excluded from
  authority, cannot satisfy equivalence, cannot create conflicts and cannot be
  selected. Data alone never triggers `REJECT`.
- **exactly one matching event** → a candidate claim. Its
  `(contract, change_identity, authority_identity)` tuple MUST be exactly
  `svm-present-representation-certification-admission@0.1` /
  `svm.revisions.CertifyArtworkRepresentationChange@0.1` /
  `svm-present-representation-independent-verifier@0.1`; mismatch is
  `UNREPLAYABLE_ASSOCIATION`.
- **two or more matching events for one descriptor** → whole-proposal
  `AMBIGUOUS_ASSOCIATION`.

When zero candidate claims remain, the outcome is
`ABSTAIN / NO_ADMITTED_ASSOCIATION`. The short-circuit happens only **after**
the structural preconditions hold — S0 (base anchoring, complete witness DAG
and admission-history authentication) and S1 (complete reference-universe
structural validation, no Artifact content parsed) per §5.1 — and before any
content parsing: "no admitted claim" is fully determined by the
reserved-reference set plus the authenticated event history, and the Spec80
replay engine is **not** invoked, because its preconditions (a complete bounded
Spec80 world) are not guaranteed for arbitrary Documents. A byte-valid reserved
reference that is omitted from, or conflicts with, the transported descriptor
set is a structural failure (S1), not an abstention; it is never silently
dropped.

### 3.2 Per-claim authentication (S3, Mode A)

Every candidate claim is independently replayed through the Spec80 v0.1
semantics using only the transported universe and the authenticated witness
DAG. The replay base is the **certification acceptance Revision R**, located
structurally in the authenticated DAG — never from `event.transition_hash`,
which is the frozen legacy-form transition commitment, not the AdmittedRevision
id (the admitted id additionally commits its admission events):

- R is the unique authenticated revision whose parent Document lacks the
  claim's exact reserved descriptor and whose own Document contains it (the
  reference birth);
- for a genuine claim, R.parent_ids MUST be exactly
  `(event.base_revision_id,)` and R's Document MUST canonically equal the
  event-base Document plus exactly that descriptor (the frozen evidence-only
  certification transition);
- zero or multiple candidates reject (`UNREPLAYABLE_ASSOCIATION`).

The exact replay entry is the frozen `admitted_associations` contract applied
at R with the witness subset `ancestors(R)` derived from the authenticated DAG
(canonical order, deterministic). Success requires exact byte, descriptor and
event-bound record reproduction. Failure (raise, or a result that does not
contain this claim as its single applicable relation) is
`UNREPLAYABLE_ASSOCIATION`.

Mode A authenticates the **historical evidence**. It never depends on the
current binding state, and no current binding can suppress it.

### 3.3 Current-base applicability (S6, Mode B)

Evaluated only when the authenticated current base has no binding addressing
the claim's endpoints and no relevant Track (§5.1 S4–S5). The exact replay
entry is the `admitted_associations` contract applied at the current base with
the complete authenticated witness DAG. Outcomes:

- the claim is the single applicable relation → continue to classification;
- engine failure of any kind → whole-proposal `UNREPLAYABLE_ASSOCIATION`
  (fail-fast, §5);
- engine success but the event-bearing claim is not applicable → contradictory,
  fail-closed `UNREPLAYABLE_ASSOCIATION`.

Mode B is skipped for bound or tracked endpoints: Spec80 v0.1's own rule that
a binding blocks this profile's new certification/consumption is preserved
unchanged and is never reinterpreted as evidence invalidity (§6).

### 3.4 No message parsing, no partial results

The Spec80 replay engine is fail-fast: it raises on the first violated
precondition and never returns partial results. The consumer MUST NOT: parse
exception messages to establish authority or to choose a stable reason code;
substitute a caller-selected subset for the complete transported universe;
treat an engine failure as a soft abstention.

Exactly one applicable certification per identity may be `SELECTED`-eligible
(§4.4 cardinality). The consumer never invents a target for an identity without
an applicable certification, and never widens a claim's scope.

### 3.5 Reference → Artifact → authenticated record data flow

`admitted_associations()` returns the tuple of **applicable Artifact
References** (`_Replay.claims()[1]`), not expanded or decoded certification
records. Every consumer stage that needs endpoint identities or the claim
equivalence key MUST perform this exact flow, in order:

1. **Accept only replayed References.** The input set is exactly the tuple
   returned by the frozen `admitted_associations` contract (or the equivalent
   internal `claims()[1]`). A caller-supplied reference list, a
   reserved-media reference that did not pass replay, or a Reference the caller
   asserts is authenticated, is never an input.
2. **Resolve each Reference to its transported Artifact** via the existing
   repository interface (`resolve_reference`), yielding the accepted
   `ArtifactSnapshot` (content-addressed blob + descriptor). No new Spec80 or
   Core API is added for this step.
3. **Verify Reference ↔ Artifact ↔ bytes consistency.** The resolved snapshot
   MUST reproduce the reference descriptor exactly
   (`snapshot.document_reference()` canonically equals the Reference), and the
   existing resolution checks (blob content hash, artifact-id ↔ content,
   registered kind / media_type / provenance / locator) MUST hold. A
   descriptor conflict for one Artifact id is fail-closed.
4. **Decode the record from the authenticated Artifact.** Use the existing
   canonical-JSON record decoding (`_record` contract): the bytes MUST parse as
   a JSON object whose `canonical_bytes` equals the stored content. From that
   authenticated record, take the T/G endpoints (`association.subject_id`,
   `association.temporal_identity_id`, `association.group_id`) and the
   equivalence key (`claim_key`, the hash of the record excluding `base` and
   `universe`, §4.3 / spec/80 §6). Endpoints and equivalence are never read from
   the Reference, from caller metadata or from an unverified copy.
5. **Fail closed on any defect**: missing Reference, unresolvable Artifact,
   descriptor conflict, non-canonical or non-object bytes, absent association
   fields, or a recomputed `claim_key` mismatch. None of these may degrade to
   `ABSTAIN`, to a silent omission or to a substitute target.
6. **No new Spec80 API and no caller-trusted copies.** The flow reuses
   `admitted_associations`, `resolve_reference` and the existing record-decoding
   contract unchanged. A replicated, serialized or caller-provided certification
   record is data and carries no authority; equivalence and endpoint identity
   are always recomputed from the resolved, replayed Artifact.

This flow is the only path from `SELECTED`-eligibility to endpoint identities.
It never widens §3.1's structural short-circuit: the flow runs only at S3, when
at least one candidate claim survived S0–S2.

## 4. Classification (C)

Every temporal identity receives exactly one status. The classification
vocabulary is versioned as `svm-representation-target-consumer-reasons@0.1` and
is independent of P2D-A's tokens.

### 4.1 SELECTED

An identity is `SELECTED` iff all hold:

- exactly one applicable, fully replayed admitted certification addresses it;
- its `temporal_identity_id` and `group_id` resolve to exactly one existing
  identity and one existing Group in the current base;
- the identity is unbound and the Group is unbound;
- no relevant Track targets the Group, a member Entity or a member geometry
  Operation (`TRACKED_REPRESENTATION` is absent);
- no competing or ambiguous claim exists anywhere in the universe (§5).

### 4.2 ABSTAIN

An identity is `ABSTAIN` iff no authority evidence exists and nothing is
contradicted. Stable codes:

| Code | Condition |
| --- | --- |
| `NO_ADMITTED_ASSOCIATION` | The universe contains zero genuinely admitted certifications (reserved bytes without events are data); the replay engine is not invoked |
| `NO_CERTIFICATION_FOR_IDENTITY` | Authenticated claims exist but none addresses this identity |

`ABSTAIN` is the correct outcome for a Document where certification simply has
not happened yet. A fresh, genuine certification proposal could legitimately
fill this state; the consumer must not guess a target in the meantime.

### 4.3 REJECT

An identity (or, where noted, the whole proposal) is `REJECT` iff evidence
claims authority but fails verification, applicability or uniqueness. The
stable v0.1 acceptance-path codes are exactly the six below; each has a
structurally verifiable trigger, a fixed deciding stage and a fixed scope (§5).
Codes are never derived from exception text.

| Code | Structural trigger | Scope | Stage |
| --- | --- | --- | --- |
| `HISTORY_BROKEN` | Witness DAG authentication fails: broken ancestry link (missing witness), reachability gap (pruned), unanchored extra witness (substituted), noncanonical order (reordered), or Revision commitment mismatch (forged / rehashed) | whole proposal | S0 |
| `AMBIGUOUS_ASSOCIATION` | Two or more matching admission events for one descriptor, or two or more authenticated records with equal equivalence keys | whole proposal | S2 / S3 |
| `UNREPLAYABLE_ASSOCIATION` | S1 structural transport mismatch (base snapshot inequality, partial or conflicting descriptor set); §3.5 flow failure (descriptor/byte/decode inconsistency); Mode A or Mode B failure (raise, non-reproduction, claim not applicable); any other fail-fast engine failure | whole proposal | S1 / S3 / S6 |
| `COMPETING_ASSOCIATION` | Two or more authenticated claim records share the temporal identity or the Group while their equivalence keys differ | whole proposal | S3 |
| `ALREADY_BOUND` | An authenticated base binding addresses the claim's identity or Group; the existing binding id is recorded; no mutation; reported only after S0–S3 pass | claim endpoints | S4 |
| `TRACKED_REPRESENTATION` | A Track targets the Group, a member Entity or a member geometry Operation | claim endpoints | S5 |

These six codes are the complete stable v0.1 acceptance-path vocabulary.
`MISSING_ASSOCIATION_ARTIFACT` is a read-only-path diagnostic only (§5.1b) and
is not part of this vocabulary.

`REPRESENTATION_MODIFIED`, `IDENTITY_EXTENDED`, `DEPENDENCY_CHANGED` and
`COVERAGE_INCOMPLETE` are **reserved future refinements**, not stable v0.1
codes: the fail-fast engine surfaces them only as failures, so v0.1 folds them
into `UNREPLAYABLE_ASSOCIATION`. A later revision MAY promote each only with
its own structural predicate — never by message parsing.

`REJECT` is deterministic: no tie-break, no best-pick, no winner selection, no
replacement of an existing binding. A whole-proposal rejection produces no
Proposal, no evidence artifact and no mutation — even when other identities or
claims would individually have been selectable.

### 4.4 Selection cardinality and global semantics

**Bounded v0.1 cardinality: at most one `SELECTED` T→G pair per base.** This is
an evidence-backed property of the frozen Spec80 v0.1 replay, not a policy
choice:

- `_Replay.facts()` constructs exactly one relation triple
  (`association: {subject_id, temporal_identity_id, group_id}`) and requires a
  single bounded world: exactly one accepted whole-subject identity companion,
  exactly one matching membership companion, exactly one source-derived Group
  intersecting the allocated members, and exactly one authenticated Group birth
  transition. Two independent whole-subject worlds fail closed at these
  exactly-one checks.
- `_Replay.claims()` compares every admitted claim against that single facts
  equivalence and fails on duplicate-equivalent claims or on endpoint-sharing
  non-equivalent claims.
- `admitted_associations()` returns that applicable set, so v0.1 can never
  yield two independent applicable relations at one base.

Consequences:

- The proposal's selected set MUST equal the complete derivation; for v0.1 it
  is empty or exactly one pair. A Proposal claiming any pair not in the
  derivation — including a second pair — rejects (matrix #16).
- Multi-target atomic binding is a **future extension** requiring a new profile
  revision; it is not a v0.1 guarantee.
- Zero `SELECTED` pairs → proposal-level abstention: no Proposal, no evidence
  artifact, no mutation (`ABSTAIN / ZERO_SELECTED`).
- `ABSTAIN` identities remain visible in the complete evaluation; they never
  become `SELECTED` through any inference.
- Precedence: evidence authentication (S0–S3) ALWAYS precedes eligibility
  (S4+). `ALREADY_BOUND` and `TRACKED_REPRESENTATION` are determined only
  after the evidence stages pass (§5, §6); they never hide evidence failure.
- Witness precedence: within the evidence stages, S0 (witness/base/admission
  authentication) precedes S1 (reference-universe structure), so a witness
  defect outranks a transport defect (§5.1 rule 2).

## 5. Deterministic failure classification (D)

### 5.1 Stage order (single normative authority; first failure wins)

This S0–S7 sequence is the **only** normative stage order in this document. Every
other section's stage references, precedence statements and adversarial cases are
defined by it; no second, conflicting execution order exists.

| Stage | Check | Artifact content parsed? | Basis |
| --- | --- | --- | --- |
| S0 | Real base anchoring: witness-DAG authentication against `source_revision_id` and per-node admission-history consistency (missing / pruned / substituted / reordered / forged / rehashed) | no | structural, frozen `authenticate_witnesses` predicates |
| S1 | Complete reference-universe structural validation: base-Document snapshot equality and `source_references` equal to the complete current reference collection (exact descriptors, canonical Artifact-ID order, no descriptor conflict), plus presence of every declared id in the received resolved map | **no** — descriptor level only | structural |
| S2 | Admitted-claim classification: reserved-media references vs matching admission events — data vs claim vs ambiguous event count. **Zero claims ⇒ `ABSTAIN / NO_ADMITTED_ASSOCIATION`; stop here.** | no | structural |
| S3 | Artifact verification for a real claim plus Mode A: §3.5 Reference→Artifact→record flow, replay at the located acceptance Revision R, endpoint/`claim_key` extraction, cross-claim competition/duplication | yes | replay pass/fail |
| S4 | Existing legal binding check | no | structural |
| S5 | Relevant Track check | no | structural |
| S6 | Mode B current applicability, only for unbound and untracked targets | yes | replay pass/fail |
| S7 | Final classification and Proposal construction | — | pure |

Rules:

1. **First failure wins.** Later stages never run before earlier ones pass; the
   first failing stage decides the outcome, and S7 runs only on complete success.
2. **Witness precedence over transport.** S0 deliberately precedes S1. When one
   request has both a witness defect and a reference-universe structural defect,
   the single, unique outcome is `HISTORY_BROKEN`. A transport defect is
   reported only when the witness DAG is authentic.
3. **Zero-claim short-circuit.** `ABSTAIN / NO_ADMITTED_ASSOCIATION` is decided
   at S2 — after S0 and S1 pass, before any Artifact content parsing or Spec80
   engine invocation. It never bypasses S0/S1 and is never conditional on a
   successful engine run.
4. **No weakened universe for a real claim.** Once at least one candidate claim
   exists, the complete current reference universe MUST be validated (S1) and
   its required Artifacts verified (S3); a partial transport is a rejection,
   never a degradation of the frozen Spec80 requirement. Untrusted or external
   storage MUST NOT be consulted to fill it.
5. **No eligibility short-circuit.** S0–S3 authenticate evidence and MUST run
   even when the endpoints are already bound; no endpoint may be classified
   `ALREADY_BOUND` before S0–S3 pass. `ALREADY_BOUND` is never a way to bypass
   historical authentication.
6. **No partial results.** Adapter derivation failure yields no Proposal or
   evidence Artifact. Acceptor failure rejects the submitted Proposal without
   an accepted Revision or evidence-reference publication. Neither path permits
   a partial `SELECTED` set or accepted-state mutation.

**Naming note.** The stage labels S0–S7 are local to this consumer contract.
They are unrelated to the frozen phase/slice names "S0"/"S1" used elsewhere in
the repository: "the frozen S1 binding" always means the Motion Target Binding
slice and its `BindTemporalMotionTargetChange` authority, never stage S1.

### 5.1b Missing-artifact failure is not a promised first domain code (Acceptor boundary)

The Acceptor resolves Artifact bytes **before** the registered verifier runs
(`_verify_artifacts` precedes `_verify_artifact_bound_changes`). A declared
Artifact the resolver cannot resolve therefore fails in the Acceptor with its
existing `ProposalArtifactError` (text from the underlying `ArtifactError`); the
verifier never observes that state. Because this failure occurs in a different
layer, the two layers MUST NOT promise one unified "first domain error code":

- the consumer MUST NOT promise `MISSING_ASSOCIATION_ARTIFACT` (or any other
  code) as the guaranteed first acceptance-path error, and MUST NOT derive a code
  by parsing exception text;
- inside the verifier, a declared id absent from the received resolved map is
  unreachable under the Acceptor contract and MUST fail closed with a plain
  raise; no stable code is promised for it;
- in the read-only derivation/preview path the consumer resolves from its own
  repository. It MAY report the diagnostic `MISSING_ASSOCIATION_ARTIFACT` only
  when absence is determinable **structurally** (the required id is absent from
  its own repository index). If a structural check cannot stably separate missing
  bytes from a corrupt descriptor, it MUST use the generic
  `UNREPLAYABLE_ASSOCIATION` rather than inventing a specific code;
- modifying `ProposalAcceptor`, its error types or its messages is explicitly out
  of scope and forbidden by this contract.

### 5.2 Reason matrix

| Outcome | Code | Trigger | Stage | Scope |
| --- | --- | --- | --- | --- |
| REJECT | `HISTORY_BROKEN` | Any witness-DAG predicate: missing ancestor, unreachable/pruned branch, unanchored/substituted witness, noncanonical order, forged or rehashed Revision commitment or admission event | S0 | whole proposal |
| REJECT | `UNREPLAYABLE_ASSOCIATION` | S1 structural transport mismatch (base snapshot inequality, `source_references` ≠ complete current universe, descriptor conflict); S3 §3.5 flow failure or Mode A failure or non-applicable event-bearing claim; S6 Mode B failure; missing/corrupt bytes of a required historical dependency that cannot be structurally separated from descriptor corruption; any other fail-fast engine failure | S1 / S3 / S6 | whole proposal |
| REJECT | `AMBIGUOUS_ASSOCIATION` | ≥2 matching admission events for one descriptor (S2), or ≥2 authenticated records with equal equivalence keys (S3) | S2 / S3 | whole proposal |
| REJECT | `COMPETING_ASSOCIATION` | Authenticated records share the identity or Group with differing equivalence keys | S3 | whole proposal |
| REJECT | `ALREADY_BOUND` | Base binding addresses the endpoints; existing binding id recorded; reported only after S0–S3 pass | S4 | claim endpoints |
| REJECT | `TRACKED_REPRESENTATION` | Track targets the Group / a member Entity / a member geometry Operation | S5 | claim endpoints |
| ABSTAIN | `NO_ADMITTED_ASSOCIATION` | Zero candidate claims after S0/S1 pass; no content parsed; engine not invoked | S2 | universe |
| ABSTAIN | `NO_CERTIFICATION_FOR_IDENTITY` | Authenticated claims exist but none addresses this identity | S7 | identity |
| SELECTED | — | The single applicable, authenticated, unbound, untracked relation | S7 | identity |

Precedence is the S0→S7 order above: a witness defect (S0) always outranks a
transport defect (S1), which always outranks a claim/eligibility outcome.

`MISSING_ASSOCIATION_ARTIFACT` is deliberately **absent** from this
acceptance-path matrix: in acceptance the Acceptor resolves artifacts first and
fails with its own `ProposalArtifactError` (§5.1b). The code exists only as a
read-only-path diagnostic and is never promised as an acceptance domain code.

### 5.3 Rules

- No stable code is derived by parsing exception text; triggers are exactly the
  structural predicates above and pass/fail of the frozen replay entries.
- Acceptance-path codes are only those the verifier can decide structurally;
  Acceptor-side failures (missing declared artifact, unregistered Change,
  source-revision mismatch, policy denial) keep their existing error types and
  are not re-coded or re-messaged by the consumer (§5.1b).
- Adapter failure produces no Proposal or evidence Artifact; Acceptor failure
  rejects the submitted Proposal without publishing an accepted Revision or
  evidence Reference. Neither permits accepted-state mutation; partial
  `SELECTED` sets and incomplete evidence are forbidden.
- Outcomes never produce a substitute target; missing authority is never
  repaired by inference.
- `REJECT` is permanent for the supplied evidence state: re-admitting the same
  bytes cannot repair it. `ABSTAIN` states are the only ones a future genuine
  certification proposal may legitimately resolve.

## 6. Bound / unbound state, binding authority and execution order (E)

Four layers MUST NOT be conflated:

```text
L1 historical evidence authenticity — base anchoring, complete witness DAG,
   admission-history consistency, reference-universe structure and claim
   reproduction (S0–S3). Fraud, forgery, pruning, substitution, reordering or
   an incomplete transport fails here, always, regardless of any binding.
L2 Spec80 current applicability — the frozen v0.1 consumption proof at the
   current base (S6); skipped for bound or tracked targets because Spec80 v0.1
   itself blocks new certification/consumption for bound pairs.
L3 existing S1 binding authority — a legal accepted binding is authoritative
   for its own semantics; it is never revoked, replaced or refreshed here.
L4 P2D-B0 new-binding eligibility — the consumer's own decision (S4–S7); it
   can propose only where L1–L2 succeeded and no L3 binding addresses the pair.
```

Deterministic order: `L1 (S0 → S1 → S2 → S3) → L3 binding check (S4) → track
check (S5) → L2 (S6, only if unbound and untracked) → L4 (S7)`. This follows the
single stage authority of §5.1; L2 cannot run before L1, and no layer may be
skipped.

Normative rules:

1. After a legal frozen motion-target-binding acceptance (S1 slice) is recorded,
   it remains fully authoritative.
   The consumer SHALL NOT revoke, replace, rebind, re-point or "refresh" it.
2. A base binding addressing the claim's endpoints is detected structurally
   from the authenticated base document (exact match on `temporal_identity_id`
   or `target.group_id`) and reported as `ALREADY_BOUND` with the existing
   binding id — but ONLY after S0–S3 pass. Unauthenticated witnesses, broken
   admission events, tampered claims, an incomplete reference universe and
   missing event-bearing artifacts are NEVER silently accepted because an
   endpoint is bound; those failures reject the whole proposal.
3. Spec80 v0.1's block on new certification/consumption for bound pairs is
   preserved unchanged: Mode B is not invoked, no certification is created,
   and the block is never read as evidence invalidity or as revocation.
4. A rerun after a legal binding therefore ends with the identity classified
   `REJECT / ALREADY_BOUND` and proposal-level `ZERO_SELECTED` abstention — no
   new Proposal is required or implied, the historical binding Revision is not
   reproduced or replaced, and no re-binding is possible.
5. `ABSTAIN` and `ALREADY_BOUND` are distinct: missing evidence vs proven
   existing ownership.
6. One-to-one ownership (one T per binding, one G per binding) remains enforced
   by the frozen binding Change and Document validation; the consumer neither
   duplicates nor weakens it.

## 7. Witness contract, transport, verifier and materialization (F)

### 7.1 Composite Change fields (field names reserved at implementation; evidence contract fixed by §7.7)

```text
source_revision_id          the real Proposal base id
base_document_snapshot      deep copy of the complete base Document
witnesses                   complete canonical ancestral DAG
                            (RevisionSnapshotWitness records, sorted by
                            Revision id), collected from the trusted store
                            by orchestration
policy_identity             the versioned consumer policy
source_references           complete current base reference universe,
                            canonical Artifact-ID order, exact descriptors
selection_evidence_reference
delegated_binds             exact frozen BindTemporalMotionTargetChange
                            records, canonical pair order
selected_pairs              the derived SELECTED set (v0.1: empty or one)
```

`witnesses` MUST be the complete DAG; a single Revision witness is permitted
only when `source_revision_id` is a root with no parents. `source_revision_id`
is bound by the existing `source_revision_resolver` to the real accepted base
(existing Revision; HEAD for ordinary acceptance), and the base witness's
Document MUST canonically equal `base_document_snapshot`.

The evidence schema/media, the deterministic encoding and the composite Change
class/identity are now **fixed** by §7.7 (Selection Evidence Contract v0.1);
the remaining field names above stay reserved for implementation.

### 7.2 Witness authentication against the real base commitment

Every witness is authenticated with the frozen `authenticate_witnesses`
semantics: recompute each Revision commitment from its Document, parent ids,
transaction id, message and admission events, then require exact equality,
canonical order, and a reachable set exactly equal to the supplied set anchored
at `source_revision_id`; validate every node's admission events with the frozen
consistency contract. Failure behaviour:

| Defect | Predicate | Code |
| --- | --- | --- |
| missing witness / broken chain | required ancestor not supplied | `HISTORY_BROKEN` |
| pruned subtree | reachability gap inside a branch | `HISTORY_BROKEN` |
| substituted / extra witness | unanchored witness and/or commitment mismatch | `HISTORY_BROKEN` |
| reordered witnesses | noncanonical witness order | `HISTORY_BROKEN` |
| forged / rehashed Revision or event | Revision commitment mismatch | `HISTORY_BROKEN` |

All are whole-proposal failures at S0; no partial state. A single Revision
witness never substitutes the authenticated ancestral history. Because S0
precedes S1 (§5.1 rule 2), a request carrying both a witness defect and a
reference-universe structural defect is always reported as `HISTORY_BROKEN`.

### 7.3 Transport: complete current universe, historical closure by resolution

`source_references` MUST equal the authenticated base's complete reference
collection — exact descriptors, deduplicated by Artifact id, canonical order —
the same equality Spec80's `verify_change` enforces against
`_references(document)`. The Composite Change's `references` are exactly those
descriptors plus the new selection evidence; `required_artifact_ids` MUST equal
that id set (the existing ProposalAcceptor resolves exactly these). The
certification Artifact, its complete dependency closure and every currently
accepted reference travel in full; caller subsets are forbidden. Non-current
historical bytes are not transported, and no external resolution is permitted.

Resolution order is fixed by the existing Acceptor and is not modified:

```text
_verify_trusted_change_types → _verify_artifacts (resolves every declared id)
  → _verify_artifact_bound_changes (source_revision_resolver, then verifier)
  → enforce_transaction_policies → apply_verified_transaction
```

A declared id the Acceptor cannot resolve fails before the verifier with the
Acceptor's own `ProposalArtifactError` (§5.1b); the verifier's S1 check covers
only the structural presence of every declared id in the resolved map it
receives. If instead a *required* historical descriptor was removed from the
current base, the failure is one of two structural kinds: `source_references` no
longer equals the current universe (S1), or the transported universe no longer
reproduces the stored claim (S3) — either way whole-proposal
`UNREPLAYABLE_ASSOCIATION`, never a degradation of the frozen Spec80
requirement, and never filled from an untrusted or external store.

### 7.4 Verifier without a live RevisionStore

The registered verifier receives exactly `(change, resolved_artifacts)` and
MUST NOT require, receive or reconstruct a live `RevisionStore`. It:

1. authenticates `witnesses` against `source_revision_id` (S0, §7.2);
2. runs S1 (content-free reference-universe structural validation, including
   presence of every declared id in the received `resolved` map), then builds a
   local scratch `ArtifactStore` from that universe, requiring exact descriptor
   equality for every id (§5.1b);
3. re-executes §3 with only that scratch store and the witness Documents:
   S2 classification (zero claims ⇒ abstain, stop), S3 §3.5 flow plus Mode A per
   claim (`admitted_associations` at the located acceptance Revision R from
   §3.2 with `ancestors(R)`), S4–S5 structural eligibility, S6 Mode B when
   unbound and untracked (full DAG at the current base);
4. re-derives the complete `selected_pairs`, evidence bytes and delegated
   binding records, requiring exact equality with the Change, every delegated
   `source_revision_id` equal to the base, and no subset, superset or reorder;
5. applies the pre-mutation `apply` guard (canonical equality of the incoming
   Document with `base_document_snapshot`) before any delegated mutation.

The Mode A entry needs no new runtime API: the acceptance Revision R is located
structurally in the authenticated DAG by the §3.2 reference-birth predicate
(frozen evidence-only transition), and `admitted_associations` is reused
unchanged at R with its ancestor subset.

### 7.5 Preview, delegation, evidence, atomicity, intents

1. **Read-only derivation and preview.** Enumeration, acquisition,
   classification, proposal construction and preview are pure: they must not
   mutate any accepted state, and preview must emit no admission event.
2. **No new authority shortcut.** Materialization goes through the existing
   `ChangeAuthority` / `ProposalAcceptor` boundary with exactly one registered
   composite Change. No direct `RevisionStore` mutation, no trusted-commit
   bypass, no new policy action, no new ProposalAcceptor capability, no
   verification-free fast path.
   For this bounded profile the transaction contains only that one composite;
   preceding or following Changes reject. This restriction does not change
   any existing transaction family.
3. **Frozen delegation.** For every `SELECTED` pair, delegate to the frozen
   `TemporalMotionTargetBindingAdapter` / `BindTemporalMotionTargetChange` with
   exactly the pair. Binding id formula, snapshot hashing, stale checks,
   one-to-one conflicts and Document mutation remain exclusively the frozen
   implementation's duties.
4. **Evidence.** One versioned evidence artifact accompanies an accepted
   proposal. Its complete closed contract — payload field sets, deterministic
   encoding, Artifact/Reference construction and the composite identity — is
   §7.7 (Selection Evidence Contract v0.1, the B0-2 prerequisite gate). It is
   never published as an accepted Document Reference for a failed proposal.
5. **Atomicity.** Selected pairs, delegated binds and the evidence reference
   publish as one atomic transaction. Rejections (verification, policy, final
   validation, delegated failure) leave HEAD, Revision count, Document, Groups,
   identities, bindings and reference universe unchanged.
6. **Existing intents only.** The registered action set is exactly
   `bind_motion_target` (per delegated pair) plus `attach_analysis` on
   `document`.

### 7.6 Idempotence and determinism distinctions

1. **Pure derivation repeat at the same base** → byte-identical classification
   and evidence payloads (pure function; no clock, randomness or paths).
2. **Proposal rebuild at the same base before acceptance** → identical
   proposal id, evidence descriptor and required-artifact closure;
   content-addressed reuse, no new Artifact.
3. **Full reset to the baseline and re-execution of the chain** → identical
   Revision ids (deterministic acceptance).
4. **Re-run after a successful acceptance**: the accepted binding is history.
   At the post-acceptance HEAD the endpoints are bound, so the run ends in
   `ALREADY_BOUND` with proposal-level `ZERO_SELECTED` abstention — no new
   binding Revision is required, reproduced or implied, and the existing
   binding is never revoked. Rebuilding the Proposal at its original
   pre-acceptance base remains case 2; acceptance of a stale base is rejected
   by the existing base checks.

### 7.7 Selection Evidence Contract v0.1 (closed; B0-2 prerequisite gate)

This subsection fixes the complete, closed contract for the selection evidence
artifact — payload, deterministic encoding, Artifact/Reference construction and
composite identity. It is the prerequisite design gate for B0-2: the B0-2
verifier MUST regenerate the evidence bytes by independently re-executing the
frozen B0-1 derivation and projecting its result through §7.7.1–§7.7.3, then
require exact canonical-byte equality with the transported artifact. This
revision adds no Python, no Artifact, no Change and no registration; every
constant below is grounded in the implemented B0-1 module
(`svm/representation_target_consumer.py`), the existing `canonical_bytes`,
`ArtifactStore`/`ArtifactDescriptor` contracts and the existing ChangeAuthority
conventions.

#### 7.7.1 Evidence payload (exact field sets)

Fixed identities (never caller-overridable):

```text
schema_version   = "svm-representation-target-selection-evidence-0.1"
media_type       = "application/vnd.svm.representation-target-selection-evidence+json;version=0.1"
artifact kind    = DerivedArtifact
provenance       = {"policy_identity": "svm-representation-target-consumer@0.1"}   (exactly this single key)
locator          = none; the Reference uri equals the Artifact id
policy_identity  = "svm-representation-target-consumer@0.1"
reason_namespace = "svm-representation-target-consumer-reasons@0.1"
```

The payload is one canonical JSON object with exactly these top-level keys.
Unknown, missing or renamed keys reject. Key order is irrelevant (encoding
canonicalizes it), but every field set and every array order below is
normative.

```text
{
  schema_version    string, fixed
  policy_identity   string, fixed
  reason_namespace  string, fixed
  base              {revision_id, document_hash}
  result            {stage, status, rejection_reason, abstention_reason}
  evaluations       [ identity evaluation, ... ]        complete, canonical order
  identity_ids      [ temporal-identity id, ... ]       complete, sorted
  group_ids         [ group id, ... ]                   complete, sorted
  existing_bindings [ binding record, ... ]             complete, sorted by id
  selected_pairs    [ {temporal_identity_id, group_id}, ... ]   canonical order
  claim_audits      [ claim audit, ... ]                complete, sorted by Artifact id
  counts            {total, selected, abstain, reject, selected_pairs}
}
```

Field semantics:

- `base.revision_id` = the derivation base
  (`CertifiedTargetResult.base_revision_id`); `base.document_hash` = the
  authenticated base Revision's committed `document_hash`. Both are strings.
  `base` is always the pre-transaction base — never the resulting Revision.
- `result.stage` = `"S7"`, `result.status` = `"SELECTED"`,
  `result.rejection_reason` = null and `result.abstention_reason` = null in
  every valid v0.1 evidence: evidence exists only for a SELECTED derivation
  (§7.7.5). Any other value rejects.
- `evaluations` entry, exactly:
  `{temporal_identity_id, status, reason, stage, group_id,
  association_reference, existing_binding_ids}`; the array is sorted ascending
  by `temporal_identity_id`, one entry per identity.
  `status`, `reason` and `stage` are the exact string values of the B0-1
  `Status`, `Reason` and `Stage` enums (the namespace carries exactly nine
  reasons: `HISTORY_BROKEN`, `UNREPLAYABLE_ASSOCIATION`,
  `AMBIGUOUS_ASSOCIATION`, `COMPETING_ASSOCIATION`, `ALREADY_BOUND`,
  `TRACKED_REPRESENTATION`, `NO_ADMITTED_ASSOCIATION`,
  `NO_CERTIFICATION_FOR_IDENTITY`, `ZERO_SELECTED`; no other value is
  admissible and no new reason may be invented). `reason` is null iff
  `status == "SELECTED"` and non-null otherwise. `group_id` is a Group id
  string or null; `association_reference` is the exact complete 5-field
  Reference descriptor (`id`, `uri`, `content_hash`, `media_type`,
  `import_metadata{artifact_kind, provenance}`) or null;
  `existing_binding_ids` is an array of binding-id strings sorted ascending
  (empty when the identity resolves to no existing binding).
- `identity_ids` = every temporal-identity id of the authenticated base,
  sorted ascending, each exactly once. `evaluations` MUST cover exactly this
  set (one evaluation per identity; no identity may be dropped, including
  unselected, unreachable and unrelated ones).
- `group_ids` = every Group id of the authenticated base, sorted ascending,
  each exactly once (complete Group enumeration).
- `existing_bindings` = every `motion_target_bindings` entry of the
  authenticated base Document, verbatim and complete, sorted ascending by
  binding id; the empty array when none exist. Scope is the complete current
  binding state, not only bindings addressing the selected claim.
- `selected_pairs` entry, exactly: `{temporal_identity_id, group_id}`. The
  array is sorted ascending by (`temporal_identity_id`, `group_id`) and, for
  v0.1 cardinality (§4.4), contains exactly one element.
- `claim_audits` entry, exactly:
  `{reference, admitted, status, reason, stage, acceptance_revision_id,
  subject_id, temporal_identity_id, group_id, claim_key}` — one entry for
  every reserved-media reference of the authenticated base
  (`application/vnd.svm.representation-certification+json;version=0.1`),
  including legacy references with no admission event (they are never omitted
  and never filtered by admission status). `reference` is the exact complete
  descriptor. `admitted` is true or false (never null in evidence). On the
  SELECTED path: exactly one entry has `admitted: true` — the selected claim,
  with `status: "SELECTED"`, `reason: null`, `stage: "S7"` and non-null
  `acceptance_revision_id` (the located birth Revision, §3.2),
  `subject_id`, `temporal_identity_id`, `group_id` and `claim_key` (all
  strings). Every `admitted: false` entry carries exactly
  `{status: "ABSTAIN", reason: "NO_ADMITTED_ASSOCIATION", stage: "S2"}` with
  the five claim fields null. A second admitted claim cannot coexist with a
  SELECTED derivation (it fails S3 competition/ambiguity or S6 whole-set
  reproduction), so exactly one admitted entry is a v0.1 invariant.
- `counts` = the deterministic `CertifiedTargetResult.counts` projection:
  `total` = `len(evaluations)` = `len(identity_ids)`; `selected`, `abstain`,
  `reject` = counts of `evaluations` statuses; `selected_pairs` =
  `len(selected_pairs)`. All are JSON integers (never floats). v0.1 evidence
  invariants: `total >= 1`; `selected + abstain + reject == total`;
  `selected == 1`; `selected_pairs == 1`.
- `source_references` is deliberately **not** in the payload: transport
  completeness is enforced by S1 against the independently enumerated universe
  (a Change-level field, §7.1/§7.3), while every audit surface that must be
  complete — identities, Groups, bindings and reserved references — is fully
  carried above. Embedding the whole universe would duplicate authority
  without adding any, and would create a second copy that could silently
  diverge. Evidence MUST NOT contain the complete reference list, its own
  descriptor, the post-transaction Document hash or the resulting Revision id.
- Null semantics: in consumer-owned fields, JSON null is admissible only where
  this subsection explicitly permits it (`result.rejection_reason`,
  `result.abstention_reason`, `reason`, `group_id`, `association_reference` and
  the five claim-audit claim fields). Null elsewhere in consumer-owned fields
  rejects. Exact source descriptors and verbatim existing binding records retain
  their pre-existing values, including any nulls; they are audit data.

#### 7.7.2 Deterministic encoding

- Bytes are exactly `canonical_bytes(payload)` under the existing contract
  (`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
  encoded UTF-8).
- The field sets are explicit: dataclass/dict implicit serialization layouts
  are never normative; this subsection's projection is. Booleans are JSON
  booleans; enums are converted to their exact string values; counts are JSON
  integers.
- The consumer-owned payload envelope MUST NOT introduce timestamps, clocks,
  randomness, absolute paths, locale-dependent formatting, adapter/proposal
  identifiers, transaction ids or messages, caller metadata, similarity or
  distance scores. Exact source Reference descriptors (including `uri` and
  `import_metadata`/provenance) and verbatim existing binding records are retained
  as authenticated audit data under §7.7.1; pre-existing values in those records
  are not new envelope fields and SHALL NOT establish selection authority. They
  MUST NOT be redacted, rewritten or interpreted as authority.
- Determinism: the same base revision, the same authenticated history and the
  same resolved Artifact bytes MUST produce identical evidence bytes on every
  derivation and every verifier re-execution.
- Acyclicity: the payload contains no digest of itself, of the final Document
  or of the resulting Revision, and no reference to its own Artifact id;
  `base` is its only commitment.

#### 7.7.3 Artifact, Reference and composite transport

- The Artifact is created through the existing writer contract:
  `import_bytes(canonical_bytes(payload), media_type=<fixed>,
  kind=ArtifactKind.DERIVED, provenance=<fixed>, locator=None)`.
- Content addressing is the existing identity rule:
  `artifact_id = "artifact:" + sha256(bytes)`,
  `content_hash = "sha256:" + sha256(bytes)`.
- The resulting Reference is exactly the snapshot's `document_reference` with
  `uri == artifact_id`. `selection_evidence_reference` MUST canonically equal
  the resolved ArtifactSnapshot's `document_reference()`, and the resolved
  kind, media type and provenance MUST equal the fixed constants.
- Composite transport follows §7.3: the Change's `references` are exactly the
  complete `source_references` descriptors plus this evidence descriptor, and
  `required_artifact_ids` equals that id set. S1 validates the universe, S3
  validates the claim, and the evidence itself is validated by byte
  regeneration (§7.7.5).
- Same-base rebuild: rebuilding from the same base, history and resolved bytes
  MUST reproduce the identical Artifact id and descriptor (content-addressed
  reuse; no new Artifact and no event).

#### 7.7.4 Composite identity (closes §12 item 2)

```text
Change class      ApplyRepresentationTargetSelectionChange
Change identity   svm.revisions.ApplyRepresentationTargetSelectionChange@0.1
policy_identity   svm-representation-target-consumer@0.1
evidence schema   svm-representation-target-selection-evidence-0.1
evidence media    application/vnd.svm.representation-target-selection-evidence+json;version=0.1
```

- The Change is registered in the closed-world `ChangeAuthority` registry with
  exactly the existing actions `bind_motion_target` (derived from the exact
  delegated records) and `attach_analysis` on `document`, the existing
  `source_revision_resolver` and one dedicated artifact verifier. No new policy
  action, no new ProposalAcceptor capability.
- One versioned correspondence: this Change is the only registered Change that
  regenerates and compares this evidence schema as a dedicated selection proof.
  Other registered Changes may attach its media as ordinary reference data,
  without dedicated selection verification or standing authority.
- No admission-event family is introduced, and the evidence media is
  deliberately **not** a reserved admission family: a canonical evidence
  reference anywhere else grants no standing authority, and nothing later
  consumes the evidence as authority — its correctness matters only inside
  this Change's acceptance, where the verifier regenerates it.
- The frozen `BindTemporalMotionTargetChange`, `motion_target_binding_id`,
  `MOTION_TARGET_BINDING_POLICY_IDENTITY` and Document binding validation are
  untouched.

#### 7.7.5 Verifier regeneration and failure boundary

Within the registered verifier, under the unchanged S0–S7 authority order
(§5.1, §7.4):

1. independently re-execute the frozen B0-1 derivation
   (`derive_certified_targets` over the authenticated witnesses, the Change's
   base Document snapshot and the verifier's scratch store) — this is the same
   S0–S7 pipeline, not a parallel implementation;
2. project the result through §7.7.1 and compute `canonical_bytes`; these are
   the regenerated evidence bytes;
3. decode the transported evidence snapshot and require both that its bytes
   parse as a JSON object whose `canonical_bytes` equals the stored content
   (canonicality) and that the stored content exactly equals the regenerated
   bytes;
4. require `selection_evidence_reference` to equal the resolved snapshot
   descriptor and the fixed kind/media/provenance constants (§7.7.3);
5. compare `change.selected_pairs` against the independently derived selected
   set (canonical order, exactly one pair in v0.1) and every `delegated_binds`
   entry one-to-one and in order with the exact frozen records, each delegated
   `source_revision_id` equal to the base.

Caller-provided evidence bytes never determine `selected_pairs`: the set is
derived first, and the evidence is only an equality target. Acceptor failures
reject the already submitted Proposal as a whole, with no accepted Revision,
no evidence-reference publication and no accepted-state mutation at every
point: missing/extra/renamed fields; non-canonical bytes; forged
counts; removed, duplicated or reordered evaluations, audits or bindings;
reordered or omitted selected pairs; descriptor, kind, media or provenance
mismatch; or any non-SELECTED `result` constant. A missing evidence Artifact
follows the Acceptor boundary of §5.1b (resolved before the verifier; the
verifier sees only the resolved map and must not promise a domain code for it).
No stable Reason beyond the nine namespace values is introduced.
At the Adapter stage, ABSTAIN (including `ZERO_SELECTED`) and any REJECT
derivation produce no Proposal and no evidence Artifact. At acceptance, the
submitted Proposal and any unaccepted staging Artifact bytes may already exist;
those bytes are not a published Document Reference. Evidence, delegated bindings
and the resulting Revision publish atomically; partial success is forbidden.

## 8. Distinct authorities (G)

Three authorities remain separate and must not be conflated:

```text
evidence authority   — Spec80 certification + its Core admission event:
                       proves the current T <-> G relationship
consumer authority   — complete enumeration + classification:
                       decides which certified pairs are proposed, nothing else
binding authority    — frozen motion-target-binding Change (S1 slice) + Document
                       validation: decides final binding legality and owns
                       binding identity
```

The consumer's selection is not proof of the relationship, and the
certification is not authorization to bind without the frozen acceptance path.
Historical evidence authentication (§5.1 S0–S3) always precedes any eligibility
classification; the binding authority layer never suppresses evidence
verification, and the consumer authority never reinterprets Spec80 semantics.
No consumer-side signal — distance, similarity, sibling Group adjacency, sole
unbound Group, "obvious" pairing — may substitute for a missing certification.
Caller-supplied `temporal_identity_id`, `group_id`, `entity_id`, thresholds,
baselines, Camera or Track inputs are not part of this consumer's request
authority (document scope, no options, no artifact-id selection).

## 9. Golden and adversarial matrix (H — verified)

**Positive Golden (implemented and independently verified).** Reuses the exact
Golden 046 chain — the admitted Spec76/77 ownership, accepted Spec79 whole
identity `temporal-identity:f89cc670dc7d6d8f54dd519532d525346817425825949ded13a79daae45aacbf`,
existing Spec78 Group `group:1f24284859439580faac31e69df1aa7bf6a1a28c450d8ddae2e3b42e48b656ac`
and the admitted certification
`artifact:6ee8fd89abc03a3094d0e1b1fbc4fbd2043345bc7ff5418d2adbe7aee6262f47`
(baseline Revision `revision:29f30d08a83e2db47bcf01db6acb28f1468e2792a38c94417b4435d52f449e87`).
Expected assertions: exactly one `SELECTED` pair — the maximum v0.1 cardinality
(§4.4); preview mutates nothing; acceptance adds exactly one
`motion_target_bindings` entry with the frozen `policy_identity`
`svm-explicit-motion-target-binding@0.1`; no Track, Keyframe, Entity, Group,
TemporalIdentity or artwork-rendering byte changes; a same-base Proposal
rebuild reproduces identical proposal/evidence identities (§7.6 case 2); the
admitted certification reference and complete dependency closure remain
untouched; a post-acceptance rerun at the bound HEAD ends in `ALREADY_BOUND`
with `ZERO_SELECTED` — no new binding Revision is produced or demanded and no
revocation occurs (§7.6 case 4).

**Adversarial matrix (implemented and independently verified).** The executable
mapping is recorded in
`tests/contracts/spec81-section9-coverage-v0.1.md`; a matrix label alone is not
test evidence. Cases 9 and 10 exercise the Consumer classification boundary
with an isolated `admitted_associations` stub. They do not claim that frozen
Spec80 v0.1 can admit two independent certification Claims end to end.

| # | Case | Required outcome |
| --- | --- | --- |
| 1 | Certification bytes present, no admission event (generic/low-level append), valid descriptors and witnesses | Data; `NO_ADMITTED_ASSOCIATION` abstention decided at S2 after S0/S1; content not parsed; engine not invoked; no REJECT |
| 2 | Genuine event, tampered bytes / descriptor | Whole-proposal `UNREPLAYABLE_ASSOCIATION` (S3 §3.5 flow), fail-closed |
| 3 | Declared required Artifact not resolvable — **acceptance path** | Acceptor `ProposalArtifactError` before the verifier (`_verify_artifacts`); no consumer domain code promised, no Acceptor change |
| 3b | Declared required Artifact not resolvable — **read-only/preview path** | Consumer's own diagnostic `MISSING_ASSOCIATION_ARTIFACT` **only when structurally determinable**; otherwise generic `UNREPLAYABLE_ASSOCIATION`; never a substitute target |
| 3c | Declared id absent from the resolved map received by the verifier | Unreachable under the Acceptor contract; plain fail-closed raise, no stable code promised |
| 3d | Historical descriptor/content required by replay absent from the validated transport (bytes vs descriptor corruption not structurally separable) | Whole-proposal `UNREPLAYABLE_ASSOCIATION` (S3); no message-derived specialized code; no untrusted/external fill |
| 4 | Group / member geometry / membership / style / render order / provenance modified after certification | Whole-proposal REJECT at S6 (`UNREPLAYABLE_ASSOCIATION` in v0.1; finer code reserved); existing bindings untouched |
| 5 | Identity extended (extra binding/provenance) or aliased | Whole-proposal REJECT at S6 (`UNREPLAYABLE_ASSOCIATION` in v0.1) |
| 6 | Required dependency descriptor changed / removed | Same as #5 |
| 7 | Coverage incomplete at the current base | Same as #5 |
| 8 | Relevant Track on Group / member / Operation | `TRACKED_REPRESENTATION` (S5); no mutation |
| 9 | Two non-equivalent authenticated claims sharing T or G | `COMPETING_ASSOCIATION` (S3), whole proposal, no tie-break |
| 10 | Duplicate equivalent claims (same or different descriptors) | `AMBIGUOUS_ASSOCIATION` (S2/S3), whole proposal |
| 11 | Already-bound endpoints with a valid historical certification | S0–S3 pass → `ALREADY_BOUND` with the existing binding id; no replacement, no revocation |
| 12 | Already-bound endpoints with forged/broken evidence (unauthenticated witness, broken event, tampered claim) | Whole-proposal REJECT at S0–S3; `ALREADY_BOUND` never suppresses evidence failure |
| 13 | Missing / pruned / substituted / reordered / rehashed witness | `HISTORY_BROKEN` (S0), whole proposal |
| 14 | Base-only single witness when the base has ancestors (any incomplete DAG) | `HISTORY_BROKEN` (S0); a single Revision witness never substitutes the ancestral DAG |
| 14b | **Both** a witness defect and a transport-structure defect in one request | `HISTORY_BROKEN` only — S0 precedes S1; the transport defect is not reported |
| 15 | Omitted identity, claim or required artifact from transport or evaluation | Reject incomplete universe (S1/S3/S7); no selective shortlist, no weakened universe once a real claim exists |
| 16 | Proposal carries a pair not in the derivation — including any second pair (v0.1 cardinality is ≤1) | Reject: the selected set must equal the complete derivation |
| 17 | Uncertified identity with an "obviously matching" Group | `ABSTAIN / NO_CERTIFICATION_FOR_IDENTITY`; never proximity or sole-candidate inference |
| 18 | Stale base after proposal | Ordinary acceptance rejects before verification |
| 19 | Policy denial / delegated binding failure / post-verification failure | Atomic rollback; HEAD, Document, bindings, references unchanged |
| 20 | Engine failure anywhere (continuity broken, world modified, fail-fast precondition) | Whole-proposal REJECT; no partial `SELECTED`, no evidence artifact |
| 21 | Post-acceptance rerun at the bound HEAD | Identity `ALREADY_BOUND` + proposal-level `ZERO_SELECTED`; no new binding Revision demanded; no revocation |
| 22 | Same-base rebuild and reset-and-replay determinism | Identical proposal/evidence identities; deterministic Revision ids on reset |
| 23 | No Track creation in every positive case | Frozen behaviour only; consumer adds no animation |
| 24 | Preview isolation | Preview mutates no accepted state and emits no admission event |
| 25 | Same-base evidence rebuild | Byte-identical payload; identical Artifact id and descriptor (§7.7.3) |
| 26 | One SELECTED pair: complete evidence | Exactly one selected pair; `selected == 1` and `selected_pairs == 1`; `evaluations` cover every identity; exactly one admitted audit (§7.7.1) |
| 27 | Unselected identity / legacy reserved reference | Still recorded: an evaluation for every identity, and an `admitted: false` audit for every reserved reference, legacy data included; nothing is silenced |
| 28 | Tampered counts / removed audit or evaluation / reordered or omitted selected pairs / non-canonical bytes / forged descriptor | Whole-proposal rejection by regenerated-byte equality (§7.7.5); no partial evidence, no mutation |
| 29 | `ZERO_SELECTED` or any REJECT derivation | No Proposal, no evidence Artifact (§7.7.5) |
| 30 | Evidence Artifact missing or unresolvable | Acceptor `ProposalArtifactError` before the verifier (§5.1b); no consumer domain code promised |
| 31 | Evidence media appended by any other Change, or present without this Change's acceptance | No standing authority; nothing consumes it; S0–S7 and transport checks are unaffected |
| 32 | Frozen binding behaviour | Unchanged: `motion_target_binding_id`, snapshot hashing, stale/conflict checks, one-to-one ownership and Document validation (§7.7.4) |

## 10. Performance budget and optimization direction (I)

Observed characteristics (from the spec/80 Gate): each derivation replays
complete history per call; nested re-authentication occurs through the Spec79
identity reproduction; admitted-claim replay recursion depth grows with the
number of admitted claims; deep chains fail closed (possibly via
`RecursionError`).

Initial budget (design):

- one consumer run over the bounded Golden 046 fixture SHOULD complete within a
  small constant multiple of a single Spec80 verification pass; the pipeline
  performs at most two replay invocations (Mode A per claim, Mode B when
  unbound). Implementation MAY fuse Mode A into Mode B when Mode B runs — the
  engine's per-claim reproduction is the same computation — but MUST NOT fuse
  when Mode B is skipped for bound or tracked endpoints;
- the exact numeric budget and any maximum claims-per-proposal bound are
  **OPEN** pending implementation measurement;
- a run MUST NOT weaken any check to meet the budget.

Allowed future optimization directions (all must preserve full authority):

- within-pass memoization (already present in the certification replay);
- replacing recursion with iteration for admitted-claim replay;
- authenticated caches keyed by Revision commitment inside the trusted host
  boundary, fully revalidated on load;
- a per-Revision canonical certification index produced at acceptance and
  independently re-verified on consumption.

Forbidden: skipping `authenticate_witnesses`, skipping per-node admission
validation, trusting bytes/hashes/provenance without event verification,
shortening the ancestral walk, or caching across trust boundaries without
revalidation.

## 11. Out of scope (J)

This contract does not cover and its future implementation SHALL NOT add:

- general ordinary-video artwork matching or inference;
- single-Entity Motion Target (remains an open separate architectural
  question);
- automatic animation Track or Keyframe authoring;
- appearance repair, stylization, occlusion or flicker handling;
- arbitrary artwork claiming / arbitrary Group adoption;
- any change to existing animation, rendering, Camera, P2A/P2B/R0/R1/P2C phase
  semantics, or the frozen Motion Target Binding (S1 slice) authority;
- substitution of P2D-A's provenance rules (P2D-A stays exactly as specified).

## 12. Open decisions, implementation split and readiness

Open decisions (not decided by this bounded v0.1 freeze):

1. Whether a future P2D composite should ever combine certification-based pairs
   with P2D-A provenance-based pairs in one proposal, or support multi-target
   atomic binding (v0.1 cardinality is one, §4.4) — keep separate profiles with
   separate evidence schemas (current design: separate; future extension).
2. ~~The exact name/version of the composite Change and evidence schema/media.~~
   **CLOSED by §7.7.4 (r4)**: `ApplyRepresentationTargetSelectionChange` /
   `svm.revisions.ApplyRepresentationTargetSelectionChange@0.1`, schema
   `svm-representation-target-selection-evidence-0.1`, media
   `application/vnd.svm.representation-target-selection-evidence+json;version=0.1`.
3. The numeric performance budget and any per-proposal claim bound (§10).
4. Whether `ALREADY_BOUND` consumption states should additionally record the
   archived certification descriptor for audit display (no authority effect).
5. Promoting `REPRESENTATION_MODIFIED`, `IDENTITY_EXTENDED`,
   `DEPENDENCY_CHANGED` and `COVERAGE_INCOMPLETE` to stable codes requires a
   structural predicate for each; reserved for a future consumer revision.
6. Whether the consumer exposes a read-only diagnostic report for
   whole-proposal REJECT outcomes (never an accepted evidence artifact).

Implemented split (each independently reviewed):

- **B0-1** — read-only derivation: enumeration, acquisition via the staged
  pipeline (S0–S7), classification, versioned reason codes, proposal-level
  abstention; pure focused unit tests. No acceptance surface. **IMPLEMENTED.**
- **Evidence Contract v0.1 — CLOSED (r4)**: the §7.7 Selection Evidence
  Contract v0.1 fixes the payload, encoding, Artifact/Reference construction and
  composite identity, so the verifier no longer depends on undefined B0-3
  interfaces.
- **B0-2** — composite Change `ApplyRepresentationTargetSelectionChange` +
  `ChangeAuthority` registration + independent verifier (witness DAG
  authentication, complete closure re-derivation, Mode A/B replay integration,
  §7.7.5 evidence regeneration, apply guard, frozen delegation).
  **IMPLEMENTED.**
- **B0-3** — adapter + Proposal + evidence Artifact construction/publishing
  (one shared pure §7.7.1 projection helper with B0-2) + preview isolation +
  policy intents (`bind_motion_target`, `attach_analysis`). **IMPLEMENTED.**
- **B0-4A** — Golden fixture (046 chain) + full adversarial matrix + regression.
  **VERIFIED.**
- **B0-4B** — final evidence gate and bounded v0.1 freeze record.
  **COMPLETE.**

The evidence schema itself is no longer a B0-3 deliverable: it is closed here
and consumed by both B0-2 (regeneration/comparison) and B0-3 (construction and
publishing).

Readiness verdict for this round:

```text
P2S-F1B freeze:                      FROZEN (bounded v0.1 profile only)
P2D-B0 bounded v0.1:                  FROZEN
Design-gate revision r2 gaps:        ALL RESOLVED (design only)
  historical witness contract        §7.1–§7.4
  bound-state vs evidence ordering   §6
  v0.1 selection cardinality         §4.4 (≤ 1; single-world evidence)
  deterministic error classification §5 (structural triggers; no parsing)
  idempotence / determinism          §7.6
Design-gate revision r3 findings:    ALL RESOLVED (design only)
  Reference vs decoded record        §3.5 (returns applicable References)
  transport vs zero-claim ordering   §5.1, §5.1b, §7.3
Evidence Contract v0.1:              CLOSED
  evidence payload/encoding/artifact §7.7.1–§7.7.3
  composite identity                 §7.7.4 (closes open item 2)
  verifier regeneration boundary     §7.7.5
B0-1 Read-only Consumer:             IMPLEMENTED
B0-2 Composite + Verifier:           IMPLEMENTED
B0-3 Production Adapter:             IMPLEMENTED
B0-4A Golden + Coverage:             VERIFIED
P2D-B0 bounded v0.1 profile:         FROZEN
Future P2D-B profiles/extensions:    OPEN / NOT FROZEN
```

The bounded v0.1 implementation and final evidence gates are satisfied: the
consumed authority (spec/80 v0.1) is frozen; every acquisition entry reuses the
frozen `admitted_associations` contract with no new Core authority, no new
ProposalAcceptor capability and no ChangeAuthority bypass; the composite
transport and witness design reuse the proven spec/70 §10–§11 and spec/80
patterns; the frozen Motion Target Binding (S1 slice) boundary is unchanged; the
five design-gate gaps, the two r3 findings and the r4 evidence contract are
resolved by these revisions. This freeze is limited to the single-target,
single-Profile behavior specified here. Multi-target or cross-Profile
selection, a numeric performance budget, optional diagnostic/audit reporting,
and new stable Reason codes remain open future decisions and are not implied by
this freeze.
