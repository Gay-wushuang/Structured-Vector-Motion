import json
import unittest
from pathlib import Path

from svm.editor_motion import EDITOR_IDENTITY, MotionEditorSession

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples" / "017-motion-rectangle.svm.json"


class RealMotionEditorVerticalSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.session = MotionEditorSession(document)

    def test_real_document_evaluator_and_renderer_supply_canvas_frame(self) -> None:
        state = self.session.state(250)
        self.assertEqual(state["editor_identity"], EDITOR_IDENTITY)
        self.assertEqual(state["document_id"], "document:golden-m-motion")
        self.assertEqual(state["revision"]["label"], "R0")
        self.assertEqual(state["frame"]["sampled_value"], 200)
        self.assertIn('data-svm-document="document:golden-m-motion"', state["frame"]["svg"])
        self.assertIn('data-svm-entity="entity:moving-rectangle"', state["frame"]["svg"])
        self.assertEqual(
            [entity["id"] for entity in state["structure"]],
            ["entity:moving-rectangle", "entity:static-rectangle"],
        )
        moving = state["structure"][0]
        self.assertEqual(moving["operation"]["id"], "op:moving-rectangle")
        self.assertEqual(moving["operation"]["parameters"]["x"], 100)
        self.assertEqual(moving["track_ids"], ["track:moving-rectangle-x"])
        self.assertEqual(state["structure"][1]["track_ids"], [])

    def test_preview_uses_real_transition_without_creating_revision(self) -> None:
        base_revision = self.session.head
        revision_count = len(self.session.store.revisions)
        state = self.session.preview(350, 250)
        self.assertTrue(state["preview"]["active"])
        self.assertEqual(state["preview"]["base_revision_id"], base_revision)
        self.assertEqual(state["revision"]["id"], base_revision)
        self.assertEqual(len(self.session.store.revisions), revision_count)
        self.assertEqual(state["frame"]["sampled_value"], 225)
        self.assertEqual(
            [(item["tick"], item["status"]) for item in state["cache"]],
            [
                (0, "reused"),
                (250, "reevaluated"),
                (500, "invalidated"),
                (750, "invalidated"),
                (1000, "reused"),
            ],
        )

    def test_commit_creates_real_child_revision_and_preserves_identity(self) -> None:
        base_state = self.session.state(500)
        base_revision = self.session.head
        self.session.preview(350, 500)
        committed = self.session.commit(350, 500)
        self.assertFalse(committed["preview"]["active"])
        self.assertNotEqual(committed["revision"]["id"], base_revision)
        self.assertEqual(committed["revision"]["parent_ids"], [base_revision])
        self.assertEqual(committed["revision"]["label"], "R1")
        self.assertEqual(committed["frame"]["sampled_value"], 350)
        self.assertEqual(committed["track"]["id"], base_state["track"]["id"])
        self.assertEqual(committed["target"], base_state["target"])
        revision = self.session.store.revisions[self.session.head]
        self.assertTrue(revision.transaction_id.startswith("transaction:motion-editor:commit:"))

    def test_checkout_parent_restores_old_revision_and_canvas(self) -> None:
        base_revision = self.session.head
        self.session.commit(350, 750)
        restored = self.session.checkout_parent(750)
        self.assertEqual(restored["revision"]["id"], base_revision)
        self.assertEqual(restored["revision"]["label"], "R0")
        self.assertEqual(restored["frame"]["sampled_value"], 400)
        self.assertFalse(restored["preview"]["active"])

    def test_noop_and_invalid_edits_fail_without_revision(self) -> None:
        revision_count = len(self.session.store.revisions)
        with self.assertRaisesRegex(ValueError, "must change"):
            self.session.commit(300, 500)
        with self.assertRaises(ValueError):
            self.session.preview(float("nan"), 500)
        self.assertEqual(len(self.session.store.revisions), revision_count)

    def test_editor_projection_preserves_untrusted_names_as_data(self) -> None:
        document = json.loads(GOLDEN.read_text(encoding="utf-8"))
        untrusted_name = "<img src=x onerror=\"fetch('/api/commit')\">"
        document["entities"][0]["name"] = untrusted_name
        state = MotionEditorSession(document).state(0)
        self.assertEqual(state["structure"][0]["name"], untrusted_name)

    def test_shell_uses_dom_text_nodes_for_document_projection(self) -> None:
        script = (ROOT / "editor" / "motion-timeline" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertIn("textContent", script)
        self.assertIn("replaceChildren", script)


if __name__ == "__main__":
    unittest.main()
