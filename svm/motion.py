from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, cast

from .backends import GeometryBackend
from .evaluator import DocumentError, Evaluator, ImmutableValue, Quality
from .operations import OperationValidationError
from .scene import EvaluatedScene, build_evaluated_scene

MOTION_SEMANTICS_V1_IDENTITY = "svm-motion@0.1"
MOTION_SEMANTICS_IDENTITY = "svm-motion@0.2"
GROUP_MOTION_SEMANTICS_IDENTITY = "svm-motion@0.3"
EASING_MOTION_SEMANTICS_IDENTITY = "svm-motion@0.4"
STYLE_MOTION_SEMANTICS_IDENTITY = "svm-motion@0.5"
CAMERA_MOTION_SEMANTICS_IDENTITY = "svm-motion@0.6"
SUPPORTED_MOTION_SEMANTICS = frozenset(
    {
        MOTION_SEMANTICS_V1_IDENTITY,
        MOTION_SEMANTICS_IDENTITY,
        GROUP_MOTION_SEMANTICS_IDENTITY,
        EASING_MOTION_SEMANTICS_IDENTITY,
        STYLE_MOTION_SEMANTICS_IDENTITY,
        CAMERA_MOTION_SEMANTICS_IDENTITY,
    }
)
GROUP_TRANSFORM_TRACK_PROPERTIES = frozenset(
    {"translate.x", "translate.y", "rotation_degrees", "scale"}
)
SUPPORTED_INTERPOLATIONS = frozenset({"linear", "ease-in-out"})
STYLE_TRACK_PROPERTIES = frozenset({"opacity", "fill"})
CAMERA_TRACK_PROPERTIES = frozenset({"position.x", "position.y", "rotation_degrees", "scale"})


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
    targets: set[tuple[str, str, str]] = set()
    for track in tracks:
        if not isinstance(track, dict):
            raise DocumentError("Animation Track must be an object")
        track_id = track.get("id")
        if not isinstance(track_id, str) or not track_id.startswith("track:"):
            raise DocumentError("Animation Track requires a track: ID")
        if track_id in track_ids:
            raise DocumentError(f"Duplicate Animation Track ID {track_id}")
        track_ids.add(track_id)
        interpolation = track.get("interpolation")
        value_type = track.get("value_type")
        if semantics_version in {STYLE_MOTION_SEMANTICS_IDENTITY, CAMERA_MOTION_SEMANTICS_IDENTITY}:
            valid_track_shape = value_type in {"number", "color"} and interpolation in {
                *SUPPORTED_INTERPOLATIONS,
                "hold",
            }
        else:
            allowed_interpolations = (
                SUPPORTED_INTERPOLATIONS
                if semantics_version == EASING_MOTION_SEMANTICS_IDENTITY
                else frozenset({"linear"})
            )
            valid_track_shape = value_type == "number" and interpolation in allowed_interpolations
        if not valid_track_shape:
            raise DocumentError(f"Track {track_id} uses unsupported value/interpolation semantics")
        target_key = _validate_track_target(document, evaluator, semantics_version, track_id, track)
        if target_key in targets:
            raise DocumentError(f"Multiple Tracks target {'.'.join(target_key)}")
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
            canonical_track_value(track, keyframe.get("value"))
            _validate_sampled_target_value(
                evaluator, track_id, keyframe_id, track["target"], keyframe["value"]
            )
            keyframe_ids.add(keyframe_id)
            ticks.append(tick)
        if ticks != sorted(set(ticks)):
            raise DocumentError(f"Track {track_id} Keyframes must have unique increasing ticks")


