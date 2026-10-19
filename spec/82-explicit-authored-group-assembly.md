# Explicit Authored Group Assembly Contract v0.1

Status: **IMPLEMENTATION IN PROGRESS / NOT FROZEN**.

Design baseline: `afb624fbdce02a8532b8478ef7b9e80f73f9ff4d`.
At that 2026-10-14 design baseline this document closed the bounded assembly
design and was not implementation authorization or executable conformance
evidence; that design record and the baseline findings below remain historical,
not a current-status claim.
Current implementation status (G1, G1.5, G2, G3, G4) is recorded in §15. The
normative contract in §§1–14 is unchanged and this document is **NOT FROZEN**.
P2D-A remains **BLOCKED / NOT READY / NOT FROZEN**. Frozen P2D-B0 v0.1, Spec80,
and all existing selection and admission authorities remain unchanged.

## 1. Decision and trust model

An explicitly requested, Policy-checked authoring transaction may assemble
existing Entities from its **real accepted Base Document** into one Group.
The author chooses the membership and, optionally, an initial static transform.
This asserts current structural intent, not an algorithm's discovery that the
members depict one physical object. Evidence MUST NOT automatically choose,
expand, rank, or substitute members.

Three guarantees are distinct:

| Guarantee | This contract |
| --- | --- |
| Current content legality | Validate the complete committed Base, exact Entity references, Group result, and complete resulting Document. |
| Current external-reference verifiability | Existing accepted descriptors are committed as Base content. Assembly does not resolve their bytes or attest their semantic contents; a consumer requiring that guarantee must independently verify them. |
| Historical dedicated acceptance | Does not prove that a particular Promotion/Construction Verifier ran in an ancestor. No such claim follows from a Group's existence or provenance object. |

The trusted starting point is the application's accepted RevisionStore Base,
not an arbitrary caller Document. Root/import trust is an existing application
boundary; this contract does not turn an untrusted imported snapshot into a
verified history. Exact Change registration and current deny-policy evaluation
grant the new operation's authority. Adapter IDs are existing policy actor
labels, not cryptographic proof of a person's identity or of a physical click.

## 2. Existing capability and missing authority

The following are findings at the design baseline, not new implementations:

| Boundary | Existing capability | Why it does not authorize this operation |
| --- | --- | --- |
| `document.py::_validate_groups` and `groupDefinition` schema | Explicit Groups, >=2 sorted unique existing Entity members; optional transform; disjoint transformed ownership | Provenance accepts only legacy inference or admitted construction origins, not author assembly. |
| `PromoteGroupsChange`, `_verify_group_promotion` | Frozen Q candidate promotion from a genuine accepted POP scene | Does not authorize an author's arbitrary selection of existing Regions. |
| `EstablishSVGGroupChange`, `EstablishVideoArtworkGroupChange` | Source-specific construction, complete newly created fragment and Group | Their source authority cannot be borrowed to adopt existing Entities. |
| `SetGroupTransformChange`, Group transform Tracks | Edit an existing legitimate Group under existing transform authority | Do not create a Group or authorize membership. |
| `ChangeAuthority`, ProposalAcceptor | Exact closed-world types, source-Base hook, independent verifier, policy intents, atomic validation | Can host a new registered authority without a new generic trust hook. |
| RevisionStore | Content-addressed full snapshots and Revision metadata; reserved admissions for existing families | Does not retain a universal execution trace of historical Changes/verifiers. |

There is no registered general-purpose member/hierarchy assembly Change at this
baseline. A hand-written Group is not evidence that ProposalAcceptor accepted
it. The earlier legal-input probe produced two exact identity-to-component
paths but no Group; the unchanged Consumer returned `NO_ELIGIBLE_GROUP` and
`ZERO_SUPPORTED`. The handwritten Consumer fixture additionally lacked Group
provenance and a real second member; it was not a complete accepted Document.

This contract deliberately introduces a **separate authoring authority**.
Spec72's prohibition on adopting old Entities continues to constrain its
construction authority; it is not reinterpreted as permission for this one.

## 3. Closed identity and member domain

The following names are reserved by this design, not presently registered:

| Item | Exact identity |
| --- | --- |
| Change class | `svm.revisions.AssembleAuthoredGroupChange` |
| Versioned Change identity | `svm.revisions.AssembleAuthoredGroupChange@0.1` |
| Authority identity | `svm-explicit-authored-group-assembly@0.1` |
| Provenance discriminator | `authored-group-assembly@0.1` |
| Producer | `AuthoredGroupAssemblyAdapter` |
| Producer ID / version | `adapter:authored-group-assembly` / `0.1` |

Members MAY be any distinct, currently legal Entity records in the exact Base,
including non-rendered `PromotedComponent` Regions. They need not share an
analysis Artifact, origin kind, or inferred subject. No shared-subject assertion
is made. Component IDs, origin fields and references remain exactly those of
the accepted records; caller-supplied replacements are not inputs.

