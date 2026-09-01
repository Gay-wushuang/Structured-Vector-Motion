from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, replace
from typing import Any

from ..artifacts import ArtifactKind, ArtifactRepository
from ..evaluator import Evaluator, Quality, canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
    StructuralRelationPreview,
)
from ..renderers import SVGRenderer, SVGRenderOptions
from ..revisions import AppendReferencesChange, Transaction
from ..scene import EvaluatedEntity, EvaluatedScene, EvaluatedStyle, build_evaluated_scene
from .pop_output import POPOutputAdapter

ANALYSIS_MEDIA_TYPE = "application/vnd.svm.pop-topmost-coverage-analysis+json"
MASK_BUNDLE_MEDIA_TYPE = "application/vnd.svm.pop-coverage-masks+json"
ANALYSIS_IDENTITY = "svm-pop-topmost-coverage-analysis@0.1"
MASK_IDENTITY = "svm-pop-pixel-center-masks@0.1"
XRAY_IDENTITY = "svm-pop-xray-svg@0.1"
NORMAL_RENDER_IDENTITY = "svm-svg-renderer/pop-256@0.1"
RELATION_IDENTITY = "svm-pop-geometric-topmost-coverage@0.1"
CANVAS_SIZE = 256
MAX_PRIMITIVES = 256
SAMPLE_COORDINATE_PRECISION = ".12g"


class POPStructureError(ValueError):
    pass


class POPStructureAdapter:
    """Derive reviewable geometric topmost-coverage evidence from a POP scene."""

    adapter_id = "adapter:pop-structure"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise POPStructureError("POP structure scope must be empty or document")
        if request.options:
            raise POPStructureError("POP structure v0.1 does not accept options")
        namespace = _validate_exact_pop_scene(request, artifacts)
        evaluator = Evaluator(request.document)
        scene = build_evaluated_scene(request.document, evaluator, Quality.FINAL)
        primitives = scene.entities[1:]
        if not primitives or len(primitives) > MAX_PRIMITIVES:
            raise POPStructureError("POP structure requires between 1 and 256 primitives")

        full_masks = tuple(_geometry_mask(entity.geometry) for entity in primitives)
        topmost_masks = _topmost_masks(full_masks)
        source_document_hash = (
            f"sha256:{hashlib.sha256(canonical_bytes(request.document)).hexdigest()}"
        )
        normal_svg = SVGRenderer(_svg_options()).render(scene).encode("utf-8")
        xray_svg = SVGRenderer(_svg_options()).render(_xray_scene(scene)).encode("utf-8")
        base_provenance = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "engine": "svm-analytic-primitive-coverage",
            "engine_version": ANALYSIS_IDENTITY,
            "source_revision_id": request.base_revision_id,
            "source_document_hash": source_document_hash,
            "namespace": namespace,
        }
        normal_artifact = artifacts.import_bytes(
            normal_svg,
            media_type="image/svg+xml",
            kind=ArtifactKind.DERIVED,
            provenance={
                **base_provenance,
                "derived_type": "normal-render",
                "render_identity": NORMAL_RENDER_IDENTITY,
            },
        )
        xray_artifact = artifacts.import_bytes(
            xray_svg,
            media_type="image/svg+xml",
            kind=ArtifactKind.DERIVED,
            provenance={
                **base_provenance,
                "derived_type": "xray-render",
                "render_identity": XRAY_IDENTITY,
            },
        )
        mask_payload = _mask_payload(
            primitives,
            full_masks,
            topmost_masks,
            request.base_revision_id,
            source_document_hash,
        )
        mask_artifact = artifacts.import_bytes(
            canonical_bytes(mask_payload),
            media_type=MASK_BUNDLE_MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                **base_provenance,
                "derived_type": "pop-coverage-mask-bundle",
                "mask_identity": MASK_IDENTITY,
            },
        )
        analysis_payload = _analysis_payload(
            primitives,
            full_masks,
            topmost_masks,
            request.base_revision_id,
            source_document_hash,
            normal_artifact.artifact_id,
            xray_artifact.artifact_id,
            mask_artifact.artifact_id,
        )
        analysis_artifact = artifacts.import_bytes(
            canonical_bytes(analysis_payload),
            media_type=ANALYSIS_MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                **base_provenance,
                "derived_type": "pop-topmost-coverage-analysis",
                "analysis_identity": ANALYSIS_IDENTITY,
                "mask_identity": MASK_IDENTITY,
                "relation_identity": RELATION_IDENTITY,
            },
        )
        derived = (normal_artifact, xray_artifact, mask_artifact, analysis_artifact)
        references = tuple(artifact.document_reference() for artifact in derived)
        parameters = {
            "analysis_identity": ANALYSIS_IDENTITY,
            "mask_identity": MASK_IDENTITY,
            "xray_identity": XRAY_IDENTITY,
            "normal_render_identity": NORMAL_RENDER_IDENTITY,
            "relation_identity": RELATION_IDENTITY,
            "canvas": [CANVAS_SIZE, CANVAS_SIZE],
            "coverage_sample": "pixel-center",
            "sample_coordinate_canonicalization": SAMPLE_COORDINATE_PRECISION,
            "coverage_basis": "topmost-later-render-stack-geometric-coverage",
            "source_document_hash": source_document_hash,
        }
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="svm-analytic-primitive-coverage",
            engine_version=ANALYSIS_IDENTITY,
            parameters=parameters,
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "generator": asdict(generator),
                    "analysis": analysis_payload,
                    "references": references,
                }
            )
        ).hexdigest()[:16]
        relation_previews = tuple(
            StructuralRelationPreview(
                relation_id=relation["relation_id"],
                relation_type="geometric-topmost-covers",
                status="evidence",
                source=relation["topmost_entity_id"],
                target=relation["covered_entity_id"],
                evidence_artifact_id=analysis_artifact.artifact_id,
            )
            for relation in analysis_payload["topmost_coverage_relations"]
        )
        fully_covered = sum(
            1 for item in analysis_payload["entities"] if item["topmost_pixels"] == 0
        )
        return Proposal(
            proposal_id=f"proposal:pop-structure:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:pop-structure:{digest}",
                changes=(AppendReferencesChange(references),),
                message="Attach deterministic POP geometric topmost coverage evidence",
            ),
            report=EvaluationReport(
                metrics={
                    "primitives": float(len(primitives)),
                    "topmost_coverage_relations": float(len(relation_previews)),
                    "fully_covered_primitives": float(fully_covered),
                }
            ),
            preview_artifacts=tuple(
                PreviewArtifact(
                    artifact_id=artifact.artifact_id,
                    content_hash=artifact.content_hash,
                    media_type=artifact.media_type,
                )
                for artifact in derived
            ),
            preview=ProposalPreview(structural_relations=relation_previews),
            required_artifact_ids=tuple(artifact.artifact_id for artifact in derived),
            confidence=None,
            notes=(
                "Topmost coverage is geometric pixel evidence only; no hierarchy, grouping, "
                "semantic label, or render-order change is proposed"
            ),
        )


