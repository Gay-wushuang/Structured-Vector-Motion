from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalPolicyError,
    RevisionStore,
)
from svm.adapters import (
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalIdentityPromotionError,
)
from svm.adapters.temporal_correspondence import OBSERVATION_MEDIA_TYPE
from svm.evaluator import canonical_bytes
from svm.revisions import TEMPORAL_IDENTITY_PROMOTION_IDENTITY

ROOT = Path(__file__).resolve().parents[1]


def primitive(
    observation_id: str,
    bounds: list[int],
    fill: str = "#FF0000",
    primitive_type: str = "ellipse",
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "primitive_type": primitive_type,
        "bounds": bounds,
        "fill": fill,
    }


class TemporalIdentityPromotionGoldenR1Test(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()

    def accept_evidence(
        self,
        source_tick: int,
        source: list[dict[str, Any]],
        target_tick: int,
        target: list[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        observations = {
            "schema_version": "svm-primitive-observations-0.1",
            "canvas": [100, 100],
            "frames": [
                {"tick": source_tick, "primitives": source},
                {"tick": target_tick, "primitives": target},
            ],
        }
        source_artifact = self.artifacts.import_bytes(
            canonical_bytes(observations),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "fixture:primitive-provider@0.1"},
        )
        assert self.store.head is not None
        proposal = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(source_artifact.artifact_id,),
            ),
            self.artifacts,
        )
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        evidence_id = proposal.preview_artifacts[0].artifact_id
        payload = json.loads(self.artifacts.get(evidence_id).content)
        self.assertEqual(self.store.head, revision.revision_id)
        return evidence_id, payload

    def promote(self, evidence_id: str, inference_id: str):
        assert self.store.head is not None
        proposal = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(evidence_id,),
                options={"inference_ids": [inference_id]},
            ),
            self.artifacts,
        )
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        return proposal, revision, self.store.get_document(revision.revision_id)

    def supported_pair(
        self, source_tick: int, source_id: str, target_tick: int, target_id: str
    ) -> tuple[str, dict[str, Any]]:
        evidence_id, payload = self.accept_evidence(
            source_tick,
            [primitive(source_id, [10, 10, 20, 20])],
            target_tick,
            [primitive(target_id, [12, 11, 22, 21], "#F80000")],
        )
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        return evidence_id, candidate

    def test_unbound_pair_creates_one_stable_identity_with_exact_provenance(self) -> None:
        evidence_id, candidate = self.supported_pair(
            0, "observation:eye-0000", 1, "observation:eye-0001"
        )
        evidence_before = self.artifacts.get(evidence_id).content
        before = self.store.get_document(self.store.head)
        proposal, _revision, after = self.promote(evidence_id, candidate["inference_id"])

        self.assertEqual(len(after["temporal_identities"]), 1)
        identity = after["temporal_identities"][0]
        self.assertEqual(
            identity["bindings"],
            [
                {"tick": 0, "observation_id": "observation:eye-0000"},
                {"tick": 1, "observation_id": "observation:eye-0001"},
            ],
        )
        self.assertEqual(
            identity["provenance"],
            [
                {
                    "candidate_id": candidate["candidate_id"],
                    "inference_id": candidate["inference_id"],
                    "evidence_artifact_id": evidence_id,
                    "evidence_policy_identity": candidate["policy_identity"],
                    "promotion_policy_identity": TEMPORAL_IDENTITY_PROMOTION_IDENTITY,
                }
            ],
        )
        self.assertEqual(proposal.preview.temporal_identities[0].stable_identity_id, identity["id"])
        for field in ("entities", "construction", "presentation", "animation"):
            self.assertEqual(after[field], before[field])
        self.assertEqual(self.artifacts.get(evidence_id).content, evidence_before)

    def test_target_inherits_existing_source_identity(self) -> None:
        first_evidence, first = self.supported_pair(
            0, "observation:eye-0000", 1, "observation:eye-0001"
        )
        _proposal, _revision, first_document = self.promote(first_evidence, first["inference_id"])
        stable_id = first_document["temporal_identities"][0]["id"]

        second_evidence, second = self.supported_pair(
            1, "observation:eye-0001", 2, "observation:eye-0002"
        )
        _proposal, _revision, after = self.promote(second_evidence, second["inference_id"])
        self.assertEqual(len(after["temporal_identities"]), 1)
        self.assertEqual(after["temporal_identities"][0]["id"], stable_id)
        self.assertEqual(len(after["temporal_identities"][0]["bindings"]), 3)
        self.assertEqual(len(after["temporal_identities"][0]["provenance"]), 2)

    def test_same_identity_promotion_is_idempotent(self) -> None:
        evidence_id, candidate = self.supported_pair(
            0, "observation:eye-0000", 1, "observation:eye-0001"
        )
        self.promote(evidence_id, candidate["inference_id"])
        before = self.store.get_document(self.store.head)
        _proposal, _revision, after = self.promote(evidence_id, candidate["inference_id"])
        self.assertEqual(after["temporal_identities"], before["temporal_identities"])
        self.assertEqual(len(after["temporal_identities"]), 1)

    def test_different_existing_identities_conflict_atomically(self) -> None:
        first_evidence, first = self.supported_pair(0, "observation:a", 1, "observation:b")
        self.promote(first_evidence, first["inference_id"])
        second_evidence, second = self.supported_pair(2, "observation:c", 3, "observation:d")
        self.promote(second_evidence, second["inference_id"])
        bridge_evidence, bridge = self.supported_pair(1, "observation:b", 2, "observation:c")
        before = self.store.get_document(self.store.head)
        revision_count = len(self.store.revisions)
        assert self.store.head is not None
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(bridge_evidence,),
            options={"inference_ids": [bridge["inference_id"]]},
        )
        with self.assertRaisesRegex(TemporalIdentityPromotionError, "TEMPORAL_IDENTITY_CONFLICT"):
            TemporalIdentityPromotionAdapter().propose(request, self.artifacts)
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(len(self.store.revisions), revision_count)

    def test_uncertain_and_rejected_cannot_be_promoted(self) -> None:
        evidence_id, payload = self.accept_evidence(
            0,
            [
                primitive("observation:mark", [40, 40, 50, 50], "#00FF00", "rectangle"),
                primitive("observation:eye", [10, 10, 20, 20]),
            ],
            1,
            [
                primitive("observation:mark-a", [39, 40, 49, 50], "#00FF00", "rectangle"),
                primitive("observation:mark-b", [41, 40, 51, 50], "#00FF00", "rectangle"),
                primitive("observation:far", [80, 80, 90, 90], "#00FF00", "rectangle"),
            ],
        )
        for status in ("UNCERTAIN", "REJECTED"):
            candidate = next(item for item in payload["candidates"] if item["status"] == status)
            assert self.store.head is not None
            request = AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(evidence_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            )
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(TemporalIdentityPromotionError, "Only a SUPPORTED"),
            ):
                TemporalIdentityPromotionAdapter().propose(request, self.artifacts)

    def test_forged_change_cannot_bypass_exact_evidence(self) -> None:
        evidence_id, candidate = self.supported_pair(
            0, "observation:eye-0000", 1, "observation:eye-0001"
        )
        assert self.store.head is not None
        proposal = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(evidence_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        forged = copy.deepcopy(proposal)
        promoted = forged.transaction.changes[0].correspondences[0]
        object.__setattr__(promoted, "target_observation_id", "observation:forged")
        with self.assertRaisesRegex(ProposalArtifactError, "does not match R0 evidence"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_promotion_uses_registered_document_permission(self) -> None:
        base = self.store.get_document(self.store.head)
        base["edit_permissions"] = [
            {
                "id": "permission:no-temporal-promotion",
                "actor": "adapter:temporal-identity-promotion",
                "effect": "deny",
                "actions": ["promote_temporal_identity"],
                "targets": ["document"],
            }
        ]
        self.store = RevisionStore.create(base)
        evidence_id, candidate = self.supported_pair(
            0, "observation:eye-0000", 1, "observation:eye-0001"
        )
        assert self.store.head is not None
        proposal = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(evidence_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        with self.assertRaisesRegex(ProposalPolicyError, "denies"):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)


if __name__ == "__main__":
    unittest.main()
