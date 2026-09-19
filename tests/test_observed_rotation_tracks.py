import unittest

from svm.adapters.observed_rotation_tracks import (
    ObservedRotationTracksError,
    _absolute_samples,
)


class ObservedRotationTrackMathTest(unittest.TestCase):
    def test_unwrapped_accumulation_crosses_wrap_boundary(self):
        samples = _absolute_samples(
            [
                {"source_tick": 0, "target_tick": 24, "rotation_degrees": {"status": "SUPPORTED", "value": 20}},
                {"source_tick": 24, "target_tick": 48, "rotation_degrees": {"status": "SUPPORTED", "value": 30}},
                {"source_tick": 48, "target_tick": 72, "rotation_degrees": {"status": "SUPPORTED", "value": -15}},
            ],
            170,
        )
        self.assertEqual([(tick, value) for tick, value, _ in samples], [(0, 170), (24, 190), (48, 220), (72, 205)])

    def test_negative_delta_is_signed_and_discontinuous_chain_rejects(self):
        samples = _absolute_samples(
            [{"source_tick": 0, "target_tick": 24, "rotation_degrees": {"status": "SUPPORTED", "value": -25}}],
            -20,
        )
        self.assertEqual([(tick, value) for tick, value, _ in samples], [(0, -20), (24, -45)])
        with self.assertRaises(ObservedRotationTracksError):
            _absolute_samples(
                [
                    {"source_tick": 0, "target_tick": 24, "rotation_degrees": {"status": "SUPPORTED", "value": 20}},
                    {"source_tick": 25, "target_tick": 48, "rotation_degrees": {"status": "SUPPORTED", "value": 10}},
                ],
                0,
            )

    def test_rotation_component_is_independent_of_scale(self):
        samples = _absolute_samples(
            [{"source_tick": 0, "target_tick": 24, "rotation_degrees": {"status": "SUPPORTED", "value": 30}, "scale": {"status": "UNCERTAIN", "value": None}}],
            10,
        )
        self.assertEqual(samples[-1][1], 40)
        with self.assertRaises(ObservedRotationTracksError):
            _absolute_samples(
                [{"source_tick": 0, "target_tick": 24, "rotation_degrees": {"status": "UNCERTAIN", "value": None}, "scale": {"status": "SUPPORTED", "value": 1.2}}],
                10,
            )
