# P2S-F1B — Present-time Verified Representation Certification

Status: **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN**.
Baseline: `f8f9ef57243fb4feb5ca9d9bd6d04f3dad9e3ed7`.
Governing invariants: INV-PROP-001/002, INV-TXN-001, INV-REF-001,
INV-ID-001/002 and INV-TIME-011; Spec71 §12 supplements its unchanged initial
atomic construction proof mode.

## 1. Exact meaning and bounded authority

This profile certifies the present relationship between an accepted whole-subject
TemporalIdentity T and a persistent source-backed Spec78 Group G. It establishes
at the current accepted base that independently reproduced Spec79 ownership of
the complete Spec76 subject and a historically Spec78-conformant representation
refer to the same exact source-qualified subject, parts, occurrences and four
membership cells. Common source IDs alone are insufficient.

The certification SHALL NOT claim that the dedicated F0 verifier executed at
birth, that association existed at birth, or that a historical F0 admission event
existed. Legacy F0 birth histories are indistinguishable between dedicated
acceptance and trusted low-level commit. Full origin replay establishes recipe
and structural conformity only. Both histories are eligible on that same basis.
The new current certification event, and not that lost historical execution
fact, grants association authority.

One authority admits only the existing authored two-triangle source, two covered
occurrences, four membership cells and complete Spec79 whole-subject identity.
No arbitrary Group adoption, caller-selected target, ordinary video inference,
new geometry reconstruction or general representation matching is supported.

Versioned identities:

```text
profile = svm-source-backed-two-triangle-representation-certification@0.1
association schema = svm-present-representation-certification-0.1
association media = application/vnd.svm.representation-certification+json;version=0.1
admission contract = svm-present-representation-certification-admission@0.1
dedicated Change = svm.revisions.CertifyArtworkRepresentationChange@0.1
independent verifier = svm-present-representation-independent-verifier@0.1
```

## 2. Authenticated base and complete transport

The Proposal base SHALL be the real accepted current base. The exact complete
Document and canonical complete ancestral Revision witness DAG are authenticated
by the existing source revision resolver and unchanged Revision commitments.
The Change's incoming-Document guard compares the entire base snapshot before
reference mutation. An earlier Change cannot substitute a different universe.

Initially every ancestry path used is single-parent. Missing, invented,
noncanonical, disconnected or hash-inconsistent history rejects. Each supplied
snapshot is checked against its Revision commitment, including supported
admission events. Hash-consistent invented events do not replace the real base
anchor. No live RevisionStore reads occur inside an artifact verifier.

The verifier independently enumerates the complete current reference universe
in canonical Artifact-ID order, every current TemporalIdentity and Group, and
every relevant current admitted association. Transport SHALL equal that complete
universe plus the exact output descriptor. Source summaries are resolved to exact
accepted descriptors at their authenticated bases. Relevant historical artifacts
and all currently required admitted claims must be available and independently
verified. Caller subsets, dependency lists or projection hashes grant no trust.

## 3. Source and TemporalIdentity verification

Authenticate genuine Spec77/76 admission and reproduce complete original and
current Spec76 ownership, pixel/source closure, subject, parts, occurrence timing
and membership through existing verifiers. No new source grammar or thresholds
are introduced. Reuse the actual Spec75 source parser.

Independently reproduce Spec79 whole-subject observations and their original
membership companion, the complete frozen R0 evidence at its accepted source
base, and the exact frozen R1 binding/provenance definition. The complete accepted
T must equal that definition. Partial, extended, fabricated or competing endpoint
ownership rejects under this bounded profile; part identities are not merged.
Accepted companion bytes alone do not prove that F1A's verifier historically ran.

T and its independently reproduced source-backed meaning SHALL already exist
in the authenticated pre-Document before G's birth and remain unchanged along
the subsequent history. The current complete identity universe is inspected;
unsupported paths cannot be omitted or relabeled as whole-subject authority.

## 4. Historical structural conformity and unique target

