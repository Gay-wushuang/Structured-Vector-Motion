from __future__ import annotations

import copy
import hashlib
import math
from bisect import bisect_right
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import ArtifactKind, ArtifactResolver, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EntityDiffPreview,
    EvaluationReport,
    GeneratorProvenance,
    MatchScorePreview,
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

MATCHER_IDENTITY = "svm-multifeature-greedy@0.2"
CONTOUR_SAMPLE_COUNT = 128
AREA_SAMPLES_PER_SUBPATH = 128
MAX_DESCRIPTOR_SEGMENTS = 10_000
MATCH_WEIGHTS = {
    "iou": 0.35,
    "centroid": 0.20,
    "area": 0.15,
    "contour": 0.30,
}


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
    score: MatchScorePreview


@dataclass(frozen=True)
class _ShapeDescriptor:
    bounds: tuple[float, float, float, float]
    centroid: tuple[float, float]
    area: float
    normalized_contour: tuple[tuple[float, float], ...]


class BitmapReconcileAdapter:
    adapter_id = "adapter:bitmap-reconcile"
    adapter_version = "0.2"

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
        matches = _match(existing, traced.paths, trace_options.fill_rule, match_threshold)
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
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine=self.tracer.engine_name,
            engine_version=self.tracer.engine_version,
            parameters={
                "namespace": namespace,
                "matcher": MATCHER_IDENTITY,
                "match_score_threshold": match_threshold,
                "match_weights": copy.deepcopy(MATCH_WEIGHTS),
                "contour_sample_count": CONTOUR_SAMPLE_COUNT,
                "area_samples_per_subpath": AREA_SAMPLES_PER_SUBPATH,
                "max_descriptor_segments": MAX_DESCRIPTOR_SEGMENTS,
                **trace_options.provenance(),
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "generator": asdict(generator),
                    "required_artifact_ids": (artifact.artifact_id,),
                    "artifact_content_hash": artifact.content_hash,
                    "change": asdict(change),
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:bitmap-reconcile:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
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
            confidence=min((match.score.composite for match in matches), default=0.0),
            notes="Previewable deterministic multi-feature Entity reconciliation",
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
        unsupported_bindings = [
            binding
            for binding in document["construction"]["output_bindings"]
            if binding["entity"] == entity_id and binding["property"] != "geometry"
        ]
        if unsupported_bindings:
            properties = ", ".join(sorted(binding["property"] for binding in unsupported_bindings))
            raise BitmapTraceError(
                f"Entity {entity_id} has unsupported non-geometry binding(s): {properties}"
            )
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
    legacy_threshold = raw.pop("match_iou_threshold", None)
    match_threshold = raw.pop("match_score_threshold", None)
    if legacy_threshold is not None:
        raise BitmapTraceError(
            "match_iou_threshold is no longer supported; use match_score_threshold instead"
        )
    if match_threshold is None:
        match_threshold = 0.65
    namespace = raw.get("namespace", "reconciled")
    if not isinstance(namespace, str) or not namespace.replace("-", "").isalnum():
        raise BitmapTraceError("Reconciliation namespace must contain letters, digits, or hyphens")
    if (
        isinstance(match_threshold, bool)
        or not isinstance(match_threshold, (int, float))
        or not math.isfinite(float(match_threshold))
        or not 0 < match_threshold <= 1
    ):
        raise BitmapTraceError(
            "match_score_threshold must be a finite number greater than 0 and at most 1"
        )
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
    proposed_fill_rule: str,
    threshold: float,
) -> tuple[_Match, ...]:
    old_descriptors = [
        _shape_descriptor(
            component.path_operation["parameters"]["d"],
            component.bounds,
            component.planar_operation["parameters"]["fill_rule"],
        )
        for component in existing
    ]
    new_descriptors = [
        _shape_descriptor(path.d, path.bounds, proposed_fill_rule) for path in proposed
    ]
    candidates: list[tuple[float, str, int, int, MatchScorePreview]] = []
    for old_index, old in enumerate(existing):
        for new_index in range(len(proposed)):
            score = _feature_score(old_descriptors[old_index], new_descriptors[new_index])
            if score.composite >= threshold:
                candidates.append((-score.composite, old.entity_id, new_index, old_index, score))
    candidates.sort()
    used_old: set[int] = set()
    used_new: set[int] = set()
    matches = []
    for _, _, new_index, old_index, score in candidates:
        if old_index in used_old or new_index in used_new:
            continue
        used_old.add(old_index)
        used_new.add(new_index)
        matches.append(_Match(old_index, new_index, score))
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


