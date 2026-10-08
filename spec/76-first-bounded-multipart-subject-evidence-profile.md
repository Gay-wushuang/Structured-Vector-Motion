# P2S-E1B — First Bounded Multipart Subject Evidence Profile

Status: **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN**.
Inspection baseline: `c7d5af4f11ee2d81bbecf4dcb6e2a3cb18ebc3d1` (clean working
tree). This document admits the first positive Multipart Subject Evidence
profile on the [spec/75](75-authored-multipart-raster-production.md) bridge.
Implementation baseline: `e73efe2b31ec90a36e2b92665444dec709ab21f3`.
Admission-history amendment: [Spec77](77-trusted-spec76-admission-history.md)
supersedes the original content-only historical admission rule. P2S-E1 is
**CLOSED for its bounded authored-source profile** (not generally frozen).
The first bounded runtime, dedicated verifier-backed Change, Golden and
adversarial tests are implemented. Whole-subject TemporalIdentity
remains **OPEN**; P2D-B remains **BLOCKED**. Ordinary-video ownership inference
and single-Entity targeting are not solved. No Group, artwork construction,
TemporalIdentity, representation correspondence or MotionTargetBinding is
created or authorized by this specification.

## 1. Profile scope and identity

Profile identity: `svm-authored-two-triangle-multipart-evidence@0.1`.

Exactly one closed-world positive profile is admitted. It may consume only the
bounded world proven executable by Spec75:

- one accepted authored SVG assembly source under grammar
  `svm-svg-g-two-triangle-paths@0.1`;
- exactly one subject at the sole canonical subject path `[0]`;
- exactly two canonical source parts, `part-a` then `part-b` in source order;
- exactly two occurrences — all occurrences of a manifest containing exactly
  two occurrences;
- fixed production policy `svm-authored-two-triangle-raster-production@0.1`
  with no options;
- the exact accepted video and manifest, decoded through unchanged spec/59;
- unchanged frozen P2A (spec/64, spec/65) and P2B (spec/66, spec/67);
- the exact source-part contribution → observed-component bijection proven by
  Spec75 replay.

The profile identity binds the evidence schema
(`svm-multipart-subject-evidence-0.1`), the identity domain, the
judgment/diagnostic taxonomy and the SUPPORTED-only acceptance route below.
Admission is SUPPORTED-only: only an independently reproduced SUPPORTED result
becomes an accepted Multipart Subject Evidence artifact, while UNCERTAIN and
REJECTED outcomes remain deterministic diagnostics (§10) that are never
persisted. A semantic change to any bound capability requires a new profile
version and review. Arbitrary SVG sources, arbitrary video, other shape
counts, other manifests, other production policies and generic profile plugins
remain forbidden. Only this explicitly admitted profile may produce or consume
this evidence.

## 2. Ownership fact being accepted

The evidence asserts exactly:

> The accepted authored subject S owns the canonical source parts
> {part-a, part-b}, and those source-defined parts correspond exactly to the
> verified observed part occurrences in the complete universe U.

This is **source-scoped structural ownership over a bounded observation
universe**. It is not, and must never be recorded or consumed as:

- a semantic object class or physical-object truth outside the bounded source
  contract;
- a whole-subject TemporalIdentity;
- Group identity or Entity membership;
- persistent artwork identity;
- a motion target identity;
- proof that observation subjects correspond to persistent artwork
  representations (spec/71).

The distinction is normative: source-scoped structural ownership and
temporal/representational identity are different relations. Neither entails
the other.

## 3. The Spec75 report is not authority

The Spec75 diagnostic production report, `golden.json`, expected fixture IDs
and claimed contribution IDs are regression checks only. They have no Document
acceptance or ownership authority (spec/75 §4). The Spec76 verifier must
independently replay every fact required from Spec75. The accepted evidence
path is:

```text
accepted authored source (ancestor source revision)
  -> independently replay Spec75 production (masks, frames, policy)
  -> accepted immutable video/manifest (verify_video_manifest, byte equality)
  -> independently replay exact observation mapping (P2A/P2B closure, labels)
  -> derive complete ownership evidence over U
  -> verifier reconstructs canonical evidence bytes
  -> evidence-only acceptance
```

The verifier re-derives the complete part set from accepted source bytes, the
complete occurrence set from the accepted manifest, the complete P2A/P2B
closure from accepted artifacts, and the exact contribution-to-observation
bijection by full-canvas label replay (spec/75 §4 steps 5–6). Nothing in the
Spec75 report is trusted as an input to the judgment.

## 4. Complete universe U

U is the major E1 contract. For this profile:

```text
U = the complete required manifest occurrence set (exactly two occurrences,
    in manifest order)
  × the complete source part set (exactly part-a, part-b, in source order)
```

Four part-occurrence cells. The verifier must independently enumerate:

1. the complete source part set, from accepted source bytes under the exact
   grammar — never pruned, never caller-supplied;
2. the complete required manifest occurrence set — a manifest with fewer or
   more than two occurrences is outside this profile; a pair selected from a
   larger manifest is forbidden (spec/74 §7);
