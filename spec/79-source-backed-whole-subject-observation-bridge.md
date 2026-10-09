# P2S-F1A — Source-backed Whole-subject Observation Bridge

Status: **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN**.
Implementation baseline: `54574b90d63a1592f956ea69fc5d1da82233cf3f`.

## 1. Scope and feasibility decision

This profile supplies a bounded whole-subject observation bridge for the
genuinely admitted [Spec76](76-first-bounded-multipart-subject-evidence-profile.md)
authored two-triangle subject. It creates one observation at each of the two
covered occurrences, then promotes their actual frozen R0 correspondence through
the existing R1 boundary. The subject observations are distinct from all P2B
part observations. No existing part TemporalIdentity is merged or reinterpreted.

The existing `svm-primitive-observations-0.1` transport is sufficient. Frozen R0
accepts a provider-native type, bounds and fill without geometry, and compares
those features using its unchanged bounds-correspondence policy. The type field
is deliberately not an enumeration. A new producer can describe the measured
bounds of a source-backed multipart subject without claiming that its disjoint
silhouette is one controlled-raster polygon.

The alternative v0.2 representation is not used: concatenating the two parts'
ordered landmarks would invent a contour, and choosing one part would omit part
of the subject. This profile makes no landmark, rotation-symmetry, primitive
geometry or geometry-similarity claim.

A distinct versioned producer and companion-evidence contract is necessary.
It defines the new observations' exact meaning while retaining the existing
observation transport, R0 policy, R1 identities, schema and ownership invariants.
It does not change the meaning of any existing producer-native type.

```text
authenticated Spec76 admission + complete current replay
  -> one bounds-only subject observation per covered occurrence
  -> dedicated acceptance of observations and membership companion
  -> actual unchanged R0 derivation and ordinary evidence acceptance
  -> dedicated source-backed bridge verification
  -> actual R1 promotion + identity bridge companion
```

This is an observation-identity bridge, not artwork correspondence. It establishes
no relationship between a TemporalIdentity and the F0 Group, any other Group, or
any Entity. It creates no Track, Keyframe, MotionTargetBinding, animation, P2D-B
consumer or general multipart framework.

## 2. Fixed profile identities

```text
producer profile = "svm-source-backed-two-triangle-subject-observation@0.1"
native type      = "source-backed-multipart-subject-bounds@0.1"
observation schema = "svm-primitive-observations-0.1"
observation media  = "application/vnd.svm.primitive-observations+json;version=0.1"
membership schema = "svm-subject-observation-bridge-0.1"
membership media  = "application/vnd.svm.subject-observation-bridge+json;version=0.1"
identity schema   = "svm-subject-identity-bridge-0.1"
identity media    = "application/vnd.svm.subject-identity-bridge+json;version=0.1"
```

Consumed ownership profile remains
`svm-authored-two-triangle-multipart-evidence@0.1`. Dedicated admission remains
the exact [Spec77](77-trusted-spec76-admission-history.md) contract. Source grammar
and raster production remain [Spec75](75-authored-multipart-raster-production.md).
R0 retains `svm-temporal-correspondence@0.1` and
`svm-bounds-correspondence-policy@0.1`. R1 retains
`svm-explicit-temporal-identity-promotion@0.1`.

Observation output is a ReferenceArtifact so frozen R0 can resolve it unchanged.
The two companion artifacts are DerivedArtifacts. None of these new artifacts
has Spec76's reserved media type or creates an admission event.

## 3. Ownership authentication and independent enumeration

Both dedicated stages authenticate the complete ancestral witness DAG of their
real acceptance base. The existing source-revision resolver binds that base to
the trusted RevisionStore. The base witness Document must canonically equal the
Change's base snapshot. Missing parents, unreachable extra witnesses, invalid
Revision commitments, invalid admission commitments and invented history reject.

`source_references` is exactly the complete current-base reference collection in
Artifact-ID order. This conservative transport is the accepted closure consumed
by frozen Spec76 replay, not a caller-selected dependency list. The verifier
requires exact descriptor equality, complete coverage and byte resolution for
that transport. Output references are deduplicated by exact Artifact identity.

