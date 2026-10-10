# P2D-B0 — Versioned Representation-Target Consumer Contract (design only)

Status: **DESIGN CONTRACT / NOT IMPLEMENTED / NOT FROZEN**.

Design baseline: `38abfde2a299a8d024cbff38b22698c48cc7f1ff`, where the bounded
present-time representation certification (spec/80 v0.1) is frozen for its
bounded profile. This document specifies a future consumer that turns
independently replayed Spec80 certifications into proposed frozen Motion Target
Bindings. It does not implement P2D-B, register a Change, produce an Artifact,
create a Golden, or reinterpret P2D-A. P2D-B remains **BLOCKED**; this document
is not authorization.

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
transaction message or a caller list SHALL NOT establish authority. For every
reserved-media reference the consumer SHALL:

1. require a matching admission event in the authenticated ancestry; references
   without an event are **data**: they are excluded from authority, cannot
   satisfy equivalence, cannot create conflicts and cannot be selected;
2. independently replay the claim through the Spec80 v0.1 semantics — the
   `admitted_associations`-equivalent contract: complete witness authentication,
   reproduction of the record at its own recorded base, exact descriptor and
   byte agreement, and current-base applicability per spec/80 §5–§6;
3. treat an event-bearing claim whose bytes cannot be resolved or reproduced as
   a hard verification failure (`REJECT`, §5) — never as data, never as a
   silent omission;
4. map the replayed association `{subject_id, temporal_identity_id, group_id}`
   to the current base: the identity and Group must each exist exactly once, and
   their current definitions must canonically equal the certified
   representation projection (already required by replay; re-checked here for
   the current base).

Exactly one applicable certification per identity may be `SELECTED`-eligible.
The consumer never invents a target for an identity without an applicable
certification, and never widens a claim's scope.

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
| `NO_ADMITTED_ASSOCIATION` | The universe contains zero genuinely admitted certifications (reserved bytes without events are data) |
| `NO_CERTIFICATION_FOR_IDENTITY` | Admitted certifications exist but none addresses this identity |

`ABSTAIN` is the correct outcome for a Document where certification simply has
not happened yet. A fresh, genuine certification proposal could legitimately
fill this state; the consumer must not guess a target in the meantime.

### 4.3 REJECT

An identity (or, where noted, the whole proposal) is `REJECT` iff evidence
claims authority but fails verification, applicability or uniqueness. Stable
codes:

| Code | Condition | Scope |
| --- | --- | --- |
| `ALREADY_BOUND` | Identity or its resolved Group already participates in an accepted `motion_target_bindings` entry; the existing binding id is recorded | identity |
| `COMPETING_ASSOCIATION` | Two or more non-equivalent admitted claims share the identity or the Group | whole proposal |
| `AMBIGUOUS_ASSOCIATION` | Two or more equivalent admitted claims exist (duplicate descriptors / duplicate evidence) | whole proposal |
| `MISSING_ASSOCIATION_ARTIFACT` | An event-bearing claim's required bytes are unresolvable in the accepted repository | claim endpoints |
| `UNREPLAYABLE_ASSOCIATION` | An event-bearing claim fails independent Spec80 replay at its own base (bytes, descriptor, event binding, provenance mismatch) | claim endpoints |
| `REPRESENTATION_MODIFIED` | The certified Group / member Entities / Operations / bindings / styles / render order / construction provenance no longer canonically match the certified representation (spec/80 §5) | claim endpoints |
| `IDENTITY_EXTENDED` | The identity's current definition is not exactly the certified definition (extra bindings, extra provenance, merged owners) | claim endpoints |
| `DEPENDENCY_CHANGED` | A required source / manifest / receipt / membership / identity / R0 descriptor changed or was removed | claim endpoints |
| `COVERAGE_INCOMPLETE` | The certified observation/membership coverage does not reproduce completely at the current base | claim endpoints |
| `TRACKED_REPRESENTATION` | A Track targets the Group, a member Entity or a member geometry Operation | claim endpoints |
| `HISTORY_BROKEN` | The single-parent continuity or Group birth transition required by spec/80 §4–§5 cannot be authenticated | claim endpoints |

`REJECT` is deterministic: no tie-break, no best-pick, no winner selection, no
replacement of an existing binding. A whole-proposal rejection produces no
Proposal, no evidence and no mutation.

### 4.4 Global selection semantics

- `SELECTED` pairs are proposed **ALL-or-none** in one proposal, in canonical
  identity-id order — never one best pair.
- Two identities contending for one Group cannot both be `SELECTED`; this state
  is reachable only through evidence defects and is therefore `REJECT`
  (`COMPETING_ASSOCIATION`), not a tie-break.
