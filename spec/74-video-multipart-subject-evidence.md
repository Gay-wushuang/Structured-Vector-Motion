# P2S-E0 — Video Multipart Subject Evidence Feasibility Audit

Status: **DESIGN CONTRACT / NOT IMPLEMENTED / NOT FROZEN**.
Audit baseline: `773c6db42262127bc6df56254f01d3b3201e9f4c` (clean working tree).

Verdict **B**: existing accepted evidence does not prove video multipart subject
ownership. A narrow, evidence-only contract is expressible without changing Core
Entity, Group or TemporalIdentity semantics. This verdict establishes the evidence
contract, not a working ownership detector, admitted producer, video construction
profile or P2D implementation. Ordinary video without an independently verifiable
ownership basis remains insufficient.

## 1. Question and governing boundary

The missing fact is that distinct simultaneous parts belong to one persistent
source artwork subject, within an explicitly bounded observation universe.
Observation correspondence across time and shared structural ownership are
different relations. Neither entails the other.

Governing requirements are INV-ID-001/004, INV-REF-001/002/003, INV-REL-001/002,
INV-TIME-003/004/011, INV-PROP-001/002 and INV-TXN-001 in
[spec/01](01-invariants.md), plus [spec/05](05-system-boundaries.md).
Artifacts remain external evidence; they do not become evaluated Values or
Document objects by being named. Exact registered Change authority, authenticated
base state, policy enforcement and atomic acceptance remain mandatory.

Construction-Derived Group Authority is already implemented for spec/73. That
closed phase is not reopened. This audit neither changes nor substitutes its
authored SVG ownership proof.

## 2. Inspection record

The audit inspected the following contracts and implementation boundaries.
Tests cited here were inspected as existing executable evidence, not newly run
or added by this documentation-only audit.

| Area | Files and relevant entry points inspected |
| --- | --- |
| Core authority | `spec/01`, `spec/05`; `svm/proposals.py`: acceptance, artifact verification and source-revision hook; `svm/change_authority.py`: registered verifiers/intents; `svm/revisions.py`: reference attachment, P2A/P2B attachment, promotion and identity allocation; `svm/document.py`: Entity provenance, source layers, TemporalIdentity and Group validation |
| Video/P2A/P2B | `spec/59`, `spec/64`, `spec/66`; `svm/adapters/raster_primitive_observation_proposal.py`: dependencies, measurement, derive and verification; `svm/adapters/primitive_observation_assembly.py`: complete inclusion/exclusion, observation allocation and verification |
| R0/P2C/R1 | `spec/35`, `spec/36`, `spec/68`; `svm/adapters/temporal_correspondence.py`, `temporal_identity_selection.py`, `temporal_identity_promotion.py`; `PromoteTemporalIdentityChange` and `_validate_temporal_identities` |
| Raster and provenance | `spec/13` through `spec/20`; `svm/adapters/bitmap_trace.py`: producer, contour grouping and fragment; `bitmap_reconcile.py`: scope, proposal and matcher; `layerpeeler_output.py`: bundle validation and fragment replay; `layerd_output.py`: bundle, RGBA and analysis validation; `PromotedComponent.to_entity`, `promoted_component_entity_id` and source-layer validation |
| POP comparison | `spec/27`, `spec/28`, `spec/29`; `svm/adapters/pop_structure.py`: `_validate_exact_pop_scene`; `pop_group_candidates.py`: complete pair iteration and feature filtering; `_verify_group_promotion` |
| Representation/construction | Complete `spec/71`, `spec/72`, `spec/73`; `svm/adapters/svg_group_construction.py`: source enumeration, source parsing, base authentication, derivation and verifier |
| Binding/readiness | `spec/38`; `spec/70` restricted derivation and full-base acceptance design; `svm/adapters/temporal_motion_target_binding.py`, `motion_target_binding_selection.py`; README readiness |
| Executable expectations | Test cases in `tests/test_raster_primitive_observation_proposal.py`, `test_primitive_observation_assembly.py`, `test_temporal_correspondence.py`, `test_temporal_identity_promotion.py`, `test_temporal_identity_selection.py`, `test_layerpeeler_output_adapter.py`, `test_layerd_output_adapter.py`, `test_bitmap_trace_adapter.py`, `test_structured_trace_components.py`, `test_entity_reconciliation.py`, `test_pop_group_candidates.py`, `test_motion_target_binding_selection.py`, `test_temporal_motion_target_binding.py`, `test_svg_group_construction.py` |

The decisive real-producer counterexample is
`test_real_p2a_p2b_ids_resolve_exact_evaluations_not_ordinals`: independently
analyzed frames resolve to different PromotedComponent Entities. P2D-A reports
`CONTRADICTORY_PROVENANCE`, even though the lineage is exact. Its manually
supplied test Groups do not prove accepted construction. P2B's Golden retains
two supported primitives per frame and exclusions; P2C's Golden promotes two
distinct identities. Neither test asserts a common subject.

## 3. Evidence-path findings

“Complete” below always names a specific universe. Completeness of a supplied
bundle is not completeness of a subject's parts or of a whole video.

