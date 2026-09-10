from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .evaluator import DocumentError, Evaluator, Quality


@dataclass(frozen=True)
class EvaluatedEntity:
    entity_id: str
    name: str
    geometry_value_id: str
    geometry: dict[str, Any]
    style: EvaluatedStyle | None


@dataclass(frozen=True)
class EvaluatedStyle:
    fill: str
    stroke: str
    stroke_width: float
    opacity: float


@dataclass(frozen=True)
class EvaluatedScene:
    document_id: str
    entities: tuple[EvaluatedEntity, ...]
    quality: Quality
    camera_transform: tuple[float, float, float, float, float, float] | None = None


def build_evaluated_scene(
    document: dict[str, Any],
    evaluator: Evaluator,
    quality: Quality = Quality.FINAL,
) -> EvaluatedScene:
    """Materialize render-stack entities from accepted output bindings."""

    if evaluator.document is not document and evaluator.document != document:
        raise DocumentError("Evaluator Document does not match scene Document")
    evaluator.evaluate_all(quality)

    entities = {entity["id"]: entity for entity in document["entities"]}
    bindings = {
        (binding["entity"], binding["property"]): binding["slot"]
        for binding in document["construction"]["output_bindings"]
    }
    styles = {
        style["entity"]: EvaluatedStyle(
            fill=style["fill"],
            stroke=style["stroke"],
            stroke_width=float(style["stroke_width"]),
            opacity=float(style["opacity"]),
        )
        for style in document["presentation"].get("styles", [])
    }
    group_transforms: dict[str, list[float]] = {}
    for group in document.get("groups", []):
        transform = group.get("transform")
        if transform is None:
            continue
        matrix = _group_transform_matrix(transform)
        for member in group["members"]:
            if member in group_transforms:
                raise DocumentError(f"Entity {member} belongs to multiple transformed Groups")
            group_transforms[member] = matrix
    evaluated_entities: list[EvaluatedEntity] = []
    for entity_id in document["presentation"]["render_stack"]:
        slot_id = bindings.get((entity_id, "geometry"))
        if slot_id is None:
            raise DocumentError(f"Rendered entity {entity_id} has no geometry binding")
        operation_id, output_name = Evaluator._split_slot(slot_id)
        node = evaluator.runtime[operation_id]
        if node.outputs is None or output_name not in node.outputs:
            raise DocumentError(f"Geometry output {slot_id} is not materialized")
        value = node.outputs[output_name]
        if not isinstance(value.payload, dict):
            raise DocumentError(f"Geometry output {slot_id} is not an object")
        geometry = value.payload
        if entity_id in group_transforms:
            geometry = {
                "kind": "transform",
                "source": geometry,
                "matrix": group_transforms[entity_id],
            }
        evaluated_entities.append(
            EvaluatedEntity(
                entity_id=entity_id,
                name=entities[entity_id]["name"],
                geometry_value_id=value.value_id,
                geometry=geometry,
                style=styles.get(entity_id),
            )
        )
    return EvaluatedScene(
        document_id=document["document_id"],
        entities=tuple(evaluated_entities),
        quality=quality,
        camera_transform=_camera_transform_matrix(document["presentation"].get("camera")),
    )


def _camera_transform_matrix(
    camera: dict[str, Any] | None,
) -> tuple[float, float, float, float, float, float] | None:
    if camera is None:
        return None
    x, y = (float(value) for value in camera["position"])
    scale = float(camera["scale"])
    radians = math.radians(-float(camera["rotation_degrees"]))
    a, b = scale * math.cos(radians), scale * math.sin(radians)
    c, d = -b, a
    return (
        _canonical_scene_number(a),
        _canonical_scene_number(b),
        _canonical_scene_number(c),
        _canonical_scene_number(d),
        _canonical_scene_number(-a * x - c * y),
        _canonical_scene_number(-b * x - d * y),
    )


def _group_transform_matrix(transform: dict[str, Any]) -> list[float]:
    translate_x, translate_y = (float(value) for value in transform["translate"])
    origin_x, origin_y = (float(value) for value in transform["origin"])
    scale = float(transform["scale"])
    radians = math.radians(float(transform["rotation_degrees"]))
    a = scale * math.cos(radians)
    b = scale * math.sin(radians)
    c = -b
    d = a
    return [
        _canonical_scene_number(a),
        _canonical_scene_number(b),
        _canonical_scene_number(c),
        _canonical_scene_number(d),
        _canonical_scene_number(translate_x + origin_x - a * origin_x - c * origin_y),
        _canonical_scene_number(translate_y + origin_y - b * origin_x - d * origin_y),
    ]


def _canonical_scene_number(value: float) -> float:
    if abs(value) < 1e-12:
        return 0.0
    return float(format(value, ".12g"))
