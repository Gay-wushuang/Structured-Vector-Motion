from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import (
    OBSERVED_SIMILARITY_MOTION_IDENTITY,
    AttachObservedSimilarityEvidenceChange,
    AttachRasterSimilarityEvidenceChange,
    Transaction,
)
from .temporal_correspondence import (
    EVIDENCE_MEDIA_TYPE,
    INFERENCE_IDENTITY,
    OBSERVATION_MEDIA_TYPE,
    OBSERVATION_MEDIA_TYPE_V2,
    read_primitive_observations,
)
from .temporal_correspondence import (
    POLICY_IDENTITY as CORRESPONDENCE_POLICY_IDENTITY,
)

MEDIA_TYPE = "application/vnd.svm.observed-similarity-motion+json;version=0.1"
POLICY_IDENTITY = "svm-geometry-similarity-observation-policy@0.1"
RASTER_POLICY_IDENTITY = "svm-controlled-raster-similarity-policy@0.1"
RASTER_SUPPORTED_RESIDUAL = 0.01
RASTER_RMS_PIXELS = 0.75
SUPPORTED_RESIDUAL = 1e-6
UNCERTAIN_RESIDUAL = 0.02


class ObservedSimilarityMotionError(ValueError):
    pass


@dataclass(frozen=True)
class ObservedSimilarityIntervalPreview:
    interval_id: str
    source_tick: int
    target_tick: int
    status: str
    rotation_status: str
    rotation_degrees: float | None
    scale_status: str
    scale: float | None
    normalized_residual: float | None


@dataclass(frozen=True)
class ObservedSimilarityMotionPreview(ProposalPreview):
    temporal_identity_id: str = ""
    intervals: tuple[ObservedSimilarityIntervalPreview, ...] = ()


