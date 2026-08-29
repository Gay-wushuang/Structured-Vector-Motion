import copy
import json
import tempfile
import unittest
from pathlib import Path

from test_cli import run_cli

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    Evaluator,
    ProposalAcceptor,
    RevisionStore,
    build_evaluated_scene,
)
from svm.adapters import BitmapTraceAdapter, BitmapTraceError
from svm.backends.shapely_geometry import ShapelyGeometryBackend
from svm.evaluator import Quality
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
EMPTY_DOCUMENT = ROOT / "examples" / "005-empty-canvas.svm.json"
SOURCE_PNG = ROOT / "examples" / "assets" / "003-bitmap-trace-source.png"
IMPORTED_GOLDEN = ROOT / "examples" / "imported" / "009-bitmap-trace.svm.json"
RENDERED_GOLDEN = ROOT / "examples" / "rendered" / "009-bitmap-trace.svg"


class BitmapTraceGoldenETest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EMPTY_DOCUMENT.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        self.artifact = self.artifacts.import_bytes(
            SOURCE_PNG.read_bytes(),
            media_type="image/png",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE_PNG.name},
        )

    def request(self, **options: object) -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.artifact.artifact_id,),
            options={"namespace": "fixture", **options},
        )

    def test_golden_e_bitmap_to_explicit_planar_geometry_and_svg(self) -> None:
        proposal = BitmapTraceAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertEqual(proposal.generator.engine, "potracer")
        self.assertEqual(proposal.report.metrics["traced_paths"], 2.0)

        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(
            [operation["type"] for operation in accepted["construction"]["operations"]],
            ["CreatePath", "PathToPolygon"],
        )
        self.assertEqual(accepted, json.loads(IMPORTED_GOLDEN.read_text(encoding="utf-8")))

        evaluator = Evaluator(accepted, geometry_backend=ShapelyGeometryBackend())
        evaluator.evaluate("op:trace-fixture-planar", Quality.FINAL)
        planar = evaluator.runtime["op:trace-fixture-planar"].outputs["geometry"]
        self.assertEqual(planar.payload["kind"], "polygon_set")
        self.assertEqual(len(planar.payload["polygons"]), 1)
        self.assertEqual(len(planar.payload["polygons"][0]["holes"]), 1)
        scene = build_evaluated_scene(accepted, evaluator, Quality.FINAL)
        rendered = SVGRenderer(
            SVGRenderOptions(width=1024, height=1024, view_box=(0, 0, 96, 80))
        ).render(scene)
        self.assertEqual(rendered, RENDERED_GOLDEN.read_text(encoding="utf-8"))

    def test_equal_inputs_are_deterministic_and_tolerance_changes_evaluation_key(self) -> None:
        first = BitmapTraceAdapter().propose(self.request(), self.artifacts)
        second = BitmapTraceAdapter().propose(self.request(), self.artifacts)
        first_change = first.transaction.changes[0]
        second_change = second.transaction.changes[0]
        self.assertEqual(first_change.operations, second_change.operations)

        accepted = first.transaction.apply(copy.deepcopy(self.document))
        evaluator = Evaluator(accepted, geometry_backend=ShapelyGeometryBackend())
        evaluator.evaluate("op:trace-fixture-planar", Quality.FINAL)
        old_key = evaluator.runtime["op:trace-fixture-planar"].evaluation_key
        evaluator.set_parameter("op:trace-fixture-planar", "tolerance", 0.5)
        evaluator.evaluate("op:trace-fixture-planar", Quality.FINAL)
        self.assertNotEqual(old_key, evaluator.runtime["op:trace-fixture-planar"].evaluation_key)

    def test_invalid_media_options_and_empty_trace_fail_closed(self) -> None:
        invalid = self.artifacts.import_bytes(b"not png", media_type="image/png")
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(invalid.artifact_id,),
        )
        with self.assertRaisesRegex(BitmapTraceError, "Invalid PNG"):
            BitmapTraceAdapter().propose(request, self.artifacts)
        with self.assertRaisesRegex(BitmapTraceError, "threshold"):
            BitmapTraceAdapter().propose(self.request(threshold=300), self.artifacts)

        wrong_media = ArtifactStore()
        artifact = wrong_media.import_bytes(SOURCE_PNG.read_bytes(), media_type="image/jpeg")
        wrong_request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(artifact.artifact_id,),
        )
        with self.assertRaisesRegex(ValueError, "matching interpretation"):
            BitmapTraceAdapter().propose(wrong_request, wrong_media)

    def test_cli_trace_bitmap_writes_a_valid_golden_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "trace.svm.json"
            completed = run_cli(
                "trace-bitmap",
                str(EMPTY_DOCUMENT),
                str(SOURCE_PNG),
                "--namespace",
                "fixture",
                "--output",
                str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["traced_paths"], 2.0)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                json.loads(IMPORTED_GOLDEN.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()
