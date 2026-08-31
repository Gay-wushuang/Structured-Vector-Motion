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
HEAD = ROOT / "examples" / "001-head-basic.svm.json"
MULTITRACK = ROOT / "examples" / "019-editor-multitrack.svm.json"
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
        self.assertEqual(animation["semantics_version"], "svm-motion@0.2")
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

    def test_numeric_parameter_without_animatable_declaration_is_rejected(self) -> None:
        document = json.loads(HEAD.read_text(encoding="utf-8"))
        store = RevisionStore.create(document)
        assert store.head is not None
        with self.assertRaisesRegex(ValueError, "is not animatable"):
            store.commit(
                store.head,
                Transaction(
                    "transaction:animate-refinement-tolerance",
                    (
                        CreateTrackChange(
                            "track:head-tolerance", "op:head_refine", "tolerance", 24
                        ),
                        AddKeyframeChange(
                            "track:head-tolerance", "keyframe:head-tolerance-0000", 0, 0.01
                        ),
                    ),
                ),
            )
        self.assertEqual(len(store.revisions), 1)

    def test_motion_validator_rejects_undeclared_numeric_target(self) -> None:
        document = json.loads(HEAD.read_text(encoding="utf-8"))
        document["animation"] = {
            "semantics_version": "svm-motion@0.2",
            "timebase": {"ticks_per_second": 24},
            "content": [
                {
                    "id": "track:head-tolerance",
                    "target": {"operation": "op:head_refine", "parameter": "tolerance"},
                    "value_type": "number",
                    "interpolation": "linear",
                    "keyframes": [{"id": "keyframe:head-tolerance-0000", "tick": 0, "value": 0.01}],
                }
            ],
            "construction_scheduling_hints": [],
        }
        with self.assertRaisesRegex(ValueError, "targets non-animatable parameter"):
            RevisionStore.create(document)

    def test_legacy_v01_numeric_target_remains_valid_under_its_recorded_identity(self) -> None:
        document = json.loads(HEAD.read_text(encoding="utf-8"))
        document["animation"] = {
            "semantics_version": "svm-motion@0.1",
            "timebase": {"ticks_per_second": 24},
            "content": [
                {
                    "id": "track:head-tolerance",
                    "target": {"operation": "op:head_refine", "parameter": "tolerance"},
                    "value_type": "number",
                    "interpolation": "linear",
                    "keyframes": [
                        {"id": "keyframe:head-tolerance-0000", "tick": 0, "value": 0.01},
                        {"id": "keyframe:head-tolerance-0024", "tick": 24, "value": 0.02},
                    ],
                }
            ],
            "construction_scheduling_hints": [],
        }
        store = RevisionStore.create(document)
        assert store.head is not None
        sampled = MotionEvaluator(store.get_document(store.head)).sample_document(12)
        operation = next(
            item for item in sampled["construction"]["operations"] if item["id"] == "op:head_refine"
        )
        self.assertEqual(operation["parameters"]["tolerance"], 0.015)

    def test_authoring_migrates_compatible_v01_tracks_to_v02_explicitly(self) -> None:
        document = json.loads(MULTITRACK.read_text(encoding="utf-8"))
        store = RevisionStore.create(document)
        assert store.head is not None
        revision = store.commit(
            store.head,
            Transaction(
                "transaction:add-v02-width-track",
                (
                    CreateTrackChange(
                        "track:moving-rectangle-width",
                        "op:moving-rectangle",
                        "width",
                        24,
                    ),
                    AddKeyframeChange(
                        "track:moving-rectangle-width",
                        "keyframe:moving-width-0000",
                        0,
                        40,
                    ),
                ),
            ),
        )
        self.assertEqual(
            store.get_document(revision.revision_id)["animation"]["semantics_version"],
            "svm-motion@0.2",
        )

    def test_authoring_rejects_incompatible_v01_migration_atomically(self) -> None:
        document = json.loads(HEAD.read_text(encoding="utf-8"))
        document["animation"] = {
            "semantics_version": "svm-motion@0.1",
            "timebase": {"ticks_per_second": 24},
            "content": [
                {
                    "id": "track:head-tolerance",
                    "target": {"operation": "op:head_refine", "parameter": "tolerance"},
                    "value_type": "number",
                    "interpolation": "linear",
                    "keyframes": [
                        {"id": "keyframe:head-tolerance-0000", "tick": 0, "value": 0.01},
                        {"id": "keyframe:head-tolerance-0024", "tick": 24, "value": 0.02},
                    ],
                }
            ],
            "construction_scheduling_hints": [],
        }
        store = RevisionStore.create(document)
        assert store.head is not None
        base_revision_id = store.head

        with self.assertRaisesRegex(ValueError, "targets non-animatable parameter"):
            store.commit(
                base_revision_id,
                Transaction(
                    "transaction:incompatible-v02-migration",
                    (
                        CreateTrackChange(
                            "track:head-rx",
                            "op:head_base",
                            "rx",
                            24,
                        ),
                        AddKeyframeChange(
                            "track:head-rx",
                            "keyframe:head-rx-0000",
                            0,
                            220,
                        ),
                    ),
                ),
            )

        self.assertEqual(store.head, base_revision_id)
        self.assertEqual(len(store.revisions), 1)
        self.assertEqual(
            store.get_document(base_revision_id)["animation"]["semantics_version"],
            "svm-motion@0.1",
        )

    def test_invalid_keyframe_endpoint_fails_without_revision(self) -> None:
        first = self.store.commit(
            self.base_revision_id,
            Transaction(
                "transaction:create-unrelated-width-track",
                (
                    CreateTrackChange("track:unrelated-width", "op:unrelated", "width", 24),
                    AddKeyframeChange(
                        "track:unrelated-width", "keyframe:unrelated-width-0000", 0, 0.2
                    ),
                ),
            ),
        )
        revision_count = len(self.store.revisions)
        with self.assertRaisesRegex(ValueError, "width and height must be greater than zero"):
            self.store.commit(
                first.revision_id,
                Transaction(
                    "transaction:invalid-width-endpoint",
                    (
                        AddKeyframeChange(
                            "track:unrelated-width", "keyframe:unrelated-width-0024", 24, -20
                        ),
                    ),
                ),
            )
        self.assertEqual(len(self.store.revisions), revision_count)

    def test_add_keyframe_permission_is_enforced_independently(self) -> None:
        first = self.store.commit(self.base_revision_id, self.create_transaction())
        protected = self.store.get_document(first.revision_id)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-new-keyframes",
                "actor": "editor:motion-timeline",
                "effect": "deny",
                "actions": ["add_keyframe"],
                "targets": [TRACK],
            }
        )
        store = RevisionStore.create(protected)
        assert store.head is not None
        proposal = Proposal(
            "proposal:add-denied-keyframe",
            store.head,
            GeneratorProvenance(
                "editor:motion-timeline", "0.3", "svm-core", "svm-document-editor@0.3"
            ),
            Transaction(
                "transaction:add-denied-keyframe",
                (AddKeyframeChange(TRACK, LAST, 24, 2),),
            ),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "denies editor:motion-timeline"):
            ProposalAcceptor().accept(store, proposal)
        self.assertEqual(len(store.revisions), 1)

    def test_existing_timebase_conflict_fails_atomically(self) -> None:
        document = json.loads(MULTITRACK.read_text(encoding="utf-8"))
        store = RevisionStore.create(document)
        assert store.head is not None
        with self.assertRaisesRegex(ValueError, "timebase conflicts"):
            store.commit(
                store.head,
                Transaction(
                    "transaction:conflicting-timebase",
                    (
                        CreateTrackChange(
                            "track:moving-rectangle-width",
                            "op:moving-rectangle",
                            "width",
                            1000,
                        ),
                        AddKeyframeChange(
                            "track:moving-rectangle-width",
                            "keyframe:moving-width-0000",
                            0,
                            40,
                        ),
                    ),
                ),
            )
        self.assertEqual(len(store.revisions), 1)


if __name__ == "__main__":
    unittest.main()
