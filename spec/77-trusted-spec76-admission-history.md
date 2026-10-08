# P2S-E1C — Trusted Spec76 Admission History

Status: implemented bounded Core admission contract; NOT FROZEN.
Baseline: `3249a37da7e3b0393f590f5be83f5b13501e2de4`.
Governing invariants: INV-PROP-001/002, INV-TXN-001, INV-REF-001;
the exact registered Change boundary of spec/05 and spec/09.

## 1. Information loss and scope

The legacy Revision commits the resulting Document, parent IDs, transaction ID
and message, but not the executed Changes or verifier success. A generic append
with copied transaction ID/message could produce precisely the same Revision
and ancestry witnesses as dedicated Spec76 acceptance. Canonical content replay
therefore could not establish historical admission. No legacy record is upgraded
by inference from those fields.

This amendment adds only trusted Spec76 admission history. The evidence schema,
profile, claim key, source ownership, pixel production, observation semantics,
Entity/Group model and TemporalIdentity are unchanged. It supersedes Spec74/76's
earlier prohibition on changing ProposalAcceptor only for this bounded boundary.
The ArtifactVerifier signature, policy intents and source revision binding remain
unchanged. P2S-E1 is **NOT CLOSED**, P2D-B **BLOCKED**, whole-subject TemporalIdentity
**OPEN**, and Stable Representation Correspondence remains a separate gate.

## 2. Trust root

The trusted host owns RevisionStore, the exact Change registry and verifier code.
Adapters supply data-only Proposals, witnesses and Artifact bytes; they MUST NOT
mutate host memory, invoke trusted commit/persistence APIs, replace registered
code, or choose a trusted reload digest. This is the existing in-process Core
boundary, not a sandbox for arbitrary Python executed inside the trusted host.

Only ordinary or anchored ProposalAcceptor acceptance, after all registered
verifiers, base/anchor checks, policy checks and candidate validation succeed,
creates admission facts. `validate()` alone creates no event. Plain
`RevisionStore.commit()` remains a trusted internal mechanism and creates NO
admission event, even when its transaction contains the dedicated Change.
`_commit_verified()` and the event builder are trusted Core internals, never
Adapter APIs. Event type names, provenance and hashes supplied in a Proposal or
Artifact confer no authority.

Hash consistency is not proof that a verifier ran. Witnesses authenticate events
only when their complete DAG links to the exact base already present in the real
trusted store, bound by the unchanged source_revision_resolver. A self-consistent
invented event and rehashed Revision cannot replace that anchor.

## 3. Event and acyclic identity

`AdmissionEvent` has exactly these fields:

| Field | Value |
| --- | --- |
| `contract` | `svm-spec76-admission@0.1` |
| `change_identity` | `svm.revisions.AttachMultipartSubjectEvidenceChange@0.1` |
| `authority_identity` | `svm-spec76-independent-verifier@0.1` |
| `base_revision_id` | exact accepted Proposal base |
| `artifact_reference` | complete admitted descriptor, including Artifact ID |
| `transition_hash` | commitment T defined below |

Let H denote full SHA-256 of repository canonical bytes. For candidate Document D:

```text
document_hash = "sha256:" + H(D)
L = {document_hash, parent_ids: [base], transaction_id, message}
T = "revision:" + H(L)
event = {contract, change_identity, authority_identity,
         base_revision_id: base, artifact_reference, transition_hash: T}
new Revision ID = "revision:" + H({**L,
    revision_contract: "svm-revision-admission@0.1", admissions: [event]})
```

T uses the legacy transition preimage as a commitment; it does not name another
stored Revision and is not the resulting Revision ID. Events commit the entire
final transaction result, including permitted ordinary Changes. No event embeds
its resulting Revision ID. Artifact bytes depend on the earlier base, not on the
admission event. The dependency graph is acyclic.

New event-bearing Revisions use `AdmittedRevision`. Events occur in transaction
order, exactly once per newly admitted Artifact. Each must match the singleton
parent, transition commitment and new exact reference. Unknown versions,
duplicates, missing coverage and mismatched events reject.

When no new admission occurs, the original `Revision` type, serialized fields
and legacy hash preimage remain unchanged. Existing IDs are never rewritten.
An ordinary or idempotent child of an admitted Revision still uses the legacy
formula, with the actual parent ID; ancestry retains the earlier admission.

