import copy
import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from test_authored_raster_production import pipeline

from svm import AdapterRequest, ProposalAcceptor, Transaction
from svm.adapters.multipart_subject_evidence import MultipartSubjectEvidenceAdapter
from svm.adapters.representation_certification import (
    MEDIA,
    PROFILE,
    SCHEMA,
    RepresentationCertificationAdapter,
    RepresentationCertificationError,
    admitted_associations,
)
from svm.adapters.subject_observation_bridge import (
    SubjectIdentityBridgeAdapter,
    SubjectObservationAdapter,
)
from svm.adapters.temporal_correspondence import TemporalCorrespondenceAdapter
from svm.adapters.temporal_identity_promotion import TemporalIdentityPromotionAdapter
from svm.adapters.temporal_motion_target_binding import TemporalMotionTargetBindingAdapter
from svm.adapters.video_artwork_construction import VideoArtworkConstructionAdapter
from svm.admission_history import (
    AUTHORITY as OWNERSHIP_AUTHORITY,
)
from svm.admission_history import (
    CERT_AUTHORITY,
    CERT_CHANGE,
    CERT_CONTRACT,
    CERT_MEDIA,
    dump_trusted_history,
    history_digest,
    load_trusted_history,
    transition_hash,
)
from svm.admission_history import (
    CHANGE as OWNERSHIP_CHANGE,
)
from svm.admission_history import (
    CONTRACT as OWNERSHIP_CONTRACT,
)
from svm.admission_history import (
    MEDIA as OWNERSHIP_MEDIA,
)
from svm.artifacts import ArtifactKind
from svm.change_authority import resolve_transaction_intents
from svm.evaluator import Evaluator, canonical_bytes
from svm.multipart_witness import authenticate_witnesses, collect_witnesses
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.revisions import (
    AddKeyframeChange,
    AdmissionEvent,
    AdmittedRevision,
    AppendReferencesChange,
    AppendSceneFragmentChange,
    CertifyArtworkRepresentationChange,
    CreateGroupTransformTrackChange,
    ReplaceSceneFragmentChange,
    SetGroupTransformChange,
    SetOperationParameterChange,
)
from svm.scene import build_evaluated_scene

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples/046-representation-certification"
GROUP_ID = "group:1f24284859439580faac31e69df1aa7bf6a1a28c450d8ddae2e3b42e48b656ac"
WHOLE_IDENTITY = (
    "temporal-identity:f89cc670dc7d6d8f54dd519532d525346817425825949ded13a79daae45aacbf"
)
ASSOCIATION_ID = "artifact:6ee8fd89abc03a3094d0e1b1fbc4fbd2043345bc7ff5418d2adbe7aee6262f47"
CERTIFICATION_REVISION = "revision:29f30d08a83e2db47bcf01db6acb28f1468e2792a38c94417b4435d52f449e87"
CERTIFICATION_DOCUMENT = "sha256:fb92332b3df73a954e43a00a7a24ccfc5161d068aabf8c643652d3949ff6e003"
CERTIFICATION_TRANSITION = (
    "revision:71bdbe8f816f845b4c53e144c478f618711c08fa8ab4bf82a24334e053317953"
)


class FixtureMutation:
    """Trusted test setup only; never an Adapter acceptance capability."""

    def __init__(self, mutate):
        self.mutate = mutate

    def apply(self, document):
        self.mutate(document)


def certification_fixture():
    """The real existing Spec75/76 -> part R1 -> F1A -> F0 sequence."""
    artifacts, store, _, _, _, ids, _ = pipeline()
    before_admission = copy.deepcopy(store)

    def request(**kwargs):
        return AdapterRequest.from_store(store, store.head, ("document",), **kwargs)

    def accept(adapter, *, witnessed=False, **kwargs):
        if witnessed:
            proposal = adapter.propose(
                request(**kwargs), artifacts, witnesses=collect_witnesses(store, store.head)
            )
        else:
            proposal = adapter.propose(request(**kwargs), artifacts)
        ProposalAcceptor().accept(store, proposal, artifacts)
        return proposal

    ownership = accept(MultipartSubjectEvidenceAdapter(), witnessed=True)
    part_r0 = accept(TemporalCorrespondenceAdapter(), artifact_ids=(ids[2],))
    part_r0_ref = part_r0.transaction.changes[0].references[0]
    candidates = json.loads(artifacts.resolve_reference(part_r0_ref).content)["candidates"]
    accept(
        TemporalIdentityPromotionAdapter(),
        artifact_ids=(part_r0_ref["id"],),
        options={
            "inference_ids": [c["inference_id"] for c in candidates if c["status"] == "SUPPORTED"]
        },
    )
    observations = accept(SubjectObservationAdapter(), witnessed=True)
    observation_ref = observations.transaction.changes[0].observation_reference
    subject_r0 = accept(TemporalCorrespondenceAdapter(), artifact_ids=(observation_ref["id"],))
    subject_identity = accept(SubjectIdentityBridgeAdapter(), witnessed=True)
    before_birth = copy.deepcopy(store)
    construction = accept(VideoArtworkConstructionAdapter(), witnessed=True)
    return {
        "artifacts": artifacts,
        "store": store,
        "before_admission": before_admission,
        "before_birth": before_birth,
        "ownership": ownership,
        "observations": observations,
        "r0": subject_r0,
        "subject_identity": subject_identity,
        "construction": construction,
    }


