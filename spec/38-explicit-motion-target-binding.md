# Explicit Motion Target Binding v0.1

Status: normative for Golden S1.

## Boundary

A Temporal Identity is not an Animation Target. Observed Motion Evidence is not
a Target Binding. A Target Binding is not an Animation Track.

This slice records only an explicit one-to-one association between an existing
Temporal Identity and an existing transformable Group. It does not create a
Track or Keyframe, mutate a Group Transform, infer a target, or change observed
motion evidence.

## Proposal contract

The caller MUST provide `temporal_identity_id` and `group_id`. The Adapter MUST
NOT select a Group from names, bounds, semantic tags, geometry, or other
heuristics. Both endpoints MUST exist uniquely in the Proposal base snapshot.
The Group MUST have a valid existing static Transform.

Acceptance MUST pass through Preview, the closed-world Change Authority
Registry, policy enforcement, and one atomic Transaction. The Change source
revision MUST equal `Proposal.base_revision_id`. Exact Temporal Identity and
Group snapshots MUST still match when the Change is applied.

## Document representation

`motion_target_bindings` is an orthogonal top-level Document collection. Each
record contains a canonical content-derived ID, `temporal_identity_id`, a
`group` target with `group_id`, policy identity
`svm-explicit-motion-target-binding@0.1`, and provenance containing the source
Revision ID plus exact hashes of both endpoint snapshots.

The endpoint snapshot hashes are historical provenance describing the Temporal
Identity and Group at binding creation. They are verified against the captured
endpoint snapshots when the binding Proposal is accepted. Persistent Document
validation verifies their fields and hash syntax, but does not compare them to
the endpoints' current content: the validator does not own the historical
Revision snapshot needed to make that claim.

After acceptance, later valid extension of the same stable Temporal Identity or
later valid edits to the bound Group do not invalidate or replace the binding.
The binding follows their stable IDs, not frozen endpoint contents. Its ID
therefore remains independent of both endpoint snapshots.

Only Group targets are supported in v0.1. This reuses the Group Transform and
`CreateGroupTransformTrackChange` target semantics already defined by the
Animation system. Entity transform semantics and a second Animation target
system are prohibited.

## Conflicts and idempotence

- An unbound identity and unoccupied Group MAY be bound.
- Repeating the same identity/Group pair is idempotent and MUST NOT add a
  second semantic binding or replace its original provenance.
- Binding an already-bound identity to another Group MUST fail atomically.
- Binding another identity to an occupied Group MUST fail atomically.
- Missing, duplicated, invalid, or stale endpoints MUST be rejected.

The accepted change MUST leave Entities, Construction, Presentation, Render
Stack, Animation, observed-motion references, Temporal Identities, and Group
Transform values unchanged.
