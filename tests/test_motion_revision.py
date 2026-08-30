import json
import unittest
from pathlib import Path

from svm import (
    GeneratorProvenance,
    MotionEvaluator,
    Proposal,
    ProposalAcceptor,
    ProposalPolicyError,
    RevisionStore,
    SetKeyframeValueChange,
    Transaction,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples" / "017-motion-rectangle.svm.json"
TICKS = (0, 250, 500, 750, 1000)


def sampled_x(motion: MotionEvaluator, tick: int) -> int | float:
    return motion.sample_document(tick)["construction"]["operations"][0]["parameters"]["x"]


def value_id(motion: MotionEvaluator, tick: int, operation_id: str) -> str:
    return motion.evaluate(tick).evaluator.runtime[operation_id].outputs["geometry"].value_id


class MotionGoldenNTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document, "Golden N base")
        assert self.store.head is not None
        self.base_revision_id = self.store.head

    @staticmethod
    def transaction(value: int | float = 350) -> Transaction:
        return Transaction(
            transaction_id=f"transaction:set-middle-keyframe-{value}",
            changes=(
                SetKeyframeValueChange("track:moving-rectangle-x", "keyframe:moving-x-0500", value),
            ),
            message="Set middle motion Keyframe",
        )

    def test_golden_n_revision_transition_is_temporally_selective_and_undoable(self) -> None:
        old_document = self.store.get_document(self.base_revision_id)
        old_motion = MotionEvaluator(old_document)
        old_frames = {tick: old_motion.evaluate(tick) for tick in TICKS}
        old_static_ids = {tick: value_id(old_motion, tick, "op:static-rectangle") for tick in TICKS}
        old_moving_ids = {tick: value_id(old_motion, tick, "op:moving-rectangle") for tick in TICKS}

        revision = self.store.commit(self.base_revision_id, self.transaction())
        new_document = self.store.get_document(revision.revision_id)
        new_motion, deltas = old_motion.transition_to_revision(new_document)

        self.assertEqual(len(deltas), 1)
        delta = deltas[0]
        self.assertEqual(delta.track_id, "track:moving-rectangle-x")
        self.assertEqual(delta.keyframe_id, "keyframe:moving-x-0500")
        self.assertEqual((delta.interval.start_tick, delta.interval.end_tick), (1, 999))
        self.assertEqual([sampled_x(old_motion, tick) for tick in TICKS], [100, 200, 300, 400, 500])
        self.assertEqual([sampled_x(new_motion, tick) for tick in TICKS], [100, 225, 350, 425, 500])

        self.assertIs(new_motion.evaluate(0), old_frames[0])
        self.assertIs(new_motion.evaluate(1000), old_frames[1000])
        for tick in (250, 500, 750):
            self.assertIsNot(new_motion.evaluate(tick), old_frames[tick])
            self.assertNotEqual(
                value_id(new_motion, tick, "op:moving-rectangle"), old_moving_ids[tick]
            )
        for tick in TICKS:
            self.assertEqual(
                value_id(new_motion, tick, "op:static-rectangle"), old_static_ids[tick]
            )
        for tick in (0, 1000):
            self.assertEqual(
                value_id(new_motion, tick, "op:moving-rectangle"), old_moving_ids[tick]
            )

        self.assertEqual(
            [entity["id"] for entity in old_document["entities"]],
            [entity["id"] for entity in new_document["entities"]],
        )
        self.assertEqual(
            [operation["id"] for operation in old_document["construction"]["operations"]],
            [operation["id"] for operation in new_document["construction"]["operations"]],
        )
        old_track = old_document["animation"]["content"][0]
        new_track = new_document["animation"]["content"][0]
        self.assertEqual(old_track["id"], new_track["id"])
        self.assertEqual(
            [item["id"] for item in old_track["keyframes"]],
            [item["id"] for item in new_track["keyframes"]],
        )

        restored_document = self.store.undo(revision.revision_id)
        restored_motion, undo_deltas = new_motion.transition_to_revision(restored_document)
        self.assertEqual(len(undo_deltas), 1)
        self.assertEqual(
            [sampled_x(restored_motion, tick) for tick in TICKS], [100, 200, 300, 400, 500]
        )
        for tick in TICKS:
            self.assertEqual(
                value_id(restored_motion, tick, "op:moving-rectangle"), old_moving_ids[tick]
            )

    def test_change_is_atomic_and_rejects_missing_invalid_and_noop_edits(self) -> None:
        revision_count = len(self.store.revisions)
        cases = (
            SetKeyframeValueChange("track:missing", "keyframe:moving-x-0500", 350),
            SetKeyframeValueChange("track:moving-rectangle-x", "keyframe:missing", 350),
            SetKeyframeValueChange(
                "track:moving-rectangle-x", "keyframe:moving-x-0500", float("nan")
            ),
            SetKeyframeValueChange("track:moving-rectangle-x", "keyframe:moving-x-0500", 300.0),
        )
        for index, change in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.store.commit(
                    self.base_revision_id,
                    Transaction(f"transaction:invalid-motion-{index}", (change,)),
                )
        self.assertEqual(len(self.store.revisions), revision_count)
        self.assertEqual(
            self.store.get_document(self.base_revision_id)["animation"]["content"][0]["keyframes"][
                1
            ]["value"],
            300,
        )

    def test_change_authority_enforces_track_edit_permission(self) -> None:
        protected = self.store.get_document(self.base_revision_id)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-motion-edit",
                "actor": "adapter:timeline",
                "effect": "deny",
                "actions": ["set_keyframe_value"],
                "targets": ["track:moving-rectangle-x"],
            }
        )
        store = RevisionStore.create(protected)
        assert store.head is not None
        proposal = Proposal(
            proposal_id="proposal:set-middle-keyframe",
            base_revision_id=store.head,
            generator=GeneratorProvenance(
                adapter_id="adapter:timeline",
                adapter_version="0.1",
                engine="fixture",
                engine_version="1",
            ),
            transaction=self.transaction(),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "denies adapter:timeline"):
            ProposalAcceptor().accept(store, proposal)
        self.assertEqual(len(store.revisions), 1)

    def test_revision_transition_rejects_non_motion_document_changes(self) -> None:
        motion = MotionEvaluator(self.document)
        changed = json.loads(json.dumps(self.document))
        changed["construction"]["operations"][1]["parameters"]["x"] = 30
        with self.assertRaisesRegex(ValueError, "only Keyframe value changes"):
            motion.transition_to_revision(changed)


if __name__ == "__main__":
    unittest.main()
