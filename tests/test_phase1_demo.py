"""D1: the documented Phase 1 demo is packaging, not new recovery semantics."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from svm.cli import main

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples/039-controlled-video-editable-svm"
SOURCE_AVI = ROOT / "examples/038-controlled-video-ingestion/scene.avi"
TICKS = (0, 12, 24, 36)
EDITED_TICK = 12


def run_demo_command(output: Path, *extra: str) -> dict:
    """Invoke the same production entry point the documented command uses."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["demo-phase1", "--output-directory", str(output), *extra])
    if code != 0:
        raise AssertionError(f"demo-phase1 exited {code}: {stderr.getvalue()}")
    return json.loads(stdout.getvalue())


def bundle_files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


class Phase1DemoTest(unittest.TestCase):
    def test_avi_input_twelve_tracks_and_single_target_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            report = run_demo_command(output)

            # 1. A real checked-in AVI/FFV1 container is the recovery input.
            self.assertEqual((output / "source/scene.avi").read_bytes(), SOURCE_AVI.read_bytes())
            self.assertEqual(report["input"]["container"], "AVI")
            self.assertEqual(report["input"]["codec"], "FFV1")
            self.assertEqual(report["input"]["selected_frames"], [0, 1, 2, 3])
            self.assertEqual(
                [item["tick"] for item in report["input"]["tick_mapping"]], list(TICKS)
            )
            self.assertEqual(
                sorted(path.name for path in (output / "frames").glob("*.png")),
                [
                    "371b1b80d20d604859d1592bf5755de08655b8f0abe7fe8d2ad91cf3fc37ab2b.png",
                    "86f8c75a769182d26ded5904e4a866c8ad8f3c15bfcd65f9b17483f11a5ddea2.png",
                    "8a53674a074cb244fe65d2de945319c8398221889266777c359edb804ba3e09d.png",
                    "b268898b92a773239151f54e53feb503d0d26f189a5a0028fea7c20b747fd4c4.png",
                ],
            )

            # 2. Recovery yields an ordinary editable SVM Document with 12 Tracks.
            self.assertEqual(report["recovery"]["track_count"], 12)
            recovered = json.loads((output / "documents/recovered.svm.json").read_text("utf-8"))
            self.assertEqual(recovered["schema_version"], "0.1")
            self.assertEqual(len(recovered["animation"]["content"]), 12)
            self.assertEqual(recovered["animation"]["timebase"]["ticks_per_second"], 12)
            summary = report["recovery"]["scene_summary"]
            for role in ("entity:target-a", "entity:target-b"):
                self.assertEqual(
                    sorted(summary[role]),
                    ["rotation_degrees", "scale", "translate.x", "translate.y"],
                )
            self.assertEqual(
                sorted(summary["camera"]),
                ["position.x", "position.y", "rotation_degrees", "scale"],
            )

            # 3. One explicit Keyframe edit through ordinary authoring.
            edited = json.loads((output / "documents/edited.svm.json").read_text("utf-8"))
            self.assertNotEqual(recovered, edited)
            self.assertEqual(report["edit"]["role"], "entity:target-a")
            self.assertEqual(report["edit"]["property"], "rotation_degrees")
            self.assertEqual(report["edit"]["tick"], EDITED_TICK)
            self.assertEqual(report["edit"]["after"], report["edit"]["before"] + 5.0)
            self.assertNotEqual(
                report["validation"]["recovered_revision_id"],
                report["validation"]["edited_revision_id"],
            )
            self.assertEqual(
                report["edit"]["base_revision_id"], report["validation"]["recovered_revision_id"]
            )
            self.assertEqual(len(edited["animation"]["content"]), 12)

            # 4. The edit is visible and strictly local.
            self.assertTrue(report["validation"]["other_targets_unchanged"])
            self.assertTrue(report["validation"]["camera_unchanged"])
            self.assertTrue(report["validation"]["edited_target_other_properties_unchanged"])
            self.assertEqual(report["validation"]["changed_ticks"], [str(EDITED_TICK)])
            self.assertEqual(report["validation"]["re_rendered_changed_ticks"], [str(EDITED_TICK)])
            for tick in TICKS:
                recovered_svg = (output / f"rendered/recovered/tick_{tick:03d}.svg").read_bytes()
                edited_svg = (output / f"rendered/edited/tick_{tick:03d}.svg").read_bytes()
                if tick == EDITED_TICK:
                    self.assertNotEqual(recovered_svg, edited_svg)
                else:
                    self.assertEqual(recovered_svg, edited_svg)

            # 5. Provenance bundle retains the video lineage next to the Document.
            manifest = json.loads((output / "source/video-manifest.json").read_text("utf-8"))
            self.assertEqual(manifest["source_video_reference"], report["input"]["video_reference"])
            by_tick = {item["tick"]: item for item in manifest["occurrences"]}
            self.assertEqual(sorted(by_tick), list(TICKS))
            self.assertEqual(
                sorted(
                    by_tick[tick]["raster_artifact_id"].removeprefix("artifact:") for tick in TICKS
                ),
                sorted(path.stem for path in (output / "frames").glob("*.png")),
            )

            # 6. No machine-specific absolute path is written into the bundle.
            for name, content in bundle_files(output).items():
                if Path(name).suffix in {".json", ".svg"}:
                    self.assertNotIn(str(ROOT), content.decode("utf-8"), name)

    def test_repeated_execution_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            first_report = run_demo_command(first)
            second_report = run_demo_command(second)
            self.assertEqual(first_report, second_report)
            self.assertEqual(bundle_files(first), bundle_files(second))

    def test_demo_does_not_require_ground_truth(self) -> None:
        read_text = Path.read_text

        def forbid(path: Path, *args: object, **kwargs: object) -> str:
            if path.name in {"ground-truth.json", "verification.json"}:
                raise AssertionError("Demo accessed Ground Truth")
            return read_text(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path, "read_text", forbid):
                report = run_demo_command(Path(directory) / "demo")
        self.assertEqual(report["recovery"]["track_count"], 12)

    def test_output_directory_requires_explicit_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            first = run_demo_command(output)
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(["demo-phase1", "--output-directory", str(output)]), 2)
            self.assertIn("must not already exist", stderr.getvalue())
            self.assertEqual(run_demo_command(output, "--replace"), first)
