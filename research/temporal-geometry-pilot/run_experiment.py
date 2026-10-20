from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

EXPERIMENT_SCHEMA = "temporal-geometry-ab-experiment-output-0.1"
METRICS_SCHEMA = "temporal-geometry-ab-metrics-0.1"
MANIFEST_SCHEMA = "temporal-geometry-ab-run-manifest-0.1"
REPRO_SCHEMA = "temporal-geometry-ab-reproducibility-0.1"
CLASSIFICATION = "experimental-only-not-svm-evidence"
METHOD_A = "A-per-frame-independent-primitive"
METHOD_B = "B-first-frame-primitive-opencv-lk-propagation"
RUNNER_IDENTITY = "svm-research/temporal-geometry-ab@0.1"


class ExperimentError(RuntimeError):
    """A fail-closed experiment configuration or input error."""


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
        raise ExperimentError(
            'T1 requires only the repository analysis extra: python -m pip install -e ".[analysis]"'
        ) from exc
    return cv2, np


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ExperimentError(f"{name} must be a finite number")
    return result


def load_config(config_path: Path, repo_root: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "experiment_id",
        "artifact_classification",
        "fixture_root",
        "ground_truth",
        "frames",
        "timebase",
        "evaluation_window",
        "frozen_first_frame_geometry",
        "common_budget",
        "method_a_budget",
        "method_b_budget",
        "decision_thresholds",
    }
    if set(config) != required:
        raise ExperimentError("experiment config fields do not match the closed T1 profile")
    if config["schema_version"] != "temporal-geometry-ab-experiment-config-0.1":
        raise ExperimentError("unsupported experiment config schema")
    if config["artifact_classification"] != CLASSIFICATION:
        raise ExperimentError("experiment output must be classified as non-SVM evidence")
    frames = config["frames"]
    if not isinstance(frames, list) or len(frames) < 2:
        raise ExperimentError("evaluation window requires at least two frames")
    expected_indices = list(range(len(frames)))
    if [frame.get("index") for frame in frames] != expected_indices:
        raise ExperimentError("frame indices must be contiguous and ordered")
    fixture_root = (repo_root / config["fixture_root"]).resolve()
    if repo_root.resolve() not in fixture_root.parents:
        raise ExperimentError("fixture root must remain inside the repository")
    if not fixture_root.is_dir():
        raise ExperimentError(f"fixture root does not exist: {fixture_root}")
    first_points = config["frozen_first_frame_geometry"].get("points")
    if not isinstance(first_points, list) or len(first_points) != config["common_budget"].get(
        "vertices_per_primitive"
    ):
        raise ExperimentError("frozen first-frame geometry violates the vertex budget")
    for point_index, point in enumerate(first_points):
        if not isinstance(point, list) or len(point) != 2:
            raise ExperimentError(f"first-frame point {point_index} must be [x,y]")
        _finite_number(point[0], f"first-frame point {point_index}.x")
        _finite_number(point[1], f"first-frame point {point_index}.y")
    return config


def load_inputs(
    config: dict[str, Any], repo_root: Path
) -> tuple[list[Any], list[list[list[float]]]]:
    cv2, _ = _opencv()
    fixture_root = repo_root / config["fixture_root"]
    ground_truth_path = fixture_root / config["ground_truth"]
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    canvas = tuple(config["common_budget"]["canvas"])
    frames: list[Any] = []
    gt_polygons: list[list[list[float]]] = []
    for entry in config["frames"]:
        path = fixture_root / entry["path"]
        frame = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if frame is None:
            raise ExperimentError(f"cannot decode input frame: {path}")
        if (int(frame.shape[1]), int(frame.shape[0])) != canvas:
            raise ExperimentError(f"input canvas mismatch: {path}")
        unique = set(int(value) for value in _opencv()[1].unique(frame))
        if not unique.issubset({0, 255}) or unique != {0, 255}:
            raise ExperimentError(f"input is not the controlled flat/solid profile: {path}")
        gt_entry = ground_truth.get(entry["ground_truth_key"])
        if not isinstance(gt_entry, dict) or "points" not in gt_entry:
            raise ExperimentError(f"missing ground truth for {entry['ground_truth_key']}")
        points = [
            [_finite_number(value, "ground-truth coordinate") for value in point]
            for point in gt_entry["points"]
        ]
        if len(points) != config["common_budget"]["vertices_per_primitive"]:
            raise ExperimentError("ground truth violates the frozen vertex budget")
        frames.append(frame)
        gt_polygons.append(points)
    frozen = config["frozen_first_frame_geometry"]["points"]
    if frozen != gt_polygons[0]:
        raise ExperimentError("frozen first-frame geometry does not match fixture ground truth")
    return frames, gt_polygons


