# Phase 2 P2C Final Freeze — Temporal Identity Selection

Status: **FINAL / FROZEN**. Documentation and status record only. It adds no
semantics, changes no contract, modifies no implementation, test or fixture, and
begins no further Phase 2 slice.

Phase 1 remains FINAL / FROZEN (`spec/62`); P2A is FINAL / FROZEN (`spec/65`);
P2B is FINAL / FROZEN (`spec/67`).

## 1. Frozen baseline

Frozen implementation baseline:

```text
887596516ea977ce80dfc3c035ed881558b99ee2
```

Normative contract:

`spec/68-p2c-temporal-identity-selection.md`

That commit (`Implement P2C temporal identity selection`) is the P2C semantic
implementation baseline: the adapter, the acceptance-binding composite Change,
the ChangeAuthority registration + verifier, the Golden fixture and the focused
tests all landed there. This freeze commit only records the frozen state; it does
not change implementation semantics.

P2C lineage: `2b8ffb0` defined the contract, `504646e` hardened the acceptance
binding, `8875965` implemented it.

## 2. Frozen capability

P2C input: **one** exact accepted R0 temporal correspondence evidence artifact.

P2C behaviour, in order:

1. read the frozen R0 candidate list;
2. select **every** candidate whose `status == "SUPPORTED"`, in the R0 canonical
   candidate order;
3. zero `SUPPORTED` → abstain / fail closed;
4. multiple disjoint `SUPPORTED` → select **all**;
5. call the frozen `TemporalIdentityPromotionAdapter` with the exact selected
   `inference_ids`;
6. take the `PromoteTemporalIdentityChange` produced by frozen R1;
7. atomically bind, with `ApplyTemporalIdentitySelectionChange`:
   - the exact ALL-`SUPPORTED` selection,
   - the selection evidence,
   - the delegated R1 promotion;
8. an acceptance-time dedicated verifier re-proves that the three agree;
9. frozen R1 continues to own stable temporal identity id, ownership reuse,
   ownership conflict, and identity mutation semantics.

## 3. Frozen authority boundary

P2C's only new authority:

> **Which already-existing R0 `SUPPORTED` correspondences are submitted to frozen
> R1?**

The answer is frozen as: **ALL `SUPPORTED`, in exact R0 canonical order.**

P2C does not own pair scoring, mutual-best, the support threshold (`0.75`), the
margin threshold (`0.08`), or the `SUPPORTED / UNCERTAIN / REJECTED`
classification — those belong to frozen R0. P2C does not own stable temporal
identity generation, owner resolution, or conflict repair — those belong to
frozen R1.

## 4. Caller authority removed

P2C removes the caller-supplied `inference_ids` selection. The old Phase 1
orchestration path (`candidate[0]` plus manual `inference_ids`) is no longer the
authority for the Phase 2 multi-primitive path.

The caller now provides only the exact accepted R0 evidence artifact. The caller
must not provide: `inference_ids`, candidate ids, observation ids, source / target
pairing, scores, thresholds, identity id, role, Entity, Group, Track, Camera, or
Ground Truth. P2C takes no options; the focused test rejects every such option key
(`test_request_authority_and_unaccepted_r0_reject`).

## 5. Frozen ALL-SUPPORTED semantics

- **zero `SUPPORTED`** — no temporal identity promotion, no selection evidence
  append, no deletion / lifecycle meaning.
- **one `SUPPORTED`** — promote exactly that one.
- **multiple disjoint `SUPPORTED`** — promote all of them; no "best one", no
  caller subset, no dedup, no reorder.
- **`UNCERTAIN`** — never promoted.
- **`REJECTED`** — never promoted.

An R0 failure or the absence of `SUPPORTED` does **not** mean deletion,
disappearance, occlusion, split, merge, a new object, or a lifecycle transition.

R0's mathematical disjointness (positive margin `>= 0.08` with mutual-best) means
at most one `SUPPORTED` pair per source and per target observation. If that
invariant is violated, P2C fails closed without a tie-break
(`test_supported_disjointness_violation_fails_closed_without_tiebreak`).

## 6. Frozen acceptance binding

New trusted Change `ApplyTemporalIdentitySelectionChange` atomically binds:

