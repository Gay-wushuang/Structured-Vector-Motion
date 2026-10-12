"""B0-3 production packaging using the real accepted Golden046 authority chain."""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_representation_target_consumer as consumer_fixture
from test_representation_certification import (
    ASSOCIATION_ID,
    CERTIFICATION_REVISION,
    GROUP_ID,
    WHOLE_IDENTITY,
    FixtureMutation,
    render,
)

from svm import AdapterRequest, ProposalAcceptor, Transaction
from svm.adapters import representation_certification as certification
from svm.adapters.representation_target_selection import (
    RepresentationTargetSelectionAdapter,
    propose_from_store,
)
from svm.adapters.temporal_motion_target_binding import TemporalMotionTargetBindingAdapter
from svm.admission_history import dump_trusted_history, history_digest, load_trusted_history
from svm.artifacts import ArtifactKind
from svm.multipart_witness import collect_witnesses
from svm.proposals import ProposalConflictError, ProposalPolicyError
from svm.representation_target_consumer import POLICY_IDENTITY, Reason
from svm.representation_target_selection import MEDIA, RepresentationTargetSelectionError
from svm.revisions import (
    AddKeyframeChange,
    AppendReferencesChange,
    ApplyRepresentationTargetSelectionChange,
    BindTemporalMotionTargetChange,
    CreateGroupTransformTrackChange,
    RevisionStore,
    SetGroupTransformChange,
)

ACTOR = "adapter:representation-target-selection"
BINDING_ID = (
    "motion-target-binding:234a54dd65aedc815735519bce19d646f9af306c110f937fa8d1fe11cec8d776"
)
ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples/046-representation-certification/target-selection-golden.json"


class RepresentationTargetSelectionAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Module import avoids collecting another copy of the existing TestCase.
        # Full discovery already built this real chain; focused discovery builds
        # it once, then every test receives its own isolated accepted state.
        existing = consumer_fixture.RepresentationTargetConsumerTest
        if not hasattr(existing, "fixture"):
            existing.setUpClass()
        cls.fixture = copy.deepcopy(existing.fixture)
        cls.uncertified_store = copy.deepcopy(existing.uncertified_store)
        cls.certificate = copy.deepcopy(existing.certificate)
        cls.original_goldens = consumer_fixture.golden_files()

    def setUp(self):
        fixture = copy.deepcopy(self.fixture)
        self.store = fixture["store"]
        self.artifacts = fixture["artifacts"]
        self.adapter = RepresentationTargetSelectionAdapter()

    def request(self):
        return AdapterRequest.from_store(self.store, self.store.head, ("document",))

    def pure_propose(self, request=None, witnesses=None):
        return self.adapter.propose(
            self.request() if request is None else request,
            self.artifacts,
            witnesses=(
                collect_witnesses(self.store, self.store.head) if witnesses is None else witnesses
            ),
        )

    def no_output(self, action, reason):
        before = copy.deepcopy(self.store)
        artifacts = copy.deepcopy((self.artifacts._blobs, self.artifacts._descriptors))
        with (
            patch.object(
                self.artifacts,
                "import_bytes",
                side_effect=AssertionError("Non-selected production must not write Artifacts"),
            ) as writer,
            patch.object(
                TemporalMotionTargetBindingAdapter,
                "propose",
                side_effect=AssertionError("Non-selected production must not create a binding"),
            ) as binder,
        ):
            with self.assertRaises(RepresentationTargetSelectionError) as failure:
                action()
            self.assertEqual(failure.exception.args, (reason.value,))
            writer.assert_not_called()
            binder.assert_not_called()
        self.assertEqual(self.store, before)
        self.assertEqual((self.artifacts._blobs, self.artifacts._descriptors), artifacts)
        if self.store.head is not None:
            self.assertEqual(
                self.store.get_document(self.store.head), before.get_document(before.head)
            )

    def test_real_production_rebuild_preview_acceptance_and_bound_rerun(self):
        before = copy.deepcopy(self.store)
        before_artifacts = copy.deepcopy(vars(self.artifacts))
        document = self.store.get_document(self.store.head)
        request = self.request()
        witnesses = collect_witnesses(self.store, self.store.head)
        inputs = copy.deepcopy((request, witnesses))
        with patch.object(
            self.artifacts, "import_bytes", wraps=self.artifacts.import_bytes
        ) as writer:
            proposal = propose_from_store(self.store, self.artifacts)
            self.assertEqual(writer.call_count, 1)
        self.assertEqual(self.store, before)
        self.assertEqual((request, witnesses), inputs)
        self.assertEqual(proposal.base_revision_id, CERTIFICATION_REVISION)
        self.assertRegex(proposal.proposal_id, r"^proposal:.*:[0-9a-f]{64}$")
        self.assertRegex(proposal.transaction.transaction_id, r"^transaction:.*:[0-9a-f]{64}$")
        self.assertEqual(proposal.generator.adapter_id, ACTOR)
        self.assertEqual(proposal.generator.adapter_version, "0.1")
        self.assertEqual(proposal.generator.engine, "svm")
        self.assertEqual(proposal.generator.engine_version, POLICY_IDENTITY)
        self.assertEqual(proposal.generator.parameters, {})
        self.assertEqual(len(proposal.transaction.changes), 1)
        change = proposal.transaction.changes[0]
        self.assertIs(type(change), ApplyRepresentationTargetSelectionChange)
        self.assertEqual(change.source_revision_id, CERTIFICATION_REVISION)
        self.assertEqual(change.base_document_snapshot, document)
        self.assertEqual(change.witnesses, witnesses)
        self.assertEqual(change.selected_pairs, ((WHOLE_IDENTITY, GROUP_ID),))
        self.assertEqual(
            change.source_references,
            tuple(sorted(document["references"], key=lambda reference: reference["id"])),
        )
        self.assertEqual(
            proposal.required_artifact_ids,
            tuple(reference["id"] for reference in change.references),
        )
        self.assertEqual(
            len(set(proposal.required_artifact_ids)), len(proposal.required_artifact_ids)
        )
        frozen = TemporalMotionTargetBindingAdapter().propose(
            replace(
                request, options={"temporal_identity_id": WHOLE_IDENTITY, "group_id": GROUP_ID}
            ),
            self.artifacts,
        )
        self.assertEqual(change.delegated_binds, frozen.transaction.changes)
        self.assertIs(type(change.delegated_binds[0]), BindTemporalMotionTargetChange)
        self.assertEqual(proposal.preview, frozen.preview)
        self.assertEqual(len(proposal.preview_artifacts), 1)
        evidence = self.artifacts.resolve_reference(change.selection_evidence_reference)
        preview = proposal.preview_artifacts[0]
        self.assertEqual(preview.artifact_id, evidence.artifact_id)
        self.assertEqual(preview.content_hash, evidence.content_hash)
        self.assertEqual(preview.media_type, MEDIA)
        self.assertEqual(evidence.kind, ArtifactKind.DERIVED)
        self.assertEqual(evidence.provenance, {"policy_identity": POLICY_IDENTITY})
        self.assertIsNone(evidence.descriptor.locator)
        payload = json.loads(evidence.content)
        self.assertEqual(payload["result"]["status"], "SELECTED")
        self.assertEqual(payload["counts"]["total"], len(document["temporal_identities"]))
        self.assertEqual(payload["counts"]["selected"], 1)
        self.assertEqual(payload["counts"]["selected_pairs"], 1)
        measured = {
            "schema_version": "svm-representation-target-selection-golden-0.1",
            "base_revision_id": proposal.base_revision_id,
            "proposal_id": proposal.proposal_id,
            "transaction_id": proposal.transaction.transaction_id,
            "selection_evidence_artifact_id": evidence.artifact_id,
            "selection_evidence_content_hash": evidence.content_hash,
            "selection_evidence_bytes": len(evidence.content),
            "selection_evidence_reference": change.selection_evidence_reference,
            "selected_pairs": [list(pair) for pair in change.selected_pairs],
            "binding_ids": [bind.binding["id"] for bind in change.delegated_binds],
            "required_artifact_count": len(proposal.required_artifact_ids),
            "source_reference_count": len(change.source_references),
            "witness_count": len(change.witnesses),
            "identity_count": len(document["temporal_identities"]),
            "group_count": len(document["groups"]),
            "entity_count": len(document["entities"]),
            "track_count": len(document.get("animation", {}).get("content", [])),
            "keyframe_count": sum(
                len(track.get("keyframes", []))
                for track in document.get("animation", {}).get("content", [])
            ),
        }
        self.assertEqual(
            set(self.artifacts._blobs) - set(before_artifacts["_blobs"]), {evidence.artifact_id}
        )
        for key, blob in before_artifacts["_blobs"].items():
            self.assertEqual(self.artifacts._blobs[key], blob)
            self.assertEqual(
                self.artifacts._descriptors[key], before_artifacts["_descriptors"][key]
            )
        staged_artifacts = copy.deepcopy(vars(self.artifacts))
        self.adapter.adapter_id = "adapter:caller-spoofed"
        rebuilt = self.pure_propose(request, witnesses)
        self.assertEqual(rebuilt, proposal)
        self.assertEqual(vars(self.artifacts), staged_artifacts)
        self.assertEqual(self.store, before)
        self.assertEqual((request, witnesses), inputs)

        ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(self.store, before)
        self.assertEqual(vars(self.artifacts), staged_artifacts)
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        measured["result_revision_id"] = revision.revision_id
        self.assertEqual(measured, json.loads(GOLDEN.read_bytes()))
        after = self.store.get_document(self.store.head)
        self.assertEqual(revision.parent_ids, (CERTIFICATION_REVISION,))
        self.assertEqual(len(self.store.revisions), len(before.revisions) + 1)
        self.assertEqual(getattr(revision, "admissions", ()), ())
        self.assertEqual(after["motion_target_bindings"], [change.delegated_binds[0].binding])
        self.assertEqual(after["motion_target_bindings"][0]["id"], BINDING_ID)
        self.assertEqual(
            after["references"], document["references"] + [change.selection_evidence_reference]
        )
        artistic_state = copy.deepcopy(after)
        artistic_state.pop("motion_target_bindings")
        artistic_state["references"].pop()
        self.assertEqual(artistic_state, document)
        self.assertEqual(render(after), render(document))
        for rid, old_revision in before.revisions.items():
            self.assertEqual(self.store.revisions[rid], old_revision)
            self.assertEqual(self.store.get_document(rid), before.get_document(rid))
        history = dump_trusted_history(self.store)
        loaded = load_trusted_history(history, trusted_history_hash=history_digest(history))
        self.assertEqual(dump_trusted_history(loaded), history)

        replay_store = copy.deepcopy(before)
        replay_artifacts = copy.deepcopy(self.artifacts)
        replay_proposal = propose_from_store(replay_store, replay_artifacts)
        self.assertEqual(replay_proposal, proposal)
        replay_revision = ProposalAcceptor().accept(replay_store, replay_proposal, replay_artifacts)
        self.assertEqual(replay_revision.revision_id, revision.revision_id)
        self.assertEqual(
            replay_store.get_document(replay_store.head),
            self.store.get_document(self.store.head),
        )
        self.no_output(lambda: propose_from_store(self.store, self.artifacts), Reason.ZERO_SELECTED)
        # Pure orchestration can rebuild the immutable original base; submitting
        # it at the bound HEAD is still a stale ordinary Proposal.
        self.assertEqual(self.pure_propose(request, witnesses), proposal)
        bound_store = copy.deepcopy(self.store)
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        self.assertEqual(self.store, bound_store)
        self.assertEqual(vars(self.artifacts), staged_artifacts)
        self.assertEqual(consumer_fixture.golden_files(), self.original_goldens)

    def test_zero_admitted_claim_and_legacy_certification_data_write_nothing(self):
        uncertified = copy.deepcopy(self.uncertified_store)
        malformed = self.artifacts.import_bytes(
            b"ordinary data, not JSON; verified=true",
            media_type=certification.MEDIA,
            provenance={"verified": True, "temporal_identity_id": WHOLE_IDENTITY},
        ).document_reference()
        for reference in (None, self.certificate, malformed):
            with self.subTest(reference=None if reference is None else reference["id"]):
                self.store = copy.deepcopy(uncertified)
                if reference is not None:
                    self.store.commit(
                        self.store.head,
                        Transaction(
                            "transaction:legacy-certification-data",
                            (AppendReferencesChange((reference,)),),
                        ),
                    )
                with patch.object(
                    self.artifacts,
                    "resolve_reference",
                    side_effect=AssertionError("S2 must not resolve data-only Artifact bytes"),
                ) as resolver:
                    self.no_output(
                        lambda: propose_from_store(self.store, self.artifacts),
                        Reason.NO_ADMITTED_ASSOCIATION,
                    )
                    resolver.assert_not_called()

    def test_witness_snapshot_missing_bytes_and_current_edit_reject_before_writer(self):
        request = self.request()
        witnesses = collect_witnesses(self.store, self.store.head)
        snapshot = copy.deepcopy(request.document)
        snapshot["references"] = []
        self.no_output(
            lambda: self.pure_propose(replace(request, document=snapshot), witnesses[:-1]),
            Reason.HISTORY_BROKEN,
        )
        self.no_output(
            lambda: self.pure_propose(replace(request, document=snapshot), witnesses),
            Reason.UNREPLAYABLE_ASSOCIATION,
        )
        original_artifacts = copy.deepcopy(self.artifacts)
        del self.artifacts._blobs[ASSOCIATION_ID]
        self.no_output(
            lambda: propose_from_store(self.store, self.artifacts), Reason.UNREPLAYABLE_ASSOCIATION
        )
        self.artifacts = original_artifacts
        transform = copy.deepcopy(request.document["groups"][0]["transform"])
        transform["translate"][0] += 1
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:modified-representation",
                (SetGroupTransformChange(GROUP_ID, transform),),
            ),
        )
        self.no_output(
            lambda: propose_from_store(self.store, self.artifacts), Reason.UNREPLAYABLE_ASSOCIATION
        )

    def test_native_request_contract_forbids_callers_selecting_authority(self):
        request = self.request()
        witnesses = collect_witnesses(self.store, self.store.head)
        callbacks = []

        class CallerOptions(dict):
            def __bool__(self):
                callbacks.append(True)
                return False

        variants = (
            replace(request, scope=()),
            replace(request, scope=("document", GROUP_ID)),
            replace(request, scope=["document"]),
            replace(request, artifact_ids=(ASSOCIATION_ID,)),
            replace(request, artifact_ids=[]),
            replace(
                request, options={"temporal_identity_id": WHOLE_IDENTITY, "group_id": GROUP_ID}
            ),
            replace(request, options={"threshold": 1}),
            replace(request, options=CallerOptions()),
        )
        before = copy.deepcopy((self.store, vars(self.artifacts), request, witnesses))
        with patch.object(
            self.artifacts,
            "import_bytes",
            side_effect=AssertionError("Invalid request wrote output"),
        ) as writer:
            for variant in variants:
                with self.subTest(
                    scope=variant.scope, artifact_ids=variant.artifact_ids, options=variant.options
                ):
                    with self.assertRaises(RepresentationTargetSelectionError):
                        self.pure_propose(variant, witnesses)
            writer.assert_not_called()
        self.assertEqual((self.store, vars(self.artifacts), request, witnesses), before)
        self.assertEqual(callbacks, [])

    def test_native_witness_boundary_and_empty_host_head_write_nothing(self):
        request = self.request()
        witnesses = list(copy.deepcopy(collect_witnesses(self.store, self.store.head)))
        object.__setattr__(witnesses[0], "caller_claim", True)
        self.no_output(lambda: self.pure_propose(request, tuple(witnesses)), Reason.HISTORY_BROKEN)
        self.store = RevisionStore()
        self.no_output(
            lambda: propose_from_store(self.store, self.artifacts), Reason.HISTORY_BROKEN
        )

    def test_legal_existing_track_yields_zero_selected_without_output(self):
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:existing-group-track",
                (
                    CreateGroupTransformTrackChange(
                        "track:production-selection", GROUP_ID, "translate.x", 12
                    ),
                    AddKeyframeChange(
                        "track:production-selection", "keyframe:production-selection", 0, 0
                    ),
                ),
            ),
        )
        self.no_output(lambda: propose_from_store(self.store, self.artifacts), Reason.ZERO_SELECTED)

    def test_actual_generator_policy_denial_publishes_neither_binding_nor_evidence(self):
        permission = {
            "id": "permission:production-selection",
            "actor": ACTOR,
            "effect": "deny",
            "actions": ["attach_analysis"],
            "targets": ["document"],
        }
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:production-selection-policy",
                (
                    FixtureMutation(
                        lambda document: document["edit_permissions"].append(permission)
                    ),
                ),
            ),
        )
        proposal = propose_from_store(self.store, self.artifacts)
        before = copy.deepcopy((self.store, vars(self.artifacts)))
        with self.assertRaisesRegex(ProposalPolicyError, "denies.*attach_analysis"):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        self.assertEqual((self.store, vars(self.artifacts)), before)
        self.assertNotIn("motion_target_bindings", self.store.get_document(self.store.head))
        evidence = proposal.transaction.changes[0].selection_evidence_reference
        self.assertNotIn(evidence, self.store.get_document(self.store.head)["references"])


if __name__ == "__main__":
    unittest.main()