def polygon_mask(points: Any, shape: tuple[int, int]) -> Any:
    cv2, np = _opencv()
    mask = np.zeros(shape, dtype=np.uint8)
    rounded = np.rint(np.asarray(points, dtype=np.float64)).astype(np.int32)
    cv2.fillPoly(mask, [rounded], 255, lineType=cv2.LINE_8)
    return mask


def mask_iou(left: Any, right: Any) -> float:
    _, np = _opencv()
    left_on = left != 0
    right_on = right != 0
    union = int(np.count_nonzero(left_on | right_on))
    if union == 0:
        return 1.0
    return float(np.count_nonzero(left_on & right_on) / union)


def _canonical_polygon(points: Any) -> Any:
    _, np = _opencv()
    polygon = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    area2 = float(
        np.sum(
            polygon[:, 0] * np.roll(polygon[:, 1], -1) - np.roll(polygon[:, 0], -1) * polygon[:, 1]
        )
    )
    if area2 < 0:
        polygon = polygon[::-1]
    start = min(
        range(len(polygon)), key=lambda index: (float(polygon[index, 1]), float(polygon[index, 0]))
    )
    return np.roll(polygon, -start, axis=0)


def fit_independent_polygon(frame: Any, config: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    cv2, np = _opencv()
    threshold = int(config["common_budget"]["foreground_grayscale_max"])
    foreground = np.where(frame <= threshold, 255, 0).astype(np.uint8)
    contours, hierarchy = cv2.findContours(foreground, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None or len(contours) != 1:
        raise ExperimentError("A abstains: expected exactly one hole-free contour")
    contour = contours[0]
    if float(cv2.contourArea(contour)) <= 0:
        raise ExperimentError("A abstains: degenerate contour")
    target_vertices = int(config["common_budget"]["vertices_per_primitive"])
    epsilons = config["method_a_budget"]["candidate_epsilon_pixels"]
    max_evaluations = int(config["method_a_budget"]["max_candidate_evaluations_per_fitted_frame"])
    if len(epsilons) != max_evaluations:
        raise ExperimentError("A budget does not match the fixed candidate schedule")
    candidates: list[tuple[float, float, Any]] = []
    for epsilon_value in epsilons:
        epsilon = _finite_number(epsilon_value, "candidate epsilon")
        candidate = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(candidate) != target_vertices:
            continue
        candidate = _canonical_polygon(candidate)
        error = 1.0 - mask_iou(polygon_mask(candidate, frame.shape), foreground)
        candidates.append((error, epsilon, candidate))
    if not candidates:
        raise ExperimentError("A abstains: no candidate satisfies the primitive vertex budget")
    error, epsilon, best = min(candidates, key=lambda item: (item[0], item[1], item[2].tolist()))
    return best, {
        "candidate_evaluations": max_evaluations,
        "eligible_candidates": len(candidates),
        "selected_epsilon_pixels": epsilon,
        "objective_mask_error": error,
    }


def _sample_polygon_boundary(points: Any, spacing: float) -> Any:
    _, np = _opencv()
    polygon = np.asarray(points, dtype=np.float32)
    samples: list[Any] = []
    for start, end in zip(polygon, np.roll(polygon, -1, axis=0), strict=True):
        count = max(1, int(math.ceil(float(np.linalg.norm(end - start)) / spacing)))
        for index in range(count):
            samples.append(start + (end - start) * (index / count))
    return np.asarray(samples, dtype=np.float32)


def run_method_a(frames: list[Any], config: dict[str, Any]) -> dict[str, Any]:
    _, np = _opencv()
    frozen = np.asarray(config["frozen_first_frame_geometry"]["points"], dtype=np.float64)
    output_frames: list[dict[str, Any]] = []
    for frame_index, (entry, frame) in enumerate(zip(config["frames"], frames, strict=True)):
        if frame_index == 0:
            polygon = frozen.copy()
            budget = {"candidate_evaluations": 0, "source": "frozen-first-frame-geometry"}
        else:
            polygon, budget = fit_independent_polygon(frame, config)
        output_frames.append(
            {
                "frame_index": entry["index"],
                "tick": entry["tick"],
                "status": "SUPPORTED",
                "primitive_id": None,
                "points": [[float(x), float(y)] for x, y in polygon],
                "budget_consumed": budget,
            }
        )
    return {
        "schema_version": EXPERIMENT_SCHEMA,
        "artifact_classification": CLASSIFICATION,
        "method": METHOD_A,
        "identity_metrics_applicability": "N/A",
        "identity_metrics_reason": (
            "No independent cross-frame matching evaluation was defined or executed."
        ),
        "frames": output_frames,
    }


def run_method_b(frames: list[Any], config: dict[str, Any]) -> dict[str, Any]:
    cv2, np = _opencv()
    budget = config["method_b_budget"]
    geometry = np.asarray(config["frozen_first_frame_geometry"]["points"], dtype=np.float64)
    tracked = _sample_polygon_boundary(geometry, float(budget["boundary_sample_spacing_pixels"]))
    output_frames: list[dict[str, Any]] = [
        {
            "frame_index": config["frames"][0]["index"],
            "tick": config["frames"][0]["tick"],
            "status": "SUPPORTED",
            "primitive_id": "experimental-propagated-primitive:0",
            "points": [[float(x), float(y)] for x, y in geometry],
            "flow": None,
        }
    ]
    for frame_index in range(1, len(frames)):
        next_points, status, lk_error = cv2.calcOpticalFlowPyrLK(
            frames[frame_index - 1],
            frames[frame_index],
            tracked.reshape(-1, 1, 2),
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
        entry = config["frames"][frame_index]
        if next_points is None or status is None or lk_error is None:
            output_frames.append(
                {
                    "frame_index": entry["index"],
                    "tick": entry["tick"],
                    "status": "ABSTAINED",
                    "reason": "LK_NO_RESULT",
                }
            )
            break
        next_flat = next_points.reshape(-1, 2)
        valid = status.reshape(-1) == 1
        valid_count = int(np.count_nonzero(valid))
        valid_ratio = float(valid_count / len(valid))
        if valid_count < int(budget["minimum_valid_track_count"]) or valid_ratio < float(
            budget["minimum_valid_track_ratio"]
        ):
            output_frames.append(
                {
                    "frame_index": entry["index"],
                    "tick": entry["tick"],
                    "status": "ABSTAINED",
                    "reason": "INSUFFICIENT_VALID_LK_TRACKS",
                    "flow": {"valid_track_count": valid_count, "valid_track_ratio": valid_ratio},
                }
            )
            break
        transform, inliers = cv2.estimateAffinePartial2D(
            tracked[valid],
            next_flat[valid],
            method=cv2.LMEDS,
            refineIters=int(budget["affine_refine_iterations"]),
        )
        if transform is None or not np.isfinite(transform).all():
            output_frames.append(
                {
                    "frame_index": entry["index"],
                    "tick": entry["tick"],
                    "status": "ABSTAINED",
                    "reason": "AFFINE_FIT_FAILED",
                }
            )
            break
        geometry = (
            np.column_stack((geometry, np.ones(len(geometry), dtype=np.float64))) @ transform.T
        )
        predicted = (
            np.column_stack((tracked[valid], np.ones(valid_count, dtype=np.float32))) @ transform.T
        )
        residuals = np.linalg.norm(predicted - next_flat[valid], axis=1)
        tracked = next_flat
        inlier_count = valid_count if inliers is None else int(np.count_nonzero(inliers))
        output_frames.append(
            {
                "frame_index": entry["index"],
                "tick": entry["tick"],
                "status": "SUPPORTED",
                "primitive_id": "experimental-propagated-primitive:0",
                "points": [[float(x), float(y)] for x, y in geometry],
                "flow": {
                    "valid_track_count": valid_count,
                    "valid_track_ratio": valid_ratio,
                    "inlier_count": inlier_count,
                    "median_lk_error": float(np.median(lk_error.reshape(-1)[valid])),
                    "median_affine_residual_px": float(np.median(residuals)),
                    "step_affine": [[float(value) for value in row] for row in transform],
                },
            }
        )
    for frame_index in range(len(output_frames), len(frames)):
        entry = config["frames"][frame_index]
        output_frames.append(
            {
                "frame_index": entry["index"],
                "tick": entry["tick"],
                "status": "ABSTAINED",
                "reason": "PREVIOUS_TRANSITION_ABSTAINED",
            }
        )
    return {
        "schema_version": EXPERIMENT_SCHEMA,
        "artifact_classification": CLASSIFICATION,
        "method": METHOD_B,
        "identity_metrics_applicability": "diagnostic-only",
        "identity_metrics_reason": (
            "A fixed experimental label is propagated by construction; this is not SVM "
            "TemporalIdentity evidence."
        ),
        "frames": output_frames,
    }


def _ordered_vertex_rmse(points: Any, ground_truth: Any) -> float:
    _, np = _opencv()
    left = np.asarray(points, dtype=np.float64)
    right = np.asarray(ground_truth, dtype=np.float64)
    if left.shape != right.shape:
        return math.nan
    candidates: list[float] = []
    for candidate in (left, left[::-1]):
        for offset in range(len(candidate)):
            delta = np.roll(candidate, offset, axis=0) - right
            candidates.append(float(np.sqrt(np.mean(np.sum(delta * delta, axis=1)))))
    return min(candidates)


def _linear_slope(values: list[float]) -> float:
    _, np = _opencv()
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=np.float64)
    return float(np.polyfit(x, np.asarray(values, dtype=np.float64), 1)[0])


def method_metrics(
    raw: dict[str, Any], frames: list[Any], gt_polygons: list[list[list[float]]]
) -> dict[str, Any]:
    cv2, np = _opencv()
    per_frame: list[dict[str, Any]] = []
    supported_polygons: list[Any | None] = []
    predicted_centroids: list[Any | None] = []
    gt_centroids: list[Any] = []
    for frame, gt, result in zip(frames, gt_polygons, raw["frames"], strict=True):
        if result["status"] != "SUPPORTED":
            per_frame.append(
                {
                    "frame_index": result["frame_index"],
                    "tick": result["tick"],
                    "status": result["status"],
                    "reason": result["reason"],
                }
            )
            supported_polygons.append(None)
            predicted_centroids.append(None)
            gt_centroids.append(np.asarray(gt, dtype=np.float64).mean(axis=0))
            continue
        points = np.asarray(result["points"], dtype=np.float64)
        predicted_mask = polygon_mask(points, frame.shape)
        source_mask = np.where(frame <= 127, 255, 0).astype(np.uint8)
        gt_points = np.asarray(gt, dtype=np.float64)
        predicted_bounds = np.asarray(
            cv2.boundingRect(np.rint(points).astype(np.int32)), dtype=np.float64
        )
        gt_bounds = np.asarray(
            cv2.boundingRect(np.rint(gt_points).astype(np.int32)), dtype=np.float64
        )
        centroid_error = float(np.linalg.norm(points.mean(axis=0) - gt_points.mean(axis=0)))
        entry = {
            "frame_index": result["frame_index"],
            "tick": result["tick"],
            "status": "SUPPORTED",
            "iou": mask_iou(predicted_mask, source_mask),
            "reconstruction_error_one_minus_iou": 1.0 - mask_iou(predicted_mask, source_mask),
            "pixel_mae": float(
                np.mean(np.abs(predicted_mask.astype(np.float64) - source_mask.astype(np.float64)))
                / 255.0
            ),
            "bounds_l2_error_px": float(np.linalg.norm(predicted_bounds - gt_bounds)),
            "centroid_l2_error_px": centroid_error,
            "gt_vertex_rmse_px": _ordered_vertex_rmse(points, gt_points),
        }
        per_frame.append(entry)
        supported_polygons.append(points)
        predicted_centroids.append(points.mean(axis=0))
        gt_centroids.append(gt_points.mean(axis=0))
    reference_predicted_centroid = predicted_centroids[0]
    reference_gt_centroid = gt_centroids[0]
    for entry, predicted_centroid, gt_centroid in zip(
        per_frame, predicted_centroids, gt_centroids, strict=True
    ):
        if (
            entry["status"] != "SUPPORTED"
            or predicted_centroid is None
            or reference_predicted_centroid is None
        ):
            continue
        predicted_motion = predicted_centroid - reference_predicted_centroid
        gt_motion = gt_centroid - reference_gt_centroid
        entry["gt_centroid_motion_error_px"] = float(np.linalg.norm(predicted_motion - gt_motion))
    supported_entries = [entry for entry in per_frame if entry["status"] == "SUPPORTED"]
    abstained = len(per_frame) - len(supported_entries)
    rmse_values = [float(entry["gt_vertex_rmse_px"]) for entry in supported_entries]
    iou_values = [float(entry["iou"]) for entry in supported_entries]
    mae_values = [float(entry["pixel_mae"]) for entry in supported_entries]
    centroid_errors = [float(entry["centroid_l2_error_px"]) for entry in supported_entries]
    gt_motion_errors = [float(entry["gt_centroid_motion_error_px"]) for entry in supported_entries]
    motion_comp_errors: list[float] = []
    transform_vectors: list[Any] = []
    if raw["method"] == METHOD_B:
        for index in range(1, len(raw["frames"])):
            current = raw["frames"][index]
            previous_polygon = supported_polygons[index - 1]
            current_polygon = supported_polygons[index]
            if (
                current["status"] != "SUPPORTED"
                or previous_polygon is None
                or current_polygon is None
            ):
                continue
            transform = np.asarray(current["flow"]["step_affine"], dtype=np.float64)
            predicted = (
                np.column_stack((previous_polygon, np.ones(len(previous_polygon)))) @ transform.T
            )
            current_source_mask = np.where(frames[index] <= 127, 255, 0).astype(np.uint8)
            motion_error = 1.0 - mask_iou(
                polygon_mask(predicted, frames[index].shape), current_source_mask
            )
            motion_comp_errors.append(motion_error)
            per_frame[index]["motion_compensated_temporal_error"] = motion_error
            scale = math.sqrt(float(transform[0, 0] ** 2 + transform[1, 0] ** 2))
            angle = math.atan2(float(transform[1, 0]), float(transform[0, 0]))
            transform_vectors.append(
                np.asarray([transform[0, 2], transform[1, 2], angle, scale], dtype=np.float64)
            )
    jitter_values: list[float] = []
    for index in range(1, len(transform_vectors) - 1):
        jitter_values.append(
            float(
                np.linalg.norm(
                    transform_vectors[index - 1]
                    - 2 * transform_vectors[index]
                    + transform_vectors[index + 1]
                )
            )
        )
    summary: dict[str, Any] = {
        "evaluated_frame_count": len(per_frame),
        "supported_frame_count": len(supported_entries),
        "abstained_frame_count": abstained,
        "abstention_rate": float(abstained / len(per_frame)),
        "mean_iou": float(np.mean(iou_values)) if iou_values else None,
        "iou_stddev": float(np.std(iou_values)) if iou_values else None,
        "mean_pixel_mae": float(np.mean(mae_values)) if mae_values else None,
        "pixel_mae_stddev": float(np.std(mae_values)) if mae_values else None,
        "mean_gt_vertex_rmse_px": float(np.mean(rmse_values)) if rmse_values else None,
        "final_gt_vertex_rmse_px": rmse_values[-1] if rmse_values else None,
        "final_centroid_drift_error_px": centroid_errors[-1] if centroid_errors else None,
        "centroid_drift_error_slope_px_per_frame": _linear_slope(centroid_errors),
        "mean_gt_centroid_motion_error_px": float(np.mean(gt_motion_errors))
        if gt_motion_errors
        else None,
        "final_gt_centroid_motion_error_px": gt_motion_errors[-1] if gt_motion_errors else None,
        "motion_compensated_temporal_error_mean": float(np.mean(motion_comp_errors))
        if motion_comp_errors
        else None,
        "transform_second_difference_jitter_mean": float(np.mean(jitter_values))
        if jitter_values
        else None,
        "visibility_flip_rate": float(abstained / max(1, len(per_frame) - 1)),
    }
    if raw["method"] == METHOD_A:
        summary["identity_switch_count"] = None
        summary["identity_switch_rate"] = None
        summary["idf1_style"] = None
        summary["identity_metrics_applicability"] = "N/A"
        summary["motion_compensated_temporal_error_mean"] = None
        summary["transform_second_difference_jitter_mean"] = None
        summary["visibility_flip_rate"] = None
    else:
        summary["identity_switch_count"] = 0 if abstained == 0 else None
        summary["identity_switch_rate"] = 0.0 if abstained == 0 else None
        summary["idf1_style"] = None
        summary["identity_metrics_applicability"] = (
            "diagnostic fixed-label continuity only; no independent identity evaluation"
        )
    return {"method": raw["method"], "per_frame": per_frame, "summary": summary}


def build_metrics(
    raw_a: dict[str, Any],
    raw_b: dict[str, Any],
    frames: list[Any],
    gt_polygons: list[list[list[float]]],
    config: dict[str, Any],
) -> dict[str, Any]:
    metrics_a = method_metrics(raw_a, frames, gt_polygons)
    metrics_b = method_metrics(raw_b, frames, gt_polygons)
    placeholder = {
        "schema_version": METRICS_SCHEMA,
        "artifact_classification": CLASSIFICATION,
        "experiment_id": config["experiment_id"],
        "evaluation_window": config["evaluation_window"],
        "method_a": metrics_a,
        "method_b": metrics_b,
    }
    return placeholder


def decide(
    metrics: dict[str, Any],
    reproducible: bool,
    thresholds: dict[str, Any],
    declared_opencv_requirement_satisfied: bool,
) -> dict[str, Any]:
    b = metrics["method_b"]["summary"]
    no_go = thresholds["no_go"]
    go = thresholds["go"]
    no_go_reasons: list[str] = []
    if b["mean_iou"] is None or b["mean_iou"] < no_go["method_b_mean_iou_below"]:
        no_go_reasons.append("METHOD_B_RECONSTRUCTION_BELOW_NO_GO_FLOOR")
    if (
        b["final_gt_vertex_rmse_px"] is None
        or b["final_gt_vertex_rmse_px"] > no_go["method_b_final_gt_vertex_rmse_px_above"]
    ):
        no_go_reasons.append("METHOD_B_FINAL_DRIFT_ABOVE_NO_GO_CEILING")
    if b["abstention_rate"] > no_go["method_b_abstention_rate_above"]:
        no_go_reasons.append("METHOD_B_ABSTENTION_ABOVE_NO_GO_CEILING")
    if no_go["downstream_reproducibility_failure"] and not reproducible:
        no_go_reasons.append("DOWNSTREAM_REPRODUCIBILITY_FAILED")
    if no_go_reasons:
        return {"outcome": "NO-GO", "reasons": no_go_reasons}
    go_checks = {
        "METHOD_B_MEAN_IOU": b["mean_iou"] is not None
        and b["mean_iou"] >= go["method_b_mean_iou_min"],
        "METHOD_B_MEAN_GT_RMSE": b["mean_gt_vertex_rmse_px"] is not None
        and b["mean_gt_vertex_rmse_px"] <= go["method_b_mean_gt_vertex_rmse_px_max"],
        "METHOD_B_FINAL_GT_RMSE": b["final_gt_vertex_rmse_px"] is not None
        and b["final_gt_vertex_rmse_px"] <= go["method_b_final_gt_vertex_rmse_px_max"],
        "METHOD_B_ABSTENTION": b["abstention_rate"] <= go["method_b_abstention_rate_max"],
        "DOWNSTREAM_REPRODUCIBILITY": reproducible or not go["downstream_reproducible_required"],
        "DECLARED_OPENCV_REQUIREMENT": declared_opencv_requirement_satisfied
        or not go["declared_opencv_requirement_required"],
    }
    if all(go_checks.values()):
        return {
            "outcome": "GO",
            "reasons": ["ALL_PREDECLARED_GO_THRESHOLDS_PASSED"],
            "checks": go_checks,
        }
    return {
        "outcome": "CONDITIONAL",
        "reasons": [name for name, passed in go_checks.items() if not passed],
        "checks": go_checks,
    }


def render_comparison_frames(
    raw_a: dict[str, Any], raw_b: dict[str, Any], frames: list[Any]
) -> list[Any]:
    cv2, np = _opencv()
    rendered: list[Any] = []
    colors = {"source": (210, 210, 210), "A": (60, 220, 80), "B": (50, 160, 255)}
    for index, source in enumerate(frames):
        panels: list[Any] = []
        for label, raw in (("A", raw_a), ("B", raw_b)):
            panel = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
            result = raw["frames"][index]
            if result["status"] == "SUPPORTED":
                points = np.rint(np.asarray(result["points"], dtype=np.float64)).astype(np.int32)
                cv2.polylines(panel, [points], True, colors[label], 2, lineType=cv2.LINE_8)
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


def write_video(path: Path, frames: list[Any], fps: float = 2.0) -> None:
    cv2, _ = _opencv()
    if not frames:
        raise ExperimentError("cannot render an empty comparison video")
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), fps, (width, height), True)
    if not writer.isOpened():
        raise ExperimentError("OpenCV FFV1 video writer is unavailable")
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()


