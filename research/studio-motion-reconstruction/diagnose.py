"""Measure controlled identity and geometry failures of the frozen research baseline."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .fixture import FPS, HEIGHT, TICK_RATE, WIDTH, shape_pixels
from .run import CLASSIFICATION, MAX_SOURCE_BYTES, bounded_read, digest, json_bytes, observe

ORIGIN = (40, 55)
COLOR = (43, 181, 247)
BACKGROUND = (44, 38, 37)
SETTINGS = {
    "ticks_per_second": TICK_RATE,
    "max_translation_px_per_frame": 4,
    "subjects": [{"id": "target", "point_xy": [ORIGIN[0] + 3, ORIGIN[1] + 3]}],
}


def transformed_mask(angle: int, scale: float) -> np.ndarray:
    mask = shape_pixels("amber").astype(np.uint8)
    if angle == 90 and scale == 1:
        return np.rot90(mask).astype(bool)
    if angle == 0 and scale == 1:
        return mask.astype(bool)
    padded = np.pad(mask, 24)
    h, w = padded.shape
    transform = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    warped = cv2.warpAffine(padded, transform, (w, h), flags=cv2.INTER_NEAREST)
    rows, columns = np.nonzero(warped)
    if (
        not len(rows)
        or rows.min() == 0
        or columns.min() == 0
        or rows.max() == h - 1
        or columns.max() == w - 1
    ):
        raise ValueError("The controlled transform clipped the template")
    return warped[rows.min() : rows.max() + 1, columns.min() : columns.max() + 1].astype(bool)


def raster(mask: np.ndarray, left: int, top: int, occupied: bool) -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH, 3), BACKGROUND, dtype=np.uint8)
    if occupied:
        height, width = mask.shape
        frame[top : top + height, left : left + width][mask] = COLOR
    return frame


def identity_fixture() -> tuple[list[np.ndarray], list[dict[str, Any]]]:
    frames, truth = [], []
    mask = shape_pixels("amber")
    # The same synthetic pixels admit two interpretations on every decoy tick.
    # Oracle labels say the original left and a lookalike entered. Swapping that
    # label to the original would leave the AVI bytes and first click untouched.
    identities = ("target", "target", "target", None, "decoy", "decoy", "decoy", None, "target")
    for index, identity in enumerate(identities):
        x, y = ORIGIN[0] + index * 3, ORIGIN[1]
        frames.append(raster(mask, x, y, identity is not None))
        truth.append({"visible_identity": identity, "origin_xy": [x, y] if identity else None})
    return frames, truth


def geometry_fixture() -> tuple[list[np.ndarray], list[dict[str, Any]]]:
    frames, truth = [], []
    poses = ((0, 1), (0, 1), (10, 1), (90, 1), (0, 1.25), (0, 2), (0, 1), (0, 1))
    for index, (angle, scale) in enumerate(poses):
        x, y = ORIGIN[0] + index * 3, ORIGIN[1]
        mask = transformed_mask(angle, scale)
        frames.append(raster(mask, x, y, occupied=True))
        truth.append(
            {
                "visible_identity": "target",
                "origin_xy": [x, y],
                "geometry": "translation" if (angle, scale) == (0, 1) else "similarity",
                "angle_degrees": angle,
                "uniform_scale": scale,
                "mask_area_px": int(mask.sum()),
            }
        )
    return frames, truth


def evaluate(
    measured: dict[str, Any], pixels: list[np.ndarray], truth: list[dict[str, Any]]
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    detail = []
    for index, (frame, decoded, answer) in enumerate(
        zip(measured["frames"], pixels, truth, strict=True)
    ):
        observation = frame["subjects"]["target"]
        tick = index * (TICK_RATE // FPS)
        if (
            frame["source_index"] != index
            or frame["tick"] != tick
            or frame["bgr24_sha256"] != digest(decoded.tobytes())
        ):
            raise ValueError("The baseline did not observe the exact controlled pixel occurrence")
        observed = observation["status"] == "OBSERVED"
        identity = answer["visible_identity"]
        category = answer.get("geometry", "translation") if identity == "target" else identity
        category = category or "empty"
        outcome = "observed" if observed else "unknown"
        counts[f"{category}_{outcome}"] += 1
        if observed:
            x, y, _, _ = observation["bounds_xywh"]
            if [x, y] != answer["origin_xy"]:
                raise ValueError("Observed location differs from the controlled visible component")
        detail.append({"tick": tick, "oracle": answer, "candidate": observation})
    return {"counts": dict(counts), "occurrences": detail}


def execute_probe(
    name: str, output: Path, pixels: list[np.ndarray], truth: list[dict[str, Any]]
) -> dict[str, Any]:
    source = output / f"{name}.avi"
    writer = cv2.VideoWriter(
        str(source), cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"FFV1"), FPS, (WIDTH, HEIGHT)
    )
    try:
        if not writer.isOpened():
            raise ValueError("OpenCV FFmpeg could not encode the synthetic probe")
        for frame in pixels:
            writer.write(frame)
    finally:
        writer.release()
    data = bounded_read(source, MAX_SOURCE_BYTES)
    # The runtime receives video and clicks only. Oracle labels (including the
    # visually indistinguishable decoy) are used solely by evaluate afterward.
    result = observe(data, SETTINGS)
    encoded = json_bytes(result)
    if json_bytes(observe(data, SETTINGS)) != encoded:
        raise ValueError("Controlled probe failed byte replay")
    (output / f"{name}.candidate.json").write_bytes(encoded)
    return {**evaluate(result, pixels, truth), "candidate_sha256": digest(encoded)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New probe output directory")
    options = parser.parse_args()
    try:
        options.output.mkdir()
        cv2.setNumThreads(1)
        identity = execute_probe("identity", options.output, *identity_fixture())
        geometry = execute_probe("geometry", options.output, *geometry_fixture())
        expected_identity = {"translation_observed": 4, "empty_unknown": 2, "decoy_observed": 3}
        expected_geometry = {"translation_observed": 4, "similarity_unknown": 4}
        if identity["counts"] != expected_identity or geometry["counts"] != expected_geometry:
            raise ValueError("Diagnostic outcomes differ from the frozen baseline expectation")
        result = {
            "artifact_classification": CLASSIFICATION,
            "sample": "SYNTHETIC",
            "identity": identity,
            "geometry": geometry,
            "interpretation": {
                "identity": (
                    "Exact visibility masks cannot distinguish these appearances. "
                    "Make identity uncertain after loss of evidence, request another user "
                    "anchor or obtain an independently informative cue. A tracker comparison "
                    "needs a distinct appearance or context signal to be informative."
                ),
                "geometry": (
                    "All transformed subjects remain uniquely visible in exact color masks. "
                    "Compare a masked pose estimator before a segmentation model. Use known "
                    "rotation and scale, clean translation controls, and abstention tests."
                ),
            },
        }
        (options.output / "report.json").write_bytes(json_bytes(result))
        print(json_bytes({"identity": identity["counts"], "geometry": geometry["counts"]}).decode())
    except (ValueError, OSError, cv2.error) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
