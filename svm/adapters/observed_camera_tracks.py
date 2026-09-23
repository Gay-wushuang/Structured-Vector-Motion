from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, GeneratorProvenance, Proposal, ProposalPreview
from ..revisions import (
    AddKeyframeChange,
    CreateCameraTransformTrackChange,
    Transaction,
    VerifyObservedCameraTracksSourceChange,
)
from .camera_compensation import CAMERA_MEDIA_TYPE, CAMERA_POLICY

POLICY_IDENTITY = "svm-verified-observed-camera-authoring@0.1"
ADAPTER_ID = "adapter:observed-camera-tracks"
PROPERTIES = ("position.x", "position.y", "rotation_degrees", "scale")
IDENTITY_CAMERA = {"position": [0, 0], "rotation_degrees": 0, "scale": 1}


class ObservedCameraTracksError(ValueError):
    pass


@dataclass(frozen=True)
class CameraKeyframePreview:
    tick: int
    value: int | float


@dataclass(frozen=True)
class CameraTrackPreview:
    track_id: str
    property_name: str
    keyframes: tuple[CameraKeyframePreview, ...]


@dataclass(frozen=True)
class ObservedCameraTracksPreview(ProposalPreview):
    mode: str = "CREATE"
    evidence_artifact_id: str = ""
    camera_target: str = "presentation"
    ticks_per_second: int = 0
    tracks: tuple[CameraTrackPreview, ...] = ()


class ObservedCameraTracksAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise ObservedCameraTracksError("Camera authoring scope must be document")
        if set(request.options) != {"camera_target", "ticks_per_second"}:
            raise ObservedCameraTracksError(
                "Explicit camera_target and ticks_per_second are required"
            )
        camera_target = request.options["camera_target"]
        ticks_per_second = request.options["ticks_per_second"]
        if camera_target != "presentation":
            raise ObservedCameraTracksError("Observed Camera target must be presentation")
        if (
            not isinstance(ticks_per_second, int)
            or isinstance(ticks_per_second, bool)
            or ticks_per_second <= 0
        ):
            raise ObservedCameraTracksError("ticks_per_second must be a positive integer")
        if len(request.artifact_ids) != 1:
            raise ObservedCameraTracksError(
                "Camera authoring requires one Camera evidence Artifact"
            )
        camera = request.document.get("presentation", {}).get("camera")
        if camera != IDENTITY_CAMERA:
            raise ObservedCameraTracksError("S9C requires an identity static Camera baseline")
        animation_before = copy.deepcopy(request.document["animation"])
        existing = [
            track
            for track in animation_before.get("content", [])
            if track.get("target", {}).get("camera") == "presentation"
            and track.get("target", {}).get("property") in PROPERTIES
        ]
        if existing:
            raise ObservedCameraTracksError("Camera Track CREATE rejects an existing target")
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        payload = _read_evidence(snapshot)
        samples = recover_camera_samples(payload["intervals"])
        definitions = _track_definitions(snapshot.artifact_id, samples, ticks_per_second)
        authored_tracks = _document_tracks(
            definitions, snapshot.artifact_id, request.base_revision_id
        )
        expected_animation = _expected_animation(
            animation_before, authored_tracks, ticks_per_second
        )
        changes: list[Any] = []
        if "anchor_entity_ids" in payload:
            from .camera_compensation import _static_anchor

            for anchor_id in payload["anchor_entity_ids"]:
                _static_anchor(request.document, anchor_id)
        for property_name, track_id, keyframes in definitions:
            changes.append(
                CreateCameraTransformTrackChange(
                    track_id, property_name, ticks_per_second, "linear"
                )
            )
            changes.extend(
                AddKeyframeChange(track_id, keyframe_id, tick, value)
                for keyframe_id, tick, value in keyframes
            )
        changes.append(
            VerifyObservedCameraTracksSourceChange(
                reference,
                copy.deepcopy(camera),
                request.base_revision_id,
                ticks_per_second,
                authored_tracks,
                animation_before,
                expected_animation,
            )
        )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "svm-verified-observed-camera-authoring",
            POLICY_IDENTITY,
            {
                "evidence_artifact_id": snapshot.artifact_id,
                "camera_target": camera_target,
                "ticks_per_second": ticks_per_second,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "tracks": authored_tracks,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:observed-camera-tracks:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:observed-camera-tracks:{digest}",
                tuple(changes),
                "Author four verified observed Camera Tracks",
            ),
            preview=ObservedCameraTracksPreview(
                mode="CREATE",
                evidence_artifact_id=snapshot.artifact_id,
                camera_target=camera_target,
                ticks_per_second=ticks_per_second,
                tracks=tuple(
                    CameraTrackPreview(
                        track_id,
                        property_name,
                        tuple(CameraKeyframePreview(tick, value) for _, tick, value in keyframes),
                    )
                    for property_name, track_id, keyframes in definitions
                ),
            ),
            required_artifact_ids=(snapshot.artifact_id,),
            notes="CREATE four linear Camera Tracks from accepted Camera evidence",
        )