Enumeration begins with the authenticated base's exact Spec76 references, not a
caller-supplied evidence list. A reference without a matching authenticated
Spec77 event is legacy data and cannot supply ownership. Every event-bearing
candidate must be transported and resolved, including candidates that later
prove inapplicable. Omitting an event-bearing candidate rejects.

The exact admission descriptor, record base, authenticated historical Document
hash and admission transition must agree. Complete recorded source, video,
manifest and dependency descriptors must still be accepted unchanged at the
current base. The source/video/manifest record fields are summaries; complete
descriptors are recovered from the authenticated historical base and verified
against their recorded IDs/hashes. A summary is never used as an invented
Artifact reference.

Exactly one eligible admitted claim must exist. Zero or multiple eligible claims
reject without a caller tie-break. Claimed membership, observation IDs, part
order, ticks, occurrences and source selection are not request options.

This profile additionally reproduces the complete Spec76 source/video/P2A/P2B
closure. A genuine historical event does not excuse a changed dependency,
incomplete membership, forged current pixels or conflicting ownership.
The reproduced claim must agree with the admitted claim's complete subject,
part, occurrence and membership projection. Spec76's existing equivalence and
competing-claim rules remain unchanged.

## 4. Exact whole-subject measurements

The admissible world is exactly two source parts, `part-a` and `part-b`, across
the two Spec76 manifest occurrences. All four membership cells must be present,
unique and independently reproduced. Their exact component/evaluation/P2B
observation links are retained. No part or occurrence is selected, pruned,
deduplicated or inferred by visual proximity.

For each occurrence, independently reproduced Spec75 contribution masks provide
the subject foreground:

```text
subject_mask = contribution(part-a, occurrence)
             OR contribution(part-b, occurrence)
```

There are two masks per occurrence, four contribution masks in total. Their
source-backed ownership and exact P2A/P2B mappings are verified before union.
The union must be nonempty, must equal the complete subject foreground under the
admitted bounded profile, and must contain no unexplained foreground or excluded
part. The parts remain disjoint as required by Spec75/76.

Bounds are the half-open pixel bounds of this union:
`[minimum_x, minimum_y, maximum_x + 1, maximum_y + 1]`. The implementation takes
the coordinate-wise union of the two independently replayed P2B component bounds.
Complete Spec75/76 replay proves their exact contribution masks and exhaustive
membership, so this arithmetic is the union-mask bound; no second pixel
reconstruction algorithm is introduced. These are not the continuous source SVG
bounds, a new polygon or an artwork transform origin.

Frozen P2B independently measures each member's solid foreground fill from its
exact reproduced component pixels. Both member fills must be the same six-digit
`#RRGGBB` value. Equality of these exhaustive member measurements proves the
whole-subject foreground is uniform. Otherwise this profile rejects rather than
averaging colors or choosing one part's fill.

Each v0.1 primitive record has exactly:

```text
{observation_id, primitive_type, bounds, fill}
```

`primitive_type` is the new native type in §2. It never uses
`controlled-raster-polygon@0.1`, `triangle`, `rectangle` or another existing type
as an alias. No `geometry`, symmetry, subject membership or provenance fields
are inserted into the frozen observation record.

The outer payload has exactly `{schema_version, canvas, frames}`, with exactly
two increasing ticks and exactly one subject observation per frame. Canvas and
timing come from the reproduced manifest. Each frame has exactly
`{tick, primitives}`. The existing frozen reader validates these exact bytes.

## 5. Observation membership companion and identity DAG

The canonical membership companion records the profile, authenticated production
base, exact admitted claim and admission binding, source-backed subject and part
identities, complete covered occurrence universe, all four original membership
cells, the exact produced observation descriptor and each occurrence's new
subject-observation mapping and measurements.

The exact outer field set is:

```text
{schema_version, profile_identity, base, admitted_evidence_reference,
 admission, subject, parts, occurrences, membership, observation_reference}
```

