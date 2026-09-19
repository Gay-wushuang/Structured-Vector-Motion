from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, cast

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, GeneratorProvenance, Proposal, ProposalPreview
from ..revisions import (
    MOTION_TARGET_BINDING_POLICY_IDENTITY,
    AddKeyframeChange,
    CreateGroupTransformTrackChange,
    Transaction,
    VerifyObservedScaleTrackSourceChange,
)
from .observed_similarity_motion import MEDIA_TYPE as SIMILARITY_MEDIA_TYPE
from .observed_similarity_motion import POLICY_IDENTITY as SIMILARITY_POLICY_IDENTITY

POLICY_IDENTITY = "svm-verified-observed-scale-authoring@0.1"
ADAPTER_ID = "adapter:observed-scale-tracks"


class ObservedScaleTracksError(ValueError):
    pass


@dataclass(frozen=True)
class ScaleKeyframePreview:
    tick: int
    value: int | float
    source_ratio: int | float | None = None


@dataclass(frozen=True)
class ObservedScaleTracksPreview(ProposalPreview):
    mode: str = "CREATE"
    group_id: str = ""
    binding_id: str = ""
    evidence_artifact_id: str = ""
    property_name: str = "scale"
    baseline_scale: int | float = 1
    track_id: str = ""
    keyframes: tuple[ScaleKeyframePreview, ...] = ()


class ObservedScaleTracksAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise ObservedScaleTracksError("Scale authoring scope must be document")
        if set(request.options) != {"motion_target_binding_id", "ticks_per_second"}:
            raise ObservedScaleTracksError(
                "Explicit motion_target_binding_id and ticks_per_second are required"
            )
        binding_id = request.options["motion_target_binding_id"]
        ticks_per_second = request.options["ticks_per_second"]
        if not isinstance(binding_id, str):
            raise ObservedScaleTracksError("Motion target binding ID must be a string")
        if (
            not isinstance(ticks_per_second, int)
            or isinstance(ticks_per_second, bool)
            or ticks_per_second <= 0
        ):
            raise ObservedScaleTracksError("ticks_per_second must be a positive integer")
        if len(request.artifact_ids) != 1:
            raise ObservedScaleTracksError("Scale authoring requires one similarity Artifact")
        bindings = [
            b
            for b in request.document.get("motion_target_bindings", [])
            if b.get("id") == binding_id
        ]
        if len(bindings) != 1:
            raise ObservedScaleTracksError(
                "Explicit Motion Target Binding is required for scale authoring"
            )
        binding = copy.deepcopy(bindings[0])
        if (
            binding.get("policy_identity") != MOTION_TARGET_BINDING_POLICY_IDENTITY
            or binding.get("target", {}).get("kind") != "group"
        ):
            raise ObservedScaleTracksError("Motion Target Binding is unsupported")
        group_id = binding["target"]["group_id"]
        groups = [g for g in request.document.get("groups", []) if g.get("id") == group_id]
        if len(groups) != 1 or not isinstance(groups[0].get("transform"), dict):
            raise ObservedScaleTracksError("Bound scale Group is missing or invalid")
        group = copy.deepcopy(groups[0])
        if any(
            t.get("target") == {"group": group_id, "property": "scale"}
            for t in request.document["animation"]["content"]
        ):
            raise ObservedScaleTracksError(
                "Existing Group scale Track requires explicit re-authoring"
            )
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        payload = _read_evidence(snapshot)
        if payload["temporal_identity_id"] != binding["temporal_identity_id"]:
            raise ObservedScaleTracksError(
                "Similarity evidence identity does not match Motion Target Binding"
            )
        baseline = group["transform"].get("scale")
        samples = _absolute_samples(payload["intervals"], baseline)
        track_id, keyframes = _track_definition(
            binding_id, snapshot.artifact_id, group_id, samples, ticks_per_second
        )
        authored_track = _document_track(
            group_id,
            track_id,
            keyframes,
            binding_id,
            snapshot.artifact_id,
            request.base_revision_id,
        )
        animation_before = copy.deepcopy(request.document["animation"])
        expected_animation = _expected_animation(animation_before, authored_track, ticks_per_second)
        changes: list[Any] = [
            CreateGroupTransformTrackChange(track_id, group_id, "scale", ticks_per_second, "linear")
        ]
        changes.extend(
            AddKeyframeChange(track_id, kid, tick, value) for kid, tick, value, _ in keyframes
        )
        changes.append(
            VerifyObservedScaleTrackSourceChange(
                reference,
                binding,
                group,
                request.base_revision_id,
                ticks_per_second,
                authored_track,
                animation_before,
                expected_animation,
            )
        )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "svm-verified-observed-scale-authoring",
            POLICY_IDENTITY,
            {
                "evidence_artifact_id": snapshot.artifact_id,
                "motion_target_binding_id": binding_id,
                "group_id": group_id,
                "ticks_per_second": ticks_per_second,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "track": authored_track,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:observed-scale-track:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:observed-scale-track:{digest}",
                tuple(changes),
                "Author verified observed scale Track",
            ),
            preview=ObservedScaleTracksPreview(
                group_id=group_id,
                binding_id=binding_id,
                evidence_artifact_id=snapshot.artifact_id,
                baseline_scale=baseline,
                track_id=track_id,
                keyframes=tuple(
                    ScaleKeyframePreview(tick, value, ratio) for _, tick, value, ratio in keyframes
                ),
            ),
            required_artifact_ids=(snapshot.artifact_id,),
            notes="Create one linear Group scale Track only after explicit acceptance",
        )


