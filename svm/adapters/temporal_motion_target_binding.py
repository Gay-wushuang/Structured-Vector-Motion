from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactRepository
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    GeneratorProvenance,
    MotionTargetBindingPreview,
    Proposal,
    ProposalPreview,
)
from ..revisions import (
    MOTION_TARGET_BINDING_POLICY_IDENTITY,
    BindTemporalMotionTargetChange,
    Transaction,
    motion_target_binding_id,
)


class TemporalMotionTargetBindingError(ValueError):
    pass


class TemporalMotionTargetBindingAdapter:
    adapter_id = "adapter:temporal-motion-target-binding"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        del artifacts
        if request.scope not in {(), ("document",)}:
            raise TemporalMotionTargetBindingError("Motion target binding scope must be document")
        if set(request.options) != {"temporal_identity_id", "group_id"}:
            raise TemporalMotionTargetBindingError(
                "Explicit temporal_identity_id and group_id are required"
            )
        identity_id = request.options["temporal_identity_id"]
        group_id = request.options["group_id"]
        if not isinstance(identity_id, str) or not isinstance(group_id, str):
            raise TemporalMotionTargetBindingError("Motion target IDs must be strings")
        identities = [
            item
            for item in request.document.get("temporal_identities", [])
            if item.get("id") == identity_id
        ]
        if len(identities) != 1:
            raise TemporalMotionTargetBindingError("Motion target requires one temporal identity")
        groups = [item for item in request.document.get("groups", []) if item.get("id") == group_id]
        if len(groups) != 1:
            raise TemporalMotionTargetBindingError("Motion target requires one Group")
        if not isinstance(groups[0].get("transform"), dict):
            raise TemporalMotionTargetBindingError(
                "Motion target Group requires a legal static transform"
            )
        identity = copy.deepcopy(identities[0])
        group = copy.deepcopy(groups[0])
        binding = _binding(request.base_revision_id, identity, group)
        change = BindTemporalMotionTargetChange(binding, identity, group, request.base_revision_id)
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "svm-explicit-motion-target-binding",
            MOTION_TARGET_BINDING_POLICY_IDENTITY,
            {"temporal_identity_id": identity_id, "group_id": group_id},
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "binding": binding,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:temporal-motion-target-binding:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:temporal-motion-target-binding:{digest}",
                (change,),
                "Bind temporal identity to Group motion target",
            ),
            preview=ProposalPreview(
                motion_target_bindings=(
                    MotionTargetBindingPreview(
                        binding["id"],
                        identity_id,
                        "group",
                        group_id,
                        MOTION_TARGET_BINDING_POLICY_IDENTITY,
                    ),
                )
            ),
            notes="Explicit target binding only; no Track or Keyframe is created",
        )


def _binding(
    source_revision_id: str, identity: dict[str, Any], group: dict[str, Any]
) -> dict[str, Any]:
    identity_id = identity["id"]
    group_id = group["id"]
    return {
        "id": motion_target_binding_id(identity_id, group_id),
        "temporal_identity_id": identity_id,
        "target": {"kind": "group", "group_id": group_id},
        "policy_identity": MOTION_TARGET_BINDING_POLICY_IDENTITY,
        "provenance": {
            "source_revision_id": source_revision_id,
            "temporal_identity_snapshot_hash": "sha256:"
            + hashlib.sha256(canonical_bytes(identity)).hexdigest(),
            "group_snapshot_hash": "sha256:" + hashlib.sha256(canonical_bytes(group)).hexdigest(),
        },
    }
