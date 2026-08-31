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
    SetOperationParameterChange,
    Transaction,
    build_evaluated_scene,
)
from svm.adapters import POPOutputAdapter, POPOutputError, POPTokenExporter
from svm.adapters.pop_output import pop_generation_config_identity
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "005-empty-canvas.svm.json"
OUTPUT = ROOT / "examples" / "derived" / "020-pop-output" / "pop-output.json"
PREFIX = ROOT / "examples" / "derived" / "020-pop-output" / "operation-prefix.json"
MEDIA_TYPE = "application/vnd.svm.pop-output+json"
PREFIX_MEDIA_TYPE = "application/vnd.svm.pop-token-prefix+json"


class POPOutputGoldenPTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        producer = payload["producer"]
        prefix_payload = json.loads(PREFIX.read_text(encoding="utf-8"))
        self.prefix = self.artifacts.import_bytes(
            canonical_bytes(prefix_payload),
            media_type=PREFIX_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={
                "source_type": "pop-operation-prefix",
                "token_layout_identity": producer["token_layout_identity"],
                "quantization_identity": producer["quantization_identity"],
            },
        )
        self.output = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance={
                "derived_type": "pop-ordered-primitives",
                "output_identity": "svm-pop-output@0.2",
                "generation_config_identity": payload["generation_config_identity"],
                "prefix_artifact_id": self.prefix.artifact_id,
                **producer,
            },
        )

    def request(self, *, namespace: str = "golden-p") -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.prefix.artifact_id, self.output.artifact_id),
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
        self.assertEqual(first.generator.parameters["identity"], "svm-pop-output-adapter@0.2")
        self.assertEqual(first.generator.adapter_version, "0.2")

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
            [style["opacity"] for style in accepted["presentation"]["styles"]],
            [1, 0.5, 0.5, 0.5],
        )
        self.assertTrue(all("parent_id" not in entity for entity in accepted["entities"]))
        evaluator = Evaluator(accepted)
        evaluator.evaluate_all()
        rendered = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 256, 256))).render(
            build_evaluated_scene(accepted, evaluator)
        )
        self.assertIn("#DC5046", rendered)
        self.assertIn("#285AA0", rendered)
        self.assertIn("matrix(0.906307787037 0.422618261741", rendered)

    def test_exporter_reproduces_checked_in_raw_token_artifacts(self) -> None:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        producer = payload["producer"]
        exported = ArtifactStore()
        prefix, output = POPTokenExporter().export(
            exported,
            payload["raw_tokens"],
            prefix_length=payload["generation_context"]["prefix_length"],
            commit=producer["commit"],
            model_id=producer["model_id"],
            checkpoint_hash=producer["checkpoint_hash"],
            seed=producer["seed"],
            decoding=producer["decoding"],
            user_intent=payload["annotations"]["user_intent"],
        )
        self.assertEqual(prefix.content, canonical_bytes(json.loads(PREFIX.read_text())))
        self.assertEqual(output.content, canonical_bytes(json.loads(OUTPUT.read_text())))

    def test_declared_field_aware_sampling_provenance_is_accepted(self) -> None:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
        producer = payload["producer"]
        sampled_artifacts = ArtifactStore()
        prefix, output = POPTokenExporter().export(
            sampled_artifacts,
            payload["raw_tokens"],
            prefix_length=payload["generation_context"]["prefix_length"],
            commit=producer["commit"],
            model_id=producer["model_id"],
            checkpoint_hash=producer["checkpoint_hash"],
            seed=11,
            decoding={
                "strategy": "field-aware-sampling",
                "target_steps": 4,
                "sampling_policy_identity": "pop/gpt-sampling-config@d5489b0",
                "configuration": {"schedule": "upstream-default"},
            },
        )
        request = AdapterRequest(
            base_revision_id=self.store.head,
            document=self.store.get_document(self.store.head),
            scope=("document",),
            artifact_ids=(prefix.artifact_id, output.artifact_id),
            options={"namespace": "sampled-pop"},
        )
        proposal = POPOutputAdapter().propose(request, sampled_artifacts)
        self.assertEqual(
            proposal.generator.parameters["decoding"]["strategy"],
            "field-aware-sampling",
        )
        self.assertEqual(len(self.store.revisions), 1)

    def test_generation_config_identity_is_distinct_from_output_identity(self) -> None:
        first = json.loads(OUTPUT.read_text(encoding="utf-8"))
        different_output = copy.deepcopy(first)
        different_output["raw_tokens"][-1] -= 1
        self.assertEqual(
            pop_generation_config_identity(first),
            pop_generation_config_identity(different_output),
        )
        self.assertNotEqual(canonical_bytes(first), canonical_bytes(different_output))

        different_annotation = copy.deepcopy(first)
        different_annotation["annotations"]["user_intent"] = "testing"
        self.assertEqual(
            pop_generation_config_identity(first),
            pop_generation_config_identity(different_annotation),
        )
        self.assertNotEqual(canonical_bytes(first), canonical_bytes(different_annotation))

    def test_accepted_document_loads_and_renders_without_pop_artifacts(self) -> None:
        proposal = POPOutputAdapter().propose(self.request(), self.artifacts)
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        detached_document = json.loads(
            canonical_bytes(self.store.get_document(revision.revision_id))
        )
        detached_store = RevisionStore.create(detached_document)
        loaded = detached_store.get_document(detached_store.head)
        evaluator = Evaluator(loaded)
        evaluator.evaluate_all()
        rendered = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 256, 256))).render(
            build_evaluated_scene(loaded, evaluator)
        )
        self.assertIn("#285AA0", rendered)

    def test_one_primitive_can_be_edited_without_pop_or_other_value_changes(self) -> None:
        proposal = POPOutputAdapter().propose(self.request(), self.artifacts)
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        before = Evaluator(accepted)
        before.evaluate_all()
        operation_ids = [operation["id"] for operation in accepted["construction"]["operations"]]
        before_ids = {
            operation_id: before.runtime[operation_id].outputs["geometry"].value_id
            for operation_id in operation_ids
        }
        edit = Transaction(
            transaction_id="transaction:edit-pop-primitive-0001",
            changes=(
                SetOperationParameterChange(
                    "op:golden-p-primitive-0001-transform",
                    "matrix",
                    [1, 0, 0, 1, 90, 60],
                ),
            ),
            message="Move one accepted POP primitive without invoking POP",
        )
        edited_revision = self.store.commit(revision.revision_id, edit)
        after = Evaluator(self.store.get_document(edited_revision.revision_id))
        after.evaluate_all()
        self.assertNotEqual(
            before_ids["op:golden-p-primitive-0001-transform"],
            after.runtime["op:golden-p-primitive-0001-transform"].outputs["geometry"].value_id,
        )
        for operation_id in (
            "op:golden-p-primitive-0000-transform",
            "op:golden-p-primitive-0002-transform",
        ):
            self.assertEqual(
                before_ids[operation_id],
                after.runtime[operation_id].outputs["geometry"].value_id,
            )

    def test_acceptance_reconstructs_the_exact_artifact_bound_change(self) -> None:
        proposal = POPOutputAdapter().propose(self.request(), self.artifacts)
        change = proposal.transaction.changes[0]
        fragment = change.fragment  # type: ignore[attr-defined]
        styles = copy.deepcopy(fragment.styles)
        styles[1]["fill"] = "#000000"
        forged_change = replace(change, fragment=replace(fragment, styles=tuple(styles)))
        forged = replace(
            proposal, transaction=replace(proposal.transaction, changes=(forged_change,))
        )
        with self.assertRaisesRegex(ProposalArtifactError, "does not match"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_raw_decode_and_provenance_drift_fail_closed(self) -> None:
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
            artifact_ids=(self.prefix.artifact_id, unsupported.artifact_id),
            options={"namespace": "bad-shape"},
        )
        with self.assertRaisesRegex(POPOutputError, "decoded geometry"):
            POPOutputAdapter().propose(request, self.artifacts)

        drifted_artifacts = ArtifactStore()
        drifted_prefix = drifted_artifacts.import_bytes(
            self.prefix.content,
            media_type=PREFIX_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance=copy.deepcopy(self.prefix.provenance),
        )
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
            artifact_ids=(drifted_prefix.artifact_id, drifted.artifact_id),
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
                    artifact_ids=(self.prefix.artifact_id, self.output.artifact_id),
                    options={"namespace": "golden-p"},
                ),
                self.artifacts,
            )


if __name__ == "__main__":
    unittest.main()
