from __future__ import annotations

import copy
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, Proposal
from ..revisions import AttachSparseCompensatedMotionChange
from .camera_compensation import (
    CompensatedMotionPreview,
    _accepted_reference,
    _compensated_payloads,
    _compose,
    _id,
    _inverse,
    _one_standard_similarity,
    _one_standard_translation,
    _proposal,
    _static_anchor,
)
from .camera_consensus import MEDIA_TYPE as CAMERA_CONSENSUS_MEDIA_TYPE
from .camera_consensus import canonical_anchor_ids, one_camera_evidence
from .observed_camera_tracks import recover_camera_samples
from .sparse_observation import MEDIA_TYPE as GAP_MEDIA_TYPE
from .sparse_observation import read_policy

POLICY = "svm-sparse-camera-similarity-compensation@0.1"
TRANSLATION_MEDIA_TYPE = (
    "application/vnd.svm.camera-compensated-translation-motion+json;version=0.2"
)
SIMILARITY_MEDIA_TYPE = "application/vnd.svm.camera-compensated-similarity-motion+json;version=0.2"
ADAPTER_ID = "adapter:sparse-camera-compensated-motion"


def camera_view_state_by_tick(camera: dict) -> dict[int, list[float]]:
    """Read exact absolute endpoints; never sample or interpolate the Camera chain."""
    recover_camera_samples(camera["intervals"])
    states = {}
    for interval in camera["intervals"]:
        states[interval["source_tick"]] = interval["source_view_transform"]
        states[interval["target_tick"]] = interval["target_view_transform"]
    return states


def camera_spans(
    camera: dict, camera_id: str, policy: dict, translation: dict, similarity: dict
) -> list[dict]:
    states = camera_view_state_by_tick(camera)
    if list(states) != policy["expected_tick_schedule"]:
        raise ValueError("Complete Camera chain must match the explicit sparse schedule")
    ticks = policy["observed_ticks"]
    pairs = list(zip(ticks[:-1], ticks[1:], strict=True))
    for evidence in (translation, similarity):
        if (
            evidence["temporal_identity_id"] != policy["temporal_identity_id"]
            or [(i["source_tick"], i["target_tick"]) for i in evidence["intervals"]] != pairs
        ):
            raise ValueError("Target evidence must share the exact observed sparse interval chain")
        gap = next(i for i in evidence["intervals"] if i["source_tick"] == policy["source_tick"])
        if (
            gap["correspondence_inference_id"] != policy["inference_id"]
            or gap["correspondence_evidence_artifact_id"]
            != policy["source_correspondence_artifact_id"]
            or (
                "source_geometry_artifact_id" in gap
                and gap["source_geometry_artifact_id"] != policy["source_observation_artifact_id"]
            )
        ):
            raise ValueError(
                "Sparse gap evidence must retain the policy's exact R0/geometry lineage"
            )
    spans = []
    for source, target in pairs:
        content = {
            "source_tick": source,
            "target_tick": target,
            "source_view_transform": states[source],
            "target_view_transform": states[target],
            "relative_view_transform": list(_compose(states[target], _inverse(states[source]))),
            "source_camera_evidence_artifact_id": camera_id,
            "source_camera_interval_ids": [
                i["interval_id"]
                for i in camera["intervals"]
                if source <= i["source_tick"] and i["target_tick"] <= target
            ],
            "policy_identity": POLICY,
        }
        spans.append({"interval_id": _id("camera-endpoint-span", content), **content})
    return spans


def sparse_payloads(revision: str, sources: tuple[ArtifactSnapshot, ...]) -> tuple[dict, dict]:
    if len(sources) != 4 or len({s.artifact_id for s in sources}) != 4:
        raise ValueError("Sparse compensation requires Camera, target S0/S4, and gap policy")
    policies = [s for s in sources if s.media_type == GAP_MEDIA_TYPE]
    if len(policies) != 1:
        raise ValueError("Exactly one accepted sparse policy is required")
    policy = read_policy(policies[0])
    camera = one_camera_evidence(sources)
    if "anchor_entity_ids" not in camera:
        raise ValueError("Sparse recovery v0 requires complete multi-anchor Camera consensus")
    camera_snapshot = next(s for s in sources if s.media_type == CAMERA_CONSENSUS_MEDIA_TYPE)
    translation, similarity = _one_standard_translation(sources), _one_standard_similarity(sources)
    spans = camera_spans(camera, camera_snapshot.artifact_id, policy, translation, similarity)
    outputs = _compensated_payloads(
        revision,
        policy["temporal_identity_id"],
        {"intervals": spans},
        translation,
        similarity,
        tuple(s.artifact_id for s in sources),
    )
    for component, payload in zip(("translation", "similarity"), outputs, strict=True):
        payload.update(
            schema_version=f"svm-camera-compensated-{component}-motion-0.2",
            identity=f"svm-camera-compensated-{component}-motion@0.2",
            policy_identity=POLICY,
            sparse_observation_policy_artifact_id=policies[0].artifact_id,
            camera_spans=spans,
        )
        for interval in payload["intervals"]:
            interval["camera_compensation_policy_identity"] = POLICY
            content = {k: v for k, v in interval.items() if k != "interval_id"}
            interval["interval_id"] = _id(f"camera-compensated-{component}-interval", content)
    return outputs


def provenance(component: str, sources: tuple[ArtifactSnapshot, ...]) -> dict:
    return {
        "adapter_id": ADAPTER_ID,
        "adapter_version": "0.1",
        "policy_identity": POLICY,
        "source_artifact_ids": sorted(s.artifact_id for s in sources),
        "component": component,
    }


class SparseCameraCompensatedMotionAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or set(request.options) != {
            "anchor_entity_ids",
            "target_temporal_identity_id",
        }:
            raise ValueError("Sparse compensation requires explicit anchors and target identity")
        anchors = tuple(
            _static_anchor(request.document, item)
            for item in canonical_anchor_ids(request.options["anchor_entity_ids"])
        )
        references = tuple(
            _accepted_reference(request.document, item) for item in sorted(request.artifact_ids)
        )
        sources = tuple(artifacts.resolve_reference(ref) for ref in references)
        payloads = sparse_payloads(request.base_revision_id, sources)
        camera = one_camera_evidence(sources)
        if camera["anchor_entity_ids"] != [a["id"] for a in anchors]:
            raise ValueError("Sparse compensation anchors must match consensus")
        identity_id = request.options["target_temporal_identity_id"]
        identities = [
            i for i in request.document.get("temporal_identities", []) if i["id"] == identity_id
        ]
        if len(identities) != 1 or identity_id != payloads[0]["temporal_identity_id"]:
            raise ValueError("Sparse target identity must match policy and evidence")
        validate_identity(identities[0], sources)
        outputs = tuple(
            artifacts.import_bytes(
                canonical_bytes(payload),
                media_type=media,
                kind=ArtifactKind.DERIVED,
                provenance=provenance(component, sources),
            )
            for payload, media, component in zip(
                payloads,
                (TRANSLATION_MEDIA_TYPE, SIMILARITY_MEDIA_TYPE),
                ("translation", "similarity"),
                strict=True,
            )
        )
        change = AttachSparseCompensatedMotionChange(
            tuple(o.document_reference() for o in outputs),
            references,
            anchors,
            copy.deepcopy(request.document.get("groups", [])),
            copy.deepcopy(request.document["animation"]),
            copy.deepcopy(request.document.get("presentation", {})),
            request.base_revision_id,
            copy.deepcopy(identities[0]),
        )
        return _proposal(
            request,
            self,
            "sparse-camera-compensation",
            outputs,
            change,
            CompensatedMotionPreview(
                temporal_identity_id=identity_id, interval_count=len(payloads[0]["intervals"])
            ),
            {
                "anchor_entity_ids": [a["id"] for a in anchors],
                "target_temporal_identity_id": identity_id,
                "policy_identity": POLICY,
            },
        )


def validate_identity(identity: dict, sources: tuple[ArtifactSnapshot, ...]) -> None:
    policy = read_policy(next(s for s in sources if s.media_type == GAP_MEDIA_TYPE))
    if (
        identity["id"] != policy["temporal_identity_id"]
        or [b["tick"] for b in identity["bindings"]] != policy["observed_ticks"]
    ):
        raise ValueError("Sparse identity must have exactly the observed endpoint bindings")
    bindings = {b["tick"]: b["observation_id"] for b in identity["bindings"]}
    if (
        bindings[policy["source_tick"]] != policy["source_observation_id"]
        or bindings[policy["target_tick"]] != policy["target_observation_id"]
    ):
        raise ValueError("Sparse gap identity endpoints do not match policy")
    for evidence in (_one_standard_translation(sources), _one_standard_similarity(sources)):
        for interval in evidence["intervals"]:
            if not any(
                p.get("inference_id") == interval["correspondence_inference_id"]
                and p.get("evidence_artifact_id") == interval["correspondence_evidence_artifact_id"]
                for p in identity["provenance"]
            ):
                raise ValueError(
                    "Sparse evidence lacks exact Temporal Identity promotion provenance"
                )
            for endpoint in ("source", "target"):
                if (
                    interval.get(endpoint + "_observation_id")
                    != bindings[interval[endpoint + "_tick"]]
                ):
                    raise ValueError(
                        "Sparse evidence observation does not belong to target identity"
                    )


def verify_sparse_compensation_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    sources = tuple(resolved[ref["id"]] for ref in change.source_references)
    payloads = sparse_payloads(change.source_revision_id, sources)
    if one_camera_evidence(sources)["anchor_entity_ids"] != [
        a["id"] for a in change.anchor_entities
    ]:
        raise ValueError("Sparse compensation requires every consensus anchor")
    validate_identity(change.temporal_identity, sources)
    if len(change.evidence_references) != 2:
        raise ValueError("Sparse compensation requires exactly two outputs")
    for ref, payload, component, media in zip(
        change.evidence_references,
        payloads,
        ("translation", "similarity"),
        (TRANSLATION_MEDIA_TYPE, SIMILARITY_MEDIA_TYPE),
        strict=True,
    ):
        snapshot = resolved[ref["id"]]
        if (
            snapshot.kind != ArtifactKind.DERIVED
            or snapshot.media_type != media
            or snapshot.content != canonical_bytes(payload)
            or snapshot.provenance != provenance(component, sources)
        ):
            raise ValueError("Sparse compensated evidence does not match verified endpoints")


def is_sparse_similarity(snapshot: ArtifactSnapshot, payload: dict) -> bool:
    return (
        snapshot.media_type == SIMILARITY_MEDIA_TYPE
        and snapshot.provenance.get("adapter_id") == ADAPTER_ID
        and snapshot.provenance.get("policy_identity") == POLICY
        and payload.get("schema_version") == "svm-camera-compensated-similarity-motion-0.2"
        and payload.get("identity") == "svm-camera-compensated-similarity-motion@0.2"
        and payload.get("policy_identity") == POLICY
    )
