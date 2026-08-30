import json
import unittest
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from svm import MotionEvaluator
from svm.document import validate_document
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples" / "017-motion-rectangle.svm.json"
SVG = SVGRenderer(SVGRenderOptions(width=600, height=100, view_box=(0, 0, 600, 100)))


def rectangle_x(svg: str, entity_id: str) -> float:
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    group = next(
        item
        for item in root.findall(".//svg:g", namespace)
        if item.get("data-svm-entity") == entity_id
    )
    rectangle = group.find("svg:rect", namespace)
    if rectangle is None:
        raise AssertionError(f"Missing rectangle for {entity_id}")
    return float(rectangle.attrib["x"])


class MotionGoldenMTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(GOLDEN.read_text(encoding="utf-8"))
        validate_document(self.document)

    def test_golden_m_samples_deterministic_frames_with_stable_identity(self) -> None:
        motion = MotionEvaluator(self.document)
        frames = [motion.evaluate(tick) for tick in (0, 250, 500, 750, 1000)]
        rendered = [SVG.render(frame.scene) for frame in frames]
        expected = [
            (ROOT / "examples" / "rendered" / f"017-motion-frame-{suffix}.svg").read_text(
                encoding="utf-8"
            )
            for suffix in ("0000", "0500", "1000")
        ]
        self.assertEqual([rendered[index] for index in (0, 2, 4)], expected)
        self.assertEqual(
            [rectangle_x(svg, "entity:moving-rectangle") for svg in rendered],
            [100.0, 200.0, 300.0, 400.0, 500.0],
        )
        self.assertEqual(
            [frame.seconds for frame in frames],
            [Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1)],
        )
        self.assertEqual(
            rendered,
            [SVG.render(motion.evaluate(tick).scene) for tick in (0, 250, 500, 750, 1000)],
        )
        self.assertEqual(
            [entity["id"] for entity in self.document["entities"]],
            ["entity:moving-rectangle", "entity:static-rectangle"],
        )
        self.assertEqual(
            [operation["id"] for operation in self.document["construction"]["operations"]],
            ["op:moving-rectangle", "op:static-rectangle"],
        )
        track = self.document["animation"]["content"][0]
        self.assertEqual(track["id"], "track:moving-rectangle-x")
        self.assertEqual(
            [keyframe["id"] for keyframe in track["keyframes"]],
            [
                "keyframe:moving-x-0000",
                "keyframe:moving-x-0500",
                "keyframe:moving-x-1000",
            ],
        )

    def test_static_subtree_reuses_content_cache_across_time(self) -> None:
        motion = MotionEvaluator(self.document)
        first = motion.evaluate(0)
        middle = motion.evaluate(500)
        final = motion.evaluate(1000)
        static_ids = [
            frame.evaluator.runtime["op:static-rectangle"].outputs["geometry"].value_id
            for frame in (first, middle, final)
        ]
        self.assertEqual(len(set(static_ids)), 1)
        self.assertFalse(first.evaluator.runtime["op:static-rectangle"].cache_hit)
        self.assertTrue(middle.evaluator.runtime["op:static-rectangle"].cache_hit)
        self.assertTrue(final.evaluator.runtime["op:static-rectangle"].cache_hit)
        moving_ids = [
            frame.evaluator.runtime["op:moving-rectangle"].outputs["geometry"].value_id
            for frame in (first, middle, final)
        ]
        self.assertEqual(len(set(moving_ids)), 3)

    def test_middle_keyframe_invalidates_only_temporally_affected_frames(self) -> None:
        motion = MotionEvaluator(self.document)
        before = {tick: motion.evaluate(tick) for tick in (0, 250, 500, 750, 1000)}
        interval = motion.set_keyframe_value(
            "track:moving-rectangle-x", "keyframe:moving-x-0500", 350
        )
        self.assertIsNotNone(interval)
        assert interval is not None
        self.assertEqual((interval.start_tick, interval.end_tick), (1, 999))
        self.assertIs(motion.evaluate(0), before[0])
        self.assertIs(motion.evaluate(1000), before[1000])
        for tick in (250, 500, 750):
            self.assertIsNot(motion.evaluate(tick), before[tick])
        changed_middle = motion.evaluate(500)
        self.assertEqual(
            rectangle_x(SVG.render(changed_middle.scene), "entity:moving-rectangle"),
            350.0,
        )
        self.assertEqual(
            changed_middle.evaluator.runtime["op:static-rectangle"].outputs["geometry"].value_id,
            before[500].evaluator.runtime["op:static-rectangle"].outputs["geometry"].value_id,
        )
        self.assertTrue(changed_middle.evaluator.runtime["op:static-rectangle"].cache_hit)

    def test_fractional_interpolation_and_numeric_canonicalization(self) -> None:
        thirds = json.loads(json.dumps(self.document))
        thirds["animation"]["content"][0]["keyframes"] = [
            {"id": "keyframe:zero", "tick": 0, "value": 0},
            {"id": "keyframe:one", "tick": 3, "value": 1},
        ]
        sampled = MotionEvaluator(thirds).sample_document(1)
        self.assertAlmostEqual(sampled["construction"]["operations"][0]["parameters"]["x"], 1 / 3)

        integer = json.loads(json.dumps(self.document))
        decimal = json.loads(json.dumps(self.document))
        decimal["animation"]["content"][0]["keyframes"][0]["value"] = 100.0
        integer_frame = MotionEvaluator(integer).evaluate(0)
        decimal_frame = MotionEvaluator(decimal).evaluate(0)
        self.assertEqual(
            integer_frame.evaluator.runtime["op:moving-rectangle"].outputs["geometry"].value_id,
            decimal_frame.evaluator.runtime["op:moving-rectangle"].outputs["geometry"].value_id,
        )

    def test_noop_keyframe_edit_preserves_all_frame_cache_entries(self) -> None:
        motion = MotionEvaluator(self.document)
        before = {tick: motion.evaluate(tick) for tick in (0, 250, 500, 750, 1000)}
        interval = motion.set_keyframe_value(
            "track:moving-rectangle-x", "keyframe:moving-x-0500", 300.0
        )
        self.assertIsNone(interval)
        self.assertEqual({key[0] for key in motion.frame_cache}, before.keys())
        for tick, frame in before.items():
            self.assertIs(motion.evaluate(tick), frame)

    def test_motion_validation_fails_closed(self) -> None:
        cases = (
            (
                "duplicate tick",
                lambda doc: doc["animation"]["content"][0]["keyframes"][1].update(tick=0),
            ),
            (
                "missing operation",
                lambda doc: doc["animation"]["content"][0]["target"].update(operation="op:missing"),
            ),
            (
                "unsupported interpolation",
                lambda doc: doc["animation"]["content"][0].update(interpolation="cubic"),
            ),
            (
                "missing motion semantics",
                lambda doc: doc["animation"].pop("semantics_version"),
            ),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                document = json.loads(json.dumps(self.document))
                mutate(document)
                with self.assertRaises(ValueError):
                    validate_document(document)


if __name__ == "__main__":
    unittest.main()
