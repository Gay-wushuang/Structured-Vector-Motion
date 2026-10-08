# P2S-F0 — First Video-backed Artwork Construction Profile

Status: **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN**.
Design baseline: `1584de5f74a69b825777cc453b87c7d6a83e5ad4` (clean working tree).
Implementation baseline: `0497db6b1ef4202f5e3d0708e5cfe4cc3f1b29fd`.
The executable bounded profile, registered Change, dedicated verifier, closed
validator/schema enum and Golden fixture implement the contract below.

Profile identity: `svm-video-two-part-group-construction@0.1`.
Authority: `svm-construction-derived-group@0.1` ([spec/72](72-construction-derived-group-authority.md)).
Consumed evidence profile: `svm-authored-two-triangle-multipart-evidence@0.1`
([spec/76](76-first-bounded-multipart-subject-evidence-profile.md)).
Admission authority: [spec/77](77-trusted-spec76-admission-history.md).

## 1. Scope, identity and reused authority

This is the first bounded **representation-construction profile** anticipated by
spec/71 §4 and §11: it consumes genuinely admitted Multipart Subject Evidence and
deterministically establishes persistent, renderable artwork — two triangle
Entities and one legal construction-origin Group — in one atomic transaction.
It reuses the Spec75 authored source (§4) and the Spec72 authority semantics
unchanged: same authority identity, same construction-origin provenance branch,
same manifest schema, same canonical Group ID formula, same initial-Transform
rule, same atomic composite-Change pattern and the same policy intent set.

It is **not** a correspondence consumer. It creates no TemporalIdentity, no
Track, no Keyframe, no MotionTargetBinding, no S1 binding, no P2D consumer and
no representation-correspondence claim. Section 13 records that dependency.

The admissible world is exactly the Spec76 profile world: one accepted authored
SVG assembly under grammar `svm-svg-g-two-triangle-paths@0.1`, its two path
parts `part-a`/`part-b`, the fixed Spec75 production policy, one admitted
SUPPORTED evidence claim, and unchanged Spec59/P2A/P2B machinery. Arbitrary
video, arbitrary sources, other shape counts, generic profile plugins, heuristic
grouping and geometry producers are forbidden.

Reused fixed constants (no new spellings):

```text
authority_identity   = "svm-construction-derived-group@0.1"
origin type          = "construction-established-group@0.1"
manifest schema      = "svm-group-construction-manifest-0.1"
manifest media       = "application/vnd.svm.group-construction-manifest+json;version=0.1"
evidence media       = "application/vnd.svm.multipart-subject-evidence+json;version=0.1"
evidence schema      = "svm-multipart-subject-evidence-0.1"
```

New fixed identities introduced by this profile only:

```text
profile_identity     = "svm-video-two-part-group-construction@0.1"
receipt schema       = "svm-video-two-part-group-establishment-0.1"
receipt media        = "application/vnd.svm.video-two-part-group-establishment+json;version=0.1"
```

## 2. Trust boundary: admission authentication through Spec77 history

Valid evidence bytes alone are insufficient. Legacy or generically attached
references remain representable historical data (Spec76 §9, §19; Spec77 §5) and
confer no ownership authority. Before any construction claim can be consumed,
the construction Change MUST authenticate the actual dedicated admission:

1. The registered composite Change (`EstablishVideoArtworkGroupChange`, §14)
   carries the complete ancestral witness DAG of its base
   (`RevisionSnapshotWitness` records, canonical Revision-ID order) and the base
   document snapshot. Authentication recomputes every existing-format Revision
   commitment from its snapshot, parent IDs, transaction ID, message and any
   Spec77 admission events; every parent must be present; only nodes reachable
   from the anchored base are permitted; per-node admission events must satisfy
   the Spec77 consistency contract (`AdmittedRevision`, exact contract/change/
   authority identities, single parent, recomputed transition commitment, exact
   new-reference coverage). This is the Spec76 §19 mechanism, reused unchanged —
   no new history mechanism is introduced.
2. The Acceptor's existing source-revision resolver binds `source_revision_id`
   to the real Proposal base; the base witness node's document must canonically
   equal the change's `base_document_snapshot`.
