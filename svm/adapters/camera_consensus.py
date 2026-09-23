from __future__ import annotations

import copy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, Proposal, ProposalPreview
from ..revisions import AttachMultiAnchorCameraEvidenceChange
from .camera_compensation import (
    CAMERA_MEDIA_TYPE,
    CameraCompensationError,
    _accepted_reference,
    _id,
    _json,
    _proposal,
    _static_anchor,
    verify_camera_compensation_change,
)

MEDIA_TYPE = "application/vnd.svm.camera-consensus+json;version=0.1"
POLICY = "svm-strict-multi-anchor-camera-consensus@0.1"
SCHEMA = "svm-camera-consensus-0.1"
IDENTITY = "svm-camera-consensus@0.1"
ADAPTER_ID = "adapter:multi-anchor-camera-consensus"
TOLERANCE = 1e-8
MATRICES = ("relative_view_transform", "source_view_transform", "target_view_transform")


@dataclass(frozen=True)
class CameraConsensusPreview(ProposalPreview):
    anchor_entity_ids: tuple[str, ...] = ()
    interval_count: int = 0


class MultiAnchorCameraConsensusAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or set(request.options) != {
            "anchor_entity_ids"
        }:
            raise CameraCompensationError("Consensus requires explicit anchor_entity_ids")
        ids = canonical_anchor_ids(request.options["anchor_entity_ids"])
        if len(request.artifact_ids) != len(ids) or len(set(request.artifact_ids)) != len(ids):
            raise CameraCompensationError("Consensus requires one distinct evidence per anchor")
        anchors = tuple(_static_anchor(request.document, anchor_id) for anchor_id in ids)
        references = {
            item: _accepted_reference(request.document, item) for item in request.artifact_ids
        }
        snapshots = {item: artifacts.resolve_reference(ref) for item, ref in references.items()}
        # Resolve accepted lineage; verification uses the existing single-anchor verifier.
        for source in tuple(snapshots.values()):
            payload = read_single_camera(source)
            similarity_id = payload["source_similarity_artifact_id"]
            ref = _accepted_reference(request.document, similarity_id)
            similarity = artifacts.resolve_reference(ref)
            references[similarity_id], snapshots[similarity_id] = ref, similarity
            for geometry_id in _json(similarity).get("source_geometry_artifact_ids", []):
                ref = _accepted_reference(request.document, geometry_id)
                references[geometry_id] = ref
                snapshots[geometry_id] = artifacts.resolve_reference(ref)
        payload = consensus_payload(request.base_revision_id, ids, snapshots)
        evidence = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=consensus_provenance(payload),
        )
        change = multi_anchor_change(
            request,
            (evidence.document_reference(),),
            tuple(references[k] for k in sorted(references)),
            anchors,
        )
        return _proposal(
            request,
            self,
            "camera-consensus",
            (evidence,),
            change,
            CameraConsensusPreview(anchor_entity_ids=ids, interval_count=len(payload["intervals"])),
            {"anchor_entity_ids": list(ids), "policy_identity": POLICY},
        )


def canonical_anchor_ids(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) < 2
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise CameraCompensationError("Consensus requires at least two distinct explicit anchors")
    return tuple(sorted(value))


def multi_anchor_change(
    request: AdapterRequest,
    outputs: tuple[dict[str, Any], ...],
    sources: tuple[dict[str, Any], ...],
    anchors: tuple[dict[str, Any], ...],
) -> AttachMultiAnchorCameraEvidenceChange:
    return AttachMultiAnchorCameraEvidenceChange(
        outputs,
        sources,
        anchors,
        copy.deepcopy(request.document.get("groups", [])),
        copy.deepcopy(request.document["animation"]),
        copy.deepcopy(request.document.get("presentation", {})),
        request.base_revision_id,
    )


