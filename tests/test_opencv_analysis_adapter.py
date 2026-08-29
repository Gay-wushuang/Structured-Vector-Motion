import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

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
from svm.adapters import OpenCVAnalysisAdapter, OpenCVAnalysisError

ROOT = Path(__file__).resolve().parents[1]
EMPTY = ROOT / "examples" / "005-empty-canvas.svm.json"
SOURCE = ROOT / "examples" / "assets" / "006-opencv-analysis-source.png"
DERIVED = ROOT / "examples" / "derived" / "012-opencv-analysis"
GOLDEN = ROOT / "examples" / "imported" / "012-opencv-analysis.svm.json"


class OpenCVAnalysisGoldenHTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EMPTY.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        self.source = self.artifacts.import_bytes(
            SOURCE.read_bytes(),
            media_type="image/png",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE.name},
        )

    def request(self, **options: object) -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.source.artifact_id,),
            options={"threshold": 128, "foreground": "dark", "connectivity": 8, **options},
        )

    def test_golden_h_creates_derived_evidence_without_entity_claims(self) -> None:
        proposal = OpenCVAnalysisAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertEqual(proposal.generator.engine, "opencv-python-headless")
        self.assertEqual(proposal.generator.engine_version, "4.14.0.94")
        self.assertEqual(proposal.generator.parameters["opencv_runtime_version"], "4.14.0")
        self.assertEqual(proposal.report.metrics["connected_components"], 2.0)
        self.assertEqual(proposal.report.metrics["foreground_pixels"], 25.0)
        self.assertIsNone(proposal.confidence)
        self.assertEqual(len(proposal.preview_artifacts), 2)
        candidates = proposal.preview.structural_candidates
        self.assertEqual(
            candidates,
            (
                type(candidates[0])(
                    "candidate:component-0001",
                    (2, 2, 5, 5),
                    9,
                    (3.0, 3.0),
                    "sha256:a5f53746c04e276c7f63092959c1ea9f3ef736db4479f8f331c05083abd74f8a",
                ),
                type(candidates[0])(
                    "candidate:component-0002",
                    (21, 4, 26, 9),
                    16,
                    (23.0, 6.0),
                    "sha256:d0ad22d3baeba14861506e331c2d91efe6a3fc50fcb32fb9b54e36c1afa868c0",
                ),
            ),
        )

        mask = self.artifacts.resolve_as(
            (proposal.preview_artifacts[0].artifact_id,),
            kind=ArtifactKind.DERIVED,
            media_types=frozenset({"image/png"}),
        )[0]
        analysis = self.artifacts.resolve_as(
            (proposal.preview_artifacts[1].artifact_id,),
            kind=ArtifactKind.DERIVED,
            media_types=frozenset({"application/vnd.svm.component-analysis+json"}),
        )[0]
        self.assertEqual(mask.content, (DERIVED / "binary-mask.png").read_bytes())
        self.assertEqual(analysis.content, (DERIVED / "component-analysis.json").read_bytes())
        self.assertEqual(mask.provenance["derived_type"], "binary-mask")
        self.assertEqual(analysis.provenance["derived_type"], "component-analysis")
        self.assertEqual(proposal.generator.adapter_version, "0.2")
        self.assertEqual(
            proposal.generator.parameters["analysis_identity"], "svm-opencv-components@0.2"
        )
        self.assertEqual(proposal.generator.parameters["mask_identity"], "svm-binary-mask-png@0.2")
        self.assertIn(b"SVMArtifact\x00binary-mask-v0.2", mask.content)
        self.assertEqual(
            json.loads(analysis.content)["schema_version"], "svm-component-analysis-0.2"
        )
        self.assertNotIn(self.source.content_hash.encode("ascii"), mask.content)
        import cv2
        import numpy as np

        decoded_mask = cv2.imdecode(
            np.frombuffer(mask.content, dtype=np.uint8), cv2.IMREAD_GRAYSCALE
        )
        self.assertEqual(set(int(value) for value in np.unique(decoded_mask)), {0, 255})
        self.assertEqual(int(np.count_nonzero(decoded_mask)), 25)

        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, json.loads(GOLDEN.read_text(encoding="utf-8")))
        self.assertEqual(len(accepted["references"]), 3)
        self.assertEqual(accepted["entities"], [])
        self.assertEqual(accepted["construction"]["operations"], [])
        self.assertEqual(accepted["presentation"]["render_stack"], [])

    def test_analysis_is_content_deterministic_and_threshold_changes_outputs(self) -> None:
        first = OpenCVAnalysisAdapter().propose(self.request(), self.artifacts)
        second = OpenCVAnalysisAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(first.preview_artifacts, second.preview_artifacts)

        changed = OpenCVAnalysisAdapter().propose(self.request(threshold=0), self.artifacts)
        self.assertNotEqual(first.proposal_id, changed.proposal_id)
        self.assertNotEqual(first.preview_artifacts, changed.preview_artifacts)

    def test_equal_mask_content_has_one_blob_identity_across_sources(self) -> None:
        from PIL import Image, PngImagePlugin

        alternate_bytes = io.BytesIO()
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("SourceVariant", "different provenance, equal samples")
        with Image.open(SOURCE) as image:
            image.save(alternate_bytes, format="PNG", pnginfo=metadata)
        alternate = self.artifacts.import_bytes(
            alternate_bytes.getvalue(),
            media_type="image/png",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": "alternate.png"},
        )
        self.assertNotEqual(self.source.artifact_id, alternate.artifact_id)
        alternate_request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(alternate.artifact_id,),
            options={"threshold": 128},
        )

        first = OpenCVAnalysisAdapter().propose(self.request(), self.artifacts)
        second = OpenCVAnalysisAdapter().propose(alternate_request, self.artifacts)

        self.assertEqual(first.preview_artifacts[0], second.preview_artifacts[0])
        self.assertNotEqual(first.preview_artifacts[1], second.preview_artifacts[1])

    def test_invalid_options_artifacts_and_permission_fail_closed(self) -> None:
        for options, message in (
            ({"threshold": 256}, "threshold"),
            ({"foreground": "red"}, "foreground"),
            ({"connectivity": 4}, "8-connectivity"),
            ({"unknown": True}, "Unknown"),
        ):
            with self.subTest(options=options):
                with self.assertRaisesRegex(OpenCVAnalysisError, message):
                    OpenCVAnalysisAdapter().propose(self.request(**options), self.artifacts)

        invalid = self.artifacts.import_bytes(b"not-png", media_type="image/png")
        invalid_request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(invalid.artifact_id,),
        )
        with self.assertRaisesRegex(OpenCVAnalysisError, "PNG IHDR"):
            OpenCVAnalysisAdapter().propose(invalid_request, self.artifacts)

        proposal = OpenCVAnalysisAdapter().propose(self.request(), self.artifacts)
        with self.assertRaisesRegex(ProposalArtifactError, "Unknown artifact"):
            ProposalAcceptor().accept(self.store, proposal, ArtifactStore())

        from PIL import Image

        for mode in ("RGBA", "RGB", "P", "1"):
            with self.subTest(mode=mode):
                unsupported_bytes = io.BytesIO()
                Image.new(mode, (2, 2)).save(unsupported_bytes, format="PNG")
                unsupported = self.artifacts.import_bytes(
                    unsupported_bytes.getvalue(), media_type="image/png"
                )
                unsupported_request = AdapterRequest.from_store(
                    self.store,
                    self.store.head,
                    ("document",),
                    artifact_ids=(unsupported.artifact_id,),
                )
                with self.assertRaisesRegex(OpenCVAnalysisError, "8-bit opaque grayscale"):
                    OpenCVAnalysisAdapter().propose(unsupported_request, self.artifacts)

        oversized_bytes = bytearray(SOURCE.read_bytes())
        oversized_bytes[16:20] = struct.pack(">I", 16_000_001)
        oversized = self.artifacts.import_bytes(bytes(oversized_bytes), media_type="image/png")
        oversized_request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(oversized.artifact_id,),
        )
        with self.assertRaisesRegex(OpenCVAnalysisError, "16 megapixel"):
            OpenCVAnalysisAdapter().propose(oversized_request, self.artifacts)

        protected = json.loads(EMPTY.read_text(encoding="utf-8"))
        protected["edit_permissions"].append(
            {
                "id": "permission:no-analysis",
                "actor": "adapter:opencv-analysis",
                "effect": "deny",
                "actions": ["attach_analysis"],
                "targets": ["document"],
            }
        )
        protected_store = RevisionStore.create(protected)
        request = AdapterRequest.from_store(
            protected_store,
            protected_store.head,
            ("document",),
            artifact_ids=(self.source.artifact_id,),
            options={"threshold": 128},
        )
        denied = OpenCVAnalysisAdapter().propose(request, self.artifacts)
        with self.assertRaisesRegex(ProposalPolicyError, "attach_analysis"):
            ProposalAcceptor().accept(protected_store, denied, self.artifacts)

    def test_stale_analysis_proposal_conflicts(self) -> None:
        proposal = OpenCVAnalysisAdapter().propose(self.request(), self.artifacts)
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def test_cli_previews_then_explicitly_writes_artifacts_and_document(self) -> None:
        preview = run_cli("analyze-bitmap", str(EMPTY), str(SOURCE), "--threshold", "128")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(json.loads(preview.stdout)["accepted"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "analysis.svm.json"
            derived = Path(directory) / "derived"
            accepted = run_cli(
                "analyze-bitmap",
                str(EMPTY),
                str(SOURCE),
                "--threshold",
                "128",
                "--derived-dir",
                str(derived),
                "--accept",
                "--output",
                str(output),
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            result = json.loads(accepted.stdout)
            self.assertTrue(result["accepted"])
            self.assertEqual(len(result["structural_candidates"]), 2)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                json.loads(GOLDEN.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                (derived / "component-analysis.json").read_bytes(),
                (DERIVED / "component-analysis.json").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
