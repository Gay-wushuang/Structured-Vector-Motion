from __future__ import annotations

import copy
import hashlib
import math
from dataclasses import dataclass
from typing import Any

from ..artifacts import ArtifactKind, ArtifactResolver, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EntityDiffPreview,
    EvaluationReport,
    GeneratorProvenance,
    Proposal,
    ProposalPreview,
)
from ..revisions import ReplaceSceneFragmentChange, Transaction
from .bitmap_trace import (
    BITMAP_MEDIA_TYPES,
    BitmapTraceError,
    BitmapTracer,
    PotracerEngine,
    TracedPath,
    TraceOptions,
    TraceResult,
)

MATCHER_IDENTITY = "svm-bounds-iou-greedy@0.1"


@dataclass(frozen=True)
class _ExistingComponent:
    entity: dict[str, Any]
    path_operation: dict[str, Any]
    planar_operation: dict[str, Any]
    binding: dict[str, Any]
    style: dict[str, Any]

    @property
    def entity_id(self) -> str:
        return self.entity["id"]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return tuple(self.path_operation["parameters"]["bounds"])


@dataclass(frozen=True)
class _Match:
    existing_index: int
    proposed_index: int
    score: float


class BitmapReconcileAdapter:
    adapter_id = "adapter:bitmap-reconcile"
    adapter_version = "0.1"

    def __init__(self, tracer: BitmapTracer | None = None) -> None:
        self.tracer = tracer or PotracerEngine()

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        existing = _extract_scope(request.document, request.scope)
        trace_options, match_threshold, namespace = _options(request.options)
        artifact = _select_artifact(
            artifacts.resolve_as(
                request.artifact_ids,
                kind=ArtifactKind.REFERENCE,
                media_types=frozenset(BITMAP_MEDIA_TYPES),
            )
        )
        traced = self.tracer.trace(artifact.content, trace_options)
        if isinstance(traced, TracedPath):
            traced = TraceResult((traced,))
        matches = _match(existing, traced.paths, match_threshold)
        match_by_proposed = {match.proposed_index: match for match in matches}
        matched_existing = {match.existing_index for match in matches}

        known_entity_ids = {entity["id"] for entity in request.document["entities"]}
        known_operation_ids = {
            operation["id"] for operation in request.document["construction"]["operations"]
        }
        entities: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []
        bindings: list[dict[str, Any]] = []
        styles: list[dict[str, Any]] = []
        preview_items: list[EntityDiffPreview] = []

        for proposed_index, path in enumerate(traced.paths):
            match = match_by_proposed.get(proposed_index)
            if match is not None:
                old = existing[match.existing_index]
                entity = copy.deepcopy(old.entity)
                path_operation = copy.deepcopy(old.path_operation)
                planar_operation = copy.deepcopy(old.planar_operation)
                path_operation["parameters"] = {"d": path.d, "bounds": list(path.bounds)}
                planar_operation["parameters"] = {
                    "tolerance": trace_options.path_tolerance,
                    "fill_rule": trace_options.fill_rule,
                }
                binding = copy.deepcopy(old.binding)
                style = copy.deepcopy(old.style)
                unchanged = (
                    old.path_operation["parameters"] == path_operation["parameters"]
                    and old.planar_operation["parameters"] == planar_operation["parameters"]
                )
                preview_items.append(
                    EntityDiffPreview(
                        status="unchanged" if unchanged else "changed",
                        entity_id=old.entity_id,
                        proposed_entity_id=old.entity_id,
                        match_score=match.score,
                        before_bounds=old.bounds,
                        after_bounds=path.bounds,
                    )
                )
            else:
                entity_id, path_id, planar_id = _allocate_added_ids(
                    namespace,
                    path,
                    known_entity_ids,
                    known_operation_ids,
                )
                known_entity_ids.add(entity_id)
                known_operation_ids.update((path_id, planar_id))
                entity = {"id": entity_id, "name": f"Bitmap trace {namespace} added component"}
                path_operation = {
                    "id": path_id,
                    "type": "CreatePath",
                    "inputs": {},
                    "parameters": {"d": path.d, "bounds": list(path.bounds)},
                }
                planar_operation = {
                    "id": planar_id,
                    "type": "PathToPolygon",
                    "inputs": {"path": f"{path_id}.geometry"},
                    "parameters": {
                        "tolerance": trace_options.path_tolerance,
                        "fill_rule": trace_options.fill_rule,
                    },
                }
                binding = {
                    "entity": entity_id,
                    "property": "geometry",
                    "slot": f"{planar_id}.geometry",
                }
                style = _default_style(entity_id)
                preview_items.append(
                    EntityDiffPreview(
                        status="added",
                        entity_id=None,
                        proposed_entity_id=entity_id,
                        after_bounds=path.bounds,
                    )
                )
            entities.append(entity)
            operations.extend((path_operation, planar_operation))
            bindings.append(binding)
            styles.append(style)

        for existing_index, old in enumerate(existing):
            if existing_index not in matched_existing:
                preview_items.append(
                    EntityDiffPreview(
                        status="removed",
                        entity_id=old.entity_id,
                        proposed_entity_id=None,
                        before_bounds=old.bounds,
                    )
                )

        existing_entity_ids = tuple(component.entity_id for component in existing)
        owned_operation_ids = tuple(
            operation_id
            for component in existing
            for operation_id in (
                component.path_operation["id"],
                component.planar_operation["id"],
            )
        )
        proposed_render_stack = tuple(entity["id"] for entity in entities)
        change = ReplaceSceneFragmentChange(
            existing_entity_ids=existing_entity_ids,
            owned_operation_ids=owned_operation_ids,
            entities=tuple(entities),
            operations=tuple(operations),
            output_bindings=tuple(bindings),
            render_entries=proposed_render_stack,
            styles=tuple(styles),
            references=(artifact.document_reference(),),
        )
        counts = {
            status: sum(item.status == status for item in preview_items)
            for status in ("unchanged", "changed", "added", "removed")
        }
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "artifact": artifact.content_hash,
                    "scope": existing_entity_ids,
                    "options": trace_options.provenance(),
                    "match_threshold": match_threshold,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:bitmap-reconcile:{digest}",
            base_revision_id=request.base_revision_id,
            generator=GeneratorProvenance(
                adapter_id=self.adapter_id,
                adapter_version=self.adapter_version,
                engine=self.tracer.engine_name,
                engine_version=self.tracer.engine_version,
                parameters={
                    "namespace": namespace,
                    "matcher": MATCHER_IDENTITY,
                    "match_iou_threshold": match_threshold,
                    **trace_options.provenance(),
                },
            ),
            transaction=Transaction(
                transaction_id=f"transaction:bitmap-reconcile:{digest}",
                changes=(change,),
                message="Reconcile traced components while preserving matched Entity identity",
            ),
            report=EvaluationReport(metrics={name: float(value) for name, value in counts.items()}),
            preview=ProposalPreview(
                entity_diffs=tuple(preview_items),
                proposed_render_stack=proposed_render_stack,
            ),
            required_artifact_ids=(artifact.artifact_id,),
            confidence=min((match.score for match in matches), default=0.0),
            notes="Previewable deterministic bounds-IoU Entity reconciliation",
        )


