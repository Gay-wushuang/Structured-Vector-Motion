from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

PILOT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PILOT_ROOT.parents[1]
sys.path.insert(0, str(PILOT_ROOT))

import run_experiment as pilot  # noqa: E402


class TemporalGeometryExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config_path = PILOT_ROOT / "experiment.json"
        cls.config = pilot.load_config(cls.config_path, REPO_ROOT)
        cls.frames, cls.gt = pilot.load_inputs(cls.config, REPO_ROOT)

    def test_a_and_b_use_frozen_first_geometry_and_stay_experimental(self) -> None:
        method_a = pilot.run_method_a(self.frames, self.config)
        method_b = pilot.run_method_b(self.frames, self.config)

        self.assertEqual(method_a["artifact_classification"], pilot.CLASSIFICATION)
        self.assertEqual(method_b["artifact_classification"], pilot.CLASSIFICATION)
        self.assertEqual(method_a["identity_metrics_applicability"], "N/A")
        self.assertEqual(method_a["frames"][0]["points"], method_b["frames"][0]["points"])
        self.assertTrue(all(frame["status"] == "SUPPORTED" for frame in method_b["frames"]))

    def test_metrics_keep_a_identity_and_temporal_link_metrics_not_applicable(self) -> None:
        method_a = pilot.run_method_a(self.frames, self.config)
        method_b = pilot.run_method_b(self.frames, self.config)
        metrics = pilot.build_metrics(method_a, method_b, self.frames, self.gt, self.config)

        summary_a = metrics["method_a"]["summary"]
        summary_b = metrics["method_b"]["summary"]
        self.assertEqual(summary_a["identity_metrics_applicability"], "N/A")
        self.assertIsNone(summary_a["identity_switch_count"])
        self.assertIsNone(summary_a["idf1_style"])
        self.assertIsNone(summary_a["motion_compensated_temporal_error_mean"])
        self.assertGreater(summary_b["motion_compensated_temporal_error_mean"], 0.0)
        self.assertIn("gt_centroid_motion_error_px", metrics["method_a"]["per_frame"][1])

    def test_frozen_raw_downstream_is_reproducible(self) -> None:
        method_a = pilot.run_method_a(self.frames, self.config)
        method_b = pilot.run_method_b(self.frames, self.config)
        report, _, _ = pilot.verify_downstream_reproducibility(
            method_a, method_b, self.frames, self.gt, self.config
        )

        self.assertTrue(report["passed"])
        self.assertTrue(report["metrics_canonical_bytes_identical"])
        self.assertTrue(report["comparison_video_decoded_frames_identical"])

    def test_runtime_version_mismatch_yields_conditional_not_go(self) -> None:
        method_a = pilot.run_method_a(self.frames, self.config)
        method_b = pilot.run_method_b(self.frames, self.config)
        metrics = pilot.build_metrics(method_a, method_b, self.frames, self.gt, self.config)
        decision = pilot.decide(metrics, True, self.config["decision_thresholds"], False)

        self.assertEqual(decision["outcome"], "CONDITIONAL")
        self.assertIn("DECLARED_OPENCV_REQUIREMENT", decision["reasons"])

    def test_tampered_frozen_first_geometry_fails_closed(self) -> None:
        tampered = copy.deepcopy(self.config)
        tampered["frozen_first_frame_geometry"]["points"][0][0] += 1.0
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "tampered.json"
            config_path.write_text(json.dumps(tampered), encoding="utf-8")
            loaded = pilot.load_config(config_path, REPO_ROOT)
            with self.assertRaisesRegex(
                pilot.ExperimentError, "does not match fixture ground truth"
            ):
                pilot.load_inputs(loaded, REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
