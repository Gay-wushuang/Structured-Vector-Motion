import builtins
import hashlib
import json
import struct
import unittest
import zlib
from dataclasses import replace
from pathlib import Path
from unittest import mock

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    ImportRasterLayerEvidenceChange,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalPolicyError,
    RevisionStore,
)
from svm.adapters import LayerDOutputAdapter, LayerDOutputError
from svm.adapters.layerd_output import layerd_run_identity
from svm.document import validate_document
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "005-empty-canvas.svm.json"
SOURCE = ROOT / "examples" / "assets" / "007-contained-components-source.png"
PROPOSALS_SHA256 = "f022a88cd03029a37784dfa692ed00dc911dfa579857f7cfd3627f34ac48aff4"
COMMIT = "21aef937a0371614adb4d961f52d02409cb8ecc7"


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def rgba_png(width: int, height: int, opaque: set[tuple[int, int]]) -> bytes:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            alpha = 255 if (x, y) in opaque else 0
            rows.extend((20 + x * 10, 30 + y * 10, 80, alpha))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + _chunk(b"IEND", b"")
    )


class LayerDGoldenLTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts, self.ids = self._bundle()

    def _bundle(
        self,
        *,
        label: str = "text",
        max_iterations: int = 3,
        fg_refine_num_colors: int = 2,
        overlap_threshold: float = 0.9,
        ocr_identity: str = "disabled@0.1",
        classifier_identity: str = "entropy-labeler@0.1",
        classifier_threshold: float = 5.0,
        manifest_hash_valid: bool = True,
        analysis_alpha_count: int = 4,
        analysis_canvas_width: int = 4,
        layer_run_override: str | None = None,
    ) -> tuple[ArtifactStore, tuple[str, ...]]:
        artifacts = ArtifactStore()
        source = artifacts.import_bytes(
            SOURCE.read_bytes(),
            media_type="image/png",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE.name},
        )
        producer = {
            "repository": "https://github.com/CyberAgentAILab/LayerD",
            "commit": COMMIT,
            "birefnet_checkpoint_hash": f"sha256:{'1' * 64}",
            "lama_checkpoint_hash": f"sha256:{'2' * 64}",
            "seed": 17,
            "runtime": "recorded-golden-l",
            "device": "cpu",
        }
        execution = {
            "max_iterations": max_iterations,
            "kernel_scale": 0.015,
            "matting_process_size": [1024, 1024],
            "use_unblend": True,
            "fg_refine": True,
            "fg_refine_num_colors": fg_refine_num_colors,
            "bg_refine": True,
            "bg_refine_num_colors": 10,
        }
        analysis_pipeline = {
            "element_extractor_identity": "layerd-elements@0.1",
            "element_extractor_parameters": {"overlap_threshold": overlap_threshold},
            "ocr_identity": ocr_identity,
            "ocr_parameters": {},
            "classifier_identity": classifier_identity,
            "classifier_parameters": {"threshold": classifier_threshold},
        }
        identity_payload = {
            "source_artifact_id": source.artifact_id,
            "producer": producer,
            "execution": execution,
            "analysis_pipeline": analysis_pipeline,
        }
        run_identity = layerd_run_identity(identity_payload)
        pixel_sets = (
            {(x, y) for y in range(4) for x in range(4)},
            {(1, 1), (2, 1), (1, 2), (2, 2)},
        )
        layer_artifacts = []
        for index, pixels in enumerate(pixel_sets):
            layer_id = "layer:background" if index == 0 else "layer:foreground-0001"
            layer_artifacts.append(
                artifacts.import_bytes(
                    rgba_png(4, 4, pixels),
                    media_type="image/png",
                    kind=ArtifactKind.DERIVED,
                    provenance={
                        "derived_type": "rgba-layer",
                        "producer_family": "layerd",
                        "bundle_identity": "svm-layerd-output@0.4",
                        "run_identity": layer_run_override or run_identity,
                        "source_artifact_id": source.artifact_id,
                        "layer_id": layer_id,
                        "sequence_index": index,
                    },
                )
            )
        analysis_payload = {
            "schema_version": "svm-layerd-analysis-0.1",
            "source_artifact_id": source.artifact_id,
            "run_identity": run_identity,
            "canvas": {"width": analysis_canvas_width, "height": 4},
            "layers": [
                {
                    "layer_id": "layer:background",
                    "sequence_index": 0,
                    "rgba_artifact_id": layer_artifacts[0].artifact_id,
                    "alpha_bounds": [0, 0, 4, 4],
                    "alpha_pixel_count": 16,
                    "elements": [],
                },
                {
                    "layer_id": "layer:foreground-0001",
                    "sequence_index": 1,
                    "rgba_artifact_id": layer_artifacts[1].artifact_id,
                    "alpha_bounds": [1, 1, 3, 3],
                    "alpha_pixel_count": analysis_alpha_count,
                    "elements": [
                        {
                            "element_id": "candidate:element-0001",
                            "bounds": [1, 1, 3, 3],
                            "classification_candidate": {"label": label, "confidence": 0.75},
                        }
                    ],
                },
            ],
        }
        analysis = artifacts.import_bytes(
            canonical_bytes(analysis_payload),
            media_type="application/vnd.svm.layerd-analysis+json",
            kind=ArtifactKind.DERIVED,
            provenance={
                "derived_type": "layerd-analysis",
                "producer_family": "layerd",
                "bundle_identity": "svm-layerd-output@0.4",
                "run_identity": run_identity,
                "source_artifact_id": source.artifact_id,
            },
        )
        manifest_payload = {
            "schema_version": "svm-layerd-output-0.4",
            "source_artifact_id": source.artifact_id,
            "run_identity": run_identity,
            "producer": producer,
            "execution": execution,
            "analysis_pipeline": analysis_pipeline,
            "analysis_artifact_id": analysis.artifact_id,
            "analysis_content_hash": analysis.content_hash,
            "layers": [
                {
                    "layer_id": "layer:background" if index == 0 else "layer:foreground-0001",
                    "sequence_index": index,
                    "role": "background" if index == 0 else "foreground",
                    "rgba_artifact_id": artifact.artifact_id,
                    "rgba_content_hash": (
                        artifact.content_hash
                        if manifest_hash_valid or index == 0
                        else f"sha256:{'f' * 64}"
                    ),
                }
                for index, artifact in enumerate(layer_artifacts)
            ],
        }
        manifest = artifacts.import_bytes(
            canonical_bytes(manifest_payload),
            media_type="application/vnd.svm.layerd-output+json",
            kind=ArtifactKind.DERIVED,
            provenance={
                "derived_type": "layerd-manifest",
                "producer_family": "layerd",
                "bundle_identity": "svm-layerd-output@0.4",
                "run_identity": run_identity,
                "source_artifact_id": source.artifact_id,
            },
        )
        return artifacts, (
            source.artifact_id,
            manifest.artifact_id,
            analysis.artifact_id,
            *(artifact.artifact_id for artifact in layer_artifacts),
        )

    def request(self) -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=self.ids,
            options={"namespace": "golden-l"},
        )

    def test_golden_l_imports_raster_evidence_without_render_semantics(self) -> None:
        adapter = LayerDOutputAdapter()
        first = adapter.propose(self.request(), self.artifacts)
        second = adapter.propose(self.request(), self.artifacts)
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(first.report.metrics, {"layers": 2.0, "classification_candidates": 1.0})
        self.assertIn("candidate labels: text", first.notes)
        self.assertEqual(len(first.preview_artifacts), 5)
        self.assertEqual(self.store.get_document(self.store.head), self.document)

        revision = ProposalAcceptor().accept(self.store, first, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(len(accepted["entities"]), 2)
        self.assertEqual(accepted["presentation"]["render_stack"], [])
        self.assertEqual(accepted["presentation"]["styles"], [])
        self.assertEqual(accepted["construction"]["operations"], [])
        self.assertEqual(accepted["construction"]["output_bindings"], [])
        self.assertEqual(
            [entity["source_layer"]["order"] for entity in accepted["entities"]],
            [
                {"index": 0, "semantics": "svm-order:layerd-extraction@0.1"},
                {"index": 1, "semantics": "svm-order:layerd-extraction@0.1"},
            ],
        )
        self.assertTrue(
            all("text" not in entity["semantic_tags"] for entity in accepted["entities"])
        )

    def test_acceptance_reconstructs_artifact_bound_change(self) -> None:
        proposal = LayerDOutputAdapter().propose(self.request(), self.artifacts)
        change = proposal.transaction.changes[0]
        self.assertIsInstance(change, ImportRasterLayerEvidenceChange)
        forged_layer = replace(change.layers[1], order_index=7)
        forged_change = replace(change, layers=(change.layers[0], forged_layer))
        forged = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(forged_change,)),
        )
        with self.assertRaisesRegex(ProposalArtifactError, "does not match"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)
        self.assertEqual(self.store.head, proposal.base_revision_id)

    def test_malformed_classification_fails_closed(self) -> None:
        artifacts, ids = self._bundle(label="person")
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=ids,
            options={"namespace": "golden-l"},
        )
        with self.assertRaisesRegex(LayerDOutputError, "classification"):
            LayerDOutputAdapter().propose(request, artifacts)

    def test_legal_classification_tampering_breaks_manifest_binding(self) -> None:
        analysis = self.artifacts.get(self.ids[2])
        payload = json.loads(analysis.content)
        payload["layers"][1]["elements"][0]["classification_candidate"]["label"] = "image"
        tampered = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=analysis.media_type,
            kind=analysis.kind,
            provenance=analysis.provenance,
        )
        ids = (self.ids[0], self.ids[1], tampered.artifact_id, *self.ids[3:])
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=ids,
            options={"namespace": "golden-l"},
        )
        with self.assertRaisesRegex(LayerDOutputError, "bind the layer-analysis"):
            LayerDOutputAdapter().propose(request, self.artifacts)

    def test_hash_alpha_and_canvas_mismatches_fail_closed(self) -> None:
        cases = (
            ({"manifest_hash_valid": False}, "RGBA Artifact"),
            ({"analysis_alpha_count": 3}, "analysis record"),
            ({"analysis_canvas_width": 5}, "analysis record"),
        )
        for options, message in cases:
            with self.subTest(options=options):
                artifacts, ids = self._bundle(**options)
                request = AdapterRequest.from_store(
                    self.store,
                    self.store.head,
                    ("document",),
                    artifact_ids=ids,
                    options={"namespace": "golden-l"},
                )
                with self.assertRaisesRegex(LayerDOutputError, message):
                    LayerDOutputAdapter().propose(request, artifacts)

    def test_execution_configuration_changes_run_identity_and_mixed_run_fails(self) -> None:
        artifacts_two, ids_two = self._bundle(max_iterations=2)
        artifacts_five, ids_five = self._bundle(max_iterations=5)
        run_two = json.loads(artifacts_two.get(ids_two[1]).content)["run_identity"]
        run_five = json.loads(artifacts_five.get(ids_five[1]).content)["run_identity"]
        self.assertNotEqual(run_two, run_five)
        artifacts_classifier, ids_classifier = self._bundle(
            max_iterations=2,
            classifier_threshold=7.0,
        )
        run_classifier = json.loads(artifacts_classifier.get(ids_classifier[1]).content)[
            "run_identity"
        ]
        self.assertNotEqual(run_two, run_classifier)
        artifacts_colors, ids_colors = self._bundle(
            max_iterations=2,
            fg_refine_num_colors=8,
        )
        run_colors = json.loads(artifacts_colors.get(ids_colors[1]).content)["run_identity"]
        self.assertNotEqual(run_two, run_colors)
        artifacts_overlap, ids_overlap = self._bundle(
            max_iterations=2,
            overlap_threshold=0.5,
        )
        run_overlap = json.loads(artifacts_overlap.get(ids_overlap[1]).content)["run_identity"]
        self.assertNotEqual(run_two, run_overlap)

        mixed_artifacts, mixed_ids = self._bundle(max_iterations=2, layer_run_override=run_five)
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=mixed_ids,
            options={"namespace": "golden-l"},
        )
        with self.assertRaisesRegex(LayerDOutputError, "provenance"):
            LayerDOutputAdapter().propose(request, mixed_artifacts)

    def test_golden_l_profile_rejects_enabled_ocr(self) -> None:
        artifacts, ids = self._bundle(ocr_identity="east-ocr@0.1")
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=ids,
            options={"namespace": "golden-l"},
        )
        with self.assertRaisesRegex(LayerDOutputError, "analysis pipeline"):
            LayerDOutputAdapter().propose(request, artifacts)

    def test_golden_l_profile_rejects_gradient_aware_classifier(self) -> None:
        artifacts, ids = self._bundle(classifier_identity="gradient-aware-labeler@0.1")
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=ids,
            options={"namespace": "golden-l"},
        )
        with self.assertRaisesRegex(LayerDOutputError, "analysis pipeline"):
            LayerDOutputAdapter().propose(request, artifacts)

    def test_generic_wrapper_change_cannot_bypass_authority(self) -> None:
        proposal = LayerDOutputAdapter().propose(self.request(), self.artifacts)
        trusted_change = proposal.transaction.changes[0]

        class DelegatingChange:
            @property
            def references(self) -> object:
                return trusted_change.references

            def apply(self, document: dict[str, object]) -> None:
                trusted_change.apply(document)

        wrapped = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(DelegatingChange(),)),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "Unregistered Change type"):
            ProposalAcceptor().accept(self.store, wrapped, self.artifacts)

    def test_accepted_document_does_not_require_layerd_adapter(self) -> None:
        proposal = LayerDOutputAdapter().propose(self.request(), self.artifacts)
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        original_import = builtins.__import__

        def reject_layerd(name: str, *args: object, **kwargs: object) -> object:
            if "layerd" in name:
                raise AssertionError("Document validation imported the LayerD Adapter")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=reject_layerd):
            validate_document(json.loads(json.dumps(accepted)))

    def test_proposal_acceptor_remains_frozen_for_second_research_adapter(self) -> None:
        digest = hashlib.sha256((ROOT / "svm" / "proposals.py").read_bytes()).hexdigest()
        self.assertEqual(digest, PROPOSALS_SHA256)

    def test_run_identity_is_independent_of_consumer_adapter(self) -> None:
        proposal = LayerDOutputAdapter().propose(self.request(), self.artifacts)
        run_identity = proposal.generator.parameters["run_identity"]
        self.assertNotIn(LayerDOutputAdapter.adapter_version, run_identity)
        self.assertEqual(proposal.generator.parameters["bundle_identity"], "svm-layerd-output@0.4")


if __name__ == "__main__":
    unittest.main()
