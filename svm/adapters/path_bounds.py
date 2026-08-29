from __future__ import annotations

import math

from svgpathtools import parse_path  # pyright: ignore[reportMissingImports]


class PathBoundsError(ValueError):
    pass


def canonical_path_bounds(path_data: str) -> tuple[float, float, float, float]:
    """Return the exact axis-aligned bounds of the geometry encoded by path_data."""

    if not isinstance(path_data, str) or not path_data.strip():
        raise PathBoundsError("Path data must be a non-empty string")
    try:
        min_x, max_x, min_y, max_y = parse_path(path_data).bbox()
    except (AttributeError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise PathBoundsError(f"Cannot compute canonical path bounds: {exc}") from exc
    bounds = tuple(float(value) for value in (min_x, min_y, max_x, max_y))
    if not all(math.isfinite(value) for value in bounds):
        raise PathBoundsError("Canonical path bounds must be finite")
    canonical = [float(format(value, ".12g")) for value in bounds]
    return (
        0.0 if canonical[0] == 0 else canonical[0],
        0.0 if canonical[1] == 0 else canonical[1],
        0.0 if canonical[2] == 0 else canonical[2],
        0.0 if canonical[3] == 0 else canonical[3],
    )
