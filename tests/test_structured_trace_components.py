import copy
import json
import unittest
from pathlib import Path

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    Evaluator,
    ProposalAcceptor,
    RevisionStore,
)
from svm.adapters import BitmapTraceAdapter
from svm.backends.shapely_geometry import ShapelyGeometryBackend
from svm.evaluator import EvaluationState, Quality
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.scene import build_evaluated_scene

ROOT = Path(__file__).resolve().parents[1]
EMPTY_DOCUMENT = ROOT / "examples" / "005-empty-canvas.svm.json"
SOURCE = ROOT / "examples" / "assets" / "004-structured-trace-source.png"
DOCUMENT_GOLDEN = ROOT / "examples" / "imported" / "010-structured-trace.svm.json"
SVG_GOLDEN = ROOT / "examples" / "rendered" / "010-structured-trace.svg"


class StructuredTraceGoldenFTest(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(EMPTY_DOCUMENT.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()
        self.artifact = self.artifacts.import_bytes(
            SOURCE.read_bytes(),
            media_type="image/png",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE.name},
        )

    def test_golden_f_structures_components_and_preserves_hole_ownership(self) -> None:
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.artifact.artifact_id,),
            options={"namespace": "structured"},
        )
        proposal = BitmapTraceAdapter().propose(request, self.artifacts)
        self.assertEqual(proposal.report.metrics["traced_paths"], 4.0)
        self.assertEqual(proposal.report.metrics["structured_entities"], 3.0)
        self.assertEqual(len(self.store.get_document(self.store.head)["entities"]), 0)

        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, json.loads(DOCUMENT_GOLDEN.read_text(encoding="utf-8")))
        accepted_for_render = copy.deepcopy(accepted)
        expected_entities = [
            "entity:trace-structured-0000",
            "entity:trace-structured-0001",
            "entity:trace-structured-0002",
        ]
        self.assertEqual([entity["id"] for entity in accepted["entities"]], expected_entities)
        self.assertEqual(accepted["presentation"]["render_stack"], expected_entities)
        self.assertEqual(len(accepted["construction"]["operations"]), 6)

        evaluator = Evaluator(accepted, geometry_backend=ShapelyGeometryBackend())
        evaluator.evaluate_all(Quality.FINAL)
        polygon_counts = []
        hole_counts = []
        for index in range(3):
            operation_id = f"op:trace-structured-{index:04d}-planar"
            payload = evaluator.runtime[operation_id].outputs["geometry"].payload
            polygon_counts.append(len(payload["polygons"]))
            hole_counts.append(sum(len(polygon["holes"]) for polygon in payload["polygons"]))
        self.assertEqual(polygon_counts, [1, 1, 1])
        self.assertEqual(hole_counts, [0, 1, 0])

        evaluator.set_parameter("op:trace-structured-0001-planar", "tolerance", 0.5)
        self.assertEqual(
            evaluator.runtime["op:trace-structured-0001-planar"].state,
            EvaluationState.DIRTY,
        )
        self.assertEqual(
            evaluator.runtime["op:trace-structured-0000-planar"].state,
            EvaluationState.CLEAN,
        )
        self.assertEqual(
            evaluator.runtime["op:trace-structured-0002-planar"].state,
            EvaluationState.CLEAN,
        )

        render_evaluator = Evaluator(accepted_for_render, geometry_backend=ShapelyGeometryBackend())
        scene = build_evaluated_scene(accepted_for_render, render_evaluator, Quality.FINAL)
        rendered = SVGRenderer(
            SVGRenderOptions(width=1024, height=1024, view_box=(0, 0, 120, 90))
        ).render(scene)
        self.assertEqual(rendered, SVG_GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