| Path | Exact fact and complete universe | Identity / shared-subject fact | Verification and accepted-state limit |
| --- | --- | --- | --- |
| Video ingestion, spec/59 | Re-decodes the bounded FFV1 source and reproduces canonical raster bytes and rational timestamps for every selected manifest occurrence; decoding validates the full stream | Video and occurrence identity, not object identity; repeated pixels do not merge occurrences | `verify_video_manifest` is replayable; ingestion itself creates no Revision. Its sidecar and frames must be accepted separately before P2A consumption |
| OpenCV / P2A | Analysis enumerates foreground connected components; P2A reproduces analysis/mask, occurrence lineage, every evaluation and eligibility status for one selected occurrence | Component/evaluation/candidate identity, no common subject; one component is not proof of an artwork assembly | P2A has acceptance-time semantic replay and accepted dependency checks. OpenCV reference attachment alone does not replay analysis at acceptance; P2A strengthens the downstream proof. Only P2A evidence is appended |
| P2B | Exactly all SUPPORTED evaluations of two selected accepted P2A occurrences become primitives, with every exclusion audited; same manifest, increasing index/tick | Distinct occurrence observation IDs; “assembly” means observation packaging, not multipart ownership | Acceptance replays P2A, raster geometry, IDs and both output artifacts. Appends observations plus audit. Frame-pair choice remains explicit; it is not whole-video coverage |
| R0 | Producer evaluates the full source-by-target Cartesian product of its two-frame observation artifact using frozen bounds/color/type policy | Candidate identifies two endpoints; SUPPORTED is a correspondence hypothesis, not structural ownership | Deterministically replayable from input, but ordinary R0 acceptance uses `AppendReferencesChange`, with no semantic replay verifier. Accepted bytes are not an independent certification of the score or source pixels |
| P2C / R1 | P2C selects ALL SUPPORTED entries in one accepted R0 artifact; R1 records stable endpoint ownership with exact promotion provenance | Stable observation identity across time under the recorded policy. No parent, assembly, family, or shared-subject field | P2C rechecks content IDs, disjointness, selection and delegation; R1 verifies selected accepted records and conflicts. Neither reruns R0 scoring nor proves physical identity. Acceptance mutates only identity/selection evidence |
| LayerPeeler | Complete declared layer bundle, common recorded run and deterministic normalization of each supplied SVG shape | `source_layer` proves bundle/run/layer association. Multiple shapes in one layer are not thereby one persistent subject | Registered verifier reconstructs imported fragment from bundle bytes. It neither reruns the model nor proves source reconstruction, semantic segmentation or cross-time ownership |
| LayerD | Complete declared layer bundle and analysis binding; derives RGBA alpha bounds/counts, validates classification shape and provenance | Research-layer identity/order only, no assembly or temporal identity | Registered verifier reproduces neutral non-rendered Entities from bundle. Model decomposition and classification truth are not independently replayed; labels remain candidates |
| Bitmap trace | Recorded tracer/options produce contour-root compound shapes, preserving descendant holes/islands; complete traced result for that input/options | Deterministic imported Entity identity, not temporal identity or shared ownership between components | Producer can be rerun with recorded engine. Generic fragment acceptance validates artifact/Document semantics, not independent retracing. Accepted artwork is an explicit construction choice |
| Bitmap reconciliation | Scores every old scoped/new traced pair, chooses deterministic thresholded greedy matches, preserves matched IDs on accepted replacement | Geometric reconciliation of an explicitly selected contiguous artwork scope; not exact real-world identity or assembly proof | Producer is replayable with versions/options. Generic replacement acceptance checks structural safety, not the matcher's semantic truth. Neither complete-video nor complete-subject authority |
| Current Entity provenance / relations | PromotedComponent binds one accepted analysis candidate/digest/bounds; `derived-from` and immediate `bounds-contains` are canonically materialized | Analysis-local origin, not a cross-frame subject; `parent_id` is authored hierarchy, not video evidence | Promotion verifies candidate records; it does not reopen pixels. Source-layer fields have separate artifact-bound import authority. Structural JSON validity alone is not proof admission |
| POP P / Q-v0 | Exact prefix/output reconstruction of the unchanged accepted primitive scene; geometric full/topmost coverage over its non-background primitives | Exact primitive source association, no same-object or video-subject assertion | Q-v0 producer checks exact scene and deterministically derives masks; reference attachment is not a general replay certificate. Restricted POP source cannot be fabricated from video to borrow authority |
| GroupCandidate / Q-v2 | Q-v1 considers pairs from Q-v0 records, omits pairs failing its feature prefilter, emits scored hypotheses; Q-v2 explicitly promotes selected SUPPORTED candidates | Candidate ID identifies member set, not an independently proven subject. Accepted Group means explicit artwork grouping under that authority | Q-v1 attaches evidence; promotion checks canonical accepted record and stale source hash, not independent physical ownership. These frozen semantics are not upgraded by this audit |
| Spec/72 + spec/73 | Replays the entire exact SVG source tree: sole authored `g`, rectangle then ellipse, complete fragment and Group | Source Artifact + path `[0]` supplies authored subject; its two source leaves are simultaneous parts | Dedicated verifier, base witness and incoming guard reconstruct all outputs. This is a real positive structured-source proof, explicitly non-temporal; no video association |
| Spec/71 | Specifies observation ownership + legal representation establishment + current applicability/history | A proven association between a TemporalIdentity and persistent artwork, not multipart ownership itself | Design only; no admitted temporal construction/correspondence profile. A receipt or media type does not authenticate itself |
| S1 / P2D-A | S1 explicitly binds existing T and transformed Group one-to-one; P2D-A derives exact common-source provenance paths over all identities | Explicit binding choice / restricted selection, not structural inference | S1 checks endpoints and conflicts atomically. P2D-A is pure derivation, no P2D acceptance registration. Different resolved Entities remain contradictory under its frozen rule |

Thus no inspected path proves that two independently video-observed primitives
are genuine simultaneous parts of one persistent source subject. This is an
absence of authority, not permission to strengthen an existing status label.

## 4. TemporalIdentity is not an assembly

