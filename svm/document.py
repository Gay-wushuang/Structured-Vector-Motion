from __future__ import annotations

from typing import Any

from .evaluator import DocumentError, Evaluator
from .policies import PolicyDefinitionError, validate_policy_definitions


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


def _is_supported_color(value: str) -> bool:
    if value == "none":
        return True
    if len(value) not in {7, 9} or not value.startswith("#"):
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value[1:])


def _validate_entity_provenance(entity_id: str, provenance: Any, reference_ids: set[str]) -> None:
    expected = {"type", "artifact_id", "candidate_id", "component_digest"}
    if not isinstance(provenance, dict) or set(provenance) != expected:
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
