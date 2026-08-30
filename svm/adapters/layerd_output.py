from __future__ import annotations

import hashlib
import json
import re
import struct
import zlib
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
from ..revisions import (
    ImportRasterLayerEvidenceChange,
    RasterLayerEvidence,
    Transaction,
)

MANIFEST_MEDIA_TYPE = "application/vnd.svm.layerd-output+json"
ANALYSIS_MEDIA_TYPE = "application/vnd.svm.layerd-analysis+json"
MANIFEST_SCHEMA = "svm-layerd-output-0.2"
ANALYSIS_SCHEMA = "svm-layerd-analysis-0.1"
RUN_IDENTITY = "svm-layerd-run@0.2"
BUNDLE_IDENTITY = "svm-layerd-output@0.2"
ADAPTER_IDENTITY = "svm-layerd-output-adapter@0.2"
RGBA_IDENTITY = "svm-png-rgba8-filter0@0.1"
MAX_LAYERS = 64
MAX_PNG_BYTES = 16 * 1024 * 1024
CLASSIFICATION_LABELS = {"text", "vector", "image", "unknown"}


class LayerDOutputError(ValueError):
    pass


def layerd_run_identity(payload: dict[str, Any]) -> str:
    producer = payload["producer"]
    digest = hashlib.sha256(
        canonical_bytes(
            {
                "identity": RUN_IDENTITY,
                "source_artifact_id": payload["source_artifact_id"],
                "repository": producer["repository"],
                "commit": producer["commit"],
                "birefnet_checkpoint_hash": producer["birefnet_checkpoint_hash"],
                "lama_checkpoint_hash": producer["lama_checkpoint_hash"],
                "seed": producer["seed"],
                "runtime": producer["runtime"],
                "device": producer["device"],
                "execution": payload["execution"],
                "analysis_pipeline": payload["analysis_pipeline"],
            }
        )
    ).hexdigest()
    return f"sha256:{digest}"


