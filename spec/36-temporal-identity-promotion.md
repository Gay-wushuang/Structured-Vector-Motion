# Explicit Temporal Identity Promotion v0.1

Status: normative Golden R1.

## Boundary

R0 correspondence evidence remains a hypothesis. R1 is the only boundary in
this version that can turn an explicitly selected `SUPPORTED` inference into a
stable cross-frame observation binding:

```text
accepted SUPPORTED R0 evidence
-> explicit promotion Proposal and Preview
-> ProposalAcceptor
-> one atomic Revision
-> temporal identity binding
```

`UNCERTAIN` and `REJECTED` inferences cannot be promoted. Promotion neither
rewrites the R0 Artifact nor creates Animation Tracks, Keyframes, geometry,
Style, Presentation state, or Render Stack entries.

## Identity representation

R1 uses an independent top-level `temporal_identities` collection rather than
creating an Entity. An Entity is already the persistent identity of an accepted
artwork object; an R0 observation is external single-frame evidence and has not
yet been promoted into artwork geometry. Creating a geometry-free Entity here
would silently conflate those meanings.

Each temporal identity contains:

- a canonical `temporal-identity:` ID;
- sorted `(tick, observation_id)` bindings;
- sorted promotion provenance identifying the exact candidate, inference,
  evidence Artifact, evidence policy, and promotion policy.

When neither endpoint is bound, the ID is the content-derived hash of the R1
promotion identity, exact evidence Artifact ID, and candidate ID. Confidence,
geometry, color, and displacement do not define the stable identity.

## Binding cases

1. Neither endpoint is bound: create one identity and bind both.
2. One endpoint is bound: bind the other to the existing identity.
3. Both endpoints have the same identity: preserve that identity and make an
   exact repeated promotion idempotent.
4. Endpoints have different identities: fail with `TEMPORAL_IDENTITY_CONFLICT`.
   R1 never merges identities.

All cases are applied inside one Transaction copy. A conflict creates no
partial Document mutation.

## Acceptance verification

The registered Core Change verifier resolves the exact accepted R0 Artifact,
requires canonical R0 content and policy identities, finds the selected
inference, requires `SUPPORTED`, and reconstructs both observation endpoints.
Adapter-owned records cannot bypass this verification.

Observed motion, centroid-displacement conversion, user overrides, editing
propagation, Animosaics, optical flow, and new correspondence heuristics are
outside R1.
