from __future__ import annotations

import hashlib
import importlib.metadata
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..path_bounds import canonical_path_bounds
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import AttachSVGGeometryObservationsChange, Transaction
from .svg_import import SVG_MEDIA_TYPES, SVG_NORMALIZATION_IDENTITY, SVGImportAdapter, SVGNormalizer
from .temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2

POLICY_IDENTITY = "svm-svg-polygon-geometry-observation-policy@0.1"
PRODUCER_IDENTITY = "svm-svg-polygon-geometry-observation-producer@0.1"
PRIMITIVE_TYPE = "svg-polygonal-path"
_TOKEN = re.compile(r"[MmLlHhVvZz]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_COMMAND = re.compile(r"[A-Za-z]")
_SYMMETRY_RESIDUAL_LIMIT = 1e-9


class SVGGeometryObservationError(ValueError):
    pass


class SVGGeometryObservationAdapter:
    """Produce v0.2 observations from two frozen asymmetric SVG paths."""

    adapter_id = "adapter:svg-geometry-observations"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise SVGGeometryObservationError("SVG geometry observation scope must be document")
        expected_options = {
            "source_svg_artifact_id",
            "target_svg_artifact_id",
            "source_tick",
            "target_tick",
            "shape_id",
        }
        if set(request.options) != expected_options:
            raise SVGGeometryObservationError(
                "SVG geometry observations require exact sources, ticks, and shape ID"
            )
        source_id = request.options["source_svg_artifact_id"]
        target_id = request.options["target_svg_artifact_id"]
        source_tick = request.options["source_tick"]
        target_tick = request.options["target_tick"]
        shape_id = request.options["shape_id"]
        if (
            not isinstance(source_id, str)
            or not isinstance(target_id, str)
            or source_id == target_id
            or type(source_tick) is not int
            or type(target_tick) is not int
            or source_tick < 0
            or target_tick <= source_tick
            or not isinstance(shape_id, str)
            or not shape_id
        ):
            raise SVGGeometryObservationError(
                "SVG source identities, ticks, or shape ID are invalid"
            )
        snapshots = {item.artifact_id: item for item in artifacts.resolve(request.artifact_ids)}
        if set(snapshots) != {source_id, target_id} or len(request.artifact_ids) != 2:
            raise SVGGeometryObservationError("Artifact IDs must exactly match both SVG sources")
        source = snapshots[source_id]
        target = snapshots[target_id]
        payload = derive_svg_polygon_observations(
            source, target, shape_id, source_tick, target_tick
        )
        provenance = svg_geometry_observation_provenance(source_id, target_id, shape_id)
        observation = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=OBSERVATION_MEDIA_TYPE_V2,
            kind=ArtifactKind.REFERENCE,
            provenance=provenance,
        )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "exact frozen SVG polygon geometry",
            PRODUCER_IDENTITY,
            {
                "geometry_observation_policy": POLICY_IDENTITY,
                "source_svg_artifact_ids": [source_id, target_id],
                "source_tick": source_tick,
                "target_tick": target_tick,
                "shape_id": shape_id,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "observation": observation.artifact_id,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:svg-geometry-observations:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:svg-geometry-observations:{digest}",
                (
                    AttachSVGGeometryObservationsChange(
                        observation.document_reference(),
                        source.document_reference(),
                        target.document_reference(),
                        source_tick,
                        target_tick,
                        shape_id,
                        POLICY_IDENTITY,
                    ),
                ),
                "Attach SVG-derived primitive observations v0.2",
            ),
            report=EvaluationReport(metrics={"observations": 2.0}),
            preview_artifacts=(
                PreviewArtifact(
                    observation.artifact_id, observation.content_hash, observation.media_type
                ),
            ),
            preview=ProposalPreview(),
            required_artifact_ids=(observation.artifact_id, source_id, target_id),
            notes="Exact ordered landmarks come from closed polygonal SVG path commands",
        )


def verify_svg_geometry_observations_change(
    change: Any, resolved: dict[str, ArtifactSnapshot]
) -> None:
    observation = resolved.get(change.observation_reference.get("id"))
    source = resolved.get(change.source_svg_reference.get("id"))
    target = resolved.get(change.target_svg_reference.get("id"))
    if (
        observation is None
        or observation.kind != ArtifactKind.REFERENCE
        or observation.media_type != OBSERVATION_MEDIA_TYPE_V2
        or source is None
        or target is None
    ):
        raise ValueError("SVG geometry observation Artifacts were not resolved")
    if change.producer_policy_identity != POLICY_IDENTITY:
        raise ValueError("SVG geometry observation policy identity is invalid")
    expected = derive_svg_polygon_observations(
        source, target, change.shape_id, change.source_tick, change.target_tick
    )
    if canonical_bytes(expected) != observation.content:
        raise ValueError("SVG geometry observation does not match its exact frozen sources")
    provenance = svg_geometry_observation_provenance(
        source.artifact_id, target.artifact_id, change.shape_id
    )
    if observation.provenance != provenance:
        raise ValueError("SVG geometry observation provenance is invalid")