Membership requires at least two real Entity IDs, sorted lexicographically,
unique, and present in that Base. A Group ID is not an Entity ID. Nested Groups,
Group parent fields, hierarchy edits and cycles are not supported. Existing
Entity parent relations remain unchanged and must already validate.

No Entity may be created, copied, split, renamed, imported, or promoted by this
Change. A preceding Change in the same Transaction cannot manufacture its
members. No dummy member, synthetic ID, duplicated component identity, inferred
companion or temporal alternative may be automatically added to meet cardinality.
An explicit author may group different real records; that choice is not a
certification that those records are independent observations or one object.

## 4. Canonical representation, Group identity and provenance

`C(x)` means the existing `svm.evaluator.canonical_bytes(x)`: JSON with sorted
object keys, separators `(',', ':')`, `ensure_ascii=False`, encoded as UTF-8.
Only native JSON values are admitted here, with string object keys and finite
numbers; booleans are not numbers. No custom encoders, dataclass field discovery,
NaN/Infinity, Unicode normalization, rounding, or platform path normalization
is part of this contract. Array order is significant. Hashes are full lowercase
SHA-256 hex digests, never truncated.

For canonical member array `M`, define:

```text
membership_seed = {
  "authority_identity": "svm-explicit-authored-group-assembly@0.1",
  "members": M
}
d = SHA256(C(membership_seed)).hexdigest()
group_id = "group:" + d
membership_hash = "sha256:" + d
```

The complete new Group has exactly these fields; `transform` is omitted when
the requested initial transform is null:

```text
{
  "id": group_id,
  "kind": "explicit-group",
  "members": M,
  "provenance": {
    "type": "authored-group-assembly@0.1",
    "authority_identity": "svm-explicit-authored-group-assembly@0.1",
    "source_revision_id": <actual accepted Base Revision ID>,
    "source_document_hash": <that Revision's complete Document hash>,
    "membership_hash": "sha256:" + d
  },
  "transform": <explicit initial transform, only if non-null>
}
```

Both fixed provenance strings are exact constants; the other fields are strings
matching `revision:[0-9a-f]{64}` and `sha256:[0-9a-f]{64}` respectively. Unknown,
missing, null, mixed-origin or extra fields fail closed. There is no inference
candidate, construction profile, source Evidence reference, actor attestation,
certification receipt or observation correspondence in this object.

The source Revision commits the *complete* member records and their current
provenance, not just the member ID array. The membership hash binds that array
to the authored authority. The Group ID deliberately excludes Base, transform
and presentation metadata: the same member set under this authority always
has the same ID. Existing ID collision is an error, including an identical
existing Group; it is not a silent no-op. Another Base may generate different
birth provenance but cannot create a second same-ID Group in a Document.

Birth provenance remains unchanged through later authorized transform edits.
It is not refreshed into a claim about the latest Base. Membership editing is
not part of v0.1. A portable reader can recompute the ID/membership hash and
check provenance syntax; without history it cannot authenticate the stated
birth Revision or prove that this Change executed. Provenance is not a signature.

### 4.1 Initial transform

The request has a required `transform` key with either null or an exact object:

```text
{"translate": [x, y], "rotation_degrees": r, "scale": s, "origin": [ox, oy]}
```

All six scalar coordinates/parameters are finite JSON numbers, excluding bool;
`scale > 0`. Arrays have length two; no extra keys or defaults are admitted.
Numbers must also be representable as finite floats under the existing Group
validator. Integer/float representation is preserved in canonical bytes; no
numeric equivalence beyond recorded representation is promised for Proposal IDs.
Null means no transform field, not an implicit identity transform. Explicit
neutral transform is `{translate:[0,0],rotation_degrees:0,scale:1,origin:[0,0]}`.
No bounds-based pivot, pixel-to-artwork mapping or geometry inference is allowed.

Composition, origin and animation semantics remain those of Specs30/31. The
same Entity cannot belong to two transformed Groups, regardless of origin or
whether either transform is numerically neutral. Untransformed Group overlap
remains permitted by the existing rules.

## 5. Versioned Schema and reader compatibility

The current frozen baseline schema and validators reject the new provenance.
This design does not make such a Document valid in the current executable.
A separately authorized implementation SHALL introduce an additive schema
dialect, with the exact new artifact identity:

```text
schema/svm-document-v0.1-authored-group-assembly-v0.1.schema.json
https://structured-vector-motion.dev/schema/svm-document-v0.1-authored-group-assembly-v0.1.schema.json
```

This is a prospective path/`$id`, not a file supplied by this docs-only change.
It SHALL retain the baseline schema's requirements, including both existing
provenance branches, and add precisely the closed authored branch in §4.
It MUST NOT edit or weaken `svm-document-v0.1.schema.json`. Because that schema
closes its provenance union, simply combining it with `allOf` is insufficient:
the extension must preserve its definitions while explicitly extending that
union. Schema equivalence tests must protect every existing definition.

