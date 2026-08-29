from __future__ import annotations

import importlib.metadata
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from shapely import (
    difference,
    geos_version_string,
    intersection,
    symmetric_difference,
    union,
)
from shapely.errors import ShapelyError
from shapely.geometry import MultiLineString, MultiPolygon, Polygon, box
from shapely.ops import polygonize, unary_union
from svgpathtools import (  # pyright: ignore[reportMissingImports]
    CubicBezier,
    Line,
    QuadraticBezier,
    parse_path,
)

from .geometry import GeometryBackendError
from .polygon_set import PolygonRings, canonicalize_polygon_set

_PATH_COMMAND = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]")
_MAX_SUBDIVISION_DEPTH = 32


class ShapelyGeometryBackend:
    """Shapely/GEOS implementation of the SVM planar geometry capability."""

    @property
    def identity(self) -> str:
        return (
            f"geometry/shapely@{importlib.metadata.version('shapely')}+geos@{geos_version_string}"
        )

    def boolean(
        self,
        operator: str,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
    ) -> dict[str, Any]:
        functions = {
            "union": union,
            "intersection": intersection,
            "difference": difference,
            "xor": symmetric_difference,
        }
        try:
            function = functions[operator]
        except KeyError as exc:
            raise GeometryBackendError(f"Unsupported boolean operator {operator!r}") from exc
        try:
            left_geometry = _to_shapely(left)
            right_geometry = _to_shapely(right)
            result = function(left_geometry, right_geometry)
            if result.is_empty:
                raise GeometryBackendError("Boolean operation produced empty geometry")
            if not result.is_valid:
                raise GeometryBackendError("Boolean operation produced invalid geometry")
            return _from_shapely(result)
        except GeometryBackendError:
            raise
        except ShapelyError as exc:
            raise GeometryBackendError(f"Shapely/GEOS boolean operation failed: {exc}") from exc

    def path_to_polygon(
        self,
        path: Mapping[str, Any],
        tolerance: float,
        fill_rule: str,
    ) -> dict[str, Any]:
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise GeometryBackendError("PathToPolygon tolerance must be finite and positive")
        if fill_rule not in {"nonzero", "evenodd"}:
            raise GeometryBackendError("PathToPolygon fill_rule must be nonzero or evenodd")
        if path.get("kind") != "path_data":
            raise GeometryBackendError("PathToPolygon requires path_data geometry")
        path_data = path.get("d")
        if not isinstance(path_data, str) or not path_data.strip():
            raise GeometryBackendError("PathToPolygon requires non-empty path data")
        _validate_explicit_closure(path_data)
        try:
            parsed = parse_path(path_data)
            subpaths = parsed.continuous_subpaths()
            rings = [_flatten_subpath(subpath, tolerance) for subpath in subpaths]
            if not rings:
                raise GeometryBackendError("PathToPolygon requires at least one subpath")
            segments = [
                (left, right)
                for ring in rings
                for left, right in zip(ring[:-1], ring[1:], strict=True)
                if left != right
            ]
            linework = unary_union(MultiLineString(segments))
            faces = tuple(polygonize(linework))
            selected = [
                face
                for face in faces
                if _inside_face(face.representative_point().coords[0], rings, fill_rule)
            ]
            if not selected:
                raise GeometryBackendError("PathToPolygon produced empty planar geometry")
            result = unary_union(selected)
            if result.is_empty:
                raise GeometryBackendError("PathToPolygon produced empty planar geometry")
            if not result.is_valid:
                raise GeometryBackendError("PathToPolygon produced invalid planar geometry")
            return _from_shapely(result)
        except GeometryBackendError:
            raise
        except (ShapelyError, TypeError, ValueError, IndexError) as exc:
            raise GeometryBackendError(f"PathToPolygon evaluation failed: {exc}") from exc


def _to_shapely(geometry: Mapping[str, Any]) -> Polygon | MultiPolygon:
    kind = geometry.get("kind")
    if kind == "rectangle":
        x = float(geometry["x"])
        y = float(geometry["y"])
        return box(x, y, x + float(geometry["width"]), y + float(geometry["height"]))
    if kind == "polygon_set":
        polygons = []
        for item in geometry["polygons"]:
            polygons.append(Polygon(item["exterior"], item["holes"]))
        return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    raise GeometryBackendError(f"Shapely geometry backend does not support input kind {kind!r}")


def _from_shapely(geometry: Any) -> dict[str, Any]:
    if isinstance(geometry, Polygon):
        polygons = (geometry,)
    elif isinstance(geometry, MultiPolygon):
        polygons = tuple(geometry.geoms)
    else:
        raise GeometryBackendError(
            f"Boolean result type {geometry.geom_type!r} is not a filled area"
        )
    polygon_rings: list[PolygonRings] = [
        {
            "exterior": _coordinates(polygon.exterior.coords),
            "holes": [_coordinates(ring.coords) for ring in polygon.interiors],
        }
        for polygon in polygons
    ]
    return canonicalize_polygon_set(polygon_rings)


def _coordinates(values: Any) -> list[list[float]]:
    return [[float(value[0]), float(value[1])] for value in values]


