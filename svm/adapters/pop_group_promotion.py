from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactResolver
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    GroupDefinitionPreview,
    Proposal,
    ProposalPreview,
)
from ..revisions import GROUP_PROMOTION_IDENTITY, PromotedGroup, PromoteGroupsChange, Transaction
from .pop_group_candidates import INFERENCE_IDENTITY, MEDIA_TYPE


class POPGroupPromotionError(ValueError):
    pass


class POPGroupPromotionAdapter:
    adapter_id = "adapter:pop-group-promotion"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise POPGroupPromotionError("Group promotion scope must be empty or document")
        if len(request.artifact_ids) != 1:
            raise POPGroupPromotionError("Group promotion requires one accepted inference Artifact")
        unknown = set(request.options) - {"candidate_ids"}
        candidate_ids = request.options.get("candidate_ids")
        if (
            unknown
            or not isinstance(candidate_ids, list)
            or not candidate_ids
            or any(not isinstance(item, str) for item in candidate_ids)
            or len(candidate_ids) != len(set(candidate_ids))
        ):
            raise POPGroupPromotionError("candidate_ids must be an explicit non-empty unique list")
        reference = _accepted_reference(request.document, request.artifact_ids[0])
        snapshot = artifacts.resolve_reference(reference)
        if snapshot.kind != ArtifactKind.DERIVED or snapshot.media_type != MEDIA_TYPE:
            raise POPGroupPromotionError("Group promotion requires Q v1 inference evidence")
        payload = _payload(snapshot.content)
        if payload.get("identity") != INFERENCE_IDENTITY:
            raise POPGroupPromotionError("Group promotion inference identity mismatch")
        source_document = json.loads(canonical_bytes(request.document))
        source_document["references"] = [
            item
            for item in source_document["references"]
            if item.get("import_metadata", {}).get("provenance", {}).get("adapter_id")
            != "adapter:pop-group-candidates"
        ]
        source_hash = f"sha256:{hashlib.sha256(canonical_bytes(source_document)).hexdigest()}"
        if payload.get("source_document_hash") != source_hash:
            raise POPGroupPromotionError("STALE_CANDIDATE: inference source Document has changed")
        by_id = {
            item.get("candidate_id"): item
            for item in payload.get("candidates", [])
            if isinstance(item, dict)
        }
        selected = []
        for candidate_id in candidate_ids:
            candidate = by_id.get(candidate_id)
            if candidate is None:
                raise POPGroupPromotionError(f"Unknown GroupCandidate {candidate_id}")
            if candidate.get("status") != "SUPPORTED":
                raise POPGroupPromotionError("Only a SUPPORTED GroupCandidate may be promoted")
            selected.append(candidate)
        existing = {
            (item["provenance"]["inference_artifact_id"], item["provenance"]["candidate_id"])
            for item in request.document.get("groups", [])
        }
        promoted = []
        for candidate in selected:
            key = (snapshot.artifact_id, candidate["candidate_id"])
            if key in existing:
                raise POPGroupPromotionError("GroupCandidate is already promoted")
            promoted.append(
                PromotedGroup(
                    inference_artifact_id=snapshot.artifact_id,
                    candidate_id=candidate["candidate_id"],
                    inference_id=candidate["inference_id"],
                    members=tuple(candidate["members"]),
                    source_document_hash=payload["source_document_hash"],
                )
            )
        change = PromoteGroupsChange(tuple(promoted), (reference,))
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="svm-explicit-group-promoter",
            engine_version=GROUP_PROMOTION_IDENTITY,
            parameters={
                "inference_artifact_id": snapshot.artifact_id,
                "candidate_ids": candidate_ids,
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "groups": [item.to_definition() for item in promoted],
                }
            )
        ).hexdigest()[:16]
        previews = tuple(
            GroupDefinitionPreview(
                group_id=item.group_id(),
                members=item.members,
                kind="explicit-group",
                candidate_id=item.candidate_id,
                inference_id=item.inference_id,
                inference_artifact_id=item.inference_artifact_id,
            )
            for item in promoted
        )
        return Proposal(
            proposal_id=f"proposal:pop-group-promotion:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:pop-group-promotion:{digest}",
                changes=(change,),
                message="Promote explicitly selected GroupCandidates",
            ),
            report=EvaluationReport(metrics={"promoted_groups": float(len(promoted))}),
            preview=ProposalPreview(
                proposed_render_stack=tuple(request.document["presentation"]["render_stack"]),
                group_definitions=previews,
            ),
            required_artifact_ids=(snapshot.artifact_id,),
            notes="Explicit promotion creates unlabeled Group Definitions only",
        )


def _accepted_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise POPGroupPromotionError("Inference Artifact must already be accepted")
    return matches[0]


def _payload(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise POPGroupPromotionError("Inference Artifact is invalid JSON") from exc
    if not isinstance(payload, dict) or canonical_bytes(payload) != content:
        raise POPGroupPromotionError("Inference Artifact must be canonical JSON")
    return payload