3. the complete applicable P2A evaluation set for both occurrences, including
   UNCERTAIN/REJECTED evaluations and missing candidate IDs;
4. the complete P2B included/excluded audit;
5. the exact source-part contribution mappings (§7);
6. all currently applicable accepted SUPPORTED claims under this profile,
   each reduced to its recomputed claim key (§9.1).

No caller-selected subset is permitted. Deterministic ordering: occurrences in
manifest order (increasing frame index, then tick); parts in source leaf
order; evaluations and observations in existing P2A/P2B canonical order;
claims in evidence Artifact ID order. The video's other frames, if any, are
explicitly outside U; full-stream decode validation is not ownership evidence
there. No ownership extrapolates beyond U.

## 5. P2A / P2B closure enumeration

The verifier does not accept caller-provided or report-provided P2A/P2B
artifact IDs. It derives the unique admissible accepted closure from the
authenticated current base:

1. Enumerate every accepted P2A artifact in the base whose recorded provenance
   names the exact accepted manifest artifact. P2A payloads record the exact
   manifest artifact id and occurrence provenance (`occurrence_id`,
   `frame_index`, `tick`), so applicability is a property of accepted
   descriptors, not of input order.
2. Require exactly one admissible P2A artifact per required occurrence, in
   manifest order. Multiple accepted references to the same artifact ID are
   aliases of one closure, audited as aliases — never as additional evidence.
   Distinct artifact IDs (distinct canonical bytes) claiming the same
   occurrence are genuinely conflicting accepted evidence: the profile does
   not choose, the closure is ambiguous.
3. Enumerate every accepted P2B assembly artifact referencing the same exact
   manifest. Require exactly one logical P2B closure whose recorded P2A
   references equal the enumerated P2A set, with complete included/excluded
   audit for both occurrences.
4. A missing P2A or P2B for any required slot, or a P2B closure covering a
   different occurrence set, is an incomplete closure.

Exactly one complete admissible closure → proceed. Byte-equivalent duplicates
collapse to one closure and never create authority or ambiguity. Genuinely
conflicting accepted closures and incomplete closures are closure failures →
UNCERTAIN (`AMBIGUOUS_CLOSURE` / `INCOMPLETE_UNIVERSE`), never a
closest-match or first-artifact choice. Artifact input order never determines
authority. Closure failures are deterministic non-SUPPORTED diagnostics
(§10): they attach no evidence reference and produce no accepted artifact
(§13).

## 6. Subject and part identities

Identities reuse the source-qualified allocation of Spec75 §2 and spec/74 §8.
Let `H(x)` be full lowercase SHA-256 of repository `canonical_bytes(x)`, and
`identity_domain = "svm-multipart-subject-evidence@0.1"`.

```text
source_subject_key = {
  ownership_profile_identity:  "svm-authored-two-triangle-multipart-evidence@0.1",
  ownership_root_artifact_id:  <accepted source ReferenceArtifact id>,
  canonical_source_subject_path: [0]
}
subject_id = "subject:multipart:" + H({identity_domain, source_subject_key})
source_part_key = "part-a" | "part-b"            (source leaf id, source order)
part_id = "part:multipart:" + H({identity_domain, subject_id, source_part_key})
```

Subject identity derives only from the exact accepted source Artifact identity
and the canonical subject path. Part identity derives only from the subject
identity and the canonical part key. Neither derives from video bytes,
observation IDs, TemporalIdentity, Group IDs, evidence Artifact IDs, scores,
statuses, base revisions, current geometry or caller strings. A byte-different
source is a different source subject; no cross-file continuity is claimed.
These canonical serialized forms are the only admitted spellings.

## 7. Observation membership

For each of the four part-occurrence cells, the evidence records exactly:

| Field | Content |
| --- | --- |
| Subject | `subject_id` |
| Part | `part_id`, `part_key` |
| Occurrence | exact spec/59 occurrence identity (`occurrence_id`, `frame_index`, `tick`, `source_timestamp`) |
| Matched analysis component / evaluation | the replayed P2A component id and `evaluation_id` |
| P2B observation identity | the exact included P2B `observation_id` |
| Contribution identity | the verified contribution artifact id and the matched full-canvas label identity |

Recorded fields are not authority. The verifier must reproduce every
relationship from the §3 replay: production mask → unique full-canvas label →
unique analysis component → exact P2A evaluation → exact P2B observation. One
match per part, two distinct labels per occurrence, foreground exhausted by
the union. No nearest-match, no caller mapping, no bbox order, no component
order, no digest-only choice.

## 8. Temporal coverage and TemporalIdentity exclusion

The evidence covers only U: the two manifest occurrences. Ownership is not
extrapolated between or beyond covered occurrences.

For part TemporalIdentities, this first profile chooses **exclusion**: the
evidence schema contains no TemporalIdentity field; the verifier neither
requires nor records them; no TemporalIdentity is created, merged, bound or
synthesized, and no whole-subject TemporalIdentity is produced. This is the
smallest contract. It deliberately narrows spec/74 §7 item 5 and §8's generic
temporal-links obligations to a future profile; the narrowing is explicit, so
nothing is silently dropped — the record simply makes no temporal claim.
Existing part TemporalIdentities in the Document are neither consumed nor
invalidated by this evidence; they remain independently governed by their own
frozen contracts.