3. An admitted claim requires a matching admission event in that authenticated
   ancestry: `event.artifact_reference` must canonically equal the exact
   consumed evidence descriptor, and `event.base_revision_id` must equal the
   record's committed base (`record["base"]["revision_id"]`). Matching events
   for one descriptor must be a single distinct admission transition; multiple
   distinct matching events reject.
4. The record's base commitment must equal the authenticated ancestor snapshot:
   the ancestor revision at `record["base"]["revision_id"]` must exist in the
   DAG and its document hash must equal `record["base"]["document_hash"]`.

Trust root: this construction does **not** re-run the Spec75/Spec76 pixel and
P2A/P2B closure. That reproduction is the dedicated Spec76 verifier's
admission-time obligation, and the Spec77 admission event is Core's authority
that it succeeded. All of its recorded inputs are content-addressed immutable
artifacts; §3 re-verifies their exact accepted presence and §4 re-reproduces the
source facts. A later correspondence consumer may demand stronger current
coverage re-verification (spec/71 §7); this profile makes no such claim.

## 3. Evidence enumeration, applicability and uniqueness

The verifier independently enumerates the evidence universe from the
authenticated base. No caller selector, list or ordering participates.

A base reference with the Spec76 media type is inspected descriptor-first:

- **No matching admission event** → legacy data. It is not read as authority,
  its bytes are not required or consumed, and it MUST NOT influence any
  outcome.
- **Matching admission event** → it is a candidate claim. Its bytes MUST be
  resolved and transported; an unenumerable or unresolvable event-bearing
  reference rejects the whole transaction (fail-closed, no selective omission).
  A descriptor that does not exactly equal an admitted transition's descriptor
  simply has no matching event; no normalization, resynchronization or
  reinterpretation exists.

A candidate is **eligible** at the authenticated base iff every condition holds:

1. exact descriptor present in the base Document references and bytes hash to
   that descriptor (content-addressed; imported into a scratch repository for
   resolution);
2. the record bytes are canonical (`canonical_bytes`), parse as JSON, satisfy
   the Spec76 §12 closed-world field set exactly (unknown, missing or extra
   fields reject), carry the exact `schema_version`, `profile_identity` and
   `production_policy` constants of §1, no `status`/`judgment` field, and
   descriptor provenance exactly `{profile_identity: <Spec76 profile>}`;
3. the admission binding of §2 holds (event identity, record base commitment,
   ancestry);
4. the complete recorded dependency closure remains exact-accepted: the
   record's `source`, `video` and `manifest` descriptors, every descriptor in
   `dependencies`, and the record's `source.source_revision_id` (as an
   authenticated ancestor). Descriptor equality is canonical and complete; a
   changed, removed or renamed descriptor makes the claim inapplicable;
5. the claim key is recomputed and matches: `claim_key` equals `H(canonical_bytes(
   claim_projection))` over the record's exact `profile_identity`, `subject_id`,
   `parts` (source order), `universe` (manifest order) and projection-reduced
   `membership` (`occurrence_id`, `part_key`, `observation_id`), per Spec76 §9.1.

Exactly one eligible candidate MUST exist. Zero candidates reject (the
ownership proof is missing, stale, unproven or ambiguous — never rebased or
replaced by bytes). Two or more candidates reject as an ambiguous evidence
universe with no tie-break, even when their subjects differ. The consumed
evidence descriptor MUST canonically equal the unique eligible candidate's
descriptor; there is no caller or producer selection among claims, sources or
observations.

## 4. Source reconstruction and exact dependencies

The source is the exact accepted descriptor named by the eligible claim's
`source` field. There is no SVG enumeration and no source selector: the claim
selects the subject, not the caller. The source MUST be an accepted
ReferenceArtifact with `media_type == "image/svg+xml"`; unrelated accepted SVG
artifacts neither participate nor block.

The verifier reuses the exact Spec75 grammar implementation (the
`svm-svg-g-two-triangle-paths@0.1` parser in `svm/authored_raster_production.py`
or a behavior-identical extraction; a second grammar interpretation is
forbidden) and re-derives from the accepted source bytes:

- the sole `g` subject at canonical path `[0]`;
- the two path parts, `part-a` then `part-b`, with their exact `d` lexemes;
- the canonical path bounds of each part via the existing
  `canonical_path_bounds` semantics.

It then requires exact agreement with the admitted record: the recomputed
Spec76 subject identity (`subject:multipart:…`, Spec76 §6 formula over
`ownership_profile_identity`, `ownership_root_artifact_id`, path `[0]`) equals
`record["subject"]["subject_id"]`; the record's
`subject.ownership_root_artifact_id` equals the source Artifact ID; the
recomputed part identities equal the record's complete `parts`; the video and
production manifest descriptors equal the record's fields and remain
exact-accepted.

The source subject object used by this profile is deliberately the existing
Spec75/Spec73-shaped object:

```json
{"source_artifact_id": "artifact:<64 lowercase hex>", "subject_path": [0]}
```

## 5. Identity allocation

Let `H` be full lowercase SHA-256 of repository `canonical_bytes`. For each
logical part key `part-a` then `part-b`:

```text
subject = {source_artifact_id: <accepted source Artifact ID>, subject_path: [0]}
allocation = {
  authority_identity: "svm-construction-derived-group@0.1",
  profile_identity: "svm-video-two-part-group-construction@0.1",
  subject: subject,
  part_key: "part-a" | "part-b"
}
Entity ID    = "entity:" + H({**allocation, record_kind: "entity"})
Operation ID = "op:"    + H({**allocation, record_kind: "operation", role: "geometry"})
```

The Spec76 `subject:multipart:` identity, the evidence Artifact ID, admission
transitions, base revisions, observations, occurrence identities, video bytes,
geometry measurements, styles and every caller string are **not** allocation
inputs. Entity records contain exactly `id` and `name`; names are the fixed
source part keys `part-a` and `part-b` (grammar-mandated constants, never
allocation inputs, never caller names). Member lineage lives in the verified
manifest and receipt, not in fabricated Entity provenance.

## 6. Reconstructed fragment

For the checked-in Golden source the reconstructed geometry is exactly:

| Part | Operation | `d` | `bounds` |
| --- | --- | --- | --- |
| part-a | `CreatePath` | `M 20 20 L 100 20 L 20 80 Z` | `[20, 20, 100, 80]` |
| part-b | `CreatePath` | `M 140 120 L 212 120 L 140 174 Z` | `[140, 120, 212, 174]` |

Generally, each part's `d` is the exact source `d` lexeme and `bounds` is its
existing canonical path bounds. The complete fragment, in source order, is:

- two Entities (`{id, name}`, names `part-a`, `part-b`);
- two Operations (`CreatePath`, empty inputs, parameters exactly `{d, bounds}`);
- one `geometry` binding per Entity to `Operation ID + ".geometry"`;
- one complete style per Entity: fill `#000000`, stroke `none`,
  `stroke_width` `1.0`, `opacity` `1.0`;
- the two Entity IDs appended to the existing Render Stack in that order.

Coordinates are source user coordinates used directly as Document coordinates,
before Group and Camera, with no viewBox remapping. Geometry is deliberately
**source-fixed**: no occurrence, frame, translation, observation, P2B
measurement or pixel replay selects or adjusts the initial geometry. Member
bounds are computed by the Spec73 procedure — apply the fragment to a Document
copy, evaluate each Operation with the ordinary evaluator and read
`operations._geometry_bounds` — and must equal the canonical path bounds above
in fragment order. The evaluated geometry kind is the existing `path_data`; the
existing SVG renderer emits it as a path with no GeometryBackend, PathToPolygon,
tracing, OpenCV, re-import or screenshot route.

## 7. Group definition

Exactly one Group is created. Members are the lexicographically sorted unique
IDs of **all** reconstructed Entities (for the Golden fixture the sorted order
places `entity:e41b…` (part-b) before `entity:eea3…` (part-a)); no filtering,
pruning or caller membership. Cardinality remains the existing minimum of two
real members; no dummy, filler, temporal alternative or artificial split is
admitted.