def render(document):
    return SVGRenderer(SVGRenderOptions(width=256, height=256, view_box=(0, 0, 256, 256))).render(
        build_evaluated_scene(document, Evaluator(document))
    )


class RepresentationCertificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = certification_fixture()

    def setUp(self):
        fixture = copy.deepcopy(self.fixture)
        self.artifacts = fixture["artifacts"]
        self.store = fixture["store"]
        self.before_birth = fixture["before_birth"]
        self.ownership = fixture["ownership"]
        self.observations = fixture["observations"]
        self.subject_identity = fixture["subject_identity"]
        self.construction = fixture["construction"]
        self.birth_change = self.construction.transaction.changes[0]

    def propose(self, **kwargs):
        return RepresentationCertificationAdapter().propose(
            AdapterRequest.from_store(self.store, self.store.head, ("document",), **kwargs),
            self.artifacts,
            witnesses=collect_witnesses(self.store, self.store.head),
        )

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def admitted(self):
        return admitted_associations(
            self.store.head, collect_witnesses(self.store, self.store.head), self.artifacts
        )

    @staticmethod
    def changed(proposal, changes):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=tuple(changes)),
            required_artifact_ids=tuple(
                dict.fromkeys(ref["id"] for c in changes for ref in getattr(c, "references", ()))
            ),
        )

    def rejected(self, action, pattern=None, *, errors=None):
        before = copy.deepcopy(self.store)
        errors = errors or (
            ValueError,
            ProposalArtifactError,
            ProposalConflictError,
            ProposalPolicyError,
        )
        context = self.assertRaisesRegex(errors, pattern) if pattern else self.assertRaises(errors)
        with context:
            action()
        self.assertEqual(self.store, before)
        self.assertEqual(self.store.head, before.head)
        self.assertEqual(len(self.store.revisions), len(before.revisions))
        self.assertEqual(self.store.get_document(self.store.head), before.get_document(before.head))
        self.assertEqual(
            self.store.get_document(self.store.head)["references"],
            before.get_document(before.head)["references"],
        )

    def mutate(self, callback):
        self.store.commit(
            self.store.head,
            Transaction("transaction:certification-test-fixture", (FixtureMutation(callback),)),
        )

    def tampered_output(self, proposal, callback):
        change = proposal.transaction.changes[0]
        original = self.artifacts.resolve_reference(change.association_reference)
        payload = json.loads(original.content)
        callback(payload)
        changed = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        ).document_reference()
        return self.changed(proposal, (replace(change, association_reference=changed),))

    def install_counterfeit_admission(self, payload):
        """Damage trusted history deliberately; never cross Adapter acceptance."""
        base = self.store.head
        payload = copy.deepcopy(payload)
        payload["base"] = {
            "revision_id": base,
            "document_hash": self.store.revisions[base].document_hash,
        }
        ref = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"profile_identity": PROFILE},
        ).document_reference()
        transaction = Transaction(
            "transaction:counterfeit-certification-fixture", (AppendReferencesChange((ref,)),)
        )
        document = transaction.apply(self.store.get_document(base))
        event = AdmissionEvent(
            CERT_CONTRACT,
            CERT_CHANGE,
            CERT_AUTHORITY,
            base,
            ref,
            transition_hash(document, (base,), transaction.transaction_id, transaction.message),
        )
        self.store._commit_verified(base, transaction, document, (event,))
        authenticate_witnesses(self.store.head, collect_witnesses(self.store, self.store.head))
        return ref

    def test_golden_preview_atomic_acceptance_and_unchanged_representation(self):
        before = copy.deepcopy(self.store)
        proposal = self.propose()
        self.assertEqual(proposal, self.propose())
        self.assertEqual(before, self.store)
        candidate = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(before, self.store)
        change = proposal.transaction.changes[0]
        self.assertIs(type(change), CertifyArtworkRepresentationChange)
        self.assertEqual(change.profile_identity, PROFILE)
        self.assertEqual(MEDIA, CERT_MEDIA)
        self.assertEqual(
            set(resolve_transaction_intents(proposal.transaction)),
            {("certify_representation", "document", None), ("attach_analysis", "document", None)},
        )
        payload = json.loads(self.artifacts.resolve_reference(change.association_reference).content)
        self.assertEqual(payload["schema_version"], SCHEMA)
        self.assertEqual(payload["proof_mode"], "PRESENT_TIME_CERTIFICATION@0.1")
        self.assertEqual(payload["construction_birth"]["proof_kind"], "STRUCTURAL_CONFORMITY_ONLY")
        self.assertEqual(
            payload["association"],
            {
                "subject_id": payload["subject_identity"]["subject_observation_evidence"][
                    "subject"
                ]["subject_id"],
                "temporal_identity_id": WHOLE_IDENTITY,
                "group_id": GROUP_ID,
            },
        )
        birth_receipt_ref = self.birth_change.references[-1]
        birth_receipt_bytes = self.artifacts.resolve_reference(birth_receipt_ref).content
        self.assertIsNone(json.loads(birth_receipt_bytes)["representation_claim"])
        revision = self.accept(proposal)
        self.assertIs(type(revision), AdmittedRevision)
        self.assertEqual(candidate, self.store.get_document(self.store.head))
        after = self.store.get_document(self.store.head)
        prior = before.get_document(before.head)
        for key in set(prior) | set(after):
            if key != "references":
                self.assertEqual(prior.get(key), after.get(key), key)
        self.assertEqual(after["references"][:-1], prior["references"])
        self.assertEqual(after["references"][-1], change.association_reference)
        self.assertEqual(
            self.artifacts.resolve_reference(birth_receipt_ref).content, birth_receipt_bytes
        )
        self.assertEqual(render(prior), render(after))
        self.assertEqual(
            render(after).encode(),
            (ROOT / "examples/044-video-artwork-construction/group.svg").read_bytes(),
        )
        (event,) = revision.admissions
        self.assertEqual(
            (event.contract, event.change_identity, event.authority_identity),
            (CERT_CONTRACT, CERT_CHANGE, CERT_AUTHORITY),
        )
        self.assertEqual(event.base_revision_id, before.head)
        self.assertEqual(event.artifact_reference, change.association_reference)
        self.assertEqual(
            event.transition_hash,
            transition_hash(after, revision.parent_ids, revision.transaction_id, revision.message),
        )
        self.assertNotEqual(event.transition_hash, revision.revision_id)
        self.assertEqual(self.admitted(), (change.association_reference,))

    def test_measured_golden_and_trusted_history_roundtrip(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        revision = self.accept(proposal)
        payload = self.artifacts.resolve_reference(change.association_reference).content
        expected = json.loads((GOLDEN / "golden.json").read_text())
        self.assertEqual(change.association_reference["id"], ASSOCIATION_ID)
        self.assertEqual(revision.revision_id, CERTIFICATION_REVISION)
        self.assertEqual(revision.document_hash, CERTIFICATION_DOCUMENT)
        self.assertEqual(revision.admissions[0].transition_hash, CERTIFICATION_TRANSITION)
        self.assertEqual(len(payload), 18289)
        self.assertEqual(expected["association_artifact_id"], change.association_reference["id"])
        self.assertEqual(expected["certification_revision_id"], revision.revision_id)
        self.assertEqual(expected["certification_document_hash"], revision.document_hash)
        self.assertEqual(expected["temporal_identity_id"], WHOLE_IDENTITY)
        self.assertEqual(expected["group_id"], GROUP_ID)
        self.assertEqual(expected["admission"], asdict(revision.admissions[0]))
        self.assertEqual(payload, (GOLDEN / "certification.json").read_bytes())
        self.assertEqual(
            json.loads((GOLDEN / "accepted.svm.json").read_bytes()),
            self.store.get_document(self.store.head),
        )
        snapshot = dump_trusted_history(self.store)
        digest = history_digest(snapshot)
        self.assertEqual(digest, expected["trusted_history_digest"])
        restored = load_trusted_history(
            json.loads(json.dumps(snapshot)), trusted_history_hash=digest
        )
        self.assertEqual(restored.head, self.store.head)
        self.assertEqual(dump_trusted_history(restored), snapshot)
        self.assertEqual(
            admitted_associations(
                restored.head, collect_witnesses(restored, restored.head), self.artifacts
            ),
            (change.association_reference,),
        )

    def test_exact_repeat_is_idempotent_without_new_admission(self):
        original = self.propose()
        ref = original.transaction.changes[0].association_reference
        self.accept(original)
        repeated = self.propose()
        self.assertEqual(repeated.transaction.changes[0].association_reference, ref)
        before = self.store.get_document(self.store.head)
        revision = self.accept(repeated)
        self.assertFalse(getattr(revision, "admissions", ()))
        self.assertEqual(before, self.store.get_document(self.store.head))
        self.assertEqual(self.admitted(), (ref,))

    def test_generic_all_reference_paths_cannot_issue_admission(self):
        proposal = self.propose()
        ref = proposal.transaction.changes[0].association_reference
        document = self.store.get_document(self.store.head)
        fragment = self.birth_change.fragment
        paths = (
            AppendReferencesChange((ref,)),
            AppendSceneFragmentChange((), (), (), (), (), (ref,)),
            ReplaceSceneFragmentChange(
                tuple(e["id"] for e in fragment.entities),
                tuple(o["id"] for o in fragment.operations),
                fragment.entities,
                fragment.operations,
                fragment.output_bindings,
                fragment.render_entries,
                fragment.styles,
                (ref,),
            ),
        )
        for change in paths:
            with self.subTest(path=type(change).__name__):
                # The mutation is valid; failure must be the reserved admission boundary.
                Transaction("transaction:valid-generic-control", (change,)).apply(document)
                self.rejected(
                    lambda change=change: self.accept(self.changed(proposal, (change,))),
                    "CERTIFICATION_ADMISSION_REQUIRED",
                    errors=ProposalArtifactError,
                )

    def test_hidden_actual_addition_cannot_bypass_declared_reference_check(self):
        proposal = self.propose()
        ref = proposal.transaction.changes[0].association_reference
        generic = AppendSceneFragmentChange((), (), (), (), ())

        def append_actual(change, document):
            document["references"].append(copy.deepcopy(ref))

        with patch.object(AppendSceneFragmentChange, "apply", append_actual):
            self.rejected(
                lambda: self.accept(self.changed(proposal, (generic,))),
                "CERTIFICATION_ADMISSION_REQUIRED",
                errors=ProposalArtifactError,
            )

    def test_hidden_in_place_reserved_descriptor_replacement_rejects(self):
        proposal = self.propose()
        certificate = proposal.transaction.changes[0].association_reference
        self.accept(proposal)
        document = self.store.get_document(self.store.head)
        generic = AppendSceneFragmentChange((), (), (), (), ())
        ordinary = self.changed(replace(proposal, base_revision_id=self.store.head), (generic,))
        ownership = self.ownership.transaction.changes[0].evidence_reference
        for reference, prefix in (
            (ownership, "SPEC76_ADMISSION_REQUIRED"),
            (certificate, "CERTIFICATION_ADMISSION_REQUIRED"),
        ):
            for field in ("uri", "provenance"):
                with self.subTest(media_type=reference["media_type"], field=field):

                    def replace_actual(change, candidate, *, reference=reference, field=field):
                        actual = next(
                            r for r in candidate["references"] if r["id"] == reference["id"]
                        )
                        if field == "uri":
                            actual["uri"] = "artifact:caller-in-place-locator"
                        else:
                            actual["import_metadata"]["provenance"]["caller_assertion"] = (
                                "authority"
                            )

                    with patch.object(AppendSceneFragmentChange, "apply", replace_actual):
                        control = Transaction(
                            "transaction:valid-replacement-control", (generic,)
                        ).apply(document)
                        changed = next(
                            r for r in control["references"] if r["id"] == reference["id"]
                        )
                        self.assertEqual(changed["id"], reference["id"])
                        self.assertEqual(changed["content_hash"], reference["content_hash"])
                        if field == "uri":
                            self.assertEqual(changed["uri"], "artifact:caller-in-place-locator")
                        else:
                            self.assertEqual(
                                changed["import_metadata"]["provenance"]["caller_assertion"],
                                "authority",
                            )
                        self.assertNotEqual(changed, reference)
                        self.rejected(
                            lambda: self.accept(ordinary),
                            prefix + ": reserved reference replacement",
                            errors=ProposalArtifactError,
                        )

    def test_mixed_and_duplicate_changes_cannot_launder_admission(self):
        proposal = self.propose()
        dedicated = proposal.transaction.changes[0]
        generic = AppendReferencesChange((dedicated.association_reference,))
        for changes in ((generic, dedicated), (dedicated, generic), (dedicated, dedicated)):
            with self.subTest(order=[type(c).__name__ for c in changes]):
                self.rejected(
                    lambda changes=changes: self.accept(self.changed(proposal, changes)),
                    "CERTIFICATION_ADMISSION_REQUIRED",
                    errors=ProposalArtifactError,
                )

    def test_plain_commit_canonical_bytes_are_not_an_admitted_association(self):
        proposal = self.propose()
        reference = proposal.transaction.changes[0].association_reference
        revision = self.store.commit(self.store.head, proposal.transaction)
        self.assertFalse(getattr(revision, "admissions", ()))
        self.assertIn(reference, self.store.get_document(self.store.head)["references"])
        self.assertEqual(self.admitted(), ())

    def test_indistinguishable_low_level_birth_is_certifiable_now(self):
        legitimate = copy.deepcopy(self.store)
        self.store = copy.deepcopy(self.before_birth)
        import svm.adapters.video_artwork_construction as construction_module

        with patch.object(
            construction_module, "verify_change", side_effect=AssertionError("must not run")
        ) as verifier:
            born = self.store.commit(self.store.head, self.construction.transaction)
        self.assertEqual(verifier.call_count, 0)
        self.assertEqual(born, legitimate.revisions[legitimate.head])
        self.assertEqual(dump_trusted_history(self.store), dump_trusted_history(legitimate))
        proposal = self.propose()
        record = json.loads(
            self.artifacts.resolve_reference(
                proposal.transaction.changes[0].association_reference
            ).content
        )
        self.assertEqual(record["construction_birth"]["proof_kind"], "STRUCTURAL_CONFORMITY_ONLY")
        self.assertNotIn("verified_change", record["construction_birth"])
        self.assertNotIn("verifier_executed", record["construction_birth"])
        self.accept(proposal)
        self.assertEqual(len(self.admitted()), 1)

    def test_exact_registered_change_type_required(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]

        class UnregisteredCertification(CertifyArtworkRepresentationChange):
            pass

        forged = UnregisteredCertification(
            **{key: getattr(change, key) for key in change.__dataclass_fields__}
        )
        self.rejected(
            lambda: self.accept(self.changed(proposal, (forged,))),
            "Unregistered Change",
            errors=ProposalPolicyError,
        )

    def test_no_caller_selected_identity_group_source_or_membership(self):
        for options in (
            {"group_id": GROUP_ID},
            {"temporal_identity_id": WHOLE_IDENTITY},
            {"parts": ["part-a"]},
            {"claim_ids": []},
        ):
            with self.subTest(options=options):
                self.rejected(lambda options=options: self.propose(options=options))
        self.rejected(lambda: self.propose(artifact_ids=(self.birth_change.references[-1]["id"],)))

    def test_every_transport_reference_is_independently_required(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        accepted = self.store.get_document(self.store.head)["references"]
        self.assertEqual(change.source_references, tuple(sorted(accepted, key=lambda r: r["id"])))
        for omitted in change.source_references:
            with self.subTest(omitted=omitted["id"]):
                forged = replace(
                    change,
                    source_references=tuple(r for r in change.source_references if r != omitted),
                )
                self.rejected(lambda forged=forged: self.accept(self.changed(proposal, (forged,))))

    def test_transport_duplicates_order_and_descriptor_forgery_reject(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        altered = copy.deepcopy(change.source_references[0])
        altered["locator"] = "caller:invented"
        variants = (
            tuple(reversed(change.source_references)),
            (*change.source_references, change.source_references[0]),
            (altered, *change.source_references[1:]),
        )
        for refs in variants:
            with self.subTest(refs=refs[0]["id"]):
                self.rejected(
                    lambda refs=refs: self.accept(
                        self.changed(proposal, (replace(change, source_references=refs),))
                    )
                )

    def test_missing_witnesses_and_forged_base_reject(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        birth_base = self.construction.base_revision_id
        variants = (
            replace(change, witnesses=()),
            replace(
                change,
                witnesses=tuple(
                    w for w in change.witnesses if w.revision.revision_id != birth_base
                ),
            ),
            replace(change, source_revision_id="revision:" + "0" * 64),
            replace(change, base_document_snapshot={}),
        )
        for forged in variants:
            with self.subTest(witness_count=len(forged.witnesses)):
                self.rejected(lambda forged=forged: self.accept(self.changed(proposal, (forged,))))

    def test_forged_history_commitment_rejects(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        witness = change.witnesses[-1]
        bad = replace(witness, revision=replace(witness.revision, message="caller:rewritten"))
        forged = replace(change, witnesses=(*change.witnesses[:-1], bad))
        self.rejected(lambda: self.accept(self.changed(proposal, (forged,))))

    def test_forged_birth_post_state_cannot_pass_structural_replay(self):
        old = self.store.revisions[self.store.head]
        document = self.store.get_document(self.store.head)
        document["presentation"]["styles"][0]["fill"] = "#FFFFFF"
        changed = self.store._make_revision(
            document, old.parent_ids, old.transaction_id, old.message
        )
        del self.store.revisions[old.revision_id]
        del self.store._documents[old.revision_id]
        self.store.revisions[changed.revision_id] = changed
        self.store._documents[changed.revision_id] = document
        self.store.head = changed.revision_id
        # Its hash-consistent origin chain is real test data; it is not the F0 recipe result.
        authenticate_witnesses(self.store.head, collect_witnesses(self.store, self.store.head))
        self.rejected(
            self.propose,
            "Complete construction birth post-Document does not independently reproduce",
            errors=RepresentationCertificationError,
        )

    def test_arbitrary_group_is_not_the_replayed_f0_representation(self):
        self.mutate(lambda d: d["groups"][0].update(id="group:" + "a" * 64))
        self.rejected(
            self.propose,
            "Exactly one source-derived eligible artwork Group is required",
            errors=RepresentationCertificationError,
        )

    def test_structural_and_ordinary_representation_edits_are_inapplicable(self):
        original = copy.deepcopy(self.store)
        mutations = (
            lambda d: d["groups"][0]["members"].reverse(),
            lambda d: d["groups"][0]["transform"]["translate"].__setitem__(0, 1),
            lambda d: d["presentation"]["styles"][0].update(fill="#FFFFFF"),
            lambda d: d["presentation"]["render_stack"].reverse(),
            lambda d: d["construction"]["operations"][0]["parameters"].update(
                d="M 21 20 L 100 20 L 20 80 Z"
            ),
            lambda d: d["groups"][0]["provenance"].update(
                profile_identity="svm-svg-two-part-group-construction@0.1"
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                self.store = copy.deepcopy(original)
                if mutate is mutations[0]:
                    # Use a legal changed member set, not an invalid sorted-order error.
                    def replacement(d):
                        entity = copy.deepcopy(d["entities"][0])
                        entity["id"] = "entity:replacement"
                        d["entities"].append(entity)
                        d["groups"][0]["members"] = sorted(
                            [entity["id"], d["groups"][0]["members"][1]]
                        )

                    self.mutate(replacement)
                else:
                    self.mutate(mutate)
                self.rejected(self.propose)

    def test_current_edit_invalidates_previously_admitted_certificate(self):
        proposal = self.propose()
        self.accept(proposal)
        original = copy.deepcopy(self.store)
        document = self.store.get_document(self.store.head)
        group = document["groups"][0]
        transform = copy.deepcopy(group["transform"])
        transform["translate"][0] = 1
        edits = (
            SetGroupTransformChange(group["id"], transform),
            SetOperationParameterChange(
                self.birth_change.fragment.operations[0]["id"],
                "d",
                "M 21 20 L 100 20 L 20 80 Z",
            ),
        )
        for edit in edits:
            with self.subTest(edit=type(edit).__name__):
                self.store = copy.deepcopy(original)
                ordinary = self.changed(
                    replace(proposal, base_revision_id=self.store.head), (edit,)
                )
                self.accept(ordinary)
                after = self.store.get_document(self.store.head)
                for collection in ("entities", "groups", "temporal_identities"):
                    self.assertEqual(
                        [item["id"] for item in after[collection]],
                        [item["id"] for item in document[collection]],
                    )
                self.assertEqual(after["groups"][0]["id"], GROUP_ID)
                self.assertIn(WHOLE_IDENTITY, [item["id"] for item in after["temporal_identities"]])
                self.rejected(
                    self.admitted,
                    "continuity changed",
                    errors=RepresentationCertificationError,
                )
                self.rejected(
                    self.propose,
                    "continuity changed",
                    errors=RepresentationCertificationError,
                )

    def test_temporary_dependency_removal_restoration_is_not_hidden(self):
        original = copy.deepcopy(self.store)
        stage1 = self.observations.transaction.changes[0].evidence_reference
        record = json.loads(
            self.artifacts.resolve_reference(
                self.ownership.transaction.changes[0].evidence_reference
            ).content
        )
        video = next(
            r
            for r in self.store.get_document(self.store.head)["references"]
            if r["id"] == record["video"]["artifact_id"]
        )
        for reference in (stage1, video):
            self.store = copy.deepcopy(original)
            self.mutate(
                lambda d, reference=reference: d.update(
                    references=[r for r in d["references"] if r["id"] != reference["id"]]
                )
            )
            self.store.commit(
                self.store.head,
                Transaction(
                    "transaction:restore-exact-proof-resource",
                    (AppendReferencesChange((reference,)),),
                ),
            )
            self.assertIn(reference, self.store.get_document(self.store.head)["references"])
            self.rejected(self.propose, "dependency descriptor continuity changed")

    def test_relevant_sampled_track_is_inapplicable_without_mutating_identity(self):
        before = self.store.get_document(self.store.head)
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:legal-existing-group-track",
                (
                    CreateGroupTransformTrackChange(
                        "track:certification-control", GROUP_ID, "translate.x", 12
                    ),
                    AddKeyframeChange(
                        "track:certification-control", "keyframe:certification-control", 0, 0
                    ),
                ),
            ),
        )
        after = self.store.get_document(self.store.head)
        self.assertEqual(before["groups"], after["groups"])
        self.assertEqual(before["temporal_identities"], after["temporal_identities"])
        self.rejected(self.propose, "sampled representation Track")

    def test_existing_explicit_s1_binding_remains_authoritative_and_excluded(self):
        binding = TemporalMotionTargetBindingAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                options={"temporal_identity_id": WHOLE_IDENTITY, "group_id": GROUP_ID},
            ),
            self.artifacts,
        )
        self.accept(binding)
        before = copy.deepcopy(self.store.get_document(self.store.head)["motion_target_bindings"])
        self.rejected(self.propose, "bound|binding|Binding")
        self.assertEqual(before, self.store.get_document(self.store.head)["motion_target_bindings"])

    def test_incomplete_and_forged_whole_identity_reject(self):
        original = copy.deepcopy(self.store)
        for mode in ("binding", "identity", "provenance"):
            self.store = copy.deepcopy(original)

            def mutate(document, mode=mode):
                whole = next(
                    t for t in document["temporal_identities"] if t["id"] == WHOLE_IDENTITY
                )
                if mode == "binding":
                    whole["bindings"][0]["observation_id"] = "observation:caller"
                elif mode == "identity":
                    whole["id"] = "temporal-identity:" + "b" * 64
                    document["temporal_identities"].sort(key=lambda t: t["id"])
                else:
                    whole["provenance"][0]["candidate_id"] = "candidate:correspondence:" + "c" * 64

            self.mutate(mutate)
            self.rejected(self.propose)

    def test_missing_birth_receipt_or_ownership_reference_reject(self):
        original = copy.deepcopy(self.store)
        refs = (
            self.birth_change.references[-1],
            self.ownership.transaction.changes[0].evidence_reference,
        )
        for ref in refs:
            self.store = copy.deepcopy(original)
            self.mutate(
                lambda d, ref=ref: d.update(
                    references=[r for r in d["references"] if r["id"] != ref["id"]]
                )
            )
            self.rejected(self.propose)

    def test_missing_accepted_identity_companion_rejects(self):
        reference = self.subject_identity.transaction.changes[0].evidence_reference
        self.mutate(
            lambda d: d.update(
                references=[r for r in d["references"] if r["id"] != reference["id"]]
            )
        )
        self.rejected(self.propose, "identity companion")

    def test_invalid_unsupported_r0_cannot_certify_the_whole_identity(self):
        definition = next(
            t
            for t in self.store.get_document(self.store.head)["temporal_identities"]
            if t["id"] == WHOLE_IDENTITY
        )
        old_id = definition["provenance"][0]["evidence_artifact_id"]
        old_ref = next(
            r for r in self.store.get_document(self.store.head)["references"] if r["id"] == old_id
        )
        snapshot = self.artifacts.resolve_reference(old_ref)
        payload = json.loads(snapshot.content)
        payload["candidates"][0]["status"] = "UNCERTAIN"
        new_ref = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=snapshot.media_type,
            kind=snapshot.kind,
            provenance=snapshot.provenance,
        ).document_reference()

        def mutate(document):
            document["references"] = [r for r in document["references"] if r["id"] != old_id] + [
                new_ref
            ]
            whole = next(t for t in document["temporal_identities"] if t["id"] == WHOLE_IDENTITY)
            whole["provenance"][0]["evidence_artifact_id"] = new_ref["id"]

        self.mutate(mutate)
        self.rejected(self.propose, "R0|identity|TemporalIdentity|reproduce")

    def test_already_admitted_claim_cannot_be_omitted_from_transport(self):
        first = self.propose()
        reference = first.transaction.changes[0].association_reference
        self.accept(first)
        repeated = self.propose()
        change = repeated.transaction.changes[0]
        forged = replace(
            change,
            source_references=tuple(
                r for r in change.source_references if r["id"] != reference["id"]
            ),
        )
        self.rejected(
            lambda: self.accept(self.changed(repeated, (forged,))),
            "complete base reference universe",
        )

    def test_output_source_part_occurrence_membership_and_universe_tampering_reject(self):
        proposal = self.propose()
        mutations = (
            lambda p: p["association"].update(group_id="group:" + "0" * 64),
            lambda p: p["association"].update(temporal_identity_id="temporal-identity:" + "0" * 64),
            lambda p: p["construction_birth"].update(proof_kind="DEDICATED_VERIFIER_EXECUTED"),
            lambda p: p["construction_birth"].update(post_revision_id="revision:" + "0" * 64),
            lambda p: p["subject_identity"]["subject_observation_evidence"]["parts"].pop(),
            lambda p: p["subject_identity"]["subject_observation_evidence"]["membership"].pop(),
            lambda p: p["subject_identity"]["subject_observation_evidence"]["membership"][0].update(
                observation_id="observation:caller"
            ),
            lambda p: p["subject_identity"]["subject_observation_evidence"]["occurrences"][
                0
            ].update(tick=1),
            lambda p: p["subject_identity"]["subject_observation_evidence"]["subject"].update(
                ownership_root_artifact_id="artifact:" + "0" * 64
            ),
            lambda p: p["universe"]["temporal_identities"].pop(),
            lambda p: p["universe"]["groups"].clear(),
            lambda p: p["representation"]["entities"].pop(),
            lambda p: p.update(caller_claim="verified"),
        )
        for mutation in mutations:
            with self.subTest(index=mutations.index(mutation)):
                self.rejected(
                    lambda mutation=mutation: self.accept(self.tampered_output(proposal, mutation)),
                    "independently reproduce",
                    errors=ProposalArtifactError,
                )

    def test_counterfeit_competing_claim_with_synthetic_event_is_not_hidden(self):
        original = self.propose()
        payload = json.loads(
            self.artifacts.resolve_reference(
                original.transaction.changes[0].association_reference
            ).content
        )
        payload["association"]["group_id"] = "group:" + "d" * 64
        ref = self.install_counterfeit_admission(payload)
        self.assertIn(ref, self.store.get_document(self.store.head)["references"])
        self.rejected(
            self.propose,
            "admitted association does not reproduce",
            errors=RepresentationCertificationError,
        )
        self.rejected(
            self.admitted,
            "admitted association does not reproduce",
            errors=RepresentationCertificationError,
        )

    def test_duplicate_equivalent_admitted_claims_are_not_hidden(self):
        proposal = self.propose()
        first = proposal.transaction.changes[0].association_reference
        payload = json.loads(self.artifacts.resolve_reference(first).content)
        self.accept(proposal)
        payload["universe"]["association_references"] = [first]
        second = self.install_counterfeit_admission(payload)
        self.assertNotEqual(first["id"], second["id"])
        self.assertIn(first, self.store.get_document(self.store.head)["references"])
        self.assertIn(second, self.store.get_document(self.store.head)["references"])
        for consume in (self.admitted, self.propose):
            self.rejected(
                consume,
                "Duplicate equivalent admitted representation claims",
                errors=RepresentationCertificationError,
            )

    def test_missing_or_forged_certification_admission_history_rejects(self):
        self.accept(self.propose())
        revision = self.store.revisions[self.store.head]
        event = revision.admissions[0]
        for forged in (
            replace(revision, admissions=()),
            replace(revision, admissions=(replace(event, authority_identity="caller:authority"),)),
            replace(revision, admissions=(replace(event, transition_hash="revision:" + "0" * 64),)),
        ):
            witnesses = list(collect_witnesses(self.store, self.store.head))
            witnesses = [
                replace(w, revision=forged) if w.revision.revision_id == revision.revision_id else w
                for w in witnesses
            ]
            with self.subTest(event=getattr(forged, "admissions", ())):
                self.rejected(
                    lambda witnesses=witnesses: admitted_associations(
                        self.store.head, tuple(witnesses), self.artifacts
                    )
                )

    def test_recomputed_certification_events_cannot_authenticate_extra_final_mutation(self):
        proposal = self.propose()
        reference = proposal.transaction.changes[0].association_reference
        ordinary = self.artifacts.import_bytes(
            b"extra mutation", media_type="text/plain"
        ).document_reference()
        base = self.store.head
        transaction = Transaction(
            "transaction:damaged-certification-post",
            (AppendReferencesChange((reference, ordinary)),),
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
        self.rejected(
            lambda: authenticate_witnesses(
                self.store.head, collect_witnesses(self.store, self.store.head)
            ),
            "Certification transition must only append",
        )

    def test_mixed_family_and_unknown_admission_events_reject(self):
        original = copy.deepcopy(self.store)
        proposal = self.propose()
        reference = proposal.transaction.changes[0].association_reference
        ownership = self.artifacts.import_bytes(
            b"damaged ownership fixture",
            media_type=OWNERSHIP_MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={},
        ).document_reference()
        for mode in ("mixed", "unknown"):
            self.store = copy.deepcopy(original)
            base = self.store.head
            refs = (reference, ownership) if mode == "mixed" else (reference,)
            transaction = Transaction(
                "transaction:damaged-mixed-events", (AppendReferencesChange(refs),)
            )
            document = transaction.apply(self.store.get_document(base))
            commitment = transition_hash(
                document, (base,), transaction.transaction_id, transaction.message
            )
            cert = AdmissionEvent(
                CERT_CONTRACT, CERT_CHANGE, CERT_AUTHORITY, base, reference, commitment
            )
            events = (
                (
                    cert,
                    AdmissionEvent(
                        OWNERSHIP_CONTRACT,
                        OWNERSHIP_CHANGE,
                        OWNERSHIP_AUTHORITY,
                        base,
                        ownership,
                        commitment,
                    ),
                )
                if mode == "mixed"
                else (replace(cert, contract="caller:unknown-contract"),)
            )
            self.store._commit_verified(base, transaction, document, events)
            self.rejected(
                lambda: authenticate_witnesses(
                    self.store.head, collect_witnesses(self.store, self.store.head)
                ),
                "exactly one admission event|Invalid admission",
            )

    def test_missing_and_forged_spec76_admission_witnesses_reject(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        ownership_id = next(
            w.revision.revision_id
            for w in change.witnesses
            if getattr(w.revision, "admissions", ())
        )
        original = next(w for w in change.witnesses if w.revision.revision_id == ownership_id)
        event = original.revision.admissions[0]
        for event_change in (None, replace(event, authority_identity="caller:ownership")):
            forged = replace(
                original.revision, admissions=() if event_change is None else (event_change,)
            )
            witnesses = tuple(
                replace(w, revision=forged) if w == original else w for w in change.witnesses
            )
            self.rejected(
                lambda witnesses=witnesses: self.accept(
                    self.changed(proposal, (replace(change, witnesses=witnesses),))
                )
            )

    def test_policy_denial_stale_base_and_atomic_multi_change_rollback(self):
        original = copy.deepcopy(self.store)
        for action in ("certify_representation", "attach_analysis"):
            self.store = copy.deepcopy(original)
            self.mutate(
                lambda d, action=action: d["edit_permissions"].append(
                    {
                        "id": "permission:no-certification",
                        "actor": "*",
                        "effect": "deny",
                        "actions": [action],
                        "targets": ["document"],
                    }
                )
            )
            proposal = self.propose()
            self.rejected(
                lambda proposal=proposal: self.accept(proposal), errors=ProposalPolicyError
            )
        self.store = copy.deepcopy(original)
        stale = self.propose()
        ordinary = self.artifacts.import_bytes(
            b"ordinary", media_type="text/plain"
        ).document_reference()
        self.store.commit(
            self.store.head,
            Transaction("transaction:ordinary", (AppendReferencesChange((ordinary,)),)),
        )
        self.rejected(lambda: self.accept(stale), errors=ProposalConflictError)
        self.store = copy.deepcopy(original)
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        document = self.store.get_document(self.store.head)
        transform = copy.deepcopy(document["groups"][0]["transform"])
        transform["translate"][0] = 1
        valid_edit = SetGroupTransformChange(GROUP_ID, transform)
        control = Transaction("transaction:valid-ordinary-edit", (valid_edit,)).apply(document)
        self.assertEqual(control["groups"][0]["transform"], transform)
        ordinary_attachment = AppendReferencesChange((ordinary,))
        for mutation in (valid_edit, ordinary_attachment):
            for changes in ((mutation, change), (change, mutation)):
                with self.subTest(
                    mutation=type(mutation).__name__, certification_first=changes[0] is change
                ):
                    self.rejected(
                        lambda changes=changes: self.accept(self.changed(proposal, changes)),
                        "CERTIFICATION_ADMISSION_REQUIRED",
                        errors=ProposalArtifactError,
                    )

    def test_ordinary_attachment_and_existing_golden_outputs_still_work(self):
        proposal = self.propose()
        ordinary = self.artifacts.import_bytes(
            b"ordinary reference", media_type="text/plain"
        ).document_reference()
        revision = self.accept(self.changed(proposal, (AppendReferencesChange((ordinary,)),)))
        self.assertFalse(getattr(revision, "admissions", ()))
        self.assertEqual(self.admitted(), ())
        self.assertEqual(
            render(self.store.get_document(self.store.head)).encode(),
            (ROOT / "examples/044-video-artwork-construction/group.svg").read_bytes(),
        )