The new reader's semantic validator dispatches on the exact discriminator and
recomputes the authored ID/membership hash. All old Group validation remains
unchanged. Schema alone does not validate cross-record hashes, membership
existence or birth acceptance; these require semantic/acceptance checks.
The Document retains `schema_version: "0.1"` and
`semantics_version: "svm-core-0.1"`: no Operation or transform semantics change.
The extension's version is its schema `$id` and provenance discriminator, not
a fabricated new Core semantics version or an extra root Document field.

New readers accept old documents unchanged. Old readers fail closed on authored
provenance; this is **not** forward compatibility. Export/import tooling must
select the extension dialect when this discriminator occurs, reject an export
explicitly requested for the baseline dialect, and never strip, reinterpret,
or silently downgrade a Group. A validator without extension support must
report unsupported provenance rather than ignore the Group.

No migration of existing snapshots or rewriting of their Revision IDs occurs.
Replaying a new assembly requires an extension-capable reader; replay of old
documents retains the old meaning. Actual schema/validator changes, reader
dispatch and compatibility tests are future implementation work, not changes
authorized by this document's current docs-only task.

### 5.1 Verified transaction and trusted-history dialect integration (G1.5)

Reader capability is not Change authority. `RevisionStore.document_dialect` is
trusted host configuration, not a Proposal field or part of Document/Revision
meaning. Normal acceptance SHALL pass that selected dialect to the final
`apply_verified_transaction` validation. Its new keyword-only `dialect` argument
defaults to `DocumentDialect.BASELINE`; existing call sites retain baseline
behavior. No candidate discriminator, Generator parameter or Change attribute
may automatically upgrade the store. All exact Change, Artifact, source-Base,
Policy and admission checks keep their existing order and semantics.

An existing baseline store needs an explicit host capability upgrade before a
future authorized Change can add the first authored Group. The bounded host
method `RevisionStore.upgrade_document_dialect(dialect)` accepts only the known
`DocumentDialect` enum and permits BASELINE -> AUTHORED_GROUP_ASSEMBLY or the
already-selected dialect. Downgrades and unknown values fail closed. It validates
all stored snapshots under the requested reader before changing configuration;
failure leaves the store unchanged. It changes no Document, head, Revision ID,
Document hash, admission or permission, and grants no Group creation operation.
Adapters must not receive a mutable store or invoke this trusted host operation.

`svm-trusted-history@0.1` remains exactly `history_contract`, `head`, `records`.
There is no new dialect field, history format version or commitment formula.
Restoration first checks the externally retained trusted history digest and
each complete Revision commitment. It then selects the known dialect required
by each authenticated Document and validates it. The restored store requires
the extension if **any** valid stored snapshot requires it, including a non-HEAD
branch or a snapshot after the checked-out Revision. Otherwise it is baseline.
This is a closed two-dialect join, not a generic latest-version fallback. Unknown
provenance versions still fail; all parent/admission checks remain required
before returning the store. Injected dialect metadata is not trusted input and
does not extend the closed history format.

An extension opt-in over exclusively baseline content is deliberately not
recoverable from this unchanged payload: both configurations have identical
historical content. The host must explicitly opt in again after restoration
if that capability is desired. Do not claim that history round-trip preserves
unrecorded host preferences. No implicit downgrade of actual authored content
is allowed, and no old hash or Revision ID is rewritten.

G1.5 may test existing registered edits on trusted structural authored fixtures;
this demonstrates final validation/rollback, not historical Group creation.
It must register no Group assembly Change. Existing source-specific Group
verifiers continue to reject authored provenance as a substitute for their
own origin. The dedicated assembly authority remains a separate G2 gate.

## 6. Exact Change and Producer contract

The exact new Change type, not subclasses or duck-typed replacements, has these
closed fields. No extra mutable execution attributes or caller hooks are allowed:

| Field | Type and constraint |
| --- | --- |
| `source_revision_id` | Actual Proposal Base `revision:<64hex>`. |
| `authority_identity` | Exact §3 authority string. |
| `base_document_snapshot` | Deep-copied complete JSON Document, not a projection. |
| `base_revision` | Exact `Revision` or `AdmittedRevision`, as specified in §7. |
| `member_ids` | Tuple of >=2 sorted unique native strings, all Entity IDs in Base. Maps to JSON array `M`. |
| `initial_transform` | Null or native JSON object from §4.1. |
| `group` | Native JSON object equal byte-for-byte under `C` to the independently derived §4 Group. Not caller authority. |

`references` is a read-only derived empty tuple, not a configurable field.
The Change does not delegate to any Promotion/Construction Change. Its only
mutation is appending this one derived Group to the Base's `groups` array,
creating the array if absent. Existing array order is preserved. All other
Document content is byte-identical under `C`.

