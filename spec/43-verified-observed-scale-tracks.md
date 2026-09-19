# Verified Observed Scale Tracks v0.1

Status: normative Golden S5A.

S5A converts one already accepted S4 similarity Artifact and one explicit S1
Motion Target Binding into one previewed, explicitly accepted Group `scale`
Track. It never guesses a Group and never authors rotation or translation.

Similarity `scale.value` is a multiplicative source-to-target ratio. A Group
scale Track stores absolute `group.transform.scale`. Proposal creation captures
the current positive Group baseline and accumulates a contiguous interval chain:

```text
absolute(t0) = baseline
absolute(tN) = baseline * ratio0 * ... * ratioN-1
```

Observed scale confidence is component-specific. Overall similarity status need
not be `SUPPORTED` when `interval.scale.status` is independently `SUPPORTED`.
Rotation ambiguity is not scale ambiguity. Every used ratio must be finite and
positive, and every interval must form one ordered contiguous chain.

Existing scale Track does not grant permission to overwrite. S5A supports only
CREATE and fails closed when any Track already targets the bound Group scale.
Preview is pure and does not mutate the Document. Acceptance uses ordinary
Group Track and Keyframe Changes plus an artifact-bound verification Change
which independently recomputes the absolute samples, deterministic identities,
provenance, and complete expected animation result. A changed binding, Group
baseline, animation baseline, evidence Artifact, or source Revision makes a
pending Proposal stale.
