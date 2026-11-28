import copy
import json
import tempfile
import unittest
from pathlib import Path

from svm.motion import MotionEvaluator
from svm.operations import _geometry_bounds

from .anchors import review
from .author_translation import accept, prepare
from .fixture import make
from .run import MAX_SOURCE_BYTES, bounded_read, digest, json_bytes, observe, read_settings


class TranslationAuthoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        directory = Path(scratch.name) / "fixture"
        make(directory)
        cls.source = bounded_read(directory / "synthetic.avi", MAX_SOURCE_BYTES)
        cls.observations = observe(cls.source, read_settings(directory / "seeds.json"))
        cls.candidate = json_bytes(cls.observations)
        cls.teal = next(item for item in cls.observations["geometry"] if item["id"] == "teal")

    def request(self, *, subject="teal", start=0, end=94):
        return {
            "subject": subject,
            "start_tick": start,
            "end_tick": end,
            "candidate_sha256": digest(self.candidate),
        }

    def test_preview_keeps_base_and_matching_accept_creates_one_revision(self):
        request = self.request()
        preview = prepare(self.source, self.candidate, request)
        parent = preview.base.head
        original = preview.base.get_document(parent)
        self.assertEqual(len(preview.base.revisions), 1)
        self.assertEqual(original["entities"], [])
        self.assertEqual(
            len(preview.document["entities"]), len(self.teal["geometry_rectangles_xywh"])
        )
        with self.assertRaises(ValueError):
            accept(preview, preview.preview_id + "-wrong")
        self.assertEqual(preview.base.head, parent)
        self.assertEqual(len(preview.base.revisions), 1)

        accepted = accept(preview, preview.preview_id)
        revision = preview.base.head
        self.assertNotEqual(revision, parent)
        self.assertEqual(len(preview.base.revisions), 2)
        self.assertEqual(preview.base.revisions[revision].parent_ids, (parent,))
        self.assertEqual(preview.base.get_document(parent), original)
        self.assertEqual(accepted["document"], preview.base.get_document(revision))
        self.assertEqual(accepted["document"], preview.document)
        self.assertEqual(accepted["revision"], revision)
        self.assertEqual(accepted["report"]["base_revision"], parent)

    def test_acceptance_preserves_primitive_geometry_and_relative_timing(self):
        preview = prepare(self.source, self.candidate, self.request(start=10, end=20))
        accepted = accept(preview, preview.preview_id)
        document = json.loads(json_bytes(accepted["document"]))
        evaluator = MotionEvaluator(document)

        def bounds(tick):
            return {
                item.entity_id: _geometry_bounds(item.geometry)
                for item in evaluator.evaluate(tick).scene.entities
            }

        shapes = len(self.teal["geometry_rectangles_xywh"])
        origin = bounds(0)
        midpoint = bounds(5)
        final = bounds(10)
        self.assertEqual(len(origin), shapes)
        self.assertEqual(set(origin), set(midpoint))
        self.assertEqual(set(origin), set(final))
        for entity_id, (left, top, right, bottom) in origin.items():
            self.assertEqual(midpoint[entity_id], (left - 5, top, right - 5, bottom))
            self.assertEqual(final[entity_id], (left - 10, top, right - 10, bottom))
        self.assertEqual(bounds(12), final)
        self.assertEqual(min(box[0] for box in origin.values()), 242)

        tracks = document["animation"]["content"]
        moving_tracks = [
            track
            for track in tracks
            if track["keyframes"][0]["value"] != track["keyframes"][-1]["value"]
        ]
        self.assertEqual(len(tracks), shapes)
        self.assertEqual(len(moving_tracks), shapes)
        for track in moving_tracks:
            self.assertEqual([key["tick"] for key in track["keyframes"]], [0, 10])
        self.assertEqual(accepted["report"]["source_ticks"], list(range(10, 21, 2)))
        self.assertEqual(accepted["report"]["document_start_tick"], 0)
        self.assertEqual(accepted["report"]["document_end_tick"], 10)
        self.assertEqual(accepted["report"]["ticks_per_second"], 24)

    def test_rejects_occluded_and_unconfirmed_return_intervals(self):
        for start, end in ((0, 68), (68, 80), (70, 80)):
            with (
                self.subTest(start=start, end=end),
                self.assertRaises(ValueError),
            ):
                prepare(
                    self.source, self.candidate, self.request(subject="amber", start=start, end=end)
                )

    def test_explicit_reanchor_allows_only_the_reestablished_continuous_interval(self):
        approved = json_bytes(
            review(
                self.candidate,
                {
                    "candidate_sha256": digest(self.candidate),
                    "reanchors": [{"subject": "amber", "tick": 68, "point_xy": [141, 65]}],
                },
            )
        )
        request = {
            **self.request(subject="amber", start=68, end=80),
            "candidate_sha256": digest(approved),
        }
        preview = prepare(self.source, approved, request)
        self.assertEqual(preview.report["source_ticks"], list(range(68, 81, 2)))
        self.assertEqual(preview.report["reviewed_unknown_intervals"]["amber"], [[34, 66]])
        with self.assertRaises(ValueError):
            prepare(self.source, approved, {**request, "start_tick": 30})

    def test_rejects_mismatched_candidate_hash_and_forgery_with_matching_hash(self):
        request = self.request()
        with self.assertRaises(ValueError):
            prepare(self.source, self.candidate, {**request, "candidate_sha256": "0" * 64})
        forged = copy.deepcopy(self.observations)
        forged["frames"][1]["subjects"]["teal"]["translation_xy"] = [-3, 0]
        forged_bytes = json_bytes(forged)
        with self.assertRaises(ValueError):
            prepare(
                self.source, forged_bytes, {**request, "candidate_sha256": digest(forged_bytes)}
            )


if __name__ == "__main__":
    unittest.main()
