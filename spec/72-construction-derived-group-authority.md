# P2S-B — Construction-Derived Group Authority

Status: **SPECIFIED / NOT IMPLEMENTED**. Not FINAL or FROZEN.

Evidence baseline: `bf87499dc87e06f982696fabdf979e798fb46bbd`.
This is a new normative authority design, not a runtime extension. It authorizes
no change to frozen POP promotion, P2A/P2B/R0/P2C/R1, or S1 semantics. P2D-B
remains blocked. The single-Entity motion-target question remains separate.

## 1. Executable basis and bounded decision

The inspected boundaries are:

- `revisions.py`: `AppendSceneFragmentChange` can append artwork definitions;
  `PromotedGroup.group_id`, `PromoteGroupsChange` create inference-origin Groups.
- `change_authority.py`: `_verify_group_promotion` verifies frozen Q-v1 records;
  exact registered Change types, not Adapter classes, hold mutation authority.
- `pop_structure.py`: `_validate_exact_pop_scene` reconstructs genuine POP output;
  `pop_group_candidates.py` derives Q-v1 evidence from that restricted scene.
- `document.py`: `_validate_groups` requires at least two sorted unique existing
  members, inference-shaped provenance and unique transformed membership.
- SVG import, bitmap trace/reconciliation and LayerPeeler can create rendered
  fragments. POP import is source-specific. LayerD and Component Promotion do
  not supply rendered vector geometry. None provides this new Group authority.
- `scene.py` and `motion.py` use Group membership and transform, independently of
  inference scoring. Group origin is therefore separable from Group meaning.
- `artifacts.py` permits arbitrary media/provenance claims at import;
  `proposals.py` verifies artifacts through `(change, resolved_artifacts)`.

The first authority SHALL establish **one new complete artwork fragment and one
Group containing its entire renderable Entity set in one atomic construction**.
It SHALL NOT group pre-existing Entities or accept a caller-selected member set.
An admitted profile must establish that the fragment is one construction subject,
not simply wrap an arbitrary scene or conveniently chosen subset.

Compared with grouping existing artwork through historical receipts, this needs
no history traversal at creation: the verifier replays the complete construction
against the authenticated current base. It avoids selecting which old edits,
imports or Entities count as the assembly. Spec/71's historical proof is still
required for later representation-correspondence consumption after edits; it is
not needed to manufacture the original Group.

## 2. Retained Group semantics

The object remains `kind: explicit-group`: persistent structural assembly plus
optional static Transform ownership. This authority always supplies an initial
Transform, making the new Group structurally eligible for S1. It creates no S1
binding and makes no claim of available/unoccupied target ownership beyond the
checks below.

Members are simultaneous artwork parts, not observations at different times.
Cardinality remains >= 2. No dummy, invisible filler, temporal alternative,
artificial split or unrelated background may be added to meet cardinality.
Profile admission must justify genuine multipart construction; merely counting
two render entries does not establish that justification.

Spec/30's matrix composition, fixed origin, persistent member IDs and unique
transformed membership are unchanged. No ConstructionGroup type, Entity
Transform, new motion target type or 3D scene object is introduced.

## 3. Versioned provenance extension

The future Group validator/schema SHALL recognize an exact disjoint union:

**Legacy inference origin:** the existing exact object, unchanged:

```json
{"candidate_id":"candidate:group:…","inference_id":"inference:group:…","inference_artifact_id":"artifact:…"}
```

Absence of a discriminator is allowed only for this exact legacy shape. Do not
add a type field, rewrite its IDs or migrate its meaning. Spec/29 and its frozen
verifier remain solely responsible for this branch.

**Construction origin:** a new exact object:

```json
{
  "type": "construction-established-group@0.1",
  "authority_identity": "svm-construction-derived-group@0.1",
  "profile_identity": "<admitted immutable versioned profile identity>",
  "construction_artifact_id": "artifact:<full SHA-256>"
}
```

Mixed fields, unknown type/version, missing fields and extra fields fail closed.
The construction artifact reference must exist in the Document. No synthetic
candidate/inference IDs are permitted. Core stores only the origin discriminator,
authority/profile identity and evidence reference. Source observations, timing,
source object namespaces, geometry derivation and correspondence claims belong
in profile evidence, never in Core Group provenance.

