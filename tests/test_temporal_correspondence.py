from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from svm import AdapterRequest, ArtifactKind, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters import TemporalCorrespondenceAdapter, TemporalCorrespondenceError
from svm.adapters.temporal_correspondence import (
    EVIDENCE_MEDIA_TYPE,
    OBSERVATION_MEDIA_TYPE,
    POLICY_IDENTITY,
)
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]


class TemporalCorrespondenceGoldenRv0Test(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()
        self.observations = {
            "schema_version": "svm-primitive-observations-0.1",
            "canvas": [100, 100],
            "frames": [
                {
                    "tick": 0,
                    "primitives": [
                        {
                            "observation_id": "observation:eye-0000",
                            "primitive_type": "ellipse",
                            "bounds": [10, 10, 20, 20],
                            "fill": "#FF0000",
                        },
                        {
                            "observation_id": "observation:mark-0000",
                            "primitive_type": "rectangle",
                            "bounds": [40, 40, 50, 50],
                            "fill": "#00FF00",
                        },
                    ],
                },
                {
                    "tick": 1,
                    "primitives": [
                        {
                            "observation_id": "observation:eye-0001",
                            "primitive_type": "ellipse",
                            "bounds": [12, 11, 22, 21],
                            "fill": "#F80000",
                        },
                        {
                            "observation_id": "observation:mark-a-0001",
                            "primitive_type": "rectangle",
                            "bounds": [39, 40, 49, 50],
                            "fill": "#00FF00",
                        },
                        {
                            "observation_id": "observation:mark-b-0001",
                            "primitive_type": "rectangle",
                            "bounds": [41, 40, 51, 50],
                            "fill": "#00FF00",
                        },
                    ],
                },
            ],
        }
        self.source = self.artifacts.import_bytes(
            canonical_bytes(self.observations),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "fixture:primitive-provider@0.1"},
        )

    def request(self) -> AdapterRequest:
        assert self.store.head is not None
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.source.artifact_id,),
        )

    def test_abstaining_correspondence_is_deterministic_and_evidence_only(self) -> None:
        first = TemporalCorrespondenceAdapter().propose(self.request(), self.artifacts)
        second = TemporalCorrespondenceAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(first.proposal_id, second.proposal_id)
        evidence = self.artifacts.get(first.preview_artifacts[0].artifact_id)
        candidates = json.loads(evidence.content)["candidates"]
        self.assertEqual(
            {candidate["status"] for candidate in candidates},
            {"SUPPORTED", "UNCERTAIN", "REJECTED"},
        )
        eye = next(
            candidate
            for candidate in candidates
            if candidate["source_observation_id"] == "observation:eye-0000"
            and candidate["target_observation_id"] == "observation:eye-0001"
        )
        self.assertEqual(eye["status"], "SUPPORTED")
        self.assertEqual(eye["displacement"], [2.0, 1.0])
        self.assertEqual(eye["policy_identity"], POLICY_IDENTITY)

        before = self.store.get_document(first.base_revision_id)
        accepted = ProposalAcceptor().accept(self.store, first, self.artifacts)
        after = self.store.get_document(accepted.revision_id)
        for field in ("entities", "construction", "presentation", "animation"):
            self.assertEqual(after[field], before[field])
        self.assertEqual(len(after["references"]), len(before["references"]) + 1)
        self.assertEqual(evidence.media_type, EVIDENCE_MEDIA_TYPE)
        self.assertEqual(
            json.loads(evidence.content)["source_artifact_id"], self.source.artifact_id
        )

    def test_identity_binds_subject_separately_from_inference_source(self) -> None:
        proposal = TemporalCorrespondenceAdapter().propose(self.request(), self.artifacts)
        candidate = json.loads(
            self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content
        )["candidates"][0]
        changed = copy.deepcopy(self.observations)
        changed["frames"][1]["primitives"][0]["fill"] = "#F70000"
        other = self.artifacts.import_bytes(
            canonical_bytes(changed),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "fixture:primitive-provider@0.1"},
        )
        assert self.store.head is not None
        other_proposal = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(other.artifact_id,),
            ),
            self.artifacts,
        )
        other_candidates = json.loads(
            self.artifacts.get(other_proposal.preview_artifacts[0].artifact_id).content
        )["candidates"]
        same_subject = next(
            item
            for item in other_candidates
            if item["source_observation_id"] == candidate["source_observation_id"]
            and item["target_observation_id"] == candidate["target_observation_id"]
        )
        self.assertEqual(candidate["candidate_id"], same_subject["candidate_id"])
        self.assertNotEqual(candidate["inference_id"], same_subject["inference_id"])

    def test_noncanonical_or_wrong_shape_input_fails_closed(self) -> None:
        noncanonical = self.artifacts.import_bytes(
            json.dumps(self.observations, indent=2).encode(),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
        )
        assert self.store.head is not None
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(noncanonical.artifact_id,),
        )
        with self.assertRaisesRegex(TemporalCorrespondenceError, "canonical JSON"):
            TemporalCorrespondenceAdapter().propose(request, self.artifacts)


if __name__ == "__main__":
    unittest.main()
