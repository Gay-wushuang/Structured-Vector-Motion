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
    VerifyObservedTranslationTrackSourceChange,
)
from .observed_translation_motion import (
    MEDIA_TYPE as OBSERVED_MOTION_MEDIA_TYPE,
)
from .observed_translation_motion import (
    POLICY_IDENTITY as OBSERVED_MOTION_POLICY_IDENTITY,
)

POLICY_IDENTITY = "svm-verified-observed-translation-authoring@0.1"
ADAPTER_ID = "adapter:observed-translation-tracks"


class ObservedTranslationTracksError(ValueError):
    pass


@dataclass(frozen=True)
class TranslationKeyframePreview:
    tick: int
    value: int | float


@dataclass(frozen=True)
class TranslationTrackPreview:
    track_id: str
    property_name: str
    keyframes: tuple[TranslationKeyframePreview, ...]


@dataclass(frozen=True)
class ObservedTranslationTracksPreview(ProposalPreview):
    group_id: str = ""
    binding_id: str = ""
    evidence_artifact_id: str = ""
    tracks: tuple[TranslationTrackPreview, ...] = ()


class ObservedTranslationTracksAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise ObservedTranslationTracksError("Translation authoring scope must be document")
        if set(request.options) != {"motion_target_binding_id", "ticks_per_second"}:
            raise ObservedTranslationTracksError(
                "Explicit motion_target_binding_id and ticks_per_second are required"
            )
        binding_id = request.options["motion_target_binding_id"]
        ticks_per_second = request.options["ticks_per_second"]
        if not isinstance(binding_id, str):
            raise ObservedTranslationTracksError("Motion target binding ID must be a string")
        if (
            not isinstance(ticks_per_second, int)
            or isinstance(ticks_per_second, bool)
            or ticks_per_second <= 0
        ):
            raise ObservedTranslationTracksError("ticks_per_second must be a positive integer")
        if len(request.artifact_ids) != 1:
            raise ObservedTranslationTracksError(
                "Translation authoring requires one observed-motion Artifact"
            )
        bindings = [
            item
            for item in request.document.get("motion_target_bindings", [])
            if item.get("id") == binding_id
        ]
        if len(bindings) != 1:
            raise ObservedTranslationTracksError(
                "Explicit Motion Target Binding is required for translation authoring"
            )
        binding = copy.deepcopy(bindings[0])
        if (
            binding.get("policy_identity") != MOTION_TARGET_BINDING_POLICY_IDENTITY
            or binding.get("target", {}).get("kind") != "group"
        ):
            raise ObservedTranslationTracksError("Motion Target Binding is unsupported")
        group_id = binding["target"]["group_id"]
        groups = [item for item in request.document.get("groups", []) if item.get("id") == group_id]
        if len(groups) != 1 or not isinstance(groups[0].get("transform"), dict):
            raise ObservedTranslationTracksError("Bound translation Group is missing or invalid")
        group = copy.deepcopy(groups[0])
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        payload = _read_evidence(snapshot)
        if payload["temporal_identity_id"] != binding["temporal_identity_id"]:
            raise ObservedTranslationTracksError(
                "Observed motion identity does not match Motion Target Binding"
            )
        samples = _absolute_samples(payload["intervals"], group["transform"]["translate"])
        tracks = _track_definitions(
            binding_id, snapshot.artifact_id, group_id, samples, ticks_per_second
        )
        authored_tracks = _document_tracks(group_id, tracks)
        animation_before = copy.deepcopy(request.document["animation"])
        expected_animation = _expected_animation(
            animation_before, authored_tracks, ticks_per_second
        )
        guard = VerifyObservedTranslationTrackSourceChange(
            reference,
            binding,
            group,
            request.base_revision_id,
            ticks_per_second,
            authored_tracks,
            animation_before,
            expected_animation,
        )
        changes: list[Any] = []
        previews: list[TranslationTrackPreview] = []
        for property_name, track_id, keyframes in tracks:
            changes.append(
                CreateGroupTransformTrackChange(
                    track_id, group_id, property_name, ticks_per_second, "linear"
                )
            )
            changes.extend(
                AddKeyframeChange(track_id, keyframe_id, tick, value)
                for keyframe_id, tick, value in keyframes
            )
            previews.append(
                TranslationTrackPreview(
                    track_id,
                    property_name,
                    tuple(TranslationKeyframePreview(tick, value) for _, tick, value in keyframes),
                )
            )
        changes.append(guard)
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "svm-verified-observed-translation-authoring",
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
                    "tracks": tracks,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:observed-translation-tracks:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:observed-translation-tracks:{digest}",
                tuple(changes),
                "Author verified observed translation Tracks",
            ),
            preview=ObservedTranslationTracksPreview(
                group_id=group_id,
                binding_id=binding_id,
                evidence_artifact_id=snapshot.artifact_id,
                tracks=tuple(previews),
            ),
            required_artifact_ids=(snapshot.artifact_id,),
            notes="Creates linear Group translate.x/y Tracks only after explicit acceptance",
        )


def verify_observed_translation_track_source(
    change: Any, resolved: dict[str, ArtifactSnapshot]
) -> None:
    artifact_id = change.evidence_reference.get("id")
    snapshot = resolved.get(artifact_id)
    if snapshot is None:
        raise ValueError("Observed translation evidence Artifact was not resolved")
    payload = _read_evidence(snapshot)
    if payload["temporal_identity_id"] != change.binding.get("temporal_identity_id"):
        raise ValueError("Observed motion identity does not match Motion Target Binding")
    if change.binding.get("target") != {"kind": "group", "group_id": change.group.get("id")}:
        raise ValueError("Motion Target Binding does not match captured Group")
    samples = _absolute_samples(
        payload["intervals"], change.group.get("transform", {}).get("translate")
    )
    expected = _document_tracks(
        change.group["id"],
        _track_definitions(
            change.binding["id"],
            snapshot.artifact_id,
            change.group["id"],
            samples,
            change.ticks_per_second,
        ),
    )
    if change.authored_tracks != expected:
        raise ValueError("Observed translation Track definitions do not match evidence")
    if change.expected_animation != _expected_animation(
        change.animation_before, expected, change.ticks_per_second
    ):
        raise ValueError("Observed translation animation result is inconsistent")


