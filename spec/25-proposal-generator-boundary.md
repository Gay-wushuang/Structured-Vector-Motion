# Proposal Generator Boundary v0.1

## Status

Editor Vertical Slice 05 is normative. It proves that candidate generation is
a replaceable capability outside Editor state, Revision storage, and Proposal
acceptance authority. No neural model is required by this slice.

## Boundary

```text
DocumentEditorSession
-> AdapterRequest(base Revision, Document snapshot, requested scope)
   + independently constructed AnchoredRegenerationContract
-> AnchoredProposalProvider
-> ProposalCandidate[]
-> ProposalAcceptor.validate_anchored()
-> preview detached candidate Document
-> ProposalAcceptor.accept_anchored()
-> child Revision
```

The Editor constructs trusted protection and regeneration policy independently
of the provider. A provider receives those facts for context but cannot widen
them. Core derives actual impact from registered Changes and remains the only
authority that can validate or accept a Proposal.

`AnchoredProposalProvider.generate()` accepts an `AdapterRequest`, the trusted
Anchor contract, and an optional Artifact resolver. It returns stable candidate
labels paired with complete Proposals. Candidate labels must be unique and the
set must be non-empty. The provider MUST NOT mutate the Revision Store or return
an accepted Revision.

## Deterministic reference provider

`DeterministicProposalProvider` contains the former Editor-local A/B/C fixture
logic. Its identity is `svm-deterministic-proposal-provider@0.1`. It proposes
only registered `SetOperationParameterChange` records for the exact highlight
`cx`/`cy` scope. It exists to prove dependency inversion, not as a semantic AI
model.

A future Primitive Painter, Motion LLM, procedural system, or research model
replaces only this provider. It must not require changes to Editor preview,
Anchor protection, Proposal validation, acceptance, or Revision branching.

## Vertical Slice 05

The executable slice proves:

1. an injected provider receives an immutable base snapshot and exact scope;
2. the Editor displays the provider's candidate set without creating a Revision;
3. preview and acceptance use the same complete Core authority validation;
4. Edit Policy denial fails identically during dry run and acceptance;
5. the deterministic provider preserves the existing A/B/C product behavior;
6. replacing the provider does not change Editor, Revision, or protection logic.