- Zero `SELECTED` pairs → abstention at the proposal level: no Proposal, no
  evidence artifact, no mutation (`ABSTAIN / ZERO_SELECTED` proposal outcome).
- `ABSTAIN` identities remain visible in the complete evaluation; they never
  become `SELECTED` through any inference.
- Precedence: `ALREADY_BOUND` is determined from the complete authenticated base
  binding state and takes precedence over unresolved or failing certification
  evidence for that endpoint. Already-bound identities and Groups do not
  participate in contention, matching P2D-A §5.1 precedence with this
  contract's own code.

## 5. Failure behaviour (D)

| Condition | Outcome | Code |
| --- | --- | --- |
| Missing artifact for an event-bearing claim | Fail-closed REJECT; must surface as the stable code, never an unhandled exception | `MISSING_ASSOCIATION_ARTIFACT` |
| Tampered / unreproducible claim bytes with a genuine event | REJECT | `UNREPLAYABLE_ASSOCIATION` |
| Modified Group, member geometry, membership, style, render order or provenance | REJECT | `REPRESENTATION_MODIFIED` |
| Identity extension beyond the certified definition | REJECT | `IDENTITY_EXTENDED` |
| Changed / removed required dependency descriptor | REJECT | `DEPENDENCY_CHANGED` |
| Incomplete observation or membership coverage | REJECT | `COVERAGE_INCOMPLETE` |
| Relevant sampled Track on the representation | REJECT | `TRACKED_REPRESENTATION` |
| Birth / continuity history not authenticable | REJECT | `HISTORY_BROKEN` |
| Already-bound identity or Group | REJECT; existing binding recorded; no replacement | `ALREADY_BOUND` |
| Competing non-equivalent claims | Whole-proposal REJECT | `COMPETING_ASSOCIATION` |
| Duplicate equivalent claims | Whole-proposal REJECT | `AMBIGUOUS_ASSOCIATION` |
| Zero admitted certifications | ABSTAIN; no Proposal | `NO_ADMITTED_ASSOCIATION` |
| No certification addresses the identity | ABSTAIN for that identity | `NO_CERTIFICATION_FOR_IDENTITY` |

None of these outcomes ever produce a substitute target. A rejection caused by
`REPRESENTATION_MODIFIED`, `IDENTITY_EXTENDED`, `DEPENDENCY_CHANGED`,
`COVERAGE_INCOMPLETE` or `HISTORY_BROKEN` is permanent for profile v0.1 (spec/80
§5 continuity cannot be re-established after the edit); the affected pair needs
a separately admitted future applicability profile. `ABSTAIN` states are the
only ones a future certification proposal may legitimately resolve.

## 6. Bound / unbound state and S1 authority (E)

Two states exist for an identity/Group pair:

```text
state U — unbound; a currently applicable certification exists
          -> eligible for SELECTED -> frozen binding proposal
state B — bound by an accepted Motion Target Binding (S1)
          -> authoritative; consumer reports ALREADY_BOUND and never touches it
```

Normative rules:

1. After a legal frozen S1 binding is accepted, that binding remains fully
   authoritative for its own semantics. The consumer SHALL NOT revoke, replace,
   rebind, re-point or "refresh" it — not even implicitly.
2. Spec80 v0.1's non-applicability for an identity or Group once a binding
   addresses it (spec/80 §5, "blocks this profile") is an **eligibility rule for
   NEW certifications only**. It is not a revocation of the existing binding,
   must not be reported as one, and must not cause a previously legal binding to
   be dropped from any enumeration.
3. A subsequent consumer run over the same Document classifies the bound
   identity (and any identity resolving to the bound Group) as
   `REJECT / ALREADY_BOUND`, recording the existing binding id — auditable
   exclusion, exactly one evaluation entry each.
4. One-to-one ownership (one T per binding, one G per binding) is enforced by
   the frozen binding Change and Document validation; the consumer must not
   duplicate or weaken that check, and must not propose a second binding for an
   already-consumed endpoint even when a stale applicable certification exists.
5. `ABSTAIN` and `ALREADY_BOUND` are distinct: the former is missing evidence,
   the latter is proven existing ownership.

## 7. Proposal, preview and atomic materialization (F)

1. **Read-only derivation.** Enumeration, acquisition, classification and
   proposal construction are pure: they must not mutate any accepted state.
2. **Preview is read-only.** Preview output is derived from the same pure
   derivation as acceptance; preview must not commit, must not write repository
   artifacts outside the ordinary local import used by existing adapters, and
   must not create an admission event.