The Producer accepts a genuine Base request and its complete Revision metadata,
as the existing construction adapters do; it does not manufacture that metadata
from just the Document. Request scope is empty or `("document",)`; Artifact IDs
are empty. Options have exactly `members` and `transform`. `members` is a JSON
array of distinct existing Entity IDs; the Producer may sort it but must reject
duplicates, not silently deduplicate. The accepted Change's members and Group
members must already be sorted; the Verifier rejects wrong order. There is no
request option for Group ID, provenance, source Evidence, Identity, Binding,
confidence, namespace, target override or automatic member selection.

The Producer emits one Change in one Transaction, zero source references,
zero required Artifact IDs, and zero Evidence/preview Artifacts. No Artifact
kind, media type, locator or content-addressed Evidence identity is introduced.
It does not read source image/analysis bytes or mint an admission receipt.
If a UI shows a Group preview, it must label it authored, not reuse an inference
or construction certification label. Preview/report objects hold no authority.

For deterministic Producer identity, let:

```text
proposal_seed = {
  "change_identity": "svm.revisions.AssembleAuthoredGroupChange@0.1",
  "source_revision_id": source_revision_id,
  "group": derived_group
}
p = SHA256(C(proposal_seed)).hexdigest()
proposal_id = "proposal:authored-group-assembly:" + p
transaction_id = "transaction:authored-group-assembly:" + p
transaction_message = "Assemble explicitly authored Group"
```

Producer version and parameters record §3, canonical members and the explicit
nullable transform. No randomness, timestamps or machine paths participate.
These IDs are deterministic labels, not substitutes for independent validation.

## 7. Single-Base witness and acceptance-time verification

**Decision: one complete Base witness, no ancestor DAG.** No permission or
membership fact required by this authority resides only in ancestor history.
The current accepted Base is the explicitly chosen trust boundary.

An ordinary Revision witness has exactly `revision_id`, `parent_ids`,
`transaction_id`, `document_hash`, `message`. Parent IDs are an ordered tuple;
transaction ID is string or null; message is string. An `AdmittedRevision`
additionally carries its full ordered `admissions` tuple. Every event retains
exactly `contract`, `change_identity`, `authority_identity`, `base_revision_id`,
`artifact_reference`, `transition_hash`, including the complete reference object.
The existing Revision commitment algorithm, including its conditional
`svm-revision-admission@0.1` payload, is authoritative. Do not omit admissions,
sort parents/events, project descriptors or invent a different hash formula.
An empty-admissions witness uses ordinary `Revision`, as `_make_revision` does.

The independent Verifier must reconstruct the witness with the existing
`RevisionStore._make_revision` commitment from the full snapshot and exact
metadata, require the exact resulting witness and source ID, and validate the
Base Document. Admissions are commitment data here, not interpreted as Group,
promotion or correspondence authority. Parent snapshots are not fetched.

The existing `source_revision_resolver` returns `source_revision_id` and pins it
to the real Proposal Base in ProposalAcceptor. Alone it does not prove members,
snapshot completeness or historical verifier execution. Commitment validation
plus that pin authenticates the whole Base (under the existing hash assumption).

The future exact ChangeAuthority entry must register this independent verifier,
even though `references=()`. Existing ProposalAcceptor invokes it with an empty
resolved map for the Producer's Proposal. If another authorized Change supplies
Artifacts in a composed Transaction, the map can contain those entries; this
Verifier ignores them and grants no authority from them.

Acceptance retains the existing Acceptor order and interfaces:

1. Confirm real Base existence, normal head/stale checks, trusted exact Change
   types, and the Proposal's declared Artifact/reference relationship.
2. Pin the source Revision. Validate closed field types, authority identity,
   full Base commitment and Base legality independently of Producer assertions.
3. Recompute the entire member set, Group ID, provenance and transform. Compare
   the complete supplied Group to that result. Reject unknown members, ID
   collision, invalid transform and transformed ownership overlap. Validate
   the independently constructed full result Document.
4. Evaluate all exact current policy intents against the real Base.
5. On application, require `C(incoming_document) == C(authenticated_base)`;
   append only the independently checked Group to an isolated candidate.
   Validate the final complete Transaction result before publication.
6. Publish through ProposalAcceptor's existing verified transaction path, one
   new Revision; never use `RevisionStore.commit()` as an Adapter acceptance API.

Malformed witness/change errors are verifier failures (existing
`ProposalArtifactError` wrapping); stale and policy errors retain the existing
Acceptor categories. Final Document/application failures retain their existing
categories. No new public stable Reason code taxonomy is introduced.

Normal `accept` must reject stale head. Existing explicitly authorized anchored
branch acceptance is not revoked; it must still use its actual declared Base
and all existing anchoring checks. A stale request must never be silently
rebased or have its members refreshed from a newer head.

