from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import AppendReferencesChange, Transaction

OBSERVATION_MEDIA_TYPE = "application/vnd.svm.primitive-observations+json;version=0.1"
OBSERVATION_MEDIA_TYPE_V2 = "application/vnd.svm.primitive-observations+json;version=0.2"
EVIDENCE_MEDIA_TYPE = "application/vnd.svm.temporal-correspondence+json;version=0.1"
INFERENCE_IDENTITY = "svm-temporal-correspondence@0.1"
POLICY_IDENTITY = "svm-bounds-correspondence-policy@0.1"


class TemporalCorrespondenceError(ValueError):
    pass


class TemporalCorrespondenceAdapter:
    """Produce abstaining pair correspondence evidence from two frozen frames."""

    adapter_id = "adapter:temporal-correspondence"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or request.options:
            raise TemporalCorrespondenceError(
                "Temporal correspondence v0.1 accepts document scope and no options"
            )
        if len(request.artifact_ids) != 1:
            raise TemporalCorrespondenceError(
                "Temporal correspondence requires one primitive-observation Artifact"
            )
        source = artifacts.resolve_as(
            request.artifact_ids,
            kind=ArtifactKind.REFERENCE,
            media_types=frozenset({OBSERVATION_MEDIA_TYPE, OBSERVATION_MEDIA_TYPE_V2}),
        )[0]
        payload = read_primitive_observations(source.content)
        candidates = _infer(payload, source.artifact_id)
        evidence_payload = {
            "schema_version": "svm-temporal-correspondence-0.1",
            "identity": INFERENCE_IDENTITY,
            "policy_identity": POLICY_IDENTITY,
            "source_artifact_id": source.artifact_id,
            "source_revision_id": request.base_revision_id,
            "frame_ticks": [frame["tick"] for frame in payload["frames"]],
            "candidates": candidates,
        }
        evidence = artifacts.import_bytes(
            canonical_bytes(evidence_payload),
            media_type=EVIDENCE_MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "engine": "svm-bounds-correspondence",
                "engine_version": INFERENCE_IDENTITY,
                "policy_identity": POLICY_IDENTITY,
                "source_artifact_id": source.artifact_id,
            },
        )
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="svm-bounds-correspondence",
            engine_version=INFERENCE_IDENTITY,
            parameters={
                "policy_identity": POLICY_IDENTITY,
                "source_artifact_id": source.artifact_id,
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
            status: sum(candidate["status"] == status for candidate in candidates)
            for status in ("SUPPORTED", "UNCERTAIN", "REJECTED")
        }
        return Proposal(
            proposal_id=f"proposal:temporal-correspondence:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:temporal-correspondence:{digest}",
                changes=(AppendReferencesChange((evidence.document_reference(),)),),
                message="Attach conservative temporal correspondence evidence",
            ),
            report=EvaluationReport(
                metrics={
                    "candidates": float(len(candidates)),
                    **{status.lower(): float(count) for status, count in counts.items()},
                }
            ),
            preview_artifacts=(
                PreviewArtifact(evidence.artifact_id, evidence.content_hash, evidence.media_type),
            ),
            preview=ProposalPreview(),
            required_artifact_ids=(evidence.artifact_id,),
            notes=(
                "Acceptance attaches correspondence evidence only; it does not create an "
                "Entity, Track, or propagated edit"
            ),
        )


