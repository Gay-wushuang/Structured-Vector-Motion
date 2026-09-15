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
    RevisionStore,
)
from svm.adapters import (
    ObservedTranslationMotionAdapter,
    ObservedTranslationMotionError,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
)
from svm.adapters.temporal_correspondence import OBSERVATION_MEDIA_TYPE
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]


def primitive(observation_id: str, bounds: list[int]) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "primitive_type": "ellipse",
        "bounds": bounds,
        "fill": "#FF0000",
    }


class ObservedTranslationMotionGoldenS0Test(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()

    def correspondence(
        self,
        source_tick: int,
        source_id: str,
        source_bounds: list[int],
        target_tick: int,
        target_id: str,
        target_bounds: list[int],
    ):
        payload = {
            "schema_version": "svm-primitive-observations-0.1",
            "canvas": [200, 200],
            "frames": [
                {"tick": source_tick, "primitives": [primitive(source_id, source_bounds)]},
                {"tick": target_tick, "primitives": [primitive(target_id, target_bounds)]},
            ],
        }
        source = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "fixture@0.1"},
        )
        proposal = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store, self.store.head, ("document",), artifact_ids=(source.artifact_id,)
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        evidence_id = proposal.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(evidence_id).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        return evidence_id, candidate

    def promote(self, evidence_id: str, inference_id: str) -> str:
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
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        return proposal.preview.temporal_identities[0].stable_identity_id

    def propose_motion(self, identity_id: str, evidence_ids: list[str], inference_ids: list[str]):
        return ObservedTranslationMotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=tuple(evidence_ids),
                options={"temporal_identity_id": identity_id, "inference_ids": inference_ids},
            ),
            self.artifacts,
        )

    def test_two_frame_displacement_is_exact_and_accept_is_evidence_only(self) -> None:
        evidence, candidate = self.correspondence(
            0, "observation:a", [10, 10, 20, 20], 1, "observation:b", [30, 15, 40, 25]
        )
        identity_id = self.promote(evidence, candidate["inference_id"])
        before = self.store.get_document(self.store.head)
        proposal = self.propose_motion(identity_id, [evidence], [candidate["inference_id"]])
        payload = json.loads(self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content)
        self.assertEqual(payload["intervals"][0]["translation"], {"dx": 20.0, "dy": 5.0})
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        after = self.store.get_document(revision.revision_id)
        for field in (
            "entities",
            "groups",
            "temporal_identities",
            "construction",
            "presentation",
            "animation",
        ):
            self.assertEqual(after.get(field), before.get(field))
        self.assertEqual(len(after["references"]), len(before["references"]) + 1)
        self.assertEqual(after["animation"]["content"], [])

    def test_three_frame_chain_yields_two_ordered_intervals(self) -> None:
        first_evidence, first = self.correspondence(
            0, "observation:a", [10, 10, 20, 20], 1, "observation:b", [30, 15, 40, 25]
        )
        identity_id = self.promote(first_evidence, first["inference_id"])
        second_evidence, second = self.correspondence(
            1, "observation:b", [30, 15, 40, 25], 2, "observation:c", [35, 12, 45, 22]
        )
        self.promote(second_evidence, second["inference_id"])
        proposal = self.propose_motion(
            identity_id,
            [second_evidence, first_evidence],
            [second["inference_id"], first["inference_id"]],
        )
        intervals = json.loads(
            self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content
        )["intervals"]
        self.assertEqual(
            [(item["source_tick"], item["target_tick"]) for item in intervals], [(0, 1), (1, 2)]
        )
        self.assertEqual(
            [item["translation"] for item in intervals],
            [{"dx": 20.0, "dy": 5.0}, {"dx": 5.0, "dy": -3.0}],
        )

    def test_unpromoted_or_other_identity_inference_is_rejected(self) -> None:
        evidence, candidate = self.correspondence(
            0, "observation:a", [10, 10, 20, 20], 1, "observation:b", [12, 10, 22, 20]
        )
        with self.assertRaisesRegex(ObservedTranslationMotionError, "existing temporal identity"):
            self.propose_motion(
                "temporal-identity:" + "0" * 64, [evidence], [candidate["inference_id"]]
            )
        identity_id = self.promote(evidence, candidate["inference_id"])
        other_evidence, other = self.correspondence(
            2, "observation:c", [40, 40, 50, 50], 3, "observation:d", [42, 40, 52, 50]
        )
        other_identity_id = self.promote(other_evidence, other["inference_id"])
        self.assertNotEqual(identity_id, other_identity_id)
        with self.assertRaisesRegex(ObservedTranslationMotionError, "not promoted into this"):
            self.propose_motion(identity_id, [other_evidence], [other["inference_id"]])

    def test_forged_displacement_is_rejected_by_acceptor(self) -> None:
        evidence, candidate = self.correspondence(
            0, "observation:a", [10, 10, 20, 20], 1, "observation:b", [30, 15, 40, 25]
        )
        identity_id = self.promote(evidence, candidate["inference_id"])
        proposal = self.propose_motion(identity_id, [evidence], [candidate["inference_id"]])
        original = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        payload = json.loads(original.content)
        payload["intervals"][0]["translation"]["dx"] = 999
        forged_artifact = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=ArtifactKind.DERIVED,
            provenance=original.provenance,
        )
        forged = copy.deepcopy(proposal)
        change = forged.transaction.changes[0]
        object.__setattr__(change, "evidence_reference", forged_artifact.document_reference())
        object.__setattr__(forged, "required_artifact_ids", (forged_artifact.artifact_id, evidence))
        with self.assertRaisesRegex(ProposalArtifactError, "does not match R0 displacement"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_forged_source_revision_and_matching_artifact_are_rejected(self) -> None:
        evidence, candidate = self.correspondence(
            0, "observation:a", [10, 10, 20, 20], 1, "observation:b", [30, 15, 40, 25]
        )
        identity_id = self.promote(evidence, candidate["inference_id"])
        proposal = self.propose_motion(identity_id, [evidence], [candidate["inference_id"]])
        original = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        forged_revision = "revision:" + "f" * 64
        payload = json.loads(original.content)
        payload["source_revision_id"] = forged_revision
        forged_artifact = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=ArtifactKind.DERIVED,
            provenance=original.provenance,
        )
        forged = copy.deepcopy(proposal)
        change = forged.transaction.changes[0]
        object.__setattr__(change, "source_revision_id", forged_revision)
        object.__setattr__(change, "evidence_reference", forged_artifact.document_reference())
        object.__setattr__(forged, "required_artifact_ids", (forged_artifact.artifact_id, evidence))
        with self.assertRaisesRegex(ProposalArtifactError, "Proposal base revision"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_generation_is_content_deterministic(self) -> None:
        evidence, candidate = self.correspondence(
            0, "observation:a", [10, 10, 20, 20], 1, "observation:b", [30, 15, 40, 25]
        )
        identity_id = self.promote(evidence, candidate["inference_id"])
        left = self.propose_motion(identity_id, [evidence], [candidate["inference_id"]])
        right = self.propose_motion(identity_id, [evidence], [candidate["inference_id"]])
        self.assertEqual(left.preview_artifacts, right.preview_artifacts)
        self.assertEqual(left.transaction, right.transaction)


if __name__ == "__main__":
    unittest.main()
