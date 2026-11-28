import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from .anchors import review
from .diagnose import identity_fixture
from .fixture import make, metrics, reconstructed_template
from .run import (
    CLASSIFICATION,
    PROFILE,
    Subject,
    bounded_read,
    digest,
    json_bytes,
    observe,
    read_settings,
    rectangles,
)


class ReconstructionTest(unittest.TestCase):
    def test_geometry_round_trip_with_holes_and_edge_runs(self):
        mask = np.array([[1, 1, 1, 1], [1, 0, 0, 1], [1, 0, 0, 1], [1, 1, 1, 1]], dtype=bool)
        np.testing.assert_array_equal(reconstructed_template(rectangles(mask), 4, 4), mask)

    def test_identical_shapes_abstain_even_when_one_match_is_near(self):
        frame = np.zeros((32, 48, 3), dtype=np.uint8)
        frame[2:8, 2:8] = (3, 92, 12)
        candidate = Subject.select({"id": "user-selected", "point_xy": [4, 4]}, frame)
        frame[8:14, 36:42] = (3, 92, 12)
        self.assertEqual(
            candidate.observation(frame, 1, 4),
            {"status": "UNKNOWN", "reason": "ambiguous_shape"},
        )

    def test_synthetic_clip_replay_occlusion_and_editable_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture"
            make(output)
            source = bounded_read(output / "synthetic.avi", 8 * 1024 * 1024)
            seeds = read_settings(output / "seeds.json")
            generated = observe(source, seeds)
            result = json_bytes(generated)
            self.assertEqual(result, json_bytes(observe(source, seeds)))
            expected = json.loads((output / "fixture.json").read_bytes())
            evaluation = metrics(result, expected)
            self.assertEqual(evaluation["decoded_bgr24_frame_matches"], 48)
            self.assertEqual(
                evaluation["first_frame_geometry_mask_iou"], {"amber": 1.0, "teal": 1.0}
            )
            self.assertEqual(evaluation["visible_max_translation_error_px"], 0)
            self.assertEqual(evaluation["visible_observation_coverage"], 1.0)
            self.assertEqual(evaluation["occlusion_false_observation_rate"], 0.0)
            self.assertGreater(evaluation["tally"]["occluded"], 0)
            self.assertEqual(generated["unknown_tick_intervals_inclusive"]["amber"], [[34, 66]])
            self.assertEqual(
                generated["frames"][34]["subjects"]["amber"]["association"],
                "exact_shape_after_gap",
            )

    def test_existing_candidate_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture"
            make(output)
            candidate = output / "existing.json"
            candidate.write_bytes(b"keep previous result")
            process = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "research.studio-motion-reconstruction.run",
                    "--input",
                    str(output / "synthetic.avi"),
                    "--seeds",
                    str(output / "seeds.json"),
                    "--output",
                    str(candidate),
                ],
                check=False,
                timeout=10,
                capture_output=True,
            )
            self.assertEqual(process.returncode, 2)
            self.assertEqual(candidate.read_bytes(), b"keep previous result")

    def test_identical_decoy_after_gap_needs_an_explicit_new_anchor(self):
        pixels, truth = identity_fixture()
        seed = Subject.select({"id": "target", "point_xy": [43, 58]}, pixels[0])
        raw = json_bytes(
            {
                "profile": PROFILE,
                "artifact_classification": CLASSIFICATION,
                "geometry": [seed.describe()],
                "frames": [
                    {"tick": 2 * index, "subjects": {"target": seed.observation(frame, index, 4)}}
                    for index, frame in enumerate(pixels)
                ],
            }
        )
        approvals = {"candidate_sha256": digest(raw), "reanchors": []}
        guarded = review(raw, approvals)
        for frame, answer in zip(guarded["frames"], truth, strict=True):
            if answer["visible_identity"] == "decoy":
                self.assertEqual(frame["subjects"]["target"]["reason"], "needs_reanchor")
        approvals["reanchors"] = [{"subject": "target", "tick": 16, "point_xy": [67, 58]}]
        restored = review(raw, approvals)
        self.assertEqual(
            restored["frames"][-1]["subjects"]["target"]["association"], "user_reanchor"
        )
        self.assertEqual(restored["unknown_tick_intervals_inclusive"]["target"], [[6, 14]])
        approvals["reanchors"][0]["point_xy"] = [84, 80]
        with self.assertRaisesRegex(ValueError, "outside observed"):
            review(raw, approvals)
        approvals["candidate_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "exact candidate hash"):
            review(raw, approvals)
