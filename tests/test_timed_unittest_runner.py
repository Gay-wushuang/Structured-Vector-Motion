"""Behavioural self-test for ``tools/run_timed_unittest.py``.

Runs the timed runner against small generated fixture suites and checks that it
preserves the semantics of ``python -m unittest discover``: an identical
executed test set, identical success/failure/error/skip counting, and a
non-zero exit code for failures, errors and import errors.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_timed_unittest.py"

PASS_SOURCE = """
    import unittest

    class SampleOk(unittest.TestCase):
        def test_alpha(self):
            self.assertTrue(True)

        def test_beta(self):
            self.assertEqual(1, 1)
"""

FAIL_SOURCE = """
    import unittest

    class SampleFail(unittest.TestCase):
        def test_ok(self):
            self.assertTrue(True)

        def test_bad(self):
            self.assertEqual(1, 2)
"""

ERROR_SOURCE = """
    import unittest

    class SampleError(unittest.TestCase):
        def test_raises(self):
            raise RuntimeError("boom")
"""

IMPORT_ERROR_SOURCE = """
    import unittest
    import this_module_does_not_exist_at_all

    class SampleImport(unittest.TestCase):
        def test_never_runs(self):
            self.assertTrue(True)
"""

SKIP_SOURCE = """
    import unittest

    class SampleSkip(unittest.TestCase):
        def test_skipped(self):
            raise unittest.SkipTest("skipped on purpose")

        def test_ran(self):
            self.assertTrue(True)
"""

SETUPCLASS_SOURCE = """
    import unittest

    class SampleSetUpClass(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            raise RuntimeError("setUpClass boom")

        def test_one(self):
            self.assertTrue(True)

        def test_two(self):
            self.assertTrue(True)
"""

TEARDOWNCLASS_SOURCE = """
    import unittest

    class SampleTearDownClass(unittest.TestCase):
        @classmethod
        def tearDownClass(cls):
            raise RuntimeError("tearDownClass boom")

        def test_one(self):
            self.assertTrue(True)
"""


def _summary(stdout: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in stdout.splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            data[key.strip()] = value.strip()
    return data


def _verbose_ids(text: str) -> list[str]:
    return re.findall(r"\(([\w.]+)\) \.\.\.", text)


class TimedUnittestRunnerTest(unittest.TestCase):
    def _fixture(self, source: str) -> Path:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        (directory / "test_fixture.py").write_text(textwrap.dedent(source), encoding="utf-8")
        return directory

    def _run_timed(self, directory: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), "--start-dir", str(directory), *extra],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            check=False,
        )

    def test_passing_suite_exits_zero_with_counts_and_timings(self) -> None:
        proc = self._run_timed(self._fixture(PASS_SOURCE))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        summary = _summary(proc.stdout)
        self.assertEqual(summary["tests_run"], "2")
        self.assertEqual(summary["failures"], "0")
        self.assertEqual(summary["errors"], "0")
        self.assertEqual(summary["skipped"], "0")
        self.assertIn("sum_test_seconds:", proc.stdout)

    def test_executed_set_matches_standard_unittest_discovery(self) -> None:
        directory = self._fixture(PASS_SOURCE)
        proc = self._run_timed(directory, "--print-ids")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        timed_ids = [
            line.split("executed: ", 1)[1].strip()
            for line in proc.stdout.splitlines()
            if line.startswith("executed: ")
        ]
        standard = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(directory), "-v"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(timed_ids, _verbose_ids(standard.stderr))

    def test_failure_exits_non_zero(self) -> None:
        proc = self._run_timed(self._fixture(FAIL_SOURCE))
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(_summary(proc.stdout)["failures"], "1")

    def test_error_exits_non_zero(self) -> None:
        proc = self._run_timed(self._fixture(ERROR_SOURCE))
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(_summary(proc.stdout)["errors"], "1")

    def test_import_error_exits_non_zero(self) -> None:
        proc = self._run_timed(self._fixture(IMPORT_ERROR_SOURCE))
        self.assertNotEqual(proc.returncode, 0)
        self.assertGreaterEqual(int(_summary(proc.stdout)["errors"]), 1)

    def test_skip_is_counted_and_still_passes(self) -> None:
        proc = self._run_timed(self._fixture(SKIP_SOURCE))
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        summary = _summary(proc.stdout)
        self.assertEqual(summary["skipped"], "1")
        self.assertEqual(summary["tests_run"], "2")

    def test_setupclass_exception_fails(self) -> None:
        proc = self._run_timed(self._fixture(SETUPCLASS_SOURCE))
        self.assertNotEqual(proc.returncode, 0)
        self.assertGreaterEqual(int(_summary(proc.stdout)["errors"]), 1)

    def test_teardownclass_exception_fails(self) -> None:
        proc = self._run_timed(self._fixture(TEARDOWNCLASS_SOURCE))
        self.assertNotEqual(proc.returncode, 0)
        self.assertGreaterEqual(int(_summary(proc.stdout)["errors"]), 1)
