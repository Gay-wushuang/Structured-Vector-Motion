from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, GeneratorProvenance, Proposal
from ..revisions import (
    MOTION_TARGET_BINDING_POLICY_IDENTITY,
    AddKeyframeChange,
    CreateGroupTransformTrackChange,
    Transaction,
    VerifyGeometryTranslationTrackSourceChange,
)
from ..scene import _group_transform_matrix
from .camera_compensation import (
    CAMERA_MEDIA_TYPE,
    _by_ticks,
    _compensated_payloads,
    _compose,
    _decompose,
    _finite,
    _interval_matrix,
    _inverse,
    _one_media,
    _one_standard_similarity,
    _one_standard_translation,
    _round,
)
from .camera_compensation import (
    SIMILARITY_MEDIA_TYPE as COMPENSATED_MEDIA_TYPE,
)
from .observed_camera_tracks import recover_camera_samples
from .observed_rotation_tracks import _read_evidence
from .observed_translation_tracks import (
    ObservedTranslationTracksError,
    ObservedTranslationTracksPreview,
    TranslationKeyframePreview,
    TranslationTrackPreview,
    _accepted_reference,
    _document_tracks,
    _expected_animation,
    _track_definitions,
    _translation_tracks,
)

POLICY_IDENTITY = "svm-geometry-correct-translation-authoring@0.1"


class GeometryTranslationTracksAdapter:
    """Explicit CREATE of Group translation from accepted geometric similarities."""

    adapter_id = "adapter:geometry-translation-tracks"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if (
            request.scope not in {(), ("document",)}
            or set(request.options) != {"motion_target_binding_id", "ticks_per_second"}
            or len(request.artifact_ids) != 1
        ):
            raise ObservedTranslationTracksError(
                "Geometry translation requires one similarity Artifact "
                "and explicit binding/timebase"
            )
        ticks = request.options["ticks_per_second"]
        if type(ticks) is not int or ticks <= 0:
            raise ObservedTranslationTracksError("ticks_per_second must be a positive integer")
        bindings = [
            item
            for item in request.document.get("motion_target_bindings", [])
            if item["id"] == request.options["motion_target_binding_id"]
        ]
        if (
            len(bindings) != 1
            or bindings[0]["policy_identity"] != MOTION_TARGET_BINDING_POLICY_IDENTITY
        ):
            raise ObservedTranslationTracksError("Explicit Motion Target Binding is required")
        binding = copy.deepcopy(bindings[0])
        if binding["target"].get("kind") != "group":
            raise ObservedTranslationTracksError("Geometry translation requires a Group binding")
        groups = [
            g
            for g in request.document.get("groups", [])
            if g["id"] == binding["target"]["group_id"]
        ]
        if len(groups) != 1 or not isinstance(groups[0].get("transform"), dict):
            raise ObservedTranslationTracksError("Bound Group transform is missing")
        group = copy.deepcopy(groups[0])
        if _translation_tracks(request.document["animation"], group["id"]):
            raise ObservedTranslationTracksError("Geometry translation is CREATE-only")
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        payload = _read_evidence(snapshot)
        source_ids = (
            payload["source_artifact_ids"] if snapshot.media_type == COMPENSATED_MEDIA_TYPE else []
        )
        source_references = tuple(
            _accepted_reference(request.document, item) for item in source_ids
        )
        resolved = {
            item.artifact_id: item
            for item in (snapshot, *(artifacts.resolve_reference(ref) for ref in source_references))
        }
        tracks = _authored_tracks(
            snapshot, resolved, binding, group, ticks, request.base_revision_id
        )
        animation_before = copy.deepcopy(request.document["animation"])
        expected_animation = _expected_animation(animation_before, tracks, ticks)
        changes: list[Any] = []
        previews = []
        for track in tracks:
            changes.append(
                CreateGroupTransformTrackChange(
                    track["id"], group["id"], track["target"]["property"], ticks, "linear"
                )
            )
            changes.extend(
                AddKeyframeChange(track["id"], key["id"], key["tick"], key["value"])
                for key in track["keyframes"]
            )
            previews.append(
                TranslationTrackPreview(
                    track["id"],
                    track["target"]["property"],
                    tuple(
                        TranslationKeyframePreview(k["tick"], k["value"])
                        for k in track["keyframes"]
                    ),
                )
            )
        changes.append(
            VerifyGeometryTranslationTrackSourceChange(
                reference,
                binding,
                group,
                request.base_revision_id,
                ticks,
                tracks,
                animation_before,
                expected_animation,
                source_references,
            )
        )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "svm-geometry-correct-translation-authoring",
            POLICY_IDENTITY,
            copy.deepcopy(request.options),
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {"base": request.base_revision_id, "generator": asdict(generator), "tracks": tracks}
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:geometry-translation:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:geometry-translation:{digest}",
                tuple(changes),
                "Author geometry-correct Group translation",
            ),
            preview=ObservedTranslationTracksPreview(
                group_id=group["id"],
                binding_id=binding["id"],
                evidence_artifact_id=snapshot.artifact_id,
                tracks=tuple(previews),
            ),
            required_artifact_ids=(snapshot.artifact_id, *source_ids),
            notes="CREATE geometry-correct translation only; rotation and scale remain explicit",
        )