def verify_observed_scale_track_source(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    artifact_id = change.evidence_reference.get("id")
    snapshot = resolved.get(artifact_id)
    if snapshot is None:
        raise ValueError("Observed similarity evidence Artifact was not resolved")
    payload = _read_evidence(snapshot)
    if payload["temporal_identity_id"] != change.binding.get("temporal_identity_id"):
        raise ValueError("Similarity evidence identity does not match Motion Target Binding")
    if change.binding.get("target") != {"kind": "group", "group_id": change.group.get("id")}:
        raise ValueError("Motion Target Binding does not match captured Group")
    samples = _absolute_samples(
        payload["intervals"], change.group.get("transform", {}).get("scale")
    )
    track_id, keyframes = _track_definition(
        change.binding["id"],
        snapshot.artifact_id,
        change.group["id"],
        samples,
        change.ticks_per_second,
    )
    expected = _document_track(
        change.group["id"],
        track_id,
        keyframes,
        change.binding["id"],
        snapshot.artifact_id,
        change.source_revision_id,
    )
    if change.authored_track != expected:
        raise ValueError("Observed scale Track definition does not match evidence")
    if change.expected_animation != _expected_animation(
        change.animation_before, expected, change.ticks_per_second
    ):
        raise ValueError("Observed scale animation result is inconsistent")


def _read_evidence(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservedScaleTracksError("Similarity evidence is invalid JSON") from exc
    if (
        snapshot.kind != ArtifactKind.DERIVED
        or snapshot.media_type != SIMILARITY_MEDIA_TYPE
        or snapshot.provenance.get("adapter_id") != "adapter:observed-similarity-motion"
        or snapshot.provenance.get("policy_identity") != SIMILARITY_POLICY_IDENTITY
        or not isinstance(payload, dict)
        or canonical_bytes(payload) != snapshot.content
        or payload.get("schema_version") != "svm-observed-similarity-motion-0.1"
        or payload.get("identity") != "svm-observed-similarity-motion@0.1"
        or payload.get("policy_identity") != SIMILARITY_POLICY_IDENTITY
        or not isinstance(payload.get("temporal_identity_id"), str)
        or not isinstance(payload.get("intervals"), list)
        or not payload["intervals"]
    ):
        raise ObservedScaleTracksError("Scale authoring requires canonical S4 evidence")
    return payload


def _absolute_samples(
    intervals: list[Any], baseline: Any
) -> tuple[tuple[int, int | float, int | float | None], ...]:
    if not _positive_number(baseline):
        raise ObservedScaleTracksError("Bound Group scale baseline is invalid")
    samples: list[tuple[int, int | float, int | float | None]] = []
    value: int | float = baseline
    previous_target: int | None = None
    for index, interval in enumerate(intervals):
        source_tick = interval.get("source_tick") if isinstance(interval, dict) else None
        target_tick = interval.get("target_tick") if isinstance(interval, dict) else None
        scale = interval.get("scale") if isinstance(interval, dict) else None
        ratio = scale.get("value") if isinstance(scale, dict) else None
        if (
            not isinstance(source_tick, int)
            or isinstance(source_tick, bool)
            or not isinstance(target_tick, int)
            or isinstance(target_tick, bool)
            or source_tick < 0
            or target_tick <= source_tick
            or not isinstance(scale, dict)
            or scale.get("status") != "SUPPORTED"
            or not _positive_number(ratio)
            or (previous_target is not None and source_tick != previous_target)
        ):
            raise ObservedScaleTracksError(
                "Observed scale intervals must form one supported ordered contiguous chain"
            )
        if index == 0:
            samples.append((source_tick, value, None))
        value = value * cast(int | float, ratio)
        if not _positive_number(value):
            raise ObservedScaleTracksError("Observed scale accumulation is invalid")
        samples.append((target_tick, value, ratio))
        previous_target = target_tick
    return tuple(samples)


def _track_definition(
    binding_id: str,
    artifact_id: str,
    group_id: str,
    samples: tuple[tuple[int, int | float, int | float | None], ...],
    ticks_per_second: int,
):
    subject = {
        "policy_identity": POLICY_IDENTITY,
        "binding_id": binding_id,
        "evidence_artifact_id": artifact_id,
        "group_id": group_id,
        "property": "scale",
        "ticks_per_second": ticks_per_second,
    }
    track_id = "track:observed-scale:" + hashlib.sha256(canonical_bytes(subject)).hexdigest()
    keyframes = tuple(
        (
            "keyframe:observed-scale:"
            + hashlib.sha256(canonical_bytes({"track_id": track_id, "tick": tick})).hexdigest(),
            tick,
            value,
            ratio,
        )
        for tick, value, ratio in samples
    )
    return track_id, keyframes


def _document_track(
    group_id: str,
    track_id: str,
    keyframes: tuple[Any, ...],
    binding_id: str,
    evidence_artifact_id: str,
    source_revision_id: str,
) -> dict[str, Any]:
    return {
        "id": track_id,
        "target": {"group": group_id, "property": "scale"},
        "value_type": "number",
        "interpolation": "linear",
        "keyframes": [
            {"id": kid, "tick": tick, "value": value} for kid, tick, value, _ in keyframes
        ],
        "provenance": {
            "type": "ObservedScaleTrack",
            "authoring_identity": POLICY_IDENTITY,
            "motion_target_binding_id": binding_id,
            "evidence_artifact_id": evidence_artifact_id,
            "source_revision_id": source_revision_id,
        },
    }


def _expected_animation(
    animation_before: dict[str, Any], authored_track: dict[str, Any], ticks_per_second: int
) -> dict[str, Any]:
    animation = copy.deepcopy(animation_before)
    timebase = animation.get("timebase")
    if timebase is not None and timebase.get("ticks_per_second") != ticks_per_second:
        raise ObservedScaleTracksError(
            "ticks_per_second conflicts with the existing Document timebase"
        )
    if animation.get("semantics_version") not in {
        "svm-motion@0.4",
        "svm-motion@0.5",
        "svm-motion@0.6",
    }:
        animation["semantics_version"] = "svm-motion@0.3"
    animation["timebase"] = {"ticks_per_second": ticks_per_second}
    animation["content"].append(copy.deepcopy(authored_track))
    return animation


def _accepted_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ObservedScaleTracksError("Similarity evidence must already be accepted")
    return copy.deepcopy(matches[0])


def _positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )
