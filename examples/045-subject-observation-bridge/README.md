# Golden F1A — source-backed whole-subject observation bridge

This Golden reuses the exact Spec75/76 two-triangle fixture. It first accepts
Spec76 through genuine Spec77 admission, then promotes the existing P2B part
observations through actual frozen R0/R1. The bridge adds one new whole-subject
observation at each covered tick and one distinct whole-subject TemporalIdentity.
The two part identities and all construction/presentation records are preserved.

| Tick | Complete source-backed membership | Half-open union bounds |
| --- | --- | --- |
| 0 | part-a + part-b, exact Spec76 occurrence | `[20, 20, 211, 174]` |
| 12 | part-a + part-b, exact Spec76 occurrence | `[28, 26, 219, 180]` |

Both exhaustive member masks have independently verified uniform `#000000` fill.
Their coordinate-wise bounds union therefore measures the complete subject,
without fabricating a polygon or landmarks. The new native type is
`source-backed-multipart-subject-bounds@0.1` in the existing v0.1 observation
envelope. It cannot supply v0.2 geometry-aware landmark semantics.

The three acceptance stages are:

1. `SubjectObservationAdapter` authenticates the complete Spec76/77 closure and
   proposes `AttachSubjectObservationsChange` for the observations and membership
   companion.
2. The actual frozen `TemporalCorrespondenceAdapter` derives and accepts R0
   evidence over that observation Artifact.
3. `SubjectIdentityBridgeAdapter` authenticates the current and historical bases,
   replays the original membership companion and complete R0 output, and proposes
   `ApplySubjectIdentityBridgeChange`, which delegates to exact frozen R1.

Canonical measured outputs:

- [subject-observations.json](subject-observations.json): two bounds-only records.
- [subject-membership.json](subject-membership.json): the original four Spec76
  cells, occurrence-to-subject-observation mapping and authenticated admission.
- [subject-correspondence.json](subject-correspondence.json): actual frozen R0
  candidate, scores, identities and SUPPORTED result.
- [subject-identity-proof.json](subject-identity-proof.json): independently
  replayed source-backed membership, exact R0 descriptor and complete R1 result.
- [accepted.svm.json](accepted.svm.json): final accepted Document, containing the
  two unchanged part identities and new whole-subject identity.
- [identities.json](identities.json): measured full Artifact, observation,
  TemporalIdentity and Revision identities.

The five canonical payloads are pinned byte-for-byte by
`tests/test_subject_observation_bridge.py`; measured identities are also literal
test constants. `identities.json` collects those measurements for review.
Run that test from the repository root with
`python -m unittest discover -s tests -p test_subject_observation_bridge.py -v`.

Companion Artifacts are recomputable data, not a new admission-history authority.
Only genuine Spec77 admission and complete Spec76 replay establish membership.
A future consumer claiming this source-backed meaning must independently replay
the bridge and check the actual R1 bindings/provenance. A matching media type,
hash, producer string or TemporalIdentity alone is insufficient.

This proves identity only at the two covered occurrences. It creates no artwork
correspondence, MotionTargetBinding, Track or P2D authority.
