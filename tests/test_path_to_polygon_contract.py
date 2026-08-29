import copy
import json
import unittest
from pathlib import Path

import jsonschema

from svm import (
    AdapterRequest,
    ArtifactStore,
    EvaluationState,
    Evaluator,
    ProposalAcceptor,
    Quality,
    RevisionStore,
    build_evaluated_scene,
)
from svm.adapters import SVGImportAdapter
from svm.backends.shapely_geometry import ShapelyGeometryBackend
from svm.document import validate_document
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "tests" / "contracts" / "path-to-polygon-v0.1.json"
GOLDEN_DOCUMENT_PATH = ROOT / "examples" / "008-golden-d.svm.json"
SOURCE_PATH = ROOT / "examples" / "assets" / "002-bezier-boolean-source.svg"
EMPTY_DOCUMENT_PATH = ROOT / "examples" / "005-empty-canvas.svm.json"
SCHEMA_PATH = ROOT / "schema" / "svm-document-v0.1.schema.json"
RENDERED_GOLDEN_PATH = ROOT / "examples" / "rendered" / "008-golden-d.svg"


class PathToPolygonContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.golden_document = json.loads(GOLDEN_DOCUMENT_PATH.read_text(encoding="utf-8"))

    def test_contract_records_explicit_document_parameters_and_rejections(self) -> None:
        operation = self.contract["operation"]
        self.assertEqual(operation["type"], "PathToPolygon")
        self.assertEqual(operation["parameters"]["fill_rule"]["enum"], ["nonzero", "evenodd"])
        self.assertEqual(operation["parameters"]["tolerance"]["exclusive_minimum"], 0)
        self.assertFalse(operation["quality_sensitive"])
        self.assertEqual(self.contract["algorithm_identity"], "svm-path-planar:0.1")
        self.assertEqual(len(self.contract["negative_cases"]), 8)

    def test_golden_d_document_is_schema_and_semantics_valid(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(self.golden_document, schema)
        validate_document(self.golden_document)

    def test_svg_boundary_produces_two_closed_cubic_create_path_operations(self) -> None:
        base = json.loads(EMPTY_DOCUMENT_PATH.read_text(encoding="utf-8"))
        revision_store = RevisionStore.create(base)
        artifact_store = ArtifactStore()
        artifact = artifact_store.import_bytes(
            SOURCE_PATH.read_bytes(),
            media_type="image/svg+xml",
            provenance={"source_name": SOURCE_PATH.name},
        )
        request = AdapterRequest.from_store(
            revision_store,
            revision_store.head,
            ("document",),
            artifact_ids=(artifact.artifact_id,),
            options={"namespace": "golden-d-contract"},
        )
        proposal = SVGImportAdapter().propose(request, artifact_store)
        revision = ProposalAcceptor().accept(revision_store, proposal, artifact_store)
        imported = revision_store.get_document(revision.revision_id)
        operations = imported["construction"]["operations"]
        golden_paths = [
            operation
            for operation in self.golden_document["construction"]["operations"]
            if operation["type"] == "CreatePath"
        ]

        self.assertEqual([operation["type"] for operation in operations], ["CreatePath"] * 2)
        self.assertEqual(
            [operation["parameters"] for operation in operations],
            [operation["parameters"] for operation in golden_paths],
        )
        for operation in operations:
            path_data = operation["parameters"]["d"]
            self.assertIn(" C ", path_data)
            self.assertTrue(path_data.endswith(" Z"))

    def test_golden_d_is_content_deterministic(self) -> None:
        first = Evaluator(
            copy.deepcopy(self.golden_document),
            geometry_backend=ShapelyGeometryBackend(),
        )
        second = Evaluator(
            copy.deepcopy(self.golden_document),
            geometry_backend=ShapelyGeometryBackend(),
        )
        first.evaluate_all(Quality.FINAL)
        second.evaluate_all(Quality.FINAL)

        for operation_id in (
            "op:golden-d-left-planar",
            "op:golden-d-right-planar",
            "op:golden-d-union",
        ):
            first_node = first.runtime[operation_id]
            second_node = second.runtime[operation_id]
            self.assertEqual(first_node.state, EvaluationState.CLEAN)
            self.assertEqual(
                first_node.outputs["geometry"].value_id,
                second_node.outputs["geometry"].value_id,
            )
            self.assertEqual(first_node.outputs["geometry"].payload["kind"], "polygon_set")
        self.assertIn(
            "svm-path-planar:0.1",
            first.runtime["op:golden-d-left-planar"].backend_identity,
        )

    def test_tolerance_changes_evaluation_key_and_invalidates_dependants(self) -> None:
        evaluator = Evaluator(
            copy.deepcopy(self.golden_document),
            geometry_backend=ShapelyGeometryBackend(),
        )
        evaluator.evaluate_all(Quality.FINAL)
        previous_key = evaluator.runtime["op:golden-d-left-planar"].evaluation_key
        independent_value = (
            evaluator.runtime["op:golden-d-right-planar"].outputs["geometry"].value_id
        )

        invalidated = evaluator.set_parameter("op:golden-d-left-planar", "tolerance", 0.25)
        self.assertEqual(
            invalidated,
            {"op:golden-d-left-planar", "op:golden-d-union"},
        )
        evaluator.evaluate_all(Quality.FINAL)
        self.assertNotEqual(
            evaluator.runtime["op:golden-d-left-planar"].evaluation_key,
            previous_key,
        )
        self.assertEqual(
            evaluator.runtime["op:golden-d-right-planar"].outputs["geometry"].value_id,
            independent_value,
        )

    def test_golden_d_render_matches_checked_in_svg(self) -> None:
        evaluator = Evaluator(
            copy.deepcopy(self.golden_document),
            geometry_backend=ShapelyGeometryBackend(),
        )
        scene = build_evaluated_scene(self.golden_document, evaluator)
        rendered = SVGRenderer(
            SVGRenderOptions(width=800, height=640, view_box=(0, 0, 140, 115))
        ).render(scene)
        self.assertEqual(rendered.encode("utf-8"), RENDERED_GOLDEN_PATH.read_bytes())

    def test_path_to_polygon_parameter_contract_is_enforced(self) -> None:
        invalid_parameters = (
            ({"tolerance": 0, "fill_rule": "nonzero"}, "greater than zero"),
            ({"tolerance": -1, "fill_rule": "nonzero"}, "greater than zero"),
            ({"tolerance": float("inf"), "fill_rule": "nonzero"}, "must be finite"),
            ({"tolerance": 0.5, "fill_rule": "winding"}, "fill_rule"),
        )
        for parameters, message in invalid_parameters:
            with self.subTest(parameters=parameters):
                document = copy.deepcopy(self.golden_document)
                operation = next(
                    operation
                    for operation in document["construction"]["operations"]
                    if operation["id"] == "op:golden-d-left-planar"
                )
                operation["parameters"] = parameters
                with self.assertRaisesRegex(ValueError, message):
                    Evaluator(document)

    def test_open_arc_degenerate_and_empty_paths_fail_explicitly(self) -> None:
        cases = (
            ("M 0 0 L 10 0 L 10 10", "nonzero", "close with Z"),
            ("M 0 0 A 10 10 0 0 1 20 0 Z", "nonzero", "elliptical arcs"),
            ("M 0 0 C 10 Z", "nonzero", "evaluation failed"),
            ("M 0 0 L 10 0 L 20 0 Z", "nonzero", "degenerate"),
            (
                "M 0 0 L 10 0 L 10 10 L 0 10 Z M 0 0 L 10 0 L 10 10 L 0 10 Z",
                "evenodd",
                "empty planar geometry",
            ),
        )
        backend = ShapelyGeometryBackend()
        for path_data, fill_rule, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    backend.path_to_polygon(
                        {"kind": "path_data", "d": path_data, "bounds": [0, 0, 20, 10]},
                        0.5,
                        fill_rule,
                    )

        with self.assertRaisesRegex(ValueError, "subdivision depth 32"):
            backend.path_to_polygon(
                {
                    "kind": "path_data",
                    "d": "M 0 0 C 0 100 100 100 100 0 L 0 0 Z",
                },
                5e-324,
                "nonzero",
            )

    def test_multiple_subpaths_and_fill_rules_select_holes_deterministically(self) -> None:
        same_direction = "M 0 0 L 10 0 L 10 10 L 0 10 Z M 2 2 L 8 2 L 8 8 L 2 8 Z"
        opposite_direction = "M 0 0 L 10 0 L 10 10 L 0 10 Z M 2 2 L 2 8 L 8 8 L 8 2 Z"
        backend = ShapelyGeometryBackend()
        nonzero_filled = backend.path_to_polygon(
            {"kind": "path_data", "d": same_direction}, 0.5, "nonzero"
        )
        evenodd_hole = backend.path_to_polygon(
            {"kind": "path_data", "d": same_direction}, 0.5, "evenodd"
        )
        nonzero_hole = backend.path_to_polygon(
            {"kind": "path_data", "d": opposite_direction}, 0.5, "nonzero"
        )

        self.assertEqual(len(nonzero_filled["polygons"][0]["holes"]), 0)
        self.assertEqual(len(evenodd_hole["polygons"][0]["holes"]), 1)
        self.assertEqual(nonzero_hole, evenodd_hole)
        self.assertEqual(
            backend.boolean("union", evenodd_hole, evenodd_hole),
            evenodd_hole,
        )

        exterior = evenodd_hole["polygons"][0]["exterior"]
        hole = evenodd_hole["polygons"][0]["holes"][0]
        self.assertLess(_signed_area(exterior), 0)
        self.assertGreater(_signed_area(hole), 0)
        self.assertEqual(exterior[0], min(exterior[:-1]))
        self.assertEqual(hole[0], min(hole[:-1]))

    def test_self_intersection_is_planarized_without_repair_heuristics(self) -> None:
        result = ShapelyGeometryBackend().path_to_polygon(
            {"kind": "path_data", "d": "M 0 0 L 10 10 L 0 10 L 10 0 Z"},
            0.5,
            "evenodd",
        )
        self.assertEqual(result["kind"], "polygon_set")
        self.assertEqual(len(result["polygons"]), 2)

    def test_relative_smooth_quadratic_and_axis_commands_are_supported(self) -> None:
        backend = ShapelyGeometryBackend()
        paths = (
            "M 0 0 q 5 10 10 0 t 10 0 v 10 h -20 z",
            "M 0 0 C 3 8 7 8 10 0 S 17 -8 20 0 V 10 H 0 Z",
        )
        for path_data in paths:
            with self.subTest(path_data=path_data):
                result = backend.path_to_polygon(
                    {"kind": "path_data", "d": path_data}, 0.25, "nonzero"
                )
                self.assertEqual(result["kind"], "polygon_set")

    def test_path_to_polygon_rejects_non_path_runtime_geometry(self) -> None:
        document = copy.deepcopy(self.golden_document)
        planar = next(
            operation
            for operation in document["construction"]["operations"]
            if operation["id"] == "op:golden-d-left-planar"
        )
        planar["inputs"]["path"] = "op:golden-d-union.geometry"
        # Rewire the union to avoid introducing a graph cycle while preserving
        # the geometry-typed but non-path runtime input.
        union = next(
            operation
            for operation in document["construction"]["operations"]
            if operation["id"] == "op:golden-d-union"
        )
        union["inputs"]["left"] = "op:golden-d-right-planar.geometry"
        evaluator = Evaluator(document, geometry_backend=ShapelyGeometryBackend())
        evaluator.evaluate_all(Quality.FINAL)
        self.assertEqual(evaluator.runtime["op:golden-d-left-planar"].state, EvaluationState.FAILED)
        self.assertIn(
            "requires path_data geometry",
            evaluator.runtime["op:golden-d-left-planar"].error,
        )


def _signed_area(ring) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(ring[:-1], ring[1:], strict=True)
    )


if __name__ == "__main__":
    unittest.main()