Determine G from the existing Spec78 source-qualified allocation recipe, not
from a request option, supplied Group ID, proximity or visual resemblance.
Enumerate all current Groups. Exactly one source-derived, currently eligible
Spec78 Group and one origin transition must exist; ambiguity rejects.

At its single-parent birth transition, G and all allocated member identities
must be absent before and present afterward. Reproduce the entire Spec78 Change
from the complete authenticated pre-base and its admitted inputs. Applying that
recipe must reproduce the complete committed post-Document, including fragment,
bindings, styles, render stack, Group, manifest and unchanged null-claim receipt.
Matching a subset of the post-state, transaction name or receipt bytes is
insufficient. Extra mutation in the birth transaction rejects this bounded mode.

Require exact equality of the source-qualified subject, admitted ownership
descriptor/event, two parts, two occurrences and all four cells across Spec79
and Spec78. Verify both the manifest and receipt as exact reproduced bytes and
descriptors. The historical receipt is neither rewritten nor upgraded.

The full replay is a newly executed structural verification. It does not assert
that any dedicated verifier, policy enforcement or association admission ran at
the historical transition. Original F0 admission authority is not certified.

## 5. Continuity and current applicability

For every snapshot from birth through the certification base, require unchanged
T, G, member Entities, geometry Operations, output bindings, member styles,
relative render order and construction provenance, plus exact continuity of
the required source, manifest and receipt descriptors. Deletion/recreation,
membership replacement, provenance alteration, identity extension or changed
representation definitions rejects profile v0.1. The profile fixes this
projection; the producer cannot choose fields to ignore.

Required descriptor continuity includes every reconstructed F0 input/output:
Spec76 ownership, exact authored source/video/production manifest and complete
P2A/P2B/raster dependency closure, plus the accepted Spec79 Stage1 membership
companion, Stage3 identity companion, frozen R0 and whole-observation descriptors.
Temporary removal followed by restoration does not preserve continuity.

A Track targeting G, a member Entity or a member geometry Operation also blocks
this initial profile: sampled representation changes are not hidden behind
unchanged base parameters. Unrelated animation does not grant or erase authority.
Existing MotionTargetBindings are enumerated separately; a binding addressing
T or G blocks this profile's new certification or consumption. Frozen S1 bindings
remain intact and authoritative for their own semantics; no automatic correction,
replacement or materialization occurs.

This is a bounded applicability rule, not a global prohibition on geometry,
style, transform or animation edits. Existing registered edits retain their
ordinary legality and stable identities. After a relevant edit, fresh consumption
must independently reverify applicability; this initial profile may reject.
Future profiles may admit wider ordinary edits without inventing history or
silently reallocating a target.

## 6. Association record, equivalence and complete ownership

The canonical record binds the versioned profile and present-time proof mode;
the exact current base and Document commitment; complete accepted T definition;
source ownership descriptor/admission and complete subject membership; historical
birth pre/post commitments; reproduced manifest/receipt and Group; and canonical
current identity, Group and admitted-association universes. Its exact field shape
is fixed by the implementation below and rejects unknown versions or extensions
by complete canonical reconstruction, never partial field checking.

The exact outer fields are:

```text
{schema_version, profile_identity, proof_mode, base,
 ownership_evidence_reference, ownership_admission, subject_identity,
 construction_birth, association, representation, universe}
```

`proof_mode` is `PRESENT_TIME_CERTIFICATION@0.1`; `base` contains exactly
`{revision_id, document_hash}`. The ownership descriptor and full admission event
are independently reproduced Spec76/77 records. `subject_identity` contains
exactly `{identity_evidence_reference, subject_observation_evidence,
r0_evidence_reference, temporal_identity}`: the original accepted Stage3 companion
descriptor, complete original Stage1 membership record, actual R0 descriptor and
complete frozen R1 definition. All are reproduced at their authenticated bases.