def _validate_track_target(
    document: dict[str, Any],
    evaluator: Evaluator,
    semantics_version: Any,
    track_id: str,
    track: dict[str, Any],
) -> tuple[str, str, str]:
    target = track.get("target")
    if isinstance(target, dict) and set(target) == {"operation", "parameter"}:
        operation_id = target["operation"]
        parameter = target["parameter"]
        if operation_id not in evaluator.operations:
            raise DocumentError(f"Track {track_id} targets missing Operation {operation_id}")
        operation = evaluator.operations[operation_id]
        if parameter not in operation.get("parameters", {}):
            raise DocumentError(f"Track {track_id} targets missing parameter {parameter}")
        if semantics_version in {
            MOTION_SEMANTICS_IDENTITY,
            GROUP_MOTION_SEMANTICS_IDENTITY,
            EASING_MOTION_SEMANTICS_IDENTITY,
            STYLE_MOTION_SEMANTICS_IDENTITY,
            CAMERA_MOTION_SEMANTICS_IDENTITY,
        } and parameter not in evaluator.registry.animatable_parameters(operation):
            raise DocumentError(
                f"Track {track_id} targets non-animatable parameter {operation_id}.{parameter}"
            )
        current = operation["parameters"][parameter]
        if not _finite_number(current):
            raise DocumentError(f"Track {track_id} target parameter is not numeric")
        if track["value_type"] != "number" or track["interpolation"] == "hold":
            raise DocumentError(f"Track {track_id} has invalid Operation Track semantics")
        return ("operation", operation_id, parameter)
    if isinstance(target, dict) and set(target) == {"group", "property"}:
        if semantics_version not in {
            GROUP_MOTION_SEMANTICS_IDENTITY,
            EASING_MOTION_SEMANTICS_IDENTITY,
            STYLE_MOTION_SEMANTICS_IDENTITY,
            CAMERA_MOTION_SEMANTICS_IDENTITY,
        }:
            raise DocumentError(f"Track {track_id} requires Group Motion semantics")
        group_id = target["group"]
        property_name = target["property"]
        if property_name not in GROUP_TRANSFORM_TRACK_PROPERTIES:
            raise DocumentError(f"Track {track_id} targets unsupported Group property")
        group = next(
            (item for item in document.get("groups", []) if item.get("id") == group_id), None
        )
        if group is None:
            raise DocumentError(f"Track {track_id} targets missing Group {group_id}")
        transform = group.get("transform")
        if not isinstance(transform, dict):
            raise DocumentError(f"Track {track_id} requires an existing Group Transform")
        _group_transform_property(transform, property_name)
        if track["value_type"] != "number" or track["interpolation"] == "hold":
            raise DocumentError(f"Track {track_id} has invalid Group Track semantics")
        return ("group", group_id, property_name)
    if isinstance(target, dict) and set(target) == {"entity", "property"}:
        if semantics_version not in {
            STYLE_MOTION_SEMANTICS_IDENTITY,
            CAMERA_MOTION_SEMANTICS_IDENTITY,
        }:
            raise DocumentError(f"Track {track_id} requires Style Motion semantics")
        entity_id = target["entity"]
        property_name = target["property"]
        if property_name not in STYLE_TRACK_PROPERTIES:
            raise DocumentError(f"Track {track_id} targets unsupported Style property")
        style = next(
            (
                item
                for item in document.get("presentation", {}).get("styles", [])
                if item.get("entity") == entity_id
            ),
            None,
        )
        if style is None:
            raise DocumentError(f"Track {track_id} targets missing Entity Style {entity_id}")
        if property_name == "opacity":
            if track["value_type"] != "number" or track["interpolation"] == "hold":
                raise DocumentError(f"Track {track_id} has invalid opacity Track semantics")
        elif track["value_type"] != "color" or track["interpolation"] != "hold":
            raise DocumentError(f"Track {track_id} has invalid fill Track semantics")
        return ("entity", entity_id, property_name)
    if isinstance(target, dict) and set(target) == {"camera", "property"}:
        if (
            semantics_version != CAMERA_MOTION_SEMANTICS_IDENTITY
            or target["camera"] != "presentation"
        ):
            raise DocumentError(f"Track {track_id} requires Camera Motion semantics")
        if target["property"] not in CAMERA_TRACK_PROPERTIES:
            raise DocumentError(f"Track {track_id} targets unsupported Camera property")
        if not isinstance(document.get("presentation", {}).get("camera"), dict):
            raise DocumentError(f"Track {track_id} requires an existing Camera")
        if track["value_type"] != "number" or track["interpolation"] == "hold":
            raise DocumentError(f"Track {track_id} has invalid Camera Track semantics")
        return ("camera", "presentation", target["property"])
    raise DocumentError(f"Track {track_id} has invalid target")


def _validate_sampled_target_value(
    evaluator: Evaluator,
    track_id: str,
    keyframe_id: str,
    target: dict[str, Any],
    value: Any,
) -> None:
    if "operation" in target:
        operation = copy.deepcopy(evaluator.operations[target["operation"]])
        operation["parameters"][target["parameter"]] = value
        try:
            evaluator.registry.validate(operation)
        except OperationValidationError as exc:
            raise DocumentError(
                f"Track {track_id} Keyframe {keyframe_id} violates target semantics: {exc}"
            ) from exc
        return
    if "entity" in target:
        if target["property"] == "opacity" and not 0 <= value <= 1:
            raise DocumentError(
                f"Track {track_id} Keyframe {keyframe_id} opacity must be between 0 and 1"
            )
        return
    if "camera" in target:
        if target["property"] == "scale" and value <= 0:
            raise DocumentError(f"Track {track_id} Keyframe {keyframe_id} requires positive scale")
        return
    if target["property"] == "scale" and value <= 0:
        raise DocumentError(f"Track {track_id} Keyframe {keyframe_id} requires positive scale")