This is an additive, version-discriminated provenance generalization requiring a
future validator/schema change. Current runtime rejects the new shape; this spec
does not claim otherwise. No new Operation registry version is implied. Legacy
documents, IDs and accepted POP behavior must remain byte/semantic compatible.
Any consumer enumerating legacy provenance fields must dispatch explicitly before
access; adding a construction Group must not break subsequent legacy promotion.

## 4. Structural validity is not admission

`validate_document` checks structure and reference presence; it does not replay
Group evidence. For example, `examples/022-group-transform.svm.json` contains
format-valid placeholder inference provenance for a hand-authored fixture.
Such fixtures demonstrate evaluation, not an accepted inference/construction run.

The new structural branch SHALL NOT convert this asymmetry into authority.
Loading valid Group JSON or appending a manifest reference is not accepted
construction. The new verifier must replay the claim even if its artifact was
previously attached. A media type, content hash, self-declared profile or producer
name alone is insufficient. The legacy validation/acceptance boundary is recorded,
not globally rewritten by this task.

## 5. Admitted construction semantics

Authority identity: `svm-construction-derived-group@0.1`.

Profile dispatch must be closed-world: only separately normatively admitted
deterministic profiles with a trusted replay implementation may execute. An
Artifact cannot register a profile, supply verifier code, or select a plugin by
URI. Unknown profiles reject. No concrete source-construction profile is admitted
by this authority specification; the first executable slice must include one
bounded admitted profile, not an arbitrary manifest interpreter.

Each profile must define:

- exact accepted source/root requirements and complete dependency discovery;
- the source construction subject and proof that all output parts belong to it;
- any complete TemporalIdentity/observation coverage needed for spec/71;
- baseline, coordinate system, finite canonical numeric and geometry rules;
- deterministic Entity/Operation allocation from trusted source subject inputs
  and logical part keys, without caller names, collision suffixes or base-style
  state as allocation entropy;
- the complete ordered fragment: Entities, Operations, output bindings, styles
  and Render Stack entries, and deterministic local geometry bounds;
- fixed style/presentation policy, bounded resource limits and abstention rules.

Replay inputs are the authenticated base plus exact already accepted dependency
descriptors and bytes. Full source discovery must precede output verification;
the proposed manifest's own list is not the authoritative universe. Relevant
upstream claims must satisfy their admitted verifier contract. Merely repeating
a producer's declared identity does not prove upstream semantics.

The entire reconstructed fragment must equal the proposed fragment. For this
initial mode, every created Entity must occur exactly once in its render entries,
have one usable geometry binding and a complete style, and be a genuine artwork
part. No non-rendered helper Entities or extra scene fragments are admitted.
Operations may provide intermediate geometry; they are not Group members.
Construction is self-contained: new geometry operations may reference new
operations and verified profile resources, not mutate/rebind old artwork.

The profile owns output order; Group membership is a set. Canonical members are
the sorted unique IDs of **all** reconstructed Entities, with no filtering by
score, name, visibility, caller choices or observed-frame identity. Duplicate
Entities/render entries are errors, not silently deduplicated repairs.

## 6. Construction manifest and evidence authority

The canonical construction manifest records exactly:

- `schema_version = svm-group-construction-manifest-0.1`;
- `authority_identity` and admitted `profile_identity`;
- `source_base_revision_id` and `source_base_document_hash`;
- the profile's canonical source-subject description and recorded parameters;
- its complete ordered accepted source reference descriptors;
- the reconstructed fragment from §5, including allocated IDs;
- the canonical per-member initial geometry bounds used by §8.

These fields bind inputs and reproduced results, not a supplied member choice.
The exact subject/parameters sub-schema belongs to the admitted profile and
rejects unknown options. Manifest bytes use repository `canonical_bytes`; all
numeric inputs/results must be finite and satisfy their existing Operation rules.
The verifier reconstructs the entire manifest, including base commitments, rather
than trusting any listed result. Proposed outputs cannot substitute for replay.

The **construction artifact ID** is the ordinary `artifact:` SHA-256 of these
manifest bytes. It is a DerivedArtifact with media type
`application/vnd.svm.group-construction-manifest+json;version=0.1` and exact
descriptor provenance `{authority_identity, profile_identity}` matching the
reproduced manifest. Both bytes and descriptor must verify. That media type
does not create authority.

The manifest contains no Group ID, Group provenance, receipt reference, resulting
Document hash or resulting Revision ID. It is newly derived proposal evidence,
normally accepted with the construction, not a pre-existing source dependency.
Pre-attaching identical evidence confers no privilege and cannot bypass replay;
conflicting descriptors for an existing artifact ID fail closed.