Current TemporalIdentity has exactly `id`, `bindings`, `provenance`; a binding
has exactly `tick`, `observation_id`. It records accepted correspondence ownership
and preserves identity when frozen R1 extends an owner. Distinct owners conflict;
R1 never merges them. The schema has no exact parent/shared-subject evidence.

The validator enforces canonical endpoint uniqueness and exclusive ownership,
not a new assembly interpretation of bindings. In particular, any ability to
store multiple different endpoints at one tick must not be used as an assembly
loophole. A later evidence consumer must check its own complete endpoint mapping.

`T1 + T2 -> S` would be a separate evidence relation, not an R1 operation. This
contract neither creates S as a TemporalIdentity nor makes T1/T2 its children in
the Document. “TemporalIdentity family” has no current authority semantics.

## 5. Minimal missing concept: Multipart Subject Evidence

Use **Multipart Subject Evidence**, following the repository's artifact/evidence
conventions. Avoid `ObservationAssemblyIdentity`: P2B already uses “assembly” for
packaging, and that name would blur its frozen meaning.

The generic claim is:

> Under admitted ownership profile P and exact source authority A, subject S
> owns precisely the persistent logical part set M throughout bounded universe U.
> Every observation in U is accounted for, and each claimed part observation has
> an exact, independently verified source-part association.

Its Core-facing meaning is an immutable structural evidence record. No new
top-level Document collection, Entity subtype, Group kind, hierarchy, render
rule, Operation, binding or motion-target type is needed. A future registered
evidence-only Change can attach the verified artifact using `attach_analysis`.
Generic reference attachment does not confer these semantics.

The five dimensions are separate:

| Dimension | Meaning |
| --- | --- |
| Subject | One source-defined persistent artwork assembly, namespaced by exact ownership authority |
| Part | One logical member in that source assembly; stable across occurrences |
| Observation | One measured occurrence of a part, with exact frame/component/observation lineage |
| Temporal coverage | Enumerated observation occurrences and stated limits; no claims between or beyond them |
| Membership | Source-authorized `owns(S, P)` relation, independent of visibility and temporal matching |

The initial semantic subset is a fixed flat part set for one source subject.
It does not define nested assemblies, membership edits, split/merge identity,
physical-object ontology or subject equivalence across separately accepted sources.
At least two distinct real parts must have verified simultaneous observations at
one covered occurrence. A sequence of single-part alternatives is ineligible.

## 6. Ownership authority cannot come from pixels alone

Two independent objects and one authored two-part object can produce identical
pixels, motion and component histories. Replaying those measurements cannot
distinguish their structural interpretation. Hashes prove bytes; model replay
proves the recorded computation. Neither proves a unique hidden object assembly.

The narrow feasible proof direction is **structured-source ownership with a
verified video occurrence bridge**. An admitted profile must independently read
a complete accepted authored assembly source, enumerate its subject and logical
parts, and verify their production/observation relation to the exact video.
The source hierarchy is the ownership basis; raster matching is only the bridge.

A possible first profile may use a bounded recorded 2D authored source and a
fixed deterministic production recipe, verify the entire source structure and
reproduce every covered decoded frame and per-part contribution. This proves
the accepted authored-source interpretation of that video. It does not prove
that this is the only possible explanation of the pixels or the actual historical
source of an unrelated video. A claim of historical production additionally needs
an independently authenticated production record with explicitly admitted trust
and issuer scope. Source/node names and a producer string are not such a record.

No concrete producer or production recipe is admitted by E0. In particular:

- A post-hoc sidecar listing convenient observations is not an authored-source
  witness, even if it is accepted, signed or rehashed.
- An AI-generated graph is still a proposal about an ordinary video's structure.
  Accepting it as a newly authored artwork source must not relabel that artistic
  decision as discovery of original video ownership.
- An attestation route requires a separate explicit trust contract describing
  exactly what the issuer may attest and how authenticity and coverage are checked.
  This version admits no attestation-only route.
- An ordinary-video heuristic-only producer cannot yield authoritative SUPPORTED
  ownership under this contract. It may emit an auditable UNCERTAIN hypothesis.

Same frame, proximity, overlap, containment, color, geometry, connectivity, analysis
Artifact, identity family, caller grouping, label, similar motion and repeated
co-occurrence SHALL NOT establish ownership, alone or merely accumulated into a
score. They may be producer features, never substitute authority.

## 7. Complete accepted universe

Completeness has two independent requirements: **observation completeness** and
**structural membership completeness**. Enumerating every detected component
does not establish that all subject parts were detected, especially under occlusion.

For the initial video bridge, derive U from the authenticated full base Document,
not the proposal's evidence list. The smallest bounded admission should require
one eligible accepted video manifest and one independently admitted ownership root;
multiple competing roots/manifests abstain, never choose the first or highest score.
Enumerate potential roots before eligibility filtering, so a malformed competing
reference cannot disappear. A future multi-source selector needs its own contract.

The initial two-occurrence bridge must use **all** occurrences of a manifest
containing exactly two occurrences, matching frozen P2B. It must not pick a pair
from a larger manifest. The source video's other frames, if any, are explicitly
outside U: full-stream decode validation is not evidence of ownership there.
This preserves spec/59's explicit sampling authority without allowing the
ownership Proposal to invent a convenient interval or claim unsampled coverage.

The verifier must reproduce and record:

1. Exact accepted video/manifest descriptors, decoder/canonicalization identities,
   source dimensions/count, rational FPS, ticks-per-second, every selected frame
   index, source timestamp, tick, occurrence ID and raster reference. Use spec/59
   exact timing; no rounding, free tick, inferred FPS or silent manifest mixing.
