# P2C — Temporal Identity Selection (normative contract)

Status: normative contract for Phase 2 slice P2C. It adds exactly one inference
authority and reuses the frozen R0 scoring and R1 promotion semantics unchanged.
It also defines one minimal P2C acceptance-binding composite Change.

Feasibility: **P2C_FEASIBILITY: STRONG**.

Phase 1 remains FINAL / FROZEN (`spec/62`); P2A is FINAL / FROZEN (`spec/65`);
P2B is FINAL / FROZEN (`spec/67`).

## 1. Authority boundary

Already frozen and **not** recomputed by P2C:

- **R0** (`svm/adapters/temporal_correspondence.py`) owns source×target pair
  enumeration, centroid / size / color / type scoring, mutual-best,
  support threshold (`0.75`), margin threshold (`0.08`), the
  `SUPPORTED / UNCERTAIN / REJECTED` status, `candidate_id` and `inference_id`
  (`_infer`, `:236-318`).
- **R1** (`svm/adapters/temporal_identity_promotion.py`) owns "only SUPPORTED may
  promote", stable temporal identity creation / reuse, observation-ownership
  conflict detection, `PromoteTemporalIdentityChange`, and `temporal_identity_id`
  (`:88-135`, `revisions.py:852-862`).

P2C's single new inference authority is therefore defined strictly as:

> **From one accepted R0 evidence artifact, determine which existing R0
> `SUPPORTED` candidates should be submitted to frozen R1 promotion.**

This is well defined and no blocker exists. P2C additionally owns the
deterministic selection-evidence artifact, the acceptance-binding composite
Change (§6), and the Proposal packaging, but it owns no scoring, no status, and
no identity semantics.

## 2. Pairwise only

P2C v0.1 consumes **exactly one** accepted R0 evidence artifact. That R0 evidence
corresponds to one P2B observation artifact and two ticks only.

P2C v0.1 does **not** do multi-interval aggregation, transitivity, chain merging,
track building, lifecycle inference, deletion, occlusion, split / merge, or
appearance / disappearance. Each of those adds temporal authority beyond
"select the existing `SUPPORTED` pairs", and would be a later slice.

## 3. Candidate selection rule

```text
selected inference_ids
  = every R0 candidate with status == "SUPPORTED",
    in the R0 evidence's deterministic candidate order.
```

The R0 evidence candidate order is deterministic (nested loop over
`observation_id`-sorted sources × target, `_infer:240-318`). P2C must **not**
pick the first, pick the highest score, accept a caller-chosen subset, re-score,
deduplicate, or infer a global winner.

**Disjointness is guaranteed by the frozen R0 mathematics.** A pair is
`SUPPORTED` only when it is the mutual best *and* `min(source_margin,
target_margin) >= 0.08`, where each margin is the score minus that row / column's
runner-up (`_infer:267-276`). A strictly positive margin means the best is
strictly greater than every alternative, so at most one target can be `SUPPORTED`
for a given source observation, and at most one source for a given target
observation. A tie would force a margin of `0`, which fails `>= 0.08`.

Consequently no observation can appear in two `SUPPORTED` pairs, P2C never needs a
tie-break, and P2C must fail closed rather than tie-break if that invariant is
ever violated. This invariant must be recorded and locked by a focused test.

## 4. Zero / multiple SUPPORTED

- **Zero `SUPPORTED`** in the R0 evidence: P2C fails closed / abstains. It must
  not create a temporal identity and must not fall back to `UNCERTAIN`.
- **Multiple disjoint `SUPPORTED`**: frozen R1 already supports promoting several
  disjoint correspondences in one call. `TemporalIdentityPromotionAdapter`
  processes the selected candidates in order, maintaining a running
  `observation_owner` map: each pair reuses a single existing owner if present,
  otherwise receives a new `temporal_identity_id(evidence_artifact_id,
  candidate_id)` (`:100-135`); the registered `PromoteTemporalIdentityChange.apply`
  re-derives the same ownership and validates it (`revisions.py:884-929`). Because
  the pairs are disjoint, each becomes its own stable identity (or extends its
  single existing owner). P2C therefore selects **all** `SUPPORTED` candidates in
  one proposal.

This multiple-promotion path is supported by the frozen code but is not yet
covered by a focused R1 test (current R1 tests promote a single inference). P2C's
Golden must lock the multiple-disjoint behaviour end to end.

