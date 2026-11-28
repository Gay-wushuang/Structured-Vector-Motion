"""Generate a deterministic synthetic source and evaluate candidates independently."""

from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .run import bounded_read, digest, json_bytes

WIDTH = 320
HEIGHT = 180
FPS = 12
TICK_RATE = 24
FRAME_COUNT = 48
OBJECTS = {
    "amber": {"origin": (36, 63), "step": (3, 0), "bgr": (43, 181, 247)},
    "teal": {"origin": (252, 112), "step": (-2, 0), "bgr": (190, 174, 58)},
}
CLIP_MASK = (113, 60, 136, 101)


def shape_pixels(identifier: str) -> np.ndarray:
    if identifier == "amber":
        mask = np.zeros((31, 27), dtype=bool)
        mask[:8, :] = True
        mask[:, :9] = True
    else:
        mask = np.zeros((21, 33), dtype=bool)
        mask[:7, :] = True
        mask[:, 12:21] = True
    return mask


def position(identifier: str, index: int) -> tuple[int, int]:
    object_ = OBJECTS[identifier]
    x, y = object_["origin"]
    dx, dy = object_["step"]
    return x + dx * index, y + dy * index


def synthetic_frame(index: int) -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH, 3), (44, 38, 37), dtype=np.uint8)
    for identifier, settings in OBJECTS.items():
        x, y = position(identifier, index)
        mask = shape_pixels(identifier)
        height, width = mask.shape
        frame[y : y + height, x : x + width][mask] = settings["bgr"]
    x, y, right, bottom = CLIP_MASK
    frame[y:bottom, x:right] = (94, 84, 99)
    return frame


def make(output: Path) -> None:
    output.mkdir()
    source = output / "synthetic.avi"
    cv2.setNumThreads(1)
    writer = cv2.VideoWriter(
        str(source), cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"FFV1"), FPS, (WIDTH, HEIGHT)
    )
    try:
        if not writer.isOpened():
            raise ValueError("OpenCV FFmpeg could not encode the synthetic FFV1 fixture")
        for index in range(FRAME_COUNT):
            writer.write(synthetic_frame(index))
    finally:
        writer.release()
    seeds = {
        "ticks_per_second": TICK_RATE,
        "max_translation_px_per_frame": 4,
        "subjects": [
            {"id": identifier, "point_xy": [position(identifier, 0)[0] + 3, 65 if i == 0 else 115]}
            for i, identifier in enumerate(OBJECTS)
        ],
    }
    (output / "seeds.json").write_bytes(json_bytes(seeds))
    (output / "fixture.json").write_bytes(
        json_bytes(
            {
                "sample": "SYNTHETIC",
                "frames": FRAME_COUNT,
                "source_sha256": digest(source.read_bytes()),
                "ticks_per_second": TICK_RATE,
                "decoded_bgr24_sha256": [
                    digest(synthetic_frame(index).tobytes()) for index in range(FRAME_COUNT)
                ],
            }
        )
    )


def fully_visible(identifier: str, index: int) -> bool:
    x, y = position(identifier, index)
    mask = shape_pixels(identifier)
    rows, columns = np.nonzero(mask)
    left, top, right, bottom = CLIP_MASK
    covered = (
        (x + columns >= left) & (x + columns < right) & (y + rows >= top) & (y + rows < bottom)
    )
    return not np.any(covered)


def reconstructed_template(rectangles: list[list[int]], width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    for x, y, w, h in rectangles:
        if not 0 <= x < x + w <= width or not 0 <= y < y + h <= height:
            raise ValueError("Candidate rectangle outside first-frame bounds")
        mask[y : y + h, x : x + w] = True
    return mask


def metrics(candidate_bytes: bytes, fixture: dict[str, Any]) -> dict[str, Any]:
    candidate = json.loads(candidate_bytes)
    if candidate.get("source", {}).get("sha256") != fixture["source_sha256"]:
        raise ValueError("Candidate source does not match the synthetic fixture")
    if candidate["settings"]["ticks_per_second"] != TICK_RATE:
        raise ValueError("Unexpected candidate timebase")
    if len(candidate["frames"]) != FRAME_COUNT:
        raise ValueError("Unexpected candidate frame count")
    geometries = {geometry["id"]: geometry for geometry in candidate["geometry"]}
    if set(geometries) != set(OBJECTS):
        raise ValueError("Unexpected candidate subject IDs")

    counts: collections.Counter[str] = collections.Counter()
    unknown_by_id = {identifier: [] for identifier in OBJECTS}
    errors: list[float] = []
    static_errors: list[float] = []
    anchor_ious = {}
    for identifier, geometry in geometries.items():
        x, y, width, height = geometry["anchor_bounds_xywh"]
        expected = shape_pixels(identifier)
        if (x, y) != position(identifier, 0) or (height, width) != expected.shape:
            raise ValueError("Unexpected geometry on the synthetic anchor")
        actual = reconstructed_template(geometry["geometry_rectangles_xywh"], width, height)
        anchor_ious[identifier] = float(np.count_nonzero(expected & actual)) / np.count_nonzero(
            expected | actual
        )

    for index, frame in enumerate(candidate["frames"]):
        tick = index * (TICK_RATE // FPS)
        if (
            frame["source_index"] != index
            or frame["tick"] != tick
            or frame["bgr24_sha256"] != fixture["decoded_bgr24_sha256"][index]
        ):
            raise ValueError("Unexpected frame identity or decoded pixel content")
        for identifier in OBJECTS:
            observation = frame["subjects"][identifier]
            visible = fully_visible(identifier, index)
            counts["visible" if visible else "occluded"] += 1
            x, y = position(identifier, index)
            x0, y0 = position(identifier, 0)
            if visible:
                static_errors.append(math.hypot(x - x0, y - y0))
            if observation["status"] == "UNKNOWN":
                unknown_by_id[identifier].append(tick)
                counts["visible_unknown" if visible else "occluded_unknown"] += 1
                continue
            if observation["status"] != "OBSERVED":
                raise ValueError("Unexpected candidate status")
            counts["visible_observed" if visible else "occluded_observed"] += 1
            if visible:
                dx, dy = observation["translation_xy"]
                errors.append(math.hypot(dx - (x - x0), dy - (y - y0)))
    return {
        "sample": "SYNTHETIC",
        "candidate_sha256": digest(candidate_bytes),
        "tally": dict(counts),
        "unknown_ticks": unknown_by_id,
        "first_frame_geometry_mask_iou": anchor_ious,
        "visible_mean_translation_error_px": sum(errors) / len(errors) if errors else None,
        "visible_max_translation_error_px": max(errors, default=None),
        "visible_observation_coverage": counts["visible_observed"] / counts["visible"],
        "occlusion_false_observation_rate": counts["occluded_observed"] / counts["occluded"],
        "decoded_bgr24_frame_matches": FRAME_COUNT,
        "first_frame_hold_baseline": {
            "visible_mean_translation_error_px": sum(static_errors) / len(static_errors),
            "visible_max_translation_error_px": max(static_errors),
            "occlusion_false_observation_rate": 1.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("output", type=Path)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("fixture", type=Path)
    evaluate.add_argument("candidate", type=Path)
    evaluate.add_argument("output", type=Path)
    options = parser.parse_args()
    if options.action == "generate":
        make(options.output)
    else:
        expected = json.loads(bounded_read(options.fixture, 65536))
        data = bounded_read(options.candidate, 4 * 1024 * 1024)
        result = json_bytes(metrics(data, expected))
        with options.output.open("xb") as output:
            output.write(result)
        print(result.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
