from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EvaluationState(str, Enum):
    UNEVALUATED = "UNEVALUATED"
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    EVALUATING = "EVALUATING"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class Quality(str, Enum):
    INTERACTIVE = "INTERACTIVE"
    PREVIEW = "PREVIEW"
    FINAL = "FINAL"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass(frozen=True)
class ImmutableValue:
    value_id: str
    payload: Any

    @classmethod
    def create(cls, payload: Any) -> "ImmutableValue":
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        return cls(f"sha256:{digest}", payload)


@dataclass
class RuntimeNode:
    state: EvaluationState = EvaluationState.UNEVALUATED
    outputs: dict[str, ImmutableValue] | None = None
    stale_outputs: dict[str, ImmutableValue] | None = None
    error: str | None = None


class DocumentError(ValueError):
    pass


class Evaluator:
    """Small deterministic evaluator used to force-test the v0.1 model."""

    def __init__(self, document: dict[str, Any]):
        self.document = document
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
        for op_id, deps in self.dependencies.items():
            missing = deps.difference(self.operations)
            if missing:
                raise DocumentError(f"{op_id} references missing operations: {sorted(missing)}")
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
        self.operations[operation_id].setdefault("parameters", {})[name] = value
        return self.invalidate(operation_id)

    def evaluate_all(self, quality: Quality = Quality.PREVIEW) -> None:
        for operation_id in self._topological_order():
            if self.runtime[operation_id].state != EvaluationState.CLEAN:
                self.evaluate(operation_id, quality)

    def evaluate(self, operation_id: str, quality: Quality = Quality.PREVIEW) -> None:
        node = self.runtime[operation_id]
        operation = self.operations[operation_id]
        inputs: dict[str, Any] = {}
        for input_name, slot_id in operation.get("inputs", {}).items():
            dependency_id, output_name = self._split_slot(slot_id)
            dependency = self.runtime[dependency_id]
            if dependency.state != EvaluationState.CLEAN:
                self.evaluate(dependency_id, quality)
            if dependency.state != EvaluationState.CLEAN or not dependency.outputs:
                node.state = EvaluationState.BLOCKED
                return
            inputs[input_name] = dependency.outputs[output_name].payload

        node.state = EvaluationState.EVALUATING
        try:
            payloads = self._execute(operation, inputs, quality)
            node.outputs = {name: ImmutableValue.create(value) for name, value in payloads.items()}
            node.stale_outputs = None
            node.error = None
            node.state = EvaluationState.CLEAN
        except Exception as exc:  # reference runtime records failures for inspection
            node.error = str(exc)
            node.state = EvaluationState.FAILED

    def _execute(self, operation: dict[str, Any], inputs: dict[str, Any], quality: Quality) -> dict[str, Any]:
        params = operation.get("parameters", {})
        op_type = operation["type"]
        if op_type == "CreateEllipse":
            return {"geometry": {"kind": "ellipse", "cx": params["cx"], "cy": params["cy"], "rx": params["rx"], "ry": params["ry"]}}
        if op_type == "CreateRectangle":
            return {"geometry": {"kind": "rectangle", **params}}
        if op_type == "Transform":
            return {"geometry": {"kind": "transform", "source": inputs["geometry"], "matrix": params["matrix"]}}
        if op_type == "ConvertToPath":
            return {"geometry": {"kind": "path", "source": inputs["geometry"]}}
        if op_type == "RefineBezier":
            return {"geometry": {"kind": "refined_path", "source": inputs["geometry"], "tolerance": params["tolerance"], "quality": quality.value}}
        if op_type == "Clip":
            return {"geometry": {"kind": "clip", "content": inputs["content"], "clip": inputs["clip"]}}
        if op_type == "SplitEntity":
            source = inputs["geometry"]
            return {
                part["output_name"]: {
                    "kind": "split_part",
                    "source": source,
                    "entity_id": part["entity_id"],
                    "selector": part["selector"],
                }
                for part in params["parts"]
            }
        raise DocumentError(f"Unsupported operation type: {op_type}")
