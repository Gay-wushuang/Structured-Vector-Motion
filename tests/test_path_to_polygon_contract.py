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
    get_operation_registry,
)
from svm.adapters import SVGImportAdapter
from svm.backends.shapely_geometry import ShapelyGeometryBackend
from svm.document import validate_document

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "tests" / "contracts" / "path-to-polygon-v0.1.json"
PENDING_DOCUMENT_PATH = ROOT / "examples" / "contracts" / "008-golden-d.pending.json"
SOURCE_PATH = ROOT / "examples" / "assets" / "002-bezier-boolean-source.svg"
EMPTY_DOCUMENT_PATH = ROOT / "examples" / "005-empty-canvas.svm.json"
SCHEMA_PATH = ROOT / "schema" / "svm-document-v0.1.schema.json"
PATH_TO_POLYGON_AVAILABLE = "PathToPolygon" in get_operation_registry("svm-core-0.1").type_names


class PathToPolygonContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.pending_document = json.loads(PENDING_DOCUMENT_PATH.read_text(encoding="utf-8"))

    def test_contract_records_explicit_document_parameters_and_rejections(self) -> None:
        operation = self.contract["operation"]
        self.assertEqual(operation["type"], "PathToPolygon")
        self.assertEqual(operation["parameters"]["fill_rule"]["enum"], ["nonzero", "evenodd"])
        self.assertEqual(operation["parameters"]["tolerance"]["exclusive_minimum"], 0)
        self.assertFalse(operation["quality_sensitive"])
        self.assertEqual(self.contract["algorithm_identity"], "svm-path-planar:0.1")
        self.assertEqual(len(self.contract["negative_cases"]), 8)

    def test_pending_golden_d_document_is_schema_valid_and_fails_closed(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(self.pending_document, schema)
        if not PATH_TO_POLYGON_AVAILABLE:
            with self.assertRaisesRegex(ValueError, "Unsupported operation type: PathToPolygon"):
                validate_document(self.pending_document)

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

        self.assertEqual([operation["type"] for operation in operations], ["CreatePath"] * 2)
        for operation in operations:
            path_data = operation["parameters"]["d"]
            self.assertIn(" C ", path_data)
            self.assertTrue(path_data.endswith(" Z"))

    @unittest.skipUnless(
        PATH_TO_POLYGON_AVAILABLE,
        "PathToPolygon algorithm is intentionally pending after the contract milestone",
    )
    def test_golden_d_is_content_deterministic(self) -> None:
        first = Evaluator(
            copy.deepcopy(self.pending_document),
            geometry_backend=ShapelyGeometryBackend(),
        )
        second = Evaluator(
            copy.deepcopy(self.pending_document),
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

    @unittest.skipUnless(
        PATH_TO_POLYGON_AVAILABLE,
        "PathToPolygon algorithm is intentionally pending after the contract milestone",
    )
    def test_tolerance_changes_evaluation_key_and_invalidates_dependants(self) -> None:
        evaluator = Evaluator(
            copy.deepcopy(self.pending_document),
            geometry_backend=ShapelyGeometryBackend(),
        )
        evaluator.evaluate_all(Quality.FINAL)
        previous_key = evaluator.runtime["op:golden-d-left-planar"].evaluation_key

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


if __name__ == "__main__":
    unittest.main()
