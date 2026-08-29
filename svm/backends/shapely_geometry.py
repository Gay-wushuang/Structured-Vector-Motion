from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable, Mapping
from typing import Any

from shapely import difference, intersection, normalize, symmetric_difference, union
from shapely.geometry import MultiPolygon, Polygon, box

from .geometry import GeometryBackendError


class ShapelyGeometryBackend:
    """Shapely/GEOS implementation of the SVM planar geometry capability."""

    @property
    def identity(self) -> str:
        return f"shapely:{importlib.metadata.version('shapely')}"

    def boolean(
        self,
        operator: str,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
    ) -> dict[str, Any]:
        left_geometry = _to_shapely(left)
        right_geometry = _to_shapely(right)
        functions = {
            "union": union,
            "intersection": intersection,
            "difference": difference,
            "xor": symmetric_difference,
        }
        try:
            result = functions[operator](left_geometry, right_geometry)
        except KeyError as exc:
            raise GeometryBackendError(f"Unsupported boolean operator {operator!r}") from exc
        if result.is_empty:
            raise GeometryBackendError("Boolean operation produced empty geometry")
        if not result.is_valid:
            raise GeometryBackendError("Boolean operation produced invalid geometry")
        return _from_shapely(normalize(result))


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


def _coordinates(values: Iterable[tuple[float, ...]]) -> list[list[float]]:
    return [[float(value[0]), float(value[1])] for value in values]


def _from_shapely(geometry: Any) -> dict[str, Any]:
    if isinstance(geometry, Polygon):
        polygons = (geometry,)
    elif isinstance(geometry, MultiPolygon):
        polygons = tuple(geometry.geoms)
    else:
        raise GeometryBackendError(
            f"Boolean result type {geometry.geom_type!r} is not a filled area"
        )
    bounds = [float(value) for value in geometry.bounds]
    return {
        "kind": "polygon_set",
        "polygons": [
            {
                "exterior": _coordinates(polygon.exterior.coords),
                "holes": [_coordinates(ring.coords) for ring in polygon.interiors],
            }
            for polygon in polygons
        ],
        "bounds": bounds,
    }