`base` is the authenticated production Revision ID and Document hash.
`admitted_evidence_reference` is the complete exact Spec76 descriptor.
`admission` binds its authenticated admission event. `subject`, `parts` and
`membership` copy the independently reproduced Spec76 records exactly, including
all four complete membership cells in occurrence order then source-part order.
`observation_reference` is the complete produced observation descriptor.
Each `occurrences` entry has exactly the original four timing fields
`{occurrence_id, frame_index, tick, source_timestamp}` plus the new aggregate
`observation_id`, measured `bounds` and uniform `fill`.

Its schema is closed: unknown versions, extra fields, missing membership cells,
noncanonical ordering, duplicate IDs, unsupported statuses, nonfinite values and
boolean timing values reject. Its bytes, Artifact descriptor and provenance must
equal dedicated deterministic derivation. These fields are not caller extension
points.

Whole-subject observation IDs use a distinct versioned content-derived identity
domain. They bind authenticated source-backed subject identity, exact occurrence
and complete member observations. They must be distinct from every P2B part
observation. They are not the Spec76 `subject_id`, `part_id`, an existing R1 ID or
the ID of an arbitrary aggregate chosen by a caller.

Let H denote full SHA-256 of repository canonical bytes. For each occurrence,
let `occurrence` contain exactly its original four Spec76 timing fields and let
`membership` contain its two complete Spec76 cells in source-part order:

```text
observation_id = "observation:subject:" + H({
    profile_identity: "svm-source-backed-two-triangle-subject-observation@0.1",
    subject_id: <reproduced Spec76 subject_id>,
    occurrence: <original four timing fields>,
    membership: <complete ordered two cells>
})
```

The ID is independent of the new companion's Artifact ID and resulting Revision.
All measurements are independently determined by the committed membership;
caller-supplied measurements do not enter as alternative identity inputs.

The identity graph is acyclic:

```text
accepted source/video/dependencies + admitted Spec76 claim
  -> complete occurrence membership + subject measurements
  -> new subject observation IDs and observation Artifact
  -> membership companion Artifact
  -> actual R0 Artifact over the observation Artifact
  -> existing R1 TemporalIdentity ID
  -> identity bridge companion Artifact
```

No output embeds its resulting Revision ID or its own Artifact ID. Full canonical
SHA-256 identities are used; filesystem paths, object identity, randomness and
clock time never participate.

## 6. Dedicated observation acceptance

`SubjectObservationAdapter` supplies a data-only Proposal carrying the complete
transport and witnesses for `AttachSubjectObservationsChange`. The registered
dedicated verifier independently repeats §§3–5, reproduces both output artifacts
and compares their complete bytes, descriptors and provenance with the supplied
outputs. Adapter-generated previews and hashes supply no authority.

The exact Change record fields are:

```text
source_revision_id
base_document_snapshot
witnesses
profile_identity
source_references
observation_reference
evidence_reference
```

`source_revision_id` names the real current Proposal base. `witnesses` carries
its complete canonical ancestral DAG; `source_references` has the meaning in §3.
The two final references name the independently reproduced observation and
membership companion outputs respectively.

The Change appends the subject observation and its membership companion through
ordinary low-level reference mutation after successful dedicated verification.
Existing exact dependency references are transport inputs, not new ownership
claims. No Spec76 reference is newly introduced by this stage.

The existing `attach_analysis` policy intent applies. No new policy vocabulary,
ProposalAcceptor exception, admission-history type or general producer registry
is added. A stale Proposal or any verification/policy/final validation failure
leaves HEAD, Document, Revision count and accepted reference universe unchanged.

## 7. Frozen R0 remains the correspondence producer

After subject observations are accepted, the actual unchanged
`TemporalCorrespondenceAdapter` consumes their ReferenceArtifact and derives its
complete evidence payload. Ordinary R0 evidence acceptance is a separate stage.
The source revision recorded in that payload is its real authenticated creation
base, where the exact subject observation and membership companion were already
accepted.

F1A does not manufacture a candidate or assert `SUPPORTED` because the subject is
owned. Frozen R0 computes its own candidate IDs, inference IDs, scores,
displacement, ambiguity and status. The membership proof establishes what the
two observations measure; it does not replace the R0 policy or thresholds.

