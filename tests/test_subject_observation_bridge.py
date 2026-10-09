import copy
import json
import unittest
from dataclasses import fields, replace
from pathlib import Path
from unittest.mock import patch

from test_authored_raster_production import pipeline

from svm import AdapterRequest, ProposalAcceptor, RevisionStore, Transaction
from svm.adapters.multipart_subject_evidence import (
    MEDIA as OWNERSHIP_MEDIA,
)
from svm.adapters.multipart_subject_evidence import (
    PROFILE as OWNERSHIP_PROFILE,
)
from svm.adapters.multipart_subject_evidence import MultipartSubjectEvidenceAdapter, claim_key
from svm.adapters.opencv_analysis import _opencv
from svm.adapters.subject_observation_bridge import (
    IDENTITY_MEDIA,
    MEDIA,
    PRIMITIVE_TYPE,
    PROFILE,
    SubjectIdentityBridgeAdapter,
    SubjectObservationAdapter,
)
from svm.adapters.temporal_correspondence import (
    OBSERVATION_MEDIA_TYPE,
    TemporalCorrespondenceAdapter,
    read_primitive_observations,
)
from svm.adapters.temporal_identity_promotion import TemporalIdentityPromotionAdapter
from svm.admission_history import AUTHORITY, CHANGE, CONTRACT, transition_hash
from svm.artifacts import ArtifactKind
from svm.change_authority import change_authority
from svm.evaluator import canonical_bytes
from svm.multipart_witness import authenticate_witnesses, collect_witnesses
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.revisions import (
    AdmissionEvent,
    AppendReferencesChange,
    AppendSceneFragmentChange,
    PromotedTemporalCorrespondence,
    PromoteTemporalIdentityChange,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples/045-subject-observation-bridge"
SUBJECT_ID = "subject:multipart:44fedac3c34e35fdb80d0aeca7167d09c758f276275a6034df14506276a6b4e3"
PART_IDENTITIES = (
    "temporal-identity:964b93c149d1f2baf83c1c33d8783355587a351de102ea95677af82359db5847",
    "temporal-identity:c66886096e185b7b0e97496d2c8587c8683f69f238f475b531ab6f5e054c0ff8",
)
PART_OBSERVATIONS = (
    "observation:p2b:17e63705aaa4f65e45cc38fd4055211b9583d2a931a1c35c6c0e8e8bb83df4e3",
    "observation:p2b:5d8d144cf963589e1254fc9f68115aedbfeecc997605c50b572b1a1e913d5c32",
    "observation:p2b:47df01148a871b1b70fcccdcf95f1a2a405ec17b085575b4c34f86b13463df94",
    "observation:p2b:2193ee92325aabc1830334c6ae35e81f931327b1ef766bd348c9e79caa5b0825",
)
SUBJECT_OBSERVATIONS = (
    "observation:subject:41f34347845507a4517821e13ca7c6f0f801a9cf562c1e74aa9f451f05c60d07",
    "observation:subject:bd2818774750fbe166b7f04d220fb6aa1ef0d5f0eb094c1cf82d1c903f66412d",
)
OBSERVATION_ARTIFACT = "artifact:44375ca66b694b68d2e0374e6b29ca2885b5e11eaa4a7eecdd3f3ef8cb0d11e2"
OBSERVATION_PROOF = "artifact:5528daf887863233d927249280ded75c4a09030f449b585dc369e682ca00221b"
OBSERVATION_REVISION = "revision:0560a730343c401e829fe1f3da7b31705534fdf785d2d215ac8a75bdd331a1b9"
OBSERVATION_DOCUMENT_HASH = (
    "sha256:2f2095402fbf88c49a2a96e1c305a82b77706d974bd554aa27fef44c5ad51434"
)
R0_ARTIFACT = "artifact:041ee965772aa0bae3e091717fd65c3a91e358f5af3c1d385e93ff9f6375c238"
R0_CANDIDATE = (
    "candidate:correspondence:f718540035f31b705d8135f1c4082624753f2953689e3841dcb2155431caeb13"
)
R0_INFERENCE = (
    "inference:correspondence:e928ef086b4e8c2f83a1b34e00159dda30ed6fc7878d7d333de4680bb8e142d6"
)
IDENTITY_PROOF = "artifact:0ce77b99e1b4cc94e2d2b60178c8ea895f4739145f90bbd49a95f4a4d66c58ab"
WHOLE_IDENTITY = (
    "temporal-identity:f89cc670dc7d6d8f54dd519532d525346817425825949ded13a79daae45aacbf"
)
FINAL_REVISION = "revision:4865787b0ed71cc93bc279f51db91ff03e272995deb06833c71f35fa20b63626"
FINAL_DOCUMENT_HASH = "sha256:4385b492db86378568a299e14b3ece562e8c1338a216cd22c1619dd0bc03948c"


class FixtureMutation:
    """Trusted test setup only; never registered for Adapter acceptance."""

    def __init__(self, mutate):
        self.mutate = mutate

    def apply(self, document):
        self.mutate(document)


class SubjectObservationBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        artifacts, store, _, produced, _, ids, _ = pipeline()
        cls.production = produced
        cls.before_admission = copy.deepcopy(store)
        ownership = MultipartSubjectEvidenceAdapter().propose(
            AdapterRequest.from_store(store, store.head, ("document",)),
            artifacts,
            witnesses=collect_witnesses(store, store.head),
        )
        ProposalAcceptor().accept(store, ownership, artifacts)
        cls.after_admission = copy.deepcopy(store)
        r0 = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(store, store.head, ("document",), artifact_ids=(ids[2],)),
            artifacts,
        )
        ProposalAcceptor().accept(store, r0, artifacts)
        r0_ref = r0.transaction.changes[0].references[0]
        candidates = json.loads(artifacts.resolve_reference(r0_ref).content)["candidates"]
        promoted = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(r0_ref["id"],),
                options={
                    "inference_ids": [
                        candidate["inference_id"]
                        for candidate in candidates
                        if candidate["status"] == "SUPPORTED"
                    ]
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, promoted, artifacts)
        cls.fixture = artifacts, store, ownership

    def setUp(self):
        self.artifacts, self.store, self.ownership = copy.deepcopy(self.fixture)
        self.ownership_ref = self.ownership.transaction.changes[0].evidence_reference
        self.ownership_record = json.loads(
            self.artifacts.resolve_reference(self.ownership_ref).content
        )

    def request(self, **kwargs):
        return AdapterRequest.from_store(self.store, self.store.head, ("document",), **kwargs)

    def observations(self, **kwargs):
        return SubjectObservationAdapter().propose(
            self.request(**kwargs),
            self.artifacts,
            witnesses=collect_witnesses(self.store, self.store.head),
        )

    def identity(self, **kwargs):
        return SubjectIdentityBridgeAdapter().propose(
            self.request(**kwargs),
            self.artifacts,
            witnesses=collect_witnesses(self.store, self.store.head),
        )

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    @staticmethod
    def reference(proposal, media):
        return next(
            r for r in proposal.transaction.changes[0].references if r["media_type"] == media
        )

    def accept_observations(self):
        proposal = self.observations()
        self.accept(proposal)
        return proposal, self.reference(proposal, OBSERVATION_MEDIA_TYPE)

    def accept_r0(self):
        observed, reference = self.accept_observations()
        r0 = TemporalCorrespondenceAdapter().propose(
            self.request(artifact_ids=(reference["id"],)), self.artifacts
        )
        self.accept(r0)
        return observed, reference, r0

    def changed(self, proposal, change):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(change,)),
            required_artifact_ids=tuple(dict.fromkeys(ref["id"] for ref in change.references)),
        )

    def rejected(self, action, pattern=None):
        before = copy.deepcopy(self.store)
        errors = (ValueError, ProposalArtifactError, ProposalConflictError, ProposalPolicyError)
        context = self.assertRaisesRegex(errors, pattern) if pattern else self.assertRaises(errors)
        with context:
            action()
        self.assertEqual(self.store, before)
        self.assertEqual(self.store.head, before.head)
        self.assertEqual(self.store.get_document(self.store.head), before.get_document(before.head))
        self.assertEqual(
            self.store.get_document(self.store.head)["references"],
            before.get_document(before.head)["references"],
        )

    def mutate_base(self, mutate):
        self.store.commit(
            self.store.head,
            Transaction("transaction:subject-bridge-fixture", (FixtureMutation(mutate),)),
        )

    def snapshot(self, original, payload):
        return self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )

    @staticmethod
    def substitute_reference(change, original, replacement):
        updates = {}
        for field in fields(change):
            value = getattr(change, field.name)
            if value == original:
                updates[field.name] = replacement
            elif field.name == "references":
                updates[field.name] = tuple(
                    replacement if ref == original else ref for ref in value
                )
        return replace(change, **updates)

    def damaged_claim(self, mutate):
        """Damage the trusted fixture; hashes alone do not substitute for replay."""
        self.store = copy.deepcopy(self.before_admission)
        record = copy.deepcopy(self.ownership_record)
        mutate(record)
        record["claim_key"] = claim_key(record)
        snapshot = self.artifacts.import_bytes(
            canonical_bytes(record),
            media_type=OWNERSHIP_MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"profile_identity": OWNERSHIP_PROFILE},
        )
        reference = snapshot.document_reference()
        transaction = Transaction(
            "transaction:damaged-subject-claim", (AppendReferencesChange((reference,)),)
        )
        parent = self.store.head
        document = transaction.apply(self.store.get_document(parent))
        event = AdmissionEvent(
            CONTRACT,
            CHANGE,
            AUTHORITY,
            parent,
            reference,
            transition_hash(document, (parent,), transaction.transaction_id, transaction.message),
        )
        self.store._commit_verified(parent, transaction, document, (event,))
        authenticate_witnesses(self.store.head, collect_witnesses(self.store, self.store.head))

    def test_whole_subject_observations_are_bounds_only_and_complete_at_both_ticks(self):
        before = copy.deepcopy(self.store)
        proposal = self.observations()
        self.assertEqual(proposal, self.observations())
        reference = self.reference(proposal, OBSERVATION_MEDIA_TYPE)
        self.assertEqual(reference["id"], OBSERVATION_ARTIFACT)
        self.assertEqual(self.reference(proposal, MEDIA)["id"], OBSERVATION_PROOF)
        payload = read_primitive_observations(self.artifacts.resolve_reference(reference).content)
        self.assertEqual(
            self.artifacts.resolve_reference(reference).content,
            (GOLDEN / "subject-observations.json").read_bytes(),
        )
        self.assertEqual(
            self.artifacts.resolve_reference(self.reference(proposal, MEDIA)).content,
            (GOLDEN / "subject-membership.json").read_bytes(),
        )
        self.assertEqual(payload["schema_version"], "svm-primitive-observations-0.1")
        self.assertEqual(payload["canvas"], [256, 256])
        self.assertEqual([frame["tick"] for frame in payload["frames"]], [0, 12])
        self.assertEqual([len(frame["primitives"]) for frame in payload["frames"]], [1, 1])
        primitives = [frame["primitives"][0] for frame in payload["frames"]]
        self.assertEqual(
            [p["bounds"] for p in primitives], [[20, 20, 211, 174], [28, 26, 219, 180]]
        )
        self.assertEqual([p["fill"] for p in primitives], ["#000000", "#000000"])
        self.assertEqual([p["primitive_type"] for p in primitives], [PRIMITIVE_TYPE] * 2)
        cv2, np = _opencv()
        for primitive, contributions, png in zip(
            primitives, self.production.contributions, self.production.frames, strict=True
        ):
            masks = [
                cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_UNCHANGED) != 0
                for content in contributions
            ]
            self.assertFalse(np.any(masks[0] & masks[1]))
            union = masks[0] | masks[1]
            raster = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
            self.assertTrue(np.array_equal(union, raster == 0))
            ys, xs = np.nonzero(union)
            self.assertEqual(
                primitive["bounds"],
                [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
            )
        self.assertTrue(all("geometry" not in p for p in primitives))
        self.assertEqual(len({p["observation_id"] for p in primitives}), 2)
        self.assertEqual(tuple(p["observation_id"] for p in primitives), SUBJECT_OBSERVATIONS)
        self.assertTrue({p["observation_id"] for p in primitives}.isdisjoint(PART_OBSERVATIONS))
        self.assertTrue(all(p["observation_id"] != SUBJECT_ID for p in primitives))
        proof = json.loads(
            self.artifacts.resolve_reference(self.reference(proposal, MEDIA)).content
        )
        self.assertEqual(proof["profile_identity"], PROFILE)
        self.assertEqual(proof["subject"], self.ownership_record["subject"])
        self.assertEqual(proof["parts"], self.ownership_record["parts"])
        self.assertEqual(proof["membership"], self.ownership_record["membership"])
        self.assertEqual(proof["admitted_evidence_reference"], self.ownership_ref)
        self.assertEqual(proof["observation_reference"], reference)
        self.assertEqual(len(proof["occurrences"]), 2)
        for occurrence, original, primitive in zip(
            proof["occurrences"], self.ownership_record["occurrences"], primitives, strict=True
        ):
            self.assertEqual({key: occurrence[key] for key in original}, original)
            self.assertEqual(occurrence["observation_id"], primitive["observation_id"])
            self.assertEqual(occurrence["bounds"], primitive["bounds"])
            self.assertEqual(occurrence["fill"], primitive["fill"])
        candidate = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(self.store, before)
        old_document = before.get_document(before.head)
        for key in old_document:
            if key != "references":
                self.assertEqual(candidate[key], old_document[key])
        self.assertEqual(len(candidate["references"]), len(old_document["references"]) + 2)
        revision = self.accept(proposal)
        self.assertEqual(revision.revision_id, OBSERVATION_REVISION)
        self.assertEqual(revision.document_hash, OBSERVATION_DOCUMENT_HASH)
        self.assertFalse(getattr(revision, "admissions", ()))
        self.assertEqual(self.store.get_document(self.store.head), candidate)

    def test_actual_r0_and_r1_add_one_whole_identity_without_merging_part_identities(self):
        old_parts = copy.deepcopy(self.store.get_document(self.store.head)["temporal_identities"])
        self.assertEqual(tuple(item["id"] for item in old_parts), PART_IDENTITIES)
        _, observation_ref, r0 = self.accept_r0()
        self.assertEqual(r0.transaction.changes[0].references[0]["id"], R0_ARTIFACT)
        self.assertEqual(
            self.artifacts.resolve_reference(r0.transaction.changes[0].references[0]).content,
            (GOLDEN / "subject-correspondence.json").read_bytes(),
        )
        candidates = json.loads(
            self.artifacts.resolve_reference(r0.transaction.changes[0].references[0]).content
        )["candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["status"], "SUPPORTED")
        self.assertEqual(candidates[0]["candidate_id"], R0_CANDIDATE)
        self.assertEqual(candidates[0]["inference_id"], R0_INFERENCE)
        self.assertEqual(candidates[0]["support_score"], 0.950281554448)
        before = copy.deepcopy(self.store)
        identity = self.identity()
        self.assertEqual(identity, self.identity())
        candidate = ProposalAcceptor().validate(self.store, identity, self.artifacts)
        self.assertEqual(self.store, before)
        revision = self.accept(identity)
        self.assertEqual(revision.revision_id, FINAL_REVISION)
        self.assertEqual(revision.document_hash, FINAL_DOCUMENT_HASH)
        self.assertEqual(self.reference(identity, IDENTITY_MEDIA)["id"], IDENTITY_PROOF)
        document = self.store.get_document(self.store.head)
        self.assertEqual(candidate, document)
        self.assertEqual(canonical_bytes(document), (GOLDEN / "accepted.svm.json").read_bytes())
        self.assertEqual(
            self.artifacts.resolve_reference(self.reference(identity, IDENTITY_MEDIA)).content,
            (GOLDEN / "subject-identity-proof.json").read_bytes(),
        )
        identities = document["temporal_identities"]
        self.assertEqual(len(identities), 3)
        self.assertEqual([item for item in identities if item["id"] in PART_IDENTITIES], old_parts)
        whole = next(item for item in identities if item["id"] not in PART_IDENTITIES)
        self.assertEqual(whole["id"], WHOLE_IDENTITY)
        observation = read_primitive_observations(
            self.artifacts.resolve_reference(observation_ref).content
        )
        self.assertEqual(
            whole["bindings"],
            [
                {"tick": frame["tick"], "observation_id": frame["primitives"][0]["observation_id"]}
                for frame in observation["frames"]
            ],
        )
        self.assertNotEqual(whole["id"], SUBJECT_ID)
        for key in before.get_document(before.head):
            if key not in {"references", "temporal_identities"}:
                self.assertEqual(document[key], before.get_document(before.head)[key])
        self.assertFalse(document.get("motion_target_bindings"))
        self.assertFalse(document["animation"]["content"])
        self.assertFalse(document.get("tracks"))
        proof = json.loads(
            self.artifacts.resolve_reference(self.reference(identity, IDENTITY_MEDIA)).content
        )
        self.assertIn(PROFILE, canonical_bytes(proof).decode())
        self.assertIn(SUBJECT_ID, canonical_bytes(proof).decode())
        self.assertEqual(proof["temporal_identity"], whole)
        self.assertEqual(
            proof["subject_observation_evidence"]["membership"], self.ownership_record["membership"]
        )

    def test_missing_spec76_admission_and_generic_canonical_evidence_reject(self):
        self.store = copy.deepcopy(self.before_admission)
        self.rejected(self.observations, "Exactly one eligible admitted evidence claim required")
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:legacy-ownership", (AppendReferencesChange((self.ownership_ref,)),)
            ),
        )
        self.rejected(self.observations, "Exactly one eligible admitted evidence claim required")

    def test_incomplete_or_conflicting_authenticated_membership_rejects(self):
        mutations = (
            lambda record: record["membership"].pop(),
            lambda record: record["membership"][0].update(observation_id=PART_OBSERVATIONS[1]),
            lambda record: record["membership"][0].update(part_key="part-b"),
            lambda record: record["membership"][2].update(tick=13),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.damaged_claim(mutate)
                self.rejected(
                    self.observations,
                    "Invalid admitted evidence universe|FORGED_BASE_OR_DEPENDENCY",
                )

    def test_competing_source_ownership_cannot_be_selected_away(self):
        self.damaged_claim(
            lambda record: record["subject"].update(subject_id="subject:multipart:" + "0" * 64)
        )
        self.rejected(self.observations, "FORGED_BASE_OR_DEPENDENCY")
        self.rejected(lambda: self.observations(artifact_ids=(self.ownership_ref["id"],)))

    def test_requests_do_not_allow_subject_part_occurrence_or_evidence_selection(self):
        for kwargs in (
            {"artifact_ids": (self.ownership_ref["id"],)},
            {"options": {"subject_id": SUBJECT_ID}},
            {"options": {"part_keys": ["part-a"]}},
            {"options": {"ticks": [0]}},
        ):
            with self.subTest(kwargs=kwargs):
                self.rejected(lambda kwargs=kwargs: self.observations(**kwargs))
        self.accept_r0()
        for kwargs in (
            {"artifact_ids": (self.ownership_ref["id"],)},
            {"options": {"inference_ids": ["caller"]}},
        ):
            with self.subTest(kwargs=kwargs):
                self.rejected(lambda kwargs=kwargs: self.identity(**kwargs))

    def test_fabricated_aggregate_bounds_id_type_and_geometry_reject_at_acceptance(self):
        proposal = self.observations()
        original = proposal.transaction.changes[0]
        reference = self.reference(proposal, OBSERVATION_MEDIA_TYPE)
        snapshot = self.artifacts.resolve_reference(reference)
        mutations = (
            lambda primitive: primitive.update(bounds=[20, 20, 99, 80]),
            lambda primitive: primitive.update(observation_id=PART_OBSERVATIONS[0]),
            lambda primitive: primitive.update(primitive_type="controlled-raster-polygon@0.1"),
            lambda primitive: primitive.update(fill="#ffffff"),
            lambda primitive: primitive.update(extra_field="caller"),
            lambda primitive: primitive.update(
                geometry={
                    "type": "ordered-landmarks",
                    "points": [[0, 0], [1, 0], [0, 1]],
                    "rotation_symmetry": "none",
                }
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                payload = json.loads(snapshot.content)
                mutate(payload["frames"][0]["primitives"][0])
                forged = self.snapshot(snapshot, payload)
                change = self.substitute_reference(original, reference, forged.document_reference())
                self.rejected(
                    lambda change=change: self.accept(self.changed(proposal, change)),
                    "does not reproduce",
                )
        noncanonical = self.artifacts.import_bytes(
            json.dumps(json.loads(snapshot.content), indent=2).encode(),
            media_type=snapshot.media_type,
            kind=snapshot.kind,
            provenance=snapshot.provenance,
        )
        change = self.substitute_reference(original, reference, noncanonical.document_reference())
        self.rejected(lambda: self.accept(self.changed(proposal, change)), "does not reproduce")

    def test_missing_r0_evidence_rejects(self):
        self.accept_observations()
        self.rejected(
            self.identity, "Exactly one accepted whole-subject R0 evidence Artifact is required"
        )

    def test_fabricated_or_unsupported_accepted_r0_evidence_rejects(self):
        _, _, r0 = self.accept_r0()
        original_ref = r0.transaction.changes[0].references[0]
        original = self.artifacts.resolve_reference(original_ref)
        base = copy.deepcopy(self.store)
        for mutate in (
            lambda payload: payload["candidates"][0].update(status="UNCERTAIN"),
            lambda payload: payload["candidates"][0].update(support_score=1.0),
            lambda payload: payload["candidates"][0].update(
                source_observation_id=PART_OBSERVATIONS[0]
            ),
            lambda payload: payload.update(policy_identity="caller-policy"),
        ):
            with self.subTest(mutation=mutate):
                self.store = copy.deepcopy(base)
                payload = json.loads(original.content)
                mutate(payload)
                forged = self.snapshot(original, payload)
                self.mutate_base(
                    lambda document, forged=forged: document.update(
                        references=[
                            forged.document_reference() if ref == original_ref else ref
                            for ref in document["references"]
                        ]
                    )
                )
                self.rejected(
                    self.identity,
                    "Complete frozen R0 evidence/descriptor does not independently reproduce",
                )

    def test_competing_r0_artifacts_cannot_be_shortlisted(self):
        _, _, r0 = self.accept_r0()
        original = self.artifacts.resolve_reference(r0.transaction.changes[0].references[0])
        payload = json.loads(original.content)
        payload["candidates"][0]["support_score"] = 1.0
        competing = self.snapshot(original, payload)
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:competing-r0",
                (AppendReferencesChange((competing.document_reference(),)),),
            ),
        )
        self.rejected(
            self.identity, "Exactly one accepted whole-subject R0 evidence Artifact is required"
        )

    def test_each_transport_omission_rejects_atomically(self):
        stage1 = self.observations()
        for reference in stage1.transaction.changes[0].references:
            with self.subTest(stage=1, reference=reference["id"]):
                original = stage1.transaction.changes[0]
                if reference in original.source_references:
                    change = replace(
                        original,
                        source_references=tuple(
                            ref for ref in original.source_references if ref != reference
                        ),
                    )
                    self.rejected(lambda change=change: self.accept(self.changed(stage1, change)))
                else:
                    blob = self.artifacts._blobs.pop(reference["id"])
                    try:
                        self.rejected(lambda: self.accept(stage1), "Unknown artifact")
                    finally:
                        self.artifacts._blobs[reference["id"]] = blob
        self.accept_r0()
        stage3 = self.identity()
        for reference in stage3.transaction.changes[0].references:
            with self.subTest(stage=3, reference=reference["id"]):
                original = stage3.transaction.changes[0]
                if reference in original.source_references:
                    change = replace(
                        original,
                        source_references=tuple(
                            ref for ref in original.source_references if ref != reference
                        ),
                    )
                    self.rejected(lambda change=change: self.accept(self.changed(stage3, change)))
                else:
                    blob = self.artifacts._blobs.pop(reference["id"])
                    try:
                        self.rejected(lambda: self.accept(stage3), "Unknown artifact")
                    finally:
                        self.artifacts._blobs[reference["id"]] = blob

    def test_stale_observation_and_identity_proposals_reject_atomically(self):
        proposal = self.observations()
        self.store.commit(self.store.head, Transaction("transaction:advance", ()))
        self.rejected(lambda: self.accept(proposal), "stale|STALE|base|HEAD")
        self.accept_r0()
        proposal = self.identity()
        self.store.commit(self.store.head, Transaction("transaction:advance-identity", ()))
        self.rejected(lambda: self.accept(proposal), "stale|STALE|base|HEAD")

    def test_omitted_or_forged_history_rejects_in_both_stages(self):
        for stage in (1, 3):
            if stage == 3:
                self.accept_r0()
            proposal = self.observations() if stage == 1 else self.identity()
            original = proposal.transaction.changes[0]
            for index, _witness in enumerate(original.witnesses):
                with self.subTest(stage=stage, index=index):
                    witnesses = original.witnesses[:index] + original.witnesses[index + 1 :]
                    self.rejected(
                        lambda witnesses=witnesses, proposal=proposal, original=original: (
                            self.accept(
                                self.changed(proposal, replace(original, witnesses=witnesses))
                            )
                        )
                    )
            admitted = next(w for w in original.witnesses if getattr(w.revision, "admissions", ()))
            event = admitted.revision.admissions[0]
            forged = replace(
                admitted,
                revision=replace(
                    admitted.revision, admissions=(replace(event, authority_identity="caller"),)
                ),
            )
            witnesses = tuple(
                forged if witness == admitted else witness for witness in original.witnesses
            )
            self.rejected(
                lambda proposal=proposal, original=original, witnesses=witnesses: self.accept(
                    self.changed(proposal, replace(original, witnesses=witnesses))
                )
            )

    def test_missing_accepted_dependency_cannot_be_resolver_only_authority(self):
        dependency = self.ownership_record["dependencies"][0]
        self.mutate_base(
            lambda document: document.update(
                references=[ref for ref in document["references"] if ref != dependency]
            )
        )
        self.rejected(self.observations)

    def test_whole_endpoints_cannot_alias_or_merge_existing_part_identities(self):
        _, reference, _ = self.accept_r0()
        observation = read_primitive_observations(
            self.artifacts.resolve_reference(reference).content
        )
        bindings = [
            {"tick": frame["tick"], "observation_id": frame["primitives"][0]["observation_id"]}
            for frame in observation["frames"]
        ]
        base = copy.deepcopy(self.store)
        for owners in ((0, 0), (0, 1)):
            with self.subTest(owners=owners):
                self.store = copy.deepcopy(base)

                def alias(document, owners=owners):
                    for binding, owner in zip(bindings, owners, strict=True):
                        identity = document["temporal_identities"][owner]
                        identity["bindings"].append(copy.deepcopy(binding))
                        identity["bindings"].sort(
                            key=lambda item: (item["tick"], item["observation_id"])
                        )

                self.mutate_base(alias)
                self.rejected(
                    self.identity,
                    "Whole-subject endpoints cannot reuse a part or unrelated identity",
                )

    def test_repeated_bridge_preserves_r1_identity_and_part_bindings(self):
        self.accept_r0()
        self.accept(self.identity())
        identities = copy.deepcopy(self.store.get_document(self.store.head)["temporal_identities"])
        self.accept(self.identity())
        self.assertEqual(
            self.store.get_document(self.store.head)["temporal_identities"], identities
        )

    def test_forged_delegated_r1_identity_cannot_select_a_part_owner(self):
        self.accept_r0()
        proposal = self.identity()
        change = proposal.transaction.changes[0]
        delegated = change.delegated_promotion
        promoted = replace(delegated.correspondences[0], stable_identity_id=PART_IDENTITIES[0])
        change = replace(
            change, delegated_promotion=replace(delegated, correspondences=(promoted,))
        )
        self.rejected(lambda: self.accept(self.changed(proposal, change)))

    def test_registered_policy_actions_are_enforced_in_both_stages(self):
        base = copy.deepcopy(self.store)
        for stage in (1, 3):
            self.store = copy.deepcopy(base)
            if stage == 3:
                self.accept_r0()
            pristine = copy.deepcopy(self.store)
            propose = self.observations if stage == 1 else self.identity
            proposal = propose()
            authority = change_authority(proposal.transaction.changes[0])
            self.assertEqual(
                authority.actions,
                frozenset({"attach_analysis"})
                if stage == 1
                else frozenset({"attach_analysis", "promote_temporal_identity"}),
            )
            for action in authority.actions:
                with self.subTest(stage=stage, action=action):
                    self.store = copy.deepcopy(pristine)
                    self.mutate_base(
                        lambda document, action=action, proposal=proposal: document.update(
                            edit_permissions=[
                                {
                                    "id": "permission:deny-subject-bridge",
                                    "actor": proposal.generator.adapter_id,
                                    "effect": "deny",
                                    "actions": [action],
                                    "targets": ["document"],
                                }
                            ]
                        )
                    )
                    self.rejected(lambda propose=propose: self.accept(propose()), "denies")

    def test_genuine_prior_ordinary_r1_promotion_can_be_independently_bridged(self):
        _, _, r0 = self.accept_r0()
        reference = r0.transaction.changes[0].references[0]
        candidate = json.loads(self.artifacts.resolve_reference(reference).content)["candidates"][0]
        promoted = TemporalIdentityPromotionAdapter().propose(
            self.request(
                artifact_ids=(reference["id"],),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        self.accept(promoted)
        before = copy.deepcopy(self.store.get_document(self.store.head)["temporal_identities"])
        self.accept(self.identity())
        self.assertEqual(self.store.get_document(self.store.head)["temporal_identities"], before)
        self.assertEqual(len(before), 3)

    def test_whole_owner_with_extra_bindings_or_provenance_is_not_reused(self):
        self.accept_r0()
        self.accept(self.identity())
        base = copy.deepcopy(self.store)
        for field in ("bindings", "provenance"):
            with self.subTest(field=field):
                self.store = copy.deepcopy(base)

                def contaminate(document, field=field):
                    whole = next(
                        item
                        for item in document["temporal_identities"]
                        if item["id"] not in PART_IDENTITIES
                    )
                    if field == "bindings":
                        whole["bindings"].append(
                            {"tick": 24, "observation_id": "observation:unrelated"}
                        )
                    else:
                        provenance = copy.deepcopy(whole["provenance"][0])
                        provenance["inference_id"] = "inference:correspondence:" + "0" * 64
                        whole["provenance"].append(provenance)
                        whole["provenance"].sort(
                            key=lambda item: (
                                item["evidence_artifact_id"],
                                item["candidate_id"],
                                item["inference_id"],
                            )
                        )

                self.mutate_base(contaminate)
                self.rejected(
                    self.identity,
                    "Existing whole identity must have exactly the replayed bindings/provenance",
                )

    def test_missing_or_forged_companion_at_r0_creation_base_rejects(self):
        observation_proposal, observation = self.accept_observations()
        companion = self.reference(observation_proposal, MEDIA)
        original = self.artifacts.resolve_reference(companion)
        base = copy.deepcopy(self.store)
        for mutation in (
            "missing",
            "membership",
            "production_base",
            "null_observation",
            "list_observation",
            "null_base",
            "list_base",
        ):
            with self.subTest(mutation=mutation):
                self.store = copy.deepcopy(base)
                if mutation == "missing":
                    replacement = None
                else:
                    payload = json.loads(original.content)
                    if mutation == "membership":
                        payload["membership"].pop()
                    elif mutation == "null_observation":
                        payload["observation_reference"] = None
                    elif mutation == "list_observation":
                        payload["observation_reference"] = []
                    elif mutation == "null_base":
                        payload["base"] = None
                    elif mutation == "list_base":
                        payload["base"] = []
                    else:
                        payload["base"]["revision_id"] = "revision:" + "0" * 64
                    replacement = self.snapshot(original, payload).document_reference()
                self.mutate_base(
                    lambda document, replacement=replacement: document.update(
                        references=[ref for ref in document["references"] if ref != companion]
                        + ([] if replacement is None else [replacement])
                    )
                )
                r0 = TemporalCorrespondenceAdapter().propose(
                    self.request(artifact_ids=(observation["id"],)), self.artifacts
                )
                self.accept(r0)
                pattern = (
                    "Exactly one accepted subject-observation companion"
                    if mutation == "missing"
                    else (
                        "does not independently reproduce"
                        if mutation == "membership"
                        else (
                            "production base must be an authenticated R0 ancestor"
                            if mutation == "production_base"
                            else (
                                "Invalid subject-observation production base"
                                if mutation in {"null_base", "list_base"}
                                else "Invalid accepted subject-observation companion"
                            )
                        )
                    )
                )
                self.rejected(self.identity, pattern)

    def test_self_consistent_companion_without_spec77_authority_rejects(self):
        proposal = self.observations()
        observation = self.reference(proposal, OBSERVATION_MEDIA_TYPE)
        companion = self.reference(proposal, MEDIA)
        self.store = copy.deepcopy(self.before_admission)
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:unproven-subject-data",
                (AppendReferencesChange((self.ownership_ref, observation, companion)),),
            ),
        )
        r0 = TemporalCorrespondenceAdapter().propose(
            self.request(artifact_ids=(observation["id"],)), self.artifacts
        )
        self.accept(r0)
        self.rejected(self.identity, "Exactly one eligible admitted evidence claim required")

    def test_same_blob_with_different_accepted_descriptor_cannot_hide_output_transport(self):
        proposal = self.observations()
        observation = self.reference(proposal, OBSERVATION_MEDIA_TYPE)
        original = self.artifacts.resolve_reference(observation)
        foreign = self.artifacts.import_bytes(
            original.content,
            media_type=original.media_type,
            kind=original.kind,
            provenance={"profile_identity": "caller"},
        )
        self.assertEqual(foreign.artifact_id, original.artifact_id)
        self.assertNotEqual(foreign.document_reference(), observation)
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:descriptor-collision",
                (AppendReferencesChange((foreign.document_reference(),)),),
            ),
        )
        self.rejected(
            lambda: self.accept(self.observations()),
            "Accepted whole-observation descriptor conflicts with reproduced output",
        )

    def test_unknown_outer_and_nested_r1_subclasses_cannot_execute(self):
        calls = []
        original = self.observations()
        change = original.transaction.changes[0]

        def forbidden_apply(self, document):
            calls.append(document)
            raise AssertionError("Unregistered caller behavior executed")

        unregistered = type(
            "UnregisteredSubjectChange", (type(change),), {"apply": forbidden_apply}
        )
        forged = unregistered(
            **{field.name: getattr(change, field.name) for field in fields(change)}
        )
        self.rejected(
            lambda: self.accept(self.changed(original, forged)), "registered|closed-world"
        )
        self.assertFalse(calls)
        self.accept_r0()
        original = self.identity()
        change = original.transaction.changes[0]
        delegated = change.delegated_promotion

        class CallerPromotion(PromoteTemporalIdentityChange):
            def apply(self, document):
                forbidden_apply(self, document)

        forged = CallerPromotion(delegated.correspondences, delegated.references)
        self.rejected(
            lambda: self.accept(
                self.changed(original, replace(change, delegated_promotion=forged))
            ),
            "exact frozen R1 Change",
        )
        self.assertFalse(calls)

        class CallerCorrespondence(PromotedTemporalCorrespondence):
            pass

        promoted = delegated.correspondences[0]
        forged = CallerCorrespondence(
            **{field.name: getattr(promoted, field.name) for field in fields(promoted)}
        )
        self.rejected(
            lambda: self.accept(
                self.changed(
                    original,
                    replace(
                        change, delegated_promotion=replace(delegated, correspondences=(forged,))
                    ),
                )
            ),
            "Temporal identity promotion record type is invalid",
        )

    def test_rehashed_self_consistent_forged_admission_cannot_replace_trusted_ancestry(self):
        proposal = self.observations()
        change = proposal.transaction.changes[0]
        original = {w.revision.revision_id: w for w in change.witnesses}
        rewritten = {}

        def rehash(rid):
            if rid in rewritten:
                return rewritten[rid]
            witness = original[rid]
            revision = witness.revision
            parents = tuple(rehash(parent).revision.revision_id for parent in revision.parent_ids)
            events = getattr(revision, "admissions", ())
            message = revision.message
            if events:
                message = "Caller fabricated this self-consistent admission history"
                commitment = transition_hash(
                    witness.document, parents, revision.transaction_id, message
                )
                events = tuple(
                    replace(event, base_revision_id=parents[0], transition_hash=commitment)
                    for event in events
                )
            altered = RevisionStore._make_revision(
                witness.document, parents, revision.transaction_id, message, events
            )
            rewritten[rid] = replace(witness, revision=altered)
            return rewritten[rid]

        forged_base = rehash(change.source_revision_id).revision.revision_id
        witnesses = tuple(sorted(rewritten.values(), key=lambda w: w.revision.revision_id))
        self.assertNotEqual(forged_base, change.source_revision_id)
        authenticate_witnesses(forged_base, witnesses)  # Complete, internally consistent DAG.
        self.rejected(
            lambda: self.accept(self.changed(proposal, replace(change, witnesses=witnesses))),
            "FORGED_BASE_OR_DEPENDENCY: broken ancestry link",
        )

    def test_late_document_failure_rolls_back_after_each_dedicated_change_executed(self):
        for stage in (1, 3):
            if stage == 3:
                self.accept_r0()
            proposal = self.observations() if stage == 1 else self.identity()
            change = proposal.transaction.changes[0]
            late_failure = AppendSceneFragmentChange(
                (
                    {"id": "entity:duplicate", "name": "duplicate"},
                    {"id": "entity:duplicate", "name": "duplicate"},
                ),
                (),
                (),
                (),
                (),
            )
            invalid = replace(
                proposal, transaction=replace(proposal.transaction, changes=(change, late_failure))
            )
            candidates = []
            apply = type(change).apply

            def observe(actual, document, apply=apply, candidates=candidates):
                apply(actual, document)
                candidates.append(copy.deepcopy(document))

            with patch.object(type(change), "apply", observe):
                self.rejected(lambda invalid=invalid: self.accept(invalid), "unique|duplicate")
            self.assertEqual(len(candidates), 1)
            self.assertIn(change.evidence_reference, candidates[0]["references"])
            if stage == 3:
                self.assertIn(
                    WHOLE_IDENTITY, [item["id"] for item in candidates[0]["temporal_identities"]]
                )

    def test_incoming_document_mutation_and_different_source_base_reject(self):
        ordinary = self.artifacts.import_bytes(b"ordinary-prefix", media_type="text/plain")
        for stage in (1, 3):
            if stage == 3:
                self.accept_r0()
            proposal = self.observations() if stage == 1 else self.identity()
            change = proposal.transaction.changes[0]
            preceding = AppendReferencesChange((ordinary.document_reference(),))
            invalid = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(preceding, change)),
                required_artifact_ids=tuple(
                    dict.fromkeys((ordinary.artifact_id, *proposal.required_artifact_ids))
                ),
            )
            self.rejected(lambda invalid=invalid: self.accept(invalid), "STALE_SUBJECT_BRIDGE")
            changed = replace(change, source_revision_id=self.before_admission.head)
            self.rejected(
                lambda changed=changed, proposal=proposal: self.accept(
                    self.changed(proposal, changed)
                ),
                "Change source revision does not match Proposal base revision",
            )


if __name__ == "__main__":
    unittest.main()
