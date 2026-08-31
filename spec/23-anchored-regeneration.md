# Anchored Regeneration v0.1

## Status

Golden Test O is normative. It defines a deterministic, model-independent
boundary for exploring candidate continuations from a protected Revision.

Anchored Regeneration is not Undo. Undo checks out an existing parent Revision.
A branch commits a new child from an explicitly named existing Revision.
Anchored Regeneration creates such a branch only after a Proposal's actual Core
Change impacts satisfy an exact protection and regeneration contract.

```text
Revision R1
   |-- pending Proposal A
   `-- pending Proposal B

accept A: R1 -> R2
accept B: R1 -> R3
```

Pending Proposals are candidate futures and are not nodes in the Revision graph.

## Contract

`AnchoredRegenerationContract` contains:

- `base_revision_id`: the immutable Revision from which every candidate starts;
- `anchor`: exact stable targets defining the retained decision point;
- `intent`: exact targets describing the user's already-confirmed edit fact;
- `protection`: exact targets a Proposal must not modify;
- `regeneration_scope`: the complete exact allowlist for Proposal changes.

Every target is a typed `(action, target, parameter)` triple matching a
ChangeAuthority intent. v0.1 has no wildcard, descendant selector, semantic
query, hierarchy expression, or natural-language authority. Every Anchor target
must also be protected. Protection and regeneration scope must be disjoint.
An anchored Proposal must contain at least one actual registered Change impact;
an empty Transaction cannot create a candidate branch.

Before scope comparison, Core validates every Contract target against the base
Revision. The action must be declared by the Change Authority Registry;
Operation parameters, Tracks, Keyframes, and Entities must exist; and
document-wide actions must name `document`. A malformed trusted protection
statement therefore fails instead of silently protecting nothing. Editors may
invoke the same public validation before presenting a Contract for acceptance.

Motion Keyframe impact uses the existing triple without widening the language:

```text
(set_keyframe_value, Track ID, Keyframe ID)
```

Edit Permission may still deny the action at Track granularity because policy
matching remains based on action and target, while Anchored Regeneration can
allow or protect individual Keyframes through the parameter field.

The confirmed `intent` records why candidates are being explored. It does not
grant mutation authority. Only `regeneration_scope` grants eligibility.
The contract is trusted user/editor policy input supplied independently at
acceptance; a Proposal generator cannot widen it by returning different notes,
preview metadata, or a self-authored scope.

## Acceptance authority

Core derives actual impact from every executable Change through the closed-world
Change Authority Registry. Proposal notes, preview metadata, generator claims,
and model output are never authoritative.

```text
registered Changes
       |
ChangeAuthority intent resolvers
       |
actual impacts
       |
       |-- intersects protection -> reject
       `-- not subset of scope   -> reject
```

Scope validation is an additional gate. Artifact verification, accepted
Document policies, atomic Transaction validation, and Document invariants still
run normally. Scope permission cannot override actor policy, and actor policy
cannot expand anchored scope. An unregistered wrapper Change fails before it can
execute.

`ProposalAcceptor.validate_anchored()` is the non-committing Core authority for
preview. It executes the same base, trusted Change, Anchor contract, Artifact,
Artifact-bound verifier, Edit Policy, Transaction, and final Document checks as
`accept_anchored()`, returning only a detached candidate Document. Acceptance
revalidates the unchanged Proposal and then commits it. Preview code MUST NOT
approximate authority by applying a Transaction directly.

## Branch acceptance

Ordinary `ProposalAcceptor.accept()` retains optimistic HEAD matching. Anchored
acceptance uses `accept_anchored()` and may target a non-HEAD Revision only when:

- the base Revision still exists;
- Proposal and contract name exactly the same base;
- the complete actual Change set passes protection and scope validation;
- every existing Artifact, Policy, Transaction, and Document check succeeds.

`RevisionStore.commit(base_revision_id, transaction)` already creates a child
whose `parent_ids` is exactly `(base_revision_id,)`. It does not require the base
to be HEAD. Accepting sibling candidates changes the active HEAD to the latest
accepted child but never mutates their common parent or earlier child.

## Golden O

The product example is a confirmed red-to-orange eye edit followed by optional
regeneration of downstream highlight/shading decisions. The executable fixture
does not introduce a Style Change merely for that story: it uses existing exact
Operation parameter Changes.

Golden O proves:

- a deterministic strict edit creates R1 from R0;
- two pending deterministic Proposals based on R1 create sibling R2 and R3;
- all four snapshots remain independently readable and valid;
- Entity and Operation identities remain stable;
- protected, outside-scope, and mixed transactions fail atomically;
- Motion scope distinguishes individual Keyframes on the same Track;
- misspelled actions and dangling Contract targets fail against the base;
- claimed impact cannot override ChangeAuthority-derived impact;
- existing Edit Permission denial remains effective;
- equivalent base, contract, and Proposal content produce the same Revision and
  Document identity.

## Deliberate exclusions

v0.1 includes no AI model, prompt system, Timeline or Canvas UI, Style mutation,
automatic eye recognition, semantic selection, wildcard scope, branch merge,
collaboration, impact prediction, or new Motion interpolation. Primitive
Painter, StarVector, OmniSVG, SVM-native models, procedural tools, and future
research systems may only act as Proposal generators outside this contract.