The bridge verifier reconstructs the exact observation source and repeats the
complete unchanged R0 derivation at its authenticated historical creation base.
It requires byte-identical payload and descriptor/provenance agreement. Comparing
only a selected candidate, source ID, policy string or embedded status is
insufficient. Unsupported, altered or fabricated R0 evidence rejects.

## 8. Dedicated source-backed R1 bridge

`SubjectIdentityBridgeAdapter` supplies a data-only Proposal for
`ApplySubjectIdentityBridgeChange`. Its verifier independently authenticates
the actual current base and relevant historical bases, repeats §§3–7, locates
the genuine R0 candidate over exactly the two derived subject observations and
requires its independently reproduced status to be `SUPPORTED`.

The exact R0 reference must already be accepted in the actual Proposal base.
Stage 3 does not silently stage a new R0 reference and describe it as historical
acceptance. The exact produced observation and membership companion must also
remain accepted. Their original deterministic production base is authenticated
before replay; a later base is not substituted into their identity preimages.

The Change delegates to the actual registered R1 implementation with its exact
`PromotedTemporalCorrespondence` record. The ordinary R1 verifier is retained.
The new dedicated verification is additional proof of source-backed meaning;
it does not replace or weaken R1.

R1's canonical ID formula and all endpoint ownership/conflict rules remain
unchanged. New unowned subject endpoints create one new R1 identity. Existing
owners must be consistent with the exact subject bridge and cannot alias any
part identity. Different owners reject. The profile never merges part identities
or binds part observations as whole-subject endpoints. Idempotent replay retains
the exact identity and its bindings.

For this bounded profile, the acceptable existing whole-subject definition is
exactly the canonical R1 ID, the two derived subject bindings and one exact
promotion-provenance record. Partial ownership, additional bindings, additional
provenance and unrelated or part-identity aliases reject. This is an additional
source-backed profile admission rule; generic frozen R1 keeps its existing
extension behavior.

The identity companion commits the authenticated subject membership, exact
observation/membership artifacts, actual R0 evidence/candidate/inference and the
resulting R1 identity's exact bindings and promotion provenance. The Change
atomically appends that companion and performs R1 promotion. It uses the existing
`attach_analysis` and `promote_temporal_identity` policy intents.

The identity companion's exact outer fields are:

```text
{schema_version, profile_identity, base, subject_observation_evidence,
 r0_evidence_reference, temporal_identity}
```

`subject_observation_evidence` embeds the entire independently reproduced Stage 1
membership record. `r0_evidence_reference` is its exact already-accepted complete
descriptor. `temporal_identity` is the complete actual R1 definition, with exactly
`{id, bindings, provenance}`. `base` is the authenticated Stage 3 acceptance base.
No field permits caller-defined membership or an artwork correspondence claim.

`ApplySubjectIdentityBridgeChange` has exactly:

```text
source_revision_id
base_document_snapshot
witnesses
profile_identity
source_references
observation_reference
r0_evidence_reference
delegated_promotion
evidence_reference
```

The base/witness/profile/transport fields have the same meaning as Stage 1.
`delegated_promotion` is the exact frozen `PromoteTemporalIdentityChange` over
the independently reproduced subject candidate. The final reference names the
identity companion; it does not replace the accepted R0 reference.

## 9. Replayable data is not a new admission authority

Only the Spec77 event authenticates structural ownership. F1A does not extend
that event system or treat the new media types as independently exclusive
admission namespaces. Its new observation and companion artifacts are
recomputable data.

A canonical membership or identity companion, an accepted reference, a native
type string, Artifact provenance, or an R1 TemporalIdentity alone does not prove
whole-subject ownership. A generic attachment of copied or fabricated companion
bytes cannot impersonate the dedicated verifier.

Every future consumer claiming the source-backed whole-subject meaning MUST
independently authenticate Spec77 admission, rederive the full membership and
observation bridge, rederive the complete R0 evidence and validate the actual
accepted R1 bindings/provenance. This requirement also applies to imported or
previously accepted bridge artifacts. It must not infer that a historical F1A
verifier ran from transaction messages, matching hashes or caller metadata.

