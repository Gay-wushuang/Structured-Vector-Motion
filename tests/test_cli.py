import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "001-head-basic.svm.json"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "svm", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class MinimalCliTest(unittest.TestCase):
    def test_validate_and_inspect(self) -> None:
        validated = run_cli("validate", str(EXAMPLE))
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertTrue(json.loads(validated.stdout)["valid"])

        inspected = run_cli("inspect", str(EXAMPLE))
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        result = json.loads(inspected.stdout)
        refine = next(op for op in result["operations"] if op["id"] == "op:head_refine")
        self.assertEqual(refine["inputs"], {"geometry": "geometry"})
        self.assertEqual(refine["outputs"], {"geometry": "geometry"})
        self.assertTrue(refine["quality_sensitive"])

    def test_evaluate_reports_materialized_value_ids(self) -> None:
        completed = run_cli("evaluate", str(EXAMPLE), "--quality", "FINAL")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["quality"], "FINAL")
        refine = result["operations"]["op:head_refine"]
        self.assertEqual(refine["state"], "CLEAN")
        self.assertEqual(refine["evaluated_quality"], "FINAL")
        self.assertTrue(refine["outputs"]["geometry"]["value_id"].startswith("sha256:"))
        self.assertNotIn("payload", refine["outputs"]["geometry"])

    def test_mutate_writes_valid_document_without_overwriting_source(self) -> None:
        original = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "mutated.svm.json"
            completed = run_cli(
                "mutate",
                str(EXAMPLE),
                "--set",
                "op:head_base.rx=0.42",
                "--output",
                str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertTrue(summary["revision_id"].startswith("revision:"))
            mutated = json.loads(output.read_text(encoding="utf-8"))
            head_base = next(
                op for op in mutated["construction"]["operations"] if op["id"] == "op:head_base"
            )
            self.assertEqual(head_base["parameters"]["rx"], 0.42)
            self.assertEqual(json.loads(EXAMPLE.read_text(encoding="utf-8")), original)

    def test_invalid_mutation_fails_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "invalid.svm.json"
            completed = run_cli(
                "mutate",
                str(EXAMPLE),
                "--set",
                'op:head_base.rx="wide"',
                "--output",
                str(output),
            )
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(output.exists())
            self.assertIn("rx must be a number", json.loads(completed.stderr)["error"])

    def test_reevaluate_reports_precise_invalidation_and_changed_values(self) -> None:
        completed = run_cli(
            "reevaluate",
            str(EXAMPLE),
            "--set",
            "op:head_base.rx=0.42",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(
            set(result["invalidated"]),
            {
                "op:head_base",
                "op:head_transform",
                "op:head_path",
                "op:head_refine",
                "op:hair_clip",
            },
        )
        self.assertNotIn("op:shield", result["changed_values"])
        self.assertNotIn("op:hair_base", result["changed_values"])


if __name__ == "__main__":
    unittest.main()
