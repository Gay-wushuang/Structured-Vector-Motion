from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..backends.polygon_set import canonicalize_polygon_set
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
)
from ..revisions import AttachRasterGeometryObservationsChange, Transaction
from .opencv_analysis import OpenCVAnalysisAdapter, OpenCVAnalysisOptions, _opencv, analyze_png
from .temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2

POLICY_IDENTITY = "svm-controlled-raster-geometry@0.1"
PRIMITIVE_TYPE = "controlled-raster-polygon@0.1"
CONTOUR_TOLERANCE = 1.0


class RasterGeometryObservationError(ValueError):
    pass


class RasterGeometryObservationAdapter:
    """Two explicitly selected pixel occurrences, ending at observation evidence."""

    adapter_id = "adapter:raster-geometry-observations"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)} or set(request.options) != {"occurrences"}:
            raise RasterGeometryObservationError(
                "Explicit raster occurrences and document scope required"
            )
        occurrences = copy.deepcopy(request.options["occurrences"])
        _validate_occurrences(occurrences)
        expected_ids = {item["analysis_artifact_id"] for item in occurrences}
        if set(request.artifact_ids) != expected_ids or len(request.artifact_ids) != len(
            expected_ids
        ):
            raise RasterGeometryObservationError(
                "Request must list exactly the selected analysis Artifacts"
            )
        accepted = {ref["id"]: ref for ref in request.document["references"]}
        dependencies: dict[str, dict[str, Any]] = {}
        for occurrence in occurrences:
            analysis_id = occurrence["analysis_artifact_id"]
            if analysis_id not in accepted:
                raise RasterGeometryObservationError("Raster analysis must already be accepted")
            analysis = artifacts.resolve_reference(accepted[analysis_id])
            payload = json.loads(analysis.content)
            for artifact_id in (
                analysis_id,
                payload["source_artifact_id"],
                payload["binary_mask_artifact_id"],
            ):
                if artifact_id not in accepted:
                    raise RasterGeometryObservationError("Raster lineage must already be accepted")
                dependencies[artifact_id] = accepted[artifact_id]
        references = tuple(dependencies[key] for key in sorted(dependencies))
        resolved = {ref["id"]: artifacts.resolve_reference(ref) for ref in references}
        payload, provenance = derive_raster_observations(occurrences, resolved)
        observation = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=OBSERVATION_MEDIA_TYPE_V2,
            kind=ArtifactKind.REFERENCE,
            provenance=provenance,
        )
        generator = GeneratorProvenance(
            self.adapter_id,
            self.adapter_version,
            "OpenCV pixel contours",
            POLICY_IDENTITY,
            provenance,
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base": request.base_revision_id,
                    "generator": asdict(generator),
                    "output": observation.artifact_id,
                }
            )
        ).hexdigest()[:16]
        return Proposal(
            proposal_id=f"proposal:raster-observations:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                f"transaction:raster-observations:{digest}",
                (
                    AttachRasterGeometryObservationsChange(
                        observation.document_reference(),
                        references,
                        tuple(occurrences),
                        POLICY_IDENTITY,
                    ),
                ),
                "Attach verified raster geometry occurrences",
            ),
            report=EvaluationReport(metrics={"observations": 2.0}),
            preview_artifacts=(
                PreviewArtifact(
                    observation.artifact_id, observation.content_hash, observation.media_type
                ),
            ),
            required_artifact_ids=(observation.artifact_id, *sorted(dependencies)),
        )


def _validate_occurrences(occurrences: Any) -> None:
    if not isinstance(occurrences, (list, tuple)) or len(occurrences) != 2:
        raise RasterGeometryObservationError("Exactly two explicit occurrences required")
    for item in occurrences:
        if not isinstance(item, dict) or set(item) != {
            "analysis_artifact_id",
            "component_id",
            "tick",
        }:
            raise RasterGeometryObservationError("Occurrence fields are invalid")
        if (
            type(item["tick"]) is not int
            or item["tick"] < 0
            or any(
                not isinstance(item[k], str) or not item[k]
                for k in ("analysis_artifact_id", "component_id")
            )
        ):
            raise RasterGeometryObservationError("Occurrence selector or tick is invalid")
    if occurrences[0]["tick"] >= occurrences[1]["tick"]:
        raise RasterGeometryObservationError("Occurrence ticks must increase")