3. **No new authority shortcut.** Materialization SHALL go through the existing
   `ChangeAuthority` / `ProposalAcceptor` boundary with exactly one registered
   composite Change. No direct `RevisionStore` mutation, no trusted-commit
   bypass, no new policy action, no new ProposalAcceptor capability, no
   verification-free fast path.
4. **Authenticated base.** The composite Change SHALL reuse the proven spec/70
   §10–§11 design: complete base-Document snapshot, detached Revision witness,
   existing `source_revision_resolver`, complete closure re-derivation, and a
   pre-mutation `apply` guard requiring canonical equality with the
   authenticated snapshot. A supplied snapshot or projection without this base
   commitment is insufficient.
5. **Frozen delegation.** For every `SELECTED` pair the consumer delegates to
   the frozen `TemporalMotionTargetBindingAdapter` /
   `BindTemporalMotionTargetChange` with exactly the pair. Binding id formula,
   snapshot hashing, stale checks, one-to-one conflicts and Document mutation
   remain exclusively the frozen implementation's duties — the consumer must
   not copy them.
6. **Evidence.** One versioned evidence artifact accompanies an accepted
   proposal (separate schema/media from P2D-A; exact identity reserved at
   implementation). It records the complete per-identity classifications, all
   audited claims with replay outcomes, existing bindings for `ALREADY_BOUND`
   entries, the selected pairs in canonical order, and deterministic counts.
   It records no geometry, distance, similarity or caller metadata as authority.
7. **Atomicity.** Selected pairs, delegated binds and the evidence reference
   publish as one atomic transaction. Rejections (verification, policy, final
   validation, delegated failure) leave HEAD, Revision count, Document, Groups,
   identities, bindings and reference universe unchanged; no partial mutation
   and no evidence append after partial failure.
8. **Existing intents only.** The registered action set is exactly
   `bind_motion_target` (per delegated pair, from the exact delegated records)
   plus `attach_analysis` on `document`.

## 8. Distinct authorities (G)

Three authorities remain separate and must not be conflated:

```text
evidence authority   — Spec80 certification + its Core admission event:
                       proves the current T <-> G relationship
consumer authority   — complete enumeration + classification:
                       decides which certified pairs are proposed, nothing else
binding authority    — frozen S1 Change + Document validation:
                       decides final binding legality and owns binding identity
```

The consumer's selection is not proof of the relationship, and the
certification is not authorization to bind without the frozen acceptance path.
No consumer-side signal — distance, similarity, sibling Group adjacency, sole
unbound Group, "obvious" pairing — may substitute for a missing certification.
Caller-supplied `temporal_identity_id`, `group_id`, `entity_id`, thresholds,
baselines, Camera or Track inputs are not part of this consumer's request
authority (document scope, no options, no artifact-id selection).

## 9. Golden and adversarial matrix (H — design only)

**Positive Golden (future, not implemented in this round).** Reuse the exact
Golden 046 chain — the admitted Spec76/77 ownership, accepted Spec79 whole
identity `temporal-identity:f89cc670dc7d6d8f54dd519532d525346817425825949ded13a79daae45aacbf`,
existing Spec78 Group `group:1f24284859439580faac31e69df1aa7bf6a1a28c450d8ddae2e3b42e48b656ac`
and the admitted certification
`artifact:6ee8fd89abc03a3094d0e1b1fbc4fbd2043345bc7ff5418d2adbe7aee6262f47`
(baseline Revision `revision:29f30d08a83e2db47bcf01db6acb28f1468e2792a38c94417b4435d52f449e87`).
Expected assertions: exactly one `SELECTED` pair; preview mutates nothing;
acceptance adds exactly one `motion_target_bindings` entry with the frozen
`policy_identity` `svm-explicit-motion-target-binding@0.1`; no Track, Keyframe,
Entity, Group, TemporalIdentity or artwork-rendering byte changes; deterministic
rerun reproduces identical Proposal/evidence/Revision identities; the admitted
certification reference and complete dependency closure remain untouched.

**Adversarial matrix (required when implemented; no test is created now).**

