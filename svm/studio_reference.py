"""Source comparison for the controlled Phase 1 Studio sample."""

from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import ArtifactKind, ArtifactStore
from .evaluator import canonical_bytes
from .video_ingestion import MANIFEST_MEDIA, POLICY, verify_video_manifest

MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_SAMPLE_FRAMES = 16
FRAME_PREFIX = "/reference/"
_ARTIFACT_ID = re.compile(r"artifact:([0-9a-f]{64})")
DOCUMENT_ID = "document:explicit-multi-object-raster-recovery"
_RECOVERED_DOCUMENT_HASH = "5f3bca52b2a32b2c19621cabdc8a21b44422cec1138cd6675c341ab6046d2e5a"
_MANIFEST_HASH = "d8ba8bacf854da27449958def153972da5620211537e237f05f9f0d452dbf7e0"


def _read(bundle: Path, relative: str) -> bytes:
    path = (bundle / relative).resolve(strict=True)
    if not path.is_relative_to(bundle) or not path.is_file():
        raise ValueError("视频示例的文件必须位于示例目录内")
    with path.open("rb") as source:
        content = source.read(MAX_ARTIFACT_BYTES + 1)
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("视频示例文件超过 4 MiB 上限")
    return content


@dataclass(frozen=True)
class StudioReference:
    document: dict[str, Any]
    ticks_per_second: int
    width: int
    height: int
    ticks: tuple[int, ...]
    frame_paths: tuple[str, ...]
    frames: dict[str, bytes]

    @classmethod
    def load(cls, bundle: Path, expected_source: Path) -> StudioReference:
        try:
            bundle = bundle.resolve(strict=True)
            document = json.loads(_read(bundle, "documents/recovered.svm.json"))
            if hashlib.sha256(canonical_bytes(document)).hexdigest() != _RECOVERED_DOCUMENT_HASH:
                raise ValueError("恢复工程内容与受控视频示例登记的快照不符")
            manifest_bytes = _read(bundle, "source/video-manifest.json")
            if hashlib.sha256(manifest_bytes).hexdigest() != _MANIFEST_HASH:
                raise ValueError("原片清单与受控视频示例登记的时间映射不符")
            manifest = json.loads(manifest_bytes)
            source_bytes = _read(bundle, "source/scene.avi")
            if source_bytes != expected_source.read_bytes():
                raise ValueError("Studio 视频示例仅接收仓库中的 Phase 1 原片")

            artifacts = ArtifactStore()
            source = artifacts.import_bytes(source_bytes, media_type="video/x-msvideo")
            snapshot = artifacts.import_bytes(
                manifest_bytes,
                media_type=MANIFEST_MEDIA,
                kind=ArtifactKind.DERIVED,
                provenance={
                    "policy_identity": POLICY,
                    "source_video_artifact_id": source.artifact_id,
                },
            )
            occurrences = manifest["occurrences"]
            if not isinstance(occurrences, list) or not 1 <= len(occurrences) <= MAX_SAMPLE_FRAMES:
                raise ValueError("视频示例帧数超出允许范围")
            for occurrence in occurrences:
                match = _ARTIFACT_ID.fullmatch(occurrence["raster_artifact_id"])
                if match is None:
                    raise ValueError("视频示例含无效帧标识")
                relative = f"frames/{match[1]}.png"
                artifacts.import_bytes(_read(bundle, relative), media_type="image/png")
            verified = verify_video_manifest(artifacts, snapshot.document_reference())
            width, height = manifest["source"]["width"], manifest["source"]["height"]
            ticks_per_second = manifest["sampling"]["ticks_per_second"]
            frame_paths = tuple(
                f"{FRAME_PREFIX}{frame.content_hash.removeprefix('sha256:')}.png"
                for frame in verified.frames
            )
            reference = cls(
                document,
                ticks_per_second,
                width,
                height,
                tuple(item["tick"] for item in verified.occurrences),
                frame_paths,
                {
                    path: frame.content
                    for path, frame in zip(frame_paths, verified.frames, strict=True)
                },
            )
            if not reference.matches(document):
                raise ValueError("视频示例的原片和恢复工程时间基不一致")
            return reference
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as exc:
            raise ValueError(f"无法加载受控视频示例：{exc}") from exc

    @property
    def box(self) -> tuple[float, float, float, float]:
        return 0.0, 0.0, float(self.width), float(self.height)

    def matches(self, document: dict[str, Any]) -> bool:
        if document.get("document_id") != DOCUMENT_ID:
            return False
        try:
            candidate = deepcopy(document)
            animation = candidate["animation"]
            if animation["timebase"]["ticks_per_second"] != self.ticks_per_second:
                return False
            for track, baseline in zip(
                animation["content"], self.document["animation"]["content"], strict=True
            ):
                for frame, original in zip(track["keyframes"], baseline["keyframes"], strict=True):
                    if type(frame["value"]) not in {int, float}:
                        return False
                    frame["value"] = original["value"]
            return candidate == self.document
        except (KeyError, TypeError, ValueError):
            return False

    def at(self, tick: int) -> dict[str, Any]:
        index = max(0, bisect_right(self.ticks, tick) - 1)
        return {
            "tick": self.ticks[index],
            "width": self.width,
            "height": self.height,
            "url": self.frame_paths[index],
            "firstTick": self.ticks[0],
            "lastTick": self.ticks[-1],
            "lastFrameTick": self.ticks[-1],
            "ticks": self.ticks,
        }
