# Conservative Group Candidate Inference v0.1

## Status and boundary

Golden Q v1 is normative. It consumes frozen Golden Q v0 geometric evidence
and accepted primitive geometry, color, and Render Stack data. It emits
reviewable `GroupCandidate` inference evidence. It SHALL NOT emit semantic
labels, materialize groups, mutate hierarchy or Render Stack order, depend on
AI/VLM execution, or define motion semantics.

Acceptance appends the immutable inference Artifact only. Accepting an
inference Proposal is not Group Promotion and leaves the Document without a
group definition.

## Identity

`candidate_id` identifies only the canonical sorted unique member Entity IDs.
It SHALL NOT depend on scores, status, confidence, evidence versions, or policy
version. `inference_id` additionally identifies the exact canonical Q v0 source
Artifact IDs, evidence vector, scores, status, and scoring policy. Equivalent
feature values derived from different evidence Artifacts SHALL NOT share an
inference identity. Re-scoring one member set therefore creates a new inference
about the same candidate subject.

## Candidate judgment

Each candidate records `SUPPORTED`, `UNCERTAIN`, or `REJECTED`, an evidence
vector, `positive_score`, `conflict_score`, `confidence`, and
`policy_version`. These are candidate judgment states, not Document states.
High positive support SHALL NOT suppress conflict. Ambiguous, conflicting, or
threshold-adjacent evidence SHALL produce `UNCERTAIN`.

`SUPPORTED` means only that a hypothesis is worth further consideration.
`REJECTED` records explicit counter-evidence. Neither state grants mutation
authority. A later, separately specified Group Promotion milestone is the only
place a selected and independently validated hypothesis may become accepted
work semantics.

## Deterministic baseline

Policy `svm-pop-group-scoring-policy@0.1` generates pair subjects only and uses
full masks, topmost coverage edges, IoU overlap, smaller-member containment,
boundary proximity, color similarity, size ratio, Render Stack distance, and
horizontal alignment similarity. The latter measures only size similarity and
vertical center alignment; it SHALL NOT be represented as bilateral symmetry.
Inputs, weights, thresholds, abstention rules, and canonical numeric precision
are versioned. Equivalent inputs and policy produce byte-identical Artifacts.

The baseline intentionally prefers missed groups over false groups. Future
geometry-only, Q-v0-assisted, and VLM-assisted policies remain distinct
inference identities so they can be evaluated through ablation without
changing candidate subject identity.
