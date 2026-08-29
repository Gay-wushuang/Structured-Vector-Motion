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


class BitmapTracer(Protocol):
    engine_name: str
    engine_version: str

    def trace(self, content: bytes, options: TraceOptions) -> TracedPath: ...


class PotracerEngine:
    engine_name = "bitmap-trace/potracer"

    @property
    def engine_version(self) -> str:
        return (
            f"{importlib.metadata.version('potracer')}"
            f"+pillow@{importlib.metadata.version('Pillow')}"
            "+svm-bitmap-preprocess@0.1"
        )

    def trace(self, content: bytes, options: TraceOptions) -> TracedPath:
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
        commands: list[str] = []
        points: list[tuple[float, float]] = []
        curve_count = 0
        for curve in curves:
            curve_count += 1
            start = _point(curve.start_point)
            points.append(start)
            commands.append(f"M {_number(start[0])} {_number(start[1])}")
            for segment in curve.segments:
                end = _point(segment.end_point)
                if segment.is_corner:
                    corner = _point(segment.c)
                    points.extend((corner, end))
                    commands.append(
                        f"L {_number(corner[0])} {_number(corner[1])} "
                        f"L {_number(end[0])} {_number(end[1])}"
                    )
                else:
                    control_1 = _point(segment.c1)
                    control_2 = _point(segment.c2)
                    points.extend((control_1, control_2, end))
                    commands.append(
                        f"C {_number(control_1[0])} {_number(control_1[1])} "
                        f"{_number(control_2[0])} {_number(control_2[1])} "
                        f"{_number(end[0])} {_number(end[1])}"
                    )
            commands.append("Z")
        if not points:
            raise BitmapTraceError("Bitmap trace produced no closed paths")
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return TracedPath(" ".join(commands), (min(xs), min(ys), max(xs), max(ys)), curve_count)


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
        namespace = self._namespace(request, artifact, options)
        entity_id = f"entity:trace-{namespace}"
        path_id = f"op:trace-{namespace}-path"
        planar_id = f"op:trace-{namespace}-planar"
        change = AppendSceneFragmentChange(
            entities=({"id": entity_id, "name": f"Bitmap trace {namespace}"},),
            operations=(
                {
                    "id": path_id,
                    "type": "CreatePath",
                    "inputs": {},
                    "parameters": {"d": traced.d, "bounds": list(traced.bounds)},
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
            ),
            output_bindings=(
                {"entity": entity_id, "property": "geometry", "slot": f"{planar_id}.geometry"},
            ),
            render_entries=(entity_id,),
            styles=(
                {
                    "entity": entity_id,
                    "fill": "#000000",
                    "stroke": "none",
                    "stroke_width": 1.0,
                    "opacity": 1.0,
                },
            ),
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
            report=EvaluationReport(metrics={"traced_paths": float(traced.curve_count)}),
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

    @staticmethod
    def _namespace(
        request: AdapterRequest, artifact: ArtifactSnapshot, options: TraceOptions
    ) -> str:
        requested = request.options.get("namespace")
        if requested is not None:
            if not isinstance(requested, str) or not requested.replace("-", "").isalnum():
                raise BitmapTraceError("Trace namespace must contain letters, digits, or hyphens")
            base = requested
        else:
            digest = hashlib.sha256(
                artifact.content_hash.encode() + canonical_bytes(options.provenance())
            ).hexdigest()
            base = digest[:12]
        entity_ids = {entity["id"] for entity in request.document["entities"]}
        operation_ids = {
            operation["id"] for operation in request.document["construction"]["operations"]
        }

        def collides(namespace: str) -> bool:
            return (
                f"entity:trace-{namespace}" in entity_ids
                or f"op:trace-{namespace}-path" in operation_ids
                or f"op:trace-{namespace}-planar" in operation_ids
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
