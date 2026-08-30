import builtins
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_cli import run_cli

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    GeneratorProvenance,
    PromoteComponentsChange,
    PromotedComponent,
    Proposal,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalConflictError,
    ProposalPolicyError,
    RevisionStore,
    Transaction,
    promoted_component_entity_id,
)
from svm.adapters import ComponentPromotionAdapter, ComponentPromotionError
from svm.document import validate_document
from svm.evaluator import DocumentError, canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "imported" / "012-opencv-analysis.svm.json"
ANALYSIS = ROOT / "examples" / "derived" / "012-opencv-analysis" / "component-analysis.json"
GOLDEN = ROOT / "examples" / "imported" / "013-component-promotion.svm.json"
MEDIA_TYPE = "application/vnd.svm.component-analysis+json"
CANDIDATES = ["candidate:component-0001", "candidate:component-0002"]


class ComponentPromotionGoldenITest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(BASE.read_text(encoding="utf-8"))
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        self.analysis = self._import_accepted_analysis(self.document, ANALYSIS.read_bytes())

    def _import_accepted_analysis(self, document: dict[str, object], content: bytes) -> object:
        artifact_id = f"artifact:{hashlib.sha256(content).hexdigest()}"
        reference = next(
            reference
            for reference in document["references"]  # type: ignore[index]
            if reference["id"] == artifact_id
        )
        metadata = reference["import_metadata"]
        return self.artifacts.import_bytes(
            content,
            media_type=reference["media_type"],
            kind=ArtifactKind(metadata["artifact_kind"]),
            provenance=metadata["provenance"],
        )

    def request(
        self,
        *,
        store: RevisionStore | None = None,
        artifact_id: str | None = None,
        **options: object,
    ) -> AdapterRequest:
        target = store or self.store
        return AdapterRequest.from_store(
            target,
            target.head,
            ("document",),
            artifact_ids=(artifact_id or self.analysis.artifact_id,),  # type: ignore[attr-defined]
            options={"candidate_ids": CANDIDATES, **options},
        )

    def test_golden_i_promotes_evidence_without_raster_or_geometry_work(self) -> None:
        original_import = builtins.__import__

        def reject_opencv(name: str, *args: object, **kwargs: object) -> object:
            if name == "cv2" or name.startswith("cv2."):
                raise AssertionError("Promotion must not import OpenCV")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=reject_opencv):
            proposal = ComponentPromotionAdapter().propose(
                self.request(candidate_ids=list(reversed(CANDIDATES))), self.artifacts
            )

        self.assertEqual(self.store.get_document(self.store.head), self.document)
        self.assertEqual(proposal.generator.engine_version, "svm-component-promotion@0.4")
        self.assertIsNone(proposal.confidence)
        self.assertEqual(proposal.report.metrics, {"promoted_components": 2.0})
        self.assertEqual(
            [relation.relation_type for relation in proposal.preview.structural_relations],
            ["derived-from", "derived-from"],
        )
        self.assertEqual(
            [diff.after_bounds for diff in proposal.preview.entity_diffs],  # type: ignore[union-attr]
            [(2, 2, 5, 5), (21, 4, 26, 9)],
        )

        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(accepted, json.loads(GOLDEN.read_text(encoding="utf-8")))
        self.assertEqual(len(accepted["entities"]), 2)
        self.assertEqual(
            [entity["semantic_tags"] for entity in accepted["entities"]],
            [["region", "promoted-component"]] * 2,
        )
        self.assertEqual(
            [entity["provenance"]["candidate_id"] for entity in accepted["entities"]],
            CANDIDATES,
        )
        self.assertEqual(accepted["construction"]["operations"], [])
        self.assertEqual(accepted["construction"]["output_bindings"], [])
        self.assertEqual(accepted["presentation"]["styles"], [])
        self.assertEqual(accepted["presentation"]["render_stack"], [])
        self.assertEqual(
            [relation["type"] for relation in accepted["structural_relations"]],
            ["derived-from", "derived-from"],
        )

    def test_selection_and_identity_are_deterministic_and_fail_closed(self) -> None:
        first = ComponentPromotionAdapter().propose(self.request(), self.artifacts)
        second = ComponentPromotionAdapter().propose(self.request(), self.artifacts)
        self.assertEqual(first.proposal_id, second.proposal_id)

        reversed_selection = ComponentPromotionAdapter().propose(
            self.request(candidate_ids=list(reversed(CANDIDATES))), self.artifacts
        )
        self.assertEqual(first.proposal_id, reversed_selection.proposal_id)

        for options, message in (
            ({"candidate_ids": []}, "non-empty"),
            ({"candidate_ids": [CANDIDATES[0], CANDIDATES[0]]}, "unique"),
            ({"candidate_ids": ["candidate:component-9999"]}, "Unknown"),
            ({"candidate_ids": CANDIDATES, "namespace": "Bad Namespace"}, "namespace"),
            ({"candidate_ids": CANDIDATES, "unknown": True}, "Unknown"),
        ):
            with self.subTest(options=options):
                request = AdapterRequest.from_store(
                    self.store,
                    self.store.head,
                    ("document",),
                    artifact_ids=(self.analysis.artifact_id,),  # type: ignore[attr-defined]
                    options=options,
                )
                with self.assertRaisesRegex(ComponentPromotionError, message):
                    ComponentPromotionAdapter().propose(request, self.artifacts)

    def test_core_change_constructs_neutral_entities_and_rejects_raw_injection(self) -> None:
        reference = next(
            reference
            for reference in self.document["references"]
            if reference["id"] == self.analysis.artifact_id  # type: ignore[attr-defined]
        )
        malicious = PromoteComponentsChange(
            components=(
                {
                    "id": "entity:fake-hair",
                    "name": "Hair",
                    "semantic_tags": ["hair", "recognized-object"],
                },  # type: ignore[arg-type]
            ),
            references=(reference,),
        )
        raw_proposal = Proposal(
            proposal_id="proposal:raw-injection",
            base_revision_id=self.store.head,
            generator=GeneratorProvenance("adapter:untrusted-third-party", "1.0", "manual", "1.0"),
            transaction=Transaction("transaction:raw-injection", (malicious,)),
            required_artifact_ids=(self.analysis.artifact_id,),  # type: ignore[attr-defined]
        )
        with self.assertRaisesRegex(ProposalArtifactError, "only PromotedComponent"):
            ProposalAcceptor().accept(self.store, raw_proposal, self.artifacts)
        with self.assertRaisesRegex(DocumentError, "only PromotedComponent"):
            self.store.commit(
                self.store.head,
                Transaction("transaction:raw-injection", (malicious,)),
            )
        self.assertEqual(self.store.get_document(self.store.head), self.document)

        component = PromotedComponent(
            artifact_id=self.analysis.artifact_id,  # type: ignore[attr-defined]
            candidate_id=CANDIDATES[0],
            component_digest="sha256:a5f53746c04e276c7f63092959c1ea9f3ef736db4479f8f331c05083abd74f8a",
            bounds=(2, 2, 5, 5),
        )
        revision = self.store.commit(
            self.store.head,
            Transaction(
                "transaction:core-owned-entity",
                (PromoteComponentsChange((component,), (reference,)),),
            ),
        )
        entity = self.store.get_document(revision.revision_id)["entities"][0]
        self.assertEqual(entity["id"], promoted_component_entity_id("region", component))
        self.assertEqual(entity["name"], "Region 0001")
        self.assertEqual(entity["semantic_tags"], ["region", "promoted-component"])
        self.assertEqual(entity["provenance"]["type"], "PromotedComponent")

    def test_acceptor_rejects_handcrafted_absent_candidate_and_wrong_digest(self) -> None:
        reference = next(
            reference
            for reference in self.document["references"]
            if reference["id"] == self.analysis.artifact_id  # type: ignore[attr-defined]
        )
        generator = GeneratorProvenance(
            adapter_id="adapter:untrusted-third-party",
            adapter_version="1.0",
            engine="manual",
            engine_version="1.0",
        )
        for component, message in (
            (
                PromotedComponent(
                    artifact_id=self.analysis.artifact_id,  # type: ignore[attr-defined]
                    candidate_id="candidate:component-999999",
                    component_digest="sha256:" + "0" * 64,
                    bounds=(0, 0, 1, 1),
                ),
                "absent from analysis",
            ),
            (
                PromotedComponent(
                    artifact_id=self.analysis.artifact_id,  # type: ignore[attr-defined]
                    candidate_id=CANDIDATES[0],
                    component_digest="sha256:" + "0" * 64,
                    bounds=(2, 2, 5, 5),
                ),
                "digest does not match",
            ),
            (
                PromotedComponent(
                    artifact_id=self.analysis.artifact_id,  # type: ignore[attr-defined]
                    candidate_id=CANDIDATES[0],
                    component_digest="sha256:a5f53746c04e276c7f63092959c1ea9f3ef736db4479f8f331c05083abd74f8a",
                    bounds=(0, 0, 1, 1),
                ),
                "bounds do not match",
            ),
        ):
            with self.subTest(candidate=component.candidate_id, message=message):
                change = PromoteComponentsChange((component,), (reference,))
                proposal = Proposal(
                    proposal_id="proposal:handcrafted-promotion",
                    base_revision_id=self.store.head,
                    generator=generator,
                    transaction=Transaction("transaction:handcrafted-promotion", (change,)),
                    required_artifact_ids=(self.analysis.artifact_id,),  # type: ignore[attr-defined]
                )
                with self.assertRaisesRegex(ProposalArtifactError, message):
                    ProposalAcceptor().accept(self.store, proposal, self.artifacts)
                self.assertEqual(self.store.get_document(self.store.head), self.document)

    def test_unaccepted_malformed_and_wrong_provenance_evidence_fail_closed(self) -> None:
        empty = copy.deepcopy(self.document)
        empty["references"] = []
        empty_store = RevisionStore.create(empty)
        with self.assertRaisesRegex(ComponentPromotionError, "already be accepted"):
            ComponentPromotionAdapter().propose(self.request(store=empty_store), self.artifacts)

        payload = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        payload["schema_version"] = "svm-component-analysis-0.1"
        malformed_bytes = canonical_bytes(payload)
        malformed_document, malformed_artifacts, malformed_id = self._replace_analysis(
            malformed_bytes
        )
        malformed_store = RevisionStore.create(malformed_document)
        with self.assertRaisesRegex(ComponentPromotionError, "conform"):
            ComponentPromotionAdapter().propose(
                self.request(store=malformed_store, artifact_id=malformed_id),
                malformed_artifacts,
            )

        wrong_document = copy.deepcopy(self.document)
        analysis_reference = next(
            reference
            for reference in wrong_document["references"]
            if reference["id"] == self.analysis.artifact_id  # type: ignore[attr-defined]
        )
        analysis_reference["import_metadata"]["provenance"]["parameters"]["analysis_identity"] = (
            "svm-opencv-components@9.9"
        )
        wrong_artifacts = ArtifactStore()
        wrong_artifacts.import_bytes(
            ANALYSIS.read_bytes(),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=analysis_reference["import_metadata"]["provenance"],
        )
        wrong_store = RevisionStore.create(wrong_document)
        with self.assertRaisesRegex(ComponentPromotionError, "analysis v0.2"):
            ComponentPromotionAdapter().propose(self.request(store=wrong_store), wrong_artifacts)

    def test_payload_descriptor_and_mask_provenance_must_form_one_evidence_chain(self) -> None:
        analysis_mismatch = copy.deepcopy(self.document)
        analysis_reference = next(
            reference
            for reference in analysis_mismatch["references"]
            if reference["media_type"] == MEDIA_TYPE
        )
        analysis_reference["import_metadata"]["provenance"]["parameters"]["threshold"] = 64
        mismatch_artifacts = ArtifactStore()
        mismatch_artifacts.import_bytes(
            ANALYSIS.read_bytes(),
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=analysis_reference["import_metadata"]["provenance"],
        )
        mismatch_store = RevisionStore.create(analysis_mismatch)
        with self.assertRaisesRegex(ComponentPromotionError, "does not match"):
            ComponentPromotionAdapter().propose(
                self.request(store=mismatch_store), mismatch_artifacts
            )

        unrelated_mask = copy.deepcopy(self.document)
        payload = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        payload["binary_mask_artifact_id"] = payload["source_artifact_id"]
        unrelated_bytes = canonical_bytes(payload)
        unrelated_document, unrelated_artifacts, unrelated_id = self._replace_analysis(
            unrelated_bytes, document=unrelated_mask
        )
        unrelated_store = RevisionStore.create(unrelated_document)
        with self.assertRaisesRegex(ComponentPromotionError, "DerivedArtifact"):
            ComponentPromotionAdapter().propose(
                self.request(store=unrelated_store, artifact_id=unrelated_id),
                unrelated_artifacts,
            )

        wrong_mask = copy.deepcopy(self.document)
        mask_reference = next(
            reference
            for reference in wrong_mask["references"]
            if reference["import_metadata"]["provenance"].get("derived_type") == "binary-mask"
        )
        mask_reference["import_metadata"]["provenance"]["parameters"]["threshold"] = 64
        wrong_mask_store = RevisionStore.create(wrong_mask)
        with self.assertRaisesRegex(ComponentPromotionError, "Binary-mask provenance"):
            ComponentPromotionAdapter().propose(
                self.request(store=wrong_mask_store), self.artifacts
            )

    def test_candidate_ids_above_9999_remain_promotable(self) -> None:
        payload = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        payload["image"] = {"width": 100, "height": 100}
        payload["components"] = [
            {
                "candidate_id": f"candidate:component-{index:04d}",
                "bounds": [x, y, x + 1, y + 1],
                "pixel_area": 1,
                "centroid": [float(x), float(y)],
                "component_digest": f"sha256:{hashlib.sha256(str(index).encode()).hexdigest()}",
            }
            for index in range(1, 10_001)
            for x, y in [((index - 1) % 100, (index - 1) // 100)]
        ]
        content = canonical_bytes(payload)
        document, artifacts, artifact_id = self._replace_analysis(content)
        store = RevisionStore.create(document)
        proposal = ComponentPromotionAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(artifact_id,),
                options={"candidate_ids": ["candidate:component-10000"]},
            ),
            artifacts,
        )
        component = proposal.transaction.changes[0].components[0]  # type: ignore[attr-defined]
        self.assertEqual(component.candidate_id, "candidate:component-10000")

    def _replace_analysis(
        self, content: bytes, *, document: dict[str, object] | None = None
    ) -> tuple[dict[str, object], ArtifactStore, str]:
        document = copy.deepcopy(document or self.document)
        old_reference = next(
            reference
            for reference in document["references"]
            if reference["media_type"] == MEDIA_TYPE  # type: ignore[index]
        )
        digest = hashlib.sha256(content).hexdigest()
        artifact_id = f"artifact:{digest}"
        old_reference["id"] = artifact_id
        old_reference["uri"] = artifact_id
        old_reference["content_hash"] = f"sha256:{digest}"
        artifacts = ArtifactStore()
        artifacts.import_bytes(
            content,
            media_type=MEDIA_TYPE,
            kind=ArtifactKind.DERIVED,
            provenance=old_reference["import_metadata"]["provenance"],
        )
        return document, artifacts, artifact_id

    def test_stale_repeated_permission_and_missing_artifact_fail_closed(self) -> None:
        proposal = ComponentPromotionAdapter().propose(self.request(), self.artifacts)
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.store, proposal, ArtifactStore())
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)

        promoted_store = RevisionStore.create(json.loads(GOLDEN.read_text(encoding="utf-8")))
        with self.assertRaisesRegex(ComponentPromotionError, "already promoted"):
            ComponentPromotionAdapter().propose(self.request(store=promoted_store), self.artifacts)

        protected = copy.deepcopy(self.document)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-promotion",
                "actor": "adapter:component-promotion",
                "effect": "deny",
                "actions": ["promote_components"],
                "targets": ["document"],
            }
        )
        protected_store = RevisionStore.create(protected)
        denied = ComponentPromotionAdapter().propose(
            self.request(store=protected_store), self.artifacts
        )
        with self.assertRaisesRegex(ProposalPolicyError, "promote_components"):
            ProposalAcceptor().accept(protected_store, denied, self.artifacts)

        invalid = json.loads(GOLDEN.read_text(encoding="utf-8"))
        invalid["entities"][0]["provenance"]["artifact_id"] = "artifact:" + "0" * 64
        with self.assertRaisesRegex(DocumentError, "missing Artifact"):
            validate_document(invalid)

    def test_cli_previews_then_accepts_golden_i(self) -> None:
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
        self.assertFalse(json.loads(preview.stdout)["accepted"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "promoted.svm.json"
            accepted = run_cli(
                "promote-components",
                str(BASE),
                str(ANALYSIS),
                "--candidate",
                CANDIDATES[0],
                "--candidate",
                CANDIDATES[1],
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


if __name__ == "__main__":
    unittest.main()