## 9. Claim equivalence and competing claims

An **accepted SUPPORTED claim** requires a trusted Spec77 admission event AND
independent replay under this schema and profile. Legacy reference presence alone
is not admission. Only SUPPORTED results are ever admitted (§10, §13), so
the accepted claim set contains no diagnostic records. The verifier enumerates
the complete currently applicable claim set from the authenticated base — all
accepted claims whose schema and profile identity match — in evidence Artifact
ID order.

### 9.1 Claim key

Let `H(x)` be full lowercase SHA-256 of repository `canonical_bytes(x)`. The
claim-equivalence projection reduces a reproduced claim to its stable
ownership facts only:

```text
claim_projection = {
  profile_identity,
  subject_id,
  parts:      [{part_id, part_key}],                                   (source order)
  universe:   [{occurrence_id, frame_index, tick, source_timestamp}],  (manifest order)
  membership: [{occurrence_id, part_key, observation_id}]              (canonical order)
}
claim_key = H(canonical_bytes(claim_projection))
```

The projection excludes the base Revision, the Document hash, the
competing-claim audit list, the resulting evidence Artifact ID, the acceptance
Revision and every other admission bookkeeping value. It derives only from the
stable ownership claim itself: profile identity, subject identity, complete
canonical part set, bounded universe U and the exact source-part →
observation membership. It is an independently reproducible verifier
computation over replayed facts; a recorded copy is never trusted. Claims
with equal `claim_key` are **equivalent**: they express the same ownership
fact and are NOT competing claims.

### 9.2 Idempotence

Before constructing a new evidence record, the verifier must enumerate the
currently applicable accepted SUPPORTED claims (§14) and recompute each claim
key.

- If an **equivalent currently applicable** SUPPORTED claim exists, the
  proposal is **idempotent**: the existing accepted claim is retained; no
  second evidence Artifact is emitted or appended; no duplicate reference
  enters the Document; no evidence chain is created, because the proposal
  never lists its equivalent predecessor as a distinct claim and no record is
  constructed at all. The verifier reports the retained claim's Artifact ID.
- If an older equivalent claim exists but is **no longer applicable** under
  the current authenticated base, it is neither reused nor rebased: it neither
  authorizes nor blocks. The verifier proceeds to construct a fresh record
  from the current base if the full §3 profile reproduction still succeeds;
  otherwise the outcome is the deterministic non-SUPPORTED diagnostic (§10).
  The older artifact remains historical and unmodified — old evidence is never
  silently rebased.

### 9.3 Competing claims

Within the bounded profile, ownership over one observed part occurrence is
exclusive: one observation cannot be a SUPPORTED member of two different
(subject, part) pairs.

| Case | Situation | Required outcome |
| --- | --- | --- |
| A | Same observation claimed by two different subjects | Incompatible. A candidate whose reproduced membership intersects an applicable accepted SUPPORTED claim under a different subject is diagnosed REJECTED (`INCOMPATIBLE_SUPPORTED_CLAIM`) and attaches nothing. Accepted claims are immutable and never retroactively demoted. |
| B | Same part observation reused by two supported subject claims | REJECTED diagnostic (`OBSERVATION_REUSED`) for the later candidate; same immutability rule. |
| C | Same subject source with conflicting member set | The source bytes are the only membership authority; accepted SUPPORTED membership is a deterministic function of source bytes, the video/manifest closure and the fixed policy. A candidate reproducing a membership that contradicts its own accepted source is diagnosed REJECTED (`SOURCE_MEMBERSHIP_CONTRADICTION`) and attaches nothing. |
| D | Byte-different authored source claiming the same observations | A different source subject. If both claims would be SUPPORTED over intersecting observations, the later candidate is diagnosed REJECTED (`INCOMPATIBLE_SUPPORTED_CLAIM`); no winner is chosen. No cross-file continuity and no global semantic uniqueness beyond observation exclusivity is invented. |
| E | Equivalent duplicate claim | NOT competing. Equivalent claims (equal `claim_key`) are the same ownership fact; §9.2 idempotence applies and no second artifact is constructed. |

Because only SUPPORTED records are admitted and admission requires no
incompatible applicable claim (§10 condition 10), the accepted set cannot
contain two incompatible SUPPORTED claims over intersecting observations: any
proposal that would create one is diagnosed and attaches nothing. Every claim
audited into a constructed record is therefore disjoint from U. Only genuinely
incompatible claims participate in competing-claim disposition.

## 10. Judgment rules

Reusing the judgment names with meanings scoped to this profile (spec/74 §10);
P2A, P2B, R0 and GroupCandidate statuses are unchanged.

**SUPPORTED** requires every condition:

1. exact accepted authored ownership root — Spec75 grammar source, accepted at
   an ancestor source revision with the video absent there (spec/75 §2);
