# P2C — Temporal Identity Selection (normative contract)

Status: normative contract for Phase 2 slice P2C. It adds exactly one inference
authority and reuses the frozen R0 scoring and R1 promotion semantics unchanged.

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

P2C's single new authority is therefore defined strictly as:

> **From one accepted R0 evidence artifact, determine which existing R0
> `SUPPORTED` candidates should be submitted to frozen R1 promotion.**

This is well defined and no blocker exists. P2C additionally owns the
deterministic selection-evidence artifact and the Proposal packaging (§6, §5B),
but it owns no scoring, no status, and no identity semantics.

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
- **B — P2C selects, then delegates to the frozen R1 adapter. (Recommended.)**
  P2C calls `TemporalIdentityPromotionAdapter.propose(...)` with the selected
  `inference_ids`, and reuses R1's resulting `PromoteTemporalIdentityChange`
  verbatim. All conflict / stable-id / reuse semantics remain R1's. This is
  feasible without modifying R1: R1 is a pure `propose(request, artifacts)`
  function whose only inputs are an accepted R0 evidence artifact and
  `inference_ids`, both of which P2C can supply. The final Proposal is P2C-owned
  (P2C generator/notes) but carries R1's Change unchanged, so acceptance runs the
  frozen R1 `apply` / registration (`change_authority.py:482-487`) with identical
  semantics.
- **C — P2C constructs `PromoteTemporalIdentityChange` itself.** Rejected: it
  would duplicate frozen R1 stable-identity / conflict logic.

**Recommended: B.** P2C must not hold a second stable-identity / conflict /
`temporal_identity_id` implementation.

## 6. Selection evidence

P2C appends one independent selection evidence artifact, because the accepted
`PromoteTemporalIdentityChange` carries no record that the `inference_ids` were
derived rather than caller-supplied. The evidence records only facts R0 already
decided:

- schema `svm-temporal-identity-selection-0.1`;
- exact R0 evidence artifact id;
- source observation artifact id;
- frame ticks;
- every R0 candidate: `candidate_id`, `inference_id`, original R0 `status`;
- `selected_inference_ids`;
- excluded `UNCERTAIN` / `REJECTED` ids with statuses;
- deterministic counts;
- policy / adapter identity.

It must add no new score or status. It is appended in the same Transaction as the
promotion (via the existing `AppendReferencesChange`), so `required_artifact_ids`
equals the union of the Transaction references (the R0 evidence plus the selection
evidence), satisfying the acceptor contract (`proposals.py:297-312`).

## 7. Forbidden caller authority

The P2C caller must not provide: `inference_ids`, `candidate_id`,
`observation_id`, source / target pairing, score, threshold, identity id, role,
Entity, Group, Track, Camera, or Ground Truth. The caller provides only the exact
accepted R0 evidence artifact; any base revision comes from the normal
`AdapterRequest`. P2C takes **no options**.

## 8. Existing identity interaction

P2C fully delegates ownership semantics to frozen R1 and must not predict or
repair a conflict. For each selected pair:

- **A.** both observations unowned → R1 creates one new stable identity;
- **B.** one owned, one unowned → R1 extends the existing identity;
- **C.** both owned by the same identity → R1 is idempotent, no new identity;
- **D.** both owned by different identities → R1 raises
  `TEMPORAL_IDENTITY_CONFLICT` and the whole transaction fails closed.

P2C must never merge two stable identities, rename an identity, choose an owner,
or silently skip a conflicting `SUPPORTED` pair. If R1 fails closed, P2C preserves
that behaviour.

## 9. Match failure is not deletion

A non-`SUPPORTED` R0 candidate (`UNCERTAIN`, `REJECTED`, or no such pair) means
only that P2C does not promote a temporal identity for that pair. It must never be
interpreted as the object disappearing, being deleted, occluded, split, merged, or
a new object appearing.

## 10. Golden P2C

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

## 11. Adversarial cases

At minimum: forged R0 status; forged `inference_id`; duplicate `inference_id`;
malformed / non-canonical R0 JSON; wrong R0 policy identity; wrong R0 inference
identity; R0 evidence not accepted; stale base; tampered selection evidence (if
present); ownership conflict; multiple disjoint `SUPPORTED`; no `SUPPORTED`;
`UNCERTAIN` only; `REJECTED` only. None may produce a partial identity mutation.

## 12. Frozen boundaries

P2C must not modify the semantics of: `temporal_correspondence.py`, the
`TemporalCorrespondenceAdapter` thresholds / policy,
`temporal_identity_promotion.py`, `PromoteTemporalIdentityChange`,
`temporal_identity_id`, P2A, P2B, S0, S4, Camera, binding, Track authoring,
`ProposalAcceptor`, or the policy vocabulary.

P2C needs no new Change and no new policy action: it reuses the existing
`PromoteTemporalIdentityChange` (`promote_temporal_identity`) and
`AppendReferencesChange` (`attach_analysis`). If P2C could only be established by
modifying R0 or R1, the contract would be STOP-and-report; it is not.

S0 / S4 remain the downstream consumers: each requires options exactly
`{temporal_identity_id, inference_ids}` and validates them against the promoted
R1 provenance (`observed_translation_motion.py:57-98`). P2C produces that
identity; it does not change how S0 / S4 consume it.

## 13. Expected implementation

- new `svm/adapters/temporal_identity_selection.py`
  (`adapter:temporal-identity-selection`, version `0.1`, policy
  `svm-temporal-identity-selection@0.1`, schema
  `svm-temporal-identity-selection-0.1`, media
  `application/vnd.svm.temporal-identity-selection+json;version=0.1`);
- reuse the frozen `TemporalIdentityPromotionAdapter` by delegation (no R1
  changes), and the existing `PromoteTemporalIdentityChange` /
  `AppendReferencesChange` (no new Change, no `change_authority.py` change);
- `svm/cli.py`: preview / accept subcommand;
- fixture `examples/042-temporal-identity-selection/`;
- test `tests/test_temporal_identity_selection.py`;
- README link.

The Phase 1 `recovery_orchestration` `candidates[0]` path is the degenerate 1×1
selector this slice supersedes for multi-primitive input; it is not modified here.

## Feasibility verdict

**P2C_FEASIBILITY: STRONG.** The slice is a thin selection + delegation + evidence
layer. It removes the caller-supplied `inference_ids` authority, keeps R0 scoring
and R1 promotion frozen, needs no new Change or policy action, and rests on a
provable R0 disjointness invariant.