def verify_geometry_translation_source(
    change: VerifyGeometryTranslationTrackSourceChange,
    resolved: dict[str, ArtifactSnapshot],
) -> None:
    snapshot = resolved[change.evidence_reference["id"]]
    if _translation_tracks(change.animation_before, change.group["id"]):
        raise ValueError("Geometry translation is CREATE-only")
    tracks = _authored_tracks(
        snapshot,
        resolved,
        change.binding,
        change.group,
        change.ticks_per_second,
        change.source_revision_id,
    )
    if tracks != change.authored_tracks or change.expected_animation != _expected_animation(
        change.animation_before, tracks, change.ticks_per_second
    ):
        raise ValueError("Geometry translation result does not match verified similarity")


def _authored_tracks(
    snapshot: ArtifactSnapshot,
    resolved: dict[str, ArtifactSnapshot],
    binding: dict[str, Any],
    group: dict[str, Any],
    ticks: int,
    revision: str,
) -> tuple[dict[str, Any], ...]:
    payload = _read_evidence(snapshot)
    if payload["temporal_identity_id"] != binding["temporal_identity_id"] or binding["target"] != {
        "kind": "group",
        "group_id": group["id"],
    }:
        raise ValueError("Similarity identity does not match explicit Group binding")
    intervals = payload["intervals"]
    camera_by_ticks = None
    if snapshot.media_type == COMPENSATED_MEDIA_TYPE:
        source_ids = payload["source_artifact_ids"]
        if set(resolved) != {snapshot.artifact_id, *source_ids} or len(source_ids) != 3:
            raise ValueError("Compensated similarity requires its exact accepted source Artifacts")
        sources = tuple(resolved[item] for item in source_ids)
        camera = _one_media(sources, CAMERA_MEDIA_TYPE)
        translation = _one_standard_translation(sources)
        similarity = _one_standard_similarity(sources)
        if (
            translation["temporal_identity_id"] != payload["temporal_identity_id"]
            or similarity["temporal_identity_id"] != payload["temporal_identity_id"]
        ):
            raise ValueError("Compensated similarity source identity mismatch")
        # Verify the accepted compensation result; never treat its bounds delta as matrix b.
        _, expected = _compensated_payloads(
            payload["source_revision_id"],
            payload["temporal_identity_id"],
            camera,
            translation,
            similarity,
            tuple(source_ids),
        )
        if canonical_bytes(expected) != snapshot.content:
            raise ValueError("Compensated similarity does not match its source Artifacts")
        recover_camera_samples(camera["intervals"])
        camera_by_ticks = _by_ticks(camera["intervals"])
        intervals = similarity["intervals"]
    elif set(resolved) != {snapshot.artifact_id}:
        raise ValueError("Unexpected geometry translation source Artifacts")
    samples = _geometry_samples(intervals, group["transform"], camera_by_ticks)
    return _document_tracks(
        group["id"],
        _track_definitions(
            binding["id"],
            snapshot.artifact_id,
            group["id"],
            samples,
            ticks,
            POLICY_IDENTITY,
            group["transform"],
        ),
        binding["id"],
        snapshot.artifact_id,
        revision,
        POLICY_IDENTITY,
    )


def _geometry_samples(
    intervals: list[dict[str, Any]],
    transform: dict[str, Any],
    camera_by_ticks: dict[tuple[int, int], dict] | None,
) -> tuple[tuple[int, int | float, int | float], ...]:
    current = tuple(_group_transform_matrix(transform))
    ox, oy = transform["origin"]
    samples = []
    previous = None
    for interval in intervals:
        source, target = interval["source_tick"], interval["target_tick"]
        if (
            type(source) is not int
            or type(target) is not int
            or source < 0
            or target <= source
            or (previous is not None and source != previous)
        ):
            raise ValueError("Geometry translation requires one ordered contiguous chain")
        origin, delta = interval.get("origin"), interval.get("translation")
        if (
            not isinstance(origin, list)
            or len(origin) != 2
            or not isinstance(delta, dict)
            or set(delta) != {"dx", "dy"}
            or any(not _finite(v) for v in (*origin, *delta.values()))
        ):
            raise ValueError("Similarity lacks finite geometric origin and displacement")
        relative = _interval_matrix(interval, "target")
        if camera_by_ticks is not None:
            camera = camera_by_ticks[(source, target)]
            relative = _compose(
                _compose(_inverse(camera["target_view_transform"]), relative),
                camera["source_view_transform"],
            )
        if previous is None:
            samples.append((source, *transform["translate"]))
        current = _compose(relative, current)
        if any(not _finite(v) for v in current):
            raise ValueError("Absolute Group similarity is not finite")
        _decompose(current)
        a, b, c, d, e, f = current
        samples.append((target, _round(e - ox + a * ox + c * oy), _round(f - oy + b * ox + d * oy)))
        previous = target
    return tuple(samples)
