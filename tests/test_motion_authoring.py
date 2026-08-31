import json
import unittest
from pathlib import Path

from svm import (
    AddKeyframeChange,
    CreateTrackChange,
    GeneratorProvenance,
    MotionEvaluator,
    Proposal,
    ProposalAcceptor,
    ProposalPolicyError,
    RevisionStore,
    Transaction,
)
from svm.change_authority import resolve_transaction_intents

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "examples" / "018-anchored-regeneration.svm.json"
TRACK = "track:unrelated-x"
FIRST = "keyframe:unrelated-x-0000"
LAST = "keyframe:unrelated-x-0024"


class MotionAuthoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(STATIC.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        assert self.store.head is not None
        self.base_revision_id = self.store.head

    @staticmethod
    def create_transaction() -> Transaction:
        return Transaction(
            "transaction:create-unrelated-x-track",
            (
                CreateTrackChange(TRACK, "op:unrelated", "x", 24),
                AddKeyframeChange(TRACK, FIRST, 0, 1),
            ),
        )

    def test_track_and_initial_keyframe_are_created_atomically(self) -> None:
        revision = self.store.commit(self.base_revision_id, self.create_transaction())
        authored = self.store.get_document(revision.revision_id)
        animation = authored["animation"]
        self.assertEqual(animation["semantics_version"], "svm-motion@0.1")
        self.assertEqual(animation["timebase"], {"ticks_per_second": 24})
        self.assertEqual(animation["content"][0]["id"], TRACK)
        self.assertEqual(animation["content"][0]["keyframes"][0]["id"], FIRST)
        self.assertEqual(self.store.get_document(self.base_revision_id)["animation"]["content"], [])

    def test_second_keyframe_creates_playable_linear_motion_revision(self) -> None:
        first = self.store.commit(self.base_revision_id, self.create_transaction())
        second = self.store.commit(
            first.revision_id,
            Transaction(
                "transaction:add-unrelated-x-24",
                (AddKeyframeChange(TRACK, LAST, 24, 2),),
            ),
        )
        motion = MotionEvaluator(self.store.get_document(second.revision_id))
        operation = motion.sample_document(12)["construction"]["operations"][2]
        self.assertEqual(operation["parameters"]["x"], 1.5)
        self.assertEqual(
            [
                keyframe["id"]
                for keyframe in motion.document["animation"]["content"][0]["keyframes"]
            ],
            [FIRST, LAST],
        )

    def test_create_track_without_initial_keyframe_fails_atomically(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires Keyframes"):
            self.store.commit(
                self.base_revision_id,
                Transaction(
                    "transaction:empty-track", (CreateTrackChange(TRACK, "op:unrelated", "x", 24),)
                ),
            )
        self.assertEqual(len(self.store.revisions), 1)

    def test_authoring_changes_have_exact_closed_world_impacts(self) -> None:
        intents = resolve_transaction_intents(self.create_transaction())
        self.assertEqual(
            intents,
            (
                ("create_track", "op:unrelated", "x"),
                ("add_keyframe", TRACK, FIRST),
            ),
        )

    def test_create_track_permission_is_enforced_at_proposal_acceptance(self) -> None:
        protected = json.loads(STATIC.read_text(encoding="utf-8"))
        protected["edit_permissions"].append(
            {
                "id": "permission:no-motion-authoring",
                "actor": "editor:motion-timeline",
                "effect": "deny",
                "actions": ["create_track"],
                "targets": ["op:unrelated"],
            }
        )
        store = RevisionStore.create(protected)
        assert store.head is not None
        proposal = Proposal(
            "proposal:create-unrelated-x-track",
            store.head,
            GeneratorProvenance(
                "editor:motion-timeline", "0.3", "svm-core", "svm-document-editor@0.3"
            ),
            self.create_transaction(),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "denies editor:motion-timeline"):
            ProposalAcceptor().accept(store, proposal)
        self.assertEqual(len(store.revisions), 1)


if __name__ == "__main__":
    unittest.main()