```text
group_id = "group:" + H({authority_identity, profile_identity, members})
provenance = {
  type: "construction-established-group@0.1",
  authority_identity: "svm-construction-derived-group@0.1",
  profile_identity: "svm-video-two-part-group-construction@0.1",
  construction_artifact_id: <constructed manifest Artifact ID>
}
transform = {translate: [0, 0], rotation_degrees: 0, scale: 1,
             origin: [canonical((xmin+xmax)/2), canonical((ymin+ymax)/2)]}
```

The origin is the canonical center of the union of the verified member bounds
(`[116.0, 97.0]` for the Golden fixture) using the existing scene canonical
number convention; finite, nondegenerate extents are required. No candidate/
inference/POP/Q fields are fabricated; no `promote_group` intent is ever
emitted. Spec/30 matrix composition, fixed origin and unique transformed
membership are unchanged, and the Group is not an S1 target, not a P2D
candidate and not a Track owner.

## 8. Construction manifest and establishment receipt

The manifest reuses the Spec72 §6 schema and media type exactly:

```text
schema_version = "svm-group-construction-manifest-0.1"
authority_identity, profile_identity                      (§1 constants)
source_base_revision_id, source_base_document_hash        (authenticated base)
subject                                                    (§4 subject object)
parameters = {}                                            (exactly empty)
source_references = [evidence descriptor, source descriptor]   (order normative)
fragment = complete §6 fragment (no references)
member_bounds = per-member bounds in fragment order
```

`source_references` lists the two directly consumed accepted descriptors in the
normative order above; the transitive video/manifest/P2A/P2B closure remains in
the admitted evidence record and is re-verified by §3. The manifest contains no
Group ID, Group provenance, receipt reference, resulting Document hash or
resulting Revision ID, and no self-referencing value. Manifest bytes are
`canonical_bytes`; the manifest Artifact is an existing-contract DerivedArtifact
with descriptor provenance exactly `{authority_identity, profile_identity}`.

The establishment receipt has exactly these fields:

```text
schema_version = "svm-video-two-part-group-establishment-0.1"
authority_identity, profile_identity
source_base_revision_id, source_base_document_hash
source_references = [evidence descriptor, source descriptor]
subject = §4 subject object
evidence = {
  reference: exact admitted evidence descriptor,
  admission: {base_revision_id, transition_hash},      (the authenticating event)
  claim_key, subject_id, parts, universe, membership   (exact record values)
}
fragment = complete §6 fragment
construction_reference = exact manifest descriptor
group = complete Group definition including initial Transform
representation_claim = null
```

The `evidence` block copies the record's exact `claim_key`, subject identity,
complete `parts`, `universe` and `membership` verbatim; it is reproducible from
the admitted evidence bytes and is never authority by itself. The `admission`
values are reproduced from the authenticated ancestry, never trusted from a
proposal. `representation_claim` MUST be null; any supplied non-null
TemporalIdentity/Group correspondence claim rejects — this profile cannot
supply correspondence. Receipt bytes are `canonical_bytes` with the §1 receipt
media type, kind DerivedArtifact and descriptor provenance exactly
`{authority_identity, profile_identity}`. The receipt excludes its own Artifact
ID, the resulting Document hash/Revision ID, any observation selection and any
baseline tick. Unknown, missing, extra or mismatched fields reject by canonical
reconstruction equality.

## 9. Hash dependency DAG

Arrows mean "is an input to". This ordering is normative:

```text
accepted authored source bytes + accepted video/production-manifest/P2A/P2B/raster closure
    -> Spec76 SUPPORTED evidence record (content-addressed)
accepted evidence record + dedicated acceptance transaction -> Spec77 admission event
    (lives in the acceptance Revision, fixed before any construction exists)
evidence descriptor + authenticated ancestry -> unique eligible claim (§3)
eligible claim source descriptor -> accepted source bytes -> grammar parts + canonical bounds
source-qualified subject + authority + profile + part keys -> Entity IDs / Operation IDs
Entity/Operation IDs + source d/bounds -> fragment -> evaluated member bounds
member bounds -> initial Transform (canonical union center)
source base commitment + evidence/source descriptors + subject + parameters{} +
    fragment + member_bounds -> manifest bytes
manifest bytes -> construction Artifact ID
construction Artifact ID + authority + profile -> Group provenance
authority + profile + sorted member IDs -> Group ID
Group ID + members + Group provenance + initial Transform -> Group definition
manifest descriptor + fragment + group + subject + source base commitment +
    evidence{reference, admission, claim} + source descriptor -> receipt bytes
receipt bytes -> receipt Artifact ID
base Document + fragment + Group definition + [evidence, source, manifest, receipt] references
    -> post Document
post Document -> document hash
document hash + parent base Revision + transaction metadata -> resulting Revision ID
```

