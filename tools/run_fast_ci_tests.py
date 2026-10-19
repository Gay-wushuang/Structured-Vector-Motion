"""Run the bounded, non-empty core contract suite used by Fast CI.

Full CI continues to discover and run every test in ``tests/``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TEST_TARGETS: tuple[tuple[str, int], ...] = (
    ("test_golden_a", 3),
    ("test_golden_b", 2),
    ("test_operations", 13),
    ("test_proposals", 6),
    ("test_anchored_regeneration", 9),
    ("test_motion_revision", 4),
    ("test_authored_group_schema_compatibility", 7),
    ("test_authored_group_authority", 22),
    ("test_authored_group_assembly.AuthoredGroupAssemblyTest", 15),
    ("test_authored_group_assembly.AuthoredGroupRenderedAcceptanceTest", 1),
    ("test_document_dialect_integration.DocumentDialectIntegrationTest", 20),
)


def main() -> int:
    tests_dir = Path(__file__).resolve().parents[1] / "tests"
    sys.path.insert(0, str(tests_dir))

    suite = unittest.TestSuite()
    for target, minimum in TEST_TARGETS:
        selected = unittest.defaultTestLoader.loadTestsFromName(target)
        count = selected.countTestCases()
        if count < minimum:
            print(
                f"Fast CI contract target {target!r} collected {count} < {minimum} tests",
                file=sys.stderr,
            )
            return 1
        suite.addTests(selected)

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
