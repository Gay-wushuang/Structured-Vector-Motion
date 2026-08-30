from __future__ import annotations

import hashlib
from typing import Any

from .evaluator import canonical_bytes

STRUCTURAL_RELATIONS_IDENTITY = "svm-structural-relations@0.1"
MAX_PROMOTED_COMPONENTS_FOR_RELATIONS = 512


def structural_relation_id(content: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_bytes({"identity": STRUCTURAL_RELATIONS_IDENTITY, **content})
    ).hexdigest()[:16]
    return f"relation:{content['type']}:{digest}"


def provenance_bounds(provenance: dict[str, Any]) -> tuple[int, int, int, int] | None:
    bounds = provenance.get("bounds")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or any(not isinstance(value, int) or isinstance(value, bool) for value in bounds)
        or not (0 <= bounds[0] < bounds[2])
        or not (0 <= bounds[1] < bounds[3])
    ):
        return None
    return bounds[0], bounds[1], bounds[2], bounds[3]


def strictly_bounds_contains(
    outer: tuple[int, int, int, int] | None,
    inner: tuple[int, int, int, int] | None,
) -> bool:
    return (
        outer is not None
        and inner is not None
        and outer != inner
        and outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )
