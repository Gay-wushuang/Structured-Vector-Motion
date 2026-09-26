"""D2: a completed D1 bundle is sufficient for a static, read-only projection."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from svm.cli import main
from svm.phase1_demo import DEFAULT_CONFIG, load_config, run_demo
from svm.phase1_showcase import (
    EDIT_FIELDS,
    INPUT_FIELDS,
    OUTPUT_FIELDS,
    RECOVERY_FIELDS,
    VALIDATION_FIELDS,
    ShowcaseError,
    generate_showcase,
)

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_FILES = {"index.html", "projection.json", "showcase.css", "showcase.js"}


def files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


class Phase1ShowcaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.workspace = Path(cls.temporary.name)
        cls.bundle = cls.workspace / "bundle"
        config = load_config(ROOT, DEFAULT_CONFIG)
        run_demo(ROOT, config, cls.bundle)
        cls.original = files(cls.bundle)
        cls.report = json.loads((cls.bundle / "report.json").read_text("utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def output(self, name: str) -> Path:
        output = self.workspace / name
        if output.exists():
            shutil.rmtree(output)
        return output

    def test_bundle_only_projection_and_static_runtime(self) -> None:
        output = self.output("showcase-main")
        before = files(self.bundle)

        def forbidden(*args, **kwargs):
            raise AssertionError("D2 invoked a frozen processing stage")

        with (
            patch("svm.video_ingestion.ingest_video", side_effect=forbidden),
            patch("svm.recovery_orchestration.recover_scene", side_effect=forbidden),
            patch("svm.phase1_demo._render_document", side_effect=forbidden),
        ):
            projection = generate_showcase(self.bundle, output)

        self.assertEqual(set(path.name for path in output.iterdir()), SHOWCASE_FILES)
        self.assertEqual(files(self.bundle), before)
        written = json.loads((output / "projection.json").read_text("utf-8"))
        self.assertEqual(projection, written)

        for section, fields in (
            ("input", INPUT_FIELDS),
            ("edit", EDIT_FIELDS),
            ("validation", VALIDATION_FIELDS),
            ("recovery", RECOVERY_FIELDS),
            ("outputs", OUTPUT_FIELDS),
        ):
            expected = {key: self.report[section][key] for key in fields}
            self.assertEqual(projection[section], expected)

        mappings = projection["input"]["tick_mapping"]
        for index, mapping in enumerate(mappings):
            self.assertEqual(mapping["frame_index"], projection["input"]["selected_frames"][index])
            self.assertEqual(
                projection["outputs"]["frames"][index], self.report["outputs"]["frames"][index]
            )
            self.assertEqual(
                projection["outputs"]["recovered_rendered"][index],
                self.report["outputs"]["recovered_rendered"][index],
            )
            self.assertEqual(
                projection["outputs"]["edited_rendered"][index],
                self.report["outputs"]["edited_rendered"][index],
            )

        index = (output / "index.html").read_text("utf-8")
        script = (output / "showcase.js").read_text("utf-8")
        self.assertIn('../bundle/source/scene.avi', index)
        self.assertIn('id="projection-data"', index)
        self.assertNotIn("fetch(", script)
        self.assertNotIn("XMLHttpRequest", script)
        self.assertNotIn("<video", index)
        for content in files(output).values():
            text = content.decode("utf-8")
            self.assertNotIn(str(ROOT), text)
            self.assertNotIn(str(self.workspace), text)

    def test_cli_ground_truth_independence_and_existing_output_rejection(self) -> None:
        output = self.output("showcase-cli")
        read_text = Path.read_text

        def forbid_truth(path: Path, *args: object, **kwargs: object) -> str:
            if path.name in {"ground-truth.json", "verification.json"}:
                raise AssertionError("D2 accessed Ground Truth")
            return read_text(path, *args, **kwargs)

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(Path, "read_text", forbid_truth):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(
                    main(
                        [
                            "showcase-phase1",
                            "--bundle",
                            str(self.bundle),
                            "--output",
                            str(output),
                        ]
                    ),
                    0,
                )
        written = json.loads((output / "projection.json").read_text())
        self.assertEqual(json.loads(stdout.getvalue()), written)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(
                main(
                    [
                        "showcase-phase1",
                        "--bundle",
                        str(self.bundle),
                        "--output",
                        str(output),
                    ]
                ),
                2,
            )
        self.assertIn("must not already exist", stderr.getvalue())

    def test_repeated_generation_is_byte_identical_and_deletion_safe(self) -> None:
        first = self.output("showcase-first")
        second = self.output("showcase-second")
        first_projection = generate_showcase(self.bundle, first)
        second_projection = generate_showcase(self.bundle, second)
        self.assertEqual(first_projection, second_projection)
        self.assertEqual(files(first), files(second))

        nested = self.bundle / "showcase"
        if nested.exists():
            shutil.rmtree(nested)
        generate_showcase(self.bundle, nested)
        shutil.rmtree(nested)
        self.assertEqual(files(self.bundle), self.original)

    def test_absolute_traversal_missing_and_manifest_mismatch_fail_closed(self) -> None:
        cases = {
            "absolute": ("source", str((self.workspace / "outside.avi").resolve())),
            "traversal": ("source", "../outside.avi"),
            "missing": ("source", "source/missing.avi"),
        }
        for name, (field, pointer) in cases.items():
            clone = self.output(f"bundle-{name}")
            shutil.copytree(self.bundle, clone)
            report = json.loads((clone / "report.json").read_text("utf-8"))
            report["outputs"][field] = pointer
            (clone / "report.json").write_text(json.dumps(report), encoding="utf-8")
            output = self.output(f"rejected-{name}")
            with self.subTest(name=name), self.assertRaises(ShowcaseError):
                generate_showcase(clone, output)
            self.assertFalse(output.exists())

        clone = self.output("bundle-order")
        shutil.copytree(self.bundle, clone)
        manifest = json.loads((clone / "source/video-manifest.json").read_text("utf-8"))
        manifest["occurrences"][0]["tick"] += 1
        (clone / "source/video-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        output = self.output("rejected-order")
        with self.assertRaisesRegex(ShowcaseError, "ordering disagrees"):
            generate_showcase(clone, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