| # | Case | Required outcome |
| --- | --- | --- |
| 1 | Certification bytes present, no admission event (generic/low-level append) | Data; excluded from authority; `NO_ADMITTED_ASSOCIATION` abstention when it is the only candidate |
| 2 | Genuine event, tampered bytes / descriptor | `UNREPLAYABLE_ASSOCIATION`, fail-closed |
| 3 | Genuine event, artifact unresolvable | `MISSING_ASSOCIATION_ARTIFACT` — stable domain rejection, never an unhandled `KeyError` |
| 4 | Group / member geometry / membership / style / render order modified after certification | `REPRESENTATION_MODIFIED`; existing bindings untouched |
| 5 | Identity extended (extra binding/provenance) or aliased | `IDENTITY_EXTENDED` |
| 6 | Required dependency descriptor changed / removed | `DEPENDENCY_CHANGED` |
| 7 | Coverage incomplete at current base | `COVERAGE_INCOMPLETE` |
| 8 | Relevant Track on Group / member / Operation | `TRACKED_REPRESENTATION` |
| 9 | Two non-equivalent admitted claims sharing T or G | Whole-proposal `COMPETING_ASSOCIATION`, no tie-break |
| 10 | Duplicate equivalent admitted claims | Whole-proposal `AMBIGUOUS_ASSOCIATION` |
| 11 | Already-bound identity and/or Group, with a stale applicable certification | `ALREADY_BOUND` with existing binding recorded; no replacement; existing binding remains authoritative |
| 12 | Forged witnesses / unanchored history / invented event | `HISTORY_BROKEN` or rejection at witness authentication |
| 13 | Omitted identity, claim or required artifact from transport or evaluation | Reject incomplete universe; no selective shortlist |
| 14 | Subset attack: two `SELECTED` pairs, proposal keeps one | Reject: `SELECTED` pairs must equal the complete derivation |
| 15 | Uncertified identity with an "obviously matching" Group | `ABSTAIN / NO_CERTIFICATION_FOR_IDENTITY`; never selected by proximity or sole-candidate inference |
| 16 | Stale base after proposal | Ordinary acceptance rejects before verification |
| 17 | Policy denial / delegated binding failure / post-verification failure | Atomic rollback; HEAD, Document, bindings, references unchanged |
| 18 | Deterministic rerun | Identical proposal, evidence, Revision identities |
| 19 | No Track creation in every positive case | Frozen behaviour only; consumer adds no animation |
| 20 | Preview isolation | Preview mutates no accepted state and emits no admission event |

## 10. Performance budget and optimization direction (I)

Observed characteristics (from the spec/80 Gate): each derivation replays
complete history per call; nested re-authentication occurs through the Spec79
identity reproduction; admitted-claim replay recursion depth grows with the
number of admitted claims; deep chains fail closed (possibly via
`RecursionError`).

Initial budget (design):

- one consumer run over the bounded Golden 046 fixture SHOULD complete within a
  small constant multiple of a single Spec80 verification pass (the consumer
  adds enumeration and classification, not new replay work);
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
- any change to existing animation, rendering, Camera, P2A/P2B/R0/R1/P2C/S0/S1
  or Document semantics;
- substitution of P2D-A's provenance rules (P2D-A stays exactly as specified).

## 12. Open decisions, implementation split and readiness

Open decisions (not decided by this draft):

1. Whether a future P2D composite should ever combine certification-based pairs
   with P2D-A provenance-based pairs in one proposal, or keep separate profiles
   with separate evidence schemas (current design: separate).
2. The exact name/version of the composite Change and evidence schema/media
   (reserved at implementation; must be a closed-world registry addition).
3. The numeric performance budget and any per-proposal claim bound (§10).
4. Whether `ALREADY_BOUND` consumption states should additionally record the
   archived certification descriptor for audit display (no authority effect).

Suggested Codex implementation split (future, each independently reviewable):

- **B0-1** — read-only derivation: enumeration, acquisition via Spec80 replay,
  classification, versioned reason codes, proposal-level abstention; pure
  focused unit tests. No acceptance surface.
- **B0-2** — composite Change + `ChangeAuthority` registration + independent
  verifier (authenticated snapshot/witness, complete closure re-derivation,
  Spec80 replay integration, apply guard, frozen delegation).
- **B0-3** — adapter + Proposal + evidence artifact schema + preview isolation +
  policy intents (`bind_motion_target`, `attach_analysis`).
- **B0-4** — Golden fixture (046 chain) + full adversarial matrix + regression +
  freeze update of this document.

Readiness verdict for this round:

```text
P2S-F1B freeze:                 FROZEN (bounded v0.1 profile only)
P2D-B0 contract draft:          PRESENT (this document, design only)
Conditions to ENTER a P2D-B0 design gate: SATISFIED
P2D-B implementation:           NOT AUTHORIZED — remains BLOCKED
```

The conditions to enter a design gate are satisfied because the consumed
authority (spec/80 v0.1) is frozen, the consumption primitive
(`admitted_associations`) exists and is independently replayed, the frozen
binding boundary (S1) is unchanged, and no runtime change is required to review
this contract. This is not a READY state: implementation awaits an explicit
design-gate decision, and P2D-B must not be marked READY by this document.