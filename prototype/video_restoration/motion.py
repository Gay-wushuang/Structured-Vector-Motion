"""R1-002 integration: SVM Motion frames -> external rasterizer -> video repair.

Three isolated stages share one run directory:

``source``
    Sample an authored Document through ``MotionEvaluator`` at FINAL quality,
    render SVG, rasterize RGB8 PNG through an external tool, then inject the
    controlled degradations and write the explicit mask bundle plus the offline
    evaluation tree.

``repair``
    Read only ``input/`` and ``mask/``. It never opens ``evaluation/`` or the
    Document, repairs, writes lossless frames, and verifies the exported media.

``evaluate``
    Read the sealed run plus the offline evaluation tree and score the result.

The prototype ``synthetic``/``demo``/``evaluate`` entries stay untouched and
remain the fixed 2-second compatibility path.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from PIL import Image
from PIL import __version__ as pillow_version

from svm import MotionEvaluator
from svm.document import validate_document
from svm.evaluator import EvaluationState, Quality
from svm.motion import MotionFrame
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.scene import EvaluatedScene, EvaluatedStyle

from . import evaluate as scoring
from . import motion_scene as spec
from .media import MediaError, export_media
from .repair import PARAMETERS, repair
from .sequence import digest, load_masks, load_sequence, save_sequence, write_json

SOURCE_PROFILE = "svm-c-r1-motion-source@1"
REPAIR_PROFILE = "svm-c-r1-motion-restoration@1"
CONTRACT_VERSION = "c-video-repair-contract@0.1"
DRAFT_REVISION = "R1-002"
FRAME_NAMES = tuple(f"{index:06d}.png" for index in range(spec.FRAME_COUNT))


def _expand(mask: np.ndarray, radius: int) -> np.ndarray:
    padded = np.pad(mask, radius)
    expanded = np.zeros_like(mask)
    for row in range(2 * radius + 1):
        for column in range(2 * radius + 1):
            expanded |= padded[row : row + spec.HEIGHT, column : column + spec.WIDTH]
    return expanded


def _rectangle(bounds: tuple[int, int, int, int]) -> np.ndarray:
    left, top, right, bottom = bounds
    mask = np.zeros((spec.HEIGHT, spec.WIDTH), dtype=bool)
    mask[top:bottom, left:right] = True
    return mask


def _write_mask(directory: Path, frames: np.ndarray, names: tuple[str, ...]) -> list[dict]:
    directory.mkdir(parents=True)
    records = []
    for tick, (name, frame) in enumerate(zip(names, frames, strict=True)):
        path = directory / name
        Image.fromarray(frame.astype(np.uint8) * 255).save(path, compress_level=6)
        records.append(
            {
                "file": name,
                "tick": tick,
                "sha256": digest(path.read_bytes()),
                "pixel_sha256": digest((frame.astype(np.uint8) * 255).tobytes()),
            }
        )
    return records


def _tool_version(executable: str, flag: str) -> str:
    try:
        process = subprocess.run([executable, flag], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"cannot query {executable}: {error}") from error
    if process.returncode:
        raise ValueError(f"{executable} {flag} exited {process.returncode}")
    return process.stdout.decode(errors="replace").strip().splitlines()[0]


def _rasterize(executable: str, svg: Path, png: Path, *, background: str | None = None) -> None:
    arguments = [executable]
    if background is not None:
        arguments += ["--background", background]
    arguments += [str(svg), str(png)]
    process = subprocess.run(arguments, capture_output=True, timeout=120, check=False)
    if process.returncode:
        raise ValueError(
            f"rasterizer exit {process.returncode}: "
            f"{process.stderr.decode(errors='replace').strip()}"
        )


def _load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        if image.size != (spec.WIDTH, spec.HEIGHT):
            raise ValueError(f"{path}: expected {spec.WIDTH}x{spec.HEIGHT}, got {image.size}")
        if image.mode == "RGBA":
            alpha = np.array(image.getchannel("A"))
            if not np.all(alpha == 255):
                raise ValueError(f"{path}: rasterized frame contains transparency")
            image = image.convert("RGB")
        elif image.mode != "RGB":
            raise ValueError(f"{path}: unexpected rasterizer mode {image.mode}")
        return np.array(image)


def _load_silhouette(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        if image.size != (spec.WIDTH, spec.HEIGHT):
            raise ValueError(f"{path}: expected {spec.WIDTH}x{spec.HEIGHT}, got {image.size}")
        rgb = np.array(image.convert("RGB")).astype(np.int16)
    silhouette = rgb.mean(axis=2) < 128
    if not silhouette.any():
        raise ValueError(f"{path}: empty silhouette")
    return silhouette


def _assert_final(frame: MotionFrame, tick: int) -> None:
    if frame.scene.quality != Quality.FINAL:
        raise ValueError(f"tick {tick}: scene quality is {frame.scene.quality}")
    for operation_id, node in frame.evaluator.runtime.items():
        if node.state != EvaluationState.CLEAN:
            raise ValueError(f"tick {tick}: {operation_id} is {node.state}")
        if node.outputs is None:
            raise ValueError(f"tick {tick}: {operation_id} has no materialized outputs")
        if node.stale_outputs is not None:
            raise ValueError(f"tick {tick}: {operation_id} retains a stale value")
        if node.evaluated_quality != Quality.FINAL:
            raise ValueError(f"tick {tick}: {operation_id} is {node.evaluated_quality}")


def _silhouette_scene(scene: EvaluatedScene) -> EvaluatedScene:
    black = EvaluatedStyle(fill="#000000", stroke="none", stroke_width=0.0, opacity=1.0)
    return replace(
        scene,
        entities=tuple(
            replace(entity, style=black)
            for entity in scene.entities
            if entity.entity_id in spec.MOVING_ENTITIES
        ),
    )


def _centroid(mask: np.ndarray) -> tuple[float, float]:
    y, x = np.nonzero(mask)
    return float(x.mean()), float(y.mean())


def source(
    run: Path,
    *,
    document_path: Path | None,
    resvg: str,
    log: list[str],
) -> int:
    """Sample the authored Document and write the degraded repair input."""
    if run.exists():
        raise ValueError(f"run directory already exists: {run}")
    started = time.perf_counter()
    run.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=run.parent, prefix=".motion-source-") as temporary:
        staging = Path(temporary) / "run"
        staging.mkdir()
        document = (
            json.loads(document_path.read_text(encoding="utf-8"))
            if document_path is not None
            else spec.build_document()
        )
        validate_document(document)
        document_bytes = (json.dumps(document, indent=2) + "\n").encode("utf-8")
        (staging / "document.svm.json").write_bytes(document_bytes)
        motion = MotionEvaluator(document)
        renderer = SVGRenderer(
            SVGRenderOptions(width=spec.WIDTH, height=spec.HEIGHT, view_box=spec.VIEW_BOX)
        )
        svg_dir, mask_svg_dir, raster_dir = (
            staging / "svg",
            staging / "mask-svg",
            staging / ".raster",
        )
        for directory in (svg_dir, mask_svg_dir, raster_dir):
            directory.mkdir()

        frames: list[np.ndarray] = []
        silhouettes: list[np.ndarray] = []
        svg_records: list[dict] = []
        raster_records: list[dict] = []
        for tick in range(spec.FRAME_COUNT):
            frame = motion.evaluate(tick, Quality.FINAL)
            _assert_final(frame, tick)
            svg = renderer.render(frame.scene)
            mask_svg = renderer.render(_silhouette_scene(frame.scene))
            svg_path = svg_dir / f"{tick:06d}.svg"
            mask_svg_path = mask_svg_dir / f"{tick:06d}.svg"
            svg_path.write_text(svg, encoding="utf-8", newline="\n")
            mask_svg_path.write_text(mask_svg, encoding="utf-8", newline="\n")

            raw_png = raster_dir / f"{tick:06d}.png"
            _rasterize(resvg, svg_path, raw_png)
            rgb = _load_rgb(raw_png)
            mask_png = raster_dir / f"mask-{tick:06d}.png"
            _rasterize(resvg, mask_svg_path, mask_png, background="white")
            silhouette = _load_silhouette(mask_png)

            frames.append(rgb)
            silhouettes.append(silhouette)
            svg_records.append(
                {
                    "tick": tick,
                    "seconds": str(Fraction(tick, spec.FPS)),
                    "file": svg_path.name,
                    "sha256": digest(svg.encode("utf-8")),
                    "quality": frame.scene.quality.value,
                    "stale": False,
                }
            )
            raster_records.append(
                {
                    "tick": tick,
                    "file": f"{tick:06d}.png",
                    "sha256": digest(raw_png.read_bytes()),
                    "width": spec.WIDTH,
                    "height": spec.HEIGHT,
                }
            )
        rasterizer_version = _tool_version(resvg, "--version")

        clean = np.stack(frames)
        object_masks = np.stack(silhouettes)
        roi = _rectangle(spec.ROI_XYXY)
        stable = _rectangle(spec.STABLE_XYXY)
        defect_region = _rectangle(spec.DEFECT_XYXY)
        if np.any(stable & roi):
            raise ValueError("stable sample must stay outside the ROI")
        if np.any(object_masks[:, stable]):
            raise ValueError("a moving object crosses the stable sample")
        if np.any(object_masks & ~roi[None]):
            raise ValueError("a moving object crosses the ROI boundary")
        static_patch = (
            slice(spec.STATIC_SCORING_XYXY[1], spec.STATIC_SCORING_XYXY[3]),
            slice(spec.STATIC_SCORING_XYXY[0], spec.STATIC_SCORING_XYXY[2]),
        )
        if np.any(object_masks[:, static_patch[0], static_patch[1]]):
            raise ValueError("a moving object crosses the static scoring patch")
        covered = np.any(np.stack([_expand(mask, 1) for mask in object_masks]), axis=0)
        uncovered = ~covered
        if not np.all(clean[:, uncovered] == clean[0:1, uncovered]):
            raise ValueError("the authored background is not static outside moving objects")

        degraded = clean.astype(np.int16)
        ghost = np.zeros_like(object_masks)
        defect = np.zeros_like(object_masks)
        for index in range(spec.FRAME_COUNT):
            if index in spec.DEFECT_FRAMES:
                defect[index] = defect_region
            ghost[index] = (
                object_masks[index - 1]
                & ~_expand(object_masks[index], spec.GHOST_PROTECTION_RADIUS)
                if index
                else np.zeros_like(roi)
            ) & roi
            ghost[index] &= ~defect[index]
        for index in range(1, spec.FRAME_COUNT):
            selected = ghost[index]
            if selected.any():
                current = clean[index].astype(np.int16)
                previous = clean[index - 1].astype(np.int16)
                blended = (
                    (spec.GHOST_DENOMINATOR - spec.GHOST_NUMERATOR) * current
                    + spec.GHOST_NUMERATOR * previous
                    + spec.GHOST_DENOMINATOR // 2
                ) // spec.GHOST_DENOMINATOR
                degraded[index][selected] = blended[selected]
        rng = np.random.Generator(np.random.PCG64(20261109))
        for index in spec.DEFECT_FRAMES:
            degraded[index][defect_region] = spec.DEFECT_RGB + rng.integers(
                -spec.DEFECT_NOISE,
                spec.DEFECT_NOISE + 1,
                size=(int(defect_region.sum()), 3),
            )
        offsets = np.array(spec.FLICKER_OFFSETS, dtype=np.int16)
        degraded += offsets[:, None, None, None]
        if degraded.min() < 0 or degraded.max() > 255:
            raise ValueError("controlled degradation clipped a frame")
        degraded = degraded.astype(np.uint8)

        edges = np.stack([_expand(mask, 1) & _expand(~mask, 1) for mask in object_masks])
        interior = np.stack([mask & ~_expand(~mask, 2) for mask in object_masks])
        if not all(np.any(region, axis=(1, 2)).all() for region in (edges, interior)):
            raise ValueError("motion evaluation masks must have support in every frame")

        input_records = save_sequence(staging / "input", degraded, names=FRAME_NAMES)
        mask_records = {
            "roi": _write_mask(
                staging / "mask" / "roi",
                np.repeat(roi[None], spec.FRAME_COUNT, axis=0),
                FRAME_NAMES,
            ),
            "stable": _write_mask(
                staging / "mask" / "stable",
                np.repeat(stable[None], spec.FRAME_COUNT, axis=0),
                FRAME_NAMES,
            ),
            "ghost": _write_mask(staging / "mask" / "ghost", ghost, FRAME_NAMES),
            "defect": _write_mask(staging / "mask" / "defect", defect, FRAME_NAMES),
        }
        clean_records = save_sequence(staging / "evaluation" / "clean", clean, names=FRAME_NAMES)
        edge_records = _write_mask(staging / "evaluation" / "edge", edges, FRAME_NAMES)
        interior_records = _write_mask(staging / "evaluation" / "interior", interior, FRAME_NAMES)
        fixture = {
            "generator": "svm-c-r1-motion@1",
            "contract_version": CONTRACT_VERSION,
            "draft_revision": DRAFT_REVISION,
            "document_sha256": digest(document_bytes),
            "width": spec.WIDTH,
            "height": spec.HEIGHT,
            "frame_count": spec.FRAME_COUNT,
            "fps": {"numerator": spec.FPS, "denominator": 1},
            "timebase_ticks_per_second": spec.FPS,
            "regions": {
                "coordinates": "half-open xyxy in source pixels",
                "appearance_xyxy": list(spec.STATIC_SCORING_XYXY),
                "defect_xyxy": list(spec.DEFECT_XYXY),
                "roi_xyxy": list(spec.ROI_XYXY),
                "stable_xyxy": list(spec.STABLE_XYXY),
            },
            "scene": {
                "moving_entities": list(spec.MOVING_ENTITIES),
                "target_center_xy_by_frame": [list(_centroid(mask)) for mask in object_masks],
                "edge_band": "one pixel on each side of the moving silhouette, Chebyshev distance",
                "interior": "moving silhouette eroded by two pixels, Chebyshev distance",
            },
            "injection_order": ["ghost", "defect", "flicker"],
            "ghost": {
                "lag_frames": 1,
                "opacity": {
                    "numerator": spec.GHOST_NUMERATOR,
                    "denominator": spec.GHOST_DENOMINATOR,
                },
                "protection_radius_chebyshev_px": spec.GHOST_PROTECTION_RADIUS,
                "rounding": "nearest integer",
                "support": "prior silhouette outside expanded current silhouette",
            },
            "defect": {
                "frames_zero_based": list(spec.DEFECT_FRAMES),
                "replacement_rgb": list(spec.DEFECT_RGB),
                "noise_inclusive_rgb": [-spec.DEFECT_NOISE, spec.DEFECT_NOISE],
            },
            "flicker": {
                "additive_rgb_offset_by_frame": list(spec.FLICKER_OFFSETS),
                "scope": "full frame",
            },
            "clean_reference_in_input": False,
        }
        write_json(staging / "evaluation" / "fixture.json", fixture)
        shutil.rmtree(raster_dir)

        manifest = {
            "profile": SOURCE_PROFILE,
            "contract_version": CONTRACT_VERSION,
            "draft_revision": DRAFT_REVISION,
            "status": "sourced",
            "scope": "authored SVM Motion ground truth with controlled degradations",
            "document_sha256": digest(document_bytes),
            "width": spec.WIDTH,
            "height": spec.HEIGHT,
            "frame_count": spec.FRAME_COUNT,
            "fps": {"numerator": spec.FPS, "denominator": 1},
            "duration_seconds": str(Fraction(spec.FRAME_COUNT, spec.FPS)),
            "endpoint_rule": "left-closed-right-open",
            "timebase_ticks_per_second": spec.FPS,
            "frame_domain": "ordered RGB8 PNG code values, ticks 0..95",
            "clean_reference_used_by_repair": False,
            "motion": {
                "semantics_version": document["animation"]["semantics_version"],
                "quality": "FINAL",
                "stale_frames": 0,
                "all_operations_clean": True,
                "start_tick": 0,
                "end_tick": spec.FRAME_COUNT - 1,
            },
            "rasterizer": {
                "executable_role": "resvg",
                "version": rasterizer_version,
                "arguments": ["<svg>", "<png>"],
                "mask_background": "white",
                "svg_sha256": [record["sha256"] for record in svg_records],
            },
            "environment": {
                "python": platform.python_version(),
                "opencv": cv2.__version__,
                "numpy": np.__version__,
                "pillow": pillow_version,
                "platform": platform.platform(),
            },
            "frames": [
                {
                    "tick": svg["tick"],
                    "seconds": svg["seconds"],
                    "svg_sha256": svg["sha256"],
                    "png_file": raster["file"],
                    "png_sha256": raster["sha256"],
                    "input_sha256": item["sha256"],
                    "input_pixel_sha256": item["pixel_sha256"],
                    "clean_sha256": clean["sha256"],
                    "clean_pixel_sha256": clean["pixel_sha256"],
                    "edge_sha256": edge["sha256"],
                    "interior_sha256": interior["sha256"],
                    "quality": svg["quality"],
                    "stale": svg["stale"],
                }
                for svg, raster, item, clean, edge, interior in zip(
                    svg_records,
                    raster_records,
                    input_records,
                    clean_records,
                    edge_records,
                    interior_records,
                    strict=True,
                )
            ],
            "inputs": input_records,
            "masks": mask_records,
            "evaluation": {
                "fixture_sha256": digest((staging / "evaluation" / "fixture.json").read_bytes()),
                "clean_frames": clean_records,
                "motion_edge_masks": edge_records,
                "object_interior_masks": interior_records,
            },
            "elapsed_seconds": None,
        }
        manifest["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        write_json(staging / "source-manifest.json", manifest)
        staging.rename(run)

    log.append(f"source: {spec.FRAME_COUNT} frames at {spec.FPS} fps")
    log.append(f"source: rasterizer {_tool_version(resvg, '--version')}")
    log.append(f"source: run {run}")
    return 0


def repair_run(run: Path, *, ffmpeg: str, ffprobe: str, log: list[str]) -> int:
    """Repair and export. This stage never reads ``evaluation/``."""
    started = time.perf_counter()
    source_manifest = json.loads((run / "source-manifest.json").read_text(encoding="utf-8"))
    frames, input_records = load_sequence(
        run / "input", width=spec.WIDTH, height=spec.HEIGHT, names=FRAME_NAMES
    )
    masks, mask_records = load_masks(
        run / "mask", width=spec.WIDTH, height=spec.HEIGHT, names=FRAME_NAMES
    )
    if input_records != source_manifest["inputs"]:
        raise ValueError("input frames differ from the source manifest")
    for role, records in mask_records.items():
        if records != source_manifest["masks"][role]:
            raise ValueError(f"{role} masks differ from the source manifest")
    repaired, reports = repair(frames, masks)
    changed = np.any(repaired != frames, axis=-1)
    outside = int(np.count_nonzero(changed & ~masks["roi"]))
    if outside:
        raise ValueError(f"repair violated ROI authorization ({outside} pixels)")

    frame_status = []
    for index in range(spec.FRAME_COUNT):
        report = reports[index]
        refused = report["ghost"]["refused_pixels"] + report["defect"]["refused_pixels"]
        changed_pixels = int(np.count_nonzero(changed[index]))
        unresolved = refused
        status = "REPAIRED" if changed_pixels else ("UNRESOLVED" if unresolved else "UNCHANGED")
        frame_status.append(
            {
                "index": index,
                "status": status,
                "changed_pixels": changed_pixels,
                "unresolved_pixels": unresolved,
            }
        )

    metrics = {
        "profile": REPAIR_PROFILE,
        "contract_version": CONTRACT_VERSION,
        "draft_revision": DRAFT_REVISION,
        "outside_roi_changed_pixels": outside,
        "inside_roi_changed_pixels": int(np.count_nonzero(changed)),
        "inside_roi_pixels": int(np.count_nonzero(masks["roi"])),
        "refused_frames_by_stage": {
            stage: [
                item["frame"] for item in reports if item[stage]["status"] in {"partial", "refused"}
            ]
            for stage in ("flicker", "ghost", "defect")
        },
        "evaluation": {"status": "not_run"},
    }
    manifest = {
        "profile": REPAIR_PROFILE,
        "contract_version": CONTRACT_VERSION,
        "draft_revision": DRAFT_REVISION,
        "status": "in_progress",
        "scope": "authored SVM Motion ground truth, controlled video repair",
        "clean_reference_used_by_repair": False,
        "document_sha256": source_manifest["document_sha256"],
        "source_manifest_sha256": digest((run / "source-manifest.json").read_bytes()),
        "width": spec.WIDTH,
        "height": spec.HEIGHT,
        "frame_count": spec.FRAME_COUNT,
        "fps": {"numerator": spec.FPS, "denominator": 1},
        "duration_seconds": str(Fraction(spec.FRAME_COUNT, spec.FPS)),
        "timebase_ticks_per_second": spec.FPS,
        "frame_domain": "ordered RGB8 PNG code values, ticks 0..95",
        "write_scope": "ROI only",
        "parameters": PARAMETERS,
        "repair_module_sha256": digest(Path(__file__).with_name("repair.py").read_bytes()),
        "environment": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pillow": pillow_version,
        },
        "inputs": input_records,
        "masks": mask_records,
        "frame_reports": reports,
        "frame_status": frame_status,
        "repair_status": (
            "contains_refusals" if any(metrics["refused_frames_by_stage"].values()) else "processed"
        ),
        "media": {"status": "pending"},
    }
    write_json(run / "run-manifest.json", manifest)
    code = 0
    try:
        manifest["frames_original"] = save_sequence(
            run / "frames-original", frames, names=FRAME_NAMES
        )
        manifest["frames_repaired"] = save_sequence(
            run / "frames-repaired", repaired, names=FRAME_NAMES
        )
        write_json(run / "metrics.json", metrics)
        manifest["media"] = export_media(
            run,
            frames,
            repaired,
            ffmpeg,
            ffprobe,
            fps=spec.FPS,
            frame_count=spec.FRAME_COUNT,
            names=("before.mp4", "after.mp4", "comparison.mp4"),
        )
    except (MediaError, OSError, ValueError) as error:
        code = error.exit_code if isinstance(error, MediaError) else 8
        manifest["media"] = {"status": "failed", "error": str(error)}
        print(error, file=sys.stderr)
    manifest["status"] = (
        "failed"
        if code
        else ("partial" if manifest["repair_status"] == "contains_refusals" else "verified")
    )
    manifest["exit_code"] = code
    manifest["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    write_json(run / "run-manifest.json", manifest)
    log.append(
        f"repair: changed={metrics['inside_roi_changed_pixels']} "
        f"outside_roi={outside} status={manifest['status']} exit={code}"
    )
    if code == 0:
        log.append(f"repair: media {manifest['media']['status']}")
    return code


def evaluate_run(run: Path, *, log: list[str]) -> int:
    started = time.perf_counter()
    scoring.evaluate(
        run,
        run / "mask",
        run / "evaluation",
        width=spec.WIDTH,
        height=spec.HEIGHT,
        frame_count=spec.FRAME_COUNT,
        names=FRAME_NAMES,
        manifest_name="run-manifest.json",
    )
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
    evaluation = metrics["evaluation"]
    metrics["r1_002_headline"] = {
        "A_local_frame_repair": {
            "metric": "local_defect_rgb_mae_dn",
            "values": evaluation["local_defect_rgb_mae_dn"],
        },
        "B_flicker_suppression": {
            "metric": "flicker_static_patch_mean_luma_temporal_std_dn",
            "values": evaluation["flicker_static_patch_mean_luma_temporal_std_dn"],
        },
        "C_ghost_improvement": {
            "metric": "ghost_rgb_residual_above_1_dn",
            "values": evaluation["ghost_rgb_residual_above_1_dn"],
        },
        "D_appearance_stability": {
            "metric": "appearance_object_mean_rgb_temporal_std_dn",
            "values": evaluation["appearance_object_mean_rgb_temporal_std_dn"],
            "clean_temporal_std_dn": evaluation["appearance_object_mean_rgb_temporal_std_clean_dn"],
            "motion_edge_rgb_mae_dn": evaluation["motion_edge_rgb_mae_dn"],
            "motion_edge_gradient_after_over_clean": evaluation[
                "motion_edge_gradient_after_over_clean"
            ],
        },
    }
    write_json(run / "metrics.json", metrics)
    manifest["evaluation"] = {
        "status": "scored",
        "metrics_sha256": digest((run / "metrics.json").read_bytes()),
        "outside_roi_max_abs_rgb_difference_dn": evaluation[
            "outside_roi_max_abs_rgb_difference_dn"
        ],
    }
    manifest["elapsed_seconds"] = round(
        float(manifest.get("elapsed_seconds") or 0) + time.perf_counter() - started, 3
    )
    write_json(run / "run-manifest.json", manifest)
    log.append(
        "evaluate: defect "
        f"{evaluation['local_defect_rgb_mae_dn']['before']:.6f} -> "
        f"{evaluation['local_defect_rgb_mae_dn']['after']:.6f}"
    )
    log.append(
        "evaluate: flicker std "
        f"{evaluation['flicker_static_patch_mean_luma_temporal_std_dn']['before']:.6f} -> "
        f"{evaluation['flicker_static_patch_mean_luma_temporal_std_dn']['after']:.6f}"
    )
    log.append(
        "evaluate: ghost residual "
        f"{evaluation['ghost_rgb_residual_above_1_dn']['before']:.6f} -> "
        f"{evaluation['ghost_rgb_residual_above_1_dn']['after']:.6f}"
    )
    return 0


def selfcheck(run: Path, *, resvg: str, ffmpeg: str, ffprobe: str) -> int:
    log: list[str] = []
    if run.exists():
        raise ValueError(f"run directory already exists: {run}")
    source(run, document_path=None, resvg=resvg, log=log)
    if repair_run(run, ffmpeg=ffmpeg, ffprobe=ffprobe, log=log):
        raise ValueError("repair stage failed")
    evaluate_run(run, log=log)
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    evaluation = metrics["evaluation"]
    checks = {
        "outside_roi_changed_pixels": metrics["outside_roi_changed_pixels"] == 0,
        "defect_after_zero": evaluation["local_defect_rgb_mae_dn"]["after"] <= 0.5,
        "flicker_after_zero": (
            evaluation["flicker_static_patch_mean_luma_temporal_std_dn"]["after"] <= 0.5
        ),
        "ghost_reduced": (
            evaluation["ghost_rgb_residual_above_1_dn"]["after"]
            < 0.5 * evaluation["ghost_rgb_residual_above_1_dn"]["before"]
        ),
        "appearance_matches_clean": (
            abs(
                evaluation["appearance_object_mean_rgb_temporal_std_dn"]["after"]
                - evaluation["appearance_object_mean_rgb_temporal_std_clean_dn"]
            )
            <= 1e-9
        ),
        "edges_preserved": (abs(evaluation["motion_edge_gradient_after_over_clean"] - 1) <= 0.02),
        "media_verified": all(
            record["verification"]["decoded_frames"] == spec.FRAME_COUNT
            for record in json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))[
                "media"
            ]["files"].values()
        ),
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    if not all(checks.values()):
        raise ValueError("R1-002 self-check failed")
    print("PASS r1-002 motion integration")
    for line in log:
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    source_parser = commands.add_parser("source", help="render Motion frames and masks")
    source_parser.add_argument("--run", type=Path, required=True)
    source_parser.add_argument("--document", type=Path)
    source_parser.add_argument("--resvg", required=True)
    repair_parser = commands.add_parser("repair", help="repair and export a sourced run")
    repair_parser.add_argument("--run", type=Path, required=True)
    repair_parser.add_argument("--ffmpeg", default="ffmpeg")
    repair_parser.add_argument("--ffprobe", default="ffprobe")
    evaluate_parser = commands.add_parser("evaluate", help="score a repaired run")
    evaluate_parser.add_argument("--run", type=Path, required=True)
    check_parser = commands.add_parser("selfcheck", help="run all stages and assert gates")
    check_parser.add_argument("--run", type=Path, required=True)
    check_parser.add_argument("--resvg", required=True)
    check_parser.add_argument("--ffmpeg", default="ffmpeg")
    check_parser.add_argument("--ffprobe", default="ffprobe")
    arguments = parser.parse_args()
    log: list[str] = []
    try:
        if arguments.command == "source":
            return source(
                arguments.run,
                document_path=arguments.document,
                resvg=arguments.resvg,
                log=log,
            )
        if arguments.command == "repair":
            return repair_run(
                arguments.run,
                ffmpeg=arguments.ffmpeg,
                ffprobe=arguments.ffprobe,
                log=log,
            )
        if arguments.command == "evaluate":
            return evaluate_run(arguments.run, log=log)
        return selfcheck(
            arguments.run,
            resvg=arguments.resvg,
            ffmpeg=arguments.ffmpeg,
            ffprobe=arguments.ffprobe,
        )
    except (OSError, ValueError, SyntaxError, KeyError, TypeError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
