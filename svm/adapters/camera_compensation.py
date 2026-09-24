from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import AttachCameraCompensationEvidenceChange, Transaction

CAMERA_MEDIA_TYPE = "application/vnd.svm.observed-camera-similarity+json;version=0.1"
TRANSLATION_MEDIA_TYPE = (
    "application/vnd.svm.camera-compensated-translation-motion+json;version=0.1"
)
SIMILARITY_MEDIA_TYPE = "application/vnd.svm.camera-compensated-similarity-motion+json;version=0.1"
CAMERA_POLICY = "svm-static-anchor-camera-similarity@0.1"
MEASURED_CAMERA_POLICY = "svm-static-anchor-camera-similarity@0.2"
COMPENSATION_POLICY = "svm-camera-similarity-compensation@0.1"


class CameraCompensationError(ValueError):
    pass


@dataclass(frozen=True)
class CameraEvidencePreview(ProposalPreview):
    anchor_entity_id: str = ""
    interval_count: int = 0


@dataclass(frozen=True)
class CompensatedMotionPreview(ProposalPreview):
    temporal_identity_id: str = ""
    interval_count: int = 0


class ObservedCameraSimilarityAdapter:
    adapter_id = "adapter:observed-camera-similarity"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if set(request.options) != {"anchor_entity_id"} or len(request.artifact_ids) != 1:
            raise CameraCompensationError(
                "Explicit anchor_entity_id and one anchor similarity Artifact are required"
            )
        anchor_id = request.options["anchor_entity_id"]
        anchor = _static_anchor(request.document, anchor_id)
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        source = artifacts.resolve_reference(reference)
        similarity = _standard_similarity(source)
        geometry_references = tuple(
            _accepted_reference(request.document, item)
            for item in similarity.get("source_geometry_artifact_ids", [])
        )
        geometry_snapshots = tuple(
            artifacts.resolve_reference(item) for item in geometry_references
        )
        dependencies = camera_geometry_dependencies(similarity, geometry_snapshots)
        source_references = (
            reference,
            *(_accepted_reference(request.document, item) for item in dependencies),
        )
        resolved = {ref["id"]: artifacts.resolve_reference(ref) for ref in source_references}
        _validate_anchor_geometry(geometry_snapshots, anchor_id, similarity, resolved)
        payload = _camera_payload(
            request.base_revision_id, anchor_id, source.artifact_id, similarity
        )
        evidence = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=CAMERA_MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=_camera_provenance(source.artifact_id, payload["policy_identity"]),
        )
        change = AttachCameraCompensationEvidenceChange(
            (evidence.document_reference(),),
            source_references,
            anchor,
            copy.deepcopy(request.document["animation"]),
            request.base_revision_id,
        )
        return _proposal(
            request,
            self,
            "camera-similarity",
            (evidence,),
            change,
            CameraEvidencePreview(
                anchor_entity_id=anchor_id, interval_count=len(payload["intervals"])
            ),
            {"anchor_entity_id": anchor_id, "policy_identity": payload["policy_identity"]},
        )


