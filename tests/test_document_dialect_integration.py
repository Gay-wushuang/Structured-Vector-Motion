"""Reader/host integration only: structural fixtures do not prove Group creation."""

import copy
import json
import unittest
from dataclasses import replace

import test_authored_group_schema_compatibility as structural
import test_svg_group_construction as svg_fixture

from svm import ProposalAcceptor, RevisionStore, SetOperationParameterChange, Transaction
from svm.admission_history import (
    AdmissionError,
    apply_verified_transaction,
    dump_trusted_history,
    history_digest,
    load_trusted_history,
)
from svm.document import (
    AUTHORED_GROUP_AUTHORITY,
    AUTHORED_GROUP_TYPE,
    DocumentDialect,
    authored_group_identity,
    validate_document,
)
from svm.document_io import select_document_dialect, validate_document_schema
from svm.evaluator import DocumentError, canonical_bytes
from svm.proposals import (
    GeneratorProvenance,
    Proposal,
    ProposalArtifactError,
    ProposalConflictError,
    ProposalPolicyError,
)
from svm.revisions import AdmittedRevision, AppendSceneFragmentChange, SetGroupTransformChange

EXTENSION = DocumentDialect.AUTHORED_GROUP_ASSEMBLY
NEUTRAL = {"translate": [0, 0], "rotation_degrees": 0, "scale": 1, "origin": [0, 0]}


class StructuralGroupFixture:
    """Trusted fixture setup only; never registered as an accepted Change."""

    def __init__(self, group):
        self.group = copy.deepcopy(group)

    def apply(self, document):
        document.setdefault("groups", []).append(copy.deepcopy(self.group))


class DocumentDialectIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        structural.AuthoredGroupSchemaCompatibilityTest.setUpClass()

    def setUp(self):
        fixture = structural.AuthoredGroupSchemaCompatibilityTest()
        self.old = copy.deepcopy(fixture.old_document)
        self.authored = fixture.authored_document()

    def store(self, *, authored=False):
        return RevisionStore.create(
            self.authored if authored else self.old,
            dialect=EXTENSION if authored else DocumentDialect.BASELINE,
        )

    def proposal(self, store, changes=()):
        return Proposal(
            "proposal:dialect-test",
            store.head,
            GeneratorProvenance("adapter:dialect-test", "0.1", "structural-test", "0.1"),
            Transaction("transaction:dialect-test", changes),
        )

    def assert_rejected_unchanged(self, store, proposal, error):
        before = copy.deepcopy(store)
        with self.assertRaises(error):
            ProposalAcceptor().accept(store, proposal)
        self.assertEqual(store, before)

    def restore(self, store):
        payload = dump_trusted_history(store)
        restored = load_trusted_history(
            json.loads(json.dumps(payload)), trusted_history_hash=history_digest(payload)
        )
        self.assertEqual(dump_trusted_history(restored), payload)
        self.assertEqual(restored.revisions, store.revisions)
        self.assertEqual(restored._documents, store._documents)
        return restored

    def test_baseline_reader_and_old_revision_identity_are_unchanged(self):
        baseline, extended = self.store(), self.store()
        original = dump_trusted_history(extended)
        extended.upgrade_document_dialect(EXTENSION)
        self.assertEqual(dump_trusted_history(extended), original)
        changes = (SetOperationParameterChange("op:head_base", "rx", 0.42),)
        old_result = ProposalAcceptor().accept(baseline, self.proposal(baseline, changes))
        new_result = ProposalAcceptor().accept(extended, self.proposal(extended, changes))
        self.assertEqual(old_result, new_result)
        self.assertEqual(dump_trusted_history(baseline), dump_trusted_history(extended))
        self.assertEqual(self.restore(baseline), baseline)
        self.assertEqual(select_document_dialect(self.old), DocumentDialect.BASELINE)
        validate_document_schema(self.old, DocumentDialect.BASELINE)
        validate_document(self.old)

    def test_final_validation_has_explicit_dialect_and_legacy_default(self):
        transaction = Transaction("transaction:no-op", ())
        with self.assertRaises(DocumentError):
            apply_verified_transaction(self.authored, transaction)
        self.assertEqual(
            apply_verified_transaction(self.authored, transaction, dialect=EXTENSION),
            self.authored,
        )
        with self.assertRaises(DocumentError):
            transaction.apply(self.authored)
        self.assertEqual(transaction.apply(self.authored, dialect=EXTENSION), self.authored)

    def test_real_acceptor_edits_existing_structural_fixture_without_creating_group(self):
        store = self.store(authored=True)
        before = copy.deepcopy(store)
        proposal = self.proposal(store, (SetOperationParameterChange("op:head_base", "rx", 0.42),))
        candidate = ProposalAcceptor().validate(store, proposal)
        self.assertEqual(store, before)
        validate_document_schema(candidate, EXTENSION)
        validate_document(candidate, EXTENSION)
        revision = ProposalAcceptor().accept(store, proposal)
        self.assertEqual(store.get_document(revision.revision_id), candidate)
        self.assertEqual(candidate["groups"], self.authored["groups"])
        self.assertEqual(candidate["entities"], self.authored["entities"])
        self.assertEqual(len(store.revisions), len(before.revisions) + 1)
        self.assertEqual(self.restore(store), store)

    def test_existing_transform_authority_can_edit_but_not_create_authored_group(self):
        store = self.store(authored=True)
        group = copy.deepcopy(self.authored["groups"][0])
        proposal = self.proposal(store, (SetGroupTransformChange(group["id"], NEUTRAL),))
        ProposalAcceptor().accept(store, proposal)
        changed = store.get_document(store.head)["groups"]
        self.assertEqual(changed, [{**group, "transform": NEUTRAL}])
        missing = self.proposal(store, (SetGroupTransformChange("group:" + "f" * 64, NEUTRAL),))
        self.assert_rejected_unchanged(store, missing, DocumentError)

    def test_host_upgrade_is_explicit_monotonic_and_changes_no_content(self):
        store = self.store()
        before = copy.deepcopy(store)
        store.upgrade_document_dialect(EXTENSION)
        store.upgrade_document_dialect(EXTENSION)
        self.assertEqual(store.document_dialect, EXTENSION)
        self.assertEqual(store.head, before.head)
        self.assertEqual(store.revisions, before.revisions)
        self.assertEqual(store._documents, before._documents)
        upgraded = copy.deepcopy(store)
        with self.assertRaises(DocumentError):
            store.upgrade_document_dialect(DocumentDialect.BASELINE)
        self.assertEqual(store, upgraded)

    def test_unknown_or_string_dialect_is_not_a_host_upgrade(self):
        store = self.store()
        for value in (None, "future", EXTENSION.value, 1):
            with self.subTest(value=value):
                before = copy.deepcopy(store)
                with self.assertRaises(DocumentError):
                    store.upgrade_document_dialect(value)
                self.assertEqual(store, before)

    def test_host_upgrade_validates_all_snapshots_before_changing_configuration(self):
        store = self.store()
        old_head = store.head
        store.commit(old_head, Transaction("transaction:other", ()))
        store._documents[old_head]["semantics_version"] = "unknown"  # Corrupt host fixture.
        before = copy.deepcopy(store)
        with self.assertRaises(DocumentError):
            store.upgrade_document_dialect(EXTENSION)
        self.assertEqual(store, before)

    def test_candidate_cannot_auto_upgrade_the_trusted_transaction_path(self):
        store = self.store()
        before = copy.deepcopy(store)
        transaction = Transaction(
            "transaction:structural-only", (StructuralGroupFixture(self.authored["groups"][0]),)
        )
        with self.assertRaises(DocumentError):
            store.commit(store.head, transaction)
        self.assertEqual(store, before)
        store.upgrade_document_dialect(EXTENSION)
        # Internal structural-history setup, NOT a Group acceptance claim.
        store.commit(store.head, transaction)
        self.assertEqual(store.get_document(store.head)["groups"], self.authored["groups"])
        self.assertEqual(self.restore(store), store)

    def test_extension_cannot_authorize_unregistered_or_subclass_change(self):
        class ParameterSubclass(SetOperationParameterChange):
            pass

        for change in (
            StructuralGroupFixture(self.authored["groups"][0]),
            ParameterSubclass("op:head_base", "rx", 0.42),
        ):
            store = self.store()
            store.upgrade_document_dialect(EXTENSION)
            self.assert_rejected_unchanged(
                store, self.proposal(store, (change,)), ProposalPolicyError
            )

    def test_generator_dialect_claim_does_not_override_host_configuration(self):
        store = self.store(authored=True)
        store.document_dialect = DocumentDialect.BASELINE  # Deliberately wrong host config.
        proposal = self.proposal(store)
        proposal.generator.parameters["document_dialect"] = EXTENSION.value
        self.assert_rejected_unchanged(store, proposal, DocumentError)

    def test_invalid_host_dialect_fails_without_publication(self):
        store = self.store(authored=True)
        store.document_dialect = "unknown"
        self.assert_rejected_unchanged(store, self.proposal(store), DocumentError)

    def test_stale_base_policy_and_final_validation_remain_atomic(self):
        store = self.store(authored=True)
        proposal = self.proposal(store)
        ProposalAcceptor().accept(store, proposal)
        self.assert_rejected_unchanged(store, proposal, ProposalConflictError)

        denied = copy.deepcopy(self.authored)
        denied["edit_permissions"].append(
            {
                "id": "permission:deny",
                "actor": "*",
                "effect": "deny",
                "actions": ["set_parameter"],
                "targets": ["*"],
            }
        )
        store = RevisionStore.create(denied, dialect=EXTENSION)
        self.assert_rejected_unchanged(
            store,
            self.proposal(store, (SetOperationParameterChange("op:head_base", "rx", 0.42),)),
            ProposalPolicyError,
        )
        store = self.store(authored=True)
        invalid = {**NEUTRAL, "scale": 0}
        self.assert_rejected_unchanged(
            store,
            self.proposal(
                store,
                (
                    SetOperationParameterChange("op:head_base", "rx", 0.42),
                    SetGroupTransformChange(self.authored["groups"][0]["id"], invalid),
                ),
            ),
            DocumentError,
        )

    def test_restore_extension_on_non_head_branch_without_changing_history_format(self):
        store = self.store()
        original = store.head
        store.upgrade_document_dialect(EXTENSION)
        store.commit(
            original,
            Transaction(
                "transaction:structural-branch",
                (StructuralGroupFixture(self.authored["groups"][0]),),
            ),
        )
        authored_revision = store.head
        store.checkout(original)
        store.commit(original, Transaction("transaction:baseline-branch", ()))
        self.assertNotEqual(store.head, authored_revision)
        payload = dump_trusted_history(store)
        self.assertEqual(set(payload), {"history_contract", "head", "records"})
        self.assertEqual(payload["history_contract"], "svm-trusted-history@0.1")
        restored = self.restore(store)
        self.assertEqual(restored, store)
        restored.checkout(authored_revision)
        ProposalAcceptor().accept(restored, self.proposal(restored))
        restored.checkout(original)
        self.assertEqual(restored.document_dialect, EXTENSION)

    def test_unused_host_opt_in_is_not_falsely_restored_from_old_history(self):
        store = self.store()
        payload = dump_trusted_history(store)
        store.upgrade_document_dialect(EXTENSION)
        self.assertEqual(payload, dump_trusted_history(store))
        restored = self.restore(store)
        self.assertEqual(restored.document_dialect, DocumentDialect.BASELINE)
        restored.upgrade_document_dialect(EXTENSION)
        self.assertEqual(restored, store)

    def test_restore_rejects_injected_dialect_metadata_even_with_recomputed_digest(self):
        payload = dump_trusted_history(self.store(authored=True))
        for location in ("root", "record", "revision"):
            with self.subTest(location=location):
                forged = copy.deepcopy(payload)
                target = (
                    forged
                    if location == "root"
                    else forged["records"][0]
                    if location == "record"
                    else forged["records"][0]["revision"]
                )
                target["document_dialect"] = EXTENSION.value
                with self.assertRaises((AdmissionError, TypeError)):
                    load_trusted_history(forged, trusted_history_hash=history_digest(forged))

    def test_restore_checks_external_anchor_and_each_revision_commitment(self):
        store = self.store(authored=True)
        payload = dump_trusted_history(store)
        anchor = history_digest(payload)
        altered = copy.deepcopy(payload)
        altered["records"][0]["document"]["entities"][0]["name"] = "tampered"
        with self.assertRaisesRegex(AdmissionError, "digest mismatch"):
            load_trusted_history(altered, trusted_history_hash=anchor)
        with self.assertRaisesRegex(AdmissionError, "revision hash"):
            load_trusted_history(altered, trusted_history_hash=history_digest(altered))
        altered = copy.deepcopy(payload)
        altered["records"][0]["revision"]["message"] = "tampered"
        with self.assertRaisesRegex(AdmissionError, "revision hash"):
            load_trusted_history(altered, trusted_history_hash=history_digest(altered))

    def test_unknown_provenance_is_rejected_even_in_rehashed_structural_history(self):
        for discriminator in ("authored-group-assembly@0.2", "unknown"):
            document = copy.deepcopy(self.authored)
            document["groups"][0]["provenance"]["type"] = discriminator
            self.assertEqual(select_document_dialect(document), DocumentDialect.BASELINE)
            store = self.store()
            # A deliberately forged host-history fixture, not an accepted Group.
            revision = store._make_revision(document, (), None, "unknown fixture")
            store.revisions = {revision.revision_id: revision}
            store._documents = {revision.revision_id: document}
            store.head = revision.revision_id
            payload = dump_trusted_history(store)
            with self.assertRaises(DocumentError):
                load_trusted_history(payload, trusted_history_hash=history_digest(payload))

    def test_generic_scene_change_has_no_group_creation_field(self):
        with self.assertRaises(TypeError):
            AppendSceneFragmentChange(groups=tuple(self.authored["groups"]))

    def test_frozen_svg_construction_rejects_authored_origin_under_extension(self):
        fixture = svg_fixture.SVGGroupConstructionTest()
        fixture.setUp()
        fixture.store.upgrade_document_dialect(EXTENSION)
        proposal = fixture.propose()
        original = copy.deepcopy(fixture.store)
        forged = copy.deepcopy(proposal.transaction.changes[0])
        forged.group["provenance"] = copy.deepcopy(self.authored["groups"][0]["provenance"])
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(
                fixture.store,
                replace(proposal, transaction=replace(proposal.transaction, changes=(forged,))),
                fixture.artifacts,
            )
        self.assertEqual(fixture.store, original)
        # The original independently verified construction still retains its own origin.
        ProposalAcceptor().accept(fixture.store, proposal, fixture.artifacts)
        group = fixture.store.get_document(fixture.store.head)["groups"][0]
        self.assertEqual(group["provenance"]["type"], "construction-established-group@0.1")
        self.assertEqual(self.restore(fixture.store).document_dialect, DocumentDialect.BASELINE)

    def test_baseline_downgrade_remains_rejected_by_reader_and_internal_transaction(self):
        with self.assertRaises(DocumentError):
            validate_document(self.authored)
        with self.assertRaises(DocumentError):
            validate_document_schema(self.authored, DocumentDialect.BASELINE)
        with self.assertRaises(DocumentError):
            RevisionStore.create(self.authored)
        self.assertEqual(
            canonical_bytes(self.authored), canonical_bytes(copy.deepcopy(self.authored))
        )


