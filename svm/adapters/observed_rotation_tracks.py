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
    MOTION_TARGET_BINDING_POLICY_IDENTITY,
    AddKeyframeChange,
    CreateGroupTransformTrackChange,
    Transaction,
    VerifyObservedRotationTrackSourceChange,
)
from .observed_similarity_motion import MEDIA_TYPE as SIMILARITY_MEDIA_TYPE
from .observed_similarity_motion import POLICY_IDENTITY as SIMILARITY_POLICY_IDENTITY

POLICY_IDENTITY = "svm-verified-observed-rotation-authoring@0.1"
ADAPTER_ID = "adapter:observed-rotation-tracks"


class ObservedRotationTracksError(ValueError):
    pass


@dataclass(frozen=True)
class RotationKeyframePreview:
    tick: int
    value: int | float
    source_delta: int | float | None = None


@dataclass(frozen=True)
class ObservedRotationTracksPreview(ProposalPreview):
    mode: str = "CREATE"
    group_id: str = ""
    binding_id: str = ""
    evidence_artifact_id: str = ""
    property_name: str = "rotation_degrees"
    baseline_rotation_degrees: int | float = 0
    track_id: str = ""
    keyframes: tuple[RotationKeyframePreview, ...] = ()


class ObservedRotationTracksAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise ObservedRotationTracksError("Rotation authoring scope must be document")
        if set(request.options) != {"motion_target_binding_id", "ticks_per_second"}:
            raise ObservedRotationTracksError("Explicit binding and timebase are required")
        binding_id = request.options["motion_target_binding_id"]
        ticks_per_second = request.options["ticks_per_second"]
        if not isinstance(binding_id, str) or not isinstance(ticks_per_second, int) or isinstance(ticks_per_second, bool) or ticks_per_second <= 0:
            raise ObservedRotationTracksError("Invalid binding or ticks_per_second")
        if len(request.artifact_ids) != 1:
            raise ObservedRotationTracksError("Rotation authoring requires one similarity Artifact")
        bindings = [b for b in request.document.get("motion_target_bindings", []) if b.get("id") == binding_id]
        if len(bindings) != 1 or bindings[0].get("policy_identity") != MOTION_TARGET_BINDING_POLICY_IDENTITY or bindings[0].get("target", {}).get("kind") != "group":
            raise ObservedRotationTracksError("Explicit Group Motion Target Binding is required")
        binding = copy.deepcopy(bindings[0])
        group_id = binding["target"]["group_id"]
        groups = [g for g in request.document.get("groups", []) if g.get("id") == group_id]
        if len(groups) != 1 or not isinstance(groups[0].get("transform"), dict):
            raise ObservedRotationTracksError("Bound rotation Group is missing or invalid")
        group = copy.deepcopy(groups[0])
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        payload = _read_evidence(snapshot)
        if payload["temporal_identity_id"] != binding["temporal_identity_id"]:
            raise ObservedRotationTracksError("Similarity evidence identity does not match binding")
        baseline = group["transform"].get("rotation_degrees")
        samples = _absolute_samples(payload["intervals"], baseline)
        track_id, keyframes = _track_definition(binding_id, snapshot.artifact_id, group_id, samples, ticks_per_second)
        authored = _document_track(group_id, track_id, keyframes, binding_id, snapshot.artifact_id, request.base_revision_id)
        animation_before = copy.deepcopy(request.document["animation"])
        if _rotation_tracks(animation_before, group_id):
            raise ObservedRotationTracksError("Existing Group rotation Track requires explicit re-authoring")
        expected_animation = _expected_animation(animation_before, authored, ticks_per_second)
        changes: list[Any] = [CreateGroupTransformTrackChange(track_id, group_id, "rotation_degrees", ticks_per_second, "linear")]
        changes.extend(AddKeyframeChange(track_id, kid, tick, value) for kid, tick, value, _ in keyframes)
        changes.append(VerifyObservedRotationTrackSourceChange(reference, binding, group, request.base_revision_id, ticks_per_second, authored, animation_before, expected_animation))
        generator = GeneratorProvenance(self.adapter_id, self.adapter_version, "svm-verified-observed-rotation-authoring", POLICY_IDENTITY, {"evidence_artifact_id": snapshot.artifact_id, "motion_target_binding_id": binding_id, "group_id": group_id, "ticks_per_second": ticks_per_second})
        digest = hashlib.sha256(canonical_bytes({"base": request.base_revision_id, "generator": asdict(generator), "track": authored})).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:observed-rotation-track:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(f"transaction:observed-rotation-track:{digest}", tuple(changes), "Author verified observed rotation Track"),
            preview=ObservedRotationTracksPreview(mode="CREATE", group_id=group_id, binding_id=binding_id, evidence_artifact_id=snapshot.artifact_id, baseline_rotation_degrees=baseline, track_id=track_id, keyframes=tuple(RotationKeyframePreview(t, v, d) for _, t, v, d in keyframes)),
            required_artifact_ids=(snapshot.artifact_id,),
            notes="CREATE one linear Group rotation Track from verified observed deltas",
        )


