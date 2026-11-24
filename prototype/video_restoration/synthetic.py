"""Generate the controlled R1-001 clip, intervention masks, and scoring inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

GENERATOR = "svm-c-r1-synthetic@1"
SIZE = 256
FPS = 12
FRAME_COUNT = 24
DEFAULT_SEED = 20261109
ROI_XYXY = (45, 72, 213, 200)
STABLE_XYXY = (14, 16, 44, 52)
APPEARANCE_XYXY = (70, 74, 128, 92)
DEFECT_XYXY = (180, 89, 191, 98)
DEFECT_FRAMES = (5, 6, 7, 14, 15, 16, 21)
DEFECT_RGB = (45, 26, 116)
DEFECT_NOISE = 5
BACKGROUND_NOISE = 2
OBJECT_RADII = (15, 12)
OBJECT_Y_OFFSETS = (0, 0, 1, 1, 2, 2, 2, 2, 1, 1, 0, 0) * 2
FLICKER_OFFSETS = (-12, 8, -8, 12, 0, 6, -6, 0) * 3
GHOST_NUMERATOR = 2
GHOST_DENOMINATOR = 5
GHOST_PROTECTION_RADIUS = 2


def _rectangle(bounds: tuple[int, int, int, int]) -> np.ndarray:
    left, top, right, bottom = bounds
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    mask[top:bottom, left:right] = True
    return mask


def _expand(mask: np.ndarray, radius: int) -> np.ndarray:
    padded = np.pad(mask, radius)
    expanded = np.zeros_like(mask)
    for row in range(2 * radius + 1):
        for column in range(2 * radius + 1):
            expanded |= padded[row : row + SIZE, column : column + SIZE]
    return expanded


def _write_png(path: Path, array: np.ndarray) -> None:
    if array.dtype == bool:
        array = array.astype(np.uint8) * 255
    Image.fromarray(array).save(path, compress_level=6)


def _scene_background(y: np.ndarray, x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    # Fixed grid and fine texture make temporal replacement verifiable at pixel resolution.
    grid = ((x // 32 + y // 32) % 2) * 5
    fine = ((x + 2 * y) % 13) // 3
    base = np.stack(
        (
            91 + y // 9 + grid + fine,
            121 + x // 13 + grid + fine,
            137 + (255 - y) // 11 + grid + fine,
        ),
        axis=-1,
    )
    noise = rng.integers(-BACKGROUND_NOISE, BACKGROUND_NOISE + 1, size=base.shape)
    return base + noise


def _draw_target(
    background: np.ndarray, y: np.ndarray, x: np.ndarray, center: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    dx, dy = x - center[0], y - center[1]
    rx, ry = OBJECT_RADII
    distance = (dx * ry) ** 2 + (dy * rx) ** 2
    limit = (rx * ry) ** 2
    target = distance <= limit
    clean = background.copy()
    clean[target] = (35, 68, 80)
    clean[distance * 4 < 3 * limit] = (220, 159, 61)
    clean[(dx + 4) ** 2 + (dy + 3) ** 2 <= 9] = (240, 212, 128)
    clean[(dx >= 1) & (dx <= 6) & (dy >= 2) & (dy <= 3)] = (117, 78, 45)
    return clean, target


def _generate(root: Path, seed: int, without: frozenset[str]) -> None:
    rng = np.random.Generator(np.random.PCG64(seed))
    folders = ("input", "mask/roi", "mask/stable", "mask/ghost", "mask/defect")
    for folder in (*folders, "evaluation/clean", "evaluation/edge", "evaluation/interior"):
        (root / folder).mkdir(parents=True)

    y, x = np.indices((SIZE, SIZE))
    background = _scene_background(y, x, rng)
    roi, stable = _rectangle(ROI_XYXY), _rectangle(STABLE_XYXY)
    defect_region = _rectangle(DEFECT_XYXY)
    defect_pixels = int(defect_region.sum())
    defect_frames = () if "defect" in without else DEFECT_FRAMES
    flicker_offsets = (0,) * FRAME_COUNT if "flicker" in without else FLICKER_OFFSETS
    previous_target = np.zeros_like(roi)
    previous_clean = background
    centers = [(72 + 4 * index, 132 + OBJECT_Y_OFFSETS[index]) for index in range(FRAME_COUNT)]
    for index, center in enumerate(centers):
        clean, target = _draw_target(background, y, x, center)
        edge = _expand(target, 1) & _expand(~target, 1)
        interior = target & ~_expand(~target, 2)
        ghost = previous_target & ~_expand(target, GHOST_PROTECTION_RADIUS)
        if "ghost" in without:
            ghost.fill(False)
        defect = defect_region & (index in defect_frames)

        degraded = clean.copy()
        degraded[ghost] = (
            (GHOST_DENOMINATOR - GHOST_NUMERATOR) * clean[ghost]
            + GHOST_NUMERATOR * previous_clean[ghost]
            + GHOST_DENOMINATOR // 2
        ) // GHOST_DENOMINATOR
        if index in defect_frames:
            degraded[defect] = DEFECT_RGB + rng.integers(
                -DEFECT_NOISE, DEFECT_NOISE + 1, size=(defect_pixels, 3)
            )
        degraded += flicker_offsets[index]
        if degraded.min() < 0 or degraded.max() > 255:
            raise ValueError("Fixture parameters clipped a degraded frame")

        name = f"{index:06d}.png"
        _write_png(root / "input" / name, degraded.astype(np.uint8))
        _write_png(root / "evaluation/clean" / name, clean.astype(np.uint8))
        _write_png(root / "evaluation/edge" / name, edge)
        _write_png(root / "evaluation/interior" / name, interior)
        for role, mask in (("roi", roi), ("stable", stable), ("ghost", ghost), ("defect", defect)):
            _write_png(root / "mask" / role / name, mask)
        previous_target, previous_clean = target, clean

    fixture = {
        "generator": GENERATOR,
        "seed": seed,
        "rng": "numpy.random.PCG64",
        "libraries": {"numpy": np.__version__, "pillow": Image.__version__},
        "width": SIZE,
        "height": SIZE,
        "frame_count": FRAME_COUNT,
        "fps": {"numerator": FPS, "denominator": 1},
        "regions": {
            "coordinates": "half-open xyxy in source pixels",
            "appearance_xyxy": APPEARANCE_XYXY,
            "defect_xyxy": DEFECT_XYXY,
            "roi_xyxy": ROI_XYXY,
            "stable_xyxy": STABLE_XYXY,
        },
        "scene": {
            "background_noise_inclusive_rgb": [-BACKGROUND_NOISE, BACKGROUND_NOISE],
            "target_center_xy_by_frame": centers,
            "target_radii_xy": OBJECT_RADII,
            "edge_band": "one pixel on each side of target silhouette, Chebyshev distance",
            "interior": "target silhouette eroded by two pixels, Chebyshev distance",
        },
        "injection_order": ["ghost", "defect", "flicker"],
        "ghost": {
            "enabled": "ghost" not in without,
            "lag_frames": 1,
            "opacity": {"numerator": GHOST_NUMERATOR, "denominator": GHOST_DENOMINATOR},
            "protection_radius_chebyshev_px": GHOST_PROTECTION_RADIUS,
            "rounding": "nearest integer",
            "support": "prior target silhouette outside expanded current silhouette",
        },
        "defect": {
            "frames_zero_based": defect_frames,
            "replacement_rgb": DEFECT_RGB,
            "noise_inclusive_rgb": [-DEFECT_NOISE, DEFECT_NOISE],
        },
        "flicker": {"additive_rgb_offset_by_frame": flicker_offsets, "scope": "full frame"},
    }
    (root / "evaluation/fixture.json").write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def generate(
    output: Path, seed: int = DEFAULT_SEED, *, without: frozenset[str] = frozenset()
) -> None:
    """Write one complete fixture to a fresh directory."""
    if seed < 0:
        raise ValueError("Seed must be a nonnegative integer")
    if output.exists():
        raise ValueError(f"Fixture output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".synthetic-") as temporary:
        staging = Path(temporary) / "fixture"
        _generate(staging, seed, without)
        staging.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", default=DEFAULT_SEED, type=int)
    parser.add_argument(
        "--without",
        action="append",
        default=[],
        choices=("flicker", "ghost", "defect"),
        help="disable one degradation, repeat for additional degradations",
    )
    args = parser.parse_args()
    try:
        generate(args.output, args.seed, without=frozenset(args.without))
    except (OSError, ValueError) as error:
        parser.exit(2, f"Fixture generation failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