2. complete source part set — exactly `part-a`, `part-b`;
3. complete two-occurrence U — all occurrences of an exactly-two-occurrence
   manifest;
4. exact Spec75 replay — production, decode, closure and mapping reproduce
   byte-for-byte;
5. exact video decode equality — canonical decoded PNG bytes equal expected
   PNG bytes;
6. all four source-part occurrences map uniquely — one match per part, two
   distinct labels per occurrence, foreground exhausted;
7. all required P2A results SUPPORTED;
8. P2B closure complete — both observations per occurrence, zero exclusions;
9. no unexplained observations in U — foreground equals the union of the two
   contributions;
10. no incompatible accepted supported ownership claim intersecting U;
11. authenticated current base — full-snapshot Revision witness and full
    Document hash (§14);
12. all dependencies accepted — video, manifest, canonical rasters, analysis,
    P2A and P2B descriptors resolve to accepted immutable artifacts.

`SUPPORTED` is the only judgment with an admission form. If the reproduced
judgment is SUPPORTED but an equivalent currently applicable accepted
SUPPORTED claim exists, the admission outcome is the idempotent no-op of §9.2
— the existing claim is retained and no second record is constructed.

**UNCERTAIN** covers noncontradictory insufficiency. It is a deterministic
diagnostic with fixed reason codes and never attaches evidence:

| Reason code | Situation |
| --- | --- |
| `OWNERSHIP_UNPROVEN` | Ordinary video without an accepted authored ownership root; resolver-only source; generic appended claim |
| `INCOMPLETE_UNIVERSE` | Missing source/video bridge; missing P2A/P2B slot; missing required observation; manifest occurrence set outside the profile |
| `AMBIGUOUS_CLOSURE` | Multiple distinct accepted P2A/P2B closures applicable; caller-selected convenient closure attempted |
| `MISSING_OBSERVATION` | A required part observation absent from an otherwise valid source |
| `UNSUPPORTED_SPLIT_MERGE` | Analysis split one part or merged several parts |
| `UNRESOLVED_COMPETING_CLAIM` | A competing accepted claim exists but is not itself SUPPORTED and cannot be resolved inside the profile |
| `INCOMPLETE_TEMPORAL_COVERAGE` | U cannot be covered as required (occurrence missing or unverifiable) |

**REJECTED** covers contradictions and forgery. It is a deterministic
diagnostic when produced for a well-formed candidate; malformed, forged or
unauthorized inputs are hard verification rejections (atomic failure) rather
than persisted results:

| Reason code | Situation |
| --- | --- |
| `SOURCE_MEMBERSHIP_CONTRADICTION` | Reproduced membership contradicts the accepted source bytes |
| `PRODUCTION_PIXEL_MISMATCH` | Changed production pixels; decode or contribution inequality |
| `OBSERVATION_REUSED` | Same observation claimed for two parts/subjects in supported claims |
| `INCOMPATIBLE_SUPPORTED_CLAIM` | Candidate conflicts with an incompatible accepted SUPPORTED owner |
| `FORGED_BASE_OR_DEPENDENCY` | Forged base snapshot, dependency descriptor or accepted-state claim |
| `UNKNOWN_PROFILE` | Malformed or unknown profile/schema/version |
| `SELF_ATTESTED_STATUS` | A producer-claimed supported status not independently reproduced (records carry no status field; §12) |

Reason codes are recorded in the canonical order above. Heuristic confidence,
scores, motion, proximity, co-occurrence and accumulated evidence never turn
into SUPPORTED (spec/74 §6).

Only SUPPORTED has a canonical evidence form (§12). UNCERTAIN and REJECTED
outcomes MUST NOT append an ownership-evidence reference, must not produce an
accepted Multipart Subject Evidence Artifact and must not create any Document
content; they remain reproducible verifier/producer diagnostics. Because no
nullable or free-form field exists, a failure is never persisted inside
accepted evidence — malformed, forged, unknown-profile or unauthorized inputs
are hard verification rejection where appropriate (§13).

## 11. Ordinary-video negative control

Mandatory normative control: take observations with the same geometry and
motion pattern as the positive fixture but without the admitted authored
ownership root — no accepted Spec75-grammar source in the applicable closure.
The result MUST NOT be SUPPORTED and MUST NOT be admitted: the required
repository-native outcome is the deterministic diagnostic UNCERTAIN with
reason `OWNERSHIP_UNPROVEN`, and no Multipart Subject Evidence Artifact is
produced, emitted or appended, leaving the Revision Store unchanged.
Resolver-only sources, fake profiles and generic appended claims must yield
this diagnostic or reject as malformed. This control is essential proof that
video pixels and motion do not manufacture structural ownership.

## 12. Canonical evidence schema

Schema identity: `svm-multipart-subject-evidence-0.1`.
Media: `application/vnd.svm.multipart-subject-evidence+json;version=0.1`.
Kind: DerivedArtifact; provenance exactly `{profile_identity: <profile>}`.
IDs use the existing SHA-256 canonical bytes contract with no truncated
hashes.

