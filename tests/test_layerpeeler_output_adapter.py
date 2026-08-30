import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    Evaluator,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
    build_evaluated_scene,
)
from svm.adapters import LayerPeelerOutputAdapter, LayerPeelerOutputError
from svm.adapters.layerpeeler_output import layerpeeler_run_identity
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
        producer = {
            "repository": "https://github.com/kingnobro/LayerPeeler",
            "commit": COMMIT,
            "model_id": "golden-k-recorded-output",
            "checkpoint_hash": f"sha256:{'1' * 64}",
            "seed": 7,
        }
        identity_payload = {"source_artifact_id": self.source.artifact_id, "producer": producer}
        run_identity = layerpeeler_run_identity(identity_payload)
        self.layer_artifacts = tuple(
            self.artifacts.import_bytes(
                (LAYERS / name).read_bytes(),
                media_type="image/svg+xml",
                kind=ArtifactKind.DERIVED,
                provenance={
                    "derived_type": "layer-svg",
                    "source_artifact_id": self.source.artifact_id,
                    "manifest_identity": "svm-layerpeeler-output@0.2",
                    "run_identity": run_identity,
                    **producer,
                    "layer_id": f"layer:{layer_name}",
                    "z_index": index,
                },
            )
            for index, (layer_name, name) in enumerate(
                (("background", "layer-background.svg"), ("foreground", "layer-foreground.svg"))
            )
        )
        payload = {
            "schema_version": "svm-layerpeeler-output-0.2",
            "source_artifact_id": self.source.artifact_id,
            "run_identity": run_identity,
            "producer": producer,
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
                "manifest_identity": "svm-layerpeeler-output@0.2",
                "run_identity": run_identity,
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
        self.assertEqual(first.report.metrics, {"layers": 2.0, "shapes": 4.0})
        self.assertEqual(len(first.preview_artifacts), 4)
        self.assertEqual(len(first.preview.proposed_render_stack), 4)

        revision = ProposalAcceptor().accept(self.store, first, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(
            accepted["presentation"]["render_stack"], list(first.preview.proposed_render_stack)
        )
        self.assertEqual(
            [entity["semantic_tags"] for entity in accepted["entities"]],
            [["research-layer", "layerpeeler-output"]] * 4,
        )
        foreground_origins = [
            entity["source_layer"]
            for entity in accepted["entities"]
            if entity["source_layer"]["layer_id"] == "layer:foreground"
        ]
        self.assertEqual(len(foreground_origins), 3)
        self.assertEqual(len({canonical_bytes(origin) for origin in foreground_origins}), 1)
        self.assertEqual(
            [operation["type"] for operation in accepted["construction"]["operations"]],
            ["CreateRectangle", "CreatePath", "CreateEllipse", "CreateRectangle"],
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

        mixed_svg = self.artifacts.import_bytes(
            self.layer_artifacts[1].content + b"\n",
            media_type="image/svg+xml",
            kind=ArtifactKind.DERIVED,
            provenance={
                **self.layer_artifacts[1].provenance,
                "commit": "2" * 40,
                "run_identity": f"sha256:{'2' * 64}",
            },
        )
        mixed_payload = json.loads(self.manifest.content)
        mixed_payload["layers"][1]["svg_artifact_id"] = mixed_svg.artifact_id
        mixed_payload["layers"][1]["svg_content_hash"] = mixed_svg.content_hash
        mixed_manifest = self.artifacts.import_bytes(
            canonical_bytes(mixed_payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=copy.deepcopy(self.manifest.provenance),
        )
        mixed_request = self.request(
            (
                self.source.artifact_id,
                mixed_manifest.artifact_id,
                self.layer_artifacts[0].artifact_id,
                mixed_svg.artifact_id,
            )
        )
        with self.assertRaisesRegex(LayerPeelerOutputError, "provenance is inconsistent"):
            LayerPeelerOutputAdapter().propose(mixed_request, self.artifacts)

    def test_acceptor_rejects_handcrafted_source_layer_semantics(self) -> None:
        proposal = LayerPeelerOutputAdapter().propose(self.request(), self.artifacts)
        change = proposal.transaction.changes[0]
        fragment = change.fragment  # type: ignore[attr-defined]
        entities = copy.deepcopy(fragment.entities)
        entities[0]["source_layer"]["run_identity"] = f"sha256:{'f' * 64}"
        forged_change = replace(change, fragment=replace(fragment, entities=tuple(entities)))
        forged = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(forged_change,)),
        )
        with self.assertRaisesRegex(ProposalArtifactError, "does not match"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

        generic_bypass = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(forged_change.fragment,)),
        )
        with self.assertRaisesRegex(ProposalArtifactError, "reserved"):
            ProposalAcceptor().accept(self.store, generic_bypass, self.artifacts)

    def test_untrusted_manifest_types_fail_with_domain_error(self) -> None:
        payload = json.loads(self.manifest.content)
        payload["producer"]["commit"] = 123
        malformed = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=copy.deepcopy(self.manifest.provenance),
        )
        request = self.request(
            (
                self.source.artifact_id,
                malformed.artifact_id,
                *(artifact.artifact_id for artifact in self.layer_artifacts),
            )
        )
        with self.assertRaisesRegex(LayerPeelerOutputError, "full Git SHA"):
            LayerPeelerOutputAdapter().propose(request, self.artifacts)


if __name__ == "__main__":
    unittest.main()