2. Every accepted analysis/P2A path for those occurrences and its full mask/raster
   closure. Reproduce measurements under the recorded versions. Competing analysis
   configurations cannot be resolved by whichever makes ownership easiest; the
   bounded profile must prescribe one, and account for alternatives/conflicts.
3. Every P2A evaluation, including UNCERTAIN/REJECTED and missing candidate IDs;
   P2B's complete supported observation set and excluded audit. No member filter,
   best-component choice or deduplication of identical-looking primitives.
4. Every accepted P2B/R0/P2C record relevant to that lineage. Repeated occurrence
   references across pair artifacts are audited as aliases of the same exact
   endpoint, not additional parts. Conflicting fields are errors, not deduplication.
5. Every current Document TemporalIdentity, its bindings and promotion provenance,
   in canonical identity order. Identify all endpoints intersecting U, resolve the
   entire identity/provenance closure, and explicitly account for out-of-U endpoints.
   Do not silently drop a partly unresolved identity or certify its outside coverage.
6. Every source-defined part of every eligible subject, including not-observed
   parts. For each occurrence, classify all evaluated observations as an exact
   member association, source-proven unrelated observation, or unresolved. “Unrelated”
   needs source evidence; it is not the complement of a caller member list.
7. All accepted competing multipart claims for these roots/endpoints, including
   incompatible ownership. One observation cannot be claimed by two parts/subjects
   in this initial flat exclusive-ownership subset.

Unaccepted data found only in a resolver cannot fill a dependency. A missing
required accepted byte blob, wrong descriptor, invalid hash or forged derivation
is an acceptance error. An absent observation/identity or unsupported evidence path
in an otherwise valid source is an explicit coverage gap and yields UNCERTAIN,
not an omitted row. Required source membership must remain visible in either case.

Frozen P2A currently rejects a raster matching multiple manifest occurrences;
P2B rejects zero-supported frames. E0 does not repair either restriction. Such
inputs cannot obtain a supported bridge by inventing aliases, swapping manifests
or dropping a frame. A separately versioned upstream capability would be needed.

Every claimed member must match a complete source-enumerated part, and every
source-enumerated part must be accounted for. This two-way set equality is the
test that distinguishes complete membership from convenient chosen members.

## 8. Identity, provenance and record contents

Separate stable source identity from a base-bound verification result. Let H be
full lowercase SHA-256 of repository `canonical_bytes`.

For the structured-source direction, the proposed allocation domain is
`svm-multipart-subject-evidence@0.1`:

```text
source_subject_key = {
  ownership_profile_identity,
  ownership_root_artifact_id,
  canonical_source_subject_path
}
subject_id = "subject:multipart:" + H({identity_domain, source_subject_key})
part_id = "part:multipart:" + H({identity_domain, subject_id, source_part_key})
```

The admitted profile derives the path and part keys from the complete source,
never from caller strings, display names, Group IDs or semantic class labels.
The ownership root is an earlier accepted immutable input, not this evidence's
own bytes, a generated Group, or a receipt which contains the subject ID.
The root fixes the complete authored membership. Its byte identity namespaces
these snapshot-local subjects; no cross-file continuity is claimed.

Observation IDs remain the existing producer's IDs. A TemporalIdentity ID remains
R1's ID. Neither is repurposed as a part or subject ID. Complete observation/R1
closure affects evidence identity/applicability, not the stable source subject ID.
Hashing a proposed member set gives a hypothesis identity, not ownership authority.
Promotion metadata can record acceptance, but cannot manufacture an ownership root.

The proposed semantic record contains:

| Field group | Required content |
| --- | --- |
| Version | Evidence schema/semantics, ownership profile, bridge profile and producer implementation/configuration identities |
| Base | Source Revision ID and full Document hash; independently authenticated by Change snapshot/witness |
| Sources | Complete ordered exact accepted descriptors for root, video, manifest, raster/analysis/mask, P2A/P2B/R0/P2C and ownership proof dependencies |
| Universe | All covered occurrences/timebase and limits, full component evaluations, observation lineage, exclusions/unknowns and complete TemporalIdentity coverage projection |
| Subject | Reproduced source subject key and ID, complete canonical part set and source-derived membership proof |
| Parts | Part IDs/source keys and per-occurrence exact observation/evaluation links or explicit absence/uncertainty evidence |
| Temporal links | Existing identity IDs plus full bindings/provenance coverage and part/whole-subject distinction; no new R1 records |
| Judgment | SUPPORTED/UNCERTAIN/REJECTED, deterministic reasons, replayable proof references, unresolved coverage and competing claims |

Use a DerivedArtifact with a versioned `svm-...-0.1` schema and
`application/vnd.svm....+json;version=0.1` media convention. Exact serialized
field sets, reason order, dependency traversal, size limits and bridge schema
must be fixed with the first bounded producer in E1; these are design obligations,
not a generic payload interpreter authorized now. Unknown versions fail closed.
Finite canonical numbers and integer-not-bool timing retain existing conventions.

Subject/part allocation excludes score, status, base revision, current geometry,
evidence artifact ID, acceptance Revision and any later Group/Entity IDs. The
evidence blob hash includes the full verified record, so coverage/base changes
produce new evidence, not silent edits to old evidence. No extension across a
changed ownership root is automatically treated as the same subject.

```text
accepted ownership root + admitted profile -> subject key -> subject/part IDs
accepted video + manifest + analyses -> occurrence/component observations
accepted R0/P2C/R1 + authenticated base -> complete temporal coverage
all three + proof replay -> evidence bytes -> evidence Artifact ID
base + accepted evidence reference -> resulting Document -> resulting Revision
```