def _extract_scope(document: dict[str, Any], scope: tuple[str, ...]) -> list[_ExistingComponent]:
    if not scope or len(scope) != len(set(scope)):
        raise BitmapTraceError("Reconciliation scope must contain unique Entity IDs")
    entities = {entity["id"]: entity for entity in document["entities"]}
    operations = {
        operation["id"]: operation for operation in document["construction"]["operations"]
    }
    styles = {style["entity"]: style for style in document["presentation"]["styles"]}
    components = []
    owned: set[str] = set()
    for entity_id in scope:
        if entity_id not in entities:
            raise BitmapTraceError(f"Reconciliation scope contains missing Entity {entity_id}")
        bindings = [
            binding
            for binding in document["construction"]["output_bindings"]
            if binding["entity"] == entity_id and binding["property"] == "geometry"
        ]
        if len(bindings) != 1:
            raise BitmapTraceError(f"Entity {entity_id} requires one geometry binding")
        planar_id = bindings[0]["slot"].rsplit(".", 1)[0]
        planar = operations.get(planar_id)
        if planar is None or planar["type"] != "PathToPolygon":
            raise BitmapTraceError(f"Entity {entity_id} is not backed by PathToPolygon")
        path_slot = planar.get("inputs", {}).get("path", "")
        path_id = path_slot.rsplit(".", 1)[0]
        path = operations.get(path_id)
        if path is None or path["type"] != "CreatePath":
            raise BitmapTraceError(f"Entity {entity_id} is not backed by CreatePath")
        if {path_id, planar_id} & owned:
            raise BitmapTraceError("Reconciliation scope contains shared trace Operations")
        owned.update((path_id, planar_id))
        components.append(
            _ExistingComponent(
                copy.deepcopy(entities[entity_id]),
                copy.deepcopy(path),
                copy.deepcopy(planar),
                copy.deepcopy(bindings[0]),
                copy.deepcopy(styles.get(entity_id, _default_style(entity_id))),
            )
        )
    return components


