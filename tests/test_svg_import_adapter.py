import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from test_cli import run_cli

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    Evaluator,
    ProposalAcceptor,
    ProposalPolicyError,
    RevisionStore,
    build_evaluated_scene,
)
from svm.adapters import SVGImportAdapter, SVGImportError
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
EMPTY_DOCUMENT = ROOT / "examples" / "005-empty-canvas.svm.json"
SOURCE_SVG = ROOT / "examples" / "assets" / "001-import-source.svg"
IMPORTED_GOLDEN = ROOT / "examples" / "imported" / "006-imported-source.svm.json"
RENDERED_GOLDEN = ROOT / "examples" / "rendered" / "006-imported-source.svg"


class SVGImportAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EMPTY_DOCUMENT.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifact_store = ArtifactStore()
        self.artifact = self.artifact_store.import_bytes(
            SOURCE_SVG.read_bytes(),
            media_type="image/svg+xml",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE_SVG.name},
        )

    def request(self) -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifacts=(self.artifact,),
            options={"namespace": "fixture"},
        )

    def test_artifact_store_is_content_addressed_and_deduplicated(self) -> None:
        duplicate = self.artifact_store.import_bytes(
            SOURCE_SVG.read_bytes(),
            media_type="image/svg+xml",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE_SVG.name},
        )
        self.assertEqual(duplicate, self.artifact)
        self.assertTrue(self.artifact.artifact_id.startswith("artifact:"))
        self.assertEqual(self.artifact_store.get(self.artifact.artifact_id), self.artifact)
        relocated = self.artifact_store.import_bytes(
            SOURCE_SVG.read_bytes(),
            media_type="image/svg+xml",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": "relocated.svg"},
        )
        self.assertEqual(relocated.artifact_id, self.artifact.artifact_id)

    def test_adapter_proposes_atomic_import_without_mutating_base(self) -> None:
        proposal = SVGImportAdapter().propose(self.request())
        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertEqual(proposal.base_revision_id, self.store.head)
        self.assertEqual(proposal.report.metrics["imported_shapes"], 3.0)
        self.assertEqual(proposal.generator.engine, "svgpathtools")

        revision = ProposalAcceptor().accept(self.store, proposal)
        imported = self.store.get_document(revision.revision_id)
        self.assertEqual(len(imported["entities"]), 3)
        self.assertEqual(len(imported["references"]), 1)
        self.assertEqual(imported["references"][0]["content_hash"], self.artifact.content_hash)
        self.assertEqual(
            [operation["type"] for operation in imported["construction"]["operations"]],
            ["CreateRectangle", "CreateEllipse", "CreatePath"],
        )

        scene = build_evaluated_scene(imported, Evaluator(imported))
        svg = SVGRenderer(
            SVGRenderOptions(width=800, height=640, view_box=(0, 0, 200, 160))
        ).render(scene)
        root = ET.fromstring(svg)
        self.assertEqual(root.attrib["data-svm-quality"], "FINAL")
        self.assertEqual(len(scene.entities), 3)

    def test_cli_import_then_render_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            imported_path = Path(temporary_directory) / "imported.svm.json"
            rendered_path = Path(temporary_directory) / "imported.svg"
            imported = run_cli(
                "import-svg",
                str(EMPTY_DOCUMENT),
                str(SOURCE_SVG),
                "--namespace",
                "fixture",
                "--output",
                str(imported_path),
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertEqual(json.loads(imported.stdout)["imported_entities"], 3)

            rendered = run_cli(
                "render-svg",
                str(imported_path),
                "--output",
                str(rendered_path),
                "--view-box",
                "0",
                "0",
                "200",
                "160",
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertEqual(ET.parse(rendered_path).getroot().attrib["viewBox"], "0 0 200 160")

    def test_unsafe_or_unsupported_svg_is_rejected(self) -> None:
        unsafe = self.artifact_store.import_bytes(
            b'<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>',
            media_type="image/svg+xml",
        )
        request = AdapterRequest.from_store(
            self.store, self.store.head, ("document",), artifacts=(unsafe,)
        )
        with self.assertRaisesRegex(SVGImportError, "DTD"):
            SVGImportAdapter().propose(request)

    def test_import_scene_permission_is_enforced_at_acceptance(self) -> None:
        protected = self.store.get_document(self.store.head)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-svg-import",
                "actor": "adapter:svg-import",
                "effect": "deny",
                "actions": ["import_scene"],
                "targets": ["document"],
            }
        )
        protected_store = RevisionStore.create(protected)
        request = AdapterRequest.from_store(
            protected_store,
            protected_store.head,
            ("document",),
            artifacts=(self.artifact,),
            options={"namespace": "fixture"},
        )
        proposal = SVGImportAdapter().propose(request)

        with self.assertRaisesRegex(ProposalPolicyError, "denies adapter:svg-import"):
            ProposalAcceptor().accept(protected_store, proposal)

    def test_imported_document_and_render_match_checked_in_goldens(self) -> None:
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifacts=(self.artifact,),
            options={"namespace": "golden"},
        )
        proposal = SVGImportAdapter().propose(request)
        revision = ProposalAcceptor().accept(self.store, proposal)
        imported = self.store.get_document(revision.revision_id)
        self.assertEqual(
            imported,
            json.loads(IMPORTED_GOLDEN.read_text(encoding="utf-8")),
        )

        scene = build_evaluated_scene(imported, Evaluator(imported))
        rendered = SVGRenderer(
            SVGRenderOptions(width=800, height=640, view_box=(0, 0, 200, 160))
        ).render(scene)
        self.assertEqual(rendered.encode("utf-8"), RENDERED_GOLDEN.read_bytes())


if __name__ == "__main__":
    unittest.main()
