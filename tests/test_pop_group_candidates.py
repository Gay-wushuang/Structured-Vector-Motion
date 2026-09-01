from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from svm import AdapterRequest, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters import (
    POPGroupCandidateAdapter,
    POPGroupCandidateError,
    POPOutputAdapter,
    POPStructureAdapter,
    POPTokenExporter,
)
from svm.adapters.pop_group_candidates import MEDIA_TYPE, POLICY_VERSION
from svm.adapters.pop_structure import ANALYSIS_MEDIA_TYPE, MASK_BUNDLE_MEDIA_TYPE
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "examples" / "derived" / "020-pop-output" / "real"


class POPGroupCandidatesGoldenQv1Test(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads((REAL / "pop-output.json").read_text(encoding="utf-8"))
        producer = payload["producer"]
        self.artifacts = ArtifactStore()
        prefix, output = POPTokenExporter().export(
            self.artifacts,
            payload["raw_tokens"],
            prefix_length=payload["generation_context"]["prefix_length"],
            commit=producer["commit"],
            model_id=producer["model_id"],
            checkpoint_hash=producer["checkpoint_hash"],
            seed=producer["seed"],
            decoding=producer["decoding"],
            user_intent=payload["annotations"]["user_intent"],
        )
        base = json.loads(
            (ROOT / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(base)
        pop = POPOutputAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(prefix.artifact_id, output.artifact_id),
                options={"namespace": "golden-p-real"},
            ),
            self.artifacts,
        )
        pop_revision = ProposalAcceptor().accept(self.store, pop, self.artifacts)
        q0 = POPStructureAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                pop_revision.revision_id,
                ("document",),
                artifact_ids=(prefix.artifact_id, output.artifact_id),
            ),
            self.artifacts,
        )
        self.q0_ids = tuple(
            item.artifact_id
            for item in q0.preview_artifacts
            if item.media_type in {MASK_BUNDLE_MEDIA_TYPE, ANALYSIS_MEDIA_TYPE}
        )
        self.q0_revision = ProposalAcceptor().accept(self.store, q0, self.artifacts)

    def request(self) -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store, self.q0_revision.revision_id, ("document",), artifact_ids=self.q0_ids
        )

    def test_real_scene_produces_deterministic_abstaining_candidates(self) -> None:
        first = POPGroupCandidateAdapter().propose(self.request(), self.artifacts)
        second = POPGroupCandidateAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(first.proposal_id, second.proposal_id)
        candidates = first.preview.group_candidates
        self.assertGreater(len(candidates), 0)
        statuses = {item.status for item in candidates}
        self.assertIn("SUPPORTED", statuses)
        self.assertIn("UNCERTAIN", statuses)
        self.assertIn("REJECTED", statuses)
        self.assertTrue(all(item.policy_version == POLICY_VERSION for item in candidates))
        self.assertTrue(
            all(item.candidate_id.startswith("candidate:group:") for item in candidates)
        )
        artifact = self.artifacts.get(first.preview_artifacts[0].artifact_id)
        self.assertEqual(artifact.media_type, MEDIA_TYPE)
        content = json.loads(artifact.content)
        self.assertEqual(content["semantic_labels"], [])
        evidence_types = {
            evidence["type"]
            for candidate in content["candidates"]
            for evidence in candidate["evidence"]
        }
        self.assertIn("horizontal_alignment_similarity", evidence_types)
        self.assertNotIn("symmetry", evidence_types)
        self.assertTrue(
            any(
                next(item["score"] for item in candidate["evidence"] if item["type"] == "overlap")
                != next(
                    item["score"] for item in candidate["evidence"] if item["type"] == "containment"
                )
                for candidate in content["candidates"]
            )
        )
        base = self.store.get_document(self.q0_revision.revision_id)
        accepted = ProposalAcceptor().accept(self.store, first, self.artifacts)
        document = self.store.get_document(accepted.revision_id)
        for field in ("entities", "construction", "presentation", "structural_relations"):
            self.assertEqual(document.get(field), base.get(field))
        self.assertEqual(len(document["references"]), len(base["references"]) + 1)

    def test_subject_identity_does_not_depend_on_inference_scores(self) -> None:
        proposal = POPGroupCandidateAdapter().propose(self.request(), self.artifacts)
        candidate = json.loads(
            self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content
        )["candidates"][0]
        expected = (
            "candidate:group:"
            + hashlib.sha256(canonical_bytes({"members": sorted(candidate["members"])})).hexdigest()
        )
        self.assertEqual(candidate["candidate_id"], expected)
        changed = copy.deepcopy(candidate)
        changed["confidence"] = 0.0
        self.assertEqual(candidate["candidate_id"], changed["candidate_id"])
        inference_content = {
            key: value
            for key, value in candidate.items()
            if key not in {"inference_id", "confidence"}
        }
        expected_inference = (
            "inference:group:" + hashlib.sha256(canonical_bytes(inference_content)).hexdigest()
        )
        self.assertEqual(candidate["inference_id"], expected_inference)
        self.assertEqual(candidate["source_artifact_ids"], sorted(self.q0_ids))

    def test_unaccepted_or_mismatched_q0_evidence_fails_closed(self) -> None:
        request = self.request()
        request.document["references"] = [
            item for item in request.document["references"] if item["id"] not in self.q0_ids
        ]
        with self.assertRaisesRegex(POPGroupCandidateError, "already be accepted"):
            POPGroupCandidateAdapter().propose(request, self.artifacts)


if __name__ == "__main__":
    unittest.main()