class ObservedSimilarityMotionAdapter:
    adapter_id = "adapter:observed-similarity-motion"
    adapter_version = "0.1"
    policy_identity = POLICY_IDENTITY

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise ObservedSimilarityMotionError("Observed similarity scope must be document")
        if set(request.options) != {"temporal_identity_id", "inference_ids"}:
            raise ObservedSimilarityMotionError(
                "Explicit temporal_identity_id and inference_ids are required"
            )
        identity_id = request.options["temporal_identity_id"]
        inference_ids = request.options["inference_ids"]
        if (
            not isinstance(identity_id, str)
            or not isinstance(inference_ids, list)
            or not inference_ids
            or any(not isinstance(item, str) for item in inference_ids)
            or len(inference_ids) != len(set(inference_ids))
        ):
            raise ObservedSimilarityMotionError(
                "inference_ids must be a non-empty unique string list"
            )
        identities = [
            item
            for item in request.document.get("temporal_identities", [])
            if item.get("id") == identity_id
        ]
        if len(identities) != 1:
            raise ObservedSimilarityMotionError(
                "Observed similarity requires an existing temporal identity"
            )
        identity = copy.deepcopy(identities[0])
        provenance = {item["inference_id"]: item for item in identity["provenance"]}
        try:
            selected = [provenance[item] for item in inference_ids]
        except KeyError as exc:
            raise ObservedSimilarityMotionError(
                "Correspondence was not promoted into this temporal identity"
            ) from exc
        correspondence_ids = tuple(sorted({item["evidence_artifact_id"] for item in selected}))
        correspondence_references = tuple(
            _accepted_reference(request.document, item) for item in correspondence_ids
        )
        correspondence_snapshots = {
            item.artifact_id: item
            for item in (artifacts.resolve_reference(ref) for ref in correspondence_references)
        }
        geometry_ids = tuple(
            sorted(
                {
                    _correspondence_payload(snapshot)["source_artifact_id"]
                    for snapshot in correspondence_snapshots.values()
                }
            )
        )
        expected_ids = tuple(sorted((*correspondence_ids, *geometry_ids)))
        if tuple(sorted(request.artifact_ids)) != expected_ids or len(request.artifact_ids) != len(
            expected_ids
        ):
            raise ObservedSimilarityMotionError(
                "Artifact IDs must exactly match R1 correspondence and source geometry"
            )
        geometry_snapshots = {item.artifact_id: item for item in artifacts.resolve(geometry_ids)}
        _validate_geometry_snapshots(geometry_snapshots)
        raster_references: tuple[dict[str, Any], ...] = ()
        if self.policy_identity == RASTER_POLICY_IDENTITY:
            from .raster_geometry_observations import raster_source_ids, verify_raster_observation

            geometry_snapshots = {
                aid: artifacts.resolve_reference(_accepted_reference(request.document, aid))
                for aid in geometry_ids
            }
            raster_ids = sorted(
                {
                    aid
                    for snapshot in geometry_snapshots.values()
                    for aid in raster_source_ids(snapshot)
                }
            )
            raster_references = tuple(
                _accepted_reference(request.document, aid) for aid in raster_ids
            )
            raster_sources = {
                ref["id"]: artifacts.resolve_reference(ref) for ref in raster_references
            }
            for snapshot in geometry_snapshots.values():
                verify_raster_observation(snapshot, raster_sources)
        intervals = _derive_intervals(
            identity, selected, correspondence_snapshots, geometry_snapshots, self.policy_identity
        )
        payload = _payload(
            request.base_revision_id,
            identity_id,
            correspondence_ids,
            geometry_ids,
            intervals,
            self.policy_identity,
        )
        evidence = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "engine": "svm-geometry-similarity-observation",
                "engine_version": OBSERVED_SIMILARITY_MOTION_IDENTITY,
                "policy_identity": self.policy_identity,
                "source_correspondence_artifact_ids": list(correspondence_ids),
                "source_geometry_artifact_ids": list(geometry_ids),
            },
        )
        geometry_references = tuple(
            geometry_snapshots[item].document_reference() for item in geometry_ids
        )
        change = AttachObservedSimilarityEvidenceChange(
            evidence.document_reference(),
            correspondence_references,
            geometry_references,
            identity,
            tuple(inference_ids),
            request.base_revision_id,
        )
        if self.policy_identity == RASTER_POLICY_IDENTITY:
            change = AttachRasterSimilarityEvidenceChange(
                **asdict(change), raster_source_references=raster_references
            )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "svm-geometry-similarity-observation",
            OBSERVED_SIMILARITY_MOTION_IDENTITY,
            {
                "temporal_identity_id": identity_id,
                "inference_ids": inference_ids,
                "policy_identity": self.policy_identity,
                "supported_residual": RASTER_SUPPORTED_RESIDUAL
                if self.policy_identity == RASTER_POLICY_IDENTITY
                else SUPPORTED_RESIDUAL,
                "uncertain_residual": UNCERTAIN_RESIDUAL,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "evidence": evidence.artifact_id,
                }
            )
        ).hexdigest()[:16]
        counts = {
            status: sum(item["status"] == status for item in intervals)
            for status in ("SUPPORTED", "UNCERTAIN", "REJECTED")
        }
        return Proposal(
            proposal_id=f"proposal:observed-similarity-motion:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:observed-similarity-motion:{digest}",
                (change,),
                "Attach geometry-aware similarity motion evidence",
            ),
            report=EvaluationReport(
                metrics={status.lower(): float(count) for status, count in counts.items()}
            ),
            preview_artifacts=(
                PreviewArtifact(evidence.artifact_id, evidence.content_hash, evidence.media_type),
            ),
            preview=ObservedSimilarityMotionPreview(
                temporal_identity_id=identity_id,
                intervals=tuple(_preview(item) for item in intervals),
            ),
            required_artifact_ids=(
                evidence.artifact_id,
                *expected_ids,
                *(ref["id"] for ref in raster_references),
            ),
            notes="Similarity observations are evidence only; no Track or Group is changed",
        )


class RasterObservedSimilarityMotionAdapter(ObservedSimilarityMotionAdapter):
    """Explicit quantized-pixel policy; exact S4 remains unchanged."""

    adapter_version = "0.2"
    policy_identity = RASTER_POLICY_IDENTITY


