import builtins
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_cli import run_cli

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalConflictError,
    ProposalPolicyError,
    RevisionStore,
)
from svm.adapters import ComponentPromotionAdapter, ComponentPromotionError
from svm.document import validate_document
from svm.evaluator import DocumentError, canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "imported" / "012-opencv-analysis.svm.json"
ANALYSIS = ROOT / "examples" / "derived" / "012-opencv-analysis" / "component-analysis.json"
GOLDEN = ROOT / "examples" / "imported" / "013-component-promotion.svm.json"
MEDIA_TYPE = "application/vnd.svm.component-analysis+json"
CANDIDATES = ["candidate:component-0001", "candidate:component-0002"]


class ComponentPromotionGoldenITest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        self.analysis = self._import_accepted_analysis(self.document, ANALYSIS.read_bytes())

    def _import_accepted_analysis(self, document: dict[str, object], content: bytes) -> object:
        artifact_id = f"artifact:{hashlib.sha256(content).hexdigest()}"
        reference = next(
            reference
            for reference in document["references"]  # type: ignore[index]
            if reference["id"] == artifact_id
        )
        metadata = reference["import_metadata"]
        return self.artifacts.import_bytes(
            content,
            media_type=reference["media_type"],
            kind=ArtifactKind(metadata["artifact_kind"]),
            provenance=metadata["provenance"],
        )

    def request(
        self,
        *,
        store: RevisionStore | None = None,
        artifact_id: str | None = None,
        **options: object,
    ) -> AdapterRequest:
        target = store or self.store
        return AdapterRequest.from_store(
            target,
            target.head,
            ("document",),
            artifact_ids=(artifact_id or self.analysis.artifact_id,),  # type: ignore[attr-defined]
            options={"candidate_ids": CANDIDATES, **options},
        )

    def test_golden_i_promotes_evidence_without_raster_or_geometry_work(self) -> None:
        original_import = builtins.__import__

        def reject_opencv(name: str, *args: object, **kwargs: object) -> object:
            if name == "cv2" or name.startswith("cv2."):
                raise AssertionError("Promotion must not import OpenCV")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=reject_opencv):
            proposal = ComponentPromotionAdapter().propose(
                self.request(candidate_ids=list(reversed(CANDIDATES))), self.artifacts
            )

        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertEqual(proposal.generator.engine_version, "svm-component-promotion@0.1")
        self.assertIsNone(proposal.confidence)
        self.assertEqual(proposal.report.metrics, {"promoted_components": 2.0})
        self.assertEqual(
            [diff.after_bounds for diff in proposal.preview.entity_diffs],  # type: ignore[union-attr]
            [(2, 2, 5, 5), (21, 4, 26, 9)],
        )

        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, json.loads(GOLDEN.read_text(encoding="utf-8")))
        self.assertEqual(len(accepted["entities"]), 2)
        self.assertEqual(
            [entity["semantic_tags"] for entity in accepted["entities"]],
            [["region", "promoted-component"]] * 2,
        )
        self.assertEqual(
            [entity["provenance"]["candidate_id"] for entity in accepted["entities"]],
            CANDIDATES,
        )
        self.assertEqual(accepted["construction"]["operations"], [])
        self.assertEqual(accepted["construction"]["output_bindings"], [])
        self.assertEqual(accepted["presentation"]["styles"], [])
        self.assertEqual(accepted["presentation"]["render_stack"], [])

    def test_selection_and_identity_are_deterministic_and_fail_closed(self) -> None:
        first = ComponentPromotionAdapter().propose(self.request(), self.artifacts)
        second = ComponentPromotionAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(first.proposal_id, second.proposal_id)

        reversed_selection = ComponentPromotionAdapter().propose(
            self.request(candidate_ids=list(reversed(CANDIDATES))), self.artifacts
        )
        self.assertEqual(first.proposal_id, reversed_selection.proposal_id)

        for options, message in (
            ({"candidate_ids": []}, "non-empty"),
            ({"candidate_ids": [CANDIDATES[0], CANDIDATES[0]]}, "unique"),
            ({"candidate_ids": ["candidate:component-9999"]}, "Unknown"),
            ({"candidate_ids": CANDIDATES, "namespace": "Bad Namespace"}, "namespace"),
            ({"candidate_ids": CANDIDATES, "unknown": True}, "Unknown"),
        ):
            with self.subTest(options=options):
                request = AdapterRequest.from_store(
                    self.store,
                    self.store.head,
                    ("document",),
                    artifact_ids=(self.analysis.artifact_id,),  # type: ignore[attr-defined]
                    options=options,
                )
                with self.assertRaisesRegex(ComponentPromotionError, message):
                    ComponentPromotionAdapter().propose(request, self.artifacts)

    def test_unaccepted_malformed_and_wrong_provenance_evidence_fail_closed(self) -> None:
        empty = copy.deepcopy(self.document)
        empty["references"] = []
        empty_store = RevisionStore.create(empty)
        with self.assertRaisesRegex(ComponentPromotionError, "already be accepted"):
            ComponentPromotionAdapter().propose(self.request(store=empty_store), self.artifacts)

        payload = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        payload["schema_version"] = "svm-component-analysis-0.1"
        malformed_bytes = canonical_bytes(payload)
        malformed_document, malformed_artifacts, malformed_id = self._replace_analysis(
            malformed_bytes
        )
        malformed_store = RevisionStore.create(malformed_document)
        with self.assertRaisesRegex(ComponentPromotionError, "conform"):
            ComponentPromotionAdapter().propose(
                self.request(store=malformed_store, artifact_id=malformed_id),
                malformed_artifacts,
            )

        wrong_document = copy.deepcopy(self.document)
        analysis_reference = next(
            reference
            for reference in wrong_document["references"]
            if reference["id"] == self.analysis.artifact_id  # type: ignore[attr-defined]
        )
        analysis_reference["import_metadata"]["provenance"]["parameters"]["analysis_identity"] = (
            "svm-opencv-components@9.9"
        )
        wrong_artifacts = ArtifactStore()
        wrong_artifacts.import_bytes(
            ANALYSIS.read_bytes(),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=analysis_reference["import_metadata"]["provenance"],
        )
        wrong_store = RevisionStore.create(wrong_document)
        with self.assertRaisesRegex(ComponentPromotionError, "svm-opencv-components@0.2"):
            ComponentPromotionAdapter().propose(self.request(store=wrong_store), wrong_artifacts)

    def _replace_analysis(self, content: bytes) -> tuple[dict[str, object], ArtifactStore, str]:
        document = copy.deepcopy(self.document)
        old_reference = next(
            reference
            for reference in document["references"]
            if reference["media_type"] == MEDIA_TYPE  # type: ignore[index]
        )
        digest = hashlib.sha256(content).hexdigest()
        artifact_id = f"artifact:{digest}"
        old_reference["id"] = artifact_id
        old_reference["uri"] = artifact_id
        old_reference["content_hash"] = f"sha256:{digest}"
        artifacts = ArtifactStore()
        artifacts.import_bytes(
            content,
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=old_reference["import_metadata"]["provenance"],
        )
        return document, artifacts, artifact_id

    def test_stale_repeated_permission_and_missing_artifact_fail_closed(self) -> None:
        proposal = ComponentPromotionAdapter().propose(self.request(), self.artifacts)
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.store, proposal, ArtifactStore())
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)

        promoted_store = RevisionStore.create(json.loads(GOLDEN.read_text(encoding="utf-8")))
        with self.assertRaisesRegex(ComponentPromotionError, "already promoted"):
            ComponentPromotionAdapter().propose(self.request(store=promoted_store), self.artifacts)

        protected = copy.deepcopy(self.document)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-promotion",
                "actor": "adapter:component-promotion",
                "effect": "deny",
                "actions": ["promote_components"],
                "targets": ["document"],
            }
        )
        protected_store = RevisionStore.create(protected)
        denied = ComponentPromotionAdapter().propose(
            self.request(store=protected_store), self.artifacts
        )
        with self.assertRaisesRegex(ProposalPolicyError, "promote_components"):
            ProposalAcceptor().accept(protected_store, denied, self.artifacts)

        invalid = json.loads(GOLDEN.read_text(encoding="utf-8"))
        invalid["entities"][0]["provenance"]["artifact_id"] = "artifact:" + "0" * 64
        with self.assertRaisesRegex(DocumentError, "missing Artifact"):
            validate_document(invalid)

    def test_cli_previews_then_accepts_golden_i(self) -> None:
        preview = run_cli(
            "promote-components",
            str(BASE),
            str(ANALYSIS),
            "--candidate",
            CANDIDATES[0],
            "--candidate",
            CANDIDATES[1],
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(json.loads(preview.stdout)["accepted"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "promoted.svm.json"
            accepted = run_cli(
                "promote-components",
                str(BASE),
                str(ANALYSIS),
                "--candidate",
                CANDIDATES[0],
                "--candidate",
                CANDIDATES[1],
                "--accept",
                "--output",
                str(output),
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertTrue(json.loads(accepted.stdout)["accepted"])
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                json.loads(GOLDEN.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()
