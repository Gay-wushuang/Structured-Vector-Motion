from __future__ import annotations

import re
from typing import Any

from .evaluator import DocumentError, Evaluator
from .policies import PolicyDefinitionError, validate_policy_definitions
from .structural_relations import (
    materialize_promoted_relations,
    provenance_bounds,
    strictly_bounds_contains,
    structural_relation_id,
)


def validate_document(document: dict[str, Any]) -> None:
    """Validate cross-record semantics not expressible in JSON Schema alone."""

    evaluator = Evaluator(document)

    reference_ids: set[str] = set()
    for reference in document.get("references", []):
        reference_id = reference.get("id")
        if not isinstance(reference_id, str) or not reference_id.startswith("artifact:"):
            raise DocumentError("Reference ID must start with artifact:")
        if reference_id in reference_ids:
            raise DocumentError(f"Duplicate reference ID {reference_id}")
        reference_ids.add(reference_id)
        content_hash = reference.get("content_hash")
        if (
            not isinstance(content_hash, str)
            or not content_hash.startswith("sha256:")
            or len(content_hash) != 71
            or any(character not in "0123456789abcdef" for character in content_hash[7:])
        ):
            raise DocumentError(f"Reference {reference_id} has invalid content hash")
        if not isinstance(reference.get("uri"), str) or not reference["uri"]:
            raise DocumentError(f"Reference {reference_id} requires a URI locator")
        if not isinstance(reference.get("media_type"), str) or not reference["media_type"]:
            raise DocumentError(f"Reference {reference_id} requires a media type")
        if not isinstance(reference.get("import_metadata"), dict):
            raise DocumentError(f"Reference {reference_id} requires import metadata")

    entities = document.get("entities", [])
    entity_ids = [entity.get("id") for entity in entities]
    if len(entity_ids) != len(set(entity_ids)):
        raise DocumentError("Entity IDs must be unique")
    known_entities = set(entity_ids)

    parents: dict[str, str] = {}
    for entity in entities:
        provenance = entity.get("provenance")
        if provenance is not None:
            _validate_entity_provenance(entity["id"], provenance, reference_ids)
        source_layer = entity.get("source_layer")
        if source_layer is not None:
            _validate_source_layer(entity["id"], source_layer, reference_ids)
        parent_id = entity.get("parent_id")
        if parent_id is not None:
            if parent_id not in known_entities:
                raise DocumentError(f"Entity {entity['id']} has missing parent {parent_id}")
            parents[entity["id"]] = parent_id
    for entity_id in known_entities:
        seen: set[str] = set()
        current = entity_id
        while current in parents:
            if current in seen:
                raise DocumentError("Entity hierarchy must be acyclic")
            seen.add(current)
            current = parents[current]

    _validate_structural_relations(
        document.get("structural_relations", []), entities, known_entities, reference_ids
    )

    bindings = document.get("construction", {}).get("output_bindings", [])
    binding_keys: set[tuple[str, str]] = set()
    for binding in bindings:
        entity_id = binding.get("entity")
        if entity_id not in known_entities:
            raise DocumentError(f"Binding references missing entity {entity_id}")
        key = (entity_id, binding.get("property"))
        if key in binding_keys:
            raise DocumentError(f"Duplicate output binding for {key}")
        binding_keys.add(key)
        operation_id, output_name = Evaluator._split_slot(binding.get("slot", ""))
        if operation_id not in evaluator.operations:
            raise DocumentError(f"Binding references missing output operation {operation_id}")
        output_signature = evaluator.registry.output_signature(evaluator.operations[operation_id])
        if output_name not in output_signature:
            raise DocumentError(f"Binding references missing output slot {binding['slot']}")
        if (
            binding.get("property") == "geometry"
            and output_signature[output_name].value != "geometry"
        ):
            raise DocumentError(f"Geometry binding {binding['slot']} does not provide geometry")

    for entity_id in document.get("presentation", {}).get("render_stack", []):
        if entity_id not in known_entities:
            raise DocumentError(f"Render stack references missing entity {entity_id}")

    style_entities: set[str] = set()
    for style in document.get("presentation", {}).get("styles", []):
        entity_id = style.get("entity")
        if entity_id not in known_entities:
            raise DocumentError(f"Style references missing entity {entity_id}")
        if entity_id in style_entities:
            raise DocumentError(f"Duplicate style for entity {entity_id}")
        style_entities.add(entity_id)
        for property_name in ("fill", "stroke"):
            color = style.get(property_name)
            if not isinstance(color, str) or not _is_supported_color(color):
                raise DocumentError(f"Style {property_name} has unsupported color {color!r}")
        stroke_width = style.get("stroke_width")
        if (
            isinstance(stroke_width, bool)
            or not isinstance(stroke_width, (int, float))
            or stroke_width < 0
        ):
            raise DocumentError("Style stroke_width must be a non-negative number")
        opacity = style.get("opacity")
        if (
            isinstance(opacity, bool)
            or not isinstance(opacity, (int, float))
            or not 0 <= opacity <= 1
        ):
            raise DocumentError("Style opacity must be between 0 and 1")

    try:
        validate_policy_definitions(document)
    except PolicyDefinitionError as exc:
        raise DocumentError(str(exc)) from exc
    from .motion import validate_motion

    validate_motion(document, evaluator)


