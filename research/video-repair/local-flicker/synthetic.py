"""Generate reproducible colored research fixtures; ground truth stays separate."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from pipeline import alpha_mask, encode


def generate(directory: Path) -> None:
    height, width, count = 128, 192, 24
    y, x = np.mgrid[:height, :width]
    mask = np.zeros((height, width), np.uint8)
    mask[15:114, 20:172] = 255
    alpha = alpha_mask(mask, 6)
    rng = np.random.default_rng(20261111)
    noise = rng.integers(-14, 15, (height, width))
    base = np.stack(
        [80 + x * 0.18 + noise, 95 + y * 0.22 + noise, 125 + np.sin(x / 5) * 8 + noise], axis=2
    )
    clean, damaged, objects = [], [], []
    for i in range(count):
        frame = base.copy()
        obj = np.zeros((height, width), np.uint8)
        left, top = 40 + 3 * i, 48 + int(4 * np.sin(i / 4))
        obj[top : top + 27, left : left + 25] = 255
        texture = (x + y) % 8 < 4
        for ch, val in enumerate((145, 75, 65)):
            plane = frame[:, :, ch]
            plane[obj > 0] = val + 12 * texture[obj > 0]
        pristine = np.clip(np.rint(frame), 0, 255).astype(np.uint8)
        gain = 1 + 0.20 * np.sin(2 * np.pi * i / 5) * (0.5 + 0.5 * x / (width - 1))
        perturbed = np.clip(
            np.rint(pristine.astype(np.float32) * (1 + alpha[..., None] * (gain[..., None] - 1))),
            0,
            255,
        ).astype(np.uint8)
        perturbed[mask == 0] = pristine[mask == 0]
        clean.append(pristine)
        damaged.append(perturbed)
        objects.append(obj)
    directory.mkdir()
    np.save(directory / "ground_truth.npy", np.stack(clean), allow_pickle=False)
    np.save(directory / "object_masks.npy", np.stack(objects), allow_pickle=False)
    if not cv2.imwrite(str(directory / "roi.png"), mask):
        raise ValueError("cannot save synthetic mask")
    encode(directory / "source.avi", np.stack(damaged), "12", lossless=True)
