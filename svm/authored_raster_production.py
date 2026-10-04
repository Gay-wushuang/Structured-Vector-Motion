"""Spec/75 bounded source production and replay; no Document mutation authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from xml.parsers import expat

from .adapters.opencv_analysis import (
    OpenCVAnalysisOptions,
    _component_digest,
    _opencv,
    analyze_png,
)
from .adapters.primitive_observation_assembly import PrimitiveObservationAssemblyAdapter
from .adapters.raster_primitive_observation_proposal import measure_component
from .artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from .evaluator import canonical_bytes
from .proposals import AdapterRequest
from .revisions import RevisionStore
from .video_ingestion import canonical_frame_png, verify_video_manifest

POLICY = "svm-authored-two-triangle-raster-production@0.1"
SOURCE_GRAMMAR = "svm-svg-g-two-triangle-paths@0.1"
MEDIA = "application/vnd.svm.authored-raster-production+json;version=0.1"
PART_KEYS = ("part-a", "part-b")
CANVAS = 256
TRANSLATIONS = ((0, 0), (8, 6))
Point = tuple[int, int]
Triangle = tuple[Point, Point, Point]


class AuthoredRasterProductionError(ValueError):
    pass


@dataclass(frozen=True)
class ProducedRaster:
    source_revision_id: str
    source_reference: dict[str, Any]
    frames: tuple[bytes, ...]
    contributions: tuple[tuple[bytes, ...], ...]
    measurements: tuple[tuple[dict[str, Any], ...], ...]


def _document(store: RevisionStore, revision_id: str) -> dict[str, Any]:
    """Use an existing store revision, never a caller's claimed base snapshot."""
    document = store.get_document(revision_id)
    witness = store.revisions[revision_id]
    if (
        store._make_revision(document, witness.parent_ids, witness.transaction_id, witness.message)
        != witness
    ):
        raise AuthoredRasterProductionError("Revision witness does not reproduce")
    return document


def _source(document: dict[str, Any], artifacts: ArtifactRepository) -> ArtifactSnapshot:
    refs = [
        ref
        for ref in document["references"]
        if ref["media_type"] in {"image/svg+xml", "application/svg+xml"}
        and ref["import_metadata"].get("artifact_kind") == ArtifactKind.REFERENCE
    ]
    if len(refs) != 1 or refs[0]["media_type"] != "image/svg+xml":
        raise AuthoredRasterProductionError("Exactly one accepted image/svg+xml source required")
    source = artifacts.resolve_reference(refs[0])
    if source.kind != ArtifactKind.REFERENCE or source.media_type != "image/svg+xml":
        raise AuthoredRasterProductionError("Source descriptor mismatch")
    return source


def _triangles(content: bytes) -> tuple[Triangle, ...]:
    if len(content) > 65536 or content.startswith(b"\xef\xbb\xbf"):
        raise AuthoredRasterProductionError("Source exceeds byte limit or has BOM")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthoredRasterProductionError("Source requires UTF-8") from exc
    if any(token in text for token in ("<!", "<?", "&")):
        raise AuthoredRasterProductionError("Declarations/references are outside source grammar")
    nodes: list[tuple[str, int, dict[str, str]]] = []
    depth = 0

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth
        if len(nodes) >= 4 or depth > 2:
            raise AuthoredRasterProductionError("Extra source node")
        nodes.append((name, depth, attrs))
        depth += 1

    def end(name: str) -> None:
        nonlocal depth
        depth -= 1

    def characters(data: str) -> None:
        if data.strip():
            raise AuthoredRasterProductionError("Source text is outside grammar")

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = characters
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        raise AuthoredRasterProductionError("Malformed source XML") from exc
    if [(name, level) for name, level, _ in nodes] != [
        ("svg", 0),
        ("g", 1),
        ("path", 2),
        ("path", 2),
    ]:
        raise AuthoredRasterProductionError("Expected sole authored g with two path parts")
    if nodes[0][2] != {"xmlns": "http://www.w3.org/2000/svg"} or nodes[1][2]:
        raise AuthoredRasterProductionError("Root/group attributes outside grammar")
    number = r"(0|[1-9][0-9]{0,2})"
    pattern = rf"M {number} {number} L {number} {number} L {number} {number} Z"
    result = []
    for key, (_, _, attrs) in zip(PART_KEYS, nodes[2:], strict=True):
        if set(attrs) != {"id", "d"} or attrs["id"] != key:
            raise AuthoredRasterProductionError("Noncanonical ordered source part keys")
        match = re.fullmatch(pattern, attrs["d"])
        if match is None:
            raise AuthoredRasterProductionError("Expected canonical integer triangular path")
        a, b, c, d, e, f = map(int, match.groups())
        triangle = ((a, b), (c, d), (e, f))
        if any(not 1 <= x <= 246 or not 1 <= y <= 248 for x, y in triangle):
            raise AuthoredRasterProductionError("Geometry outside bounded canvas interior")
        if (c - a) * (f - b) - (d - b) * (e - a) <= 0:
            raise AuthoredRasterProductionError("Expected nondegenerate positive winding")
        result.append(triangle)
    # Separating-axis test on complete continuous geometry, including touching edges.
    # Disjoint pixels alone would not rule out subpixel source overlap.
    first, second = result
    separated = False
    for triangle in result:
        for a, b in zip(triangle, triangle[1:] + triangle[:1], strict=True):
            axis = (a[1] - b[1], b[0] - a[0])
            p = [x * axis[0] + y * axis[1] for x, y in first]
            q = [x * axis[0] + y * axis[1] for x, y in second]
            separated |= max(p) < min(q) or max(q) < min(p)
    if not separated:
        raise AuthoredRasterProductionError("Source parts overlap or touch")
    return tuple(result)


