from __future__ import annotations

import hashlib
import importlib.metadata
import io
import math
from dataclasses import dataclass
from typing import Any, Protocol

from ..artifacts import ArtifactKind, ArtifactResolver, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, EvaluationReport, GeneratorProvenance, Proposal
from ..revisions import AppendSceneFragmentChange, Transaction
from .path_bounds import PathBoundsError, canonical_path_bounds

BITMAP_MEDIA_TYPES = {"image/png"}
_TURN_POLICIES = {
    "black": 0,
    "white": 1,
    "left": 2,
    "right": 3,
    "minority": 4,
    "majority": 5,
}


class BitmapTraceError(ValueError):
    pass


@dataclass(frozen=True)
class TraceOptions:
    threshold: int = 128
    invert: bool = False
    turd_size: int = 2
    turn_policy: str = "minority"
    alpha_max: float = 1.0
    optimize_curve: bool = True
    optimization_tolerance: float = 0.2
    path_tolerance: float = 0.25
    fill_rule: str = "nonzero"

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> TraceOptions:
        allowed = set(cls.__dataclass_fields__) | {"namespace"}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise BitmapTraceError(f"Unknown bitmap trace option(s): {', '.join(unknown)}")
        options = cls(**{key: value for key, value in values.items() if key != "namespace"})
        if type(options.threshold) is not int or not 0 <= options.threshold <= 255:
            raise BitmapTraceError("threshold must be an integer between 0 and 255")
        if type(options.invert) is not bool:
            raise BitmapTraceError("invert must be a boolean")
        if type(options.turd_size) is not int or options.turd_size < 0:
            raise BitmapTraceError("turd_size must be a non-negative integer")
        if options.turn_policy not in _TURN_POLICIES:
            raise BitmapTraceError(
                "turn_policy must be black, white, left, right, minority, or majority"
            )
        for name in ("alpha_max", "optimization_tolerance", "path_tolerance"):
            value = getattr(options, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or value <= 0
            ):
                raise BitmapTraceError(f"{name} must be a finite positive number")
        if type(options.optimize_curve) is not bool:
            raise BitmapTraceError("optimize_curve must be a boolean")
        if options.fill_rule not in {"nonzero", "evenodd"}:
            raise BitmapTraceError("fill_rule must be nonzero or evenodd")
        return options

    def provenance(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class TracedPath:
    d: str
    bounds: tuple[float, float, float, float]
    curve_count: int


@dataclass(frozen=True)
class TraceResult:
    paths: tuple[TracedPath, ...]

    @property
    def curve_count(self) -> int:
        return sum(path.curve_count for path in self.paths)


class BitmapTracer(Protocol):
    engine_name: str
    engine_version: str

    def trace(self, content: bytes, options: TraceOptions) -> TraceResult | TracedPath: ...


class PotracerEngine:
    engine_name = "bitmap-trace/potracer"

    @property
    def engine_version(self) -> str:
        return (
            f"{importlib.metadata.version('potracer')}"
            f"+pillow@{importlib.metadata.version('Pillow')}"
            "+svm-bitmap-preprocess@0.1"
            f"+svgpathtools@{importlib.metadata.version('svgpathtools')}"
            "+svm-path-bounds@0.1"
        )

    def trace(self, content: bytes, options: TraceOptions) -> TraceResult:
        try:
            import potrace  # pyright: ignore[reportMissingImports]
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise BitmapTraceError(
                "Bitmap tracing requires the 'trace' optional dependency"
            ) from exc
        try:
            with Image.open(io.BytesIO(content)) as source:
                if source.format != "PNG":
                    raise BitmapTraceError("Bitmap Artifact bytes must be PNG format")
                if (
                    source.width <= 0
                    or source.height <= 0
                    or source.width * source.height > 16_000_000
                ):
                    raise BitmapTraceError("Bitmap exceeds the 16 megapixel trace limit")
                if "A" in source.getbands() or "transparency" in source.info:
                    raise BitmapTraceError("PNG alpha/transparency is not supported in v0.1")
                source.load()
                grayscale = source.convert("L")
                if options.invert:
                    grayscale = ImageOps.invert(grayscale)
                bitmap = potrace.Bitmap(grayscale, blacklevel=options.threshold / 255.0)
        except BitmapTraceError:
            raise
        except Exception as exc:
            raise BitmapTraceError(f"Invalid PNG bitmap: {exc}") from exc
        curves = bitmap.trace(
            turdsize=options.turd_size,
            turnpolicy=_TURN_POLICIES[options.turn_policy],
            alphamax=options.alpha_max,
            opticurve=options.optimize_curve,
            opttolerance=options.optimization_tolerance,
        )
        traced_curves: list[tuple[str, tuple[tuple[float, float], ...]]] = []
        for curve in curves:
            commands: list[str] = []
            start = _point(curve.start_point)
            commands.append(f"M {_number(start[0])} {_number(start[1])}")
            for segment in curve.segments:
                end = _point(segment.end_point)
                if segment.is_corner:
                    corner = _point(segment.c)
                    commands.append(
                        f"L {_number(corner[0])} {_number(corner[1])} "
                        f"L {_number(end[0])} {_number(end[1])}"
                    )
                else:
                    control_1 = _point(segment.c1)
                    control_2 = _point(segment.c2)
                    commands.append(
                        f"C {_number(control_1[0])} {_number(control_1[1])} "
                        f"{_number(control_2[0])} {_number(control_2[1])} "
                        f"{_number(end[0])} {_number(end[1])}"
                    )
            commands.append("Z")
            traced_curves.append(
                (
                    " ".join(commands),
                    tuple(_point(point) for point in curve.decomposition_points),
                )
            )
        if not traced_curves:
            raise BitmapTraceError("Bitmap trace produced no closed paths")
        paths: list[TracedPath] = []
        for group in _component_groups(traced_curves):
            path_data = " ".join(traced_curves[index][0] for index in group)
            try:
                bounds = canonical_path_bounds(path_data)
            except PathBoundsError as exc:
                raise BitmapTraceError(str(exc)) from exc
            paths.append(TracedPath(path_data, bounds, len(group)))
        paths.sort(
            key=lambda path: (path.bounds[1], path.bounds[0], path.bounds[3], path.bounds[2])
        )
        return TraceResult(tuple(paths))


class BitmapTraceAdapter:
    adapter_id = "adapter:bitmap-trace"
    adapter_version = "0.1"

    def __init__(self, tracer: BitmapTracer | None = None) -> None:
        self.tracer = tracer or PotracerEngine()

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        artifact = self._select_artifact(
            artifacts.resolve_as(
                request.artifact_ids,
                kind=ArtifactKind.REFERENCE,
                media_types=frozenset(BITMAP_MEDIA_TYPES),
            )
        )
        options = TraceOptions.from_mapping(request.options)
        traced = self.tracer.trace(artifact.content, options)
        if isinstance(traced, TracedPath):
            traced = TraceResult((traced,))
        namespace = self._namespace(request, artifact, options)
        entities: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []
        bindings: list[dict[str, Any]] = []
        render_entries: list[str] = []
        styles: list[dict[str, Any]] = []
        multiple = len(traced.paths) > 1
        for index, traced_path in enumerate(traced.paths):
            suffix = f"-{index:04d}" if multiple else ""
            entity_id = f"entity:trace-{namespace}{suffix}"
            path_id = f"op:trace-{namespace}{suffix}-path"
            planar_id = f"op:trace-{namespace}{suffix}-planar"
            entities.append(
                {
                    "id": entity_id,
                    "name": (
                        f"Bitmap trace {namespace} component {index + 1}"
                        if multiple
                        else f"Bitmap trace {namespace}"
                    ),
                }
            )
            operations.extend(
                (
                    {
                        "id": path_id,
                        "type": "CreatePath",
                        "inputs": {},
                        "parameters": {
                            "d": traced_path.d,
                            "bounds": list(traced_path.bounds),
                        },
                    },
                    {
                        "id": planar_id,
                        "type": "PathToPolygon",
                        "inputs": {"path": f"{path_id}.geometry"},
                        "parameters": {
                            "tolerance": options.path_tolerance,
                            "fill_rule": options.fill_rule,
                        },
                    },
                )
            )
            bindings.append(
                {"entity": entity_id, "property": "geometry", "slot": f"{planar_id}.geometry"}
            )
            render_entries.append(entity_id)
            styles.append(
                {
                    "entity": entity_id,
                    "fill": "#000000",
                    "stroke": "none",
                    "stroke_width": 1.0,
                    "opacity": 1.0,
                }
            )
        change = AppendSceneFragmentChange(
            entities=tuple(entities),
            operations=tuple(operations),
            output_bindings=tuple(bindings),
            render_entries=tuple(render_entries),
            styles=tuple(styles),
            references=(artifact.document_reference(),),
        )
        return Proposal(
            proposal_id=f"proposal:bitmap-trace:{namespace}",
            base_revision_id=request.base_revision_id,
            generator=GeneratorProvenance(
                adapter_id=self.adapter_id,
                adapter_version=self.adapter_version,
                engine=self.tracer.engine_name,
                engine_version=self.tracer.engine_version,
                parameters={"namespace": namespace, **options.provenance()},
            ),
            transaction=Transaction(
                transaction_id=f"transaction:bitmap-trace:{namespace}",
                changes=(change,),
                message="Trace bitmap into explicit path and planar geometry",
            ),
            report=EvaluationReport(
                metrics={
                    "traced_paths": float(traced.curve_count),
                    "structured_entities": float(len(traced.paths)),
                }
            ),
            required_artifact_ids=(artifact.artifact_id,),
            confidence=1.0,
            notes="Deterministic binary bitmap trace; acceptance remains explicit",
        )

    @staticmethod
    def _select_artifact(artifacts: tuple[ArtifactSnapshot, ...]) -> ArtifactSnapshot:
        if len(artifacts) != 1:
            raise BitmapTraceError("Bitmap Trace requires exactly one Artifact snapshot")
        artifact = artifacts[0]
        if len(artifact.content) > 32 * 1024 * 1024:
            raise BitmapTraceError("Bitmap Artifact exceeds the 32 MiB trace limit")
        return artifact

    def _namespace(
        self, request: AdapterRequest, artifact: ArtifactSnapshot, options: TraceOptions
    ) -> str:
        requested = request.options.get("namespace")
        if requested is not None:
            if not isinstance(requested, str) or not requested.replace("-", "").isalnum():
                raise BitmapTraceError("Trace namespace must contain letters, digits, or hyphens")
            base = requested
        else:
            seed = {
                "artifact_content_hash": artifact.content_hash,
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "engine_name": self.tracer.engine_name,
                "engine_version": self.tracer.engine_version,
                "options": options.provenance(),
            }
            digest = hashlib.sha256(canonical_bytes(seed)).hexdigest()
            base = digest[:12]
        entity_ids = {entity["id"] for entity in request.document["entities"]}
        operation_ids = {
            operation["id"] for operation in request.document["construction"]["operations"]
        }

        def collides(namespace: str) -> bool:
            entity_prefix = f"entity:trace-{namespace}"
            operation_prefix = f"op:trace-{namespace}"
            return any(
                entity_id == entity_prefix or entity_id.startswith(f"{entity_prefix}-")
                for entity_id in entity_ids
            ) or any(
                operation_id.startswith(f"{operation_prefix}-") for operation_id in operation_ids
            )

        candidate = base
        suffix = 2
        while collides(candidate):
            candidate = f"{base}{suffix}"
            suffix += 1
        return candidate


def _point(value: Any) -> tuple[float, float]:
    return _canonical_coordinate(float(value.x)), _canonical_coordinate(float(value.y))


def _canonical_coordinate(value: float) -> float:
    if not math.isfinite(value):
        raise BitmapTraceError("Bitmap trace produced a non-finite coordinate")
    canonical = float(format(value, ".12g"))
    return 0.0 if canonical == 0 else canonical


def _number(value: float) -> str:
    return format(value, ".12g")


def _component_groups(
    curves: list[tuple[str, tuple[tuple[float, float], ...]]],
) -> list[tuple[int, ...]]:
    """Group every top-level contour with its nested hole/island contours."""
    bounds = [_polygon_bounds(curve[1]) for curve in curves]
    parents: list[int | None] = []
    for index, (_, polygon) in enumerate(curves):
        candidates: list[tuple[float, int]] = []
        for candidate, (_, candidate_polygon) in enumerate(curves):
            if candidate == index or not _bounds_contain(bounds[candidate], bounds[index]):
                continue
            if _point_in_polygon(polygon[0], candidate_polygon):
                candidate_bounds = bounds[candidate]
                area = (candidate_bounds[2] - candidate_bounds[0]) * (
                    candidate_bounds[3] - candidate_bounds[1]
                )
                candidates.append((area, candidate))
        parents.append(min(candidates)[1] if candidates else None)

    grouped: dict[int, list[int]] = {}
    for index in range(len(curves)):
        root = index
        while True:
            parent = parents[root]
            if parent is None:
                break
            root = parent
        grouped.setdefault(root, []).append(index)
    return [tuple(indices) for _, indices in sorted(grouped.items())]


def _polygon_bounds(
    polygon: tuple[tuple[float, float], ...],
) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _bounds_contain(
    outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]
) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
        and outer != inner
    )


def _point_in_polygon(point: tuple[float, float], polygon: tuple[tuple[float, float], ...]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside
