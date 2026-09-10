from __future__ import annotations

import copy
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from svm import (
    AddKeyframeChange,
    CreateCameraTransformTrackChange,
    Evaluator,
    MotionEvaluator,
    RevisionStore,
    Transaction,
    build_evaluated_scene,
)
from svm.renderers import SVGRenderer

ROOT = Path(__file__).resolve().parents[1]


def camera_document() -> dict:
    document = json.loads((ROOT / "examples/001-head-basic.svm.json").read_text())
    document["presentation"]["camera"] = {"position": [1, 2], "rotation_degrees": 90, "scale": 2}
    return document


class CameraMotionTest(unittest.TestCase):
    def test_camera_is_one_outer_view_transform_without_geometry_rewrite(self) -> None:
        document = camera_document()
        plain = copy.deepcopy(document)
        del plain["presentation"]["camera"]
        before = build_evaluated_scene(plain, Evaluator(plain))
        scene = build_evaluated_scene(document, Evaluator(document))
        self.assertEqual(scene.camera_transform, (0.0, -2.0, 2.0, 0.0, -4.0, 2.0))
        self.assertEqual(
            [item.geometry_value_id for item in scene.entities],
            [item.geometry_value_id for item in before.entities],
        )
        root = ET.fromstring(SVGRenderer().render(scene))
        stack = next(
            node for node in root.iter() if node.attrib.get("data-svm-role") == "render-stack"
        )
        self.assertEqual(stack.attrib["transform"], "matrix(0 -2 2 0 -4 2)")

    def test_camera_track_authors_and_samples_existing_numeric_semantics(self) -> None:
        document = camera_document()
        store = RevisionStore.create(document)
        assert store.head is not None
        revision = store.commit(
            store.head,
            Transaction(
                "transaction:camera-scale",
                (
                    CreateCameraTransformTrackChange(
                        "track:camera-scale", "scale", 24, "ease-in-out"
                    ),
                    AddKeyframeChange("track:camera-scale", "keyframe:camera-scale-0000", 0, 1),
                    AddKeyframeChange("track:camera-scale", "keyframe:camera-scale-0024", 24, 2),
                ),
            ),
        )
        accepted = store.get_document(revision.revision_id)
        self.assertEqual(accepted["animation"]["semantics_version"], "svm-motion@0.6")
        self.assertEqual(
            MotionEvaluator(accepted).sample_document(12)["presentation"]["camera"]["scale"], 1.5
        )
        self.assertEqual(document["presentation"]["camera"]["scale"], 2)

    def test_invalid_camera_and_nonpositive_sample_fail_closed(self) -> None:
        invalid = camera_document()
        invalid["presentation"]["camera"]["scale"] = 0
        with self.assertRaisesRegex(ValueError, "scale must be finite and positive"):
            RevisionStore.create(invalid)
        document = camera_document()
        document["animation"] = {
            "semantics_version": "svm-motion@0.6",
            "timebase": {"ticks_per_second": 24},
            "content": [
                {
                    "id": "track:camera-scale",
                    "target": {"camera": "presentation", "property": "scale"},
                    "value_type": "number",
                    "interpolation": "linear",
                    "keyframes": [{"id": "keyframe:bad", "tick": 0, "value": 0}],
                }
            ],
            "construction_scheduling_hints": [],
        }
        with self.assertRaisesRegex(ValueError, "requires positive scale"):
            RevisionStore.create(document)


if __name__ == "__main__":
    unittest.main()