class CameraCompensatedMotionAdapter:
    adapter_id = "adapter:camera-compensated-motion"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        from .camera_consensus import canonical_anchor_ids, multi_anchor_change, one_camera_evidence

        consensus_mode = "anchor_entity_ids" in request.options
        anchor_key = "anchor_entity_ids" if consensus_mode else "anchor_entity_id"
        if set(request.options) != {anchor_key, "target_temporal_identity_id"}:
            raise CameraCompensationError(
                "Explicit anchor_entity_id and target_temporal_identity_id are required"
            )
        if len(request.artifact_ids) != 3:
            raise CameraCompensationError(
                "Camera compensation requires camera, target translation, "
                "and target similarity evidence"
            )
        anchor_id = request.options.get("anchor_entity_id")
        anchors = (
            tuple(
                _static_anchor(request.document, item)
                for item in canonical_anchor_ids(request.options[anchor_key])
            )
            if consensus_mode
            else ()
        )
        identity_id = request.options["target_temporal_identity_id"]
        anchor = {} if consensus_mode else _static_anchor(request.document, anchor_id)
        references = tuple(
            _accepted_reference(request.document, item) for item in request.artifact_ids
        )
        snapshots = tuple(artifacts.resolve_reference(item) for item in references)
        camera = one_camera_evidence(snapshots)
        translation = _one_standard_translation(snapshots)
        similarity = _one_standard_similarity(snapshots)
        if (
            camera.get("anchor_entity_ids") != [item["id"] for item in anchors]
            if consensus_mode
            else camera.get("anchor_entity_id") != anchor_id
        ):
            raise CameraCompensationError("Camera evidence belongs to another anchor")
        if (
            translation["temporal_identity_id"] != identity_id
            or similarity["temporal_identity_id"] != identity_id
        ):
            raise CameraCompensationError("Target evidence temporal identity is inconsistent")
        translation_payload, similarity_payload = _compensated_payloads(
            request.base_revision_id,
            identity_id,
            camera,
            translation,
            similarity,
            tuple(item.artifact_id for item in snapshots),
        )
        common = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "engine": "svm-camera-similarity-compensation",
            "engine_version": "svm-camera-similarity-compensation@0.1",
            "policy_identity": COMPENSATION_POLICY,
            "source_artifact_ids": sorted(item.artifact_id for item in snapshots),
        }
        outputs = (
            artifacts.import_bytes(
                canonical_bytes(translation_payload),
                media_type=TRANSLATION_MEDIA_TYPE,
                kind=ArtifactKind.DERIVED,
                provenance={**common, "component": "translation"},
            ),
            artifacts.import_bytes(
                canonical_bytes(similarity_payload),
                media_type=SIMILARITY_MEDIA_TYPE,
                kind=ArtifactKind.DERIVED,
                provenance={**common, "component": "similarity"},
            ),
        )
        change = AttachCameraCompensationEvidenceChange(
            tuple(item.document_reference() for item in outputs),
            references,
            anchor,
            copy.deepcopy(request.document["animation"]),
            request.base_revision_id,
        )
        if consensus_mode:
            change = multi_anchor_change(
                request, tuple(item.document_reference() for item in outputs), references, anchors
            )
        return _proposal(
            request,
            self,
            "camera-compensated-motion",
            outputs,
            change,
            CompensatedMotionPreview(
                temporal_identity_id=identity_id,
                interval_count=len(translation_payload["intervals"]),
            ),
            {
                anchor_key: [item["id"] for item in anchors] if consensus_mode else anchor_id,
                "target_temporal_identity_id": identity_id,
                "policy_identity": COMPENSATION_POLICY,
            },
        )


def verify_camera_compensation_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    outputs = [resolved.get(item.get("id")) for item in change.evidence_references]
    sources = [resolved.get(item.get("id")) for item in change.source_references]
    if any(item is None for item in (*outputs, *sources)):
        raise ValueError("Camera compensation Artifact was not resolved")
    output_snapshots = [item for item in outputs if item is not None]
    source_snapshots = tuple(item for item in sources if item is not None)
    if len(output_snapshots) == 1 and output_snapshots[0].media_type == CAMERA_MEDIA_TYPE:
        source = _only(
            [
                item
                for item in source_snapshots
                if item.media_type
                == "application/vnd.svm.observed-similarity-motion+json;version=0.1"
            ]
        )
        similarity = _standard_similarity(source)
        geometry_ids = similarity["source_geometry_artifact_ids"]
        geometry_snapshots = tuple(resolved[item] for item in geometry_ids)
        if {item.artifact_id for item in source_snapshots} != {
            source.artifact_id,
            *camera_geometry_dependencies(similarity, geometry_snapshots),
        }:
            raise ValueError("Camera similarity dependencies must match exact geometry lineage")
        _validate_anchor_geometry(
            geometry_snapshots,
            change.anchor_entity["id"],
            similarity,
            resolved,
        )
        expected = _camera_payload(
            change.source_revision_id,
            change.anchor_entity["id"],
            source.artifact_id,
            similarity,
        )
        if output_snapshots[0].provenance != _camera_provenance(
            source.artifact_id, expected["policy_identity"]
        ) or output_snapshots[0].content != canonical_bytes(expected):
            raise ValueError("Camera similarity evidence does not match static-anchor observations")
        return
    by_media = {item.media_type: item for item in output_snapshots}
    if set(by_media) != {TRANSLATION_MEDIA_TYPE, SIMILARITY_MEDIA_TYPE}:
        raise ValueError("Camera compensation outputs are incomplete")
    from .camera_consensus import one_camera_evidence

    camera = one_camera_evidence(source_snapshots)
    if "anchor_entity_ids" in camera and camera["anchor_entity_ids"] != [
        item["id"] for item in getattr(change, "anchor_entities", ())
    ]:
        raise ValueError("Consensus compensation requires all anchor state checks")
    translation = _one_standard_translation(source_snapshots)
    similarity = _one_standard_similarity(source_snapshots)
    translation_expected, similarity_expected = _compensated_payloads(
        change.source_revision_id,
        translation["temporal_identity_id"],
        camera,
        translation,
        similarity,
        tuple(item.artifact_id for item in source_snapshots),
    )
    for media_type, expected, component in (
        (TRANSLATION_MEDIA_TYPE, translation_expected, "translation"),
        (SIMILARITY_MEDIA_TYPE, similarity_expected, "similarity"),
    ):
        snapshot = by_media[media_type]
        provenance = {
            "adapter_id": "adapter:camera-compensated-motion",
            "adapter_version": "0.1",
            "engine": "svm-camera-similarity-compensation",
            "engine_version": "svm-camera-similarity-compensation@0.1",
            "policy_identity": COMPENSATION_POLICY,
            "source_artifact_ids": sorted(item.artifact_id for item in source_snapshots),
            "component": component,
        }
        if snapshot.provenance != provenance or snapshot.content != canonical_bytes(expected):
            raise ValueError("Compensated motion evidence does not match its verified sources")


