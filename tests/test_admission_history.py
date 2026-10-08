import copy
import hashlib
import json
import unittest
from dataclasses import asdict, replace
from unittest.mock import patch

from test_authored_raster_production import ROOT, pipeline

from svm import (
    AdapterRequest,
    AnchoredRegenerationContract,
    ImpactTarget,
    ProposalAcceptor,
    RevisionStore,
    Transaction,
)
from svm.adapters.multipart_subject_evidence import MultipartSubjectEvidenceAdapter, derive
from svm.admission_history import (
    AUTHORITY,
    CHANGE,
    CONTRACT,
    AdmissionError,
    dump_trusted_history,
    history_digest,
    load_trusted_history,
    transition_hash,
)
from svm.evaluator import canonical_bytes
from svm.multipart_witness import authenticate_witnesses, collect_witnesses
from svm.proposals import ProposalArtifactError
from svm.revisions import (
    AdmittedRevision,
    AppendReferencesChange,
    AppendSceneFragmentChange,
    ReplaceSceneFragmentChange,
    Revision,
)


class AdmissionHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = pipeline()

    def setUp(self):
        self.artifacts, self.store, *_ = copy.deepcopy(self.fixture)

    def propose(self):
        return MultipartSubjectEvidenceAdapter().propose(
            AdapterRequest.from_store(self.store, self.store.head, ("document",)),
            self.artifacts,
            witnesses=collect_witnesses(self.store, self.store.head),
        )

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def changed(self, proposal, changes):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=changes),
            required_artifact_ids=tuple(
                dict.fromkeys(ref["id"] for c in changes for ref in getattr(c, "references", ()))
            ),
        )

    def reject(self, proposal):
        before = copy.deepcopy(self.store)
        with self.assertRaisesRegex(ProposalArtifactError, "SPEC76_ADMISSION_REQUIRED"):
            self.accept(proposal)
        self.assertEqual(before, self.store)
        self.assertEqual(before.head, self.store.head)
        self.assertEqual(
            before.get_document(before.head)["references"],
            self.store.get_document(self.store.head)["references"],
        )

    def test_dedicated_event_binds_exact_transition(self):
        proposal = self.propose()
        before = copy.deepcopy(self.store)
        ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(before, self.store)  # Validation alone never issues admission.
        revision = self.accept(proposal)
        self.assertIs(type(revision), AdmittedRevision)
        (event,) = revision.admissions
        self.assertEqual(
            (event.contract, event.change_identity, event.authority_identity),
            (CONTRACT, CHANGE, AUTHORITY),
        )
        self.assertEqual(event.base_revision_id, proposal.base_revision_id)
        self.assertEqual(
            event.artifact_reference, proposal.transaction.changes[0].evidence_reference
        )
        self.assertEqual(
            event.transition_hash,
            transition_hash(
                self.store.get_document(self.store.head),
                revision.parent_ids,
                revision.transaction_id,
                revision.message,
            ),
        )
        self.assertNotEqual(event.transition_hash, revision.revision_id)

    def test_two_paths_same_bytes_and_copied_transaction_are_distinguishable(self):
        proposal = self.propose()
        ref = proposal.transaction.changes[0].evidence_reference
        legacy = copy.deepcopy(self.store)
        transaction = replace(proposal.transaction, changes=(AppendReferencesChange((ref,)),))
        # Simulate pre-E1C persisted history using the trusted low-level commit.
        old = legacy.commit(legacy.head, transaction)
        current = self.accept(proposal)
        self.assertEqual(
            legacy.get_document(old.revision_id), self.store.get_document(current.revision_id)
        )
        self.assertEqual(old.transaction_id, current.transaction_id)
        self.assertEqual(old.message, current.message)
        self.assertNotEqual(old.revision_id, current.revision_id)
        self.assertIs(type(old), Revision)
        _, unproven_reuse = derive(
            legacy.head, collect_witnesses(legacy, legacy.head), self.artifacts
        )
        _, admitted_reuse = derive(
            self.store.head, collect_witnesses(self.store, self.store.head), self.artifacts
        )
        self.assertIsNone(unproven_reuse)
        self.assertEqual(admitted_reuse, ref)

    def test_generic_append_and_fragment_and_replacement_cannot_admit(self):
        # A real legal scene provides a valid ReplaceSceneFragment scope.
        source = json.loads((ROOT / "examples/003-split-head.svm.json").read_text())
        d = self.store.get_document(self.store.head)
        for key in ("entities", "construction", "presentation"):
            d[key] = source[key]

        # Preserve the actual ancestral source/video chain with a trusted fixture change.
        class InstallScene:
            def apply(inner, document):
                for key in ("entities", "construction", "presentation"):
                    document[key] = copy.deepcopy(d[key])

        self.store.commit(self.store.head, Transaction("transaction:test-scene", (InstallScene(),)))
        proposal = self.propose()
        ref = proposal.transaction.changes[0].evidence_reference
        changes = (
            AppendReferencesChange((ref,)),
            AppendSceneFragmentChange((), (), (), (), (), (ref,)),
            ReplaceSceneFragmentChange(
                tuple(e["id"] for e in d["entities"]),
                tuple(o["id"] for o in d["construction"]["operations"]),
                tuple(d["entities"]),
                tuple(d["construction"]["operations"]),
                tuple(d["construction"]["output_bindings"]),
                tuple(d["presentation"]["render_stack"]),
                tuple(d["presentation"]["styles"]),
                (ref,),
            ),
        )
        for change in changes:
            with self.subTest(change=type(change).__name__):
                # Prove the input is valid for its mutation path, not an unrelated error.
                Transaction("test", (change,)).apply(d)
                self.reject(self.changed(proposal, (change,)))

    def test_actual_additions_checked_even_without_declared_reference(self):
        proposal = self.propose()
        ref = proposal.transaction.changes[0].evidence_reference
        generic = AppendSceneFragmentChange((), (), (), (), ())

        # Simulate a future registered writer that fails to expose its reference.
        def append_actual(change, document):
            document["references"].append(copy.deepcopy(ref))

        with patch.object(AppendSceneFragmentChange, "apply", append_actual):
            self.reject(self.changed(proposal, (generic,)))

    def test_mixed_and_duplicate_changes_cannot_launder_admission(self):
        proposal = self.propose()
        dedicated = proposal.transaction.changes[0]
        generic = AppendReferencesChange((dedicated.evidence_reference,))
        for changes in ((generic, dedicated), (dedicated, generic), (dedicated, dedicated)):
            with self.subTest(order=[type(c).__name__ for c in changes]):
                self.reject(self.changed(proposal, changes))

    def test_ordinary_generic_attachments_and_legacy_identity_unchanged(self):
        template = self.propose()
        ref = self.artifacts.import_bytes(b"ordinary", media_type="text/plain").document_reference()
        proposal = self.changed(template, (AppendReferencesChange((ref,)),))
        revision = self.accept(proposal)
        self.assertIs(type(revision), Revision)
        preimage = {
            "document_hash": revision.document_hash,
            "parent_ids": revision.parent_ids,
            "transaction_id": revision.transaction_id,
            "message": revision.message,
        }
        self.assertEqual(
            revision.revision_id,
            "revision:" + hashlib.sha256(canonical_bytes(preimage)).hexdigest(),
        )
        self.assertNotIn("admissions", asdict(revision))

    def test_persisted_json_history_preserves_admission_and_idempotence(self):
        first = self.propose()
        self.accept(first)
        encoded = json.loads(json.dumps(dump_trusted_history(self.store)))
        restored = load_trusted_history(
            encoded, trusted_history_hash=history_digest(dump_trusted_history(self.store))
        )
        self.assertEqual(restored, self.store)
        self.store = restored
        repeat = self.propose()
        self.assertEqual(first.preview_artifacts, repeat.preview_artifacts)
        document = self.store.get_document(self.store.head)
        revision = self.accept(repeat)
        self.assertIs(type(revision), Revision)  # No duplicate event for idempotent reuse.
        self.assertEqual(document, self.store.get_document(revision.revision_id))
        self.assertEqual(
            load_trusted_history(
                dump_trusted_history(self.store),
                trusted_history_hash=history_digest(dump_trusted_history(self.store)),
            ),
            self.store,
        )

    def test_legacy_roundtrip_and_explicit_fresh_readmission_preserve_old_data(self):
        original = self.propose()
        ref = original.transaction.changes[0].evidence_reference
        self.store.commit(
            self.store.head,
            replace(original.transaction, changes=(AppendReferencesChange((ref,)),)),
        )
        old_head = self.store.head
        encoded = dump_trusted_history(self.store)
        self.assertTrue(all("revision_contract" not in r["revision"] for r in encoded["records"]))
        self.store = load_trusted_history(
            json.loads(json.dumps(encoded)), trusted_history_hash=history_digest(encoded)
        )
        before = self.store.get_document(old_head)
        fresh = self.propose()
        self.assertNotEqual(original.preview_artifacts, fresh.preview_artifacts)
        revision = self.accept(fresh)
        self.assertEqual(len(revision.admissions), 1)
        self.assertEqual(self.store.get_document(old_head), before)
        self.assertIn(ref, self.store.get_document(self.store.head)["references"])
        self.assertEqual(self.propose().preview_artifacts, fresh.preview_artifacts)

    def test_missing_forged_or_mismatched_event_cannot_replace_anchored_witness(self):
        self.accept(self.propose())
        repeat = self.propose()
        change = repeat.transaction.changes[0]
        current = self.store.revisions[self.store.head]
        (event,) = current.admissions
        variants = (
            (),
            (replace(event, contract="fake"),),
            (replace(event, change_identity="fake"),),
            (replace(event, authority_identity="fake"),),
            (replace(event, base_revision_id=self.store.head),),
            (
                replace(
                    event, artifact_reference={**event.artifact_reference, "id": "artifact:fake"}
                ),
            ),
            (replace(event, transition_hash="revision:fake"),),
        )
        before = copy.deepcopy(self.store)
        for events in variants:
            for rehash in (False, True):
                with self.subTest(events=events, rehash=rehash):
                    altered = (
                        RevisionStore._make_revision(
                            self.store.get_document(self.store.head),
                            current.parent_ids,
                            current.transaction_id,
                            current.message,
                            events,
                        )
                        if rehash
                        else replace(current, admissions=events)
                    )
                    witnesses = tuple(
                        sorted(
                            (
                                replace(w, revision=altered) if w.revision == current else w
                                for w in change.witnesses
                            ),
                            key=lambda w: w.revision.revision_id,
                        )
                    )
                    bad = self.changed(repeat, (replace(change, witnesses=witnesses),))
                    with self.assertRaises(ProposalArtifactError):
                        self.accept(bad)
                    self.assertEqual(before, self.store)

    def test_trusted_reload_rejects_damaged_event_revision_and_descriptor(self):
        self.accept(self.propose())
        original = dump_trusted_history(self.store)
        for field in ("contract", "base_revision_id", "transition_hash", "artifact_reference"):
            payload = copy.deepcopy(original)
            record = next(r for r in payload["records"] if "admissions" in r["revision"])
            record["revision"]["admissions"][0][field] = "forged"
            with self.subTest(field=field), self.assertRaises(AdmissionError):
                load_trusted_history(payload, trusted_history_hash=history_digest(original))
        payload = copy.deepcopy(original)
        record = next(r for r in payload["records"] if "admissions" in r["revision"])
        record["revision"].pop("admissions")
        with self.assertRaises(AdmissionError):
            load_trusted_history(payload, trusted_history_hash=history_digest(original))

    def test_witness_event_consistency_even_with_recomputed_untrusted_hash(self):
        self.accept(self.propose())
        current = self.store.revisions[self.store.head]
        event = replace(current.admissions[0], transition_hash="revision:fake")
        fake = RevisionStore._make_revision(
            self.store.get_document(self.store.head),
            current.parent_ids,
            current.transaction_id,
            current.message,
            (event,),
        )
        witnesses = tuple(
            sorted(
                (
                    replace(w, revision=fake) if w.revision == current else w
                    for w in collect_witnesses(self.store, self.store.head)
                ),
                key=lambda w: w.revision.revision_id,
            )
        )
        with self.assertRaisesRegex(AdmissionError, "event/transition"):
            authenticate_witnesses(fake.revision_id, witnesses)

    def test_anchored_acceptance_has_same_exclusive_admission_boundary(self):
        proposal = self.propose()
        protected = ImpactTarget("import_scene", "document")
        contract = AnchoredRegenerationContract(
            proposal.base_revision_id,
            (protected,),
            (protected,),
            (protected,),
            (ImpactTarget("attach_analysis", "document"),),
        )
        # Current head advances, while the explicit anchor remains immutable.
        self.store.commit(self.store.head, Transaction("transaction:advance", ()))
        ref = proposal.transaction.changes[0].evidence_reference
        bad = self.changed(proposal, (AppendReferencesChange((ref,)),))
        before = copy.deepcopy(self.store)
        with self.assertRaisesRegex(ProposalArtifactError, "SPEC76_ADMISSION_REQUIRED"):
            ProposalAcceptor().accept_anchored(self.store, bad, contract, self.artifacts)
        self.assertEqual(before, self.store)
        revision = ProposalAcceptor().accept_anchored(
            self.store, proposal, contract, self.artifacts
        )
        self.assertEqual(revision.parent_ids, (proposal.base_revision_id,))
        self.assertEqual(revision.admissions[0].base_revision_id, proposal.base_revision_id)

    def test_rehashed_forged_persistence_cannot_replace_trusted_snapshot(self):
        self.accept(self.propose())
        payload = dump_trusted_history(self.store)
        trusted_digest = history_digest(payload)
        row = next(r for r in payload["records"] if "admissions" in r["revision"])
        old = self.store.revisions[self.store.head]
        fake = RevisionStore._make_revision(
            row["document"],
            old.parent_ids,
            old.transaction_id,
            old.message,
            (replace(old.admissions[0], authority_identity="forged"),),
        )
        row["revision"] = {**asdict(fake), "revision_contract": "svm-revision-admission@0.1"}
        payload["head"] = fake.revision_id
        with self.assertRaisesRegex(AdmissionError, "Trusted history digest mismatch"):
            load_trusted_history(payload, trusted_history_hash=trusted_digest)

    def test_later_failure_and_verifier_failure_never_issue_event(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        before = copy.deepcopy(self.store)
        with self.assertRaises(ProposalArtifactError):
            self.accept(self.changed(proposal, (replace(change, profile_identity="forged"),)))
        self.assertEqual(before, self.store)
        # First Change executes only on the candidate; a later structural failure rolls back.
        bad = AppendReferencesChange(())
        with self.assertRaisesRegex(ValueError, "at least one Artifact reference"):
            self.accept(self.changed(proposal, (change, bad)))
        self.assertEqual(before, self.store)


if __name__ == "__main__":
    unittest.main()
