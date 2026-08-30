import copy
import hashlib
import json
import unittest
from pathlib import Path

from test_cli import run_cli

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    PromoteComponentsChange,
    PromotedComponent,
    ProposalAcceptor,
    RevisionStore,
    Transaction,
)
from svm.adapters import ComponentPromotionAdapter
from svm.document import validate_document
from svm.evaluator import DocumentError, canonical_bytes
from svm.structural_relations import materialize_promoted_relations, structural_relation_id

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "imported" / "014-contained-analysis.svm.json"
ANALYSIS = ROOT / "examples" / "derived" / "014-contained-analysis" / "component-analysis.json"
GOLDEN = ROOT / "examples" / "imported" / "015-structural-relations.svm.json"
CANDIDATES = ("candidate:component-0001", "candidate:component-0002")
MEDIA_TYPE = "application/vnd.svm.component-analysis+json"


class StructuralRelationsGoldenJTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        content = ANALYSIS.read_bytes()
        artifact_id = f"artifact:{hashlib.sha256(content).hexdigest()}"
        reference = next(
            reference for reference in self.document["references"] if reference["id"] == artifact_id
        )
        metadata = reference["import_metadata"]
        self.analysis = self.artifacts.import_bytes(
            content,
            media_type=MEDIA_TYPE,
            kind=ArtifactKind(metadata["artifact_kind"]),
            provenance=metadata["provenance"],
        )

    def request(self, store: RevisionStore, candidate_ids: tuple[str, ...]) -> AdapterRequest:
        return AdapterRequest.from_store(
            store,
            store.head,
            ("document",),
            artifact_ids=(self.analysis.artifact_id,),
            options={"candidate_ids": list(candidate_ids)},
        )

    def test_golden_j_materializes_previewable_orthogonal_relations(self) -> None:
        proposal = ComponentPromotionAdapter().propose(
            self.request(self.store, CANDIDATES), self.artifacts
        )
        self.assertEqual(self.store.get_document(self.store.head), self.document)
        preview = proposal.preview.structural_relations
        self.assertEqual(
            [relation.relation_type for relation in preview],
            ["bounds-contains", "derived-from", "derived-from"],
        )
        self.assertTrue(
            all(relation.evidence_artifact_id == self.analysis.artifact_id for relation in preview)
        )

        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, json.loads(GOLDEN.read_text(encoding="utf-8")))
        relations = accepted["structural_relations"]
        self.assertEqual(
            [relation["type"] for relation in relations],
            ["bounds-contains", "derived-from", "derived-from"],
        )
        bounds_contains = relations[0]
        self.assertEqual(bounds_contains["container"], accepted["entities"][0]["id"])
        self.assertEqual(bounds_contains["contained"], accepted["entities"][1]["id"])
        self.assertEqual(bounds_contains["evidence"]["basis"], "strict-half-open-bounds@0.1")

        self.assertTrue(all("parent_id" not in entity for entity in accepted["entities"]))
        self.assertEqual(accepted["presentation"]["render_stack"], [])
        self.assertEqual(accepted["presentation"]["styles"], [])
        self.assertEqual(accepted["construction"]["operations"], [])
        self.assertEqual(accepted["construction"]["output_bindings"], [])
        self.assertEqual(accepted["animation"], self.document["animation"])

    def test_batch_and_incremental_promotion_converge(self) -> None:
        first = ComponentPromotionAdapter().propose(
            self.request(self.store, (CANDIDATES[0],)), self.artifacts
        )
        ProposalAcceptor().accept(self.store, first, self.artifacts)
        second = ComponentPromotionAdapter().propose(
            self.request(self.store, (CANDIDATES[1],)), self.artifacts
        )
        self.assertEqual(
            [relation.relation_type for relation in second.preview.structural_relations],
            ["bounds-contains", "derived-from"],
        )
        self.assertTrue(
            all(relation.status == "added" for relation in second.preview.structural_relations)
        )
        revision = ProposalAcceptor().accept(self.store, second, self.artifacts)
        self.assertEqual(
            self.store.get_document(revision.revision_id),
            json.loads(GOLDEN.read_text(encoding="utf-8")),
        )

        reverse_store = RevisionStore.create(self.document)
        second_first = ComponentPromotionAdapter().propose(
            self.request(reverse_store, (CANDIDATES[1],)), self.artifacts
        )
        ProposalAcceptor().accept(reverse_store, second_first, self.artifacts)
        first_second = ComponentPromotionAdapter().propose(
            self.request(reverse_store, (CANDIDATES[0],)), self.artifacts
        )
        reverse_revision = ProposalAcceptor().accept(reverse_store, first_second, self.artifacts)
        reverse_relations = reverse_store.get_document(reverse_revision.revision_id)[
            "structural_relations"
        ]
        self.assertEqual(
            reverse_relations,
            json.loads(GOLDEN.read_text(encoding="utf-8"))["structural_relations"],
        )
        self.assertEqual(
            canonical_bytes(reverse_relations),
            canonical_bytes(json.loads(GOLDEN.read_text(encoding="utf-8"))["structural_relations"]),
        )

    def test_forged_relation_identity_evidence_and_type_fail_closed(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        mutations = []

        wrong_id = copy.deepcopy(golden)
        wrong_id["structural_relations"][0]["id"] = "relation:derived-from:forged"
        mutations.append((wrong_id, "canonical ID"))

        wrong_direction = copy.deepcopy(golden)
        bounds_contains = wrong_direction["structural_relations"][0]
        bounds_contains["container"], bounds_contains["contained"] = (
            bounds_contains["contained"],
            bounds_contains["container"],
        )
        mutations.append((wrong_direction, "not supported"))

        wrong_evidence = copy.deepcopy(golden)
        wrong_evidence["structural_relations"][0]["evidence"]["contained_candidate_id"] = (
            CANDIDATES[0]
        )
        mutations.append((wrong_evidence, "not supported"))

        missing_bounds = copy.deepcopy(golden)
        del missing_bounds["entities"][1]["provenance"]["bounds"]
        mutations.append((missing_bounds, "provenance fields"))

        unsupported = copy.deepcopy(golden)
        unsupported["structural_relations"][0]["type"] = "overlaps"
        mutations.append((unsupported, "Unsupported"))

        for document, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(DocumentError, message):
                    validate_document(document)

    def test_relation_order_and_transitive_edges_fail_closed(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        unordered = copy.deepcopy(golden)
        unordered["structural_relations"].reverse()
        with self.assertRaisesRegex(DocumentError, "sorted"):
            validate_document(unordered)

        transitive = copy.deepcopy(golden)
        outer = transitive["entities"][0]
        middle = transitive["entities"][1]
        inner = copy.deepcopy(middle)
        inner["id"] = "entity:region-inner-regression"
        inner["provenance"]["candidate_id"] = "candidate:component-0003"
        inner["provenance"]["component_digest"] = f"sha256:{'3' * 64}"
        inner["provenance"]["bounds"] = [10, 10, 12, 12]
        transitive["entities"].append(inner)
        content = {
            "type": "bounds-contains",
            "container": outer["id"],
            "contained": inner["id"],
            "evidence": {
                "artifact_id": outer["provenance"]["artifact_id"],
                "container_candidate_id": outer["provenance"]["candidate_id"],
                "contained_candidate_id": inner["provenance"]["candidate_id"],
                "basis": "strict-half-open-bounds@0.1",
            },
        }
        transitive["structural_relations"].append(
            {"id": structural_relation_id(content), **content}
        )
        transitive["structural_relations"].sort(key=lambda relation: relation["id"])
        with self.assertRaisesRegex(DocumentError, "immediate containment"):
            validate_document(transitive)

    def test_relation_graph_must_be_complete(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for relation_type in ("derived-from", "bounds-contains"):
            incomplete = copy.deepcopy(golden)
            incomplete["structural_relations"] = [
                relation
                for relation in incomplete["structural_relations"]
                if relation["type"] != relation_type
            ]
            with self.subTest(relation_type=relation_type):
                with self.assertRaisesRegex(DocumentError, "complete canonical"):
                    validate_document(incomplete)

    def test_relation_materialization_limit_fails_closed(self) -> None:
        reference = next(
            item for item in self.document["references"] if item["id"] == self.analysis.artifact_id
        )
        components = tuple(
            PromotedComponent(
                artifact_id=self.analysis.artifact_id,
                candidate_id=f"candidate:component-{index:04d}",
                component_digest=f"sha256:{index:064x}",
                bounds=(0, 0, 1, 1),
            )
            for index in range(1, 514)
        )
        transaction = Transaction(
            transaction_id="transaction:relation-limit-regression",
            changes=(PromoteComponentsChange(components=components, references=(reference,)),),
        )
        with self.assertRaisesRegex(DocumentError, "limit of 512"):
            transaction.apply(self.document)
        self.assertEqual(self.store.get_document(self.store.head), self.document)

    def test_relation_limit_is_applied_per_analysis_artifact(self) -> None:
        entities = []
        for artifact_index in (1, 2):
            artifact_id = f"artifact:{artifact_index:064x}"
            for candidate_index in range(1, 301):
                entities.append(
                    {
                        "id": f"entity:artifact-{artifact_index}-{candidate_index:04d}",
                        "provenance": {
                            "type": "PromotedComponent",
                            "artifact_id": artifact_id,
                            "candidate_id": f"candidate:component-{candidate_index:04d}",
                            "component_digest": f"sha256:{candidate_index:064x}",
                            "bounds": [candidate_index, 0, candidate_index + 1, 1],
                        },
                    }
                )

        relations = materialize_promoted_relations(entities)
        self.assertEqual(len(relations), 600)
        self.assertTrue(all(relation["type"] == "derived-from" for relation in relations))

    def test_cli_previews_relations_and_validates_golden_j(self) -> None:
        preview = run_cli(
            "promote-components",
            str(BASE),
            str(ANALYSIS),
            "--candidate",
            CANDIDATES[0],
            "--candidate",
            CANDIDATES[1],
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(
            [relation["type"] for relation in json.loads(preview.stdout)["structural_relations"]],
            ["bounds-contains", "derived-from", "derived-from"],
        )
        validated = run_cli("validate", str(GOLDEN))
        self.assertEqual(validated.returncode, 0, validated.stderr)


if __name__ == "__main__":
    unittest.main()