No arrow may return from evidence/result identity to its own inputs. Geometry or
newly observed information does not rename an already established artwork Entity;
future construction must retain birth identity under spec/71 and spec/72.

## 9. Producer, verifier and acceptance

A producer may use segmentation, learned models, motion or appearance to propose
a hypothesis and collect proof candidates. Record all result-affecting versions,
parameters, model/checkpoint identities, randomness and immutable outputs. Those
records improve reproducibility; they do not grant admission.

The trusted verifier owns the exact claim that can be admitted. It must:

1. Authenticate the full base snapshot with an existing-format Revision witness,
   bound through the existing `source_revision_resolver` to the actual Proposal base,
   following spec/72. A self-consistent invented snapshot is insufficient.
2. Independently enumerate U and the complete source membership/dependency closure.
3. Dispatch only an explicitly admitted, versioned ownership and bridge profile;
   artifacts cannot register code or declare their own authority.
4. Replay the source ownership proof and the video/observation bridge. Revalidate
   frozen R1 records as accepted observation ownership, without merging identities
   or upgrading R0's hypotheses into physical truth. Where the bridge requires R0
   derivation to be checked, reproduce the unchanged frozen policy in the new
   consumer; do not rewrite R0/P2C/R1 acceptance or alter any tolerance.
5. Reproduce the whole evidence record, including exclusions, unresolved cases,
   conflicts, IDs and exact descriptors; require byte equality.

A future exact registered evidence-only Change must guard incoming Document
equality before applying, then append only the verified evidence reference in one
atomic transaction. A preceding Change must not substitute a smaller universe.
No Group, Entity, TemporalIdentity, binding, Track or rendering state is created.
The verifier interface and ProposalAcceptor remain unchanged.

Artifact presence is not admission. Later consumers must replay the admitted proof
against authenticated accepted inputs and current applicability; a generic appended
record or `verified: true` cannot pass. Historical claims require authenticated
history where relied upon, not merely a receipt or transaction name.

Well-formed negative/uncertain evidence may be accepted for audit under the same
verifier. Acceptance of that record does not accept ownership. Only an independently
verified SUPPORTED result under its named profile is consumable as ownership proof.
Malformed/forged proof data rejects the transaction rather than becoming an ordinary
low-confidence hypothesis. Stale proposals require reproposal, never silent rebasing.

## 10. Temporal variation and abstention

Reuse the familiar judgment names, with meanings scoped to this new evidence
contract; do not change R0, P2A or GroupCandidate status semantics.

| Situation | Required evidence judgment / consequence |
| --- | --- |
| Complete fixed membership, exact ownership and unique observation bridge, no unresolved coverage | SUPPORTED within U only; genuine simultaneous contribution required |
| No ownership witness; confidence/motion/co-occurrence only | UNCERTAIN (`OWNERSHIP_UNPROVEN` design reason); no trusted membership |
| Temporarily missing observation | UNCERTAIN coverage; preserve the part in the membership ledger; no deletion or zero-length replacement |
| Claimed occlusion inferred only from overlap or disappearance | UNCERTAIN; neither cause nor hidden geometry is proven |
| Independently verified occlusion under a future admitted profile | Membership may remain supported only if that profile verifies complete latent membership and occurrence accounting; construction/baseline eligibility is separate |
| Newly seen observation of an already source-enumerated part | Reverify association and full coverage; retain subject/part identity, append new evidence only |
| Newly proposed part absent from the fixed source membership | REJECTED for the old claim if contradictory; otherwise UNCERTAIN pending a new ownership contract/source; no automatic membership extension |
| Analysis splits one part or merges several parts | UNCERTAIN bridge in the initial one-part/one-observation subset; no invented part IDs, borrowed Group members or implicit R1 merge |
| Exact witness proves a different owner, reused endpoint, or incompatible competing supported claims | REJECTED conflicting claim; never choose a winner or partially accept convenient members |
| Repeated pixel blob at different ticks | Distinct occurrences; existing P2A ambiguity still blocks its path. Never count repeated pixels as simultaneous parts |

The first bounded implementation should abstain on missing/occluded/split/merged
observations rather than implement latent recovery. Recording these cases is not
occlusion/deformation rendering. Do not infer deletion, birth, reparenting or
part replacement from failure to match. Fixed structural membership and observed
visibility must remain distinct, even when strict coverage makes the initial
profile ineligible.

## 11. Construction, correspondence and P2D are separate gates

The conceptual order is:

```text
accepted, verified multipart evidence
  -> separately admitted video artwork construction profile
  -> persistent renderable Entities + construction Group
  -> verified Stable Representation Correspondence
  -> separately versioned P2D consumer / existing S1 binding
```

For a video representation establishment, spec/72 requires the Entity fragment,
Group, receipt and representation correspondence to succeed atomically. The
arrows describe proof dependencies, not permission to commit an orphan Group
before correspondence succeeds.

The future construction profile must consume the exact SUPPORTED evidence
descriptor/bytes, admitted ownership root/profile, complete part keys, accepted
video/analysis/observation closure, complete current temporal coverage and
authenticated base. It must separately fix baseline selection, coordinates,
geometry/style construction, persistent Entity/Operation allocation, complete
fragment replay and receipt. It cannot choose only attractive visible parts or
use observations from different times as simultaneous Group members. E0 defines
no baseline, renderer, geometry repair or source-to-Entity constructor.

**Additional spec/71 dependency:** multipart evidence relates subject S to its
parts and their observations. Spec/71 initially relates one accepted
TemporalIdentity T to one representation Group G. T1/T2 belonging to parts do
not supply a whole-subject T. E0 SHALL NOT select one part as a proxy, merge T1/T2,
bind both to G, or put a subject ID into S1's TemporalIdentity field.