Acyclicity: no F0 output is an input to the evidence record, its admission event
or its acceptance Revision; no output embeds its own Artifact ID or the
resulting Revision ID; Entity IDs depend only on accepted source identity and
fixed constants; the Group ID does not depend on the manifest, receipt or post
state; the receipt embeds the manifest/Group but nothing points back. The
dependency graph remains acyclic under Spec76 §12.1 and Spec72 §9.

## 10. Complete-base verification, atomic establishment and rollback

The registered composite `EstablishVideoArtworkGroupChange` (CREATE only)
performs, in order, before any publication:

1. exact profile/type checks: `profile_identity` is the §1 constant, the
   fragment is a plain `AppendSceneFragmentChange` with no references, the
   group/evidence/fragment shapes are well formed;
2. witness-DAG and base authentication (§2), including the Spec77 per-node
   admission consistency checks;
3. complete evidence enumeration, eligibility and uniqueness (§3), including
   transport completeness: every event-bearing evidence descriptor in the base
   MUST be resolved;
4. source reconstruction, subject/parts agreement, claim-key recomputation
   (§4);
5. full output replay (§5–§8): allocation, fragment, member bounds, Group,
   manifest bytes, receipt bytes — compared by canonical equality against the
   proposed change and against the resolved new artifacts (bytes and
   descriptors);
6. reference-set equality with the transported descriptors;
7. policy enforcement with exactly the Spec72 intent set: `establish_group` on
   `document`, `import_scene` on `document`, `set_group_transform` on the new
   Group ID with parameter `transform`, and `attach_analysis` on `document`.
   Denying any required action rejects the entire transaction atomically.

`apply()` re-guards canonical equality of the actual incoming Document against
`base_document_snapshot` (spec/72 `STALE_CONSTRUCTION` pattern) and checks
Entity/Operation/Group ID collisions, reference descriptor conflicts and
transformed-ownership conflicts. The checked candidate is then published once
through the trusted commit path; this Change creates **no** admission event
(Spec77 enforcement remains in force and passes because no reserved Spec76
media reference is added, removed or changed).

Reject the entire establishment for: base Revision or Document mismatch (no
silent rebase); no eligible claim; ambiguous or unresolvable evidence universe;
forged, malformed or tampered record; missing/mismatched admission event;
changed/removed dependency descriptor; source grammar or bounds violation;
subject/parts/claim-key disagreement; any fragment/Group/manifest/receipt
mismatch; any ID collision (including byte-identical duplicates — this is
creation, not adoption or retry-as-update); transformed-ownership conflict;
denied policy intent.

Atomicity: preview and `validate()` change no accepted state. Any rejection
leaves HEAD, Revision count, Document, Groups, render entries and accepted
references unchanged, and no orphan target, receipt or partial Render Stack may
remain. Alternatives are not supported in this slice: no adoption of existing
artwork, no update mode, no caller-composed fragment-plus-Group sequence, no
generic reference append. Ordinary optimistic staleness after any base edit
requires reproposal; reproposal preserves the same allocation for the same
source subject, so an already established subject collides and rejects, while a
still-unconsumed subject re-establishes identically. Established identities are
never recalculated by later edits; the receipt records the birth facts, and
later consumption proofs (spec/71 §7) are a separate, unimplemented gate.

## 11. Adversarial matrix

Implementation must cover at least these cases. Every rejection is atomic and
leaves the Revision Store unchanged.