class _ResolvedBundle:
    def __init__(self, snapshots: dict[str, ArtifactSnapshot]):
        self.snapshots = snapshots

    def resolve(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        return tuple(self.snapshots[artifact_id] for artifact_id in artifact_ids)

    def resolve_as(
        self,
        artifact_ids: tuple[str, ...],
        *,
        kind: ArtifactKind,
        media_types: frozenset[str],
    ) -> tuple[ArtifactSnapshot, ...]:
        snapshots = self.resolve(artifact_ids)
        if any(
            snapshot.kind != kind or snapshot.media_type not in media_types
            for snapshot in snapshots
        ):
            raise LayerDOutputError("Resolved Artifact interpretation is invalid")
        return snapshots

    def resolve_reference(self, reference: dict[str, Any]) -> ArtifactSnapshot:
        snapshot = self.snapshots[reference["id"]]
        if snapshot.document_reference() != reference:
            raise LayerDOutputError("Resolved Artifact reference is inconsistent")
        return snapshot


def verify_import_raster_layer_evidence_change(
    change: ImportRasterLayerEvidenceChange,
    resolved: dict[str, ArtifactSnapshot],
) -> None:
    request = AdapterRequest(
        base_revision_id="revision:artifact-verification",
        document={"entities": []},
        scope=("document",),
        artifact_ids=tuple(sorted(resolved)),
        options={"namespace": change.namespace},
    )
    proposal = LayerDOutputAdapter().propose(request, _ResolvedBundle(resolved))
    expected = proposal.transaction.changes[0]
    if not isinstance(expected, ImportRasterLayerEvidenceChange) or expected != change:
        raise LayerDOutputError("LayerD evidence does not match resolved Artifact semantics")


class LayerDOutputAdapter:
    """Consume an immutable LayerD result bundle; never execute its models."""

    adapter_id = "adapter:layerd-output"
    adapter_version = "0.2"

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise LayerDOutputError("LayerD output scope must be empty or document")
        if set(request.options) - {"namespace"}:
            raise LayerDOutputError("Unknown LayerD output option")
        snapshots = artifacts.resolve(request.artifact_ids)
        manifest = _select_one(snapshots, MANIFEST_MEDIA_TYPE, "manifest")
        analysis = _select_one(snapshots, ANALYSIS_MEDIA_TYPE, "analysis")
        payload = _canonical_json(manifest, "Manifest")
        analysis_payload = _canonical_json(analysis, "Layer analysis")
        by_id = {snapshot.artifact_id: snapshot for snapshot in snapshots}
        _validate_bundle(payload, analysis_payload, manifest, analysis, by_id)
        namespace = _namespace(request, manifest)
        layers = tuple(
            RasterLayerEvidence(
                bundle_artifact_id=manifest.artifact_id,
                run_identity=payload["run_identity"],
                layer_id=layer["layer_id"],
                layer_artifact_id=layer["rgba_artifact_id"],
                order_index=layer["sequence_index"],
            )
            for layer in payload["layers"]
        )
        references = tuple(by_id[artifact_id].document_reference() for artifact_id in sorted(by_id))
        change = ImportRasterLayerEvidenceChange(
            layers=layers, references=references, namespace=namespace
        )
        producer = payload["producer"]
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="LayerD research output",
            engine_version=producer["commit"],
            parameters={
                "identity": ADAPTER_IDENTITY,
                "bundle_identity": BUNDLE_IDENTITY,
                "run_identity": payload["run_identity"],
                "manifest_artifact_id": manifest.artifact_id,
                "analysis_artifact_id": analysis.artifact_id,
                "rgba_identity": RGBA_IDENTITY,
                "namespace": namespace,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "generator": asdict(generator),
                    "manifest": payload,
                    "analysis": analysis_payload,
                    "references": references,
                    "change": asdict(change),
                }
            )
        ).hexdigest()[:16]
        classifications = sorted(
            {
                element["classification_candidate"]["label"]
                for layer in analysis_payload["layers"]
                for element in layer["elements"]
            }
        )
        return Proposal(
            proposal_id=f"proposal:layerd-output:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:layerd-output:{digest}",
                changes=(change,),
                message="Import snapshotted LayerD raster decomposition evidence",
            ),
            report=EvaluationReport(
                metrics={
                    "layers": float(len(layers)),
                    "classification_candidates": float(
                        sum(len(layer["elements"]) for layer in analysis_payload["layers"])
                    ),
                }
            ),
            preview=ProposalPreview(),
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
            notes=(
                "LayerD order and classification remain evidence only; "
                f"candidate labels: {', '.join(classifications)}"
            ),
        )


def _select_one(
    snapshots: tuple[ArtifactSnapshot, ...], media_type: str, label: str
) -> ArtifactSnapshot:
    matches = [
        snapshot
        for snapshot in snapshots
        if snapshot.kind == ArtifactKind.DERIVED and snapshot.media_type == media_type
    ]
    if len(matches) != 1:
        raise LayerDOutputError(f"Bundle requires exactly one Derived {label} Artifact")
    return matches[0]


def _canonical_json(snapshot: ArtifactSnapshot, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LayerDOutputError(f"{label} must be canonical UTF-8 JSON") from exc
    if not isinstance(payload, dict) or canonical_bytes(payload) != snapshot.content:
        raise LayerDOutputError(f"{label} must use canonical JSON encoding")
    return payload


def _namespace(request: AdapterRequest, manifest: ArtifactSnapshot) -> str:
    value = request.options.get("namespace")
    if value is None:
        value = f"layerd-{manifest.artifact_id[9:17]}"
    if not isinstance(value, str) or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value) is None:
        raise LayerDOutputError("LayerD namespace is invalid")
    return value


