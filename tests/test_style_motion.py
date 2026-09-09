from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from svm import (
    STYLE_MOTION_SEMANTICS_IDENTITY,
    AddKeyframeChange,
    CreateStyleTrackChange,
    MotionEvaluator,
    RevisionStore,
    SetKeyframeValueChange,
    Transaction,
)
from svm.change_authority import resolve_transaction_intents

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "026-style-opacity-motion.svm.json"
STATIC = ROOT / "examples" / "001-head-basic.svm.json"


class StyleMotionV0Test(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_opacity_eases_and_fill_holds_at_recorded_boundaries(self) -> None:
        motion = MotionEvaluator(self.document)
        self.assertEqual(
            [
                motion.sample_document(tick)["presentation"]["styles"][0]["fill"]
                for tick in (0, 23, 24, 47, 48)
            ],
            ["#7C5CFC", "#7C5CFC", "#56C596", "#56C596", "#FF6B8A"],
        )
        self.assertEqual(motion.sample_document(6)["presentation"]["styles"][0]["opacity"], 0.6)

    def test_sampling_is_ephemeral_and_reuses_static_geometry(self) -> None:
        before = copy.deepcopy(self.document)
        motion = MotionEvaluator(self.document)
        purple = motion.evaluate(0)
        green = motion.evaluate(24)
        self.assertEqual(self.document, before)
        self.assertEqual(
            purple.scene.entities[0].geometry_value_id, green.scene.entities[0].geometry_value_id
        )
        assert purple.scene.entities[0].style is not None
        assert green.scene.entities[0].style is not None
        self.assertEqual(purple.scene.entities[0].style.fill, "#7C5CFC")
        self.assertEqual(green.scene.entities[0].style.fill, "#56C596")
        self.assertEqual(green.scene.entities[0].style.opacity, 0.4)

    def test_style_tracks_are_authored_atomically_with_explicit_authority(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))
        transaction = Transaction(
            "transaction:create-style-tracks",
            (
                CreateStyleTrackChange(
                    "track:head-opacity", "entity:head", "opacity", 24, "ease-in-out"
                ),
                AddKeyframeChange("track:head-opacity", "keyframe:head-opacity-0000", 0, 1),
                CreateStyleTrackChange("track:head-fill", "entity:head", "fill", 24),
                AddKeyframeChange("track:head-fill", "keyframe:head-fill-0000", 0, "#F2C6A0"),
            ),
        )
        self.assertEqual(
            resolve_transaction_intents(transaction),
            (
                ("create_style_track", "entity:head", "opacity"),
                ("add_keyframe", "track:head-opacity", "keyframe:head-opacity-0000"),
                ("create_style_track", "entity:head", "fill"),
                ("add_keyframe", "track:head-fill", "keyframe:head-fill-0000"),
            ),
        )
        store = RevisionStore.create(document)
        assert store.head is not None
        revision = store.commit(store.head, transaction)
        accepted = store.get_document(revision.revision_id)
        self.assertEqual(
            accepted["animation"]["semantics_version"], STYLE_MOTION_SEMANTICS_IDENTITY
        )
        self.assertEqual(
            [track["interpolation"] for track in accepted["animation"]["content"]],
            ["ease-in-out", "hold"],
        )
        self.assertEqual(document["animation"]["content"], [])

    def test_invalid_style_track_combinations_fail_closed(self) -> None:
        cases = []
        outside = copy.deepcopy(self.document)
        outside["animation"]["content"][0]["keyframes"][0]["value"] = 1.1
        cases.append((outside, "opacity must be between"))
        bad_color = copy.deepcopy(self.document)
        bad_color["animation"]["content"][1]["keyframes"][0]["value"] = "purple"
        cases.append((bad_color, "recorded value type"))
        lerped_fill = copy.deepcopy(self.document)
        lerped_fill["animation"]["content"][1]["interpolation"] = "linear"
        cases.append((lerped_fill, "invalid fill Track semantics"))
        old = copy.deepcopy(self.document)
        old["animation"]["semantics_version"] = "svm-motion@0.4"
        cases.append((old, "requires Style Motion semantics"))
        for candidate, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                RevisionStore.create(candidate)

    def test_hold_keyframe_edit_invalidates_only_its_hold_interval(self) -> None:
        runtime = MotionEvaluator(self.document)
        ticks = (0, 23, 24, 47, 48)
        cached = {tick: runtime.evaluate(tick) for tick in ticks}
        interval = runtime.set_keyframe_value(
            "track:accent-fill", "keyframe:accent-fill-0024", "#112233"
        )
        assert interval is not None
        self.assertEqual((interval.start_tick, interval.end_tick), (24, 47))
        for tick in (0, 23, 48):
            self.assertIs(runtime.frame_cache[(tick, cached[tick].scene.quality)], cached[tick])
        for tick in (24, 47):
            self.assertNotIn((tick, cached[tick].scene.quality), runtime.frame_cache)

        store = RevisionStore.create(self.document)
        assert store.head is not None
        revision = store.commit(
            store.head,
            Transaction(
                "transaction:edit-held-fill",
                (
                    SetKeyframeValueChange(
                        "track:accent-fill", "keyframe:accent-fill-0024", "#112233"
                    ),
                ),
            ),
        )
        previous = MotionEvaluator(self.document)
        previous_cached = {tick: previous.evaluate(tick) for tick in ticks}
        successor, deltas = previous.transition_to_revision(
            store.get_document(revision.revision_id)
        )
        self.assertEqual(
            [(item.interval.start_tick, item.interval.end_tick) for item in deltas], [(24, 47)]
        )
        for tick in (0, 23, 48):
            self.assertIs(
                successor.frame_cache[(tick, previous_cached[tick].scene.quality)],
                previous_cached[tick],
            )
        for tick in (24, 47):
            self.assertNotIn((tick, previous_cached[tick].scene.quality), successor.frame_cache)


if __name__ == "__main__":
    unittest.main()
