from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactResolver, ArtifactSnapshot, ArtifactWriter
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
PREFIX_MEDIA_TYPE = "application/vnd.svm.pop-token-prefix+json"
OUTPUT_SCHEMA = "svm-pop-output-0.2"
PREFIX_SCHEMA = "svm-pop-token-prefix-0.1"
OUTPUT_IDENTITY = "svm-pop-output@0.2"
RUN_IDENTITY = "svm-pop-run@0.2"
ADAPTER_IDENTITY = "svm-pop-output-adapter@0.2"
TOKEN_LAYOUT_IDENTITY = "pop/geometrize_256_v1"
QUANTIZATION_IDENTITY = "pop/geometrize-256-quantization@0.1"
DECODER_IDENTITY = "pop/decode-tokens-to-render-data@d5489b0"
RENDERER_IDENTITY = "pop/matplotlib-half-alpha@d5489b0"
UPSTREAM_REPOSITORY = "https://github.com/wonderfulearth/primitive-operation-painter"
MAX_PRIMITIVES = 512

TOKENS_PER_STEP = 9
X_OFFSET = 0
Y_OFFSET = 512
ANGLE_OFFSET = 1024
WIDTH_OFFSET = 1294
HEIGHT_OFFSET = 1806
SHAPE_OFFSET = 2318
RED_OFFSET = 2574
GREEN_OFFSET = 2702
BLUE_OFFSET = 2830
SPECIAL_OFFSET = 2958
FIELD_RANGES = (
    (X_OFFSET, Y_OFFSET),
    (Y_OFFSET, ANGLE_OFFSET),
    (ANGLE_OFFSET, WIDTH_OFFSET),
    (WIDTH_OFFSET, HEIGHT_OFFSET),
    (HEIGHT_OFFSET, SHAPE_OFFSET),
    (SHAPE_OFFSET, RED_OFFSET),
    (RED_OFFSET, GREEN_OFFSET),
    (GREEN_OFFSET, BLUE_OFFSET),
    (BLUE_OFFSET, SPECIAL_OFFSET),
)


class POPOutputError(ValueError):
    pass


def pop_run_identity(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_bytes(
            {
                "identity": RUN_IDENTITY,
                "generation_context": payload["generation_context"],
                "producer": payload["producer"],
                "canvas": payload["canvas"],
            }
        )
    ).hexdigest()
    return f"sha256:{digest}"


