"""Post-runtime evaluator; ground truth is never passed to the worker."""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np
from pipeline import decode, probe, sha


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.astype(np.float64), b.astype(np.float64)
    scores = []
    for ch in range(3):
        x, y = a[..., ch], b[..., ch]
        mx = cv2.GaussianBlur(x, (11, 11), 1.5)
        my = cv2.GaussianBlur(y, (11, 11), 1.5)
        vx = cv2.GaussianBlur(x * x, (11, 11), 1.5) - mx * mx
        vy = cv2.GaussianBlur(y * y, (11, 11), 1.5) - my * my
        cov = cv2.GaussianBlur(x * y, (11, 11), 1.5) - mx * my
        scores.append(
            np.mean(
                ((2 * mx * my + 6.5025) * (2 * cov + 58.5225))
                / ((mx * mx + my * my + 6.5025) * (vx + vy + 58.5225))
            )
        )
    return float(np.mean(scores))


def evaluate(out: Path, mask_path: Path, gt_path: Path | None, object_path: Path | None) -> None:
    started = time.perf_counter()
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError("missing evaluation mask")
    original = np.load(out / "input_frames.npy", allow_pickle=False)
    gt = np.load(gt_path, allow_pickle=False) if gt_path else None
    objects = np.load(object_path, allow_pickle=False) if object_path else None
    if gt is not None and gt.shape != original.shape:
        raise ValueError("GT shape mismatch")
    if objects is not None and objects.shape != original.shape[:3]:
        raise ValueError("object masks shape mismatch")
    inside = mask > 0
    edge = inside & (cv2.distanceTransform(inside.astype(np.uint8), cv2.DIST_L2, 5) <= 3)
    metrics = {
        "classification": "SYNTHETIC" if gt is not None else "REAL_NO_GT",
        "ground_truth_used_only_after_runtime": gt is not None,
        "methods": {},
    }
    lum_weights = np.array([0.114, 0.587, 0.299])
    for name in ("A_noop", "B_roi_normalization", "C_low_frequency"):
        frames = np.load(out / f"{name}.npy", allow_pickle=False)
        if frames.shape != original.shape:
            raise ValueError("candidate shape mismatch")
        lum = frames.astype(np.float64) @ lum_weights
        roi_medians = [float(np.median(frame[inside])) for frame in lum]
        delta = frames.astype(np.int16) - original.astype(np.int16)
        rec = {
            "roi_luma_median_temporal_std": float(np.std(roi_medians)),
            "roi_color_temporal_std_bgr": np.std(
                np.mean(frames[:, inside].astype(np.float64), axis=1), axis=0
            ).tolist(),
            "outside_roi_preencode_max_abs": int(np.max(np.abs(delta[:, ~inside]))),
            "edge_correction_mae": float(np.mean(np.abs(delta[:, edge]))),
            "mean_roi_correction_mae": float(np.mean(np.abs(delta[:, inside]))),
        }
        if gt is not None:
            diff = frames.astype(np.float64) - gt.astype(np.float64)
            mse = float(np.mean(diff**2))
            rec["psnr_db"] = None if mse == 0 else 10 * np.log10(255**2 / mse)
            rec["ssim"] = float(np.mean([ssim(a, b) for a, b in zip(frames, gt, strict=True)]))
            rec["roi_gt_mae"] = float(np.mean(np.abs(diff[:, inside])))
            rec["roi_color_bias_bgr"] = np.mean(diff[:, inside], axis=(0, 1)).tolist()
            rec["edge_gt_mae"] = float(np.mean(np.abs(diff[:, edge])))
            boundary = cv2.dilate(inside.astype(np.uint8), np.ones((3, 3), np.uint8)) != cv2.erode(
                inside.astype(np.uint8), np.ones((3, 3), np.uint8)
            )
            gradients = []
            for a, b in zip(frames, gt, strict=True):
                difference = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32) - cv2.cvtColor(
                    b, cv2.COLOR_BGR2GRAY
                ).astype(np.float32)
                gx = cv2.Sobel(difference, cv2.CV_32F, 1, 0, ksize=3)
                gy = cv2.Sobel(difference, cv2.CV_32F, 0, 1, ksize=3)
                gradients.append(float(np.mean(np.hypot(gx, gy)[boundary])))
            rec["boundary_gradient_error_vs_gt"] = float(np.mean(gradients))
            texture = []
            shape_iou = []
            for idx, (a, b) in enumerate(zip(frames, gt, strict=True)):
                ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
                gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
                lap_a, lap_b = cv2.Laplacian(ga, cv2.CV_32F), cv2.Laplacian(gb, cv2.CV_32F)
                region = inside if objects is None else inside & (objects[idx] == 0)
                texture.append(float(np.mean(np.abs(lap_a[region] - lap_b[region]))))
                if objects is not None:
                    # Ground-truth silhouette neighborhood; edge preservation is not tracking.
                    obj = objects[idx] > 0
                    dilated = cv2.dilate(obj.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                    ea, eb = cv2.Canny(a, 60, 120) > 0, cv2.Canny(b, 60, 120) > 0
                    union = np.count_nonzero((ea | eb) & dilated)
                    shape_iou.append(
                        float(np.count_nonzero(ea & eb & dilated) / union) if union else 1.0
                    )
            rec["background_texture_laplacian_mae"] = float(np.mean(texture))
            if shape_iou:
                rec["object_edge_iou"] = float(np.mean(shape_iou))
        metrics["methods"][name] = rec
    manifest = json.loads((out / "runtime-manifest.json").read_text(encoding="utf-8"))
    decoded = decode(out / "candidate.mp4", probe(out / "candidate.mp4"))
    selected = np.load(out / f"{manifest['selected_method']}.npy", allow_pickle=False)
    encdiff = np.abs(decoded.astype(np.int16) - selected.astype(np.int16))
    metrics["candidate_encoding"] = {
        "mae_all": float(np.mean(encdiff)),
        "outside_roi_mae": float(np.mean(encdiff[:, ~inside])),
        "outside_roi_max_abs": int(np.max(encdiff[:, ~inside])),
    }
    metrics["evaluation_seconds"] = time.perf_counter() - started
    if gt_path:
        metrics["ground_truth_sha256"] = sha(gt_path)
    with (out / "metrics.json").open("x", encoding="utf-8") as stream:
        json.dump(metrics, stream, indent=2, sort_keys=True, allow_nan=False)