def derive_raster_observations(
    occurrences: Any, resolved: dict[str, ArtifactSnapshot]
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_occurrences(occurrences)
    frames, lineage = [], []
    canvas = None
    for occurrence in occurrences:
        analysis = resolved[occurrence["analysis_artifact_id"]]
        payload = json.loads(analysis.content)
        source = resolved[payload["source_artifact_id"]]
        mask_snapshot = resolved[payload["binary_mask_artifact_id"]]
        if source.kind != ArtifactKind.REFERENCE or source.media_type != "image/png":
            raise RasterGeometryObservationError("Raster source must be a Reference PNG")
        options = OpenCVAnalysisOptions.from_mapping(
            {
                "threshold": payload["threshold"]["value"],
                "foreground": payload["threshold"]["foreground"],
                "connectivity": payload["connectivity"],
            }
        )
        # Reuse the existing producer to verify bytes and descriptors,
        # including exact engine versions.
        scratch = ArtifactStore()
        scratch.import_bytes(
            source.content,
            media_type=source.media_type,
            kind=source.kind,
            provenance=source.provenance,
        )
        proposal = OpenCVAnalysisAdapter().propose(
            AdapterRequest(
                "verification",
                {},
                ("document",),
                artifact_ids=(source.artifact_id,),
                options=asdict(options),
            ),
            scratch,
        )
        for actual, preview in zip(
            (mask_snapshot, analysis), proposal.preview_artifacts, strict=True
        ):
            expected = scratch.get(preview.artifact_id)
            if (
                actual.content != expected.content
                or actual.kind != expected.kind
                or actual.media_type != expected.media_type
                or actual.provenance != expected.provenance
            ):
                raise RasterGeometryObservationError(
                    "Raster analysis lineage does not match PNG pixels"
                )
        mask, labels, components, width, height = analyze_png(source, options)
        matches = [c for c in components if c["candidate_id"] == occurrence["component_id"]]
        if len(matches) != 1:
            raise RasterGeometryObservationError("Selected raster component is absent or ambiguous")
        component = matches[0]
        cv2, np = _opencv()
        gray = cv2.imdecode(np.frombuffer(source.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if (
            len(np.unique(gray)) != 2
            or len(np.unique(gray[mask == 0])) != 1
            or len(np.unique(gray[mask != 0])) != 1
        ):
            raise RasterGeometryObservationError(
                "Controlled raster requires flat background and solid foreground"
            )
        x, y, right, bottom = component["bounds"]
        crop = labels[y:bottom, x:right]
        # Exact component membership is identified by the existing canonical pixel-set digest.
        from .opencv_analysis import _component_digest

        matching_labels = [
            int(label)
            for label in np.unique(crop)
            if label
            and _component_digest(labels, int(label), x, y, right - x, bottom - y)
            == component["component_digest"]
        ]
        if len(matching_labels) != 1:
            raise RasterGeometryObservationError("Selected component pixel set is ambiguous")
        selected = np.where(labels == matching_labels[0], 255, 0).astype(np.uint8)
        points = contour_landmarks(selected)
        if canvas is not None and canvas != [width, height]:
            raise RasterGeometryObservationError("Raster frame dimensions must match")
        canvas = [width, height]
        identity = {
            "source_png_artifact_id": source.artifact_id,
            "tick": occurrence["tick"],
            "component_id": occurrence["component_id"],
            "policy_identity": POLICY_IDENTITY,
            "analysis_policy": asdict(options),
        }
        value = int(gray[selected != 0][0])
        frames.append(
            {
                "tick": occurrence["tick"],
                "primitives": [
                    {
                        "observation_id": "observation:raster:"
                        + hashlib.sha256(canonical_bytes(identity)).hexdigest(),
                        "primitive_type": PRIMITIVE_TYPE,
                        "bounds": component["bounds"],
                        "fill": f"#{value:02X}{value:02X}{value:02X}",
                        "geometry": {
                            "type": "ordered-landmarks",
                            "points": points,
                            "rotation_symmetry": "none",
                        },
                    }
                ],
            }
        )
        lineage.append(
            {
                **identity,
                "analysis_artifact_id": analysis.artifact_id,
                "mask_artifact_id": mask_snapshot.artifact_id,
                "component_digest": component["component_digest"],
                "analysis_provenance": analysis.provenance,
            }
        )
    return {
        "schema_version": "svm-primitive-observations-0.2",
        "canvas": canvas,
        "frames": frames,
    }, {
        "producer_identity": POLICY_IDENTITY,
        "geometry_observation_policy": POLICY_IDENTITY,
        "contour_tolerance_pixels": CONTOUR_TOLERANCE,
        "source_occurrences": lineage,
    }


def contour_landmarks(mask: Any) -> list[list[float]]:
    cv2, _ = _opencv()
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if len(contours) != 1 or hierarchy is None or abs(cv2.contourArea(contours[0])) < 256:
        raise RasterGeometryObservationError(
            "One non-degenerate hole-free polygon contour required"
        )
    raw = cv2.approxPolyDP(contours[0], CONTOUR_TOLERANCE, True).reshape(-1, 2).tolist()
    points = canonicalize_polygon_set([{"exterior": raw, "holes": []}])["polygons"][0]["exterior"][
        :-1
    ]
    if not 3 <= len(points) <= 32:
        raise RasterGeometryObservationError("Unsupported polygon landmark count")
    lengths = [math.dist(point, points[(i + 1) % len(points)]) for i, point in enumerate(points)]
    ordered = sorted(lengths)
    if ordered[0] < 8 or ordered[-1] - ordered[-2] <= 4:
        raise RasterGeometryObservationError("Raster landmark origin is ambiguous or degenerate")
    start = lengths.index(ordered[-1])
    return points[start:] + points[:start]


def verify_raster_geometry_observations_change(
    change: Any, resolved: dict[str, ArtifactSnapshot]
) -> None:
    if change.policy_identity != POLICY_IDENTITY:
        raise ValueError("Unsupported raster geometry policy")
    output = resolved[change.observation_reference["id"]]
    payload, provenance = derive_raster_observations(change.occurrences, resolved)
    expected_ids = {
        value
        for occurrence in provenance["source_occurrences"]
        for value in (
            occurrence["source_png_artifact_id"],
            occurrence["analysis_artifact_id"],
            occurrence["mask_artifact_id"],
        )
    }
    if {ref["id"] for ref in change.source_references} != expected_ids:
        raise ValueError("Raster dependencies do not match exact lineage")
    if (
        output.kind != ArtifactKind.REFERENCE
        or output.media_type != OBSERVATION_MEDIA_TYPE_V2
        or output.content != canonical_bytes(payload)
        or output.provenance != provenance
    ):
        raise ValueError("Raster occurrence does not match its exact PNG analysis lineage")


def raster_source_ids(snapshot: ArtifactSnapshot) -> tuple[str, ...]:
    """Exact immutable dependencies needed to reverify a raster observation."""
    if snapshot.provenance.get("geometry_observation_policy") != POLICY_IDENTITY:
        raise RasterGeometryObservationError("Raster similarity requires raster geometry policy")
    occurrences = snapshot.provenance.get("source_occurrences")
    if not isinstance(occurrences, list) or len(occurrences) != 2:
        raise RasterGeometryObservationError("Raster geometry requires its pixel lineage")
    return tuple(
        sorted(
            {
                occurrence[key]
                for occurrence in occurrences
                for key in ("source_png_artifact_id", "analysis_artifact_id", "mask_artifact_id")
            }
        )
    )


def verify_raster_observation(
    snapshot: ArtifactSnapshot, resolved: dict[str, ArtifactSnapshot]
) -> None:
    source_ids = raster_source_ids(snapshot)
    occurrences = tuple(
        {key: occurrence[key] for key in ("analysis_artifact_id", "component_id", "tick")}
        for occurrence in snapshot.provenance["source_occurrences"]
    )
    verify_raster_geometry_observations_change(
        AttachRasterGeometryObservationsChange(
            snapshot.document_reference(),
            tuple(resolved[aid].document_reference() for aid in source_ids),
            occurrences,
            POLICY_IDENTITY,
        ),
        {**resolved, snapshot.artifact_id: snapshot},
    )