def _group_transform_property(transform: dict[str, Any], property_name: str) -> int | float:
    if property_name == "translate.x":
        return transform["translate"][0]
    if property_name == "translate.y":
        return transform["translate"][1]
    return transform[property_name]


def _set_group_transform_property(
    transform: dict[str, Any], property_name: str, value: int | float
) -> None:
    if property_name == "translate.x":
        transform["translate"][0] = value
    elif property_name == "translate.y":
        transform["translate"][1] = value
    else:
        transform[property_name] = value


def _set_camera_property(camera: dict[str, Any], property_name: str, value: int | float) -> None:
    if property_name == "position.x":
        camera["position"][0] = value
    elif property_name == "position.y":
        camera["position"][1] = value
    else:
        camera[property_name] = value


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
        groups = {group["id"]: group for group in sampled.get("groups", [])}
        styles = {
            style["entity"]: style for style in sampled.get("presentation", {}).get("styles", [])
        }
        camera = sampled["presentation"].get("camera")
        for track in sampled["animation"]["content"]:
            target = track["target"]
            value = _sample_track(track, tick)
            if "operation" in target:
                operations[target["operation"]]["parameters"][target["parameter"]] = value
            elif "group" in target:
                _set_group_transform_property(
                    groups[target["group"]]["transform"],
                    target["property"],
                    cast(int | float, value),
                )
            elif "entity" in target:
                styles[target["entity"]][target["property"]] = value
            else:
                _set_camera_property(camera, target["property"], cast(int | float, value))
        return sampled

    def set_keyframe_value(
        self, track_id: str, keyframe_id: str, value: Any
    ) -> TemporalInterval | None:
        """Exercise runtime invalidation; this is not a persistent Document edit API."""
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
        value = canonical_track_value(track, value)
        previous_raw = keyframes[index]["value"]
        previous = canonical_track_value(track, previous_raw)
        if previous == value:
            return None
        keyframes[index]["value"] = value
        try:
            validate_motion(
                self.document,
                Evaluator(self.document, geometry_backend=self.geometry_backend),
            )
        except DocumentError:
            keyframes[index]["value"] = previous_raw
            raise
        interval = _keyframe_influence_interval(keyframes, index, track["interpolation"])
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
            if canonical_track_value(old_track, old_keyframe["value"]) == canonical_track_value(
                new_track, new_keyframe["value"]
            ):
                continue
            deltas.append(
                MotionRevisionDelta(
                    track_id=old_track["id"],
                    keyframe_id=old_keyframe["id"],
                    interval=_keyframe_influence_interval(
                        old_keyframes, index, old_track["interpolation"]
                    ),
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


def _keyframe_influence_interval(
    keyframes: list[dict[str, Any]], index: int, interpolation: str = "linear"
) -> TemporalInterval:
    if interpolation == "hold":
        return TemporalInterval(
            start_tick=keyframes[index]["tick"] if index > 0 else 0,
            end_tick=(keyframes[index + 1]["tick"] - 1 if index + 1 < len(keyframes) else None),
        )
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


def _sample_track(track: dict[str, Any], tick: int) -> int | float | str:
    keyframes = track["keyframes"]
    if tick <= keyframes[0]["tick"]:
        return canonical_track_value(track, keyframes[0]["value"])
    if tick >= keyframes[-1]["tick"]:
        return canonical_track_value(track, keyframes[-1]["value"])
    if track["interpolation"] == "hold":
        return canonical_track_value(
            track,
            next(
                keyframe["value"]
                for keyframe, following in zip(keyframes, keyframes[1:], strict=False)
                if keyframe["tick"] <= tick < following["tick"]
            ),
        )
    for left, right in zip(keyframes, keyframes[1:], strict=False):
        if left["tick"] <= tick <= right["tick"]:
            span = right["tick"] - left["tick"]
            offset = tick - left["tick"]
            progress = Fraction(offset, span)
            if track["interpolation"] == "ease-in-out":
                progress = 3 * progress**2 - 2 * progress**3
            value = (
                Fraction(str(left["value"]))
                + (Fraction(str(right["value"])) - Fraction(str(left["value"]))) * progress
            )
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


def canonical_track_value(track: dict[str, Any], value: Any) -> int | float | str:
    if track.get("value_type") == "number":
        return canonical_motion_number(value)
    if track.get("value_type") == "color" and isinstance(value, str) and _supported_color(value):
        return value
    raise DocumentError("Track value does not match its recorded value type")


def _supported_color(value: str) -> bool:
    if value == "none":
        return True
    return (
        len(value) in {7, 9}
        and value.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in value[1:])
    )
