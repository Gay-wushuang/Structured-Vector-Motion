from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import (
    OBSERVED_TRANSLATION_MOTION_IDENTITY,
    AttachObservedMotionEvidenceChange,
    Transaction,
)
from .temporal_correspondence import EVIDENCE_MEDIA_TYPE, INFERENCE_IDENTITY

MEDIA_TYPE = "application/vnd.svm.observed-translation-motion+json;version=0.1"
POLICY_IDENTITY = "svm-r0-displacement-observation-policy@0.1"


class ObservedTranslationMotionError(ValueError):
    pass


@dataclass(frozen=True)
class ObservedMotionIntervalPreview:
    interval_id: str
    source_tick: int
    target_tick: int
    dx: float
    dy: float


@dataclass(frozen=True)
class ObservedTranslationMotionPreview(ProposalPreview):
    temporal_identity_id: str = ""
    intervals: tuple[ObservedMotionIntervalPreview, ...] = ()


class ObservedTranslationMotionAdapter:
    adapter_id = "adapter:observed-translation-motion"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise ObservedTranslationMotionError("Observed motion scope must be document")
        if set(request.options) != {"temporal_identity_id", "inference_ids"}:
            raise ObservedTranslationMotionError(
                "Explicit temporal_identity_id and inference_ids are required"
            )
        identity_id = request.options["temporal_identity_id"]
        inference_ids = request.options["inference_ids"]
        if (
            not isinstance(identity_id, str)
            or not isinstance(inference_ids, list)
            or not inference_ids
            or any(not isinstance(item, str) for item in inference_ids)
            or len(inference_ids) != len(set(inference_ids))
        ):
            raise ObservedTranslationMotionError(
                "inference_ids must be a non-empty unique string list"
            )
        identities = [
            item
            for item in request.document.get("temporal_identities", [])
            if item.get("id") == identity_id
        ]
        if len(identities) != 1:
            raise ObservedTranslationMotionError(
                "Observed motion requires an existing temporal identity"
            )
        identity = copy.deepcopy(identities[0])
        provenance = {item["inference_id"]: item for item in identity["provenance"]}
        selected = []
        for inference_id in inference_ids:
            record = provenance.get(inference_id)
            if record is None:
                raise ObservedTranslationMotionError(
                    "Correspondence was not promoted into this temporal identity"
                )
            selected.append(record)
        expected_artifacts = tuple(sorted({item["evidence_artifact_id"] for item in selected}))
        if tuple(sorted(request.artifact_ids)) != expected_artifacts or len(
            request.artifact_ids
        ) != len(expected_artifacts):
            raise ObservedTranslationMotionError(
                "Artifact IDs must exactly match selected R1 provenance"
            )
        source_references = tuple(
            _accepted_reference(request.document, item) for item in expected_artifacts
        )
        snapshots = tuple(artifacts.resolve_reference(item) for item in source_references)
        intervals = _derive_intervals(
            identity, selected, {item.artifact_id: item for item in snapshots}
        )
        payload = _payload(request.base_revision_id, identity_id, expected_artifacts, intervals)
        evidence = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "engine": "svm-observed-translation-motion",
                "engine_version": OBSERVED_TRANSLATION_MOTION_IDENTITY,
                "policy_identity": POLICY_IDENTITY,
                "source_correspondence_artifact_ids": list(expected_artifacts),
            },
        )
        change = AttachObservedMotionEvidenceChange(
            evidence.document_reference(),
            source_references,
            identity,
            tuple(inference_ids),
            request.base_revision_id,
        )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "svm-observed-translation-motion",
            OBSERVED_TRANSLATION_MOTION_IDENTITY,
            {
                "temporal_identity_id": identity_id,
                "inference_ids": inference_ids,
                "policy_identity": POLICY_IDENTITY,
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
        return Proposal(
            proposal_id=f"proposal:observed-translation-motion:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:observed-translation-motion:{digest}",
                (change,),
                "Attach observed translation motion evidence",
            ),
            report=EvaluationReport(metrics={"motion_intervals": float(len(intervals))}),
            preview_artifacts=(
                PreviewArtifact(evidence.artifact_id, evidence.content_hash, evidence.media_type),
            ),
            preview=ObservedTranslationMotionPreview(
                temporal_identity_id=identity_id,
                intervals=tuple(
                    ObservedMotionIntervalPreview(
                        item["interval_id"],
                        item["source_tick"],
                        item["target_tick"],
                        item["translation"]["dx"],
                        item["translation"]["dy"],
                    )
                    for item in intervals
                ),
            ),
            required_artifact_ids=(evidence.artifact_id, *expected_artifacts),
            notes="Observed motion is evidence only; no Track or Keyframe is created",
        )