def _validate_bundle(
    payload: dict[str, Any],
    analysis_payload: dict[str, Any],
    manifest: ArtifactSnapshot,
    analysis: ArtifactSnapshot,
    by_id: dict[str, ArtifactSnapshot],
) -> None:
    if (
        set(payload)
        != {
            "schema_version",
            "source_artifact_id",
            "run_identity",
            "producer",
            "analysis_artifact_id",
            "analysis_content_hash",
            "execution",
            "analysis_pipeline",
            "layers",
        }
        or payload.get("schema_version") != MANIFEST_SCHEMA
    ):
        raise LayerDOutputError("Manifest fields or schema are invalid")
    producer = payload.get("producer")
    producer_fields = {
        "repository",
        "commit",
        "birefnet_checkpoint_hash",
        "lama_checkpoint_hash",
        "seed",
        "runtime",
        "device",
    }
    if not isinstance(producer, dict) or set(producer) != producer_fields:
        raise LayerDOutputError("LayerD producer fields are invalid")
    if producer["repository"] != "https://github.com/CyberAgentAILab/LayerD":
        raise LayerDOutputError("LayerD repository identity is invalid")
    if not _full_sha(producer["commit"]):
        raise LayerDOutputError("LayerD commit must be a full Git SHA")
    if not _content_hash(producer["birefnet_checkpoint_hash"]) or not _content_hash(
        producer["lama_checkpoint_hash"]
    ):
        raise LayerDOutputError("LayerD checkpoint hashes are invalid")
    if (
        not isinstance(producer["seed"], int)
        or isinstance(producer["seed"], bool)
        or not isinstance(producer["runtime"], str)
        or not producer["runtime"]
        or not isinstance(producer["device"], str)
        or not producer["device"]
    ):
        raise LayerDOutputError("LayerD execution provenance is invalid")
    _validate_execution(payload.get("execution"))
    _validate_analysis_pipeline(payload.get("analysis_pipeline"))
    if payload.get("run_identity") != layerd_run_identity(payload):
        raise LayerDOutputError("LayerD run identity is invalid")
    source_artifact_id = payload.get("source_artifact_id")
    if not isinstance(source_artifact_id, str):
        raise LayerDOutputError("LayerD source Artifact ID is invalid")
    source = by_id.get(source_artifact_id)
    if source is None or source.kind != ArtifactKind.REFERENCE:
        raise LayerDOutputError("LayerD source ReferenceArtifact is missing")
    if (
        payload.get("analysis_artifact_id") != analysis.artifact_id
        or payload.get("analysis_content_hash") != analysis.content_hash
    ):
        raise LayerDOutputError("Manifest does not bind the layer-analysis Artifact")
    _validate_descriptor(
        manifest,
        "layerd-manifest",
        payload["run_identity"],
        payload["source_artifact_id"],
    )
    _validate_descriptor(
        analysis,
        "layerd-analysis",
        payload["run_identity"],
        payload["source_artifact_id"],
    )
    layers = payload.get("layers")
    if not isinstance(layers, list) or not (1 <= len(layers) <= MAX_LAYERS):
        raise LayerDOutputError("LayerD bundle layer count is invalid")
    if [layer.get("sequence_index") for layer in layers if isinstance(layer, dict)] != list(
        range(len(layers))
    ):
        raise LayerDOutputError("LayerD sequence must be contiguous and start at background")
    analysis_layers = analysis_payload.get("layers")
    if (
        set(analysis_payload)
        != {"schema_version", "source_artifact_id", "run_identity", "canvas", "layers"}
        or analysis_payload.get("schema_version") != ANALYSIS_SCHEMA
        or analysis_payload.get("source_artifact_id") != payload["source_artifact_id"]
        or analysis_payload.get("run_identity") != payload["run_identity"]
        or not isinstance(analysis_layers, list)
        or len(analysis_layers) != len(layers)
    ):
        raise LayerDOutputError("Layer-analysis evidence is inconsistent")
    canvas = analysis_payload.get("canvas")
    if (
        not isinstance(canvas, dict)
        or set(canvas) != {"width", "height"}
        or any(not isinstance(canvas.get(key), int) or canvas[key] <= 0 for key in canvas)
    ):
        raise LayerDOutputError("Layer-analysis canvas is invalid")
    seen: set[str] = set()
    for index, (layer, layer_analysis) in enumerate(zip(layers, analysis_layers, strict=True)):
        _validate_layer(
            layer,
            layer_analysis,
            index,
            payload,
            canvas,
            by_id,
            seen,
        )
    expected_ids = {
        payload["source_artifact_id"],
        manifest.artifact_id,
        analysis.artifact_id,
        *(layer["rgba_artifact_id"] for layer in layers),
    }
    if set(by_id) != expected_ids:
        raise LayerDOutputError("LayerD bundle contains missing or unexpected Artifacts")


