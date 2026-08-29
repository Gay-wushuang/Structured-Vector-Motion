from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactResolver
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EntityDiffPreview,
    EvaluationReport,
    GeneratorProvenance,
    Proposal,
    ProposalPreview,
)
from ..revisions import PromoteComponentsChange, Transaction

PROMOTION_IDENTITY = "svm-component-promotion@0.1"
ANALYSIS_SCHEMA = "svm-component-analysis-0.2"
ANALYSIS_IDENTITY = "svm-opencv-components@0.2"
ANALYSIS_MEDIA_TYPE = "application/vnd.svm.component-analysis+json"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANDIDATE_ID = re.compile(r"^candidate:component-[0-9]{4}$")
_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ComponentPromotionError(ValueError):
    pass


class ComponentPromotionAdapter:
    adapter_id = "adapter:component-promotion"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise ComponentPromotionError("Component promotion scope must be empty or document")
        if len(request.artifact_ids) != 1:
            raise ComponentPromotionError(
                "Component promotion requires exactly one accepted component-analysis Artifact"
            )
        reference = _accepted_analysis_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        if snapshot.kind != ArtifactKind.DERIVED or snapshot.media_type != ANALYSIS_MEDIA_TYPE:
            raise ComponentPromotionError(
                "Component promotion input must be a Derived component-analysis Artifact"
            )
        _validate_analysis_provenance(snapshot.provenance)
        payload = _parse_analysis(snapshot.content)
        candidates = _validate_analysis_payload(payload, request.document)
        selected = _select_candidates(candidates, request.options)
        namespace = request.options.get("namespace", "region")
        if not isinstance(namespace, str) or _NAMESPACE.fullmatch(namespace) is None:
            raise ComponentPromotionError(
                "namespace must contain lowercase letters, digits, underscores, or hyphens"
            )
        unknown_options = sorted(set(request.options) - {"candidate_ids", "namespace"})
        if unknown_options:
            raise ComponentPromotionError(
                f"Unknown component promotion option(s): {', '.join(unknown_options)}"
            )

        existing_ids = {entity["id"] for entity in request.document["entities"]}
        promoted_keys = {
            (provenance.get("artifact_id"), provenance.get("candidate_id"))
            for entity in request.document["entities"]
            if isinstance((provenance := entity.get("provenance")), dict)
            and provenance.get("type") == "PromotedComponent"
        }
        entities: list[dict[str, Any]] = []
        previews: list[EntityDiffPreview] = []
        for candidate in selected:
            key = (snapshot.artifact_id, candidate["candidate_id"])
            if key in promoted_keys:
                raise ComponentPromotionError(
                    f"Candidate {candidate['candidate_id']} is already promoted"
                )
            entity_id = _entity_id(namespace, snapshot.artifact_id, candidate)
            if entity_id in existing_ids:
                raise ComponentPromotionError(f"Promoted Entity ID collision: {entity_id}")
            entity = {
                "id": entity_id,
                "name": f"Region {candidate['candidate_id'].rsplit('-', 1)[1]}",
                "semantic_tags": ["region", "promoted-component"],
                "provenance": {
                    "type": "PromotedComponent",
                    "artifact_id": snapshot.artifact_id,
                    "candidate_id": candidate["candidate_id"],
                    "component_digest": candidate["component_digest"],
                },
            }
            entities.append(entity)
            previews.append(
                EntityDiffPreview(
                    status="added",
                    entity_id=None,
                    proposed_entity_id=entity_id,
                    after_bounds=tuple(candidate["bounds"]),
                )
            )

        parameters = {
            "promotion_identity": PROMOTION_IDENTITY,
            "analysis_schema": ANALYSIS_SCHEMA,
            "analysis_artifact_id": snapshot.artifact_id,
            "candidate_ids": [candidate["candidate_id"] for candidate in selected],
            "namespace": namespace,
        }
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="svm-component-analysis-interpreter",
            engine_version=PROMOTION_IDENTITY,
            parameters=parameters,
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "generator": asdict(generator),
                    "entities": entities,
                    "reference": reference,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:component-promotion:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:component-promotion:{digest}",
                changes=(
                    PromoteComponentsChange(
                        entities=tuple(entities),
                        references=(reference,),
                    ),
                ),
                message="Promote accepted component-analysis candidates to Entities",
            ),
            report=EvaluationReport(metrics={"promoted_components": float(len(entities))}),
            preview=ProposalPreview(
                entity_diffs=tuple(previews),
                proposed_render_stack=tuple(request.document["presentation"]["render_stack"]),
            ),
            required_artifact_ids=(snapshot.artifact_id,),
            confidence=None,
            notes="Explicit promotion creates neutral, non-rendered Region Entities",
        )


def _accepted_analysis_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [
        reference
        for reference in document.get("references", [])
        if reference.get("id") == artifact_id
    ]
    if len(matches) != 1:
        raise ComponentPromotionError(
            "Component-analysis Artifact must already be accepted by the base Document"
        )
    if matches[0].get("media_type") != ANALYSIS_MEDIA_TYPE:
        raise ComponentPromotionError("Accepted Artifact is not component-analysis JSON")
    return matches[0]


def _validate_analysis_provenance(provenance: dict[str, Any]) -> None:
    parameters = provenance.get("parameters")
    if (
        provenance.get("derived_type") != "component-analysis"
        or not isinstance(parameters, dict)
        or parameters.get("analysis_identity") != ANALYSIS_IDENTITY
    ):
        raise ComponentPromotionError(
            f"Component-analysis provenance must declare {ANALYSIS_IDENTITY}"
        )