## 7. Canonical Group identity

Let `members` be the canonical full set derived under §5. Normatively:

```text
group_id = "group:" + SHA256(canonical_bytes({
    "authority_identity": "svm-construction-derived-group@0.1",
    "profile_identity": admitted_profile_identity,
    "members": sorted_member_ids
})).hexdigest()
```

Use full SHA-256, repository canonical encoding and lexicographic ID order.
The distinct input object/authority domain separates it from frozen
`PromotedGroup.group_id`; frozen inference IDs remain unchanged.

The ID includes authority, profile and member identities. It does **not** include
the construction artifact ID, source base commitment, display names, styles,
Transform values, receipt ID or resulting Revision ID. Source identity enters
through independently reproduced member allocation, not through caller ordering.
Profiles SHALL NOT hide unrelated base style or receipt/result hashes inside
Entity allocation. A legitimate change of construction subject may create new
member IDs; an unrelated base edit must not manufacture a new assembly identity.

This formula allocates identity at birth. Later allowed property edits do not
recalculate it. Membership replacement is not part of this authority. Duplicate
Group or Entity IDs in the base reject even if content matches; this is CREATE,
not idempotent append or implicit retargeting. Hash collision assumptions are the
repository's existing SHA-256 assumptions; no last-writer-wins behavior is allowed.

## 8. Initial static Transform

Replay each member's initial geometry in construction/Document coordinates,
before this Group and before Camera. Use the existing Operation geometry-bounds
conventions (`operations.py: _geometry_bounds`): path bounds must already pass
canonical path validation; member-local transforms compose by the existing
matrix convention. Bounds for transformed shapes are those convention's bounds,
not a newly claimed tight silhouette box. Profiles with unsupported bounds or
unrecorded backend-dependent results are ineligible.

Union these verified finite nonempty bounds to `[xmin, ymin, xmax, ymax]`.
Reject degenerate extents. The initial Transform is:

```text
translate = [0, 0]
rotation_degrees = 0
scale = 1
origin = [canonical((xmin + xmax)/2), canonical((ymin + ymax)/2)]
```

Here `canonical` uses the existing Group numeric convention: zero for absolute
values below `1e-12`, otherwise `.12g` formatting converted to a JSON number.
Overflow/non-finite intermediates reject. This is the center of the constructed
geometry bounds, independent of style stroke, unrelated scene contents and
Camera. It is stored once, not recomputed after edits or later observations.
Neutral motion does not relocate artwork. No observed displacement, rotation,
scale, Camera compensation or Track is encoded at establishment.

## 9. Hash dependency DAG

Arrows mean "is an input to". This ordering is normative:

```text
accepted source artifacts + admitted profile
    -> canonical source subject / logical part keys
    -> Entity IDs and Operation IDs
    -> complete fragment + verified initial geometry bounds

authenticated pre-Document / base Revision + accepted descriptors +
    profile + subject/parameters + complete fragment + bounds -> manifest bytes
manifest bytes -> construction artifact ID
construction artifact ID + authority + profile -> Group provenance
authority + profile + sorted Entity IDs -> Group ID
verified geometry bounds -> initial Transform
Group ID + members + Group provenance + initial Transform -> Group definition
construction artifact ID + Group definition + fragment +
    source base commitment + verified representation claim -> establishment receipt
receipt bytes -> receipt artifact ID
pre-Document + fragment + Group definition +
    construction/receipt references -> post Document
post Document -> document hash
document hash + parent Revision + recorded transaction metadata -> resulting Revision ID
```

Group provenance also contains authority/profile as in §3. Entity IDs do not
depend on manifest ID because that manifest contains them. Group ID has no
manifest/receipt dependency. The receipt may include the complete Group and
construction reference; neither Group nor manifest points to that receipt.
Receipt bytes exclude their own artifact ID and the post Document/Revision hash.
Only the post Document adds the receipt reference. Thus no edge returns from
receipt, post Document or resulting Revision to any earlier identity input.

The pre-Document/base commitment is an existing input, not the resulting state.
No fields may be added to a profile that introduce a reverse edge in this DAG.

## 10. Base authentication, replay and staleness

The future exact registered establishment Change must use the existing source
revision hook and the full-snapshot/Revision witness mechanism in spec/70 §10.1.
The reproduced witness must equal the actual Proposal base commitment. The
verifier receives no live Document or store. A full incoming-Document equality
guard before mutation prevents preceding Changes from replacing replay inputs.

