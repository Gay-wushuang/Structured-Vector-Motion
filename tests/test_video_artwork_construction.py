import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import jsonschema
from test_authored_raster_production import FIXTURE, pipeline

from svm import AdapterRequest, ProposalAcceptor, RevisionStore, Transaction
from svm.adapters.multipart_subject_evidence import (
    DOMAIN,
    MultipartSubjectEvidenceAdapter,
    _hash,
    claim_key,
)
from svm.adapters.multipart_subject_evidence import (
    MEDIA as EVIDENCE_MEDIA,
)
from svm.adapters.multipart_subject_evidence import (
    PROFILE as EVIDENCE_PROFILE,
)
from svm.adapters.video_artwork_construction import (
    MANIFEST_MEDIA,
    RECEIPT_MEDIA,
    VideoArtworkConstructionAdapter,
)
from svm.admission_history import AUTHORITY, CHANGE, CONTRACT, transition_hash
from svm.artifacts import ArtifactKind
from svm.change_authority import resolve_transaction_intents
from svm.document import validate_document
from svm.evaluator import Evaluator, canonical_bytes
from svm.multipart_witness import authenticate_witnesses, collect_witnesses
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.revisions import (
    AdmissionEvent,
    AppendReferencesChange,
    AppendSceneFragmentChange,
    EstablishVideoArtworkGroupChange,
)
from svm.scene import build_evaluated_scene

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples/044-video-artwork-construction"
ENTITY_IDS = (
    "entity:eea3bdf4975a00e2452136ca655ea4c28335e88a4aa86057f479b00d8f06e3c4",
    "entity:e41b0949fa5c081d7d634a7989ecd67c2b5139d2c0c6d112e5481863559cbfad",
)
OPERATION_IDS = (
    "op:e68ba2bd468131455ed18f3e85350b92663086653028f2abbc9482fc32d504fd",
    "op:f53631a1d4d30a0f8366fa7e5c4a8243adfa24557e02cec03fd3da04c1cf95ce",
)
GROUP_ID = "group:1f24284859439580faac31e69df1aa7bf6a1a28c450d8ddae2e3b42e48b656ac"
MANIFEST_ID = "artifact:7d0b42099c1a717bb3b7c9c944f29d7e7fd8946d6ab4eb579e32e3228fb729f5"
RECEIPT_ID = "artifact:5fc6ec132b566fa20201cc74aeceaaf31c82a9fe2fb7802357c9761a24a9db3b"
DOCUMENT_HASH = "sha256:cf9a67e616b4c0d7edbc706a7803af4d4d8a365d8cc2aaf9d439f727d5008ec3"
REVISION_ID = "revision:e54b39d3b14a15047a29e1313d9d8b6bcaa8a798a7e2f5360e996d114fc320b3"
SVG_HASH = "sha256:4552399140954d1d9e95d7fc0369dff37695efc02023862f503ba6b2bbb5efc4"


class FixtureMutation:
    """Trusted test setup only; never registered or proposed across acceptance."""

    def __init__(self, mutate):
        self.mutate = mutate

    def apply(self, document):
        self.mutate(document)


class VideoArtworkConstructionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        artifacts, store, *_ = pipeline()
        cls.before_admission = copy.deepcopy(store)
        evidence = MultipartSubjectEvidenceAdapter().propose(
            AdapterRequest.from_store(store, store.head, ("document",)),
            artifacts,
            witnesses=collect_witnesses(store, store.head),
        )
        ProposalAcceptor().accept(store, evidence, artifacts)
        cls.fixture = artifacts, store, evidence

    def setUp(self):
        self.artifacts, self.store, self.evidence_proposal = copy.deepcopy(self.fixture)
        self.evidence_ref = self.evidence_proposal.transaction.changes[0].evidence_reference
        self.record = json.loads(self.artifacts.resolve_reference(self.evidence_ref).content)

    def propose(self, **kwargs):
        return VideoArtworkConstructionAdapter().propose(
            AdapterRequest.from_store(self.store, self.store.head, ("document",), **kwargs),
            self.artifacts,
            witnesses=collect_witnesses(self.store, self.store.head),
        )

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def changed(self, proposal, change):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(change,)),
            required_artifact_ids=tuple(dict.fromkeys(r["id"] for r in change.references)),
        )

    def rejected(self, action, pattern=None):
        before = copy.deepcopy(self.store)
        errors = (ValueError, ProposalArtifactError, ProposalConflictError, ProposalPolicyError)
        context = self.assertRaisesRegex(errors, pattern) if pattern else self.assertRaises(errors)
        with context:
            action()
        self.assertEqual(before, self.store)
        self.assertEqual(
            before.get_document(before.head)["references"],
            self.store.get_document(self.store.head)["references"],
        )

    def mutate_base(self, mutate):
        self.store.commit(
            self.store.head,
            Transaction("transaction:f0-fixture", (FixtureMutation(mutate),)),
        )

    def install_claim(self, record, *, content=None, provenance=None, bind_base=True):
        """Simulate damaged trusted history to exercise F0 beyond witness consistency.

        Normal Golden admission always uses the real dedicated Spec76 verifier.
        This helper is never an Adapter or an acceptance capability.
        """
        record = copy.deepcopy(record)
        parent = self.store.head
        if bind_base:
            record["base"] = {
                "revision_id": parent,
                "document_hash": self.store.revisions[parent].document_hash,
            }
        snapshot = self.artifacts.import_bytes(
            canonical_bytes(record) if content is None else content(record),
            media_type=EVIDENCE_MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"profile_identity": EVIDENCE_PROFILE} if provenance is None else provenance,
        )
        ref = snapshot.document_reference()
        transaction = Transaction(
            "transaction:damaged-admission-fixture", (AppendReferencesChange((ref,)),)
        )
        document = transaction.apply(self.store.get_document(parent))
        event = AdmissionEvent(
            CONTRACT,
            CHANGE,
            AUTHORITY,
            parent,
            ref,
            transition_hash(document, (parent,), transaction.transaction_id, transaction.message),
        )
        self.store._commit_verified(parent, transaction, document, (event,))
        authenticate_witnesses(self.store.head, collect_witnesses(self.store, self.store.head))
        return ref

    def install_single_claim(self, record, **kwargs):
        self.store = copy.deepcopy(self.before_admission)
        return self.install_claim(record, **kwargs)

    def test_golden_preview_atomic_commit_and_exact_svg(self):
        before = copy.deepcopy(self.store)
        proposal = self.propose()
        self.assertEqual(proposal, self.propose())
        change = proposal.transaction.changes[0]
        self.assertIs(type(change), EstablishVideoArtworkGroupChange)
        candidate = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(before, self.store)
        self.assertEqual(tuple(e["id"] for e in change.fragment.entities), ENTITY_IDS)
        self.assertEqual(tuple(o["id"] for o in change.fragment.operations), OPERATION_IDS)
        self.assertEqual(change.group["id"], GROUP_ID)
        self.assertEqual(change.group["members"], sorted(ENTITY_IDS))
        self.assertEqual(change.group["transform"]["origin"], [116.0, 97.0])
        self.assertEqual(
            [o["parameters"] for o in change.fragment.operations],
            [
                {"d": "M 20 20 L 100 20 L 20 80 Z", "bounds": [20.0, 20.0, 100.0, 80.0]},
                {"d": "M 140 120 L 212 120 L 140 174 Z", "bounds": [140.0, 120.0, 212.0, 174.0]},
            ],
        )
        base = before.get_document(before.head)
        self.assertEqual(candidate["references"][: len(base["references"])], base["references"])
        self.assertEqual(len(candidate["references"]), len(base["references"]) + 2)
        for key in base:
            if key not in {"entities", "construction", "presentation", "references"}:
                self.assertEqual(candidate[key], base[key])
        self.assertFalse(candidate.get("temporal_identities"))
        self.assertFalse(candidate.get("motion_target_bindings"))
        self.assertEqual(candidate["animation"], base["animation"])
        self.assertNotIn("camera", candidate)
        jsonschema.validate(
            candidate, json.loads((ROOT / "schema/svm-document-v0.1.schema.json").read_text())
        )
        renderer = SVGRenderer(SVGRenderOptions(256, 256, (0, 0, 256, 256)))
        svg = renderer.render(build_evaluated_scene(candidate, Evaluator(candidate)))
        self.assertEqual(svg.encode(), (GOLDEN / "group.svg").read_bytes())
        self.assertEqual(
            svg, renderer.render(build_evaluated_scene(candidate, Evaluator(candidate)))
        )
        revision = self.accept(proposal)
        self.assertEqual(len(self.store.revisions), len(before.revisions) + 1)
        self.assertEqual(self.store.get_document(revision.revision_id), candidate)
        self.assertFalse(getattr(revision, "admissions", ()))
        measured = json.loads((GOLDEN / "golden.json").read_text())
        manifest = next(r for r in change.references if r["media_type"] == MANIFEST_MEDIA)
        receipt = next(r for r in change.references if r["media_type"] == RECEIPT_MEDIA)
        self.assertEqual(manifest["id"], MANIFEST_ID)
        self.assertEqual(receipt["id"], RECEIPT_ID)
        self.assertEqual(revision.document_hash, DOCUMENT_HASH)
        self.assertEqual(revision.revision_id, REVISION_ID)
        self.assertEqual("sha256:" + hashlib.sha256(svg.encode()).hexdigest(), SVG_HASH)
        self.assertEqual(measured["manifest_artifact_id"], manifest["id"])
        self.assertEqual(measured["receipt_artifact_id"], receipt["id"])
        self.assertEqual(measured["document_hash"], revision.document_hash)
        self.assertEqual(measured["revision_id"], revision.revision_id)
        self.assertEqual(measured["svg_hash"], "sha256:" + hashlib.sha256(svg.encode()).hexdigest())

    def test_generic_and_legacy_evidence_are_data_even_when_bytes_unavailable(self):
        for generic in (
            AppendReferencesChange((self.evidence_ref,)),
            AppendSceneFragmentChange((), (), (), (), (), (self.evidence_ref,)),
        ):
            with self.subTest(change=type(generic).__name__):
                self.store = copy.deepcopy(self.before_admission)
                # Pre-Spec77 persisted legacy history, deliberately outside acceptance.
                self.store.commit(self.store.head, Transaction("legacy", (generic,)))
                self.rejected(self.propose)
        self.artifacts._blobs.pop(self.evidence_ref["id"])
        self.rejected(self.propose)

    def test_unproven_descriptor_does_not_influence_the_admitted_candidate(self):
        legacy = self.artifacts.import_bytes(
            b"legacy bytes are not JSON authority",
            media_type=EVIDENCE_MEDIA,
            kind=ArtifactKind.DERIVED,
        )
        self.store.commit(
            self.store.head,
            Transaction("legacy-data", (AppendReferencesChange((legacy.document_reference(),)),)),
        )
        self.artifacts._blobs.pop(legacy.artifact_id)
        proposal = self.propose()
        self.assertNotIn(legacy.artifact_id, proposal.required_artifact_ids)
        self.assertEqual(proposal.transaction.changes[0].evidence_reference, self.evidence_ref)
        self.accept(proposal)

    def test_ordinary_video_without_admitted_ownership_rejects(self):
        self.store = copy.deepcopy(self.before_admission)
        self.rejected(self.propose)
        self.assertFalse(self.store.get_document(self.store.head).get("groups"))

    def test_every_witness_omission_tamper_order_and_unanchored_node_rejects(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        for index, witness in enumerate(original.witnesses):
            with self.subTest(index=index, mutation="omission"):
                change = replace(
                    original, witnesses=original.witnesses[:index] + original.witnesses[index + 1 :]
                )
                self.rejected(lambda change=change: self.accept(self.changed(proposal, change)))
            with self.subTest(index=index, mutation="hash"):
                changed = replace(witness, revision=replace(witness.revision, message="forged"))
                witnesses = list(original.witnesses)
                witnesses[index] = changed
                self.rejected(
                    lambda witnesses=witnesses: self.accept(
                        self.changed(proposal, replace(original, witnesses=tuple(witnesses)))
                    )
                )
        self.rejected(
            lambda: self.accept(
                self.changed(
                    proposal, replace(original, witnesses=tuple(reversed(original.witnesses)))
                )
            )
        )
        extra = RevisionStore.create(self.store.get_document(self.store.head), "unanchored")
        witnesses = tuple(
            sorted(
                original.witnesses + collect_witnesses(extra, extra.head),
                key=lambda w: w.revision.revision_id,
            )
        )
        self.rejected(
            lambda: self.accept(self.changed(proposal, replace(original, witnesses=witnesses)))
        )

    def test_missing_forged_and_rehashed_admission_events_cannot_replace_history(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        admitted = self.store.revisions[self.store.head]
        event = admitted.admissions[0]
        variants = (
            (),
            (replace(event, authority_identity="caller"),),
            (replace(event, base_revision_id=self.store.head),),
            (replace(event, transition_hash="revision:" + "1" * 64),),
        )
        for events in variants:
            for rehash in (False, True):
                with self.subTest(events=events, rehash=rehash):
                    revision = (
                        RevisionStore._make_revision(
                            self.store.get_document(self.store.head),
                            admitted.parent_ids,
                            admitted.transaction_id,
                            admitted.message,
                            events,
                        )
                        if rehash
                        else replace(admitted, admissions=events)
                    )
                    witnesses = tuple(
                        sorted(
                            (
                                replace(w, revision=revision) if w.revision == admitted else w
                                for w in original.witnesses
                            ),
                            key=lambda w: w.revision.revision_id,
                        )
                    )
                    self.rejected(
                        lambda witnesses=witnesses: self.accept(
                            self.changed(proposal, replace(original, witnesses=witnesses))
                        )
                    )

    def test_record_base_binding_and_hash_require_authenticated_ancestor(self):
        for field, value in (
            ("revision_id", "revision:" + "1" * 64),
            ("revision_id", self.store.head),
            ("document_hash", "sha256:" + "2" * 64),
        ):
            with self.subTest(field=field, value=value):
                record = copy.deepcopy(self.record)
                record["base"][field] = value
                self.install_single_claim(record, bind_base=False)
                self.rejected(self.propose)

    def test_other_branch_admission_does_not_authorize_the_same_bytes(self):
        admitted_branch = self.store.head
        self.store.checkout(self.before_admission.head)
        self.store.commit(
            self.store.head,
            Transaction("other-branch-data", (AppendReferencesChange((self.evidence_ref,)),)),
        )
        self.assertIn(admitted_branch, self.store.revisions)
        self.assertNotIn(
            admitted_branch,
            {w.revision.revision_id for w in collect_witnesses(self.store, self.store.head)},
        )
        self.rejected(self.propose, "Exactly one eligible admitted evidence claim required")

    def test_two_eligible_claims_have_no_caller_tiebreak(self):
        original_proposal = self.propose()
        other = self.install_claim(self.record)
        self.rejected(self.propose)
        self.rejected(lambda: self.propose(artifact_ids=(self.evidence_ref["id"],)))
        original = original_proposal.transaction.changes[0]
        change = replace(
            original,
            source_revision_id=self.store.head,
            base_document_snapshot=self.store.get_document(self.store.head),
            witnesses=collect_witnesses(self.store, self.store.head),
            references=original.references + (other,),
        )
        proposal = replace(original_proposal, base_revision_id=self.store.head)
        self.rejected(
            lambda: self.accept(self.changed(proposal, change)),
            "eligible admitted evidence claim",
        )

    def test_nonempty_base_records_and_render_prefix_are_preserved(self):
        scene = json.loads((ROOT / "examples/003-split-head.svm.json").read_text())

        def install(document):
            for key in ("entities", "construction", "presentation"):
                document[key] = copy.deepcopy(scene[key])

        self.mutate_base(install)
        before = self.store.get_document(self.store.head)
        proposal = self.propose()
        candidate = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        for old, new in (
            (before["entities"], candidate["entities"]),
            (before["construction"]["operations"], candidate["construction"]["operations"]),
            (
                before["construction"]["output_bindings"],
                candidate["construction"]["output_bindings"],
            ),
            (before["presentation"]["styles"], candidate["presentation"]["styles"]),
            (before["presentation"]["render_stack"], candidate["presentation"]["render_stack"]),
        ):
            self.assertEqual(new[: len(old)], old)
            self.assertEqual(len(new), len(old) + 2)
        self.assertEqual(proposal.transaction.changes[0].group["id"], GROUP_ID)
        self.accept(proposal)

    def test_different_admitted_evidence_cannot_recreate_same_source(self):
        self.accept(self.propose())
        replacement = self.install_claim(self.record)
        self.assertNotEqual(replacement, self.evidence_ref)
        self.mutate_base(
            lambda d: d.update(
                references=[r for r in d["references"] if r["id"] != self.evidence_ref["id"]]
            )
        )
        self.rejected(self.propose, "collision|IDs must be unique")

    def test_all_transport_references_are_required_and_exact(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        for index, reference in enumerate(original.references):
            with self.subTest(reference=reference["id"]):
                change = replace(
                    original,
                    references=original.references[:index] + original.references[index + 1 :],
                )
                self.rejected(lambda change=change: self.accept(self.changed(proposal, change)))
        for refs in (
            original.references + (original.references[0],),
            tuple(reversed(original.references)),
        ):
            self.rejected(
                lambda refs=refs: self.accept(
                    self.changed(proposal, replace(original, references=refs))
                )
            )

    def test_ineligible_admitted_candidate_is_still_required_in_transport(self):
        extra = self.artifacts.import_bytes(b"old claim dependency", media_type="text/plain")
        self.store.commit(
            self.store.head,
            Transaction("old-extra", (AppendReferencesChange((extra.document_reference(),)),)),
        )
        record = copy.deepcopy(self.record)
        record["dependencies"].append(extra.document_reference())
        other = self.install_claim(record)
        self.mutate_base(
            lambda d: d.update(
                references=[r for r in d["references"] if r["id"] != extra.artifact_id]
            )
        )
        proposal = self.propose()
        self.assertIn(other["id"], proposal.required_artifact_ids)
        original = proposal.transaction.changes[0]
        change = replace(
            original, references=tuple(r for r in original.references if r["id"] != other["id"])
        )
        self.rejected(lambda change=change: self.accept(self.changed(proposal, change)))
        self.artifacts._blobs.pop(other["id"])
        self.rejected(self.propose)

    def test_record_closed_world_constants_and_canonical_bytes(self):
        mutations = {
            "extra": lambda r: r.update(caller="selection"),
            "missing": lambda r: r.pop("membership"),
            "schema": lambda r: r.update(schema_version="unknown"),
            "profile": lambda r: r.update(profile_identity="unknown"),
            "policy": lambda r: r.update(production_policy="unknown"),
            "audit_disposition": lambda r: r["competing_claims"].update(disposition="SUPPORTED"),
            "audit_type": lambda r: r["competing_claims"].update(claim_artifact_ids="caller"),
            "status": lambda r: r.update(status="SUPPORTED"),
            "judgment": lambda r: r.update(judgment="SUPPORTED"),
            "subject_extra": lambda r: r["subject"].update(caller="root"),
            "part_extra": lambda r: r["parts"][0].update(caller="part"),
            "occurrence_extra": lambda r: r["occurrences"][0].update(caller="occurrence"),
            "boolean_timing": lambda r: r["occurrences"][0].update(frame_index=False),
            "invalid_timestamp": lambda r: r["occurrences"][0].update(source_timestamp=[0, 0]),
            "membership_extra": lambda r: r["membership"][0].update(caller="member"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                record = copy.deepcopy(self.record)
                mutate(record)
                if "membership" in record:
                    record["claim_key"] = claim_key(record)
                self.install_single_claim(record)
                reason = {
                    "audit_disposition": "Invalid admitted competing claim audit",
                    "audit_type": "Invalid admitted competing claim audit",
                    "subject_extra": "Invalid admitted evidence fields",
                    "part_extra": "Invalid admitted evidence universe",
                    "occurrence_extra": "Invalid admitted evidence universe",
                    "membership_extra": "Invalid admitted evidence universe",
                    "boolean_timing": "Invalid admitted evidence timing",
                    "invalid_timestamp": "Invalid admitted evidence timing",
                }.get(label, "Invalid admitted evidence schema/descriptor")
                self.rejected(self.propose, reason)
        self.install_single_claim(self.record, content=lambda r: json.dumps(r).encode())
        self.rejected(self.propose, "Invalid admitted evidence schema/descriptor")
        self.install_single_claim(
            self.record, provenance={"profile_identity": EVIDENCE_PROFILE, "caller": "admitted"}
        )
        self.rejected(self.propose, "Invalid admitted evidence schema/descriptor")

    def test_summary_hash_and_media_are_checked_against_real_base_descriptors(self):
        for key in ("source", "video", "manifest"):
            with self.subTest(summary=key, field="content_hash"):
                record = copy.deepcopy(self.record)
                record[key]["content_hash"] = "sha256:" + "0" * 64
                self.install_single_claim(record)
                parent = self.store.revisions[self.store.head].parent_ids[0]
                descriptor = next(
                    r
                    for r in self.store.get_document(parent)["references"]
                    if r["id"] == record[key]["artifact_id"]
                )
                self.assertNotEqual(descriptor["content_hash"], record[key]["content_hash"])
                self.artifacts.resolve_reference(descriptor)
                self.rejected(
                    self.propose,
                    "Evidence summary does not match its authenticated base descriptor",
                )
            with self.subTest(summary=key, field="media_type"):
                record = copy.deepcopy(self.record)
                record[key]["media_type"] = "text/plain"
                self.install_single_claim(record)
                self.rejected(
                    self.propose,
                    "Source summary media mismatch"
                    if key == "source"
                    else "Invalid admitted evidence fields",
                )

    def test_claim_key_and_source_subject_and_part_agreement(self):
        mutations = {
            "claim_key": lambda r: r.update(claim_key="0" * 64),
            "subject_id": lambda r: r["subject"].update(subject_id="subject:multipart:" + "0" * 64),
            "root": lambda r: r["subject"].update(
                ownership_root_artifact_id="artifact:" + "0" * 64
            ),
            "path": lambda r: r["subject"].update(canonical_source_subject_path=[1]),
            "parts_order": lambda r: r["parts"].reverse(),
            "part_id": lambda r: r["parts"][0].update(part_id="part:multipart:" + "0" * 64),
            "missing_part": lambda r: r["parts"].pop(),
            "extra_part": lambda r: r["parts"].append(copy.deepcopy(r["parts"][0])),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                record = copy.deepcopy(self.record)
                mutate(record)
                if label != "claim_key":
                    record["claim_key"] = claim_key(record)
                self.install_single_claim(record)
                self.rejected(self.propose)

    def test_changed_removed_or_renamed_closure_is_inapplicable(self):
        original_store = copy.deepcopy(self.store)
        ids = [self.record[k]["artifact_id"] for k in ("source", "video", "manifest")]
        ids += [r["id"] for r in self.record["dependencies"]]
        for aid in dict.fromkeys(ids):
            for action in ("remove", "rename", "descriptor"):
                with self.subTest(aid=aid, action=action):
                    self.store = copy.deepcopy(original_store)

                    def mutate(document, action=action, aid=aid):
                        if action == "remove":
                            document["references"] = [
                                r for r in document["references"] if r["id"] != aid
                            ]
                        else:
                            ref = next(r for r in document["references"] if r["id"] == aid)
                            ref["uri"] = (
                                "caller:renamed" if action == "rename" else "caller:descriptor"
                            )

                    self.mutate_base(mutate)
                    self.rejected(self.propose)

    def test_source_parser_is_exact_spec75_and_unrelated_svg_is_ignored(self):
        original_store = copy.deepcopy(self.store)
        original_artifacts = copy.deepcopy(self.artifacts)
        source = (FIXTURE / "source.svg").read_bytes()
        bad_sources = (
            b"not XML",
            source.replace(b"<g>", b'<g id="caller">'),
            source.replace(b'id="part-a"', b'id="part-b"'),
            source.replace(b"M 20 20", b"M 020 20"),
            source.replace(b"M 20 20", b"M 0 20"),
            source.replace(b"L 100 20 L 20 80", b"L 20 80 L 100 20"),
            source.replace(b"M 140 120 L 212 120 L 140 174", b"M 20 20 L 100 20 L 20 80"),
            source.replace(b"</g>", b'<path id="part-c" d="M 1 1 L 2 1 L 1 2 Z"/></g>'),
        )
        for index, content in enumerate(bad_sources):
            with self.subTest(index=index):
                self.store = copy.deepcopy(self.before_admission)
                self.artifacts = copy.deepcopy(original_artifacts)
                snapshot = self.artifacts.import_bytes(content, media_type="image/svg+xml")
                self.store.commit(
                    self.store.head,
                    Transaction(
                        "bad-source", (AppendReferencesChange((snapshot.document_reference(),)),)
                    ),
                )
                record = copy.deepcopy(self.record)
                record["source"] = {
                    "artifact_id": snapshot.artifact_id,
                    "content_hash": snapshot.content_hash,
                    "media_type": snapshot.media_type,
                    "source_revision_id": self.store.head,
                }
                subject_key = {
                    "ownership_profile_identity": EVIDENCE_PROFILE,
                    "ownership_root_artifact_id": snapshot.artifact_id,
                    "canonical_source_subject_path": [0],
                }
                sid = "subject:multipart:" + _hash(
                    {"identity_domain": DOMAIN, "source_subject_key": subject_key}
                )
                record["subject"] = {
                    "subject_id": sid,
                    "ownership_root_artifact_id": snapshot.artifact_id,
                    "canonical_source_subject_path": [0],
                }
                record["parts"] = [
                    {
                        "part_id": "part:multipart:"
                        + _hash(
                            {"identity_domain": DOMAIN, "subject_id": sid, "source_part_key": key}
                        ),
                        "part_key": key,
                    }
                    for key in ("part-a", "part-b")
                ]
                record["claim_key"] = claim_key(record)
                self.install_claim(record)
                self.rejected(self.propose)
        self.store, self.artifacts = original_store, original_artifacts
        extra = self.artifacts.import_bytes(
            b"unrelated SVG need not satisfy production grammar", media_type="image/svg+xml"
        )
        self.store.commit(
            self.store.head,
            Transaction(
                "unrelated-source", (AppendReferencesChange((extra.document_reference(),)),)
            ),
        )
        self.assertEqual(self.propose().transaction.changes[0].group["id"], GROUP_ID)

    def test_corrupted_source_or_transitive_artifact_bytes_reject(self):
        proposal = self.propose()
        original_artifacts = copy.deepcopy(self.artifacts)
        for aid in (
            self.record["source"]["artifact_id"],
            self.record["video"]["artifact_id"],
            self.record["dependencies"][0]["id"],
        ):
            with self.subTest(aid=aid):
                self.artifacts = copy.deepcopy(original_artifacts)
                self.artifacts._blobs[aid] = replace(
                    self.artifacts._blobs[aid], content=b"corrupted"
                )
                self.rejected(lambda: self.accept(proposal))

    def test_fragment_is_completely_reproduced(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        mutations = {
            "d": lambda c: c.fragment.operations[0]["parameters"].update(d="M 1 1 L 2 1 L 1 2 Z"),
            "bounds": lambda c: c.fragment.operations[0]["parameters"].update(bounds=[0, 0, 1, 1]),
            "nonfinite": lambda c: c.fragment.operations[0]["parameters"].update(
                bounds=[0, 0, float("nan"), 1]
            ),
            "entity_id": lambda c: c.fragment.entities[0].update(id="entity:caller"),
            "name": lambda c: c.fragment.entities[0].update(name="caller"),
            "binding": lambda c: c.fragment.output_bindings[0].update(slot="op:caller.geometry"),
            "style": lambda c: c.fragment.styles[0].update(fill="#FFFFFF"),
            "operation_type": lambda c: c.fragment.operations[0].update(type="CreateRectangle"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                change = copy.deepcopy(original)
                mutate(change)
                self.rejected(lambda change=change: self.accept(self.changed(proposal, change)))
        for field in ("entities", "operations", "output_bindings", "styles", "render_entries"):
            value = getattr(original.fragment, field)
            for replacement in (value[:-1], value + (value[0],), tuple(reversed(value))):
                with self.subTest(field=field, replacement=replacement):
                    fragment = replace(original.fragment, **{field: replacement})
                    self.rejected(
                        lambda fragment=fragment: self.accept(
                            self.changed(proposal, replace(original, fragment=fragment))
                        )
                    )
        self.rejected(
            lambda: self.accept(
                self.changed(
                    proposal,
                    replace(
                        original,
                        fragment=replace(original.fragment, references=original.references),
                    ),
                )
            )
        )

    def test_group_and_evidence_selection_cannot_be_supplied(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        mutations = {
            "group_id": lambda c: c.group.update(id="group:" + "a" * 64),
            "member": lambda c: c.group["members"].pop(),
            "member_order": lambda c: c.group["members"].reverse(),
            "origin": lambda c: c.group["transform"].update(origin=[0, 0]),
            "translate": lambda c: c.group["transform"].update(translate=[8, 6]),
            "scale": lambda c: c.group["transform"].update(scale=2),
            "provenance": lambda c: c.group["provenance"].update(candidate_id="caller"),
            "profile": lambda c: c.group["provenance"].update(
                profile_identity="svm-svg-two-part-group-construction@0.1"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                change = copy.deepcopy(original)
                mutate(change)
                self.rejected(lambda change=change: self.accept(self.changed(proposal, change)))
        self.rejected(
            lambda: self.accept(
                self.changed(
                    proposal,
                    replace(original, profile_identity="svm-svg-two-part-group-construction@0.1"),
                )
            )
        )
        other = copy.deepcopy(original.evidence_reference)
        other["uri"] = "caller:evidence"
        self.rejected(
            lambda: self.accept(self.changed(proposal, replace(original, evidence_reference=other)))
        )

    def test_manifest_receipt_and_correspondence_claims_cannot_self_attest(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        mutations = {
            MANIFEST_MEDIA: (
                lambda r: r.update(subject={"source_artifact_id": "caller", "subject_path": [0]}),
                lambda r: r.update(member_bounds=[]),
                lambda r: r.update(parameters={"caller": 1}),
                lambda r: r["source_references"].reverse(),
                lambda r: r.update(group_id=GROUP_ID),
            ),
            RECEIPT_MEDIA: (
                lambda r: r.update(
                    representation_claim={"TemporalIdentity": "caller", "Group": GROUP_ID}
                ),
                lambda r: r["evidence"]["admission"].update(transition_hash="revision:caller"),
                lambda r: r["evidence"].update(claim_key="0" * 64),
                lambda r: r.update(caller="selection"),
                lambda r: r.pop("group"),
            ),
        }
        for media, alterations in mutations.items():
            reference = next(r for r in original.references if r["media_type"] == media)
            snapshot = self.artifacts.resolve_reference(reference)
            for index, mutate in enumerate(alterations):
                with self.subTest(media=media, index=index):
                    record = json.loads(snapshot.content)
                    mutate(record)
                    forged = self.artifacts.import_bytes(
                        canonical_bytes(record),
                        media_type=media,
                        kind=snapshot.kind,
                        provenance=snapshot.provenance,
                    )
                    refs = tuple(
                        forged.document_reference() if r == reference else r
                        for r in original.references
                    )
                    self.rejected(
                        lambda refs=refs: self.accept(
                            self.changed(proposal, replace(original, references=refs))
                        )
                    )

    def test_base_envelope_and_incoming_document_guards(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        change = copy.deepcopy(original)
        change.base_document_snapshot["references"] = []
        self.rejected(lambda change=change: self.accept(self.changed(proposal, change)))
        change = replace(original, source_revision_id=self.record["base"]["revision_id"])
        self.rejected(lambda change=change: self.accept(self.changed(proposal, change)))
        extra = self.artifacts.import_bytes(b"earlier mutation", media_type="text/plain")
        earlier = AppendReferencesChange((extra.document_reference(),))
        bad = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(earlier, original)),
            required_artifact_ids=proposal.required_artifact_ids + (extra.artifact_id,),
        )
        self.rejected(lambda: self.accept(bad), "STALE_CONSTRUCTION")
        self.store.commit(self.store.head, Transaction("advance", (earlier,)))
        self.rejected(lambda: self.accept(proposal), "base revision")
        reproposal = self.propose()
        self.assertEqual(reproposal.transaction.changes[0].fragment, original.fragment)
        self.assertEqual(reproposal.transaction.changes[0].group["id"], original.group["id"])

    def test_create_only_collisions_and_same_allocation_after_later_edit(self):
        proposal = self.propose()
        self.accept(proposal)
        extra = self.artifacts.import_bytes(b"unrelated edit", media_type="text/plain")
        self.store.commit(
            self.store.head,
            Transaction("later", (AppendReferencesChange((extra.document_reference(),)),)),
        )
        self.rejected(self.propose, "collision|IDs must be unique")
        self.assertEqual(self.store.get_document(self.store.head)["groups"][0]["id"], GROUP_ID)
        for kind in ("entity", "operation", "group"):
            with self.subTest(kind=kind):
                self.artifacts, self.store, _ = copy.deepcopy(self.fixture)
                original = proposal.transaction.changes[0]

                def install(document, kind=kind, original=original):
                    if kind == "entity":
                        document["entities"].append(copy.deepcopy(original.fragment.entities[0]))
                    elif kind == "operation":
                        document["construction"]["operations"].append(
                            copy.deepcopy(original.fragment.operations[0])
                        )
                    else:
                        original.fragment.apply(document)
                        document["groups"] = [copy.deepcopy(original.group)]
                        document["references"].append(
                            copy.deepcopy(
                                next(
                                    r
                                    for r in original.references
                                    if r["media_type"] == MANIFEST_MEDIA
                                )
                            )
                        )

                self.mutate_base(install)
                self.rejected(self.propose, "collision|IDs must be unique")

    def test_exact_registered_type_and_structural_profile_admission(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        candidate = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        for provenance in (
            {"type": "unknown"},
            {"profile_identity": "unknown"},
            {"candidate_id": "candidate:caller"},
            {"type": "pop-group-inference@0.1"},
        ):
            with self.subTest(provenance=provenance):
                document = copy.deepcopy(candidate)
                document["groups"][0]["provenance"].update(provenance)
                with self.assertRaises(ValueError):
                    validate_document(document)
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(
                        document,
                        json.loads((ROOT / "schema/svm-document-v0.1.schema.json").read_text()),
                    )

        class Unregistered(EstablishVideoArtworkGroupChange):
            pass

        forged = Unregistered(**original.__dict__)
        self.rejected(lambda: self.accept(self.changed(proposal, forged)))

    def test_later_failure_rolls_back_the_entire_construction(self):
        proposal = self.propose()
        bad = replace(
            proposal,
            transaction=replace(
                proposal.transaction,
                changes=(*proposal.transaction.changes, AppendReferencesChange(())),
            ),
        )
        self.rejected(lambda: self.accept(bad), "at least one Artifact reference")

    def test_all_four_required_policy_intents_deny_atomically(self):
        proposal = self.propose()
        intents = resolve_transaction_intents(proposal.transaction)
        self.assertEqual(
            set(intents),
            {
                ("establish_group", "document", None),
                ("import_scene", "document", None),
                ("set_group_transform", GROUP_ID, "transform"),
                ("attach_analysis", "document", None),
            },
        )
        for action, target, _ in intents:
            with self.subTest(action=action):
                self.artifacts, self.store, _ = copy.deepcopy(self.fixture)
                self.mutate_base(
                    lambda d, action=action, target=target: d["edit_permissions"].append(
                        {
                            "id": "permission:f0-deny",
                            "actor": "*",
                            "effect": "deny",
                            "actions": [action],
                            "targets": ["*" if action == "set_group_transform" else target],
                        }
                    )
                )
                denied_proposal = self.propose()
                before = copy.deepcopy(self.store)
                with self.assertRaises(ProposalPolicyError):
                    self.accept(denied_proposal)
                self.assertEqual(before, self.store)
                self.assertEqual(
                    before.get_document(before.head)["references"],
                    self.store.get_document(self.store.head)["references"],
                )

    def test_request_has_no_options_artifact_ids_or_partial_scope(self):
        request = AdapterRequest.from_store(self.store, self.store.head, ("document",))
        for option in (
            "evidence",
            "source",
            "members",
            "baseline",
            "subject",
            "style",
            "origin",
            "profile",
        ):
            with self.subTest(option=option):
                self.rejected(lambda option=option: self.propose(options={option: "caller"}))
        self.rejected(lambda: self.propose(artifact_ids=(self.evidence_ref["id"],)))
        self.rejected(
            lambda: VideoArtworkConstructionAdapter().propose(
                replace(request, scope=("entity:caller",)),
                self.artifacts,
                witnesses=collect_witnesses(self.store, self.store.head),
            )
        )

    def test_admission_trust_does_not_rerun_spec75_or_spec76_pixels(self):
        with (
            patch(
                "svm.adapters.multipart_subject_evidence._facts",
                side_effect=AssertionError("F0 must trust genuine admission"),
            ),
            patch(
                "svm.authored_raster_production.replay_snapshots",
                side_effect=AssertionError("F0 must not rerun pixels"),
            ),
        ):
            self.accept(self.propose())


if __name__ == "__main__":
    unittest.main()
