"""P2A eligibility evidence over every component of one verified video occurrence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..backends.geometry import GeometryBackendError
from ..backends.polygon_set import canonicalize_polygon_set
from ..evaluator import canonical_bytes
from ..proposals import AdapterRequest, GeneratorProvenance, PreviewArtifact, Proposal
from ..revisions import AttachRasterPrimitiveObservationProposalChange, Transaction
from ..video_ingestion import MANIFEST_MEDIA, verify_video_manifest
from .opencv_analysis import (
    ANALYSIS_MEDIA_TYPE,
    OpenCVAnalysisAdapter,
    OpenCVAnalysisOptions,
    _component_digest,
    _opencv,
    analyze_png,
)
from .raster_geometry_observations import CONTOUR_TOLERANCE

ADAPTER_ID = "adapter:raster-primitive-observation-proposal"
ADAPTER_VERSION = "0.1"
POLICY = "svm-raster-primitive-observation-proposal@0.1"
SCHEMA = "svm-raster-primitive-observation-proposal-0.1"
MEDIA = "application/vnd.svm.raster-primitive-observation-proposal+json;version=0.1"
REASONS = (
    "NO_CONTOUR",
    "MULTIPLE_CONTOURS",
    "HAS_HOLE",
    "DEGENERATE_CONTOUR",
    "AREA_BELOW_256",
    "CANONICALIZATION_FAILED",
    "VERTEX_COUNT_OUT_OF_RANGE",
    "MIN_EDGE_BELOW_8",
    "AMBIGUOUS_LANDMARK_ORIGIN",
)


class RasterPrimitiveObservationProposalError(ValueError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()[:32]


def measure_component(mask: Any) -> dict[str, Any]:
    """Use the frozen polygon construction and exact eligibility thresholds."""
    cv2, _ = _opencv()
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    parents = [] if hierarchy is None else hierarchy[0, :, 3].tolist()
    outer = [i for i, parent in enumerate(parents) if parent == -1]
    reasons = []
    if not contours:
        reasons.append("NO_CONTOUR")
    if len(outer) > 1:
        reasons.append("MULTIPLE_CONTOURS")
    if any(parent != -1 for parent in parents):
        reasons.append("HAS_HOLE")
    points: list[list[float]] = []
    area = None
    if len(outer) == 1:
        contour = contours[outer[0]]
        area = abs(float(cv2.contourArea(contour)))
        if area == 0:
            reasons.append("DEGENERATE_CONTOUR")
        if area < 256:
            reasons.append("AREA_BELOW_256")
        if area > 0:
            raw = cv2.approxPolyDP(contour, CONTOUR_TOLERANCE, True).reshape(-1, 2).tolist()
            try:
                points = canonicalize_polygon_set([{"exterior": raw, "holes": []}])["polygons"][0][
                    "exterior"
                ][:-1]
            except GeometryBackendError:
                reasons.append("CANONICALIZATION_FAILED")
            else:
                if not 3 <= len(points) <= 32:
                    reasons.append("VERTEX_COUNT_OUT_OF_RANGE")
    lengths = [math.dist(p, points[(i + 1) % len(points)]) for i, p in enumerate(points)]
    minimum = min(lengths) if lengths else None
    ordered = sorted(lengths)
    margin = ordered[-1] - ordered[-2] if len(ordered) >= 2 else None
    if minimum is not None and minimum < 8:
        reasons.append("MIN_EDGE_BELOW_8")
    status = "REJECTED" if reasons else "SUPPORTED"
    if not reasons and margin is not None and margin <= 4:
        status = "UNCERTAIN"
        reasons.append("AMBIGUOUS_LANDMARK_ORIGIN")
    landmarks = None
    if status == "SUPPORTED":
        start = lengths.index(max(lengths))
        landmarks = points[start:] + points[:start]
    return {
        "status": status,
        "reason_codes": [reason for reason in REASONS if reason in reasons],
        "measurements": {
            "contour_count": len(contours),
            "outer_contour_count": len(outer),
            "has_hole": any(parent != -1 for parent in parents),
            "contour_area": area,
            "simplified_vertex_count": len(points),
            "minimum_edge_pixels": minimum,
            "longest_edge_margin_pixels": margin,
        },
        "ordered_landmarks": landmarks,
    }


def _dependencies(
    analysis_id: str,
    manifest_id: str,
    references: dict[str, dict[str, Any]],
    artifacts: ArtifactRepository,
) -> tuple[tuple[dict[str, Any], ...], ArtifactStore]:
    """Close the manifest's decoder dependencies using accepted descriptors only."""
    try:
        analysis = artifacts.resolve_reference(references[analysis_id])
        manifest = artifacts.resolve_reference(references[manifest_id])
        if analysis.media_type != ANALYSIS_MEDIA_TYPE or manifest.media_type != MANIFEST_MEDIA:
            raise RasterPrimitiveObservationProposalError(
                "P2A requires analysis and video manifest"
            )
        data, video = json.loads(analysis.content), json.loads(manifest.content)
        ids = {
            analysis_id,
            manifest_id,
            data["source_artifact_id"],
            data["binary_mask_artifact_id"],
            video["source_video_reference"]["id"],
        }
        ids.update(o["raster_artifact_id"] for o in video["occurrences"])
        refs = tuple(references[aid] for aid in sorted(ids))
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
        return refs, scratch
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RasterPrimitiveObservationProposalError(
            "Missing or malformed accepted P2A lineage"
        ) from exc


