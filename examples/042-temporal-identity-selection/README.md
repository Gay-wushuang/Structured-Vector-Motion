# Golden P2C — Temporal Identity Selection

`observations.json` supplies a small deterministic two-frame primitive scene.
Like 041's controlled geometry, it uses two separated solid rectangles; an
additional green ellipse with two equally plausible targets makes ambiguity
explicit. The fixture contains no preassigned R0 scores or statuses.

The focused test imports canonical observation bytes, runs frozen R0, accepts
the R0 evidence, and only then invokes P2C. R0 produces 12 candidates:
2 SUPPORTED, 4 UNCERTAIN, and 6 REJECTED. P2C selects both SUPPORTED candidates
in R0 order and delegates their exact promotion to frozen R1. Non-selected
candidates are recorded as exclusions and have no deletion/lifecycle meaning.

```powershell
python -m unittest tests.test_temporal_identity_selection -v
```

The same fixture has small in-test variants for zero support, a single match,
ownership reuse, idempotency, conflicts, and primitive-order permutations.
Permutation preserves R0 candidate subject order, status, and selected binding
pairs. Exact observation bytes still define the source Artifact identity:
permuting the serialized input changes its Artifact ID, hence R0 inference IDs
and newly allocated R1 IDs on independent empty Documents. With existing owners,
R1 reuses the same stable identity set. P2C does not override these frozen rules.

P2C accepts one already accepted R0 Artifact and no options. Its only Change is
`ApplyTemporalIdentitySelectionChange`, with references in exact order:
R0 evidence, then selection evidence. The verifier re-derives ALL-SUPPORTED
selection and its audit bytes, checks correspondence order/content, and calls
the unchanged R1 verifier. R1 applies promotion before selection evidence is
appended, within the existing atomic Transaction copy.

The selection Artifact is DERIVED, with schema
`svm-temporal-identity-selection-0.1` and media
`application/vnd.svm.temporal-identity-selection+json;version=0.1`.
It records original statuses, selected/excluded inference IDs, counts, the
source observation Artifact, ticks, and exact R0 evidence identity. It adds no
scores or stable-identity semantics. Zero support raises
`TemporalIdentitySelectionError` without a Proposal or Document mutation.

Import directly from `svm.adapters.temporal_identity_selection`; there is no
package-root eager export. CLI preview/accept remains a non-semantic packaging
follow-up; preview and acceptance are available through the adapter and the
ordinary `ProposalAcceptor` APIs.