def derive_svg_polygon_observations(
    source_svg: ArtifactSnapshot,
    target_svg: ArtifactSnapshot,
    shape_id: str,
    source_tick: int,
    target_tick: int,
) -> dict[str, Any]:
    """Pure derivation shared by the producer and acceptance verifier."""

    if (
        source_svg.kind != ArtifactKind.REFERENCE
        or target_svg.kind != ArtifactKind.REFERENCE
        or source_svg.media_type not in SVG_MEDIA_TYPES
        or target_svg.media_type not in SVG_MEDIA_TYPES
    ):
        raise SVGGeometryObservationError("SVG geometry sources must be Reference SVG Artifacts")
    source = _extract_polygon(source_svg, shape_id)
    target = _extract_polygon(target_svg, shape_id)
    if source["canvas"] != target["canvas"]:
        raise SVGGeometryObservationError("SVG observation frames must use the same viewBox")
    if source["topology"] != target["topology"]:
        raise SVGGeometryObservationError("SVG polygon command topology must match exactly")
    return {
        "schema_version": "svm-primitive-observations-0.2",
        "canvas": source["canvas"],
        "frames": [
            _frame(source, source_svg.artifact_id, shape_id, source_tick),
            _frame(target, target_svg.artifact_id, shape_id, target_tick),
        ],
    }


def svg_geometry_observation_provenance(
    source_artifact_id: str, target_artifact_id: str, shape_id: str
) -> dict[str, Any]:
    return {
        "producer_identity": PRODUCER_IDENTITY,
        "producer_version": SVGGeometryObservationAdapter.adapter_version,
        "geometry_observation_policy": POLICY_IDENTITY,
        "source_svg_artifact_ids": [source_artifact_id, target_artifact_id],
        "svg_normalization_identity": SVG_NORMALIZATION_IDENTITY,
        "svgpathtools_version": importlib.metadata.version("svgpathtools"),
        "shape_id": shape_id,
    }


def _extract_polygon(snapshot: ArtifactSnapshot, shape_id: str) -> dict[str, Any]:
    try:
        root = SVGImportAdapter._parse_svg(snapshot)
        rendered = _extract_rendered_entity_polygon(root, shape_id)
        if rendered is not None:
            return rendered
        shapes = SVGNormalizer().normalize(snapshot, "observation")
    except ValueError as exc:
        raise SVGGeometryObservationError(str(exc)) from exc
    if len(shapes) != 1 or shapes[0].operation["type"] != "CreatePath":
        raise SVGGeometryObservationError(
            "SVG geometry observation requires exactly one renderable path"
        )
    elements = [element for element in root.iter() if _local_name(element.tag) == "path"]
    if len(elements) != 1 or elements[0].attrib.get("id") != shape_id:
        raise SVGGeometryObservationError("Both SVG frames must contain the selected path ID")
    view_box = root.attrib.get("viewBox")
    if view_box is None:
        raise SVGGeometryObservationError("SVG geometry observation requires a positive viewBox")
    canvas_values = _view_box(view_box)
    if canvas_values[0] != 0 or canvas_values[1] != 0:
        raise SVGGeometryObservationError("SVG observation viewBox origin must be zero")
    d = shapes[0].operation["parameters"]["d"]
    points, topology = _polygon_vertices(d)
    if _has_rotational_symmetry(points):
        raise SVGGeometryObservationError(
            "UNSUPPORTED_FOR_ASYMMETRIC_SVG_PRODUCER: polygon has rotational symmetry"
        )
    fill = shapes[0].style["fill"]
    if not isinstance(fill, str) or re.fullmatch(r"#[0-9A-F]{6}", fill) is None:
        raise SVGGeometryObservationError("SVG polygon fill must resolve to six-digit hex")
    return {
        "canvas": [_round(canvas_values[2]), _round(canvas_values[3])],
        "points": points,
        "topology": topology,
        "bounds": list(canonical_path_bounds(d)),
        "fill": fill,
    }


