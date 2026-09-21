from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import jsonschema

from svm import MotionEvaluator, RevisionStore
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "027-integrated-animation"
DOCUMENT = DEMO / "demo-002.svm.json"
SCHEMA = ROOT / "schema" / "svm-document-v0.1.schema.json"
SNAPSHOT_TICKS = (0, 12, 24, 36, 48, 60, 72)
GROUP_ID = "group:" + "1" * 64


def load_demo() -> dict:
    return json.loads(DOCUMENT.read_text(encoding="utf-8"))


def group_transform(document: dict) -> dict:
    return next(group for group in document["groups"] if group["id"] == GROUP_ID)["transform"]


def style(document: dict, entity_id: str) -> dict:
    return next(item for item in document["presentation"]["styles"] if item["entity"] == entity_id)


class Demo002IntegratedAnimationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = load_demo()
        self.motion = MotionEvaluator(self.document)
        self.renderer = SVGRenderer(
            SVGRenderOptions(width=960, height=480, view_box=(-60, -40, 240, 120))
        )

    def test_demo_is_schema_valid_and_loads_as_six_second_motion(self) -> None:
        jsonschema.validate(
            self.document,
            json.loads(SCHEMA.read_text(encoding="utf-8")),
        )
        store = RevisionStore.create(self.document)
        self.assertIsNotNone(store.head)
        self.assertEqual(self.motion.ticks_per_second, 12)
        self.assertEqual(
            max(k["tick"] for t in self.document["animation"]["content"] for k in t["keyframes"]),
            72,
        )

    def test_start_mid_and_end_poses_compose_all_authored_tracks(self) -> None:
        start = self.motion.sample_document(0)
        middle = self.motion.sample_document(36)
        end = self.motion.sample_document(72)
        self.assertEqual(group_transform(start)["translate"], [0, 0])
        self.assertEqual(group_transform(start)["rotation_degrees"], 0)
        self.assertEqual(group_transform(start)["scale"], 1)
        self.assertEqual(style(start, "entity:demo-accent")["opacity"], 0)
        self.assertEqual(
            start["presentation"]["camera"], {"position": [0, 0], "rotation_degrees": 0, "scale": 1}
        )

        self.assertEqual(group_transform(middle)["translate"], [85, -12])
        self.assertEqual(group_transform(middle)["rotation_degrees"], 30)
        self.assertEqual(group_transform(middle)["scale"], 1.2)
        self.assertEqual(style(middle, "entity:demo-accent")["opacity"], 1)
        self.assertEqual(style(middle, "entity:demo-body")["fill"], "#FF8C42")
        self.assertEqual(middle["presentation"]["camera"]["position"], [5, 0])
        self.assertEqual(middle["presentation"]["camera"]["scale"], 1.05)

        self.assertEqual(group_transform(end)["translate"], [115, 0])
        self.assertEqual(group_transform(end)["rotation_degrees"], 0)
        self.assertEqual(group_transform(end)["scale"], 1)
        self.assertEqual(style(end, "entity:demo-accent")["opacity"], 0)
        self.assertEqual(style(end, "entity:demo-body")["fill"], "#56C596")
        self.assertEqual(end["presentation"]["camera"]["position"], [10, 0])
        self.assertEqual(end["presentation"]["camera"]["scale"], 1.1)

    def test_between_keyframe_easing_differs_from_linear_track(self) -> None:
        sampled = self.motion.sample_document(18)
        transform = group_transform(sampled)
        self.assertEqual(transform["translate"][0], 17.5)
        self.assertEqual(transform["translate"][1], -6)
        self.assertEqual(transform["rotation_degrees"], 4.6875)
        self.assertEqual(transform["scale"], 1.03125)
        self.assertNotEqual(transform["translate"][0], 25)

    def test_group_style_and_camera_compose_without_rewriting_geometry(self) -> None:
        scene = self.motion.evaluate(36).scene
        entities = {item.entity_id: item for item in scene.entities}
        body = entities["entity:demo-body"]
        accent = entities["entity:demo-accent"]
        self.assertEqual(body.geometry["kind"], "transform")
        self.assertEqual(accent.geometry["kind"], "transform")
        self.assertEqual(body.geometry["matrix"], accent.geometry["matrix"])
        self.assertEqual(body.style.fill, "#FF8C42")
        self.assertEqual(accent.style.opacity, 1)
        self.assertIsNotNone(scene.camera_transform)
        self.assertEqual(body.geometry["source"]["kind"], "rectangle")
        self.assertEqual(accent.geometry["source"]["kind"], "rectangle")

    def test_sampling_preserves_authored_structure_and_is_deterministic(self) -> None:
        original = copy.deepcopy(self.document)
        for tick in (0, 18, 36, 54, 72):
            first = self.motion.sample_document(tick)
            second = self.motion.sample_document(tick)
            self.assertEqual(first, second)
            self.assertEqual(first["entities"], original["entities"])
            self.assertEqual(first["construction"], original["construction"])
            self.assertEqual(
                first["presentation"]["render_stack"],
                original["presentation"]["render_stack"],
            )
            self.assertEqual(first["groups"][0]["members"], original["groups"][0]["members"])
            self.assertEqual(
                self.renderer.render(self.motion.evaluate(tick).scene),
                self.renderer.render(self.motion.evaluate(tick).scene),
            )
        self.assertEqual(self.document, original)

    def test_json_round_trip_preserves_key_samples(self) -> None:
        reloaded = json.loads(json.dumps(self.document, sort_keys=True))
        round_trip = MotionEvaluator(reloaded)
        for tick in (0, 18, 36, 54, 72):
            self.assertEqual(round_trip.sample_document(tick), self.motion.sample_document(tick))

    def test_checked_in_svg_snapshots_match_real_motion_pipeline(self) -> None:
        for tick in SNAPSHOT_TICKS:
            with self.subTest(tick=tick):
                expected = (DEMO / "frames" / f"frame_{tick:03d}.svg").read_text(encoding="utf-8")
                actual = self.renderer.render(self.motion.evaluate(tick).scene)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