`construction_birth` contains exactly `{proof_kind, pre_revision_id,
post_revision_id, construction_reference, receipt_reference}`; `proof_kind` is
`STRUCTURAL_CONFORMITY_ONLY`. `association` contains exactly `{subject_id,
temporal_identity_id, group_id}`. `representation` contains exactly `{entities,
operations, output_bindings, styles, render_entries, group, temporal_identity}`,
in the original ordered fragment representation. `universe` contains exactly
`{temporal_identities, groups, association_references}`, with complete definitions
in canonical ID order and every genuinely admitted current association descriptor.
The complete current base commitment also authenticates all unadmitted references.

The record explicitly describes birth evidence as structural conformity and
current acceptance as the association authority. It includes no assertion of
historical dedicated verifier success. DerivedArtifact provenance is fixed by
the profile; content hash or provenance alone is not admission.

All current reserved references remain visible in the complete base and source
transport. Only those with
the exact supported admission event in authenticated ancestor history are
authoritative claims. Low-level/generic attachments without events are data and
do not satisfy equivalence, conflict ownership or idempotence. An existing admitted
claim must be reproduced at its own authentic certification base and checked
again against current identity, representation and dependency continuity.

At most one active G is allowed for a T and at most one T for a G. Conflicting,
duplicated non-equivalent or unreplayable admitted claims reject; no tie-break or
winner selection is permitted. An equivalent genuine admitted claim reuses its
exact reference without another Artifact or event. Claim equivalence binds the
full logical T/G/source/birth/membership relationship, not just the endpoint IDs.
`claim_key(record)` is the full SHA-256 of its canonical complete contents except
`base` and `universe`; this is a computed equivalence key, not an extra record
field. Each admitted record's original base and universe are nevertheless fully
replayed before that key can be used.
The ordinary same-Document child Revision remains permitted for idempotence.
An equivalent unadmitted reference cannot be silently promoted by reuse.

## 7. Dedicated Change, policy and atomic acceptance

`CertifyArtworkRepresentationChange` is an exact registered evidence-only Change
with these fields:

```text
source_revision_id
base_document_snapshot
witnesses
profile_identity
source_references
association_reference
```

Its registered independent verifier reconstructs the complete derivation and
canonical association bytes/descriptors. The producer adapter has no authority.
The dedicated policy actions are `certify_representation` and `attach_analysis`,
both on `document`. Denying either rejects acceptance.

For profile v0.1 a certification transaction contains exactly one dedicated
certification Change. Preceding or following Changes cannot alter the verified
universe or representation before publication. This bounded restriction does not
change ordinary transactions or Spec76's existing mixed-transaction support.

Only the exact verified dedicated Change may establish a new reference with the
reserved association media type. Transaction-wide actual-delta enforcement covers
every registered reference-producing path, delegated imports, mixed transactions,
hidden additions, replacements/removals and generic declared no-op laundering.
Do not forbid the media inside the shared low-level append helper: the dedicated
Change uses that helper after verification. Duplicate dedicated Changes reject.
Existing exact references may be transport inputs without creating authority.

After every verifier, policy and candidate-validation check succeeds, Core emits
one supported event per new dedicated association descriptor. Validation alone
and trusted plain commit emit none. No caller metadata can supply an event.
Candidate and events publish once atomically; rejection leaves HEAD, Revision
count, Document, Groups, identities and reference universe unchanged.

## 8. Event commitment, persistence and acyclicity

Use the existing `AdmissionEvent` fields and `AdmittedRevision` identity design:
contract, exact Change/verifier identities, exact current base, complete association
descriptor and legacy-form final-transition commitment. Dispatch only the original
Spec76 tuple and this new exact tuple. Unknown versions, descriptor/media-family
mismatch, duplicate or missing coverage, wrong parent or transition reject.

A certification-bearing Revision has exactly one event. Removing that event's
new association reference from its entire post-Document SHALL reproduce its
complete parent Document. Persistence and witness validation enforce this
evidence-only transition; a self-consistent extra mutation is not certification.

No admission occurs when the exact genuinely admitted output is reused. Preserve
legacy and Spec76-only Revision preimages byte-for-byte. No historical F0 Revision,
receipt, Artifact or admission is rewritten. Extend trusted-history persistence
and witness validation only for the exact new event family, using the separately
retained host commitment; a digest computed from untrusted input is not trust.

