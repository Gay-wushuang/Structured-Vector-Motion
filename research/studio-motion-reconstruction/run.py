"""Read-only, translation-only observations for a research AVI/FFV1 profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import cv2
import numpy as np

from svm.video_ingestion import _avi_metadata

PROFILE = "studio-flat-color-translation@0.1"
CLASSIFICATION = "experimental-only-not-svm-evidence"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 1280 * 720
MAX_FRAMES = 120
MAX_TARGET_PIXELS = 32_768
MAX_RECTANGLES = 128
MIN_TARGET_PIXELS = 16


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n").encode()


def bounded_read(path: Path, size: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(size + 1)
    if len(data) > size:
        raise ValueError(f"{path.name} exceeds the {size}-byte budget")
    return data


def read_settings(path: Path) -> dict[str, Any]:
    return validate_settings(json.loads(bounded_read(path, 16_384)))


def validate_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "ticks_per_second",
        "max_translation_px_per_frame",
        "subjects",
    }:
        raise ValueError("Expected tick rate, translation budget and first-frame subject clicks")
    rate, step, subjects = (
        value["ticks_per_second"],
        value["max_translation_px_per_frame"],
        value["subjects"],
    )
    if type(rate) is not int or not 1 <= rate <= 100000:
        raise ValueError("ticks_per_second must be an integer in [1, 100000]")
    if type(step) is not int or not 1 <= step <= 64:
        raise ValueError("max_translation_px_per_frame must be an integer in [1, 64]")
    if not isinstance(subjects, list) or not 1 <= len(subjects) <= 2:
        raise ValueError("One or two subject clicks are required")
    identifiers = set()
    for subject in subjects:
        if not isinstance(subject, dict) or set(subject) != {"id", "point_xy"}:
            raise ValueError("Each subject needs an id and point_xy")
        identifier, point = subject["id"], subject["point_xy"]
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", identifier)
            or identifier in identifiers
        ):
            raise ValueError("Subject IDs must be unique ASCII identifiers")
        if not isinstance(point, list) or len(point) != 2 or any(type(v) is not int for v in point):
            raise ValueError("Subject point_xy must contain two integers")
        identifiers.add(identifier)
    return value


def frames(source: bytes, meta: dict[str, Any]) -> Iterator[np.ndarray]:
    width, height, count = meta["width"], meta["height"], meta["frame_count"]
    if width * height > MAX_PIXELS or count > MAX_FRAMES:
        raise ValueError("Research profile allows up to 921600 pixels and 120 frames")
    with TemporaryDirectory(prefix="studio-research-") as directory:
        path = Path(directory) / "source.avi"
        path.write_bytes(source)
        capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
        try:
            if not capture.isOpened() or capture.getBackendName() != "FFMPEG":
                raise ValueError("The bundled FFmpeg backend could not open the AVI/FFV1 source")
            if capture.get(cv2.CAP_PROP_FOURCC) not in {
                cv2.VideoWriter_fourcc(*"FFV1"),
                cv2.VideoWriter_fourcc(*"ffv1"),
            }:
                raise ValueError("Decoder did not identify the stream as FFV1")
            for prop, expected in (
                (cv2.CAP_PROP_FRAME_COUNT, count),
                (cv2.CAP_PROP_FRAME_WIDTH, width),
                (cv2.CAP_PROP_FRAME_HEIGHT, height),
            ):
                if capture.get(prop) != expected:
                    raise ValueError("AVI metadata and decoded stream disagree")
            fps = Fraction(*meta["source_fps"])
            if abs(capture.get(cv2.CAP_PROP_FPS) - float(fps)) > 1e-9:
                raise ValueError("Decoder does not match the declared frame rate")
            for index in range(count):
                ok, frame = capture.read()
                if not ok or frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                    raise ValueError(f"Unexpected BGR24 frame at source index {index}")
                if capture.get(cv2.CAP_PROP_PTS) != index:
                    raise ValueError(f"Unexpected CFR presentation timestamp at {index}")
                yield frame
            if capture.read()[0]:
                raise ValueError("Decoder produced frames beyond the declared count")
        finally:
            capture.release()


def components(frame: np.ndarray, color: tuple[int, ...]):
    mask = cv2.inRange(frame, color, color)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return labels, stats


def rectangles(mask: np.ndarray) -> list[list[int]]:
    """Cover selected pixel cells exactly by integer rectangles in local coordinates."""
    output: list[list[int]] = []
    active: dict[tuple[int, int], list[int]] = {}
    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.pad(row, (1, 1))))
        next_active = {}
        for start, stop in zip(edges[::2], edges[1::2], strict=True):
            key = (int(start), int(stop - start))
            rect = active.get(key)
            if rect is None:
                if len(output) == MAX_RECTANGLES:
                    raise ValueError("Selected component exceeds the vector rectangle budget")
                rect = [key[0], y, key[1], 0]
                output.append(rect)
            rect[3] += 1
            next_active[key] = rect
        active = next_active
    return output


@dataclass
class Subject:
    identifier: str
    point: tuple[int, int]
    color: tuple[int, ...]
    origin: tuple[int, int]
    template: np.ndarray
    area: int
    last_origin: tuple[int, int]
    last_index: int = 0

    @classmethod
    def select(cls, seed: dict[str, Any], frame: np.ndarray) -> Subject:
        x, y = seed["point_xy"]
        if not 0 <= x < frame.shape[1] or not 0 <= y < frame.shape[0]:
            raise ValueError("A subject click is outside the first frame")
        color = tuple(map(int, frame[y, x]))
        labels, stats = components(frame, color)
        label = labels[y, x]
        left, top, width, height, area = map(int, stats[label])
        if not MIN_TARGET_PIXELS <= area <= MAX_TARGET_PIXELS or width * height > MAX_TARGET_PIXELS:
            raise ValueError("A clicked component is outside the geometry budget")
        if (
            left == 0
            or top == 0
            or left + width == frame.shape[1]
            or top + height == frame.shape[0]
        ):
            raise ValueError("A clicked component touches the frame boundary")
        window = labels[top : top + height, left : left + width]
        origin = (left, top)
        return cls(seed["id"], (x, y), color, origin, window == label, area, origin)

    def describe(self) -> dict[str, Any]:
        height, width = self.template.shape
        return {
            "id": self.identifier,
            "first_frame_click_xy": self.point,
            "bgr24": self.color,
            "anchor_bounds_xywh": [*self.origin, width, height],
            "anchor_mask_sha256": digest(self.template.astype(np.uint8).tobytes()),
            "geometry_rectangles_xywh": rectangles(self.template),
            "area_px": self.area,
        }

    def observation(self, frame: np.ndarray, index: int, step: int) -> dict[str, Any]:
        height, width = self.template.shape
        if index == 0:
            return self._supported(self.origin, width, height, "first_frame_click")
        labels, stats = components(frame, self.color)
        matches = []
        for label, row in enumerate(stats[1:], start=1):
            x, y, w, h, area = map(int, row)
            if (h, w, area) != (height, width, self.area):
                continue
            if np.array_equal(labels[y : y + h, x : x + w] == label, self.template):
                matches.append((x, y))
        if len(matches) != 1:
            return {
                "status": "UNKNOWN",
                "reason": "no_exact_shape" if not matches else "ambiguous_shape",
            }
        x, y = matches[0]
        if x == 0 or y == 0 or x + width == frame.shape[1] or y + height == frame.shape[0]:
            return {"status": "UNKNOWN", "reason": "frame_edge"}
        gap = index - self.last_index
        if max(abs(x - self.last_origin[0]), abs(y - self.last_origin[1])) > step * gap:
            return {"status": "UNKNOWN", "reason": "translation_budget"}
        self.last_index = index
        self.last_origin = (x, y)
        association = "exact_shape_after_gap" if gap > 1 else "exact_shape"
        return self._supported((x, y), width, height, association)

    def _supported(
        self, origin: tuple[int, int], width: int, height: int, association: str
    ) -> dict[str, Any]:
        return {
            "status": "OBSERVED",
            "bounds_xywh": [*origin, width, height],
            "translation_xy": [origin[0] - self.origin[0], origin[1] - self.origin[1]],
            "association": association,
        }


def unknown_intervals(records: list[dict[str, Any]], identifier: str) -> list[list[int]]:
    intervals: list[list[int]] = []
    active = False
    for record in records:
        is_unknown = record["subjects"][identifier]["status"] == "UNKNOWN"
        if is_unknown and not active:
            intervals.append([record["tick"], record["tick"]])
        elif is_unknown:
            intervals[-1][1] = record["tick"]
        active = is_unknown
    return intervals


def observe(source: bytes, settings: dict[str, Any]) -> dict[str, Any]:
    settings = validate_settings(settings)
    cv2.setNumThreads(1)
    meta = _avi_metadata(source)
    source_fps = Fraction(*meta["source_fps"])
    ticks_per_frame = settings["ticks_per_second"] / source_fps
    if ticks_per_frame.denominator != 1:
        raise ValueError("The source frame cadence must map to exact integer ticks")
    decoded = frames(source, meta)
    try:
        first = next(decoded)
        subjects = [Subject.select(seed, first) for seed in settings["subjects"]]
        if len({subject.color for subject in subjects}) != len(subjects):
            raise ValueError("Selected subjects must have distinct flat colors")
        descriptions = [subject.describe() for subject in subjects]

        def occurrence(index: int, frame: np.ndarray) -> dict[str, Any]:
            time = index / source_fps
            return {
                "source_index": index,
                "time_seconds": [time.numerator, time.denominator],
                "tick": index * int(ticks_per_frame),
                "bgr24_sha256": digest(frame.tobytes()),
                "subjects": {
                    subject.identifier: subject.observation(
                        frame, index, settings["max_translation_px_per_frame"]
                    )
                    for subject in subjects
                },
            }

        observations = [occurrence(0, first)]
        observations.extend(occurrence(index, frame) for index, frame in enumerate(decoded, 1))
    finally:
        decoded.close()
    return {
        "artifact_classification": CLASSIFICATION,
        "profile": PROFILE,
        "source": {**meta, "sha256": digest(source), "byte_length": len(source)},
        "runtime": {
            "opencv": cv2.__version__,
            "opencv_wheel": version("opencv-python-headless"),
            "opencv_build_sha256": digest(cv2.getBuildInformation().encode()),
            "numpy": np.__version__,
            "script_sha256": digest(Path(__file__).read_bytes()),
        },
        "settings": settings,
        "geometry": descriptions,
        "frames": observations,
        "unknown_tick_intervals_inclusive": {
            subject.identifier: unknown_intervals(observations, subject.identifier)
            for subject in subjects
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--seeds", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path, help="Compare candidate output byte for byte")
    arguments = parser.parse_args()
    try:
        settings = read_settings(arguments.seeds)
        source = bounded_read(arguments.input, MAX_SOURCE_BYTES)
        result = json_bytes(observe(source, settings))
        if arguments.verify:
            if result != bounded_read(arguments.verify, 4 * 1024 * 1024):
                raise ValueError("Replay differs from the recorded candidate")
            print(f"Matching candidate SHA-256 {digest(result)}")
        else:
            output = arguments.output
            with TemporaryDirectory(prefix=".candidate-", dir=output.parent) as staging:
                candidate = Path(staging) / "candidate.json"
                candidate.write_bytes(result)
                os.link(candidate, output)
            print(f"Candidate SHA-256 {digest(result)}")
    except (ValueError, OSError, cv2.error) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