def read_single_camera(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    # Keep the frozen S9C reader as the single-anchor contract.
    from .observed_camera_tracks import _read_single_evidence

    return _read_single_evidence(snapshot)


def read_camera_evidence(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    if snapshot.media_type != MEDIA_TYPE:
        return read_single_camera(snapshot)
    payload = _json(snapshot)
    if (
        snapshot.media_type != MEDIA_TYPE
        or snapshot.kind != ArtifactKind.DERIVED
        or payload.get("schema_version") != SCHEMA
        or payload.get("identity") != IDENTITY
        or payload.get("policy_identity") != POLICY
        or canonical_bytes(payload) != snapshot.content
    ):
        raise CameraCompensationError("Unsupported Camera evidence contract")
    ids = canonical_anchor_ids(payload.get("anchor_entity_ids"))
    supports = payload.get("supporting_hypotheses")
    if (
        not isinstance(supports, list)
        or len(supports) != len(ids)
        or any(not isinstance(item, dict) for item in supports)
        or [item.get("anchor_entity_id") for item in supports] != list(ids)
        or payload.get("source_camera_evidence_artifact_ids")
        != [item.get("camera_evidence_artifact_id") for item in supports]
        or len(set(payload["source_camera_evidence_artifact_ids"])) != len(ids)
        or payload.get("anchor_entity_ids") != list(ids)
        or payload.get("representative") != supports[0]
        or payload.get("agreement_absolute_tolerance") != TOLERANCE
        or snapshot.provenance != consensus_provenance(payload)
    ):
        raise CameraCompensationError("Invalid consensus provenance")
    from .observed_camera_tracks import recover_camera_samples

    recover_camera_samples(payload.get("intervals"))
    for interval in payload["intervals"]:
        content = {k: v for k, v in interval.items() if k != "interval_id"}
        if interval.get("interval_id") != _id("camera-consensus-interval", content):
            raise CameraCompensationError("Invalid consensus interval identity")
    return payload


def one_camera_evidence(snapshots: tuple[ArtifactSnapshot, ...]) -> dict[str, Any]:
    cameras = [item for item in snapshots if item.media_type in {CAMERA_MEDIA_TYPE, MEDIA_TYPE}]
    if len(cameras) != 1:
        raise CameraCompensationError("Exactly one verified Camera evidence is required")
    return read_camera_evidence(cameras[0])


def consensus_provenance(payload: dict) -> dict:
    return {
        "adapter_id": ADAPTER_ID,
        "adapter_version": "0.1",
        "policy_identity": POLICY,
        "anchor_entity_ids": payload["anchor_entity_ids"],
        "supporting_hypotheses": payload["supporting_hypotheses"],
        "source_camera_evidence_artifact_ids": payload["source_camera_evidence_artifact_ids"],
    }


def consensus_payload(
    revision_id: str, anchor_ids: tuple[str, ...], sources: dict[str, ArtifactSnapshot]
) -> dict:
    from .observed_camera_tracks import recover_camera_samples

    hypotheses = []
    used = set()
    for source in sources.values():
        if source.media_type != CAMERA_MEDIA_TYPE:
            continue
        camera = read_single_camera(source)
        similarity_id = camera["source_similarity_artifact_id"]
        similarity = sources[similarity_id]
        geometry_ids = _json(similarity)["source_geometry_artifact_ids"]
        dependency_ids = [similarity_id, *geometry_ids]
        verify_camera_compensation_change(
            SimpleNamespace(
                evidence_references=(source.document_reference(),),
                source_references=tuple(sources[k].document_reference() for k in dependency_ids),
                source_revision_id=camera["source_revision_id"],
                anchor_entity={"id": camera["anchor_entity_id"]},
            ),
            sources,
        )
        recover_camera_samples(camera["intervals"])
        used.update((source.artifact_id, *dependency_ids))
        hypotheses.append((camera["anchor_entity_id"], source.artifact_id, camera))
    hypotheses.sort(key=lambda item: (item[0], item[1]))
    if tuple(item[0] for item in hypotheses) != anchor_ids or used != set(sources):
        raise CameraCompensationError(
            "Camera hypotheses must exactly match distinct selected anchors"
        )
    supports = [{"anchor_entity_id": a, "camera_evidence_artifact_id": e} for a, e, _ in hypotheses]
    representative = hypotheses[0][2]["intervals"]
    ticks = [(i["source_tick"], i["target_tick"]) for i in representative]
    for _, _, camera in hypotheses:
        if [(i["source_tick"], i["target_tick"]) for i in camera["intervals"]] != ticks:
            raise CameraCompensationError("Consensus interval chains must match exactly")
    intervals = []
    for index, reference in enumerate(representative):
        for key in MATRICES:
            for coefficient in range(6):
                values = [c["intervals"][index][key][coefficient] for _, _, c in hypotheses]
                if max(values) - min(values) > TOLERANCE:
                    raise CameraCompensationError("Camera hypotheses disagree; consensus rejected")
        content = {
            "source_tick": reference["source_tick"],
            "target_tick": reference["target_tick"],
            **{key: reference[key] for key in MATRICES},
            "supporting_camera_interval_ids": [
                c["intervals"][index]["interval_id"] for _, _, c in hypotheses
            ],
            "supporting_hypotheses": supports,
            "policy_identity": POLICY,
        }
        intervals.append({"interval_id": _id("camera-consensus-interval", content), **content})
    return {
        "schema_version": SCHEMA,
        "identity": IDENTITY,
        "policy_identity": POLICY,
        "source_revision_id": revision_id,
        "anchor_entity_ids": list(anchor_ids),
        "source_camera_evidence_artifact_ids": [e for _, e, _ in hypotheses],
        "supporting_hypotheses": supports,
        "representative": supports[0],
        "agreement_absolute_tolerance": TOLERANCE,
        "intervals": intervals,
    }


def verify_multi_anchor_camera_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    source_ids = [ref["id"] for ref in change.source_references]
    output_ids = [ref["id"] for ref in change.evidence_references]
    if (
        len(set(source_ids)) != len(source_ids)
        or len(set(output_ids)) != len(output_ids)
        or set(source_ids) & set(output_ids)
    ):
        raise ValueError("Consensus references must be distinct")
    sources = {ref["id"]: resolved[ref["id"]] for ref in change.source_references}
    ids = tuple(item["id"] for item in change.anchor_entities)
    if ids != canonical_anchor_ids(ids):
        raise ValueError("Anchor selections must be canonical")
    outputs = [resolved[ref["id"]] for ref in change.evidence_references]
    if len(outputs) == 1 and outputs[0].media_type == MEDIA_TYPE:
        if outputs[0].kind != ArtifactKind.DERIVED:
            raise ValueError("Consensus must be a Derived Artifact")
        expected = consensus_payload(change.source_revision_id, ids, sources)
        if outputs[0].content != canonical_bytes(expected) or outputs[
            0
        ].provenance != consensus_provenance(expected):
            raise ValueError("Consensus does not match all verified hypotheses")
        return
    camera = one_camera_evidence(tuple(sources.values()))
    if camera.get("anchor_entity_ids") != list(ids):
        raise ValueError("Consensus anchors do not match explicit selection")
    if len(outputs) != 2 or len(sources) != 3:
        raise ValueError("Consensus compensation requires exactly three sources and two outputs")
    verify_camera_compensation_change(change, resolved)