def decoded_video_frame_hashes(path: Path) -> list[str]:
    cv2, _ = _opencv()
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    hashes: list[str] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            hashes.append(sha256_bytes(frame.tobytes()))
    finally:
        capture.release()
    return hashes


def verify_downstream_reproducibility(
    raw_a: dict[str, Any],
    raw_b: dict[str, Any],
    frames: list[Any],
    gt_polygons: list[list[list[float]]],
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    metrics_first = build_metrics(raw_a, raw_b, frames, gt_polygons, config)
    metrics_second = build_metrics(raw_a, raw_b, frames, gt_polygons, config)
    metrics_identical = canonical_bytes(metrics_first) == canonical_bytes(metrics_second)
    frames_first = render_comparison_frames(raw_a, raw_b, frames)
    frames_second = render_comparison_frames(raw_a, raw_b, frames)
    frame_hashes_first = [sha256_bytes(frame.tobytes()) for frame in frames_first]
    frame_hashes_second = [sha256_bytes(frame.tobytes()) for frame in frames_second]
    with tempfile.TemporaryDirectory(prefix="svm-t1-repro-") as directory:
        first_path = Path(directory) / "first.avi"
        second_path = Path(directory) / "second.avi"
        write_video(first_path, frames_first)
        write_video(second_path, frames_second)
        video_byte_identical = first_path.read_bytes() == second_path.read_bytes()
        decoded_identical = decoded_video_frame_hashes(first_path) == decoded_video_frame_hashes(
            second_path
        )
    report = {
        "schema_version": REPRO_SCHEMA,
        "artifact_classification": CLASSIFICATION,
        "scope": (
            "frozen raw experimental outputs to deterministic metrics and comparison rendering"
        ),
        "metrics_canonical_bytes_identical": metrics_identical,
        "comparison_frame_hashes_identical": frame_hashes_first == frame_hashes_second,
        "comparison_video_container_bytes_identical": video_byte_identical,
        "comparison_video_decoded_frames_identical": decoded_identical,
        "comparison_frame_hashes": frame_hashes_first,
    }
    report["passed"] = all(
        (
            report["metrics_canonical_bytes_identical"],
            report["comparison_frame_hashes_identical"],
            report["comparison_video_decoded_frames_identical"],
        )
    )
    return report, metrics_first, frames_first


def _peak_rss_bytes() -> int | None:
    if os.name == "nt":
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


def measured_method(
    method: str, frames: list[Any], config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    tracemalloc.start()
    started = time.perf_counter()
    raw = run_method_a(frames, config) if method == "A" else run_method_b(frames, config)
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
            "process peak includes the isolated Python/OpenCV worker; tracemalloc excludes "
            "native OpenCV allocations"
        ),
    }


