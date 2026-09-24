import unittest
from pathlib import Path

from svm.adapters.observed_similarity_motion import _similarity_observation
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
    def test_real_pixel_quantization_blocks_exact_s4(self):
        result = _similarity_observation(pixel_landmarks("base"), pixel_landmarks("rotation"))
        self.assertLess(result["fit"]["rms_error"], 0.5)
        self.assertEqual(result["rotation_degrees"]["status"], "SUPPORTED")