The canonical schema is satisfied only by a complete SUPPORTED record, and a
record exists only when a SUPPORTED result is admitted. There is no schema for
UNCERTAIN or REJECTED outcomes and no nullable or diagnostic field: those
outcomes are never serialized into accepted evidence (§10). The record is
canonical JSON with exactly the following closed-world fields, in this order:

| # | Field | Required content |
| --- | --- | --- |
| 1 | `schema_version` | `"svm-multipart-subject-evidence-0.1"` |
| 2 | `profile_identity` | `"svm-authored-two-triangle-multipart-evidence@0.1"` |
| 3 | `base` | `{revision_id, document_hash}` — authenticated base commitment (§14) |
| 4 | `source` | `{artifact_id, content_hash, media_type, source_revision_id}` — exact accepted source descriptor |
| 5 | `subject` | `{subject_id, ownership_root_artifact_id, canonical_source_subject_path}` |
| 6 | `parts` | Ordered `[{part_id, part_key}]` — complete set, source order |
| 7 | `production_policy` | `"svm-authored-two-triangle-raster-production@0.1"` |
| 8 | `video` | `{artifact_id, content_hash}` — accepted video descriptor |
| 9 | `manifest` | `{artifact_id, content_hash}` — accepted manifest descriptor |
| 10 | `occurrences` | Ordered covered occurrence identities (spec/59) |
| 11 | `membership` | Ordered per §7, all four cells |
| 12 | `claim_key` | Recomputed §9.1 claim-equivalence key (a recorded copy is never authority) |
| 13 | `dependencies` | Ordered exact accepted descriptors: P2A per occurrence, P2B observation and audit artifacts, analysis/raster closure |
| 14 | `competing_claims` | `{claim_artifact_ids, disposition}` — `claim_artifact_ids`: complete audit of the currently applicable accepted SUPPORTED claims at construction, in Artifact ID order; `disposition`: exactly `"NO_COMPETING_CLAIM"` — no audited claim is equivalent (idempotence would have produced no record) and none is incompatible |

There is no optional free-form metadata field and no judgment, status or
reason field: only SUPPORTED results become records, so an embedded status
could only be redundant or self-attestation. Every audited claim Artifact ID
in field 14 references a pre-existing, older accepted artifact; a claim
intersecting U would have been equivalent (idempotent — no record) or
incompatible (rejected — no record), so audited claims in a constructed
record are disjoint from U. No producer or verifier identity field exists:
the profile identity plus schema version pin the verifier semantics, and the
record is the verifier's deterministic replay output. Unknown fields, unknown
schema version and unknown profile identity reject. Finite canonical numbers
and integer-not-bool timing retain existing conventions.

### 12.1 Identity DAG and acyclicity

```text
accepted source + accepted video/manifest + accepted raster/analysis closure
        |
        |  independent replay (§3–§5)
        v
stable ownership claim facts: subject, parts, U, membership
        |
        +----> claim_projection -> claim_key = H(canonical_bytes(projection))
        |             (excludes base, Document hash, claim audit,
        |              own Artifact ID, acceptance Revision)
        v
currently applicable accepted SUPPORTED claims (§14); claim keys recomputed
        |
        +-- equivalent applicable claim exists --> IDEMPOTENT outcome:
        |                                          no record, no second
        |                                          Artifact, no chain (§9.2)
        +-- incompatible applicable claim exists -> REJECTED diagnostic,
        |                                           no record (§9.3)
        v  (no equivalent and no incompatible claim)
evidence record (fields 1–14 above)
        |
        v
evidence Artifact ID = H(canonical_bytes(record))
        |        (the record never embeds its own Artifact ID)
        v
evidence-only acceptance -> acceptance Revision
                 (no field in the record depends on the acceptance Revision)
```

The DAG is acyclic: every arrow points from accepted immutable inputs to
newer derived values. No field inside the evidence record depends on its own
Artifact ID, on a future acceptance Revision, or on a duplicate evidence
record created only because the first one already exists — §9.2 idempotence
guarantees an equivalent claim never produces a second record, and the record
never lists a successor. Subject, part, occurrence, observation, claim-key and
dependency identities are all fixed before the evidence bytes exist.

## 13. Acceptance boundary

The dedicated registered evidence-only Change appends ONLY the verified SUPPORTED
evidence reference, in one atomic transaction. It must not create an Entity,
Group, TemporalIdentity, Track, MotionTargetBinding or Render Stack state, and
retains the verifier interface. Spec77 adds the narrowly scoped ProposalAcceptor
admission-history enforcement required to distinguish admission from attachment.

The Change admits only a record that the verifier independently reconstructs
as SUPPORTED (§10) with complete canonical bytes (§12). Every other outcome —
UNCERTAIN, REJECTED, malformed, forged, unknown profile or stale — fails
atomically: no reference is appended, no evidence Artifact enters the
Document, and the Revision Store is unchanged. Diagnostics remain available
as deterministic producer/verifier results (§10); they are never persisted as
accepted evidence and the Change never serializes them.