def _validate_layer(
    layer: Any,
    layer_analysis: Any,
    index: int,
    payload: dict[str, Any],
    canvas: dict[str, int],
    by_id: dict[str, ArtifactSnapshot],
    seen: set[str],
) -> None:
    fields = {"layer_id", "sequence_index", "role", "rgba_artifact_id", "rgba_content_hash"}
    if not isinstance(layer, dict) or set(layer) != fields:
        raise LayerDOutputError("Layer manifest record is invalid")
    layer_id = layer.get("layer_id")
    if (
        not isinstance(layer_id, str)
        or re.fullmatch(r"layer:[a-z0-9][a-z0-9_-]*", layer_id) is None
        or layer_id in seen
        or layer.get("sequence_index") != index
        or layer.get("role") != ("background" if index == 0 else "foreground")
    ):
        raise LayerDOutputError("Layer identity, role, or sequence is invalid")
    seen.add(layer_id)
    rgba_artifact_id = layer.get("rgba_artifact_id")
    if not isinstance(rgba_artifact_id, str):
        raise LayerDOutputError("Layer RGBA Artifact ID is invalid")
    snapshot = by_id.get(rgba_artifact_id)
    if (
        snapshot is None
        or snapshot.kind != ArtifactKind.DERIVED
        or snapshot.media_type != "image/png"
        or layer.get("rgba_content_hash") != snapshot.content_hash
    ):
        raise LayerDOutputError("Layer RGBA Artifact is missing or inconsistent")
    _validate_descriptor(
        snapshot,
        "rgba-layer",
        payload["run_identity"],
        payload["source_artifact_id"],
        layer_id=layer_id,
        sequence_index=index,
    )
    width, height, alpha_bounds, alpha_pixels = _decode_rgba_png(snapshot.content)
    analysis_fields = {
        "layer_id",
        "sequence_index",
        "rgba_artifact_id",
        "alpha_bounds",
        "alpha_pixel_count",
        "elements",
    }
    if (
        not isinstance(layer_analysis, dict)
        or set(layer_analysis) != analysis_fields
        or layer_analysis.get("layer_id") != layer_id
        or layer_analysis.get("sequence_index") != index
        or layer_analysis.get("rgba_artifact_id") != snapshot.artifact_id
        or layer_analysis.get("alpha_bounds") != list(alpha_bounds)
        or layer_analysis.get("alpha_pixel_count") != alpha_pixels
        or (width, height) != (canvas["width"], canvas["height"])
    ):
        raise LayerDOutputError("Layer-analysis record does not match RGBA evidence")
    elements = layer_analysis.get("elements")
    if not isinstance(elements, list):
        raise LayerDOutputError("Layer elements must be an array")
    element_ids: set[str] = set()
    for element in elements:
        if not isinstance(element, dict) or set(element) != {
            "element_id",
            "bounds",
            "classification_candidate",
        }:
            raise LayerDOutputError("Layer element evidence is invalid")
        element_id = element.get("element_id")
        bounds = element.get("bounds")
        classification = element.get("classification_candidate")
        if (
            not isinstance(element_id, str)
            or re.fullmatch(r"candidate:element-[0-9]{4,}", element_id) is None
            or element_id in element_ids
            or not _bounds(bounds, width, height)
            or not isinstance(classification, dict)
            or set(classification) != {"label", "confidence"}
            or classification.get("label") not in CLASSIFICATION_LABELS
            or not isinstance(classification.get("confidence"), (int, float))
            or isinstance(classification.get("confidence"), bool)
            or not 0.0 <= classification["confidence"] <= 1.0
        ):
            raise LayerDOutputError("Layer element classification evidence is invalid")
        element_ids.add(element_id)


def _validate_descriptor(
    snapshot: ArtifactSnapshot,
    derived_type: str,
    run_identity: str,
    source_artifact_id: str,
    **extra: Any,
) -> None:
    expected = {
        "derived_type": derived_type,
        "producer_family": "layerd",
        "bundle_identity": BUNDLE_IDENTITY,
        "run_identity": run_identity,
        "source_artifact_id": source_artifact_id,
        **extra,
    }
    if snapshot.provenance != expected:
        raise LayerDOutputError(f"{derived_type} provenance is inconsistent")


def _validate_execution(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "max_iterations",
        "kernel_scale",
        "matting_process_size",
        "use_unblend",
        "fg_refine",
        "bg_refine",
    }:
        raise LayerDOutputError("LayerD execution contract is invalid")
    size = value["matting_process_size"]
    if (
        not isinstance(value["max_iterations"], int)
        or isinstance(value["max_iterations"], bool)
        or value["max_iterations"] <= 0
        or not isinstance(value["kernel_scale"], (int, float))
        or isinstance(value["kernel_scale"], bool)
        or not 0 < value["kernel_scale"] <= 1
        or not isinstance(size, list)
        or len(size) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in size)
        or any(
            not isinstance(value[key], bool) for key in ("use_unblend", "fg_refine", "bg_refine")
        )
    ):
        raise LayerDOutputError("LayerD execution parameters are invalid")


def _validate_analysis_pipeline(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "element_extractor_identity",
        "classifier_identity",
        "classifier_parameters",
    }:
        raise LayerDOutputError("LayerD analysis pipeline contract is invalid")
    identity_pattern = r"[a-z0-9][a-z0-9._-]*@[0-9]+\.[0-9]+"
    if (
        not isinstance(value["element_extractor_identity"], str)
        or re.fullmatch(identity_pattern, value["element_extractor_identity"]) is None
        or not isinstance(value["classifier_identity"], str)
        or re.fullmatch(identity_pattern, value["classifier_identity"]) is None
        or not isinstance(value["classifier_parameters"], dict)
    ):
        raise LayerDOutputError("LayerD analysis pipeline identity is invalid")


def _full_sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _content_hash(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _bounds(value: Any, width: int, height: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
        and 0 <= value[0] < value[2] <= width
        and 0 <= value[1] < value[3] <= height
    )


def _decode_rgba_png(content: bytes) -> tuple[int, int, tuple[int, int, int, int], int]:
    if len(content) > MAX_PNG_BYTES or not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise LayerDOutputError("Layer must be a bounded PNG")
    offset = 8
    width = height = 0
    compressed = bytearray()
    saw_iend = False
    while offset + 12 <= len(content):
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(content):
            raise LayerDOutputError("PNG chunk is truncated")
        data = content[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", content[offset + 8 + length : end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            raise LayerDOutputError("PNG chunk CRC is invalid")
        if chunk_type == b"IHDR":
            if length != 13:
                raise LayerDOutputError("PNG IHDR is invalid")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            if (
                width <= 0
                or height <= 0
                or depth != 8
                or color != 6
                or compression != 0
                or filtering != 0
                or interlace != 0
            ):
                raise LayerDOutputError("Layer PNG must be non-interlaced 8-bit RGBA")
        elif chunk_type == b"IDAT":
            compressed.extend(data)
        elif chunk_type == b"IEND":
            saw_iend = True
            offset = end
            break
        offset = end
    if not saw_iend or offset != len(content) or width * height > 16_777_216:
        raise LayerDOutputError("PNG structure or dimensions are invalid")
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise LayerDOutputError("PNG image data is invalid") from exc
    stride = width * 4
    if len(raw) != height * (stride + 1):
        raise LayerDOutputError("PNG sample length is invalid")
    xs: list[int] = []
    ys: list[int] = []
    for y in range(height):
        row = raw[y * (stride + 1) : (y + 1) * (stride + 1)]
        if row[0] != 0:
            raise LayerDOutputError("Layer PNG requires canonical filter-0 scanlines")
        for x in range(width):
            if row[1 + x * 4 + 3] != 0:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise LayerDOutputError("Layer PNG must contain non-transparent pixels")
    return width, height, (min(xs), min(ys), max(xs) + 1, max(ys) + 1), len(xs)
