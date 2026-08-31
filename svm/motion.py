from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .backends import GeometryBackend
from .evaluator import DocumentError, Evaluator, ImmutableValue, Quality
from .operations import OperationValidationError
from .scene import EvaluatedScene, build_evaluated_scene

MOTION_SEMANTICS_V1_IDENTITY = "svm-motion@0.1"
MOTION_SEMANTICS_IDENTITY = "svm-motion@0.2"
SUPPORTED_MOTION_SEMANTICS = frozenset({MOTION_SEMANTICS_V1_IDENTITY, MOTION_SEMANTICS_IDENTITY})


@dataclass(frozen=True)
class TemporalInterval:
    start_tick: int
    end_tick: int | None


@dataclass(frozen=True)
class MotionRevisionDelta:
    track_id: str
    keyframe_id: str
    interval: TemporalInterval


@dataclass(frozen=True)
class MotionFrame:
    tick: int
    seconds: Fraction
    scene: EvaluatedScene
    evaluator: Evaluator


def validate_motion(document: dict[str, Any], evaluator: Evaluator) -> None:
    animation = document.get("animation")
    if not isinstance(animation, dict):
        raise DocumentError("Document animation must be an object")
    tracks = animation.get("content")
    if not isinstance(tracks, list):
        raise DocumentError("Animation content must be an array")
    timebase = animation.get("timebase")
    if not tracks:
        semantics_version = animation.get("semantics_version")
        if semantics_version is not None and semantics_version not in SUPPORTED_MOTION_SEMANTICS:
            raise DocumentError(f"Unsupported Motion semantics {semantics_version!r}")
        if timebase is not None:
            _ticks_per_second(timebase)
        return
    semantics_version = animation.get("semantics_version")
    if semantics_version not in SUPPORTED_MOTION_SEMANTICS:
        raise DocumentError(f"Unsupported Motion semantics {semantics_version!r}")
    _ticks_per_second(timebase)
    track_ids: set[str] = set()
    targets: set[tuple[str, str]] = set()
    for track in tracks:
        if not isinstance(track, dict):
            raise DocumentError("Animation Track must be an object")
        track_id = track.get("id")
        if not isinstance(track_id, str) or not track_id.startswith("track:"):
            raise DocumentError("Animation Track requires a track: ID")
        if track_id in track_ids:
            raise DocumentError(f"Duplicate Animation Track ID {track_id}")
        track_ids.add(track_id)
        if track.get("value_type") != "number" or track.get("interpolation") != "linear":
            raise DocumentError(f"Track {track_id} uses unsupported value/interpolation semantics")
        target = track.get("target")
        if not isinstance(target, dict) or set(target) != {"operation", "parameter"}:
            raise DocumentError(f"Track {track_id} has invalid target")
        operation_id = target["operation"]
        parameter = target["parameter"]
        if operation_id not in evaluator.operations:
            raise DocumentError(f"Track {track_id} targets missing Operation {operation_id}")
        operation = evaluator.operations[operation_id]
        if parameter not in operation.get("parameters", {}):
            raise DocumentError(f"Track {track_id} targets missing parameter {parameter}")
        if (
            semantics_version == MOTION_SEMANTICS_IDENTITY
            and parameter not in evaluator.registry.animatable_parameters(operation)
        ):
            raise DocumentError(
                f"Track {track_id} targets non-animatable parameter {operation_id}.{parameter}"
            )
        current = operation["parameters"][parameter]
        if not _finite_number(current):
            raise DocumentError(f"Track {track_id} target parameter is not numeric")
        target_key = (operation_id, parameter)
        if target_key in targets:
            raise DocumentError(f"Multiple Tracks target {operation_id}.{parameter}")
        targets.add(target_key)
        keyframes = track.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            raise DocumentError(f"Track {track_id} requires Keyframes")
        keyframe_ids: set[str] = set()
        ticks: list[int] = []
        for keyframe in keyframes:
            if not isinstance(keyframe, dict):
                raise DocumentError(f"Track {track_id} Keyframe must be an object")
            keyframe_id = keyframe.get("id")
            tick = keyframe.get("tick")
            if not isinstance(keyframe_id, str) or not keyframe_id.startswith("keyframe:"):
                raise DocumentError(f"Track {track_id} has invalid Keyframe ID")
            if keyframe_id in keyframe_ids:
                raise DocumentError(f"Track {track_id} has duplicate Keyframe IDs")
            if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
                raise DocumentError(f"Track {track_id} has invalid Keyframe tick")
            if not _finite_number(keyframe.get("value")):
                raise DocumentError(f"Track {track_id} has non-finite Keyframe value")
            candidate = copy.deepcopy(operation)
            candidate["parameters"][parameter] = keyframe["value"]
            try:
                evaluator.registry.validate(candidate)
            except OperationValidationError as exc:
                raise DocumentError(
                    f"Track {track_id} Keyframe {keyframe_id} violates target semantics: {exc}"
                ) from exc
            keyframe_ids.add(keyframe_id)
            ticks.append(tick)
        if ticks != sorted(set(ticks)):
            raise DocumentError(f"Track {track_id} Keyframes must have unique increasing ticks")