class _ResolvedOutput:
    def __init__(self, snapshots: dict[str, ArtifactSnapshot]):
        self.snapshots = snapshots

    def resolve(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        try:
            return tuple(self.snapshots[artifact_id] for artifact_id in artifact_ids)
        except KeyError as exc:
            raise POPOutputError("POP verification requires its exact Artifacts") from exc

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
            raise POPOutputError("Resolved POP Artifact interpretation is invalid")
        return snapshots

    def resolve_reference(self, reference: dict[str, Any]) -> ArtifactSnapshot:
        artifact_id = reference.get("id")
        if not isinstance(artifact_id, str):
            raise POPOutputError("Resolved POP Artifact reference has no ID")
        snapshot = self.snapshots.get(artifact_id)
        if snapshot is None or snapshot.document_reference() != reference:
            raise POPOutputError("Resolved POP Artifact reference is inconsistent")
        return snapshot


def verify_import_primitive_sequence_change(
    change: ImportPrimitiveSequenceChange, resolved: dict[str, ArtifactSnapshot]
) -> None:
    if len(resolved) != 2:
        raise POPOutputError("POP import requires exact prefix and output Artifacts")
    request = AdapterRequest(
        base_revision_id="revision:artifact-verification",
        document={"entities": [], "construction": {"operations": []}},
        scope=("document",),
        artifact_ids=tuple(sorted(resolved)),
        options={"namespace": change.namespace},
    )
    proposal = POPOutputAdapter().propose(request, _ResolvedOutput(resolved))
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
        snapshots = artifacts.resolve(request.artifact_ids)
        output_matches = [
            snapshot
            for snapshot in snapshots
            if snapshot.kind == ArtifactKind.DERIVED and snapshot.media_type == OUTPUT_MEDIA_TYPE
        ]
        prefix_matches = [
            snapshot
            for snapshot in snapshots
            if snapshot.kind == ArtifactKind.REFERENCE and snapshot.media_type == PREFIX_MEDIA_TYPE
        ]
        if len(snapshots) != 2 or len(output_matches) != 1 or len(prefix_matches) != 1:
            raise POPOutputError("POP import requires one prefix and one Derived output Artifact")
        snapshot = output_matches[0]
        prefix = prefix_matches[0]
        payload = self._payload(snapshot)
        self._validate(payload, snapshot, prefix)
        namespace = self._namespace(request, snapshot)
        fragment = self._fragment(payload, (prefix, snapshot), namespace)
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
                "generation_context": payload["generation_context"],
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
                *(
                    PreviewArtifact(
                        artifact_id=item.artifact_id,
                        content_hash=item.content_hash,
                        media_type=item.media_type,
                    )
                    for item in snapshots
                ),
            ),
            required_artifact_ids=tuple(sorted(item.artifact_id for item in snapshots)),
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
    def _validate(
        payload: dict[str, Any], snapshot: ArtifactSnapshot, prefix: ArtifactSnapshot
    ) -> None:
        if set(payload) != {
            "schema_version",
            "run_identity",
            "producer",
            "generation_context",
            "canvas",
            "primitives",
            "raw_tokens",
        }:
            raise POPOutputError("POP output fields are invalid")
        if payload["schema_version"] != OUTPUT_SCHEMA:
            raise POPOutputError("Unsupported POP output schema")
        generation_context = payload["generation_context"]
        if not isinstance(generation_context, dict) or set(generation_context) != {
            "kind",
            "prefix_artifact_id",
            "prefix_content_hash",
            "prefix_length",
            "target_steps",
            "user_intent",
        }:
            raise POPOutputError("POP generation context fields are invalid")
        if generation_context["kind"] != "operation_prefix":
            raise POPOutputError("POP generation context must be an operation prefix")
        if (
            generation_context["prefix_artifact_id"] != prefix.artifact_id
            or generation_context["prefix_content_hash"] != prefix.content_hash
        ):
            raise POPOutputError("POP generation context prefix identity is inconsistent")
        if not isinstance(generation_context["user_intent"], str):
            raise POPOutputError("POP optional user intent must be text")
        producer = payload["producer"]
        if not isinstance(producer, dict) or set(producer) != {
            "repository",
            "commit",
            "model_id",
            "checkpoint_hash",
            "seed",
            "decoding",
            "token_layout_identity",
            "quantization_identity",
            "decoder_identity",
            "renderer_identity",
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
        expected_identities = {
            "token_layout_identity": TOKEN_LAYOUT_IDENTITY,
            "quantization_identity": QUANTIZATION_IDENTITY,
            "decoder_identity": DECODER_IDENTITY,
            "renderer_identity": RENDERER_IDENTITY,
        }
        if any(producer[name] != value for name, value in expected_identities.items()):
            raise POPOutputError(
                "POP token, quantization, decoder, or renderer identity is invalid"
            )
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
        raw_tokens = _raw_tokens(payload["raw_tokens"])
        prefix_payload = _prefix_payload(prefix)
        prefix_tokens = _raw_tokens(prefix_payload["raw_tokens"])
        prefix_length = generation_context["prefix_length"]
        target_steps = generation_context["target_steps"]
        if type(prefix_length) is not int or prefix_length < 1:
            raise POPOutputError("POP prefix_length must be positive")
        if type(target_steps) is not int or not prefix_length <= target_steps <= 512:
            raise POPOutputError("POP target_steps is invalid")
        if target_steps != decoding["max_steps"]:
            raise POPOutputError("POP target_steps must equal the recorded decoding max_steps")
        if len(prefix_tokens) != prefix_length * TOKENS_PER_STEP:
            raise POPOutputError("POP prefix token count is inconsistent")
        if len(raw_tokens) != target_steps * TOKENS_PER_STEP:
            raise POPOutputError("POP output token count is inconsistent")
        if raw_tokens[: len(prefix_tokens)] != prefix_tokens:
            raise POPOutputError("POP output does not preserve the recorded operation prefix")
        decoded_canvas, decoded_primitives = _decode_tokens(raw_tokens)
        if decoded_canvas != canvas or decoded_primitives != payload["primitives"]:
            raise POPOutputError("POP decoded geometry does not match its raw token sequence")
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
            or provenance.get("token_layout_identity") != TOKEN_LAYOUT_IDENTITY
            or provenance.get("quantization_identity") != QUANTIZATION_IDENTITY
            or provenance.get("decoder_identity") != DECODER_IDENTITY
            or provenance.get("renderer_identity") != RENDERER_IDENTITY
            or provenance.get("prefix_artifact_id") != prefix.artifact_id
        ):
            raise POPOutputError("POP Artifact provenance is inconsistent")
        if (
            prefix_payload.get("schema_version") != PREFIX_SCHEMA
            or prefix.provenance.get("token_layout_identity") != TOKEN_LAYOUT_IDENTITY
            or prefix.provenance.get("quantization_identity") != QUANTIZATION_IDENTITY
        ):
            raise POPOutputError("POP prefix Artifact provenance is inconsistent")

    @staticmethod
    def _fragment(
        payload: dict[str, Any], snapshots: tuple[ArtifactSnapshot, ...], namespace: str
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
        styles.append(_style(background_entity, canvas["background_rgb"], opacity=1))
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
            styles.append(_style(entity_id, primitive["rgb"], opacity=0.5))
            render_entries.append(entity_id)
        return AppendSceneFragmentChange(
            entities=tuple(entities),
            operations=tuple(operations),
            output_bindings=tuple(bindings),
            render_entries=tuple(render_entries),
            styles=tuple(styles),
            references=tuple(snapshot.document_reference() for snapshot in snapshots),
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


class POPTokenExporter:
    """Convert one captured upstream nine-token continuation into SVM Artifacts."""

    def export(
        self,
        artifacts: ArtifactWriter,
        raw_tokens: list[int],
        *,
        prefix_length: int,
        commit: str,
        model_id: str,
        checkpoint_hash: str,
        seed: int,
        decoding: dict[str, Any],
        user_intent: str = "",
    ) -> tuple[ArtifactSnapshot, ArtifactSnapshot]:
        tokens = _raw_tokens(raw_tokens)
        if len(tokens) % TOKENS_PER_STEP != 0:
            raise POPOutputError("POP raw token count must be divisible by nine")
        target_steps = len(tokens) // TOKENS_PER_STEP
        if type(prefix_length) is not int or not 1 <= prefix_length <= target_steps:
            raise POPOutputError("POP prefix_length is invalid")
        canvas, primitives = _decode_tokens(tokens)
        prefix_tokens = tokens[: prefix_length * TOKENS_PER_STEP]
        prefix = artifacts.import_bytes(
            canonical_bytes(
                {
                    "schema_version": PREFIX_SCHEMA,
                    "raw_tokens": prefix_tokens,
                }
            ),
            media_type=PREFIX_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={
                "source_type": "pop-operation-prefix",
                "token_layout_identity": TOKEN_LAYOUT_IDENTITY,
                "quantization_identity": QUANTIZATION_IDENTITY,
            },
        )
        producer = {
            "repository": UPSTREAM_REPOSITORY,
            "commit": commit,
            "model_id": model_id,
            "checkpoint_hash": checkpoint_hash,
            "seed": seed,
            "decoding": decoding,
            "token_layout_identity": TOKEN_LAYOUT_IDENTITY,
            "quantization_identity": QUANTIZATION_IDENTITY,
            "decoder_identity": DECODER_IDENTITY,
            "renderer_identity": RENDERER_IDENTITY,
        }
        payload = {
            "schema_version": OUTPUT_SCHEMA,
            "generation_context": {
                "kind": "operation_prefix",
                "prefix_artifact_id": prefix.artifact_id,
                "prefix_content_hash": prefix.content_hash,
                "prefix_length": prefix_length,
                "target_steps": target_steps,
                "user_intent": user_intent,
            },
            "producer": producer,
            "canvas": canvas,
            "raw_tokens": tokens,
            "primitives": primitives,
        }
        payload["run_identity"] = pop_run_identity(payload)
        output = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=OUTPUT_MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "derived_type": "pop-ordered-primitives",
                "output_identity": OUTPUT_IDENTITY,
                "run_identity": payload["run_identity"],
                "prefix_artifact_id": prefix.artifact_id,
                **producer,
            },
        )
        return prefix, output


