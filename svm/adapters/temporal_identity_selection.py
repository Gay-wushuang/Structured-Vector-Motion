from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
)
from ..revisions import (
    ApplyTemporalIdentitySelectionChange,
    PromotedTemporalCorrespondence,
    PromoteTemporalIdentityChange,
    Transaction,
)
from .temporal_correspondence import EVIDENCE_MEDIA_TYPE, INFERENCE_IDENTITY, POLICY_IDENTITY
from .temporal_identity_promotion import TemporalIdentityPromotionAdapter

ADAPTER_ID = "adapter:temporal-identity-selection"
ADAPTER_VERSION = "0.1"
POLICY = "svm-temporal-identity-selection@0.1"
SCHEMA = "svm-temporal-identity-selection-0.1"
MEDIA = "application/vnd.svm.temporal-identity-selection+json;version=0.1"


class TemporalIdentitySelectionError(ValueError):
    pass


def _read_r0(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    if snapshot.kind != ArtifactKind.DERIVED or snapshot.media_type != EVIDENCE_MEDIA_TYPE:
        raise TemporalIdentitySelectionError("P2C requires DERIVED R0 evidence")
    try:
        payload = json.loads(snapshot.content)
        canonical = canonical_bytes(payload)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise TemporalIdentitySelectionError("R0 evidence must be canonical JSON") from exc
    if (
        not isinstance(payload, dict)
        or canonical != snapshot.content
        or payload.get("schema_version") != "svm-temporal-correspondence-0.1"
        or payload.get("identity") != INFERENCE_IDENTITY
        or payload.get("policy_identity") != POLICY_IDENTITY
        or not isinstance(payload.get("source_artifact_id"), str)
        or not isinstance(payload.get("candidates"), list)
    ):
        raise TemporalIdentitySelectionError("P2C requires canonical frozen R0 identity/policy")
    ticks = payload.get("frame_ticks")
    if (
        not isinstance(ticks, list)
        or len(ticks) != 2
        or any(type(tick) is not int or tick < 0 for tick in ticks)
        or ticks[0] >= ticks[1]
    ):
        raise TemporalIdentitySelectionError("R0 requires two increasing frame ticks")
    inference_ids: set[str] = set()
    supported_endpoints: set[tuple[int, str]] = set()
    for candidate in payload["candidates"]:
        if (
            not isinstance(candidate, dict)
            or any(
                not isinstance(candidate.get(field), str) or not candidate[field]
                for field in (
                    "candidate_id",
                    "inference_id",
                    "source_observation_id",
                    "target_observation_id",
                )
            )
            or candidate.get("status") not in ("SUPPORTED", "UNCERTAIN", "REJECTED")
            or candidate.get("policy_identity") != POLICY_IDENTITY
            or candidate.get("source_artifact_id") != payload["source_artifact_id"]
            or any(
                type(candidate.get(field)) is not int for field in ("source_tick", "target_tick")
            )
            or [candidate["source_tick"], candidate["target_tick"]] != ticks
        ):
            raise TemporalIdentitySelectionError("Invalid R0 candidate")
        inference_id = candidate["inference_id"]
        if inference_id in inference_ids:
            raise TemporalIdentitySelectionError("R0 inference IDs must be unique")
        inference_ids.add(inference_id)
        # Verify the recorded R0 content identities, without recomputing scores/status.
        subject = {
            key: candidate[key]
            for key in (
                "source_tick",
                "target_tick",
                "source_observation_id",
                "target_observation_id",
            )
        }
        inference = {key: value for key, value in candidate.items() if key != "inference_id"}
        if (
            candidate["candidate_id"]
            != "candidate:correspondence:" + hashlib.sha256(canonical_bytes(subject)).hexdigest()
            or inference_id
            != "inference:correspondence:" + hashlib.sha256(canonical_bytes(inference)).hexdigest()
        ):
            raise TemporalIdentitySelectionError("R0 candidate/inference content identity mismatch")
        if candidate["status"] == "SUPPORTED":
            endpoints = {
                (candidate["source_tick"], candidate["source_observation_id"]),
                (candidate["target_tick"], candidate["target_observation_id"]),
            }
            if supported_endpoints & endpoints:
                raise TemporalIdentitySelectionError("R0 SUPPORTED candidates must be disjoint")
            supported_endpoints.update(endpoints)
    return payload


def _supported(payload: dict[str, Any]) -> list[dict[str, Any]]:
    supported = [item for item in payload["candidates"] if item["status"] == "SUPPORTED"]
    if not supported:
        raise TemporalIdentitySelectionError("P2C abstains: zero SUPPORTED candidates")
    return supported


def _selection_payload(r0: ArtifactSnapshot, payload: dict[str, Any]) -> dict[str, Any]:
    supported = _supported(payload)
    candidates = [
        {key: item[key] for key in ("candidate_id", "inference_id", "status")}
        for item in payload["candidates"]
    ]
    return {
        "schema_version": SCHEMA,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "policy_identity": POLICY,
        "r0_evidence_artifact_id": r0.artifact_id,
        "source_observation_artifact_id": payload["source_artifact_id"],
        "frame_ticks": payload["frame_ticks"],
        "candidates": candidates,
        "selected_inference_ids": [item["inference_id"] for item in supported],
        "excluded_candidates": [item for item in candidates if item["status"] != "SUPPORTED"],
        "counts": {
            "total": len(candidates),
            **{
                status.lower(): sum(item["status"] == status for item in candidates)
                for status in ("SUPPORTED", "UNCERTAIN", "REJECTED")
            },
            "selected": len(supported),
        },
    }


def _provenance(r0: ArtifactSnapshot) -> dict[str, Any]:
    return {
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "policy_identity": POLICY,
        "r0_evidence_artifact_id": r0.artifact_id,
    }


class TemporalIdentitySelectionAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or request.options:
            raise TemporalIdentitySelectionError("P2C accepts document scope and no options")
        if len(request.artifact_ids) != 1:
            raise TemporalIdentitySelectionError("P2C requires exactly one accepted R0 artifact")
        references = [
            item
            for item in request.document.get("references", [])
            if item.get("id") == request.artifact_ids[0]
        ]
        if len(references) != 1:
            raise TemporalIdentitySelectionError("R0 evidence must already be accepted")
        reference = copy.deepcopy(references[0])
        r0 = artifacts.resolve_reference(reference)
        payload = _read_r0(r0)
        selected_ids = tuple(item["inference_id"] for item in _supported(payload))
        delegated = TemporalIdentityPromotionAdapter().propose(
            replace(request, options={"inference_ids": list(selected_ids)}), artifacts
        )
        if (
            len(delegated.transaction.changes) != 1
            or type(delegated.transaction.changes[0]) is not PromoteTemporalIdentityChange
            or delegated.required_artifact_ids != (r0.artifact_id,)
        ):
            raise TemporalIdentitySelectionError("Unexpected frozen R1 Proposal shape")
        promotion = delegated.transaction.changes[0]
        if not isinstance(promotion, PromoteTemporalIdentityChange):
            raise TemporalIdentitySelectionError("Unexpected frozen R1 Change")
        evidence = artifacts.import_bytes(
            canonical_bytes(_selection_payload(r0, payload)),
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance=_provenance(r0),
        )
        change = ApplyTemporalIdentitySelectionChange(
            evidence.document_reference(), reference, promotion, selected_ids, POLICY
        )
        generator = GeneratorProvenance(
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            engine="svm-all-supported-selection",
            engine_version=POLICY,
            parameters={"r0_evidence_artifact_id": r0.artifact_id},
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "change": asdict(change),
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:temporal-identity-selection:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:temporal-identity-selection:{digest}",
                (change,),
                "Select all SUPPORTED temporal correspondences and delegate promotion to R1",
            ),
            report=EvaluationReport(metrics={"selected_correspondences": float(len(selected_ids))}),
            preview=delegated.preview,
            preview_artifacts=(
                PreviewArtifact(evidence.artifact_id, evidence.content_hash, evidence.media_type),
            ),
            required_artifact_ids=tuple(item["id"] for item in change.references),
            notes=(
                "Automatic ALL-SUPPORTED selection; "
                "stable identity semantics delegated to frozen R1."
            ),
        )