The snapshot guard rejects a preceding state-changing sibling, including one
that creates members. The existing verifier interface cannot inspect siblings;
this contract does **not** promise rejection of every no-op predecessor or every
separately authorized successor. Later Changes retain their own authority and
the entire Transaction remains atomic. In particular, assembly itself never
delegates a Binding; a separate explicit S1 Change is separate authorization.
Any failed sibling/final validation leaves head, revisions and stored documents
unchanged. Standalone Producer output remains one Change only.

## 8. Policy and authority isolation

Reuse of `establish_group` is sufficient: it already describes Group creation
at document scope. Exact registration, independent provenance and the new
Verifier provide the required authority separation; a new Policy Action would
not add a missing effect boundary. The declared action set is exactly
`{establish_group, set_group_transform}`, with these actual intents:

| Condition | Intent tuple `(action, target, parameter)` |
| --- | --- |
| Always | `("establish_group", "document", None)` |
| Initial transform is non-null | `("set_group_transform", derived_group_id, "transform")` |

Document/wildcard `establish_group` denial must reject assembly. Applicable
transform denial, including wildcard target denial, must reject initial
transform creation. A new Group cannot already be a valid Group-specific
permission target in the Base; existing target-validation rules are unchanged.

No `import_scene`, `promote_group`, `attach_analysis`, `bind_motion_target`, Track
authoring or Entity-edit intent is granted. Denying an unrelated import or
promotion action is not a denial of this separately authorized capability;
applications wishing to forbid assembly must deny `establish_group`.
Action reuse does not call Spec72's construction verifier or reuse its source
rights. Mixed provenance, legacy candidate claims and construction/certification
identities are rejected, not translated into authored provenance.

## 9. Document, render, motion and history invariants

Entities, their provenance/hierarchy, construction Operations/output bindings,
Styles, Render Stack, Structural Relations, TemporalIdentities, Motion Target
Bindings, Tracks and Keyframes remain exactly unchanged by this Change.
The existing complete canonical Structural Relations graph still validates;
no new relation is inferred merely from Group membership.

A new Group ID cannot be a valid pre-existing Binding/Group Track target.
Transformed overlap rejection also protects bound/animated Groups, which
already require transform ownership. Untransformed overlap does not take that
ownership. Ordinary member Operation/Style Tracks are not prohibited by a
borrowed B0 `TRACKED_REPRESENTATION` rule; their existing composition semantics
remain valid, with exact records preserved.

No-transform assembly preserves render semantics. An explicit transform may
legitimately change the rendered artwork according to Spec30. Even neutral
transform can introduce an SVG wrapper, so byte-identical SVG is not promised
generally. Non-rendered promoted Regions stay non-rendered; grouping does not
manufacture geometry or Render Stack entries. Old snapshots remain evaluable,
identity survives later transform edits, and equivalent full inputs replay to
the same Group, Proposal, result Document and Revision.

No authored AdmissionEvent is added. RevisionStore's existing limited admission
mechanism is not expanded into a universal history log. A future consumer that
needs proof of historical execution must design separately versioned persistent
Admission Evidence and independent replay rules. Neither this provenance nor
an optional future audit report can retroactively certify execution.

## 10. P2D-A and B0 compatibility decision

**A — Candidate entry: yes, for a transformed authored Group.** At the baseline,
`motion_target_binding_selection.py::_Context` builds eligibility from
`kind`, ID, members and transform, without provenance-origin dispatch. Exact
component tuple resolution then maps a verified observation path to an Entity
and that Entity's unique eligible Group. With every other condition satisfied,
an authored Group can cause the unchanged pure Consumer to return `SUPPORTED`.
An untransformed Group does not enter that eligible set.

**B — Meaning:** this changes the Document's structural input, not the algorithm.
Exact Identity-to-Entity provenance plus *authored* Entity-to-Group membership
does not prove independent observation-to-whole-Group subject correspondence.
It says nothing about the other member(s) belonging to the same observed object.
Do not advertise that result as independent source certification.

**C — Automatic acceptance requires a separate author-mediated selection Gate.**
The current P2D-A module is pure derivation; its spec70 Composite/Producer
acceptance path is not implemented. Before automatic consumption of authored
Groups can be authorized, a separate versioned profile must explicitly define
the authority of authored membership, its Evidence, independent Verifier and
ALL-SUPPORTED multi-Pair atomic binding. This document grants none of them and
does not modify spec70 or reinterpret its future independent-source guarantees.
Do not add an origin filter, alter `ALREADY_BOUND` priority, relax exact paths,
or change `GROUP_CONTENTION` / `ZERO_SUPPORTED` to force a desired outcome.

**D — Bypass prevention:** the assembly request has no Identity/Binding inputs,
its exact mutation/intents cannot bind, and a pure `SUPPORTED` result cannot
cross ProposalAcceptor without a separately registered selection authority.
Future automatic binding MUST NOT launder author-chosen membership as an
independent source proof. Existing explicit S1 binding remains available under
its own explicit pair request and frozen validation/policy; it is not P2D-A
automatic acceptance and is not revoked by this contract.

B0/Spec80 retain their independent construction profiles, full applicable
universe checks, birth replay and admission requirements. Authored provenance
cannot substitute for any of them. Additional Groups can affect applicability
or ownership conflicts in that universe; identical B0 results for every changed
Document are not promised. No B0 code, identity constant, witness, policy or
admission rule is modified. Rendered SVG still cannot prove an unsupported
rendered-origin path merely because its Entities are now grouped.

## 11. Legal Golden construction plan

All Group-success expectations below are **future implementation gates**, not
passed tests at this baseline. No expected Golden values may be regenerated to
hide a mismatch. Store actual accepted snapshots, proposals and outputs from
the implemented authority when establishing a new, separately reviewed Golden.

### 11.1 Real input prerequisites

On 2026-10-14, an external temporary probe started from the actual empty-canvas
example, accepted OpenCV analysis and Component Promotion for each of
`006-opencv-analysis-source.png` and `007-contained-components-source.png`.
Four genuine `ProposalAcceptor.accept` calls produced four unique
PromotedComponent Entities, zero Groups and five Revisions including the root.
Every resulting Document validated; no Group or Entity was manually inserted.

```text
A = [entity:authored-a-33d12c53ad28cb57,
     entity:authored-a-4709eee470dd4306]
B = [entity:authored-b-6ad352df26aeeed9,
     entity:authored-b-b443b45ad94a8c37]
final Revision = revision:8ae72054b4c177d8e53c7f8b53e54069037d7c35c3d27e33a7989c3fd358c838
Document hash = sha256:31b604f369671c047df795922a7ca7fe68b60c4ebe5af53019e3ff93e000ed74
```

This proves Entity input availability only, not assembly acceptance. These are
explicitly authored test memberships, not claimed inferred physical objects.

### 11.2 Single and dual Group sequences

For the assembly-only Golden, use two distinct accepted records in `A` for one
Group, then two in `B` for a second. Build each Proposal against its actual head
and accept it through ProposalAcceptor. The second Group uses the first Group's
result Revision as Base; two same-Base proposals must not both pass normal
head acceptance. All four members are disjoint and have genuine promotion
origins. Assert zero Identity/Binding/Track additions and unchanged Entity bytes.

For a later identity-aware Golden, rebuild the earlier genuine ten-accept
sequence: for each of `035-controlled-raster-recovery/base.png` and
`translation.png`, accept analysis, component promotion, raster occurrences,
R0 and R1. Call their two exact endpoint Entities `P_a`, `P_b`, and their
Identities `T_a`, `T_b`. Accept another real two-component analysis/promotion
for companions `C_a`, `C_b`; assert all four IDs differ. Explicitly request
`G_a={P_a,C_a}` and `G_b={P_b,C_b}`, each with a valid transform.
Companions are real author-selected records, not padding inserted by the
Producer, not new TemporalIdentity endpoints, and not source-certified parts
of either observed subject.

After both real assembly accepts, run the unchanged pure Consumer and verify
all exact paths and both expected `SUPPORTED` pairs; do not call that a new
source-authentication proof. This diagnostic is a future integration gate.
Atomic binding of both Pairs belongs only to the separate author-mediated
selection Gate: both Bindings and its Evidence must eventually be one accepted
transaction, with complete rollback on a failed Pair. Assembly acceptance alone
must leave zero new Bindings and is not enough to pass that later Gate.

## 12. Minimal executable acceptance matrix (planned, not PASS)

Each negative case asserts the actual error boundary plus unchanged head,
Revision set and stored Base/descendant snapshots. Merely inspecting test source
or filling this table does not satisfy a Gate.