def verify_observed_similarity_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    output = resolved.get(change.evidence_reference.get("id"))
    if output is None or output.kind != ArtifactKind.DERIVED or output.media_type != MEDIA_TYPE:
        raise ValueError("Observed similarity output Artifact was not resolved")
    correspondence_ids = tuple(sorted(item["id"] for item in change.correspondence_references))
    geometry_ids = tuple(sorted(item["id"] for item in change.geometry_references))
    policy = output.provenance.get("policy_identity")
    if policy not in {POLICY_IDENTITY, RASTER_POLICY_IDENTITY}:
        raise ValueError("Unsupported similarity measurement policy")
    expected_provenance = {
        "adapter_id": "adapter:observed-similarity-motion",
        "adapter_version": "0.2" if policy == RASTER_POLICY_IDENTITY else "0.1",
        "engine": "svm-geometry-similarity-observation",
        "engine_version": OBSERVED_SIMILARITY_MOTION_IDENTITY,
        "policy_identity": policy,
        "source_correspondence_artifact_ids": list(correspondence_ids),
        "source_geometry_artifact_ids": list(geometry_ids),
    }
    if output.provenance != expected_provenance:
        raise ValueError("Observed similarity Artifact provenance is invalid")
    correspondences = {item: resolved[item] for item in correspondence_ids}
    geometries = {item: resolved[item] for item in geometry_ids}
    _validate_geometry_snapshots(geometries)
    if policy == RASTER_POLICY_IDENTITY:
        from .raster_geometry_observations import raster_source_ids, verify_raster_observation

        if type(change) is not AttachRasterSimilarityEvidenceChange:
            raise ValueError("Raster similarity requires verified pixel lineage Change")
        expected_raster_ids = {
            aid for snapshot in geometries.values() for aid in raster_source_ids(snapshot)
        }
        if tuple(ref["id"] for ref in change.raster_source_references) != tuple(
            sorted(expected_raster_ids)
        ):
            raise ValueError("Raster similarity pixel dependencies are not exact")
        for snapshot in geometries.values():
            verify_raster_observation(snapshot, resolved)
    elif type(change) is AttachRasterSimilarityEvidenceChange:
        raise ValueError("Raster Change cannot relabel the exact vector policy")
    identity = change.temporal_identity
    provenance = {item["inference_id"]: item for item in identity["provenance"]}
    if len(change.inference_ids) != len(set(change.inference_ids)):
        raise ValueError("Observed similarity inference IDs must be unique")
    try:
        selected = [provenance[item] for item in change.inference_ids]
    except KeyError as exc:
        raise ValueError("Observed similarity inference was not promoted") from exc
    expected_correspondence_ids = tuple(sorted({item["evidence_artifact_id"] for item in selected}))
    if correspondence_ids != expected_correspondence_ids:
        raise ValueError("Observed similarity sources do not match R1 provenance")
    expected_geometry_ids = tuple(
        sorted(
            {
                _correspondence_payload(snapshot)["source_artifact_id"]
                for snapshot in correspondences.values()
            }
        )
    )
    if geometry_ids != expected_geometry_ids:
        raise ValueError("Observed similarity geometry does not match R0 sources")
    expected = _payload(
        change.source_revision_id,
        identity["id"],
        correspondence_ids,
        geometry_ids,
        _derive_intervals(identity, selected, correspondences, geometries, policy),
        policy,
    )
    if canonical_bytes(expected) != output.content:
        raise ValueError("Observed similarity evidence does not match frozen geometry")


