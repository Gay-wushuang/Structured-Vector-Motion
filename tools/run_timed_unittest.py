"""Measure per-test wall time for the full SVM unittest suite.

This is a drop-in replacement for ``python -m unittest discover -s tests -v``:
it uses the same discovery rule (``unittest.defaultTestLoader.discover`` over the
``tests`` directory with the default ``test*.py`` pattern), runs the exact same
tests in the same order, and preserves the same success/failure propagation and
process exit code.  The only addition is a per-test timing report measured with
``time.perf_counter``.

The runner can also emit a machine-readable metrics document with
``--metrics-json <path>`` and list the discovered tests without running them
with ``--collect-only``.  Neither option changes the default console output,
test ordering, or exit-code semantics.

It is implemented with the standard library only and uses one identical timing
methodology on Python 3.11 and Python 3.12.

Invoke it from the repository root as ``python -m tools.run_timed_unittest``
(as Full CI does): like ``python -m unittest``, this places the repository
root on ``sys.path`` so test modules importing the repository ``tests``
namespace (``import tests...``) resolve exactly as they do under the plain
unittest entry point. Running the file as a plain script puts ``tools/`` on
``sys.path`` instead and breaks such imports.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import unittest
from collections import Counter, defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

DEFAULT_SLOWEST = 30
METRICS_SCHEMA_VERSION = "svm-timed-unittest-metrics-0.1"


@dataclass(frozen=True)
class TestRecord:
    """One executed test and its observed wall time and outcome."""

    test_id: str
    duration_seconds: float
    status: str


class TimingTestResult(unittest.TextTestResult):
    """A ``TextTestResult`` that records every test's wall time and outcome."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.records: list[TestRecord] = []
        self._started_at: float | None = None

    def startTest(self, test: unittest.TestCase) -> None:
        self._started_at = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test: unittest.TestCase) -> None:
        super().stopTest(test)
        if self._started_at is not None:
            duration = max(0.0, time.perf_counter() - self._started_at)
            self.records.append(TestRecord(test.id(), duration, self._status(test)))
            self._started_at = None

    def _status(self, test: unittest.TestCase) -> str:
        if self._contains(self.skipped, test):
            return "skipped"
        if self._contains(self.errors, test):
            return "error"
        if self._contains(self.failures, test):
            return "failed"
        if self._contains(self.expectedFailures, test):
            return "expected_failure"
        if any(item is test for item in self.unexpectedSuccesses):
            return "unexpected_success"
        return "passed"

    @staticmethod
    def _contains(outcomes: list[tuple[object, str]], test: unittest.TestCase) -> bool:
        for outcome, _ in outcomes:
            # A failing subTest is reported against the parent TestCase.
            if outcome is test or getattr(outcome, "test_case", None) is test:
                return True
        return False


def build_suite(start_dir: Path, pattern: str) -> unittest.TestSuite:
    """Discover tests exactly as ``python -m unittest discover`` does."""
    loader = unittest.defaultTestLoader
    return loader.discover(str(start_dir), pattern=pattern, top_level_dir=str(start_dir))


