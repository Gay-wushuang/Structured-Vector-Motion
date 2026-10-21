"""T2-P1 offline ground-truth evaluation, metrics, and decision grammar.

This module is part of the offline phase only. It loads ``ground-truth.json``,
computes metrics, renders comparisons, and applies the frozen T2-P0A gates. It
is never imported by ``runtime.py`` and never feeds a runtime transform.

The decision object is intentionally written to the run manifest rather than
``metrics.json`` because the frozen cost gate uses measured wall time, while
``metrics.json`` must stay byte-identical across repeated full runs.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

T2_ROOT = Path(__file__).resolve().parent
PILOT_ROOT = T2_ROOT.parent
sys.path.insert(0, str(T2_ROOT))
sys.path.insert(0, str(PILOT_ROOT))
import run_experiment as t1  # noqa: E402
import runtime  # noqa: E402

GT_SCHEMA = "t2-fixture-ground-truth-0.1"
METRICS_SCHEMA = "t2-group-anchor-metrics-0.1"
REPRO_SCHEMA = "t2-group-anchor-reproducibility-0.1"
GS = runtime.FROZEN_DECISION_THRESHOLDS

REQUIRED_GT_FIELDS = {
    "schema_version",
    "fixture_id",
    "canvas",
    "primary_anchor_id",
    "witness_anchor_ids",
    "frames",
    "anchor_sets",
    "occluders",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise runtime.T2Error(message)


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise runtime.T2Error(f"{name} must be an object")
    return value


def _require_keys(value: dict[str, Any], required: set[str], name: str) -> None:
    if set(value) != required:
        missing = sorted(required - set(value))
        extra = sorted(set(value) - required)
        raise runtime.T2Error(
            f"{name} fields do not match the closed profile; missing={missing} extra={extra}"
        )


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise runtime.T2Error(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise runtime.T2Error(f"{name} must be a finite number")
    return result


def load_ground_truth(loaded: dict[str, Any]) -> dict[str, Any]:
    """Load and validate the offline GT; called only after raw output exists."""
    config = loaded["config"]
    path = loaded["fixture_root"] / "ground-truth.json"
    try:
        gt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise runtime.T2Error(f"cannot read ground truth {path}: {exc}") from exc
    gt = _require_mapping(gt, "ground_truth")
    _require_keys(gt, REQUIRED_GT_FIELDS, "ground_truth")
    if gt["schema_version"] != GT_SCHEMA:
        raise runtime.T2Error("unsupported ground-truth schema")
    if gt["canvas"] != [runtime.CANVAS[0], runtime.CANVAS[1]]:
        raise runtime.T2Error("ground-truth canvas must be 512x512")
    fixture_id = Path(config["fixture_root"]).name
    if gt["fixture_id"] != f"t2-{fixture_id}":
        raise runtime.T2Error("ground-truth fixture_id does not match fixture_root")
    if gt["primary_anchor_id"] != loaded["primary_anchor_id"]:
        raise runtime.T2Error("ground-truth primary anchor does not match config")
    if gt["witness_anchor_ids"] != loaded["witness_anchor_ids"]:
        raise runtime.T2Error("ground-truth witness anchors do not match config")

    frames = gt["frames"]
    _require(isinstance(frames, list) and len(frames) == len(runtime.TICKS), "GT frames")
    for index, frame in enumerate(frames):
        frame = _require_mapping(frame, f"GT frame {index}")
        _require_keys(frame, {"index", "tick", "members", "group_transform"}, f"GT frame {index}")
        if frame["index"] != index or frame["tick"] != runtime.TICKS[index]:
            raise runtime.T2Error("ground-truth frames must be ordered ticks 0,12,24,36")
        members = frame["members"]
        if not isinstance(members, list) or len(members) != len(loaded["members"]):
            raise runtime.T2Error("ground-truth member count does not match config")
        for member, configured in zip(members, loaded["members"], strict=True):
            member = _require_mapping(member, "GT member")
            _require_keys(member, {"primitive_id", "points"}, "GT member")
            if member["primitive_id"] != configured["primitive_id"]:
                raise runtime.T2Error("ground-truth member order does not match config")
            points = _validate_gt_points(member["points"], "GT member points")
            if index == 0 and points != configured["frame_zero_points"]:
                raise runtime.T2Error("config frame-zero geometry does not match ground truth")
        group_transform = _require_mapping(frame["group_transform"], "GT group_transform")
        _require_keys(
            group_transform,
            {"translation", "rotation_degrees", "scale"},
            "GT group_transform",
        )
        translation = group_transform["translation"]
        _require(
            isinstance(translation, list) and len(translation) == 2,
            "GT group translation must be [x, y]",
        )
        _finite(translation[0], "GT group translation x")
        _finite(translation[1], "GT group translation y")
        _finite(group_transform["rotation_degrees"], "GT group rotation")
        _finite(group_transform["scale"], "GT group scale")

    anchors = gt["anchor_sets"]
    if not isinstance(anchors, list) or len(anchors) != len(loaded["anchors"]):
        raise runtime.T2Error("ground-truth anchor count does not match config")
    for anchor, configured in zip(anchors, loaded["anchors"], strict=True):
        anchor = _require_mapping(anchor, "GT anchor")
        _require_keys(anchor, {"anchor_id", "member_id", "frame_index", "points"}, "GT anchor")
        if (
            anchor["anchor_id"] != configured["anchor_id"]
            or anchor["member_id"] != configured["member_id"]
            or anchor["frame_index"] != configured["frame_index"]
        ):
            raise runtime.T2Error("ground-truth anchors do not match config")
        points = _validate_gt_points(anchor["points"], "GT anchor points")
        if points != configured["points"]:
            raise runtime.T2Error("config anchor points do not match ground truth")

    occluders = gt["occluders"]
    if not isinstance(occluders, list):
        raise runtime.T2Error("GT occluders must be a list")
    for occluder in occluders:
        occluder = _require_mapping(occluder, "GT occluder")
        _require_keys(occluder, {"frame_index", "rect"}, "GT occluder")
        if occluder["frame_index"] not in range(len(runtime.TICKS)):
            raise runtime.T2Error("GT occluder frame_index is out of range")
        rect = occluder["rect"]
        if (
            not isinstance(rect, list)
            or len(rect) != 4
            or any(isinstance(value, bool) or not isinstance(value, int) for value in rect)
        ):
            raise runtime.T2Error("GT occluder rect must be four integers")
        x0, y0, x1, y1 = rect
        if not (0 <= x0 < x1 <= runtime.CANVAS[0] and 0 <= y0 < y1 <= runtime.CANVAS[1]):
            raise runtime.T2Error("GT occluder rect is outside the canvas")
    return gt


def _validate_gt_points(value: Any, name: str) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise runtime.T2Error(f"{name} must be a non-empty list")
    points = []
    for index, point in enumerate(value):
        if not isinstance(point, list) or len(point) != 2:
            raise runtime.T2Error(f"{name}[{index}] must be [x, y]")
        points.append(
            [_finite(point[0], f"{name}[{index}].x"), _finite(point[1], f"{name}[{index}].y")]
        )
    return points


def verify_fixture_frames(gt: dict[str, Any], frames: list[Any]) -> None:
    """Verify each decoded frame equals the GT rasterization plus occluders."""
    _require(len(frames) == len(gt["frames"]), "frame count does not match GT")
    for frame_index, (frame, gt_frame) in enumerate(zip(frames, gt["frames"], strict=True)):
        expected = np.full(runtime.CANVAS[::-1], 255, dtype=np.uint8)
        for member in gt_frame["members"]:
            rounded = np.rint(np.asarray(member["points"], dtype=np.float64)).astype(np.int32)
            cv2.fillPoly(expected, [rounded], 0, lineType=cv2.LINE_8)
        for occluder in gt["occluders"]:
            if occluder["frame_index"] != frame_index:
                continue
            x0, y0, x1, y1 = occluder["rect"]
            expected[y0:y1, x0:x1] = 255
        if not np.array_equal(frame, expected):
            raise runtime.T2Error(f"fixture frame {frame_index} does not match ground truth")


def _fit_similarity_ls(source: Any, target: Any) -> list[list[float]] | None:
    source_array = np.asarray(source, dtype=np.float64)
    target_array = np.asarray(target, dtype=np.float64)
    if source_array.shape != target_array.shape or len(source_array) < 2:
        return None
    source_mean = source_array.mean(axis=0)
    target_mean = target_array.mean(axis=0)
    source_centered = source_array - source_mean
    target_centered = target_array - target_mean
    covariance = target_centered.T @ source_centered / len(source_array)
    u, singular_values, vt = np.linalg.svd(covariance)
    sign = 1.0 if np.linalg.det(u @ vt) >= 0 else -1.0
    correction = np.asarray([[1.0, 0.0], [0.0, sign]], dtype=np.float64)
    rotation = u @ correction @ vt
    variance = float(np.mean(np.sum(source_centered * source_centered, axis=1)))
    if variance <= 0:
        return None
    scale = float(np.sum(singular_values * np.asarray([1.0, sign]))) / variance
    if not math.isfinite(scale) or scale <= 0:
        return None
    translation = target_mean - scale * (rotation @ source_mean)
    matrix = [
        [scale * float(rotation[0, 0]), scale * float(rotation[0, 1]), float(translation[0])],
        [scale * float(rotation[1, 0]), scale * float(rotation[1, 1]), float(translation[1])],
    ]
    if not all(math.isfinite(value) for row in matrix for value in row):
        return None
    return matrix


def _step_vector(matrix: list[list[float]]) -> list[float]:
    a, _, tx = (float(value) for value in matrix[0])
    c, _, ty = (float(value) for value in matrix[1])
    return [tx, ty, math.degrees(math.atan2(c, a)), math.sqrt(a * a + c * c)]


def _second_difference_jitter(vectors: list[list[float]]) -> float | None:
    if len(vectors) < 3:
        return None
    values = []
    for index in range(1, len(vectors) - 1):
        previous = np.asarray(vectors[index - 1], dtype=np.float64)
        current = np.asarray(vectors[index], dtype=np.float64)
        following = np.asarray(vectors[index + 1], dtype=np.float64)
        values.append(float(np.linalg.norm(previous - 2 * current + following)))
    return float(np.mean(values)) if values else None


def _member_centroid(points: Any) -> Any:
    return np.asarray(points, dtype=np.float64).mean(axis=0)


def _pairwise_distances(centroids: list[Any]) -> dict[tuple[int, int], float]:
    distances = {}
    for left in range(len(centroids)):
        for right in range(left + 1, len(centroids)):
            distances[(left, right)] = float(np.linalg.norm(centroids[left] - centroids[right]))
    return distances


def method_metrics(
    raw: dict[str, Any],
    frames: list[Any],
    gt: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    method = raw["method"]
    per_frame: list[dict[str, Any]] = []
    supported_frames: list[tuple[int, dict[str, Any]]] = []
    predicted_centroids: dict[int, Any] = {}
    gt_centroids: dict[int, Any] = {}
    group_ious: list[float] = []
    member_ious: list[float] = []
    member_rmses: list[float] = []
    group_rmses: list[float] = []
    for frame_index, raw_frame in enumerate(raw["frames"]):
        gt_frame = gt["frames"][frame_index]
        if raw_frame["frame_index"] != frame_index or raw_frame["tick"] != gt_frame["tick"]:
            raise runtime.T2Error("raw frame order does not match the frozen frame table")
        if raw_frame["status"] != "SUPPORTED":
            per_frame.append(
                {
                    "frame_index": frame_index,
                    "tick": gt_frame["tick"],
                    "status": raw_frame["status"],
                    "reason": raw_frame.get("reason"),
                }
            )
            continue
        predicted = {
            member["primitive_id"]: np.asarray(member["points"], dtype=np.float64)
            for member in raw_frame["members"]
        }
        expected_ids = [member["primitive_id"] for member in gt_frame["members"]]
        if set(predicted) != set(expected_ids):
            raise runtime.T2Error("raw supported frame does not contain exactly the GT members")
        frame_member_metrics = []
        masks = []
        gt_masks = []
        for member in gt_frame["members"]:
            member_id = member["primitive_id"]
            points = predicted[member_id]
            gt_points = np.asarray(member["points"], dtype=np.float64)
            predicted_mask = t1.polygon_mask(points, frames[frame_index].shape)
            gt_mask = t1.polygon_mask(gt_points, frames[frame_index].shape)
            iou = t1.mask_iou(predicted_mask, gt_mask)
            vertex_rmse = t1._ordered_vertex_rmse(points, gt_points)
            centroid_error = float(np.linalg.norm(points.mean(axis=0) - gt_points.mean(axis=0)))
            frame_member_metrics.append(
                {
                    "primitive_id": member_id,
                    "iou": iou,
                    "vertex_rmse_px": vertex_rmse,
                    "centroid_error_px": centroid_error,
                }
            )
            member_ious.append(iou)
            member_rmses.append(vertex_rmse)
            masks.append(predicted_mask)
            gt_masks.append(gt_mask)
        predicted_union = np.zeros_like(masks[0])
        gt_union = np.zeros_like(gt_masks[0])
        for mask in masks:
            predicted_union = np.maximum(predicted_union, mask)
        for mask in gt_masks:
            gt_union = np.maximum(gt_union, mask)
        group_iou = t1.mask_iou(predicted_union, gt_union)
        predicted_centroids[frame_index] = np.asarray(
            [_member_centroid(predicted[member_id]) for member_id in expected_ids],
            dtype=np.float64,
        ).mean(axis=0)
        gt_centroids[frame_index] = np.asarray(
            [_member_centroid(member["points"]) for member in gt_frame["members"]],
            dtype=np.float64,
        ).mean(axis=0)
        group_rmse = float(np.mean([item["vertex_rmse_px"] for item in frame_member_metrics]))
        group_centroid_error = float(
            np.linalg.norm(predicted_centroids[frame_index] - gt_centroids[frame_index])
        )
        group_ious.append(group_iou)
        group_rmses.append(group_rmse)
        supported_frames.append((frame_index, raw_frame))
        per_frame.append(
            {
                "frame_index": frame_index,
                "tick": gt_frame["tick"],
                "status": "SUPPORTED",
                "members": frame_member_metrics,
                "group_iou": group_iou,
                "group_vertex_rmse_px": group_rmse,
                "group_centroid_error_px": group_centroid_error,
            }
        )

    reference_index = runtime.DRIFT_REFERENCE_FRAME_INDEX
    reference_available = reference_index in predicted_centroids and reference_index in gt_centroids
    drift_by_frame: dict[int, float] = {}
    for frame_index, _raw_frame in supported_frames:
        entry = per_frame[frame_index]
        if reference_available and frame_index != reference_index:
            entry["group_drift_px"] = float(
                np.linalg.norm(
                    (predicted_centroids[frame_index] - predicted_centroids[reference_index])
                    - (gt_centroids[frame_index] - gt_centroids[reference_index])
                )
            )
            drift_by_frame[frame_index] = entry["group_drift_px"]
        elif frame_index == reference_index:
            entry["group_drift_px"] = 0.0
            drift_by_frame[frame_index] = 0.0

    step_vectors_group: list[list[float]] = []
    step_vectors_members: dict[str, list[list[float]]] = {}
    lk_point_counts: list[int | None] = []
    for frame_index in range(1, len(frames)):
        current = per_frame[frame_index]
        previous = per_frame[frame_index - 1]
        if current["status"] != "SUPPORTED" or previous["status"] != "SUPPORTED":
            break
        raw_frame = raw["frames"][frame_index]
        if method == runtime.METHOD_C:
            step_matrix = raw_frame["group_transform"]["step_affine"]
        else:
            source_centroids = np.asarray(
                [
                    _member_centroid(
                        next(
                            member["points"]
                            for member in raw["frames"][frame_index - 1]["members"]
                            if member["primitive_id"] == gt_member["primitive_id"]
                        )
                    )
                    for gt_member in gt["frames"][frame_index - 1]["members"]
                ],
                dtype=np.float64,
            )
            target_centroids = np.asarray(
                [
                    _member_centroid(
                        next(
                            member["points"]
                            for member in raw_frame["members"]
                            if member["primitive_id"] == gt_member["primitive_id"]
                        )
                    )
                    for gt_member in gt["frames"][frame_index]["members"]
                ],
                dtype=np.float64,
            )
            step_matrix = _fit_similarity_ls(source_centroids, target_centroids)
            _require(step_matrix is not None, "cannot derive B group step transform")
        step_vectors_group.append(_step_vector(step_matrix))
        for member in gt["frames"][frame_index]["members"]:
            member_id = member["primitive_id"]
            source = np.asarray(
                next(
                    member["points"]
                    for member in raw["frames"][frame_index - 1]["members"]
                    if member["primitive_id"] == member_id
                ),
                dtype=np.float64,
            )
            target = np.asarray(
                next(
                    member["points"]
                    for member in raw_frame["members"]
                    if member["primitive_id"] == member_id
                ),
                dtype=np.float64,
            )
            matrix = _fit_similarity_ls(source, target)
            if matrix is not None:
                step_vectors_members.setdefault(member_id, []).append(_step_vector(matrix))
        if method == runtime.METHOD_C:
            count = 0
            for anchor in raw_frame["anchor"]["sets"]:
                count += int(anchor["valid_count"])
            lk_point_counts.append(count)
        else:
            count = 0
            for flow in raw_frame["member_flow"]:
                count += int(flow["valid_count"] or 0)
            lk_point_counts.append(count)

    rigidity_values: list[float] = []
    if reference_available:
        reference_members = gt["frames"][reference_index]["members"]
        reference_points = {
            member["primitive_id"]: member["points"]
            for member in raw["frames"][reference_index]["members"]
        }
        reference_distances = _pairwise_distances(
            [
                _member_centroid(reference_points[gt_member["primitive_id"]])
                for gt_member in reference_members
            ]
        )
        for frame_index, raw_frame in supported_frames:
            if frame_index <= reference_index:
                continue
            current_points = {
                member["primitive_id"]: member["points"] for member in raw_frame["members"]
            }
            current_distances = _pairwise_distances(
                [
                    _member_centroid(current_points[gt_member["primitive_id"]])
                    for gt_member in gt["frames"][frame_index]["members"]
                ]
            )
            changes = [
                abs(current_distances[key] - reference_distances[key])
                for key in reference_distances
            ]
            rigidity = float(np.mean(changes)) if changes else 0.0
            rigidity_values.append(rigidity)
            per_frame[frame_index]["rigidity_error_px"] = rigidity

    member_jitters = [
        value
        for member_id, vectors in step_vectors_members.items()
        if (value := _second_difference_jitter(vectors)) is not None
    ]
    group_jitter = _second_difference_jitter(step_vectors_group)
    supported_entries = [entry for entry in per_frame if entry["status"] == "SUPPORTED"]
    abstained_entries = [entry for entry in per_frame if entry["status"] != "SUPPORTED"]
    reason_counts = Counter(entry["reason"] for entry in abstained_entries if entry.get("reason"))
    final_supported = len(per_frame) > 0 and per_frame[-1]["status"] == "SUPPORTED"
    drift_values = [drift_by_frame[index] for index in sorted(drift_by_frame)]
    summary = {
        "evaluated_frame_count": len(per_frame),
        "supported_frame_count": len(supported_entries),
        "abstained_frame_count": len(abstained_entries),
        "supported_frame_indices": [entry["frame_index"] for entry in supported_entries],
        "abstention_rate": float(len(abstained_entries) / len(per_frame)),
        "reason_counts": dict(sorted(reason_counts.items())),
        "mean_group_iou": float(np.mean(group_ious)) if group_ious else None,
        "mean_member_iou": float(np.mean(member_ious)) if member_ious else None,
        "mean_group_vertex_rmse_px": float(np.mean(group_rmses)) if group_rmses else None,
        "mean_member_vertex_rmse_px": float(np.mean(member_rmses)) if member_rmses else None,
        "final_group_vertex_rmse_px": group_rmses[-1] if final_supported and group_rmses else None,
        "mean_group_centroid_error_px": (
            float(np.mean([entry["group_centroid_error_px"] for entry in supported_entries]))
            if supported_entries
            else None
        ),
        "final_group_drift_px": drift_values[-1] if final_supported and drift_values else None,
        "drift_slope_px_per_frame": (
            t1._linear_slope(drift_values) if len(drift_values) >= 2 else None
        ),
        "rigidity_error_px": float(np.mean(rigidity_values)) if rigidity_values else None,
        "member_step_jitter_mean": float(np.mean(member_jitters)) if member_jitters else None,
        "group_step_jitter_mean": group_jitter,
        "lk_point_count_mean": (
            float(np.mean([count for count in lk_point_counts if count is not None]))
            if any(count is not None for count in lk_point_counts)
            else None
        ),
        "lk_point_counts": lk_point_counts,
    }
    return {"method": method, "per_frame": per_frame, "summary": summary}


def build_metrics(
    raw_b: dict[str, Any],
    raw_c: dict[str, Any],
    frames: list[Any],
    gt: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": METRICS_SCHEMA,
        "artifact_classification": runtime.CLASSIFICATION,
        "experiment_id": config["experiment_id"],
        "protocol": GS["protocol"],
        "evaluation_window": config["evaluation_window"],
        "methods": {
            "B": method_metrics(raw_b, frames, gt, config),
            "C": method_metrics(raw_c, frames, gt, config),
        },
    }


def _upper_miss(observed: float | None, required: float | None) -> float:
    if observed is None or required is None:
        return 1.0
    if required == 0:
        return 0.0 if observed <= 0 else 1.0
    return max(0.0, (observed - required) / abs(required))


def _lower_miss(observed: float | None, required: float | None) -> float:
    if observed is None or required is None:
        return 1.0
    if required == 0:
        return 0.0 if observed >= 0 else 1.0
    return max(0.0, (required - observed) / abs(required))


def _check(
    name: str,
    observed: float | None,
    required: float | None,
    passed: bool,
    miss: float,
) -> dict[str, Any]:
    return {
        "name": name,
        "observed": observed,
        "required": required,
        "passed": bool(passed),
        "relative_miss": float(miss),
    }


def evaluate_quality(
    fixture_id: str,
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    gates = thresholds["quality"][fixture_id]
    b = metrics["methods"]["B"]["summary"]
    c = metrics["methods"]["C"]["summary"]
    checks: list[dict[str, Any]] = []

    def add_binary(name: str, observed: float | None, required: float) -> None:
        passed = observed is not None and abs(observed - required) <= 1e-12
        checks.append(_check(name, observed, required, passed, 0.0 if passed else 1.0))

    add_binary("B_ABSTENTION_ZERO", b["abstention_rate"], float(gates["b_abstention_required"]))
    add_binary("C_ABSTENTION_ZERO", c["abstention_rate"], float(gates["c_abstention_required"]))

    observed = c["mean_group_iou"]
    required = float(gates["c_group_iou_min"])
    checks.append(
        _check(
            "C_GROUP_IOU_MIN",
            observed,
            required,
            observed is not None and observed >= required - 1e-12,
            _lower_miss(observed, required),
        )
    )
    observed = c["mean_member_iou"]
    required = float(gates["c_mean_member_iou_min"])
    checks.append(
        _check(
            "C_MEAN_MEMBER_IOU_MIN",
            observed,
            required,
            observed is not None and observed >= required - 1e-12,
            _lower_miss(observed, required),
        )
    )

    b_rmse = b["mean_group_vertex_rmse_px"]
    required = float(gates["c_mean_vertex_rmse_px_max"])
    if b_rmse is not None and b_rmse >= float(gates["c_mean_vertex_rmse_relative_band_b_min_px"]):
        required = min(
            required,
            float(gates["c_mean_vertex_rmse_relative_to_b_max"]) * b_rmse,
        )
    observed = c["mean_group_vertex_rmse_px"]
    checks.append(
        _check(
            "C_MEAN_VERTEX_RMSE_MAX",
            observed,
            required,
            observed is not None and observed <= required + 1e-12,
            _upper_miss(observed, required),
        )
    )

    b_drift = b["final_group_drift_px"]
    required = float(gates["c_final_group_drift_px_max"])
    if b_drift is not None and b_drift >= float(
        gates["c_final_group_drift_relative_band_b_min_px"]
    ):
        required = min(
            required,
            float(gates["c_final_group_drift_relative_to_b_max"]) * b_drift,
        )
    observed = c["final_group_drift_px"]
    checks.append(
        _check(
            "C_FINAL_GROUP_DRIFT_MAX",
            observed,
            required,
            observed is not None and observed <= required + 1e-12,
            _upper_miss(observed, required),
        )
    )

    b_jitter = b["group_step_jitter_mean"]
    if b_jitter is None:
        required = None
    elif b_jitter >= float(gates["c_group_step_jitter_relative_band_b_min"]):
        required = float(gates["c_group_step_jitter_relative_to_b_max"]) * b_jitter
    else:
        required = float(gates["c_group_step_jitter_absolute_max_when_b_below"])
    observed = c["group_step_jitter_mean"]
    checks.append(
        _check(
            "C_GROUP_STEP_JITTER_MAX",
            observed,
            required,
            observed is not None and required is not None and observed <= required + 1e-12,
            _upper_miss(observed, required),
        )
    )

    observed = c["rigidity_error_px"]
    required = float(gates["c_rigidity_error_px_max"])
    checks.append(
        _check(
            "C_RIGIDITY_ERROR_MAX",
            observed,
            required,
            observed is not None and observed <= required + 1e-12,
            _upper_miss(observed, required),
        )
    )

    failed = [check for check in checks if not check["passed"]]
    max_miss = max((check["relative_miss"] for check in failed), default=0.0)
    stop_band = float(thresholds["stop_band_relative_miss"][fixture_id])
    if not failed:
        status = "PASS"
    elif max_miss > stop_band:
        status = "STOP"
    else:
        status = "CONDITIONAL"
    b_control_valid = b["abstention_rate"] == 0.0 and b["supported_frame_count"] == len(
        runtime.TICKS
    )
    return {
        "fixture_id": fixture_id,
        "status": status,
        "max_relative_miss": max_miss,
        "stop_band_relative_miss": stop_band,
        "b_control_valid": b_control_valid,
        "failed_gates": [check["name"] for check in failed],
        "checks": checks,
    }


def evaluate_fail_closed(
    fixture_id: str,
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    gates = thresholds["fail_closed"][fixture_id]
    c_frames = metrics["methods"]["C"]["per_frame"]
    b_frames = metrics["methods"]["B"]["per_frame"]
    if fixture_id == "f3-low-texture":
        hard_c = [frame for frame in c_frames if frame["frame_index"] > 0]
        hard_b = [frame for frame in b_frames if frame["frame_index"] > 0]
        supported_c = [frame for frame in hard_c if frame["status"] == "SUPPORTED"]
        supported_b = [frame for frame in hard_b if frame["status"] == "SUPPORTED"]
        fail_open = [
            frame
            for frame in supported_c
            if frame["group_iou"] < float(gates["supported_group_iou_conditional_min"])
        ]
        conditional = [
            frame
            for frame in supported_c
            if float(gates["supported_group_iou_conditional_min"])
            <= frame["group_iou"]
            < float(gates["supported_group_iou_pass_min"])
        ]
        c_reasons = [frame["reason"] for frame in hard_c if frame["status"] == "ABSTAINED"]
        if fail_open:
            status = "FAIL_OPEN"
        elif conditional:
            status = "CONDITIONAL"
        elif supported_c:
            status = "PASS"
        elif not supported_b:
            status = "INCONCLUSIVE"
        else:
            status = "PASS"
        return {
            "fixture_id": fixture_id,
            "status": status,
            "observations": {
                "c_abstained_frame_reasons": c_reasons,
                "c_supported_hard_frames": [frame["frame_index"] for frame in supported_c],
                "b_supported_hard_frames": [frame["frame_index"] for frame in supported_b],
                "fail_open_group_ious": [frame["group_iou"] for frame in fail_open],
                "conditional_group_ious": [frame["group_iou"] for frame in conditional],
            },
        }
    if fixture_id == "f4-occlusion":
        frame_index = int(gates["occluded_frame_index"])
        frame = c_frames[frame_index]
        later = [c_frames[index] for index in range(frame_index + 1, len(c_frames))]
        if frame["status"] == "SUPPORTED":
            status = "FAIL_OPEN"
        elif frame["reason"] in gates["accepted_reasons"]:
            if any(later_frame["status"] == "SUPPORTED" for later_frame in later):
                status = "FAIL_OPEN"
            elif all(
                later_frame["reason"] == "PREVIOUS_TRANSITION_ABSTAINED" for later_frame in later
            ):
                status = "PASS"
            else:
                status = "CONDITIONAL"
        else:
            status = "CONDITIONAL"
        return {
            "fixture_id": fixture_id,
            "status": status,
            "observations": {
                "occluded_frame_status": frame["status"],
                "occluded_frame_reason": frame["reason"],
                "later_frames": [
                    {"status": later_frame["status"], "reason": later_frame["reason"]}
                    for later_frame in later
                ],
                "accepted_reasons": gates["accepted_reasons"],
            },
        }
    frame_index = int(gates["conflict_frame_index"])
    frame = c_frames[frame_index]
    later = [c_frames[index] for index in range(frame_index + 1, len(c_frames))]
    if frame["status"] == "SUPPORTED":
        status = "FAIL_OPEN"
    elif frame["reason"] == gates["required_reason"]:
        if any(later_frame["status"] == "SUPPORTED" for later_frame in later):
            status = "FAIL_OPEN"
        elif all(later_frame["reason"] == "PREVIOUS_TRANSITION_ABSTAINED" for later_frame in later):
            status = "PASS"
        else:
            status = "CONDITIONAL"
    else:
        status = "CONDITIONAL"
    return {
        "fixture_id": fixture_id,
        "status": status,
        "observations": {
            "conflict_frame_status": frame["status"],
            "conflict_frame_reason": frame["reason"],
            "later_frames": [
                {"status": later_frame["status"], "reason": later_frame["reason"]}
                for later_frame in later
            ],
            "required_reason": gates["required_reason"],
        },
    }


def evaluate_fixture(
    fixture_id: str,
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    evaluation: dict[str, Any] = {
        "fixture_id": fixture_id,
        "b_abstention_rate": metrics["methods"]["B"]["summary"]["abstention_rate"],
        "c_abstention_rate": metrics["methods"]["C"]["summary"]["abstention_rate"],
        "b_safety": {
            "supported_frames_below_0_90_group_iou": [
                frame["frame_index"]
                for frame in metrics["methods"]["B"]["per_frame"]
                if frame["status"] == "SUPPORTED" and frame["group_iou"] < 0.90
            ],
            "abstained_frame_reasons": metrics["methods"]["B"]["summary"]["reason_counts"],
        },
    }
    if fixture_id in thresholds["quality"]:
        evaluation["quality"] = evaluate_quality(fixture_id, metrics, thresholds)
    if fixture_id in thresholds["fail_closed"]:
        evaluation["fail_closed"] = evaluate_fail_closed(fixture_id, metrics, thresholds)
    return evaluation


def decide_overall(
    evaluations: dict[str, dict[str, Any]],
    metrics_by_fixture: dict[str, dict[str, Any]],
    costs: dict[str, dict[str, Any]],
    environment: dict[str, Any],
    determinism: dict[str, Any],
) -> dict[str, Any]:
    thresholds = GS
    total_b = sum(float(costs[fixture]["B"]["wall_time_seconds"]) for fixture in costs)
    total_c = sum(float(costs[fixture]["C"]["wall_time_seconds"]) for fixture in costs)
    cost_ratio = total_c / total_b if total_b > 0 else None
    environment_ok = bool(environment["opencv_requirement_satisfied"])
    full_determinism = bool(determinism["full_run_byte_identical"])

    stop_reasons: list[str] = []
    conditional_reasons: list[str] = []
    for fixture in ("f1-translation", "f2-rotation-scale"):
        quality = evaluations.get(fixture, {}).get("quality")
        if quality is None:
            continue
        if not quality["b_control_valid"]:
            stop_reasons.append(f"{fixture.upper()}_B_CONTROL_ABSTAINED")
        if quality["status"] == "STOP":
            stop_reasons.append(f"{fixture.upper()}_QUALITY_STOP")
        elif quality["status"] == "CONDITIONAL":
            conditional_reasons.append(f"{fixture.upper()}_QUALITY_CONDITIONAL")
    for fixture in ("f3-low-texture", "f4-occlusion", "f5-conflicting-anchors"):
        fail_closed = evaluations.get(fixture, {}).get("fail_closed")
        if fail_closed is None:
            continue
        if fail_closed["status"] == "FAIL_OPEN":
            stop_reasons.append(f"{fixture.upper()}_FAIL_OPEN")
        elif fail_closed["status"] == "CONDITIONAL":
            conditional_reasons.append(f"{fixture.upper()}_CONDITIONAL")
        # F3 INCONCLUSIVE is reported in unresolved_limits; the frozen protocol allows
        # GO when F3 is inconclusive, so it is not a conditional reason by itself.
    if not full_determinism:
        stop_reasons.append("FULL_RUN_NONDETERMINISM")

    compensating_gain = False
    if all(
        evaluations.get(fixture, {}).get("quality", {}).get("status") == "PASS"
        for fixture in (
            "f1-translation",
            "f2-rotation-scale",
        )
    ):
        compensating_gain = True
        for fixture in ("f1-translation", "f2-rotation-scale"):
            b_summary = metrics_by_fixture[fixture]["methods"]["B"]["summary"]
            c_summary = metrics_by_fixture[fixture]["methods"]["C"]["summary"]
            b_rmse = b_summary["mean_group_vertex_rmse_px"]
            c_rmse = c_summary["mean_group_vertex_rmse_px"]
            if b_rmse is None or c_rmse is None or c_rmse > 0.75 * b_rmse:
                compensating_gain = False
    if cost_ratio is not None and cost_ratio > 1.5 and not compensating_gain:
        stop_reasons.append("COST_ABOVE_1_5_WITHOUT_QUALITY_GAIN")
    elif cost_ratio is not None and cost_ratio > 1.0:
        conditional_reasons.append("COST_ABOVE_1_0")
    if not environment_ok:
        conditional_reasons.append("ENVIRONMENT_MISMATCH")

    go_gates = {
        "F1_QUALITY": evaluations.get("f1-translation", {}).get("quality", {}).get("status")
        == "PASS",
        "F2_QUALITY": evaluations.get("f2-rotation-scale", {}).get("quality", {}).get("status")
        == "PASS",
        "F3_FAIL_CLOSED": evaluations.get("f3-low-texture", {}).get("fail_closed", {}).get("status")
        in {"PASS", "INCONCLUSIVE"},
        "F4_FAIL_CLOSED": evaluations.get("f4-occlusion", {}).get("fail_closed", {}).get("status")
        == "PASS",
        "F5_FAIL_CLOSED": evaluations.get("f5-conflicting-anchors", {})
        .get("fail_closed", {})
        .get("status")
        == "PASS",
        "B_CONTROL": all(
            evaluations.get(fixture, {}).get("quality", {}).get("b_control_valid")
            for fixture in ("f1-translation", "f2-rotation-scale")
        ),
        "FULL_DETERMINISM": full_determinism,
        "ENVIRONMENT": environment_ok,
        "COST": cost_ratio is not None and cost_ratio <= 1.0,
    }
    if stop_reasons:
        outcome = "STOP"
    elif all(go_gates.values()):
        outcome = "GO"
    else:
        outcome = "CONDITIONAL"
        for gate, passed in go_gates.items():
            if not passed:
                conditional_reasons.append(f"GO_GATE_{gate}_FAILED")
    return {
        "protocol": thresholds["protocol"],
        "outcome": outcome,
        "stop_reasons": stop_reasons,
        "conditional_reasons": conditional_reasons,
        "go_gates": go_gates,
        "cost_ratio_c_over_b": cost_ratio,
        "compensating_quality_gain": compensating_gain,
        "environment_ok": environment_ok,
        "full_run_byte_identical": full_determinism,
        "fixture_statuses": {
            fixture: {
                "quality": evaluation.get("quality", {}).get("status"),
                "fail_closed": evaluation.get("fail_closed", {}).get("status"),
            }
            for fixture, evaluation in evaluations.items()
        },
        "unresolved_limits": [
            item
            for item in (
                "F3_INCONCLUSIVE"
                if evaluations.get("f3-low-texture", {}).get("fail_closed", {}).get("status")
                == "INCONCLUSIVE"
                else None,
                "F4_ABSTENTION_REASON_DIFFERS"
                if evaluations.get("f4-occlusion", {}).get("fail_closed", {}).get("status")
                == "CONDITIONAL"
                else None,
            )
            if item is not None
        ],
    }


def render_comparison_frames(
    raw_b: dict[str, Any],
    raw_c: dict[str, Any],
    frames: list[Any],
    gt: dict[str, Any],
) -> list[Any]:
    rendered = []
    colors = {
        "source": (210, 210, 210),
        "gt": (255, 220, 120),
        "B": (60, 220, 80),
        "C": (50, 160, 255),
    }
    for frame_index, source in enumerate(frames):
        gt_polygons = [
            np.rint(np.asarray(member["points"], dtype=np.float64)).astype(np.int32)
            for member in gt["frames"][frame_index]["members"]
        ]
        panels = []
        for label, raw in (("B", raw_b), ("C", raw_c)):
            panel = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
            for points in gt_polygons:
                cv2.polylines(panel, [points], True, colors["gt"], 1, lineType=cv2.LINE_8)
            result = raw["frames"][frame_index]
            if result["status"] == "SUPPORTED":
                for member in result["members"]:
                    points = np.rint(np.asarray(member["points"], dtype=np.float64)).astype(
                        np.int32
                    )
                    cv2.polylines(panel, [points], True, colors[label], 2, lineType=cv2.LINE_8)
            else:
                cv2.putText(
                    panel,
                    f"ABSTAINED  {result.get('reason')}",
                    (12, 52),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    colors[label],
                    2,
                    cv2.LINE_8,
                )
            cv2.putText(
                panel,
                f"{label}  tick={result['tick']}  {result['status']}",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                colors[label],
                2,
                cv2.LINE_8,
            )
            panels.append(panel)
        source_panel = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
        for points in gt_polygons:
            cv2.polylines(source_panel, [points], True, colors["gt"], 1, lineType=cv2.LINE_8)
        cv2.putText(
            source_panel,
            "SOURCE / GT fixture",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            colors["source"],
            2,
            cv2.LINE_8,
        )
        rendered.append(np.concatenate((source_panel, panels[0], panels[1]), axis=1))
    return rendered


def verify_downstream_reproducibility(
    raw_b: dict[str, Any],
    raw_c: dict[str, Any],
    frames: list[Any],
    gt: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    metrics_first = build_metrics(raw_b, raw_c, frames, gt, config)
    metrics_second = build_metrics(raw_b, raw_c, frames, gt, config)
    metrics_identical = runtime.canonical_bytes(metrics_first) == runtime.canonical_bytes(
        metrics_second
    )
    frames_first = render_comparison_frames(raw_b, raw_c, frames, gt)
    frames_second = render_comparison_frames(raw_b, raw_c, frames, gt)
    hashes_first = [runtime.sha256_bytes(frame.tobytes()) for frame in frames_first]
    hashes_second = [runtime.sha256_bytes(frame.tobytes()) for frame in frames_second]
    with tempfile.TemporaryDirectory(prefix="svm-t2-repro-") as directory:
        first_path = Path(directory) / "first.avi"
        second_path = Path(directory) / "second.avi"
        t1.write_video(first_path, frames_first)
        t1.write_video(second_path, frames_second)
        container_identical = first_path.read_bytes() == second_path.read_bytes()
        decoded_identical = t1.decoded_video_frame_hashes(
            first_path
        ) == t1.decoded_video_frame_hashes(second_path)
    report = {
        "schema_version": REPRO_SCHEMA,
        "artifact_classification": runtime.CLASSIFICATION,
        "scope": (
            "frozen raw experimental outputs to deterministic metrics and comparison rendering"
        ),
        "metrics_canonical_bytes_identical": metrics_identical,
        "comparison_frame_hashes_identical": hashes_first == hashes_second,
        "comparison_video_container_bytes_identical": container_identical,
        "comparison_video_decoded_frames_identical": decoded_identical,
        "comparison_frame_hashes": hashes_first,
    }
    report["passed"] = all(
        (
            report["metrics_canonical_bytes_identical"],
            report["comparison_frame_hashes_identical"],
            report["comparison_video_decoded_frames_identical"],
        )
    )
    return report