This contract deliberately leaves generic frozen R0/R1 behavior unchanged.
Those primitives still express their existing observation correspondence
semantics; they cannot by themselves establish the added source-backed claim.
No historical Revision or admission record is rewritten.

## 10. Positive Golden

The Golden uses the existing Spec75/76 authored fixture; no new source, video,
reconstruction or tolerance is introduced. It retains the exact two part
observations and both covered occurrences at ticks 0 and 12.

The new subject union measurements are:

| Tick | Whole-subject half-open pixel bounds | Fill | Original part memberships |
| --- | --- | --- | --- |
| 0 | `[20, 20, 211, 174]` | `#000000` | exact `part-a` and `part-b` observation IDs |
| 12 | `[28, 26, 219, 180]` | `#000000` | exact `part-a` and `part-b` observation IDs |

The measured bounds-center displacement is `[8, 6]`. This is observation evidence,
not an accepted motion Track or correspondence to artwork. Actual frozen R0 must
produce a SUPPORTED candidate for these exact records, and actual R1 must produce
one accepted whole-subject TemporalIdentity distinct from both part identities.

Golden assertions pin measured full observation/companion/R0/R1 identities,
canonical bytes, exact subject-to-observation membership at both ticks, genuine
admission binding and unchanged part identities. Repeated derivation is exact;
no design-time hash is trusted without measurement.

## 11. Mandatory negative and atomicity matrix

| Case | Required result |
| --- | --- |
| No admitted Spec76 claim; legacy valid bytes only | Reject; no source-backed ownership |
| Missing or invalid admission event, invented history, broken witness DAG | Reject against the real base |
| Omitted event-bearing candidate or transport dependency | Reject; no selected subset |
| Multiple eligible admitted claims or competing ownership | Reject; no tie-break |
| Missing part, reused part observation, incomplete occurrence universe | Reject |
| Altered membership, contribution mask or component/evaluation/P2B link | Reject on independent replay |
| Fabricated subject observation, bounds, fill or observation ID | Reject on exact output reproduction |
| Borrowed existing producer type or invented v0.2 landmarks | Reject |
| Nonuniform union foreground or unexplained pixel contribution | Reject; no averaging or repair |
| Missing/unaccepted/changed observation or companion at R0/bridge base | Reject |
| Fabricated R0 candidate, status, score, displacement, IDs or source base | Reject on complete frozen R0 replay |
| Genuine R0 candidate is UNCERTAIN or REJECTED | Reject promotion |
| Subject endpoint owners differ or alias a part identity | Reject; no identity merge |
| Altered delegated R1 record or identity companion | Reject |
| Stale Proposal or forged historical production base | Reject |
| Malformed/noncanonical/extra-field/nonfinite payload | Reject |
| Policy denial or any post-verification transaction failure | Atomic rollback |

Every acceptance rejection must assert unchanged HEAD, Document, Revision count
and accepted reference universe. An unrelated exception is not a successful
authority regression. Ordinary generic attachments, genuine Spec76 admission,
existing R0/R1 promotion and F0 construction remain functional.

## 12. Preserved boundaries and remaining limitations

This profile supplies whole-subject observation identity only for the two
authenticated covered occurrences. It does not extrapolate between or beyond
them, establish physical recognition, infer membership from arbitrary video,
merge part identities, or assign identities to missing observations.

F0 artwork construction remains independent. No F0 Group or Entity is an input
to observation identity derivation, and an identity bridge does not prove
representation correspondence, current artwork coverage, Group ownership or
legal motion-target binding. Those remain separate gates. P2D-B remains outside
this implementation.

P2A/P2B, Spec75 production, Spec76 evidence, Spec77 admission, R0/R1 policies,
numeric thresholds, frozen Golden outputs, TemporalIdentity Document format and
ProposalAcceptor authority semantics remain unchanged.

## 13. Verification requirements

