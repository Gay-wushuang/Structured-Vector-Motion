from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, GeneratorProvenance, PreviewArtifact, Proposal
from ..revisions import AttachSparseObservationPolicyChange, PromoteTemporalIdentityChange
from .camera_compensation import _accepted_reference, _id, _json
from .temporal_correspondence import _infer, read_primitive_observations
from .temporal_identity_promotion import TemporalIdentityPromotionAdapter

POLICY = "svm-one-internal-missing-occurrence@0.1"
MEDIA_TYPE = "application/vnd.svm.sparse-observation-policy+json;version=0.1"


def observed_schedule(schedule: Any, missing_tick: Any) -> list[int]:
    if (
        not isinstance(schedule, list)
        or len(schedule) < 3
        or any(type(t) is not int or t < 0 for t in schedule)
        or schedule != sorted(set(schedule))
        or type(missing_tick) is not int
        or missing_tick not in schedule[1:-1]
    ):
        raise ValueError(
            "Sparse recovery requires one explicit internal missing schedule occurrence"
        )
    return [t for t in schedule if t != missing_tick]


class SparseTemporalIdentityPromotionAdapter:
    """Guard one explicit gap; delegate identity creation to the frozen R1 adapter."""

    adapter_id = "adapter:sparse-temporal-identity-promotion"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if set(request.options) != {"inference_ids", "expected_tick_schedule", "missing_tick"}:
            raise ValueError(
                "Sparse promotion requires explicit inference, schedule and missing tick"
            )
        schedule, missing = (
            request.options["expected_tick_schedule"],
            request.options["missing_tick"],
        )
        observed_schedule(schedule, missing)
        ordinary = TemporalIdentityPromotionAdapter().propose(
            replace(request, options={"inference_ids": request.options["inference_ids"]}), artifacts
        )
        promotion_change = ordinary.transaction.changes[0]
        if not isinstance(promotion_change, PromoteTemporalIdentityChange):
            raise ValueError("Sparse promotion requires the registered R1 Change")
        promoted = promotion_change.correspondences
        if len(promoted) != 1:
            raise ValueError("Sparse recovery permits one explicitly selected gap correspondence")
        correspondence = artifacts.resolve_reference(promotion_change.references[0])
        observation_ref = _accepted_reference(
            request.document, _json(correspondence)["source_artifact_id"]
        )
        observation = artifacts.resolve_reference(observation_ref)
        identity_id = promoted[0].stable_identity_id
        payload = policy_payload(
            schedule, missing, identity_id, promoted[0].inference_id, correspondence, observation
        )
        evidence = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=policy_provenance(payload),
        )
        after = ordinary.transaction.apply(request.document)
        identity = next(i for i in after["temporal_identities"] if i["id"] == identity_id)
        change = AttachSparseObservationPolicyChange(
            evidence.document_reference(),
            correspondence.document_reference(),
            observation_ref,
            copy.deepcopy(schedule),
            missing,
            promoted[0].inference_id,
            identity,
            request.base_revision_id,
        )
        change.apply(after)
        digest = _id(
            "sparse-promotion", {"base": request.base_revision_id, "policy": evidence.artifact_id}
        )
        return replace(
            ordinary,
            proposal_id="proposal:" + digest,
            generator=GeneratorProvenance(
                self.adapter_id,
                self.adapter_version,
                "svm-sparse-promotion",
                POLICY,
                copy.deepcopy(request.options),
            ),
            transaction=replace(
                ordinary.transaction,
                transaction_id="transaction:" + digest,
                changes=(*ordinary.transaction.changes, change),
            ),
            required_artifact_ids=(
                correspondence.artifact_id,
                observation.artifact_id,
                evidence.artifact_id,
            ),
            preview_artifacts=(
                PreviewArtifact(evidence.artifact_id, evidence.content_hash, MEDIA_TYPE),
            ),
            notes="Explicit one-occurrence gap; no missing observation or binding is created",
        )


