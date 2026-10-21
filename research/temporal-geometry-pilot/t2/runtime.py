"""T2-P1 runtime: isolated, GT-free Method B and Method C workers.

This module is the only entry point used by the runtime worker process. It
reads frames plus the frozen experiment config; it never reads, imports, or
mentions ``ground-truth.json``. Ground-truth evaluation lives in
``gt_eval.py`` and runs only after raw output has been written and hashed.

All outputs are explicitly classified ``experimental-only-not-svm-evidence``.
No Entity, Group, Track, Keyframe, Binding, TemporalIdentity, Document,
Revision, or ChangeAuthority object is created or claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "t2-group-anchor-experiment-config-0.1"
OUTPUT_SCHEMA = "t2-group-anchor-experiment-output-0.1"
CLASSIFICATION = "experimental-only-not-svm-evidence"
METHOD_B = "B-per-member-opencv-lk-propagation"
METHOD_C = "C-author-anchored-group-similarity"
RUNNER_IDENTITY = "svm-research/t2-group-anchor@0.1"
IDENTITY_CLAIM = "none"
CANVAS = (512, 512)
TICKS = (0, 12, 24, 36)
DRIFT_REFERENCE_FRAME_INDEX = 0
TICKS_PER_SECOND = 12

FORBIDDEN_KEYS = {
    "entity_id",
    "entity_ids",
    "group_id",
    "group_ids",
    "track_id",
    "track_ids",
    "keyframe_id",
    "keyframe_ids",
    "binding_id",
    "binding_ids",
    "motion_target_binding_id",
    "temporal_identity_id",
    "temporal_identity_ids",
    "observation_id",
    "observation_ids",
    "change_id",
    "change_ids",
    "authority",
}

FROZEN_LIMITS: dict[str, Any] = {
    "min_valid_anchor_points": 8,
    "min_valid_anchor_ratio": 0.75,
    "max_median_lk_error_px": 8.0,
    "max_median_affine_residual_px": 2.0,
    "min_anchor_spread_px": 4.0,
    "min_anchor_planarity": 0.02,
    "conflict_rms_px": 2.0,
    "conflict_rotation_deg": 2.0,
    "conflict_scale_ratio": 0.02,
    "min_scale": 0.5,
    "max_scale": 2.0,
    "max_step_rotation_deg": 15.0,
    "max_step_translation_px": 64.0,
}

FROZEN_LK: dict[str, Any] = {
    "lk_window": [31, 31],
    "lk_pyramid_max_level": 3,
    "lk_max_iterations": 30,
    "lk_epsilon": 0.01,
    "lk_min_eigen_threshold": 0.0001,
    "affine_estimator": "LMEDS",
    "affine_refine_iterations": 10,
}

FROZEN_B_BUDGET: dict[str, Any] = {
    "boundary_sample_spacing_px": 8.0,
    "min_valid_member_tracks": 10,
    "min_valid_member_ratio": 0.75,
    "max_median_lk_error_px": 8.0,
    "max_member_median_residual_px": 2.0,
    **FROZEN_LK,
}

FROZEN_C_BUDGET: dict[str, Any] = dict(FROZEN_LK)

FROZEN_DECISION_THRESHOLDS: dict[str, Any] = {
    "protocol": "t2-p0a",
    "relative_miss_definition": (
        "max over failed numeric quality gates of (required-observed)/|required| for "
        "lower bounds and (observed-required)/|required| for upper bounds; a missing "
        "observation counts as 1.0; a failed binary gate counts as 1.0"
    ),
    "quality": {
        "f1-translation": {
            "b_abstention_required": 0,
            "c_abstention_required": 0,
            "c_group_iou_min": 0.990,
            "c_mean_member_iou_min": 0.985,
            "c_mean_vertex_rmse_px_max": 0.75,
            "c_mean_vertex_rmse_relative_to_b_max": 0.75,
            "c_mean_vertex_rmse_relative_band_b_min_px": 0.50,
            "c_final_group_drift_px_max": 0.30,
            "c_final_group_drift_relative_to_b_max": 0.50,
            "c_final_group_drift_relative_band_b_min_px": 0.10,
            "c_group_step_jitter_relative_to_b_max": 0.50,
            "c_group_step_jitter_relative_band_b_min": 0.05,
            "c_group_step_jitter_absolute_max_when_b_below": 0.05,
            "c_rigidity_error_px_max": 0.10,
        },
        "f2-rotation-scale": {
            "b_abstention_required": 0,
            "c_abstention_required": 0,
            "c_group_iou_min": 0.975,
            "c_mean_member_iou_min": 0.970,
            "c_mean_vertex_rmse_px_max": 1.50,
            "c_mean_vertex_rmse_relative_to_b_max": 0.75,
            "c_mean_vertex_rmse_relative_band_b_min_px": 0.50,
            "c_final_group_drift_px_max": 0.75,
            "c_final_group_drift_relative_to_b_max": 0.50,
            "c_final_group_drift_relative_band_b_min_px": 0.10,
            "c_group_step_jitter_relative_to_b_max": 0.60,
            "c_group_step_jitter_relative_band_b_min": 0.05,
            "c_group_step_jitter_absolute_max_when_b_below": 0.05,
            "c_rigidity_error_px_max": 0.20,
        },
    },
    "stop_band_relative_miss": {"f1-translation": 0.10, "f2-rotation-scale": 0.25},
    "fail_closed": {
        "f3-low-texture": {
            "supported_group_iou_pass_min": 0.95,
            "supported_group_iou_conditional_min": 0.90,
        },
        "f4-occlusion": {
            "occluded_frame_index": 1,
            "accepted_reasons": ["PRIMARY_ANCHOR_LOST", "INSUFFICIENT_VALID_ANCHOR_TRACKS"],
        },
        "f5-conflicting-anchors": {
            "conflict_frame_index": 1,
            "required_reason": "ANCHOR_CONFLICT",
        },
    },
    "cost": {"c_over_b_go_max": 1.0, "c_over_b_conditional_max": 1.5},
    "environment": {
        "opencv_version": "4.14.0",
        "opencv_wheel": "opencv-python-headless==4.14.0.94",
    },
}

REQUIRED_CONFIG_FIELDS = {
    "schema_version",
    "experiment_id",
    "artifact_classification",
    "identity_claim",
    "fixture_root",
    "frames",
    "timebase",
    "evaluation_window",
    "group",
    "method_b_budget",
    "method_c_budget",
    "decision_thresholds",
}

REQUIRED_GROUP_FIELDS = {
    "group_label",
    "members",
    "anchors",
    "primary_anchor_id",
    "witness_anchor_ids",
    "transform_model",
    "anchor_policy",
    "limits",
    "reanchor",
}

REQUIRED_MEMBER_FIELDS = {"primitive_id", "frame_zero_points"}
REQUIRED_ANCHOR_FIELDS = {"anchor_id", "member_id", "frame_index", "points"}

C_GROUP_REASONS = {
    1: "PRIMARY_ANCHOR_LOST",
    2: "WITNESS_ANCHOR_LOST",
    3: "ANCHOR_DEGENERATE",
    4: "LK_QUALITY_TOO_LOW",
    5: "ANCHOR_RESIDUAL_TOO_HIGH",
    6: "ANCHOR_FIT_FAILED",
    7: "ANCHOR_CONFLICT",
    8: "TRANSFORM_OUT_OF_BOUNDS",
}


class T2Error(RuntimeError):
    """A fail-closed T2 configuration, input, or runtime error."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _opencv() -> tuple[Any, Any]:
    try:
        import cv2  # pyright: ignore[reportMissingImports]
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise T2Error(
            'T2 requires the repository analysis extra: python -m pip install -e ".[analysis]"'
        ) from exc
    return cv2, np


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise T2Error(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise T2Error(f"{name} must be a finite number")
    return result


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise T2Error(f"{name} must be an object")
    return value


def _require_keys(value: dict[str, Any], required: set[str], name: str) -> None:
    if set(value) != required:
        missing = sorted(required - set(value))
        extra = sorted(set(value) - required)
        raise T2Error(
            f"{name} fields do not match the closed profile; missing={missing} extra={extra}"
        )


def _reject_forbidden_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                raise T2Error(f"forbidden authority field at {path}.{key}")
            _reject_forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, f"{path}[{index}]")


