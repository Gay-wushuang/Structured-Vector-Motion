from __future__ import annotations

import copy
import json
import unittest

import tests.test_pop_group_candidates as qv1
from svm import (
    AdapterRequest,
    AppendReferencesChange,
    ArtifactKind,
    ProposalAcceptor,
    Transaction,
)
from svm.adapters import POPGroupCandidateAdapter, POPGroupPromotionAdapter, POPGroupPromotionError
from svm.evaluator import canonical_bytes


class POPGroupPromotionGoldenQv2Test(unittest.TestCase):
    def setUp(self) -> None:
        setup = qv1.POPGroupCandidatesGoldenQv1Test()
        setup.setUp()
        self.artifacts = setup.artifacts
        self.store = setup.store
        inference = POPGroupCandidateAdapter().propose(setup.request(), self.artifacts)
        self.inference_artifact_id = inference.preview_artifacts[0].artifact_id
        self.inference_revision = ProposalAcceptor().accept(self.store, inference, self.artifacts)
        payload = json.loads(self.artifacts.get(self.inference_artifact_id).content)
        self.by_status = {
            status: next(item for item in payload["candidates"] if item["status"] == status)
            for status in ("SUPPORTED", "UNCERTAIN", "REJECTED")
        }

    def request(
        self, candidate_id: str, *, document: dict[str, object] | None = None
    ) -> AdapterRequest:
        return AdapterRequest(
            base_revision_id=self.inference_revision.revision_id,
            document=copy.deepcopy(
                document or self.store.get_document(self.inference_revision.revision_id)
            ),
            scope=("document",),
            artifact_ids=(self.inference_artifact_id,),
            options={"candidate_ids": [candidate_id]},
        )

    def test_supported_candidate_promotes_atomically_without_scene_changes(self) -> None:
        candidate = self.by_status["SUPPORTED"]
        base = self.store.get_document(self.inference_revision.revision_id)
        proposal = POPGroupPromotionAdapter().propose(
            self.request(candidate["candidate_id"]), self.artifacts
        )
        dry_run = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, dry_run)
        self.assertEqual(len(accepted["groups"]), 1)
        group = accepted["groups"][0]
        self.assertEqual(group["kind"], "explicit-group")
        self.assertEqual(group["members"], candidate["members"])
        self.assertEqual(
            group["provenance"],
            {
                "candidate_id": candidate["candidate_id"],
                "inference_id": candidate["inference_id"],
                "inference_artifact_id": self.inference_artifact_id,
            },
        )
        for field in (
            "entities",
            "construction",
            "presentation",
            "structural_relations",
            "references",
        ):
            self.assertEqual(accepted.get(field), base.get(field))

    def test_uncertain_and_rejected_candidates_cannot_be_promoted(self) -> None:
        for status in ("UNCERTAIN", "REJECTED"):
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(POPGroupPromotionError, "SUPPORTED"),
            ):
                POPGroupPromotionAdapter().propose(
                    self.request(self.by_status[status]["candidate_id"]), self.artifacts
                )

    def test_source_drift_is_stale_even_when_members_still_exist(self) -> None:
        candidate = self.by_status["SUPPORTED"]
        drifted = self.store.get_document(self.inference_revision.revision_id)
        member = candidate["members"][0]
        style = next(item for item in drifted["presentation"]["styles"] if item["entity"] == member)
        style["fill"] = "#010203"
        with self.assertRaisesRegex(POPGroupPromotionError, "STALE_CANDIDATE"):
            POPGroupPromotionAdapter().propose(
                self.request(candidate["candidate_id"], document=drifted), self.artifacts
            )

        missing_member = self.store.get_document(self.inference_revision.revision_id)
        missing_member["entities"] = [
            item for item in missing_member["entities"] if item["id"] != member
        ]
        with self.assertRaisesRegex(POPGroupPromotionError, "STALE_CANDIDATE"):
            POPGroupPromotionAdapter().propose(
                self.request(candidate["candidate_id"], document=missing_member), self.artifacts
            )

    def test_promotion_requires_explicit_selection(self) -> None:
        request = self.request(self.by_status["SUPPORTED"]["candidate_id"])
        request.options.clear()
        with self.assertRaisesRegex(POPGroupPromotionError, "explicit"):
            POPGroupPromotionAdapter().propose(request, self.artifacts)

    def test_another_inference_reference_makes_the_first_candidate_stale(self) -> None:
        candidate = self.by_status["SUPPORTED"]
        first = self.artifacts.get(self.inference_artifact_id)
        second_payload = json.loads(first.content)
        second_payload["benchmark_variant"] = "independent-inference-b"
        second = self.artifacts.import_bytes(
            canonical_bytes(second_payload),
            media_type=first.media_type,
            kind=ArtifactKind.DERIVED,
            provenance={
                **first.provenance,
                "inference_variant": "b",
            },
        )
        second_revision = self.store.commit(
            self.inference_revision.revision_id,
            Transaction(
                transaction_id="transaction:test-accept-second-inference",
                changes=(AppendReferencesChange((second.document_reference(),)),),
                message="Accept a second independent inference Artifact",
            ),
        )
        request = AdapterRequest.from_store(
            self.store,
            second_revision.revision_id,
            ("document",),
            artifact_ids=(self.inference_artifact_id,),
            options={"candidate_ids": [candidate["candidate_id"]]},
        )
        with self.assertRaisesRegex(POPGroupPromotionError, "STALE_CANDIDATE"):
            POPGroupPromotionAdapter().propose(request, self.artifacts)


if __name__ == "__main__":
    unittest.main()
