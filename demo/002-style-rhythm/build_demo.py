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
PREVIEWS = HERE / "previews"
FPS = 24
DURATION_TICKS = 192
ARTIFACT_ID = "artifact:" + "b" * 64


def primitive(
    entity_id: str,
    operation_type: str,
    parameters: dict[str, int | float],
    fill: str,
    *,
    opacity: float = 1,
) -> tuple[dict[str, Any], ...]:
    operation_id = entity_id.replace("entity:", "op:")
    return (
        {"id": entity_id, "name": entity_id.removeprefix("entity:").replace("-", " ").title()},
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


def numeric_track(
    group_id: str,
    property_name: str,
    values: list[tuple[int, int | float]],
) -> dict[str, Any]:
    slug = f"g{group_id[-1]}-{property_name}".replace(".", "-").replace("_", "-")
    return {
        "id": f"track:{slug}",
        "target": {"group": group_id, "property": property_name},
        "value_type": "number",
        "interpolation": "ease-in-out",
        "keyframes": [
            {"id": f"keyframe:{slug}-{tick:04d}", "tick": tick, "value": value}
            for tick, value in values
        ],
    }


def style_track(
    entity_id: str,
    property_name: str,
    values: list[tuple[int, int | float | str]],
) -> dict[str, Any]:
    slug = f"{entity_id.removeprefix('entity:')}-{property_name}"
    return {
        "id": f"track:{slug}",
        "target": {"entity": entity_id, "property": property_name},
        "value_type": "color" if property_name == "fill" else "number",
        "interpolation": "hold" if property_name == "fill" else "ease-in-out",
        "keyframes": [
            {"id": f"keyframe:{slug}-{tick:04d}", "tick": tick, "value": value}
            for tick, value in values
        ],
    }


def build_document() -> dict[str, Any]:
    specs = [
        primitive(
            "entity:background",
            "CreateRectangle",
            {"x": -2, "y": -1.125, "width": 4, "height": 2.25},
            "#171427",
        ),
        primitive(
            "entity:halo",
            "CreateEllipse",
            {"cx": 0, "cy": -0.55, "rx": 0.72, "ry": 0.72},
            "#332A55",
            opacity=0.7,
        ),
        primitive(
            "entity:a-body",
            "CreateEllipse",
            {"cx": -0.72, "cy": 0.18, "rx": 0.42, "ry": 0.68},
            "#7C5CFC",
        ),
        primitive(
            "entity:a-face",
            "CreateEllipse",
            {"cx": -0.72, "cy": -0.32, "rx": 0.29, "ry": 0.25},
            "#FFF0D6",
        ),
        primitive(
            "entity:a-mark",
            "CreateRectangle",
            {"x": -0.89, "y": -0.37, "width": 0.34, "height": 0.08},
            "#171427",
        ),
        primitive(
            "entity:b-body",
            "CreateEllipse",
            {"cx": 0.72, "cy": 0.18, "rx": 0.42, "ry": 0.68},
            "#56C596",
        ),
        primitive(
            "entity:b-face",
            "CreateEllipse",
            {"cx": 0.72, "cy": -0.32, "rx": 0.29, "ry": 0.25},
            "#FFF0D6",
        ),
        primitive(
            "entity:b-mark",
            "CreateRectangle",
            {"x": 0.55, "y": -0.37, "width": 0.34, "height": 0.08},
            "#171427",
        ),
        primitive(
            "entity:signal-left",
            "CreateRectangle",
            {"x": -0.25, "y": -1.03, "width": 0.1, "height": 0.4},
            "#FF6B8A",
        ),
        primitive(
            "entity:signal-right",
            "CreateRectangle",
            {"x": 0.15, "y": -1.03, "width": 0.1, "height": 0.4},
            "#FF6B8A",
        ),
        primitive(
            "entity:overlay-top",
            "CreateRectangle",
            {"x": -2, "y": -1.125, "width": 4, "height": 0.12},
            "#FF6B8A",
            opacity=0.8,
        ),
        primitive(
            "entity:overlay-bottom",
            "CreateRectangle",
            {"x": -2, "y": 1.005, "width": 4, "height": 0.12},
            "#56C596",
            opacity=0.8,
        ),
        primitive(
            "entity:flash",
            "CreateRectangle",
            {"x": -2, "y": -1.125, "width": 4, "height": 2.25},
            "#FFF0D6",
            opacity=0,
        ),
    ]
    entities, operations, bindings, styles = (list(items) for items in zip(*specs, strict=True))
    groups = [
        group(1, ["entity:a-body", "entity:a-face", "entity:a-mark"], (-0.72, 0.18)),
        group(2, ["entity:b-body", "entity:b-face", "entity:b-mark"], (0.72, 0.18)),
        group(3, ["entity:signal-left", "entity:signal-right"], (0, -0.83)),
        group(4, ["entity:overlay-top", "entity:overlay-bottom"], (0, 0)),
    ]
    ticks = [0, 24, 48, 72, 96, 120, 144, 168, 192]

    def keys(values: list[int | float]) -> list[tuple[int, int | float]]:
        return list(zip(ticks, values, strict=True))

    animation = [
        numeric_track(
            groups[0]["id"], "translate.x", keys([0, 0.18, 0.6, 0.12, 0.82, 0.3, 0.62, 0.08, 0])
        ),
        numeric_track(
            groups[0]["id"],
            "translate.y",
            keys([0, -0.08, 0.02, 0.12, -0.05, 0.08, -0.02, 0.04, 0]),
        ),
        numeric_track(groups[0]["id"], "rotation_degrees", keys([0, -5, 4, -3, -8, 5, -4, 2, 0])),
        numeric_track(
            groups[0]["id"], "scale", keys([1, 1.08, 1.28, 0.94, 1.15, 1.02, 1.22, 0.98, 1])
        ),
        numeric_track(
            groups[1]["id"],
            "translate.x",
            keys([0, -0.14, -0.52, -0.08, -0.78, -0.24, -0.58, -0.06, 0]),
        ),
        numeric_track(
            groups[1]["id"], "translate.y", keys([0, 0.06, -0.04, 0.1, 0.02, -0.09, 0.04, -0.03, 0])
        ),
        numeric_track(groups[1]["id"], "rotation_degrees", keys([0, 4, -5, 3, 8, -4, 5, -2, 0])),
        numeric_track(
            groups[1]["id"], "scale", keys([1, 0.96, 1.2, 1.06, 1.12, 1.25, 0.97, 1.08, 1])
        ),
        numeric_track(
            groups[2]["id"],
            "translate.y",
            keys([0, -0.08, 0.07, -0.04, 0.09, -0.06, 0.08, -0.03, 0]),
        ),
        numeric_track(
            groups[2]["id"], "rotation_degrees", keys([0, 25, -32, 42, -48, 38, -28, 18, 0])
        ),
        numeric_track(
            groups[2]["id"], "scale", keys([1, 1.4, 0.78, 1.5, 0.86, 1.42, 0.82, 1.3, 1])
        ),
        numeric_track(groups[3]["id"], "rotation_degrees", keys([0, 1, -1, 2, -2, 1, -1, 2, 0])),
        numeric_track(
            groups[3]["id"], "scale", keys([1, 1.03, 0.98, 1.05, 0.96, 1.04, 0.98, 1.02, 1])
        ),
        style_track(
            "entity:background",
            "fill",
            [(0, "#171427"), (48, "#2B1746"), (96, "#102F34"), (144, "#3B1837"), (168, "#171427")],
        ),
        style_track(
            "entity:a-body",
            "fill",
            [(0, "#7C5CFC"), (48, "#FF6B8A"), (96, "#56C596"), (144, "#F7C948"), (168, "#7C5CFC")],
        ),
        style_track(
            "entity:b-body",
            "fill",
            [(0, "#56C596"), (48, "#F7C948"), (96, "#7C5CFC"), (144, "#FF6B8A"), (168, "#56C596")],
        ),
        style_track(
            "entity:halo",
            "opacity",
            [
                (0, 0.3),
                (24, 0.8),
                (48, 0.25),
                (72, 0.9),
                (96, 0.35),
                (120, 0.85),
                (144, 0.3),
                (168, 0.75),
                (192, 0.3),
            ],
        ),
        style_track(
            "entity:flash",
            "opacity",
            [
                (0, 0),
                (46, 0),
                (48, 0.46),
                (51, 0),
                (94, 0),
                (96, 0.6),
                (99, 0),
                (142, 0),
                (144, 0.5),
                (147, 0),
                (192, 0),
            ],
        ),
        style_track(
            "entity:overlay-top",
            "fill",
            [(0, "#FF6B8A"), (48, "#56C596"), (96, "#F7C948"), (144, "#7C5CFC")],
        ),
        style_track(
            "entity:overlay-bottom",
            "fill",
            [(0, "#56C596"), (48, "#7C5CFC"), (96, "#FF6B8A"), (144, "#F7C948")],
        ),
    ]
    return {
        "schema_version": "0.1",
        "semantics_version": "svm-core-0.1",
        "document_id": "document:authoring-ground-truth-demo-002",
        "references": [
            {
                "id": ARTIFACT_ID,
                "uri": ARTIFACT_ID.replace(":", "://", 1),
                "content_hash": "sha256:" + "b" * 64,
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
            "semantics_version": "svm-motion@0.5",
            "timebase": {"ticks_per_second": FPS},
            "content": animation,
            "construction_scheduling_hints": [],
        },
    }


def encode(output: Path) -> None:
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
            str(PNG_FRAMES / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
    )


def rasterize_frames() -> None:
    candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    )
    browser = next((item for item in candidates if item.is_file()), None)
    if browser is None:
        raise RuntimeError("Edge or Chrome is required to rasterize frames")
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
    rasterize_frames()
    encode(HERE / "demo.mp4")
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for tick in (0, 48, 96, 144, 192):
        shutil.copyfile(PNG_FRAMES / f"frame-{tick:04d}.png", PREVIEWS / f"frame-{tick:04d}.png")


if __name__ == "__main__":
    main()