def derive(
    analysis_id: str,
    manifest_id: str,
    references: dict[str, dict[str, Any]],
    artifacts: ArtifactRepository,
) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    refs, scratch = _dependencies(analysis_id, manifest_id, references, artifacts)
    analysis = scratch.resolve_reference(references[analysis_id])
    payload = json.loads(analysis.content)
    source = scratch.resolve_reference(references[payload["source_artifact_id"]])
    mask_snapshot = scratch.resolve_reference(references[payload["binary_mask_artifact_id"]])
    options = OpenCVAnalysisOptions.from_mapping(
        {
            "threshold": payload["threshold"]["value"],
            "foreground": payload["threshold"]["foreground"],
            "connectivity": payload["connectivity"],
        }
    )
    if source.kind != ArtifactKind.REFERENCE or source.media_type != "image/png":
        raise RasterPrimitiveObservationProposalError(
            "P2A source must be a canonical Reference PNG"
        )
    expected_store = ArtifactStore()
    expected_source = expected_store.import_bytes(
        source.content, media_type=source.media_type, kind=source.kind, provenance=source.provenance
    )
    expected_proposal = OpenCVAnalysisAdapter().propose(
        AdapterRequest(
            "verification",
            {},
            ("document",),
            artifact_ids=(expected_source.artifact_id,),
            options=asdict(options),
        ),
        expected_store,
    )
    for actual, preview in zip(
        (mask_snapshot, analysis), expected_proposal.preview_artifacts, strict=True
    ):
        expected = expected_store.get(preview.artifact_id)
        if (actual.content, actual.media_type, actual.kind, actual.provenance) != (
            expected.content,
            expected.media_type,
            expected.kind,
            expected.provenance,
        ):
            raise RasterPrimitiveObservationProposalError("P2A analysis lineage does not reproduce")
    verified = verify_video_manifest(scratch, references[manifest_id])
    matches = [o for o in verified.occurrences if o["raster_artifact_id"] == source.artifact_id]
    if len(matches) != 1:
        raise RasterPrimitiveObservationProposalError(
            "P2A requires exactly one matching video occurrence"
        )
    occurrence = matches[0]
    provenance = {
        "policy_identity": POLICY,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "manifest_artifact_id": manifest_id,
        "analysis_artifact_id": analysis_id,
        "source_png_artifact_id": source.artifact_id,
        "binary_mask_artifact_id": mask_snapshot.artifact_id,
        "occurrence_id": occurrence["occurrence_id"],
        "frame_index": occurrence["frame_index"],
        "tick": occurrence["tick"],
        "source_timestamp": occurrence["source_timestamp"],
        "analysis_options": asdict(options),
        "contour_tolerance_pixels": CONTOUR_TOLERANCE,
    }
    mask, labels, components, _, _ = analyze_png(source, options)
    cv2, np = _opencv()
    gray = cv2.imdecode(np.frombuffer(source.content, np.uint8), cv2.IMREAD_UNCHANGED)
    flat = (
        len(np.unique(gray)) == 2
        and len(np.unique(gray[mask == 0])) == 1
        and len(np.unique(gray[mask != 0])) == 1
    )
    if not flat:
        raise RasterPrimitiveObservationProposalError(
            "P2A requires a flat-background solid-foreground source raster"
        )
    evaluations = []
    for component in components:
        x, y, right, bottom = component["bounds"]
        matching = [
            int(label)
            for label in np.unique(labels[y:bottom, x:right])
            if label
            and _component_digest(labels, int(label), x, y, right - x, bottom - y)
            == component["component_digest"]
        ]
        if len(matching) != 1:
            raise RasterPrimitiveObservationProposalError("P2A component pixels are ambiguous")
        selected = np.where(labels == matching[0], 255, 0).astype(np.uint8)
        result = measure_component(selected)
        identity = {
            **provenance,
            "component_id": component["candidate_id"],
            "component_digest": component["component_digest"],
        }
        identity.pop("analysis_options")
        identity.pop("source_timestamp")
        evaluations.append(
            {
                **result,
                "component_id": component["candidate_id"],
                "component_digest": component["component_digest"],
                "evaluation_id": "evaluation:primitive-observation:"
                + _digest(
                    {**identity, "status": result["status"], "reason_codes": result["reason_codes"]}
                ),
                "candidate_id": "candidate:primitive-observation:" + _digest(identity)
                if result["status"] != "REJECTED"
                else None,
                "provenance": {
                    **provenance,
                    "component_id": component["candidate_id"],
                    "component_digest": component["component_digest"],
                },
            }
        )
    return (
        {
            "schema_version": SCHEMA,
            "policy_identity": POLICY,
            "adapter_id": ADAPTER_ID,
            "adapter_version": ADAPTER_VERSION,
            "occurrence_provenance": provenance,
            "evaluations": evaluations,
            "proposed_candidates": [e for e in evaluations if e["status"] != "REJECTED"],
            "status_counts": {
                status: sum(e["status"] == status for e in evaluations)
                for status in ("SUPPORTED", "UNCERTAIN", "REJECTED")
            },
        },
        provenance,
        refs,
    )


class RasterPrimitiveObservationProposalAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or request.options:
            raise RasterPrimitiveObservationProposalError("P2A takes document scope and no options")
        if len(request.artifact_ids) != 2 or len(set(request.artifact_ids)) != 2:
            raise RasterPrimitiveObservationProposalError(
                "P2A requires exactly analysis and manifest IDs"
            )
        accepted = {ref["id"]: ref for ref in request.document["references"]}
        try:
            inputs = [artifacts.resolve_reference(accepted[aid]) for aid in request.artifact_ids]
            analyses = [s for s in inputs if s.media_type == ANALYSIS_MEDIA_TYPE]
            manifests = [s for s in inputs if s.media_type == MANIFEST_MEDIA]
            if len(analyses) != 1 or len(manifests) != 1:
                raise RasterPrimitiveObservationProposalError(
                    "P2A requires one analysis and one manifest"
                )
            analysis, manifest = analyses[0], manifests[0]
            payload, provenance, refs = derive(
                analysis.artifact_id, manifest.artifact_id, accepted, artifacts
            )
        except (KeyError, TypeError) as exc:
            raise RasterPrimitiveObservationProposalError(
                "P2A requires accepted exact inputs"
            ) from exc
        evidence = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance=provenance,
        )
        change = AttachRasterPrimitiveObservationProposalChange(
            evidence.document_reference(), refs, analysis.artifact_id, manifest.artifact_id, POLICY
        )
        digest = _digest({"base_revision_id": request.base_revision_id, "change": asdict(change)})
        return Proposal(
            proposal_id=f"proposal:raster-primitive-observation:{digest}",
            base_revision_id=request.base_revision_id,
            generator=GeneratorProvenance(
                ADAPTER_ID, ADAPTER_VERSION, "OpenCV component eligibility", POLICY, provenance
            ),
            transaction=Transaction(
                f"transaction:raster-primitive-observation:{digest}",
                (change,),
                "Attach P2A primitive observation eligibility evidence",
            ),
            preview_artifacts=(
                PreviewArtifact(evidence.artifact_id, evidence.content_hash, MEDIA),
            ),
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
        )


def verify_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    if change.policy_identity != POLICY:
        raise RasterPrimitiveObservationProposalError("Unsupported P2A policy identity")
    references = {ref["id"]: ref for ref in change.source_references}
    if len(references) != len(change.source_references):
        raise RasterPrimitiveObservationProposalError("Duplicate P2A dependency")
    scratch = ArtifactStore()
    for aid in references:
        snapshot = resolved[aid]
        scratch.import_bytes(
            snapshot.content,
            media_type=snapshot.media_type,
            kind=snapshot.kind,
            provenance=snapshot.provenance,
            locator=snapshot.descriptor.locator,
        )
    payload, provenance, refs = derive(
        change.analysis_artifact_id, change.manifest_artifact_id, references, scratch
    )
    if set(references) != {ref["id"] for ref in refs}:
        raise RasterPrimitiveObservationProposalError("P2A dependency set is not exact")
    actual = resolved[change.evidence_reference["id"]]
    if (actual.content, actual.media_type, actual.kind, actual.provenance) != (
        canonical_bytes(payload),
        MEDIA,
        ArtifactKind.DERIVED,
        provenance,
    ):
        raise RasterPrimitiveObservationProposalError("P2A evidence does not reproduce")
