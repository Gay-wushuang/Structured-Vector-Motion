import json
import re
import unittest
from pathlib import Path

from svm import DeterministicProposalProvider, ProposalCandidate
from svm.editor_motion import EDITOR_IDENTITY, DocumentEditorSession

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples" / "017-motion-rectangle.svm.json"
STATIC = ROOT / "examples" / "018-anchored-regeneration.svm.json"
MULTITRACK = ROOT / "examples" / "019-editor-multitrack.svm.json"
TRACK = "track:moving-rectangle-x"
KEYFRAME = "keyframe:moving-x-0500"


class RealMotionEditorVerticalSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.session = DocumentEditorSession(document)

    def test_real_document_evaluator_and_renderer_supply_canvas_frame(self) -> None:
        state = self.session.state(250)
        self.assertEqual(state["editor_identity"], EDITOR_IDENTITY)
        self.assertEqual(state["document_id"], "document:golden-m-motion")
        self.assertEqual(state["revision"]["label"], "R0")
        self.assertEqual(state["frame"]["effective_parameters"]["op:moving-rectangle"]["x"], 200)
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

    def test_motion_canvas_view_box_is_stable_across_sampled_time(self) -> None:
        start = self.session.state(0)["frame"]["svg"]
        end = self.session.state(1000)["frame"]["svg"]
        pattern = r'viewBox="([^"]+)"'
        self.assertEqual(re.search(pattern, start).group(1), re.search(pattern, end).group(1))

    def test_preview_uses_real_transition_without_creating_revision(self) -> None:
        base_revision = self.session.head
        revision_count = len(self.session.store.revisions)
        state = self.session.preview(TRACK, KEYFRAME, 350, 250)
        self.assertTrue(state["preview"]["active"])
        self.assertEqual(state["preview"]["base_revision_id"], base_revision)
        self.assertEqual(state["revision"]["id"], base_revision)
        self.assertEqual(len(self.session.store.revisions), revision_count)
        self.assertEqual(state["frame"]["effective_parameters"]["op:moving-rectangle"]["x"], 225)
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
        self.session.preview(TRACK, KEYFRAME, 350, 500)
        committed = self.session.commit(TRACK, KEYFRAME, 350, 500)
        self.assertFalse(committed["preview"]["active"])
        self.assertNotEqual(committed["revision"]["id"], base_revision)
        self.assertEqual(committed["revision"]["parent_ids"], [base_revision])
        self.assertEqual(committed["revision"]["label"], "R1")
        self.assertEqual(
            committed["frame"]["effective_parameters"]["op:moving-rectangle"]["x"], 350
        )
        self.assertEqual(committed["tracks"][0]["id"], base_state["tracks"][0]["id"])
        revision = self.session.store.revisions[self.session.head]
        self.assertTrue(revision.transaction_id.startswith("transaction:motion-editor:commit:"))

    def test_checkout_parent_restores_old_revision_and_canvas(self) -> None:
        base_revision = self.session.head
        self.session.commit(TRACK, KEYFRAME, 350, 750)
        restored = self.session.checkout_parent(750)
        self.assertEqual(restored["revision"]["id"], base_revision)
        self.assertEqual(restored["revision"]["label"], "R0")
        self.assertEqual(restored["frame"]["effective_parameters"]["op:moving-rectangle"]["x"], 400)
        self.assertFalse(restored["preview"]["active"])

    def test_noop_and_invalid_edits_fail_without_revision(self) -> None:
        revision_count = len(self.session.store.revisions)
        with self.assertRaisesRegex(ValueError, "must change"):
            self.session.commit(TRACK, KEYFRAME, 300, 500)
        with self.assertRaises(ValueError):
            self.session.preview(TRACK, KEYFRAME, float("nan"), 500)
        self.assertEqual(len(self.session.store.revisions), revision_count)

    def test_editor_projection_preserves_untrusted_names_as_data(self) -> None:
        document = json.loads(GOLDEN.read_text(encoding="utf-8"))
        untrusted_name = "<img src=x onerror=\"fetch('/api/commit')\">"
        document["entities"][0]["name"] = untrusted_name
        state = DocumentEditorSession(document).state(0)
        self.assertEqual(state["structure"][0]["name"], untrusted_name)

    def test_static_simple_document_uses_evaluator_and_reports_no_motion(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))
        session = DocumentEditorSession(document)
        state = session.state(999)
        self.assertEqual(state["document_id"], "document:golden-o-anchored-regeneration")
        self.assertEqual(state["tracks"], [])
        self.assertIsNone(state["timebase"])
        self.assertEqual(state["frame"]["tick"], 0)
        self.assertEqual(len(state["structure"]), 3)
        self.assertEqual(state["structure"][0]["animatable_parameters"], ["cx", "cy", "rx", "ry"])
        self.assertEqual(
            state["structure"][2]["animatable_parameters"],
            ["height", "width", "x", "y"],
        )
        self.assertIn('data-svm-entity="entity:eye-frame"', state["frame"]["svg"])
        with self.assertRaisesRegex(ValueError, "no editable Motion Track"):
            session.preview("track:missing", "keyframe:missing", 1, 0)

    def test_static_rectangle_can_author_a_real_motion_track_and_keyframes(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))
        session = DocumentEditorSession(document)
        base_revision = session.head
        tracked = session.create_track("op:unrelated", "x", 24)
        self.assertEqual(tracked["revision"]["label"], "R1")
        self.assertEqual(tracked["timebase"], {"ticks_per_second": 24})
        self.assertEqual(len(tracked["tracks"]), 1)
        track = tracked["tracks"][0]
        self.assertEqual(track["target"], {"operation": "op:unrelated", "parameter": "x"})
        self.assertEqual(track["keyframes"][0]["tick"], 0)
        self.assertEqual(track["keyframes"][0]["value"], 1)
        self.assertEqual(session.store.get_document(base_revision)["animation"]["content"], [])

        authored = session.add_keyframe(track["id"], 24, 2)
        self.assertEqual(authored["revision"]["label"], "R2")
        self.assertEqual([item["tick"] for item in authored["tracks"][0]["keyframes"]], [0, 24])
        middle = session.state(12)
        self.assertEqual(middle["frame"]["effective_parameters"]["op:unrelated"]["x"], 1.5)

        parent = session.checkout_parent(12)
        self.assertEqual(parent["revision"]["label"], "R1")
        self.assertEqual(len(parent["tracks"][0]["keyframes"]), 1)
        restored = session.checkout_parent(0)
        self.assertEqual(restored["revision"]["label"], "R0")
        self.assertEqual(restored["tracks"], [])

    def test_real_anchored_candidates_preview_without_creating_revision(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))
        session = DocumentEditorSession(document)
        base_revision = session.head
        generated = session.generate_anchored_candidates(["cx", "cy"])
        self.assertEqual(
            [candidate["id"] for candidate in generated["anchored_regeneration"]["candidates"]],
            ["A", "B", "C"],
        )
        self.assertEqual(len(session.store.revisions), 1)

        preview = session.preview_anchored_candidate("C")
        self.assertTrue(preview["preview"]["active"])
        self.assertEqual(preview["preview"]["kind"], "anchored")
        self.assertEqual(preview["preview"]["candidate_id"], "C")
        self.assertEqual(preview["preview"]["base_revision_id"], base_revision)
        self.assertEqual(preview["revision"]["id"], base_revision)
        self.assertEqual(len(session.store.revisions), 1)
        parameters = preview["frame"]["effective_parameters"]["op:eye-highlight"]
        self.assertEqual(parameters["cx"], 0.2)
        self.assertEqual(parameters["cy"], -0.1)
        self.assertEqual(
            session.store.get_document(base_revision)["construction"]["operations"][1][
                "parameters"
            ],
            {"cx": 0.12, "cy": -0.05, "rx": 0.08, "ry": 0.05},
        )
        cleared = session.clear_anchored_candidates()
        self.assertFalse(cleared["preview"]["active"])
        self.assertEqual(cleared["anchored_regeneration"]["candidates"], [])
        self.assertEqual(cleared["revision"]["id"], base_revision)
        self.assertEqual(len(session.store.revisions), 1)

    def test_editor_consumes_replaceable_proposal_provider(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))

        class RecordingProvider:
            def __init__(self) -> None:
                self.request = None
                self.contract = None

            def generate(self, request, contract, artifacts=None):
                self.request = request
                self.contract = contract
                generated = DeterministicProposalProvider().generate(request, contract, artifacts)
                return (ProposalCandidate("external-A", generated[0].proposal),)

        provider = RecordingProvider()
        session = DocumentEditorSession(document, proposal_provider=provider)
        base_revision = session.head
        state = session.generate_anchored_candidates(["cx"])

        self.assertEqual(
            [candidate["id"] for candidate in state["anchored_regeneration"]["candidates"]],
            ["external-A"],
        )
        self.assertEqual(provider.request.base_revision_id, base_revision)
        self.assertEqual(provider.request.scope, ("cx",))
        self.assertEqual(provider.request.document, session.store.get_document(base_revision))
        self.assertEqual(provider.contract.base_revision_id, base_revision)
        preview = session.preview_anchored_candidate("external-A")
        self.assertTrue(preview["preview"]["active"])
        self.assertEqual(len(session.store.revisions), 1)

    def test_real_anchored_acceptance_creates_sibling_revisions(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))
        session = DocumentEditorSession(document)
        base_revision = session.head
        session.generate_anchored_candidates(["cx", "cy"])

        first = session.accept_anchored_candidate("A")
        first_revision = first["revision"]["id"]
        self.assertEqual(first["revision"]["parent_ids"], [base_revision])
        self.assertEqual(first["revision"]["label"], "R1")

        preview = session.preview_anchored_candidate("B")
        self.assertEqual(preview["revision"]["id"], first_revision)
        self.assertEqual(preview["preview"]["base_revision_id"], base_revision)
        second = session.accept_anchored_candidate("B")
        second_revision = second["revision"]["id"]
        self.assertEqual(second["revision"]["parent_ids"], [base_revision])
        self.assertEqual(second["revision"]["label"], "R2")
        self.assertNotEqual(first_revision, second_revision)
        self.assertEqual(session.store.revisions[first_revision].parent_ids, (base_revision,))
        self.assertEqual(session.store.revisions[second_revision].parent_ids, (base_revision,))
        self.assertEqual(len(session.store.revisions), 3)
        self.assertEqual(
            {node["candidate_id"] for node in second["revision_graph"]},
            {None, "A", "B"},
        )

        with self.assertRaisesRegex(ValueError, "already accepted"):
            session.accept_anchored_candidate("A")
        self.assertEqual(len(session.store.revisions), 3)

    def test_anchored_scope_is_reflected_in_real_candidate_impacts(self) -> None:
        document = json.loads(STATIC.read_text(encoding="utf-8"))
        session = DocumentEditorSession(document)
        state = session.generate_anchored_candidates(["cx"])
        self.assertEqual(state["anchored_regeneration"]["scope"], ["cx"])
        for candidate in state["anchored_regeneration"]["candidates"]:
            self.assertEqual(
                {impact["parameter"] for impact in candidate["impacts"]},
                {"cx"},
            )
        with self.assertRaisesRegex(ValueError, "supports only highlight cx/cy"):
            session.generate_anchored_candidates(["rx"])

    def test_unsupported_operation_subset_fails_closed(self) -> None:
        document = json.loads((ROOT / "examples" / "001-head-basic.svm.json").read_text())
        with self.assertRaisesRegex(ValueError, "supports only CreateRectangle/CreateEllipse"):
            DocumentEditorSession(document)

    def test_multiple_tracks_are_addressable_and_edit_independently(self) -> None:
        document = json.loads(MULTITRACK.read_text(encoding="utf-8"))
        session = DocumentEditorSession(document)
        initial = session.state(12)
        self.assertEqual(initial["timebase"]["ticks_per_second"], 24)
        self.assertEqual(
            initial["structure"][0]["track_ids"],
            ["track:moving-rectangle-x", "track:moving-rectangle-y"],
        )
        self.assertEqual(initial["frame"]["effective_parameters"]["op:moving-rectangle"]["x"], 200)
        self.assertEqual(initial["frame"]["effective_parameters"]["op:moving-rectangle"]["y"], 80)

        preview = session.preview("track:moving-rectangle-y", "keyframe:moving-y-0012", 100, 12)
        parameters = preview["frame"]["effective_parameters"]["op:moving-rectangle"]
        self.assertEqual(parameters["x"], 200)
        self.assertEqual(parameters["y"], 100)
        self.assertEqual(preview["preview"]["target"]["track_id"], "track:moving-rectangle-y")

    def test_shell_uses_dom_text_nodes_for_document_projection(self) -> None:
        script = (ROOT / "editor" / "motion-timeline" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertIn("textContent", script)
        self.assertIn("replaceChildren", script)


if __name__ == "__main__":
    unittest.main()