def _derive_intervals(
    identity: dict[str, Any],
    selected: list[dict[str, Any]],
    correspondences: dict[str, ArtifactSnapshot],
    geometries: dict[str, ArtifactSnapshot],
    policy: str = POLICY_IDENTITY,
) -> list[dict[str, Any]]:
    bindings = {(item["tick"], item["observation_id"]) for item in identity["bindings"]}
    intervals = []
    for provenance in selected:
        correspondence = correspondences.get(provenance["evidence_artifact_id"])
        if correspondence is None:
            raise ObservedSimilarityMotionError("Missing exact R0 evidence Artifact")
        r0 = _correspondence_payload(correspondence)
        candidates = [
            item
            for item in r0["candidates"]
            if item.get("inference_id") == provenance["inference_id"]
        ]
        if len(candidates) != 1:
            raise ObservedSimilarityMotionError("R1 inference is absent from R0 evidence")
        candidate = candidates[0]
        if (
            candidate.get("candidate_id") != provenance["candidate_id"]
            or candidate.get("status") != "SUPPORTED"
            or provenance["evidence_policy_identity"] != r0["policy_identity"]
        ):
            raise ObservedSimilarityMotionError("R1 provenance does not match R0 inference")
        pair = (
            (candidate["source_tick"], candidate["source_observation_id"]),
            (candidate["target_tick"], candidate["target_observation_id"]),
        )
        if any(item not in bindings for item in pair):
            raise ObservedSimilarityMotionError(
                "Observation pair does not belong to the temporal identity"
            )
        geometry_snapshot = geometries.get(r0["source_artifact_id"])
        if geometry_snapshot is None:
            raise ObservedSimilarityMotionError("Missing frozen observation geometry")
        observations = _observation_payload(geometry_snapshot)
        source = _observation(observations, pair[0])
        target = _observation(observations, pair[1])
        if policy == RASTER_POLICY_IDENTITY:
            from .raster_geometry_observations import (
                POLICY_IDENTITY as RASTER_GEOMETRY_POLICY,
            )
            from .raster_geometry_observations import (
                PRIMITIVE_TYPE,
            )

            if geometry_snapshot.provenance.get(
                "geometry_observation_policy"
            ) != RASTER_GEOMETRY_POLICY or any(
                item["primitive_type"] != PRIMITIVE_TYPE for item in (source, target)
            ):
                raise ObservedSimilarityMotionError(
                    "Raster measurement requires raster geometry evidence"
                )
        observation = _similarity_observation(source, target, policy=policy)
        content = {
            "temporal_identity_id": identity["id"],
            "source_tick": pair[0][0],
            "target_tick": pair[1][0],
            "source_observation_id": pair[0][1],
            "target_observation_id": pair[1][1],
            "source_geometry_artifact_id": geometry_snapshot.artifact_id,
            "correspondence_candidate_id": candidate["candidate_id"],
            "correspondence_inference_id": candidate["inference_id"],
            "correspondence_evidence_artifact_id": correspondence.artifact_id,
            "temporal_identity_promotion_policy_identity": provenance["promotion_policy_identity"],
            "similarity_observation_policy_identity": policy,
            **observation,
        }
        intervals.append(
            {
                "interval_id": "observed-similarity-interval:"
                + hashlib.sha256(canonical_bytes(content)).hexdigest(),
                **content,
            }
        )
    intervals.sort(
        key=lambda item: (
            item["source_tick"],
            item["target_tick"],
            item["source_observation_id"],
            item["target_observation_id"],
        )
    )
    return intervals


