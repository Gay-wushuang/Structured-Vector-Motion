from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .backends import GeometryBackend
from .operations import (
    OperationExecutionContext,
    OperationRegistry,
    OperationValidationError,
    get_operation_registry,
)


class EvaluationState(StrEnum):
    UNEVALUATED = "UNEVALUATED"
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    EVALUATING = "EVALUATING"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class Quality(StrEnum):
    INTERACTIVE = "INTERACTIVE"
    PREVIEW = "PREVIEW"
    FINAL = "FINAL"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


@dataclass(frozen=True)
class ImmutableValue:
    value_id: str
    payload: Any

    @classmethod
    def create(cls, payload: Any) -> ImmutableValue:
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        return cls(f"sha256:{digest}", payload)


@dataclass
class RuntimeNode:
    state: EvaluationState = EvaluationState.UNEVALUATED
    outputs: dict[str, ImmutableValue] | None = None
    stale_outputs: dict[str, ImmutableValue] | None = None
    evaluation_key: str | None = None
    evaluated_quality: Quality | None = None
    backend_identity: str | None = None
    error: str | None = None
    cache_hit: bool = False


class DocumentError(ValueError):
    pass


class Evaluator:
    """Small deterministic evaluator used to force-test the v0.1 model."""

    def __init__(
        self,
        document: dict[str, Any],
        *,
        geometry_backend: GeometryBackend | None = None,
        value_cache: dict[str, dict[str, ImmutableValue]] | None = None,
    ):
        self.document = document
        self.geometry_backend = geometry_backend
        self.value_cache = value_cache
        try:
            self.registry: OperationRegistry = get_operation_registry(
                document.get("semantics_version", "")
            )
        except OperationValidationError as exc:
            raise DocumentError(str(exc)) from exc
        self.operations = {
            operation["id"]: operation
            for operation in document.get("construction", {}).get("operations", [])
        }
        self.dependencies: dict[str, set[str]] = {op_id: set() for op_id in self.operations}
        self.dependants: dict[str, set[str]] = {op_id: set() for op_id in self.operations}
        self.runtime = {op_id: RuntimeNode() for op_id in self.operations}
        self._build_graph()
        self.validate()

    def _build_graph(self) -> None:
        for op_id, operation in self.operations.items():
            for slot_id in operation.get("inputs", {}).values():
                dependency_id, _ = self._split_slot(slot_id)
                self.dependencies[op_id].add(dependency_id)
                if dependency_id in self.dependants:
                    self.dependants[dependency_id].add(op_id)

    @staticmethod
    def _split_slot(slot_id: str) -> tuple[str, str]:
        parts = slot_id.rsplit(".", 1)
        if len(parts) != 2 or not all(parts):
            raise DocumentError(f"Invalid output slot: {slot_id}")
        return parts[0], parts[1]

    def validate(self) -> None:
        if self.document.get("schema_version") != "0.1":
            raise DocumentError("Document schema_version must be 0.1")
        if not self.document.get("semantics_version"):
            raise DocumentError("Document requires semantics_version")
        if len(self.operations) != len(self.document["construction"]["operations"]):
            raise DocumentError("Operation IDs must be unique")
        try:
            for operation in self.operations.values():
                self.registry.validate(operation)
        except OperationValidationError as exc:
            raise DocumentError(str(exc)) from exc
        for op_id, deps in self.dependencies.items():
            missing = deps.difference(self.operations)
            if missing:
                raise DocumentError(f"{op_id} references missing operations: {sorted(missing)}")
            operation = self.operations[op_id]
            input_signature = self.registry.input_signature(operation)
            for input_name, slot_id in operation.get("inputs", {}).items():
                dependency_id, output_name = self._split_slot(slot_id)
                output_signature = self.registry.output_signature(self.operations[dependency_id])
                if output_name not in output_signature:
                    raise DocumentError(
                        f"{op_id}.{input_name} references missing output slot {slot_id}"
                    )
                if output_signature[output_name] != input_signature[input_name]:
                    raise DocumentError(
                        f"{op_id}.{input_name} expects {input_signature[input_name].value}, "
                        f"but {slot_id} provides {output_signature[output_name].value}"
                    )
        self._topological_order()

    def _topological_order(self) -> list[str]:
        remaining = {op_id: set(deps) for op_id, deps in self.dependencies.items()}
        ready = sorted(op_id for op_id, deps in remaining.items() if not deps)
        result: list[str] = []
        while ready:
            op_id = ready.pop(0)
            result.append(op_id)
            for dependant in sorted(self.dependants[op_id]):
                remaining[dependant].discard(op_id)
                if not remaining[dependant] and dependant not in result and dependant not in ready:
                    ready.append(dependant)
                    ready.sort()
        if len(result) != len(self.operations):
            raise DocumentError("Construction graph must be acyclic")
        return result

    def invalidate(self, operation_id: str) -> set[str]:
        if operation_id not in self.operations:
            raise KeyError(operation_id)
        affected: set[str] = set()
        pending = [operation_id]
        while pending:
            current = pending.pop()
            if current in affected:
                continue
            affected.add(current)
            node = self.runtime[current]
            node.stale_outputs = node.outputs
            node.state = EvaluationState.DIRTY
            pending.extend(self.dependants[current])
        return affected

    def set_parameter(self, operation_id: str, name: str, value: Any) -> set[str]:
        operation = self.operations[operation_id]
        parameters = operation.setdefault("parameters", {})
        missing = object()
        previous = parameters.get(name, missing)
        parameters[name] = value
        try:
            self.registry.validate(operation)
        except OperationValidationError as exc:
            if previous is missing:
                del parameters[name]
            else:
                parameters[name] = previous
            raise DocumentError(str(exc)) from exc
        return self.invalidate(operation_id)

    def evaluate_all(self, quality: Quality = Quality.PREVIEW) -> None:
        for operation_id in self._topological_order():
            self.evaluate(operation_id, quality)

    def evaluate(self, operation_id: str, quality: Quality = Quality.PREVIEW) -> None:
        node = self.runtime[operation_id]
        operation = self.operations[operation_id]
        inputs: dict[str, Any] = {}
        input_value_ids: dict[str, str] = {}
        for input_name, slot_id in operation.get("inputs", {}).items():
            dependency_id, output_name = self._split_slot(slot_id)
            dependency = self.runtime[dependency_id]
            self.evaluate(dependency_id, quality)
            if dependency.state != EvaluationState.CLEAN or not dependency.outputs:
                node.state = EvaluationState.BLOCKED
                return
            inputs[input_name] = dependency.outputs[output_name].payload
            input_value_ids[input_name] = dependency.outputs[output_name].value_id

        evaluation_key = self._evaluation_key(operation, input_value_ids, quality)
        if node.state == EvaluationState.CLEAN and node.evaluation_key == evaluation_key:
            return

        if self.value_cache is not None and evaluation_key in self.value_cache:
            node.outputs = self.value_cache[evaluation_key]
            node.stale_outputs = None
            node.evaluation_key = evaluation_key
            node.evaluated_quality = quality
            node.backend_identity = self._execution_identity(operation)
            node.error = None
            node.cache_hit = True
            node.state = EvaluationState.CLEAN
            return

        if node.outputs is not None:
            node.stale_outputs = node.outputs
        node.state = EvaluationState.EVALUATING
        try:
            payloads = self._execute(operation, inputs, quality)
            node.outputs = {name: ImmutableValue.create(value) for name, value in payloads.items()}
            node.stale_outputs = None
            node.evaluation_key = evaluation_key
            node.evaluated_quality = quality
            node.backend_identity = self._execution_identity(operation)
            node.error = None
            node.cache_hit = False
            node.state = EvaluationState.CLEAN
            if self.value_cache is not None:
                self.value_cache[evaluation_key] = node.outputs
        except Exception as exc:  # reference runtime records failures for inspection
            node.error = str(exc)
            node.state = EvaluationState.FAILED

    def _evaluation_key(
        self,
        operation: dict[str, Any],
        input_value_ids: dict[str, str],
        quality: Quality,
    ) -> str:
        context = {
            "semantics_version": self.document["semantics_version"],
            "operation_type": operation["type"],
            "parameters": operation.get("parameters", {}),
            "input_value_ids": input_value_ids,
            "quality": quality.value
            if self.registry.definition(operation["type"]).quality_sensitive
            else None,
            "backend": self._execution_identity(operation),
        }
        return f"sha256:{hashlib.sha256(canonical_bytes(context)).hexdigest()}"

    def _execution_identity(self, operation: dict[str, Any]) -> str | None:
        definition = self.registry.definition(operation["type"])
        if definition.capability is None or self.geometry_backend is None:
            return None
        identities = [self.geometry_backend.identity]
        if definition.algorithm_identity is not None:
            identities.append(definition.algorithm_identity)
        return "+".join(identities)

    def _execute(
        self, operation: dict[str, Any], inputs: dict[str, Any], quality: Quality
    ) -> dict[str, Any]:
        return self.registry.evaluate(
            operation,
            inputs,
            OperationExecutionContext(
                quality=quality.value,
                geometry_backend=self.geometry_backend,
            ),
        )
