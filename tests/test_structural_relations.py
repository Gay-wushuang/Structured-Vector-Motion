import copy
import hashlib
import json
import unittest
from pathlib import Path

from test_cli import run_cli

from svm import AdapterRequest, ArtifactKind, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters import ComponentPromotionAdapter
from svm.document import validate_document
from svm.evaluator import DocumentError

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
            ["derived-from", "derived-from", "contains"],
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
            ["derived-from", "derived-from", "contains"],
        )
        contains = relations[2]
        self.assertEqual(contains["container"], accepted["entities"][0]["id"])
        self.assertEqual(contains["contained"], accepted["entities"][1]["id"])
        self.assertEqual(contains["evidence"]["basis"], "strict-half-open-bounds@0.1")

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
            ["derived-from", "contains"],
        )
        revision = ProposalAcceptor().accept(self.store, second, self.artifacts)
        self.assertEqual(
            self.store.get_document(revision.revision_id),
            json.loads(GOLDEN.read_text(encoding="utf-8")),
        )

    def test_forged_relation_identity_evidence_and_type_fail_closed(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        mutations = []

        wrong_id = copy.deepcopy(golden)
        wrong_id["structural_relations"][0]["id"] = "relation:derived-from:forged"
        mutations.append((wrong_id, "canonical ID"))

        wrong_direction = copy.deepcopy(golden)
        contains = wrong_direction["structural_relations"][2]
        contains["container"], contains["contained"] = contains["contained"], contains["container"]
        mutations.append((wrong_direction, "not supported"))

        wrong_evidence = copy.deepcopy(golden)
        wrong_evidence["structural_relations"][2]["evidence"]["contained_candidate_id"] = (
            CANDIDATES[0]
        )
        mutations.append((wrong_evidence, "not supported"))

        missing_bounds = copy.deepcopy(golden)
        del missing_bounds["entities"][1]["provenance"]["bounds"]
        mutations.append((missing_bounds, "not supported"))

        unsupported = copy.deepcopy(golden)
        unsupported["structural_relations"][2]["type"] = "overlaps"
        mutations.append((unsupported, "Unsupported"))

        for document, message in mutations:
            with self.subTest(message=message):
                with self.assertRaisesRegex(DocumentError, message):
                    validate_document(document)

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
            ["derived-from", "derived-from", "contains"],
        )
        validated = run_cli("validate", str(GOLDEN))
        self.assertEqual(validated.returncode, 0, validated.stderr)


if __name__ == "__main__":
    unittest.main()
