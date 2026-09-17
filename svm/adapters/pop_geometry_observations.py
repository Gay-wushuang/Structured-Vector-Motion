from __future__ import annotations

import hashlib
import math
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import AppendReferencesChange, Transaction
from .pop_output import (
    ADAPTER_IDENTITY as POP_ADAPTER_IDENTITY,
)
from .pop_output import (
    OUTPUT_IDENTITY,
    OUTPUT_MEDIA_TYPE,
    PREFIX_MEDIA_TYPE,
    POPOutputError,
    read_validated_pop_output,
)
from .temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2

POLICY_IDENTITY = "svm-pop-geometry-observation-policy@0.1"
PRODUCER_IDENTITY = "svm-pop-geometry-observation-producer@0.1"


class POPGeometryObservationError(ValueError):
    pass


class POPGeometryObservationAdapter:
    """Produce two-frame v0.2 observations from exact frozen POP geometry."""

    adapter_id = "adapter:pop-geometry-observations"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise POPGeometryObservationError("POP geometry observation scope must be document")
        required_options = {
            "source_output_artifact_id",
            "target_output_artifact_id",
            "source_tick",
            "target_tick",
        }
        if set(request.options) != required_options:
            raise POPGeometryObservationError(
                "POP geometry observations require explicit outputs and ticks"
            )
        source_id = request.options["source_output_artifact_id"]
        target_id = request.options["target_output_artifact_id"]
        source_tick = request.options["source_tick"]
        target_tick = request.options["target_tick"]
        if (
            not isinstance(source_id, str)
            or not isinstance(target_id, str)
            or source_id == target_id
            or type(source_tick) is not int
            or type(target_tick) is not int
            or source_tick < 0
            or target_tick <= source_tick
        ):
            raise POPGeometryObservationError("POP output identities or ticks are invalid")
        snapshots = {item.artifact_id: item for item in artifacts.resolve(request.artifact_ids)}
        try:
            source = snapshots[source_id]
            target = snapshots[target_id]
        except KeyError as exc:
            raise POPGeometryObservationError("Exact POP output Artifacts are required") from exc
        outputs = (source, target)
        if any(
            item.kind != ArtifactKind.DERIVED or item.media_type != OUTPUT_MEDIA_TYPE
            for item in outputs
        ):
            raise POPGeometryObservationError("POP observation sources must be Derived outputs")
        payloads: list[dict[str, Any]] = []
        prefix_ids: list[str] = []
        for output in outputs:
            raw = _raw_payload(output)
            prefix_id = raw.get("generation_context", {}).get("prefix_artifact_id")
            prefix = snapshots.get(prefix_id)
            if (
                prefix is None
                or prefix.kind != ArtifactKind.REFERENCE
                or prefix.media_type != PREFIX_MEDIA_TYPE
            ):
                raise POPGeometryObservationError("Exact POP prefix Artifact is required")
            try:
                payloads.append(read_validated_pop_output(output, prefix))
            except POPOutputError as exc:
                raise POPGeometryObservationError(str(exc)) from exc
            prefix_ids.append(prefix.artifact_id)
        exact_ids = tuple(sorted({source_id, target_id, *prefix_ids}))
        if tuple(sorted(request.artifact_ids)) != exact_ids or len(request.artifact_ids) != len(
            exact_ids
        ):
            raise POPGeometryObservationError("Artifact IDs must exactly match both POP sources")
        if payloads[0]["canvas"] != payloads[1]["canvas"]:
            raise POPGeometryObservationError("POP frames must use the same canvas")
        frames = [
            _frame(payload, output, tick)
            for payload, output, tick in zip(
                payloads, outputs, (source_tick, target_tick), strict=True
            )
        ]
        observation_payload = {
            "schema_version": "svm-primitive-observations-0.2",
            "canvas": [payloads[0]["canvas"]["width"], payloads[0]["canvas"]["height"]],
            "frames": frames,
        }
        provenance = {
            "producer_identity": PRODUCER_IDENTITY,
            "producer_version": self.adapter_version,
            "source_artifact_ids": [source_id, target_id],
            "source_prefix_artifact_ids": prefix_ids,
            "source_format_identity": OUTPUT_IDENTITY,
            "source_adapter_identity": POP_ADAPTER_IDENTITY,
            "geometry_observation_policy": POLICY_IDENTITY,
        }
        observation = artifacts.import_bytes(
            canonical_bytes(observation_payload),
            media_type=OBSERVATION_MEDIA_TYPE_V2,
            kind=ArtifactKind.REFERENCE,
            provenance=provenance,
        )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "frozen POP geometry observation producer",
            PRODUCER_IDENTITY,
            {
                "policy_identity": POLICY_IDENTITY,
                "source_artifact_ids": [source_id, target_id],
                "source_tick": source_tick,
                "target_tick": target_tick,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "observation": observation.artifact_id,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:pop-geometry-observations:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:pop-geometry-observations:{digest}",
                (
                    AppendReferencesChange(
                        (
                            observation.document_reference(),
                            *(snapshots[item].document_reference() for item in exact_ids),
                        )
                    ),
                ),
                "Attach POP-derived primitive observations v0.2",
            ),
            report=EvaluationReport(
                metrics={"observations": float(sum(len(item["primitives"]) for item in frames))}
            ),
            preview_artifacts=(
                PreviewArtifact(
                    observation.artifact_id, observation.content_hash, observation.media_type
                ),
            ),
            preview=ProposalPreview(),
            required_artifact_ids=(observation.artifact_id, *exact_ids),
            notes="Landmarks come from frozen POP primitive geometry, not rendered bounds",
        )


