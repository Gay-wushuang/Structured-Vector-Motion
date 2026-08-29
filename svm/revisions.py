from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from .document import validate_document
from .evaluator import DocumentError, canonical_bytes


class Change(Protocol):
    def apply(self, document: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class SplitPart:
    entity_id: str
    name: str
    output_name: str
    selector: dict[str, Any]


@dataclass(frozen=True)
class SplitEntityChange:
    source_entity_id: str
    operation_id: str
    parts: tuple[SplitPart, ...]

    def apply(self, document: dict[str, Any]) -> None:
        entities = document["entities"]
        entity_by_id = {entity["id"]: entity for entity in entities}
        if self.source_entity_id not in entity_by_id:
            raise DocumentError(f"Cannot split missing entity {self.source_entity_id}")
        if self.operation_id in {op["id"] for op in document["construction"]["operations"]}:
            raise DocumentError(f"Operation already exists: {self.operation_id}")
        if not self.parts:
            raise DocumentError("SplitEntity requires at least one part")

        new_ids = [part.entity_id for part in self.parts]
        if len(new_ids) != len(set(new_ids)) or set(new_ids).intersection(entity_by_id):
            raise DocumentError("SplitEntity child IDs must be new and unique")
        output_names = [part.output_name for part in self.parts]
        if len(output_names) != len(set(output_names)):
            raise DocumentError("SplitEntity output names must be unique")

        source_bindings = [
            binding
            for binding in document["construction"]["output_bindings"]
            if binding["entity"] == self.source_entity_id and binding["property"] == "geometry"
        ]
        if len(source_bindings) != 1:
            raise DocumentError("SplitEntity source requires exactly one geometry binding")

        for part in self.parts:
            entities.append(
                {"id": part.entity_id, "name": part.name, "parent_id": self.source_entity_id}
            )

        document["construction"]["operations"].append(
            {
                "id": self.operation_id,
                "type": "SplitEntity",
                "inputs": {"geometry": source_bindings[0]["slot"]},
                "parameters": {
                    "parts": [
                        {
                            "entity_id": part.entity_id,
                            "output_name": part.output_name,
                            "selector": copy.deepcopy(part.selector),
                        }
                        for part in self.parts
                    ]
                },
            }
        )
        for part in self.parts:
            document["construction"]["output_bindings"].append(
                {
                    "entity": part.entity_id,
                    "property": "geometry",
                    "slot": f"{self.operation_id}.{part.output_name}",
                }
            )

        render_stack = document["presentation"]["render_stack"]
        try:
            source_index = render_stack.index(self.source_entity_id)
        except ValueError as exc:
            raise DocumentError("SplitEntity source must occur in the render stack") from exc
        render_stack[source_index : source_index + 1] = new_ids


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    changes: tuple[Change, ...]
    message: str = ""

    def apply(self, base_document: dict[str, Any]) -> dict[str, Any]:
        candidate = copy.deepcopy(base_document)
        for change in self.changes:
            change.apply(candidate)
        validate_document(candidate)
        return candidate


@dataclass(frozen=True)
class Revision:
    revision_id: str
    parent_ids: tuple[str, ...]
    transaction_id: str | None
    document_hash: str
    message: str = ""


@dataclass
class RevisionStore:
    revisions: dict[str, Revision] = field(default_factory=dict)
    _documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    head: str | None = None

    @classmethod
    def create(cls, document: dict[str, Any], message: str = "Initial revision") -> "RevisionStore":
        validate_document(document)
        store = cls()
        revision = store._make_revision(document, (), None, message)
        store.revisions[revision.revision_id] = revision
        store._documents[revision.revision_id] = copy.deepcopy(document)
        store.head = revision.revision_id
        return store

    def commit(self, base_revision_id: str, transaction: Transaction) -> Revision:
        if base_revision_id not in self.revisions:
            raise KeyError(base_revision_id)
        candidate = transaction.apply(self._documents[base_revision_id])
        revision = self._make_revision(
            candidate, (base_revision_id,), transaction.transaction_id, transaction.message
        )
        self.revisions[revision.revision_id] = revision
        self._documents[revision.revision_id] = copy.deepcopy(candidate)
        self.head = revision.revision_id
        return revision

    def checkout(self, revision_id: str) -> dict[str, Any]:
        if revision_id not in self._documents:
            raise KeyError(revision_id)
        self.head = revision_id
        return copy.deepcopy(self._documents[revision_id])

    def get_document(self, revision_id: str) -> dict[str, Any]:
        """Return an isolated snapshot without changing the active head."""
        if revision_id not in self._documents:
            raise KeyError(revision_id)
        return copy.deepcopy(self._documents[revision_id])

    def undo(self, revision_id: str | None = None) -> dict[str, Any]:
        current_id = revision_id or self.head
        if current_id is None or current_id not in self.revisions:
            raise KeyError(current_id)
        parents = self.revisions[current_id].parent_ids
        if not parents:
            raise DocumentError("Initial revision cannot be undone")
        return self.checkout(parents[0])

    @staticmethod
    def _make_revision(
        document: dict[str, Any],
        parent_ids: tuple[str, ...],
        transaction_id: str | None,
        message: str,
    ) -> Revision:
        document_hash = f"sha256:{hashlib.sha256(canonical_bytes(document)).hexdigest()}"
        revision_payload = {
            "document_hash": document_hash,
            "parent_ids": parent_ids,
            "transaction_id": transaction_id,
            "message": message,
        }
        revision_id = f"revision:{hashlib.sha256(canonical_bytes(revision_payload)).hexdigest()}"
        return Revision(revision_id, parent_ids, transaction_id, document_hash, message)