def _camera_payload(revision_id: str, anchor_id: str, source_id: str, similarity: dict) -> dict:
    from .observed_similarity_motion import RASTER_POLICY_IDENTITY

    measured = similarity.get("policy_identity") == RASTER_POLICY_IDENTITY
    intervals = []
    current = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for item in similarity["intervals"]:
        relative = _interval_matrix(item, "anchor")
        following = _compose(relative, current)
        content = {
            "source_tick": item["source_tick"],
            "target_tick": item["target_tick"],
            "relative_view_transform": list(relative),
            "source_view_transform": list(current),
            "target_view_transform": list(following),
            "source_similarity_interval_id": item["interval_id"],
        }
        intervals.append({"interval_id": _id("camera-similarity-interval", content), **content})
        current = following
    return {
        "schema_version": "svm-observed-camera-similarity-0.1",
        "identity": "svm-observed-camera-similarity@0.1",
        "policy_identity": MEASURED_CAMERA_POLICY if measured else CAMERA_POLICY,
        **({"measurement_policy_identity": RASTER_POLICY_IDENTITY} if measured else {}),
        "source_revision_id": revision_id,
        "anchor_entity_id": anchor_id,
        "source_similarity_artifact_id": source_id,
        "intervals": intervals,
    }


def _compensated_payloads(
    revision_id: str,
    identity_id: str,
    camera: dict,
    translation: dict,
    similarity: dict,
    source_ids: tuple[str, ...],
) -> tuple[dict, dict]:
    camera_by_ticks = _by_ticks(camera["intervals"])
    translation_by_ticks = _by_ticks(translation["intervals"])
    similarity_by_ticks = _by_ticks(similarity["intervals"])
    if (
        not camera_by_ticks
        or set(camera_by_ticks) != set(translation_by_ticks)
        or set(camera_by_ticks) != set(similarity_by_ticks)
    ):
        raise CameraCompensationError("Camera and target intervals must match exactly")
    translation_intervals = []
    similarity_intervals = []
    for ticks in sorted(camera_by_ticks):
        camera_interval = camera_by_ticks[ticks]
        target_similarity = similarity_by_ticks[ticks]
        target_translation = translation_by_ticks[ticks]
        view_relative = _interval_matrix(target_similarity, "target")
        view0 = tuple(camera_interval["source_view_transform"])
        view1 = tuple(camera_interval["target_view_transform"])
        world_relative = _compose(_compose(_inverse(view1), view_relative), view0)
        scale, rotation = _decompose(world_relative)
        input_geometry = target_similarity.get("input_geometry")
        source_geometry = input_geometry.get("source") if isinstance(input_geometry, dict) else None
        source_points = source_geometry.get("points") if isinstance(source_geometry, dict) else None
        view_delta = target_translation.get("translation")
        if (
            not isinstance(source_points, list)
            or not source_points
            or not isinstance(view_delta, dict)
        ):
            raise CameraCompensationError("Target evidence lacks supported bounds displacement")
        xs = [point[0] for point in source_points]
        ys = [point[1] for point in source_points]
        source_view_center = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2]
        source_center = _point(_inverse(view0), source_view_center)
        target_center = _point(
            _inverse(view1),
            [
                source_view_center[0] + view_delta["dx"],
                source_view_center[1] + view_delta["dy"],
            ],
        )
        delta = {
            "dx": _round(target_center[0] - source_center[0]),
            "dy": _round(target_center[1] - source_center[1]),
        }
        common = {
            "source_tick": ticks[0],
            "target_tick": ticks[1],
            "temporal_identity_id": identity_id,
            "camera_interval_id": camera_interval["interval_id"],
            "target_translation_interval_id": target_translation["interval_id"],
            "target_similarity_interval_id": target_similarity["interval_id"],
            "camera_compensation_policy_identity": COMPENSATION_POLICY,
        }
        translation_content = {**common, "translation": delta}
        translation_intervals.append(
            {
                "interval_id": _id("camera-compensated-translation-interval", translation_content),
                **translation_content,
            }
        )
        similarity_content = {
            **common,
            "status": "SUPPORTED",
            "translation": delta,
            "rotation_degrees": {
                "status": "SUPPORTED",
                "value": _round(rotation),
                "ambiguity": "none",
            },
            "scale": {"status": "SUPPORTED", "value": _round(scale)},
        }
        similarity_intervals.append(
            {
                "interval_id": _id("camera-compensated-similarity-interval", similarity_content),
                **similarity_content,
            }
        )
    base = {
        "source_revision_id": revision_id,
        "temporal_identity_id": identity_id,
        "source_artifact_ids": sorted(source_ids),
    }
    return (
        {
            "schema_version": "svm-camera-compensated-translation-motion-0.1",
            "identity": "svm-camera-compensated-translation-motion@0.1",
            "policy_identity": COMPENSATION_POLICY,
            **base,
            "intervals": translation_intervals,
        },
        {
            "schema_version": "svm-camera-compensated-similarity-motion-0.1",
            "identity": "svm-camera-compensated-similarity-motion@0.1",
            "policy_identity": COMPENSATION_POLICY,
            **base,
            "intervals": similarity_intervals,
        },
    )