## 5. Implementation seam

Three seams were considered.

- **A — P2C emits selection evidence only; a later caller invokes R1.** Rejected
  as the P2C contract: it leaves the `inference_ids` hand-off to a caller, which
  is exactly the residual authority P2C must remove.
- **B — P2C selects, then delegates to the frozen R1 adapter. (Recommended for
  all identity semantics.)** P2C calls
  `TemporalIdentityPromotionAdapter.propose(...)` with the selected
  `inference_ids`, and reuses R1's resulting `PromoteTemporalIdentityChange`
  verbatim. All conflict / stable-id / reuse semantics remain R1's. This is
  feasible without modifying R1: R1 is a pure `propose(request, artifacts)`
  function whose only inputs are an accepted R0 evidence artifact and
  `inference_ids`, both of which P2C can supply.
- **C — P2C constructs `PromoteTemporalIdentityChange` itself.** Rejected: it
  would duplicate frozen R1 stable-identity / conflict logic.

**Recommended: B for identity semantics.** P2C must not hold a second
stable-identity / conflict / `temporal_identity_id` implementation.

Delegation alone, however, is **not sufficient for normative acceptance**; a
separate P2C acceptance-binding composite Change is also required (§6).

## 6. Acceptance-binding composite Change

### 6.1 Why delegation alone is insufficient

The earlier draft bound P2C with `PromoteTemporalIdentityChange` plus a bare
`AppendReferencesChange(selection_evidence)`. That does not implement the P2C
authority. Repository facts:

- `AppendReferencesChange` only appends references, and it is registered with the
  `attach_analysis` intent and **no** `artifact_verifier`
  (`change_authority.py:438`); `ChangeAuthority.artifact_verifier` is optional
  (`:66`).
- `ProposalAcceptor` resolves the Transaction references and calls each Change's
  registered `artifact_verifier`; it cannot understand the selection-evidence
  schema on its own.
- `_verify_temporal_identity_promotion` only checks that every promoted
  correspondence is an R0 `SUPPORTED` candidate (`:216-221`). It does **not**
  check that *all* R0 `SUPPORTED` candidates were promoted.

So `R0 SUPPORTED = [A, B]`, promotion `= [A]`, selection evidence `= [A, B]`
would leave both sides locally legal while P2C's ALL-`SUPPORTED` authority was
never atomically bound. Likewise a tampered selection evidence could not be
re-derived and rejected by a generic `AppendReferencesChange`.

### 6.2 Composite Change

Define one minimal P2C trusted composite Change,
`ApplyTemporalIdentitySelectionChange`. It is not a second R1; it is only an
acceptance-binding wrapper.

Contents:

- `selection_evidence_reference`;
- `r0_evidence_reference`;
- `delegated_promotion`: the exact `PromoteTemporalIdentityChange` returned by
  frozen R1;
- `selected_inference_ids`;
- `policy_identity`.

`references` must contain at least, first-occurrence unique:

1. the R0 evidence reference;
2. the selection evidence reference.

The caller must never construct the delegated promotion; only the P2C adapter
obtains it from the frozen R1 Proposal.

### 6.3 Composite apply semantics

`apply(document)` must:

1. call the frozen `delegated_promotion.apply(document)` — without copying its
   logic;
2. append `selection_evidence_reference` to `document["references"]` **only
   after** the promotion succeeds.

Both effects therefore live in the same Change, the same Transaction and the same
Revision. Any R1 conflict raises out of the whole Change and the selection
evidence is never written. Atomicity is provided by `Transaction.apply`'s
deepcopy.

The composite must never catch an R1 conflict and continue, repair an owner, skip
a correspondence, or generate a stable id independently.

### 6.4 Dedicated artifact verifier

The composite Change must register a dedicated `artifact_verifier`
(`_verify_temporal_identity_selection`). It must, from the resolved exact R0
evidence, re-derive:

```text
supported_candidates
  = every R0 candidate with status == "SUPPORTED",
    in canonical R0 order
```

and then confirm:

- **A.** `selected_inference_ids` equals exactly all `SUPPORTED` inference ids —
  no subset, no superset, no reorder, no duplicate.
- **B.** `delegated_promotion.correspondences` maps exactly one-to-one onto the
  selected `SUPPORTED` candidates, matching at least `inference_id`,
  `candidate_id`, `source_tick`, `source_observation_id`, `target_tick`,
  `target_observation_id`, `evidence_artifact_id` and the evidence policy
  identity.