def _similarity_observation(
    source: dict[str, Any], target: dict[str, Any], *, policy: str = POLICY_IDENTITY
) -> dict[str, Any]:
    source_geometry = source.get("geometry")
    target_geometry = target.get("geometry")
    if source_geometry is None or target_geometry is None:
        return _abstention("insufficient_geometry", source_geometry, target_geometry)
    source_points = source_geometry["points"]
    target_points = target_geometry["points"]
    if len(source_points) != len(target_points):
        return _abstention("landmark_count_mismatch", source_geometry, target_geometry)
    source_chirality = _chirality(source_points)
    target_chirality = _chirality(target_points)
    if source_chirality == 0 or target_chirality == 0:
        return _abstention("degenerate_geometry", source_geometry, target_geometry)
    if source_chirality != target_chirality:
        return _rejection("reflection", source_geometry, target_geometry)
    fitted = _fit_similarity(source_points, target_points)
    if fitted is None:
        return _abstention("degenerate_geometry", source_geometry, target_geometry)
    scale, angle, source_center, target_center, rms, normalized = fitted
    supported_threshold = (
        RASTER_SUPPORTED_RESIDUAL if policy == RASTER_POLICY_IDENTITY else SUPPORTED_RESIDUAL
    )
    if normalized <= supported_threshold and (
        policy != RASTER_POLICY_IDENTITY or rms <= RASTER_RMS_PIXELS
    ):
        fit_status = "SUPPORTED"
    elif normalized <= UNCERTAIN_RESIDUAL:
        fit_status = "UNCERTAIN"
    else:
        fit_status = "REJECTED"
    symmetry = source_geometry["rotation_symmetry"]
    symmetry_matches = symmetry == target_geometry["rotation_symmetry"]
    rotation_supported = fit_status == "SUPPORTED" and symmetry == "none" and symmetry_matches
    rotation_status = (
        "SUPPORTED"
        if rotation_supported
        else ("REJECTED" if fit_status == "REJECTED" else "UNCERTAIN")
    )
    scale_status = fit_status
    overall = (
        "SUPPORTED"
        if rotation_status == scale_status == "SUPPORTED"
        else ("REJECTED" if "REJECTED" in {rotation_status, scale_status} else "UNCERTAIN")
    )
    ambiguity = (
        "none"
        if rotation_supported
        else ("fit_residual" if fit_status != "SUPPORTED" else "rotation_symmetry")
    )
    return {
        "status": overall,
        "reason": "similarity_fit" if fit_status != "REJECTED" else "non_uniform_deformation",
        "input_geometry": {
            "source": copy.deepcopy(source_geometry),
            "target": copy.deepcopy(target_geometry),
        },
        "translation": {
            "dx": _round(target_center[0] - source_center[0]),
            "dy": _round(target_center[1] - source_center[1]),
        },
        "origin": [_round(source_center[0]), _round(source_center[1])],
        "rotation_degrees": {
            "status": rotation_status,
            "value": _round(angle) if rotation_supported else None,
            "ambiguity": ambiguity,
        },
        "scale": {"status": scale_status, "value": _round(scale)},
        "fit": {
            "rms_error": _round(rms),
            "normalized_rms": _round(normalized),
            "supported_threshold": supported_threshold,
            "uncertain_threshold": UNCERTAIN_RESIDUAL,
        },
    }


def _fit_similarity(
    source: list[list[int | float]], target: list[list[int | float]]
) -> tuple[float, float, tuple[float, float], tuple[float, float], float, float] | None:
    source_center = _center(source)
    target_center = _center(target)
    centered_source = [(x - source_center[0], y - source_center[1]) for x, y in source]
    centered_target = [(x - target_center[0], y - target_center[1]) for x, y in target]
    source_energy = sum(x * x + y * y for x, y in centered_source)
    target_energy = sum(x * x + y * y for x, y in centered_target)
    if source_energy <= 0 or target_energy <= 0:
        return None
    dot = sum(
        sx * tx + sy * ty
        for (sx, sy), (tx, ty) in zip(centered_source, centered_target, strict=True)
    )
    cross = sum(
        sx * ty - sy * tx
        for (sx, sy), (tx, ty) in zip(centered_source, centered_target, strict=True)
    )
    a, b = dot / source_energy, cross / source_energy
    scale = math.hypot(a, b)
    if not math.isfinite(scale) or scale <= 0:
        return None
    errors = [
        math.hypot(a * sx - b * sy - tx, b * sx + a * sy - ty)
        for (sx, sy), (tx, ty) in zip(centered_source, centered_target, strict=True)
    ]
    rms = math.sqrt(sum(value * value for value in errors) / len(errors))
    target_rms = math.sqrt(target_energy / len(centered_target))
    normalized = rms / target_rms
    angle = _shortest_degrees(math.degrees(math.atan2(b, a)))
    return scale, angle, source_center, target_center, rms, normalized


def _chirality(points: list[list[int | float]]) -> int:
    for first, second, third in itertools.combinations(points, 3):
        cross = (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
            third[0] - first[0]
        )
        if abs(cross) > 1e-12:
            return 1 if cross > 0 else -1
    return 0


def _center(points: list[list[int | float]]) -> tuple[float, float]:
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _shortest_degrees(value: float) -> float:
    result = (value + 180.0) % 360.0 - 180.0
    return 0.0 if abs(result) < 1e-12 else result


def _abstention(reason: str, source: Any, target: Any) -> dict[str, Any]:
    return {
        "status": "UNCERTAIN",
        "reason": reason,
        "input_geometry": {"source": copy.deepcopy(source), "target": copy.deepcopy(target)},
        "translation": None,
        "origin": None,
        "rotation_degrees": {"status": "UNCERTAIN", "value": None, "ambiguity": reason},
        "scale": {"status": "UNCERTAIN", "value": None},
        "fit": None,
    }


