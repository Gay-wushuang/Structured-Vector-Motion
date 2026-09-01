from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import (
    AdapterRequest,
    ArtifactStore,
    Evaluator,
    ProposalAcceptor,
    RevisionStore,
)
from svm.adapters import (
    POPOutputAdapter,
    POPStructureAdapter,
    POPStructureError,
    POPTokenExporter,
)
from svm.adapters.pop_structure import ANALYSIS_MEDIA_TYPE, MASK_BUNDLE_MEDIA_TYPE
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "005-empty-canvas.svm.json"
GOLDEN_P = ROOT / "examples" / "derived" / "020-pop-output" / "real"
GOLDEN_Q = ROOT / "examples" / "derived" / "021-pop-structure"


class POPStructureGoldenQTest(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads((GOLDEN_P / "pop-output.json").read_text(encoding="utf-8"))
        producer = payload["producer"]
        self.artifacts = ArtifactStore()
        self.prefix, self.output = POPTokenExporter().export(
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
        self.store = RevisionStore.create(json.loads(BASE.read_text(encoding="utf-8")))
        proposal = POPOutputAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.prefix.artifact_id, self.output.artifact_id),
                options={"namespace": "golden-p-real"},
            ),
            self.artifacts,
        )
        self.pop_revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def request(
        self, *, document: dict[str, object] | None = None, options: dict[str, object] | None = None
    ) -> AdapterRequest:
        return AdapterRequest(
            base_revision_id=self.pop_revision.revision_id,
            document=copy.deepcopy(
                document or self.store.get_document(self.pop_revision.revision_id)
            ),
            scope=("document",),
            artifact_ids=(self.prefix.artifact_id, self.output.artifact_id),
            options=copy.deepcopy(options or {}),
        )

    def test_golden_q_attaches_evidence_without_changing_scene_semantics(self) -> None:
        base = self.store.get_document(self.pop_revision.revision_id)
        first = POPStructureAdapter().propose(self.request(), self.artifacts)
        second = POPStructureAdapter().propose(self.request(), self.artifacts)
        manifest = json.loads((GOLDEN_Q / "run-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(first.proposal_id, manifest["proposal_id"])
        self.assertEqual(
            first.report.metrics,
            {
                "primitives": 143.0,
                "topmost_coverage_relations": 783.0,
                "fully_covered_primitives": 2.0,
            },
        )
        self.assertEqual(len(first.preview_artifacts), 4)
        self.assertEqual(len(first.preview.structural_relations), 783)
        self.assertTrue(
            all(
                relation.relation_type == "geometric-topmost-covers"
                for relation in first.preview.structural_relations
            )
        )
        self.assertEqual(self.store.get_document(self.pop_revision.revision_id), base)

        dry_run = ProposalAcceptor().validate(self.store, first, self.artifacts)
        revision = ProposalAcceptor().accept(self.store, first, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, dry_run)
        self.assertEqual(revision.revision_id, manifest["accepted_revision_id"])
        for field in ("entities", "construction", "presentation", "structural_relations"):
            self.assertEqual(accepted.get(field), base.get(field))
        self.assertEqual(len(accepted["references"]), len(base["references"]) + 4)
        self.assertEqual(
            hashlib.sha256(canonical_bytes(accepted)).hexdigest(),
            manifest["accepted_document_sha256"],
        )
        detached = json.loads(canonical_bytes(accepted))
        evaluator = Evaluator(detached)
        evaluator.evaluate_all()

    def test_real_mask_analysis_and_renders_match_frozen_fixtures(self) -> None:
        proposal = POPStructureAdapter().propose(self.request(), self.artifacts)
        snapshots = {
            item.artifact_id: self.artifacts.get(item.artifact_id)
            for item in proposal.preview_artifacts
        }
        by_media = {snapshot.media_type: snapshot for snapshot in snapshots.values()}
        analysis = by_media[ANALYSIS_MEDIA_TYPE]
        masks = by_media[MASK_BUNDLE_MEDIA_TYPE]
        svgs = [
            snapshot for snapshot in snapshots.values() if snapshot.media_type == "image/svg+xml"
        ]
        normal = next(snapshot for snapshot in svgs if b'opacity="0.5"' in snapshot.content)
        xray = next(snapshot for snapshot in svgs if b'opacity="0.2"' in snapshot.content)

        self.assertEqual(normal.content, (GOLDEN_Q / "normal.svg").read_bytes())
        self.assertEqual(normal.content, (GOLDEN_P / "svm.svg").read_bytes())
        self.assertEqual(xray.content, (GOLDEN_Q / "xray.svg").read_bytes())
        self.assertEqual(masks.content, (GOLDEN_Q / "coverage-masks.json").read_bytes())
        self.assertEqual(
            analysis.content, (GOLDEN_Q / "topmost-coverage-analysis.json").read_bytes()
        )

        analysis_payload = json.loads(analysis.content)
        mask_payload = json.loads(masks.content)
        incoming_coverage: dict[str, int] = {}
        for relation in analysis_payload["topmost_coverage_relations"]:
            incoming_coverage[relation["covered_entity_id"]] = (
                incoming_coverage.get(relation["covered_entity_id"], 0)
                + relation["coverage_pixels"]
            )
            self.assertLess(relation["covered_render_index"], relation["topmost_render_index"])
        for entity in analysis_payload["entities"]:
            self.assertEqual(
                entity["full_pixels"],
                entity["topmost_pixels"] + incoming_coverage.get(entity["entity_id"], 0),
            )

        topmost_union = 0
        for entity in mask_payload["entities"]:
            full = _runs_to_mask(entity["full_runs"])
            topmost = _runs_to_mask(entity["topmost_runs"])
            self.assertEqual(full.bit_count(), entity["full_pixels"])
            self.assertEqual(topmost.bit_count(), entity["topmost_pixels"])
            self.assertEqual(topmost & ~full, 0)
            self.assertEqual(topmost_union & topmost, 0)
            topmost_union |= topmost

    def test_source_drift_options_and_artifact_mismatch_fail_closed(self) -> None:
        with self.assertRaisesRegex(POPStructureError, "does not accept options"):
            POPStructureAdapter().propose(self.request(options={"threshold": 0.5}), self.artifacts)

        drifted = self.store.get_document(self.pop_revision.revision_id)
        drifted["presentation"]["styles"][1]["opacity"] = 0.4
        with self.assertRaisesRegex(POPStructureError, "unchanged accepted"):
            POPStructureAdapter().propose(self.request(document=drifted), self.artifacts)

        wrong_artifacts = replace(self.request(), artifact_ids=(self.output.artifact_id,))
        with self.assertRaisesRegex(POPStructureError, "exact prefix and output"):
            POPStructureAdapter().propose(wrong_artifacts, self.artifacts)


def _runs_to_mask(runs: list[list[int]]) -> int:
    mask = 0
    for y, start, end in runs:
        if not (0 <= y < 256 and 0 <= start < end <= 256):
            raise AssertionError("invalid canonical mask run")
        for x in range(start, end):
            mask |= 1 << (y * 256 + x)
    return mask


if __name__ == "__main__":
    unittest.main()
