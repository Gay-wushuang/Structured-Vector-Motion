# Explicit Group Promotion v0.1

## Status

Golden Q v2 is normative. It promotes an explicitly selected `SUPPORTED`
Golden Q v1 candidate into one persistent, unlabeled `GroupDefinition` through
one atomic Proposal and Revision. It is the separate Promotion stage after
deterministic evidence and conservative inference.

## Group Definition

```text
GroupDefinition
|- id
|- kind = explicit-group
|- members[]
`- provenance
   |- candidate_id
   |- inference_id
   `- inference_artifact_id
```

Members are sorted unique existing Entity IDs. Promotion preserves member
identity, primitive geometry and style, construction, Render Stack order, and
all inference evidence. It adds no semantic role, motion-parent meaning,
occlusion meaning, transform, or AI label.

## Authority and staleness

Only an explicit `candidate_ids` request may create a Promotion Proposal. The
closed-world `PromoteGroupsChange` has the `promote_group` action and an
Artifact verifier that reconstructs the exact selected record from canonical
Q v1 inference evidence. `UNCERTAIN` and `REJECTED` candidates fail closed.

The inference Artifact must already be accepted. Its exact source Document hash
must match the current Document after removing only the inference reference
attached by Q v1. Missing members, changed geometry/style/construction,
different evidence, or any other incompatible source drift produces
`STALE_CANDIDATE` and requires re-inference.

Accepting Q v1 evidence is not promotion. Promotion is a separate dry-runnable
Proposal and one atomic Revision. Static Group Transform is specified
separately by Golden Q v3; Group Motion remains reserved for the later
Authoring Motion Slice.
