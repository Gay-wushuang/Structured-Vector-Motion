from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from svm import MotionEvaluator  # noqa: E402
from svm.renderers import SVGRenderer, SVGRenderOptions  # noqa: E402

DIRECTORY = Path(__file__).resolve().parent
SOURCE = ROOT / "examples" / "028-synthetic-motion-recovery"
TICKS = (0, 12, 24, 36)
ANCHOR = "entity:camera-anchor"


def camera_track(property_name: str, values: tuple[float, ...]) -> dict:
    slug = property_name.replace(".", "-")
    return {
        "id": f"track:ground-truth-camera-{slug}",
        "target": {"camera": "presentation", "property": property_name},
        "value_type": "number",
        "interpolation": "linear",
        "keyframes": [
            {
                "id": f"keyframe:ground-truth-camera-{slug}-{tick:03d}",
                "tick": tick,
                "value": value,
            }
            for tick, value in zip(TICKS, values, strict=True)
        ],
    }


def add_anchor(document: dict) -> None:
    document["entities"].append({"id": ANCHOR, "name": "Static Camera Anchor"})
    document["construction"]["operations"].append(
        {
            "id": "op:camera-anchor",
            "type": "CreatePath",
            "inputs": {},
            "parameters": {
                "d": "M 105 35 L 137 38 L 132 66 L 119 55 L 103 62 Z",
                "bounds": [103, 35, 137, 66],
            },
        }
    )
    document["construction"]["output_bindings"].append(
        {"entity": ANCHOR, "property": "geometry", "slot": "op:camera-anchor.geometry"}
    )
    document["presentation"]["render_stack"].append(ANCHOR)
    document["presentation"]["styles"].append(
        {
            "entity": ANCHOR,
            "fill": "#238A72",
            "stroke": "none",
            "stroke_width": 0,
            "opacity": 1,
        }
    )


def build() -> tuple[dict, dict]:
    ground_truth = json.loads((SOURCE / "ground-truth.svm.json").read_text(encoding="utf-8"))
    recovery = json.loads((SOURCE / "recovery-base.svm.json").read_text(encoding="utf-8"))
    for document in (ground_truth, recovery):
        add_anchor(document)
    ground_truth["document_id"] = "document:synthetic-camera-compensation-ground-truth"
    recovery["document_id"] = "document:synthetic-camera-compensation-recovery-base"
    ground_truth["presentation"]["camera"] = {
        "position": [0, 0],
        "rotation_degrees": 0,
        "scale": 1,
    }
    ground_truth["animation"]["semantics_version"] = "svm-motion@0.6"
    target_end_values = {
        "track:ground-truth-translate-x": 38,
        "track:ground-truth-translate-y": 0,
        "track:ground-truth-rotation": 42,
        "track:ground-truth-scale": 1.1,
    }
    for track in ground_truth["animation"]["content"]:
        if track["id"] in target_end_values:
            track["keyframes"][-1]["value"] = target_end_values[track["id"]]
    ground_truth["animation"]["content"].extend(
        [
            camera_track("position.x", (0, 2, 4, 6)),
            camera_track("position.y", (0, -1, 1, 0)),
            camera_track("rotation_degrees", (0, 3, -2, 4)),
            camera_track("scale", (1, 1.03, 0.98, 1.04)),
        ]
    )
    recovery["presentation"]["camera"] = copy.deepcopy(ground_truth["presentation"]["camera"])
    return ground_truth, recovery


def main() -> None:
    ground_truth, recovery = build()
    for name, document in (
        ("ground-truth.svm.json", ground_truth),
        ("recovery-base.svm.json", recovery),
    ):
        (DIRECTORY / name).write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    observations = DIRECTORY / "observations"
    observations.mkdir(exist_ok=True)
    evaluator = MotionEvaluator(ground_truth)
    renderer = SVGRenderer(SVGRenderOptions(width=800, height=480, view_box=(0, 0, 200, 120)))
    for tick in TICKS:
        (observations / f"tick_{tick:03d}.svg").write_text(
            renderer.render(evaluator.evaluate(tick).scene), encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
