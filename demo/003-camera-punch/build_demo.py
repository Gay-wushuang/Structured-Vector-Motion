from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from svm import MotionEvaluator
from svm.document import validate_document
from svm.renderers import SVGRenderer, SVGRenderOptions

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "002-style-rhythm" / "build_demo.py"
FRAMES, PNG_FRAMES, PREVIEWS = HERE / "frames", HERE / "frames-png", HERE / "previews"
FPS, DURATION_TICKS = 24, 192


def source_module() -> Any:
    spec = importlib.util.spec_from_file_location("svm_demo_002", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Demo 002 builder is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def camera_track(property_name: str, values: list[tuple[int, int | float]]) -> dict[str, Any]:
    slug = property_name.replace(".", "-").replace("_", "-")
    return {
        "id": f"track:camera-{slug}",
        "target": {"camera": "presentation", "property": property_name},
        "value_type": "number",
        "interpolation": "ease-in-out",
        "keyframes": [
            {"id": f"keyframe:camera-{slug}-{tick:04d}", "tick": tick, "value": value}
            for tick, value in values
        ],
    }


def build_document() -> dict[str, Any]:
    document = source_module().build_document()
    document["document_id"] = "document:authoring-ground-truth-demo-003"
    document["presentation"]["camera"] = {"position": [0, 0], "rotation_degrees": 0, "scale": 1}
    document["animation"]["semantics_version"] = "svm-motion@0.6"
    document["animation"]["content"].extend(
        [
            camera_track(
                "position.x",
                [
                    (0, 0),
                    (30, 0),
                    (42, 0.08),
                    (50, 0.04),
                    (64, 0.04),
                    (92, -0.05),
                    (108, -0.05),
                    (128, 0.07),
                    (138, 0.03),
                    (152, 0.03),
                    (184, 0),
                    (192, 0),
                ],
            ),
            camera_track(
                "position.y",
                [
                    (0, 0),
                    (30, 0),
                    (42, -0.05),
                    (50, -0.03),
                    (64, -0.03),
                    (92, 0.04),
                    (108, 0.04),
                    (128, -0.04),
                    (138, -0.02),
                    (152, -0.02),
                    (184, 0),
                    (192, 0),
                ],
            ),
            camera_track(
                "rotation_degrees",
                [
                    (0, 0),
                    (30, 0),
                    (42, 2.8),
                    (50, 1.4),
                    (64, 1.4),
                    (92, -2.2),
                    (108, -2.2),
                    (128, 3.2),
                    (138, 1.2),
                    (152, 1.2),
                    (184, 0),
                    (192, 0),
                ],
            ),
            camera_track(
                "scale",
                [
                    (0, 1),
                    (30, 1),
                    (42, 1.48),
                    (50, 1.36),
                    (64, 1.36),
                    (92, 1.12),
                    (108, 1.12),
                    (128, 1.58),
                    (138, 1.42),
                    (152, 1.42),
                    (176, 0.96),
                    (184, 1),
                    (192, 1),
                ],
            ),
        ]
    )
    return document


def rasterize() -> None:
    browser = next(
        (
            path
            for path in (
                Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            )
            if path.is_file()
        ),
        None,
    )
    if browser is None:
        raise RuntimeError("Edge or Chrome is required")
    PNG_FRAMES.mkdir(parents=True, exist_ok=True)
    for tick in range(DURATION_TICKS + 1):
        subprocess.run(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--window-size=960,540",
                f"--screenshot={PNG_FRAMES / f'frame-{tick:04d}.png'}",
                (FRAMES / f"frame-{tick:04d}.svg").resolve().as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> None:
    document = build_document()
    validate_document(document)
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "scene.svm.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    FRAMES.mkdir(parents=True, exist_ok=True)
    motion = MotionEvaluator(document)
    renderer = SVGRenderer(SVGRenderOptions(width=960, height=540, view_box=(-2, -1.125, 4, 2.25)))
    for tick in range(DURATION_TICKS + 1):
        (FRAMES / f"frame-{tick:04d}.svg").write_text(
            renderer.render(motion.evaluate(tick).scene), encoding="utf-8"
        )
    rasterize()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            str(PNG_FRAMES / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(HERE / "demo.mp4"),
        ],
        check=True,
    )
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for tick in (0, 42, 92, 128, 192):
        shutil.copyfile(PNG_FRAMES / f"frame-{tick:04d}.png", PREVIEWS / f"frame-{tick:04d}.png")


if __name__ == "__main__":
    main()
