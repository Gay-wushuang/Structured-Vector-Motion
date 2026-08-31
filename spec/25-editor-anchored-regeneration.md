# Editor Vertical Slice 04 — Real Anchored Regeneration

## Status

This vertical slice is the first Editor interaction backed by the normative
Golden O branch-acceptance path. It adds no new Document or Core semantics.

The supported fixture is `examples/018-anchored-regeneration.svm.json`. The
Editor recognizes its explicit Operation IDs and presents human-readable locks
and scope choices. This fixture recognition is an Editor capability, not
semantic eye recognition.

## Interaction contract

```text
accepted base Revision
  -> trusted Editor creates AnchoredRegenerationContract
  -> deterministic generator creates pending Proposals A/B/C
  -> preview applies one Transaction to an isolated base snapshot
  -> no Revision
  -> accept_anchored()
  -> real child Revision
```

Every candidate remains bound to the base Revision recorded when generation
occurred. Accepting A changes the active HEAD but does not rebase B. Accepting B
therefore creates a sibling of A, not its child.

The fixture always protects `op:eye-frame.rx` and `op:unrelated.x`. The user may
allow `op:eye-highlight.cx`, `op:eye-highlight.cy`, or both. Candidate impact is
derived from registered `SetOperationParameterChange` values and must pass the
existing Golden O contract at preview and acceptance.

## Editor state

Pending candidates, selected preview, scope checkboxes, and branch layout are
discardable Editor State. They do not enter the SVM Document. A preview must
show its Proposal identity while the committed Revision label remains visible.
Changing scope clears pending candidates and any stale preview.

Accepted branches are real `RevisionStore` records. The common base and sibling
parent relationships are projected from the store rather than simulated in
JavaScript.

## Deliberate exclusions

The generator is deterministic and contains no AI, prompt, network, research
model, semantic detector, branch merge, Style mutation, or wildcard scope. A
future model may replace only the Proposal generator; it receives no additional
acceptance authority.
