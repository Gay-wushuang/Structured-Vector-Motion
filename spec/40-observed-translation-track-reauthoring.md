# Observed Translation Track Re-authoring v0.1

Status: normative Golden S3.

## Boundary

New observed motion evidence does not automatically update Document animation.
Re-authoring requires a new Proposal, an old-to-new Preview, and explicit
acceptance. Target equality is not ownership and an existing Track is not
permission to overwrite it.

The Adapter supports exactly two modes:

```text
no Group translate.x/y Tracks -> CREATE
one trusted observed-translation x/y pair -> REPLACE
anything else -> reject
```

Only Tracks carrying canonical `ObservedTranslationTrack` provenance for the
same accepted Motion Target Binding and authoring policy may be replaced. A
manual, unknown, mixed, or partial pair fails closed.

## Identity and provenance

The semantic animation target remains `(Group ID, property)`. A Track ID names
one exact authored result and therefore includes the evidence Artifact and
timebase. Re-authoring from new evidence creates new Track and Keyframe IDs; it
does not reuse IDs whose historical provenance described the old evidence.

Each owned Track records the authoring identity, Motion Target Binding ID,
evidence Artifact ID, and source Revision ID. This is deliberately narrow
lineage metadata, not a general provenance framework.

## Atomic replacement and staleness

The x/y pair is replaced by one registered Core Change on a transactional copy.
Both Tracks are replaced or neither is. Acceptance verifies the exact S0
Artifact, Binding snapshot, current Group baseline, old Track pair, new Track
definitions, source Revision, and expected final animation.

A pending replacement snapshot protects only that Proposal. It does not turn
the persistent S1 Binding into a frozen Group snapshot: a valid later Group
edit leaves the Binding intact, and a newly generated S3 Proposal captures the
new current baseline.

S3 adds no rotation, scale, interpolation, merging, override, or recovery
semantics.
