"""Focused T2-P1 contract tests.

These tests exercise the frozen T2-P0A protocol: closed configs, deterministic
fixtures, GT-free runtime workers, primary/witness validity, conflict/fail-closed
behavior, byte determinism, and the aggregate decision grammar.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

T2_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(T2_ROOT))

import generate_fixtures as fixtures  # noqa: E402
import gt_eval  # noqa: E402
import run_t2  # noqa: E402
import runtime  # noqa: E402

CONFIG_BY_FIXTURE = {
    fixture_id: T2_ROOT / config_name for fixture_id, config_name, _run_name in run_t2.FIXTURES
}
DECLARED_RUNTIME = runtime.environment_report()["opencv_requirement_satisfied"]
DECLARED_RUNTIME_REASON = (
    "requires the declared OpenCV 4.14.0.94 runtime; the frozen LK gate outcomes "
    "are environment-dependent"
)


class T2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = {
            fixture_id: runtime.load_config(config_path, REPO_ROOT)
            for fixture_id, config_path in CONFIG_BY_FIXTURE.items()
        }
        cls.frames = {
            fixture_id: runtime.load_runtime_frames(loaded)
            for fixture_id, loaded in cls.loaded.items()
        }

    def _worker(self, method: str, fixture_id: str) -> dict:
        raw, _cost = run_t2._run_worker(method, CONFIG_BY_FIXTURE[fixture_id], REPO_ROOT)
        return raw

    def _ground_truth(self, fixture_id: str) -> dict:
        return gt_eval.load_ground_truth(self.loaded[fixture_id])

    def _metrics(self, fixture_id: str, raw_b: dict, raw_c: dict) -> dict:
        return gt_eval.build_metrics(
            raw_b,
            raw_c,
            self.frames[fixture_id],
            self._ground_truth(fixture_id),
            self.loaded[fixture_id]["config"],
        )

    def test_configs_are_closed_frozen_and_have_no_gt_path(self) -> None:
        for fixture_id, loaded in self.loaded.items():
            config = loaded["config"]
            with self.subTest(fixture=fixture_id):
                self.assertNotIn("ground_truth", config)
                self.assertEqual(config["identity_claim"], "none")
                self.assertEqual(config["schema_version"], runtime.SCHEMA_VERSION)
                self.assertEqual(config["decision_thresholds"], runtime.FROZEN_DECISION_THRESHOLDS)
                self.assertEqual(config["group"]["limits"], runtime.FROZEN_LIMITS)
                self.assertEqual(config["method_b_budget"], runtime.FROZEN_B_BUDGET)
                self.assertEqual(config["method_c_budget"], runtime.FROZEN_C_BUDGET)
                self.assertEqual(config["group"]["transform_model"], "similarity")
                self.assertIsNone(config["group"]["reanchor"])

    def _assert_tamper_fails(self, fixture_id: str, mutate) -> None:
        config = copy.deepcopy(self.loaded[fixture_id]["config"])
        mutate(config)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(runtime.T2Error):
                runtime.load_config(path, REPO_ROOT)

    def test_config_tampering_fails_closed(self) -> None:
        mutations = {
            "ground_truth_path": lambda config: config.__setitem__(
                "ground_truth", "ground-truth.json"
            ),
            "missing_identity_claim": lambda config: config.pop("identity_claim"),
            "threshold_changed": lambda config: config["decision_thresholds"]["quality"][
                "f1-translation"
            ].__setitem__("c_group_iou_min", 0.98),
            "lk_parameter_changed": lambda config: config["method_b_budget"].__setitem__(
                "lk_window", [21, 21]
            ),
            "limit_changed": lambda config: config["group"]["limits"].__setitem__(
                "min_valid_anchor_points", 7
            ),
            "transform_model_changed": lambda config: config["group"].__setitem__(
                "transform_model", "translation"
            ),
            "identity_claim_changed": lambda config: config.__setitem__(
                "identity_claim", "group:0"
            ),
            "forbidden_authority_field": lambda config: config.__setitem__("track_id", "track:0"),
            "primary_is_witness": lambda config: config["group"].__setitem__(
                "witness_anchor_ids", [config["group"]["primary_anchor_id"]]
            ),
            "witness_on_primary_member": lambda config: config["group"]["anchors"][1].__setitem__(
                "member_id", "member:body"
            ),
            "witness_points_shared": lambda config: config["group"]["anchors"][1].__setitem__(
                "points", copy.deepcopy(config["group"]["anchors"][0]["points"])
            ),
            "witness_not_independent": lambda config: config["group"]["anchors"][1].__setitem__(
                "points",
                [[x + 1.0, y + 1.0] for x, y in config["group"]["anchors"][0]["points"]],
            ),
            "anchor_not_frame_zero": lambda config: config["group"]["anchors"][0].__setitem__(
                "frame_index", 1
            ),
            "too_few_anchor_points": lambda config: config["group"]["anchors"][1].__setitem__(
                "points", config["group"]["anchors"][1]["points"][:7]
            ),
            "anchor_outside_canvas": lambda config: config["group"]["anchors"][1][
                "points"
            ].__setitem__(0, [600.0, 600.0]),
            "anchor_duplicate_point": lambda config: config["group"]["anchors"][1][
                "points"
            ].__setitem__(1, copy.deepcopy(config["group"]["anchors"][1]["points"][0])),
            "duplicate_anchor_id": lambda config: config["group"]["anchors"][1].__setitem__(
                "anchor_id", config["group"]["anchors"][0]["anchor_id"]
            ),
            "duplicate_member_id": lambda config: config["group"]["members"][1].__setitem__(
                "primitive_id", config["group"]["members"][0]["primitive_id"]
            ),
            "one_member": lambda config: config["group"].__setitem__(
                "members", [config["group"]["members"][0]]
            ),
            "wrong_frame_path": lambda config: config["frames"][0].__setitem__(
                "path", "../tick_000.png"
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                self._assert_tamper_fails("f1-translation", mutate)

    def test_fixtures_are_deterministic_and_committed(self) -> None:
        for fixture_id in fixtures.FIXTURE_IDS:
            first = fixtures.build_fixture(fixture_id)
            second = fixtures.build_fixture(fixture_id)
            self.assertEqual(first, second)
            if not DECLARED_RUNTIME:
                continue
            for relative_path, content in first.items():
                self.assertEqual(
                    (T2_ROOT / "fixtures" / fixture_id / relative_path).read_bytes(),
                    content,
                )
        if DECLARED_RUNTIME:
            report = fixtures.check_fixtures(T2_ROOT / "fixtures")
            self.assertTrue(report["passed"])

    def test_fixture_safety_assertions(self) -> None:
        f3 = self._ground_truth("f3-low-texture")
        for anchor in f3["anchor_sets"]:
            spread, planarity = fixtures._eigen_statistics(anchor["points"])
            self.assertTrue(spread < 4.0 or planarity < 0.02)
        f4 = self._ground_truth("f4-occlusion")
        primary = next(
            anchor for anchor in f4["anchor_sets"] if anchor["anchor_id"] == f4["primary_anchor_id"]
        )
        group = f4["frames"][1]["group_transform"]
        moved = fixtures._transform(
            primary["points"],
            (
                group["translation"][0],
                group["translation"][1],
                group["rotation_degrees"],
                group["scale"],
            ),
        )
        x0, y0, x1, y1 = f4["occluders"][0]["rect"]
        covered = sum(1 for x, y in moved if x0 <= x < x1 and y0 <= y < y1)
        self.assertGreaterEqual(covered, 8)
        f5 = self._ground_truth("f5-conflicting-anchors")
        frame_zero = {
            member["primitive_id"]: member["points"] for member in f5["frames"][0]["members"]
        }
        frame_one = {
            member["primitive_id"]: member["points"] for member in f5["frames"][1]["members"]
        }
        body_shift = [
            sum(
                frame_one["member:body"][index][0] - frame_zero["member:body"][index][0]
                for index in range(len(frame_zero["member:body"]))
            )
            / len(frame_zero["member:body"]),
            sum(
                frame_one["member:body"][index][1] - frame_zero["member:body"][index][1]
                for index in range(len(frame_zero["member:body"]))
            )
            / len(frame_zero["member:body"]),
        ]
        decoy_shift = [
            sum(
                frame_one["member:decoy"][index][0] - frame_zero["member:decoy"][index][0]
                for index in range(len(frame_zero["member:decoy"]))
            )
            / len(frame_zero["member:decoy"]),
            sum(
                frame_one["member:decoy"][index][1] - frame_zero["member:decoy"][index][1]
                for index in range(len(frame_zero["member:decoy"]))
            )
            / len(frame_zero["member:decoy"]),
        ]
        self.assertGreater(
            ((body_shift[0] - decoy_shift[0]) ** 2 + (body_shift[1] - decoy_shift[1]) ** 2) ** 0.5,
            2.0,
        )

    def test_runtime_source_has_no_gt_loader(self) -> None:
        source = (T2_ROOT / "runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("load_ground_truth", source)
        self.assertNotIn("import gt_eval", source)
        self.assertNotIn("from gt_eval", source)

    def _temp_fixture(self, directory: Path, write_gt: bool) -> tuple[Path, Path]:
        source = T2_ROOT / "fixtures" / "f1-translation"
        target = directory / "fixtures" / "f1-translation"
        target.mkdir(parents=True)
        for path in source.glob("tick_*.png"):
            shutil.copyfile(path, target / path.name)
        if write_gt:
            (target / "ground-truth.json").write_text("{not valid json", encoding="utf-8")
        config = copy.deepcopy(self.loaded["f1-translation"]["config"])
        config["fixture_root"] = "fixtures/f1-translation"
        config_path = directory / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return config_path, target

    def test_missing_or_corrupt_gt_does_not_change_runtime_raw(self) -> None:
        for write_gt in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                config_path, _fixture = self._temp_fixture(Path(directory), write_gt)
                for method in ("B", "C"):
                    with self.subTest(method=method, gt_present=write_gt):
                        normal_raw, _ = run_t2._run_worker(
                            method, CONFIG_BY_FIXTURE["f1-translation"], REPO_ROOT
                        )
                        temp_raw, _ = run_t2._run_worker(method, config_path, Path(directory))
                        self.assertEqual(
                            runtime.canonical_bytes(normal_raw),
                            runtime.canonical_bytes(temp_raw),
                        )

    def test_c_frame_zero_identity_and_no_authority_fields(self) -> None:
        raw = self._worker("C", "f1-translation")
        frame_zero = raw["frames"][0]
        self.assertEqual(frame_zero["status"], "SUPPORTED")
        self.assertEqual(
            frame_zero["group_transform"]["cumulative_affine"],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
        self.assertIsNone(frame_zero["group_transform"]["step_affine"])
        expected = {
            member["primitive_id"]: member["frame_zero_points"]
            for member in self.loaded["f1-translation"]["members"]
        }
        for member in frame_zero["members"]:
            self.assertEqual(member["points"], expected[member["primitive_id"]])
        self.assertEqual(raw["artifact_classification"], runtime.CLASSIFICATION)
        self.assertEqual(raw["identity_claim"], "none")
        self.assertEqual(raw["method"], runtime.METHOD_C)

        def scan(value) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key, runtime.FORBIDDEN_KEYS)
                    scan(child)
            elif isinstance(value, list):
                for child in value:
                    scan(child)

        scan(raw)

    def test_b_and_c_raw_are_deterministic(self) -> None:
        for method in ("B", "C"):
            first, _ = run_t2._run_worker(method, CONFIG_BY_FIXTURE["f1-translation"], REPO_ROOT)
            second, _ = run_t2._run_worker(method, CONFIG_BY_FIXTURE["f1-translation"], REPO_ROOT)
            with self.subTest(method=method):
                self.assertEqual(runtime.canonical_bytes(first), runtime.canonical_bytes(second))

    @unittest.skipUnless(DECLARED_RUNTIME, DECLARED_RUNTIME_REASON)
    def test_b_control_status_under_frozen_lk_gate(self) -> None:
        f1 = self._worker("B", "f1-translation")
        self.assertTrue(all(frame["status"] == "SUPPORTED" for frame in f1["frames"]))
        f2 = self._worker("B", "f2-rotation-scale")
        self.assertEqual(f2["frames"][1]["status"], "ABSTAINED")
        self.assertEqual(f2["frames"][1]["reason"], "MEMBER_LOST")
        self.assertEqual(f2["frames"][2]["reason"], "PREVIOUS_TRANSITION_ABSTAINED")

    @unittest.skipUnless(DECLARED_RUNTIME, DECLARED_RUNTIME_REASON)
    def test_method_c_fail_closed_scenarios(self) -> None:
        f3 = self._worker("C", "f3-low-texture")
        self.assertEqual(f3["frames"][1]["status"], "ABSTAINED")
        self.assertIn(
            f3["frames"][1]["reason"],
            {
                "PRIMARY_ANCHOR_LOST",
                "WITNESS_ANCHOR_LOST",
                "ANCHOR_DEGENERATE",
                "INSUFFICIENT_VALID_ANCHOR_TRACKS",
                "LK_QUALITY_TOO_LOW",
                "ANCHOR_RESIDUAL_TOO_HIGH",
                "ANCHOR_FIT_FAILED",
            },
        )
        self.assertEqual(f3["frames"][2]["reason"], "PREVIOUS_TRANSITION_ABSTAINED")
        f4 = self._worker("C", "f4-occlusion")
        self.assertEqual(f4["frames"][1]["status"], "ABSTAINED")
        self.assertEqual(f4["frames"][2]["reason"], "PREVIOUS_TRANSITION_ABSTAINED")
        f5 = self._worker("C", "f5-conflicting-anchors")
        self.assertEqual(f5["frames"][1]["reason"], "ANCHOR_CONFLICT")
        self.assertEqual(f5["frames"][2]["reason"], "PREVIOUS_TRANSITION_ABSTAINED")

    def test_metrics_and_rendering_are_deterministic(self) -> None:
        raw_b = self._worker("B", "f1-translation")
        raw_c = self._worker("C", "f1-translation")
        first = self._metrics("f1-translation", raw_b, raw_c)
        second = self._metrics("f1-translation", raw_b, raw_c)
        self.assertEqual(runtime.canonical_bytes(first), runtime.canonical_bytes(second))
        gt = self._ground_truth("f1-translation")
        frames_first = gt_eval.render_comparison_frames(
            raw_b, raw_c, self.frames["f1-translation"], gt
        )
        frames_second = gt_eval.render_comparison_frames(
            raw_b, raw_c, self.frames["f1-translation"], gt
        )
        self.assertEqual(
            [frame.tobytes() for frame in frames_first],
            [frame.tobytes() for frame in frames_second],
        )

    def test_gt_metrics_run_only_after_raw_is_written(self) -> None:
        observed: list[tuple[bool, bool]] = []

        def fake_load(loaded):
            del loaded
            observed.append(
                (
                    (output_dir / "raw/method-b.json").is_file(),
                    (output_dir / "raw/method-c.json").is_file(),
                )
            )
            raise runtime.T2Error("synthetic post-raw stop")

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "run"
            with (
                mock.patch.object(run_t2, "_guard_output", lambda path, force: path.resolve()),
                mock.patch.object(gt_eval, "load_ground_truth", fake_load),
            ):
                with self.assertRaises(runtime.T2Error):
                    run_t2.prepare_fixture(
                        CONFIG_BY_FIXTURE["f1-translation"],
                        output_dir,
                        REPO_ROOT,
                        force=True,
                    )
        self.assertEqual(observed, [(True, True)])

    def test_t1_canonical_snapshot_is_unchanged(self) -> None:
        self.assertTrue(run_t2.verify_t1_snapshot()["passed"])

    def test_transform_bounds_are_enforced(self) -> None:
        limits = runtime.FROZEN_LIMITS
        self.assertIsNone(runtime._bounds_reason([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], limits))
        self.assertIsNone(runtime._bounds_reason([[1.0, 0.0, 10.0], [0.0, 1.0, 20.0]], limits))
        self.assertEqual(
            runtime._bounds_reason([[0.4, 0.0, 0.0], [0.0, 0.4, 0.0]], limits),
            "TRANSFORM_OUT_OF_BOUNDS",
        )
        self.assertEqual(
            runtime._bounds_reason([[2.1, 0.0, 0.0], [0.0, 2.1, 0.0]], limits),
            "TRANSFORM_OUT_OF_BOUNDS",
        )
        angle = math.radians(16.0)
        self.assertEqual(
            runtime._bounds_reason(
                [
                    [math.cos(angle), -math.sin(angle), 0.0],
                    [math.sin(angle), math.cos(angle), 0.0],
                ],
                limits,
            ),
            "TRANSFORM_OUT_OF_BOUNDS",
        )
        self.assertEqual(
            runtime._bounds_reason([[1.0, 0.0, 65.0], [0.0, 1.0, 0.0]], limits),
            "TRANSFORM_OUT_OF_BOUNDS",
        )

    def test_decision_grammar(self) -> None:
        def quality(status: str, b_control_valid: bool = True) -> dict:
            return {"status": status, "b_control_valid": b_control_valid}

        def evaluation(
            f1: str = "PASS",
            f2: str = "PASS",
            f3: str = "PASS",
            f4: str = "PASS",
            f5: str = "PASS",
            f2_b_valid: bool = True,
        ) -> dict:
            return {
                "f1-translation": {"quality": quality(f1)},
                "f2-rotation-scale": {"quality": quality(f2, f2_b_valid)},
                "f3-low-texture": {"fail_closed": {"status": f3}},
                "f4-occlusion": {"fail_closed": {"status": f4}},
                "f5-conflicting-anchors": {"fail_closed": {"status": f5}},
            }

        def metrics(rmse_b: float = 1.0, rmse_c: float = 0.5) -> dict:
            summaries = {
                "B": {"mean_group_vertex_rmse_px": rmse_b},
                "C": {"mean_group_vertex_rmse_px": rmse_c},
            }
            return {
                fixture: {
                    "methods": {"B": {"summary": summaries["B"]}, "C": {"summary": summaries["C"]}}
                }
                for fixture in ("f1-translation", "f2-rotation-scale")
            }

        def costs(ratio: float) -> dict:
            return {
                fixture: {
                    "B": {"wall_time_seconds": 1.0},
                    "C": {"wall_time_seconds": ratio},
                }
                for fixture in CONFIG_BY_FIXTURE
            }

        environment = {"opencv_requirement_satisfied": True}
        deterministic = {"full_run_byte_identical": True}

        go = gt_eval.decide_overall(evaluation(), metrics(), costs(0.5), environment, deterministic)
        self.assertEqual(go["outcome"], "GO")
        self.assertEqual(go["stop_reasons"], [])

        inconclusive = gt_eval.decide_overall(
            evaluation(f3="INCONCLUSIVE"), metrics(), costs(0.5), environment, deterministic
        )
        self.assertEqual(inconclusive["outcome"], "GO")
        self.assertIn("F3_INCONCLUSIVE", inconclusive["unresolved_limits"])

        f4_conditional = gt_eval.decide_overall(
            evaluation(f4="CONDITIONAL"), metrics(), costs(0.5), environment, deterministic
        )
        self.assertEqual(f4_conditional["outcome"], "CONDITIONAL")

        f3_fail_open = gt_eval.decide_overall(
            evaluation(f3="FAIL_OPEN"), metrics(), costs(0.5), environment, deterministic
        )
        self.assertEqual(f3_fail_open["outcome"], "STOP")

        invalid_control = gt_eval.decide_overall(
            evaluation(f2_b_valid=False), metrics(), costs(0.5), environment, deterministic
        )
        self.assertEqual(invalid_control["outcome"], "STOP")

        environment_mismatch = gt_eval.decide_overall(
            evaluation(),
            metrics(),
            costs(0.5),
            {"opencv_requirement_satisfied": False},
            deterministic,
        )
        self.assertEqual(environment_mismatch["outcome"], "CONDITIONAL")

        cost_conditional = gt_eval.decide_overall(
            evaluation(), metrics(), costs(1.2), environment, deterministic
        )
        self.assertEqual(cost_conditional["outcome"], "CONDITIONAL")

        cost_gain = gt_eval.decide_overall(
            evaluation(), metrics(rmse_b=1.0, rmse_c=0.5), costs(1.7), environment, deterministic
        )
        self.assertEqual(cost_gain["outcome"], "CONDITIONAL")
        self.assertTrue(cost_gain["compensating_quality_gain"])

        cost_no_gain = gt_eval.decide_overall(
            evaluation(), metrics(rmse_b=1.0, rmse_c=1.0), costs(1.7), environment, deterministic
        )
        self.assertEqual(cost_no_gain["outcome"], "STOP")


if __name__ == "__main__":
    unittest.main()