- **C.** the delegated `PromoteTemporalIdentityChange` is validated by
  *reusing* the existing `_verify_temporal_identity_promotion`
  (`change_authority.py:183`), not by re-implementing its evidence validation.
  Reusing a private helper from the P2C `change_authority` wrapper is allowed;
  R1 semantics are not modified.
- **D.** the selection evidence bytes are re-canonically derived and required to
  equal the resolved evidence exactly.

Therefore a tampered selection evidence, or selection evidence `[A, B]` with
promotion `[A]`, fails acceptance closed.

### 6.5 ChangeAuthority registration

Register the composite Change in `svm/change_authority.py` with its dedicated
verifier wrapper. Its allowed intents must accurately reflect the composite side
effects, reusing the two existing actions:

- `promote_temporal_identity`;
- `attach_analysis`.

Returning multiple existing intents from one ChangeAuthority is already the
established architecture (`_replace_scene`, `change_authority.py:392`), so the
composite intent function returns both. No new policy vocabulary action is added
and `policies.py` is not modified.

## 7. Selection evidence

P2C appends one independent selection evidence artifact, because the accepted
promotion record carries no proof that the `inference_ids` were derived rather
than caller-supplied. The evidence records only facts R0 already decided:

- schema `svm-temporal-identity-selection-0.1`;
- exact R0 evidence artifact id;
- source observation artifact id;
- frame ticks;
- every R0 candidate: `candidate_id`, `inference_id`, original R0 `status`;
- `selected_inference_ids`;
- excluded `UNCERTAIN` / `REJECTED` ids with statuses;
- deterministic counts;
- policy / adapter identity.

It must add no new score or status, and it is a `DERIVED` artifact. It is bound
by the composite Change (§6), not by a bare `AppendReferencesChange`.

## 8. Forbidden caller authority

The P2C caller must not provide: `inference_ids`, `candidate_id`,
`observation_id`, source / target pairing, score, threshold, identity id, role,
Entity, Group, Track, Camera, or Ground Truth. The caller provides only the exact
accepted R0 evidence artifact; any base revision comes from the normal
`AdapterRequest`. P2C takes **no options**.

## 9. Existing identity interaction

P2C fully delegates ownership semantics to frozen R1 and must not predict or
repair a conflict. For each selected pair:

- **A.** both observations unowned → R1 creates one new stable identity;
- **B.** one owned, one unowned → R1 extends the existing identity;
- **C.** both owned by the same identity → R1 is idempotent, no new identity;
- **D.** both owned by different identities → R1 raises
  `TEMPORAL_IDENTITY_CONFLICT` and the whole Change fails closed.

P2C must never merge two stable identities, rename an identity, choose an owner,
or silently skip a conflicting `SUPPORTED` pair. If R1 fails closed, the composite
Change propagates that failure.

## 10. Match failure is not deletion

A non-`SUPPORTED` R0 candidate (`UNCERTAIN`, `REJECTED`, or no such pair) means
only that P2C does not promote a temporal identity for that pair. It must never be
interpreted as the object disappearing, being deleted, occluded, split, merged, or
a new object appearing.

## 11. Golden P2C

Deterministic fixture `examples/042-temporal-identity-selection/`, built so the
frozen R0 genuinely faces multi-primitive frames (based on the P2B 041 scene or a
new equivalent). Required cases:

- **A. two disjoint clear matches** — R0 yields `SUPPORTED A1↔A2` and
  `SUPPORTED B1↔B2`; P2C selects **both** `inference_ids`; R1 creates two distinct
  stable temporal identities.
- **B. ambiguous pair** — R0 `UNCERTAIN`; P2C does not select it.
- **C. rejected mismatch** — R0 `REJECTED`; P2C does not select it.
- **D. zero-supported case** — P2C abstains / fails closed; no temporal identity
  change in the Document.
- **E. ownership reuse** — an existing identity owner is extended by a new
  `SUPPORTED` pair, exactly per frozen R1 semantics.
- **F. identity conflict** — source and target already belong to different stable
  identities → frozen R1 `TEMPORAL_IDENTITY_CONFLICT` → atomic fail closed.
- **G. permutation determinism** — primitive input order / candidate enumeration
  must not change the selected identity set.

## 12. Adversarial cases