def _is_supported_color(value: str) -> bool:
    if value == "none":
        return True
    if len(value) not in {7, 9} or not value.startswith("#"):
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value[1:])


def _validate_entity_provenance(entity_id: str, provenance: Any, reference_ids: set[str]) -> None:
    required = {"type", "artifact_id", "candidate_id", "component_digest", "bounds"}
    if (
        not isinstance(provenance, dict)
        or not required <= set(provenance)
        or set(provenance) != required
    ):
        raise DocumentError(f"Entity {entity_id} has invalid provenance fields")
    if provenance["type"] != "PromotedComponent":
        raise DocumentError(f"Entity {entity_id} has unsupported provenance type")
    if provenance["artifact_id"] not in reference_ids:
        raise DocumentError(f"Entity {entity_id} provenance references a missing Artifact")
    candidate_id = provenance["candidate_id"]
    if (
        not isinstance(candidate_id, str)
        or not candidate_id.startswith("candidate:component-")
        or len(candidate_id) < 24
        or any(character not in "0123456789" for character in candidate_id[20:])
    ):
        raise DocumentError(f"Entity {entity_id} has invalid provenance candidate ID")
    digest = provenance["component_digest"]
    if (
        not isinstance(digest, str)
        or len(digest) != 71
        or not digest.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in digest[7:])
    ):
        raise DocumentError(f"Entity {entity_id} has invalid provenance component digest")
    if _bounds(provenance["bounds"]) is None:
        raise DocumentError(f"Entity {entity_id} has invalid provenance bounds")


def _validate_source_layer(entity_id: str, source_layer: Any, reference_ids: set[str]) -> None:
    expected = {
        "producer_family",
        "bundle_artifact_id",
        "run_identity",
        "layer_id",
        "layer_artifact_id",
        "order",
    }
    if not isinstance(source_layer, dict) or set(source_layer) != expected:
        raise DocumentError(f"Entity {entity_id} has invalid source-layer fields")
    producer_family = source_layer["producer_family"]
    if (
        not isinstance(producer_family, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", producer_family) is None
    ):
        raise DocumentError(f"Entity {entity_id} source layer has invalid producer family")
    if source_layer["bundle_artifact_id"] not in reference_ids:
        raise DocumentError(f"Entity {entity_id} source layer has missing bundle Artifact")
    if source_layer["layer_artifact_id"] not in reference_ids:
        raise DocumentError(f"Entity {entity_id} source layer has missing layer Artifact")
    run_identity = source_layer["run_identity"]
    if (
        not isinstance(run_identity, str)
        or len(run_identity) != 71
        or not run_identity.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in run_identity[7:])
    ):
        raise DocumentError(f"Entity {entity_id} source layer has invalid run identity")
    order = source_layer["order"]
    if (
        not isinstance(order, dict)
        or set(order) != {"index", "semantics"}
        or not isinstance(order["index"], int)
        or isinstance(order["index"], bool)
        or order["index"] < 0
        or not isinstance(order["semantics"], str)
        or re.fullmatch(
            r"svm-order:[a-z0-9][a-z0-9_-]*@[0-9]+\.[0-9]+",
            order["semantics"],
        )
        is None
    ):
        raise DocumentError(f"Entity {entity_id} source layer has invalid order evidence")


