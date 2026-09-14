# Temporal Correspondence Evidence v0.1

Status: normative Golden R v0 baseline.

## Scope

This slice consumes one immutable, canonical two-frame primitive-observation
Artifact and derives conservative pairwise correspondence evidence. It does not
invoke a Primitive Provider or Animosaics, mutate an Entity, create a Track, or
propagate a user edit.

```text
two frozen primitive observation frames
-> deterministic pair evidence
-> SUPPORTED | UNCERTAIN | REJECTED
-> evidence-only Proposal
```

The input records canvas size and, for each observation, an ID, provider-native
primitive type, axis-aligned bounds, and six-digit RGB fill. Observation IDs are
unique within the Artifact and do not become Entity IDs.

## Evidence policy

`svm-bounds-correspondence-policy@0.1` compares every primitive across the two
frames using centroid proximity, bounding-box area similarity, RGB similarity,
and exact primitive-type agreement. The recorded support score is:

```text
0.45 centroid_proximity
+ 0.20 size_similarity
+ 0.20 color_similarity
+ 0.15 type_agreement
```

A pair is `SUPPORTED` only when it is the mutual best match, support is at least
`0.75`, and both alternative margins are at least `0.08`. A score below `0.35`
is `REJECTED`; every other case is `UNCERTAIN`. High support cannot erase an
ambiguity conflict. The candidate records the observed centroid displacement,
not an accepted motion Track.

Candidate subject identity depends only on the two ticks and observation IDs.
Inference identity additionally binds the exact source Artifact, evidence,
status, and policy identity.

## Acceptance boundary

Acceptance appends only the derived evidence Artifact reference. It leaves
Entities, construction, presentation, Render Stack, animation, and existing
Tracks unchanged. Promotion to a stable Entity correspondence and generation
of observed Tracks are later Golden R/S work.

User style edits remain ordinary non-destructive SVM Style Tracks. A future
promotion layer may bind those overrides through an accepted persistent Entity
identity; this evidence slice does not infer that authority.