def verify_observed_rotation_track_source(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    snapshot = resolved.get(change.evidence_reference.get("id"))
    if snapshot is None:
        raise ValueError("Observed similarity evidence Artifact was not resolved")
    payload = _read_evidence(snapshot)
    if payload["temporal_identity_id"] != change.binding.get("temporal_identity_id"):
        raise ValueError("Similarity evidence identity does not match Motion Target Binding")
    if change.binding.get("target") != {"kind": "group", "group_id": change.group.get("id")}:
        raise ValueError("Motion Target Binding does not match captured Group")
    samples = _absolute_samples(payload["intervals"], change.group.get("transform", {}).get("rotation_degrees"))
    track_id, keyframes = _track_definition(change.binding["id"], snapshot.artifact_id, change.group["id"], samples, change.ticks_per_second)
    expected = _document_track(change.group["id"], track_id, keyframes, change.binding["id"], snapshot.artifact_id, change.source_revision_id)
    if change.authored_track != expected:
        raise ValueError("Observed rotation Track definition does not match evidence")
    if change.expected_animation != _expected_animation(change.animation_before, expected, change.ticks_per_second):
        raise ValueError("Observed rotation animation result is inconsistent")


def _read_evidence(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservedRotationTracksError("Similarity evidence is invalid JSON") from exc
    if snapshot.kind != ArtifactKind.DERIVED or snapshot.media_type != SIMILARITY_MEDIA_TYPE or snapshot.provenance.get("adapter_id") != "adapter:observed-similarity-motion" or snapshot.provenance.get("policy_identity") != SIMILARITY_POLICY_IDENTITY or not isinstance(payload, dict) or canonical_bytes(payload) != snapshot.content or payload.get("schema_version") != "svm-observed-similarity-motion-0.1" or payload.get("identity") != "svm-observed-similarity-motion@0.1" or payload.get("policy_identity") != SIMILARITY_POLICY_IDENTITY or not isinstance(payload.get("temporal_identity_id"), str) or not isinstance(payload.get("intervals"), list) or not payload["intervals"]:
        raise ObservedRotationTracksError("Rotation authoring requires canonical S4 evidence")
    return payload


def _absolute_samples(intervals: list[Any], baseline: Any) -> tuple[tuple[int, int | float, int | float | None], ...]:
    if not _finite_number(baseline):
        raise ObservedRotationTracksError("Bound Group rotation baseline is invalid")
    value: int | float = baseline
    samples: list[tuple[int, int | float, int | float | None]] = []
    previous_target: int | None = None
    for index, interval in enumerate(intervals):
        source_tick, target_tick = interval.get("source_tick"), interval.get("target_tick")
        rotation = interval.get("rotation_degrees")
        delta = rotation.get("value") if isinstance(rotation, dict) else None
        if not isinstance(source_tick, int) or isinstance(source_tick, bool) or not isinstance(target_tick, int) or isinstance(target_tick, bool) or source_tick < 0 or target_tick <= source_tick or (previous_target is not None and source_tick != previous_target) or not isinstance(rotation, dict) or rotation.get("status") != "SUPPORTED" or not _finite_number(delta):
            raise ObservedRotationTracksError("Observed rotation intervals must form one supported ordered contiguous chain")
        if index == 0:
            samples.append((source_tick, value, None))
        value = value + delta
        if not _finite_number(value):
            raise ObservedRotationTracksError("Observed rotation accumulation is invalid")
        samples.append((target_tick, value, delta))
        previous_target = target_tick
    return tuple(samples)


def _track_definition(binding_id, artifact_id, group_id, samples, ticks_per_second):
    subject = {"policy_identity": POLICY_IDENTITY, "binding_id": binding_id, "evidence_artifact_id": artifact_id, "group_id": group_id, "property": "rotation_degrees", "ticks_per_second": ticks_per_second}
    track_id = "track:observed-rotation:" + hashlib.sha256(canonical_bytes(subject)).hexdigest()
    keyframes = tuple(("keyframe:observed-rotation:" + hashlib.sha256(canonical_bytes({"track_id": track_id, "tick": tick})).hexdigest(), tick, value, delta) for tick, value, delta in samples)
    return track_id, keyframes


def _document_track(group_id, track_id, keyframes, binding_id, evidence_artifact_id, source_revision_id):
    return {"id": track_id, "target": {"group": group_id, "property": "rotation_degrees"}, "value_type": "number", "interpolation": "linear", "keyframes": [{"id": kid, "tick": tick, "value": value} for kid, tick, value, _ in keyframes], "provenance": {"type": "ObservedRotationTrack", "authoring_identity": POLICY_IDENTITY, "motion_target_binding_id": binding_id, "evidence_artifact_id": evidence_artifact_id, "source_revision_id": source_revision_id}}


def _expected_animation(animation_before, authored_track, ticks_per_second):
    animation = copy.deepcopy(animation_before)
    if animation.get("timebase") is not None and animation["timebase"].get("ticks_per_second") != ticks_per_second:
        raise ObservedRotationTracksError("ticks_per_second conflicts with the existing Document timebase")
    if animation.get("semantics_version") not in {"svm-motion@0.4", "svm-motion@0.5", "svm-motion@0.6"}:
        animation["semantics_version"] = "svm-motion@0.3"
    animation["timebase"] = {"ticks_per_second": ticks_per_second}
    animation["content"].append(copy.deepcopy(authored_track))
    return animation


def _rotation_tracks(animation, group_id):
    return tuple(copy.deepcopy(track) for track in animation.get("content", []) if track.get("target") == {"group": group_id, "property": "rotation_degrees"})


def _accepted_reference(document, artifact_id):
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ObservedRotationTracksError("Similarity evidence must already be accepted")
    return copy.deepcopy(matches[0])


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