If the verifier finds an equivalent currently applicable accepted SUPPORTED
claim (§9.2), the proposal completes as an **idempotent no-op**: the existing
accepted claim is retained, no second evidence Artifact is emitted or
appended, no duplicate reference enters the Document, and no new evidence
content changes the Document. The verifier reports the retained claim's
Artifact ID. An older equivalent claim that is no longer applicable is not
reused and not rebased (§9.2, §14).

`attach_analysis` is the correct ChangeAuthority intent, and reuse is
preferred: it is the existing policy intent for evidence attachment, already
shared by `AppendReferencesChange` and the verifier-backed
`AttachRasterPrimitiveObservationProposalChange`,
`AttachPrimitiveObservationAssemblyChange` and
`AttachRasterGeometryObservationsChange` family. The dedicated evidence Change
registers its own dedicated verifier in the closed-world Change Authority
Registry exactly like those predecessors — no new policy intent, no generic
evidence/plugin authority, and no artifact-declared authority. The verifier
guards exact incoming Document equality before applying (spec/72 pattern);
any preceding Change substituting a smaller universe fails.

## 14. Base / stale semantics and claim applicability

Use the repository's strongest existing model: full-snapshot acceptance with a
Revision witness, bound through the existing `source_revision_resolver`
(spec/70 §10.1 design, spec/72 implementation pattern). Verification
must authenticate:

- the full base Revision snapshot against its witness;
- the complete current Document at that base;
- the accepted exact dependency descriptors (§12 field 13);
- source ancestry and order: the source revision is an ancestor of the
  explicit current base, its sole source descriptor remains accepted there,
  and the video reference is absent from the earlier source revision
  (spec/75 §2);
- the current applicable ownership-claim universe (§9), enumerated from the
  same authenticated base with claim keys recomputed.

An accepted SUPPORTED claim is **currently applicable** at the authenticated
base iff its committed base revision remains an ancestor of that base, its
complete stable facts and recorded dependency closure remain accepted and
resolvable there, and its full §3–§5 reproduction succeeds at that base. Its
committed base Revision ID and full Document hash are immutable and are never
rewritten or retargeted: evidence generated against base A must not become
valid at mutated base B by retargeting an envelope, and applicability never
means the record certifies the current base — consumers still replay the
admitted proof against authenticated accepted inputs and current
applicability (spec/74 §9).

A proposal against a changed base requires the full independent reproduction
at that base. An older equivalent claim that is no longer applicable is
neither reused nor rebased: it neither authorizes nor blocks, the fresh
reproduction proceeds, and the older artifact remains historical and
unmodified. A forged or invented snapshot is insufficient: existing-format witnesses must
hash-link to the Acceptor's existing-store base (section 19).

## 15. Producer vs verifier

The producer computes candidate evidence and may be external. The trusted
verifier independently enumerates and replays the complete profile and must
not trust any producer-chosen input: not the part list, not the occurrence
list, not the P2A/P2B artifact IDs, not the applicable-claim audit or
equivalence outcome, not the claim key and not any claimed supported status.
Every one of these is reconstructed per §3–§5, §7, §9 and §10, and the
reproduced canonical record must be byte-identical to the candidate record
before acceptance.

## 16. Golden

The positive Golden reuses the existing checked-in
`examples/043-authored-raster-production` fixture. The test must end with:

    SUPPORTED Multipart Subject Evidence

and nothing else. No Group, no artwork construction, no TemporalIdentity, no
representation correspondence, no MotionTargetBinding. The Golden also proves
idempotence: re-proposing the same claim against the resulting base finds the
equivalent applicable claim, retains it and admits no second artifact (§9.2).
The implemented hash DAG is acyclic (§12); measured evidence and claim
identities are recorded in section 19 and pinned by the Golden test.

## 17. Adversarial matrix

Implementation must cover at least the following cases, each with its
deterministic outcome under this specification. Unless stated otherwise, every
non-SUPPORTED outcome below is a deterministic diagnostic (§10) that attaches
no evidence reference, produces no accepted artifact (§13) and leaves the
Revision Store unchanged.

