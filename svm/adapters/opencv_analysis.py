from __future__ import annotations

import hashlib
import importlib.metadata
import math
import struct
import zlib
from dataclasses import asdict, dataclass
from typing import Any

from ..artifacts import (
    ArtifactKind,
    ArtifactRepository,
    ArtifactSnapshot,
)
from ..evaluator import canonical_bytes
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalPreview,
    StructuralCandidatePreview,
)
from ..revisions import AppendReferencesChange, Transaction
from .bitmap_trace import BITMAP_MEDIA_TYPES

ANALYSIS_MEDIA_TYPE = "application/vnd.svm.component-analysis+json"
ANALYSIS_IDENTITY = "svm-opencv-components@0.1"
MASK_IDENTITY = "svm-binary-mask-png@0.1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class OpenCVAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class OpenCVAnalysisOptions:
    threshold: int = 128
    foreground: str = "dark"
    connectivity: int = 8

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> OpenCVAnalysisOptions:
        unknown = sorted(set(values) - set(cls.__dataclass_fields__))
        if unknown:
            raise OpenCVAnalysisError(f"Unknown OpenCV analysis option(s): {', '.join(unknown)}")
        options = cls(**values)
        if type(options.threshold) is not int or not 0 <= options.threshold <= 255:
            raise OpenCVAnalysisError("threshold must be an integer between 0 and 255")
        if options.foreground not in {"dark", "light"}:
            raise OpenCVAnalysisError("foreground must be dark or light")
        if options.connectivity != 8:
            raise OpenCVAnalysisError("OpenCV analysis v0.1 requires 8-connectivity")
        return options


class OpenCVAnalysisAdapter:
    adapter_id = "adapter:opencv-analysis"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactRepository) -> Proposal:
        if request.scope not in {(), ("document",)}:
            raise OpenCVAnalysisError("OpenCV analysis scope must be empty or document")
        source = _select_source(
            artifacts.resolve_as(
                request.artifact_ids,
                kind=ArtifactKind.REFERENCE,
                media_types=frozenset(BITMAP_MEDIA_TYPES),
            )
        )
        options = OpenCVAnalysisOptions.from_mapping(request.options)
        cv2, np = _opencv()
        width, height, color_type = _png_header(source.content)
        if width * height > 16_000_000:
            raise OpenCVAnalysisError("PNG exceeds the 16 megapixel analysis limit")
        if color_type in {4, 6}:
            raise OpenCVAnalysisError("PNG alpha/transparency is not supported in v0.1")
        encoded = np.frombuffer(source.content, dtype=np.uint8)
        grayscale = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        if grayscale is None or grayscale.shape != (height, width):
            raise OpenCVAnalysisError("OpenCV could not decode the declared PNG image")
        comparison = cv2.CMP_LE if options.foreground == "dark" else cv2.CMP_GE
        mask = cv2.compare(grayscale, options.threshold, comparison)
        count, _, stats, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=options.connectivity, ltype=cv2.CV_32S
        )
        candidates = []
        for label in range(1, count):
            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            component_width = int(stats[label, cv2.CC_STAT_WIDTH])
            component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
            area = int(stats[label, cv2.CC_STAT_AREA])
            centroid = (
                _canonical_number(float(centroids[label, 0])),
                _canonical_number(float(centroids[label, 1])),
            )
            candidates.append(
                {
                    "bounds": [x, y, x + component_width, y + component_height],
                    "pixel_area": area,
                    "centroid": list(centroid),
                }
            )
        candidates.sort(
            key=lambda item: (
                item["bounds"][1],
                item["bounds"][0],
                item["bounds"][3],
                item["bounds"][2],
                item["pixel_area"],
                item["centroid"],
            )
        )
        for index, candidate in enumerate(candidates, start=1):
            candidate["candidate_id"] = f"candidate:component-{index:04d}"

        engine_version = importlib.metadata.version("opencv-python-headless")
        parameters = {
            "threshold": options.threshold,
            "foreground": options.foreground,
            "connectivity": options.connectivity,
            "analysis_identity": ANALYSIS_IDENTITY,
            "mask_identity": MASK_IDENTITY,
            "opencv_runtime_version": cv2.__version__,
        }
        provenance = {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "engine": "opencv-python-headless",
            "engine_version": engine_version,
            "parameters": parameters,
            "source_artifact_id": source.artifact_id,
            "source_content_hash": source.content_hash,
        }
        mask_artifact = artifacts.import_bytes(
            _encode_mask_png(mask, width, height, source.content_hash),
            media_type="image/png",
            kind=ArtifactKind.DERIVED,
            provenance={**provenance, "derived_type": "binary-mask"},
        )
        analysis_payload = {
            "schema_version": "svm-component-analysis-0.1",
            "source_artifact_id": source.artifact_id,
            "source_content_hash": source.content_hash,
            "image": {"width": width, "height": height},
            "threshold": {
                "value": options.threshold,
                "foreground": options.foreground,
                "comparison": "<=" if options.foreground == "dark" else ">=",
            },
            "connectivity": options.connectivity,
            "binary_mask_artifact_id": mask_artifact.artifact_id,
            "components": candidates,
        }
        analysis_artifact = artifacts.import_bytes(
            canonical_bytes(analysis_payload),
            media_type=ANALYSIS_MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={**provenance, "derived_type": "component-analysis"},
        )
        derived = (mask_artifact, analysis_artifact)
        references = (source.document_reference(),) + tuple(
            artifact.document_reference() for artifact in derived
        )
        generator = GeneratorProvenance(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            engine="opencv-python-headless",
            engine_version=engine_version,
            parameters=parameters,
        )
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "base_revision_id": request.base_revision_id,
                    "generator": asdict(generator),
                    "references": references,
                    "analysis": analysis_payload,
                }
            )
        ).hexdigest()[:16]
        previews = tuple(
            PreviewArtifact(
                artifact_id=artifact.artifact_id,
                content_hash=artifact.content_hash,
                media_type=artifact.media_type,
            )
            for artifact in derived
        )
        structural_candidates = tuple(
            StructuralCandidatePreview(
                candidate_id=candidate["candidate_id"],
                bounds=tuple(candidate["bounds"]),
                pixel_area=candidate["pixel_area"],
                centroid=tuple(candidate["centroid"]),
            )
            for candidate in candidates
        )
        return Proposal(
            proposal_id=f"proposal:opencv-analysis:{digest}",
            base_revision_id=request.base_revision_id,
            generator=generator,
            transaction=Transaction(
                transaction_id=f"transaction:opencv-analysis:{digest}",
                changes=(AppendReferencesChange(references),),
                message="Attach deterministic OpenCV component analysis evidence",
            ),
            report=EvaluationReport(
                metrics={
                    "connected_components": float(len(candidates)),
                    "foreground_pixels": float(sum(item["pixel_area"] for item in candidates)),
                }
            ),
            preview_artifacts=previews,
            preview=ProposalPreview(structural_candidates=structural_candidates),
            required_artifact_ids=tuple(reference["id"] for reference in references),
            confidence=1.0,
            notes="Deterministic pixel analysis; candidates are not Entities",
        )


