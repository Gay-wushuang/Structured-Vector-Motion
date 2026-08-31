import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    Evaluator,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
    build_evaluated_scene,
)
from svm.adapters import POPOutputAdapter, POPOutputError
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "005-empty-canvas.svm.json"
OUTPUT = ROOT / "examples" / "derived" / "020-pop-output" / "pop-output.json"
MEDIA_TYPE = "application/vnd.svm.pop-output+json"


class POPOutputGoldenPTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        producer = payload["producer"]
        self.output = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "derived_type": "pop-ordered-primitives",
                "output_identity": "svm-pop-output@0.1",
                "run_identity": payload["run_identity"],
                **producer,
            },
        )

    def request(self, *, namespace: str = "golden-p") -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.output.artifact_id,),
            options={"namespace": namespace},
        )

    def test_golden_p_imports_ordered_primitives_as_one_editable_revision(self) -> None:
        adapter = POPOutputAdapter()
        first = adapter.propose(self.request(), self.artifacts)
        second = adapter.propose(self.request(), self.artifacts)

        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(first.report.metrics, {"primitives": 3.0})
        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertEqual(len(self.store.revisions), 1)
        self.assertEqual(first.generator.parameters["identity"], "svm-pop-output-adapter@0.1")

        dry_run = ProposalAcceptor().validate(self.store, first, self.artifacts)
        self.assertEqual(len(self.store.revisions), 1)
        revision = ProposalAcceptor().accept(self.store, first, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, dry_run)
        self.assertEqual(len(self.store.revisions), 2)
        self.assertEqual(
            accepted["presentation"]["render_stack"],
            [
                "entity:golden-p-background",
                "entity:golden-p-primitive-0000",
                "entity:golden-p-primitive-0001",
                "entity:golden-p-primitive-0002",
            ],
        )
        self.assertEqual(
            [operation["type"] for operation in accepted["construction"]["operations"]],
            [
                "CreateRectangle",
                "CreateEllipse",
                "Transform",
                "CreateRectangle",
                "Transform",
                "CreateEllipse",
                "Transform",
            ],
        )
        self.assertEqual(
            {tag for entity in accepted["entities"] for tag in entity["semantic_tags"]},
            {"generated-primitive", "pop-output"},
        )
        self.assertTrue(all("parent_id" not in entity for entity in accepted["entities"]))
        evaluator = Evaluator(accepted)
        evaluator.evaluate_all()
        rendered = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 128, 96))).render(
            build_evaluated_scene(accepted, evaluator)
        )
        self.assertIn("#DC5046", rendered)
        self.assertIn("#285AA0", rendered)
        self.assertIn("matrix(0.906307787037 0.422618261741", rendered)

    def test_acceptance_reconstructs_the_exact_artifact_bound_change(self) -> None:
        proposal = POPOutputAdapter().propose(self.request(), self.artifacts)
        change = proposal.transaction.changes[0]
        fragment = change.fragment  # type: ignore[attr-defined]
        styles = copy.deepcopy(fragment.styles)
        styles[1]["fill"] = "#000000"
        forged_change = replace(change, fragment=replace(fragment, styles=tuple(styles)))
        forged = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(forged_change,)),
        )
        with self.assertRaisesRegex(ProposalArtifactError, "does not match"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_malformed_unsupported_and_provenance_drift_fail_closed(self) -> None:
        payload = json.loads(self.output.content)
        payload["primitives"][0]["shape_type"] = "path"
        unsupported = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=copy.deepcopy(self.output.provenance),
        )
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(unsupported.artifact_id,),
            options={"namespace": "bad-shape"},
        )
        with self.assertRaisesRegex(POPOutputError, "shape_type"):
            POPOutputAdapter().propose(request, self.artifacts)

        noncanonical = self.artifacts.import_bytes(
            json.dumps(json.loads(self.output.content), indent=2).encode(),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=copy.deepcopy(self.output.provenance),
        )
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(noncanonical.artifact_id,),
            options={"namespace": "noncanonical"},
        )
        with self.assertRaisesRegex(POPOutputError, "canonical JSON"):
            POPOutputAdapter().propose(request, self.artifacts)

        drifted_artifacts = ArtifactStore()
        drifted = drifted_artifacts.import_bytes(
            self.output.content,
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={**self.output.provenance, "seed": 8},
        )
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(drifted.artifact_id,),
            options={"namespace": "drifted"},
        )
        with self.assertRaisesRegex(POPOutputError, "provenance"):
            POPOutputAdapter().propose(request, drifted_artifacts)

    def test_generated_ids_are_checked_before_acceptance(self) -> None:
        proposal = POPOutputAdapter().propose(self.request(), self.artifacts)
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        with self.assertRaisesRegex(POPOutputError, "collides"):
            POPOutputAdapter().propose(
                AdapterRequest.from_store(
                    self.store,
                    self.store.head,
                    ("document",),
                    artifact_ids=(self.output.artifact_id,),
                    options={"namespace": "golden-p"},
                ),
                self.artifacts,
            )


if __name__ == "__main__":
    unittest.main()