def verify_observed_camera_tracks_source(
    change: Any, resolved: dict[str, ArtifactSnapshot]
) -> None:
    snapshot = resolved.get(change.evidence_reference.get("id"))
    if snapshot is None:
        raise ValueError("Observed Camera evidence Artifact was not resolved")
    payload = _read_evidence(snapshot)
    samples = recover_camera_samples(payload["intervals"])
    definitions = _track_definitions(snapshot.artifact_id, samples, change.ticks_per_second)
    expected_tracks = _document_tracks(definitions, snapshot.artifact_id, change.source_revision_id)
    if change.authored_tracks != expected_tracks:
        raise ValueError("Observed Camera Track definitions do not match evidence")
    if change.camera_before != IDENTITY_CAMERA:
        raise ValueError("Observed Camera authoring baseline is invalid")
    expected_animation = _expected_animation(
        change.animation_before, expected_tracks, change.ticks_per_second
    )
    if change.expected_animation != expected_animation:
        raise ValueError("Observed Camera animation result is inconsistent")


def recover_camera_samples(intervals: Any) -> tuple[dict[str, int | float], ...]:
    if not isinstance(intervals, list) or not intervals:
        raise ObservedCameraTracksError("Camera evidence requires a non-empty interval chain")
    matrices: list[tuple[int, tuple[float, float, float, float, float, float]]] = []
    previous_target_tick: int | None = None
    previous_target_matrix: tuple[float, float, float, float, float, float] | None = None
    for index, interval in enumerate(intervals):
        if not isinstance(interval, dict):
            raise ObservedCameraTracksError("Camera evidence interval is invalid")
        source_tick, target_tick = interval.get("source_tick"), interval.get("target_tick")
        source = _matrix(interval.get("source_view_transform"))
        target = _matrix(interval.get("target_view_transform"))
        if (
            not isinstance(source_tick, int)
            or isinstance(source_tick, bool)
            or not isinstance(target_tick, int)
            or isinstance(target_tick, bool)
            or source_tick < 0
            or target_tick <= source_tick
            or (previous_target_tick is not None and source_tick != previous_target_tick)
            or (previous_target_matrix is not None and source != previous_target_matrix)
        ):
            raise ObservedCameraTracksError(
                "Camera evidence intervals must form one exact contiguous chain"
            )
        if index == 0:
            matrices.append((source_tick, source))
        matrices.append((target_tick, target))
        previous_target_tick, previous_target_matrix = target_tick, target
    samples = []
    previous_rotation: float | None = None
    for tick, matrix in matrices:
        state = recover_camera_state(matrix, previous_rotation)
        samples.append({"tick": tick, **state})
        previous_rotation = float(state["rotation_degrees"])
    if samples[0] != {
        "tick": samples[0]["tick"],
        "position.x": 0.0,
        "position.y": 0.0,
        "rotation_degrees": 0.0,
        "scale": 1.0,
    }:
        raise ObservedCameraTracksError("Camera evidence must start at the identity baseline")
    return tuple(samples)


def recover_camera_state(matrix: Any, previous_rotation: float | None = None) -> dict[str, float]:
    a, b, c, d, tx, ty = _matrix(matrix)
    scale = math.hypot(a, b)
    determinant = a * d - b * c
    tolerance = max(1.0, scale) * 1e-9
    if scale <= 0 or determinant <= 0 or abs(c + b) > tolerance or abs(d - a) > tolerance:
        raise ObservedCameraTracksError("Camera view transform is not a uniform similarity")
    wrapped = _canonical(-math.degrees(math.atan2(b, a)))
    rotation = wrapped
    if previous_rotation is not None:
        rotation += 360.0 * round((previous_rotation - rotation) / 360.0)
        if rotation - previous_rotation <= -180.0:
            rotation += 360.0
        elif rotation - previous_rotation > 180.0:
            rotation -= 360.0
    position_x = -(d * tx - c * ty) / determinant
    position_y = -(-b * tx + a * ty) / determinant
    return {
        "position.x": _canonical(position_x),
        "position.y": _canonical(position_y),
        "rotation_degrees": _canonical(rotation),
        "scale": _canonical(scale),
    }


