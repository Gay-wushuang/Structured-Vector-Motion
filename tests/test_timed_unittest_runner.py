"""Behavioural self-test for ``tools/run_timed_unittest.py``.

Runs the timed runner against small generated fixture suites and checks that it
preserves the semantics of ``python -m unittest discover``: an identical
executed test set, identical success/failure/error/skip counting, and a
non-zero exit code for failures, errors and import errors.
"""

from __future__ import annotations

import json
import os
import re
import shutil
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

EXPECTED_FAILURE_SOURCE = """
    import unittest

    class SampleExpectedFailure(unittest.TestCase):
        @unittest.expectedFailure
        def test_expected(self):
            self.assertEqual(1, 2)
"""

UNEXPECTED_SUCCESS_SOURCE = """
    import unittest

    class SampleUnexpectedSuccess(unittest.TestCase):
        @unittest.expectedFailure
        def test_unexpected(self):
            self.assertEqual(1, 1)
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

NOT_EXECUTED_SOURCE = """
    import unittest

    class SampleNotExecuted(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            raise RuntimeError("collect-only must not run setUpClass")

        def test_never(self):
            raise RuntimeError("collect-only must not run test bodies")
"""

DUPLICATE_SOURCE = """
    import unittest

    class SampleDuplicate(unittest.TestCase):
        def test_once(self):
            self.assertTrue(True)

    def load_tests(loader, tests, pattern):
        suite = unittest.TestSuite()
        case = SampleDuplicate("test_once")
        suite.addTests((case, case))
        return suite
"""

EMPTY_SOURCE = """
    VALUE = 1
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

    def _run_metrics(
        self, directory: Path, *extra: str
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        metrics = directory / "metrics.json"
        proc = self._run_timed(directory, "--metrics-json", str(metrics), *extra)
        return proc, metrics

    def _run_timed_module(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "tools.run_timed_unittest", *args],
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

    def test_metrics_json_schema_and_timings(self) -> None:
        directory = self._fixture(PASS_SOURCE)
        proc, metrics_path = self._run_metrics(directory)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(metrics_path.read_text(encoding="utf-8"))

        self.assertEqual(data["schema_version"], "svm-timed-unittest-metrics-0.1")
        self.assertEqual(
            set(data["runner"]),
            {
                "module",
                "script",
                "argv",
                "cwd",
                "start_dir",
                "resolved_start_dir",
                "pattern",
            },
        )
        self.assertEqual(data["runner"]["start_dir"], str(directory))
        self.assertEqual(data["runner"]["resolved_start_dir"], str(directory.resolve()))
        self.assertEqual(data["runner"]["pattern"], "test*.py")
        self.assertIn("--metrics-json", data["runner"]["argv"])
        self.assertIsInstance(data["python"]["version"], str)
        self.assertIsInstance(data["python"]["version_info"], list)
        self.assertIsInstance(data["platform"]["system"], str)
        self.assertTrue(data["platform"]["system"])

        self.assertEqual(
            set(data["counts"]),
            {
                "collected",
                "tests_run",
                "not_run",
                "skipped",
                "failures",
                "errors",
                "expected_failures",
                "unexpected_successes",
            },
        )
        self.assertEqual(data["counts"]["collected"], 2)
        self.assertEqual(data["counts"]["tests_run"], 2)
        self.assertEqual(data["counts"]["not_run"], 0)
        self.assertEqual(data["counts"]["skipped"], 0)
        self.assertEqual(data["counts"]["failures"], 0)
        self.assertEqual(data["counts"]["errors"], 0)

        timing = data["timing"]
        self.assertEqual(
            set(timing),
            {
                "total_wall_seconds",
                "sum_test_seconds",
                "unattributed_seconds",
                "process_cpu_seconds",
                "process_cpu_scope",
            },
        )
        self.assertGreater(timing["total_wall_seconds"], 0)
        self.assertGreater(timing["sum_test_seconds"], 0)
        self.assertGreaterEqual(timing["unattributed_seconds"], 0)
        self.assertGreaterEqual(timing["process_cpu_seconds"], 0)
        self.assertEqual(timing["process_cpu_scope"], "discovery_and_run")

        tests = data["tests"]
        self.assertEqual(
            set(tests[0]),
            {"index", "id", "executed", "duration_seconds", "status"},
        )
        self.assertEqual(
            [entry["id"] for entry in tests],
            ["test_fixture.SampleOk.test_alpha", "test_fixture.SampleOk.test_beta"],
        )
        self.assertEqual([entry["index"] for entry in tests], [0, 1])
        self.assertTrue(all(entry["executed"] is True for entry in tests))
        self.assertTrue(all(isinstance(entry["duration_seconds"], float) for entry in tests))
        self.assertTrue(all(entry["duration_seconds"] >= 0 for entry in tests))
        self.assertEqual({entry["status"] for entry in tests}, {"passed"})
        self.assertAlmostEqual(
            timing["sum_test_seconds"],
            sum(entry["duration_seconds"] for entry in tests),
            places=6,
        )
        self.assertAlmostEqual(
            timing["unattributed_seconds"],
            timing["total_wall_seconds"] - timing["sum_test_seconds"],
            places=6,
        )

    def test_metrics_json_statuses_follow_result_outcomes(self) -> None:
        cases = (
            ("pass", PASS_SOURCE, ["passed", "passed"], 0),
            ("fail", FAIL_SOURCE, ["failed", "passed"], 1),
            ("error", ERROR_SOURCE, ["error"], 1),
            ("skip", SKIP_SOURCE, ["passed", "skipped"], 0),
            ("expected_failure", EXPECTED_FAILURE_SOURCE, ["expected_failure"], 0),
            ("unexpected_success", UNEXPECTED_SUCCESS_SOURCE, ["unexpected_success"], 1),
        )
        for label, source, expected_statuses, expected_exit in cases:
            with self.subTest(case=label):
                proc, metrics_path = self._run_metrics(self._fixture(source))
                self.assertEqual(proc.returncode, expected_exit, msg=proc.stderr)
                self.assertTrue(metrics_path.exists())
                data = json.loads(metrics_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    sorted(entry["status"] for entry in data["tests"]),
                    sorted(expected_statuses),
                )
                self.assertEqual(data["counts"]["tests_run"], len(expected_statuses))
                self.assertEqual(data["counts"]["failures"], expected_statuses.count("failed"))
                self.assertEqual(data["counts"]["errors"], expected_statuses.count("error"))
                self.assertEqual(data["counts"]["skipped"], expected_statuses.count("skipped"))
                self.assertEqual(
                    data["counts"]["expected_failures"],
                    expected_statuses.count("expected_failure"),
                )
                self.assertEqual(
                    data["counts"]["unexpected_successes"],
                    expected_statuses.count("unexpected_success"),
                )

    def test_metrics_not_run_for_setupclass_failure(self) -> None:
        proc, metrics_path = self._run_metrics(self._fixture(SETUPCLASS_SOURCE))
        self.assertNotEqual(proc.returncode, 0)
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        self.assertEqual(data["counts"]["tests_run"], 0)
        self.assertGreaterEqual(data["counts"]["errors"], 1)
        self.assertEqual(data["counts"]["not_run"], 2)
        self.assertEqual(len(data["tests"]), 2)
        self.assertEqual(
            [entry["id"] for entry in data["tests"]],
            [
                "test_fixture.SampleSetUpClass.test_one",
                "test_fixture.SampleSetUpClass.test_two",
            ],
        )
        for entry in data["tests"]:
            self.assertIs(entry["executed"], False)
            self.assertIsNone(entry["duration_seconds"])
            self.assertEqual(entry["status"], "not_run")

    def test_metrics_json_write_failure_is_reported(self) -> None:
        directory = self._fixture(PASS_SOURCE)
        missing = directory / "missing" / "metrics.json"
        proc = self._run_timed(directory, "--metrics-json", str(missing))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("metrics JSON", proc.stderr)
        self.assertFalse(missing.exists())

    def test_collect_only_does_not_execute_tests(self) -> None:
        proc = self._run_timed(self._fixture(NOT_EXECUTED_SOURCE), "--collect-only")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.stdout.splitlines(), ["test_fixture.SampleNotExecuted.test_never"])

    def test_collect_only_matches_standard_discovery_order(self) -> None:
        directory = self._fixture(PASS_SOURCE)
        proc = self._run_timed(directory, "--collect-only")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        standard = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(directory), "-v"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(proc.stdout.splitlines(), _verbose_ids(standard.stderr))
        self.assertEqual(
            proc.stdout.splitlines(),
            ["test_fixture.SampleOk.test_alpha", "test_fixture.SampleOk.test_beta"],
        )

    def test_collect_only_detects_import_error(self) -> None:
        proc = self._run_timed(self._fixture(IMPORT_ERROR_SOURCE), "--collect-only")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("discovery/import error", proc.stderr)

    def test_collect_only_detects_duplicate_ids(self) -> None:
        proc = self._run_timed(self._fixture(DUPLICATE_SOURCE), "--collect-only")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("duplicate test id", proc.stderr)

    def test_collect_only_detects_empty_suite(self) -> None:
        proc = self._run_timed(self._fixture(EMPTY_SOURCE), "--collect-only")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("empty", proc.stderr)

    def test_collect_only_enforces_expected_count(self) -> None:
        directory = self._fixture(PASS_SOURCE)
        ok = self._run_timed(directory, "--collect-only", "--expected-count", "2")
        self.assertEqual(ok.returncode, 0, msg=ok.stderr)
        self.assertEqual(len(ok.stdout.splitlines()), 2)

        bad = self._run_timed(directory, "--collect-only", "--expected-count", "3")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("expected 3 tests", bad.stderr)

    def test_module_invocation_writes_metrics_from_repository_root(self) -> None:
        directory = self._fixture(PASS_SOURCE)
        metrics_path = directory / "metrics.json"
        proc = self._run_timed_module(
            "--start-dir", str(directory), "--metrics-json", str(metrics_path)
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        self.assertEqual(data["counts"]["tests_run"], 2)
        self.assertEqual(data["counts"]["errors"], 0)


class TimedRunnerCIInvocationContractTest(unittest.TestCase):
    """Guard the Full CI invocation contract discovered by Full CI #178.

    Full CI must invoke the timed runner as a module from the repository root
    (``python -m tools.run_timed_unittest``), exactly like
    ``python -m unittest discover -s tests``: ``python -m`` places the
    repository root on ``sys.path`` so test modules importing the repository
    ``tests`` namespace (for example ``import tests.test_pop_group_candidates``)
    resolve. Invoking the runner as a plain script puts ``tools/`` on
    ``sys.path`` instead and turns every such module into
    ``ModuleNotFoundError`` (Full CI #178: six loader errors across four files).

    The contract is proven without re-executing real repository tests, which
    would violate strict execute-once semantics during a full regression run:

    - a synthetic repository fixture runs the real runner file under both the
      module and the script invocation forms, so exactly one synthetic probe
      test executes and the known-broken script form is proven to still fail;
    - a ``--collect-only`` pass over the real repository (a module that itself
      performs ``import tests...``) proves the real namespace resolves while
      executing no real test body or fixture.
    """

    def test_full_ci_invokes_timed_runner_as_module(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "python -m tools.run_timed_unittest",
            workflow,
            "Full CI must run the timed runner via 'python -m' from the repository root",
        )
        self.assertNotIn(
            "python tools/run_timed_unittest.py",
            workflow,
            "script-form invocation breaks repository 'tests.*' imports (Full CI #178)",
        )

    def test_module_invocation_imports_synthetic_tests_namespace(self) -> None:
        # A polluted ambient PYTHONPATH (for example one containing ".") would
        # hand the synthetic repository root to every invocation form and make
        # both assertions vacuous, so the subprocesses run without it.
        clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        with TemporaryDirectory() as name:
            repo = Path(name)
            tools = repo / "tools"
            tests = repo / "tests"
            tools.mkdir()
            tests.mkdir()
            shutil.copyfile(RUNNER, tools / "run_timed_unittest.py")
            (tests / "test_probe_support.py").write_text(
                'PROBE_SUPPORT_MARKER = "synthetic-tests-namespace"\n',
                encoding="utf-8",
            )
            (tests / "test_probe.py").write_text(
                textwrap.dedent(
                    """
                    import unittest

                    import tests.test_probe_support


                    class NamespaceProbe(unittest.TestCase):
                        def test_repository_root_is_on_sys_path(self) -> None:
                            self.assertEqual(
                                tests.test_probe_support.PROBE_SUPPORT_MARKER,
                                "synthetic-tests-namespace",
                            )
                    """
                ),
                encoding="utf-8",
            )
            module = subprocess.run(
                [sys.executable, "-m", "tools.run_timed_unittest", "--start-dir", str(tests)],
                capture_output=True,
                text=True,
                cwd=str(repo),
                env=clean_env,
                check=False,
            )
            self.assertEqual(module.returncode, 0, msg=module.stdout + module.stderr)
            summary = _summary(module.stdout)
            self.assertEqual(summary["tests_run"], "1")
            self.assertEqual(summary["errors"], "0")
            self.assertEqual(summary["failures"], "0")

            # The known-broken script form must keep failing: this proves the
            # positive assertion above really discriminates the Full CI #178
            # regression instead of passing unconditionally.
            script = subprocess.run(
                [sys.executable, str(tools / "run_timed_unittest.py"), "--start-dir", str(tests)],
                capture_output=True,
                text=True,
                cwd=str(repo),
                env=clean_env,
                check=False,
            )
            self.assertNotEqual(script.returncode, 0)
            self.assertEqual(_summary(script.stdout)["errors"], "1")
            self.assertIn("ModuleNotFoundError", script.stdout + script.stderr)

    def test_module_invocation_collects_real_tests_namespace_without_execution(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.run_timed_unittest",
                "--collect-only",
                "--pattern",
                "test_pop_group_promotion.py",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertEqual(proc.stderr, "")
        ids = proc.stdout.splitlines()
        self.assertGreaterEqual(len(ids), 1)
        self.assertTrue(all(test_id.startswith("test_pop_group_promotion.") for test_id in ids))
