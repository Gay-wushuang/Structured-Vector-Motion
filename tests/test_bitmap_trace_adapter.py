import copy
import importlib.metadata
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
from svm.adapters import BitmapTraceAdapter, BitmapTraceError, PotracerEngine
from svm.adapters.bitmap_trace import TracedPath, _number, _point
from svm.adapters.path_bounds import canonical_path_bounds
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
        self.assertEqual(proposal.generator.engine, "bitmap-trace/potracer")
        self.assertEqual(
            proposal.generator.engine_version,
            f"{importlib.metadata.version('potracer')}"
            f"+pillow@{importlib.metadata.version('Pillow')}"
            "+svm-bitmap-preprocess@0.1"
            f"+svgpathtools@{importlib.metadata.version('svgpathtools')}"
            "+svm-path-bounds@0.1",
        )
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

    def test_non_png_bytes_and_png_transparency_fail_closed(self) -> None:
        from PIL import Image

        encoded = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(encoded, format="JPEG")
        jpeg = self.artifacts.import_bytes(encoded.getvalue(), media_type="image/png")
        jpeg_request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(jpeg.artifact_id,),
        )
        with self.assertRaisesRegex(BitmapTraceError, "must be PNG format"):
            BitmapTraceAdapter().propose(jpeg_request, self.artifacts)

        encoded = io.BytesIO()
        Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(encoded, format="PNG")
        transparent = self.artifacts.import_bytes(encoded.getvalue(), media_type="image/png")
        transparent_request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(transparent.artifact_id,),
        )
        with self.assertRaisesRegex(BitmapTraceError, "alpha/transparency"):
            BitmapTraceAdapter().propose(transparent_request, self.artifacts)

    def test_decode_limit_is_checked_before_image_load(self) -> None:
        class OversizedImage:
            format = "PNG"
            width = 16_000_001
            height = 1
            info = {}
            loaded = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def getbands(self):
                return ("L",)

            def load(self):
                self.loaded = True

        source = OversizedImage()
        with patch("PIL.Image.open", return_value=source):
            with self.assertRaisesRegex(BitmapTraceError, "16 megapixel"):
                PotracerEngine().trace(b"header fixture", self._trace_options())
        self.assertFalse(source.loaded)

    def test_non_finite_trace_options_fail_closed(self) -> None:
        for name in ("alpha_max", "optimization_tolerance", "path_tolerance"):
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(BitmapTraceError, "finite positive"):
                        BitmapTraceAdapter().propose(self.request(**{name: value}), self.artifacts)

    def test_namespace_checks_entity_and_all_operation_ids(self) -> None:
        document = copy.deepcopy(self.document)
        document["construction"]["operations"].append(
            {
                "id": "op:trace-fixture-path",
                "type": "CreateRectangle",
                "inputs": {},
                "parameters": {"x": 0, "y": 0, "width": 1, "height": 1},
            }
        )
        store = RevisionStore.create(document)
        request = AdapterRequest.from_store(
            store,
            store.head,
            ("document",),
            artifact_ids=(self.artifact.artifact_id,),
            options={"namespace": "fixture"},
        )
        proposal = BitmapTraceAdapter().propose(request, self.artifacts)
        change = proposal.transaction.changes[0]

        self.assertEqual(change.entities[0]["id"], "entity:trace-fixture2")
        self.assertEqual(
            [operation["id"] for operation in change.operations],
            ["op:trace-fixture2-path", "op:trace-fixture2-planar"],
        )

    def test_path_numbers_and_bounds_share_canonical_coordinates(self) -> None:
        point = _point(SimpleNamespace(x=1.23456789012349, y=-0.0000000000004))

        self.assertEqual(point, (1.23456789012, -4e-13))
        self.assertEqual((_number(point[0]), _number(point[1])), ("1.23456789012", "-4e-13"))
        self.assertEqual(
            canonical_path_bounds("M 0 0 C 0 100 100 100 100 0"),
            (0.0, 0.0, 100.0, 75.0),
        )

    def test_automatic_namespace_includes_generator_identity(self) -> None:
        class FixtureTracer:
            engine_name = "fixture-tracer"

            def __init__(self, engine_version: str) -> None:
                self.engine_version = engine_version

            def trace(self, content, options):
                return TracedPath("M 0 0 L 1 0 L 1 1 Z", (0.0, 0.0, 1.0, 1.0), 1)

        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.artifact.artifact_id,),
        )
        first = BitmapTraceAdapter(FixtureTracer("1")).propose(request, self.artifacts)
        second = BitmapTraceAdapter(FixtureTracer("2")).propose(request, self.artifacts)

        first_change = first.transaction.changes[0]
        second_change = second.transaction.changes[0]
        self.assertNotEqual(first_change.entities[0]["id"], second_change.entities[0]["id"])
        self.assertNotEqual(first_change.operations[0]["id"], second_change.operations[0]["id"])

    @staticmethod
    def _trace_options():
        from svm.adapters.bitmap_trace import TraceOptions

        return TraceOptions()

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