class AdmittedHistoryDialectIntegrationTest(unittest.TestCase):
    def test_real_admissions_survive_extension_structural_history_roundtrip(self):
        import test_representation_target_consumer as admitted_fixture

        admitted_fixture.RepresentationTargetConsumerTest.setUpClass()
        store = copy.deepcopy(admitted_fixture.RepresentationTargetConsumerTest.fixture["store"])
        admitted = {
            rid: copy.deepcopy(revision)
            for rid, revision in store.revisions.items()
            if type(revision) is AdmittedRevision
        }
        self.assertGreaterEqual(len(admitted), 2)  # Real Spec76 and Spec80 accepts.
        store.upgrade_document_dialect(EXTENSION)
        base = store.revisions[store.head]
        members = sorted(e["id"] for e in store.get_document(store.head)["entities"])
        group_id, membership_hash = authored_group_identity(members)
        group = {
            "id": group_id,
            "kind": "explicit-group",
            "members": members,
            "provenance": {
                "type": AUTHORED_GROUP_TYPE,
                "authority_identity": AUTHORED_GROUP_AUTHORITY,
                "source_revision_id": base.revision_id,
                "source_document_hash": base.document_hash,
                "membership_hash": membership_hash,
            },
        }
        # Structural persistence fixture only, not a registered assembly acceptance.
        store.commit(
            store.head,
            Transaction("transaction:structural-history", (StructuralGroupFixture(group),)),
        )
        payload = dump_trusted_history(store)
        anchor = history_digest(payload)
        restored = load_trusted_history(
            json.loads(json.dumps(payload)), trusted_history_hash=anchor
        )
        self.assertEqual(restored, store)
        self.assertEqual(dump_trusted_history(restored), payload)
        for rid, revision in admitted.items():
            self.assertEqual(restored.revisions[rid], revision)
        forged = copy.deepcopy(payload)
        record = next(r for r in forged["records"] if r["revision"]["revision_id"] in admitted)
        record["revision"]["admissions"][0]["authority_identity"] = "forged"
        with self.assertRaisesRegex(AdmissionError, "digest mismatch"):
            load_trusted_history(forged, trusted_history_hash=anchor)
        with self.assertRaisesRegex(AdmissionError, "revision hash"):
            load_trusted_history(forged, trusted_history_hash=history_digest(forged))


if __name__ == "__main__":
    unittest.main()
