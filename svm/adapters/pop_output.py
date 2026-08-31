from __future__ import annotations

import hashlib
import json
import math
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
from ..revisions import (
    AppendSceneFragmentChange,
    ImportPrimitiveSequenceChange,
    Transaction,
)

OUTPUT_MEDIA_TYPE = "application/vnd.svm.pop-output+json"
OUTPUT_SCHEMA = "svm-pop-output-0.1"
OUTPUT_IDENTITY = "svm-pop-output@0.1"
RUN_IDENTITY = "svm-pop-run@0.1"
ADAPTER_IDENTITY = "svm-pop-output-adapter@0.1"
UPSTREAM_REPOSITORY = "https://github.com/wonderfulearth/primitive-operation-painter"
MAX_PRIMITIVES = 512


class POPOutputError(ValueError):
    pass


def pop_run_identity(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_bytes(
            {
                "identity": RUN_IDENTITY,
                "input": payload["input"],
                "producer": payload["producer"],
                "canvas": payload["canvas"],
            }
        )
    ).hexdigest()
    return f"sha256:{digest}"


class _ResolvedOutput:
    def __init__(self, snapshot: ArtifactSnapshot):
        self.snapshot = snapshot

    def resolve(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        if artifact_ids != (self.snapshot.artifact_id,):
            raise POPOutputError("POP verification requires its exact output Artifact")
        return (self.snapshot,)

    def resolve_as(
        self,
        artifact_ids: tuple[str, ...],
        *,
        kind: ArtifactKind,
        media_types: frozenset[str],
    ) -> tuple[ArtifactSnapshot, ...]:
        snapshots = self.resolve(artifact_ids)
        if self.snapshot.kind != kind or self.snapshot.media_type not in media_types:
            raise POPOutputError("Resolved POP Artifact interpretation is invalid")
        return snapshots

    def resolve_reference(self, reference: dict[str, Any]) -> ArtifactSnapshot:
        if self.snapshot.document_reference() != reference:
            raise POPOutputError("Resolved POP Artifact reference is inconsistent")
        return self.snapshot


def verify_import_primitive_sequence_change(
    change: ImportPrimitiveSequenceChange, resolved: dict[str, ArtifactSnapshot]
) -> None:
    if len(resolved) != 1:
        raise POPOutputError("POP import requires exactly one resolved output Artifact")
    snapshot = next(iter(resolved.values()))
    request = AdapterRequest(
        base_revision_id="revision:artifact-verification",
        document={"entities": [], "construction": {"operations": []}},
        scope=("document",),
        artifact_ids=(snapshot.artifact_id,),
        options={"namespace": change.namespace},
    )
    proposal = POPOutputAdapter().propose(request, _ResolvedOutput(snapshot))
    expected = proposal.transaction.changes[0]
    if not isinstance(expected, ImportPrimitiveSequenceChange) or expected != change:
        raise POPOutputError("POP scene does not match resolved Artifact semantics")


class POPOutputAdapter:
    """Normalize one immutable Primitive Operation Painter output snapshot."""

    adapter_id = "adapter:pop-output"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise POPOutputError("POP output scope must be empty or document")
        if set(request.options) - {"namespace"}:
            raise POPOutputError("Unknown POP output option")
        snapshots = artifacts.resolve_as(
            request.artifact_ids,
            kind=ArtifactKind.DERIVED,
            media_types=frozenset({OUTPUT_MEDIA_TYPE}),
        )
        if len(snapshots) != 1:
            raise POPOutputError("POP import requires exactly one Derived output Artifact")
        snapshot = snapshots[0]
        payload = self._payload(snapshot)
        self._validate(payload, snapshot)
        namespace = self._namespace(request, snapshot)
        fragment = self._fragment(payload, snapshot, namespace)
        self._check_collisions(request.document, fragment)
        change = ImportPrimitiveSequenceChange(fragment=fragment, namespace=namespace)
        producer = payload["producer"]
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="Primitive Operation Painter snapshotted output",
            engine_version=producer["commit"],
            parameters={
                "identity": ADAPTER_IDENTITY,
                "output_identity": OUTPUT_IDENTITY,
                "run_identity": payload["run_identity"],
                "input": payload["input"],
                "output_artifact_id": snapshot.artifact_id,
                "namespace": namespace,
                "model_id": producer["model_id"],
                "checkpoint_hash": producer["checkpoint_hash"],
                "seed": producer["seed"],
                "decoding": producer["decoding"],
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "generator": asdict(generator),
                    "change": asdict(change),
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:pop-output:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:pop-output:{digest}",
                changes=(change,),
                message="Import snapshotted Primitive Operation Painter output",
            ),
            report=EvaluationReport(metrics={"primitives": float(len(payload["primitives"]))}),
            preview=ProposalPreview(proposed_render_stack=fragment.render_entries),
            preview_artifacts=(
                PreviewArtifact(
                    artifact_id=snapshot.artifact_id,
                    content_hash=snapshot.content_hash,
                    media_type=snapshot.media_type,
                ),
            ),
            required_artifact_ids=(snapshot.artifact_id,),
            confidence=None,
            notes=(
                "Ordered primitive evidence; no semantic Entity labels or animation timing inferred"
            ),
        )

    @staticmethod
    def _payload(snapshot: ArtifactSnapshot) -> dict[str, Any]:
        try:
            payload = json.loads(snapshot.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise POPOutputError("POP output must be canonical UTF-8 JSON") from exc
        if not isinstance(payload, dict) or canonical_bytes(payload) != snapshot.content:
            raise POPOutputError("POP output must use canonical JSON encoding")
        return payload

    @staticmethod
    def _validate(payload: dict[str, Any], snapshot: ArtifactSnapshot) -> None:
        if set(payload) != {
            "schema_version",
            "run_identity",
            "producer",
            "input",
            "canvas",
            "primitives",
        }:
            raise POPOutputError("POP output fields are invalid")
        if payload["schema_version"] != OUTPUT_SCHEMA:
            raise POPOutputError("Unsupported POP output schema")
        generation_input = payload["input"]
        if not isinstance(generation_input, dict) or set(generation_input) != {"kind", "value"}:
            raise POPOutputError("POP input fields are invalid")
        if generation_input["kind"] != "text":
            raise POPOutputError("Golden P supports only a recorded text input")
        if not isinstance(generation_input["value"], str) or not generation_input["value"].strip():
            raise POPOutputError("POP text input must not be empty")
        producer = payload["producer"]
        if not isinstance(producer, dict) or set(producer) != {
            "repository",
            "commit",
            "model_id",
            "checkpoint_hash",
            "seed",
            "decoding",
        }:
            raise POPOutputError("POP producer fields are invalid")
        if producer["repository"] != UPSTREAM_REPOSITORY:
            raise POPOutputError("POP repository is not the recorded upstream")
        if (
            not isinstance(producer["commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", producer["commit"]) is None
        ):
            raise POPOutputError("POP commit must be a full Git SHA")
        if not isinstance(producer["model_id"], str) or not producer["model_id"]:
            raise POPOutputError("POP model ID is invalid")
        if (
            not isinstance(producer["checkpoint_hash"], str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", producer["checkpoint_hash"]) is None
        ):
            raise POPOutputError("POP checkpoint hash is invalid")
        if type(producer["seed"]) is not int or producer["seed"] < 0:
            raise POPOutputError("POP seed is invalid")
        decoding = producer["decoding"]
        if not isinstance(decoding, dict) or set(decoding) != {"strategy", "max_steps"}:
            raise POPOutputError("POP decoding fields are invalid")
        if decoding["strategy"] != "greedy":
            raise POPOutputError("Golden P supports only deterministic greedy decoding")
        if type(decoding["max_steps"]) is not int or not 1 <= decoding["max_steps"] <= 512:
            raise POPOutputError("POP max_steps must be an integer from 1 to 512")
        canvas = payload["canvas"]
        if not isinstance(canvas, dict) or set(canvas) != {"width", "height", "background_rgb"}:
            raise POPOutputError("POP canvas fields are invalid")
        width = _positive_number(canvas["width"], "canvas width")
        height = _positive_number(canvas["height"], "canvas height")
        _rgb(canvas["background_rgb"], "background")
        primitives = payload["primitives"]
        if not isinstance(primitives, list) or not 1 <= len(primitives) <= MAX_PRIMITIVES:
            raise POPOutputError("POP output must contain between 1 and 512 primitives")
        if len(primitives) > decoding["max_steps"]:
            raise POPOutputError("POP primitive count exceeds recorded max_steps")
        for index, primitive in enumerate(primitives):
            if not isinstance(primitive, dict) or set(primitive) != {
                "index",
                "x",
                "y",
                "angle_degrees",
                "width",
                "height",
                "shape_type",
                "rgb",
            }:
                raise POPOutputError("POP primitive fields are invalid")
            if primitive["index"] != index:
                raise POPOutputError("POP primitive indices must be contiguous draw order")
            x = _finite_number(primitive["x"], "primitive x")
            y = _finite_number(primitive["y"], "primitive y")
            _finite_number(primitive["angle_degrees"], "primitive angle")
            primitive_width = _positive_number(primitive["width"], "primitive width")
            primitive_height = _positive_number(primitive["height"], "primitive height")
            if primitive["shape_type"] not in {"ellipse", "rotated_rectangle"}:
                raise POPOutputError("POP primitive shape_type is unsupported")
            _rgb(primitive["rgb"], f"primitive {index}")
            if not (0 <= x <= width and 0 <= y <= height):
                raise POPOutputError("POP primitive center must lie inside the canvas")
            if primitive_width > width * 2 or primitive_height > height * 2:
                raise POPOutputError("POP primitive dimensions exceed the supported canvas bound")
        expected_run = pop_run_identity(payload)
        if payload["run_identity"] != expected_run:
            raise POPOutputError("POP run identity is invalid")
        provenance = snapshot.provenance
        if (
            provenance.get("derived_type") != "pop-ordered-primitives"
            or provenance.get("output_identity") != OUTPUT_IDENTITY
            or provenance.get("run_identity") != expected_run
            or provenance.get("repository") != producer["repository"]
            or provenance.get("commit") != producer["commit"]
            or provenance.get("model_id") != producer["model_id"]
            or provenance.get("checkpoint_hash") != producer["checkpoint_hash"]
            or provenance.get("seed") != producer["seed"]
            or provenance.get("decoding") != decoding
        ):
            raise POPOutputError("POP Artifact provenance is inconsistent")

    @staticmethod
    def _fragment(
        payload: dict[str, Any], snapshot: ArtifactSnapshot, namespace: str
    ) -> AppendSceneFragmentChange:
        entities: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []
        bindings: list[dict[str, Any]] = []
        styles: list[dict[str, Any]] = []
        render_entries: list[str] = []

        background_entity = f"entity:{namespace}-background"
        background_op = f"op:{namespace}-background"
        canvas = payload["canvas"]
        entities.append(
            {
                "id": background_entity,
                "name": "POP Background",
                "semantic_tags": ["generated-primitive", "pop-output"],
            }
        )
        operations.append(
            {
                "id": background_op,
                "type": "CreateRectangle",
                "inputs": {},
                "parameters": {
                    "x": 0,
                    "y": 0,
                    "width": canvas["width"],
                    "height": canvas["height"],
                },
            }
        )
        bindings.append(
            {
                "entity": background_entity,
                "property": "geometry",
                "slot": f"{background_op}.geometry",
            }
        )
        styles.append(_style(background_entity, canvas["background_rgb"]))
        render_entries.append(background_entity)

        for primitive in payload["primitives"]:
            suffix = f"primitive-{primitive['index']:04d}"
            entity_id = f"entity:{namespace}-{suffix}"
            create_op = f"op:{namespace}-{suffix}-create"
            transform_op = f"op:{namespace}-{suffix}-transform"
            entities.append(
                {
                    "id": entity_id,
                    "name": f"POP Primitive {primitive['index'] + 1}",
                    "semantic_tags": ["generated-primitive", "pop-output"],
                }
            )
            if primitive["shape_type"] == "ellipse":
                operation_type = "CreateEllipse"
                parameters = {
                    "cx": 0,
                    "cy": 0,
                    "rx": primitive["width"] / 2,
                    "ry": primitive["height"] / 2,
                }
            else:
                operation_type = "CreateRectangle"
                parameters = {
                    "x": -primitive["width"] / 2,
                    "y": -primitive["height"] / 2,
                    "width": primitive["width"],
                    "height": primitive["height"],
                }
            operations.append(
                {
                    "id": create_op,
                    "type": operation_type,
                    "inputs": {},
                    "parameters": parameters,
                }
            )
            operations.append(
                {
                    "id": transform_op,
                    "type": "Transform",
                    "inputs": {"geometry": f"{create_op}.geometry"},
                    "parameters": {
                        "matrix": _matrix(
                            primitive["angle_degrees"], primitive["x"], primitive["y"]
                        )
                    },
                }
            )
            bindings.append(
                {"entity": entity_id, "property": "geometry", "slot": f"{transform_op}.geometry"}
            )
            styles.append(_style(entity_id, primitive["rgb"]))
            render_entries.append(entity_id)
        return AppendSceneFragmentChange(
            entities=tuple(entities),
            operations=tuple(operations),
            output_bindings=tuple(bindings),
            render_entries=tuple(render_entries),
            styles=tuple(styles),
            references=(snapshot.document_reference(),),
        )

    @staticmethod
    def _check_collisions(document: dict[str, Any], fragment: AppendSceneFragmentChange) -> None:
        existing_entities = {entity.get("id") for entity in document.get("entities", [])}
        existing_operations = {
            operation.get("id")
            for operation in document.get("construction", {}).get("operations", [])
        }
        if existing_entities & {entity["id"] for entity in fragment.entities}:
            raise POPOutputError("POP generated Entity ID collides with the base Document")
        if existing_operations & {operation["id"] for operation in fragment.operations}:
            raise POPOutputError("POP generated Operation ID collides with the base Document")

    @staticmethod
    def _namespace(request: AdapterRequest, snapshot: ArtifactSnapshot) -> str:
        namespace = request.options.get("namespace", f"pop-{snapshot.artifact_id[-12:]}")
        if not isinstance(namespace, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]*", namespace) is None:
            raise POPOutputError("Namespace must contain lowercase letters, digits, and hyphens")
        return namespace


def _finite_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise POPOutputError(f"POP {label} must be finite")
    return value


def _positive_number(value: Any, label: str) -> int | float:
    number = _finite_number(value, label)
    if number <= 0:
        raise POPOutputError(f"POP {label} must be greater than zero")
    return number


def _rgb(value: Any, label: str) -> tuple[int, int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(channel) is not int or not 0 <= channel <= 255 for channel in value)
    ):
        raise POPOutputError(f"POP {label} RGB must contain three 8-bit integers")
    return value[0], value[1], value[2]


def _style(entity_id: str, rgb: list[int]) -> dict[str, Any]:
    return {
        "entity": entity_id,
        "fill": f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}",
        "stroke": "none",
        "stroke_width": 0,
        "opacity": 1,
    }


def _matrix(angle_degrees: int | float, x: int | float, y: int | float) -> list[int | float]:
    radians = math.radians(angle_degrees)
    cosine = _canonical_float(math.cos(radians))
    sine = _canonical_float(math.sin(radians))
    return [cosine, sine, _canonical_float(-sine), cosine, x, y]


def _canonical_float(value: float) -> int | float:
    canonical = float(format(value, ".12g"))
    if canonical == 0:
        return 0
    if canonical.is_integer():
        return int(canonical)
    return canonical