| # | Case | Required outcome |
| --- | --- | --- |
| 1 | Generic admission: byte-valid evidence appended via `AppendReferencesChange` or any generic path | No admission event → no eligible claim → reject; bytes remain data |
| 2 | Legacy re-admitted reference without event | Same as #1; never consumed |
| 3 | Forged/missing/reordered/rehashed witnesses, unanchored history | Reject by DAG authentication; no partial state |
| 4 | Invented/rehashed admission event for the exact descriptor | Reject: event must live in the authenticated ancestry and reproduce |
| 5 | Admission event base ≠ record base, or record base absent from DAG, or record base hash mismatch | Reject |
| 6 | Other-branch or stale claim (event not in ancestry) | Not admitted here → no eligible claim → reject; never rebased |
| 7 | Two eligible claims / caller tries to select one of several | Ambiguous universe → reject; no tie-break |
| 8 | Event-bearing evidence descriptor omitted from transport or unresolvable | Reject (fail-closed; no selective shortlist) |
| 9 | Record field set, schema, profile, production policy, provenance or canonical bytes tampered | Reject |
| 10 | Claim key disagreement with recomputed projection | Reject |
| 11 | Source bytes changed, grammar violations (tree, ids, lexemes, range, overlap, winding), reordered/omitted/extra parts | Reject without repair |
| 12 | Video/production-manifest/dependency descriptor changed, removed or renamed at base | Claim inapplicable → reject unless another eligible claim exists |
| 13 | Incorrect geometry: changed `d`, wrong bounds, swapped parts, nonfinite values | Fragment replay mismatch → reject |
| 14 | Incomplete fragment: missing/extra Entity, binding, style, render entry, or reordered entries | Exact fragment equality rejects |
| 15 | Caller-supplied members, Group ID, provenance, Transform, subject or evidence selection | Not an input; replay mismatch rejects |
| 16 | Stale base / preceding Change mutates the base snapshot | Incoming-Document guard rejects atomically |
| 17 | Duplicate construction of the same source subject (same or different evidence) | ID collision → reject; CREATE only |
| 18 | Unauthorized Group creation: fabricated Q/POP provenance, spec/73 profile reuse, unregistered Change | Registry, provenance union and profile checks reject |
| 19 | Partial mutation: construction followed by a failing Change in one transaction | Whole transaction rolls back; nothing published |
| 20 | Denied `establish_group`, `import_scene`, `set_group_transform` or `attach_analysis` | Atomic policy rejection |
| 21 | Request options, artifact IDs, non-document scope | Adapter rejects; no overrides exist |
| 22 | Non-null `representation_claim` or TemporalIdentity claim in receipt | Reject — this profile supplies no correspondence |
| 23 | Ordinary-video negative control (no admitted evidence at all) | No eligible claim → reject; no Entity/Group is created |

## 12. Golden requirements (positive and negative)

Positive Golden reuses the existing checked-in
`examples/043-authored-raster-production` source and video through the real
Spec76 pipeline, ending with one genuinely admitted SUPPORTED evidence claim at
the pinned identity
`artifact:45861f9b0ad1723fd3c3b624a7d820042a8e665f72d30cb5b4c80f1a4ba99ad4`
(Spec76 §19). At that base the Golden MUST:

1. propose through the new adapter and `validate()` without state change,
   then accept exactly one atomic Revision containing the complete §6 fragment,
   the §7 Group, the manifest and the receipt;
2. reproduce the §5 allocation exactly; expected values for the checked-in
   fixture (computed from the formulas during this design pass, to be
   re-verified by the implementation):

```text
part-a Entity    entity:eea3bdf4975a00e2452136ca655ea4c28335e88a4aa86057f479b00d8f06e3c4
part-a Operation op:e68ba2bd468131455ed18f3e85350b92663086653028f2abbc9482fc32d504fd
part-b Entity    entity:e41b0949fa5c081d7d634a7989ecd67c2b5139d2c0c6d112e5481863559cbfad
part-b Operation op:f53631a1d4d30a0f8366fa7e5c4a8243adfa24557e02cec03fd3da04c1cf95ce
Group            group:1f24284859439580faac31e69df1aa7bf6a1a28c450d8ddae2e3b42e48b656ac
sorted members   [entity:e41b0949fa5c081d7d634a7989ecd67c2b5139d2c0c6d112e5481863559cbfad,
                  entity:eea3bdf4975a00e2452136ca655ea4c28335e88a4aa86057f479b00d8f06e3c4]
initial origin   [116.0, 97.0]
```