def _read_evidence(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    from .camera_consensus import read_camera_evidence

    try:
        return read_camera_evidence(snapshot)
    except ValueError as exc:
        raise ObservedCameraTracksError(str(exc)) from exc


def _read_single_evidence(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservedCameraTracksError("Camera evidence is invalid JSON") from exc
    if (
        snapshot.kind != ArtifactKind.DERIVED
        or snapshot.media_type != CAMERA_MEDIA_TYPE
        or snapshot.provenance.get("adapter_id") != "adapter:observed-camera-similarity"
        or snapshot.provenance.get("policy_identity") != CAMERA_POLICY
        or not isinstance(payload, dict)
        or canonical_bytes(payload) != snapshot.content
        or payload.get("schema_version") != "svm-observed-camera-similarity-0.1"
        or payload.get("identity") != "svm-observed-camera-similarity@0.1"
        or payload.get("policy_identity") != CAMERA_POLICY
        or not isinstance(payload.get("anchor_entity_id"), str)
        or not isinstance(payload.get("source_similarity_artifact_id"), str)
        or not isinstance(payload.get("intervals"), list)
    ):
        raise ObservedCameraTracksError("Camera authoring requires canonical S9B evidence")
    return payload


def _track_definitions(evidence_id: str, samples, ticks_per_second: int):
    definitions = []
    for property_name in PROPERTIES:
        subject = {
            "policy_identity": POLICY_IDENTITY,
            "evidence_artifact_id": evidence_id,
            "camera_target": "presentation",
            "property": property_name,
            "ticks_per_second": ticks_per_second,
        }
        track_id = "track:observed-camera:" + hashlib.sha256(canonical_bytes(subject)).hexdigest()
        keyframes = tuple(
            (
                "keyframe:observed-camera:"
                + hashlib.sha256(
                    canonical_bytes({"track_id": track_id, "tick": sample["tick"]})
                ).hexdigest(),
                sample["tick"],
                sample[property_name],
            )
            for sample in samples
        )
        definitions.append((property_name, track_id, keyframes))
    return tuple(definitions)


def _document_tracks(definitions, evidence_id: str, source_revision_id: str):
    return tuple(
        {
            "id": track_id,
            "target": {"camera": "presentation", "property": property_name},
            "value_type": "number",
            "interpolation": "linear",
            "keyframes": [
                {"id": keyframe_id, "tick": tick, "value": value}
                for keyframe_id, tick, value in keyframes
            ],
            "provenance": {
                "type": "ObservedCameraTrack",
                "authoring_identity": POLICY_IDENTITY,
                "evidence_artifact_id": evidence_id,
                "source_revision_id": source_revision_id,
                "camera_target": "presentation",
                "property": property_name,
            },
        }
        for property_name, track_id, keyframes in definitions
    )


def _expected_animation(animation_before, authored_tracks, ticks_per_second):
    animation = copy.deepcopy(animation_before)
    timebase = animation.get("timebase")
    if timebase is not None and timebase.get("ticks_per_second") != ticks_per_second:
        raise ObservedCameraTracksError("ticks_per_second conflicts with Document timebase")
    animation["semantics_version"] = "svm-motion@0.6"
    animation["timebase"] = {"ticks_per_second": ticks_per_second}
    animation["content"].extend(copy.deepcopy(authored_tracks))
    return animation


def _matrix(value: Any) -> tuple[float, float, float, float, float, float]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 6
        or any(not _finite(item) for item in value)
    ):
        raise ObservedCameraTracksError("Camera view transform must contain six finite numbers")
    return tuple(float(item) for item in value)  # type: ignore[return-value]


def _accepted_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ObservedCameraTracksError("Camera evidence must already be accepted")
    return copy.deepcopy(matches[0])


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _canonical(value: float) -> float:
    return 0.0 if abs(value) < 1e-12 else float(format(value, ".12g"))