| ID | Case | Required assertion / boundary |
| --- | --- | --- |
| P01 | Single authored Group of two real accepted Entities | Real accept, exact members/provenance/ID, one Revision, no Entity or motion mutation. |
| P02 | Two disjoint Groups / four accepted Entities | Two real current-Base accepts; second full witness includes first Group; exact independent membership. |
| P03 | Null and explicit neutral/non-neutral transforms | Omission vs explicit field preserved; correct intents; existing render composition, no geometry creation. |
| P04 | Ordinary and admitted Base | Complete witness commitment including admissions; no authored admission minted. |
| P05 | Replay and later transform edit | Same full inputs yield same Proposal/Document/Revision; transform edit preserves ID and birth provenance. |
| P06 | Existing Binding, Group Track, member Style/Operation Track, Structural Relations | Existing records unchanged; legal disjoint ownership and canonical relations; no borrowed B0 track ban. |
| P07 | Old inference/construction documents plus mixed authored origin | Old validation unchanged; new reader supports exact union; old reader rejects new branch. |
| P08 | Identity-aware accepted inputs and two assembled Groups | Independent pure Consumer yields both expected pairs; assembly itself creates no Binding. |
| P09 | Same members at another Base | Same derived Group ID; existing-ID collision rejected, no duplicate Group/no silent no-op. |
| N01 | Nonexistent or caller-only member; Group ID supplied as member | Producer/Verifier reject against authenticated Base, not a caller record map. |
| N02 | Member created by preceding Change | Full incoming-Base guard rejects; no partial Entity/Group commit. |
| N03 | One member, duplicate, malformed ID, unsorted serialized Change/Group | Reject; Producer sorting of distinct request members is allowed, silent deduplication is not. |
| N04 | Forged Group ID or collision | Independently recomputed identity and existing-ID checks reject. |
| N05 | NaN/Infinity/bool, non-positive scale, wrong array lengths, extra transform keys | Reject before publication; no default/rounding repair. |
| N06 | Missing/extra/unknown provenance; wrong membership/source hash or version | Exact schema/Verifier reject; no origin coercion. |
| N07 | Fake inference/construction/Spec80 Evidence identity or injected required Artifact | No borrowed authority; closed fields and exact reference/required-ID check reject standalone proposal. |
| N08 | Valid member from another Base, incomplete snapshot, altered witness message/parents/admissions | Actual Base pin plus full commitment rejects; no selected-subset witness. |
| N09 | Existing transformed ownership conflict, including bound/animated/neutral Groups | Reject new transformed overlap; no transform transfer or rebinding. |
| N10 | Group hierarchy/parent fields, nested Group or cycle attempt | Closed fields/member domain reject; existing Entity hierarchy unchanged. |
| N11 | Stale head | Normal accept rejects without refreshing/rebasing request; authorized anchored branch remains a distinct existing path. |
| N12 | Establish denial; initial-transform denial | Each applicable policy independently rejects; unrelated import denial is not an assembly veto. |
| N13 | Invalid full Base/result, changed unrelated records, malformed Structural Relations | Independent full validation or exact result/snapshot comparison rejects. |
| N14 | Failure after assembly in a composed Transaction | Final validation/sibling failure rolls back entire candidate; no partial Group/Revision publication. |
| N15 | Subclass/unregistered Change or overridden behavior | Exact closed-world registration and closed-field validation reject. |
| N16 | Author chooses members to induce a pure SUPPORTED result | Assembly still has no Binding intent/effect; unregistered automatic selection rejected; independent existing explicit S1 remains separately governed. |
| N17 | Missing resolver for a later provenance-consuming operation | Assembly's zero-Artifact behavior must not be reported as validation of unavailable source bytes. |
| N18 | Authored Group offered as B0 certified representation | Frozen Spec80/B0 checks still require their own birth/admission/applicability; no implicit Profile merge. |

For `GROUP_CONTENTION` and ambiguous-path diagnostics, do not violate the Core
rule forbidding overlapping transformed membership merely to manufacture a
fixture. Use legal accepted paths to distinct component Entities within one
authored Group for contention. Multiple paths of one Identity resolving to
different Groups require genuine accepted provenance and must follow unchanged
P2D-A classification; if such input is unavailable, report that limitation,
not a fabricated accepted history.

## 13. Design closure, implementation scope and remaining gates

The standalone design is closed: explicit author intent is the chosen authority;
single full Base commitment is sufficient; members/transform/identity/provenance
and policy effects are fixed; the versioned additive reader path is defined.
No historical execution guarantee is assumed or missing from this authority.

A subsequent task **may be separately authorized** to implement only this
Change, its exact registry entry/source hook/verifier, deterministic Producer,
extension schema/reader support and the §12 tests/new Golden. It must not add
generic ProposalAcceptor trust, historical admission, Group hierarchy editing,
automatic membership inference or motion selection. Local quality checks, full
tests, real acceptance replay and CI must then establish implementation status.
This document grants no permission to start that work in the current task.

The current docs-only review ran 41 existing focused tests across
`test_motion_target_binding_selection`, `test_component_promotion_adapter`,
`test_group_transform`, and `test_group_transform_motion`: **OK**. These are
baseline regressions/behavior checks, not §12 implementation conformance.
No new Group Change, schema, test or Golden was executed or changed. Full
unittest/Ruff/Pyright/CI are not asserted as rerun by this design task.

Remaining separate decisions are intentionally outside this closed authority:
author-mediated P2D-A automatic selection and Evidence, any historical Admission
Evidence, future membership editing, multi-Group atomic creation, numeric
performance budgets and optional audit UI. In particular, two-Pair automatic
binding is not authorized by a successful assembly Golden. P2D-A stays
**BLOCKED / NOT READY / NOT FROZEN**; no B0 freeze scope is expanded.