def _options(values: dict[str, Any]) -> tuple[TraceOptions, float, str]:
    raw = copy.deepcopy(values)
    match_threshold = raw.pop("match_iou_threshold", 0.2)
    namespace = raw.get("namespace", "reconciled")
    if not isinstance(namespace, str) or not namespace.replace("-", "").isalnum():
        raise BitmapTraceError("Reconciliation namespace must contain letters, digits, or hyphens")
    if (
        isinstance(match_threshold, bool)
        or not isinstance(match_threshold, (int, float))
        or not math.isfinite(float(match_threshold))
        or not 0 <= match_threshold <= 1
    ):
        raise BitmapTraceError("match_iou_threshold must be a finite number from 0 to 1")
    return TraceOptions.from_mapping(raw), float(match_threshold), namespace


def _select_artifact(artifacts: tuple[ArtifactSnapshot, ...]) -> ArtifactSnapshot:
    if len(artifacts) != 1:
        raise BitmapTraceError("Bitmap Reconciliation requires exactly one Artifact snapshot")
    artifact = artifacts[0]
    if len(artifact.content) > 32 * 1024 * 1024:
        raise BitmapTraceError("Bitmap Artifact exceeds the 32 MiB trace limit")
    return artifact


def _match(
    existing: list[_ExistingComponent],
    proposed: tuple[TracedPath, ...],
    threshold: float,
) -> tuple[_Match, ...]:
    candidates = []
    for old_index, old in enumerate(existing):
        for new_index, path in enumerate(proposed):
            score = _bounds_iou(old.bounds, path.bounds)
            if score >= threshold:
                candidates.append((-score, old.entity_id, new_index, old_index))
    candidates.sort()
    used_old: set[int] = set()
    used_new: set[int] = set()
    matches = []
    for negative_score, _, new_index, old_index in candidates:
        if old_index in used_old or new_index in used_new:
            continue
        used_old.add(old_index)
        used_new.add(new_index)
        matches.append(_Match(old_index, new_index, float(format(-negative_score, ".12g"))))
    return tuple(matches)


def _bounds_iou(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> float:
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = width * height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def _allocate_added_ids(
    namespace: str,
    path: TracedPath,
    entity_ids: set[str],
    operation_ids: set[str],
) -> tuple[str, str, str]:
    digest = hashlib.sha256(canonical_bytes({"d": path.d, "bounds": path.bounds})).hexdigest()[:12]
    base = f"{namespace}-added-{digest}"
    candidate = base
    suffix = 2
    while (
        f"entity:trace-{candidate}" in entity_ids
        or f"op:trace-{candidate}-path" in operation_ids
        or f"op:trace-{candidate}-planar" in operation_ids
    ):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return (
        f"entity:trace-{candidate}",
        f"op:trace-{candidate}-path",
        f"op:trace-{candidate}-planar",
    )


def _default_style(entity_id: str) -> dict[str, Any]:
    return {
        "entity": entity_id,
        "fill": "#000000",
        "stroke": "none",
        "stroke_width": 1.0,
        "opacity": 1.0,
    }