def _validate_structural_relations(
    relations: Any,
    entities: list[dict[str, Any]],
    known_entities: set[str],
    reference_ids: set[str],
) -> None:
    if not isinstance(relations, list):
        raise DocumentError("Structural relations must be an array")
    entity_by_id = {entity["id"]: entity for entity in entities}
    relation_ids: set[str] = set()
    for relation in relations:
        if not isinstance(relation, dict):
            raise DocumentError("Structural relation must be an object")
        relation_id = relation.get("id")
        if not isinstance(relation_id, str) or not relation_id.startswith("relation:"):
            raise DocumentError("Structural relation requires a relation: ID")
        if relation_id in relation_ids:
            raise DocumentError(f"Duplicate structural relation ID {relation_id}")
        relation_ids.add(relation_id)
        relation_type = relation.get("type")
        if relation_type == "derived-from":
            _validate_derived_from(relation, entity_by_id, known_entities, reference_ids)
        elif relation_type == "bounds-contains":
            _validate_bounds_contains(relation, entity_by_id, known_entities, reference_ids)
        else:
            raise DocumentError(f"Unsupported structural relation type {relation_type!r}")
        content = {key: value for key, value in relation.items() if key != "id"}
        expected_id = structural_relation_id(content)
        if relation_id != expected_id:
            raise DocumentError(
                f"Structural relation ID {relation_id} must equal canonical ID {expected_id}"
            )
    if [relation["id"] for relation in relations] != sorted(relation_ids):
        raise DocumentError("Structural relations must be sorted by canonical relation ID")
    expected = materialize_promoted_relations(entities)
    if relations != expected:
        raise DocumentError(
            "Structural relations must equal the complete canonical promoted relation graph"
        )


def _validate_derived_from(
    relation: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
    known_entities: set[str],
    reference_ids: set[str],
) -> None:
    expected = {"id", "type", "subject", "artifact_id", "candidate_id", "component_digest"}
    if set(relation) != expected or relation.get("subject") not in known_entities:
        raise DocumentError("derived-from relation fields or subject are invalid")
    if relation.get("artifact_id") not in reference_ids:
        raise DocumentError("derived-from relation references a missing Artifact")
    provenance = entity_by_id[relation["subject"]].get("provenance")
    if not isinstance(provenance, dict) or any(
        relation[field] != provenance.get(field)
        for field in ("artifact_id", "candidate_id", "component_digest")
    ):
        raise DocumentError("derived-from relation does not match Entity provenance")


def _validate_bounds_contains(
    relation: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
    known_entities: set[str],
    reference_ids: set[str],
) -> None:
    if set(relation) != {"id", "type", "container", "contained", "evidence"}:
        raise DocumentError("bounds-contains relation fields are invalid")
    container_id, contained_id = relation.get("container"), relation.get("contained")
    if (
        container_id not in known_entities
        or contained_id not in known_entities
        or container_id == contained_id
    ):
        raise DocumentError("bounds-contains relation Entity endpoints are invalid")
    evidence = relation.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {
        "artifact_id",
        "container_candidate_id",
        "contained_candidate_id",
        "basis",
    }:
        raise DocumentError("bounds-contains relation evidence fields are invalid")
    if evidence["artifact_id"] not in reference_ids:
        raise DocumentError("bounds-contains relation references a missing Artifact")
    if evidence["basis"] != "strict-half-open-bounds@0.1":
        raise DocumentError("bounds-contains relation basis is unsupported")
    container = entity_by_id[container_id].get("provenance")
    contained = entity_by_id[contained_id].get("provenance")
    if not isinstance(container, dict) or not isinstance(contained, dict):
        raise DocumentError("bounds-contains relation requires promoted Entity provenance")
    if (
        container.get("artifact_id") != evidence["artifact_id"]
        or contained.get("artifact_id") != evidence["artifact_id"]
        or container.get("candidate_id") != evidence["container_candidate_id"]
        or contained.get("candidate_id") != evidence["contained_candidate_id"]
        or not strictly_bounds_contains(provenance_bounds(container), provenance_bounds(contained))
    ):
        raise DocumentError("bounds-contains relation is not supported by Entity evidence")
    for intermediate_id, intermediate_entity in entity_by_id.items():
        if intermediate_id in {container_id, contained_id}:
            continue
        intermediate = intermediate_entity.get("provenance")
        if (
            isinstance(intermediate, dict)
            and intermediate.get("type") == "PromotedComponent"
            and intermediate.get("artifact_id") == evidence["artifact_id"]
            and strictly_bounds_contains(
                provenance_bounds(container), provenance_bounds(intermediate)
            )
            and strictly_bounds_contains(
                provenance_bounds(intermediate), provenance_bounds(contained)
            )
        ):
            raise DocumentError("bounds-contains relation must describe immediate containment")


def _bounds(value: Any) -> tuple[int, int, int, int] | None:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(not isinstance(item, int) or isinstance(item, bool) for item in value)
        or not (0 <= value[0] < value[2])
        or not (0 <= value[1] < value[3])
    ):
        return None
    return value[0], value[1], value[2], value[3]