def _validate_explicit_closure(path_data: str) -> None:
    commands = _PATH_COMMAND.findall(path_data)
    if not commands or commands[0].lower() != "m":
        raise GeometryBackendError("PathToPolygon path must start with moveto")
    if any(command.lower() == "a" for command in commands):
        raise GeometryBackendError("PathToPolygon does not support elliptical arcs")
    starts = [index for index, command in enumerate(commands) if command.lower() == "m"]
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(commands)
        subpath_commands = commands[start:end]
        if subpath_commands[-1].lower() != "z":
            raise GeometryBackendError("PathToPolygon requires every subpath to close with Z")
        if any(command.lower() == "z" for command in subpath_commands[:-1]):
            raise GeometryBackendError("PathToPolygon requires moveto after closepath")


def _flatten_subpath(subpath: Any, tolerance: float) -> list[tuple[float, float]]:
    if len(subpath) == 0 or not subpath.isclosed():
        raise GeometryBackendError("PathToPolygon requires every subpath to be closed")
    points = [_complex_point(subpath[0].start)]
    for segment in subpath:
        if isinstance(segment, Line):
            points.append(_complex_point(segment.end))
        elif isinstance(segment, QuadraticBezier):
            points.extend(
                _flatten_quadratic(
                    segment.start,
                    segment.control,
                    segment.end,
                    tolerance,
                    0,
                )
            )
        elif isinstance(segment, CubicBezier):
            points.extend(
                _flatten_cubic(
                    segment.start,
                    segment.control1,
                    segment.control2,
                    segment.end,
                    tolerance,
                    0,
                )
            )
        else:
            raise GeometryBackendError(
                f"PathToPolygon does not support segment type {type(segment).__name__}"
            )
    cleaned: list[tuple[float, float]] = []
    for point in points:
        if not cleaned or cleaned[-1] != point:
            cleaned.append(point)
    if cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])
    distinct = tuple(dict.fromkeys(cleaned[:-1]))
    if len(distinct) < 3 or not _has_non_collinear_triple(distinct):
        raise GeometryBackendError("PathToPolygon subpath is degenerate")
    return cleaned


def _flatten_quadratic(
    start: complex,
    control: complex,
    end: complex,
    tolerance: float,
    depth: int,
) -> list[tuple[float, float]]:
    if _distance_to_chord(control, start, end) <= tolerance:
        return [_complex_point(end)]
    if depth >= _MAX_SUBDIVISION_DEPTH:
        raise GeometryBackendError("PathToPolygon exceeded subdivision depth 32")
    start_control = (start + control) / 2
    control_end = (control + end) / 2
    middle = (start_control + control_end) / 2
    return _flatten_quadratic(start, start_control, middle, tolerance, depth + 1) + (
        _flatten_quadratic(middle, control_end, end, tolerance, depth + 1)
    )


def _flatten_cubic(
    start: complex,
    control1: complex,
    control2: complex,
    end: complex,
    tolerance: float,
    depth: int,
) -> list[tuple[float, float]]:
    if (
        max(
            _distance_to_chord(control1, start, end),
            _distance_to_chord(control2, start, end),
        )
        <= tolerance
    ):
        return [_complex_point(end)]
    if depth >= _MAX_SUBDIVISION_DEPTH:
        raise GeometryBackendError("PathToPolygon exceeded subdivision depth 32")
    first = (start + control1) / 2
    middle_controls = (control1 + control2) / 2
    last = (control2 + end) / 2
    left_control2 = (first + middle_controls) / 2
    right_control1 = (middle_controls + last) / 2
    middle = (left_control2 + right_control1) / 2
    return _flatten_cubic(
        start, first, left_control2, middle, tolerance, depth + 1
    ) + _flatten_cubic(middle, right_control1, last, end, tolerance, depth + 1)


def _distance_to_chord(point: complex, start: complex, end: complex) -> float:
    chord = end - start
    if abs(chord) == 0:
        return abs(point - start)
    return abs(chord.real * (point - start).imag - chord.imag * (point - start).real) / abs(chord)


def _complex_point(value: complex) -> tuple[float, float]:
    x = float(value.real)
    y = float(value.imag)
    if not math.isfinite(x) or not math.isfinite(y):
        raise GeometryBackendError("PathToPolygon coordinates must be finite")
    return (0.0 if x == 0 else x, 0.0 if y == 0 else y)


def _has_non_collinear_triple(points: Sequence[tuple[float, float]]) -> bool:
    first = points[0]
    second = next((point for point in points[1:] if point != first), None)
    if second is None:
        return False
    return any(
        (second[0] - first[0]) * (point[1] - first[1])
        - (second[1] - first[1]) * (point[0] - first[0])
        != 0
        for point in points[1:]
    )


def _inside_face(
    point: Sequence[float],
    rings: Sequence[Sequence[tuple[float, float]]],
    fill_rule: str,
) -> bool:
    x = float(point[0])
    y = float(point[1])
    winding = 0
    crossings = 0
    for ring in rings:
        for start, end in zip(ring[:-1], ring[1:], strict=True):
            if (start[1] <= y < end[1]) or (end[1] <= y < start[1]):
                intersection_x = start[0] + (y - start[1]) * (end[0] - start[0]) / (
                    end[1] - start[1]
                )
                if intersection_x > x:
                    crossings += 1
            cross = (end[0] - start[0]) * (y - start[1]) - (x - start[0]) * (end[1] - start[1])
            if start[1] <= y < end[1] and cross > 0:
                winding += 1
            elif end[1] <= y < start[1] and cross < 0:
                winding -= 1
    return winding != 0 if fill_rule == "nonzero" else crossings % 2 == 1
