"""Bounded lossless video input processing; no Document or authoring authority."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .adapters.opencv_analysis import _encode_mask_png, _opencv, _png_header
from .artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot
from .evaluator import canonical_bytes

POLICY = "svm-controlled-avi-ffv1-ingestion@0.1"
RASTER_POLICY = "svm-exact-binary-gray8-video-frames@0.1"
MANIFEST_MEDIA = "application/vnd.svm.video-frame-manifest+json;version=0.1"
WHEEL_VERSION = "4.14.0.94"
MAX_PIXELS = 16_000_000
MAX_FRAMES = 256


class VideoIngestionError(ValueError):
    pass


@dataclass(frozen=True)
class VideoSampling:
    frame_indices: tuple[int, ...]
    ticks_per_second: int
    source_fps: tuple[int, int] | None = None

    def validate(self) -> None:
        if (
            not isinstance(self.frame_indices, tuple)
            or not 1 <= len(self.frame_indices) <= MAX_FRAMES
            or any(type(i) is not int or not 0 <= i < MAX_FRAMES for i in self.frame_indices)
            or tuple(sorted(set(self.frame_indices))) != self.frame_indices
        ):
            raise VideoIngestionError("Frame indices must be explicit, unique, increasing integers")
        if (
            type(self.ticks_per_second) is not int
            or not 1 <= self.ticks_per_second <= 1_000_000_000
        ):
            raise VideoIngestionError("ticks_per_second must be a positive bounded integer")
        if self.source_fps is not None and (
            not isinstance(self.source_fps, tuple)
            or len(self.source_fps) != 2
            or any(type(v) is not int or v <= 0 for v in self.source_fps)
            or math.gcd(*self.source_fps) != 1
        ):
            raise VideoIngestionError(
                "Explicit source FPS must be a reduced positive rational pair"
            )


@dataclass(frozen=True)
class VideoFrames:
    manifest: ArtifactSnapshot
    frames: tuple[ArtifactSnapshot, ...]
    occurrences: tuple[dict[str, Any], ...]


def canonical_frame_png(frame: Any) -> bytes:
    """Exact gray-channel projection only; reject color, alpha and intermediate gray."""
    _, np = _opencv()
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8:
        raise VideoIngestionError("Decoded frame must contain uint8 samples")
    if frame.ndim == 3:
        if frame.shape[2] != 3 or not (
            np.array_equal(frame[:, :, 0], frame[:, :, 1])
            and np.array_equal(frame[:, :, 0], frame[:, :, 2])
        ):
            raise VideoIngestionError(
                "Controlled video requires equal BGR channels; no color/alpha"
            )
        frame = frame[:, :, 0]
    if frame.ndim != 2 or min(frame.shape) <= 0 or frame.size > MAX_PIXELS:
        raise VideoIngestionError("Invalid frame dimensions")
    if not np.all((frame == 0) | (frame == 255)):
        raise VideoIngestionError("Controlled video requires exact black/white samples")
    height, width = frame.shape
    return _encode_mask_png(np.ascontiguousarray(frame), width, height)


def canonical_reference_png(content: bytes) -> bytes:
    """Canonicalize a controlled PNG independently (e.g. an equivalence assertion)."""
    width, height, depth, color = _png_header(content)
    if depth != 8 or color != 0 or width * height > MAX_PIXELS:
        raise VideoIngestionError("Reference requires bounded opaque gray8 PNG")
    cv2, np = _opencv()
    frame = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_UNCHANGED)
    if frame is None or frame.shape != (height, width):
        raise VideoIngestionError("Reference PNG decode failed")
    return canonical_frame_png(frame)


def _chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    chunks = []
    offset = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise VideoIngestionError("Truncated AVI chunk header")
        size = struct.unpack_from("<I", data, offset + 4)[0]
        end = offset + 8 + size
        if end + size % 2 > len(data):
            raise VideoIngestionError("Truncated AVI chunk")
        chunks.append((data[offset : offset + 4], data[offset + 8 : end]))
        offset = end + size % 2
    return chunks


def _one(chunks: list[tuple[bytes, bytes]], tag: bytes) -> bytes:
    values = [data for kind, data in chunks if kind == tag]
    if len(values) != 1:
        raise VideoIngestionError(f"AVI requires exactly one {tag!r}")
    return values[0]


def _avi_metadata(content: bytes) -> dict[str, Any]:
    # Read bounded RIFF metadata, not compressed pixels. No general container parser.
    if (
        not 12 <= len(content) <= 32 * 1024 * 1024
        or content[:4] != b"RIFF"
        or content[8:12] != b"AVI "
        or struct.unpack_from("<I", content, 4)[0] + 8 != len(content)
    ):
        raise VideoIngestionError("Requires one complete bounded RIFF AVI container")
    chunks = _chunks(content[12:])
    lists = [(data[:4], data[4:]) for tag, data in chunks if tag == b"LIST"]
    if any(tag not in {b"hdrl", b"movi", b"INFO"} for tag, _ in lists):
        raise VideoIngestionError("Unsupported AVI list")
    header = _chunks(_one(lists, b"hdrl"))
    avih = _one(header, b"avih")
    streams = [data[4:] for tag, data in header if tag == b"LIST" and data[:4] == b"strl"]
    if len(avih) != 56 or len(streams) != 1 or struct.unpack_from("<I", avih, 24)[0] != 1:
        raise VideoIngestionError("AVI requires exactly one video stream; no audio")
    stream = _chunks(streams[0])
    strh, strf = _one(stream, b"strh"), _one(stream, b"strf")
    if len(strh) != 56 or len(strf) < 40 or strh[:8] != b"vidsFFV1" or strf[16:20] != b"FFV1":
        raise VideoIngestionError("Only AVI FFV1 video is supported")
    scale, rate, start, count = struct.unpack_from("<4I", strh, 20)
    width, height = struct.unpack_from("<2i", strf, 4)
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise VideoIngestionError("Invalid frame dimensions")
    if (
        not rate
        or not scale
        or start != 0
        or not 1 <= count <= MAX_FRAMES
        or width * height * count > 256_000_000
        or struct.unpack_from("<I", avih, 16)[0] != count
        or struct.unpack_from("<2I", avih, 32) != (width, height)
        or struct.unpack_from("<I", strh, 44)[0] != 0
    ):
        raise VideoIngestionError("Unsupported AVI timing, frame count or dimensions")
    packets = _chunks(_one(lists, b"movi"))
    if len(packets) != count or any(tag != b"00dc" or not data for tag, data in packets):
        raise VideoIngestionError(
            "Requires one nonempty video packet per CFR frame; no dropped frames"
        )
    fps = Fraction(rate, scale)
    return {
        "container": "AVI",
        "codec": "FFV1",
        "width": width,
        "height": height,
        "frame_count": count,
        "source_fps": [fps.numerator, fps.denominator],
    }


def _decode(content: bytes, metadata: dict[str, Any], indices: tuple[int, ...]) -> dict[int, bytes]:
    cv2, _ = _opencv()
    if version("opencv-python-headless") != WHEEL_VERSION or cv2.__version__ != "4.14.0":
        raise VideoIngestionError("Video policy requires the recorded OpenCV wheel/runtime version")
    outputs = {}
    # Closed file before opening is required on Windows. This path is never identity.
    with TemporaryDirectory(prefix="svm-video-") as directory:
        path = Path(directory) / "input.avi"
        path.write_bytes(content)
        capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
        try:
            if not capture.isOpened() or capture.getBackendName() != "FFMPEG":
                raise VideoIngestionError("Bundled OpenCV FFMPEG backend could not open AVI")
            for prop, expected in (
                (cv2.CAP_PROP_FRAME_COUNT, metadata["frame_count"]),
                (cv2.CAP_PROP_FRAME_WIDTH, metadata["width"]),
                (cv2.CAP_PROP_FRAME_HEIGHT, metadata["height"]),
            ):
                if capture.get(prop) != expected:
                    raise VideoIngestionError("Decoder disagrees with recorded AVI metadata")
            # FFmpeg reports its codec tag in lower case on the Windows wheel.
            if capture.get(cv2.CAP_PROP_FOURCC) not in {
                cv2.VideoWriter_fourcc(*"FFV1"),
                cv2.VideoWriter_fourcc(*"ffv1"),
            }:
                raise VideoIngestionError("Decoder did not select FFV1")
            fps = Fraction(*metadata["source_fps"])
            if not math.isclose(capture.get(cv2.CAP_PROP_FPS), float(fps), rel_tol=1e-12):
                raise VideoIngestionError("Decoder disagrees with exact source FPS")
            for index in range(metadata["frame_count"]):
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise VideoIngestionError(f"Failed frame decode at source index {index}")
                if frame.shape[:2] != (metadata["height"], metadata["width"]):
                    raise VideoIngestionError("Decoded frame dimensions changed")
                if capture.get(cv2.CAP_PROP_PTS) != index:
                    raise VideoIngestionError(
                        "Decoder timestamp is not the declared CFR occurrence"
                    )
                canonical = canonical_frame_png(frame)
                if index in indices:
                    outputs[index] = canonical
            if capture.read()[0]:
                raise VideoIngestionError("Unexpected extra decoded frame")
        finally:
            capture.release()
    return outputs


def _produce(
    source: ArtifactSnapshot, options: VideoSampling
) -> tuple[dict[str, Any], dict[int, bytes]]:
    options.validate()
    if source.media_type != "video/x-msvideo" or source.kind != ArtifactKind.REFERENCE:
        raise VideoIngestionError("Requires an immutable AVI ReferenceArtifact")
    metadata = _avi_metadata(source.content)
    if options.frame_indices[-1] >= metadata["frame_count"]:
        raise VideoIngestionError("Requested frame index is out of range")
    fps = Fraction(*metadata["source_fps"])
    if options.source_fps is not None and Fraction(*options.source_fps) != fps:
        raise VideoIngestionError("Explicit source FPS disagrees with exact AVI rate/scale")
    occurrences = []
    for index in options.frame_indices:
        timestamp = Fraction(index, 1) / fps
        tick = timestamp * options.ticks_per_second
        if tick.denominator != 1:
            raise VideoIngestionError("Source timestamp has no exact integer SVM tick")
        occurrences.append(
            {
                "frame_index": index,
                "source_timestamp": [timestamp.numerator, timestamp.denominator],
                "tick": tick.numerator,
            }
        )
    outputs = _decode(source.content, metadata, options.frame_indices)
    for occurrence in occurrences:
        png_id = "artifact:" + hashlib.sha256(outputs[occurrence["frame_index"]]).hexdigest()
        occurrence["raster_artifact_id"] = png_id
        identity = {
            "source_video_artifact_id": source.artifact_id,
            "policy_identity": POLICY,
            "raster_policy_identity": RASTER_POLICY,
            "ticks_per_second": options.ticks_per_second,
            **occurrence,
        }
        occurrence["occurrence_id"] = (
            "video-frame-occurrence:" + hashlib.sha256(canonical_bytes(identity)).hexdigest()
        )
    manifest = {
        "schema_version": "svm-video-frame-manifest-0.1",
        "policy_identity": POLICY,
        "raster_policy_identity": RASTER_POLICY,
        "source_video_reference": source.document_reference(),
        "source": metadata,
        "sampling": asdict(options),
        "decoder": {
            "backend": "FFMPEG",
            "opencv_version": "4.14.0",
            "wheel_version": WHEEL_VERSION,
        },
        "occurrences": occurrences,
    }
    return manifest, outputs


def ingest_video(
    artifacts: ArtifactRepository, source_reference: dict[str, Any], options: VideoSampling
) -> VideoFrames:
    """Verify source and decode completely before publishing any derived outputs."""
    source = artifacts.resolve_reference(source_reference)
    data, outputs = _produce(source, options)
    frames = tuple(
        artifacts.import_bytes(outputs[i], media_type="image/png") for i in options.frame_indices
    )
    manifest = artifacts.import_bytes(
        canonical_bytes(data),
        media_type=MANIFEST_MEDIA,
        kind=ArtifactKind.DERIVED,
        provenance={"policy_identity": POLICY, "source_video_artifact_id": source.artifact_id},
    )
    return VideoFrames(manifest, frames, tuple(data["occurrences"]))


def verify_video_manifest(artifacts: ArtifactRepository, reference: dict[str, Any]) -> VideoFrames:
    """Re-decode the recorded source; never trust a claimed timestamp or pixel lineage."""
    snapshot = artifacts.resolve_reference(reference)
    try:
        data = json.loads(snapshot.content)
        sampling = data["sampling"]
        options = VideoSampling(
            tuple(sampling["frame_indices"]),
            sampling["ticks_per_second"],
            tuple(sampling["source_fps"]) if sampling["source_fps"] is not None else None,
        )
        source = artifacts.resolve_reference(data["source_video_reference"])
        expected, outputs = _produce(source, options)
        if (
            snapshot.media_type != MANIFEST_MEDIA
            or snapshot.kind != ArtifactKind.DERIVED
            or snapshot.content != canonical_bytes(expected)
            or snapshot.provenance
            != {"policy_identity": POLICY, "source_video_artifact_id": source.artifact_id}
        ):
            raise VideoIngestionError("Video manifest/provenance does not reproduce")
        frames = artifacts.resolve_as(
            tuple(o["raster_artifact_id"] for o in expected["occurrences"]),
            kind=ArtifactKind.REFERENCE,
            media_types=frozenset({"image/png"}),
        )
        for index, frame in zip(options.frame_indices, frames, strict=True):
            if frame.content != outputs[index] or frame.provenance:
                raise VideoIngestionError("Canonical frame bytes/provenance do not reproduce")
        return VideoFrames(snapshot, frames, tuple(expected["occurrences"]))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise VideoIngestionError("Invalid video manifest") from exc