def _mask(triangle: Triangle, translation: Point) -> Any:
    _, np = _opencv()
    dx, dy = translation
    vertices = [(2 * (x + dx), 2 * (y + dy)) for x, y in triangle]
    # Doubled integers: samples are odd/odd pixel centers; edge equality is inside.
    return np.array(
        [
            [
                all(
                    (b[0] - a[0]) * (2 * y + 1 - a[1]) - (b[1] - a[1]) * (2 * x + 1 - a[0]) >= 0
                    for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True)
                )
                for x in range(CANVAS)
            ]
            for y in range(CANVAS)
        ],
        dtype=np.bool_,
    )


def reproduce_source(
    store: RevisionStore, source_revision_id: str, artifacts: ArtifactRepository
) -> ProducedRaster:
    """Replay accepted source bytes; return bytes only, without publishing artifacts."""
    source = _source(_document(store, source_revision_id), artifacts)
    triangles = _triangles(source.content)
    _, np = _opencv()
    frames, contributions, measurements = [], [], []
    for translation in TRANSLATIONS:
        masks = [_mask(triangle, translation) for triangle in triangles]
        if np.any(masks[0] & masks[1]):
            raise AuthoredRasterProductionError("Overlapping pixel contributions")
        results = tuple(measure_component(mask.astype(np.uint8) * 255) for mask in masks)
        if any(result["status"] != "SUPPORTED" for result in results):
            raise AuthoredRasterProductionError("AUTHORED_PARTS_NOT_P2A_ELIGIBLE")
        contributions.append(tuple(canonical_frame_png(m.astype(np.uint8) * 255) for m in masks))
        frames.append(canonical_frame_png(np.where(masks[0] | masks[1], 0, 255).astype(np.uint8)))
        measurements.append(results)
    return ProducedRaster(
        source_revision_id,
        source.document_reference(),
        tuple(frames),
        tuple(contributions),
        tuple(measurements),
    )


def _ancestor(store: RevisionStore, ancestor: str, base: str) -> bool:
    pending, seen = [base], set()
    while pending:
        current = pending.pop()
        if current == ancestor:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(store.revisions[current].parent_ids)
    return False