Run focused F1A tests first, including the complete negative matrix and exact
positive membership/R1 Golden. Then run ProposalAcceptor/ChangeAuthority,
Spec75/76/77, F0, P2B, R0/R1 and generic reference-attachment regressions, the full
unittest suite, Ruff, Pyright, formatting and `git diff --check`. Inspect the
complete working-tree diff and record measured outputs and any limitations.

## 14. Implementation and measured Golden record

Implementation uses `svm/adapters/subject_observation_bridge.py`, two exact Core
registered Changes in `svm/revisions.py`, and additive verifier/action entries in
`svm/change_authority.py`. Existing Spec78 descriptor/admission enumeration is
reused, followed by full original/current Spec76 replay. No existing acceptance
primitive, Document schema, numeric threshold or admission-history contract is
changed.

The measured Golden is [example 045](../examples/045-subject-observation-bridge/README.md).
It first admits Spec76 and promotes the two existing P2B part identities through
actual R0/R1, then runs the three bridge stages. Its five canonical payloads and
all important identities are pinned in `tests/test_subject_observation_bridge.py`.
`identities.json` collects the exact measured mapping for review.

```text
subject = subject:multipart:44fedac3c34e35fdb80d0aeca7167d09c758f276275a6034df14506276a6b4e3
tick 0 observation = observation:subject:41f34347845507a4517821e13ca7c6f0f801a9cf562c1e74aa9f451f05c60d07
tick 12 observation = observation:subject:bd2818774750fbe166b7f04d220fb6aa1ef0d5f0eb094c1cf82d1c903f66412d
observation Artifact = artifact:44375ca66b694b68d2e0374e6b29ca2885b5e11eaa4a7eecdd3f3ef8cb0d11e2
membership Artifact = artifact:5528daf887863233d927249280ded75c4a09030f449b585dc369e682ca00221b
R0 Artifact = artifact:041ee965772aa0bae3e091717fd65c3a91e358f5af3c1d385e93ff9f6375c238
identity companion = artifact:0ce77b99e1b4cc94e2d2b60178c8ea895f4739145f90bbd49a95f4a4d66c58ab
whole identity = temporal-identity:f89cc670dc7d6d8f54dd519532d525346817425825949ded13a79daae45aacbf
final Revision = revision:4865787b0ed71cc93bc279f51db91ff03e272995deb06833c71f35fa20b63626
final Document hash = sha256:4385b492db86378568a299e14b3ece562e8c1338a216cd22c1619dd0bc03948c
```

The actual frozen R0 support score is `0.950281554448`; its sole candidate is
`SUPPORTED`. No tolerance was relaxed to obtain that result.

Direct F1A regressions cover the user-required missing admission, incomplete or
conflicting membership, aggregate forgery, invalid/unsupported recorded R0,
competing ownership, stale base and forged history cases, plus exact transport,
descriptor conflicts, policy denial, nested caller types and atomic rollback.
The positive test independently checks actual contribution-mask union against
the decoded frame pixels. Existing Spec75/76 regressions additionally cover pixel
and source-grammar failures. The fixed Golden's actual R0 result is SUPPORTED;
recorded unsupported evidence is tested through complete replay rejection,
without manufacturing a different source or altering the frozen policy.

Verification on Windows / Python 3.12:

- All 27 focused F1A methods verified passing. Four expected diagnostic matchers
  were corrected after their initial rejections; those methods and the expanded
  aggregate-forgery case passed in a five-method rerun. The final full suite also
  passed all 27 methods unchanged.
- 125 P2B/R0/R1, Spec76/77, ProposalAcceptor/ChangeAuthority, anchored policy and
  F0 regression tests passed (`144.045s`).
- 54 Spec73/75 and P2A regressions passed (`52.142s`).
- Full unittest suite: **670 tests passed** (`1285.066s`).
- Ruff formatting/lint, Pyright, compile-check, CLI validation of this Golden
  and Golden A, and `git diff --check` passed.
- Complete tracked and new-file changes were inspected; frozen authority,
  numeric thresholds, old Golden files and P2D are unchanged.

This records local verification; the remote Windows/Linux Python 3.11/3.12 CI
matrix was not dispatched. The bounded profile is implemented and Golden
verified, without a format-freeze or broader correspondence claim.