3. append exactly two render entries, change no existing Entity/Operation/
   binding/style/group, and leave the admitted evidence reference and the
   complete recorded dependency closure untouched;
4. record the measured manifest/receipt/document/revision identities in this
   document's implementation record and pin them in
   `tests/test_video_artwork_construction.py`;
5. render deterministic SVG through the existing renderer (no backend) and pin
   its exact bytes; the output contains the two triangle paths with the §6
   styles inside the deterministic scene serialization;
6. prove preview isolation, one-Revision atomicity, same-allocation reproposal
   after an unrelated base edit terminating in the #17 collision rejection,
   and complete rollback on rejection;
7. create no TemporalIdentity, Track, Keyframe, MotionTargetBinding, S1
   binding, Camera state or animation content — the accepted Document differs
   from the base only by the §6 fragment, the §7 Group and the two new
   references.

Negative Golden: the implementation must cover every §11 row as an executable
test, and re-run the Spec73, Spec76 and Spec77 goldens byte-identically. The
checked-in reviewable example is `examples/044-video-artwork-construction/`
(`golden.json` with pinned identities plus the rendered `group.svg`);
`examples/043` remains unchanged.

## 13. Unresolved whole-subject TemporalIdentity dependency

Spec76 subject identity is **not** an R1 TemporalIdentity, and this profile
neither creates, promotes, substitutes nor merges any TemporalIdentity. The
established Group is a legal persistent representation, but no representation
correspondence is proven:

```text
observation subject  <->  persistent artwork representation   NOT SOLVED HERE
```

| Capability | Status |
| --- | --- |
| First video-backed artwork construction profile (this document) | IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN |
| Whole-subject TemporalIdentity | OPEN |
| Stable Representation Correspondence (spec/71) | DESIGN CONTRACT / NOT IMPLEMENTED |
| Construction-history/current-coverage consumption proof | NOT IMPLEMENTED |
| Versioned P2D consumer contract | NOT IMPLEMENTED |
| P2D-B | BLOCKED |
| Single-Entity Motion Target | OPEN SEPARATE ARCHITECTURAL QUESTION |
| Motion binding / Track creation | NOT AUTHORIZED by this profile |

The future correspondence contract must still define: the temporal origin and
baseline semantics for the association; authenticated construction history and
current coverage; the T-to-G association claim and its complete universe; and
atomic delegation to the frozen S1/binding boundary. Establishing this profile
does not discharge those gates, and this document makes no video-restoration,
stylization, deformation, occlusion or flicker claim.

## 14. Implementation boundary and Codex-ready acceptance criteria

The implementation touches exactly:

1. `svm/revisions.py`: add `EstablishVideoArtworkGroupChange` with fields
   `source_revision_id`, `base_document_snapshot`, `witnesses`,
   `profile_identity`, `evidence_reference`, `fragment`, `group`, `references`.
   No separate `base_revision` field: the base Revision witness is
   `witnesses[source_revision_id]`, authenticated by the §2 DAG check. `apply()`
   mirrors the spec/72 guard/collision/reference behavior.
2. `svm/adapters/video_artwork_construction.py`: constants, `_derive`,
   `verify_change` and the adapter (id `adapter:video-artwork-construction`),
   mirroring the spec/73 module structure; it reuses the Spec75 grammar
   implementation and the existing `canonical_path_bounds`, `_geometry_bounds`
   and evaluator semantics without a second interpretation.
3. `svm/change_authority.py`: register the new Change with the §10 intent set,
   the `_source_revision` resolver and a dedicated verifier wrapper.
4. `svm/document.py`: replace the single-literal construction
   `profile_identity` check with the closed-world admitted set
   `{"svm-svg-two-part-group-construction@0.1", "svm-video-two-part-group-construction@0.1"}`
   — exact enum, never a pattern or generic string.
5. `schema/svm-document-v0.1.schema.json`: the same closed enum extension.
6. `tests/test_video_artwork_construction.py` and
   `examples/044-video-artwork-construction/` (§12).

Unchanged and re-verified: `svm/proposals.py` (no ProposalAcceptor change is
required; the LayerD pinned authority hash stays valid), the spec/73 module,
the Spec76/77 modules, P2A/P2B, motion, POP and all frozen goldens.
`svm/__init__.py` needs no change (spec/73 convention: the Change lives in
`svm.revisions`).

