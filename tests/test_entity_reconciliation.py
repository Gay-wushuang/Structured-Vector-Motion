import copy
import json
import tempfile
import unittest
from pathlib import Path

from test_cli import run_cli

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    ProposalAcceptor,
    ProposalConflictError,
    ProposalPolicyError,
    RevisionStore,
)
from svm.adapters import BitmapReconcileAdapter, BitmapTraceError

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "imported" / "010-structured-trace.svm.json"
SOURCE = ROOT / "examples" / "assets" / "005-retrace-source.png"
GOLDEN = ROOT / "examples" / "imported" / "011-reconciled-trace.svm.json"
SCOPE = (
    "entity:trace-structured-0000",
    "entity:trace-structured-0001",
    "entity:trace-structured-0002",
)


class EntityReconciliationGoldenGTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        self.artifact = self.artifacts.import_bytes(
            SOURCE.read_bytes(),
            media_type="image/png",
            kind=ArtifactKind.REFERENCE,
            provenance={"source_name": SOURCE.name},
        )

    def request(self, **options: object) -> AdapterRequest:
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            SCOPE,
            artifact_ids=(self.artifact.artifact_id,),
            options={"namespace": "structured", **options},
        )

    def test_golden_g_preview_then_atomic_acceptance_preserves_matched_identity(self) -> None:
        proposal = BitmapReconcileAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertIsNotNone(proposal.preview)
        self.assertEqual(
            proposal.report.metrics,
            {"unchanged": 1.0, "changed": 1.0, "added": 1.0, "removed": 1.0},
        )
        preview = proposal.preview
        statuses = [item.status for item in preview.entity_diffs]
        self.assertEqual(statuses, ["unchanged", "changed", "added", "removed"])
        self.assertEqual(preview.entity_diffs[0].match_score, 1.0)
        self.assertEqual(preview.entity_diffs[0].entity_id, SCOPE[0])
        self.assertEqual(preview.entity_diffs[1].entity_id, SCOPE[1])
        self.assertEqual(preview.entity_diffs[3].entity_id, SCOPE[2])

        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, json.loads(GOLDEN.read_text(encoding="utf-8")))
        entity_ids = [entity["id"] for entity in accepted["entities"]]
        self.assertIn(SCOPE[0], entity_ids)
        self.assertIn(SCOPE[1], entity_ids)
        self.assertNotIn(SCOPE[2], entity_ids)
        operation_ids = {operation["id"] for operation in accepted["construction"]["operations"]}
        for entity_index in (0, 1):
            self.assertIn(f"op:trace-structured-{entity_index:04d}-path", operation_ids)
            self.assertIn(f"op:trace-structured-{entity_index:04d}-planar", operation_ids)
        self.assertNotIn("op:trace-structured-0002-path", operation_ids)
        self.assertEqual(len(accepted["references"]), 2)

    def test_stale_preview_conflicts_and_permission_can_deny_reconciliation(self) -> None:
        proposal = BitmapReconcileAdapter().propose(self.request(), self.artifacts)
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)

        protected = copy.deepcopy(self.document)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-retrace",
                "actor": "adapter:bitmap-reconcile",
                "effect": "deny",
                "actions": ["reconcile_scene"],
                "targets": ["document"],
            }
        )
        protected_store = RevisionStore.create(protected)
        request = AdapterRequest.from_store(
            protected_store,
            protected_store.head,
            SCOPE,
            artifact_ids=(self.artifact.artifact_id,),
            options={"namespace": "structured"},
        )
        denied = BitmapReconcileAdapter().propose(request, self.artifacts)
        with self.assertRaisesRegex(ProposalPolicyError, "reconcile_scene"):
            ProposalAcceptor().accept(protected_store, denied, self.artifacts)

        constrained = copy.deepcopy(self.document)
        constrained["constraints"].append(
            {
                "id": "constraint:preserve-traced-path",
                "type": "PreserveParameter",
                "operation": "op:trace-structured-0001-path",
                "parameter": "d",
            }
        )
        constrained_store = RevisionStore.create(constrained)
        constrained_request = AdapterRequest.from_store(
            constrained_store,
            constrained_store.head,
            SCOPE,
            artifact_ids=(self.artifact.artifact_id,),
            options={"namespace": "structured"},
        )
        constrained_proposal = BitmapReconcileAdapter().propose(constrained_request, self.artifacts)
        with self.assertRaisesRegex(ProposalPolicyError, "preserves"):
            ProposalAcceptor().accept(constrained_store, constrained_proposal, self.artifacts)

    def test_invalid_scope_threshold_and_external_dependency_fail_closed(self) -> None:
        with self.assertRaisesRegex(BitmapTraceError, "unique Entity IDs"):
            duplicate = AdapterRequest.from_store(
                self.store,
                self.store.head,
                (SCOPE[0], SCOPE[0]),
                artifact_ids=(self.artifact.artifact_id,),
            )
            BitmapReconcileAdapter().propose(duplicate, self.artifacts)
        with self.assertRaisesRegex(BitmapTraceError, "0 to 1"):
            BitmapReconcileAdapter().propose(self.request(match_iou_threshold=1.1), self.artifacts)

        dependent = copy.deepcopy(self.document)
        dependent["entities"].append({"id": "entity:external", "name": "External consumer"})
        dependent["construction"]["operations"].append(
            {
                "id": "op:external-transform",
                "type": "Transform",
                "inputs": {"geometry": "op:trace-structured-0000-planar.geometry"},
                "parameters": {"matrix": [1, 0, 0, 1, 0, 0]},
            }
        )
        dependent["construction"]["output_bindings"].append(
            {
                "entity": "entity:external",
                "property": "geometry",
                "slot": "op:external-transform.geometry",
            }
        )
        dependent["presentation"]["render_stack"].append("entity:external")
        dependent["presentation"]["styles"].append(
            {
                "entity": "entity:external",
                "fill": "#000000",
                "stroke": "none",
                "stroke_width": 1.0,
                "opacity": 1.0,
            }
        )
        dependent_store = RevisionStore.create(dependent)
        request = AdapterRequest.from_store(
            dependent_store,
            dependent_store.head,
            SCOPE,
            artifact_ids=(self.artifact.artifact_id,),
            options={"namespace": "structured"},
        )
        proposal = BitmapReconcileAdapter().propose(request, self.artifacts)
        revision_count = len(dependent_store.revisions)
        with self.assertRaisesRegex(ValueError, "external Operation"):
            ProposalAcceptor().accept(dependent_store, proposal, self.artifacts)
        self.assertEqual(len(dependent_store.revisions), revision_count)

    def test_cli_previews_without_writing_then_accepts_explicitly(self) -> None:
        entities = [argument for entity in SCOPE for argument in ("--entity", entity)]
        preview = run_cli(
            "retrace-bitmap",
            str(BASE),
            str(SOURCE),
            *entities,
            "--namespace",
            "structured",
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        preview_result = json.loads(preview.stdout)
        self.assertFalse(preview_result["accepted"])
        self.assertEqual(preview_result["metrics"]["changed"], 1.0)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "accepted.svm.json"
            accepted = run_cli(
                "retrace-bitmap",
                str(BASE),
                str(SOURCE),
                *entities,
                "--namespace",
                "structured",
                "--accept",
                "--output",
                str(output),
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertTrue(json.loads(accepted.stdout)["accepted"])
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                json.loads(GOLDEN.read_text(encoding="utf-8")),
            )
            rendered = Path(directory) / "accepted.svg"
            render = run_cli(
                "render-svg",
                str(output),
                "--geometry-backend",
                "shapely",
                "--view-box",
                "0",
                "0",
                "120",
                "90",
                "--output",
                str(rendered),
            )
            self.assertEqual(render.returncode, 0, render.stderr)
            self.assertEqual(
                rendered.read_text(encoding="utf-8"),
                (ROOT / "examples" / "rendered" / "011-reconciled-trace.svg").read_text(
                    encoding="utf-8"
                ),
            )


if __name__ == "__main__":
    unittest.main()
