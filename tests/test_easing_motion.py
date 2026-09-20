from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import jsonschema

from svm import (
    EASING_MOTION_SEMANTICS_IDENTITY,
    AddKeyframeChange,
    CreateGroupTransformTrackChange,
    CreateTrackChange,
    MotionEvaluator,
    RevisionStore,
    Transaction,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "025-easing-motion.svm.json"
STATIC_GROUP = ROOT / "examples" / "022-group-transform.svm.json"
STATIC_OPERATION = ROOT / "examples" / "018-anchored-regeneration.svm.json"
GROUP_MOTION = ROOT / "examples" / "023-group-transform-motion.svm.json"
SCHEMA = ROOT / "schema" / "svm-document-v0.1.schema.json"
GROUP_ID = "group:" + "1" * 64


class EasingMotionV0Test(unittest.TestCase):
    def test_smoothstep_samples_exact_quarters_and_endpoints(self) -> None:
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        motion = MotionEvaluator(document)
        self.assertEqual(
            [
                motion.sample_document(tick)["groups"][0]["transform"]["translate"][0]
                for tick in range(5)
            ],
            [0, 15.625, 50, 84.375, 100],
        )

    def test_linear_remains_distinct_and_unchanged(self) -> None:
        eased = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        linear = copy.deepcopy(eased)
        linear["animation"]["content"][0]["interpolation"] = "linear"
        eased_motion = MotionEvaluator(eased)
        linear_motion = MotionEvaluator(linear)
        self.assertEqual(
            linear_motion.sample_document(1)["groups"][0]["transform"]["translate"][0], 25
        )
        self.assertEqual(
            eased_motion.sample_document(1)["groups"][0]["transform"]["translate"][0], 15.625
        )
        self.assertEqual(
            [
                linear_motion.sample_document(tick)["groups"][0]["transform"]["translate"][0]
                for tick in range(5)
            ],
            [0, 25, 50, 75, 100],
        )

    def test_missing_interpolation_is_schema_valid_and_defaults_to_linear(self) -> None:
        explicit = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        explicit["animation"]["content"][0]["interpolation"] = "linear"
        omitted = copy.deepcopy(explicit)
        omitted["animation"]["content"][0].pop("interpolation")
        jsonschema.validate(omitted, json.loads(SCHEMA.read_text(encoding="utf-8")))
        explicit_motion = MotionEvaluator(explicit)
        omitted_motion = MotionEvaluator(omitted)
        self.assertEqual(
            [
                explicit_motion.sample_document(tick)["groups"][0]["transform"]["translate"][0]
                for tick in range(5)
            ],
            [
                omitted_motion.sample_document(tick)["groups"][0]["transform"]["translate"][0]
                for tick in range(5)
            ],
        )
        self.assertNotIn("interpolation", omitted_motion.document["animation"]["content"][0])

    def test_group_numeric_properties_share_easing_and_keep_rotation_unwrapped(self) -> None:
        document = json.loads(GROUP_MOTION.read_text(encoding="utf-8"))
        document["animation"]["semantics_version"] = EASING_MOTION_SEMANTICS_IDENTITY
        values = {
            "translate.x": (0, 100, 50),
            "translate.y": (0, 100, 50),
            "rotation_degrees": (170, 190, 200),
            "scale": (1, 2, 3),
        }
        for track in document["animation"]["content"]:
            track["interpolation"] = "ease-in-out"
            property_name = track["target"]["property"]
            for keyframe, tick, value in zip(
                track["keyframes"], (0, 4, 8), values[property_name], strict=True
            ):
                keyframe["tick"] = tick
                keyframe["value"] = value
        motion = MotionEvaluator(document)
        quarter = motion.sample_document(1)["groups"][0]["transform"]
        midpoint = motion.sample_document(2)["groups"][0]["transform"]
        three_quarters = motion.sample_document(3)["groups"][0]["transform"]
        self.assertEqual(quarter["translate"], [15.625, 15.625])
        self.assertEqual(midpoint["translate"], [50, 50])
        self.assertEqual(three_quarters["translate"], [84.375, 84.375])
        self.assertEqual(quarter["scale"], 1.15625)
        self.assertEqual(midpoint["scale"], 1.5)
        self.assertEqual(quarter["rotation_degrees"], 173.125)
        self.assertEqual(midpoint["rotation_degrees"], 180)
        self.assertEqual(three_quarters["rotation_degrees"], 186.875)
        self.assertGreater(three_quarters["rotation_degrees"], 180)
        self.assertEqual(
            motion.sample_document(5)["groups"][0]["transform"]["translate"][0],
            92.1875,
        )
        self.assertEqual(motion.sample_document(0)["groups"][0]["transform"]["translate"][0], 0)
        self.assertEqual(motion.sample_document(100)["groups"][0]["transform"]["translate"][0], 50)
        first_segment = [
            motion.sample_document(tick)["groups"][0]["transform"]["translate"][0]
            for tick in range(5)
        ]
        self.assertEqual(first_segment, sorted(first_segment))
        round_tripped = json.loads(json.dumps(document, sort_keys=True))
        self.assertEqual(
            MotionEvaluator(round_tripped).sample_document(1), motion.sample_document(1)
        )

    def test_group_easing_track_is_authored_atomically(self) -> None:
        document = json.loads(STATIC_GROUP.read_text(encoding="utf-8"))
        store = RevisionStore.create(document)
        assert store.head is not None
        revision = store.commit(
            store.head,
            Transaction(
                "transaction:create-eased-group-track",
                (
                    CreateGroupTransformTrackChange(
                        "track:eased-group-x",
                        GROUP_ID,
                        "translate.x",
                        4,
                        interpolation="ease-in-out",
                    ),
                    AddKeyframeChange("track:eased-group-x", "keyframe:eased-x-0000", 0, 0),
                    AddKeyframeChange("track:eased-group-x", "keyframe:eased-x-0004", 4, 100),
                ),
            ),
        )
        accepted = store.get_document(revision.revision_id)
        self.assertEqual(
            accepted["animation"]["semantics_version"], EASING_MOTION_SEMANTICS_IDENTITY
        )
        self.assertEqual(accepted["animation"]["content"][0]["interpolation"], "ease-in-out")
        self.assertEqual(document["animation"]["content"], [])

    def test_operation_parameter_track_can_use_the_same_recorded_easing(self) -> None:
        document = json.loads(STATIC_OPERATION.read_text(encoding="utf-8"))
        store = RevisionStore.create(document)
        assert store.head is not None
        revision = store.commit(
            store.head,
            Transaction(
                "transaction:create-eased-operation-track",
                (
                    CreateTrackChange(
                        "track:eased-operation-x",
                        "op:unrelated",
                        "x",
                        4,
                        interpolation="ease-in-out",
                    ),
                    AddKeyframeChange(
                        "track:eased-operation-x", "keyframe:eased-operation-x-0000", 0, 1
                    ),
                    AddKeyframeChange(
                        "track:eased-operation-x", "keyframe:eased-operation-x-0004", 4, 101
                    ),
                ),
            ),
        )
        accepted = store.get_document(revision.revision_id)
        self.assertEqual(
            accepted["animation"]["semantics_version"], EASING_MOTION_SEMANTICS_IDENTITY
        )
        sampled = MotionEvaluator(accepted).sample_document(1)
        operation = next(
            item for item in sampled["construction"]["operations"] if item["id"] == "op:unrelated"
        )
        self.assertEqual(operation["parameters"]["x"], 16.625)

    def test_old_semantics_and_unknown_interpolation_fail_closed(self) -> None:
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        for semantics_version in ("svm-motion@0.1", "svm-motion@0.2", "svm-motion@0.3"):
            candidate = copy.deepcopy(document)
            candidate["animation"]["semantics_version"] = semantics_version
            with (
                self.subTest(semantics_version=semantics_version),
                self.assertRaisesRegex(ValueError, "unsupported value/interpolation"),
            ):
                RevisionStore.create(candidate)

        invalid_schema = copy.deepcopy(document)
        invalid_schema["animation"]["content"][0]["interpolation"] = "ease_magic"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid_schema, json.loads(SCHEMA.read_text(encoding="utf-8")))

        static = json.loads(STATIC_GROUP.read_text(encoding="utf-8"))
        store = RevisionStore.create(static)
        assert store.head is not None
        with self.assertRaisesRegex(ValueError, "unsupported interpolation"):
            store.commit(
                store.head,
                Transaction(
                    "transaction:unknown-easing",
                    (
                        CreateGroupTransformTrackChange(
                            "track:unknown-easing",
                            GROUP_ID,
                            "translate.x",
                            4,
                            interpolation="bounce",
                        ),
                        AddKeyframeChange("track:unknown-easing", "keyframe:unknown-0000", 0, 0),
                    ),
                ),
            )
        self.assertEqual(len(store.revisions), 1)


if __name__ == "__main__":
    unittest.main()
