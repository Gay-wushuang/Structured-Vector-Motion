from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactResolver, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import AppendSceneFragmentChange, Transaction
from .svg_import import SVGImportError, SVGNormalizer

MANIFEST_MEDIA_TYPE = "application/vnd.svm.layerpeeler-output+json"
MANIFEST_SCHEMA = "svm-layerpeeler-output-0.1"
ADAPTER_IDENTITY = "svm-layerpeeler-output@0.1"
MAX_LAYERS = 128


class LayerPeelerOutputError(ValueError):
    pass


def layerpeeler_run_identity(payload: dict[str, Any]) -> str:
    producer = payload["producer"]
    digest = hashlib.sha256(
        canonical_bytes(
            {
                "identity": ADAPTER_IDENTITY,
                "source_artifact_id": payload["source_artifact_id"],
                "repository": producer["repository"],
                "commit": producer["commit"],
                "model_id": producer["model_id"],
                "checkpoint_hash": producer["checkpoint_hash"],
                "seed": producer["seed"],
            }
        )
    ).hexdigest()
    return f"sha256:{digest}"


class LayerPeelerOutputAdapter:
    """Consume snapshotted LayerPeeler output; never execute the research model."""

    adapter_id = "adapter:layerpeeler-output"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise LayerPeelerOutputError("LayerPeeler output scope must be empty or document")
        if set(request.options) - {"namespace"}:
            raise LayerPeelerOutputError("Unknown LayerPeeler output option")
        snapshots = artifacts.resolve(request.artifact_ids)
        manifest = self._select_manifest(snapshots)
        payload = self._manifest_payload(manifest)
        by_id = {snapshot.artifact_id: snapshot for snapshot in snapshots}
        self._validate_bundle(payload, manifest, by_id)
        namespace = self._namespace(request, manifest)

        entities: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []
        bindings: list[dict[str, Any]] = []
        styles: list[dict[str, Any]] = []
        render_entries: list[str] = []
        normalizer = SVGNormalizer()
        for layer in payload["layers"]:
            snapshot = by_id[layer["svg_artifact_id"]]
            try:
                shapes = normalizer.normalize(
                    snapshot, f"{namespace}-{layer['layer_id'].removeprefix('layer:')}"
                )
            except SVGImportError as exc:
                raise LayerPeelerOutputError(
                    f"Layer {layer['layer_id']} contains unsupported SVG: {exc}"
                ) from exc
            if not shapes:
                raise LayerPeelerOutputError(f"Layer {layer['layer_id']} contains no shapes")
            for shape in shapes:
                entity = shape.entity
                entity["name"] = f"{layer['layer_id']} / {entity['name']}"
                entity["semantic_tags"] = ["research-layer", "layerpeeler-output"]
                entity["source_layer"] = {
                    "manifest_artifact_id": manifest.artifact_id,
                    "run_identity": payload["run_identity"],
                    "layer_id": layer["layer_id"],
                    "layer_svg_artifact_id": snapshot.artifact_id,
                    "z_index": layer["z_index"],
                }
                entities.append(entity)
                operations.append(shape.operation)
                bindings.append(shape.binding)
                styles.append(shape.style)
                render_entries.append(entity["id"])

        references = tuple(by_id[artifact_id].document_reference() for artifact_id in sorted(by_id))
        change = AppendSceneFragmentChange(
            entities=tuple(entities),
            operations=tuple(operations),
            output_bindings=tuple(bindings),
            render_entries=tuple(render_entries),
            styles=tuple(styles),
            references=references,
        )
        producer = payload["producer"]
        parameters = {
            "identity": ADAPTER_IDENTITY,
            "namespace": namespace,
            "repository": producer["repository"],
            "commit": producer["commit"],
            "model_id": producer["model_id"],
            "checkpoint_hash": producer["checkpoint_hash"],
            "seed": producer["seed"],
            "manifest_artifact_id": manifest.artifact_id,
            "svg_normalization_identity": normalizer.identity,
        }
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="LayerPeeler research output",
            engine_version=producer["commit"],
            parameters=parameters,
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "generator": asdict(generator),
                    "manifest": payload,
                    "references": references,
                    "change": asdict(change),
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:layerpeeler-output:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:layerpeeler-output:{digest}",
                changes=(change,),
                message="Import snapshotted LayerPeeler layered SVG output",
            ),
            report=EvaluationReport(
                metrics={"layers": float(len(payload["layers"])), "shapes": float(len(entities))}
            ),
            preview=ProposalPreview(proposed_render_stack=tuple(render_entries)),
            preview_artifacts=tuple(
                PreviewArtifact(
                    artifact_id=snapshot.artifact_id,
                    content_hash=snapshot.content_hash,
                    media_type=snapshot.media_type,
                )
                for snapshot in snapshots
            ),
            required_artifact_ids=tuple(sorted(by_id)),
            confidence=None,
            notes="Untrusted research output normalized through existing SVG import semantics",
        )

    @staticmethod
    def _select_manifest(snapshots: tuple[ArtifactSnapshot, ...]) -> ArtifactSnapshot:
        matches = [
            snapshot
            for snapshot in snapshots
            if snapshot.kind == ArtifactKind.DERIVED and snapshot.media_type == MANIFEST_MEDIA_TYPE
        ]
        if len(matches) != 1:
            raise LayerPeelerOutputError("Bundle requires exactly one Derived manifest Artifact")
        return matches[0]

    @staticmethod
    def _manifest_payload(manifest: ArtifactSnapshot) -> dict[str, Any]:
        try:
            payload = json.loads(manifest.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LayerPeelerOutputError("Manifest must be canonical UTF-8 JSON") from exc
        if not isinstance(payload, dict) or canonical_bytes(payload) != manifest.content:
            raise LayerPeelerOutputError("Manifest must use canonical JSON encoding")
        return payload

    @staticmethod
    def _validate_bundle(
        payload: dict[str, Any], manifest: ArtifactSnapshot, by_id: dict[str, ArtifactSnapshot]
    ) -> None:
        if set(payload) != {
            "schema_version",
            "source_artifact_id",
            "run_identity",
            "producer",
            "layers",
        }:
            raise LayerPeelerOutputError("Manifest fields are invalid")
        if payload["schema_version"] != MANIFEST_SCHEMA:
            raise LayerPeelerOutputError("Unsupported LayerPeeler output manifest schema")
        producer = payload["producer"]
        if not isinstance(producer, dict) or set(producer) != {
            "repository",
            "commit",
            "model_id",
            "checkpoint_hash",
            "seed",
        }:
            raise LayerPeelerOutputError("Manifest producer fields are invalid")
        if producer["repository"] != "https://github.com/kingnobro/LayerPeeler":
            raise LayerPeelerOutputError("Manifest repository is not the LayerPeeler upstream")
        if re.fullmatch(r"[0-9a-f]{40}", producer["commit"] or "") is None:
            raise LayerPeelerOutputError("Manifest commit must be a full Git SHA")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", producer["checkpoint_hash"] or "") is None:
            raise LayerPeelerOutputError("Manifest checkpoint hash is invalid")
        if not isinstance(producer["model_id"], str) or not producer["model_id"]:
            raise LayerPeelerOutputError("Manifest model ID is invalid")
        if type(producer["seed"]) is not int or producer["seed"] < 0:
            raise LayerPeelerOutputError("Manifest seed is invalid")
        source = by_id.get(payload["source_artifact_id"])
        if source is None or source.kind != ArtifactKind.REFERENCE:
            raise LayerPeelerOutputError("Manifest source must be a supplied ReferenceArtifact")
        expected_run_identity = layerpeeler_run_identity(payload)
        if payload["run_identity"] != expected_run_identity:
            raise LayerPeelerOutputError("Manifest run identity is invalid")
        if (
            manifest.provenance.get("derived_type") != "layerpeeler-output-manifest"
            or manifest.provenance.get("source_artifact_id") != source.artifact_id
            or manifest.provenance.get("manifest_identity") != ADAPTER_IDENTITY
            or manifest.provenance.get("run_identity") != expected_run_identity
        ):
            raise LayerPeelerOutputError("Manifest provenance is inconsistent")
        layers = payload["layers"]
        if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_LAYERS:
            raise LayerPeelerOutputError("Manifest must contain between 1 and 128 layers")
        if [layer.get("z_index") for layer in layers if isinstance(layer, dict)] != list(
            range(len(layers))
        ):
            raise LayerPeelerOutputError("Layers must have contiguous back-to-front z_index values")
        seen_ids: set[str] = set()
        expected_artifacts = {manifest.artifact_id, source.artifact_id}
        for layer in layers:
            if not isinstance(layer, dict) or set(layer) != {
                "layer_id",
                "z_index",
                "svg_artifact_id",
                "svg_content_hash",
            }:
                raise LayerPeelerOutputError("Layer descriptor fields are invalid")
            layer_id = layer["layer_id"]
            if re.fullmatch(r"layer:[a-z0-9][a-z0-9_-]*", layer_id or "") is None:
                raise LayerPeelerOutputError("Layer ID is invalid")
            if layer_id in seen_ids:
                raise LayerPeelerOutputError("Layer IDs must be unique")
            seen_ids.add(layer_id)
            artifact = by_id.get(layer["svg_artifact_id"])
            if (
                artifact is None
                or artifact.kind != ArtifactKind.DERIVED
                or artifact.media_type not in {"image/svg+xml", "application/svg+xml"}
                or artifact.content_hash != layer["svg_content_hash"]
            ):
                raise LayerPeelerOutputError(f"Layer {layer_id} SVG Artifact is invalid")
            provenance = artifact.provenance
            if (
                provenance.get("derived_type") != "layer-svg"
                or provenance.get("source_artifact_id") != source.artifact_id
                or provenance.get("manifest_identity") != ADAPTER_IDENTITY
                or provenance.get("run_identity") != expected_run_identity
                or provenance.get("repository") != producer["repository"]
                or provenance.get("commit") != producer["commit"]
                or provenance.get("model_id") != producer["model_id"]
                or provenance.get("checkpoint_hash") != producer["checkpoint_hash"]
                or provenance.get("seed") != producer["seed"]
                or provenance.get("layer_id") != layer_id
                or provenance.get("z_index") != layer["z_index"]
            ):
                raise LayerPeelerOutputError(f"Layer {layer_id} provenance is inconsistent")
            expected_artifacts.add(artifact.artifact_id)
        if set(by_id) != expected_artifacts:
            raise LayerPeelerOutputError("Bundle contains missing or undeclared Artifacts")

    @staticmethod
    def _namespace(request: AdapterRequest, manifest: ArtifactSnapshot) -> str:
        namespace = request.options.get("namespace", manifest.artifact_id[-12:])
        if not isinstance(namespace, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]*", namespace) is None:
            raise LayerPeelerOutputError(
                "Namespace must contain lowercase letters, digits, hyphens"
            )
        return namespace
