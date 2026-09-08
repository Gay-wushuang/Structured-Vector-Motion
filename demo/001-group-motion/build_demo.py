from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from svm import MotionEvaluator
from svm.document import validate_document
from svm.renderers import SVGRenderer, SVGRenderOptions

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
PNG_FRAMES = HERE / "frames-png"
FPS = 24
DURATION_TICKS = 144
ARTIFACT_ID = "artifact:" + "a" * 64


def primitive(
    entity_id: str,
    operation_id: str,
    name: str,
    operation_type: str,
    parameters: dict[str, int | float],
    fill: str,
    *,
    opacity: float = 1.0,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {"id": entity_id, "name": name},
        {"id": operation_id, "type": operation_type, "inputs": {}, "parameters": parameters},
        {"entity": entity_id, "property": "geometry", "slot": f"{operation_id}.geometry"},
        {
            "entity": entity_id,
            "fill": fill,
            "stroke": "none",
            "stroke_width": 0,
            "opacity": opacity,
        },
    )


def group(index: int, members: list[str], origin: tuple[float, float]) -> dict[str, Any]:
    digit = format(index, "x")
    return {
        "id": "group:" + digit * 64,
        "kind": "explicit-group",
        "members": sorted(members),
        "transform": {
            "translate": [0, 0],
            "rotation_degrees": 0,
            "scale": 1,
            "origin": list(origin),
        },
        "provenance": {
            "candidate_id": "candidate:group:" + digit * 64,
            "inference_id": "inference:group:" + digit * 64,
            "inference_artifact_id": ARTIFACT_ID,
        },
    }


def track(
    group_id: str,
    property_name: str,
    values: list[tuple[int, int | float]],
) -> dict[str, Any]:
    slug = property_name.replace(".", "-").replace("_", "-")
    group_slug = group_id[-1]
    return {
        "id": f"track:demo-{group_slug}-{slug}",
        "target": {"group": group_id, "property": property_name},
        "value_type": "number",
        "interpolation": "linear",
        "keyframes": [
            {
                "id": f"keyframe:demo-{group_slug}-{slug}-{tick:04d}",
                "tick": tick,
                "value": value,
            }
            for tick, value in values
        ],
    }


