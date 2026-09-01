from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict
from itertools import combinations
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    GroupCandidatePreview,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
)
from ..revisions import AppendReferencesChange, Transaction
from .pop_structure import ANALYSIS_IDENTITY, ANALYSIS_MEDIA_TYPE, MASK_BUNDLE_MEDIA_TYPE

MEDIA_TYPE = "application/vnd.svm.pop-group-candidates+json"
INFERENCE_IDENTITY = "svm-pop-conservative-group-inference@0.1"
POLICY_VERSION = "svm-pop-group-scoring-policy@0.1"


class POPGroupCandidateError(ValueError):
    pass


class POPGroupCandidateAdapter:
    """Infer evidence-only, abstaining pair candidates from frozen Q v0 evidence."""

    adapter_id = "adapter:pop-group-candidates"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or request.options:
            raise POPGroupCandidateError("POP group inference v0.1 accepts document scope only")
        if len(request.artifact_ids) != 2:
            raise POPGroupCandidateError(
                "POP group inference requires exact Q v0 mask and analysis Artifacts"
            )
        snapshots = artifacts.resolve_as(
            request.artifact_ids,
            kind=ArtifactKind.DERIVED,
            media_types=frozenset({MASK_BUNDLE_MEDIA_TYPE, ANALYSIS_MEDIA_TYPE}),
        )
        by_media = {item.media_type: item for item in snapshots}
        if set(by_media) != {MASK_BUNDLE_MEDIA_TYPE, ANALYSIS_MEDIA_TYPE}:
            raise POPGroupCandidateError(
                "POP group inference requires one Artifact of each Q v0 type"
            )
        masks = _json(by_media[MASK_BUNDLE_MEDIA_TYPE].content)
        analysis = _json(by_media[ANALYSIS_MEDIA_TYPE].content)
        document_hash = f"sha256:{hashlib.sha256(canonical_bytes(request.document)).hexdigest()}"
        source_document_hash = _validate_sources(request, masks, analysis)
        candidates = _infer(masks, analysis, request.document)
        payload = {
            "schema_version": "svm-pop-group-candidates-0.1",
            "identity": INFERENCE_IDENTITY,
            "policy_version": POLICY_VERSION,
            "source_revision_id": request.base_revision_id,
            "source_document_hash": document_hash,
            "q_v0_source_document_hash": source_document_hash,
            "source_artifact_ids": sorted(request.artifact_ids),
            "semantic_labels": [],
            "candidates": candidates,
        }
        evidence = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "engine": "svm-deterministic-pairwise-evidence",
                "engine_version": INFERENCE_IDENTITY,
                "policy_version": POLICY_VERSION,
                "source_revision_id": request.base_revision_id,
                "source_document_hash": document_hash,
                "source_artifact_ids": sorted(request.artifact_ids),
            },
        )
        previews = tuple(
            GroupCandidatePreview(
                candidate_id=item["candidate_id"],
                inference_id=item["inference_id"],
                members=tuple(item["members"]),
                status=item["status"],
                positive_score=item["positive_score"],
                conflict_score=item["conflict_score"],
                confidence=item["confidence"],
                policy_version=POLICY_VERSION,
                evidence_artifact_id=evidence.artifact_id,
            )
            for item in candidates
        )
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="svm-deterministic-pairwise-evidence",
            engine_version=INFERENCE_IDENTITY,
            parameters={
                "policy_version": POLICY_VERSION,
                "source_artifact_ids": sorted(request.artifact_ids),
            },
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "artifact": evidence.artifact_id,
                }
            )
        ).hexdigest()[:16]
        counts = {
            status: sum(item["status"] == status for item in candidates)
            for status in ("SUPPORTED", "UNCERTAIN", "REJECTED")
        }
        reference = evidence.document_reference()
        return Proposal(
            proposal_id=f"proposal:pop-group-candidates:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:pop-group-candidates:{digest}",
                changes=(AppendReferencesChange((reference,)),),
                message="Attach conservative POP group candidate evidence",
            ),
            report=EvaluationReport(
                metrics={
                    "candidates": float(len(candidates)),
                    **{key.lower(): float(value) for key, value in counts.items()},
                }
            ),
            preview_artifacts=(
                PreviewArtifact(evidence.artifact_id, evidence.content_hash, evidence.media_type),
            ),
            preview=ProposalPreview(group_candidates=previews),
            required_artifact_ids=(evidence.artifact_id,),
            notes=(
                "Candidate acceptance attaches inference evidence only; "
                "it does not materialize a group"
            ),
        )


