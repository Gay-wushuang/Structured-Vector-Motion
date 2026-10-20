from __future__ import annotations

import hashlib
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.fogleman_primitive_svg import (
    NORMALIZATION_IDENTITY,
    normalize_primitive_svg,
)
from .adapters.svg_import import SVGImportAdapter
from .artifacts import ArtifactKind, ArtifactStore
from .evaluator import Evaluator, Quality, canonical_bytes
from .external.fogleman_primitive import (
    RUNNER_IDENTITY,
    PrimitiveRunConfig,
    producer_record,
    run_primitive,
)
from .proposals import AdapterRequest, ProposalAcceptor
from .renderers import SVGRenderer, SVGRenderOptions
from .revisions import RevisionStore
from .scene import build_evaluated_scene

BUNDLE_SCHEMA = "svm-fogleman-primitive-run-0.1"
BUNDLE_IDENTITY = "svm-fogleman-primitive-toolchain@0.1"


class PrimitiveBundleError(ValueError):
    pass


@dataclass(frozen=True)
class PrimitiveBundle:
    files: dict[str, bytes]
    summary: dict[str, Any]


def run_primitive_toolchain(
    document: dict[str, Any],
    source_path: Path,
    executable: Path,
    engine_commit: str,
    config: PrimitiveRunConfig,
    namespace: str,
) -> PrimitiveBundle:
    """Run, snapshot, import, accept, and render one Primitive result."""

    started = time.perf_counter()
    if not namespace or not namespace.replace("-", "").isalnum():
        raise PrimitiveBundleError("Primitive namespace must contain letters, digits, or hyphens")
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise PrimitiveBundleError(f"Cannot read Primitive source PNG: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="svm-primitive-source-") as temporary_directory:
        frozen_source = Path(temporary_directory) / "source.png"
        frozen_source.write_bytes(source_bytes)
        execution = run_primitive(executable, frozen_source, engine_commit, config)
    normalized = normalize_primitive_svg(execution.raw_svg)

    artifacts = ArtifactStore()
    source = artifacts.import_bytes(
        source_bytes,
        media_type="image/png",
        kind=ArtifactKind.REFERENCE,
        provenance={"source_name": source_path.name},
    )
    producer = producer_record(execution)
    raw_svg = artifacts.import_bytes(
        execution.raw_svg,
        media_type="image/svg+xml",
        kind=ArtifactKind.DERIVED,
        provenance={
            "derived_type": "fogleman-primitive-raw-svg",
            "runner_identity": RUNNER_IDENTITY,
            "source_artifact_id": source.artifact_id,
            "producer": producer,
            "parameters": execution.parameters,
        },
    )
    preview = artifacts.import_bytes(
        execution.preview_png,
        media_type="image/png",
        kind=ArtifactKind.DERIVED,
        provenance={
            "derived_type": "fogleman-primitive-native-preview",
            "runner_identity": RUNNER_IDENTITY,
            "source_artifact_id": source.artifact_id,
            "raw_svg_artifact_id": raw_svg.artifact_id,
            "producer": producer,
            "parameters": execution.parameters,
        },
    )
    normalized_provenance = {
        "derived_type": "fogleman-primitive-normalized-svg",
        "normalization_identity": NORMALIZATION_IDENTITY,
        "runner_identity": RUNNER_IDENTITY,
        "source_artifact_id": source.artifact_id,
        "source_content_hash": source.content_hash,
        "raw_svg_artifact_id": raw_svg.artifact_id,
        "raw_svg_content_hash": raw_svg.content_hash,
        "native_preview_artifact_id": preview.artifact_id,
        "producer": producer,
        "parameters": execution.parameters,
    }
    normalized_svg = artifacts.import_bytes(
        normalized.content,
        media_type="image/svg+xml",
        kind=ArtifactKind.REFERENCE,
        provenance=normalized_provenance,
    )

    result = _accept_and_render(
        document,
        artifacts,
        normalized_svg.artifact_id,
        namespace,
        normalized.width,
        normalized.height,
    )
    document_bytes = _document_bytes(result["document"])
    svg_bytes = result["svg"]
    files = {
        "source.png": source_bytes,
        "primitive.svg": execution.raw_svg,
        "primitive.png": execution.preview_png,
        "normalized.svg": normalized.content,
        "accepted.svm.json": document_bytes,
        "svm.svg": svg_bytes,
    }
    manifest = {
        "schema_version": BUNDLE_SCHEMA,
        "identity": BUNDLE_IDENTITY,
        "producer": producer,
        "randomness_boundary": (
            "upstream fitting is clock-seeded; deterministic replay begins at primitive.svg"
        ),
        "command": list(execution.command),
        "parameters": execution.parameters,
        "namespace": namespace,
        "normalization_identity": NORMALIZATION_IDENTITY,
        "base_document_sha256": _sha256(canonical_bytes(document)),
        "artifacts": {
            "source": _artifact_record(source),
            "raw_svg": _artifact_record(raw_svg),
            "native_preview": _artifact_record(preview),
            "normalized_svg": {
                **_artifact_record(normalized_svg),
                "provenance": normalized_provenance,
            },
        },
        "acceptance": {
            "base_revision_id": result["base_revision_id"],
            "proposal_id": result["proposal_id"],
            "transaction_id": result["transaction_id"],
            "revision_id": result["revision_id"],
            "imported_entities": result["imported_entities"],
        },
        "render": {
            "quality": Quality.FINAL.value,
            "width": normalized.width,
            "height": normalized.height,
            "view_box": [0.0, 0.0, normalized.width, normalized.height],
            "entity_count": result["entity_count"],
        },
        "files": {name: _file_record(content) for name, content in files.items()},
        "performance": {
            "primitive_seconds": float(format(execution.elapsed_seconds, ".6f")),
            "total_seconds": float(format(time.perf_counter() - started, ".6f")),
        },
        "replay": {
            "deterministic_from": "primitive.svg",
            "accepted_document_sha256": _sha256(document_bytes),
            "svm_svg_sha256": _sha256(svg_bytes),
        },
    }
    manifest_bytes = canonical_bytes(manifest)
    files["run-manifest.json"] = manifest_bytes
    summary = {
        "schema_version": BUNDLE_SCHEMA,
        "source_artifact_id": source.artifact_id,
        "raw_svg_artifact_id": raw_svg.artifact_id,
        "normalized_svg_artifact_id": normalized_svg.artifact_id,
        "proposal_id": result["proposal_id"],
        "revision_id": result["revision_id"],
        "imported_entities": result["imported_entities"],
        "primitive_seconds": manifest["performance"]["primitive_seconds"],
        "total_seconds": manifest["performance"]["total_seconds"],
        "replay_boundary": "primitive.svg",
    }
    return PrimitiveBundle(files, summary)


def write_primitive_bundle(bundle: PrimitiveBundle, output_directory: Path) -> None:
    if output_directory.exists():
        raise PrimitiveBundleError("Primitive output directory must not already exist")
    output_directory.mkdir(parents=True)
    for name, content in bundle.files.items():
        (output_directory / name).write_bytes(content)


def replay_primitive_bundle(document: dict[str, Any], bundle_directory: Path) -> dict[str, Any]:
    manifest_path = bundle_directory / "run-manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrimitiveBundleError(f"Cannot read Primitive run manifest: {exc}") from exc
    if not isinstance(manifest, dict) or canonical_bytes(manifest) != manifest_bytes:
        raise PrimitiveBundleError("Primitive run manifest must be canonical JSON")
    if (
        manifest.get("schema_version") != BUNDLE_SCHEMA
        or manifest.get("identity") != BUNDLE_IDENTITY
    ):
        raise PrimitiveBundleError("Unsupported Primitive run manifest")
    if manifest.get("base_document_sha256") != _sha256(canonical_bytes(document)):
        raise PrimitiveBundleError("Primitive replay base Document hash mismatch")

    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {
        "source.png",
        "primitive.svg",
        "primitive.png",
        "normalized.svg",
        "accepted.svm.json",
        "svm.svg",
    }:
        raise PrimitiveBundleError("Primitive manifest file set is invalid")
    loaded: dict[str, bytes] = {}
    for name, record in files.items():
        try:
            content = (bundle_directory / name).read_bytes()
        except OSError as exc:
            raise PrimitiveBundleError(f"Cannot read Primitive replay file {name}: {exc}") from exc
        if record != _file_record(content):
            raise PrimitiveBundleError(f"Primitive replay file hash mismatch: {name}")
        loaded[name] = content

    normalized = normalize_primitive_svg(loaded["primitive.svg"])
    if normalized.content != loaded["normalized.svg"]:
        raise PrimitiveBundleError("Primitive replay normalization mismatch")
    artifact_records = manifest.get("artifacts")
    if not isinstance(artifact_records, dict) or set(artifact_records) != {
        "source",
        "raw_svg",
        "native_preview",
        "normalized_svg",
    }:
        raise PrimitiveBundleError("Primitive manifest Artifact set is invalid")
    expected_records = {
        "source": _byte_artifact_record(loaded["source.png"], ArtifactKind.REFERENCE, "image/png"),
        "raw_svg": _byte_artifact_record(
            loaded["primitive.svg"], ArtifactKind.DERIVED, "image/svg+xml"
        ),
        "native_preview": _byte_artifact_record(
            loaded["primitive.png"], ArtifactKind.DERIVED, "image/png"
        ),
        "normalized_svg": _byte_artifact_record(
            loaded["normalized.svg"], ArtifactKind.REFERENCE, "image/svg+xml"
        ),
    }
    for name in ("source", "raw_svg", "native_preview"):
        if artifact_records[name] != expected_records[name]:
            raise PrimitiveBundleError(f"Primitive replay Artifact identity mismatch: {name}")
    normalized_record = artifact_records["normalized_svg"]
    if not isinstance(normalized_record, dict):
        raise PrimitiveBundleError("Primitive normalized SVG Artifact record is invalid")
    provenance = normalized_record.get("provenance")
    if not isinstance(provenance, dict):
        raise PrimitiveBundleError("Primitive normalized SVG provenance is invalid")
    if {
        key: normalized_record.get(key)
        for key in ("artifact_id", "content_hash", "kind", "media_type")
    } != expected_records["normalized_svg"]:
        raise PrimitiveBundleError("Primitive normalized SVG Artifact identity mismatch")
    if (
        set(provenance)
        != {
            "derived_type",
            "normalization_identity",
            "runner_identity",
            "source_artifact_id",
            "source_content_hash",
            "raw_svg_artifact_id",
            "raw_svg_content_hash",
            "native_preview_artifact_id",
            "producer",
            "parameters",
        }
        or provenance.get("derived_type") != "fogleman-primitive-normalized-svg"
        or provenance.get("normalization_identity") != NORMALIZATION_IDENTITY
        or provenance.get("runner_identity") != RUNNER_IDENTITY
        or provenance.get("source_artifact_id") != expected_records["source"]["artifact_id"]
        or provenance.get("source_content_hash") != expected_records["source"]["content_hash"]
        or provenance.get("raw_svg_artifact_id") != expected_records["raw_svg"]["artifact_id"]
        or provenance.get("raw_svg_content_hash") != expected_records["raw_svg"]["content_hash"]
        or provenance.get("native_preview_artifact_id")
        != expected_records["native_preview"]["artifact_id"]
        or provenance.get("producer") != manifest.get("producer")
        or provenance.get("parameters") != manifest.get("parameters")
    ):
        raise PrimitiveBundleError("Primitive normalized SVG provenance linkage mismatch")
    artifacts = ArtifactStore()
    snapshot = artifacts.import_bytes(
        loaded["normalized.svg"],
        media_type="image/svg+xml",
        kind=ArtifactKind.REFERENCE,
        provenance=provenance,
    )
    if _artifact_record(snapshot) != expected_records["normalized_svg"]:
        raise PrimitiveBundleError("Primitive normalized SVG descriptor mismatch")

    result = _accept_and_render(
        document,
        artifacts,
        snapshot.artifact_id,
        manifest["namespace"],
        normalized.width,
        normalized.height,
    )
    acceptance = manifest.get("acceptance")
    expected_acceptance = {
        "base_revision_id": result["base_revision_id"],
        "proposal_id": result["proposal_id"],
        "transaction_id": result["transaction_id"],
        "revision_id": result["revision_id"],
        "imported_entities": result["imported_entities"],
    }
    if acceptance != expected_acceptance:
        raise PrimitiveBundleError("Primitive replay Proposal or Revision identity mismatch")
    document_bytes = _document_bytes(result["document"])
    svg_bytes = result["svg"]
    if document_bytes != loaded["accepted.svm.json"] or svg_bytes != loaded["svm.svg"]:
        raise PrimitiveBundleError("Primitive replay output bytes mismatch")
    expected_render = {
        "quality": Quality.FINAL.value,
        "width": normalized.width,
        "height": normalized.height,
        "view_box": [0.0, 0.0, normalized.width, normalized.height],
        "entity_count": result["entity_count"],
    }
    if manifest.get("render") != expected_render:
        raise PrimitiveBundleError("Primitive replay render record mismatch")
    if manifest.get("replay") != {
        "deterministic_from": "primitive.svg",
        "accepted_document_sha256": _sha256(document_bytes),
        "svm_svg_sha256": _sha256(svg_bytes),
    }:
        raise PrimitiveBundleError("Primitive replay digest record mismatch")
    return {
        "replayed": True,
        "proposal_id": result["proposal_id"],
        "revision_id": result["revision_id"],
        "accepted_document_sha256": _sha256(document_bytes),
        "svm_svg_sha256": _sha256(svg_bytes),
    }


def _accept_and_render(
    document: dict[str, Any],
    artifacts: ArtifactStore,
    normalized_artifact_id: str,
    namespace: str,
    width: float,
    height: float,
) -> dict[str, Any]:
    store = RevisionStore.create(document)
    base_revision_id = store.head
    if base_revision_id is None:
        raise PrimitiveBundleError("Revision Store did not create an initial head")
    request = AdapterRequest.from_store(
        store,
        base_revision_id,
        ("document",),
        artifact_ids=(normalized_artifact_id,),
        options={"namespace": namespace},
    )
    proposal = SVGImportAdapter().propose(request, artifacts)
    revision = ProposalAcceptor().accept(store, proposal, artifacts)
    accepted = store.get_document(revision.revision_id)
    scene = build_evaluated_scene(accepted, Evaluator(accepted), Quality.FINAL)
    svg = SVGRenderer(
        SVGRenderOptions(
            width=_integer_dimension(width, "width"),
            height=_integer_dimension(height, "height"),
            view_box=(0.0, 0.0, width, height),
        )
    ).render(scene)
    return {
        "base_revision_id": base_revision_id,
        "proposal_id": proposal.proposal_id,
        "transaction_id": proposal.transaction.transaction_id,
        "revision_id": revision.revision_id,
        "document": accepted,
        "svg": svg.encode("utf-8"),
        "entity_count": len(scene.entities),
        "imported_entities": len(accepted["entities"]) - len(document["entities"]),
    }


def _integer_dimension(value: float, name: str) -> int:
    rounded = round(value)
    if value != rounded or rounded <= 0:
        raise PrimitiveBundleError(f"Primitive output {name} must be a positive integer")
    return rounded


def _artifact_record(snapshot: Any) -> dict[str, str]:
    return {
        "artifact_id": snapshot.artifact_id,
        "content_hash": snapshot.content_hash,
        "kind": snapshot.kind.value,
        "media_type": snapshot.media_type,
    }


def _byte_artifact_record(content: bytes, kind: ArtifactKind, media_type: str) -> dict[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    return {
        "artifact_id": f"artifact:{digest}",
        "content_hash": f"sha256:{digest}",
        "kind": kind.value,
        "media_type": media_type,
    }


def _file_record(content: bytes) -> dict[str, int | str]:
    return {"sha256": _sha256(content), "bytes": len(content)}


def _document_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