def _extract_rendered_entity_polygon(root: ET.Element, shape_id: str) -> dict[str, Any] | None:
    """Read the strict single-path subset emitted for one rendered SVM Entity."""

    matches = [
        element
        for element in root.iter()
        if _local_name(element.tag) == "g" and element.attrib.get("data-svm-entity") == shape_id
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise SVGGeometryObservationError("Rendered SVG Entity selector is ambiguous")
    entity = matches[0]
    children = list(entity)
    if len(children) != 1:
        raise SVGGeometryObservationError("Rendered SVG Entity observation requires one geometry")
    child = children[0]
    if _local_name(child.tag) == "g":
        if set(child.attrib) != {"transform"}:
            raise SVGGeometryObservationError("Rendered SVG geometry transform fields are invalid")
        geometry = list(child)
        if len(geometry) != 1:
            raise SVGGeometryObservationError(
                "Rendered SVG Entity observation requires one polygonal path"
            )
        path = geometry[0]
        matrix = _matrix(child.attrib["transform"])
    else:
        path = child
        matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    if _local_name(path.tag) != "path" or set(path.attrib) != {"d"}:
        raise SVGGeometryObservationError(
            "Rendered SVG Entity observation requires one polygonal path"
        )
    render_stacks = [
        element
        for element in root
        if _local_name(element.tag) == "g"
        and element.attrib.get("data-svm-role") == "render-stack"
        and entity in list(element)
    ]
    if len(render_stacks) != 1:
        raise SVGGeometryObservationError("Rendered SVG Entity must belong to one render stack")
    render_stack = render_stacks[0]
    allowed_stack_fields = {"data-svm-role", "transform"}
    if not set(render_stack.attrib).issubset(allowed_stack_fields):
        raise SVGGeometryObservationError("Rendered SVG render-stack fields are invalid")
    camera = (
        _matrix(render_stack.attrib["transform"])
        if "transform" in render_stack.attrib
        else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    )
    matrix = _compose_matrix(camera, matrix)
    points, topology = _polygon_vertices(path.attrib["d"])
    points = [
        [
            _round(matrix[0] * x + matrix[2] * y + matrix[4]),
            _round(matrix[1] * x + matrix[3] * y + matrix[5]),
        ]
        for x, y in points
    ]
    if _has_rotational_symmetry(points):
        raise SVGGeometryObservationError(
            "UNSUPPORTED_FOR_ASYMMETRIC_SVG_PRODUCER: polygon has rotational symmetry"
        )
    fill = entity.attrib.get("fill")
    if not isinstance(fill, str) or re.fullmatch(r"#[0-9A-F]{6}", fill) is None:
        raise SVGGeometryObservationError("Rendered SVG polygon fill must be six-digit hex")
    view_box = root.attrib.get("viewBox")
    if view_box is None:
        raise SVGGeometryObservationError("SVG geometry observation requires a positive viewBox")
    canvas_values = _view_box(view_box)
    if canvas_values[0] != 0 or canvas_values[1] != 0:
        raise SVGGeometryObservationError("SVG observation viewBox origin must be zero")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "canvas": [_round(canvas_values[2]), _round(canvas_values[3])],
        "points": points,
        "topology": topology,
        "bounds": [_round(min(xs)), _round(min(ys)), _round(max(xs)), _round(max(ys))],
        "fill": fill,
    }


def _matrix(value: str) -> tuple[float, float, float, float, float, float]:
    match = re.fullmatch(r"matrix\(([^()]*)\)", value)
    if match is None:
        raise SVGGeometryObservationError("Rendered SVG geometry requires one matrix transform")
    parts = match.group(1).replace(",", " ").split()
    if len(parts) != 6:
        raise SVGGeometryObservationError("Rendered SVG matrix must contain six numbers")
    try:
        matrix = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise SVGGeometryObservationError("Rendered SVG matrix must be numeric") from exc
    if not all(math.isfinite(item) for item in matrix):
        raise SVGGeometryObservationError("Rendered SVG matrix must be finite")
    return (matrix[0], matrix[1], matrix[2], matrix[3], matrix[4], matrix[5])


def _compose_matrix(
    outer: tuple[float, float, float, float, float, float],
    inner: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a, b, c, d, e, f = outer
    g, h, i, j, k, offset_y = inner
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * offset_y + e,
        b * k + d * offset_y + f,
    )