Codex-ready acceptance criteria:

- A1: focused tests implement every §11 row and the §12 positive Golden with
  recorded identities; all new tests pass.
- A2: the full suite passes; Spec73, Spec76 and Spec77 golden bytes and all
  frozen expectations/tolerances are unchanged; the original E1C bypass
  regression still passes.
- A3: `ruff format --check`, `ruff check`, `pyright`, `git diff --check` clean.
- A4: this document is updated to **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN**
  with the implementation baseline and measured identities recorded.
- A5: no behavior outside §14's file list changes; no TemporalIdentity, Track,
  binding, Camera or P2D surface appears.

No structural blocker was found: the authority, witness, registry, validator,
schema and renderer surfaces required by this profile all exist, and the only
Core-adjacent edits are the two closed-set enum extensions in item 4–5.

## 15. Measured implementation record

The real Spec75 → Spec76 dedicated admission pipeline reproduces the existing
evidence Artifact ID in §12. The F0 producer and independent verifier share a
deterministic derivation, but the verifier receives only the Acceptor-resolved
`Change.references` and authenticated witnesses. It enumerates every base
Spec76 descriptor with an exact ancestral admission event before considering
eligibility. Legacy descriptors are excluded without resolving their bytes.

`source`, `video` and `manifest` record summaries are resolved by Artifact ID in
the record's authenticated historical base, checked against their recorded
hashes/media type, and compared as complete descriptors against the current
base. Every event-bearing evidence record and each exact-present dependency is
transported in canonical Artifact-ID order; manifest and receipt follow. The
Golden transports 16 descriptors and adds exactly the two new output references.
Omitting any required descriptor or supplying a selective subset rejects during
independent replay. No pixel closure is rerun and no admission event is created.

The actual Spec75 `_triangles` parser is used unchanged. Its grammar permits
one canonical spelling of each integer triangle path, so formatting its parsed
vertices recovers the exact source `d` lexemes without a second grammar.
Entity/Operation/Group allocation and origin match every design-time value in
§12; measured identities are pinned as literal expectations in the F0 tests:

| Record | Measured identity |
| --- | --- |
| Authenticated construction base | `revision:6ce22d3c175531fd5348de5a2e6e2577cdb67764c18861d873113b404e24bc53` |
| Construction manifest | `artifact:7d0b42099c1a717bb3b7c9c944f29d7e7fd8946d6ab4eb579e32e3228fb729f5` |
| Establishment receipt | `artifact:5fc6ec132b566fa20201cc74aeceaaf31c82a9fe2fb7802357c9761a24a9db3b` |
| Accepted Document | `sha256:cf9a67e616b4c0d7edbc706a7803af4d4d8a365d8cc2aaf9d439f727d5008ec3` |
| Acceptance Revision | `revision:e54b39d3b14a15047a29e1313d9d8b6bcaa8a798a7e2f5360e996d114fc320b3` |
| SVG bytes | `sha256:4552399140954d1d9e95d7fc0369dff37695efc02023862f503ba6b2bbb5efc4` |

The reviewable 950-byte SVG uses `SVGRenderOptions(width=256, height=256,
view_box=(0, 0, 256, 256))` to expose the authored source coordinates. Both
paths have black fill, no stroke and opacity 1, and retain source render order.
`examples/044-video-artwork-construction/golden.json` records these measured
identities; `group.svg` is compared byte-for-byte and against its literal hash.
No frozen source, video or prior Golden was changed. There is no deviation from
the authority semantics of sections 1–14. The unresolved gates in §13 remain open.

Verification: 29 focused F0 tests cover every §11 row; 104 Spec73/75/76/77,
ProposalAcceptor/ChangeAuthority and LayerD regressions pass; the full unittest
suite passes all 643 tests. Ruff lint, Ruff formatting, Pyright, compileall and
`git diff --check` pass. The unchanged ProposalAcceptor retains its reviewed
SHA-256 pin `0336d93e1151c49bc8f46a37960b01d323632ba4c17873904096336949985b97`.