At minimum: forged R0 status; forged `inference_id`; duplicate `inference_id`;
malformed / non-canonical R0 JSON; wrong R0 policy identity; wrong R0 inference
identity; R0 evidence not accepted; stale base; ownership conflict; multiple
disjoint `SUPPORTED`; no `SUPPORTED`; `UNCERTAIN` only; `REJECTED` only.

Acceptance-binding cases that must now reject:

- R0 `SUPPORTED [A, B]` but promotion only `[A]` → reject;
- R0 `SUPPORTED [A, B]` but promotion `[A, B]` while selection evidence says
  `[A]` → reject;
- selection evidence reordered → reject;
- selection evidence with a tampered status / count / id → reject;
- an extra promoted inference → reject;
- a duplicate selected inference → reject;
- a delegated R1 conflict → reject atomically.

Every failure must leave HEAD, Revision count and Document unchanged, must not
append the selection evidence, and must produce no partial temporal identity
mutation.

## 13. Frozen boundaries

P2C must not modify the semantics of: `temporal_correspondence.py`, the
`TemporalCorrespondenceAdapter` thresholds / policy,
`temporal_identity_promotion.py`, `PromoteTemporalIdentityChange`,
`temporal_identity_id`, the R1 artifact-verifier semantics, P2A, P2B, S0, S4,
Camera, binding, Track authoring, `ProposalAcceptor`, or `policies.py`.

P2C may instantiate / call `TemporalIdentityPromotionAdapter.propose(...)` to
obtain the canonical delegated promotion Change. P2C must not modify
`temporal_identity_promotion.py`, `PromoteTemporalIdentityChange`,
`temporal_identity_id`, or the R1 verifier semantics. The composite wrapper's only
responsibility is binding "ALL SUPPORTED selection" to "selection evidence ↔ exact
delegated promotion" at acceptance. No new policy vocabulary action is added and
`policies.py` is not modified.

S0 / S4 remain the downstream consumers: each requires options exactly
`{temporal_identity_id, inference_ids}` and validates them against the promoted
R1 provenance (`observed_translation_motion.py:57-98`). P2C produces that
identity; it does not change how S0 / S4 consume it.

## 14. Expected implementation

- new `svm/adapters/temporal_identity_selection.py`
  (`adapter:temporal-identity-selection`, version `0.1`, policy
  `svm-temporal-identity-selection@0.1`, schema
  `svm-temporal-identity-selection-0.1`, media
  `application/vnd.svm.temporal-identity-selection+json;version=0.1`);
- `svm/revisions.py`: the new `ApplyTemporalIdentitySelectionChange` composite
  Change;
- `svm/change_authority.py`: register it with the dedicated verifier wrapper,
  reusing `_verify_temporal_identity_promotion` and allowing the two existing
  intents;
- `svm/cli.py`: preview / accept subcommand;
- fixture `examples/042-temporal-identity-selection/`;
- test `tests/test_temporal_identity_selection.py`;
- README link.

Proposal construction: (1) validate one accepted canonical R0 evidence;
(2) derive all `SUPPORTED` inference ids; (3) on zero, abstain / fail closed;
(4) create the selection evidence artifact; (5) call the frozen R1 adapter with
exactly those ids; (6) extract its exact `PromoteTemporalIdentityChange`;
(7) wrap that change and the selection evidence in the composite Change;
(8) return a P2C-owned Proposal whose `required_artifact_ids` are the exact
unique ids of the composite Change's references (the R0 evidence and the selection
evidence). Do not widen the closure unnecessarily.

Not modified: `temporal_correspondence.py`, `temporal_identity_promotion.py`,
`policies.py`, `ProposalAcceptor`, P2A, P2B, S0, S4.

The Phase 1 `recovery_orchestration` `candidates[0]` path is the degenerate 1×1
selector this slice supersedes for multi-primitive input; it is not modified here.

## Feasibility verdict

**P2C_FEASIBILITY: STRONG.** The slice is a thin selection + R1-delegation + one
acceptance-binding composite Change + evidence. It removes the caller-supplied
`inference_ids` authority, keeps R0 scoring and R1 promotion frozen, needs no new
policy vocabulary action, and rests on a provable R0 disjointness invariant. The
only addition beyond delegation is the minimal composite Change required to bind
the ALL-`SUPPORTED` selection to the delegated promotion atomically.