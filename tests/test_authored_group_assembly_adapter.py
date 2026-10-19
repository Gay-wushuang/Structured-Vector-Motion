"""Spec82 G3 focused tests: the authored assembly Producer, not its verifier.

Every accepted input comes from the real promoted Entity fixture in
`authored_group_test_support`; no history is hand-written.
"""

from __future__ import annotations

import copy
import hashlib
import unittest
from dataclasses import replace

from authored_group_test_support import NEUTRAL_TRANSFORM, make_accepted_base

from svm import AdapterRequest, ProposalAcceptor, RevisionStore
from svm.adapters.authored_group_assembly import (
    AuthoredGroupAssemblyAdapter,
    AuthoredGroupAssemblyError,
    propose_from_store,
)
from svm.document import (
    AUTHORED_GROUP_AUTHORITY,
    AUTHORED_GROUP_TYPE,
    DocumentDialect,
    authored_group_identity,
)
from svm.evaluator import canonical_bytes
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.revisions import AssembleAuthoredGroupChange, Revision

CHANGE_IDENTITY = "svm.revisions.AssembleAuthoredGroupChange@0.1"
NON_NEUTRAL_TRANSFORM = {
    "translate": [3, -2],
    "rotation_degrees": 45,
    "scale": 2,
    "origin": [1, 4],
}


def _digest(change: AssembleAuthoredGroupChange) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "change_identity": CHANGE_IDENTITY,
                "source_revision_id": change.source_revision_id,
                "group": change.group,
            }
        )
    ).hexdigest()


class AuthoredGroupAssemblyAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Four genuinely promoted Entities from real upstream accepts.
        cls.fixture = make_accepted_base()

    def setUp(self):
        self.store, self.artifacts = copy.deepcopy(self.fixture)
        self.members = self.entities_of(self.store)[:2]

    @staticmethod
    def entities_of(store):
        return sorted(entity["id"] for entity in store.get_document(store.head)["entities"])

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def propose(self, *, members=None, transform=None):
        return propose_from_store(
            self.store,
            self.artifacts,
            members=self.members if members is None else members,
            transform=transform,
        )

    def test_real_base_two_members_accepts_one_group(self):
        base = self.store.head
        base_revision = self.store.revisions[base]
        before = self.store.get_document(base)

        proposal = self.propose()

        self.assertEqual(len(proposal.transaction.changes), 1)
        change = proposal.transaction.changes[0]
        self.assertIs(type(change), AssembleAuthoredGroupChange)
        self.assertEqual(change.references, ())
        self.assertEqual(proposal.required_artifact_ids, ())
        self.assertEqual(proposal.preview_artifacts, ())
        self.assertEqual(proposal.base_revision_id, base)
        self.assertEqual(change.base_revision, base_revision)
        self.assertEqual(
            proposal.proposal_id, f"proposal:authored-group-assembly:{_digest(change)}"
        )
        self.assertEqual(
            proposal.transaction.transaction_id,
            f"transaction:authored-group-assembly:{_digest(change)}",
        )

        revision = self.accept(proposal)
        document = self.store.get_document(revision.revision_id)
        self.assertEqual(len(document["groups"]), 1)
        group = document["groups"][0]
        self.assertEqual(group["members"], self.members)
        self.assertEqual(group["kind"], "explicit-group")
        self.assertNotIn("transform", group)
        self.assertEqual(group["provenance"]["type"], AUTHORED_GROUP_TYPE)
        self.assertEqual(group["provenance"]["authority_identity"], AUTHORED_GROUP_AUTHORITY)
        self.assertEqual(group["provenance"]["source_revision_id"], base)
        self.assertEqual(group["provenance"]["source_document_hash"], base_revision.document_hash)
        self.assertTrue(group["provenance"]["membership_hash"].startswith("sha256:"))
        self.assertEqual(group["id"], authored_group_identity(list(self.members))[0])
        # Nothing outside the appended groups array changed.
        self.assertEqual({k: v for k, v in document.items() if k != "groups"}, before)

    def test_two_disjoint_member_sets_accept_sequentially(self):
        first = self.entities_of(self.store)[:2]
        second = self.entities_of(self.store)[2:4]
        self.accept(self.propose(members=first))
        self.accept(self.propose(members=second))
        document = self.store.get_document(self.store.head)
        self.assertEqual(len(document["groups"]), 2)
        identifiers = {group["id"] for group in document["groups"]}
        self.assertEqual(len(identifiers), 2)
        self.assertIn(authored_group_identity(first)[0], identifiers)
        self.assertIn(authored_group_identity(second)[0], identifiers)

    def test_null_neutral_and_non_neutral_transform(self):
        for transform, has_field in (
            (None, False),
            (NEUTRAL_TRANSFORM, True),
            (NON_NEUTRAL_TRANSFORM, True),
        ):
            with self.subTest(transform=transform):
                self.store, self.artifacts = copy.deepcopy(self.fixture)
                self.members = self.entities_of(self.store)[:2]
                revision = self.accept(self.propose(transform=transform))
                group = self.store.get_document(revision.revision_id)["groups"][0]
                self.assertEqual("transform" in group, has_field)
                if has_field:
                    self.assertEqual(group["transform"], transform)

    def test_identical_inputs_are_deterministic(self):
        first_store, first_artifacts = copy.deepcopy(self.fixture)
        second_store, second_artifacts = copy.deepcopy(self.fixture)
        members = self.entities_of(first_store)[:2]
        first = propose_from_store(first_store, first_artifacts, members=members)
        second = propose_from_store(second_store, second_artifacts, members=members)
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(first.transaction, second.transaction)
        first_revision = ProposalAcceptor().accept(first_store, first, first_artifacts)
        second_revision = ProposalAcceptor().accept(second_store, second, second_artifacts)
        self.assertEqual(first_revision.revision_id, second_revision.revision_id)
        self.assertEqual(
            first_store.get_document(first_revision.revision_id),
            second_store.get_document(second_revision.revision_id),
        )

    def test_duplicate_missing_member_and_illegal_transform_reject(self):
        base = self.store.head
        before = self.store.get_document(base)
        with self.assertRaises(AuthoredGroupAssemblyError):
            self.propose(members=[self.members[0], self.members[0]])
        with self.assertRaises(AuthoredGroupAssemblyError):
            self.propose(members=[self.members[0], "entity:" + "f" * 64])
        with self.assertRaises(AuthoredGroupAssemblyError):
            self.propose(members=[self.members[0]])
        with self.assertRaises(AuthoredGroupAssemblyError):
            self.propose(
                transform={
                    "translate": [0, 0],
                    "rotation_degrees": 0,
                    "scale": 0,
                    "origin": [0, 0],
                }
            )
        with self.assertRaises(AuthoredGroupAssemblyError):
            self.propose(transform={"translate": [0, 0], "scale": 1, "origin": [0, 0]})
        self.assertEqual(self.store.head, base)
        self.assertEqual(self.store.get_document(base), before)

    def test_existing_group_id_collision_rejects(self):
        self.accept(self.propose())
        head = self.store.head
        before = self.store.get_document(head)
        revisions = set(self.store.revisions)
        with self.assertRaises(ProposalArtifactError):
            self.accept(self.propose())
        self.assertEqual(self.store.head, head)
        self.assertEqual(set(self.store.revisions), revisions)
        self.assertEqual(self.store.get_document(head), before)

    def test_stale_head_rejects_without_mutation(self):
        stale = self.propose(members=self.entities_of(self.store)[:2])
        self.accept(self.propose(members=self.entities_of(self.store)[2:4]))
        head = self.store.head
        before = self.store.get_document(head)
        revisions = set(self.store.revisions)
        with self.assertRaises(ProposalConflictError):
            self.accept(stale)
        self.assertEqual(self.store.head, head)
        self.assertEqual(set(self.store.revisions), revisions)
        self.assertEqual(self.store.get_document(head), before)

    def test_policy_deny_establish_group_is_atomic(self):
        document = self.store.get_document(self.store.head)
        document["edit_permissions"] = [
            {
                "id": "permission:deny-authored-establish",
                "actor": "*",
                "effect": "deny",
                "actions": ["establish_group"],
                "targets": ["document"],
            }
        ]
        denied = RevisionStore.create(
            document,
            "Denied authored assembly root",
            dialect=DocumentDialect.AUTHORED_GROUP_ASSEMBLY,
        )
        members = self.entities_of(denied)[:2]
        proposal = propose_from_store(denied, self.artifacts, members=members)
        head = denied.head
        revisions = set(denied.revisions)
        with self.assertRaises(ProposalPolicyError):
            ProposalAcceptor().accept(denied, proposal, self.artifacts)
        self.assertEqual(denied.head, head)
        self.assertEqual(set(denied.revisions), revisions)

    def test_forged_witness_and_mismatched_base_reject_before_acceptance(self):
        witness = copy.deepcopy(self.store.revisions[self.store.head])
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            options={"members": list(self.members), "transform": None},
        )
        adapter = AuthoredGroupAssemblyAdapter()
        with self.assertRaises(AuthoredGroupAssemblyError):
            adapter.propose(
                request, self.artifacts, base_revision=replace(witness, message="forged base")
            )
        with self.assertRaises(AuthoredGroupAssemblyError):
            adapter.propose(
                replace(request, base_revision_id="revision:" + "0" * 64),
                self.artifacts,
                base_revision=witness,
            )

    def test_assembly_creates_no_identity_binding_track_or_admission(self):
        base = self.store.head
        before = self.store.get_document(base)
        revision = self.accept(self.propose())
        document = self.store.get_document(revision.revision_id)
        self.assertEqual(len(document["groups"]), 1)
        self.assertEqual({k: v for k, v in document.items() if k != "groups"}, before)
        self.assertEqual(document["entities"], before["entities"])
        self.assertEqual(document["references"], before["references"])
        self.assertEqual(document.get("temporal_identities"), before.get("temporal_identities"))
        self.assertEqual(
            document.get("motion_target_bindings"), before.get("motion_target_bindings")
        )
        self.assertEqual(document["animation"]["content"], before["animation"]["content"])
        self.assertEqual(
            document["presentation"]["render_stack"],
            before["presentation"]["render_stack"],
        )
        published = self.store.revisions[revision.revision_id]
        self.assertIs(type(published), Revision)
        self.assertFalse(getattr(published, "admissions", ()))
