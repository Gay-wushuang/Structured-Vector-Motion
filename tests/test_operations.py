import copy
import json
import unittest
from pathlib import Path

from test_golden_b import split_transaction

from svm import Evaluator, RevisionStore, ValueType, get_operation_registry
from svm.document import validate_document
from svm.evaluator import DocumentError

ROOT = Path(__file__).resolve().parents[1]


class OperationRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(
            (ROOT / "examples" / "001-head-basic.svm.json").read_text(encoding="utf-8")
        )
        self.registry = get_operation_registry("svm-core-0.1")

    def test_registry_declares_static_signatures_and_quality_sensitivity(self) -> None:
        self.assertEqual(
            self.registry.type_names,
            (
                "BooleanGeometry",
                "Clip",
                "ConvertToPath",
                "CreateEllipse",
                "CreatePath",
                "CreateRectangle",
                "PathToPolygon",
                "RefineBezier",
                "SplitEntity",
                "Transform",
            ),
        )
        refine = self.registry.definition("RefineBezier")
        self.assertEqual(refine.inputs, {"geometry": ValueType.GEOMETRY})
        self.assertEqual(
            refine.output_signature(
                {
                    "type": "RefineBezier",
                    "inputs": {"geometry": "op:source.geometry"},
                    "parameters": {"tolerance": 0.1},
                }
            ),
            {"geometry": ValueType.GEOMETRY},
        )
        self.assertTrue(refine.quality_sensitive)
        self.assertFalse(self.registry.definition("CreateEllipse").quality_sensitive)
        path_to_polygon = self.registry.definition("PathToPolygon")
        self.assertEqual(path_to_polygon.inputs, {"path": ValueType.GEOMETRY})
        self.assertEqual(path_to_polygon.capability, "geometry")
        self.assertEqual(path_to_polygon.algorithm_identity, "svm-path-planar:0.1")
        self.assertFalse(path_to_polygon.quality_sensitive)

    def test_split_entity_declares_dynamic_output_signature(self) -> None:
        source = json.loads(
            (ROOT / "examples" / "003-split-head.svm.json").read_text(encoding="utf-8")
        )
        store = RevisionStore.create(source)
        revision = store.commit(store.head, split_transaction())
        split_document = store.get_document(revision.revision_id)
        operation = next(
            operation
            for operation in split_document["construction"]["operations"]
            if operation["id"] == "op:split_head"
        )

        self.assertEqual(
            self.registry.output_signature(operation),
            {
                "face_geometry": ValueType.GEOMETRY,
                "hair_geometry": ValueType.GEOMETRY,
            },
        )

    def test_dag_input_cannot_reference_nonexistent_output(self) -> None:
        invalid = copy.deepcopy(self.document)
        transform = next(
            operation
            for operation in invalid["construction"]["operations"]
            if operation["id"] == "op:head_transform"
        )
        transform["inputs"]["geometry"] = "op:head_base.nonexistent"

        with self.assertRaisesRegex(DocumentError, "missing output slot"):
            Evaluator(invalid)

    def test_entity_binding_cannot_reference_nonexistent_output(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["construction"]["output_bindings"][0]["slot"] = "op:head_refine.nonexistent"

        with self.assertRaisesRegex(DocumentError, "missing output slot"):
            validate_document(invalid)

    def test_operation_inputs_and_parameters_must_match_signature(self) -> None:
        missing_input = copy.deepcopy(self.document)
        transform = next(
            operation
            for operation in missing_input["construction"]["operations"]
            if operation["id"] == "op:head_transform"
        )
        transform["inputs"] = {}
        with self.assertRaisesRegex(DocumentError, "Input keys do not match signature"):
            Evaluator(missing_input)

    def test_primitive_dimensions_must_be_positive_and_finite(self) -> None:
        invalid_values = (("rx", 0), ("ry", -1), ("rx", float("inf")))
        for parameter, value in invalid_values:
            with self.subTest(parameter=parameter, value=value):
                invalid = copy.deepcopy(self.document)
                ellipse = next(
                    operation
                    for operation in invalid["construction"]["operations"]
                    if operation["type"] == "CreateEllipse"
                )
                ellipse["parameters"][parameter] = value
                with self.assertRaises(DocumentError):
                    validate_document(invalid)

        invalid_parameter = copy.deepcopy(self.document)
        ellipse = next(
            operation
            for operation in invalid_parameter["construction"]["operations"]
            if operation["id"] == "op:head_base"
        )
        ellipse["parameters"]["rx"] = "wide"
        with self.assertRaisesRegex(DocumentError, "rx must be a number"):
            Evaluator(invalid_parameter)

    def test_unknown_operation_type_is_rejected_by_semantics_registry(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["construction"]["operations"][0]["type"] = "MagicTrace"

        with self.assertRaisesRegex(DocumentError, "Unsupported operation type"):
            Evaluator(invalid)

    def test_parameter_mutation_is_validated_atomically(self) -> None:
        evaluator = Evaluator(copy.deepcopy(self.document))
        original = evaluator.operations["op:head_base"]["parameters"]["rx"]

        with self.assertRaisesRegex(DocumentError, "rx must be a number"):
            evaluator.set_parameter("op:head_base", "rx", "wide")

        self.assertEqual(evaluator.operations["op:head_base"]["parameters"]["rx"], original)

    def test_unknown_policy_definition_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["constraints"].append(
            {
                "id": "constraint:unknown",
                "type": "PreserveBounds",
                "operation": "op:head_base",
                "parameter": "rx",
            }
        )

        with self.assertRaisesRegex(DocumentError, "Unsupported constraint type"):
            validate_document(invalid)

    def test_policy_dangling_targets_are_rejected(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["edit_permissions"].append(
            {
                "id": "permission:dangling",
                "actor": "adapter:test",
                "effect": "deny",
                "actions": ["split_entity"],
                "targets": ["entity:missing"],
            }
        )

        with self.assertRaisesRegex(DocumentError, "missing targets"):
            validate_document(invalid)

    def test_invalid_style_is_rejected_semantically(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["presentation"]["styles"][0]["fill"] = "javascript:red"

        with self.assertRaisesRegex(DocumentError, "unsupported color"):
            validate_document(invalid)

    def test_split_selector_must_be_inside_normalized_bounds(self) -> None:
        source = json.loads(
            (ROOT / "examples" / "003-split-head.svm.json").read_text(encoding="utf-8")
        )
        store = RevisionStore.create(source)
        revision = store.commit(store.head, split_transaction())
        invalid = store.get_document(revision.revision_id)
        split = next(
            operation
            for operation in invalid["construction"]["operations"]
            if operation["id"] == "op:split_head"
        )
        split["parameters"]["parts"][0]["selector"]["width"] = 1.1

        with self.assertRaisesRegex(DocumentError, "inside normalized bounds"):
            validate_document(invalid)


if __name__ == "__main__":
    unittest.main()