def read_primitive_observations(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TemporalCorrespondenceError("Primitive observations are not valid JSON") from exc
    if not isinstance(payload, dict) or canonical_bytes(payload) != content:
        raise TemporalCorrespondenceError("Primitive observations must be canonical JSON")
    schema_version = payload.get("schema_version")
    if schema_version not in {
        "svm-primitive-observations-0.1",
        "svm-primitive-observations-0.2",
    }:
        raise TemporalCorrespondenceError("Primitive observation schema is unsupported")
    canvas = payload.get("canvas")
    if (
        not isinstance(canvas, list)
        or len(canvas) != 2
        or any(not _positive_number(value) for value in canvas)
    ):
        raise TemporalCorrespondenceError("Primitive observations require a positive canvas")
    frames = payload.get("frames")
    if not isinstance(frames, list) or len(frames) != 2:
        raise TemporalCorrespondenceError("Temporal correspondence v0.1 requires two frames")
    ticks: list[int] = []
    observation_ids: set[str] = set()
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"tick", "primitives"}:
            raise TemporalCorrespondenceError("Primitive observation frame is invalid")
        tick = frame["tick"]
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            raise TemporalCorrespondenceError("Primitive observation tick is invalid")
        ticks.append(tick)
        primitives = frame["primitives"]
        if not isinstance(primitives, list):
            raise TemporalCorrespondenceError("Frame primitives must be an array")
        for primitive in primitives:
            _validate_primitive(primitive, observation_ids, schema_version)
    if ticks != sorted(set(ticks)):
        raise TemporalCorrespondenceError("Frame ticks must be unique and increasing")
    return payload


def _validate_primitive(primitive: Any, observation_ids: set[str], schema_version: str) -> None:
    fields = {
        "observation_id",
        "primitive_type",
        "bounds",
        "fill",
    }
    if schema_version == "svm-primitive-observations-0.2":
        fields.add("geometry")
    if not isinstance(primitive, dict) or set(primitive) != fields:
        raise TemporalCorrespondenceError("Primitive observation has invalid fields")
    observation_id = primitive["observation_id"]
    if (
        not isinstance(observation_id, str)
        or not observation_id.startswith("observation:")
        or observation_id in observation_ids
    ):
        raise TemporalCorrespondenceError("Primitive observation ID is invalid or duplicated")
    observation_ids.add(observation_id)
    if not isinstance(primitive["primitive_type"], str) or not primitive["primitive_type"]:
        raise TemporalCorrespondenceError("Primitive type must be non-empty")
    bounds = primitive["bounds"]
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or any(not _finite_number(value) for value in bounds)
        or not (bounds[0] < bounds[2] and bounds[1] < bounds[3])
    ):
        raise TemporalCorrespondenceError("Primitive bounds are invalid")
    fill = primitive["fill"]
    if not isinstance(fill, str) or len(fill) != 7 or not fill.startswith("#"):
        raise TemporalCorrespondenceError("Primitive fill must be six-digit hex")
    try:
        int(fill[1:], 16)
    except ValueError as exc:
        raise TemporalCorrespondenceError("Primitive fill must be six-digit hex") from exc
    if schema_version == "svm-primitive-observations-0.2":
        _validate_observed_geometry(primitive["geometry"])


def _validate_observed_geometry(geometry: Any) -> None:
    if not isinstance(geometry, dict) or set(geometry) != {
        "type",
        "points",
        "rotation_symmetry",
    }:
        raise TemporalCorrespondenceError("Primitive observed geometry fields are invalid")
    if geometry["type"] != "ordered-landmarks" or geometry["rotation_symmetry"] not in {
        "none",
        "half-turn",
        "quarter-turn",
        "continuous",
    }:
        raise TemporalCorrespondenceError("Primitive observed geometry semantics are unsupported")
    points = geometry["points"]
    if (
        not isinstance(points, list)
        or len(points) < 3
        or any(
            not isinstance(point, list)
            or len(point) != 2
            or any(not _finite_number(value) for value in point)
            for point in points
        )
    ):
        raise TemporalCorrespondenceError("Primitive observed landmarks are invalid")


