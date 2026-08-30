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
    build_evaluated_scene,
)
from svm.adapters import LayerPeelerOutputAdapter, LayerPeelerOutputError
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "005-empty-canvas.svm.json"
SOURCE = ROOT / "examples" / "assets" / "007-contained-components-source.png"
LAYERS = ROOT / "examples" / "derived" / "016-layerpeeler-output"
COMMIT = "b75f2353011972f4c8c2dc748c1f0861ede2ee80"
MEDIA_TYPE = "application/vnd.svm.layerpeeler-output+json"


class LayerPeelerOutputGoldenKTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        self.source = self.artifacts.import_bytes(
            SOURCE.read_bytes(),
            media_type="image/png",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE.name},
        )
        provenance = {
            "derived_type": "layer-svg",
            "source_artifact_id": self.source.artifact_id,
            "manifest_identity": "svm-layerpeeler-output@0.1",
            "repository": "https://github.com/kingnobro/LayerPeeler",
            "commit": COMMIT,
        }
        self.layer_artifacts = tuple(
            self.artifacts.import_bytes(
                (LAYERS / name).read_bytes(),
                media_type="image/svg+xml",
                kind=ArtifactKind.DERIVED,
                provenance=provenance,
            )
            for name in ("layer-background.svg", "layer-foreground.svg")
        )
        payload = {
            "schema_version": "svm-layerpeeler-output-0.1",
            "source_artifact_id": self.source.artifact_id,
            "producer": {
                "repository": "https://github.com/kingnobro/LayerPeeler",
                "commit": COMMIT,
                "model_id": "golden-k-recorded-output",
                "checkpoint_hash": f"sha256:{'1' * 64}",
                "seed": 7,
            },
            "layers": [
                {
                    "layer_id": f"layer:{name}",
                    "z_index": index,
                    "svg_artifact_id": artifact.artifact_id,
                    "svg_content_hash": artifact.content_hash,
                }
                for index, (name, artifact) in enumerate(
                    zip(("background", "foreground"), self.layer_artifacts, strict=True)
                )
            ],
        }
        self.manifest = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "derived_type": "layerpeeler-output-manifest",
                "source_artifact_id": self.source.artifact_id,
                "manifest_identity": "svm-layerpeeler-output@0.1",
            },
        )

    def request(self, artifact_ids: tuple[str, ...] | None = None) -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=artifact_ids
            or (
                self.source.artifact_id,
                self.manifest.artifact_id,
                *(artifact.artifact_id for artifact in self.layer_artifacts),
            ),
            options={"namespace": "golden-k"},
        )

    def test_golden_k_normalizes_research_output_without_core_changes(self) -> None:
        adapter = LayerPeelerOutputAdapter()
        first = adapter.propose(self.request(), self.artifacts)
        second = adapter.propose(self.request(), self.artifacts)
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertEqual(first.report.metrics, {"layers": 2.0, "shapes": 2.0})
        self.assertEqual(len(first.preview_artifacts), 4)
        self.assertEqual(len(first.preview.proposed_render_stack), 2)

        revision = ProposalAcceptor().accept(self.store, first, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(
            accepted["presentation"]["render_stack"], list(first.preview.proposed_render_stack)
        )
        self.assertEqual(
            [entity["semantic_tags"] for entity in accepted["entities"]],
            [["research-layer", "layerpeeler-output"]] * 2,
        )
        self.assertEqual(
            [operation["type"] for operation in accepted["construction"]["operations"]],
            ["CreateRectangle", "CreatePath"],
        )
        evaluator = Evaluator(accepted)
        evaluator.evaluate_all()
        rendered = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 32, 32))).render(
            build_evaluated_scene(accepted, evaluator)
        )
        self.assertIn("background", accepted["entities"][0]["name"])
        self.assertIn("foreground", accepted["entities"][1]["name"])
        self.assertIn("#F4C95D", rendered)
        self.assertIn("#D1495B", rendered)

    def test_bundle_hash_order_and_provenance_fail_closed(self) -> None:
        missing = self.request(
            (
                self.source.artifact_id,
                self.manifest.artifact_id,
                self.layer_artifacts[0].artifact_id,
            )
        )
        with self.assertRaisesRegex(LayerPeelerOutputError, "invalid"):
            LayerPeelerOutputAdapter().propose(missing, self.artifacts)

        payload = json.loads(self.manifest.content)
        payload["layers"].reverse()
        forged = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=copy.deepcopy(self.manifest.provenance),
        )
        request = self.request(
            (
                self.source.artifact_id,
                forged.artifact_id,
                *(artifact.artifact_id for artifact in self.layer_artifacts),
            )
        )
        with self.assertRaisesRegex(LayerPeelerOutputError, "z_index"):
            LayerPeelerOutputAdapter().propose(request, self.artifacts)


if __name__ == "__main__":
    unittest.main()