def _polygon_vertices(path_data: str) -> tuple[list[list[float]], list[str]]:
    tokens = _TOKEN.findall(path_data)
    if "".join(tokens) != re.sub(r"[\s,]+", "", path_data):
        unsupported = sorted(set(_COMMAND.findall(path_data)) - set("MmLlHhVvZz"))
        detail = f" {unsupported}" if unsupported else ""
        raise SVGGeometryObservationError(f"Unsupported polygonal path syntax{detail}")
    index = 0
    command: str | None = None
    current = (0.0, 0.0)
    start: tuple[float, float] | None = None
    points: list[list[float]] = []
    topology: list[str] = []
    closed = False

    def number() -> float:
        nonlocal index
        if index >= len(tokens) or _COMMAND.fullmatch(tokens[index]):
            raise SVGGeometryObservationError("Polygonal path command is missing a coordinate")
        value = float(tokens[index])
        index += 1
        if not math.isfinite(value):
            raise SVGGeometryObservationError("Polygonal path coordinates must be finite")
        return value

    while index < len(tokens):
        if _COMMAND.fullmatch(tokens[index]):
            command = tokens[index]
            index += 1
        if command is None or closed:
            raise SVGGeometryObservationError("Polygonal path must contain one closed subpath")
        upper = command.upper()
        relative = command.islower()
        if upper == "Z":
            if start is None:
                raise SVGGeometryObservationError("Polygonal path closes before it starts")
            closed = True
            topology.append("Z")
            command = None
            continue
        if upper == "M" and points:
            raise SVGGeometryObservationError("Polygonal path must contain exactly one moveto")
        if upper in {"M", "L"}:
            x, y = number(), number()
            if relative:
                x, y = current[0] + x, current[1] + y
        elif upper == "H":
            x = number()
            if relative:
                x += current[0]
            y = current[1]
        elif upper == "V":
            y = number()
            if relative:
                y += current[1]
            x = current[0]
        else:
            raise SVGGeometryObservationError(f"Unsupported path command {command!r}")
        point = [_round(x), _round(y)]
        if points and point == points[-1]:
            raise SVGGeometryObservationError("Polygonal path has consecutive duplicate vertices")
        if upper != "M" and point == points[0]:
            raise SVGGeometryObservationError("Use Z instead of a duplicate closing vertex")
        points.append(point)
        topology.append(upper)
        current = (x, y)
        if upper == "M":
            start = current
            command = "l" if relative else "L"
    if not closed or topology[0] != "M" or topology[-1] != "Z":
        raise SVGGeometryObservationError("Polygonal path must be closed with Z")
    if len(points) < 3 or len({tuple(point) for point in points}) < 3:
        raise SVGGeometryObservationError(
            "Polygonal path requires at least three distinct vertices"
        )
    area2 = sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    )
    scale = max(max(abs(value) for point in points for value in point), 1.0)
    if abs(area2) <= 1e-12 * scale * scale:
        raise SVGGeometryObservationError("Polygonal path area must be non-zero")
    return points, topology


def _has_rotational_symmetry(points: list[list[float]]) -> bool:
    count = len(points)
    center = (
        sum(point[0] for point in points) / count,
        sum(point[1] for point in points) / count,
    )
    centered = [(point[0] - center[0], point[1] - center[1]) for point in points]
    energy = sum(x * x + y * y for x, y in centered)
    if energy <= 0:
        return True
    for shift in range(1, count):
        dot = sum(
            centered[i][0] * centered[(i + shift) % count][0]
            + centered[i][1] * centered[(i + shift) % count][1]
            for i in range(count)
        )
        cross = sum(
            centered[i][0] * centered[(i + shift) % count][1]
            - centered[i][1] * centered[(i + shift) % count][0]
            for i in range(count)
        )
        magnitude = math.hypot(dot, cross)
        if magnitude == 0:
            continue
        cosine, sine = dot / magnitude, cross / magnitude
        residual = math.sqrt(
            sum(
                (cosine * centered[i][0] - sine * centered[i][1] - centered[(i + shift) % count][0])
                ** 2
                + (
                    sine * centered[i][0]
                    + cosine * centered[i][1]
                    - centered[(i + shift) % count][1]
                )
                ** 2
                for i in range(count)
            )
            / energy
        )
        if residual <= _SYMMETRY_RESIDUAL_LIMIT:
            return True
    return False


def _frame(
    geometry: dict[str, Any], source_artifact_id: str, shape_id: str, tick: int
) -> dict[str, Any]:
    identity = {
        "source_svg_artifact_id": source_artifact_id,
        "shape_id": shape_id,
        "policy_identity": POLICY_IDENTITY,
    }
    return {
        "tick": tick,
        "primitives": [
            {
                "observation_id": "observation:svg:"
                + hashlib.sha256(canonical_bytes(identity)).hexdigest(),
                "primitive_type": PRIMITIVE_TYPE,
                "bounds": geometry["bounds"],
                "fill": geometry["fill"],
                "geometry": {
                    "type": "ordered-landmarks",
                    "points": geometry["points"],
                    "rotation_symmetry": "none",
                },
            }
        ],
    }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _view_box(value: str) -> list[float]:
    parts = value.replace(",", " ").split()
    if len(parts) != 4:
        raise SVGGeometryObservationError("SVG viewBox must contain four unitless numbers")
    try:
        result = [float(part) for part in parts]
    except ValueError as exc:
        raise SVGGeometryObservationError("SVG viewBox must contain unitless numbers") from exc
    if not all(math.isfinite(item) for item in result) or result[2] <= 0 or result[3] <= 0:
        raise SVGGeometryObservationError("SVG viewBox must be finite and positive")
    return result


def _round(value: float) -> float:
    result = float(format(value, ".12g"))
    return 0.0 if result == 0 else result
