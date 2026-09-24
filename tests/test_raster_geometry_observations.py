import unittest
from pathlib import Path

from svm.adapters.observed_similarity_motion import (
    RASTER_POLICY_IDENTITY,
    RASTER_RMS_PIXELS,
    RASTER_SUPPORTED_RESIDUAL,
    _similarity_observation,
)
from svm.backends.polygon_set import canonicalize_polygon_set

FIXTURE = Path(__file__).resolve().parents[1] / "examples/035-controlled-raster-recovery"


def pixel_landmarks(name):
    import cv2

    image = cv2.imread(str(FIXTURE / f"{name}.png"), 0)
    contours, _ = cv2.findContours(255 - image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    raw = cv2.approxPolyDP(contours[0], 1.0, True).reshape(-1, 2).tolist()
    points = canonicalize_polygon_set([{"exterior": raw, "holes": []}])["polygons"][0]["exterior"][
        :-1
    ]
    import math

    start = max(
        range(len(points)), key=lambda i: math.dist(points[i], points[(i + 1) % len(points)])
    )
    return {
        "geometry": {
            "type": "ordered-landmarks",
            "points": points[start:] + points[:start],
            "rotation_symmetry": "none",
        }
    }


class RasterGeometryObservationTest(unittest.TestCase):
    def test_raster_policy_requires_both_residual_limits(self):
        self.assertEqual(RASTER_SUPPORTED_RESIDUAL, 0.01)
        self.assertEqual(RASTER_RMS_PIXELS, 0.75)

        def geometry(points, factor):
            return {
                "geometry": {
                    "type": "ordered-landmarks",
                    "rotation_symmetry": "none",
                    "points": [[x * factor, y * factor] for x, y in points],
                }
            }

        source = [[0, 0], [100, 0], [0, 100]]
        for factor, target, status in (
            (1, [[0, 0], [100, 0], [0, 102]], "SUPPORTED"),
            (10, [[0, 0], [100, 0], [0, 102]], "UNCERTAIN"),
            (0.01, [[0, 0], [100, 0], [0, 110]], "REJECTED"),
        ):
            result = _similarity_observation(
                geometry(source, factor), geometry(target, factor), policy=RASTER_POLICY_IDENTITY
            )
            self.assertEqual(result["status"], status)
            if factor == 10:
                self.assertLess(result["fit"]["normalized_rms"], RASTER_SUPPORTED_RESIDUAL)
                self.assertGreater(result["fit"]["rms_error"], RASTER_RMS_PIXELS)
            if factor == 0.01:
                self.assertLess(result["fit"]["rms_error"], RASTER_RMS_PIXELS)
                self.assertGreater(result["fit"]["normalized_rms"], RASTER_SUPPORTED_RESIDUAL)

    def test_real_pixel_quantization_blocks_exact_s4(self):
        result = _similarity_observation(pixel_landmarks("base"), pixel_landmarks("rotation"))
        self.assertLess(result["fit"]["rms_error"], 0.5)
        self.assertEqual(result["rotation_degrees"]["status"], "UNCERTAIN")
