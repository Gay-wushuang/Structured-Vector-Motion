from __future__ import annotations

from typing import Any

from .evaluator import DocumentError, Evaluator


def validate_document(document: dict[str, Any]) -> None:
    """Validate cross-record semantics not expressible in JSON Schema alone."""

    Evaluator(document)

    entities = document.get("entities", [])
    entity_ids = [entity.get("id") for entity in entities]
    if len(entity_ids) != len(set(entity_ids)):
        raise DocumentError("Entity IDs must be unique")
    known_entities = set(entity_ids)

    parents: dict[str, str] = {}
    for entity in entities:
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
        operation_id, _ = Evaluator._split_slot(binding.get("slot", ""))
        if operation_id not in {operation["id"] for operation in document["construction"]["operations"]}:
            raise DocumentError(f"Binding references missing output operation {operation_id}")

    for entity_id in document.get("presentation", {}).get("render_stack", []):
        if entity_id not in known_entities:
            raise DocumentError(f"Render stack references missing entity {entity_id}")

