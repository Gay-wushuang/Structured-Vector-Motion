from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

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
