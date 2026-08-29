import copy
import json
import unittest
from pathlib import Path

from svm import Evaluator, RevisionStore, SplitEntityChange, SplitPart, Transaction
from svm.evaluator import DocumentError


ROOT = Path(__file__).resolve().parents[1]


def split_transaction(*, face_id: str = "entity:face") -> Transaction:
    return Transaction(
        transaction_id="transaction:split-head",
        message="Split Head into Face and Hair",
        changes=(
            SplitEntityChange(
                source_entity_id="entity:head",
                operation_id="op:split_head",
                parts=(
                    SplitPart(face_id, "Face", "face_geometry", {"region": "lower"}),
                    SplitPart("entity:hair", "Hair", "hair_geometry", {"region": "upper"}),
                ),
            ),
        ),
    )


class GoldenTestB(unittest.TestCase):
    def setUp(self) -> None:
        self.original = json.loads(
            (ROOT / "examples" / "003-split-head.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(self.original)
        self.initial_revision_id = self.store.head

    def test_split_is_atomic_revision_with_stable_parent_identity(self) -> None:
        revision = self.store.commit(self.initial_revision_id, split_transaction())
        split_document = self.store.checkout(revision.revision_id)

        entities = {entity["id"]: entity for entity in split_document["entities"]}
        self.assertIn("entity:head", entities)
        self.assertEqual(entities["entity:face"]["parent_id"], "entity:head")
        self.assertEqual(entities["entity:hair"]["parent_id"], "entity:head")
        self.assertEqual(
            split_document["presentation"]["render_stack"],
            ["entity:face", "entity:hair", "entity:shield"],
        )

        bindings = {
            (binding["entity"], binding["property"]): binding["slot"]
            for binding in split_document["construction"]["output_bindings"]
        }
        self.assertEqual(bindings[("entity:head", "geometry")], "op:head_base.geometry")
        self.assertEqual(bindings[("entity:face", "geometry")], "op:split_head.face_geometry")
        self.assertEqual(bindings[("entity:hair", "geometry")], "op:split_head.hair_geometry")
        self.assertNotEqual(bindings[("entity:head", "geometry")], bindings[("entity:face", "geometry")])

        evaluator = Evaluator(split_document)
        evaluator.evaluate("op:split_head")
        face_value = evaluator.runtime["op:split_head"].outputs["face_geometry"]
        hair_value = evaluator.runtime["op:split_head"].outputs["hair_geometry"]
        self.assertNotEqual(face_value.value_id, hair_value.value_id)

        old_document = self.store.checkout(self.initial_revision_id)
        self.assertEqual(old_document, self.original)
        self.assertEqual([entity["id"] for entity in old_document["entities"]], ["entity:head", "entity:shield"])

        self.store.checkout(revision.revision_id)
        undone = self.store.undo()
        self.assertEqual(undone, self.original)
        self.assertEqual(self.store.head, self.initial_revision_id)

    def test_failed_transaction_does_not_commit_partial_changes(self) -> None:
        revision_count = len(self.store.revisions)
        head_before = self.store.head
        document_before = copy.deepcopy(self.store.checkout(self.initial_revision_id))

        with self.assertRaises(DocumentError):
            self.store.commit(
                self.initial_revision_id,
                split_transaction(face_id="entity:shield"),
            )

        self.assertEqual(len(self.store.revisions), revision_count)
        self.assertEqual(self.store.head, head_before)
        self.assertEqual(self.store.checkout(self.initial_revision_id), document_before)


if __name__ == "__main__":
    unittest.main()