def build_document() -> dict[str, Any]:
    specs = [
        primitive(
            "entity:background",
            "op:background",
            "Night Field",
            "CreateRectangle",
            {"x": -2, "y": -1.125, "width": 4, "height": 2.25},
            "#171427",
        ),
        primitive(
            "entity:moon",
            "op:moon",
            "Moon",
            "CreateEllipse",
            {"cx": 0, "cy": -0.72, "rx": 0.22, "ry": 0.22},
            "#F5E7B2",
            opacity=0.9,
        ),
        primitive(
            "entity:a-body",
            "op:a-body",
            "Figure A Body",
            "CreateEllipse",
            {"cx": -0.68, "cy": 0.22, "rx": 0.38, "ry": 0.64},
            "#7C5CFC",
        ),
        primitive(
            "entity:a-face",
            "op:a-face",
            "Figure A Face",
            "CreateEllipse",
            {"cx": -0.68, "cy": -0.28, "rx": 0.28, "ry": 0.26},
            "#F4E8D1",
        ),
        primitive(
            "entity:a-mark",
            "op:a-mark",
            "Figure A Mark",
            "CreateRectangle",
            {"x": -0.84, "y": -0.34, "width": 0.32, "height": 0.08},
            "#171427",
        ),
        primitive(
            "entity:b-body",
            "op:b-body",
            "Figure B Body",
            "CreateEllipse",
            {"cx": 0.68, "cy": 0.22, "rx": 0.38, "ry": 0.64},
            "#56C596",
        ),
        primitive(
            "entity:b-face",
            "op:b-face",
            "Figure B Face",
            "CreateEllipse",
            {"cx": 0.68, "cy": -0.28, "rx": 0.28, "ry": 0.26},
            "#F4E8D1",
        ),
        primitive(
            "entity:b-mark",
            "op:b-mark",
            "Figure B Mark",
            "CreateRectangle",
            {"x": 0.52, "y": -0.34, "width": 0.32, "height": 0.08},
            "#171427",
        ),
        primitive(
            "entity:signal-left",
            "op:signal-left",
            "Signal Left",
            "CreateRectangle",
            {"x": -0.22, "y": -0.96, "width": 0.09, "height": 0.34},
            "#FF6B8A",
            opacity=0.82,
        ),
        primitive(
            "entity:signal-right",
            "op:signal-right",
            "Signal Right",
            "CreateRectangle",
            {"x": 0.13, "y": -0.96, "width": 0.09, "height": 0.34},
            "#FF6B8A",
            opacity=0.82,
        ),
        primitive(
            "entity:foreground",
            "op:foreground",
            "Foreground Band",
            "CreateRectangle",
            {"x": -2, "y": 0.92, "width": 4, "height": 0.205},
            "#292342",
            opacity=0.94,
        ),
    ]
    entities, operations, bindings, styles = (list(items) for items in zip(*specs, strict=True))
    groups = [
        group(1, ["entity:a-body", "entity:a-face", "entity:a-mark"], (-0.68, 0.22)),
        group(2, ["entity:b-body", "entity:b-face", "entity:b-mark"], (0.68, 0.22)),
        group(3, ["entity:signal-left", "entity:signal-right"], (0, -0.79)),
    ]
    ticks = [0, 18, 36, 60, 84, 108, 132, 144]

    def keys(values: list[int | float]) -> list[tuple[int, int | float]]:
        return list(zip(ticks, values, strict=True))

    animation = [
        track(groups[0]["id"], "translate.x", keys([0, 0.16, 0.05, 0.58, 0.82, 0.34, 0.08, 0])),
        track(groups[0]["id"], "translate.y", keys([0, -0.04, 0.06, 0, -0.08, 0.04, 0.02, 0])),
        track(groups[0]["id"], "rotation_degrees", keys([0, -4, 5, 0, -7, 4, -2, 0])),
        track(groups[0]["id"], "scale", keys([1, 1.06, 0.96, 1.22, 1.02, 1.1, 0.98, 1])),
        track(
            groups[1]["id"], "translate.x", keys([0, -0.12, -0.02, -0.48, -0.76, -0.28, -0.05, 0])
        ),
        track(groups[1]["id"], "translate.y", keys([0, 0.03, -0.05, 0.02, -0.03, -0.07, 0.03, 0])),
        track(groups[1]["id"], "rotation_degrees", keys([0, 3, -5, 1, 7, -4, 2, 0])),
        track(groups[1]["id"], "scale", keys([1, 0.97, 1.05, 1.14, 1.04, 1.12, 0.99, 1])),
        track(groups[2]["id"], "translate.y", keys([0, -0.05, 0.04, -0.02, 0.06, -0.04, 0.02, 0])),
        track(
            groups[2]["id"],
            "rotation_degrees",
            keys([0, 18, -22, 35, -40, 28, -12, 0]),
        ),
        track(groups[2]["id"], "scale", keys([1, 1.28, 0.84, 1.38, 0.9, 1.24, 0.94, 1])),
    ]
    return {
        "schema_version": "0.1",
        "semantics_version": "svm-core-0.1",
        "document_id": "document:authoring-ground-truth-demo-001",
        "references": [
            {
                "id": ARTIFACT_ID,
                "uri": ARTIFACT_ID.replace(":", "://", 1),
                "content_hash": "sha256:" + "a" * 64,
                "media_type": "application/vnd.svm.pop-group-candidates+json;version=0.1",
                "import_metadata": {"fixture": "hand-authored-demo"},
            }
        ],
        "entities": entities,
        "groups": groups,
        "construction": {
            "operations": operations,
            "output_bindings": bindings,
            "refinement_stages": [],
        },
        "presentation": {"render_stack": [item["id"] for item in entities], "styles": styles},
        "constraints": [],
        "evaluation_policies": [],
        "edit_permissions": [],
        "animation": {
            "semantics_version": "svm-motion@0.3",
            "timebase": {"ticks_per_second": FPS},
            "content": animation,
            "construction_scheduling_hints": [],
        },
    }


def encode(pattern: str, output: Path, extra: list[str]) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to encode the demo")
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
            pattern,
            *extra,
            str(output),
        ],
        check=True,
    )


def rasterize_frames() -> None:
    browser_candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    )
    browser = next((candidate for candidate in browser_candidates if candidate.is_file()), None)
    if browser is None:
        raise RuntimeError("Edge or Chrome is required to rasterize SVG demo frames")
    PNG_FRAMES.mkdir(parents=True, exist_ok=True)
    for tick in range(DURATION_TICKS + 1):
        source = (FRAMES / f"frame-{tick:04d}.svg").resolve().as_uri()
        output = (PNG_FRAMES / f"frame-{tick:04d}.png").resolve()
        subprocess.run(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--window-size=960,540",
                f"--screenshot={output}",
                source,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> None:
    document = build_document()
    validate_document(document)
    HERE.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    (HERE / "scene.svm.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    renderer = SVGRenderer(SVGRenderOptions(width=960, height=540, view_box=(-2, -1.125, 4, 2.25)))
    motion = MotionEvaluator(document)
    for tick in range(DURATION_TICKS + 1):
        (FRAMES / f"frame-{tick:04d}.svg").write_text(
            renderer.render(motion.evaluate(tick).scene), encoding="utf-8"
        )
    rasterize_frames()
    pattern = str(PNG_FRAMES / "frame-%04d.png")
    encode(
        pattern,
        HERE / "demo.mp4",
        ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    encode(pattern, HERE / "demo.gif", ["-vf", "fps=12,scale=640:-1:flags=lanczos", "-loop", "0"])


if __name__ == "__main__":
    main()
