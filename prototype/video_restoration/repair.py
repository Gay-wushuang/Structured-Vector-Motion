"""Conservative restoration of masked defects in fixed-camera RGB8 sequences."""

from itertools import groupby

import cv2
import numpy as np

PARAMETERS = {
    "stable_min_frames": 5,
    "stable_min_pixels": 64,
    "stable_max_residual_p95_dn": 2,
    "flicker_max_offset_dn": 20,
    "flicker_max_same_sign_run": 2,
    "donor_min_frames": 6,
    "donor_min_available_fraction": 0.67,
    "donor_tolerance_dn": 2,
    "ghost_max_residual_dn": 80,
    "ghost_max_local_range_dn": 100,
    "defect_max_pixels": 256,
    "defect_context_radius_px": 2,
    "defect_min_context_pixels": 12,
    "defect_min_context_fraction": 0.9,
}


def _count(mask: np.ndarray) -> int:
    return int(np.count_nonzero(mask))


def _flicker(
    frames: np.ndarray, roi: np.ndarray, stable: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    # A single trusted patch must be available throughout the shot. Never fit
    # against the edited area or substitute a frame-dependent fitting region.
    patch = np.all(stable & ~roi, axis=0)
    samples = frames[:, patch].astype(np.int16)
    reference = np.median(samples, axis=0)
    normalized = frames.copy()
    usable = np.zeros(roi.shape, dtype=bool)
    reliable = np.zeros(len(frames), dtype=bool)
    offset_signs = np.zeros(len(frames), dtype=np.int8)
    reports = []
    for index, frame in enumerate(frames):
        differences = samples[index] - reference
        stable_unclipped = np.all((samples[index] > 0) & (samples[index] < 255), axis=1)
        stable_count = _count(stable_unclipped)
        report = {
            "status": "refused",
            "reason": None,
            "offset_dn": None,
            "stable_pixels": stable_count,
            "stable_residual_p95_dn": None,
            "changed_pixels": 0,
            "refused_pixels": _count(roi[index]),
        }
        reports.append(report)
        if len(frames) < PARAMETERS["stable_min_frames"] or (
            stable_count < PARAMETERS["stable_min_pixels"]
        ):
            report["reason"] = "insufficient_stable_patch_support"
            continue
        differences = differences[stable_unclipped]
        offset = int(np.rint(np.median(differences)))
        residual = np.max(np.abs(differences - offset), axis=1)
        residual_p95 = float(np.percentile(residual, 95))
        report["offset_dn"] = offset
        report["stable_residual_p95_dn"] = residual_p95
        if abs(offset) > PARAMETERS["flicker_max_offset_dn"]:
            report["reason"] = "offset_out_of_range"
            continue
        if residual_p95 > PARAMETERS["stable_max_residual_p95_dn"]:
            report["reason"] = "non_additive_or_unstable_patch"
            continue

        corrected = frame.astype(np.int16) - offset
        safe = np.all((frame > 0) & (frame < 255) & (corrected >= 0) & (corrected <= 255), axis=2)
        normalized[index, safe] = corrected[safe]
        usable[index] = safe
        reliable[index] = True
        offset_signs[index] = np.sign(offset)
        changed = _count(safe & roi[index]) if offset else 0
        refused = _count(~safe & roi[index]) if offset else 0
        if refused:
            report["reason"] = "clipped_or_out_of_range_pixels"
        report["status"] = (
            ("partial" if changed else "refused")
            if refused
            else ("applied" if changed else "unchanged")
        )
        report["changed_pixels"] = changed
        report["refused_pixels"] = refused

    # A sustained brightness shift could be an intentional fade or lighting
    # change. Do not flatten that shot or use it as a stationary donor pool.
    if any(
        sign and sum(1 for _ in run) > PARAMETERS["flicker_max_same_sign_run"]
        for sign, run in groupby(offset_signs)
    ):
        for index in np.flatnonzero(reliable):
            reports[index].update(
                status="refused",
                reason="sustained_brightness_change",
                changed_pixels=0,
                refused_pixels=_count(roi[index]),
            )
        return frames.copy(), np.zeros_like(usable), np.zeros_like(reliable), reports
    return normalized, usable, reliable, reports


def _stationary_donors(
    normalized: np.ndarray, usable: np.ndarray, suspect: np.ndarray, needed: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    donors = np.zeros_like(normalized[0])
    supported = np.zeros(needed.shape, dtype=bool)
    if not needed.any():
        return donors, supported
    samples = normalized[:, needed].astype(np.int16)
    available = (usable & ~suspect)[:, needed]
    masked = np.ma.array(samples, mask=np.broadcast_to(~available[..., None], samples.shape))
    centers = np.ma.median(masked, axis=0).filled(0)
    distance = np.max(np.abs(samples - centers), axis=2)
    agrees = available & (distance <= PARAMETERS["donor_tolerance_dn"])
    count = np.count_nonzero(agrees, axis=0)
    # Require a strict majority of the whole shot as well as agreement among
    # usable samples, so masking or fit failures cannot manufacture consensus.
    supported[needed] = (
        (count >= PARAMETERS["donor_min_frames"])
        & (count > len(normalized) // 2)
        & (count >= PARAMETERS["donor_min_available_fraction"] * available.sum(axis=0))
    )
    # Choose the closest actual observation. The temporal median is only an
    # agreement test, not a blended frame or a new RGB triplet.
    donor_index = np.argmin(np.where(agrees, distance, 256), axis=0)
    donors[needed] = samples[donor_index, np.arange(samples.shape[1])]
    return donors, supported


def _result(
    requested: np.ndarray, resolved: np.ndarray, changed: int, reasons: dict[str, int]
) -> dict:
    requested_count = _count(requested)
    refused = requested_count - _count(resolved)
    status = "not_requested"
    if requested_count:
        status = "refused" if refused == requested_count else "partial" if refused else "applied"
    return {
        "status": status,
        "requested_pixels": requested_count,
        "changed_pixels": changed,
        "refused_pixels": refused,
        "refusal_reasons": {reason: count for reason, count in reasons.items() if count},
    }


def _refused(requested: np.ndarray, reason: str) -> dict:
    return _result(requested, np.zeros_like(requested), 0, {reason: _count(requested)})


def _ghost(
    output: np.ndarray,
    normalized: np.ndarray,
    usable: np.ndarray,
    requested: np.ndarray,
    donors: np.ndarray,
    supported: np.ndarray,
) -> dict:
    candidates = requested & supported
    if not candidates.any():
        return _refused(requested, "insufficient_stationary_donors")

    residual = np.max(np.abs(normalized.astype(np.int16) - donors), axis=2)
    kernel = np.ones((3, 3), dtype=np.uint8)
    local_range = np.max(cv2.dilate(normalized, kernel) - cv2.erode(normalized, kernel), axis=2)
    resembles_ghost = (
        usable
        & (residual <= PARAMETERS["ghost_max_residual_dn"])
        & (local_range <= PARAMETERS["ghost_max_local_range_dn"])
    )
    # A perfect donor match already needs no change, even at a strong edge.
    resolved = candidates & ((residual == 0) | resembles_ghost)
    changes = resolved & (residual != 0)
    output[changes] = donors[changes]
    return _result(
        requested,
        resolved,
        _count(changes),
        {
            "insufficient_stationary_donors": _count(requested & ~supported),
            "strong_edge_large_residual_or_clipping": _count(candidates & ~resolved),
        },
    )


def _defect(
    output: np.ndarray,
    normalized: np.ndarray,
    usable: np.ndarray,
    requested: np.ndarray,
    context: np.ndarray,
    donors: np.ndarray,
    supported: np.ndarray,
) -> dict:
    if not requested.any():
        return _refused(requested, "empty_mask")
    y, x = np.nonzero(requested)
    radius = PARAMETERS["defect_context_radius_px"]
    height, width = requested.shape
    if (
        len(y) > PARAMETERS["defect_max_pixels"]
        or y.min() < radius
        or x.min() < radius
        or y.max() >= height - radius
        or x.max() >= width - radius
    ):
        return _refused(requested, "mask_too_large_or_near_border")
    components, _ = cv2.connectedComponents(requested.astype(np.uint8))
    if components != 2:  # One interior foreground component plus background.
        return _refused(requested, "multiple_defect_components")

    residual = np.max(np.abs(normalized.astype(np.int16) - donors), axis=2)
    agrees = usable & supported & (residual <= PARAMETERS["donor_tolerance_dn"])
    matching_context = _count(context & agrees)
    if matching_context < PARAMETERS["defect_min_context_pixels"] or matching_context < PARAMETERS[
        "defect_min_context_fraction"
    ] * _count(context):
        return _refused(requested, "surroundings_not_verified_static")

    resolved = requested & supported
    changed = _count(np.any(output[resolved] != donors[resolved], axis=1))
    output[resolved] = donors[resolved]
    return _result(
        requested,
        resolved,
        changed,
        {"insufficient_stationary_donors": _count(requested & ~resolved)},
    )


def repair(frames: np.ndarray, masks: dict[str, np.ndarray]) -> tuple[np.ndarray, list[dict]]:
    """Return a new RGB8 sequence and diagnostics for each frame.

    Input validation belongs to the caller. Even when a suspect mask extends
    beyond its authorized ROI, its writable subset is intersected here.
    """
    roi = masks["roi"]
    ghost = masks["ghost"] & roi
    defect = masks["defect"] & roi
    suspect = masks["ghost"] | masks["defect"]
    normalized, usable, reliable, flicker = _flicker(frames, roi, masks["stable"])
    output = frames.copy()
    output[roi] = normalized[roi]

    radius = PARAMETERS["defect_context_radius_px"]
    kernel = np.ones((2 * radius + 1, 2 * radius + 1), dtype=np.uint8)
    context = (
        np.stack([cv2.dilate(mask.astype(np.uint8), kernel).astype(bool) for mask in defect])
        & ~suspect
    )
    donors, supported = _stationary_donors(
        normalized, usable, suspect, np.any(ghost | defect | context, axis=0)
    )
    reports = []
    for index, frame in enumerate(output):
        if reliable[index]:
            ghost_report = _ghost(
                frame, normalized[index], usable[index], ghost[index], donors, supported
            )
            defect_report = _defect(
                frame,
                normalized[index],
                usable[index],
                defect[index],
                context[index],
                donors,
                supported,
            )
        else:
            ghost_report = _refused(ghost[index], "photometric_fit_unreliable")
            defect_report = _refused(defect[index], "photometric_fit_unreliable")
        reports.append(
            {
                "frame": index,
                "flicker": flicker[index],
                "ghost": ghost_report,
                "defect": defect_report,
            }
        )
    return output, reports
