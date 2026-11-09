"""Score a completed frame run against separate synthetic evaluation inputs."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .sequence import (
    FRAME_COUNT,
    HEIGHT,
    WIDTH,
    digest,
    load_masks,
    load_sequence,
    verify_records,
    write_json,
)


def _pair(before: float, after: float) -> dict:
    return {
        "before": float(before),
        "after": float(after),
        "relative_reduction": float(1 - after / before) if before > 0 else None,
    }


def _masked_pair(before: np.ndarray, after: np.ndarray, support: np.ndarray) -> dict | None:
    if not support.any():
        return None
    return _pair(float(before[support].mean()), float(after[support].mean()))


def _gradient(frames: np.ndarray) -> np.ndarray:
    luminance = frames @ np.array([0.2126, 0.7152, 0.0722])
    dx = np.diff(luminance, axis=2, append=luminance[:, :, -1:])
    dy = np.diff(luminance, axis=1, append=luminance[:, -1:, :])
    return np.hypot(dx, dy)


def evaluate(run: Path, mask_path: Path, evaluation: Path) -> None:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    original, original_records = load_sequence(run / "frames-original")
    repaired, repaired_records = load_sequence(run / "frames-repaired")
    masks, mask_records = load_masks(mask_path)
    verify_records(original_records, manifest["frames_original"], "original")
    verify_records(repaired_records, manifest["frames_repaired"], "repaired")
    for name, records in mask_records.items():
        verify_records(records, manifest["masks"][name], name)
    clean, clean_records = load_sequence(evaluation / "clean")
    edges, edge_records = load_sequence(evaluation / "edge", mask=True)
    interior, interior_records = load_sequence(evaluation / "interior", mask=True)
    fixture_data = (evaluation / "fixture.json").read_bytes()
    fixture = json.loads(fixture_data)
    x0, y0, x1, y1 = fixture["regions"]["appearance_xyxy"]
    if not (0 <= x0 < x1 <= WIDTH and 0 <= y0 < y1 <= HEIGHT):
        raise ValueError("static scoring rectangle is outside the frame or empty")
    static = (slice(None), slice(y0, y1), slice(x0, x1))
    if not masks["roi"][static].all() or np.any((edges | interior)[static]):
        raise ValueError("static scoring rectangle must be inside the ROI and away from the object")
    if not all(np.any(region, axis=(1, 2)).all() for region in (edges, interior)):
        raise ValueError("motion scoring masks must have support in every frame")

    before = np.abs(original.astype(np.int16) - clean)
    after = np.abs(repaired.astype(np.int16) - clean)
    patch_error = [errors[static].mean(axis=(1, 2, 3)) for errors in (before, after)]
    patch_delta = [np.abs(np.diff(errors)) for errors in patch_error]
    patch_luma_std = [
        (frames[static] @ np.array([0.2126, 0.7152, 0.0722])).mean(axis=(1, 2)).std()
        for frames in (original, repaired)
    ]
    object_std = [
        np.stack([frame[area].mean(axis=0) for frame, area in zip(frames, interior, strict=True)])
        .std(axis=0)
        .mean()
        for frames in (original, repaired)
    ]
    gradients = [float(_gradient(frames)[edges].mean()) for frames in (original, repaired, clean)]
    motion = np.array(fixture["scene"]["target_center_xy_by_frame"])
    if motion.shape != (FRAME_COUNT, 2):
        raise ValueError("fixture motion center sequence has invalid shape")
    metrics["evaluation"] = {
        "status": "scored",
        "unit": "8-bit code values (DN) unless specified otherwise",
        "fixture_sha256": digest(fixture_data),
        "clean_frames": clean_records,
        "motion_edge_masks": edge_records,
        "object_interior_masks": interior_records,
        "full_frame_rgb_mae_dn": _pair(before.mean(), after.mean()),
        "roi_rgb_mae_dn": _masked_pair(before, after, masks["roi"]),
        "local_defect_rgb_mae_dn": _masked_pair(before, after, masks["defect"]),
        "ghost_rgb_residual_above_1_dn": _masked_pair(
            np.maximum(before - 1, 0), np.maximum(after - 1, 0), masks["ghost"]
        ),
        "flicker_static_patch_mean_luma_temporal_std_dn": _pair(*patch_luma_std),
        "flicker_static_patch_temporal_rgb_mae_delta_dn": {
            **_pair(patch_delta[0].mean(), patch_delta[1].mean()),
            "max_step_before": float(patch_delta[0].max()),
            "max_step_after": float(patch_delta[1].max()),
            "per_frame_rgb_mae_before": patch_error[0].tolist(),
            "per_frame_rgb_mae_after": patch_error[1].tolist(),
        },
        "appearance_object_mean_rgb_temporal_std_dn": _pair(*object_std),
        "appearance_object_interior_rgb_mae_dn": _masked_pair(before, after, interior),
        "motion_edge_rgb_mae_dn": _masked_pair(before, after, edges),
        "motion_edge_gradient_mean_dn_per_px": dict(
            zip(("before", "after", "clean"), gradients, strict=True)
        ),
        "motion_edge_gradient_after_over_clean": gradients[1] / gradients[2]
        if gradients[2]
        else None,
        "reference_motion_displacement_px": (motion[-1] - motion[0]).tolist(),
        "outside_roi_max_abs_rgb_difference_dn": int(
            np.abs(repaired.astype(np.int16) - original)[~masks["roi"]].max(initial=0)
        ),
    }
    write_json(run / "metrics.json", metrics)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    args = parser.parse_args()
    try:
        evaluate(args.run, args.mask, args.evaluation)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
