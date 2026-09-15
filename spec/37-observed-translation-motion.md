# Observed Translation Motion Evidence v0.1

Status: normative Golden S0.

## Boundary

S0 derives deterministic translation observations only from an existing R1
temporal identity and the exact accepted R0 correspondence Artifacts named by
its promotion provenance.

```text
promoted temporal identity + exact R0 inference
-> verified dx/dy interval
-> evidence-only Proposal
```

**Observed Motion Evidence is not an Animation Track.** A temporal identity is
an identity for external observations, not an Animation target. Acceptance may
append only the derived Artifact reference; it creates no Entity, Group, Track,
or Keyframe and changes no construction, geometry, Style, Presentation, Render
Stack, animation, or temporal identity definition.

## Evidence identity

`svm-r0-displacement-observation-policy@0.1` copies the two finite components of
the exact R0 candidate `displacement`. The Adapter accepts no displacement
option. Each canonical interval records its temporal identity, ordered ticks and
observations, exact candidate and inference IDs, R0 Artifact ID, R1 promotion
policy, and S0 policy. Its ID hashes that complete content.

For a promoted chain A->B and B->C, S0 emits two independently attributable,
tick-ordered intervals. It performs no smoothing, interpolation, velocity
fitting, missing-frame inference, or extrapolation.

## Acceptance verification

The registered Core Change resolves both the new Derived Artifact and every
accepted R0 source reference. It reconstructs the complete expected payload
from an exact temporal-identity snapshot and the selected promoted inference
IDs. A changed identity, forged endpoint, provenance, source Artifact, dx/dy,
policy, or payload fails before commit. Acceptance is atomic and evidence-only.
