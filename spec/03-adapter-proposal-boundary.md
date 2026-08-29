# Adapter and Proposal Boundary v0.1

System-wide definitions of Adapter, Artifact, Backend, Evaluator, Renderer, and
Exporter are provided by `05-system-boundaries.md`.

## 1. Rule

An external tool never receives a mutable Revision Store and never edits an
accepted SVM Document. It receives an isolated Document snapshot plus an
explicit request and returns a Proposal.

```text
Revision snapshot + scope + artifacts
                ↓
             Adapter
                ↓
 Proposal(Transaction + report + provenance)
                ↓
 preview / validate / accept / reject
```

This boundary applies equally to deterministic geometry libraries, optimizers,
AI models, importers, and research repositories.

## 2. Adapter request

An adapter request contains:

- `base_revision_id`;
- an isolated Document snapshot;
- an explicit target scope;
- evaluation quality;
- accepted artifact references;
- optional adapter-specific options.

The snapshot may be mutated inside an adapter process without affecting the
Revision Store. Such mutation has no formal meaning unless represented in the
returned Proposal transaction.

## 3. Proposal

A Proposal contains:

- a stable Proposal ID;
- the exact base Revision ID;
- generator identity, version, and provenance;
- one atomic Transaction containing proposed changes;
- an evaluation report with named metrics and constraint violations;
- content-addressed preview artifacts;
- optional confidence;
- explanatory notes.

A Proposal is descriptive and has no authority to commit itself.

When a Proposal changes Entity structure, it may include a typed
`ProposalPreview` containing Entity-level diffs and a proposed Render Stack.
Preview data is descriptive: acceptance still applies and validates the
Transaction rather than trusting the preview.

## 4. Acceptance

The v0.1 acceptor performs optimistic base-revision checking. If the active head
does not equal the Proposal base, acceptance fails as a conflict and the
adapter must be rerun or a future rebase process must create a new Proposal.

After the base check, the Proposal transaction is applied to a copy and the
resulting Document is fully validated. Only then is one new Revision committed.
Rejection creates no Revision.

Constraint and Edit Permission enforcement belongs in acceptance, not in
adapter-specific code. The supported v0.1 subset and fail-closed behavior are
defined in `09-policy-enforcement.md`.

## 5. Artifact discipline

Preview images, masks, model outputs, and imported geometry referenced by a
Proposal must be content-addressed before acceptance. Remote URLs, temporary
paths, and model conversation state are provenance or locators, never accepted
artifact identity.

## 6. Adapter packaging

Adapters live outside `svm` core semantics. They may translate external formats
into core Transactions, but must not introduce external repository objects into
the Document schema. Removing an adapter must not make an already accepted SVM
Document uninterpretable, unless the Document explicitly declares a separately
versioned operation-semantics extension.