def policy_payload(
    schedule: list[int],
    missing: int,
    identity_id: str,
    inference_id: str,
    correspondence: ArtifactSnapshot,
    observation: ArtifactSnapshot,
) -> dict:
    visible = observed_schedule(schedule, missing)
    r0 = _json(correspondence)
    observations = read_primitive_observations(observation.content)
    if r0.get("source_artifact_id") != observation.artifact_id or r0.get("candidates") != _infer(
        observations, observation.artifact_id
    ):
        raise ValueError("Sparse gap correspondence does not match formal inference")
    candidates = [c for c in r0["candidates"] if c["inference_id"] == inference_id]
    index = schedule.index(missing)
    if (
        len(candidates) != 1
        or candidates[0]["status"] != "SUPPORTED"
        or (candidates[0]["source_tick"], candidates[0]["target_tick"])
        != (schedule[index - 1], schedule[index + 1])
    ):
        raise ValueError("Only a SUPPORTED gap spanning one missing occurrence may be promoted")
    candidate = candidates[0]
    return {
        "schema_version": "svm-sparse-observation-policy-0.1",
        "policy_identity": POLICY,
        "expected_tick_schedule": schedule,
        "missing_tick": missing,
        "observed_ticks": visible,
        "max_missing_occurrences": 1,
        "temporal_identity_id": identity_id,
        "inference_id": inference_id,
        "source_correspondence_artifact_id": correspondence.artifact_id,
        "source_observation_artifact_id": observation.artifact_id,
        "source_tick": candidate["source_tick"],
        "target_tick": candidate["target_tick"],
        "source_observation_id": candidate["source_observation_id"],
        "target_observation_id": candidate["target_observation_id"],
    }


def policy_provenance(payload: dict) -> dict:
    return {
        "adapter_id": SparseTemporalIdentityPromotionAdapter.adapter_id,
        "policy_identity": POLICY,
        "source_correspondence_artifact_id": payload["source_correspondence_artifact_id"],
        "source_observation_artifact_id": payload["source_observation_artifact_id"],
        "temporal_identity_id": payload["temporal_identity_id"],
        "expected_tick_schedule": payload["expected_tick_schedule"],
        "missing_tick": payload["missing_tick"],
    }


def read_policy(snapshot: ArtifactSnapshot) -> dict:
    payload = _json(snapshot)
    if (
        snapshot.kind != ArtifactKind.DERIVED
        or snapshot.media_type != MEDIA_TYPE
        or payload.get("schema_version") != "svm-sparse-observation-policy-0.1"
        or payload.get("policy_identity") != POLICY
        or payload.get("max_missing_occurrences") != 1
        or canonical_bytes(payload) != snapshot.content
        or snapshot.provenance != policy_provenance(payload)
        or payload.get("observed_ticks")
        != observed_schedule(payload.get("expected_tick_schedule"), payload.get("missing_tick"))
    ):
        raise ValueError("Invalid accepted sparse observation policy")
    return payload


def verify_sparse_policy_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    snapshot = resolved[change.evidence_reference["id"]]
    expected = policy_payload(
        change.expected_tick_schedule,
        change.missing_tick,
        change.temporal_identity["id"],
        change.inference_id,
        resolved[change.correspondence_reference["id"]],
        resolved[change.observation_reference["id"]],
    )
    read_policy(snapshot)
    if snapshot.content != canonical_bytes(expected):
        raise ValueError("Sparse observation policy does not match its explicit gap contract")
    bindings = {(i["tick"], i["observation_id"]) for i in change.temporal_identity["bindings"]}
    if (
        any(t not in expected["observed_ticks"] for t, _ in bindings)
        or not {
            (expected["source_tick"], expected["source_observation_id"]),
            (expected["target_tick"], expected["target_observation_id"]),
        }
        <= bindings
    ):
        raise ValueError(
            "Sparse identity must contain only observed bindings and both gap endpoints"
        )
