# P2S-E1B — First Bounded Multipart Subject Evidence Profile

Status: **SPECIFIED / NOT IMPLEMENTED / NOT FROZEN**.
Inspection baseline: `c7d5af4f11ee2d81bbecf4dcb6e2a3cb18ebc3d1` (clean working
tree). This document admits the first positive Multipart Subject Evidence
profile on the [spec/75](75-authored-multipart-raster-production.md) bridge.
Multipart Subject Evidence runtime is **NOT IMPLEMENTED**; no verifier, Change
type, Golden or adversarial test exists yet. Whole-subject TemporalIdentity
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
(`svm-multipart-subject-evidence-0.1`), the identity domain, the judgment
taxonomy and the acceptance route below. A semantic change to any bound
capability requires a new profile version and review. Arbitrary SVG sources,
arbitrary video, other shape counts, other manifests, other production
policies and generic profile plugins remain forbidden. Only this explicitly
admitted profile may produce or consume this evidence.

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
acceptance or ownership authority (spec/75 §4). A future Spec76 verifier must
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
6. all applicable accepted ownership claims under this profile (§9).

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
authority.

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

## 9. Competing ownership claims

A claim is an accepted evidence record under this schema and profile, plus the
candidate record under evaluation. The verifier enumerates the complete
applicable claim set from the authenticated base — all accepted records whose
schema and profile identity match — in evidence Artifact ID order. Within the
bounded profile, ownership over one observed part occurrence is exclusive: one
observation cannot be a SUPPORTED member of two different
(subject, part) pairs.

| Case | Situation | Required outcome |
| --- | --- | --- |
| A | Same observation claimed by two different subjects | Incompatible supported claims. A candidate that would be SUPPORTED over an observation owned by an incompatible accepted SUPPORTED claim is REJECTED (`INCOMPATIBLE_SUPPORTED_CLAIM`). An accepted SUPPORTED claim is immutable and never retroactively demoted. |
| B | Same part observation reused by two supported subject claims | REJECTED for the later candidate (`OBSERVATION_REUSED`); same immutability rule. |
| C | Same subject source with conflicting member set | The source bytes are the only membership authority. A reproduced membership contradicting its own source is REJECTED (`SOURCE_MEMBERSHIP_CONTRADICTION`). |
| D | Byte-different authored source claiming the same observations | A different source subject. Two supported claims over intersecting observations conflict: the later candidate is REJECTED (`INCOMPATIBLE_SUPPORTED_CLAIM`). No cross-file continuity and no global semantic uniqueness beyond observation exclusivity is invented. |
| E | Duplicate identical supported claim | Byte-identical records have the same content hash and Artifact ID; multiple accepted references are audited as one logical claim. Never a conflict, never extra authority. |

A later accepted evidence record must not silently coexist with an
incompatible SUPPORTED owner: the exclusivity check in the SUPPORTED
conditions (§10) enforces this at judgment time. Non-SUPPORTED records may be
accepted for audit; they grant no ownership and do not conflict. If the base
already contains two incompatible accepted SUPPORTED claims, the profile does
not repair history: it reports the conflict and rejects any new candidate over
intersecting observations. Resolution of historical conflicts is not admitted
by this profile.

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

**UNCERTAIN** covers noncontradictory insufficiency, with deterministic
reasons:

| Reason code | Situation |
| --- | --- |
| `OWNERSHIP_UNPROVEN` | Ordinary video without an accepted authored ownership root; resolver-only source; generic appended claim |
| `INCOMPLETE_UNIVERSE` | Missing source/video bridge; missing P2A/P2B slot; missing required observation; manifest occurrence set outside the profile |
| `AMBIGUOUS_CLOSURE` | Multiple distinct accepted P2A/P2B closures applicable; caller-selected convenient closure attempted |
| `MISSING_OBSERVATION` | A required part observation absent from an otherwise valid source |
| `UNSUPPORTED_SPLIT_MERGE` | Analysis split one part or merged several parts |
| `UNRESOLVED_COMPETING_CLAIM` | A competing accepted claim exists but is not itself SUPPORTED and cannot be resolved inside the profile |
| `INCOMPLETE_TEMPORAL_COVERAGE` | U cannot be covered as required (occurrence missing or unverifiable) |

**REJECTED** covers contradictions and forgery:

| Reason code | Situation |
| --- | --- |
| `SOURCE_MEMBERSHIP_CONTRADICTION` | Reproduced membership contradicts the accepted source bytes |
| `PRODUCTION_PIXEL_MISMATCH` | Changed production pixels; decode or contribution inequality |
| `OBSERVATION_REUSED` | Same observation claimed for two parts/subjects in supported claims |
| `INCOMPATIBLE_SUPPORTED_CLAIM` | Candidate conflicts with an incompatible accepted SUPPORTED owner |
| `FORGED_BASE_OR_DEPENDENCY` | Forged base snapshot, dependency descriptor or accepted-state claim |
| `UNKNOWN_PROFILE` | Malformed or unknown profile/schema/version |
| `SELF_ATTESTED_STATUS` | A claimed supported status not independently reproduced |

Reason codes are recorded in the canonical order above. Heuristic confidence,
scores, motion, proximity, co-occurrence and accumulated evidence never turn
into SUPPORTED (spec/74 §6). Acceptance of a UNCERTAIN/REJECTED record for
audit is not acceptance of ownership.

## 11. Ordinary-video negative control

Mandatory normative control: take observations with the same geometry and
motion pattern as the positive fixture but without the admitted authored
ownership root — no accepted Spec75-grammar source in the applicable closure.
The result MUST NOT be SUPPORTED. The required repository-native outcome is
UNCERTAIN with reason `OWNERSHIP_UNPROVEN`. Resolver-only sources, fake
profiles and generic appended claims must yield this outcome or reject as
malformed. This control is essential proof that video pixels and motion do
not manufacture structural ownership.