- the exact R0 evidence;
- the exact selected `inference_ids`;
- the exact selection evidence;
- the exact delegated `PromoteTemporalIdentityChange`.

Reference order is exact: R0 evidence, then selection evidence.

`apply` ordering:

1. `delegated_promotion.apply(document)`;
2. append the selection evidence **only after** the promotion succeeds.

An R1 conflict fails the whole Change / Transaction closed. It is impossible for
the identity promotion to partially succeed while the selection evidence fails,
and impossible for the selection evidence to be written while the promotion
fails. Atomicity is provided by `Transaction.apply`'s document copy.

The ChangeAuthority registered for it exposes exactly the two existing actions
`promote_temporal_identity` and `attach_analysis`; the intent function reuses
`_promote_temporal_identity(change.delegated_promotion)` plus the composite
`attach_analysis` intent. Both actions are enforced by the existing policy gate
(`test_both_existing_policy_actions_are_enforced`). No new policy action exists.

## 7. Frozen dedicated verifier

The acceptance-time verifier `_verify_temporal_identity_selection`:

- re-reads the exact R0 evidence;
- derives every `SUPPORTED` candidate;
- derives the exact selected `inference_ids`;
- enforces exact order;
- rejects subset / superset / reorder / duplicate;
- requires the delegated promotion to map one-to-one onto the expected
  `SUPPORTED` candidates;
- reuses the frozen R1 promotion verifier (`_verify_temporal_identity_promotion`);
- re-derives the selection evidence and requires exact canonical byte equality.

Frozen adversarial properties:

- R0 `SUPPORTED [A, B]` with promotion `[A]` → **REJECT**;
- R0 `SUPPORTED [A, B]` with promotion `[A, B]` but selection evidence `[A]` →
  **REJECT**;
- tampered selection evidence → **REJECT**;
- extra / reordered / duplicated selection → **REJECT**.

## 8. Frozen R1 delegation

P2C does not implement a second temporal identity system. It delegates to
`TemporalIdentityPromotionAdapter` / `PromoteTemporalIdentityChange`. Frozen R1
retains `temporal_identity_id`, `observation_owner`, stable identity reuse,
same-owner continuation, `TEMPORAL_IDENTITY_CONFLICT`, and conflict atomicity.

P2C must not merge stable identities, rename an identity, choose between
conflicting owners, skip a conflicting `SUPPORTED` correspondence, or generate
stable ids independently.

## 9. Selection evidence

- schema: `svm-temporal-identity-selection-0.1`
- media: `application/vnd.svm.temporal-identity-selection+json;version=0.1`
- kind: `DERIVED`

It records at least: the exact R0 evidence id, the source observation artifact,
the frame ticks, every R0 candidate (`candidate_id`, `inference_id`, original R0
`status`), the selected `inference_ids`, the excluded `UNCERTAIN` / `REJECTED`
ids, deterministic counts, and the P2C policy / adapter identity
(`adapter:temporal-identity-selection`, version `0.1`, policy
`svm-temporal-identity-selection@0.1`).

It adds no new score, confidence, match status or lifecycle interpretation.

## 10. Golden / focused acceptance

Fixture `examples/042-temporal-identity-selection/observations.json` supplies a
deterministic two-frame primitive observation scene (a canonical
`svm-primitive-observations` artifact; there is no AVI in this fixture). It
contains no preassigned R0 scores or statuses. The focused tests import the
canonical observation bytes, run frozen R0, accept the R0 evidence, and only then
invoke P2C. Frozen R0 produces 12 candidates: 2 `SUPPORTED`, 4 `UNCERTAIN`,
6 `REJECTED`.

The Golden proves: multi-primitive R0 input; multiple disjoint `SUPPORTED`; P2C
selects all `SUPPORTED`; `UNCERTAIN` / `REJECTED` are excluded; stable identities
are delegated through R1.

Focused coverage actually present (`tests/test_temporal_identity_selection.py`,
19 tests):

- `test_golden_selects_both_with_exact_order_and_exclusion_audit` — happy path:
  both `SUPPORTED`, exact order, exclusion audit, deterministic proposal;
- `test_zero_supported_uncertain_only_and_rejected_only_abstain` — zero /
  `UNCERTAIN`-only / `REJECTED`-only abstain;