Against that authenticated base, independently discover dependencies, require
exact accepted reference descriptors, replay the admitted profile, reproduce
manifest/fragment/bounds, derive members/ID/Transform/provenance, and compare
every claimed output. The verifier and proposing code must share this derivation
authority. No second correspondence algorithm is authorized.

Reject the entire establishment for:

- base Revision or full Document mismatch; no silent rebase;
- missing/unaccepted source evidence, wrong descriptors or unavailable bytes;
- manifest/profile mismatch or omitted/extra/reordered semantic output;
- missing, incompatible or extra expected fragment Entity/binding/style;
- any Entity, Operation or Group ID collision with the base;
- inconsistent Render Stack membership or occupied transformed ownership;
- invalid geometry/Transform or unsupported profile/claim.

Expected members are **new outputs**, not old Entities the caller may edit or
adopt. An allegedly new member already owned by a transformed Group is a
collision/conflict, not a reason to drop it. No adoption/replacement mode exists.

Whole-base optimistic acceptance makes a submitted proposal stale after any base
edit, including an unrelated style edit. Reproposing against the new base may
produce different manifest/receipt commitments, but identical source subject and
members yield the same Group ID. Unrelated style is not an ongoing ownership
condition or identity ingredient. Ordinary post-acceptance edits do not revoke
Group existence; spec/71 governs later proof applicability separately.

## 11. Atomic establishment and permissions

One accepted establishment must contain exactly the replayed new Entities,
Operations, bindings, styles, ordered Render Stack append, one Group with its
initial Transform, construction evidence and establishment receipt reference.
Existing artwork/order remain unchanged; no partial staging Revision is accepted.
Prior source analyses/correspondence may be separate accepted evidence stages.

Use one future composite registered Change, with a single replay verifier and
base guard; no caller-composed fragment-plus-unverified-Group sequence may obtain
this authority. Transaction copy/validation preserves all-or-nothing behavior.
Rejected preview/acceptance leaves HEAD, Revision count, Document, Group and
accepted references unchanged. Unaccepted blobs in an ArtifactStore are not
accepted state. No orphan target, receipt or partial Render Stack may remain.

Intent coverage must include the existing `import_scene`, `promote_group`,
`set_group_transform` and `attach_analysis` actions at their applicable scopes.
Reusing the Group-creation permission does not invoke or change POP inference
semantics. Denying any required action must deny the entire construction. No new
policy action or `policies.py` change is specified here; concrete intent coverage
must be tested when the composite is implemented.

## 12. Relationship to stable representation correspondence

Choose **one atomic establishment transaction**, with logically distinct proofs:

1. This authority proves the complete artwork fragment legally creates Group G.
2. For a spec/71 profile, the profile's separately admitted correspondence proof
   proves that this representation was established for TemporalIdentity T.

Neither proof implies the other. Generic source artwork can have a construction
Group without claiming TemporalIdentity ownership; such a Group is not a P2D
representation candidate merely because it exists. For video establishment both
proofs and the receipt must succeed together; failure of correspondence cannot
leave accepted orphan artwork under the guise of partial success.

The receipt binds the source base, complete accepted closure, profile, baseline
choice, source subject, complete fragment, construction artifact descriptor,
Group definition and initial Transform, and (when applicable) the verified T-to-G
claim and its coverage. It follows the non-self-referential ordering in §9.
Its profile-specific correspondence payload must be independently reproducible;
no universal self-attested mapping schema is introduced.

Spec/71's authenticated origin/history and current-coverage requirements remain
for later consumption. A structurally valid current Group or receipt with the
right media type does not prove that an old establishment was accepted. Choosing
atomic creation here removes historical adoption from the creation authority;
it does not erase the later provenance obligation.

## 13. P2D and single-Entity boundaries

Future P2D consumes the complete current TemporalIdentity universe, accepted
representation-correspondence proof, its exact closure, and a legal persistent
Group. Group-origin evidence is checked where that proof requires it. P2D does
not infer origins from field names, run Group construction, or require all
frame-local component Entities to be Group members. The existing P2D-A restricted
rule remains unchanged until a separately versioned consumer contract is enacted.

Frozen S1 can eventually bind the established Group through its existing endpoint
and conflict checks. Existing Group Tracks and evaluation remain unchanged.
Single Entity targets remain unsupported: Group cardinality is >= 2 and S1 is
Group-only. No one-member Group, dummy part, invisible filler, artificial split,
Entity Transform or generalized binding workaround is authorized.

