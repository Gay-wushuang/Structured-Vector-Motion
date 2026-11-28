"""Validate local armor proxy motion on the user-provided MP4 without changing it."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from svm.artifacts import ArtifactStore
from svm.cli import _validate_schema
from svm.evaluator import canonical_bytes
from svm.motion import MotionEvaluator
from svm.proposals import GeneratorProvenance, Proposal, ProposalAcceptor
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.revisions import (
    AddKeyframeChange,
    AppendReferencesChange,
    Change,
    CreateTrackChange,
    RevisionStore,
    SetKeyframeValueChange,
    Transaction,
)
from svm.studio import _empty, _shape

from .run import CLASSIFICATION, bounded_read, digest, json_bytes

PROFILE = "svm-armor-translation-validation@0.1"
WIDTH, HEIGHT, FPS = 1280, 720, 24
LABELS = Path(__file__).parent / "armor-validation" / "labels.json"
GENERATOR = GeneratorProvenance("editor:armor-validation", "0.1", "svm-core", PROFILE)
FLOW = {"winSize": (21, 21), "maxLevel": 3}


def decode(path: Path, start: int, stop: int) -> Iterator[tuple[int, np.ndarray]]:
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened() or (
            cap.get(cv2.CAP_PROP_FRAME_WIDTH),
            cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
            cap.get(cv2.CAP_PROP_FPS),
        ) != (WIDTH, HEIGHT, FPS):
            raise ValueError("Expected the recorded 1280×720, 24 fps clip")
        for index in range(stop + 1):
            ok, frame = cap.read()
            if not ok or frame.shape != (HEIGHT, WIDTH, 3) or cap.get(cv2.CAP_PROP_PTS) != index:
                raise ValueError(f"Unexpected decoded frame or presentation timestamp at {index}")
            if index >= start:
                yield index, frame
    finally:
        cap.release()


def measure(anchor: np.ndarray, image: np.ndarray, points: np.ndarray) -> dict[str, Any]:
    moved, valid, _ = cv2.calcOpticalFlowPyrLK(anchor, image, points, None, **FLOW)
    if moved is None or valid is None:
        return {"status": "UNKNOWN"}
    src, dst = points[valid.ravel() == 1], moved[valid.ravel() == 1]
    if not len(src):
        return {"status": "UNKNOWN"}
    returned, back_valid, _ = cv2.calcOpticalFlowPyrLK(image, anchor, dst, None, **FLOW)
    if returned is None or back_valid is None:
        return {"status": "UNKNOWN"}
    kept = (back_valid.ravel() == 1) & (np.linalg.norm((returned - src)[:, 0], axis=1) < 1)
    xy = src[kept, 0]
    displacement = dst[kept, 0] - xy
    held_out = np.floor(xy / 24).sum(axis=1).astype(int) % 3 == 0
    fit_count, held_count = int((~held_out).sum()), int(held_out.sum())
    if fit_count < 30 or held_count < 15:
        return {"status": "UNKNOWN", "fit_count": fit_count, "holdout_count": held_count}
    offset = np.median(displacement[~held_out], axis=0)
    stable = np.linalg.norm(displacement[held_out], axis=1)
    residual = np.linalg.norm(displacement[held_out] - offset, axis=1)
    p90 = float(np.quantile(residual, 0.9))
    return {
        "status": "OBSERVED" if p90 <= 2.0 else "UNKNOWN",
        "fit_count": fit_count,
        "holdout_count": held_count,
        "translation_xy_px": [round(float(value), 6) for value in offset],
        "holdout_stationary_median_px": float(np.median(stable)),
        "holdout_translation_median_px": float(np.median(residual)),
        "holdout_translation_p90_px": p90,
    }


def rectangle_bands(mask: np.ndarray, step: int = 4) -> tuple[list[tuple[int, ...]], float]:
    rows = np.flatnonzero(mask.any(axis=1))
    if not rows.size:
        raise ValueError("The anchor polygon has no pixels")
    proxy = np.zeros_like(mask)
    rectangles = []
    for y in range(int(rows[0]), int(rows[-1]) + 1, step):
        height = min(step, int(rows[-1]) - y + 1)
        edges = np.flatnonzero(np.diff(np.pad(mask[y + height // 2], (1, 1))))
        for start, stop in zip(edges[::2], edges[1::2], strict=True):
            x, right = int(start), int(stop)
            rectangles.append((x, y, right - x, height))
            proxy[y : y + height, x:right] = 1
    iou = np.count_nonzero(mask & proxy) / np.count_nonzero(mask | proxy)
    return rectangles, iou


def author(
    source: bytes, labels: dict[str, Any], observations: list[dict[str, Any]], mask: np.ndarray
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, Any]]:
    keys = labels["motion_keyframes"]
    box_rects, iou = rectangle_bands(mask)
    if iou < 0.97:
        raise ValueError(f"The authored proxy deviates from the hand-marked polygon: IoU {iou}")
    document = _empty()
    identity = digest(
        canonical_bytes({"profile": PROFILE, "source": digest(source), "labels": labels})
    )
    document["document_id"] = f"document:studio-authored-armor-{identity[:12]}"
    artifacts = ArtifactStore()
    reference = artifacts.import_bytes(source, media_type="video/mp4").document_reference()
    store = RevisionStore.create(document)
    acceptor = ProposalAcceptor()
    base = store.head
    if base is None:
        raise ValueError("The initial document has no revision")
    changes: list[Change] = [AppendReferencesChange((reference,))]
    for index, (x, y, width, height) in enumerate(box_rects):
        name = f"armor-band-{index:03d}"
        changes.append(
            _shape(
                name,
                f"甲片条带 {index + 1}",
                "CreateRectangle",
                {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
                "#8e99be",
            )
        )
        for axis, offset in (("x", x), ("y", y)):
            coordinate = 0 if axis == "x" else 1
            track = f"track:{name}-{axis}"
            changes.append(CreateTrackChange(track, f"op:{name}", axis, FPS))
            changes.extend(
                AddKeyframeChange(
                    track,
                    f"keyframe:{name}-{axis}-{tick}",
                    tick,
                    offset + observations[tick]["translation_xy_px"][coordinate],
                )
                for tick in keys
            )
    original = Proposal(
        f"proposal:armor:{identity}",
        base,
        GENERATOR,
        Transaction(f"transaction:armor:{identity}", tuple(changes), "Author a local armor proxy"),
        required_artifact_ids=(reference["id"],),
    )
    preview = acceptor.validate(store, original, artifacts)
    _validate_schema(preview)
    if store.head != base:
        raise ValueError("Authoring preview changed the active revision")
    created = acceptor.accept(store, original, artifacts)
    if store.get_document(created.revision_id) != preview:
        raise ValueError("Accepted authoring differs from its preview")
    edit_tick, delta = labels["edit"]["tick"], labels["edit"]["delta_x"]
    edited_changes: list[Change] = []
    for track in preview["animation"]["content"]:
        if track["target"]["parameter"] == "x":
            key = next(key for key in track["keyframes"] if key["tick"] == edit_tick)
            edited_changes.append(
                SetKeyframeValueChange(track["id"], key["id"], key["value"] + delta)
            )
    edit = Proposal(
        f"proposal:armor-edit:{identity}",
        created.revision_id,
        GENERATOR,
        Transaction(
            f"transaction:armor-edit:{identity}", tuple(edited_changes), "Shift armor preview"
        ),
    )
    edited = acceptor.validate(store, edit, artifacts)
    if store.head != created.revision_id:
        raise ValueError("Edit preview changed the active revision")
    successor = acceptor.accept(store, edit, artifacts)
    if store.get_document(successor.revision_id) != edited:
        raise ValueError("Accepted edit differs from its preview")
    baseline_motion = MotionEvaluator(preview)
    edited_motion = MotionEvaluator(edited)
    affected = []
    sampling_errors = []
    anchor_x, anchor_y, _, _ = box_rects[0]
    for tick in range(keys[-1] + 1):
        before_ops = baseline_motion.sample_document(tick)["construction"]["operations"]
        after_ops = edited_motion.sample_document(tick)["construction"]["operations"]
        first_band = before_ops[0]["parameters"]
        sampled_offset = np.array([first_band["x"] - anchor_x, first_band["y"] - anchor_y])
        sampling_errors.append(
            float(np.linalg.norm(sampled_offset - observations[tick]["translation_xy_px"]))
        )
        if before_ops != after_ops:
            affected.append(tick)
        for before, after in zip(before_ops, after_ops, strict=True):
            a, b = before["parameters"], after["parameters"]
            if {**a, "x": b["x"]} != b:
                raise ValueError(f"The edit changed a non-horizontal parameter at tick {tick}")
            if tick == edit_tick and abs(b["x"] - a["x"] - delta) >= 1e-6:
                raise ValueError("The edit did not shift every band by the requested distance")
    left, right = keys[keys.index(edit_tick) - 1], keys[keys.index(edit_tick) + 1]
    if affected != list(range(left + 1, right)) or preview["references"] != edited["references"]:
        raise ValueError("The edit exceeded the neighboring keyframes or changed source references")
    renderer = SVGRenderer(
        SVGRenderOptions(width=WIDTH, height=HEIGHT, view_box=(0, 0, WIDTH, HEIGHT))
    )
    original_svg = renderer.render(baseline_motion.evaluate(edit_tick).scene)
    edited_svg = renderer.render(edited_motion.evaluate(edit_tick).scene)
    store.undo()
    if store.head != created.revision_id:
        raise ValueError("Undo did not restore the authored revision")
    reopened = RevisionStore.create(json.loads(json_bytes(edited)))
    undo_scene = MotionEvaluator(store.get_document(created.revision_id)).evaluate(edit_tick).scene
    reload_scene = MotionEvaluator(reopened.get_document(reopened.head)).evaluate(edit_tick).scene
    if renderer.render(undo_scene) != original_svg or renderer.render(reload_scene) != edited_svg:
        raise ValueError("Undo or JSON reload changed the expected SVG bytes")
    return (
        preview,
        edited,
        {"before": original_svg, "after": edited_svg},
        {
            "base_revision": base,
            "authored_revision": created.revision_id,
            "edited_revision": successor.revision_id,
            "edited_document_hash": successor.document_hash,
            "source_artifact_id": reference["id"],
            "rectangles": len(box_rects),
            "tracks": len(preview["animation"]["content"]),
            "proxy_iou_against_anchor_polygon": iou,
            "authored_sample_error_max_px": max(sampling_errors),
            "authored_sample_error_p90_px": float(np.quantile(sampling_errors, 0.9)),
            "edited_ticks_inclusive": [affected[0], affected[-1]],
            "undo_and_json_reload_match_svg": True,
        },
    )


def overlay(image: np.ndarray, polygon: np.ndarray, offset: list[float], color) -> np.ndarray:
    out = image.copy()
    contour = np.round(polygon + np.asarray(offset)).astype(np.int32)
    cv2.polylines(out, [contour], True, color, 2, cv2.LINE_AA)
    return out


def validate(input_file: Path, output: Path) -> dict[str, Any]:
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Use a fresh output directory under an existing parent")
    cv2.setNumThreads(1)
    started = time.perf_counter()
    source = bounded_read(input_file, 32 * 1024 * 1024)
    source_hash = digest(source)
    label_bytes = LABELS.read_bytes()
    labels = json.loads(label_bytes)
    if source_hash != labels["source_sha256"]:
        raise ValueError("Source SHA-256 does not match the annotated armor sample")
    poly = np.asarray(labels["anchor_polygon"], dtype=np.int32)
    mask = np.zeros((HEIGHT, WIDTH), np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    start, stop = labels["source_frame_range"]
    manual = labels["manual_landmarks"]
    edit_tick = labels["edit"]["tick"]
    frames = {}
    observations = []
    iterator = decode(input_file, start, stop)
    try:
        _, first = next(iterator)
        anchor = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
        points = cv2.goodFeaturesToTrack(anchor, 180, 0.005, 5, mask=mask)
        if points is None:
            raise ValueError("No feature points inside the annotated plate")
        frames[0] = first
        observations.append({"tick": 0, "status": "USER_ANCHOR", "translation_xy_px": [0, 0]})
        for index, frame in iterator:
            if str(index) in manual:
                frames[index] = frame
            sample = measure(anchor, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), points)
            observations.append({"tick": index, **sample})
    finally:
        iterator.close()
    unknown = [entry["tick"] for entry in observations if entry["status"] == "UNKNOWN"]
    if unknown:
        raise ValueError(f"Armor track is discontinuous at ticks {unknown}")
    manual_checks = {}
    for frame, marks in manual.items():
        displacement = np.asarray(marks) - np.asarray(manual["0"])
        error = np.linalg.norm(displacement - observations[int(frame)]["translation_xy_px"], axis=1)
        manual_checks[frame] = [float(value) for value in error]
    worst_manual = max(max(values) for values in manual_checks.values())
    if worst_manual > 2:
        raise ValueError(f"Manual landmark disagreement exceeds 2 px: {worst_manual}")
    before, after, svgs, editing = author(source, labels, observations, mask)
    at_edit = observations[edit_tick]["translation_xy_px"]
    original = frames[edit_tick]
    edited_delta = [at_edit[0] + labels["edit"]["delta_x"], at_edit[1]]
    crop = (slice(435, 685), slice(900, 1270))
    panels = [
        ("Source T48", original),
        ("Tracked outline", overlay(original, poly, at_edit, (135, 255, 99))),
        ("Edited outline +24 px", overlay(original, poly, edited_delta, (38, 177, 255))),
    ]
    image = np.full((282, 1110, 3), (32, 38, 45), np.uint8)
    for index, (title, panel) in enumerate(panels):
        image[0:250, index * 370 : (index + 1) * 370] = panel[crop]
        cv2.putText(
            image,
            title,
            (index * 370 + 10, 272),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.56,
            (224, 233, 237),
            1,
            cv2.LINE_AA,
        )
    if digest(bounded_read(input_file, 32 * 1024 * 1024)) != source_hash:
        raise ValueError("Source bytes changed during measurement")
    report = {
        "classification": CLASSIFICATION,
        "profile": PROFILE,
        "source_sha256": source_hash,
        "runtime": {"opencv": cv2.__version__, "numpy": np.__version__},
        "labels_sha256": digest(label_bytes),
        "source_dimensions": [WIDTH, HEIGHT],
        "source_fps": FPS,
        "sampled_frames": len(observations),
        "geometry_check": "hand-marked anchor polygon and sparse manual landmarks",
        "manual_landmark_error_px": manual_checks,
        "manual_landmark_max_px": worst_manual,
        "holdout_p90_max_px": max(
            entry["holdout_translation_p90_px"] for entry in observations[1:]
        ),
        "unknown_ticks": unknown,
        "measurements": observations,
        "editing": editing,
        "elapsed_seconds": time.perf_counter() - started,
    }
    output.mkdir()
    for name, data in {"before": before, "after": after}.items():
        (output / f"{name}.svm.json").write_bytes(json_bytes(data))
        (output / f"{name}.svg").write_text(svgs[name], encoding="utf-8", newline="\n")
    if not cv2.imwrite(str(output / "comparison.png"), image):
        raise ValueError("Could not write the comparison image")
    (output / "report.json").write_bytes(json_bytes(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.input, args.output)
    except (ValueError, OSError, cv2.error) as exc:
        parser.exit(2, f"{exc}\n")
    print(
        json_bytes({key: value for key, value in report.items() if key != "measurements"}).decode()
    )


if __name__ == "__main__":
    main()