## 4. Complete transaction enforcement

After ordinary verifier and policy success, Core applies Changes to an isolated
candidate while checking every actual reserved-reference delta. Only the exact
registered `AttachMultipartSubjectEvidenceChange` may add its independently
verified evidence reference with media type
`application/vnd.svm.multipart-subject-evidence+json;version=0.1`.

The check covers all registered mutation paths, not only AppendReferencesChange:
AppendSceneFragmentChange, ReplaceSceneFragmentChange, delegated imports and all
other reference-producing Changes pass through the same actual-mutation check.
Unknown Change subclasses still fail the existing exact registry lookup.

A generic Change cannot declare a new reserved reference even if an earlier
dedicated Change would make that later generic append a no-op. Duplicate dedicated
Changes for the same Artifact reject. Existing exact references may remain ordinary
inputs without creating any new authority. Reserved reference replacement/removal
through acceptance rejects. Unrelated ordinary attachment remains permitted.
The shared low-level AppendReferencesChange.apply helper is unchanged.

All checks precede publication. Candidate Document and events commit together;
verifier, policy, stale, per-Change or final Document failure leaves the store
unchanged. The checked candidate is committed without executing the transaction
a second time. Both ordinary and anchored acceptance use this path.

## 5. Historical claims and explicit re-admission

An existing reference counts as admitted only if BOTH hold:

1. its exact descriptor has a supported admission event in authenticated ancestor
   history, whose base matches the evidence record's original base;
2. complete canonical original-base replay and current applicability checks pass.

An event cannot replace replay; replay cannot replace an event. Complete closure,
competing-claim checks and claim_key semantics remain Spec76's. An applicable,
genuinely admitted equivalent claim reuses its Artifact without another event or
Artifact; the ordinary same-Document child Revision remains permitted.

Legacy references without such events remain representable, immutable historical
data. They SHALL NOT be counted in admitted ownership, idempotence or competing
claims, even if their bytes replay. Their embedded status/profile/key cannot
upgrade them. No event is retroactively fabricated.

Explicit re-admission is a new current-base Spec76 Proposal followed by dedicated
acceptance. It independently replays the full current closure, constructs a new
base-bound evidence record, and creates a present-tense admission event. The old
reference and old Revisions remain unchanged. Missing source/dependencies or an
ineligible current closure prevent re-admission; there is no metadata-only
migration or recovery of historic verifier execution.

## 6. Host persistence

There was no existing serialized RevisionStore interchange contract. The bounded
host snapshot format `svm-trusted-history@0.1` stores `head` and Revision-ID-sorted
`records`, each containing `revision` and `document`. Legacy revision records keep
their old fields; event-bearing records additionally carry `revision_contract`
and `admissions`. JSON roundtrip preserves identities and admission semantics.

The host persists `history_digest(snapshot)` separately as a trusted commitment.
`load_trusted_history(snapshot, trusted_history_hash=...)` requires that previously
trusted digest, then validates every Document, Revision hash, parent and event
transition, including off-head branches. It restores into a new store only.
Computing the expected digest from an untrusted incoming file does NOT authenticate
that file. Secure storage of the host commitment is an external trust assumption;
this slice supplies no signature issuer, cross-host federation or untrusted
history-import endpoint. Losing the trusted commitment does not authorize accepting
replacement history on the strength of self-consistent hashes.

## 7. Verification and reviewed authority pin

`tests/test_admission_history.py` covers the original indistinguishability case,
all three generic paths, hidden actual additions, mixed/duplicate Changes,
anchored acceptance, atomicity, ordinary attachments, new events, forged/missing
witness events, trusted reload, rehashed persistence forgery, old hash compatibility,
explicit fresh re-admission and genuine idempotence. Spec76's original red test
now requires the specific boundary rejection and unchanged HEAD/Document/references.

ProposalAcceptor's intentional diff adds transaction-wide admission enforcement
after existing verifiers/policies, and commits the validated candidate with trusted
events. Artifact resolution, exact Change lookup, source revision resolver and
anchor rules are unchanged. The LayerD integrity test remains intact; its source
pin is updated only for this reviewed Core authority extension:

```text
old: 617269931cd24653dc63c1fe4d9886ce086f490ff3eb9ad2a9417f910c6c8940
new: 0336d93e1151c49bc8f46a37960b01d323632ba4c17873904096336949985b97
```