def verify_change(
    change: ApplyTemporalIdentitySelectionChange, resolved: dict[str, ArtifactSnapshot]
) -> None:
    if change.policy_identity != POLICY or len(change.references) != 2:
        raise TemporalIdentitySelectionError("Invalid P2C policy or reference closure")
    r0 = resolved[change.r0_evidence_reference["id"]]
    payload = _read_r0(r0)
    supported = _supported(payload)
    expected_ids = tuple(item["inference_id"] for item in supported)
    if change.selected_inference_ids != expected_ids:
        raise TemporalIdentitySelectionError("P2C must select exactly ALL SUPPORTED in R0 order")
    promotion = change.delegated_promotion
    if (
        type(promotion) is not PromoteTemporalIdentityChange
        or promotion.references != (change.r0_evidence_reference,)
        or len(promotion.correspondences) != len(supported)
    ):
        raise TemporalIdentitySelectionError(
            "Delegated promotion must bind every selected candidate"
        )
    for record, candidate in zip(promotion.correspondences, supported, strict=True):
        if (
            type(record) is not PromotedTemporalCorrespondence
            or any(
                getattr(record, key) != candidate[key]
                for key in (
                    "inference_id",
                    "candidate_id",
                    "source_tick",
                    "source_observation_id",
                    "target_tick",
                    "target_observation_id",
                )
            )
            or record.evidence_artifact_id != r0.artifact_id
            or record.evidence_policy_identity != POLICY_IDENTITY
        ):
            raise TemporalIdentitySelectionError(
                "Delegated promotion order/content differs from R0"
            )
    evidence = resolved[change.selection_evidence_reference["id"]]
    if (
        evidence.kind != ArtifactKind.DERIVED
        or evidence.media_type != MEDIA
        or evidence.provenance != _provenance(r0)
        or evidence.content != canonical_bytes(_selection_payload(r0, payload))
    ):
        raise TemporalIdentitySelectionError("P2C selection evidence does not reproduce")