def _raw_payload(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    import json

    try:
        value = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise POPGeometryObservationError("POP source is invalid JSON") from exc
    if not isinstance(value, dict):
        raise POPGeometryObservationError("POP source payload is invalid")
    return value


def _frame(payload: dict[str, Any], output: ArtifactSnapshot, tick: int) -> dict[str, Any]:
    return {
        "tick": tick,
        "primitives": [
            _observation(primitive, output.artifact_id) for primitive in payload["primitives"]
        ],
    }


def _observation(primitive: dict[str, Any], source_artifact_id: str) -> dict[str, Any]:
    shape = primitive["shape_type"]
    if shape not in {"ellipse", "rotated_rectangle"}:
        raise POPGeometryObservationError(f"POP shape {shape!r} has no v0.2 landmark policy")
    x = float(primitive["x"])
    y = float(primitive["y"])
    half_width = float(primitive["width"]) / 2.0
    half_height = float(primitive["height"]) / 2.0
    if shape == "rotated_rectangle":
        local = [
            (-half_width, -half_height),
            (half_width, -half_height),
            (half_width, half_height),
            (-half_width, half_height),
        ]
        symmetry = "quarter-turn" if primitive["width"] == primitive["height"] else "half-turn"
    else:
        local = [(half_width, 0.0), (0.0, half_height), (-half_width, 0.0), (0.0, -half_height)]
        symmetry = "continuous" if primitive["width"] == primitive["height"] else "half-turn"
    points = [_transform(point, x, y, primitive["angle_degrees"]) for point in local]
    if shape == "ellipse":
        radians = math.radians(float(primitive["angle_degrees"]))
        cosine, sine = math.cos(radians), math.sin(radians)
        extent_x = math.sqrt((half_width * cosine) ** 2 + (half_height * sine) ** 2)
        extent_y = math.sqrt((half_width * sine) ** 2 + (half_height * cosine) ** 2)
        bounds = [
            _round(x - extent_x),
            _round(y - extent_y),
            _round(x + extent_x),
            _round(y + extent_y),
        ]
    else:
        bounds = [
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        ]
    identity = {
        "source_artifact_id": source_artifact_id,
        "primitive_index": primitive["index"],
        "policy_identity": POLICY_IDENTITY,
    }
    return {
        "observation_id": "observation:pop:"
        + hashlib.sha256(canonical_bytes(identity)).hexdigest(),
        "primitive_type": shape,
        "bounds": [_round(value) for value in bounds],
        "fill": "#" + "".join(f"{channel:02X}" for channel in primitive["rgb"]),
        "geometry": {
            "type": "ordered-landmarks",
            "points": points,
            "rotation_symmetry": symmetry,
        },
    }


def _transform(
    point: tuple[float, float], x: float, y: float, angle_degrees: int | float
) -> list[float]:
    radians = math.radians(float(angle_degrees))
    cosine, sine = math.cos(radians), math.sin(radians)
    return [
        _round(x + cosine * point[0] - sine * point[1]),
        _round(y + sine * point[0] + cosine * point[1]),
    ]


def _round(value: float) -> float:
    result = float(format(value, ".12g"))
    return 0.0 if result == 0 else result
