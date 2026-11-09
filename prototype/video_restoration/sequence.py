"""Canonical RGB8 PNG input, binary mask bundles, and output provenance."""

import hashlib
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

WIDTH = HEIGHT = 256
FRAME_COUNT = 24
FPS = 12
MASK_ROLES = ("roi", "stable", "ghost", "defect")
FRAME_NAMES = tuple(f"{index:06d}.png" for index in range(FRAME_COUNT))


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_sequence(directory: Path, *, mask: bool = False) -> tuple[np.ndarray, list[dict]]:
    """Decode only the canonical ordered sequence, hashing the bytes actually decoded."""
    entries = sorted(item.name for item in directory.iterdir())
    if entries != list(FRAME_NAMES):
        raise ValueError(f"{directory}: expected only 000000.png through 000023.png")
    frames = []
    records = []
    for tick, name in enumerate(FRAME_NAMES):
        path = directory / name
        data = path.read_bytes()
        expected_color = 0 if mask else 2
        if (
            len(data) < 33
            or data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
            or struct.unpack(">IIBBBBB", data[16:29]) != (WIDTH, HEIGHT, 8, expected_color, 0, 0, 0)
        ):
            raise ValueError(f"{path}: expected non-interlaced 256x256 8-bit canonical PNG")
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            metadata = {"icc_profile", "transparency", "exif", "srgb", "gamma", "chromaticity"}
            if getattr(image, "n_frames", 1) != 1 or metadata & image.info.keys():
                raise ValueError(
                    f"{path}: animation or embedded color/EXIF metadata is unsupported"
                )
            pixels = np.array(image)
        if mask and not np.all((pixels == 0) | (pixels == 255)):
            raise ValueError(f"{path}: mask values must be 0 or 255")
        frames.append(pixels != 0 if mask else pixels)
        records.append(
            {
                "file": name,
                "tick": tick,
                "sha256": digest(data),
                "pixel_sha256": digest(pixels.tobytes()),
            }
        )
    return np.stack(frames), records


def load_masks(directory: Path) -> tuple[dict[str, np.ndarray], dict[str, list[dict]]]:
    masks = {}
    records = {}
    for role in MASK_ROLES:
        masks[role], records[role] = load_sequence(directory / role, mask=True)
    roi, stable, ghost, defect = (masks[role] for role in MASK_ROLES)
    if not np.any(stable) or not np.any(roi) or np.any(np.all(roi, axis=(1, 2))):
        raise ValueError("stable and ROI must have support, and ROI must be smaller than the frame")
    if np.any(stable != stable[0]):
        raise ValueError("the stable sample mask must be constant across all frames")
    if np.any(roi & stable) or np.any((ghost | defect) & ~roi) or np.any(ghost & defect):
        raise ValueError(
            "stable must be outside ROI, and ghost and defect must be disjoint inside ROI"
        )
    return masks, records


def save_sequence(directory: Path, frames: np.ndarray) -> list[dict]:
    directory.mkdir()
    records = []
    for tick, (name, frame) in enumerate(zip(FRAME_NAMES, frames, strict=True)):
        path = directory / name
        Image.fromarray(frame).save(path, compress_level=6)
        records.append(
            {
                "file": name,
                "tick": tick,
                "sha256": digest(path.read_bytes()),
                "pixel_sha256": digest(frame.tobytes()),
            }
        )
    return records


def write_json(path: Path, content: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(content, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def verify_records(records: list[dict], expected: list[dict], label: str) -> None:
    if records != expected:
        raise ValueError(f"{label}: frame/mask digests differ from the run manifest")
