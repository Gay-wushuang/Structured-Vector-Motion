from __future__ import annotations

import copy
import json
import math
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from svm import (
    Evaluator,
    GeneratorProvenance,
    Proposal,
    ProposalAcceptor,
    RevisionStore,
    SetGroupTransformChange,
    Transaction,
    build_evaluated_scene,
)
from svm.change_authority import resolve_transaction_intents
from svm.renderers import SVGRenderer

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "001-head-basic.svm.json"
ARTIFACT_ID = "artifact:" + "0" * 64
GROUP_ID = "group:" + "1" * 64
TRANSFORM = {
    "translate": [2, 3],
    "rotation_degrees": 90,
    "scale": 2,
    "origin": [0, 0],
}


def group_document() -> dict[str, object]:
    document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    document["references"].append(
        {
            "id": ARTIFACT_ID,
            "uri": "artifact://" + "0" * 64,
            "content_hash": "sha256:" + "0" * 64,
            "media_type": "application/vnd.svm.pop-group-candidates+json;version=0.1",
            "import_metadata": {"fixture": "golden-q-v3"},
        }
    )
    document["groups"] = [
        {
            "id": GROUP_ID,
            "kind": "explicit-group",
            "members": ["entity:hair", "entity:head"],
            "provenance": {
                "candidate_id": "candidate:group:" + "2" * 64,
                "inference_id": "inference:group:" + "3" * 64,
                "inference_artifact_id": ARTIFACT_ID,
            },
        }
    ]
    return document


class GroupTransformGoldenQv3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.document = group_document()
        self.store = RevisionStore.create(self.document)
        assert self.store.head is not None
        self.base_revision_id = self.store.head

    def proposal(self, transform: dict[str, object] | None = None) -> Proposal:
        return Proposal(
            "proposal:set-group-transform",
            self.base_revision_id,
            GeneratorProvenance("editor:group-transform", "0.1", "svm-core", "0.1"),
            Transaction(
                "transaction:set-group-transform",
                (SetGroupTransformChange(GROUP_ID, transform or copy.deepcopy(TRANSFORM)),),
            ),
        )

    def test_group_transform_commits_atomically_without_rewriting_members(self) -> None:
        base = self.store.get_document(self.base_revision_id)
        proposal = self.proposal()
        preview = ProposalAcceptor().validate(self.store, proposal)
        revision = ProposalAcceptor().accept(self.store, proposal)
        accepted = self.store.get_document(revision.revision_id)

        self.assertEqual(accepted, preview)
        for field in (
            "entities",
            "construction",
            "presentation",
            "references",
            "structural_relations",
        ):
            self.assertEqual(accepted.get(field), base.get(field))
        self.assertEqual(accepted["groups"][0]["transform"], TRANSFORM)
        for field in ("id", "kind", "members", "provenance"):
            self.assertEqual(accepted["groups"][0][field], base["groups"][0][field])
        self.assertEqual(
            resolve_transaction_intents(proposal.transaction),
            (("set_group_transform", GROUP_ID, "transform"),),
        )

    def test_transform_is_an_outer_evaluation_composition(self) -> None:
        base = self.store.get_document(self.base_revision_id)
        base_scene = build_evaluated_scene(base, Evaluator(base))
        revision = ProposalAcceptor().accept(self.store, self.proposal())
        accepted = self.store.get_document(revision.revision_id)
        transformed_scene = build_evaluated_scene(accepted, Evaluator(accepted))
        before = {entity.entity_id: entity for entity in base_scene.entities}
        after = {entity.entity_id: entity for entity in transformed_scene.entities}

        for entity_id in ("entity:hair", "entity:head"):
            self.assertEqual(after[entity_id].geometry["kind"], "transform")
            self.assertEqual(after[entity_id].geometry["matrix"], [0.0, 2.0, -2.0, 0.0, 2.0, 3.0])
            self.assertEqual(after[entity_id].geometry["source"], before[entity_id].geometry)
            self.assertEqual(
                after[entity_id].geometry_value_id, before[entity_id].geometry_value_id
            )
        self.assertEqual(after["entity:shield"], before["entity:shield"])

        svg = SVGRenderer().render(transformed_scene)
        root = ET.fromstring(svg)
        transforms = [node.attrib.get("transform") for node in root.iter()]
        self.assertEqual(transforms.count("matrix(0 2 -2 0 2 3)"), 2)

    def test_fixed_origin_controls_rotation_and_uniform_scale(self) -> None:
        transform = {**TRANSFORM, "origin": [1, 1]}
        revision = ProposalAcceptor().accept(self.store, self.proposal(transform))
        accepted = self.store.get_document(revision.revision_id)
        scene = build_evaluated_scene(accepted, Evaluator(accepted))
        head = next(entity for entity in scene.entities if entity.entity_id == "entity:head")
        self.assertEqual(head.geometry["matrix"], [0.0, 2.0, -2.0, 0.0, 5.0, 2.0])

    def test_invalid_missing_noop_and_ambiguous_transforms_fail_closed(self) -> None:
        invalid = {**TRANSFORM, "scale": 0}
        with self.assertRaisesRegex(ValueError, "scale must be finite and positive"):
            ProposalAcceptor().accept(self.store, self.proposal(invalid))
        self.assertEqual(len(self.store.revisions), 1)

        missing = Proposal(
            "proposal:missing-group",
            self.base_revision_id,
            GeneratorProvenance("editor:group-transform", "0.1", "svm-core", "0.1"),
            Transaction(
                "transaction:missing-group",
                (SetGroupTransformChange("group:" + "9" * 64, TRANSFORM),),
            ),
        )
        with self.assertRaisesRegex(ValueError, "missing Group"):
            ProposalAcceptor().accept(self.store, missing)

        transformed = group_document()
        transformed["groups"][0]["transform"] = copy.deepcopy(TRANSFORM)
        transformed["groups"].append(
            {
                **copy.deepcopy(transformed["groups"][0]),
                "id": "group:" + "4" * 64,
                "provenance": {
                    "candidate_id": "candidate:group:" + "5" * 64,
                    "inference_id": "inference:group:" + "6" * 64,
                    "inference_artifact_id": ARTIFACT_ID,
                },
            }
        )
        with self.assertRaisesRegex(ValueError, "multiple transformed Groups"):
            RevisionStore.create(transformed)

        transformed["groups"].pop()
        noop_store = RevisionStore.create(transformed)
        assert noop_store.head is not None
        with self.assertRaisesRegex(ValueError, "must change"):
            noop_store.commit(
                noop_store.head,
                Transaction("transaction:noop", (SetGroupTransformChange(GROUP_ID, TRANSFORM),)),
            )

        non_finite = {**TRANSFORM, "rotation_degrees": math.nan}
        with self.assertRaisesRegex(ValueError, "rotation must be finite"):
            ProposalAcceptor().accept(self.store, self.proposal(non_finite))


if __name__ == "__main__":
    unittest.main()