def _shape_descriptor(
    path_data: str,
    bounds: tuple[float, float, float, float],
    fill_rule: str,
) -> _ShapeDescriptor:
    try:
        from svgpathtools import parse_path  # pyright: ignore[reportMissingImports]

        path = parse_path(path_data)
        subpaths = path.continuous_subpaths()
    except (AssertionError, TypeError, ValueError) as exc:
        raise BitmapTraceError(f"Cannot describe reconciliation path: {exc}") from exc
    segments = [segment for subpath in subpaths for segment in subpath]
    if not segments or len(segments) > MAX_DESCRIPTOR_SEGMENTS:
        raise BitmapTraceError(
            f"Reconciliation path must contain 1 to {MAX_DESCRIPTOR_SEGMENTS} segments"
        )

    rings: list[tuple[tuple[float, float], ...]] = []
    for subpath in subpaths:
        rings.append(_sample_segments_by_arc_length(list(subpath), AREA_SAMPLES_PER_SUBPATH))

    ring_metrics = [_ring_metrics(ring) for ring in rings]
    coefficients = _fill_coefficients(rings, ring_metrics, fill_rule)
    area = sum(
        coefficient * abs(metrics[0]) / 2
        for coefficient, metrics in zip(coefficients, ring_metrics, strict=True)
    )
    if area > 1e-12:
        centroid = (
            sum(
                coefficient * abs(metrics[0]) / 2 * metrics[1][0]
                for coefficient, metrics in zip(coefficients, ring_metrics, strict=True)
            )
            / area,
            sum(
                coefficient * abs(metrics[0]) / 2 * metrics[1][1]
                for coefficient, metrics in zip(coefficients, ring_metrics, strict=True)
            )
            / area,
        )
    else:
        centroid = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        area = 0.0

    contour = tuple(
        _normalize_point(point, bounds)
        for point in _sample_segments_by_arc_length(segments, CONTOUR_SAMPLE_COUNT)
    )
    return _ShapeDescriptor(bounds, centroid, area, contour)


def _feature_score(left: _ShapeDescriptor, right: _ShapeDescriptor) -> MatchScorePreview:
    iou = _bounds_iou(left.bounds, right.bounds)
    centroid = _centroid_score(left, right)
    area = _area_score(left.area, right.area)
    contour = _contour_score(left.normalized_contour, right.normalized_contour)
    values = {
        "iou": _canonical_score(iou),
        "centroid": _canonical_score(centroid),
        "area": _canonical_score(area),
        "contour": _canonical_score(contour),
    }
    composite = sum(MATCH_WEIGHTS[name] * values[name] for name in MATCH_WEIGHTS)
    return MatchScorePreview(
        iou=values["iou"],
        centroid=values["centroid"],
        area=values["area"],
        contour=values["contour"],
        composite=_canonical_score(composite),
    )


def _centroid_score(left: _ShapeDescriptor, right: _ShapeDescriptor) -> float:
    distance = math.hypot(
        left.centroid[0] - right.centroid[0], left.centroid[1] - right.centroid[1]
    )
    union_width = max(left.bounds[2], right.bounds[2]) - min(left.bounds[0], right.bounds[0])
    union_height = max(left.bounds[3], right.bounds[3]) - min(left.bounds[1], right.bounds[1])
    diagonal = math.hypot(union_width, union_height)
    return max(0.0, 1 - distance / diagonal) if diagonal else float(distance == 0)


def _area_score(left: float, right: float) -> float:
    largest = max(left, right)
    return min(left, right) / largest if largest > 0 else float(left == right)