def _interval_matrix(interval: dict, label: str) -> tuple[float, float, float, float, float, float]:
    rotation = interval.get("rotation_degrees")
    scale = interval.get("scale")
    origin = interval.get("origin")
    translation = interval.get("translation")
    if (
        not isinstance(rotation, dict)
        or rotation.get("status") != "SUPPORTED"
        or not _finite(rotation.get("value"))
        or not isinstance(scale, dict)
        or scale.get("status") != "SUPPORTED"
        or not _finite(scale.get("value"))
        or scale["value"] <= 0
        or not isinstance(origin, list)
        or len(origin) != 2
        or not isinstance(translation, dict)
    ):
        raise CameraCompensationError(
            f"{label.title()} similarity must support translation, rotation, and scale"
        )
    angle = math.radians(rotation["value"])
    a = scale["value"] * math.cos(angle)
    b = scale["value"] * math.sin(angle)
    c, d = -b, a
    target = [origin[0] + translation["dx"], origin[1] + translation["dy"]]
    return (
        a,
        b,
        c,
        d,
        target[0] - a * origin[0] - c * origin[1],
        target[1] - b * origin[0] - d * origin[1],
    )


def _static_anchor(document: dict, anchor_id: Any) -> dict:
    if not isinstance(anchor_id, str):
        raise CameraCompensationError("Anchor Entity ID must be explicit")
    matches = [item for item in document.get("entities", []) if item.get("id") == anchor_id]
    if len(matches) != 1:
        raise CameraCompensationError("Static anchor Entity is missing")
    groups = {group["id"] for group in document.get("groups", []) if anchor_id in group["members"]}
    for track in document.get("animation", {}).get("content", []):
        target = track.get("target", {})
        if target.get("entity") == anchor_id or target.get("group") in groups:
            raise CameraCompensationError("Camera anchor is not static in the Recovery Document")
    camera = document.get("presentation", {}).get("camera")
    if camera not in (None, {"position": [0, 0], "rotation_degrees": 0, "scale": 1}):
        raise CameraCompensationError("S9B requires an identity Camera baseline")
    return copy.deepcopy(matches[0])