class MotionEvaluator:
    """Deterministically samples accepted content animation at integer ticks."""

    def __init__(
        self,
        document: dict[str, Any],
        *,
        geometry_backend: GeometryBackend | None = None,
    ) -> None:
        self.document = copy.deepcopy(document)
        baseline = Evaluator(self.document, geometry_backend=geometry_backend)
        validate_motion(self.document, baseline)
        self.geometry_backend = geometry_backend
        self.ticks_per_second = _ticks_per_second(self.document["animation"].get("timebase"))
        self.value_cache: dict[str, dict[str, ImmutableValue]] = {}
        self.frame_cache: dict[tuple[int, Quality], MotionFrame] = {}

    def evaluate(self, tick: int, quality: Quality = Quality.FINAL) -> MotionFrame:
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            raise DocumentError("Motion evaluation tick must be a non-negative integer")
        cache_key = (tick, quality)
        cached = self.frame_cache.get(cache_key)
        if cached is not None:
            return cached
        sampled = self.sample_document(tick)
        evaluator = Evaluator(
            sampled,
            geometry_backend=self.geometry_backend,
            value_cache=self.value_cache,
        )
        scene = build_evaluated_scene(sampled, evaluator, quality)
        frame = MotionFrame(
            tick=tick,
            seconds=Fraction(tick, self.ticks_per_second),
            scene=scene,
            evaluator=evaluator,
        )
        self.frame_cache[cache_key] = frame
        return frame

    def sample_document(self, tick: int) -> dict[str, Any]:
        sampled = copy.deepcopy(self.document)
        operations = {
            operation["id"]: operation for operation in sampled["construction"]["operations"]
        }
        for track in sampled["animation"]["content"]:
            target = track["target"]
            operations[target["operation"]]["parameters"][target["parameter"]] = _sample_track(
                track, tick
            )
        return sampled

    def set_keyframe_value(
        self, track_id: str, keyframe_id: str, value: float
    ) -> TemporalInterval | None:
        """Exercise runtime invalidation; this is not a persistent Document edit API."""
        if not _finite_number(value):
            raise DocumentError("Keyframe value must be finite")
        track = next(
            (item for item in self.document["animation"]["content"] if item["id"] == track_id),
            None,
        )
        if track is None:
            raise DocumentError(f"Missing Animation Track {track_id}")
        keyframes = track["keyframes"]
        index = next(
            (position for position, item in enumerate(keyframes) if item["id"] == keyframe_id),
            None,
        )
        if index is None:
            raise DocumentError(f"Missing Keyframe {keyframe_id}")
        previous = keyframes[index]["value"]
        if canonical_motion_number(previous) == canonical_motion_number(value):
            return None
        keyframes[index]["value"] = value
        try:
            validate_motion(
                self.document,
                Evaluator(self.document, geometry_backend=self.geometry_backend),
            )
        except DocumentError:
            keyframes[index]["value"] = previous
            raise
        interval = TemporalInterval(
            start_tick=keyframes[index - 1]["tick"] + 1 if index > 0 else 0,
            end_tick=(keyframes[index + 1]["tick"] - 1 if index + 1 < len(keyframes) else None),
        )
        self.frame_cache = {
            key: frame
            for key, frame in self.frame_cache.items()
            if not (
                key[0] >= interval.start_tick
                and (interval.end_tick is None or key[0] <= interval.end_tick)
            )
        }
        return interval

    def transition_to_revision(
        self, document: dict[str, Any]
    ) -> tuple[MotionEvaluator, tuple[MotionRevisionDelta, ...]]:
        """Create a runtime for a new snapshot and retain only unaffected frame entries."""
        successor = MotionEvaluator(document, geometry_backend=self.geometry_backend)
        deltas = motion_revision_deltas(self.document, successor.document)
        successor.value_cache = self.value_cache
        successor.frame_cache = {
            key: frame
            for key, frame in self.frame_cache.items()
            if not any(_tick_in_interval(key[0], delta.interval) for delta in deltas)
        }
        return successor, deltas