def _contour_score(
    left: tuple[tuple[float, float], ...], right: tuple[tuple[float, float], ...]
) -> float:
    def directed(
        source: tuple[tuple[float, float], ...], target: tuple[tuple[float, float], ...]
    ) -> float:
        return sum(
            min(math.hypot(x - other_x, y - other_y) for other_x, other_y in target)
            for x, y in source
        ) / len(source)

    chamfer = (directed(left, right) + directed(right, left)) / 2
    return max(0.0, 1 - chamfer / math.sqrt(2))


def _sample_segments_by_arc_length(
    segments: list[Any], sample_count: int
) -> tuple[tuple[float, float], ...]:
    lengths = [float(segment.length()) for segment in segments]
    cumulative = []
    total = 0.0
    for length in lengths:
        if not math.isfinite(length) or length < 0:
            raise BitmapTraceError("Reconciliation path produced an invalid segment length")
        total += length
        cumulative.append(total)
    if total <= 0:
        return tuple(_complex_point(segments[0].point(0)) for _ in range(sample_count))

    points = []
    for sample in range(sample_count):
        distance = total * sample / sample_count
        index = min(bisect_right(cumulative, distance), len(segments) - 1)
        prior = cumulative[index - 1] if index else 0.0
        local_distance = distance - prior
        parameter = segments[index].ilength(local_distance) if lengths[index] else 0.0
        points.append(_complex_point(segments[index].point(parameter)))
    return tuple(points)


def _ring_metrics(
    ring: tuple[tuple[float, float], ...],
) -> tuple[float, tuple[float, float]]:
    area_twice = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for first, second in zip(ring, ring[1:] + ring[:1], strict=True):
        cross = first[0] * second[1] - second[0] * first[1]
        area_twice += cross
        centroid_x += (first[0] + second[0]) * cross
        centroid_y += (first[1] + second[1]) * cross
    if abs(area_twice) <= 1e-12:
        return area_twice, ring[0]
    return area_twice, (centroid_x / (3 * area_twice), centroid_y / (3 * area_twice))


def _fill_coefficients(
    rings: list[tuple[tuple[float, float], ...]],
    metrics: list[tuple[float, tuple[float, float]]],
    fill_rule: str,
) -> tuple[int, ...]:
    coefficients = []
    orientations = [1 if metric[0] > 0 else -1 for metric in metrics]
    for index, ring in enumerate(rings):
        containing = [
            other_index
            for other_index, other in enumerate(rings)
            if other_index != index and _point_in_ring(ring[0], other)
        ]
        if fill_rule == "evenodd":
            coefficients.append(1 if len(containing) % 2 == 0 else -1)
            continue
        outside_winding = sum(orientations[other_index] for other_index in containing)
        inside_winding = outside_winding + orientations[index]
        coefficients.append(int(inside_winding != 0) - int(outside_winding != 0))
    return tuple(coefficients)


def _point_in_ring(point: tuple[float, float], ring: tuple[tuple[float, float], ...]) -> bool:
    x, y = point
    inside = False
    for first, second in zip(ring, ring[1:] + ring[:1], strict=True):
        if (first[1] > y) != (second[1] > y):
            crossing_x = (second[0] - first[0]) * (y - first[1]) / (second[1] - first[1])
            crossing_x += first[0]
            if x < crossing_x:
                inside = not inside
    return inside


def _complex_point(point: complex) -> tuple[float, float]:
    x, y = float(point.real), float(point.imag)
    if not math.isfinite(x) or not math.isfinite(y):
        raise BitmapTraceError("Reconciliation path produced non-finite samples")
    return x, y


def _normalize_point(
    point: tuple[float, float], bounds: tuple[float, float, float, float]
) -> tuple[float, float]:
    center_x = (bounds[0] + bounds[2]) / 2
    center_y = (bounds[1] + bounds[3]) / 2
    scale = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
    return (
        (point[0] - center_x) / scale if scale else 0.0,
        (point[1] - center_y) / scale if scale else 0.0,
    )


def _canonical_score(value: float) -> float:
    return float(format(min(1.0, max(0.0, value)), ".12g"))


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