def _prefix_payload(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise POPOutputError("POP prefix must be canonical UTF-8 JSON") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "raw_tokens"}
        or canonical_bytes(payload) != snapshot.content
    ):
        raise POPOutputError("POP prefix must use the canonical prefix schema")
    return payload


def _raw_tokens(value: Any) -> list[int]:
    if not isinstance(value, list) or not value:
        raise POPOutputError("POP raw_tokens must be a non-empty list")
    if any(type(token) is not int for token in value):
        raise POPOutputError("POP raw tokens must be integers")
    for index, token in enumerate(value):
        lower, upper = FIELD_RANGES[index % TOKENS_PER_STEP]
        if not lower <= token < upper:
            raise POPOutputError("POP raw token is outside its field vocabulary")
    return list(value)


def _decode_tokens(tokens: list[int]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(tokens) % TOKENS_PER_STEP != 0:
        raise POPOutputError("POP raw token count must be divisible by nine")
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(tokens), TOKENS_PER_STEP):
        values = tokens[offset : offset + TOKENS_PER_STEP]
        rows.append(
            {
                "x": (values[0] - X_OFFSET) / 2,
                "y": (values[1] - Y_OFFSET) / 2,
                "angle_degrees": (values[2] - ANGLE_OFFSET) / 3,
                "width": (values[3] - WIDTH_OFFSET) / 4,
                "height": (values[4] - HEIGHT_OFFSET) / 4,
                "shape": values[5] - SHAPE_OFFSET - 1,
                "rgb": [
                    (values[6] - RED_OFFSET) * 2,
                    (values[7] - GREEN_OFFSET) * 2,
                    (values[8] - BLUE_OFFSET) * 2,
                ],
            }
        )
    background = rows[0]
    if background["shape"] != -1:
        raise POPOutputError("POP sequence must begin with one background operation")
    primitives: list[dict[str, Any]] = []
    for index, row in enumerate(rows[1:]):
        if row["shape"] not in {0, 1}:
            raise POPOutputError("POP sequence contains an unsupported primitive shape")
        primitives.append(
            {
                "index": index,
                "x": row["x"],
                "y": row["y"],
                "angle_degrees": row["angle_degrees"],
                "width": row["width"],
                "height": row["height"],
                "shape_type": "ellipse" if row["shape"] == 1 else "rotated_rectangle",
                "rgb": row["rgb"],
            }
        )
    return {"width": 256, "height": 256, "background_rgb": background["rgb"]}, primitives


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


def _style(entity_id: str, rgb: list[int], *, opacity: int | float) -> dict[str, Any]:
    return {
        "entity": entity_id,
        "fill": f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}",
        "stroke": "none",
        "stroke_width": 0,
        "opacity": opacity,
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