A future temporal profile must supply an independently justified whole-subject
observation identity and exact S-to-T coverage bridge compatible with the frozen
R1 contract, or obtain a separate normative decision before changing that consumer
scope. No such producer/bridge exists in the inspected paths. A valid structural
ownership record can therefore remain unusable for spec/71/P2D. This is a later
proof/consumer gate, not evidence that Entity/Group structure must change now.

After that gate, spec/71 still requires legal atomic establishment, authenticated
origin/history, continuity through edits, complete current identity coverage and
global conflict checks. Historical evidence does not silently certify new frames.
P2D-A remains its existing common-source derivation; P2D-B remains BLOCKED.
Frozen S1 remains explicit and one-to-one. No P2D implementation is authorized.

A single persistent renderable part remains outside the Group-based S1 scope.
No dummy/invisible member, artificial contour split, background filler or one-member
Group is permitted. Single-Entity Motion Target remains a separate open question.

## 12. Product direction and source generality

Structural identity can later support stable vector stylization, toon/cel/三渲二
rendering, identity-consistent repair, flicker suppression, unstable-shape repair
and local structure persistence. The evidence establishes none of those visual
quality results and contains no style, repair or rendering instructions. Preserve
original raster evidence independently of any future stylized representation.

Generic semantics are source authority, subject, parts, membership, occurrence
coverage and verification status. The first bridge may use video-specific
manifest/analysis inputs. Container details, decoder settings and producer source
graphs remain in profile evidence; no UI, 3D scene, mesh, bone or camera-rig fields
are added to Core.

## 13. Next gate: P2S-E1 bounded ownership-proof profile

E1 must specify and demonstrate one independently checkable source-ownership
witness and video bridge before any runtime implementation can claim SUPPORTED
multipart evidence. If only ordinary pixels and heuristic output are available,
the correct result remains UNCERTAIN; do not invent a positive fixture by calling
two observed components a subject.

The next specification must fix the exact source grammar, root admission,
production/observation verification, dependency enumeration, record schema,
canonical ordering, reason taxonomy, resource limits and deterministic profile
identity. Prefer a controlled authored-source proof with two genuine parts and
two covered occurrences. This is a source-profile feasibility demonstration,
not a claim that arbitrary video is solved. Ownership and the frame bridge must
come from independent source inputs, never from expected SVM output or a
caller-selected member list.

Required future executable obligations:

- Positive: independently sourced complete authored assembly, exact video bridge,
  all components and exclusions audited, stable part IDs across occurrences,
  byte-identical replay, evidence-only atomic acceptance and isolated preview.
- Negative control: visually/motion-identical unrelated objects do not gain common
  ownership without a source witness; removing or forging that witness abstains
  or rejects even if every heuristic score remains high.
- Omitted part, occurrence, rejected evaluation, identity, provenance path, competing
  root/claim, analysis or required descriptor cannot shrink the universe.
- Resolver-only sources, accepted-but-generic appended claims, fake profile names,
  self-attestation and model confidence cannot bypass proof replay.
- Wrong timing, duplicate endpoint, repeated pixels, split/merge, missing/occluded
  observations and unsupported source versions produce the specified outcomes.
- Stale/forged base witness, preceding-Change substitution, missing/corrupt bytes,
  denied `attach_analysis` and any partial mutation fail atomically.
- Evidence IDs are acyclic; scores/base edits change evidence but not source subject
  identity; changed ownership roots do not silently preserve source identity.
- Multiple part TemporalIdentities stay distinct; no whole-subject T, Group, Entity,
  Motion Target Binding or Track is created as an evidence side effect.

After the bounded profile specification is reviewed, implement its producer and
evidence-only verifier together with the Golden/adversarial cases above. Passing
those cases is the gate for claiming implemented evidence authority. Video
construction, whole-subject identity/correspondence and P2D remain subsequent
explicit gates. No frozen tolerance, test or authority is relaxed to make the
example positive.

## 14. Audit completion

Outcome B is chosen because immutable artifacts plus existing registered
verification/acceptance mechanisms can express the missing relation. Outcome A
fails the evidence inventory; outcome C is unnecessary for this evidence scope.
This does not promise extraction of unobservable semantic truth from pixels.

This change is documentation/specification only. No Python, schema, test, Group,
runtime, P2D-A/B or frozen numeric behavior is changed. TemporalIdentity remains
observation identity, and single-Entity targeting remains separate.

## 15. P2S-E1 capability audit — blocked before profile admission

Inspection baseline: `04d44f5896e13b83ec97e70cdcb937bd584d4f86`, clean working
tree. E1 is specification/feasibility only. Its stop condition applies:
**SOURCE_VIDEO_BRIDGE_CAPABILITY_REQUIRED**. No spec/75, production profile,
canonical evidence schema or positive Golden is admitted by this audit.
E0's evidence-model feasibility conclusion remains valid; the missing capability
is an executable source-production/observation bridge, not a demonstrated need
to change Entity, Group or TemporalIdentity.

### 15.1 Existing executable capabilities inspected before profile selection

