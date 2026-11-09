"""Run the isolated R1 controlled restoration experiment from a PNG bundle."""

import argparse
import platform
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import __version__ as pillow_version

from .media import MediaError, export_media
from .repair import PARAMETERS, repair
from .sequence import (
    FPS,
    FRAME_COUNT,
    HEIGHT,
    WIDTH,
    digest,
    load_masks,
    load_sequence,
    save_sequence,
    write_json,
)

PROFILE = "svm-c-r1-restoration@1"


def run(input_path: Path, mask_path: Path, output: Path, ffmpeg: str, ffprobe: str) -> int:
    if any(output.resolve().is_relative_to(path.resolve()) for path in (input_path, mask_path)):
        raise ValueError("output must be outside the input and mask directories")
    frames, inputs = load_sequence(input_path)
    masks, mask_records = load_masks(mask_path)
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    repaired, reports = repair(frames, masks)
    changed = np.any(repaired != frames, axis=-1)
    outside = int(np.count_nonzero(changed & ~masks["roi"]))
    if outside:
        raise ValueError(f"repair violated ROI authorization ({outside} pixels)")
    output.mkdir(parents=True)
    metrics = {
        "profile": PROFILE,
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
        "profile": PROFILE,
        "status": "in_progress",
        "scope": "controlled synthetic R1 experiment",
        "clean_reference_used_by_repair": False,
        "width": WIDTH,
        "height": HEIGHT,
        "frame_count": FRAME_COUNT,
        "fps": {"numerator": FPS, "denominator": 1},
        "timebase_ticks_per_second": FPS,
        "frame_domain": "ordered RGB8 PNG code values, ticks 0..23",
        "write_scope": "ROI only",
        "parameters": PARAMETERS,
        "repair_module_sha256": digest(Path(__file__).with_name("repair.py").read_bytes()),
        "environment": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pillow": pillow_version,
        },
        "inputs": inputs,
        "masks": mask_records,
        "frame_reports": reports,
        "repair_status": (
            "contains_refusals" if any(metrics["refused_frames_by_stage"].values()) else "processed"
        ),
        "media": {"status": "pending"},
    }
    write_json(output / "manifest.json", manifest)
    code = 0
    try:
        manifest["frames_original"] = save_sequence(output / "frames-original", frames)
        manifest["frames_repaired"] = save_sequence(output / "frames-repaired", repaired)
        write_json(output / "metrics.json", metrics)
        manifest["media"] = export_media(output, frames, repaired, ffmpeg, ffprobe)
    except (MediaError, OSError, ValueError) as error:
        code = error.exit_code if isinstance(error, MediaError) else 8
        manifest["media"] = {"status": "failed", "error": str(error)}
        print(error, file=sys.stderr)
    if code:
        manifest["status"] = "failed"
    else:
        manifest["status"] = (
            "partial" if manifest["repair_status"] == "contains_refusals" else "verified"
        )
    manifest["exit_code"] = code
    write_json(output / "manifest.json", manifest)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="canonical PNG directory")
    parser.add_argument("--mask", type=Path, required=True, help="four-role binary PNG bundle")
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="executable path or PATH command")
    parser.add_argument("--ffprobe", default="ffprobe", help="executable path or PATH command")
    arguments = parser.parse_args()
    try:
        return run(
            arguments.input, arguments.mask, arguments.output, arguments.ffmpeg, arguments.ffprobe
        )
    except (OSError, ValueError, SyntaxError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