def _replay(
    store: RevisionStore,
    base_revision_id: str,
    source_revision_id: str,
    manifest_id: str,
    p2a_ids: tuple[str, str],
    p2b_observation_id: str,
    p2b_evidence_id: str,
    artifacts: ArtifactRepository,
) -> tuple[dict[str, Any], ProducedRaster]:
    if store.head != base_revision_id:
        raise AuthoredRasterProductionError("Stale verification base")
    if not _ancestor(store, source_revision_id, base_revision_id):
        raise AuthoredRasterProductionError("Source revision is not an ancestor")
    # Ordering is intentional: source replay precedes any claimed video linkage.
    produced = reproduce_source(store, source_revision_id, artifacts)
    document = _document(store, base_revision_id)
    if _source(document, artifacts).document_reference() != produced.source_reference:
        raise AuthoredRasterProductionError("Accepted source changed")
    accepted = {ref["id"]: ref for ref in document["references"]}
    manifest = artifacts.resolve_reference(accepted[manifest_id])
    manifest_payload = json.loads(manifest.content)
    video_ref = manifest_payload["source_video_reference"]
    if accepted.get(video_ref["id"]) != video_ref:
        raise AuthoredRasterProductionError("Video is not accepted under its exact descriptor")
    earlier = _document(store, source_revision_id)
    if any(ref["id"] == video_ref["id"] for ref in earlier["references"]):
        raise AuthoredRasterProductionError("Source revision must precede accepted video")
    verified = verify_video_manifest(artifacts, manifest.document_reference())
    if (
        manifest_payload["source"]["frame_count"] != 2
        or manifest_payload["source"]["source_fps"] != [1, 1]
        or manifest_payload["sampling"]
        != {"frame_indices": [0, 1], "ticks_per_second": 12, "source_fps": [1, 1]}
        or tuple(frame.content for frame in verified.frames) != produced.frames
    ):
        raise AuthoredRasterProductionError("Exact full video frames/timing do not reproduce")
    for frame in verified.frames:
        if accepted.get(frame.artifact_id) != frame.document_reference():
            raise AuthoredRasterProductionError("Decoded frame is not accepted")

    # Reuse unchanged P2B replay (which independently verifies P2A and all lineage).
    scratch = ArtifactStore()
    for ref in document["references"]:
        snapshot = artifacts.resolve_reference(ref)
        scratch.import_bytes(
            snapshot.content,
            media_type=snapshot.media_type,
            kind=snapshot.kind,
            provenance=snapshot.provenance,
            locator=snapshot.descriptor.locator,
        )
    proposal = PrimitiveObservationAssemblyAdapter().propose(
        AdapterRequest(base_revision_id, document, ("document",), artifact_ids=p2a_ids), scratch
    )
    for actual_id, preview in zip(
        (p2b_observation_id, p2b_evidence_id), proposal.preview_artifacts, strict=True
    ):
        actual = artifacts.resolve_reference(accepted[actual_id])
        expected = scratch.get(preview.artifact_id)
        if (actual.content, actual.kind, actual.media_type, actual.provenance) != (
            expected.content,
            expected.kind,
            expected.media_type,
            expected.provenance,
        ):
            raise AuthoredRasterProductionError("Accepted P2B output does not reproduce")
    audit = json.loads(scratch.get(proposal.preview_artifacts[1].artifact_id).content)
    cv2, np = _opencv()
    occurrences = []
    for index, (frame, occurrence, evidence_id, audit_frame) in enumerate(
        zip(verified.frames, verified.occurrences, p2a_ids, audit["frames"], strict=True)
    ):
        payload = json.loads(artifacts.resolve_reference(accepted[evidence_id]).content)
        provenance = payload["occurrence_provenance"]
        if (
            provenance["manifest_artifact_id"] != manifest_id
            or provenance["occurrence_id"] != occurrence["occurrence_id"]
            or provenance["analysis_options"]
            != {"threshold": 128, "foreground": "dark", "connectivity": 8}
            or len(payload["evaluations"]) != 2
            or any(e["status"] != "SUPPORTED" for e in payload["evaluations"])
            or audit_frame["excluded"]
            or len(audit_frame["included"]) != 2
        ):
            raise AuthoredRasterProductionError("Requires complete two-part SUPPORTED observations")
        foreground, labels, components, _, _ = analyze_png(frame, OpenCVAnalysisOptions())
        if len(components) != 2:
            raise AuthoredRasterProductionError("Unexpected observed component set")
        parts, matched_labels = [], set()
        for key, png, measurement in zip(
            PART_KEYS, produced.contributions[index], produced.measurements[index], strict=True
        ):
            mask = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED) != 0
            matches = [
                int(label)
                for label in np.unique(labels)
                if label and np.array_equal(mask, labels == label)
            ]
            if len(matches) != 1 or matches[0] in matched_labels:
                raise AuthoredRasterProductionError("Exact contribution/component bijection failed")
            label = matches[0]
            matched_labels.add(label)
            ys, xs = np.where(mask)
            x, y, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
            digest = _component_digest(labels, label, x, y, right - x, bottom - y)
            candidates = [
                c
                for c in components
                if c["bounds"] == [x, y, right, bottom] and c["component_digest"] == digest
            ]
            if len(candidates) != 1:
                raise AuthoredRasterProductionError("Component lineage is ambiguous")
            evaluations = [
                e
                for e in payload["evaluations"]
                if e["component_id"] == candidates[0]["candidate_id"]
            ]
            if len(evaluations) != 1:
                raise AuthoredRasterProductionError("Evaluation lineage is ambiguous")
            evaluation = evaluations[0]
            included = [
                e
                for e in audit_frame["included"]
                if e["evaluation_id"] == evaluation["evaluation_id"]
            ]
            if len(included) != 1 or any(evaluation[k] != v for k, v in measurement.items()):
                raise AuthoredRasterProductionError("Observation/measurement lineage mismatch")
            parts.append(
                {
                    "part_key": key,
                    "contribution_artifact_id": "artifact:" + hashlib.sha256(png).hexdigest(),
                    "component_id": evaluation["component_id"],
                    "evaluation_id": evaluation["evaluation_id"],
                    "observation_id": included[0]["observation_id"],
                    **measurement,
                }
            )
        union = np.isin(labels, list(matched_labels))
        if not np.array_equal(union, foreground != 0):
            raise AuthoredRasterProductionError("Unexplained foreground")
        occurrences.append({**occurrence, "translation": list(TRANSLATIONS[index]), "parts": parts})
    subject = {"source_artifact_id": produced.source_reference["id"], "subject_path": [0]}
    payload = {
        "schema_version": "svm-authored-raster-production-0.1",
        "policy_identity": POLICY,
        "source_grammar": SOURCE_GRAMMAR,
        "canvas": [CANVAS, CANVAS],
        "source_revision_id": source_revision_id,
        "verification_revision_id": base_revision_id,
        "source_reference": produced.source_reference,
        "subject": subject,
        "part_identities": [{"subject": subject, "part_key": key} for key in PART_KEYS],
        "video_reference": video_ref,
        "manifest_reference": manifest.document_reference(),
        "p2a_references": [accepted[aid] for aid in p2a_ids],
        "p2b_observation_reference": accepted[p2b_observation_id],
        "p2b_evidence_reference": accepted[p2b_evidence_id],
        "occurrences": occurrences,
    }
    return payload, produced