- `test_one_supported_delegates_normally` — single `SUPPORTED`;
- `test_independent_runs_have_identical_proposals_revisions_and_documents` —
  determinism;
- `test_forged_stable_id_is_rejected_by_frozen_r1_apply` — forged stable id;
- `test_resolved_but_unaccepted_r0_rejects_at_acceptance` — unaccepted R0;
- `test_owner_reuse_and_same_owner_idempotency` — owner reuse and same-owner
  idempotency;
- `test_owner_conflict_at_proposal_and_acceptance_is_atomic` — different-owner
  conflict, atomic;
- `test_primitive_permutation_preserves_r0_order_and_selected_identity_subjects` —
  permutation determinism;
- `test_subset_extra_duplicate_and_reordered_promotions_reject` — subset / extra /
  duplicate / reordered promotions;
- `test_subset_superset_duplicate_and_reordered_selected_ids_reject` — subset /
  superset / duplicate / reordered selected ids;
- `test_selection_evidence_tamper_rejects_exact_bytes_and_provenance` — tampered
  evidence bytes and tampered media / kind / provenance;
- `test_wrong_policy_reference_and_delegated_type_reject` — wrong policy,
  wrong delegated change type, crossed references;
- `test_exact_correspondence_fields_and_r1_record_type_are_bound` — forged
  correspondence fields and record type;
- `test_malformed_r0_authority_fails_closed_at_proposal_and_acceptance` —
  malformed / non-canonical R0 authority;
- `test_supported_disjointness_violation_fails_closed_without_tiebreak` —
  disjointness violation;
- `test_request_authority_and_unaccepted_r0_reject` — request authority and
  forbidden caller options;
- `test_stale_base_rejects_without_mutation` — stale base;
- `test_both_existing_policy_actions_are_enforced` — the two existing actions.

Every rejection asserts HEAD, Revision count and Document are unchanged. No
coverage is claimed beyond these tests.

Implementation note: the adapter is imported directly from
`svm.adapters.temporal_identity_selection` (no package-root eager export, per the
P2B import-cycle lesson). There is no P2C CLI subcommand; CLI preview/accept
packaging remains a non-semantic follow-up, and preview / acceptance are available
through the adapter and `ProposalAcceptor` APIs.

## 11. CI acceptance

Frozen implementation baseline:

```text
887596516ea977ce80dfc3c035ed881558b99ee2
```

GitHub CI matrix (workflow `CI`, job `quality`,
`.github/workflows/ci.yml`):

- Ubuntu / Python 3.11 PASS
- Ubuntu / Python 3.12 PASS
- Windows / Python 3.11 PASS
- Windows / Python 3.12 PASS

## 12. Frozen non-goals

P2C explicitly does not implement: cross-interval aggregation, transitivity,
temporal chain construction, identity merge, lifecycle inference, deletion,
disappearance, appearance, occlusion, split / merge, Track authoring, motion
target binding, Camera inference, anchor / reference selection, or semantic role
inference. P2C is pairwise-selection authority only.

## 13. Trust boundary

P2C validates the accepted canonical R0 evidence and does not recompute R0
correspondence scoring from primitive observations. This is inherited from the
frozen R0 / R1 trust model. P2C must not reopen or silently strengthen R0 / R1
verification semantics. A future
"observation -> acceptance-time full R0 re-derivation" is an independent hardening
slice, not P2C polish.

## 14. Phase boundary

Any future change to the ALL-`SUPPORTED` rule, the pairwise-only scope, the
R0 / R1 authority split, identity ownership semantics, or the selection acceptance
binding must not be called P2C polish. P2C may only reopen for a demonstrated bug.
The next semantic slice is not defined here, and P2D is not designed.

## 15. Change control

P2C is FINAL / FROZEN at the baseline above. After this freeze, the P2C adapter,
its policy / schema / media identities, the ALL-`SUPPORTED` selection rule, the
pairwise-only scope, the `ApplyTemporalIdentitySelectionChange` binding, the
dedicated verifier and the selection-evidence schema must not change silently. Any
change to P2C output must be an explicitly versioned slice with updated
specifications, fixtures and tests.