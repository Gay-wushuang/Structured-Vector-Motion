from __future__ import annotations

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
        evaluated_entities.append(
            EvaluatedEntity(
                entity_id=entity_id,
                name=entities[entity_id]["name"],
                geometry_value_id=value.value_id,
                geometry=value.payload,
                style=styles.get(entity_id),
            )
        )
    return EvaluatedScene(
        document_id=document["document_id"],
        entities=tuple(evaluated_entities),
        quality=quality,
    )
