from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any, TypedDict

from .geometry import GeometryBackendError

Point = tuple[float, float]


class PolygonRings(TypedDict):
    exterior: Sequence[Sequence[float]]
    holes: Sequence[Sequence[Sequence[float]]]


def canonicalize_polygon_set(
    polygons: Iterable[PolygonRings],
) -> dict[str, Any]:
    canonical_polygons: list[dict[str, Any]] = []
    for polygon in polygons:
        exterior = _canonical_ring(polygon["exterior"], clockwise=True)
        holes = sorted(
            (_canonical_ring(ring, clockwise=False) for ring in polygon.get("holes", ())),
            key=_ring_key,
        )
        canonical_polygons.append({"exterior": exterior, "holes": holes})
    if not canonical_polygons:
        raise GeometryBackendError("Polygon set must not be empty")
    canonical_polygons.sort(
        key=lambda polygon: (
            _ring_key(polygon["exterior"]),
            tuple(_ring_key(ring) for ring in polygon["holes"]),
        )
    )
    points = [
        point
        for polygon in canonical_polygons
        for ring in (polygon["exterior"], *polygon["holes"])
        for point in ring[:-1]
    ]
    return {
        "kind": "polygon_set",
        "polygons": canonical_polygons,
        "bounds": [
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        ],
    }


def _canonical_ring(values: Sequence[Sequence[float]], *, clockwise: bool) -> list[list[float]]:
    points = [_point(value) for value in values]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    points = _remove_consecutive_duplicates(points)
    points = _remove_collinear(points)
    if len(points) < 3:
        raise GeometryBackendError("Polygon ring must contain at least three vertices")
    area = _signed_area(points)
    if area == 0:
        raise GeometryBackendError("Polygon ring must have non-zero area")
    if (clockwise and area > 0) or (not clockwise and area < 0):
        points.reverse()
    rotations = [points[index:] + points[:index] for index in range(len(points))]
    points = min(rotations, key=lambda ring: tuple(ring))
    return [[x, y] for x, y in (*points, points[0])]


def _point(value: Sequence[float]) -> Point:
    if len(value) < 2:
        raise GeometryBackendError("Polygon coordinate requires x and y")
    x = float(value[0])
    y = float(value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise GeometryBackendError("Polygon coordinates must be finite")
    return (0.0 if x == 0 else x, 0.0 if y == 0 else y)


def _remove_consecutive_duplicates(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or result[-1] != point:
            result.append(point)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result


def _remove_collinear(points: list[Point]) -> list[Point]:
    result = list(points)
    changed = True
    while changed and len(result) >= 3:
        changed = False
        kept: list[Point] = []
        for index, point in enumerate(result):
            previous = result[index - 1]
            following = result[(index + 1) % len(result)]
            cross = (point[0] - previous[0]) * (following[1] - point[1]) - (
                point[1] - previous[1]
            ) * (following[0] - point[0])
            if cross == 0:
                changed = True
            else:
                kept.append(point)
        result = kept
    return result


def _signed_area(points: Sequence[Point]) -> float:
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(points, (*points[1:], points[0]), strict=True)
    )


def _ring_key(ring: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    return tuple((float(point[0]), float(point[1])) for point in ring)