def _rejection(reason: str, source: Any, target: Any) -> dict[str, Any]:
    return {
        "status": "REJECTED",
        "reason": reason,
        "input_geometry": {"source": copy.deepcopy(source), "target": copy.deepcopy(target)},
        "translation": None,
        "origin": None,
        "rotation_degrees": {"status": "REJECTED", "value": None, "ambiguity": reason},
        "scale": {"status": "REJECTED", "value": None},
        "fit": None,
    }


def _preview(interval: dict[str, Any]) -> ObservedSimilarityIntervalPreview:
    rotation = interval["rotation_degrees"]
    scale = interval["scale"]
    fit = interval["fit"]
    return ObservedSimilarityIntervalPreview(
        interval["interval_id"],
        interval["source_tick"],
        interval["target_tick"],
        interval["status"],
        rotation["status"],
        rotation["value"],
        scale["status"],
        scale["value"],
        fit["normalized_rms"] if fit else None,
    )


def _payload(
    revision_id: str,
    identity_id: str,
    correspondence_ids: tuple[str, ...],
    geometry_ids: tuple[str, ...],
    intervals: list[dict[str, Any]],
    policy: str = POLICY_IDENTITY,
) -> dict[str, Any]:
    return {
        "schema_version": "svm-observed-similarity-motion-0.1",
        "identity": OBSERVED_SIMILARITY_MOTION_IDENTITY,
        "policy_identity": policy,
        "source_revision_id": revision_id,
        "temporal_identity_id": identity_id,
        "source_correspondence_artifact_ids": list(correspondence_ids),
        "source_geometry_artifact_ids": list(geometry_ids),
        "intervals": intervals,
    }


def _correspondence_payload(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservedSimilarityMotionError("R0 evidence is invalid JSON") from exc
    if (
        snapshot.kind != ArtifactKind.DERIVED
        or snapshot.media_type != EVIDENCE_MEDIA_TYPE
        or not isinstance(payload, dict)
        or canonical_bytes(payload) != snapshot.content
        or payload.get("identity") != INFERENCE_IDENTITY
        or payload.get("policy_identity") != CORRESPONDENCE_POLICY_IDENTITY
        or not isinstance(payload.get("source_artifact_id"), str)
        or not isinstance(payload.get("candidates"), list)
    ):
        raise ObservedSimilarityMotionError("Observed similarity requires canonical R0 evidence")
    return payload


def _observation_payload(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = read_primitive_observations(snapshot.content)
    except ValueError as exc:
        raise ObservedSimilarityMotionError("Observation geometry is invalid") from exc
    if (
        snapshot.kind != ArtifactKind.REFERENCE
        or snapshot.media_type not in {OBSERVATION_MEDIA_TYPE, OBSERVATION_MEDIA_TYPE_V2}
        or payload.get("schema_version")
        not in {"svm-primitive-observations-0.1", "svm-primitive-observations-0.2"}
        or (
            payload["schema_version"] == "svm-primitive-observations-0.1"
            and snapshot.media_type != OBSERVATION_MEDIA_TYPE
        )
        or (
            payload["schema_version"] == "svm-primitive-observations-0.2"
            and snapshot.media_type != OBSERVATION_MEDIA_TYPE_V2
        )
    ):
        raise ObservedSimilarityMotionError("Observation geometry Artifact is unsupported")
    return payload


def _validate_geometry_snapshots(snapshots: dict[str, ArtifactSnapshot]) -> None:
    for snapshot in snapshots.values():
        _observation_payload(snapshot)


def _observation(payload: dict[str, Any], key: tuple[int, str]) -> dict[str, Any]:
    matches = [
        primitive
        for frame in payload.get("frames", [])
        if frame.get("tick") == key[0]
        for primitive in frame.get("primitives", [])
        if primitive.get("observation_id") == key[1]
    ]
    if len(matches) != 1:
        raise ObservedSimilarityMotionError("Observation geometry endpoint is missing")
    return matches[0]


def _accepted_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ObservedSimilarityMotionError("R0 evidence must already be accepted")
    return copy.deepcopy(matches[0])


def _round(value: float) -> float:
    return float(format(value, ".12g"))