The dependency order is acyclic:

```text
accepted Spec76/77 ownership -> Spec79/R0/R1 T
earlier F0 pre-base -> manifest -> Group/receipt -> F0 birth post-base
current base + authenticated earlier proofs + earlier admitted claims
  -> association bytes -> association descriptor
current base + appended descriptor -> final Document/legacy transition commitment
descriptor + base + transition commitment -> admission event -> new Revision
```

The record contains neither its own Artifact ID nor its resulting Revision ID.
Existing-claim replay follows strictly earlier authenticated bases and cannot
recursively certify itself or hide a cycle through caller-selected history.

## 9. Golden, required regressions and remaining gates

Golden 046 uses the existing Spec75/76 fixture: genuine ownership admission,
accepted Spec79 T, existing Spec78 G and a separate present-time certification.
Pin measured association/event/Revision identities and canonical bytes. Preserve
T, G, member Entity/Operation IDs and the exact original null-claim receipt.
Persist/reload and independently consume the admitted relationship. Create no
Entity, Group, TemporalIdentity, MotionTargetBinding, Track or Keyframe.

Test generic laundering through every reference mutation family, low-level commit
without an event, both indistinguishable F0 birth paths, arbitrary Group, source/
part/occurrence mismatch, missing/forged ownership admission, incomplete T,
incomplete origin replay, structural changes, omitted or conflicting association
claims, duplicate idempotence, stale base, policy denial and partial rollback.
Run focused tests, authority and Spec76–79 regressions, full unittest suite,
Ruff formatting/lint, Pyright and `git diff --check`. Earlier Goldens and numeric
tolerances remain unchanged.

This profile does not provide historical F0 execution attestation, general artwork
matching, third-occurrence coverage, edit-aware association consumption, arbitrary
video ownership, P2D-B, S1 target selection or animation authority. Portable
Document references without authenticated host admission history remain data.

## 10. Implementation and measured Golden

The implementation is `svm/adapters/representation_certification.py`, its exact
Core Change/registry and the narrow second family in `svm/admission_history.py`.
The relationship remains an admitted Document-referenced evidence record; no
materialized relationship collection is introduced. The only schema addition is
the dedicated policy action. ProposalAcceptor, legacy Revision hashing, existing
Spec76 event identities, F0 receipt bytes and frozen R0/R1 semantics are unchanged.

[Golden 046](../examples/046-representation-certification/README.md) measures:

```text
T = temporal-identity:f89cc670dc7d6d8f54dd519532d525346817425825949ded13a79daae45aacbf
G = group:1f24284859439580faac31e69df1aa7bf6a1a28c450d8ddae2e3b42e48b656ac
birth pre = revision:4865787b0ed71cc93bc279f51db91ff03e272995deb06833c71f35fa20b63626
birth post / certification base = revision:cf523ee00bde4e8dd0d3d9830b79d1aa6cae239188e34dd15ba3951ae9375756
unchanged F0 receipt = artifact:a81e206c77162db48212fc086704a948ee4d99de2fb5de9a306af8e50861aaf4
association = artifact:6ee8fd89abc03a3094d0e1b1fbc4fbd2043345bc7ff5418d2adbe7aee6262f47
transition = revision:71bdbe8f816f845b4c53e144c478f618711c08fa8ab4bf82a24334e053317953
certification Revision = revision:29f30d08a83e2db47bcf01db6acb28f1468e2792a38c94417b4435d52f449e87
Document hash = sha256:fb92332b3df73a954e43a00a7a24ccfc5161d068aabf8c643652d3949ff6e003
```

The certificate is 18,289 canonical bytes. It transports the complete 21-reference
base. Its one event binds the exact descriptor, current base and final transition.
All existing artwork/observation identities and rendering bytes are preserved.
`admitted_associations` provides read-only, independently replayed current
consumption; an equivalent valid repeat reuses the same descriptor without a new
event. The trusted-history roundtrip preserves the admitted relationship.