| Files / entry points | Available capability | Missing proof |
| --- | --- | --- |
| `spec/73`; `svm/adapters/svg_group_construction.py`: `_parameters`, `_derive`; `svm/adapters/svg_import.py`: `SVGNormalizer`, `_parse`, `_shape` | Exact authored `svg/g/rect+ellipse` ownership and ordinary geometry normalization | No frame-production recipe, raster output or source-part/video association |
| `spec/08`; `svm/evaluator.py`; `svm/scene.py`; `svm/renderers/__init__.py`, `svg.py` | Pure geometry evaluation, transformed Evaluated Scene, deterministic SVG text | The renderer package exports SVG rendering, not a controlled binary raster producer with per-part contribution outputs |
| `tools/run_pop_golden_p.py`: `rasterize_svg`, `parity_metrics`; `pyproject.toml` | SVG-to-PNG parity helper using CairoSVG, falling back to Chromium screenshots | Backend fallback and no fixed cross-platform pixel/canonicalization contract; no admitted source-part contribution production. SVG parity is not exact binary-video proof |
| `svm/adapters/pop_structure.py`: `_validate_exact_pop_scene`, `_geometry_mask`, `_primitive_contains`, `_topmost_masks`; `spec/27` | Deterministic 256x256 pixel-center geometric masks for the exact reconstructed POP primitive scene | Q requires genuine POP prefix/output and unchanged scene. Its masks are geometric coverage, not general SVG rasterization or alpha contributions. No SVG-source/video production profile; private numeric helper reuse alone would not establish it |
| `spec/59`; `svm/video_ingestion.py`: `canonical_frame_png`, `_decode`, `_produce`, `ingest_video`, `verify_video_manifest` | Pinned FFV1 decode, full stream checks, exact rational timing and canonical black/white PNGs; re-verifiable manifest | Direction is video-to-frames. No accepted structured source or per-part attribution is an input to that proof |
| `examples/036-controlled-raster-camera-recovery/README.md`, `examples/037-explicit-multi-object-raster-recovery/README.md`, `examples/038-controlled-video-ingestion/README.md`; `tests/test_video_ingestion.py`, `test_video_recovery.py` | Offline polygon fixtures use existing transforms, NumPy rounding and OpenCV `fillPoly`; offline FFV1 encoding and checked-in decode/reference equality exist | Fixture provenance notes and ground truth are not an executable ownership-bound source-production verifier. Recovery tests deliberately consume video/pixels without source-vector/ground-truth inference. No reusable authored multipart production entry point was found |
| `tests/test_raster_primitive_observation_proposal.py`: measurement cases; `svm/adapters/raster_primitive_observation_proposal.py`: `measure_component`, `derive`; `spec/64` | Actual OpenCV component measurements and acceptance replay under frozen contour eligibility | Requires a distinguishable landmark origin; exact source ownership does not change pixel eligibility |
| `svm/adapters/primitive_observation_assembly.py`: `_frame`, `derive`; `spec/66` | All SUPPORTED evaluations materialized, all exclusions audited, exactly two selected occurrences | Does not materialize UNCERTAIN/REJECTED parts or attach source-part identity; zero supported in either frame fails |
| `svm/adapters/temporal_correspondence.py`, `temporal_identity_selection.py`, `temporal_identity_promotion.py`; `spec/35`, `spec/36`, `spec/68` | Pairwise hypotheses, ALL-SUPPORTED selection and stable observation ownership | No source rasterization, simultaneous assembly proof or whole-subject identity construction |
| `svm/artifacts.py`; sections 7–9 above | Content-addressed bytes, exact descriptors, Reference/Derived distinction and future evidence-only admission obligations | Importing a source/manifest/sidecar is not proof of their causal or structural relationship |

Repository-wide searches of Python production, tools and tests found no other
source-to-video generator or exact source-part raster verifier. The `VideoWriter_fourcc`
calls in ingestion check the decoder's codec tag; they do not encode video.
The offline fixture recipe is useful implementation precedent, not an existing
complete executable bridge. Drawing calls in measurement tests do not bind an
independently accepted authored subject to a video occurrence.

There are useful deterministic raster *building blocks*. The finding is not
that SVM contains no pixel mathematics, nor that FFV1 cannot preserve pixels.
Combining those blocks into a new SVG/part renderer and verifier would introduce
the missing production semantics, which E1 explicitly forbids inventing to pass
the feasibility gate. Recasting SVG shapes as a captured POP run is also forbidden.

Byte-identical AVI re-encoding is not asserted to be necessary for every future
bridge: independently produced exact frames could be compared with canonical
decodes of an accepted immutable AVI. That would reuse spec/59. The decisive
missing link remains independent authored-source-to-frame/per-part production
and verified attribution; a source video hash alone cannot supply it.

### 15.2 Preferred ownership root evaluated, not selected

Spec/73 is a sound ownership root in its own domain: sole SVG `g` at path `[0]`,
exact ordered leaves `rect:0`, `ellipse:1`, canonical bounded integer attributes,
no transforms/animation/extra elements. Its accepted source bytes independently
define both parts. Its successful construction receipt says nothing about video.

The preferred root is not adopted for E1 because the full required bridge is
unavailable. Even the closest existing mask comparison exposes a second obstacle
to the proposed positive P2A/P2B route.

A read-only Python 3.12 diagnostic called the existing POP `_geometry_mask` on
four geometry dictionaries, unpacked each bitset to a 256x256 uint8 component
mask, then called the unchanged P2A `measure_component`. It wrote no fixture,
Python file, test, Artifact, Document or artwork. Results:

| Probe geometry, in pixel coordinates | Contour area | Minimum edge | Longest-edge margin | P2A result |
| --- | ---: | ---: | ---: | --- |
| Spec/73 Golden rectangle: x=0, y=0, width=20, height=10 | 171 | 9 | 0 | REJECTED: `AREA_BELOW_256` |
| Spec/73 Golden ellipse: cx=30, cy=5, rx=5, ry=3 | 37 | 2.8284271247461903 | 0 | REJECTED: `AREA_BELOW_256`, `MIN_EDGE_BELOW_8` |
| Larger rectangle: x=20, y=20, width=80, height=40 | 3081 | 39 | 0 | UNCERTAIN: `AMBIGUOUS_LANDMARK_ORIGIN` |
| Larger ellipse: cx=160, cy=80, rx=40, ry=25 | 3057 | 10 | 0 | UNCERTAIN: `AMBIGUOUS_LANDMARK_ORIGIN` |

