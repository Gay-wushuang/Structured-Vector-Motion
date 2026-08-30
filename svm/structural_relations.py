from __future__ import annotations

import hashlib
from typing import Any

from .evaluator import DocumentError, canonical_bytes

STRUCTURAL_RELATIONS_IDENTITY = "svm-structural-relations@0.2"
MAX_PROMOTED_COMPONENTS_FOR_RELATIONS = 512


def structural_relation_id(content: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_bytes({"identity": STRUCTURAL_RELATIONS_IDENTITY, **content})
    ).hexdigest()[:16]
    return f"relation:{content['type']}:{digest}"


def provenance_bounds(provenance: dict[str, Any]) -> tuple[int, int, int, int] | None:
    bounds = provenance.get("bounds")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or any(not isinstance(value, int) or isinstance(value, bool) for value in bounds)
        or not (0 <= bounds[0] < bounds[2])
        or not (0 <= bounds[1] < bounds[3])
    ):
        return None
    return bounds[0], bounds[1], bounds[2], bounds[3]


def strictly_bounds_contains(
    outer: tuple[int, int, int, int] | None,
    inner: tuple[int, int, int, int] | None,
) -> bool:
    return (
        outer is not None
        and inner is not None
        and outer != inner
        and outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def materialize_promoted_relations(all_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    promoted = [
        entity
        for entity in all_entities
        if isinstance(entity.get("provenance"), dict)
        and entity["provenance"].get("type") == "PromotedComponent"
    ]
    if any(provenance_bounds(entity["provenance"]) is None for entity in promoted):
        raise DocumentError("Promoted component relation materialization requires valid bounds")
    by_artifact: dict[str, list[dict[str, Any]]] = {}
    for entity in promoted:
        by_artifact.setdefault(entity["provenance"]["artifact_id"], []).append(entity)
    for artifact_id, entities in by_artifact.items():
        if len(entities) > MAX_PROMOTED_COMPONENTS_FOR_RELATIONS:
            raise DocumentError(
                f"Structural relation materialization for {artifact_id} exceeds the "
                f"per-Artifact promoted-component limit of "
                f"{MAX_PROMOTED_COMPONENTS_FOR_RELATIONS}"
            )

    relations = [_derived_from_relation(entity) for entity in promoted]
    for artifact_entities in by_artifact.values():
        relations.extend(_immediate_containment_relations(artifact_entities))
    return sorted(relations, key=lambda relation: relation["id"])


def _immediate_containment_relations(
    promoted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    containment = {
        (container["id"], contained["id"])
        for container in promoted
        for contained in promoted
        if container["id"] != contained["id"]
        and strictly_bounds_contains(
            provenance_bounds(container["provenance"]),
            provenance_bounds(contained["provenance"]),
        )
    }
    by_id = {entity["id"]: entity for entity in promoted}
    outgoing: dict[str, set[str]] = {entity_id: set() for entity_id in by_id}
    incoming: dict[str, set[str]] = {entity_id: set() for entity_id in by_id}
    for outer, inner in containment:
        outgoing[outer].add(inner)
        incoming[inner].add(outer)
    immediate = [
        (outer, inner)
        for outer, inner in containment
        if not outgoing[outer].intersection(incoming[inner])
    ]
    return [_bounds_contains_relation(by_id[outer], by_id[inner]) for outer, inner in immediate]


def _derived_from_relation(entity: dict[str, Any]) -> dict[str, Any]:
    provenance = entity["provenance"]
    content = {
        "type": "derived-from",
        "subject": entity["id"],
        "artifact_id": provenance["artifact_id"],
        "candidate_id": provenance["candidate_id"],
        "component_digest": provenance["component_digest"],
    }
    return {"id": structural_relation_id(content), **content}


def _bounds_contains_relation(
    container: dict[str, Any], contained: dict[str, Any]
) -> dict[str, Any]:
    container_provenance = container["provenance"]
    contained_provenance = contained["provenance"]
    content = {
        "type": "bounds-contains",
        "container": container["id"],
        "contained": contained["id"],
        "evidence": {
            "artifact_id": container_provenance["artifact_id"],
            "container_candidate_id": container_provenance["candidate_id"],
            "contained_candidate_id": contained_provenance["candidate_id"],
            "basis": "strict-half-open-bounds@0.1",
        },
    }
    return {"id": structural_relation_id(content), **content}
