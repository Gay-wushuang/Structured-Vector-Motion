"""Spec81 B0-2 acceptance using genuine Golden046 and test-only Proposals."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import unittest
from dataclasses import replace
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

from svm import AdapterRequest, GeneratorProvenance, Proposal, ProposalAcceptor, Transaction
from svm.adapters.temporal_motion_target_binding import TemporalMotionTargetBindingAdapter
from svm.admission_history import dump_trusted_history, history_digest, load_trusted_history
from svm.artifacts import ArtifactKind
from svm.change_authority import change_authority, resolve_transaction_intents
from svm.document import DocumentError
from svm.evaluator import canonical_bytes
from svm.multipart_witness import (
    RevisionSnapshotWitness,
    authenticate_witnesses,
    collect_witnesses,
)
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.representation_target_consumer import (
    POLICY_IDENTITY,
    REASON_NAMESPACE,
    Reason,
    Status,
    derive_certified_targets,
)
from svm.representation_target_selection import (
    CHANGE_IDENTITY,
    MEDIA,
    SCHEMA,
    RepresentationTargetSelectionError,
    evidence_payload,
    verify_change,
)
from svm.revisions import (
    AddKeyframeChange,
    AppendReferencesChange,
    ApplyRepresentationTargetSelectionChange,
    BindTemporalMotionTargetChange,
    CreateGroupTransformTrackChange,
    Revision,
    SetGroupTransformChange,
    SetOperationParameterChange,
)

ACTOR = "adapter:test-representation-target-selection"
BINDING_ID = (
    "motion-target-binding:234a54dd65aedc815735519bce19d646f9af306c110f937fa8d1fe11cec8d776"
)


class RepresentationTargetSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Full discovery runs the existing consumer class first. Reuse its real
        # pipeline instead of regenerating source/video for a second test class.
        existing = consumer_fixture.RepresentationTargetConsumerTest
        if not hasattr(existing, "fixture"):
            existing.setUpClass()
        cls.fixture = copy.deepcopy(existing.fixture)
        cls.uncertified_store = copy.deepcopy(existing.uncertified_store)
        store, artifacts = cls.fixture["store"], cls.fixture["artifacts"]
        cls.base = store.head
        cls.result = derive_certified_targets(
            store.head,
            store.get_document(store.head),
            collect_witnesses(store, store.head),
            artifacts,
        )
        cls.payload = evidence_payload(cls.result, store.revisions[store.head].document_hash)
        cls.original_goldens = consumer_fixture.golden_files()

    def setUp(self):
        fixture = copy.deepcopy(self.fixture)
        self.store = fixture["store"]
        self.artifacts = fixture["artifacts"]
        self.membership_reference = (
            fixture["observations"].transaction.changes[0].evidence_reference
        )
        self.birth_change = fixture["construction"].transaction.changes[0]

    def proposal(self):
        """Test-only packaging; no production generator or acceptance shortcut."""
        base = self.store.head
        document = self.store.get_document(base)
        witnesses = collect_witnesses(self.store, base)
        result = self.result
        if base != self.base:
            current = derive_certified_targets(base, document, witnesses, self.artifacts)
            if current.status == Status.SELECTED:
                result = current
            # A non-selected state deliberately submits the old alleged proof.
            # The verifier must reject the real derivation before trusting it.
        payload = evidence_payload(result, self.store.revisions[base].document_hash)
        reference = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"policy_identity": POLICY_IDENTITY},
        ).document_reference()
        frozen = (
            TemporalMotionTargetBindingAdapter()
            .propose(
                AdapterRequest.from_store(
                    self.store,
                    base,
                    ("document",),
                    options={"temporal_identity_id": WHOLE_IDENTITY, "group_id": GROUP_ID},
                ),
                self.artifacts,
            )
            .transaction.changes[0]
        )
        change = ApplyRepresentationTargetSelectionChange(
            source_revision_id=base,
            base_document_snapshot=document,
            witnesses=witnesses,
            policy_identity=POLICY_IDENTITY,
            source_references=tuple(sorted(document["references"], key=lambda r: r["id"])),
            selection_evidence_reference=reference,
            delegated_binds=(frozen,),
            selected_pairs=((WHOLE_IDENTITY, GROUP_ID),),
        )
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        return Proposal(
            proposal_id="proposal:test-selection:" + digest,
            base_revision_id=base,
            generator=GeneratorProvenance(ACTOR, "0.1", "test-only", "0.1"),
            transaction=Transaction(
                "transaction:test-selection:" + digest,
                (change,),
                "Test-only certified target selection",
            ),
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
        )

    @staticmethod
    def changed(proposal, *changes):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=changes),
            required_artifact_ids=tuple(
                dict.fromkeys(
                    ref["id"] for change in changes for ref in getattr(change, "references", ())
                )
            ),
        )

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def rejected(self, proposal, pattern, *, error=ProposalArtifactError, action=None):
        before = copy.deepcopy(self.store)
        artifact_state = copy.deepcopy(vars(self.artifacts))
        with self.assertRaisesRegex(error, pattern):
            (action or (lambda: self.accept(proposal)))()
        self.assertEqual(self.store, before)
        self.assertEqual(self.store.head, before.head)
        self.assertEqual(len(self.store.revisions), len(before.revisions))
        self.assertEqual(self.store.get_document(self.store.head), before.get_document(before.head))
        self.assertEqual(
            self.store.get_document(self.store.head)["references"],
            before.get_document(before.head)["references"],
        )
        self.assertEqual(vars(self.artifacts), artifact_state)

    def tampered_payload(self, proposal, mutate, *, canonical=True):
        change = proposal.transaction.changes[0]
        original = self.artifacts.resolve_reference(change.selection_evidence_reference)
        payload = json.loads(original.content)
        mutate(payload)
        content = canonical_bytes(payload) if canonical else json.dumps(payload, indent=2).encode()
        reference = self.artifacts.import_bytes(
            content,
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"policy_identity": POLICY_IDENTITY},
        ).document_reference()
        return self.changed(proposal, replace(change, selection_evidence_reference=reference))

    def mutate(self, change):
        self.store.commit(self.store.head, Transaction("transaction:test-state", (change,)))

    def test_genuine_acceptance_adds_only_one_frozen_binding_and_one_evidence_reference(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        before = self.store.get_document(self.store.head)
        old_store = copy.deepcopy(self.store)
        ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(self.store, old_store)
        revision = self.accept(proposal)
        after = self.store.get_document(self.store.head)
        self.assertEqual(revision.parent_ids, (CERTIFICATION_REVISION,))
        self.assertEqual(len(self.store.revisions), len(old_store.revisions) + 1)
        self.assertEqual(getattr(revision, "admissions", ()), ())
        self.assertEqual(after["motion_target_bindings"], [change.delegated_binds[0].binding])
        self.assertEqual(after["motion_target_bindings"][0]["id"], BINDING_ID)
        self.assertEqual(
            after["references"], before["references"] + [change.selection_evidence_reference]
        )
        restored = copy.deepcopy(after)
        restored.pop("motion_target_bindings")
        restored["references"].pop()
        self.assertEqual(restored, before)
        self.assertEqual(render(after), render(before))
        self.assertEqual(self.store.get_document(CERTIFICATION_REVISION), before)
        history = dump_trusted_history(self.store)
        loaded = load_trusted_history(history, trusted_history_hash=history_digest(history))
        self.assertEqual(dump_trusted_history(loaded), history)
        result = derive_certified_targets(
            self.store.head, after, collect_witnesses(self.store, self.store.head), self.artifacts
        )
        self.assertEqual(result.selected_pairs, ())
        self.assertEqual(result.abstention_reason, Reason.ZERO_SELECTED)
        whole = next(e for e in result.evaluations if e.temporal_identity_id == WHOLE_IDENTITY)
        self.assertEqual(whole.reason, Reason.ALREADY_BOUND)
        with patch("svm.representation_target_selection.verify_change") as verifier:
            self.rejected(proposal, "does not match head", error=ProposalConflictError)
            verifier.assert_not_called()

    def test_exact_evidence_envelope_complete_counts_and_explicit_nulls(self):
        proposal = self.proposal()
        reference = proposal.transaction.changes[0].selection_evidence_reference
        snapshot = self.artifacts.resolve_reference(reference)
        payload = json.loads(snapshot.content)
        self.assertEqual(
            set(payload),
            {
                "schema_version",
                "policy_identity",
                "reason_namespace",
                "base",
                "result",
                "evaluations",
                "identity_ids",
                "group_ids",
                "existing_bindings",
                "selected_pairs",
                "claim_audits",
                "counts",
            },
        )
        self.assertEqual(payload["schema_version"], SCHEMA)
        self.assertEqual(payload["policy_identity"], POLICY_IDENTITY)
        self.assertEqual(payload["reason_namespace"], REASON_NAMESPACE)
        self.assertEqual(
            payload["result"],
            {
                "stage": "S7",
                "status": "SELECTED",
                "rejection_reason": None,
                "abstention_reason": None,
            },
        )
        self.assertEqual(
            payload["counts"],
            {
                "total": 3,
                "selected": 1,
                "abstain": 2,
                "reject": 0,
                "selected_pairs": 1,
            },
        )
        self.assertTrue(all(type(value) is int for value in payload["counts"].values()))
        self.assertEqual(len(payload["evaluations"]), len(payload["identity_ids"]))
        self.assertEqual(payload["group_ids"], [GROUP_ID])
        self.assertEqual(
            payload["selected_pairs"],
            [
                {
                    "temporal_identity_id": WHOLE_IDENTITY,
                    "group_id": GROUP_ID,
                }
            ],
        )
        self.assertEqual(
            payload["claim_audits"][0]["acceptance_revision_id"], CERTIFICATION_REVISION
        )
        self.assertIsNone(payload["claim_audits"][0]["reason"])
        self.assertEqual(snapshot.content, canonical_bytes(payload))
        self.assertEqual(snapshot.kind, ArtifactKind.DERIVED)
        self.assertEqual(snapshot.provenance, {"policy_identity": POLICY_IDENTITY})
        self.assertEqual(reference["uri"], reference["id"])

    def test_same_base_rebuild_reuses_bytes_descriptor_and_required_transport(self):
        first = self.proposal()
        artifact_state = copy.deepcopy(vars(self.artifacts))
        second = self.proposal()
        self.assertEqual(first, second)
        self.assertEqual(vars(self.artifacts), artifact_state)
        change = first.transaction.changes[0]
        self.assertEqual(
            change.references,
            tuple(
                sorted(
                    (*change.source_references, change.selection_evidence_reference),
                    key=lambda r: r["id"],
                )
            ),
        )
        self.assertEqual(set(first.required_artifact_ids), {r["id"] for r in change.references})

    def test_closed_registration_uses_both_existing_frozen_policy_intents(self):
        proposal = self.proposal()
        authority = change_authority(proposal.transaction.changes[0])
        self.assertEqual(
            CHANGE_IDENTITY, "svm.revisions.ApplyRepresentationTargetSelectionChange@0.1"
        )
        self.assertEqual(authority.actions, frozenset({"bind_motion_target", "attach_analysis"}))
        self.assertEqual(
            resolve_transaction_intents(proposal.transaction),
            (
                ("bind_motion_target", GROUP_ID, WHOLE_IDENTITY),
                ("attach_analysis", "document", None),
            ),
        )
        self.assertIsNotNone(authority.artifact_verifier)
        self.assertEqual(
            authority.source_revision_resolver(proposal.transaction.changes[0]), self.base
        )

    def test_composite_constructor_and_slots_exclude_caller_authority_fields(self):
        change = self.proposal().transaction.changes[0]
        fields = {name: getattr(change, name) for name in change.__dataclass_fields__}
        with self.assertRaisesRegex(TypeError, "unexpected keyword"):
            ApplyRepresentationTargetSelectionChange(**fields, caller_verified=True)
        with self.assertRaises(AttributeError):
            object.__setattr__(change, "caller_verified", True)

    def test_tampered_counts_arrays_field_sets_and_consumer_nulls_reject(self):
        proposal = self.proposal()
        for key in ("total", "selected", "abstain", "reject", "selected_pairs"):
            with self.subTest(boolean_count=key):
                self.rejected(
                    self.tampered_payload(
                        proposal,
                        lambda p, key=key: p["counts"].update({key: bool(p["counts"][key])}),
                    ),
                    "exact JSON integers",
                )
        mutations = (
            lambda p: p["counts"].update(selected=1.0),
            lambda p: p["counts"].update(total=3.0),
            lambda p: p["counts"].update(abstain=0),
            lambda p: p.update(evaluations=p["evaluations"][:-1]),
            lambda p: p.update(evaluations=p["evaluations"][::-1]),
            lambda p: p.update(claim_audits=[]),
            lambda p: p.update(identity_ids=p["identity_ids"][:-1]),
            lambda p: p.update(group_ids=[]),
            lambda p: p.update(selected_pairs=[]),
            lambda p: p["selected_pairs"].append(copy.deepcopy(p["selected_pairs"][0])),
            lambda p: p.update(existing_bindings=[{"id": "caller:binding"}]),
            lambda p: p.update(schema_version=None),
            lambda p: p["result"].update(status="ABSTAIN"),
            lambda p: p["claim_audits"][0].update(admitted=None),
            lambda p: p.update(caller_metadata={"verified": True}),
            lambda p: p.pop("reason_namespace"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.rejected(self.tampered_payload(proposal, mutate), "Selection evidence")

    def test_noncanonical_and_nonobject_output_bytes_reject(self):
        proposal = self.proposal()
        self.rejected(
            self.tampered_payload(proposal, lambda p: None, canonical=False), "Selection evidence"
        )
        change = proposal.transaction.changes[0]
        for content in (b"[]", b"null", b"not-json"):
            reference = self.artifacts.import_bytes(
                content,
                media_type=MEDIA,
                kind=ArtifactKind.DERIVED,
                provenance={"policy_identity": POLICY_IDENTITY},
            ).document_reference()
            self.rejected(
                self.changed(proposal, replace(change, selection_evidence_reference=reference)),
                "Selection evidence",
            )

    def test_output_descriptor_kind_media_provenance_and_locator_are_exact(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        content = self.artifacts.resolve_reference(change.selection_evidence_reference).content
        variants = (
            {"kind": ArtifactKind.REFERENCE},
            {"media_type": "application/json"},
            {"provenance": {"policy_identity": POLICY_IDENTITY, "verified": True}},
            {"provenance": {"policy_identity": "caller-policy"}},
            {"locator": "caller:locator"},
        )
        for overrides in variants:
            with self.subTest(overrides=overrides):
                reference = self.artifacts.import_bytes(
                    content,
                    **{
                        "media_type": MEDIA,
                        "kind": ArtifactKind.DERIVED,
                        "provenance": {"policy_identity": POLICY_IDENTITY},
                        **overrides,
                    },
                ).document_reference()
                self.rejected(
                    self.changed(proposal, replace(change, selection_evidence_reference=reference)),
                    "Selection.*(evidence|descriptor)",
                )

    def test_complete_pair_and_exact_delegated_record_are_independently_reproduced(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        for pairs in (
            (),
            ((GROUP_ID, WHOLE_IDENTITY),),
            change.selected_pairs * 2,
            list(change.selected_pairs),
            (list(change.selected_pairs[0]),),
        ):
            with self.subTest(pairs=pairs):
                self.rejected(
                    self.changed(proposal, replace(change, selected_pairs=pairs)),
                    "Selection.*(pair|cardinality|binding)",
                )
        for binds in ((), change.delegated_binds * 2, list(change.delegated_binds)):
            with self.subTest(bind_count=len(binds)):
                self.rejected(
                    self.changed(proposal, replace(change, delegated_binds=binds)),
                    "Selection.*(pair|cardinality|binding)",
                )
        bind = change.delegated_binds[0]
        for field, value in (
            ("binding", {**bind.binding, "id": "motion-target-binding:caller"}),
            ("source_revision_id", "revision:" + "0" * 64),
            ("temporal_identity", self.store.get_document(self.base)["temporal_identities"][0]),
            ("group", {**bind.group, "members": bind.group["members"][::-1]}),
        ):
            with self.subTest(field=field):
                altered = replace(bind, **{field: value})
                self.rejected(
                    self.changed(proposal, replace(change, delegated_binds=(altered,))),
                    "Selection.*(binding|source|frozen)",
                )

    def test_outer_and_nested_subclasses_cannot_execute_unregistered_behavior(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        executed = []

        def forbidden_apply(_self, _document):
            executed.append(True)
            raise AssertionError("Unregistered nested code executed")

        outer_type = type("UnauthorizedSelection", (type(change),), {"apply": forbidden_apply})
        outer = outer_type(**{name: getattr(change, name) for name in change.__dataclass_fields__})
        self.rejected(self.changed(proposal, outer), "Unregistered", error=ProposalPolicyError)
        bind = change.delegated_binds[0]
        nested_type = type("UnauthorizedBinding", (type(bind),), {"apply": forbidden_apply})
        nested = nested_type(
            bind.binding, bind.temporal_identity, bind.group, bind.source_revision_id
        )
        self.rejected(
            self.changed(proposal, replace(change, delegated_binds=(nested,))),
            "exact frozen binding",
        )
        self.assertEqual(executed, [])

    def test_witness_failures_precede_transport_defects(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        wrong = replace(
            change.witnesses[-1],
            revision=replace(change.witnesses[-1].revision, message="caller history"),
        )
        variants = (
            (),
            change.witnesses[:-1],
            change.witnesses[::-1],
            (*change.witnesses[:-1], wrong),
        )
        for witnesses in variants:
            with self.subTest(witness_count=len(witnesses)):
                self.rejected(
                    self.changed(proposal, replace(change, witnesses=witnesses)), "HISTORY_BROKEN"
                )
        self.rejected(
            self.changed(proposal, replace(change, witnesses=(), source_references=())),
            "HISTORY_BROKEN",
        )

    def test_behavior_bearing_revision_metadata_cannot_hide_ancestry(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        head = self.store.commit(
            self.store.head,
            Transaction("transaction:metadata-audit", (), "Metadata audit"),
        )
        calls = {"iter": 0, "getitem": 0}

        class EncodedParents(tuple):
            current_base = head.revision_id

            def __iter__(self):
                calls["iter"] += 1
                if any(frame.function == "iterencode" for frame in inspect.stack()):
                    return tuple.__iter__(self)
                return iter(())

            def __getitem__(self, index):
                calls["getitem"] += 1
                if index == 0:
                    return self.current_base
                return tuple.__getitem__(self, index)

            def __deepcopy__(self, memo):
                return self

        hostile = replace(head, parent_ids=EncodedParents(head.parent_ids))
        document = self.store.get_document(head.revision_id)
        witness = RevisionSnapshotWitness(hostile, document)
        # The frozen hashing/traversal API accepts this head-only witness even
        # though the actual parent is absent. The new boundary must reject the
        # metadata before running either caller-controlled traversal method.
        self.assertEqual(canonical_bytes(head.parent_ids), canonical_bytes(hostile.parent_ids))
        self.assertEqual(
            self.store._make_revision(
                document, hostile.parent_ids, head.transaction_id, head.message
            ),
            hostile,
        )
        self.assertEqual(
            set(authenticate_witnesses(head.revision_id, (witness,))), {head.revision_id}
        )
        self.assertNotEqual(head.parent_ids, ())
        calls.update(iter=0, getitem=0)
        hostile_change = replace(
            change,
            source_revision_id=head.revision_id,
            base_document_snapshot=document,
            witnesses=(witness,),
            delegated_binds=(
                replace(change.delegated_binds[0], source_revision_id=head.revision_id),
            ),
        )
        hostile_proposal = self.changed(
            replace(proposal, base_revision_id=head.revision_id), hostile_change
        )
        with patch("svm.representation_target_selection.authenticate_witnesses") as authenticate:
            with self.assertRaisesRegex(RepresentationTargetSelectionError, "HISTORY_BROKEN"):
                verify_change(hostile_change, {})
            self.rejected(hostile_proposal, "HISTORY_BROKEN")
            authenticate.assert_not_called()
        self.assertEqual(calls, {"iter": 0, "getitem": 0})

    def test_extra_instance_attributes_cannot_impersonate_frozen_authority(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        executed = []

        class FalseyAdmissions(tuple):
            def __bool__(self):
                executed.append("admission truthiness")
                return False

        variants = []
        witness = copy.deepcopy(change.witnesses[0])
        object.__setattr__(witness, "caller_claim", True)
        variants.append((0, witness))
        index = next(
            i for i, item in enumerate(change.witnesses) if type(item.revision) is Revision
        )
        witness = copy.deepcopy(change.witnesses[index])
        object.__setattr__(witness.revision, "admissions", FalseyAdmissions(()))
        variants.append((index, witness))
        index = next(
            i for i, item in enumerate(change.witnesses) if getattr(item.revision, "admissions", ())
        )
        witness = copy.deepcopy(change.witnesses[index])
        object.__setattr__(witness.revision.admissions[0], "caller_claim", True)
        variants.append((index, witness))
        key_calls = []

        class FieldName(str):
            def __hash__(self):
                key_calls.append("hash")
                return str.__hash__(self)

            def __eq__(self, other):
                key_calls.append("equality")
                return str.__eq__(self, other)

        for is_revision, field in ((False, "revision"), (True, "parent_ids")):
            witness = copy.deepcopy(change.witnesses[0])
            record = witness.revision if is_revision else witness
            attributes = vars(record)
            value = attributes.pop(field)
            attributes[FieldName(field)] = value
            variants.append((0, witness))
        # Construction necessarily hashes keys; validation must reject their
        # non-native type before hashing or comparing those keys again.
        key_calls.clear()
        with patch("svm.representation_target_selection.authenticate_witnesses") as authenticate:
            for index, witness in variants:
                witnesses = list(change.witnesses)
                witnesses[index] = witness
                self.rejected(
                    self.changed(proposal, replace(change, witnesses=tuple(witnesses))),
                    "HISTORY_BROKEN",
                )
            authenticate.assert_not_called()
        self.assertEqual(key_calls, [])

        delegated = copy.deepcopy(change.delegated_binds[0])

        def caller_apply(document):
            executed.append("binding apply")
            document["motion_target_bindings"] = []

        object.__setattr__(delegated, "apply", caller_apply)
        hostile = replace(change, delegated_binds=(delegated,))
        self.rejected(self.changed(proposal, hostile), "delegated Change fields must be exact")
        # The direct Core helper also dispatches the frozen class implementation,
        # so an instance attribute cannot substitute caller execution for S1.
        expected = copy.deepcopy(change.base_document_snapshot)
        actual = copy.deepcopy(expected)
        change.apply(expected)
        hostile.apply(actual)
        self.assertEqual(actual, expected)
        self.assertEqual(executed, [])

    def test_base_snapshot_reference_universe_policy_and_source_are_bound(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        snapshot = copy.deepcopy(change.base_document_snapshot)
        snapshot["references"] = []
        self.rejected(
            self.changed(proposal, replace(change, base_document_snapshot=snapshot)),
            "UNREPLAYABLE_ASSOCIATION",
        )
        altered = copy.deepcopy(change.source_references)
        altered[0]["uri"] = "caller:locator"
        original = self.artifacts.resolve_reference(change.source_references[0])
        self.artifacts.import_bytes(
            original.content,
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
            locator="caller:locator",
        )
        for refs in (
            change.source_references[1:],
            change.source_references[::-1],
            (*change.source_references, change.source_references[0]),
            altered,
        ):
            with self.subTest(reference_count=len(refs)):
                self.rejected(
                    self.changed(proposal, replace(change, source_references=refs)),
                    "UNREPLAYABLE_ASSOCIATION",
                )
        self.rejected(
            self.changed(proposal, replace(change, policy_identity="caller-policy")),
            "Selection.*policy",
        )
        self.rejected(
            self.changed(proposal, replace(change, source_revision_id="revision:" + "0" * 64)),
            "source revision does not match Proposal base",
        )

    def test_unresolved_artifact_stays_at_existing_acceptor_error_boundary(self):
        proposal = self.proposal()
        original = copy.deepcopy(self.artifacts)
        proof_id = proposal.transaction.changes[0].selection_evidence_reference["id"]
        with patch("svm.representation_target_selection.verify_change") as verifier:
            for aid in (proof_id, ASSOCIATION_ID):
                self.artifacts = copy.deepcopy(original)
                del self.artifacts._blobs[aid]
                self.rejected(proposal, "Unknown artifact")
            verifier.assert_not_called()

    def test_missing_required_ids_and_received_map_cannot_omit_transport(self):
        proposal = self.proposal()
        self.rejected(
            replace(proposal, required_artifact_ids=proposal.required_artifact_ids[1:]),
            "required Artifact IDs do not match",
        )
        self.rejected(
            replace(proposal, required_artifact_ids=proposal.required_artifact_ids * 2),
            "required Artifact IDs must be unique",
        )
        change = proposal.transaction.changes[0]
        resolved = {ref["id"]: self.artifacts.resolve_reference(ref) for ref in change.references}
        del resolved[change.selection_evidence_reference["id"]]
        self.rejected(
            proposal,
            "declared Artifact is absent",
            error=RepresentationTargetSelectionError,
            action=lambda: verify_change(change, resolved),
        )

    def test_received_snapshot_bytes_descriptor_identity_and_map_keys_are_verified(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        resolved = {ref["id"]: self.artifacts.resolve_reference(ref) for ref in change.references}
        proof_id = change.selection_evidence_reference["id"]
        proof = resolved[proof_id]
        faults = (
            replace(proof, blob=replace(proof.blob, content=b"tampered transported evidence")),
            replace(
                proof, descriptor=replace(proof.descriptor, artifact_id="artifact:" + "0" * 64)
            ),
            resolved[change.source_references[0]["id"]],
        )
        for fault in faults:
            with self.subTest(snapshot=fault):
                supplied = {**resolved, proof_id: fault}
                self.rejected(
                    proposal,
                    "transported bytes or exact descriptor mismatch",
                    error=RepresentationTargetSelectionError,
                    action=lambda supplied=supplied: verify_change(change, supplied),
                )
        self.rejected(
            proposal,
            "exactly the declared Artifact IDs",
            error=RepresentationTargetSelectionError,
            action=lambda: verify_change(change, {**resolved, "artifact:caller": proof}),
        )

    def test_uncertified_bound_and_tracked_states_cannot_accept_old_selection_proof(self):
        original = copy.deepcopy(self.store)
        self.store = copy.deepcopy(self.uncertified_store)
        self.rejected(self.proposal(), "NO_ADMITTED_ASSOCIATION")
        self.store = copy.deepcopy(original)
        bind = TemporalMotionTargetBindingAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                options={"temporal_identity_id": WHOLE_IDENTITY, "group_id": GROUP_ID},
            ),
            self.artifacts,
        )
        self.accept(bind)
        self.rejected(self.proposal(), "ZERO_SELECTED")
        self.store = copy.deepcopy(original)
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:existing-track",
                (
                    CreateGroupTransformTrackChange("track:selection", GROUP_ID, "translate.x", 12),
                    AddKeyframeChange("track:selection", "keyframe:selection", 0, 0),
                ),
            ),
        )
        self.rejected(self.proposal(), "ZERO_SELECTED")

    def test_current_representation_edit_and_missing_historical_dependency_fail_closed(self):
        original = copy.deepcopy(self.store)
        transform = copy.deepcopy(
            self.store.get_document(self.store.head)["groups"][0]["transform"]
        )
        transform["translate"][0] = 1
        for edit in (
            SetGroupTransformChange(GROUP_ID, transform),
            SetOperationParameterChange(
                self.birth_change.fragment.operations[0]["id"], "d", "M 21 20 L 100 20 L 20 80 Z"
            ),
        ):
            with self.subTest(edit=type(edit).__name__):
                self.store = copy.deepcopy(original)
                self.mutate(edit)
                self.rejected(self.proposal(), "UNREPLAYABLE_ASSOCIATION")
        self.store = copy.deepcopy(original)
        aid = self.membership_reference["id"]
        self.mutate(
            FixtureMutation(
                lambda d: d.update(references=[r for r in d["references"] if r["id"] != aid])
            )
        )
        self.rejected(self.proposal(), "UNREPLAYABLE_ASSOCIATION")

    def test_denying_binding_or_evidence_intent_publishes_neither(self):
        original = copy.deepcopy(self.store)
        for action, target in (("bind_motion_target", GROUP_ID), ("attach_analysis", "document")):
            self.store = copy.deepcopy(original)
            permission = {
                "id": "permission:selection",
                "actor": ACTOR,
                "effect": "deny",
                "actions": [action],
                "targets": [target],
            }
            self.mutate(FixtureMutation(lambda d, p=permission: d["edit_permissions"].append(p)))
            self.rejected(self.proposal(), "denies.*" + action, error=ProposalPolicyError)

    def test_single_composite_transaction_and_incoming_snapshot_guard(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        transform = copy.deepcopy(change.delegated_binds[0].group["transform"])
        transform["translate"][0] = 1
        before = SetGroupTransformChange(GROUP_ID, transform)
        no_op = AppendReferencesChange((change.source_references[0],))
        for changes in ((before, change), (change, before), (change, no_op)):
            with self.subTest(order=[type(item).__name__ for item in changes]):
                self.rejected(self.changed(proposal, *changes), "requires one composite Change")
        incoming = copy.deepcopy(change.base_document_snapshot)
        incoming["groups"][0]["transform"] = transform
        snapshot = copy.deepcopy(incoming)
        with self.assertRaisesRegex(DocumentError, "requires the exact base Document"):
            change.apply(incoming)
        self.assertEqual(incoming, snapshot)

    def test_direct_apply_rolls_back_failure_after_frozen_binding_mutation(self):
        change = self.proposal().transaction.changes[0]
        incoming = copy.deepcopy(change.base_document_snapshot)
        before = copy.deepcopy(incoming)
        frozen_apply = BindTemporalMotionTargetChange.apply

        def fail_after_binding(bind, document):
            frozen_apply(bind, document)
            self.assertEqual(document["motion_target_bindings"][0]["id"], BINDING_ID)
            raise DocumentError("selection delegated rollback marker")

        with patch.object(BindTemporalMotionTargetChange, "apply", fail_after_binding):
            with self.assertRaisesRegex(DocumentError, "delegated rollback marker"):
                change.apply(incoming)
        self.assertEqual(incoming, before)

    def test_behavior_bearing_witness_and_delegated_record_containers_reject(self):
        proposal = self.proposal()
        change = proposal.transaction.changes[0]
        executed = []

        class BehavioralDict(dict):
            def get(self, key, default=None):
                executed.append(key)
                raise AssertionError("Caller record behavior executed")

        witness = replace(
            change.witnesses[-1], document=BehavioralDict(change.witnesses[-1].document)
        )
        self.rejected(
            self.changed(proposal, replace(change, witnesses=(*change.witnesses[:-1], witness))),
            "HISTORY_BROKEN",
        )
        bind = change.delegated_binds[0]
        delegated = replace(bind, binding=BehavioralDict(bind.binding))
        self.rejected(
            self.changed(proposal, replace(change, delegated_binds=(delegated,))),
            "portable JSON data",
        )
        self.assertEqual(executed, [])

    def test_final_validation_failure_and_stale_base_do_not_publish(self):
        proposal = self.proposal()
        with patch(
            "svm.admission_history.validate_document",
            side_effect=DocumentError("selection final validation marker"),
        ):
            self.rejected(proposal, "final validation marker", error=DocumentError)
        transform = copy.deepcopy(
            self.store.get_document(self.store.head)["groups"][0]["transform"]
        )
        transform["translate"][0] = 1
        self.mutate(SetGroupTransformChange(GROUP_ID, transform))
        with patch("svm.representation_target_selection.verify_change") as verifier:
            self.rejected(proposal, "does not match head", error=ProposalConflictError)
            verifier.assert_not_called()

    def test_generic_selection_evidence_attachment_is_data_not_dedicated_authority(self):
        proof = self.proposal().transaction.changes[0].selection_evidence_reference
        before = self.store.get_document(self.store.head)
        generic = Proposal(
            "proposal:generic-selection-data",
            self.store.head,
            GeneratorProvenance(ACTOR, "0.1", "test-only", "0.1"),
            Transaction("transaction:generic-selection-data", (AppendReferencesChange((proof,)),)),
            required_artifact_ids=(proof["id"],),
        )
        with patch("svm.representation_target_selection.verify_change") as verifier:
            revision = self.accept(generic)
            verifier.assert_not_called()
        after = self.store.get_document(self.store.head)
        self.assertEqual(getattr(revision, "admissions", ()), ())
        self.assertNotIn("motion_target_bindings", after)
        self.assertEqual(after["references"], before["references"] + [proof])
        result = derive_certified_targets(
            self.store.head, after, collect_witnesses(self.store, self.store.head), self.artifacts
        )
        self.assertEqual(result.selected_pairs, ((WHOLE_IDENTITY, GROUP_ID),))
        self.assertEqual(len(result.claim_audits), 1)
        self.assertEqual(result.claim_audits[0].reference["id"], ASSOCIATION_ID)

    def test_unadmitted_certification_audit_preserves_source_provenance_locator_and_nulls(self):
        # Trusted legacy setup only: ordinary external proposals cannot add the
        # reserved certification media, and this plain revision creates no event.
        data = self.artifacts.import_bytes(
            b"ordinary legacy data; not JSON",
            media_type="application/vnd.svm.representation-certification+json;version=0.1",
            provenance={"caller": None, "verified": True, "path": "E:/caller/source"},
            locator="fixture:ordinary-data",
        ).document_reference()
        self.mutate(AppendReferencesChange((data,)))
        proposal = self.proposal()
        proof = self.artifacts.resolve_reference(
            proposal.transaction.changes[0].selection_evidence_reference
        )
        payload = json.loads(proof.content)
        audit = next(a for a in payload["claim_audits"] if a["reference"]["id"] == data["id"])
        self.assertEqual(audit["reference"], data)
        self.assertFalse(audit["admitted"])
        self.assertEqual(audit["status"], "ABSTAIN")
        self.assertEqual(audit["reason"], "NO_ADMITTED_ASSOCIATION")
        self.assertIsNone(audit["acceptance_revision_id"])
        self.accept(proposal)

    def test_frozen_s1_direct_acceptance_and_old_golden_bytes_remain_unchanged(self):
        proposal = TemporalMotionTargetBindingAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                options={"temporal_identity_id": WHOLE_IDENTITY, "group_id": GROUP_ID},
            ),
            self.artifacts,
        )
        before = self.store.get_document(self.store.head)
        self.accept(proposal)
        after = self.store.get_document(self.store.head)
        self.assertEqual(after["motion_target_bindings"][0]["id"], BINDING_ID)
        self.assertEqual(after["references"], before["references"])
        self.assertEqual(render(after), render(before))
        self.assertEqual(consumer_fixture.golden_files(), self.original_goldens)


if __name__ == "__main__":
    unittest.main()
