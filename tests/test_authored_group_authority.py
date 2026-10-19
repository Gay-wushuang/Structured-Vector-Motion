"""Spec82 G2 authority, policy, and atomicity through the real Acceptor."""

from __future__ import annotations

import copy
import unittest
from dataclasses import fields, replace

from authored_group_test_support import (
    NEUTRAL_TRANSFORM,
    make_accepted_base,
    make_change,
    make_proposal,
)

from svm import ProposalAcceptor, RevisionStore
from svm.artifacts import ArtifactKind
from svm.change_authority import change_authority, resolve_transaction_intents
from svm.document import DocumentDialect, validate_document
from svm.evaluator import DocumentError
from svm.proposals import ProposalArtifactError, ProposalPolicyError
from svm.revisions import (
    AppendReferencesChange,
    AppendSceneFragmentChange,
    AssembleAuthoredGroupChange,
    SetGroupTransformChange,
)

ACTOR = "adapter:authored-group-assembly"


class AuthoredGroupAuthorityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Every member starts with genuine analysis/promotion acceptance. Policy
        # tests below explicitly create trusted roots with those same records;
        # they do not claim to reproduce historical policy editing.
        cls.fixture = make_accepted_base()

    def setUp(self):
        self.store, self.artifacts = copy.deepcopy(self.fixture)

    def with_permission(self, action, targets, *, actor="*"):
        document = self.store.get_document(self.store.head)
        document["edit_permissions"] = [
            {
                "id": "permission:authored-authority-test",
                "actor": actor,
                "effect": "deny",
                "actions": [action],
                "targets": list(targets),
            }
        ]
        self.store = RevisionStore.create(
            document,
            "Trusted policy-test root with accepted Entity content",
            dialect=DocumentDialect.AUTHORED_GROUP_ASSEMBLY,
        )

    def assert_rejected_unchanged(self, proposal, error, *, artifacts=None):
        before = copy.deepcopy(self.store)
        with self.assertRaises(error):
            ProposalAcceptor().accept(self.store, proposal, artifacts)
        self.assertEqual(self.store, before)

    def accept(self, changes, *, artifacts=None):
        proposal = make_proposal(self.store, changes)
        revision = ProposalAcceptor().accept(self.store, proposal, artifacts)
        return self.store.get_document(revision.revision_id)

    def test_exact_registration_and_conditional_effects(self):
        for transform in (None, NEUTRAL_TRANSFORM):
            with self.subTest(transform=transform):
                change = make_change(self.store, transform=transform)
                authority = change_authority(change)
                self.assertIsNotNone(authority)
                self.assertIs(authority.change_type, AssembleAuthoredGroupChange)
                self.assertEqual(
                    authority.actions, frozenset({"establish_group", "set_group_transform"})
                )
                self.assertIsNotNone(authority.artifact_verifier)
                self.assertIsNotNone(authority.source_revision_resolver)
                self.assertEqual(authority.source_revision_resolver(change), self.store.head)
                expected = (("establish_group", "document", None),)
                if transform is not None:
                    expected += (("set_group_transform", change.group["id"], "transform"),)
                self.assertEqual(
                    resolve_transaction_intents(make_proposal(self.store, (change,)).transaction),
                    expected,
                )

    def test_document_and_wildcard_establish_denials_are_atomic(self):
        for target in ("document", "*"):
            for actor in ("*", ACTOR):
                with self.subTest(target=target, actor=actor):
                    self.store, self.artifacts = copy.deepcopy(self.fixture)
                    self.with_permission("establish_group", (target,), actor=actor)
                    change = make_change(self.store)
                    self.assert_rejected_unchanged(
                        make_proposal(self.store, (change,)), ProposalPolicyError
                    )

    def test_transform_denial_matches_explicit_neutral_and_non_neutral(self):
        non_neutral = {**NEUTRAL_TRANSFORM, "translate": [3, -2], "scale": 2}
        for transform in (NEUTRAL_TRANSFORM, non_neutral):
            with self.subTest(transform=transform):
                self.store, self.artifacts = copy.deepcopy(self.fixture)
                self.with_permission("set_group_transform", ("*",))
                change = make_change(self.store, transform=transform)
                self.assert_rejected_unchanged(
                    make_proposal(self.store, (change,)), ProposalPolicyError
                )

    def test_null_transform_is_not_denied_as_a_transform_edit(self):
        self.with_permission("set_group_transform", ("*",))
        change = make_change(self.store, transform=None)
        accepted = self.accept((change,))
        self.assertEqual(accepted["groups"], [change.group])
        self.assertNotIn("transform", accepted["groups"][0])

    def test_document_transform_target_is_not_a_wildcard(self):
        self.with_permission("set_group_transform", ("document",))
        change = make_change(self.store, transform=NEUTRAL_TRANSFORM)
        accepted = self.accept((change,))
        self.assertEqual(accepted["groups"], [change.group])

    def test_new_group_is_not_a_valid_base_permission_target(self):
        change = make_change(self.store, transform=NEUTRAL_TRANSFORM)
        document = self.store.get_document(self.store.head)
        document["edit_permissions"] = [
            {
                "id": "permission:not-yet-existing-group",
                "actor": "*",
                "effect": "deny",
                "actions": ["set_group_transform"],
                "targets": [change.group["id"]],
            }
        ]
        with self.assertRaises(DocumentError):
            validate_document(document, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)

    def test_other_actor_and_unrelated_actions_do_not_deny_assembly(self):
        permissions = (
            ("establish_group", "adapter:other-author"),
            ("import_scene", "*"),
            ("promote_group", "*"),
            ("attach_analysis", "*"),
            ("bind_motion_target", "*"),
        )
        for action, actor in permissions:
            with self.subTest(action=action, actor=actor):
                self.store, self.artifacts = copy.deepcopy(self.fixture)
                self.with_permission(action, ("*",), actor=actor)
                change = make_change(self.store, transform=NEUTRAL_TRANSFORM)
                self.assertEqual(self.accept((change,))["groups"], [change.group])

    def test_zero_artifact_preview_and_accept_still_run_the_verifier(self):
        change = make_change(self.store)
        proposal = make_proposal(self.store, (change,))
        self.assertEqual(change.references, ())
        self.assertEqual(proposal.required_artifact_ids, ())
        self.assertEqual(proposal.preview_artifacts, ())
        before = copy.deepcopy(self.store)
        preview = ProposalAcceptor().validate(self.store, proposal)
        self.assertEqual(self.store, before)
        wrong = replace(change, base_revision=replace(change.base_revision, message="forged"))
        self.assert_rejected_unchanged(make_proposal(self.store, (wrong,)), ProposalArtifactError)
        revision = ProposalAcceptor().accept(self.store, proposal)
        self.assertEqual(self.store.get_document(revision.revision_id), preview)
        self.assertEqual(len(self.store.revisions), len(before.revisions) + 1)
        self.assertEqual(getattr(revision, "admissions", ()), ())

    def test_required_artifact_injection_cannot_expand_standalone_authority(self):
        change = make_change(self.store)
        proposal = make_proposal(self.store, (change,))
        reference = self.store.get_document(self.store.head)["references"][0]
        forged = replace(proposal, required_artifact_ids=(reference["id"],))
        self.assert_rejected_unchanged(forged, ProposalArtifactError, artifacts=self.artifacts)

    def test_false_null_transform_cannot_hide_a_transform_intent(self):
        self.with_permission("set_group_transform", ("*",))
        change = make_change(self.store, transform=NEUTRAL_TRANSFORM)
        forged = replace(change, initial_transform=None)
        self.assert_rejected_unchanged(make_proposal(self.store, (forged,)), ProposalArtifactError)

    def test_forged_group_target_cannot_redirect_policy_effects(self):
        self.with_permission("set_group_transform", ("*",))
        change = make_change(self.store, transform=NEUTRAL_TRANSFORM)
        forged_group = {**change.group, "id": "group:" + "f" * 64}
        self.assert_rejected_unchanged(
            make_proposal(self.store, (replace(change, group=forged_group),)),
            ProposalArtifactError,
        )

    def test_no_op_predecessor_is_not_blanket_rejected(self):
        change = make_change(self.store)
        # A real, already-accepted Reference is a genuine no-op predecessor:
        # AppendReferencesChange only appends ids it does not already know, so
        # this exercises the no-op case without relaxing the frozen Change's
        # "at least one Artifact reference" contract.
        before = self.store.get_document(self.store.head)
        existing = copy.deepcopy(before["references"][0])
        accepted = self.accept(
            (AppendReferencesChange((existing,)), change), artifacts=self.artifacts
        )
        self.assertEqual(accepted["groups"], [change.group])
        # The no-op predecessor appended nothing and left Entity content untouched.
        self.assertEqual(accepted["references"], before["references"])
        self.assertEqual(accepted["entities"], before["entities"])

    def test_nonempty_sibling_artifact_map_grants_no_assembly_authority(self):
        change = make_change(self.store)
        reference = self.artifacts.import_bytes(
            b'{"authored-test":"independently attached reference"}',
            media_type="application/json",
            kind=ArtifactKind.DERIVED,
        ).document_reference()
        before = self.store.get_document(self.store.head)
        accepted = self.accept(
            (change, AppendReferencesChange((reference,))), artifacts=self.artifacts
        )
        self.assertEqual(accepted["groups"], [change.group])
        self.assertEqual(accepted["references"], [*before["references"], reference])
        self.assertEqual(accepted["entities"], before["entities"])

    def test_separately_authorized_successor_can_transform_new_group(self):
        change = make_change(self.store)
        successor = SetGroupTransformChange(change.group["id"], NEUTRAL_TRANSFORM)
        accepted = self.accept((change, successor))
        self.assertEqual(accepted["groups"], [{**change.group, "transform": NEUTRAL_TRANSFORM}])

    def test_successor_transform_policy_denial_rolls_back_assembly(self):
        self.with_permission("set_group_transform", ("*",))
        change = make_change(self.store)
        successor = SetGroupTransformChange(change.group["id"], NEUTRAL_TRANSFORM)
        self.assert_rejected_unchanged(
            make_proposal(self.store, (change, successor)), ProposalPolicyError
        )

    @staticmethod
    def append_entity(entity):
        return AppendSceneFragmentChange((entity,), (), (), (), ())

    def test_preceding_entity_creation_cannot_replace_the_authenticated_base(self):
        change = make_change(self.store)
        predecessor = self.append_entity({"id": "entity:temporary", "name": "Temporary"})
        self.assert_rejected_unchanged(
            make_proposal(self.store, (predecessor, change)), DocumentError
        )

    def test_temporary_member_in_caller_snapshot_is_not_an_accepted_base_member(self):
        temporary = {"id": "entity:temporary", "name": "Temporary"}
        caller_store = copy.deepcopy(self.store)
        caller_store._documents[caller_store.head]["entities"].append(temporary)
        original_member = self.store.get_document(self.store.head)["entities"][0]["id"]
        forged = make_change(caller_store, members=sorted((original_member, temporary["id"])))
        self.assert_rejected_unchanged(
            make_proposal(self.store, (self.append_entity(temporary), forged)),
            ProposalArtifactError,
        )

    def test_failing_successor_leaves_no_group_or_revision(self):
        change = make_change(self.store)
        failure = SetGroupTransformChange("group:" + "f" * 64, NEUTRAL_TRANSFORM)
        self.assert_rejected_unchanged(make_proposal(self.store, (change, failure)), DocumentError)

    def test_final_validation_failure_rolls_back_assembly_and_sibling(self):
        change = make_change(self.store)
        duplicate = copy.deepcopy(self.store.get_document(self.store.head)["entities"][0])
        self.assert_rejected_unchanged(
            make_proposal(self.store, (change, self.append_entity(duplicate))), DocumentError
        )

    def test_subclass_cannot_inherit_registered_mutation_authority(self):
        executed = []

        class MaliciousSubclass(AssembleAuthoredGroupChange):
            def apply(self, document):
                executed.append(True)
                document["entities"].clear()

        original = make_change(self.store)
        malicious = MaliciousSubclass(
            **{field.name: getattr(original, field.name) for field in fields(original)}
        )
        self.assertIsNone(change_authority(malicious))
        self.assert_rejected_unchanged(make_proposal(self.store, (malicious,)), ProposalPolicyError)
        self.assertEqual(executed, [])

    def test_duck_typed_change_cannot_claim_authored_authority(self):
        executed = []

        class Unregistered:
            references = ()

            def apply(self, document):
                executed.append(True)
                document["entities"].clear()

        self.assert_rejected_unchanged(
            make_proposal(self.store, (Unregistered(),)), ProposalPolicyError
        )
        self.assertEqual(executed, [])

    def test_authored_change_cannot_claim_construction_identity(self):
        change = replace(
            make_change(self.store), authority_identity="svm-construction-derived-group@0.1"
        )
        self.assert_rejected_unchanged(make_proposal(self.store, (change,)), ProposalArtifactError)


if __name__ == "__main__":
    unittest.main()