def _worker_main(method: str, config_path: Path, repo_root: Path) -> int:
    config = load_config(config_path, repo_root)
    frames, _ = load_inputs(config, repo_root)
    raw, cost = measured_method(method, frames, config)
    sys.stdout.buffer.write(canonical_bytes({"raw": raw, "cost": cost}))
    return 0


def run_isolated_worker(
    method: str, config_path: Path, repo_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            method,
            "--config",
            str(config_path),
            "--repo-root",
            str(repo_root),
        ],
        check=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)
    return result["raw"], result["cost"]


def _git_value(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def build_manifest(
    config_path: Path,
    repo_root: Path,
    output_dir: Path,
    config: dict[str, Any],
    costs: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    cv2, np = _opencv()
    fixture_root = repo_root / config["fixture_root"]
    input_paths = [fixture_root / entry["path"] for entry in config["frames"]]
    input_paths.append(fixture_root / config["ground_truth"])
    output_names = [
        "raw/method-a.json",
        "raw/method-b.json",
        "metrics.json",
        "costs.json",
        "reproducibility.json",
        "comparison.avi",
    ]
    branch = _git_value(repo_root, "branch", "--show-current")
    local_head = _git_value(repo_root, "rev-parse", "HEAD")
    remote_default = _git_value(repo_root, "ls-remote", "origin", "HEAD").split()[0]
    remote_branch_lines = _git_value(
        repo_root, "ls-remote", "origin", f"refs/heads/{branch}"
    ).splitlines()
    remote_branch_head = remote_branch_lines[0].split()[0] if remote_branch_lines else None
    return {
        "schema_version": MANIFEST_SCHEMA,
        "artifact_classification": CLASSIFICATION,
        "experiment_id": config["experiment_id"],
        "runner_identity": RUNNER_IDENTITY,
        "repository": {
            "remote": _git_value(repo_root, "remote", "get-url", "origin"),
            "branch": branch,
            "checked_out_head": local_head,
            "remote_branch_head": remote_branch_head,
            "remote_default_head": remote_default,
            "worktree_dirty": bool(_git_value(repo_root, "status", "--porcelain")),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "opencv_declared_analysis_requirement": "opencv-python-headless==4.14.0.94",
            "opencv_requirement_satisfied": cv2.__version__ == "4.14.0",
            "external_models": [],
            "gpu_used": False,
        },
        "fixed_protocol": {
            "config_path": config_path.relative_to(repo_root).as_posix(),
            "config_sha256": sha256_file(config_path),
            "runner_path": Path(__file__).resolve().relative_to(repo_root).as_posix(),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "evaluation_window": config["evaluation_window"],
            "common_budget": config["common_budget"],
            "method_a_budget": config["method_a_budget"],
            "method_b_budget": config["method_b_budget"],
            "decision_thresholds": config["decision_thresholds"],
        },
        "inputs": [
            {
                "path": path.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in input_paths
        ],
        "outputs": [
            {
                "path": name,
                "sha256": sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in output_names
        ],
        "cost_measurements": costs,
        "decision": outcome,
        "authority_statement": (
            "These are offline experimental outputs, not accepted SVM Evidence; no Document, "
            "Revision, Entity, Group, Track, Keyframe, TemporalIdentity, ChangeAuthority, "
            "schema, or frozen spec was modified."
        ),
    }


def run(config_path: Path, repo_root: Path, output_dir: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    config = load_config(config_path, repo_root)
    frames, gt_polygons = load_inputs(config, repo_root)
    raw_a, cost_a = run_isolated_worker("A", config_path, repo_root)
    raw_b, cost_b = run_isolated_worker("B", config_path, repo_root)
    repro, metrics, comparison_frames = verify_downstream_reproducibility(
        raw_a, raw_b, frames, gt_polygons, config
    )
    cv2, _ = _opencv()
    outcome = decide(
        metrics,
        bool(repro["passed"]),
        config["decision_thresholds"],
        cv2.__version__ == "4.14.0",
    )
    metrics["decision"] = outcome
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "raw").mkdir(parents=True, exist_ok=True)
    (output_dir / "raw/method-a.json").write_bytes(pretty_bytes(raw_a))
    (output_dir / "raw/method-b.json").write_bytes(pretty_bytes(raw_b))
    (output_dir / "metrics.json").write_bytes(pretty_bytes(metrics))
    costs = {
        "schema_version": "temporal-geometry-ab-costs-0.1",
        "artifact_classification": CLASSIFICATION,
        "method_a": cost_a,
        "method_b": cost_b,
    }
    (output_dir / "costs.json").write_bytes(pretty_bytes(costs))
    (output_dir / "reproducibility.json").write_bytes(pretty_bytes(repro))
    write_video(output_dir / "comparison.avi", comparison_frames)
    manifest = build_manifest(config_path, repo_root, output_dir, config, costs, outcome)
    (output_dir / "run-manifest.json").write_bytes(pretty_bytes(manifest))
    return {
        "output_dir": str(output_dir),
        "decision": outcome,
        "metrics": metrics,
        "reproducibility": repro,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated T1 temporal geometry A/B experiment"
    )
    default_config = Path(__file__).with_name("experiment.json")
    default_repo = Path(__file__).resolve().parents[2]
    default_output = Path(__file__).with_name("runs") / "t1-controlled-raster-ab-v1"
    parser.add_argument("--config", type=Path, default=default_config)
    parser.add_argument("--repo-root", type=Path, default=default_repo)
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--worker", choices=("A", "B"), help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.worker:
            return _worker_main(args.worker, args.config.resolve(), args.repo_root.resolve())
        result = run(args.config, args.repo_root, args.output)
    except (ExperimentError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"T1 failed closed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps({"output_dir": result["output_dir"], "decision": result["decision"]}, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