def camera_geometry_dependencies(
    similarity: dict, snapshots: tuple[ArtifactSnapshot, ...]
) -> tuple[str, ...]:
    from .observed_similarity_motion import RASTER_POLICY_IDENTITY
    from .raster_geometry_observations import raster_source_ids

    geometry_ids = tuple(similarity["source_geometry_artifact_ids"])
    if similarity.get("policy_identity") != RASTER_POLICY_IDENTITY:
        return geometry_ids
    return tuple(
        sorted({*geometry_ids, *(aid for item in snapshots for aid in raster_source_ids(item))})
    )


def _validate_anchor_geometry(
    snapshots: tuple[ArtifactSnapshot, ...],
    anchor_id: str,
    similarity: dict | None = None,
    resolved: dict[str, ArtifactSnapshot] | None = None,
) -> None:
    if not snapshots:
        raise CameraCompensationError("Camera evidence lacks anchor geometry lineage")
    from .observed_similarity_motion import RASTER_POLICY_IDENTITY

    if similarity is not None and similarity.get("policy_identity") == RASTER_POLICY_IDENTITY:
        from .observed_similarity_motion import (
            _observation,
            _observation_payload,
            _similarity_observation,
        )
        from .raster_geometry_observations import verify_raster_observation

        if resolved is None:
            raise CameraCompensationError("Measured Camera requires complete pixel lineage")
        geometries = {snapshot.artifact_id: snapshot for snapshot in snapshots}
        for snapshot in snapshots:
            verify_raster_observation(snapshot, resolved)
        for interval in similarity["intervals"]:
            geometry = _observation_payload(geometries[interval["source_geometry_artifact_id"]])
            source = _observation(
                geometry, (interval["source_tick"], interval["source_observation_id"])
            )
            target = _observation(
                geometry, (interval["target_tick"], interval["target_observation_id"])
            )
            expected = _similarity_observation(source, target, policy=RASTER_POLICY_IDENTITY)
            content = {key: value for key, value in interval.items() if key != "interval_id"}
            if (
                any(interval.get(key) != value for key, value in expected.items())
                or interval.get("similarity_observation_policy_identity") != RASTER_POLICY_IDENTITY
                or interval.get("interval_id") != _id("observed-similarity-interval", content)
            ):
                raise CameraCompensationError(
                    "Measured Camera similarity does not match raster observations"
                )
        return
    for snapshot in snapshots:
        if snapshot.provenance.get("shape_id") != anchor_id:
            raise CameraCompensationError("Camera similarity evidence belongs to another anchor")


def _standard_similarity(snapshot: ArtifactSnapshot) -> dict:
    payload = _json(snapshot)
    if snapshot.media_type != "application/vnd.svm.observed-similarity-motion+json;version=0.1":
        raise CameraCompensationError("Camera anchor requires accepted S4 similarity evidence")
    from .observed_similarity_motion import RASTER_POLICY_IDENTITY

    if payload.get("policy_identity") == RASTER_POLICY_IDENTITY:
        from .observed_rotation_tracks import _read_evidence

        _read_evidence(snapshot)
        if snapshot.provenance != {
            "adapter_id": "adapter:observed-similarity-motion",
            "adapter_version": "0.2",
            "engine": "svm-geometry-similarity-observation",
            "engine_version": "svm-observed-similarity-motion@0.1",
            "policy_identity": RASTER_POLICY_IDENTITY,
            "source_correspondence_artifact_ids": payload["source_correspondence_artifact_ids"],
            "source_geometry_artifact_ids": payload["source_geometry_artifact_ids"],
        }:
            raise CameraCompensationError(
                "Measured Camera requires verified raster similarity provenance"
            )
    return payload


def _one_standard_similarity(snapshots: tuple[ArtifactSnapshot, ...]) -> dict:
    matches = [
        item
        for item in snapshots
        if item.media_type == "application/vnd.svm.observed-similarity-motion+json;version=0.1"
    ]
    return _standard_similarity(_only(matches))


