from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import alpha_mask, decode, probe, repair, run, sha  # noqa: E402
from synthetic import generate  # noqa: E402


class FlickerPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="svm-flicker-tests-")
        cls.root = Path(cls.temp.name)
        cls.fixture = cls.root / "fixture"
        generate(cls.fixture)
        cls.mask = cv2.imread(str(cls.fixture / "roi.png"), cv2.IMREAD_GRAYSCALE)
        cls.source = decode(cls.fixture / "source.avi", probe(cls.fixture / "source.avi"))
        cls.gt = np.load(cls.fixture / "ground_truth.npy", allow_pickle=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_no_flicker_static_texture_unchanged(self) -> None:
        frames = np.repeat(self.gt[:1], 6, axis=0)
        outputs, _ = repair(frames, self.mask, 2, 6, 1.3, 6)
        for actual in outputs.values():
            np.testing.assert_array_equal(actual, frames)

    def test_no_flicker_moving_object_has_small_change(self) -> None:
        outputs, _ = repair(self.gt, self.mask, 2, 6, 1.3, 6)
        for name in ("B_roi_normalization", "C_low_frequency"):
            error = np.abs(outputs[name].astype(float) - self.gt)
            self.assertLess(float(np.mean(error[:, self.mask > 0])), 0.1)
            self.assertEqual(float(np.max(error[:, self.mask == 0])), 0.0)

    def test_roi_improvement_outside_and_replay(self) -> None:
        first, _ = repair(self.source, self.mask, 2, 6, 1.3, 6)
        second, _ = repair(self.source, self.mask, 2, 6, 1.3, 6)
        roi = self.mask > 0
        baseline = np.mean(np.abs(self.source[:, roi].astype(float) - self.gt[:, roi]))
        for name in ("B_roi_normalization", "C_low_frequency"):
            np.testing.assert_array_equal(first[name], second[name])
            np.testing.assert_array_equal(first[name][:, ~roi], self.source[:, ~roi])
            candidate = np.mean(np.abs(first[name][:, roi].astype(float) - self.gt[:, roi]))
            self.assertLess(candidate, baseline * 0.5)

    def test_feather_limits_edge_changes(self) -> None:
        outputs, _ = repair(self.source, self.mask, 2, 6, 1.3, 6)
        alpha = alpha_mask(self.mask, 6)
        correction = np.abs(outputs["B_roi_normalization"].astype(float) - self.source)
        self.assertLess(
            np.mean(correction[:, (alpha > 0) & (alpha < 0.4)]),
            np.mean(correction[:, alpha >= 0.99]),
        )
        self.assertTrue(np.all(alpha[self.mask == 0] == 0))

    def test_scene_cut_and_bad_mask_fail_closed(self) -> None:
        frames = np.stack([self.gt[0], np.full_like(self.gt[0], 240)])
        with self.assertRaises(ValueError):
            repair(frames, self.mask, 2, 6, 1.3, 6)
        with self.assertRaises(ValueError):
            repair(self.source, np.full_like(self.mask, 128), 2, 6, 1.3, 6)

    def test_failed_preview_preserves_source(self) -> None:
        bad_mask = self.root / "invalid-mask.png"
        self.assertTrue(cv2.imwrite(str(bad_mask), np.full_like(self.mask, 128)))
        source = self.fixture / "source.avi"
        before = sha(source)
        output = self.root / "failed-preview"
        command = [
            sys.executable,
            "-B",
            str(ROOT / "main.py"),
            "preview",
            "--input",
            str(source),
            "--mask",
            str(bad_mask),
            "--output",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, sha(source))
        self.assertFalse((output / "candidate.mp4").exists())

    def test_full_synthetic_preview_and_no_overwrite(self) -> None:
        output = self.root / "full"
        command = [
            sys.executable,
            "-B",
            str(ROOT / "main.py"),
            "synthetic",
            "--output",
            str(output),
        ]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        manifest = json.loads((output / "experiment-manifest.json").read_text())
        metrics = json.loads((output / "metrics.json").read_text())
        self.assertEqual(manifest["artifact_classification"], "experimental-only-not-svm-evidence")
        self.assertEqual(manifest["svm_acceptance"], "NOT_IMPLEMENTED")
        self.assertEqual(manifest["input_classification"], "SYNTHETIC")
        self.assertEqual(metrics["classification"], "SYNTHETIC")
        for filename in (
            "candidate.mp4",
            "original_preview.mp4",
            "comparison.mp4",
            "mask_preview.png",
        ):
            self.assertEqual(sha(output / filename), manifest["artifacts"][filename])
        for filename in ("candidate.mp4", "original_preview.mp4", "comparison.mp4"):
            meta = manifest["output_decode"][filename]["probe"]
            self.assertEqual(meta["frame_count"], 24)
            self.assertEqual(meta["fps"], "12")
            self.assertEqual(meta["audio_streams"], [])
        self.assertLess(
            metrics["methods"]["B_roi_normalization"]["roi_gt_mae"],
            metrics["methods"]["A_noop"]["roi_gt_mae"],
        )
        before = sha(output / "candidate.mp4")
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(before, sha(output / "candidate.mp4"))

    def test_runtime_rejects_gt_argument(self) -> None:
        output = self.root / "no-gt"
        output.mkdir()
        command = [
            sys.executable,
            "-B",
            str(ROOT / "main.py"),
            "_worker",
            "--input",
            str(self.fixture / "source.avi"),
            "--mask",
            str(self.fixture / "roi.png"),
            "--gt",
            str(self.fixture / "ground_truth.npy"),
            "--output",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("never ground truth", result.stderr)
        self.assertEqual(list(output.iterdir()), [])

    def test_runtime_output_ignores_missing_or_corrupt_gt(self) -> None:
        outputs = []
        for label in ("missing", "corrupt"):
            fixture = self.root / f"gt-{label}"
            fixture.mkdir()
            for name in ("source.avi", "roi.png"):
                shutil.copyfile(self.fixture / name, fixture / name)
            if label == "corrupt":
                (fixture / "ground_truth.npy").write_bytes(b"not a numpy file")
            output = self.root / f"gt-output-{label}"
            output.mkdir()
            command = [
                sys.executable,
                "-B",
                str(ROOT / "main.py"),
                "_worker",
                "--input",
                str(fixture / "source.avi"),
                "--mask",
                str(fixture / "roi.png"),
                "--output",
                str(output),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(sha(output / "B_roi_normalization.npy"))
        self.assertEqual(outputs[0], outputs[1])

    def test_preview_without_gt_omits_reference_quality(self) -> None:
        output = self.root / "no-reference"
        command = [
            sys.executable,
            "-B",
            str(ROOT / "main.py"),
            "preview",
            "--input",
            str(self.fixture / "source.avi"),
            "--mask",
            str(self.fixture / "roi.png"),
            "--output",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        metrics = json.loads((output / "metrics.json").read_text())
        self.assertEqual(metrics["classification"], "REAL_NO_GT")
        for values in metrics["methods"].values():
            self.assertNotIn("psnr_db", values)
            self.assertNotIn("ssim", values)

    def test_audio_presence_and_explicit_drop(self) -> None:
        audio = self.root / "audio.avi"
        run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-n",
                "-i",
                str(self.fixture / "source.avi"),
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "2",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "pcm_s16le",
                str(audio),
            ]
        )
        self.assertEqual(len(probe(audio)["audio_streams"]), 1)
        output = self.root / "audio-run"
        output.mkdir()
        command = [
            sys.executable,
            "-B",
            str(ROOT / "main.py"),
            "_worker",
            "--input",
            str(audio),
            "--mask",
            str(self.fixture / "roi.png"),
            "--output",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((output / "runtime-manifest.json").read_text())
        self.assertEqual(len(manifest["input"]["audio_streams"]), 1)
        self.assertIn("DROPPED", manifest["audio_processing"])
        self.assertEqual(manifest["output_decode"]["candidate.mp4"]["probe"]["audio_streams"], [])


if __name__ == "__main__":
    unittest.main()
