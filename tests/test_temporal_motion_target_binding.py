from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from svm import (
    AdapterRequest,
    GeneratorProvenance,
    PromotedTemporalCorrespondence,
    PromoteTemporalIdentityChange,
    Proposal,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
    SetGroupTransformChange,
    Transaction,
)
from svm.adapters import (
    TemporalMotionTargetBindingAdapter,
    TemporalMotionTargetBindingError,
)
from svm.evaluator import DocumentError

ROOT = Path(__file__).resolve().parents[1]
GROUP_A = "group:" + "1" * 64
GROUP_B = "group:" + "4" * 64
IDENTITY_A = "temporal-identity:" + "5" * 64
IDENTITY_B = "temporal-identity:" + "6" * 64


def identity(identity_id: str, suffix: str) -> dict:
    return {
        "id": identity_id,
        "bindings": [
            {"tick": 0, "observation_id": f"observation:{suffix}-a"},
            {"tick": 1, "observation_id": f"observation:{suffix}-b"},
        ],
        "provenance": [
            {
                "candidate_id": "candidate:correspondence:" + suffix * 64,
                "inference_id": "inference:correspondence:" + suffix * 64,
                "evidence_artifact_id": "artifact:" + "0" * 64,
                "evidence_policy_identity": "svm-bounds-correspondence-policy@0.1",
                "promotion_policy_identity": "svm-explicit-temporal-identity-promotion@0.1",
            }
        ],
    }


