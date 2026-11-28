import tempfile
import unittest
from pathlib import Path

import numpy as np

from .armor_validation import rectangle_bands, validate


class ArmorValidationTest(unittest.TestCase):
    def test_bands_preserve_separate_runs_in_each_row(self):
        mask = np.array([[1, 1, 0, 1], [1, 1, 0, 1], [0, 1, 0, 1]], dtype=np.uint8)
        rectangles, iou = rectangle_bands(mask, step=2)
        self.assertEqual(rectangles, [(0, 0, 2, 2), (3, 0, 1, 2), (1, 2, 1, 1), (3, 2, 1, 1)])
        self.assertEqual(iou, 1.0)

    def test_refuses_a_different_file_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            input_file = parent / "unmatched.mp4"
            input_file.write_bytes(b"unmatched")
            output = parent / "candidate"
            with self.assertRaisesRegex(ValueError, "Source SHA-256 does not match"):
                validate(input_file, output)
            self.assertFalse(output.exists())
