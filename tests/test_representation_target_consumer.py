"""Read-only Spec81 classification using the real frozen Golden046 authority chain."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from test_representation_certification import (
    ASSOCIATION_ID,
    CERTIFICATION_REVISION,
    GROUP_ID,
    WHOLE_IDENTITY,
    FixtureMutation,
    certification_fixture,
    render,
)

from svm import AdapterRequest, ProposalAcceptor, RevisionStore, Transaction
from svm.adapters import representation_certification as certification
from svm.adapters.temporal_motion_target_binding import TemporalMotionTargetBindingAdapter
from svm.admission_history import CERT_AUTHORITY, CERT_CHANGE, CERT_CONTRACT, transition_hash
from svm.artifacts import ArtifactKind, ArtifactSnapshot, ArtifactStore
from svm.evaluator import canonical_bytes
from svm.multipart_witness import authenticate_witnesses, collect_witnesses
from svm.representation_target_consumer import (
    Reason,
    Stage,
    Status,
    derive_certified_targets,
)
from svm.revisions import (
    AddKeyframeChange,
    AdmissionEvent,
    AppendReferencesChange,
    CreateGroupTransformTrackChange,
    CreateStyleTrackChange,
    SetGroupTransformChange,
    SetOperationParameterChange,
)

ROOT = Path(__file__).resolve().parents[1]


class ResolverOnly:
    """Expose precisely read capabilities, without an Artifact writer."""

    def __init__(self, store, *, forbid=False, descriptor_fault=None):
        self.store = store
        self.forbid = forbid
        self.descriptor_fault = descriptor_fault
        self.snapshot_fault = None
        self.calls = []

    def resolve_reference(self, reference):
        if self.forbid:
            raise AssertionError("Zero-claim classification must not resolve Artifact bytes")
        self.calls.append(reference["id"])
        result = self.store.resolve_reference(reference)
        if self.snapshot_fault == "bytes" and reference["id"] == ASSOCIATION_ID:
            return ArtifactSnapshot(
                replace(result.blob, content=b"malicious resolver bytes"), result.descriptor
            )
        if self.snapshot_fault == "descriptor_id" and reference["id"] == ASSOCIATION_ID:
            return ArtifactSnapshot(
                result.blob, replace(result.descriptor, artifact_id="artifact:" + "0" * 64)
            )
        if self.descriptor_fault == reference["id"]:
            return ArtifactSnapshot(
                result.blob, replace(result.descriptor, locator="caller:locator")
            )
        return result

    def resolve(self, ids):
        if self.forbid:
            raise AssertionError("Zero-claim classification must not resolve Artifact bytes")
        self.calls.extend(ids)
        return self.store.resolve(ids)

    def resolve_as(self, ids, *, kind, media_types):
        if self.forbid:
            raise AssertionError("Zero-claim classification must not resolve Artifact bytes")
        self.calls.extend(ids)
        return self.store.resolve_as(ids, kind=kind, media_types=media_types)


def golden_files():
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for number in ("043", "044", "045", "046")
        for directory in (ROOT / "examples").glob(number + "-*")
        for path in directory.rglob("*")
        if path.is_file()
    }


class RepresentationTargetConsumerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_golden_files = golden_files()
        fixture = certification_fixture()
        cls.uncertified_store = copy.deepcopy(fixture["store"])
        store, artifacts = fixture["store"], fixture["artifacts"]
        proposal = certification.RepresentationCertificationAdapter().propose(
            AdapterRequest.from_store(store, store.head, ("document",)),
            artifacts,
            witnesses=collect_witnesses(store, store.head),
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        cls.fixture = fixture
        cls.certificate = proposal.transaction.changes[0].association_reference
        cls.certification_revision = store.head

    def setUp(self):
        fixture = copy.deepcopy(self.fixture)
        self.store = fixture["store"]
        self.artifacts = fixture["artifacts"]
        self.uncertified = copy.deepcopy(self.uncertified_store)
        self.birth_change = fixture["construction"].transaction.changes[0]
        self.membership_reference = (
            fixture["observations"].transaction.changes[0].evidence_reference
        )

    def derive(
        self, *, base=None, document=None, witnesses=None, source_references=None, resolver=None
    ):
        base = self.store.head if base is None else base
        document = self.store.get_document(base) if document is None else document
        witnesses = collect_witnesses(self.store, base) if witnesses is None else witnesses
        resolver = ResolverOnly(self.artifacts) if resolver is None else resolver
        before = copy.deepcopy(
            (self.store, vars(self.artifacts), document, witnesses, source_references)
        )
        result = derive_certified_targets(
            base,
            document,
            witnesses,
            resolver,
            source_references=source_references,
        )
        self.assertEqual(
            (self.store, vars(self.artifacts), document, witnesses, source_references), before
        )
        return result

    def assert_failure(self, result, reason, stage):
        self.assertEqual(result.status, Status.REJECT)
        self.assertEqual(result.rejection_reason, reason)
        self.assertEqual(result.stage, stage)
        self.assertEqual(result.selected_pairs, ())
        self.assertEqual(result.counts["selected"], 0)
        self.assertEqual(result.counts["selected_pairs"], 0)
        self.assertTrue(all(e.status == Status.REJECT for e in result.evaluations))

    def mutate(self, callback):
        self.store.commit(
            self.store.head,
            Transaction("transaction:consumer-damaged-state", (FixtureMutation(callback),)),
        )

    def bind(self, identity=WHOLE_IDENTITY):
        proposal = TemporalMotionTargetBindingAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                options={"temporal_identity_id": identity, "group_id": GROUP_ID},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        return self.store.get_document(self.store.head)["motion_target_bindings"][0]

    def replace_head_events(self, events):
        """Deliberately damaged trusted host fixture, never consumer admission authority."""
        old = self.store.revisions[self.store.head]
        document = self.store.get_document(self.store.head)
        new = self.store._make_revision(
            document, old.parent_ids, old.transaction_id, old.message, events
        )
        del self.store.revisions[old.revision_id]
        del self.store._documents[old.revision_id]
        self.store.revisions[new.revision_id] = new
        self.store._documents[new.revision_id] = document
        self.store.head = new.revision_id

    def install_counterfeit_claim(self, payload):
        """Synthetic host-history corruption used only to prove independent replay rejects it."""
        base = self.store.head
        payload = copy.deepcopy(payload)
        payload["base"] = {
            "revision_id": base,
            "document_hash": self.store.revisions[base].document_hash,
        }
        reference = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=certification.MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"profile_identity": certification.PROFILE},
        ).document_reference()
        transaction = Transaction(
            "transaction:consumer-counterfeit-history", (AppendReferencesChange((reference,)),)
        )
        document = transaction.apply(self.store.get_document(base))
        event = AdmissionEvent(
            CERT_CONTRACT,
            CERT_CHANGE,
            CERT_AUTHORITY,
            base,
            reference,
            transition_hash(document, (base,), transaction.transaction_id, transaction.message),
        )
        self.store._commit_verified(base, transaction, document, (event,))
        authenticate_witnesses(self.store.head, collect_witnesses(self.store, self.store.head))
        return reference

    def test_genuine_certification_selects_only_whole_identity_and_enumerates_everything(self):
        resolver = ResolverOnly(self.artifacts)
        result = self.derive(resolver=resolver)
        document = self.store.get_document(self.store.head)
        self.assertEqual(self.store.head, CERTIFICATION_REVISION)
        self.assertEqual(self.certificate["id"], ASSOCIATION_ID)
        self.assertEqual(result.status, Status.SELECTED)
        self.assertEqual(result.stage, Stage.S7)
        self.assertEqual(result.selected_pairs, ((WHOLE_IDENTITY, GROUP_ID),))
        self.assertIsNone(result.rejection_reason)
        self.assertIsNone(result.abstention_reason)
        self.assertEqual(result.reason_namespace, "svm-representation-target-consumer-reasons@0.1")
        self.assertEqual(
            result.identity_ids, tuple(sorted(t["id"] for t in document["temporal_identities"]))
        )
        self.assertEqual(result.group_ids, (GROUP_ID,))
        self.assertEqual(result.existing_bindings, ())
        self.assertEqual(
            result.source_references, tuple(sorted(document["references"], key=lambda r: r["id"]))
        )
        self.assertEqual(
            [e.temporal_identity_id for e in result.evaluations], list(result.identity_ids)
        )
        self.assertEqual(
            result.counts,
            {"total": 3, "selected": 1, "abstain": 2, "reject": 0, "selected_pairs": 1},
        )
        for evaluation in result.evaluations:
            if evaluation.temporal_identity_id == WHOLE_IDENTITY:
                self.assertEqual(evaluation.status, Status.SELECTED)
                self.assertEqual(evaluation.group_id, GROUP_ID)
                self.assertEqual(evaluation.association_reference, self.certificate)
            else:
                self.assertEqual(evaluation.status, Status.ABSTAIN)
                self.assertEqual(evaluation.reason, Reason.NO_CERTIFICATION_FOR_IDENTITY)
                self.assertIsNone(evaluation.group_id)
        (audit,) = result.claim_audits
        self.assertTrue(audit.admitted)
        self.assertEqual(audit.reference, self.certificate)
        self.assertEqual(audit.acceptance_revision_id, self.certification_revision)
        self.assertEqual((audit.temporal_identity_id, audit.group_id), (WHOLE_IDENTITY, GROUP_ID))
        record = json.loads(self.artifacts.resolve_reference(self.certificate).content)
        self.assertEqual(audit.subject_id, record["association"]["subject_id"])
        self.assertEqual(audit.claim_key, certification.claim_key(record))
        self.assertNotIn("association", self.certificate)
        self.assertIn(ASSOCIATION_ID, resolver.calls)

    def test_arbitrary_zero_identity_root_needs_no_artifact_bytes_or_spec80_world(self):
        document = json.loads((ROOT / "examples/001-head-basic.svm.json").read_bytes())
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()
        resolver = ResolverOnly(self.artifacts, forbid=True)
        with patch.object(
            certification, "admitted_associations", side_effect=AssertionError("No replay")
        ) as replay:
            result = self.derive(resolver=resolver)
        replay.assert_not_called()
        self.assertEqual(resolver.calls, [])
        self.assertEqual(result.status, Status.ABSTAIN)
        self.assertEqual(result.abstention_reason, Reason.NO_ADMITTED_ASSOCIATION)
        self.assertEqual(result.stage, Stage.S2)
        self.assertEqual(result.evaluations, ())
        self.assertEqual(
            result.counts,
            {"total": 0, "selected": 0, "abstain": 0, "reject": 0, "selected_pairs": 0},
        )

    def test_uncertified_whole_and_part_identities_all_abstain_without_resolution(self):
        self.store = copy.deepcopy(self.uncertified)
        resolver = ResolverOnly(self.artifacts, forbid=True)
        with patch.object(
            certification, "admitted_associations", side_effect=AssertionError("No replay")
        ) as replay:
            result = self.derive(resolver=resolver)
        replay.assert_not_called()
        self.assertEqual(result.abstention_reason, Reason.NO_ADMITTED_ASSOCIATION)
        self.assertEqual(result.counts["total"], 3)
        self.assertEqual(result.counts["abstain"], 3)
        self.assertTrue(all(e.reason == Reason.NO_ADMITTED_ASSOCIATION for e in result.evaluations))
        self.assertEqual(result.claim_audits, ())
        self.assertEqual(resolver.calls, [])

    def test_byte_valid_and_malformed_reserved_references_without_events_are_data(self):
        original = copy.deepcopy(self.uncertified)
        malformed = self.artifacts.import_bytes(
            b"not JSON; verified=true; caller-selected Group",
            media_type=certification.MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={
                "verified": True,
                "temporal_identity_id": WHOLE_IDENTITY,
                "group_id": GROUP_ID,
            },
        ).document_reference()
        for reference in (self.certificate, malformed):
            with self.subTest(artifact_id=reference["id"]):
                self.store = copy.deepcopy(original)
                self.store.commit(
                    self.store.head,
                    Transaction("transaction:data-only", (AppendReferencesChange((reference,)),)),
                )
                resolver = ResolverOnly(self.artifacts, forbid=True)
                with patch.object(
                    certification, "admitted_associations", side_effect=AssertionError("No replay")
                ) as replay:
                    result = self.derive(resolver=resolver)
                replay.assert_not_called()
                self.assertEqual(result.abstention_reason, Reason.NO_ADMITTED_ASSOCIATION)
                self.assertEqual(result.rejection_reason, None)
                self.assertEqual(result.selected_pairs, ())
                (audit,) = result.claim_audits
                self.assertFalse(audit.admitted)
                self.assertEqual(audit.reference, reference)
                self.assertIsNone(audit.temporal_identity_id)
                self.assertIsNone(audit.group_id)
                self.assertEqual(resolver.calls, [])

    def test_data_reference_cannot_conflict_with_or_hide_genuine_claim(self):
        data = self.artifacts.import_bytes(
            b"invalid certification record with competing caller ownership",
            media_type=certification.MEDIA,
            provenance={"temporal_identity_id": WHOLE_IDENTITY, "group_id": GROUP_ID},
        ).document_reference()
        self.store.commit(
            self.store.head,
            Transaction("transaction:ordinary-data", (AppendReferencesChange((data,)),)),
        )
        result = self.derive()
        self.assertEqual(result.selected_pairs, ((WHOLE_IDENTITY, GROUP_ID),))
        self.assertEqual(len(result.claim_audits), 2)
        audits = {a.reference["id"]: a for a in result.claim_audits}
        self.assertTrue(audits[ASSOCIATION_ID].admitted)
        self.assertFalse(audits[data["id"]].admitted)
        self.assertIsNone(audits[data["id"]].temporal_identity_id)

    def test_complete_reference_structure_is_checked_before_no_claim_abstention(self):
        self.store = copy.deepcopy(self.uncertified)
        references = tuple(
            sorted(self.store.get_document(self.store.head)["references"], key=lambda r: r["id"])
        )
        altered = copy.deepcopy(references)
        altered[0]["uri"] = "caller:conflicting-locator"
        for supplied in (references[1:], references[::-1], (*references, references[0]), altered):
            with self.subTest(supplied_ids=[r["id"] for r in supplied]):
                result = self.derive(
                    source_references=supplied, resolver=ResolverOnly(self.artifacts, forbid=True)
                )
                self.assert_failure(result, Reason.UNREPLAYABLE_ASSOCIATION, Stage.S1)

    def test_supplied_snapshot_omission_rejects_with_complete_authenticated_inventory(self):
        document = self.store.get_document(self.store.head)
        document["temporal_identities"].pop()
        document["groups"].clear()
        document["references"].pop()
        result = self.derive(document=document, resolver=ResolverOnly(self.artifacts, forbid=True))
        self.assert_failure(result, Reason.UNREPLAYABLE_ASSOCIATION, Stage.S1)
        self.assertEqual(len(result.identity_ids), 3)
        self.assertEqual(result.group_ids, (GROUP_ID,))
        self.assertEqual(
            len(result.source_references),
            len(self.store.get_document(self.store.head)["references"]),
        )
        self.assertEqual(len(result.claim_audits), 1)

    def test_incomplete_reordered_substituted_and_forged_witnesses_reject(self):
        witnesses = collect_witnesses(self.store, self.store.head)
        base_witness = next(w for w in witnesses if w.revision.revision_id == self.store.head)
        extra_store = RevisionStore.create(
            json.loads((ROOT / "examples/001-head-basic.svm.json").read_bytes())
        )
        extra = collect_witnesses(extra_store, extra_store.head)[0]
        forged = replace(
            base_witness, revision=replace(base_witness.revision, message="caller:forged")
        )
        variants = (
            (),
            (base_witness,),
            witnesses[1:],
            witnesses[::-1],
            (*witnesses, witnesses[0]),
            tuple(sorted((*witnesses, extra), key=lambda w: w.revision.revision_id)),
            tuple(forged if w == base_witness else w for w in witnesses),
        )
        for supplied in variants:
            with self.subTest(witness_count=len(supplied)):
                result = self.derive(
                    witnesses=supplied, resolver=ResolverOnly(self.artifacts, forbid=True)
                )
                self.assert_failure(result, Reason.HISTORY_BROKEN, Stage.S0)
                self.assertTrue(all(a.admitted is None for a in result.claim_audits))

    def test_witness_defect_outranks_transport_and_snapshot_defects(self):
        document = self.store.get_document(self.store.head)
        document["references"] = []
        missing_reference_id = self.store.get_document(self.store.head)
        missing_reference_id["references"] = [{"media_type": certification.MEDIA}]
        missing_reference_media = self.store.get_document(self.store.head)
        missing_reference_media["references"] = [{"id": ASSOCIATION_ID}]
        missing_identity_id = self.store.get_document(self.store.head)
        missing_identity_id["temporal_identities"] = [{}]
        variants = (
            {"document": document, "source_references": ()},
            {"source_references": ({"media_type": certification.MEDIA},)},
            {"source_references": ({"id": ASSOCIATION_ID},)},
            {"document": missing_reference_id},
            {"document": missing_reference_media},
            {"document": missing_identity_id},
        )
        for supplied in variants:
            with self.subTest(supplied=supplied):
                resolver = ResolverOnly(self.artifacts, forbid=True)
                with patch.object(
                    certification,
                    "admitted_associations",
                    side_effect=AssertionError("S0 failure must not replay"),
                ) as replay:
                    result = self.derive(witnesses=(), resolver=resolver, **supplied)
                self.assert_failure(result, Reason.HISTORY_BROKEN, Stage.S0)
                replay.assert_not_called()
                self.assertEqual(resolver.calls, [])

    def test_missing_blob_hash_tampering_and_descriptor_conflict_fail_closed(self):
        original = copy.deepcopy(self.artifacts)
        for fault in ("missing", "bytes", "descriptor", "resolver_bytes", "descriptor_id"):
            with self.subTest(fault=fault):
                self.artifacts = copy.deepcopy(original)
                resolver = ResolverOnly(self.artifacts)
                if fault == "missing":
                    del self.artifacts._blobs[ASSOCIATION_ID]
                elif fault == "bytes":
                    blob = self.artifacts._blobs[ASSOCIATION_ID]
                    self.artifacts._blobs[ASSOCIATION_ID] = replace(blob, content=b"forged content")
                elif fault == "descriptor":
                    resolver.descriptor_fault = ASSOCIATION_ID
                else:
                    resolver.snapshot_fault = (
                        "bytes" if fault == "resolver_bytes" else "descriptor_id"
                    )
                    supplied = resolver.resolve_reference(self.certificate)
                    self.assertEqual(supplied.document_reference(), self.certificate)
                    if fault == "resolver_bytes":
                        self.assertNotEqual(
                            hashlib.sha256(supplied.content).hexdigest(),
                            self.certificate["id"].split(":")[1],
                        )
                    else:
                        self.assertNotEqual(
                            supplied.descriptor.artifact_id, supplied.blob.artifact_id
                        )
                self.assert_failure(
                    self.derive(resolver=resolver), Reason.UNREPLAYABLE_ASSOCIATION, Stage.S3
                )

    def test_malformed_duplicate_and_incompatible_event_histories_fail_at_s0(self):
        original = copy.deepcopy(self.store)
        event = self.store.revisions[self.store.head].admissions[0]
        for events in (
            (event, event),
            (replace(event, authority_identity="caller:verifier"),),
            (replace(event, contract="caller:unsupported-contract"),),
            (replace(event, transition_hash="revision:" + "0" * 64),),
        ):
            with self.subTest(events=len(events)):
                self.store = copy.deepcopy(original)
                self.replace_head_events(events)
                self.assert_failure(
                    self.derive(resolver=ResolverOnly(self.artifacts, forbid=True)),
                    Reason.HISTORY_BROKEN,
                    Stage.S0,
                )

    def test_counterfeit_event_bound_record_is_not_authenticated_by_its_bytes(self):
        payload = json.loads(self.artifacts.resolve_reference(self.certificate).content)
        self.store = copy.deepcopy(self.uncertified)
        payload["association"]["group_id"] = "group:" + "d" * 64
        self.install_counterfeit_claim(payload)
        self.assert_failure(self.derive(), Reason.UNREPLAYABLE_ASSOCIATION, Stage.S3)

    def test_duplicate_equivalent_claims_fail_replay_without_partial_selection(self):
        payload = json.loads(self.artifacts.resolve_reference(self.certificate).content)
        payload["universe"]["association_references"] = [self.certificate]
        second = self.install_counterfeit_claim(payload)
        self.assertNotEqual(second["id"], ASSOCIATION_ID)
        # Frozen Mode A raises before yielding two authenticated records at the second birth.
        result = self.derive()
        self.assert_failure(result, Reason.UNREPLAYABLE_ASSOCIATION, Stage.S3)
        self.assertEqual(len(result.claim_audits), 2)

    def test_existing_legitimate_binding_preserves_authority_and_skips_current_replay(self):
        binding = self.bind()
        bound_head = self.store.head
        real_replay = certification.admitted_associations
        with patch.object(certification, "admitted_associations", wraps=real_replay) as replay:
            result = self.derive()
        self.assertEqual(result.status, Status.ABSTAIN)
        self.assertEqual(result.abstention_reason, Reason.ZERO_SELECTED)
        self.assertEqual(result.selected_pairs, ())
        whole = next(e for e in result.evaluations if e.temporal_identity_id == WHOLE_IDENTITY)
        self.assertEqual(whole.status, Status.REJECT)
        self.assertEqual(whole.reason, Reason.ALREADY_BOUND)
        self.assertEqual(whole.stage, Stage.S4)
        self.assertEqual(whole.existing_binding_ids, (binding["id"],))
        self.assertEqual(result.existing_bindings, (binding,))
        self.assertEqual(
            [call.args[0] for call in replay.call_args_list], [self.certification_revision]
        )
        self.assertNotEqual(bound_head, self.certification_revision)
        self.assertNotEqual(
            self.store.revisions[self.certification_revision].admissions[0].transition_hash,
            self.certification_revision,
        )

    def test_group_endpoint_binding_to_another_identity_is_already_bound(self):
        other = next(
            t["id"]
            for t in self.store.get_document(self.store.head)["temporal_identities"]
            if t["id"] != WHOLE_IDENTITY
        )
        binding = self.bind(other)
        result = self.derive()
        whole = next(e for e in result.evaluations if e.temporal_identity_id == WHOLE_IDENTITY)
        self.assertEqual(whole.reason, Reason.ALREADY_BOUND)
        self.assertEqual(whole.existing_binding_ids, (binding["id"],))
        self.assertEqual(result.selected_pairs, ())

    def test_bound_state_never_hides_history_transport_or_artifact_fraud(self):
        self.bind()
        witnesses = collect_witnesses(self.store, self.store.head)
        self.assert_failure(self.derive(witnesses=witnesses[::-1]), Reason.HISTORY_BROKEN, Stage.S0)
        self.assert_failure(
            self.derive(source_references=()), Reason.UNREPLAYABLE_ASSOCIATION, Stage.S1
        )
        del self.artifacts._blobs[ASSOCIATION_ID]
        result = self.derive()
        self.assert_failure(result, Reason.UNREPLAYABLE_ASSOCIATION, Stage.S3)
        self.assertFalse(any(e.reason == Reason.ALREADY_BOUND for e in result.evaluations))

    def test_legal_group_and_member_tracks_are_ineligible_without_current_replay(self):
        original = copy.deepcopy(self.store)
        member = self.birth_change.fragment.entities[0]["id"]
        changes = (
            CreateGroupTransformTrackChange("track:consumer-group", GROUP_ID, "translate.x", 12),
            CreateStyleTrackChange("track:consumer-style", member, "opacity", 12),
        )
        for change in changes:
            with self.subTest(track=change.track_id):
                self.store = copy.deepcopy(original)
                self.store.commit(
                    self.store.head,
                    Transaction(
                        "transaction:legal-existing-track",
                        (change, AddKeyframeChange(change.track_id, "keyframe:consumer", 0, 0)),
                    ),
                )
                real_replay = certification.admitted_associations
                with patch.object(
                    certification, "admitted_associations", wraps=real_replay
                ) as replay:
                    result = self.derive()
                whole = next(
                    e for e in result.evaluations if e.temporal_identity_id == WHOLE_IDENTITY
                )
                self.assertEqual(whole.reason, Reason.TRACKED_REPRESENTATION)
                self.assertEqual(whole.stage, Stage.S5)
                self.assertEqual(result.abstention_reason, Reason.ZERO_SELECTED)
                self.assertEqual(result.selected_pairs, ())
                self.assertEqual(
                    [call.args[0] for call in replay.call_args_list], [self.certification_revision]
                )

    def test_current_group_geometry_and_identity_edits_fail_applicability(self):
        original = copy.deepcopy(self.store)
        transform = copy.deepcopy(
            self.store.get_document(self.store.head)["groups"][0]["transform"]
        )
        transform["translate"][0] = 1
        edits = (
            SetGroupTransformChange(GROUP_ID, transform),
            SetOperationParameterChange(
                self.birth_change.fragment.operations[0]["id"], "d", "M 21 20 L 100 20 L 20 80 Z"
            ),
            FixtureMutation(
                lambda d: next(t for t in d["temporal_identities"] if t["id"] == WHOLE_IDENTITY)[
                    "bindings"
                ][0].update(observation_id="observation:caller")
            ),
        )
        for change in edits:
            with self.subTest(change=type(change).__name__):
                self.store = copy.deepcopy(original)
                self.store.commit(
                    self.store.head, Transaction("transaction:legal-current-edit", (change,))
                )
                self.assert_failure(self.derive(), Reason.UNREPLAYABLE_ASSOCIATION, Stage.S6)

    def test_missing_dependency_and_remove_restore_history_never_recover_applicability(self):
        original = copy.deepcopy(self.store)
        reference = self.membership_reference
        self.mutate(
            lambda d: d.update(
                references=[r for r in d["references"] if r["id"] != reference["id"]]
            )
        )
        self.assert_failure(self.derive(), Reason.UNREPLAYABLE_ASSOCIATION, Stage.S3)
        self.store = copy.deepcopy(original)
        document = self.store.get_document(self.store.head)
        self.mutate(
            lambda d: d.update(
                references=[r for r in d["references"] if r["id"] != reference["id"]]
            )
        )
        self.mutate(lambda d: d.update(references=copy.deepcopy(document["references"])))
        self.assertEqual(self.store.get_document(self.store.head), document)
        self.assert_failure(self.derive(), Reason.UNREPLAYABLE_ASSOCIATION, Stage.S6)

    def test_second_replayed_reference_contract_violation_cannot_create_partial_selection(self):
        data = self.artifacts.import_bytes(
            b"second asserted pair", media_type=certification.MEDIA
        ).document_reference()
        self.store.commit(
            self.store.head,
            Transaction("transaction:data-second-pair", (AppendReferencesChange((data,)),)),
        )
        # Deliberately violate the frozen return contract; this is never a real admission.
        with patch.object(
            certification, "admitted_associations", return_value=(self.certificate, data)
        ):
            result = self.derive()
            self.assert_failure(result, Reason.UNREPLAYABLE_ASSOCIATION, Stage.S3)
        data_audit = next(a for a in result.claim_audits if a.reference == data)
        self.assertFalse(data_audit.admitted)
        self.assertEqual(data_audit.status, Status.ABSTAIN)
        self.assertEqual(data_audit.stage, Stage.S2)
        self.assertIsNone(data_audit.temporal_identity_id)

    def test_engine_exception_text_never_changes_error_classification(self):
        self.bind()
        with patch.object(
            certification,
            "admitted_associations",
            side_effect=certification.RepresentationCertificationError(
                "ALREADY_BOUND TRACKED_REPRESENTATION NO_ADMITTED_ASSOCIATION"
            ),
        ):
            self.assert_failure(self.derive(), Reason.UNREPLAYABLE_ASSOCIATION, Stage.S3)

    def test_same_base_rerun_is_deterministic_and_accepted_artifact_writer_is_unused(self):
        with patch.object(
            self.artifacts,
            "import_bytes",
            side_effect=AssertionError("Consumer cannot write Artifacts"),
        ) as writer:
            first = self.derive(resolver=self.artifacts)
            second = self.derive(resolver=self.artifacts)
        writer.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(canonical_bytes(asdict(first)), canonical_bytes(asdict(second)))
        self.assertLessEqual(len(first.selected_pairs), 1)
        self.assertFalse(hasattr(first, "proposal"))
        self.assertFalse(hasattr(first, "transaction"))

    def test_existing_golden_documents_artifacts_and_svg_are_unmodified(self):
        document = self.store.get_document(self.store.head)
        self.assertEqual(
            document,
            json.loads(
                (ROOT / "examples/046-representation-certification/accepted.svm.json").read_bytes()
            ),
        )
        self.assertEqual(
            self.artifacts.resolve_reference(self.certificate).content,
            (ROOT / "examples/046-representation-certification/certification.json").read_bytes(),
        )
        self.assertEqual(
            render(document).encode(),
            (ROOT / "examples/044-video-artwork-construction/group.svg").read_bytes(),
        )
        self.assertEqual(golden_files(), self.original_golden_files)

    def test_returned_reference_snapshots_are_detached_from_inputs_and_accepted_state(self):
        document = self.store.get_document(self.store.head)
        witnesses = collect_witnesses(self.store, self.store.head)
        before = copy.deepcopy((document, witnesses, self.store, vars(self.artifacts)))
        result = self.derive(document=document, witnesses=witnesses)
        result.source_references[0]["uri"] = "caller:changed-output"
        result.claim_audits[0].reference["import_metadata"]["provenance"]["caller"] = True
        whole = next(e for e in result.evaluations if e.temporal_identity_id == WHOLE_IDENTITY)
        whole.association_reference["uri"] = "caller:changed-selected-output"
        self.assertEqual((document, witnesses, self.store, vars(self.artifacts)), before)


if __name__ == "__main__":
    unittest.main()