class TemporalMotionTargetBindingGoldenS1Test(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "022-group-transform.svm.json").read_text(encoding="utf-8")
        )
        document["temporal_identities"] = [identity(IDENTITY_A, "a"), identity(IDENTITY_B, "b")]
        second_group = copy.deepcopy(document["groups"][0])
        second_group["id"] = GROUP_B
        second_group["provenance"]["candidate_id"] = "candidate:group:" + "7" * 64
        second_group["provenance"]["inference_id"] = "inference:group:" + "8" * 64
        document["entities"].extend(
            [
                {"id": "entity:target-b-left", "name": "Target B Left"},
                {"id": "entity:target-b-right", "name": "Target B Right"},
            ]
        )
        second_group["members"] = ["entity:target-b-left", "entity:target-b-right"]
        document["groups"].append(second_group)
        self.store = RevisionStore.create(document)

    def propose(self, identity_id: str = IDENTITY_A, group_id: str = GROUP_A):
        return TemporalMotionTargetBindingAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                options={"temporal_identity_id": identity_id, "group_id": group_id},
            ),
            None,
        )

    def test_binding_succeeds_and_changes_only_binding_state(self) -> None:
        before = self.store.get_document(self.store.head)
        proposal = self.propose()
        after = self.store.get_document(ProposalAcceptor().accept(self.store, proposal).revision_id)
        for field in (
            "entities",
            "groups",
            "temporal_identities",
            "construction",
            "presentation",
            "structural_relations",
            "animation",
            "references",
        ):
            self.assertEqual(after.get(field), before.get(field))
        self.assertEqual(len(after["motion_target_bindings"]), 1)
        self.assertEqual(after["animation"]["content"], [])
        self.assertNotIn("keyframes", after["motion_target_bindings"][0])

    def test_same_binding_is_idempotent_without_duplicate(self) -> None:
        ProposalAcceptor().accept(self.store, self.propose())
        ProposalAcceptor().accept(self.store, self.propose())
        self.assertEqual(len(self.store.get_document(self.store.head)["motion_target_bindings"]), 1)

    def test_identity_and_group_conflicts_are_atomic(self) -> None:
        ProposalAcceptor().accept(self.store, self.propose())
        before = self.store.get_document(self.store.head)
        for proposal in (self.propose(IDENTITY_A, GROUP_B), self.propose(IDENTITY_B, GROUP_A)):
            with self.assertRaisesRegex(DocumentError, "MOTION_TARGET_CONFLICT"):
                ProposalAcceptor().accept(self.store, proposal)
            self.assertEqual(self.store.get_document(self.store.head), before)

    def test_missing_endpoints_and_missing_transform_are_rejected(self) -> None:
        with self.assertRaisesRegex(TemporalMotionTargetBindingError, "temporal identity"):
            self.propose("temporal-identity:" + "9" * 64)
        with self.assertRaisesRegex(TemporalMotionTargetBindingError, "one Group"):
            self.propose(group_id="group:" + "9" * 64)
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            options={"temporal_identity_id": IDENTITY_A, "group_id": GROUP_A},
        )
        del request.document["groups"][0]["transform"]
        with self.assertRaisesRegex(TemporalMotionTargetBindingError, "static transform"):
            TemporalMotionTargetBindingAdapter().propose(request, None)

    def test_stale_identity_group_and_source_revision_are_rejected(self) -> None:
        for field, message in (
            ("temporal_identity", "STALE_TEMPORAL_IDENTITY"),
            ("group", "STALE_GROUP"),
        ):
            proposal = self.propose()
            change = proposal.transaction.changes[0]
            snapshot = copy.deepcopy(getattr(change, field))
            snapshot["stale"] = True
            object.__setattr__(change, field, snapshot)
            with self.assertRaisesRegex(DocumentError, message):
                ProposalAcceptor().accept(self.store, proposal)
        proposal = self.propose()
        object.__setattr__(
            proposal.transaction.changes[0], "source_revision_id", "revision:" + "f" * 64
        )
        with self.assertRaisesRegex(ProposalArtifactError, "Proposal base revision"):
            ProposalAcceptor().accept(self.store, proposal)

    def test_binding_survives_later_temporal_identity_extension(self) -> None:
        proposal = self.propose()
        ProposalAcceptor().accept(self.store, proposal)
        binding_before = copy.deepcopy(
            self.store.get_document(self.store.head)["motion_target_bindings"][0]
        )
        extension = PromotedTemporalCorrespondence(
            evidence_artifact_id="artifact:" + "0" * 64,
            candidate_id="candidate:correspondence:" + "c" * 64,
            inference_id="inference:correspondence:" + "c" * 64,
            source_tick=1,
            source_observation_id="observation:a-b",
            target_tick=2,
            target_observation_id="observation:a-c",
            evidence_policy_identity="svm-bounds-correspondence-policy@0.1",
            stable_identity_id=IDENTITY_A,
        )
        reference = next(
            item
            for item in self.store.get_document(self.store.head)["references"]
            if item["id"] == extension.evidence_artifact_id
        )
        revision = self.store.commit(
            self.store.head,
            Transaction(
                "transaction:extend-temporal-identity",
                (PromoteTemporalIdentityChange((extension,), (reference,)),),
            ),
        )
        after = self.store.get_document(revision.revision_id)
        self.assertEqual(len(after["temporal_identities"][0]["bindings"]), 3)
        self.assertEqual(after["motion_target_bindings"][0], binding_before)
        self.assertEqual(after["motion_target_bindings"][0]["id"], binding_before["id"])

    def test_binding_survives_later_group_transform_edit(self) -> None:
        ProposalAcceptor().accept(self.store, self.propose())
        binding_before = copy.deepcopy(
            self.store.get_document(self.store.head)["motion_target_bindings"][0]
        )
        transform = {
            "translate": [12, -4],
            "rotation_degrees": 3,
            "scale": 1.25,
            "origin": [0, 0],
        }
        edit = Proposal(
            "proposal:edit-bound-group",
            self.store.head,
            GeneratorProvenance("editor:group-transform", "0.1", "svm-core", "0.1"),
            Transaction(
                "transaction:edit-bound-group",
                (SetGroupTransformChange(GROUP_A, transform),),
            ),
        )
        revision = ProposalAcceptor().accept(self.store, edit)
        after = self.store.get_document(revision.revision_id)
        self.assertEqual(after["groups"][0]["transform"], transform)
        self.assertEqual(after["motion_target_bindings"][0], binding_before)
        self.assertEqual(after["motion_target_bindings"][0]["id"], binding_before["id"])

    def test_original_change_rejects_identity_or_group_drift_at_apply_time(self) -> None:
        for endpoint, message in (
            ("temporal_identity", "STALE_TEMPORAL_IDENTITY"),
            ("group", "STALE_GROUP"),
        ):
            proposal = self.propose()
            evolved = self.store.get_document(self.store.head)
            collection = "temporal_identities" if endpoint == "temporal_identity" else "groups"
            evolved[collection][0]["post_proposal_change"] = True
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(DocumentError, message):
                proposal.transaction.apply(evolved)


if __name__ == "__main__":
    unittest.main()