def _parse_analysis(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComponentPromotionError(
            "Component-analysis Artifact is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict) or canonical_bytes(payload) != content:
        raise ComponentPromotionError("Component-analysis Artifact must use canonical JSON bytes")
    return payload


def _validate_analysis_payload(
    payload: dict[str, Any], document: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    expected_keys = {
        "schema_version",
        "source_artifact_id",
        "source_content_hash",
        "image",
        "threshold",
        "connectivity",
        "binary_mask_artifact_id",
        "components",
    }
    if set(payload) != expected_keys or payload.get("schema_version") != ANALYSIS_SCHEMA:
        raise ComponentPromotionError(f"Component-analysis must conform to {ANALYSIS_SCHEMA}")
    references = {reference["id"]: reference for reference in document["references"]}
    source = references.get(payload.get("source_artifact_id"))
    mask = references.get(payload.get("binary_mask_artifact_id"))
    if source is None or source.get("content_hash") != payload.get("source_content_hash"):
        raise ComponentPromotionError("Component-analysis source Artifact is not accepted")
    if mask is None or mask.get("media_type") != "image/png":
        raise ComponentPromotionError("Component-analysis binary mask Artifact is not accepted")
    image = payload.get("image")
    if not isinstance(image, dict) or set(image) != {"width", "height"}:
        raise ComponentPromotionError("Component-analysis image dimensions are invalid")
    width, height = image.get("width"), image.get("height")
    if not _positive_int(width) or not _positive_int(height):
        raise ComponentPromotionError("Component-analysis image dimensions are invalid")
    threshold = payload.get("threshold")
    if (
        not isinstance(threshold, dict)
        or set(threshold) != {"value", "foreground", "comparison"}
        or not isinstance(threshold.get("value"), int)
        or isinstance(threshold.get("value"), bool)
        or not 0 <= threshold["value"] <= 255
        or (threshold.get("foreground"), threshold.get("comparison"))
        not in {("dark", "<="), ("light", ">=")}
        or payload.get("connectivity") != 8
    ):
        raise ComponentPromotionError("Component-analysis threshold semantics are invalid")
    components = payload.get("components")
    if not isinstance(components, list):
        raise ComponentPromotionError("Component-analysis components must be an array")
    validated: list[dict[str, Any]] = []
    for index, candidate in enumerate(components, start=1):
        if not isinstance(candidate, dict) or set(candidate) != {
            "candidate_id",
            "bounds",
            "pixel_area",
            "centroid",
            "component_digest",
        }:
            raise ComponentPromotionError("Component-analysis candidate fields are invalid")
        expected_id = f"candidate:component-{index:04d}"
        if (
            candidate.get("candidate_id") != expected_id
            or _CANDIDATE_ID.fullmatch(expected_id) is None
        ):
            raise ComponentPromotionError("Component-analysis candidate IDs are not canonical")
        bounds = candidate.get("bounds")
        if (
            not isinstance(bounds, list)
            or len(bounds) != 4
            or any(not isinstance(value, int) or isinstance(value, bool) for value in bounds)
            or not (0 <= bounds[0] < bounds[2] <= width)
            or not (0 <= bounds[1] < bounds[3] <= height)
        ):
            raise ComponentPromotionError(f"Candidate {expected_id} bounds are invalid")
        area = candidate.get("pixel_area")
        if not _positive_int(area) or area > (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]):
            raise ComponentPromotionError(f"Candidate {expected_id} pixel area is invalid")
        centroid = candidate.get("centroid")
        if (
            not isinstance(centroid, list)
            or len(centroid) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in centroid
            )
            or not (bounds[0] <= centroid[0] < bounds[2])
            or not (bounds[1] <= centroid[1] < bounds[3])
        ):
            raise ComponentPromotionError(f"Candidate {expected_id} centroid is invalid")
        if (
            not isinstance(candidate.get("component_digest"), str)
            or _DIGEST.fullmatch(candidate["component_digest"]) is None
        ):
            raise ComponentPromotionError(f"Candidate {expected_id} digest is invalid")
        validated.append(candidate)
    ordering = [
        (
            candidate["bounds"][1],
            candidate["bounds"][0],
            candidate["bounds"][3],
            candidate["bounds"][2],
            candidate["pixel_area"],
            candidate["centroid"],
            candidate["component_digest"],
        )
        for candidate in validated
    ]
    if ordering != sorted(ordering):
        raise ComponentPromotionError("Component-analysis candidates are not canonically ordered")
    return tuple(validated)


def _select_candidates(
    candidates: tuple[dict[str, Any], ...], options: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    selected_ids = options.get("candidate_ids")
    if (
        not isinstance(selected_ids, list)
        or not selected_ids
        or any(not isinstance(value, str) for value in selected_ids)
        or len(selected_ids) != len(set(selected_ids))
    ):
        raise ComponentPromotionError("candidate_ids must be a non-empty unique string array")
    known = {candidate["candidate_id"]: candidate for candidate in candidates}
    missing = sorted(set(selected_ids) - set(known))
    if missing:
        raise ComponentPromotionError(f"Unknown component candidate(s): {', '.join(missing)}")
    selected = set(selected_ids)
    return tuple(candidate for candidate in candidates if candidate["candidate_id"] in selected)


def _entity_id(namespace: str, artifact_id: str, candidate: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_bytes(
            {
                "promotion_identity": PROMOTION_IDENTITY,
                "artifact_id": artifact_id,
                "candidate_id": candidate["candidate_id"],
                "component_digest": candidate["component_digest"],
            }
        )
    ).hexdigest()[:16]
    return f"entity:{namespace}-{digest}"


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