def publish_verified_production(
    store: RevisionStore,
    base_revision_id: str,
    produced: ProducedRaster,
    manifest_id: str,
    p2a_ids: tuple[str, str],
    p2b_observation_id: str,
    p2b_evidence_id: str,
    artifacts: ArtifactRepository,
) -> ArtifactSnapshot:
    """Publish a replayable diagnostic artifact only; never accept it into a Document."""
    payload, expected = _replay(
        store,
        base_revision_id,
        produced.source_revision_id,
        manifest_id,
        p2a_ids,
        p2b_observation_id,
        p2b_evidence_id,
        artifacts,
    )
    if produced != expected:
        raise AuthoredRasterProductionError("Claimed source production differs from replay")
    for frame in expected.frames:
        artifacts.import_bytes(frame, media_type="image/png")
    for masks in expected.contributions:
        for mask in masks:
            artifacts.import_bytes(
                mask,
                media_type="image/png",
                kind=ArtifactKind.DERIVED,
                provenance={"policy_identity": POLICY, "role": "contribution"},
            )
    return artifacts.import_bytes(
        canonical_bytes(payload),
        media_type=MEDIA,
        kind=ArtifactKind.DERIVED,
        provenance={"policy_identity": POLICY},
    )


def verify_production(
    store: RevisionStore,
    base_revision_id: str,
    reference: dict[str, Any],
    artifacts: ArtifactRepository,
) -> None:
    """Independent full replay; report IDs, part IDs and claimed linkage are not authority."""
    report = artifacts.resolve_reference(reference)
    claimed = json.loads(report.content)
    payload, expected = _replay(
        store,
        base_revision_id,
        claimed["source_revision_id"],
        claimed["manifest_reference"]["id"],
        tuple(ref["id"] for ref in claimed["p2a_references"]),
        claimed["p2b_observation_reference"]["id"],
        claimed["p2b_evidence_reference"]["id"],
        artifacts,
    )
    if (
        report.content != canonical_bytes(payload)
        or report.media_type != MEDIA
        or report.kind != ArtifactKind.DERIVED
        or report.provenance != {"policy_identity": POLICY}
    ):
        raise AuthoredRasterProductionError("Production report does not reproduce")
    for masks in expected.contributions:
        for mask in masks:
            aid = "artifact:" + hashlib.sha256(mask).hexdigest()
            snapshot = artifacts.resolve_as(
                (aid,), kind=ArtifactKind.DERIVED, media_types=frozenset({"image/png"})
            )[0]
            if snapshot.content != mask or snapshot.provenance != {
                "policy_identity": POLICY,
                "role": "contribution",
            }:
                raise AuthoredRasterProductionError("Contribution artifact mismatch")