def _validate_exact_pop_scene(request: AdapterRequest, artifacts: ArtifactRepository) -> str:
    render_stack = request.document.get("presentation", {}).get("render_stack")
    if not isinstance(render_stack, list) or len(render_stack) < 2:
        raise POPStructureError("POP structure requires an accepted rendered POP scene")
    background_id = render_stack[0]
    prefix = "entity:"
    suffix = "-background"
    if (
        not isinstance(background_id, str)
        or not background_id.startswith(prefix)
        or not background_id.endswith(suffix)
    ):
        raise POPStructureError("POP background Entity ID cannot identify its namespace")
    namespace = background_id[len(prefix) : -len(suffix)]
    if not namespace:
        raise POPStructureError("POP namespace is empty")
    if len(request.artifact_ids) != 2:
        raise POPStructureError("POP structure requires the exact prefix and output Artifacts")
    empty = {
        "entities": [],
        "construction": {"operations": [], "output_bindings": []},
        "presentation": {"render_stack": [], "styles": []},
    }
    try:
        expected = POPOutputAdapter().propose(
            AdapterRequest(
                base_revision_id=request.base_revision_id,
                document=empty,
                scope=("document",),
                artifact_ids=request.artifact_ids,
                options={"namespace": namespace},
            ),
            artifacts,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise POPStructureError("POP structure input Artifacts are invalid") from exc
    change = expected.transaction.changes[0]
    fragment = getattr(change, "fragment", None)
    if fragment is None:
        raise POPStructureError("POP structure could not reconstruct the accepted scene")
    actual = request.document
    comparisons = (
        (actual.get("entities"), list(fragment.entities)),
        (actual.get("construction", {}).get("operations"), list(fragment.operations)),
        (
            actual.get("construction", {}).get("output_bindings"),
            list(fragment.output_bindings),
        ),
        (actual.get("presentation", {}).get("render_stack"), list(fragment.render_entries)),
        (actual.get("presentation", {}).get("styles"), list(fragment.styles)),
    )
    if any(left != right for left, right in comparisons):
        raise POPStructureError(
            "POP structure v0.1 requires the unchanged accepted POP primitive scene"
        )
    return namespace


def _svg_options() -> SVGRenderOptions:
    return SVGRenderOptions(width=256, height=256, view_box=(0, 0, 256, 256))


def _xray_scene(scene: EvaluatedScene) -> EvaluatedScene:
    entities: list[EvaluatedEntity] = []
    for index, entity in enumerate(scene.entities):
        if index == 0:
            style = EvaluatedStyle(fill="#101018", stroke="none", stroke_width=0, opacity=1)
        else:
            fill = entity.style.fill if entity.style is not None else "#FFFFFF"
            style = EvaluatedStyle(fill=fill, stroke="#FFFFFF", stroke_width=0.5, opacity=0.2)
        entities.append(replace(entity, style=style))
    return replace(scene, entities=tuple(entities))


def _geometry_mask(geometry: dict[str, Any]) -> int:
    primitive = geometry
    inverse: tuple[float, float, float, float, float, float] | None = None
    if geometry.get("kind") == "transform":
        primitive = geometry.get("source")
        matrix = geometry.get("matrix")
        if not isinstance(primitive, dict) or not isinstance(matrix, list) or len(matrix) != 6:
            raise POPStructureError("POP transformed geometry is invalid")
        inverse = _inverse_matrix(
            (
                float(matrix[0]),
                float(matrix[1]),
                float(matrix[2]),
                float(matrix[3]),
                float(matrix[4]),
                float(matrix[5]),
            )
        )
    if primitive.get("kind") not in {"rectangle", "ellipse"}:
        raise POPStructureError("POP structure supports only rectangles and ellipses")
    mask = 0
    for y in range(CANVAS_SIZE):
        sample_y = y + 0.5
        row_offset = y * CANVAS_SIZE
        for x in range(CANVAS_SIZE):
            sample_x = x + 0.5
            if inverse is not None:
                sample_x, sample_y_local = _transform_point(inverse, sample_x, sample_y)
            else:
                sample_y_local = sample_y
            if _primitive_contains(primitive, sample_x, sample_y_local):
                mask |= 1 << (row_offset + x)
    return mask


def _inverse_matrix(
    matrix: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a, b, c, d, e, f = matrix
    determinant = a * d - b * c
    if not math.isfinite(determinant) or abs(determinant) <= 1e-15:
        raise POPStructureError("POP transform is not invertible")
    return (
        d / determinant,
        -b / determinant,
        -c / determinant,
        a / determinant,
        (c * f - d * e) / determinant,
        (b * e - a * f) / determinant,
    )


def _transform_point(
    matrix: tuple[float, float, float, float, float, float], x: float, y: float
) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _primitive_contains(primitive: dict[str, Any], x: float, y: float) -> bool:
    x = float(format(x, SAMPLE_COORDINATE_PRECISION))
    y = float(format(y, SAMPLE_COORDINATE_PRECISION))
    if primitive["kind"] == "rectangle":
        left = float(primitive["x"])
        top = float(primitive["y"])
        return left <= x < left + float(primitive["width"]) and top <= y < top + float(
            primitive["height"]
        )
    rx = float(primitive["rx"])
    ry = float(primitive["ry"])
    if rx <= 0 or ry <= 0:
        raise POPStructureError("POP ellipse radii must be positive")
    dx = (x - float(primitive["cx"])) / rx
    dy = (y - float(primitive["cy"])) / ry
    return dx * dx + dy * dy <= 1


def _topmost_masks(full_masks: tuple[int, ...]) -> tuple[int, ...]:
    covered = 0
    reversed_topmost: list[int] = []
    for full_mask in reversed(full_masks):
        reversed_topmost.append(full_mask & ~covered)
        covered |= full_mask
    return tuple(reversed(reversed_topmost))


def _mask_payload(
    primitives: tuple[EvaluatedEntity, ...],
    full_masks: tuple[int, ...],
    topmost_masks: tuple[int, ...],
    revision_id: str,
    document_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "svm-pop-coverage-masks-0.1",
        "identity": MASK_IDENTITY,
        "source_revision_id": revision_id,
        "source_document_hash": document_hash,
        "image": {"width": CANVAS_SIZE, "height": CANVAS_SIZE},
        "coverage_sample": "pixel-center",
        "sample_coordinate_canonicalization": SAMPLE_COORDINATE_PRECISION,
        "entities": [
            {
                "entity_id": entity.entity_id,
                "render_index": index + 1,
                "full_pixels": full_mask.bit_count(),
                "topmost_pixels": topmost_mask.bit_count(),
                "full_runs": _runs(full_mask),
                "topmost_runs": _runs(topmost_mask),
            }
            for index, (entity, full_mask, topmost_mask) in enumerate(
                zip(primitives, full_masks, topmost_masks, strict=True)
            )
        ],
    }


def _analysis_payload(
    primitives: tuple[EvaluatedEntity, ...],
    full_masks: tuple[int, ...],
    topmost_masks: tuple[int, ...],
    revision_id: str,
    document_hash: str,
    normal_artifact_id: str,
    xray_artifact_id: str,
    mask_artifact_id: str,
) -> dict[str, Any]:
    entities = []
    for index, (entity, full_mask, topmost_mask) in enumerate(
        zip(primitives, full_masks, topmost_masks, strict=True)
    ):
        full_pixels = full_mask.bit_count()
        topmost_pixels = topmost_mask.bit_count()
        entities.append(
            {
                "entity_id": entity.entity_id,
                "render_index": index + 1,
                "full_pixels": full_pixels,
                "topmost_pixels": topmost_pixels,
                "covered_by_later_pixels": full_pixels - topmost_pixels,
                "topmost_ratio": _ratio(topmost_pixels, full_pixels),
                "fully_covered_by_later": topmost_pixels == 0,
            }
        )
    relations = []
    for lower_index, (lower_entity, lower_mask) in enumerate(
        zip(primitives, full_masks, strict=True)
    ):
        for upper_index in range(lower_index + 1, len(primitives)):
            coverage_pixels = (lower_mask & topmost_masks[upper_index]).bit_count()
            if coverage_pixels == 0:
                continue
            content = {
                "topmost_entity_id": primitives[upper_index].entity_id,
                "covered_entity_id": lower_entity.entity_id,
                "topmost_render_index": upper_index + 1,
                "covered_render_index": lower_index + 1,
                "coverage_pixels": coverage_pixels,
                "covered_fraction": _ratio(coverage_pixels, lower_mask.bit_count()),
                "basis": "geometric-topmost-coverage@0.1",
            }
            relations.append({"relation_id": _relation_id(content), **content})
    return {
        "schema_version": "svm-pop-topmost-coverage-analysis-0.1",
        "identity": ANALYSIS_IDENTITY,
        "relation_identity": RELATION_IDENTITY,
        "source_revision_id": revision_id,
        "source_document_hash": document_hash,
        "image": {"width": CANVAS_SIZE, "height": CANVAS_SIZE},
        "normal_render_artifact_id": normal_artifact_id,
        "xray_render_artifact_id": xray_artifact_id,
        "mask_bundle_artifact_id": mask_artifact_id,
        "entities": entities,
        "topmost_coverage_relations": relations,
        "semantic_claims": [],
    }


def _relation_id(content: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_bytes({"identity": RELATION_IDENTITY, **content})).hexdigest()
    return f"relation:geometric-topmost-covers:{digest}"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise POPStructureError("POP primitive has no covered pixel centers")
    return float(format(numerator / denominator, ".12g"))


def _runs(mask: int) -> list[list[int]]:
    runs: list[list[int]] = []
    for y in range(CANVAS_SIZE):
        row = (mask >> (y * CANVAS_SIZE)) & ((1 << CANVAS_SIZE) - 1)
        x = 0
        while x < CANVAS_SIZE:
            while x < CANVAS_SIZE and not (row >> x) & 1:
                x += 1
            if x == CANVAS_SIZE:
                break
            start = x
            while x < CANVAS_SIZE and (row >> x) & 1:
                x += 1
            runs.append([y, start, x])
    return runs