def _json(content: bytes) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise POPGroupCandidateError("Q v0 evidence is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise POPGroupCandidateError("Q v0 evidence must be an object")
    return value


def _validate_sources(
    request: AdapterRequest, masks: dict[str, Any], analysis: dict[str, Any]
) -> str:
    if analysis.get("identity") != ANALYSIS_IDENTITY:
        raise POPGroupCandidateError("Q v0 analysis identity mismatch")
    if masks.get("source_revision_id") != analysis.get("source_revision_id") or masks.get(
        "source_document_hash"
    ) != analysis.get("source_document_hash"):
        raise POPGroupCandidateError("Q v0 evidence source chain mismatch")
    accepted = {item.get("id") for item in request.document.get("references", [])}
    if not set(request.artifact_ids) <= accepted:
        raise POPGroupCandidateError("Q v0 evidence must already be accepted by the Document")
    source_document = json.loads(canonical_bytes(request.document))
    source_document["references"] = [
        item
        for item in source_document.get("references", [])
        if item.get("import_metadata", {}).get("provenance", {}).get("adapter_id")
        != "adapter:pop-structure"
    ]
    source_hash = f"sha256:{hashlib.sha256(canonical_bytes(source_document)).hexdigest()}"
    if analysis.get("source_document_hash") != source_hash:
        raise POPGroupCandidateError("Q v0 evidence does not match the accepted scene")
    return source_hash


def _infer(
    masks: dict[str, Any], analysis: dict[str, Any], document: dict[str, Any]
) -> list[dict[str, Any]]:
    records = {item["entity_id"]: item for item in masks["entities"]}
    styles = {item["entity"]: item for item in document["presentation"]["styles"]}
    coverage: dict[frozenset[str], float] = {}
    for edge in analysis["topmost_coverage_relations"]:
        pair = frozenset((edge["topmost_entity_id"], edge["covered_entity_id"]))
        coverage[pair] = coverage.get(pair, 0.0) + float(edge["covered_fraction"])
    results = []
    for left_id, right_id in combinations(sorted(records), 2):
        left, right = records[left_id], records[right_id]
        left_box, right_box = _bounds(left["full_runs"]), _bounds(right["full_runs"])
        proximity = max(0.0, 1.0 - _box_distance(left_box, right_box) / 32.0)
        overlap = _run_overlap(left["full_runs"], right["full_runs"]) / min(
            left["full_pixels"], right["full_pixels"]
        )
        containment = overlap
        size_ratio = min(left["full_pixels"], right["full_pixels"]) / max(
            left["full_pixels"], right["full_pixels"]
        )
        color = _color_similarity(styles[left_id]["fill"], styles[right_id]["fill"])
        render = max(0.0, 1.0 - abs(left["render_index"] - right["render_index"]) / 12.0)
        symmetry = size_ratio * max(
            0.0, 1.0 - abs(_center(left_box)[1] - _center(right_box)[1]) / 32.0
        )
        cover = min(1.0, coverage.get(frozenset((left_id, right_id)), 0.0))
        if max(proximity, overlap, cover) < 0.15:
            continue
        signals = {
            "overlap": overlap,
            "containment": containment,
            "proximity": proximity,
            "color": color,
            "size_ratio": size_ratio,
            "topmost_coverage": cover,
            "render_order": render,
            "symmetry": symmetry,
        }
        positive = _round(
            sum(
                signals[key] * weight
                for key, weight in {
                    "overlap": 0.16,
                    "containment": 0.12,
                    "proximity": 0.20,
                    "color": 0.08,
                    "size_ratio": 0.10,
                    "topmost_coverage": 0.16,
                    "render_order": 0.06,
                    "symmetry": 0.12,
                }.items()
            )
        )
        conflicts = {
            "spatial_separation": (1.0 - proximity) * 0.55,
            "scale_mismatch": (1.0 - size_ratio) * 0.35,
            "color_difference": (1.0 - color) * 0.2,
        }
        conflict = _round(min(1.0, sum(conflicts.values())))
        strong = sum(value >= 0.7 for value in signals.values())
        status = (
            "SUPPORTED"
            if positive >= 0.68 and conflict <= 0.25 and strong >= 2
            else ("REJECTED" if conflict >= 0.65 else "UNCERTAIN")
        )
        members = [left_id, right_id]
        candidate_id = _subject_id(members)
        evidence = [
            {"type": key, "effect": "support", "score": _round(value)}
            for key, value in signals.items()
        ] + [
            {"type": key, "effect": "conflict", "score": _round(value)}
            for key, value in conflicts.items()
        ]
        inference_content = {
            "candidate_id": candidate_id,
            "members": members,
            "evidence": evidence,
            "positive_score": positive,
            "conflict_score": conflict,
            "status": status,
            "policy_version": POLICY_VERSION,
        }
        inference_id = (
            f"inference:group:{hashlib.sha256(canonical_bytes(inference_content)).hexdigest()}"
        )
        results.append(
            {
                **inference_content,
                "inference_id": inference_id,
                "confidence": _round(positive * (1.0 - conflict)),
            }
        )
    return results


def _subject_id(members: list[str]) -> str:
    digest = hashlib.sha256(canonical_bytes({"members": sorted(members)})).hexdigest()
    return f"candidate:group:{digest}"


def _bounds(runs: list[list[int]]) -> tuple[int, int, int, int]:
    return (
        min(row[1] for row in runs),
        min(row[0] for row in runs),
        max(row[2] for row in runs),
        max(row[0] + 1 for row in runs),
    )


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _box_distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return math.hypot(dx, dy)


def _run_overlap(left: list[list[int]], right: list[list[int]]) -> int:
    by_row: dict[int, list[tuple[int, int]]] = {}
    for y, start, end in right:
        by_row.setdefault(y, []).append((start, end))
    return sum(
        max(0, min(end, other_end) - max(start, other_start))
        for y, start, end in left
        for other_start, other_end in by_row.get(y, ())
    )


def _color_similarity(left: str, right: str) -> float:
    try:
        a = tuple(int(left[index : index + 2], 16) for index in (1, 3, 5))
        b = tuple(int(right[index : index + 2], 16) for index in (1, 3, 5))
    except (ValueError, TypeError):
        return 0.0
    return max(
        0.0,
        1.0
        - math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True))) / math.sqrt(3 * 255**2),
    )


def _round(value: float) -> float:
    return float(format(value, ".12g"))