def verify_observed_motion_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    output = resolved.get(change.evidence_reference.get("id"))
    if output is None or output.kind != ArtifactKind.DERIVED or output.media_type != MEDIA_TYPE:
        raise ValueError("Observed motion output Artifact was not resolved")
    if output.provenance != {
        "adapter_id": "adapter:observed-translation-motion",
        "adapter_version": "0.1",
        "engine": "svm-observed-translation-motion",
        "engine_version": OBSERVED_TRANSLATION_MOTION_IDENTITY,
        "policy_identity": POLICY_IDENTITY,
        "source_correspondence_artifact_ids": sorted(
            item["id"] for item in change.source_references
        ),
    }:
        raise ValueError("Observed motion Artifact provenance is invalid")
    source_ids = tuple(sorted(item["id"] for item in change.source_references))
    sources = {item: resolved[item] for item in source_ids}
    for snapshot in sources.values():
        if snapshot.media_type != EVIDENCE_MEDIA_TYPE or snapshot.kind != ArtifactKind.DERIVED:
            raise ValueError("Observed motion source is not R0 evidence")
    identity = change.temporal_identity
    provenance = {item["inference_id"]: item for item in identity["provenance"]}
    if len(change.inference_ids) != len(set(change.inference_ids)):
        raise ValueError("Observed motion inference IDs must be unique")
    try:
        selected = [provenance[item] for item in change.inference_ids]
    except KeyError as exc:
        raise ValueError("Observed motion inference was not promoted") from exc
    expected_source_ids = tuple(sorted({item["evidence_artifact_id"] for item in selected}))
    if source_ids != expected_source_ids:
        raise ValueError("Observed motion sources do not match R1 provenance")
    expected = _payload(
        change.source_revision_id,
        identity["id"],
        source_ids,
        _derive_intervals(identity, selected, sources),
    )
    if canonical_bytes(expected) != output.content:
        raise ValueError(
            "Observed motion evidence does not match R0 displacement and R1 provenance"
        )


def _derive_intervals(
    identity: dict[str, Any], selected: list[dict[str, Any]], snapshots: dict[str, ArtifactSnapshot]
) -> list[dict[str, Any]]:
    bindings = {(item["tick"], item["observation_id"]) for item in identity["bindings"]}
    intervals = []
    for provenance in selected:
        snapshot = snapshots.get(provenance["evidence_artifact_id"])
        if snapshot is None:
            raise ObservedTranslationMotionError("Missing exact R0 evidence Artifact")
        payload = _correspondence_payload(snapshot)
        candidates = [
            item
            for item in payload["candidates"]
            if item.get("inference_id") == provenance["inference_id"]
        ]
        if len(candidates) != 1:
            raise ObservedTranslationMotionError(
                "R1 provenance inference is absent from R0 evidence"
            )
        candidate = candidates[0]
        if (
            candidate.get("candidate_id") != provenance["candidate_id"]
            or candidate.get("status") != "SUPPORTED"
            or provenance["evidence_policy_identity"] != payload["policy_identity"]
        ):
            raise ObservedTranslationMotionError("R1 provenance does not match exact R0 inference")
        pair = (
            (candidate["source_tick"], candidate["source_observation_id"]),
            (candidate["target_tick"], candidate["target_observation_id"]),
        )
        if any(item not in bindings for item in pair):
            raise ObservedTranslationMotionError(
                "Observation pair does not belong to the temporal identity"
            )
        displacement = candidate.get("displacement")
        if (
            not isinstance(displacement, list)
            or len(displacement) != 2
            or any(not _finite_number(value) for value in displacement)
        ):
            raise ObservedTranslationMotionError("R0 centroid displacement is invalid")
        content = {
            "temporal_identity_id": identity["id"],
            "source_tick": pair[0][0],
            "target_tick": pair[1][0],
            "source_observation_id": pair[0][1],
            "target_observation_id": pair[1][1],
            "translation": {"dx": displacement[0], "dy": displacement[1]},
            "correspondence_candidate_id": candidate["candidate_id"],
            "correspondence_inference_id": candidate["inference_id"],
            "correspondence_evidence_artifact_id": snapshot.artifact_id,
            "temporal_identity_promotion_policy_identity": provenance["promotion_policy_identity"],
            "motion_observation_policy_identity": POLICY_IDENTITY,
        }
        intervals.append(
            {
                "interval_id": "observed-motion-interval:"
                + hashlib.sha256(canonical_bytes(content)).hexdigest(),
                **content,
            }
        )
    intervals.sort(
        key=lambda item: (
            item["source_tick"],
            item["target_tick"],
            item["source_observation_id"],
            item["target_observation_id"],
        )
    )
    return intervals


def _payload(
    revision_id: str,
    identity_id: str,
    artifact_ids: tuple[str, ...],
    intervals: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "svm-observed-translation-motion-0.1",
        "identity": OBSERVED_TRANSLATION_MOTION_IDENTITY,
        "policy_identity": POLICY_IDENTITY,
        "source_revision_id": revision_id,
        "temporal_identity_id": identity_id,
        "source_correspondence_artifact_ids": list(artifact_ids),
        "intervals": intervals,
    }


def _correspondence_payload(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        payload = json.loads(snapshot.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservedTranslationMotionError("R0 evidence is invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or canonical_bytes(payload) != snapshot.content
        or payload.get("identity") != INFERENCE_IDENTITY
        or payload.get("policy_identity") != "svm-bounds-correspondence-policy@0.1"
        or not isinstance(payload.get("candidates"), list)
    ):
        raise ObservedTranslationMotionError("Observed motion requires canonical R0 evidence")
    return payload


def _accepted_reference(document: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [item for item in document.get("references", []) if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ObservedTranslationMotionError("R0 evidence must already be accepted")
    return copy.deepcopy(matches[0])


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
