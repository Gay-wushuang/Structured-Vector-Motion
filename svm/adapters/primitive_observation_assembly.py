"""P2B deterministic assembly of verified P2A evaluations for frozen R0."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, GeneratorProvenance, PreviewArtifact, Proposal
from ..revisions import AttachPrimitiveObservationAssemblyChange, Transaction
from .opencv_analysis import OpenCVAnalysisOptions, _component_digest, _opencv, analyze_png
from .raster_geometry_observations import PRIMITIVE_TYPE
from .raster_primitive_observation_proposal import MEDIA as P2A_MEDIA
from .raster_primitive_observation_proposal import derive as derive_p2a
from .temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2, read_primitive_observations

ADAPTER_ID = "adapter:primitive-observation-assembly"
ADAPTER_VERSION = "0.1"
POLICY = "svm-primitive-observation-assembly@0.1"
SCHEMA = "svm-primitive-observation-assembly-0.1"
MEDIA = "application/vnd.svm.primitive-observation-assembly+json;version=0.1"


class PrimitiveObservationAssemblyError(ValueError):
    pass


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _dependency_references(
    evidence_ids: tuple[str, str],
    accepted: dict[str, dict[str, Any]],
    artifacts: ArtifactRepository,
) -> tuple[tuple[dict[str, Any], ...], ArtifactStore, tuple[dict[str, Any], ...]]:
    try:
        evidences = tuple(artifacts.resolve_reference(accepted[aid]) for aid in evidence_ids)
        if any(
            item.kind != ArtifactKind.DERIVED or item.media_type != P2A_MEDIA for item in evidences
        ):
            raise PrimitiveObservationAssemblyError("P2B requires two P2A evidence artifacts")
        payloads = tuple(json.loads(item.content) for item in evidences)
        manifest_ids = tuple(
            item["occurrence_provenance"]["manifest_artifact_id"] for item in payloads
        )
        if len(set(manifest_ids)) != 1:
            raise PrimitiveObservationAssemblyError("P2B requires one exact shared manifest")
        manifest_id = manifest_ids[0]
        manifest = artifacts.resolve_reference(accepted[manifest_id])
        manifest_payload = json.loads(manifest.content)
        ordered = [*evidence_ids, manifest_id, manifest_payload["source_video_reference"]["id"]]
        ordered.extend(item["raster_artifact_id"] for item in manifest_payload["occurrences"])
        for payload in payloads:
            provenance = payload["occurrence_provenance"]
            ordered.extend(
                (provenance["analysis_artifact_id"], provenance["binary_mask_artifact_id"])
            )
        ids = _dedupe(ordered)
        refs = tuple(accepted[aid] for aid in ids)
        scratch = ArtifactStore()
        for ref in refs:
            snapshot = artifacts.resolve_reference(ref)
            scratch.import_bytes(
                snapshot.content,
                media_type=snapshot.media_type,
                kind=snapshot.kind,
                provenance=snapshot.provenance,
                locator=snapshot.descriptor.locator,
            )
        return refs, scratch, payloads
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise PrimitiveObservationAssemblyError(
            "Missing or malformed accepted P2B lineage"
        ) from exc


def _verify_p2a(
    evidence: ArtifactSnapshot,
    payload: dict[str, Any],
    references: dict[str, dict[str, Any]],
    scratch: ArtifactStore,
) -> dict[str, Any]:
    provenance = payload["occurrence_provenance"]
    expected, expected_provenance, _ = derive_p2a(
        provenance["analysis_artifact_id"],
        provenance["manifest_artifact_id"],
        references,
        scratch,
    )
    if (
        evidence.content != canonical_bytes(expected)
        or evidence.media_type != P2A_MEDIA
        or evidence.kind != ArtifactKind.DERIVED
        or evidence.provenance != expected_provenance
    ):
        raise PrimitiveObservationAssemblyError("P2A evidence does not reproduce")
    return expected


def _frame(
    evidence_id: str,
    payload: dict[str, Any],
    references: dict[str, dict[str, Any]],
    scratch: ArtifactStore,
) -> tuple[dict[str, Any], dict[str, Any], list[int]]:
    provenance = payload["occurrence_provenance"]
    analysis = scratch.resolve_reference(references[provenance["analysis_artifact_id"]])
    analysis_payload = json.loads(analysis.content)
    source = scratch.resolve_reference(references[analysis_payload["source_artifact_id"]])
    options = OpenCVAnalysisOptions.from_mapping(
        {
            "threshold": analysis_payload["threshold"]["value"],
            "foreground": analysis_payload["threshold"]["foreground"],
            "connectivity": analysis_payload["connectivity"],
        }
    )
    mask, labels, components, width, height = analyze_png(source, options)
    by_id = {component["candidate_id"]: component for component in components}
    cv2, np = _opencv()
    gray = cv2.imdecode(np.frombuffer(source.content, np.uint8), cv2.IMREAD_UNCHANGED)
    included, excluded, primitives = [], [], []
    for evaluation in payload["evaluations"]:
        if evaluation["status"] != "SUPPORTED":
            excluded.append(
                {
                    "evaluation_id": evaluation["evaluation_id"],
                    "status": evaluation["status"],
                    "reason_codes": evaluation["reason_codes"],
                }
            )
            continue
        component = by_id.get(evaluation["component_id"])
        if component is None or component["component_digest"] != evaluation["component_digest"]:
            raise PrimitiveObservationAssemblyError("P2B component lineage does not reproduce")
        x, y, right, bottom = component["bounds"]
        matching = [
            int(label)
            for label in np.unique(labels[y:bottom, x:right])
            if label
            and _component_digest(labels, int(label), x, y, right - x, bottom - y)
            == evaluation["component_digest"]
        ]
        if len(matching) != 1:
            raise PrimitiveObservationAssemblyError("P2B component pixels are ambiguous")
        selected = labels == matching[0]
        fill_values = np.unique(gray[selected])
        if len(fill_values) != 1:
            raise PrimitiveObservationAssemblyError("P2B component fill is not solid")
        candidate_id = evaluation["candidate_id"]
        if not isinstance(candidate_id, str):
            raise PrimitiveObservationAssemblyError("SUPPORTED P2A evaluation requires candidate")
        identity = {
            "policy_identity": POLICY,
            "adapter_id": ADAPTER_ID,
            "adapter_version": ADAPTER_VERSION,
            "source_p2a_evidence_artifact_id": evidence_id,
            "p2a_candidate_id": candidate_id,
            "manifest_artifact_id": provenance["manifest_artifact_id"],
            "occurrence_id": provenance["occurrence_id"],
            "frame_index": provenance["frame_index"],
            "tick": provenance["tick"],
            "component_digest": evaluation["component_digest"],
        }
        observation_id = "observation:p2b:" + _hash(identity)
        value = int(fill_values[0])
        primitives.append(
            {
                "observation_id": observation_id,
                "primitive_type": PRIMITIVE_TYPE,
                "bounds": component["bounds"],
                "fill": f"#{value:02X}{value:02X}{value:02X}",
                "geometry": {
                    "type": "ordered-landmarks",
                    "points": evaluation["ordered_landmarks"],
                    "rotation_symmetry": "none",
                },
            }
        )
        included.append(
            {
                "evaluation_id": evaluation["evaluation_id"],
                "candidate_id": candidate_id,
                "observation_id": observation_id,
            }
        )
    if not primitives:
        raise PrimitiveObservationAssemblyError("P2B requires a SUPPORTED primitive in each frame")
    audit = {
        "occurrence_id": provenance["occurrence_id"],
        "frame_index": provenance["frame_index"],
        "tick": provenance["tick"],
        "included": included,
        "excluded": excluded,
        "counts": {
            "included": len(included),
            "excluded": len(excluded),
            "statuses": {
                status: sum(item["status"] == status for item in payload["evaluations"])
                for status in ("SUPPORTED", "UNCERTAIN", "REJECTED")
            },
        },
    }
    return {"tick": provenance["tick"], "primitives": primitives}, audit, [width, height]


def derive(
    evidence_ids: tuple[str, str],
    accepted: dict[str, dict[str, Any]],
    artifacts: ArtifactRepository,
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]
]:
    refs, scratch, claimed = _dependency_references(evidence_ids, accepted, artifacts)
    reference_map = {ref["id"]: ref for ref in refs}
    payloads = tuple(
        _verify_p2a(scratch.resolve_reference(reference_map[aid]), payload, reference_map, scratch)
        for aid, payload in zip(evidence_ids, claimed, strict=True)
    )
    occurrences = [payload["occurrence_provenance"] for payload in payloads]
    if (
        occurrences[0]["occurrence_id"] == occurrences[1]["occurrence_id"]
        or occurrences[0]["frame_index"] >= occurrences[1]["frame_index"]
        or occurrences[0]["tick"] >= occurrences[1]["tick"]
    ):
        raise PrimitiveObservationAssemblyError("P2B requires an increasing distinct interval")
    frames, audits, canvases = [], [], []
    for evidence_id, payload in zip(evidence_ids, payloads, strict=True):
        frame, audit, canvas = _frame(evidence_id, payload, reference_map, scratch)
        frames.append(frame)
        audits.append(audit)
        canvases.append(canvas)
    if canvases[0] != canvases[1]:
        raise PrimitiveObservationAssemblyError("P2B frame dimensions must match")
    observation = {
        "schema_version": "svm-primitive-observations-0.2",
        "canvas": canvases[0],
        "frames": frames,
    }
    read_primitive_observations(canonical_bytes(observation))
    observation_provenance = {
        "producer_identity": POLICY,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "source_p2a_evidence_artifact_ids": list(evidence_ids),
        "manifest_artifact_id": occurrences[0]["manifest_artifact_id"],
    }
    evidence_provenance = dict(observation_provenance)
    return observation, {"frames": audits}, observation_provenance, evidence_provenance, refs


def _evidence_payload(
    audit: dict[str, Any], provenance: dict[str, Any], observation_id: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "policy_identity": POLICY,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "source_p2a_evidence_artifact_ids": provenance["source_p2a_evidence_artifact_ids"],
        "manifest_artifact_id": provenance["manifest_artifact_id"],
        "observation_artifact_id": observation_id,
        "frames": audit["frames"],
    }


class PrimitiveObservationAssemblyAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or request.options:
            raise PrimitiveObservationAssemblyError("P2B takes document scope and no options")
        if len(request.artifact_ids) != 2 or len(set(request.artifact_ids)) != 2:
            raise PrimitiveObservationAssemblyError(
                "P2B requires exactly two distinct P2A evidences"
            )
        accepted = {ref["id"]: ref for ref in request.document["references"]}
        evidence_ids = (request.artifact_ids[0], request.artifact_ids[1])
        observation, audit, observation_provenance, evidence_provenance, refs = derive(
            evidence_ids, accepted, artifacts
        )
        observation_artifact = artifacts.import_bytes(
            canonical_bytes(observation),
            media_type=OBSERVATION_MEDIA_TYPE_V2,
            kind=ArtifactKind.REFERENCE,
            provenance=observation_provenance,
        )
        evidence_payload = _evidence_payload(
            audit, evidence_provenance, observation_artifact.artifact_id
        )
        evidence_artifact = artifacts.import_bytes(
            canonical_bytes(evidence_payload),
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance=evidence_provenance,
        )
        change = AttachPrimitiveObservationAssemblyChange(
            observation_artifact.document_reference(),
            evidence_artifact.document_reference(),
            refs,
            POLICY,
        )
        digest = _hash({"base": request.base_revision_id, "change": asdict(change)})[:32]
        return Proposal(
            proposal_id=f"proposal:primitive-observation-assembly:{digest}",
            base_revision_id=request.base_revision_id,
            generator=GeneratorProvenance(
                ADAPTER_ID,
                ADAPTER_VERSION,
                "deterministic primitive observation assembly",
                POLICY,
                evidence_provenance,
            ),
            transaction=Transaction(
                f"transaction:primitive-observation-assembly:{digest}",
                (change,),
                "Attach P2B primitive observations and assembly evidence",
            ),
            preview_artifacts=(
                PreviewArtifact(
                    observation_artifact.artifact_id,
                    observation_artifact.content_hash,
                    observation_artifact.media_type,
                ),
                PreviewArtifact(
                    evidence_artifact.artifact_id,
                    evidence_artifact.content_hash,
                    evidence_artifact.media_type,
                ),
            ),
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
        )


def verify_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    if change.policy_identity != POLICY:
        raise PrimitiveObservationAssemblyError("Unsupported P2B policy identity")
    references = {ref["id"]: ref for ref in change.source_references}
    if len(references) != len(change.source_references):
        raise PrimitiveObservationAssemblyError("Duplicate P2B dependency")
    scratch = ArtifactStore()
    for ref in change.source_references:
        snapshot = resolved[ref["id"]]
        scratch.import_bytes(
            snapshot.content,
            media_type=snapshot.media_type,
            kind=snapshot.kind,
            provenance=snapshot.provenance,
            locator=snapshot.descriptor.locator,
        )
    evidence_ids = tuple(ref["id"] for ref in change.source_references[:2])
    if len(evidence_ids) != 2:
        raise PrimitiveObservationAssemblyError("P2B source evidence set is incomplete")
    observation, audit, observation_provenance, evidence_provenance, refs = derive(
        evidence_ids, references, scratch
    )
    if tuple(ref["id"] for ref in refs) != tuple(ref["id"] for ref in change.source_references):
        raise PrimitiveObservationAssemblyError("P2B dependency order is not exact")
    actual_observation = resolved[change.observation_reference["id"]]
    if (
        actual_observation.content != canonical_bytes(observation)
        or actual_observation.media_type != OBSERVATION_MEDIA_TYPE_V2
        or actual_observation.kind != ArtifactKind.REFERENCE
        or actual_observation.provenance != observation_provenance
    ):
        raise PrimitiveObservationAssemblyError("P2B observation does not reproduce")
    evidence_payload = _evidence_payload(audit, evidence_provenance, actual_observation.artifact_id)
    actual_evidence = resolved[change.evidence_reference["id"]]
    if (
        actual_evidence.content != canonical_bytes(evidence_payload)
        or actual_evidence.media_type != MEDIA
        or actual_evidence.kind != ArtifactKind.DERIVED
        or actual_evidence.provenance != evidence_provenance
    ):
        raise PrimitiveObservationAssemblyError("P2B assembly evidence does not reproduce")