def _read_evidence(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservedTranslationTracksError("Observed motion evidence is invalid JSON") from exc
    if (
        snapshot.kind != ArtifactKind.DERIVED
        or snapshot.media_type != OBSERVED_MOTION_MEDIA_TYPE
        or snapshot.provenance.get("adapter_id") != "adapter:observed-translation-motion"
        or snapshot.provenance.get("policy_identity") != OBSERVED_MOTION_POLICY_IDENTITY
        or not isinstance(payload, dict)
        or canonical_bytes(payload) != snapshot.content
        or payload.get("schema_version") != "svm-observed-translation-motion-0.1"
        or payload.get("identity") != "svm-observed-translation-motion@0.1"
        or payload.get("policy_identity") != OBSERVED_MOTION_POLICY_IDENTITY
        or not isinstance(payload.get("temporal_identity_id"), str)
        or not isinstance(payload.get("intervals"), list)
        or not payload["intervals"]
    ):
        raise ObservedTranslationTracksError("Translation authoring requires canonical S0 evidence")
    return payload


def _absolute_samples(
    intervals: list[Any], baseline: Any
) -> tuple[tuple[int, int | float, int | float], ...]:
    if (
        not isinstance(baseline, list)
        or len(baseline) != 2
        or any(not _finite_number(value) for value in baseline)
    ):
        raise ObservedTranslationTracksError("Bound Group translation baseline is invalid")
    samples: list[tuple[int, int | float, int | float]] = []
    x, y = baseline
    previous_target: int | None = None
    for index, interval in enumerate(intervals):
        if not isinstance(interval, dict):
            raise ObservedTranslationTracksError("Observed motion interval is invalid")
        source_tick = interval.get("source_tick")
        target_tick = interval.get("target_tick")
        translation = interval.get("translation")
        if (
            not isinstance(source_tick, int)
            or isinstance(source_tick, bool)
            or not isinstance(target_tick, int)
            or isinstance(target_tick, bool)
            or source_tick < 0
            or target_tick <= source_tick
            or not isinstance(translation, dict)
            or set(translation) != {"dx", "dy"}
            or any(not _finite_number(translation[key]) for key in ("dx", "dy"))
            or (previous_target is not None and source_tick != previous_target)
        ):
            raise ObservedTranslationTracksError(
                "Observed translation intervals must form one ordered contiguous chain"
            )
        if index == 0:
            samples.append((source_tick, x, y))
        x += translation["dx"]
        y += translation["dy"]
        samples.append((target_tick, x, y))
        previous_target = target_tick
    return tuple(samples)


def _track_definitions(
    binding_id: str,
    artifact_id: str,
    group_id: str,
    samples: tuple[tuple[int, int | float, int | float], ...],
    ticks_per_second: int,
) -> tuple[tuple[str, str, tuple[tuple[str, int, int | float], ...]], ...]:
    result = []
    for property_name, value_index in (("translate.x", 1), ("translate.y", 2)):
        subject = {
            "policy_identity": POLICY_IDENTITY,
            "binding_id": binding_id,
            "evidence_artifact_id": artifact_id,
            "group_id": group_id,
            "property": property_name,
            "ticks_per_second": ticks_per_second,
        }
        track_id = (
            "track:observed-translation:" + hashlib.sha256(canonical_bytes(subject)).hexdigest()
        )
        keyframes = tuple(
            (
                "keyframe:observed-translation:"
                + hashlib.sha256(
                    canonical_bytes({"track_id": track_id, "tick": sample[0]})
                ).hexdigest(),
                sample[0],
                sample[value_index],
            )
            for sample in samples
        )
        result.append((property_name, track_id, keyframes))
    return tuple(result)


def _document_tracks(
    group_id: str,
    definitions: tuple[tuple[str, str, tuple[tuple[str, int, int | float], ...]], ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "id": track_id,
            "target": {"group": group_id, "property": property_name},
            "value_type": "number",
            "interpolation": "linear",
            "keyframes": [
                {"id": keyframe_id, "tick": tick, "value": value}
                for keyframe_id, tick, value in keyframes
            ],
        }
        for property_name, track_id, keyframes in definitions
    )


def _expected_animation(
    animation_before: dict[str, Any],
    authored_tracks: tuple[dict[str, Any], ...],
    ticks_per_second: int,
) -> dict[str, Any]:
    animation = copy.deepcopy(animation_before)
    current_timebase = animation.get("timebase")
    if (
        current_timebase is not None
        and current_timebase.get("ticks_per_second") != ticks_per_second
    ):
        raise ObservedTranslationTracksError(
            "ticks_per_second conflicts with the existing Document timebase"
        )
    if animation.get("semantics_version") not in {
        "svm-motion@0.4",
        "svm-motion@0.5",
        "svm-motion@0.6",
    }:
        animation["semantics_version"] = "svm-motion@0.3"
    animation["timebase"] = {"ticks_per_second": ticks_per_second}
    animation["content"].extend(copy.deepcopy(authored_tracks))
    return animation


def _accepted_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ObservedTranslationTracksError("Observed motion evidence must already be accepted")
    return copy.deepcopy(matches[0])


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
