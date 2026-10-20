"""Measure per-test wall time for the full SVM unittest suite.

This is a drop-in replacement for ``python -m unittest discover -s tests -v``:
it uses the same discovery rule (``unittest.defaultTestLoader.discover`` over the
``tests`` directory with the default ``test*.py`` pattern), runs the exact same
tests in the same order, and preserves the same success/failure propagation and
process exit code.  The only addition is a per-test timing report measured with
``time.perf_counter``.

It is implemented with the standard library only and uses one identical timing
methodology on Python 3.11 and Python 3.12.
"""

from __future__ import annotations

import argparse
import sys
import time
import unittest
from pathlib import Path

DEFAULT_SLOWEST = 30


class TimingTestResult(unittest.TextTestResult):
    """A ``TextTestResult`` that records the wall time of every test."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.durations: list[tuple[float, str]] = []
        self._started_at: float | None = None
        self._current_id: str = ""

    def startTest(self, test: unittest.TestCase) -> None:
        self._started_at = time.perf_counter()
        self._current_id = test.id()
        super().startTest(test)

    def stopTest(self, test: unittest.TestCase) -> None:
        super().stopTest(test)
        if self._started_at is not None:
            self.durations.append((time.perf_counter() - self._started_at, self._current_id))
            self._started_at = None


def build_suite(start_dir: Path, pattern: str) -> unittest.TestSuite:
    """Discover tests exactly as ``python -m unittest discover`` does."""
    loader = unittest.defaultTestLoader
    return loader.discover(str(start_dir), pattern=pattern, top_level_dir=str(start_dir))


def _print_summary(
    *,
    start_dir: str,
    pattern: str,
    slowest: int,
    result: unittest.TestResult,
    durations: list[tuple[float, str]],
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
    for duration, test_id in sorted(durations, key=lambda item: item[0], reverse=True)[:slowest]:
        print(f"  {duration:8.3f}  {test_id}")


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
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    start_arg = args.start_dir if args.start_dir else "tests"
    start_dir = Path(args.start_dir).resolve() if args.start_dir else (repo_root / "tests")

    runner = unittest.TextTestRunner(verbosity=2, resultclass=TimingTestResult)
    wall_start = time.perf_counter()
    try:
        suite = build_suite(start_dir, args.pattern)
        result = runner.run(suite)
    except Exception as exc:  # pragma: no cover - defensive discovery guard
        print(f"timed unittest runner: discovery failed: {exc!r}", file=sys.stderr)
        return 1
    wall_seconds = time.perf_counter() - wall_start

    durations: list[tuple[float, str]] = list(getattr(result, "durations", []))
    if args.print_ids:
        for _, test_id in durations:
            print(f"executed: {test_id}")

    sum_test_seconds = sum(duration for duration, _ in durations)
    _print_summary(
        start_dir=start_arg,
        pattern=args.pattern,
        slowest=args.slowest,
        result=result,
        durations=durations,
        wall_seconds=wall_seconds,
        sum_test_seconds=sum_test_seconds,
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
