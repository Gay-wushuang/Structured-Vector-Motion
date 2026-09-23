# Repeated-Frame Observation Occurrence Identity v0 (S10B)

Status: normative SVG producer extension; geometry-correct translation
`svm-geometry-correct-translation-authoring@0.1` remains frozen.

## Content and occurrence identity

Artifact identity remains a hash of immutable content. Identical SVG bytes at
different ticks MUST retain the same Artifact ID. No timestamp or synthetic
frame marker is inserted into SVG bytes.

`SVGGeometryOccurrenceAdapter` explicitly selects producer
`svm-svg-polygon-geometry-observation-producer@0.2` and policy
`svm-svg-polygon-geometry-observation-policy@0.2`. Its observation ID is
`observation:svg:` followed by SHA-256 of canonical bytes of this object:

```json
{
  "source_svg_artifact_id": "<content-addressed SVG ID>",
  "tick": 12,
  "shape_id": "<explicit selector>",
  "policy_identity": "svm-svg-polygon-geometry-observation-policy@0.2"
}
```

The same tuple MUST produce the same ID across adjacent interval requests.
Different ticks distinguish occurrences of the same content. Occurrence identity
does not create an Entity or establish Temporal Identity automatically.

The payload and media type remain primitive-observations v0.2: their existing
tick and opaque observation ID fields suffice. This is a versioned producer
identity contract, not a reinterpretation of all v0.2 observation IDs.
`SVGGeometryObservationAdapter` and default pure derivation retain policy @0.1,
its original hash inputs, provenance, and distinct-source requirement. Acceptance
recomputes the exact recorded policy; unknown policies and policy substitution
fail closed. Existing persisted evidence remains readable and verifiable.

## Two temporal slots, exact capabilities

Ticks MUST be non-negative integers with source tick strictly below target tick.
The explicit source/target selectors may reference the same SVG Artifact under
policy @0.2. The request lists exactly the distinct source blob IDs: one for a
repeated blob, two otherwise, with no duplicates, missing IDs, or extras.

The typed Change retains both temporal slots and their full references. Only
the two SVG references may coincide, and their descriptors MUST match exactly;
the output observation reference remains distinct. Document Artifact references
are deduplicated by content identity. Proposal dependencies likewise list each
blob once. Acceptance remains registered ChangeAuthority/Proposal mediated.

Provenance retains the ordered `source_svg_artifact_ids` pair, including repeated
IDs, and adds ordered `source_occurrences` records containing each source ID and
its tick. The selector and producer/policy version are recorded alongside them.
Acceptance reconstructs payload bytes and provenance from the resolved sources,
ticks, selector, and allowlisted policy. A forged tick, source, selector, ID,
payload, or provenance MUST reject atomically.

## Existing downstream semantics

For the supported asymmetric polygon subset, identical geometry produces a
SUPPORTED R0 candidate with zero bounds-center displacement. S0 retains that
zero displacement as observation evidence; S4 retains identity similarity
(rotation zero, scale one). Neither evidence contract changes.

Explicit R1 promotion can extend one Temporal Identity over hold → move → hold:
the shared endpoint has the same occurrence ID while other ticks have distinct
IDs. Entity identity and explicit motion target binding remain separate.
The existing single-anchor Camera pipeline accepts identity intervals. Frozen
geometry-correct authoring consumes verified world similarity after compensation
and creates constant tracks for an all-static sequence under existing authoring
contracts. This slice changes no similarity, compensation, or decomposition math.

`examples/032-repeated-frame-occurrences` and
`tests/test_repeated_frame_occurrences.py` exercise ticks 0, 12, 24, 36, repeated
rendered bytes, deterministic evidence/revisions, explicit recovery, legacy
verification, and atomic stale/forged rejection.

No multi-anchor consensus, automatic binding, missing-frame interpolation,
uncertainty, occlusion, noisy fitting, raster input, or Track/Camera replacement
is introduced. Matching still requires the existing exact supported geometry.