def _select_source(snapshots: tuple[ArtifactSnapshot, ...]) -> ArtifactSnapshot:
    if len(snapshots) != 1:
        raise OpenCVAnalysisError("OpenCV analysis requires exactly one PNG Artifact")
    source = snapshots[0]
    if len(source.content) > 32 * 1024 * 1024:
        raise OpenCVAnalysisError("PNG Artifact exceeds the 32 MiB analysis limit")
    return source


def _opencv() -> tuple[Any, Any]:
    try:
        import cv2  # pyright: ignore[reportMissingImports]
        import numpy as np
    except ImportError as exc:
        raise OpenCVAnalysisError(
            "OpenCV analysis requires the 'analysis' optional dependency"
        ) from exc
    return cv2, np


def _png_header(content: bytes) -> tuple[int, int, int]:
    if len(content) < 29 or content[:8] != PNG_SIGNATURE or content[12:16] != b"IHDR":
        raise OpenCVAnalysisError("Artifact bytes must contain a valid PNG IHDR")
    width, height = struct.unpack(">II", content[16:24])
    if width == 0 or height == 0:
        raise OpenCVAnalysisError("PNG dimensions must be positive")
    offset = 8
    while offset + 12 <= len(content):
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(content):
            raise OpenCVAnalysisError("PNG contains a truncated chunk")
        chunk_type = content[offset + 4 : offset + 8]
        if chunk_type == b"tRNS":
            raise OpenCVAnalysisError("PNG alpha/transparency is not supported in v0.1")
        offset = end
        if chunk_type == b"IEND":
            break
    return width, height, content[25]


def _encode_mask_png(mask: Any, width: int, height: int, source_hash: str) -> bytes:
    pixels = memoryview(mask).tobytes()
    if len(pixels) != width * height:
        raise OpenCVAnalysisError("Binary mask storage does not match PNG dimensions")
    scanlines = b"".join(b"\x00" + pixels[row * width : (row + 1) * width] for row in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    metadata = f"binary-mask-v0.1;source={source_hash}".encode("ascii")
    return b"".join(
        (
            PNG_SIGNATURE,
            _png_chunk(b"IHDR", ihdr),
            _png_chunk(b"tEXt", b"SVMArtifact\x00" + metadata),
            _png_chunk(b"IDAT", _stored_zlib(scanlines)),
            _png_chunk(b"IEND", b""),
        )
    )


def _stored_zlib(content: bytes) -> bytes:
    blocks = []
    for offset in range(0, len(content), 65_535):
        block = content[offset : offset + 65_535]
        final = offset + len(block) == len(content)
        length = len(block)
        blocks.append(
            bytes((1 if final else 0,))
            + struct.pack("<H", length)
            + struct.pack("<H", 0xFFFF ^ length)
            + block
        )
    return b"\x78\x01" + b"".join(blocks) + struct.pack(">I", zlib.adler32(content) & 0xFFFFFFFF)


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _canonical_number(value: float) -> float:
    if not math.isfinite(value):
        raise OpenCVAnalysisError("OpenCV produced a non-finite centroid")
    return float(format(value, ".12g"))