| # | Case | Required outcome |
| --- | --- | --- |
| 1 | Missing ownership source | UNCERTAIN `OWNERSHIP_UNPROVEN`; never SUPPORTED |
| 2 | Resolver-only source | UNCERTAIN `OWNERSHIP_UNPROVEN` or reject; no authority from resolver bytes |
| 3 | Multiple eligible source roots | Ambiguity: UNCERTAIN, never choose |
| 4 | Changed source bytes | Different subject; replay mismatch → REJECTED/UNCERTAIN per stage |
| 5 | Omitted or extra source part | Incomplete/nonconforming part set → UNCERTAIN or grammar reject |
| 6 | Wrong source subject path | No admissible subject → UNCERTAIN/grammar reject |
| 7 | Wrong production policy | `UNKNOWN_PROFILE` reject |
| 8 | Changed frame | `PRODUCTION_PIXEL_MISMATCH` |
| 9 | Changed contribution | Contribution/label replay mismatch → REJECTED |
| 10 | Wrong immutable video | Decode/closure mismatch → REJECTED |
| 11 | Wrong manifest or timing | Closure mismatch → REJECTED |
| 12 | Omitted occurrence | `INCOMPLETE_UNIVERSE` |
| 13 | Duplicate occurrence | Spec/59 frozen duplicate rule rejects; never aliases across occurrences |
| 14 | Incomplete P2A | `INCOMPLETE_UNIVERSE` |
| 15 | Non-SUPPORTED required P2A | Not SUPPORTED; UNCERTAIN bridge gap |
| 16 | Incomplete P2B | `INCOMPLETE_UNIVERSE` |
| 17 | Excluded relevant observation | P2B audit completeness fails → UNCERTAIN/REJECTED |
| 18 | Ambiguous exact mapping | UNCERTAIN `AMBIGUOUS_CLOSURE`; no tie-break |
| 19 | Observation reused between parts | REJECTED `OBSERVATION_REUSED` |
| 20 | Caller-selected convenient closure | Not an input; replayed closure differs → reject/UNCERTAIN |
| 21 | Multiple conflicting accepted P2A/P2B closures | UNCERTAIN `AMBIGUOUS_CLOSURE` |
| 22 | Duplicate equivalent closure | Aliases of one closure; no extra authority |
| 23 | Conflicting subject claim | REJECTED diagnostic `INCOMPATIBLE_SUPPORTED_CLAIM`; attaches nothing (§9.3) |
| 24 | Duplicate equivalent ownership claim | Idempotent: equivalent applicable claim retained; no second artifact; `claim_key` equality (§9.2) |
| 25 | Stale equivalent claim on a new base | Not reused and not rebased; fresh independent reproduction at the current base, or the non-SUPPORTED diagnostic; older artifact stays historical (§9.2, §14) |
| 26 | Stale base | Ordinary staleness: reproposal, never rebasing |
| 27 | Forged base snapshot | REJECTED `FORGED_BASE_OR_DEPENDENCY` |
| 28 | Preceding-change mutation | Incoming Document-equality guard rejects atomically |
| 29 | Changed dependency descriptor | Dependency replay mismatch → REJECTED |
| 30 | Fake profile | `UNKNOWN_PROFILE` reject |
| 31 | Fake supported status | No status field exists (§12); forged/self-attested content fails independent replay → hard rejection (`SELF_ATTESTED_STATUS`) |
| 32 | Denied evidence attachment; partial mutation attempt | Policy/atomic acceptance rejects; no side effect |
| 33 | Ordinary-video negative control | UNCERTAIN `OWNERSHIP_UNPROVEN` diagnostic; never SUPPORTED; no artifact |

## 18. Relation to later phases

After E1B runtime succeeds, Multipart Subject Evidence proves structural
ownership over bounded U only. It still does NOT prove:

```text
observation subject  <->  persistent artwork representation
```

Therefore the next phase remains Stable Representation Correspondence, and
separately the whole-subject TemporalIdentity question. Only after the
representation correspondence contract is solved may P2D-B be revisited.
These phases are not merged: E1B consumes no TemporalIdentity, creates no
Group, and touches no spec/71 correspondence machinery. P2D-B remains
**BLOCKED**; Single-Entity Motion Target remains an **OPEN SEPARATE
ARCHITECTURAL QUESTION**.

## 19. Executable boundary and verification record

Runtime: `svm/adapters/multipart_subject_evidence.py`, with
`AttachMultipartSubjectEvidenceChange` registered under `attach_analysis`.
There is no generic dispatch. The two-argument ArtifactVerifier interface and
existing source-revision resolver semantics are unchanged. Spec77 extends the
ProposalAcceptor to enforce and persist dedicated admission authority.
The Change's `source_revision_id` denotes the current Proposal base; the
record's `source.source_revision_id` denotes the earlier authored-source revision.

### Revision authentication

`RevisionSnapshotWitness` contains an existing-format Revision and its complete
Document. `collect_witnesses` is a producer convenience which collects the complete
ancestor DAG in Revision-ID order. The verifier never receives, constructs or
simulates a RevisionStore instance. It recomputes each revision hash from the
snapshot, parent IDs, transaction ID and message. Every parent must be present;
duplicate, omitted, unlinked or noncanonical witnesses reject. Only nodes reachable
from the anchored base are permitted. The full DAG also authenticates historical
claim bases and prevents omission of a relevant ancestry branch.

The anchor is not a caller assertion: ordinary ProposalAcceptor establishes that
the Proposal base exists in its real store and is current, then its existing
source-revision resolver binds the Change to that exact ID. Hash-linked witnesses
authenticate earlier snapshots against this anchor. `apply()` additionally checks
canonical equality of the actual incoming Document and authenticated base before
appending. Preceding-change substitution fails; subsequent failure rolls back the
entire transaction. The smallest Revision ID among authenticated ancestors with
the exact sole source descriptor and absent video is the deterministic source
witness. This selects a proof of the same source, never a different source/part.

### Complete closure and replay

