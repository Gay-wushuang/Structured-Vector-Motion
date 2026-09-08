from __future__ import annotations

import json
import unittest
from pathlib import Path

from svm import (
    GROUP_MOTION_SEMANTICS_IDENTITY,
    AddKeyframeChange,
    CreateGroupTransformTrackChange,
    Evaluator,
    GeneratorProvenance,
    MotionEvaluator,
    Proposal,
    ProposalAcceptor,
    RevisionStore,
    Transaction,
    build_evaluated_scene,
)
from svm.change_authority import resolve_transaction_intents

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "022-group-transform.svm.json"
MOTION_EXAMPLE = ROOT / "examples" / "023-group-transform-motion.svm.json"
GROUP_ID = "group:" + "1" * 64
PROPERTIES = {
    "translate.x": ("track:group-x", 2, 42),
    "translate.y": ("track:group-y", 3, -7),
    "rotation_degrees": ("track:group-rotation", 90, 4),
    "scale": ("track:group-scale", 2, 1.1),
}


def initial_tracks() -> Transaction:
    changes = []
    for property_name, (track_id, initial, _final) in PROPERTIES.items():
        changes.extend(
            (
                CreateGroupTransformTrackChange(track_id, GROUP_ID, property_name, 24),
                AddKeyframeChange(track_id, f"keyframe:{property_name}:0000", 0, initial),
            )
        )
    return Transaction("transaction:create-group-transform-tracks", tuple(changes))


def final_keyframes() -> Transaction:
    return Transaction(
        "transaction:add-group-transform-keyframes",
        tuple(
            AddKeyframeChange(track_id, f"keyframe:{property_name}:0024", 24, final)
            for property_name, (track_id, _initial, final) in PROPERTIES.items()
        ),
    )


class GroupTransformMotionSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        assert self.store.head is not None

    def test_four_group_tracks_are_authored_atomically_with_exact_authority(self) -> None:
        base_revision_id = self.store.head
        assert base_revision_id is not None
        transaction = initial_tracks()
        proposal = Proposal(
            "proposal:create-group-transform-tracks",
            base_revision_id,
            GeneratorProvenance("editor:group-motion", "0.1", "svm-core", "0.1"),
            transaction,
        )
        preview = ProposalAcceptor().validate(self.store, proposal)
        revision = ProposalAcceptor().accept(self.store, proposal)
        accepted = self.store.get_document(revision.revision_id)

        self.assertEqual(accepted, preview)
        self.assertEqual(
            accepted["animation"]["semantics_version"], GROUP_MOTION_SEMANTICS_IDENTITY
        )
        self.assertEqual(accepted["animation"]["timebase"], {"ticks_per_second": 24})
        self.assertEqual(len(accepted["animation"]["content"]), 4)
        for field in ("entities", "groups", "construction", "presentation", "references"):
            self.assertEqual(accepted[field], self.document[field])
        self.assertEqual(
            resolve_transaction_intents(transaction)[::2],
            tuple(
                ("create_group_transform_track", GROUP_ID, property_name)
                for property_name in PROPERTIES
            ),
        )

    def test_checked_in_motion_example_samples_recorded_one_second_pose(self) -> None:
        document = json.loads(MOTION_EXAMPLE.read_text(encoding="utf-8"))
        motion = MotionEvaluator(document)
        sampled = motion.sample_document(24)
        self.assertEqual(
            sampled["groups"][0]["transform"],
            {
                "translate": [40, -10],
                "rotation_degrees": 4,
                "scale": 1.1,
                "origin": [0, 0],
            },
        )
        self.assertEqual(motion.evaluate(24).seconds.numerator, 1)

    def test_sampling_changes_effective_group_transform_not_member_state(self) -> None:
        first = self.store.commit(self.store.head, initial_tracks())
        second = self.store.commit(first.revision_id, final_keyframes())
        animated = self.store.get_document(second.revision_id)
        motion = MotionEvaluator(animated)
        at_start = motion.evaluate(0)
        at_middle = motion.evaluate(12)
        at_end = motion.evaluate(24)

        middle_document = motion.sample_document(12)
        transform = middle_document["groups"][0]["transform"]
        self.assertEqual(transform["translate"], [22, -2])
        self.assertEqual(transform["rotation_degrees"], 47)
        self.assertEqual(transform["scale"], 1.55)
        self.assertEqual(transform["origin"], [0, 0])
        self.assertEqual(
            animated["groups"][0]["transform"], self.document["groups"][0]["transform"]
        )

        for entity_id in ("entity:hair", "entity:head", "entity:shield"):
            frames = [
                next(entity for entity in frame.scene.entities if entity.entity_id == entity_id)
                for frame in (at_start, at_middle, at_end)
            ]
            self.assertEqual(len({entity.geometry_value_id for entity in frames}), 1)
        start_head = next(
            entity for entity in at_start.scene.entities if entity.entity_id == "entity:head"
        )
        end_head = next(
            entity for entity in at_end.scene.entities if entity.entity_id == "entity:head"
        )
        self.assertNotEqual(start_head.geometry["matrix"], end_head.geometry["matrix"])
        self.assertEqual(at_end.seconds.numerator, 1)
        self.assertEqual(at_end.seconds.denominator, 1)
        self.assertTrue(at_middle.evaluator.runtime["op:head_base"].cache_hit)
        self.assertTrue(at_end.evaluator.runtime["op:head_base"].cache_hit)

        static_scene = build_evaluated_scene(self.document, Evaluator(self.document))
        static_shield = next(
            entity for entity in static_scene.entities if entity.entity_id == "entity:shield"
        )
        for frame in (at_start, at_middle, at_end):
            shield = next(
                entity for entity in frame.scene.entities if entity.entity_id == "entity:shield"
            )
            self.assertEqual(shield, static_shield)

    def test_invalid_targets_scale_and_partial_authoring_fail_atomically(self) -> None:
        assert self.store.head is not None
        with self.assertRaisesRegex(ValueError, "Unsupported Group Transform Track property"):
            self.store.commit(
                self.store.head,
                Transaction(
                    "transaction:animate-origin",
                    (
                        CreateGroupTransformTrackChange(
                            "track:group-origin-x", GROUP_ID, "origin.x", 24
                        ),
                        AddKeyframeChange("track:group-origin-x", "keyframe:origin:0000", 0, 0),
                    ),
                ),
            )
        with self.assertRaisesRegex(ValueError, "requires Keyframes"):
            self.store.commit(
                self.store.head,
                Transaction(
                    "transaction:empty-group-track",
                    (CreateGroupTransformTrackChange("track:empty", GROUP_ID, "scale", 24),),
                ),
            )
        with self.assertRaisesRegex(ValueError, "requires positive scale"):
            self.store.commit(
                self.store.head,
                Transaction(
                    "transaction:invalid-scale-track",
                    (
                        CreateGroupTransformTrackChange("track:bad-scale", GROUP_ID, "scale", 24),
                        AddKeyframeChange("track:bad-scale", "keyframe:bad-scale:0000", 0, 0),
                    ),
                ),
            )
        self.assertEqual(len(self.store.revisions), 1)


if __name__ == "__main__":
    unittest.main()