## 12. Canonical evidence schema

Schema identity: `svm-multipart-subject-evidence-0.1`.
Media: `application/vnd.svm.multipart-subject-evidence+json;version=0.1`.
Kind: DerivedArtifact; provenance exactly `{profile_identity: <profile>}`.
IDs use the existing SHA-256 canonical bytes contract with no truncated
hashes. The record is canonical JSON with exactly the following closed-world
fields, in this order:

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
| 12 | `dependencies` | Ordered exact accepted descriptors: P2A per occurrence, P2B observation and audit artifacts, analysis/raster closure |
| 13 | `competing_claims` | `{claim_artifact_ids, disposition}` — complete §9 evaluation |
| 14 | `judgment` | `SUPPORTED` \| `UNCERTAIN` \| `REJECTED` |
| 15 | `reason_codes` | Ordered reason codes; empty only when SUPPORTED |

There is no optional free-form metadata field. No producer or verifier
identity field exists: the profile identity plus schema version pin the
verifier semantics, and the record is the verifier's deterministic replay
output. Unknown fields, unknown schema version and unknown profile identity
reject. Finite canonical numbers and integer-not-bool timing retain existing
conventions. The evidence Artifact ID is the hash of the complete record; the
record must not contain its own Artifact ID or any digest derived from it —
no identity cycle may exist between the evidence ID and the facts used to
compute it. Subject, part, occurrence, observation and dependency identities
are all fixed before the evidence bytes exist.

## 13. Acceptance boundary

A future registered evidence-only Change appends ONLY the verified evidence
reference, in one atomic transaction. It must not create an Entity, Group,
TemporalIdentity, Track, MotionTargetBinding or Render Stack state, and must
not change the ProposalAcceptor or verifier interface.

`attach_analysis` is the correct ChangeAuthority intent, and reuse is
preferred: it is the existing policy intent for evidence attachment, already
shared by `AppendReferencesChange` and the verifier-backed
`AttachRasterPrimitiveObservationProposalChange`,
`AttachPrimitiveObservationAssemblyChange` and
`AttachRasterGeometryObservationsChange` family. The future evidence Change
registers its own dedicated verifier in the closed-world Change Authority
Registry exactly like those predecessors — no new policy intent, no generic
evidence/plugin authority, and no artifact-declared authority. The verifier
guards exact incoming Document equality before applying (spec/72 pattern);
any preceding Change substituting a smaller universe fails. Acceptance failure
leaves the Revision Store unchanged.

## 14. Base / stale semantics

Use the repository's strongest existing model: full-snapshot acceptance with a
Revision witness, bound through the existing `source_revision_resolver`
(spec/70 §10.1 design, spec/72 implementation pattern). Future verification
must authenticate:

- the full base Revision snapshot against its witness;
- the complete current Document at that base;
- the accepted exact dependency descriptors (§12 field 12);
- source ancestry and order: the source revision is an ancestor of the
  explicit current base, its sole source descriptor remains accepted there,
  and the video reference is absent from the earlier source revision
  (spec/75 §2);
- the current applicable ownership-claim universe (§9), enumerated from the
  same authenticated base.

The evidence record commits its base Revision ID and full Document hash.
Evidence generated against base A must not become valid at mutated base B by
retargeting an envelope: any base mutation makes the evidence stale, and stale
proposals require reproposal — never silent rebasing. A forged or invented
snapshot is insufficient; the witness must be an existing-format Revision
witness verified by the store.

## 15. Producer vs verifier

The producer computes candidate evidence and may be external. The trusted
verifier independently enumerates and replays the complete profile and must
not trust any producer-chosen input: not the part list, not the occurrence
list, not the P2A/P2B artifact IDs, not the competing-claim set, and not the
judgment. Every one of these is reconstructed per §3–§5, §7 and §9, and the
reproduced canonical record must be byte-identical to the candidate record
before acceptance.

## 16. Golden

Exactly one future positive Golden reuses the existing checked-in
`examples/043-authored-raster-production` fixture. The test must end with:

    SUPPORTED Multipart Subject Evidence

and nothing else. No Group, no artwork construction, no TemporalIdentity, no
representation correspondence, no MotionTargetBinding. The deterministic
expected evidence identity is specified only after the implemented hash DAG
is shown acyclic (§12); until then no expected evidence Artifact ID is
recorded.

## 17. Adversarial matrix

Future implementation must cover at least the following cases, each with its
deterministic outcome under this specification:

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
| 23 | Conflicting subject claim | REJECTED `INCOMPATIBLE_SUPPORTED_CLAIM` per §9 |
| 24 | Duplicate equivalent ownership claim | One logical claim; idempotent |
| 25 | Stale base | Ordinary staleness: reproposal, never rebasing |
| 26 | Forged base snapshot | REJECTED `FORGED_BASE_OR_DEPENDENCY` |
| 27 | Preceding-change mutation | Incoming Document-equality guard rejects atomically |
| 28 | Changed dependency descriptor | Dependency replay mismatch → REJECTED |
| 29 | Fake profile | `UNKNOWN_PROFILE` reject |
| 30 | Fake supported status | `SELF_ATTESTED_STATUS` reject |
| 31 | Denied evidence attachment; partial mutation attempt | Policy/atomic acceptance rejects; no side effect |
| 32 | Ordinary-video negative control | UNCERTAIN `OWNERSHIP_UNPROVEN`; never SUPPORTED |

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
