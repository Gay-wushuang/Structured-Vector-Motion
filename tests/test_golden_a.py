import json
import unittest
from pathlib import Path

from svm import EvaluationState, Evaluator, Quality

ROOT = Path(__file__).resolve().parents[1]


class GoldenTestA(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(
            (ROOT / "examples" / "001-head-basic.svm.json").read_text(encoding="utf-8")
        )
        self.evaluator = Evaluator(self.document)
        self.evaluator.evaluate_all(Quality.PREVIEW)

    def test_parameter_invalidation_is_isolated_and_identity_is_stable(self) -> None:
        old_head_value = self.evaluator.runtime["op:head_refine"].outputs["geometry"].value_id
        old_shield_value = self.evaluator.runtime["op:shield"].outputs["geometry"].value_id
        head_entity_id = self.document["entities"][0]["id"]

        affected = self.evaluator.set_parameter("op:head_base", "rx", 0.42)

        self.assertEqual(
            affected,
            {"op:head_base", "op:head_transform", "op:head_path", "op:head_refine", "op:hair_clip"},
        )
        self.assertEqual(self.evaluator.runtime["op:shield"].state, EvaluationState.CLEAN)
        self.assertEqual(self.evaluator.runtime["op:head_refine"].state, EvaluationState.DIRTY)
        self.assertIsNotNone(self.evaluator.runtime["op:head_refine"].stale_outputs)

        self.evaluator.evaluate("op:hair_clip", Quality.PREVIEW)

        new_head_value = self.evaluator.runtime["op:head_refine"].outputs["geometry"].value_id
        self.assertNotEqual(old_head_value, new_head_value)
        self.assertEqual(
            old_shield_value, self.evaluator.runtime["op:shield"].outputs["geometry"].value_id
        )
        self.assertEqual(head_entity_id, self.document["entities"][0]["id"])

    def test_repeat_evaluation_is_content_deterministic(self) -> None:
        first = self.evaluator.runtime["op:head_refine"].outputs["geometry"].value_id
        self.evaluator.invalidate("op:head_base")
        self.evaluator.evaluate("op:head_refine", Quality.PREVIEW)
        second = self.evaluator.runtime["op:head_refine"].outputs["geometry"].value_id
        self.assertEqual(first, second)

    def test_preview_result_is_not_reused_for_final_quality(self) -> None:
        preview_refine = self.evaluator.runtime["op:head_refine"].outputs["geometry"].value_id
        preview_clip = self.evaluator.runtime["op:hair_clip"].outputs["geometry"].value_id
        preview_base = self.evaluator.runtime["op:head_base"].outputs["geometry"].value_id
        preview_refine_key = self.evaluator.runtime["op:head_refine"].evaluation_key
        preview_base_key = self.evaluator.runtime["op:head_base"].evaluation_key

        self.evaluator.evaluate_all(Quality.FINAL)

        refine = self.evaluator.runtime["op:head_refine"]
        clip = self.evaluator.runtime["op:hair_clip"]
        base = self.evaluator.runtime["op:head_base"]
        self.assertNotEqual(preview_refine, refine.outputs["geometry"].value_id)
        self.assertNotEqual(preview_clip, clip.outputs["geometry"].value_id)
        self.assertNotEqual(preview_refine_key, refine.evaluation_key)
        self.assertEqual(preview_base, base.outputs["geometry"].value_id)
        self.assertEqual(preview_base_key, base.evaluation_key)
        self.assertEqual(refine.evaluated_quality, Quality.FINAL)


if __name__ == "__main__":
    unittest.main()
