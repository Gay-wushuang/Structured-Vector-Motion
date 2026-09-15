from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import ArtifactKind, ArtifactResolver
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    Proposal,
    ProposalPreview,
)
from ..revisions import (
    TEMPORAL_IDENTITY_PROMOTION_IDENTITY,
    PromotedTemporalCorrespondence,
    PromoteTemporalIdentityChange,
    Transaction,
    temporal_identity_id,
)
from .temporal_correspondence import EVIDENCE_MEDIA_TYPE, INFERENCE_IDENTITY, POLICY_IDENTITY


class TemporalIdentityPromotionError(ValueError):
    pass


@dataclass(frozen=True)
class TemporalIdentityDefinitionPreview:
    stable_identity_id: str
    bindings: tuple[tuple[int, str], ...]
    candidate_id: str
    inference_id: str
    evidence_artifact_id: str


@dataclass(frozen=True)
class TemporalIdentityPromotionPreview(ProposalPreview):
    temporal_identities: tuple[TemporalIdentityDefinitionPreview, ...] = ()


class TemporalIdentityPromotionAdapter:
    adapter_id = "adapter:temporal-identity-promotion"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise TemporalIdentityPromotionError(
                "Temporal identity promotion scope must be empty or document"
            )
        if len(request.artifact_ids) != 1:
            raise TemporalIdentityPromotionError(
                "Temporal identity promotion requires one accepted evidence Artifact"
            )
        unknown = set(request.options) - {"inference_ids"}
        inference_ids = request.options.get("inference_ids")
        if (
            unknown
            or not isinstance(inference_ids, list)
            or not inference_ids
            or any(not isinstance(item, str) for item in inference_ids)
            or len(inference_ids) != len(set(inference_ids))
        ):
            raise TemporalIdentityPromotionError(
                "inference_ids must be an explicit non-empty unique list"
            )
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        if snapshot.kind != ArtifactKind.DERIVED or snapshot.media_type != EVIDENCE_MEDIA_TYPE:
            raise TemporalIdentityPromotionError(
                "Temporal identity promotion requires accepted R0 evidence"
            )
        payload = _payload(snapshot.content)
        if (
            payload.get("identity") != INFERENCE_IDENTITY
            or payload.get("policy_identity") != POLICY_IDENTITY
        ):
            raise TemporalIdentityPromotionError("Temporal correspondence identity mismatch")
        by_id = {
            item.get("inference_id"): item
            for item in payload.get("candidates", [])
            if isinstance(item, dict)
        }
        selected: list[dict[str, Any]] = []
        for inference_id in inference_ids:
            candidate = by_id.get(inference_id)
            if candidate is None:
                raise TemporalIdentityPromotionError(
                    f"Unknown temporal correspondence inference {inference_id}"
                )
            if candidate.get("status") != "SUPPORTED":
                raise TemporalIdentityPromotionError(
                    "Only a SUPPORTED temporal correspondence may be promoted"
                )
            selected.append(candidate)

        observation_owner = {
            (binding["tick"], binding["observation_id"]): identity["id"]
            for identity in request.document.get("temporal_identities", [])
            for binding in identity["bindings"]
        }
        promoted: list[PromotedTemporalCorrespondence] = []
        previews: list[TemporalIdentityDefinitionPreview] = []
        for candidate in selected:
            source_key = (candidate["source_tick"], candidate["source_observation_id"])
            target_key = (candidate["target_tick"], candidate["target_observation_id"])
            owners = {
                observation_owner[key]
                for key in (source_key, target_key)
                if key in observation_owner
            }
            if len(owners) > 1:
                raise TemporalIdentityPromotionError(
                    "TEMPORAL_IDENTITY_CONFLICT: observations have different stable identities"
                )
            stable_id = next(iter(owners), None) or temporal_identity_id(
                snapshot.artifact_id, candidate["candidate_id"]
            )
            record = PromotedTemporalCorrespondence(
                evidence_artifact_id=snapshot.artifact_id,
                candidate_id=candidate["candidate_id"],
                inference_id=candidate["inference_id"],
                source_tick=candidate["source_tick"],
                source_observation_id=candidate["source_observation_id"],
                target_tick=candidate["target_tick"],
                target_observation_id=candidate["target_observation_id"],
                evidence_policy_identity=payload["policy_identity"],
                stable_identity_id=stable_id,
            )
            promoted.append(record)
            for key in (source_key, target_key):
                observation_owner[key] = stable_id
            previews.append(
                TemporalIdentityDefinitionPreview(
                    stable_identity_id=stable_id,
                    bindings=tuple(
                        (binding["tick"], binding["observation_id"])
                        for binding in record.bindings()
                    ),
                    candidate_id=record.candidate_id,
                    inference_id=record.inference_id,
                    evidence_artifact_id=record.evidence_artifact_id,
                )
            )
        change = PromoteTemporalIdentityChange(tuple(promoted), (reference,))
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="svm-explicit-temporal-identity-promoter",
            engine_version=TEMPORAL_IDENTITY_PROMOTION_IDENTITY,
            parameters={
                "evidence_artifact_id": snapshot.artifact_id,
                "inference_ids": inference_ids,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "promotions": [asdict(item) for item in promoted],
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:temporal-identity-promotion:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:temporal-identity-promotion:{digest}",
                changes=(change,),
                message="Promote explicitly selected temporal correspondences",
            ),
            report=EvaluationReport(metrics={"promoted_correspondences": float(len(promoted))}),
            preview=TemporalIdentityPromotionPreview(
                proposed_render_stack=tuple(request.document["presentation"]["render_stack"]),
                temporal_identities=tuple(previews),
            ),
            required_artifact_ids=(snapshot.artifact_id,),
            notes="Explicit promotion creates stable observation identity bindings only",
        )


def _accepted_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise TemporalIdentityPromotionError(
            "Temporal correspondence evidence must already be accepted"
        )
    return matches[0]


def _payload(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TemporalIdentityPromotionError(
            "Temporal correspondence evidence is invalid JSON"
        ) from exc
    if not isinstance(payload, dict) or canonical_bytes(payload) != content:
        raise TemporalIdentityPromotionError(
            "Temporal correspondence evidence must be canonical JSON"
        )
    return payload
