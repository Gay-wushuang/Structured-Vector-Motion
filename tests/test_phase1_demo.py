"""D1: the documented Phase 1 demo is packaging, not new recovery semantics."""

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from svm.cli import main
from svm.phase1_demo import DEFAULT_CONFIG, DemoError, _validate_output, load_config, run_demo
from svm.recovery_orchestration import (
    RecoveryOrchestrationError,
    author_recovered_document,
    recover_scene,
)

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
            # Recorded from unmodified 2e6a458. Normalize only OS text newlines.
            for name, digest in {
                "recovered": "e18a3af9054161a3c72b021df2e81522bde428543425dd256944b469bf42484a",
                "edited": "53871073fbf8507c52861731e4b2b812e471472027f613beef5493dc815343e1",
            }.items():
                content = (output / f"documents/{name}.svm.json").read_bytes()
                self.assertEqual(
                    hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest(), digest
                )
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
            clean = bundle_files(output)
            (output / "old-only.txt").write_bytes(b"retain until commit")
            original = bundle_files(output)
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(["demo-phase1", "--output-directory", str(output)]), 2)
            self.assertIn("must not already exist", stderr.getvalue())
            from svm.phase1_demo import _write_json

            def fail_report(path, value):
                if path.name == "report.json":
                    # Recovery, edit, rendering and almost all writes completed.
                    self.assertEqual(bundle_files(output), original)
                    raise OSError("injected final bundle write failure")
                _write_json(path, value)

            with patch("svm.phase1_demo._write_json", side_effect=fail_report):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(
                        main(["demo-phase1", "--output-directory", str(output), "--replace"]), 2
                    )
            self.assertEqual(bundle_files(output), original)
            self.assertEqual(list(Path(directory).iterdir()), [output])
            self.assertEqual(run_demo_command(output, "--replace"), first)
            self.assertEqual(bundle_files(output), clean)
            self.assertEqual(list(Path(directory).iterdir()), [output])


class DemoPublicationContractTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT, DEFAULT_CONFIG)

    def test_protected_outputs_reject_before_build_and_cli_returns_two(self):
        protected = [
            ROOT,
            ROOT.parent,
            Path(ROOT.anchor),
            DEMO,
            SOURCE_AVI.parent,
            ROOT / "examples",
            ROOT / self.config.base_document_locator,
        ]
        if os.name == "nt":
            # resolve() preserves this prefix, although samefile() sees the
            # same directory. Canonical lexical containment alone is insufficient.
            protected.extend(Path("\\\\?\\" + str(path)) for path in (ROOT, ROOT.parent, DEMO))
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            protected.append(cwd)
            with patch.object(Path, "cwd", return_value=cwd):
                for output in protected:
                    with (
                        self.subTest(output=output),
                        patch("svm.phase1_demo._build_bundle") as build,
                    ):
                        with self.assertRaisesRegex(DemoError, "output safety"):
                            run_demo(ROOT, self.config, output, replace=True)
                        stderr = io.StringIO()
                        with redirect_stderr(stderr):
                            self.assertEqual(
                                main(
                                    ["demo-phase1", "--output-directory", str(output), "--replace"]
                                ),
                                2,
                            )
                        self.assertIn("output safety", stderr.getvalue())
                        build.assert_not_called()

    def test_normal_build_output_allowed_and_canonical_parent_rejected(self):
        output = ROOT / "build" / "safe-demo-contract-test"
        self.assertEqual(_validate_output(ROOT, self.config, output, True), output.resolve())
        with self.assertRaisesRegex(DemoError, "protected directory"):
            _validate_output(ROOT, self.config, ROOT / "build" / "..", True)

    def test_links_reparse_points_and_resolution_errors_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            info = type(
                "ReparseStat",
                (),
                {
                    "st_mode": stat.S_IFDIR,
                    "st_file_attributes": stat.FILE_ATTRIBUTE_REPARSE_POINT,
                },
            )()
            for failure in [PermissionError("denied"), RuntimeError("link loop")]:
                with patch.object(Path, "resolve", side_effect=failure):
                    with self.assertRaisesRegex(DemoError, "cannot safely resolve"):
                        run_demo(ROOT, self.config, output, replace=True)
            with patch.object(Path, "lstat", return_value=info):
                with self.assertRaisesRegex(DemoError, "links and reparse points"):
                    run_demo(ROOT, self.config, output, replace=True)
            info.st_mode = stat.S_IFLNK
            info.st_file_attributes = 0
            with patch.object(Path, "lstat", return_value=info):
                with self.assertRaisesRegex(DemoError, "links and reparse points"):
                    run_demo(ROOT, self.config, output, replace=True)

    def test_failed_staging_never_publishes_new_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"

            def fail(root, config, pending):
                pending.mkdir()
                (pending / "partial").write_bytes(b"incomplete")
                raise DemoError("injected staging failure")

            with patch("svm.phase1_demo._build_bundle", side_effect=fail):
                with self.assertRaisesRegex(DemoError, "injected staging"):
                    run_demo(ROOT, self.config, output)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_publish_failure_rolls_back_old_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            output.mkdir()
            (output / "old").write_bytes(b"original")
            original = bundle_files(output)
            rename = Path.rename

            def build(root, config, pending):
                pending.mkdir()
                (pending / "new").write_bytes(b"complete")
                return {}

            def fail_publish(path, target):
                if path.name == "bundle":
                    raise OSError("injected publish rename failure")
                return rename(path, target)

            with patch("svm.phase1_demo._build_bundle", side_effect=build):
                with patch.object(Path, "rename", fail_publish):
                    with self.assertRaisesRegex(DemoError, "original output preserved"):
                        run_demo(ROOT, self.config, output, replace=True)
            self.assertEqual(bundle_files(output), original)
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_failed_rollback_retains_original_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            output.mkdir()
            (output / "old").write_bytes(b"original")
            original = bundle_files(output)
            rename = Path.rename

            def build(root, config, pending):
                pending.mkdir()
                return {}

            def fail_publish_and_rollback(path, target):
                if path.name in {"bundle", "previous"}:
                    raise PermissionError("injected filesystem failure")
                return rename(path, target)

            with patch("svm.phase1_demo._build_bundle", side_effect=build):
                with patch.object(Path, "rename", fail_publish_and_rollback):
                    with self.assertRaisesRegex(DemoError, "original bundle retained at"):
                        run_demo(ROOT, self.config, output, replace=True)
            backups = list(Path(directory).glob(".demo-staging-*/previous"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(bundle_files(backups[0]), original)
            self.assertFalse(output.exists())

    def test_cleanup_failure_after_commit_keeps_published_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            output.mkdir()
            (output / "old").write_bytes(b"original")

            def build(root, config, pending):
                pending.mkdir()
                (pending / "new").write_bytes(b"complete")
                return {"complete": True}

            with patch("svm.phase1_demo._build_bundle", side_effect=build):
                with patch("svm.phase1_demo.shutil.rmtree", side_effect=PermissionError("busy")):
                    with self.assertWarnsRegex(UserWarning, "staging cleanup requires attention"):
                        self.assertEqual(
                            run_demo(ROOT, self.config, output, replace=True), {"complete": True}
                        )
            self.assertEqual(bundle_files(output), {"new": b"complete"})


class RecoveryConfigContractTest(unittest.TestCase):
    def setUp(self):
        demo = load_config(ROOT, DEFAULT_CONFIG)
        selectors = json.loads((ROOT / demo.selectors_locator).read_text("utf-8"))
        self.config = demo.recovery(selectors)

    def test_normal_configuration_validates(self):
        self.config.validate()

    def test_invalid_configuration_rejects_at_both_orchestration_boundaries(self):
        cases = [
            {"ticks": None},
            {"groups": None},
            {"anchors": 1},
            {"targets": (), "groups": ()},
            {"anchors": ()},
            {"groups": ()},
            {"groups": (self.config.groups[0],) * 2},
            {"targets": (self.config.targets[0],) * 2},
            {"ticks": ()},
            {"ticks": (0, 0)},
            {"ticks": (1, 0)},
            {"ticks": (-1, 0)},
            {"ticks": (False, 12)},
            {"ticks": (0, 1.5)},
            {"ticks_per_second": 0},
            {"ticks_per_second": True},
            {"selectors": {}},
            {"selectors": {"0": None}},
            {"selectors": {"0": {self.config.anchors[0]: ""}}},
        ]
        for changes in cases:
            config = replace(self.config, **changes)
            with self.subTest(changes=changes):
                with self.assertRaises(RecoveryOrchestrationError):
                    recover_scene({}, (), config)
                with self.assertRaises(RecoveryOrchestrationError):
                    author_recovered_document(None, config)