The Change transports the entire current base Reference set, identical aliases
deduplicated and sorted by Artifact ID. Conflicting descriptors reject. The
verifier independently enumerates this set from the authenticated snapshot and
requires exact equality before replay. This conservative transport set prevents
producer shortlisting; it exceeds the semantic record's dependency set.

Every accepted Spec59 manifest is verified/decoded before its relevance to the
reproduced source frames is decided. Claimed frame hashes cannot hide a relevant
manifest. Multiple matching closures abstain; valid unrelated manifests do not
change the claim. P2A/P2B enumeration checks payload and descriptor provenance
and includes the applicable observation artifacts as well as assembly audits.
Missing closure abstains; genuinely conflicting artifact IDs never choose first.

Spec75's `reproduce_source_snapshot` and `replay_snapshots` extract the existing
numeric algorithm; their callers must authenticate snapshots/ancestry first.
Original trusted-host APIs retain their store checks. Grammar, pixel arithmetic,
timing, P2A/P2B and exact label matching are unchanged. The P2B scratch repository
loads its actual replay closure rather than unrelated historical resources.
Spec75 Golden bytes remain unchanged; its diagnostic report is never an input.

Membership uses the §7 fields named `subject_id`, `part_id`, `part_key`,
`occurrence_id`, `frame_index`, `tick`, `source_timestamp`, `component_id`,
`evaluation_id`, `observation_id`, `contribution_artifact_id` and
`full_canvas_label_identity`. The latter is `sha256:<digest>` of the canonical
full-canvas label mask, proven equal to the contribution; it is not a label index
or bbox-relative digest. Dependencies are P2A per occurrence, P2B observation,
P2B audit, then analysis/mask/raster per occurrence, deduplicated at first use.
Serialization uses repository `canonical_bytes` key ordering.

### Diagnostics and historical claims

`MultipartSubjectDiagnostic(status, reason)` raises without a Proposal, evidence
Artifact or Document mutation. Malformed/forged inputs may hard-reject. Acceptance
uses ordinary atomic artifact/policy/conflict rejection. The ordinary-video
control is exactly `UNCERTAIN / OWNERSHIP_UNPROVEN`.

An admitted old record must first have a matching trusted Spec77 ancestor event.
Unproven legacy references remain data and are excluded from ownership claims;
fresh explicit re-admission is specified by Spec77. An admitted record is then
reconstructed against its authenticated ancestor base, including
the old audit. Its required descriptors must remain accepted, and its current
closure and stable facts must reproduce. Stored keys never establish equivalence.
Stale or other-branch claims are not rebased or reused. Different independently
reproduced source subjects over intersecting observations conflict; fabricated
accepted claims fail original-record replay. Multiple source candidates still
abstain rather than choosing an owner.

Only the NEW path constructs a base/audit-bearing record. An equivalent applicable
claim returns its existing reference before artifact construction. Ordinary
ProposalAcceptor commits a **same-Document child Revision**: canonical Document
bytes and evidence count remain unchanged, and no second evidence Artifact is
emitted. Permission denial applies to both new and idempotent proposals.

### Golden and tests

The real `examples/043-authored-raster-production` path ends with four membership
cells, one evidence reference and no Entity, Group, Track or temporal mutation.
Canonical record bytes are pinned by `tests/test_multipart_subject_evidence.py`:

```text
evidence Artifact:
artifact:45861f9b0ad1723fd3c3b624a7d820042a8e665f72d30cb5b4c80f1a4ba99ad4
claim_key:
803afcf7d1780c2917e69a95f83a36ce74b89e22310d79d8d4925328ea786b65
subject:
subject:multipart:44fedac3c34e35fdb80d0aeca7167d09c758f276275a6034df14506276a6b4e3
part-a:
part:multipart:865d5662321dc893922690273ef3d569cf6b715b4b0989c1fe795eea24cfc32e
part-b:
part:multipart:2fa0e5f6b213c0c988c4c56019b408b98a3c2d617c462d2e5211d763a352c901
```

The 29 focused tests include 16 record-mutation variants, omission of every
transported base reference, tampering/removal of every ancestor, recomputed
forged ancestry, actual permission denial, preceding/partial transactions,
source grammar failures, corrupted source/video/frame/P2A bytes, incomplete and
conflicting closures, manifest-selection forgery, swapped/reused observations,
stale/currently applicable claims, unrelated references/manifests, idempotence
and the ordinary-video negative control. Accepted-state atomicity and diagnostic
non-persistence are checked. Frozen expectations and tolerances are unchanged.

Stable Representation Correspondence is the **NEXT GATE**; whole-subject
TemporalIdentity and Single-Entity Motion Target remain **OPEN**; P2D-B remains
**BLOCKED**; ordinary-video ownership inference is **NOT SOLVED**.

The first bounded representation-construction profile is now specified by
[spec/78](78-first-video-backed-artwork-construction-profile.md)
(**SPECIFIED / NOT IMPLEMENTED / NOT FROZEN**). It consumes only genuinely
admitted evidence through the Section 19 / Spec77 history boundary, establishes
a construction-origin Group, and creates no TemporalIdentity or correspondence
claim; Stable Representation Correspondence and P2D-B remain open and blocked.
