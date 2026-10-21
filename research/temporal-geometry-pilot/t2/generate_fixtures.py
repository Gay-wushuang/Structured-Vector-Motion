"""Deterministic T2-P1 fixture generator (research-only, not SVM evidence).

The five fixtures and the frozen primary/witness anchor assignments come from
``T2-P0A-PROTOCOL-FREEZE.md``. The generator is the only producer of the
committed PNG/ground-truth bytes; ``--check`` regenerates every byte in memory
and fails if the committed fixtures differ.

No stochastic step is used: vertices, transforms, draw order and anchor rules
are fixed constants.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

CANVAS = (512, 512)
TICKS = (0, 12, 24, 36)
ORIGIN = (256.0, 256.0)
GROUND_TRUTH_NAME = "ground-truth.json"
FIXTURE_IDS = (
    "f1-translation",
    "f2-rotation-scale",
    "f3-low-texture",
    "f4-occlusion",
    "f5-conflicting-anchors",
)

BODY = [[180.0, 190.0], [320.0, 200.0], [350.0, 270.0], [250.0, 330.0], [170.0, 280.0]]
SAT_A = [[70.0, 140.0], [120.0, 135.0], [125.0, 185.0], [75.0, 190.0]]
SAT_B = [[390.0, 240.0], [440.0, 235.0], [445.0, 285.0], [395.0, 290.0]]
DECOY = [[400.0, 360.0], [450.0, 355.0], [455.0, 400.0], [405.0, 405.0]]

F3_BODY = [[190.0, 210.0], [310.0, 210.0], [310.0, 290.0], [190.0, 290.0]]
F3_SAT_A = [[100.0, 150.0], [145.0, 150.0], [145.0, 195.0], [100.0, 195.0]]
F3_SAT_B = [[365.0, 240.0], [410.0, 240.0], [410.0, 285.0], [365.0, 285.0]]

F4_OCCLUDER_RECT = [230, 175, 360, 345]


def _group_transform(fixture_id: str, frame_index: int) -> tuple[float, float, float, float]:
    """Cumulative group transform ``(tx, ty, rotation_degrees, scale)`` at k."""
    if fixture_id == "f2-rotation-scale":
        return (4.0 * frame_index, -2.0 * frame_index, 8.0 * frame_index, 1.04**frame_index)
    if fixture_id == "f5-conflicting-anchors":
        return (12.0 * frame_index, -6.0 * frame_index, 0.0, 1.0)
    return (12.0 * frame_index, -6.0 * frame_index, 0.0, 1.0)


def _decoy_transform(frame_index: int) -> tuple[float, float, float, float]:
    return (-10.0 * frame_index, 8.0 * frame_index, 0.0, 1.0)


def _transform(
    points: list[list[float]], transform: tuple[float, float, float, float]
) -> list[list[float]]:
    tx, ty, rotation_degrees, scale = transform
    radians = math.radians(rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    ox, oy = ORIGIN
    transformed: list[list[float]] = []
    for x, y in points:
        dx = x - ox
        dy = y - oy
        transformed.append(
            [
                ox + scale * (cosine * dx - sine * dy) + tx,
                oy + scale * (sine * dx + cosine * dy) + ty,
            ]
        )
    return transformed


def _affine(translation: tuple[float, float], rotation_degrees: float, scale: float) -> np.ndarray:
    radians = math.radians(rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    ox, oy = ORIGIN
    tx, ty = translation
    a = scale * cosine
    b = -scale * sine
    c = scale * sine
    d = scale * cosine
    return np.asarray(
        [[a, b, ox + tx - (a * ox + b * oy)], [c, d, oy + ty - (c * ox + d * oy)]],
        dtype=np.float64,
    )


def _apply_affine(points: list[list[float]], matrix: np.ndarray) -> np.ndarray:
    array = np.asarray(points, dtype=np.float64)
    homogeneous = np.column_stack((array, np.ones(len(array), dtype=np.float64)))
    return homogeneous @ matrix.T


def _matrix(transform: tuple[float, float, float, float]) -> np.ndarray:
    tx, ty, rotation_degrees, scale = transform
    return _affine((tx, ty), rotation_degrees, scale)


def _arc_length_points(polygon: list[list[float]], count: int = 16) -> list[list[float]]:
    perimeter = math.fsum(
        math.dist(polygon[index], polygon[(index + 1) % len(polygon)])
        for index in range(len(polygon))
    )
    points: list[list[float]] = []
    for sample_index in range(count):
        target = perimeter * sample_index / count
        accumulated = 0.0
        for index in range(len(polygon)):
            start = polygon[index]
            end = polygon[(index + 1) % len(polygon)]
            segment = math.dist(start, end)
            if target <= accumulated + segment:
                ratio = (target - accumulated) / segment
                points.append(
                    [
                        start[0] + (end[0] - start[0]) * ratio,
                        start[1] + (end[1] - start[1]) * ratio,
                    ]
                )
                break
            accumulated += segment
        else:  # pragma: no cover - only reachable through floating-point exhaustion
            raise AssertionError("arc-length sampling failed")
    return points


def _bottom_edge(points: list[list[float]], count: int = 16) -> list[list[float]]:
    left = min(point[0] for point in points)
    right = max(point[0] for point in points)
    y = max(point[1] for point in points)
    step = (right - left) / (count - 1)
    return [[left + step * index, y] for index in range(count)]


def _fixture_members(fixture_id: str) -> dict[str, list[list[float]]]:
    if fixture_id == "f3-low-texture":
        return {"member:body": F3_BODY, "member:sat-a": F3_SAT_A, "member:sat-b": F3_SAT_B}
    members = {"member:body": BODY, "member:sat-a": SAT_A, "member:sat-b": SAT_B}
    if fixture_id == "f5-conflicting-anchors":
        members["member:decoy"] = DECOY
    return members


def _member_transform(
    fixture_id: str, member_id: str, frame_index: int
) -> tuple[float, float, float, float]:
    if fixture_id == "f5-conflicting-anchors" and member_id == "member:decoy":
        return _decoy_transform(frame_index)
    return _group_transform(fixture_id, frame_index)


def _anchor_assignments(
    fixture_id: str, members: dict[str, list[list[float]]]
) -> tuple[str, list[str], dict[str, dict[str, Any]]]:
    if fixture_id == "f3-low-texture":
        primary = "anchor:body-bottom"
        witnesses = ["anchor:sat-a-bottom"]
        return (
            primary,
            witnesses,
            {
                primary: {
                    "anchor_id": primary,
                    "member_id": "member:body",
                    "frame_index": 0,
                    "points": _bottom_edge(members["member:body"]),
                },
                witnesses[0]: {
                    "anchor_id": witnesses[0],
                    "member_id": "member:sat-a",
                    "frame_index": 0,
                    "points": _bottom_edge(members["member:sat-a"]),
                },
            },
        )
    if fixture_id == "f5-conflicting-anchors":
        primary = "anchor:body"
        witnesses = ["anchor:decoy"]
        return (
            primary,
            witnesses,
            {
                primary: {
                    "anchor_id": primary,
                    "member_id": "member:body",
                    "frame_index": 0,
                    "points": _arc_length_points(members["member:body"]),
                },
                witnesses[0]: {
                    "anchor_id": witnesses[0],
                    "member_id": "member:decoy",
                    "frame_index": 0,
                    "points": _arc_length_points(members["member:decoy"]),
                },
            },
        )
    primary = "anchor:body"
    witnesses = ["anchor:sat-a"]
    return (
        primary,
        witnesses,
        {
            primary: {
                "anchor_id": primary,
                "member_id": "member:body",
                "frame_index": 0,
                "points": _arc_length_points(members["member:body"]),
            },
            witnesses[0]: {
                "anchor_id": witnesses[0],
                "member_id": "member:sat-a",
                "frame_index": 0,
                "points": _arc_length_points(members["member:sat-a"]),
            },
        },
    )


def _occluders(fixture_id: str) -> list[dict[str, Any]]:
    if fixture_id == "f4-occlusion":
        return [{"frame_index": 1, "rect": list(F4_OCCLUDER_RECT)}]
    return []


def _rasterize(
    members: dict[str, list[list[float]]],
    occluders: list[dict[str, Any]],
    frame_index: int,
) -> np.ndarray:
    frame = np.full(CANVAS[::-1], 255, dtype=np.uint8)
    for points in members.values():
        rounded = np.rint(np.asarray(points, dtype=np.float64)).astype(np.int32)
        cv2.fillPoly(frame, [rounded], 0, lineType=cv2.LINE_8)
    for occluder in occluders:
        if occluder["frame_index"] != frame_index:
            continue
        x0, y0, x1, y1 = (int(value) for value in occluder["rect"])
        frame[y0:y1, x0:x1] = 255
    return frame


def _encode_png(frame: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:  # pragma: no cover - OpenCV always supports PNG
        raise RuntimeError("cannot encode fixture PNG")
    return buffer.tobytes()


def _encode_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _eigen_statistics(points: list[list[float]]) -> tuple[float, float]:
    array = np.asarray(points, dtype=np.float64)
    covariance = np.cov(array.T, bias=True)
    eigenvalues = np.linalg.eigvalsh(covariance)
    lambda_2 = max(0.0, float(eigenvalues[0]))
    lambda_1 = max(lambda_2, float(eigenvalues[1]))
    spread = math.sqrt(lambda_2)
    planarity = lambda_2 / lambda_1 if lambda_1 > 0 else 0.0
    return spread, planarity


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_independence(
    primary: dict[str, Any], witness: dict[str, Any], primary_member: str, witness_member: str
) -> None:
    _assert(primary_member != witness_member, "witness must be on a different member")
    primary_points = {(float(x), float(y)) for x, y in primary["points"]}
    shared = [
        point for point in witness["points"] if (float(point[0]), float(point[1])) in primary_points
    ]
    _assert(not shared, "witness shares exact coordinates with the primary")
    far = 0
    for point in witness["points"]:
        nearest = min(math.dist(point, primary_point) for primary_point in primary["points"])
        if nearest >= 8.0:
            far += 1
    _assert(
        far / len(witness["points"]) >= 0.5,
        "at least 50% of witness points must be >= 8 px from every primary point",
    )


def _check_fixture(
    fixture_id: str,
    members_by_frame: list[dict[str, list[list[float]]]],
    anchors: dict[str, dict[str, Any]],
    primary_id: str,
    witness_ids: list[str],
    occluders: list[dict[str, Any]],
) -> None:
    for frame_index, members in enumerate(members_by_frame):
        for member_id, points in members.items():
            for point in points:
                _assert(
                    0.0 <= point[0] < CANVAS[0] and 0.0 <= point[1] < CANVAS[1],
                    f"{fixture_id} frame {frame_index} {member_id} point outside canvas",
                )
        masks = {}
        for member_id, points in members.items():
            mask = np.zeros(CANVAS[::-1], dtype=np.uint8)
            cv2.fillPoly(
                mask,
                [np.rint(np.asarray(points)).astype(np.int32)],
                255,
                lineType=cv2.LINE_8,
            )
            masks[member_id] = mask
        ids = list(masks)
        for left in range(len(ids)):
            for right in range(left + 1, len(ids)):
                overlap = int(np.count_nonzero(masks[ids[left]] & masks[ids[right]]))
                _assert(overlap == 0, f"{fixture_id} frame {frame_index} members overlap")

    primary = anchors[primary_id]
    _check_independence(
        primary,
        anchors[witness_ids[0]],
        primary["member_id"],
        anchors[witness_ids[0]]["member_id"],
    )
    for witness_id in witness_ids[1:]:
        _check_independence(
            primary, anchors[witness_id], primary["member_id"], anchors[witness_id]["member_id"]
        )

    if fixture_id == "f3-low-texture":
        for anchor in anchors.values():
            _assert(
                all(abs(point[1] - 290.0) < 1e-9 for point in anchor["points"])
                or all(abs(point[1] - 195.0) < 1e-9 for point in anchor["points"]),
                "F3 anchors must be collinear",
            )
            spread, planarity = _eigen_statistics(anchor["points"])
            _assert(spread < 4.0 or planarity < 0.02, "F3 anchor must be degenerate")
    else:
        for anchor in anchors.values():
            moved = _apply_affine(
                anchor["points"],
                _matrix(_member_transform(fixture_id, anchor["member_id"], 1)),
            ).tolist()
            spread, planarity = _eigen_statistics(moved)
            _assert(spread >= 4.0, "anchor spread would be degenerate")
            _assert(planarity >= 0.02, "anchor planarity would be degenerate")

    if fixture_id == "f4-occlusion":
        occluder = occluders[0]
        x0, y0, x1, y1 = occluder["rect"]
        moved_primary = _apply_affine(primary["points"], _matrix(_group_transform(fixture_id, 1)))
        covered = sum(1 for x, y in moved_primary.tolist() if x0 <= x < x1 and y0 <= y < y1)
        _assert(covered >= 8, f"F4 occluder must cover at least 8/16 primary points, got {covered}")

    if fixture_id == "f5-conflicting-anchors":
        primary_matrix = _matrix(_group_transform(fixture_id, 1))
        witness_matrix = _matrix(_decoy_transform(1))
        frame_zero_members = [point for points in members_by_frame[0].values() for point in points]
        difference = _apply_affine(frame_zero_members, primary_matrix) - _apply_affine(
            frame_zero_members, witness_matrix
        )
        rms = float(np.sqrt(np.mean(np.sum(difference * difference, axis=1))))
        _assert(rms > 2.0, f"F5 anchors must conflict, got RMS {rms}")
    elif fixture_id in {"f1-translation", "f2-rotation-scale"}:
        primary_matrix = _matrix(_group_transform(fixture_id, 1))
        witness_matrix = _matrix(_group_transform(fixture_id, 1))
        frame_zero_members = [point for points in members_by_frame[0].values() for point in points]
        difference = _apply_affine(frame_zero_members, primary_matrix) - _apply_affine(
            frame_zero_members, witness_matrix
        )
        _assert(
            float(np.max(np.abs(difference))) < 1e-9,
            "co-moving anchors must not conflict",
        )


def build_fixture(fixture_id: str) -> dict[str, bytes]:
    members = _fixture_members(fixture_id)
    members_by_frame: list[dict[str, list[list[float]]]] = []
    frame_records: list[dict[str, Any]] = []
    for frame_index, tick in enumerate(TICKS):
        frame_members: dict[str, list[list[float]]] = {}
        for member_id, points in members.items():
            transform = _member_transform(fixture_id, member_id, frame_index)
            frame_members[member_id] = _transform(points, transform)
        members_by_frame.append(frame_members)
        group_transform = _group_transform(fixture_id, frame_index)
        frame_records.append(
            {
                "index": frame_index,
                "tick": tick,
                "members": [
                    {"primitive_id": member_id, "points": frame_members[member_id]}
                    for member_id in members
                ],
                "group_transform": {
                    "translation": [group_transform[0], group_transform[1]],
                    "rotation_degrees": group_transform[2],
                    "scale": group_transform[3],
                },
            }
        )

    primary_id, witness_ids, anchors = _anchor_assignments(fixture_id, members)
    occluders = _occluders(fixture_id)
    _check_fixture(fixture_id, members_by_frame, anchors, primary_id, witness_ids, occluders)

    ground_truth = {
        "schema_version": "t2-fixture-ground-truth-0.1",
        "fixture_id": f"t2-{fixture_id}",
        "canvas": [CANVAS[0], CANVAS[1]],
        "primary_anchor_id": primary_id,
        "witness_anchor_ids": list(witness_ids),
        "frames": frame_records,
        "anchor_sets": [anchors[anchor_id] for anchor_id in [primary_id, *witness_ids]],
        "occluders": occluders,
    }

    files: dict[str, bytes] = {}
    for frame_index, tick in enumerate(TICKS):
        frame = _rasterize(members_by_frame[frame_index], occluders, frame_index)
        files[f"tick_{tick:03d}.png"] = _encode_png(frame)
    files[GROUND_TRUTH_NAME] = _encode_json(ground_truth)
    return files


def write_fixtures(root: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"fixtures_root": str(root), "fixtures": {}}
    for fixture_id in FIXTURE_IDS:
        fixture_root = root / fixture_id
        fixture_root.mkdir(parents=True, exist_ok=True)
        files = build_fixture(fixture_id)
        for relative_path, content in files.items():
            (fixture_root / relative_path).write_bytes(content)
        summary["fixtures"][fixture_id] = {
            "files": len(files),
            "bytes": sum(len(content) for content in files.values()),
        }
    return summary


def check_fixtures(root: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"fixtures_root": str(root), "fixtures": {}, "passed": True}
    for fixture_id in FIXTURE_IDS:
        expected = build_fixture(fixture_id)
        repeated = build_fixture(fixture_id)
        if expected != repeated:
            summary["passed"] = False
            summary["fixtures"][fixture_id] = {"deterministic_in_memory": False}
            continue
        mismatches = []
        for relative_path, content in expected.items():
            path = root / fixture_id / relative_path
            if not path.is_file() or path.read_bytes() != content:
                mismatches.append(relative_path)
        summary["fixtures"][fixture_id] = {
            "deterministic_in_memory": True,
            "mismatches": mismatches,
        }
        summary["passed"] = summary["passed"] and not mismatches
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or check T2-P1 fixtures")
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=Path(__file__).resolve().with_name("fixtures"),
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        summary = check_fixtures(args.fixtures_root)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["passed"] else 1
    summary = write_fixtures(args.fixtures_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