**Status note (2026-10-19).** Everything in this section is the 2026-10-14
design-baseline record and is preserved verbatim; it is a historical statement,
not a current-status claim. The `may be separately authorized` permission
boundary still holds. §15 records which parts have since been implemented
(G1, G1.5, G2) and which remain outstanding (G3 production Producer, G4 Golden
047 / freeze, and every separate decision listed above).

## 14. Evidence navigation

Baseline implementation boundaries for independent review:

- [Group schema](../schema/svm-document-v0.1.schema.json),
  [Document validation](../svm/document.py): `_validate_groups`,
  `_validate_group_transform`, `_validate_structural_relations`.
- [Change authority](../svm/change_authority.py): exact registry, source hooks,
  existing construction and transform intent resolvers.
- [Acceptor](../svm/proposals.py): `_validate`, `_verify_artifacts`,
  `_verify_artifact_bound_changes`;
  [Revisions](../svm/revisions.py): `Transaction.apply`, `RevisionStore`,
  `Revision`, `AdmittedRevision`, and the existing Group Changes.
- [P2D-A pure Consumer](../svm/adapters/motion_target_binding_selection.py),
  [explicit S1](../svm/adapters/temporal_motion_target_binding.py),
  [Spec80 verifier](../svm/adapters/representation_certification.py),
  [B0 Consumer](../svm/representation_target_consumer.py).
- [Component Promotion](17-component-promotion.md),
  [Group Promotion](29-explicit-group-promotion.md),
  [Group Transform](30-group-transform.md),
  [construction authority](72-construction-derived-group-authority.md).

The prerequisite BLOCKED reports dated 2026-10-13 and 2026-10-14 are external
investigation artifacts, not normative repository inputs. The present explicit
current-Base authoring decision resolves their assembly-authority design question;
it does not retroactively turn their unsuccessful Group fixtures into accepted
states or resolve the separate P2D-A implementation gate.

## 15. Implementation progress record (as of 2026-10-19)

This record tracks implementation of the §13 authorization boundary. It is
status documentation, not a normative contract change, not executable
conformance evidence and not a freeze. The normative semantics in §§1–14 are
unchanged.

| Step | Scope | Status | Evidence |
| --- | --- | --- | --- |
| G1 | Authored-group Document dialect and reader/schema support | **IMPLEMENTED / NOT FROZEN** | commit `46bf27b`; `svm/document.py` (`DocumentDialect.AUTHORED_GROUP_ASSEMBLY`, `AUTHORED_GROUP_TYPE`, `AUTHORED_GROUP_AUTHORITY`); `schema/svm-document-v0.1-authored-group-assembly-v0.1.schema.json` |
| G1.5 | RevisionStore dialect upgrade, trusted-history restore and final-validation integration | **IMPLEMENTED / NOT FROZEN** | commit `9d3b8a4`; `svm/admission_history.py`, `svm/proposals.py`, `svm/revisions.py`; `tests/test_document_dialect_integration.py` |
| G2 | `AssembleAuthoredGroupChange`, exact `ChangeAuthority` registration and the independent verifier | **IMPLEMENTED / NOT FROZEN** | commit `86a308e` (format/test follow-ups `ffbbc27`, `a93fb45`); `svm/authored_group_assembly.py`, `svm/revisions.py`, `svm/change_authority.py`; `tests/test_authored_group_assembly.py`, `tests/test_authored_group_authority.py` |
| G3 | `AuthoredGroupAssemblyAdapter` production Producer (Proposal/preview packaging) | **NOT IMPLEMENTED** | no `svm/adapters/authored_group_assembly.py` and no `adapter:authored-group-assembly` registration is tracked in `git ls-files` |
| G4 | Golden 047 and the final freeze record | **NOT DONE** | no `examples/047-*` path is tracked |

Non-claims that this record does not change:

- **G2 implementation is not G3 Producer completion.** G2 supplies a registered
  Change, its independent verifier and tests; there is no production
  Proposal-producing Producer, CLI entry or editor packaging.
- **Author-chosen membership is not independent cross-frame identity
  authentication.** The assembly asserts current structural author intent over
  existing accepted Entities; it performs no cross-frame matching, no evidence
  recognition, no automatic membership inference and no geometric assignment
  (§1, §10).
- **This document is NOT FROZEN.** No G4 freeze has occurred.
- **P2D-A stays BLOCKED / NOT READY / NOT FROZEN**; a successful authored
  assembly is not automatic Binding authority and does not authorize
  two-Pair automatic binding (§13).
- **Frozen P2D-B0 v0.1 and Spec80 are unchanged**; no B0 freeze scope expands.

Verification position: the W1 repair (`a93fb454`) fixed the G2 no-op-predecessor
test; local Ruff formatting, Ruff lint, Pyright and the focused
`test_authored_group_authority.py` module pass. Full CI on the repaired revision
is still pending and is **not** asserted as PASS here.
