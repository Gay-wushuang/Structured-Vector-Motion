from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class GeometryBackendError(ValueError):
    pass


class GeometryBackend(Protocol):
    """Capability interface for deterministic planar geometry operations."""

    @property
    def identity(self) -> str: ...

    def boolean(
        self,
        operator: str,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def path_to_polygon(
        self,
        path: Mapping[str, Any],
        tolerance: float,
        fill_rule: str,
    ) -> dict[str, Any]: ...