def motion_revision_deltas(
    previous: dict[str, Any], current: dict[str, Any]
) -> tuple[MotionRevisionDelta, ...]:
    """Compare compatible Motion snapshots and locate changed interpolation domains."""
    if _without_keyframe_values(previous) != _without_keyframe_values(current):
        raise DocumentError("Motion revision transition supports only Keyframe value changes")
    previous_animation = previous.get("animation", {})
    current_animation = current.get("animation", {})
    if {key: value for key, value in previous_animation.items() if key != "content"} != {
        key: value for key, value in current_animation.items() if key != "content"
    }:
        raise DocumentError("Motion revision transition requires unchanged animation semantics")
    previous_tracks = previous_animation.get("content", [])
    current_tracks = current_animation.get("content", [])
    if len(previous_tracks) != len(current_tracks):
        raise DocumentError("Motion revision transition requires stable Track structure")
    deltas: list[MotionRevisionDelta] = []
    for old_track, new_track in zip(previous_tracks, current_tracks, strict=True):
        old_shape = {key: value for key, value in old_track.items() if key != "keyframes"}
        new_shape = {key: value for key, value in new_track.items() if key != "keyframes"}
        old_keyframes = old_track.get("keyframes", [])
        new_keyframes = new_track.get("keyframes", [])
        if old_shape != new_shape or len(old_keyframes) != len(new_keyframes):
            raise DocumentError("Motion revision transition requires stable Track structure")
        for index, (old_keyframe, new_keyframe) in enumerate(
            zip(old_keyframes, new_keyframes, strict=True)
        ):
            if {key: value for key, value in old_keyframe.items() if key != "value"} != {
                key: value for key, value in new_keyframe.items() if key != "value"
            }:
                raise DocumentError("Motion revision transition requires stable Keyframe identity")
            if canonical_motion_number(old_keyframe["value"]) == canonical_motion_number(
                new_keyframe["value"]
            ):
                continue
            deltas.append(
                MotionRevisionDelta(
                    track_id=old_track["id"],
                    keyframe_id=old_keyframe["id"],
                    interval=_keyframe_influence_interval(old_keyframes, index),
                )
            )
    return tuple(deltas)


def _without_keyframe_values(document: dict[str, Any]) -> dict[str, Any]:
    shape = copy.deepcopy(document)
    for track in shape.get("animation", {}).get("content", []):
        for keyframe in track.get("keyframes", []):
            if "value" in keyframe:
                keyframe["value"] = None
    return shape


def _keyframe_influence_interval(keyframes: list[dict[str, Any]], index: int) -> TemporalInterval:
    return TemporalInterval(
        start_tick=keyframes[index - 1]["tick"] + 1 if index > 0 else 0,
        end_tick=keyframes[index + 1]["tick"] - 1 if index + 1 < len(keyframes) else None,
    )


def _tick_in_interval(tick: int, interval: TemporalInterval) -> bool:
    return tick >= interval.start_tick and (interval.end_tick is None or tick <= interval.end_tick)


def _ticks_per_second(timebase: Any) -> int:
    if (
        not isinstance(timebase, dict)
        or set(timebase) != {"ticks_per_second"}
        or not isinstance(timebase["ticks_per_second"], int)
        or isinstance(timebase["ticks_per_second"], bool)
        or not 1 <= timebase["ticks_per_second"] <= 1_000_000_000
    ):
        raise DocumentError("Animated content requires a valid integer Timebase")
    return timebase["ticks_per_second"]


def _sample_track(track: dict[str, Any], tick: int) -> int | float:
    keyframes = track["keyframes"]
    if tick <= keyframes[0]["tick"]:
        return canonical_motion_number(keyframes[0]["value"])
    if tick >= keyframes[-1]["tick"]:
        return canonical_motion_number(keyframes[-1]["value"])
    for left, right in zip(keyframes, keyframes[1:], strict=False):
        if left["tick"] <= tick <= right["tick"]:
            span = right["tick"] - left["tick"]
            offset = tick - left["tick"]
            value = Fraction(str(left["value"])) + (
                Fraction(str(right["value"])) - Fraction(str(left["value"]))
            ) * Fraction(offset, span)
            return canonical_motion_number(value)
    raise DocumentError(f"Cannot sample Track {track['id']} at tick {tick}")


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def canonical_motion_number(value: Any) -> int | float:
    if isinstance(value, Fraction):
        number = value
    elif _finite_number(value):
        number = Fraction(str(value))
    else:
        raise DocumentError("Motion number must be finite")
    return number.numerator if number.denominator == 1 else float(number)