def _infer(payload: dict[str, Any], source_artifact_id: str) -> list[dict[str, Any]]:
    source_frame, target_frame = payload["frames"]
    width, height = payload["canvas"]
    diagonal = math.hypot(width, height)
    sources = sorted(source_frame["primitives"], key=lambda item: item["observation_id"])
    targets = sorted(target_frame["primitives"], key=lambda item: item["observation_id"])
    scored: dict[tuple[str, str], float] = {}
    raw: dict[tuple[str, str], dict[str, float]] = {}
    for source in sources:
        for target in targets:
            key = (source["observation_id"], target["observation_id"])
            signals = _signals(source, target, diagonal)
            raw[key] = signals
            scored[key] = _round(
                0.45 * signals["centroid_proximity"]
                + 0.20 * signals["size_similarity"]
                + 0.20 * signals["color_similarity"]
                + 0.15 * signals["type_agreement"]
            )
    results: list[dict[str, Any]] = []
    for source in sources:
        source_id = source["observation_id"]
        source_scores = sorted(
            (scored[(source_id, target["observation_id"])] for target in targets), reverse=True
        )
        for target in targets:
            target_id = target["observation_id"]
            support = scored[(source_id, target_id)]
            target_scores = sorted(
                (scored[(other["observation_id"], target_id)] for other in sources), reverse=True
            )
            source_margin = support - (source_scores[1] if len(source_scores) > 1 else 0.0)
            target_margin = support - (target_scores[1] if len(target_scores) > 1 else 0.0)
            mutual_best = support == source_scores[0] and support == target_scores[0]
            ambiguity = max(0.0, 1.0 - min(source_margin, target_margin) / 0.12)
            conflict = _round(max(1.0 - support, ambiguity if mutual_best else 1.0))
            status = (
                "SUPPORTED"
                if mutual_best and support >= 0.75 and min(source_margin, target_margin) >= 0.08
                else ("REJECTED" if support < 0.35 else "UNCERTAIN")
            )
            candidate_content = {
                "source_tick": source_frame["tick"],
                "target_tick": target_frame["tick"],
                "source_observation_id": source_id,
                "target_observation_id": target_id,
            }
            candidate_id = (
                "candidate:correspondence:"
                + hashlib.sha256(canonical_bytes(candidate_content)).hexdigest()
            )
            source_center = _center(source["bounds"])
            target_center = _center(target["bounds"])
            evidence = [
                {"type": name, "effect": "support", "score": _round(value)}
                for name, value in raw[(source_id, target_id)].items()
            ] + [
                {"type": "source_margin", "effect": "support", "score": _round(source_margin)},
                {"type": "target_margin", "effect": "support", "score": _round(target_margin)},
                {"type": "ambiguity", "effect": "conflict", "score": _round(ambiguity)},
            ]
            inference_content = {
                **candidate_content,
                "candidate_id": candidate_id,
                "source_artifact_id": source_artifact_id,
                "support_score": support,
                "conflict_score": conflict,
                "status": status,
                "displacement": [
                    _round(target_center[0] - source_center[0]),
                    _round(target_center[1] - source_center[1]),
                ],
                "evidence": evidence,
                "policy_identity": POLICY_IDENTITY,
            }
            results.append(
                {
                    **inference_content,
                    "inference_id": "inference:correspondence:"
                    + hashlib.sha256(canonical_bytes(inference_content)).hexdigest(),
                }
            )
    return results


def _signals(source: dict[str, Any], target: dict[str, Any], diagonal: float) -> dict[str, float]:
    source_bounds, target_bounds = source["bounds"], target["bounds"]
    distance = math.dist(_center(source_bounds), _center(target_bounds))
    source_area = (source_bounds[2] - source_bounds[0]) * (source_bounds[3] - source_bounds[1])
    target_area = (target_bounds[2] - target_bounds[0]) * (target_bounds[3] - target_bounds[1])
    return {
        "centroid_proximity": max(0.0, 1.0 - distance / (0.25 * diagonal)),
        "size_similarity": min(source_area, target_area) / max(source_area, target_area),
        "color_similarity": _color_similarity(source["fill"], target["fill"]),
        "type_agreement": float(source["primitive_type"] == target["primitive_type"]),
    }


def _center(bounds: list[int | float]) -> tuple[float, float]:
    return ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)


def _color_similarity(left: str, right: str) -> float:
    a = tuple(int(left[index : index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(right[index : index + 2], 16) for index in (1, 3, 5))
    return max(
        0.0,
        1.0
        - math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True))) / math.sqrt(3 * 255**2),
    )


def _positive_number(value: Any) -> bool:
    return _finite_number(value) and value > 0


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _round(value: float) -> float:
    return float(format(value, ".12g"))