def _iter_tests(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    """Yield the leaf tests of a discovered suite in discovery order."""
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _iter_tests(test)
        else:
            yield test


def _is_failed_test(test: unittest.TestCase) -> bool:
    """Return whether discovery represented an import failure as a fake test."""
    return type(test).__module__ == "unittest.loader" and type(test).__name__ == "_FailedTest"


def _collect_only(*, start_dir: Path, pattern: str, expected_count: int | None) -> int:
    """Print discovered test IDs without executing any test body or fixture."""
    try:
        suite = build_suite(start_dir, pattern)
        tests = list(_iter_tests(suite))
    except Exception as exc:  # pragma: no cover - defensive discovery guard
        print(f"timed unittest runner: discovery failed: {exc!r}", file=sys.stderr)
        return 1

    test_ids = [test.id() for test in tests]
    import_failures = [test.id() for test in tests if _is_failed_test(test)]
    duplicates = sorted(test_id for test_id, count in Counter(test_ids).items() if count > 1)

    problems: list[str] = []
    if import_failures:
        problems.extend(f"discovery/import error: {test_id}" for test_id in import_failures)
    if duplicates:
        problems.append(f"duplicate test id(s): {', '.join(duplicates)}")
    if not test_ids:
        problems.append("collected test set is empty")

    counted = suite.countTestCases()
    if counted != len(test_ids):
        problems.append(f"test count mismatch: suite reports {counted}, collected {len(test_ids)}")
    if expected_count is not None and len(test_ids) != expected_count:
        problems.append(f"expected {expected_count} tests, collected {len(test_ids)}")

    if problems:
        for problem in problems:
            print(f"timed unittest runner: {problem}", file=sys.stderr)
        return 1

    for test_id in test_ids:
        print(test_id)
    return 0


def _metrics_payload(
    *,
    start_arg: str,
    start_dir: Path,
    pattern: str,
    result: TimingTestResult,
    collected_ids: list[str],
    wall_seconds: float,
    process_cpu_seconds: float,
) -> dict[str, Any]:
    """Build an honest, JSON-serializable view of one timed execution."""
    pending: dict[str, deque[TestRecord]] = defaultdict(deque)
    for record in result.records:
        pending[record.test_id].append(record)

    entries: list[dict[str, Any]] = []
    for test_id in collected_ids:
        queue = pending.get(test_id)
        if queue:
            record = queue.popleft()
            entries.append(
                {
                    "index": len(entries),
                    "id": record.test_id,
                    "executed": True,
                    "duration_seconds": record.duration_seconds,
                    "status": record.status,
                }
            )
        else:
            entries.append(
                {
                    "index": len(entries),
                    "id": test_id,
                    "executed": False,
                    "duration_seconds": None,
                    "status": "not_run",
                }
            )

    # Defensive: an executed test absent from collection cannot be given a
    # reliable collection index, but its measured time must not be dropped.
    for queue in pending.values():
        for record in queue:
            entries.append(
                {
                    "index": len(entries),
                    "id": record.test_id,
                    "executed": True,
                    "duration_seconds": record.duration_seconds,
                    "status": record.status,
                }
            )

    total_wall = max(0.0, wall_seconds)
    sum_test = sum(record.duration_seconds for record in result.records)
    not_run = sum(1 for entry in entries if not entry["executed"])

    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        "runner": {
            "module": "tools.run_timed_unittest",
            "script": str(Path(__file__).resolve()),
            "argv": list(sys.argv),
            "cwd": str(Path.cwd()),
            "start_dir": start_arg,
            "resolved_start_dir": str(start_dir),
            "pattern": pattern,
        },
        "python": {
            "implementation": sys.implementation.name,
            "version": platform.python_version(),
            "version_info": list(sys.version_info),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "counts": {
            "collected": len(collected_ids),
            "tests_run": result.testsRun,
            "not_run": not_run,
            "skipped": len(result.skipped),
            "failures": len(result.failures),
            "errors": len(result.errors),
            "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses),
        },
        "timing": {
            "total_wall_seconds": total_wall,
            "sum_test_seconds": sum_test,
            "unattributed_seconds": max(0.0, total_wall - sum_test),
            "process_cpu_seconds": max(0.0, process_cpu_seconds),
            "process_cpu_scope": "discovery_and_run",
        },
        "tests": entries,
    }


def _write_metrics_json(path: Path, payload: dict[str, Any]) -> bool:
    """Write metrics and fail loudly if the document cannot be serialized or stored."""
    try:
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    except (TypeError, ValueError) as exc:
        print(
            f"timed unittest runner: failed to serialize metrics JSON for {str(path)!r}: {exc}",
            file=sys.stderr,
        )
        return False

    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        try:
            path.unlink()
        except OSError:
            pass
        print(
            f"timed unittest runner: failed to write metrics JSON to {str(path)!r}: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def _print_summary(
    *,
    start_dir: str,
    pattern: str,
    slowest: int,
    result: unittest.TestResult,
    records: list[TestRecord],
    wall_seconds: float,
    sum_test_seconds: float,
) -> None:
    print()
    print("=== timed unittest summary ===")
    print(f"start_dir: {start_dir}")
    print(f"pattern: {pattern}")
    print(f"tests_run: {result.testsRun}")
    print(f"skipped: {len(result.skipped)}")
    print(f"failures: {len(result.failures)}")
    print(f"errors: {len(result.errors)}")
    print(f"total_wall_seconds: {wall_seconds:.3f}")
    print(f"sum_test_seconds: {sum_test_seconds:.3f}")
    print(f"unattributed_seconds: {wall_seconds - sum_test_seconds:.3f}")
    print(f"slowest_{slowest}_tests:")
    for record in sorted(records, key=lambda item: item.duration_seconds, reverse=True)[:slowest]:
        print(f"  {record.duration_seconds:8.3f}  {record.test_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time the full unittest suite.")
    parser.add_argument(
        "--start-dir",
        default=None,
        help="Discovery root directory (default: <repository>/tests).",
    )
    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="Discovery file pattern (default: 'test*.py').",
    )
    parser.add_argument(
        "--slowest",
        type=int,
        default=DEFAULT_SLOWEST,
        help="Number of slowest tests to list (default: %(default)s).",
    )
    parser.add_argument(
        "--print-ids",
        action="store_true",
        help="Print every executed test id in execution order.",
    )
    parser.add_argument(
        "--metrics-json",
        type=Path,
        default=None,
        help="Write a machine-readable metrics JSON document to this path.",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Print discovered test ids in order without executing tests.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="With --collect-only, require exactly this many discovered tests.",
    )
    args = parser.parse_args(argv)

    if args.collect_only and args.metrics_json is not None:
        parser.error("--metrics-json cannot be combined with --collect-only")
    if args.expected_count is not None and not args.collect_only:
        parser.error("--expected-count requires --collect-only")
    if args.expected_count is not None and args.expected_count < 0:
        parser.error("--expected-count must be non-negative")

    repo_root = Path(__file__).resolve().parents[1]
    start_arg = args.start_dir if args.start_dir else "tests"
    start_dir = Path(args.start_dir).resolve() if args.start_dir else (repo_root / "tests")

    if args.collect_only:
        return _collect_only(
            start_dir=start_dir,
            pattern=args.pattern,
            expected_count=args.expected_count,
        )

    runner = unittest.TextTestRunner(verbosity=2, resultclass=TimingTestResult)
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    collected_ids: list[str] = []
    try:
        suite = build_suite(start_dir, args.pattern)
        if args.metrics_json is not None:
            # Collect before running: TestSuite.run() releases its test
            # references afterwards to reclaim memory.
            collected_ids = [test.id() for test in _iter_tests(suite)]
        result = cast(TimingTestResult, runner.run(suite))
    except Exception as exc:  # pragma: no cover - defensive discovery guard
        print(f"timed unittest runner: discovery failed: {exc!r}", file=sys.stderr)
        return 1
    wall_seconds = time.perf_counter() - wall_start
    process_cpu_seconds = time.process_time() - cpu_start

    records: list[TestRecord] = list(result.records)
    if args.print_ids:
        for record in records:
            print(f"executed: {record.test_id}")

    sum_test_seconds = sum(record.duration_seconds for record in records)
    _print_summary(
        start_dir=start_arg,
        pattern=args.pattern,
        slowest=args.slowest,
        result=result,
        records=records,
        wall_seconds=wall_seconds,
        sum_test_seconds=sum_test_seconds,
    )

    if args.metrics_json is not None:
        try:
            payload = _metrics_payload(
                start_arg=start_arg,
                start_dir=start_dir,
                pattern=args.pattern,
                result=result,
                collected_ids=collected_ids,
                wall_seconds=wall_seconds,
                process_cpu_seconds=process_cpu_seconds,
            )
        except Exception as exc:  # pragma: no cover - defensive metrics guard
            print(
                f"timed unittest runner: failed to build metrics JSON: {exc!r}",
                file=sys.stderr,
            )
            return 1
        if not _write_metrics_json(args.metrics_json, payload):
            return 1

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