def _validate_label(value: Any, pattern_name: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise T2Error(f"{name} must be a non-empty string")
    prefix, _, suffix = value.partition(":")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if (
        prefix != pattern_name
        or not suffix
        or any(character not in allowed for character in suffix)
    ):
        raise T2Error(f"{name} must match {pattern_name}:[a-z0-9-]+")
    return value


def _validate_points(
    value: Any, name: str, minimum: int, canvas: tuple[int, int] = CANVAS
) -> list[list[float]]:
    if not isinstance(value, list) or len(value) < minimum:
        raise T2Error(f"{name} must be a list of at least {minimum} points")
    points: list[list[float]] = []
    seen: set[tuple[float, float]] = set()
    for index, point in enumerate(value):
        if not isinstance(point, list) or len(point) != 2:
            raise T2Error(f"{name}[{index}] must be [x, y]")
        x = _finite_number(point[0], f"{name}[{index}].x")
        y = _finite_number(point[1], f"{name}[{index}].y")
        if not (0.0 <= x < canvas[0] and 0.0 <= y < canvas[1]):
            raise T2Error(f"{name}[{index}] is outside the frozen canvas")
        if (x, y) in seen:
            raise T2Error(f"{name}[{index}] duplicates an earlier point")
        seen.add((x, y))
        points.append([x, y])
    return points


def _transform_matrix(value: Any, name: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != 2:
        raise T2Error(f"{name} must be a 2x3 matrix")
    matrix: list[list[float]] = []
    for row_index, row in enumerate(value):
        if not isinstance(row, list) or len(row) != 3:
            raise T2Error(f"{name}[{row_index}] must contain three numbers")
        matrix.append([_finite_number(item, f"{name}[{row_index}]") for item in row])
    return matrix


def _validate_independence(
    primary: dict[str, Any],
    witness: dict[str, Any],
    primary_member_id: str,
    name: str,
) -> None:
    if witness["member_id"] == primary_member_id:
        raise T2Error(f"{name} must be on a different member than the primary anchor")
    primary_points = {(float(x), float(y)) for x, y in primary["points"]}
    if any((float(x), float(y)) in primary_points for x, y in witness["points"]):
        raise T2Error(f"{name} shares exact coordinates with the primary anchor")
    far = 0
    for x, y in witness["points"]:
        if min(math.dist((x, y), point) for point in primary["points"]) >= 8.0:
            far += 1
    if far / len(witness["points"]) < 0.5:
        raise T2Error(f"{name} must keep at least 50% of points >= 8 px from every primary point")


def load_config(config_path: Path, repo_root: Path) -> dict[str, Any]:
    """Load and validate the closed, GT-free T2 runtime config."""
    config_path = config_path.resolve()
    repo_root = repo_root.resolve()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise T2Error(f"cannot read config {config_path}: {exc}") from exc
    config = _require_mapping(config, "config")
    _reject_forbidden_keys(config)
    _require_keys(config, REQUIRED_CONFIG_FIELDS, "config")
    if config["schema_version"] != SCHEMA_VERSION:
        raise T2Error("unsupported T2 config schema")
    if config["artifact_classification"] != CLASSIFICATION:
        raise T2Error("T2 artifacts must be classified as non-SVM evidence")
    if config["identity_claim"] != IDENTITY_CLAIM:
        raise T2Error("identity_claim must be exactly 'none'")
    if not isinstance(config["experiment_id"], str) or not config["experiment_id"]:
        raise T2Error("experiment_id must be a non-empty string")

    fixture_root_value = config["fixture_root"]
    if not isinstance(fixture_root_value, str) or not fixture_root_value:
        raise T2Error("fixture_root must be a non-empty string")
    fixture_root = (repo_root / fixture_root_value).resolve()
    if repo_root not in fixture_root.parents:
        raise T2Error("fixture_root must remain inside the repository root")
    if not fixture_root.is_dir():
        raise T2Error(f"fixture_root does not exist: {fixture_root}")

    frames = config["frames"]
    if not isinstance(frames, list) or len(frames) != len(TICKS):
        raise T2Error("T2 requires exactly four frames")
    seen_indices: list[int] = []
    for entry in frames:
        _require_mapping(entry, "frame")
        _require_keys(entry, {"index", "tick", "path"}, "frame")
        index = entry["index"]
        if isinstance(index, bool) or not isinstance(index, int):
            raise T2Error("frame index must be an integer")
        tick = entry["tick"]
        if isinstance(tick, bool) or not isinstance(tick, int):
            raise T2Error("frame tick must be an integer")
        if index != len(seen_indices):
            raise T2Error("frame indices must be contiguous and ordered from zero")
        if tick != TICKS[index]:
            raise T2Error("frame ticks must be exactly 0, 12, 24, 36")
        path_value = entry["path"]
        expected_name = f"tick_{tick:03d}.png"
        if path_value != expected_name:
            raise T2Error(f"frame path must be {expected_name}")
        frame_path = fixture_root / path_value
        if not frame_path.is_file():
            raise T2Error(f"frame does not exist: {frame_path}")
        seen_indices.append(index)

    _require_mapping(config["timebase"], "timebase")
    _require_keys(config["timebase"], {"ticks_per_second"}, "timebase")
    if config["timebase"]["ticks_per_second"] != TICKS_PER_SECOND:
        raise T2Error("timebase must be 12 ticks per second")

    window = _require_mapping(config["evaluation_window"], "evaluation_window")
    _require_keys(
        window,
        {"first_frame_index", "last_frame_index", "drift_reference_frame_index"},
        "evaluation_window",
    )
    if (
        window["first_frame_index"] != 0
        or window["last_frame_index"] != len(TICKS) - 1
        or window["drift_reference_frame_index"] != DRIFT_REFERENCE_FRAME_INDEX
    ):
        raise T2Error("evaluation window must cover frames 0-3 with drift reference 0")

    group = _require_mapping(config["group"], "group")
    _require_keys(group, REQUIRED_GROUP_FIELDS, "group")
    group_label = _validate_label(group["group_label"], "experimental-group", "group_label")
    if group_label.startswith("group:"):
        raise T2Error("group_label must not look like an SVM Group ID")
    if group["transform_model"] != "similarity":
        raise T2Error("transform_model must be 'similarity'")
    if group["anchor_policy"] != "strict":
        raise T2Error("anchor_policy must be 'strict'")
    if group["reanchor"] is not None:
        raise T2Error("reanchor must be null; T2-P1 has no recovery")

    members = group["members"]
    if not isinstance(members, list) or len(members) < 2:
        raise T2Error("group.members must contain at least two members")
    member_ids: list[str] = []
    for member in members:
        _require_mapping(member, "member")
        _require_keys(member, REQUIRED_MEMBER_FIELDS, "member")
        member_id = _validate_label(member["primitive_id"], "member", "member.primitive_id")
        if member_id in member_ids:
            raise T2Error("group.members must have distinct primitive_id values")
        _validate_points(member["frame_zero_points"], f"{member_id}.frame_zero_points", 3)
        member_ids.append(member_id)

    anchors = group["anchors"]
    if not isinstance(anchors, list) or len(anchors) < 2:
        raise T2Error("group.anchors must contain one primary and at least one witness")
    anchor_by_id: dict[str, dict[str, Any]] = {}
    for anchor in anchors:
        _require_mapping(anchor, "anchor")
        _require_keys(anchor, REQUIRED_ANCHOR_FIELDS, "anchor")
        anchor_id = _validate_label(anchor["anchor_id"], "anchor", "anchor.anchor_id")
        if anchor_id in anchor_by_id:
            raise T2Error("group.anchors must have distinct anchor_id values")
        if anchor["member_id"] not in member_ids:
            raise T2Error(f"{anchor_id} references an undeclared member")
        if anchor["frame_index"] != 0:
            raise T2Error("anchors must be declared at frame 0")
        points = _validate_points(anchor["points"], f"{anchor_id}.points", 8)
        anchor_by_id[anchor_id] = {
            "anchor_id": anchor_id,
            "member_id": anchor["member_id"],
            "frame_index": 0,
            "points": points,
        }

    primary_anchor_id = group["primary_anchor_id"]
    if primary_anchor_id not in anchor_by_id:
        raise T2Error("primary_anchor_id must reference a declared anchor")
    witness_ids = group["witness_anchor_ids"]
    if not isinstance(witness_ids, list) or not witness_ids:
        raise T2Error("witness_anchor_ids must contain at least one anchor")
    if len(set(witness_ids)) != len(witness_ids):
        raise T2Error("witness_anchor_ids must be distinct")
    if primary_anchor_id in witness_ids:
        raise T2Error("the primary anchor cannot also be a witness")
    if set(witness_ids) | {primary_anchor_id} != set(anchor_by_id):
        raise T2Error("every declared anchor must be the primary or a witness")
    primary = anchor_by_id[primary_anchor_id]
    for witness_id in witness_ids:
        _validate_independence(primary, anchor_by_id[witness_id], primary["member_id"], witness_id)

    limits = _require_mapping(group["limits"], "group.limits")
    if limits != FROZEN_LIMITS:
        raise T2Error("group.limits must exactly match the frozen T2-P0A runtime limits")

    if config["method_b_budget"] != FROZEN_B_BUDGET:
        raise T2Error("method_b_budget must exactly match the frozen T2-P0A budget")
    if config["method_c_budget"] != FROZEN_C_BUDGET:
        raise T2Error("method_c_budget must exactly match the frozen T2-P0A budget")
    if config["decision_thresholds"] != FROZEN_DECISION_THRESHOLDS:
        raise T2Error("decision_thresholds must exactly match the frozen T2-P0A gates")

    return {
        "config": config,
        "config_path": config_path,
        "repo_root": repo_root,
        "fixture_root": fixture_root,
        "members": [
            {
                "primitive_id": member["primitive_id"],
                "frame_zero_points": [[float(x), float(y)] for x, y in member["frame_zero_points"]],
            }
            for member in members
        ],
        "anchors": [anchor_by_id[primary_anchor_id]]
        + [anchor_by_id[witness_id] for witness_id in witness_ids],
        "primary_anchor_id": primary_anchor_id,
        "witness_anchor_ids": list(witness_ids),
    }


def load_runtime_frames(loaded: dict[str, Any]) -> list[Any]:
    """Decode only the frozen frames; this function has no ground-truth input."""
    cv2, np = _opencv()
    config = loaded["config"]
    fixture_root = loaded["fixture_root"]
    frames: list[Any] = []
    for entry in config["frames"]:
        path = fixture_root / entry["path"]
        frame = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if frame is None:
            raise T2Error(f"cannot decode input frame: {path}")
        if (int(frame.shape[1]), int(frame.shape[0])) != CANVAS:
            raise T2Error(f"input canvas mismatch: {path}")
        unique = {int(value) for value in np.unique(frame)}
        if unique != {0, 255}:
            raise T2Error(f"input is not the controlled flat/solid profile: {path}")
        frames.append(frame)
    return frames


def _sample_polygon_boundary(points: list[list[float]], spacing: float) -> Any:
    _, np = _opencv()
    polygon = np.asarray(points, dtype=np.float32)
    samples: list[Any] = []
    for start, end in zip(polygon, np.roll(polygon, -1, axis=0), strict=True):
        count = max(1, int(math.ceil(float(np.linalg.norm(end - start)) / spacing)))
        for index in range(count):
            samples.append(start + (end - start) * (index / count))
    return np.asarray(samples, dtype=np.float32)


def _track(
    previous_frame: Any, next_frame: Any, points: Any, budget: dict[str, Any]
) -> tuple[Any | None, Any | None, Any | None]:
    cv2, _ = _opencv()
    next_points, status, error = cv2.calcOpticalFlowPyrLK(
        previous_frame,
        next_frame,
        points.reshape(-1, 1, 2),
        None,
        winSize=tuple(int(value) for value in budget["lk_window"]),
        maxLevel=int(budget["lk_pyramid_max_level"]),
        criteria=(
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            int(budget["lk_max_iterations"]),
            float(budget["lk_epsilon"]),
        ),
        flags=0,
        minEigThreshold=float(budget["lk_min_eigen_threshold"]),
    )
    if next_points is None or status is None or error is None:
        return None, None, None
    return next_points.reshape(-1, 2), status.reshape(-1) == 1, error.reshape(-1)


def _fit_similarity(source: Any, target: Any, budget: dict[str, Any]) -> Any | None:
    cv2, _ = _opencv()
    matrix, _ = cv2.estimateAffinePartial2D(
        source,
        target,
        method=cv2.LMEDS,
        refineIters=int(budget["affine_refine_iterations"]),
    )
    return matrix


def _decompose(matrix: list[list[float]]) -> dict[str, Any]:
    a, _, tx = (float(value) for value in matrix[0])
    c, _, ty = (float(value) for value in matrix[1])
    scale = math.sqrt(a * a + c * c)
    rotation_degrees = math.degrees(math.atan2(c, a))
    return {
        "translation": [tx, ty],
        "rotation_degrees": rotation_degrees,
        "scale": scale,
        "determinant": a * float(matrix[1][1]) - float(matrix[0][1]) * c,
    }


def _matrix_list(matrix: Any) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix]


def _apply(matrix: list[list[float]], points: Any) -> Any:
    _, np = _opencv()
    array = np.asarray(points, dtype=np.float64)
    homogeneous = np.column_stack((array, np.ones(len(array), dtype=np.float64)))
    return homogeneous @ np.asarray(matrix, dtype=np.float64).T


def _compose(step: list[list[float]], cumulative: list[list[float]]) -> list[list[float]]:
    """Return ``step o cumulative`` in the ``q = A p + t`` convention."""
    _, np = _opencv()
    step_array = np.asarray(step, dtype=np.float64)
    cumulative_array = np.asarray(cumulative, dtype=np.float64)
    a = step_array[:, :2] @ cumulative_array[:, :2]
    t = step_array[:, :2] @ cumulative_array[:, 2] + step_array[:, 2]
    return [
        [float(a[0, 0]), float(a[0, 1]), float(t[0])],
        [float(a[1, 0]), float(a[1, 1]), float(t[1])],
    ]


def _eigen_statistics(points: Any) -> tuple[float, float]:
    _, np = _opencv()
    array = np.asarray(points, dtype=np.float64)
    covariance = np.cov(array.T, bias=True)
    eigenvalues = np.linalg.eigvalsh(covariance)
    lambda_2 = max(0.0, float(eigenvalues[0]))
    lambda_1 = max(lambda_2, float(eigenvalues[1]))
    spread = math.sqrt(lambda_2)
    planarity = lambda_2 / lambda_1 if lambda_1 > 0 else 0.0
    return spread, planarity


def _bounds_reason(matrix: list[list[float]], limits: dict[str, Any]) -> str | None:
    decomposition = _decompose(matrix)
    translation = decomposition["translation"]
    if not (float(limits["min_scale"]) <= decomposition["scale"] <= float(limits["max_scale"])):
        return "TRANSFORM_OUT_OF_BOUNDS"
    if abs(decomposition["rotation_degrees"]) > float(limits["max_step_rotation_deg"]):
        return "TRANSFORM_OUT_OF_BOUNDS"
    if math.hypot(translation[0], translation[1]) > float(limits["max_step_translation_px"]):
        return "TRANSFORM_OUT_OF_BOUNDS"
    return None


def _identity_matrix() -> list[list[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


def _c_frame_zero(config: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    members = loaded["members"]
    anchor_sets: list[dict[str, Any]] = []
    for anchor in loaded["anchors"]:
        spread, planarity = _eigen_statistics(anchor["points"])
        anchor_sets.append(
            {
                "anchor_id": anchor["anchor_id"],
                "role": "primary"
                if anchor["anchor_id"] == loaded["primary_anchor_id"]
                else "witness",
                "member_id": anchor["member_id"],
                "valid_count": len(anchor["points"]),
                "valid_ratio": 1.0,
                "median_lk_error": None,
                "median_affine_residual_px": None,
                "spread_px": spread,
                "planarity": planarity,
                "step_affine": None,
                "decomposed": None,
                "status": "VALID",
                "reason": None,
            }
        )
    return {
        "frame_index": config["frames"][0]["index"],
        "tick": config["frames"][0]["tick"],
        "status": "SUPPORTED",
        "members": [
            {
                "primitive_id": member["primitive_id"],
                "points": [[float(x), float(y)] for x, y in member["frame_zero_points"]],
            }
            for member in members
        ],
        "group_transform": {
            "step_affine": None,
            "cumulative_affine": _identity_matrix(),
            "decomposed": {
                "translation": [0.0, 0.0],
                "rotation_degrees": 0.0,
                "scale": 1.0,
            },
        },
        "anchor": {
            "sets": anchor_sets,
            "conflict_rms_px": None,
            "conflict_rotation_deg": None,
            "conflict_scale_ratio": None,
        },
        "reason": None,
    }


def _evaluate_anchor(
    anchor: dict[str, Any],
    role: str,
    previous_points: Any,
    next_points: Any | None,
    valid: Any | None,
    lk_error: Any | None,
    limits: dict[str, Any],
    budget: dict[str, Any],
) -> dict[str, Any]:
    _, np = _opencv()
    diagnosis: dict[str, Any] = {
        "anchor_id": anchor["anchor_id"],
        "role": role,
        "member_id": anchor["member_id"],
        "valid_count": 0,
        "valid_ratio": 0.0,
        "median_lk_error": None,
        "median_affine_residual_px": None,
        "spread_px": None,
        "planarity": None,
        "step_affine": None,
        "decomposed": None,
        "status": "INVALID",
        "reason": None,
    }
    if next_points is None or valid is None or lk_error is None:
        diagnosis["reason"] = "ANCHOR_FIT_FAILED"
        return {
            "diagnosis": diagnosis,
            "rank": 6,
            "reason": "ANCHOR_FIT_FAILED",
            "matrix": None,
            "bounds": None,
        }
    valid_count = int(np.count_nonzero(valid))
    valid_ratio = float(valid_count / len(previous_points))
    diagnosis["valid_count"] = valid_count
    diagnosis["valid_ratio"] = valid_ratio
    if valid_count < int(limits["min_valid_anchor_points"]) or valid_ratio < float(
        limits["min_valid_anchor_ratio"]
    ):
        diagnosis["reason"] = "INSUFFICIENT_VALID_ANCHOR_TRACKS"
        return {
            "diagnosis": diagnosis,
            "rank": 1 if role == "primary" else 2,
            "reason": "INSUFFICIENT_VALID_ANCHOR_TRACKS",
            "matrix": None,
            "bounds": None,
        }
    tracked = next_points[valid]
    spread, planarity = _eigen_statistics(tracked)
    diagnosis["spread_px"] = spread
    diagnosis["planarity"] = planarity
    if spread < float(limits["min_anchor_spread_px"]) or planarity < float(
        limits["min_anchor_planarity"]
    ):
        diagnosis["reason"] = "ANCHOR_DEGENERATE"
        return {
            "diagnosis": diagnosis,
            "rank": 3,
            "reason": "ANCHOR_DEGENERATE",
            "matrix": None,
            "bounds": None,
        }
    median_lk_error = float(np.median(lk_error[valid]))
    diagnosis["median_lk_error"] = median_lk_error
    if median_lk_error > float(limits["max_median_lk_error_px"]):
        diagnosis["reason"] = "LK_QUALITY_TOO_LOW"
        return {
            "diagnosis": diagnosis,
            "rank": 4,
            "reason": "LK_QUALITY_TOO_LOW",
            "matrix": None,
            "bounds": None,
        }
    matrix = _fit_similarity(previous_points[valid], tracked, budget)
    if matrix is None or not np.isfinite(matrix).all():
        diagnosis["reason"] = "ANCHOR_FIT_FAILED"
        return {
            "diagnosis": diagnosis,
            "rank": 6,
            "reason": "ANCHOR_FIT_FAILED",
            "matrix": None,
            "bounds": None,
        }
    matrix_list = _matrix_list(matrix)
    predicted = _apply(matrix_list, previous_points[valid])
    residuals = np.linalg.norm(predicted - tracked, axis=1)
    median_residual = float(np.median(residuals))
    diagnosis["median_affine_residual_px"] = median_residual
    diagnosis["step_affine"] = matrix_list
    diagnosis["decomposed"] = {
        "translation": _decompose(matrix_list)["translation"],
        "rotation_degrees": _decompose(matrix_list)["rotation_degrees"],
        "scale": _decompose(matrix_list)["scale"],
    }
    if median_residual > float(limits["max_median_affine_residual_px"]):
        diagnosis["reason"] = "ANCHOR_RESIDUAL_TOO_HIGH"
        return {
            "diagnosis": diagnosis,
            "rank": 5,
            "reason": "ANCHOR_RESIDUAL_TOO_HIGH",
            "matrix": matrix_list,
            "bounds": None,
        }
    if _decompose(matrix_list)["determinant"] <= 0:
        diagnosis["reason"] = "ANCHOR_FIT_FAILED"
        return {
            "diagnosis": diagnosis,
            "rank": 6,
            "reason": "ANCHOR_FIT_FAILED",
            "matrix": matrix_list,
            "bounds": None,
        }
    bounds = _bounds_reason(matrix_list, limits)
    if bounds is not None:
        diagnosis["reason"] = bounds
    else:
        diagnosis["status"] = "VALID"
    return {
        "diagnosis": diagnosis,
        "rank": 8 if bounds is not None else None,
        "reason": bounds,
        "matrix": matrix_list,
        "bounds": bounds,
    }


def _conflict(
    results: list[dict[str, Any]],
    loaded: dict[str, Any],
    limits: dict[str, Any],
) -> dict[str, Any]:
    _, np = _opencv()
    anchor_order = [anchor["anchor_id"] for anchor in loaded["anchors"]]
    primary_index = anchor_order.index(loaded["primary_anchor_id"])
    primary_result = results[primary_index]
    frame_zero_points = [
        point for member in loaded["members"] for point in member["frame_zero_points"]
    ]
    primary_matrix = primary_result["matrix"]
    if primary_matrix is None:
        return {
            "conflict": False,
            "rms": None,
            "rotation_deg": None,
            "scale_ratio": None,
        }
    primary_prediction = _apply(primary_matrix, frame_zero_points)
    primary_decomposition = _decompose(primary_matrix)
    max_rms = 0.0
    max_rotation = 0.0
    max_scale_ratio = 0.0
    for index, result in enumerate(results):
        if index == primary_index or result["matrix"] is None:
            continue
        witness_matrix = result["matrix"]
        witness_prediction = _apply(witness_matrix, frame_zero_points)
        difference = primary_prediction - witness_prediction
        rms = float(np.sqrt(np.mean(np.sum(difference * difference, axis=1))))
        witness_decomposition = _decompose(witness_matrix)
        rotation = abs(
            primary_decomposition["rotation_degrees"] - witness_decomposition["rotation_degrees"]
        )
        scale_ratio = abs(primary_decomposition["scale"] / witness_decomposition["scale"] - 1.0)
        max_rms = max(max_rms, rms)
        max_rotation = max(max_rotation, rotation)
        max_scale_ratio = max(max_scale_ratio, scale_ratio)
    conflict = (
        max_rms > float(limits["conflict_rms_px"])
        or max_rotation > float(limits["conflict_rotation_deg"])
        or max_scale_ratio > float(limits["conflict_scale_ratio"])
    )
    return {
        "conflict": conflict,
        "rms": max_rms,
        "rotation_deg": max_rotation,
        "scale_ratio": max_scale_ratio,
    }


def _sticky_c_frame(config: dict[str, Any], frame_index: int) -> dict[str, Any]:
    return {
        "frame_index": config["frames"][frame_index]["index"],
        "tick": config["frames"][frame_index]["tick"],
        "status": "ABSTAINED",
        "members": [],
        "group_transform": None,
        "anchor": None,
        "reason": "PREVIOUS_TRANSITION_ABSTAINED",
    }


def run_method_c(
    config: dict[str, Any], loaded: dict[str, Any], frames: list[Any]
) -> dict[str, Any]:
    _, np = _opencv()
    limits = config["group"]["limits"]
    budget = config["method_c_budget"]
    members = loaded["members"]
    frame_zero_members = {
        member["primitive_id"]: np.asarray(member["frame_zero_points"], dtype=np.float64)
        for member in members
    }
    anchor_points = {
        anchor["anchor_id"]: np.asarray(anchor["points"], dtype=np.float32)
        for anchor in loaded["anchors"]
    }
    output_frames: list[dict[str, Any]] = [_c_frame_zero(config, loaded)]
    cumulative = _identity_matrix()
    sticky = False
    for frame_index in range(1, len(frames)):
        if sticky:
            output_frames.append(_sticky_c_frame(config, frame_index))
            continue
        results: list[dict[str, Any]] = []
        next_anchor_points: dict[str, Any] = {}
        for anchor in loaded["anchors"]:
            anchor_id = anchor["anchor_id"]
            role = "primary" if anchor_id == loaded["primary_anchor_id"] else "witness"
            previous_points = anchor_points[anchor_id]
            next_points, valid, lk_error = _track(
                frames[frame_index - 1], frames[frame_index], previous_points, budget
            )
            result = _evaluate_anchor(
                anchor,
                role,
                previous_points,
                next_points,
                valid,
                lk_error,
                limits,
                budget,
            )
            results.append(result)
            if next_points is not None:
                next_anchor_points[anchor_id] = next_points
        failures = [
            (index, result)
            for index, result in enumerate(results)
            if result["reason"] is not None
            and result["rank"] is not None
            and int(result["rank"]) <= 6
        ]
        group_reason: str | None = None
        conflict: dict[str, Any] = {
            "conflict": False,
            "rms": None,
            "rotation_deg": None,
            "scale_ratio": None,
        }
        if failures:
            _index, first_failure = min(failures, key=lambda item: (item[1]["rank"], item[0]))
            group_reason = C_GROUP_REASONS[int(first_failure["rank"])]
        else:
            conflict = _conflict(results, loaded, limits)
            if conflict["conflict"]:
                group_reason = "ANCHOR_CONFLICT"
            else:
                bounds_failures = [result for result in results if result["bounds"] is not None]
                if bounds_failures:
                    group_reason = "TRANSFORM_OUT_OF_BOUNDS"
        if group_reason is not None:
            output_frames.append(
                {
                    "frame_index": config["frames"][frame_index]["index"],
                    "tick": config["frames"][frame_index]["tick"],
                    "status": "ABSTAINED",
                    "members": [],
                    "group_transform": None,
                    "anchor": {
                        "sets": [result["diagnosis"] for result in results],
                        "conflict_rms_px": conflict["rms"],
                        "conflict_rotation_deg": conflict["rotation_deg"],
                        "conflict_scale_ratio": conflict["scale_ratio"],
                    },
                    "reason": group_reason,
                }
            )
            sticky = True
            continue
        step = results[
            [anchor["anchor_id"] for anchor in loaded["anchors"]].index(loaded["primary_anchor_id"])
        ]["matrix"]
        cumulative = _compose(step, cumulative)
        transformed_members: list[dict[str, Any]] = []
        valid_geometry = True
        for member in members:
            points = _apply(cumulative, frame_zero_members[member["primitive_id"]])
            if not np.isfinite(points).all():
                valid_geometry = False
                break
            transformed_members.append(
                {
                    "primitive_id": member["primitive_id"],
                    "points": [[float(x), float(y)] for x, y in points],
                }
            )
        if not valid_geometry or _decompose(cumulative)["scale"] <= 0:
            output_frames.append(
                {
                    "frame_index": config["frames"][frame_index]["index"],
                    "tick": config["frames"][frame_index]["tick"],
                    "status": "ABSTAINED",
                    "members": [],
                    "group_transform": None,
                    "anchor": {
                        "sets": [result["diagnosis"] for result in results],
                        "conflict_rms_px": conflict["rms"],
                        "conflict_rotation_deg": conflict["rotation_deg"],
                        "conflict_scale_ratio": conflict["scale_ratio"],
                    },
                    "reason": "INVALID_MEMBER_GEOMETRY",
                }
            )
            sticky = True
            continue
        anchor_points.update(next_anchor_points)
        output_frames.append(
            {
                "frame_index": config["frames"][frame_index]["index"],
                "tick": config["frames"][frame_index]["tick"],
                "status": "SUPPORTED",
                "members": transformed_members,
                "group_transform": {
                    "step_affine": step,
                    "cumulative_affine": cumulative,
                    "decomposed": {
                        "translation": _decompose(cumulative)["translation"],
                        "rotation_degrees": _decompose(cumulative)["rotation_degrees"],
                        "scale": _decompose(cumulative)["scale"],
                    },
                },
                "anchor": {
                    "sets": [result["diagnosis"] for result in results],
                    "conflict_rms_px": conflict["rms"],
                    "conflict_rotation_deg": conflict["rotation_deg"],
                    "conflict_scale_ratio": conflict["scale_ratio"],
                },
                "reason": None,
            }
        )
    return {
        "schema_version": OUTPUT_SCHEMA,
        "artifact_classification": CLASSIFICATION,
        "method": METHOD_C,
        "identity_claim": IDENTITY_CLAIM,
        "group_label": config["group"]["group_label"],
        "frames": output_frames,
    }


def _b_frame_zero(config: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame_index": config["frames"][0]["index"],
        "tick": config["frames"][0]["tick"],
        "status": "SUPPORTED",
        "members": [
            {
                "primitive_id": member["primitive_id"],
                "points": [[float(x), float(y)] for x, y in member["frame_zero_points"]],
            }
            for member in loaded["members"]
        ],
        "member_flow": [
            {
                "primitive_id": member["primitive_id"],
                "status": "SUPPORTED",
                "valid_count": None,
                "valid_ratio": None,
                "median_lk_error": None,
                "median_affine_residual_px": None,
                "step_affine": None,
            }
            for member in loaded["members"]
        ],
        "group_transform": None,
        "anchor": None,
        "reason": None,
    }


def _b_sticky_frame(config: dict[str, Any], frame_index: int) -> dict[str, Any]:
    return {
        "frame_index": config["frames"][frame_index]["index"],
        "tick": config["frames"][frame_index]["tick"],
        "status": "ABSTAINED",
        "members": [],
        "member_flow": [],
        "group_transform": None,
        "anchor": None,
        "reason": "PREVIOUS_TRANSITION_ABSTAINED",
    }


def run_method_b(
    config: dict[str, Any], loaded: dict[str, Any], frames: list[Any]
) -> dict[str, Any]:
    _, np = _opencv()
    budget = config["method_b_budget"]
    members = loaded["members"]
    geometry = {
        member["primitive_id"]: np.asarray(member["frame_zero_points"], dtype=np.float64)
        for member in members
    }
    samples = {
        member["primitive_id"]: _sample_polygon_boundary(
            member["frame_zero_points"], float(budget["boundary_sample_spacing_px"])
        )
        for member in members
    }
    output_frames: list[dict[str, Any]] = [_b_frame_zero(config, loaded)]
    sticky = False
    for frame_index in range(1, len(frames)):
        if sticky:
            output_frames.append(_b_sticky_frame(config, frame_index))
            continue
        member_flow: list[dict[str, Any]] = []
        next_geometry: dict[str, Any] = {}
        next_samples: dict[str, Any] = {}
        failed = False
        for member in members:
            member_id = member["primitive_id"]
            previous_samples = samples[member_id]
            next_points, valid, lk_error = _track(
                frames[frame_index - 1], frames[frame_index], previous_samples, budget
            )
            flow: dict[str, Any] = {
                "primitive_id": member_id,
                "status": "SUPPORTED",
                "valid_count": 0,
                "valid_ratio": 0.0,
                "median_lk_error": None,
                "median_affine_residual_px": None,
                "step_affine": None,
            }
            if next_points is None or valid is None or lk_error is None:
                flow["status"] = "ABSTAINED"
                flow["reason"] = "MEMBER_FIT_FAILED"
                member_flow.append(flow)
                failed = True
                continue
            valid_count = int(np.count_nonzero(valid))
            valid_ratio = float(valid_count / len(previous_samples))
            flow["valid_count"] = valid_count
            flow["valid_ratio"] = valid_ratio
            if valid_count < int(budget["min_valid_member_tracks"]) or valid_ratio < float(
                budget["min_valid_member_ratio"]
            ):
                flow["status"] = "ABSTAINED"
                flow["reason"] = "INSUFFICIENT_VALID_MEMBER_TRACKS"
                member_flow.append(flow)
                failed = True
                continue
            median_lk_error = float(np.median(lk_error[valid]))
            flow["median_lk_error"] = median_lk_error
            if median_lk_error > float(budget["max_median_lk_error_px"]):
                flow["status"] = "ABSTAINED"
                flow["reason"] = "LK_QUALITY_TOO_LOW"
                member_flow.append(flow)
                failed = True
                continue
            tracked = next_points[valid]
            matrix = _fit_similarity(previous_samples[valid], tracked, budget)
            if matrix is None or not np.isfinite(matrix).all():
                flow["status"] = "ABSTAINED"
                flow["reason"] = "MEMBER_FIT_FAILED"
                member_flow.append(flow)
                failed = True
                continue
            matrix_list = _matrix_list(matrix)
            predicted = _apply(matrix_list, previous_samples[valid])
            residuals = np.linalg.norm(predicted - tracked, axis=1)
            median_residual = float(np.median(residuals))
            flow["median_affine_residual_px"] = median_residual
            flow["step_affine"] = matrix_list
            if median_residual > float(budget["max_member_median_residual_px"]):
                flow["status"] = "ABSTAINED"
                flow["reason"] = "MEMBER_RESIDUAL_TOO_HIGH"
                member_flow.append(flow)
                failed = True
                continue
            if _decompose(matrix_list)["determinant"] <= 0:
                flow["status"] = "ABSTAINED"
                flow["reason"] = "MEMBER_FIT_FAILED"
                member_flow.append(flow)
                failed = True
                continue
            bounds = _bounds_reason(matrix_list, config["group"]["limits"])
            if bounds is not None:
                flow["status"] = "ABSTAINED"
                flow["reason"] = bounds
                member_flow.append(flow)
                failed = True
                continue
            next_geometry[member_id] = _apply(matrix_list, geometry[member_id])
            next_samples[member_id] = next_points
            member_flow.append(flow)
        if failed:
            output_frames.append(
                {
                    "frame_index": config["frames"][frame_index]["index"],
                    "tick": config["frames"][frame_index]["tick"],
                    "status": "ABSTAINED",
                    "members": [],
                    "member_flow": member_flow,
                    "group_transform": None,
                    "anchor": None,
                    "reason": "MEMBER_LOST",
                }
            )
            sticky = True
            continue
        geometry.update(next_geometry)
        samples.update(next_samples)
        output_frames.append(
            {
                "frame_index": config["frames"][frame_index]["index"],
                "tick": config["frames"][frame_index]["tick"],
                "status": "SUPPORTED",
                "members": [
                    {
                        "primitive_id": member["primitive_id"],
                        "points": [
                            [float(x), float(y)] for x, y in geometry[member["primitive_id"]]
                        ],
                    }
                    for member in members
                ],
                "member_flow": member_flow,
                "group_transform": None,
                "anchor": None,
                "reason": None,
            }
        )
    return {
        "schema_version": OUTPUT_SCHEMA,
        "artifact_classification": CLASSIFICATION,
        "method": METHOD_B,
        "identity_claim": IDENTITY_CLAIM,
        "group_label": config["group"]["group_label"],
        "frames": output_frames,
    }


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize)
        return None
    try:  # pragma: no cover - platform dependent
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(usage * (1 if sys.platform == "darwin" else 1024))
    except (ImportError, OSError):
        return None


def measured_runtime(
    method: str, config: dict[str, Any], loaded: dict[str, Any], frames: list[Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    tracemalloc.start()
    started = time.perf_counter()
    raw = (
        run_method_b(config, loaded, frames)
        if method == "B"
        else run_method_c(config, loaded, frames)
    )
    elapsed = time.perf_counter() - started
    _, python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return raw, {
        "method": raw["method"],
        "wall_time_seconds": elapsed,
        "wall_time_seconds_per_frame": elapsed / len(frames),
        "python_tracemalloc_peak_bytes": python_peak,
        "process_peak_working_set_bytes": _peak_rss_bytes(),
        "gpu_vram_bytes": None,
        "memory_scope_note": (
            "process peak includes the isolated Python/OpenCV worker; tracemalloc "
            "excludes native OpenCV allocations"
        ),
    }


def run_worker(method: str, config_path: Path, repo_root: Path) -> int:
    config_path = config_path.resolve()
    repo_root = repo_root.resolve()
    loaded = load_config(config_path, repo_root)
    frames = load_runtime_frames(loaded)
    raw, cost = measured_runtime(method, loaded["config"], loaded, frames)
    payload = canonical_bytes({"raw": raw, "cost": cost})
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
    return 0


def environment_report() -> dict[str, Any]:
    cv2, np = _opencv()
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "opencv": cv2.__version__,
        "opencv_declared_analysis_requirement": FROZEN_DECISION_THRESHOLDS["environment"][
            "opencv_wheel"
        ],
        "opencv_requirement_satisfied": cv2.__version__
        == FROZEN_DECISION_THRESHOLDS["environment"]["opencv_version"],
        "external_models": [],
        "gpu_used": False,
        "runner_identity": RUNNER_IDENTITY,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="T2-P1 isolated runtime worker")
    parser.add_argument("--worker", choices=("B", "C"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return run_worker(args.worker, args.config, args.repo_root)
    except (T2Error, OSError, ValueError) as exc:
        print(f"T2 runtime failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