All four return `ordered_landmarks = null`. P2A requires longest-edge margin
greater than 4 after earlier checks succeed. P2B excludes these evaluations;
the probed two-part combinations supply no supported primitive in a frame.
The diagnostic is not an admitted rasterization recipe or a general theorem
about every transformed ellipse. It demonstrates that neither the exact Golden
nor simply using these larger symmetric shapes supplies the proposed positive.
Integer translation does not repair those measured edge ties.

Do not introduce asymmetry, crop a part, relax a threshold, synthesize landmarks,
reinterpret UNCERTAIN as SUPPORTED, or change source grammar merely to evade this
result. An alternative independently authored source with eligible parts would
still need its own bounded ownership grammar and executable production bridge.
The asymmetric polygon fixtures do not already supply that ownership authority.

### 15.3 Disposition of the requested profile design

The stop condition takes precedence over filling in a non-executable contract.

| Requested item | Disposition at this baseline |
| --- | --- |
| Selected root / source grammar | None admitted; spec/73 exact two-part source evaluated above |
| Production identity, recipe and frame parameters | Not defined: missing executable bridge must be supplied first |
| Per-part contribution proof | Missing outside restricted POP evidence; whole-frame equality, order or approximate shape matching is insufficient |
| Complete universe | Retain §7: all two manifest occurrences and complete accepted evaluations/observations, exclusions, dependencies and competing claims; no convenient pair from a larger manifest |
| P2A/P2B mapping | Future bridge must prove unique exact full-pixel contribution-to-component correspondence in frame coordinates, then resolve exact evaluation/observation lineage. Bbox-relative component digest alone is insufficient; do not choose first/best or use component order |
| TemporalIdentity | No mutation or whole-subject merge. Source-part identity plus exact production may be sufficient for structural ownership without part R1 IDs, but no positive profile adopts this option here. Existing identities must still be audited completely; spec/74's exact coverage requirements need explicit refinement if absence is made non-blocking |
| Canonical schema / IDs | Deferred under the stop condition. No schema/media/profile identity or unmeasured Golden IDs are fabricated; §8 remains a design obligation |
| Judgment | No SUPPORTED bridge can be claimed. Missing ownership in otherwise legitimate input remains UNCERTAIN / `OWNERSHIP_UNPROVEN`; incomplete/ambiguous mapping is ineligible/UNCERTAIN; forged or contradictory proof rejects acceptance. These are obligations, not newly executable statuses |
| Positive Golden | Blocked; no fixture/evidence/expected-ID set produced. Must start with independent authored input and demonstrate eligible per-part production before specifying expected evidence |
| Negative control | Retain identical AVI/decoded observations but omit the independently accepted ownership root (including resolver-only root variant): never SUPPORTED, ownership unproven. No current E1 runtime is claimed to execute this case |
| Evidence-only acceptance | Future authenticated full-base replay, independently enumerated closure, canonical record equality, incoming-state guard and `attach_analysis` only; no new registration in this task |

### 15.4 Retained adversarial obligations, not new tests

| Cases | Required future boundary |
| --- | --- |
| Missing/resolver-only ownership root; multiple eligible roots | Missing authority is unproven; multiple roots abstain without choosing; a claim falsely declaring them accepted/unique rejects |
| Missing source subject; omitted/extra/reordered part; changed source bytes | Exact source grammar/membership/identity mismatch rejects; no subset or byte substitution |
| Wrong production profile/parameter; changed frame or per-part contribution; wrong video/manifest | Independent production/decode/contribution comparison rejects |
| Manifest >2; omitted occurrence; wrong tick/time | Complete bounded-universe/timing rule rejects; no truncation or retiming |
| Missing P2A evaluation; omitted REJECTED/UNCERTAIN evaluation; duplicate observation | Complete re-derived audit must match; forged omission/duplication rejects |
| Ambiguous mapping; missing part observation; split/merge | Legitimate coverage gaps are UNCERTAIN/ineligible; no heuristic tie-break or synthetic part |
| Observation reused for two parts; incompatible supported competing owner | Contradiction rejects; no winner or partial subset |
| Stale base; forged snapshot; preceding Change substitution | Ordinary staleness, authenticated base witness and incoming-state guard reject atomically |
| Fake profile/media; self-attested supported flag; wrong descriptor | Closed-world admission and independent replay reject; hashes/labels are not proof |
| Denied `attach_analysis`; partial mutation attempt | Policy/atomic acceptance rejects; no evidence or artwork side effect |

### 15.5 Next capability gate

Before retrying E1, separately authorize and demonstrate a bounded independently
authored-source production capability with fixed pixel semantics, complete
per-part masks/contributions and exact comparison to spec/59 canonical decoded
frames. Demonstrate that both genuine source parts reach the unchanged P2A/P2B
observation path; otherwise report that observation-eligibility limitation for a
separate versioned decision. No threshold relaxation or frozen-code change is
authorized by this finding.

Only after that capability exists can E1 choose a profile, freeze its complete
serialization/IDs and specify a real positive Golden plus the negative controls.
Whole-subject TemporalIdentity, spec/71 representation correspondence, artwork
construction and P2D-B remain later gates. Ordinary-video ownership inference and
single-Entity targeting remain unsolved. No deeper Core structural-model change
is demonstrated by this audit.