## 14. Future multipart acceptance example

The normative future-positive template is a genuine two-part assembly, such as
an authored head-and-hair object with both parts contributing visible artwork.
Independent frame analyses X and Y produce differing observations OA and OB;
accepted R0/P2C/R1 establishes whole-object identity T. A separately admitted
construction profile must verify accepted **multipart source evidence** connecting
both simultaneous parts to that subject. P2C alone does not supply this fact.

Given that additional proof, the profile deterministically selects its recorded
baseline and constructs real Entity A and Entity B with geometry/bindings/style.
Their full fragment yields sorted members `[A, B]`, Group G under §7 and the
neutral transform with union-bounds origin under §8. The single transaction
accepts fragment, Group, receipt and verified T-to-G representation association.
Later P2D/S1 can bind T to G; observed motion Tracks then sample the same A and B
across time despite X != Y and changed observation geometry.

This is an acceptance requirement, not a claim that a current fixture/profile
supplies multipart evidence. A current P2B artifact with two unrelated primitives
does not satisfy it; two component TemporalIdentities cannot be silently merged.
If only the current single-contour P2A/P2B evidence exists, or multipart/subject
proof is missing, the example must abstain. No scene-wide grouping, contour split
or reused-analysis example may replace the required positive evidence.

The authority resolves the origin/provenance design blocker, not the missing
source profile. It unlocks a legal stable target for future stylization once
implemented and supplied with an admitted multipart profile. It proves no contour
stabilization, deformation, occlusion, style transfer, toon/cel rendering, flicker
repair or restoration. Those remain separate authorities.

## 15. Source neutrality and implementation gates

Future profiles may consume video/AI-video evidence, SVG animation, manual
structured authoring, AI structure extraction or animated-3D-derived evidence.
Each needs its own admitted reconstruction and subject proof. Source node IDs
are namespaced evidence, not implicit SVM IDs. Core Group provenance contains
no frame-specific fields, bones, meshes or quaternions. SVM remains a 2D artwork
construction model; later restoration retains independent source appearance.

The implementation must add only the new provenance branch and exact authority
support it requires, preserving legacy behavior. In particular, legacy promotion
must remain usable in a mixed-origin Document without indexing construction
provenance as Q-v1 provenance. No frozen POP scoring, candidate identity, promotion
ID, source-hash rule or reference interpretation may change.

Required statuses after this design:

| Capability | Status |
| --- | --- |
| Construction-Derived Group Authority | SPECIFIED / NOT IMPLEMENTED |
| Stable Artwork Construction Profile | BLOCKED ON AUTHORITY IMPLEMENTATION; no concrete profile admitted here |
| P2D-B | BLOCKED |
| Single-Entity Motion Target | OPEN SEPARATE ARCHITECTURAL QUESTION |

Authority implementation is necessary, not sufficient for video coverage: a
bounded multipart construction/correspondence profile must still be specified
and verified. No runtime or fixture is added in this task.

## 16. Adversarial design review / future acceptance obligations

| Case | Required result |
| --- | --- |
| Caller supplies members | Ignore as authority; reconstruct and require exact equality |
| Reordered membership | Same canonical ID; serialized members must still be canonical |
| Omitted or extra member | Full fragment/set equality rejects; no selectable subset |
| Fake media type or self-declared construction identity | No authority without admitted profile replay and exact accepted dependencies |
| Source exists only in resolver | Reject; exact accepted base reference required |
| Stale base / forged snapshot / preceding Change | Revision witness and incoming-base guard reject |
| Pre-existing Entity/Operation/target or Group ID collision | Reject, even if bytes match; no adoption or auto-suffix |
| Wrong manifest / modified geometry or style output | Replay rejects; proposed output is not an input authority |
| Transformed ownership conflict | Reject entire establishment; do not prune members |
| Receipt points back into Group/manifest hash inputs | Forbidden DAG; reject profile design |
| Synthetic inference fields on construction Group | Reject mixed provenance; never send to frozen POP verifier |
| One Entity or fabricated second member | Ineligible; no cardinality workaround |
| Legacy and construction Groups coexist | Both retain their origin-specific checks and shared transform rules |
| Representation association fails | Entire video establishment rejects atomically |

Design verdict: **GROUP_AUTHORITY_CONTRACT_READY**. Readiness is for this
normative authority contract, not runtime acceptance or P2D-B.