def _one_standard_translation(snapshots: tuple[ArtifactSnapshot, ...]) -> dict:
    matches = [
        item
        for item in snapshots
        if item.media_type == "application/vnd.svm.observed-translation-motion+json;version=0.1"
    ]
    return _json(_only(matches))


def _one_media(snapshots: tuple[ArtifactSnapshot, ...], media_type: str) -> dict:
    return _json(_only([item for item in snapshots if item.media_type == media_type]))


def _json(snapshot: ArtifactSnapshot) -> dict:
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CameraCompensationError("Evidence is invalid JSON") from exc
    if not isinstance(payload, dict) or canonical_bytes(payload) != snapshot.content:
        raise CameraCompensationError("Evidence is not canonical")
    return payload


def _only(items):
    if len(items) != 1:
        raise CameraCompensationError("Expected exactly one evidence Artifact of each kind")
    return items[0]


def _by_ticks(intervals: list[dict]) -> dict[tuple[int, int], dict]:
    result = {(item["source_tick"], item["target_tick"]): item for item in intervals}
    if len(result) != len(intervals):
        raise CameraCompensationError("Evidence interval ticks must be unique")
    return result


def _compose(outer, inner):
    a, b, c, d, e, f = outer
    g, h, i, j, k, offset_y = inner
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * offset_y + e,
        b * k + d * offset_y + f,
    )


def _inverse(matrix):
    a, b, c, d, e, f = matrix
    determinant = a * d - b * c
    if not math.isfinite(determinant) or abs(determinant) < 1e-12:
        raise CameraCompensationError("Similarity transform is not invertible")
    return (
        d / determinant,
        -b / determinant,
        -c / determinant,
        a / determinant,
        (c * f - d * e) / determinant,
        (b * e - a * f) / determinant,
    )


def _point(matrix, point):
    a, b, c, d, e, f = matrix
    return (a * point[0] + c * point[1] + e, b * point[0] + d * point[1] + f)


def _decompose(matrix):
    a, b, c, d, _, _ = matrix
    scale = math.hypot(a, b)
    if scale <= 0 or abs(c + b) > 1e-7 or abs(d - a) > 1e-7:
        raise CameraCompensationError("Compensated transform is not a uniform similarity")
    angle = (math.degrees(math.atan2(b, a)) + 180.0) % 360.0 - 180.0
    return scale, angle


def _round(value):
    return 0.0 if abs(value) < 1e-12 else float(format(value, ".12g"))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _id(prefix: str, value: dict) -> str:
    return prefix + ":" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _accepted_reference(document: dict, artifact_id: str) -> dict:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise CameraCompensationError("Source evidence must already be accepted")
    return copy.deepcopy(matches[0])


def _camera_provenance(source_id: str, policy: str = CAMERA_POLICY) -> dict:
    return {
        "adapter_id": "adapter:observed-camera-similarity",
        "adapter_version": "0.2" if policy == MEASURED_CAMERA_POLICY else "0.1",
        "engine": "svm-static-anchor-camera-similarity",
        "engine_version": "svm-static-anchor-camera-similarity@0.1",
        "policy_identity": policy,
        "source_similarity_artifact_id": source_id,
    }


def _proposal(request, adapter, label, outputs, change, preview, parameters):
    generator = GeneratorProvenance(
        adapter.adapter_id, adapter.adapter_version, label, label + "@0.1", parameters
    )
    digest = hashlib.sha256(
        canonical_bytes(
            {
                "base": request.base_revision_id,
                "generator": asdict(generator),
                "outputs": [item.artifact_id for item in outputs],
            }
        )
    ).hexdigest()[:16]
    return Proposal(
        proposal_id=f"proposal:{label}:{digest}",
        base_revision_id=request.base_revision_id,
        generator=generator,
        transaction=Transaction(
            f"transaction:{label}:{digest}", (change,), f"Attach {label} evidence"
        ),
        preview_artifacts=tuple(
            PreviewArtifact(item.artifact_id, item.content_hash, item.media_type)
            for item in outputs
        ),
        preview=preview,
        required_artifact_ids=tuple(
            dict.fromkeys(
                [
                    *(item.artifact_id for item in outputs),
                    *(item["id"] for item in change.source_references),
                ]
            )
        ),
        notes="Evidence only; Camera and target Tracks are unchanged",
    )
