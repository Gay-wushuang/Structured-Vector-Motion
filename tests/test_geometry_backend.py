import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_cli import run_cli

from svm import EvaluationState, Evaluator, Quality, build_evaluated_scene
from svm.backends import GeometryBackendError
from svm.backends.shapely_geometry import ShapelyGeometryBackend
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_PATH = ROOT / "examples" / "007-boolean-geometry.svm.json"
RENDERED_GOLDEN = ROOT / "examples" / "rendered" / "007-boolean-geometry.svg"


class GeometryBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(DOCUMENT_PATH.read_text(encoding="utf-8"))
        self.backend = ShapelyGeometryBackend()

    def test_boolean_union_is_canonical_and_content_deterministic(self) -> None:
        first = Evaluator(self.document, geometry_backend=self.backend)
        second = Evaluator(self.document, geometry_backend=self.backend)
        first.evaluate_all(Quality.FINAL)
        second.evaluate_all(Quality.FINAL)
        first_value = first.runtime["op:boolean"].outputs["geometry"]
        second_value = second.runtime["op:boolean"].outputs["geometry"]

        self.assertEqual(first_value.value_id, second_value.value_id)
        self.assertEqual(
            first.runtime["op:boolean"].evaluation_key, second.runtime["op:boolean"].evaluation_key
        )
        self.assertEqual(first_value.payload["bounds"], [10.0, 20.0, 160.0, 120.0])
        self.assertEqual(first_value.payload["kind"], "polygon_set")
        self.assertEqual(first.runtime["op:boolean"].backend_identity, self.backend.identity)
        self.assertEqual(first_value.payload["polygons"][0]["exterior"][0], [10.0, 20.0])

    def test_missing_backend_fails_at_runtime_without_changing_document_validity(self) -> None:
        evaluator = Evaluator(self.document)
        evaluator.evaluate_all(Quality.FINAL)

        node = evaluator.runtime["op:boolean"]
        self.assertEqual(node.state, EvaluationState.FAILED)
        self.assertIn("requires a GeometryBackend", node.error)

    def test_unknown_boolean_operator_is_rejected_during_document_validation(self) -> None:
        boolean = next(
            operation
            for operation in self.document["construction"]["operations"]
            if operation["id"] == "op:boolean"
        )
        boolean["parameters"]["operator"] = "maybe"
        with self.assertRaisesRegex(ValueError, "operator must be"):
            Evaluator(self.document)

    def test_backend_identity_participates_in_capability_evaluation_key(self) -> None:
        class AlternateIdentityBackend:
            identity = "test-geometry:alternate"

            def boolean(self, operator, left, right):
                return self_backend.boolean(operator, left, right)

        self_backend = self.backend
        first = Evaluator(self.document, geometry_backend=self.backend)
        alternate = Evaluator(self.document, geometry_backend=AlternateIdentityBackend())
        first.evaluate_all(Quality.FINAL)
        alternate.evaluate_all(Quality.FINAL)

        self.assertNotEqual(
            first.runtime["op:boolean"].evaluation_key,
            alternate.runtime["op:boolean"].evaluation_key,
        )
        self.assertEqual(
            first.runtime["op:boolean"].outputs["geometry"].value_id,
            alternate.runtime["op:boolean"].outputs["geometry"].value_id,
        )

    def test_geos_version_participates_in_capability_evaluation_key(self) -> None:
        class RecordedIdentityBackend:
            def __init__(self, identity: str) -> None:
                self.identity = identity

            def boolean(self, operator, left, right):
                return self_backend.boolean(operator, left, right)

        self_backend = self.backend
        with patch("svm.backends.shapely_geometry.geos_version_string", "3.13.0"):
            first_identity = self.backend.identity
        with patch("svm.backends.shapely_geometry.geos_version_string", "3.13.1"):
            second_identity = self.backend.identity

        first = Evaluator(self.document, geometry_backend=RecordedIdentityBackend(first_identity))
        second = Evaluator(self.document, geometry_backend=RecordedIdentityBackend(second_identity))
        first.evaluate_all(Quality.FINAL)
        second.evaluate_all(Quality.FINAL)

        self.assertNotEqual(first_identity, second_identity)
        self.assertNotEqual(
            first.runtime["op:boolean"].evaluation_key,
            second.runtime["op:boolean"].evaluation_key,
        )
        self.assertEqual(
            first.runtime["op:boolean"].outputs["geometry"].value_id,
            second.runtime["op:boolean"].outputs["geometry"].value_id,
        )

    def test_shapely_exceptions_are_normalized_at_backend_boundary(self) -> None:
        from shapely.errors import GEOSException

        with patch(
            "svm.backends.shapely_geometry.union",
            side_effect=GEOSException("fixture topology failure"),
        ):
            with self.assertRaisesRegex(
                GeometryBackendError, "Shapely/GEOS boolean operation failed"
            ) as raised:
                self.backend.boolean(
                    "union",
                    {"kind": "rectangle", "x": 0, "y": 0, "width": 1, "height": 1},
                    {"kind": "rectangle", "x": 1, "y": 0, "width": 1, "height": 1},
                )
        self.assertIsInstance(raised.exception.__cause__, GEOSException)

    def test_backend_rejects_unsupported_input_geometry(self) -> None:
        with self.assertRaisesRegex(GeometryBackendError, "input kind 'ellipse'"):
            self.backend.boolean(
                "union",
                {"kind": "ellipse", "cx": 0, "cy": 0, "rx": 1, "ry": 1},
                {"kind": "rectangle", "x": 0, "y": 0, "width": 1, "height": 1},
            )

    def test_all_declared_boolean_operators_execute(self) -> None:
        left = {"kind": "rectangle", "x": 0, "y": 0, "width": 4, "height": 3}
        right = {"kind": "rectangle", "x": 2, "y": 1, "width": 4, "height": 3}
        expected = {
            "union": ([0.0, 0.0, 6.0, 4.0], 1),
            "intersection": ([2.0, 1.0, 4.0, 3.0], 1),
            "difference": ([0.0, 0.0, 4.0, 3.0], 1),
            "xor": ([0.0, 0.0, 6.0, 4.0], 2),
        }
        for operator, (bounds, polygon_count) in expected.items():
            with self.subTest(operator=operator):
                result = self.backend.boolean(operator, left, right)
                self.assertEqual(result["bounds"], bounds)
                self.assertEqual(len(result["polygons"]), polygon_count)

    def test_empty_area_result_is_explicitly_rejected(self) -> None:
        with self.assertRaisesRegex(GeometryBackendError, "empty geometry"):
            self.backend.boolean(
                "intersection",
                {"kind": "rectangle", "x": 0, "y": 0, "width": 1, "height": 1},
                {"kind": "rectangle", "x": 2, "y": 2, "width": 1, "height": 1},
            )

    def test_scene_and_cli_render_match_checked_in_golden(self) -> None:
        evaluator = Evaluator(self.document, geometry_backend=self.backend)
        scene = build_evaluated_scene(self.document, evaluator)
        rendered = SVGRenderer(
            SVGRenderOptions(width=800, height=640, view_box=(0, 0, 180, 140))
        ).render(scene)
        self.assertEqual(rendered.encode("utf-8"), RENDERED_GOLDEN.read_bytes())

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "boolean.svg"
            result = run_cli(
                "render-svg",
                str(DOCUMENT_PATH),
                "--geometry-backend",
                "shapely",
                "--output",
                str(output),
                "--width",
                "800",
                "--height",
                "640",
                "--view-box",
                "0",
                "0",
                "180",
                "140",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), RENDERED_GOLDEN.read_bytes())


if __name__ == "__main__":
    unittest.main()
