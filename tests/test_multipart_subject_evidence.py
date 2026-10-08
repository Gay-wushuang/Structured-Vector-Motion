import copy
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from test_authored_raster_production import accept_refs, pipeline

from svm import AdapterRequest, ProposalAcceptor, RevisionStore, Transaction
from svm.adapters.multipart_subject_evidence import (
    DOMAIN,
    MEDIA,
    PROFILE,
    MultipartSubjectDiagnostic,
    MultipartSubjectEvidenceAdapter,
    _compare_claims,
    _hash,
    claim_key,
    derive,
)
from svm.artifacts import ArtifactKind
from svm.change_authority import change_authority
from svm.evaluator import canonical_bytes
from svm.multipart_witness import authenticate_witnesses, collect_witnesses
from svm.proposals import (
    GeneratorProvenance,
    Proposal,
    ProposalArtifactError,
    ProposalConflictError,
    ProposalPolicyError,
)
from svm.revisions import AppendReferencesChange, AttachMultipartSubjectEvidenceChange
from svm.video_ingestion import VideoSampling, ingest_video


class MultipartSubjectEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = pipeline()

    def setUp(self):
        (
            self.artifacts,
            self.store,
            self.source,
            self.produced,
            self.video,
            self.ids,
            self.report,
        ) = copy.deepcopy(self.fixture)
        self.adapter = MultipartSubjectEvidenceAdapter()

    def propose(self, **kwargs):
        return self.adapter.propose(
            AdapterRequest.from_store(self.store, self.store.head, ("document",), **kwargs),
            self.artifacts,
            witnesses=collect_witnesses(self.store, self.store.head),
        )

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def record(self, proposal):
        return json.loads(self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content)

    def assert_atomic(self, action):
        before = copy.deepcopy(self.store)
        with self.assertRaises(
            (
                ValueError,
                KeyError,
                TypeError,
                ProposalArtifactError,
                ProposalConflictError,
                ProposalPolicyError,
            )
        ):
            action()
        self.assertEqual(before, self.store)

    def assert_diagnostic(self, reason):
        before = copy.deepcopy(self.store)
        blobs = set(self.artifacts._blobs)
        with self.assertRaises(MultipartSubjectDiagnostic) as caught:
            self.propose()
        self.assertEqual(caught.exception.status, "UNCERTAIN")
        self.assertEqual(caught.exception.reason_codes, (reason,))
        self.assertEqual(before, self.store)
        self.assertEqual(blobs, set(self.artifacts._blobs))

    def changed_proposal(self, proposal, change):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(change,)),
            required_artifact_ids=tuple(dict.fromkeys(r["id"] for r in change.references)),
        )

    def mutate_record(self, proposal, mutation):
        record = self.record(proposal)
        mutation(record)
        snapshot = self.artifacts.import_bytes(
            canonical_bytes(record),
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"profile_identity": PROFILE},
        )
        change = replace(
            proposal.transaction.changes[0], evidence_reference=snapshot.document_reference()
        )
        return self.changed_proposal(proposal, change)

    def new_root_without(self, ids):
        document = self.store.get_document(self.store.head)
        document["references"] = [r for r in document["references"] if r["id"] not in ids]
        self.store = RevisionStore.create(document)

    def test_golden_exact_identity_universe_record_and_only_reference_mutation(self):
        proposal = self.propose()
        record = self.record(proposal)
        subject_key = {
            "ownership_profile_identity": PROFILE,
            "ownership_root_artifact_id": self.source.artifact_id,
            "canonical_source_subject_path": [0],
        }
        subject = "subject:multipart:" + _hash(
            {"identity_domain": DOMAIN, "source_subject_key": subject_key}
        )
        self.assertEqual(record["subject"]["subject_id"], subject)
        self.assertEqual(
            record["parts"],
            [
                {
                    "part_id": "part:multipart:"
                    + _hash(
                        {"identity_domain": DOMAIN, "subject_id": subject, "source_part_key": key}
                    ),
                    "part_key": key,
                }
                for key in ("part-a", "part-b")
            ],
        )
        self.assertEqual(
            record["occurrences"],
            [
                {k: o[k] for k in ("occurrence_id", "frame_index", "tick", "source_timestamp")}
                for o in self.video.occurrences
            ],
        )
        self.assertEqual(len(record["membership"]), 4)
        self.assertEqual(len({m["observation_id"] for m in record["membership"]}), 4)
        self.assertEqual(record["claim_key"], claim_key(record))
        self.assertNotIn("status", record)
        self.assertNotIn("judgment", record)
        self.assertEqual(
            self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content,
            canonical_bytes(record),
        )
        before = self.store.get_document(self.store.head)
        self.accept(proposal)
        after = self.store.get_document(self.store.head)
        self.assertEqual(after["references"][:-1], before["references"])
        self.assertEqual(
            after["references"][-1], proposal.transaction.changes[0].evidence_reference
        )
        self.assertEqual(
            {k: v for k, v in before.items() if k != "references"},
            {k: v for k, v in after.items() if k != "references"},
        )
        self.assertEqual(
            proposal.preview_artifacts[0].content_hash,
            "sha256:45861f9b0ad1723fd3c3b624a7d820042a8e665f72d30cb5b4c80f1a4ba99ad4",
        )

    def test_idempotent_reuses_artifact_and_same_document_child_revision(self):
        first = self.propose()
        self.accept(first)
        before, head, count = (
            self.store.get_document(self.store.head),
            self.store.head,
            len(self.store.revisions),
        )
        blobs = set(self.artifacts._blobs)
        second = self.propose()
        self.assertEqual(first.preview_artifacts, second.preview_artifacts)
        self.assertEqual(blobs, set(self.artifacts._blobs))
        self.accept(second)
        self.assertEqual(
            canonical_bytes(before), canonical_bytes(self.store.get_document(self.store.head))
        )
        self.assertEqual(len(self.store.revisions), count + 1)
        self.assertEqual(self.store.revisions[self.store.head].parent_ids, (head,))
        self.assertEqual(blobs, set(self.artifacts._blobs))

    def test_claim_key_excludes_admission_bookkeeping(self):
        record = self.record(self.propose())
        expected = claim_key(record)
        record["base"] = {"revision_id": "another", "document_hash": "another"}
        record["competing_claims"] = {"claim_artifact_ids": ["another"], "disposition": "ignored"}
        record["artifact_id"] = "another"
        self.assertEqual(claim_key(record), expected)

    def test_ordinary_video_and_resolver_only_source_are_unproven(self):
        self.new_root_without({self.source.artifact_id})
        self.assert_diagnostic("OWNERSHIP_UNPROVEN")
        self.artifacts._blobs.pop(self.source.artifact_id)
        self.assert_diagnostic("OWNERSHIP_UNPROVEN")

    def test_multiple_eligible_sources_abstain(self):
        another = self.artifacts.import_bytes(
            self.source.content + b"\n", media_type="image/svg+xml"
        )
        accept_refs(self.store, another)
        self.assert_diagnostic("AMBIGUOUS_CLOSURE")

    def test_all_request_selectors_reject(self):
        for key in (
            "source",
            "parts",
            "occurrences",
            "p2a_ids",
            "p2b_ids",
            "competing_claims",
            "judgment",
        ):
            with self.subTest(key=key):
                self.assert_atomic(lambda key=key: self.propose(options={key: []}))
        self.assert_atomic(lambda: self.propose(artifact_ids=(self.source.artifact_id,)))

    def test_spec75_report_is_never_read(self):
        self.artifacts._blobs.pop(self.report.artifact_id)
        with patch(
            "svm.authored_raster_production.verify_production",
            side_effect=AssertionError("report trusted"),
        ):
            self.accept(self.propose())

    def test_omitted_dependency_even_if_required_ids_are_rewritten_rejects(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        for index in range(len(original.source_references)):
            with self.subTest(index=index):
                refs = original.source_references[:index] + original.source_references[index + 1 :]
                bad = self.changed_proposal(proposal, replace(original, source_references=refs))
                self.assert_atomic(lambda bad=bad: self.accept(bad))

    def test_forged_base_and_ancestry_reject(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        altered = copy.deepcopy(change.base_document_snapshot)
        altered["references"].pop()
        self.assert_atomic(
            lambda: self.accept(
                self.changed_proposal(proposal, replace(change, base_document_snapshot=altered))
            )
        )
        witnesses = change.witnesses
        for i in range(len(witnesses)):
            with self.subTest(witness=i):
                bad_witness = replace(
                    witnesses[i], revision=replace(witnesses[i].revision, message="forged")
                )
                bad = replace(change, witnesses=(*witnesses[:i], bad_witness, *witnesses[i + 1 :]))
                self.assert_atomic(
                    lambda bad=bad: self.accept(self.changed_proposal(proposal, bad))
                )
                bad = replace(change, witnesses=witnesses[:i] + witnesses[i + 1 :])
                self.assert_atomic(
                    lambda bad=bad: self.accept(self.changed_proposal(proposal, bad))
                )

    def test_recomputed_forged_ancestor_does_not_match_anchored_parent_link(self):
        witnesses = collect_witnesses(self.store, self.store.head)
        item = next(w for w in witnesses if not w.revision.parent_ids)
        changed_doc = copy.deepcopy(item.document)
        changed_doc["references"] = [self.source.document_reference()]
        invented = RevisionStore._make_revision(changed_doc, (), None, "Invented ancestor")
        forged = tuple(
            sorted(
                (
                    replace(w, revision=invented, document=changed_doc) if w == item else w
                    for w in witnesses
                ),
                key=lambda w: w.revision.revision_id,
            )
        )
        with self.assertRaises(ValueError):
            authenticate_witnesses(self.store.head, forged)

    def test_preceding_change_mutation_and_partial_transaction_are_atomic(self):
        proposal = self.propose()
        ref = self.artifacts.import_bytes(
            b"incoming mutation", media_type="text/plain"
        ).document_reference()
        earlier = AppendReferencesChange((ref,))
        bad = replace(
            proposal,
            transaction=replace(
                proposal.transaction, changes=(earlier, *proposal.transaction.changes)
            ),
            required_artifact_ids=(*proposal.required_artifact_ids, ref["id"]),
        )
        self.assert_atomic(lambda: self.accept(bad))
        # First evidence mutation occurs on a candidate only; the second guard fails.
        bad = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=proposal.transaction.changes * 2),
        )
        self.assert_atomic(lambda: self.accept(bad))

    def test_unknown_profile_and_changed_dependency_descriptor_reject(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        self.assert_atomic(
            lambda: self.accept(
                self.changed_proposal(proposal, replace(change, profile_identity="fake"))
            )
        )
        refs = copy.deepcopy(change.source_references)
        refs[0]["media_type"] = "text/plain"
        self.assert_atomic(
            lambda: self.accept(
                self.changed_proposal(proposal, replace(change, source_references=refs))
            )
        )

    def test_record_forgery_matrix(self):
        proposal = self.propose()
        mutations = {
            "profile": lambda r: r.update(profile_identity="fake"),
            "schema": lambda r: r.update(schema_version="fake"),
            "status": lambda r: r.update(status="SUPPORTED"),
            "policy": lambda r: r.update(production_policy="fake"),
            "path": lambda r: r["subject"].update(canonical_source_subject_path=[1]),
            "parts": lambda r: r["parts"].pop(),
            "extra_part": lambda r: r["parts"].append(r["parts"][0]),
            "omit_occurrence": lambda r: r["occurrences"].pop(),
            "duplicate_occurrence": lambda r: r["occurrences"].append(r["occurrences"][0]),
            "membership": lambda r: r["membership"].pop(),
            "reuse": lambda r: r["membership"][1].update(
                observation_id=r["membership"][0]["observation_id"]
            ),
            "contribution": lambda r: r["membership"][0].update(contribution_artifact_id="forged"),
            "label": lambda r: r["membership"][0].update(full_canvas_label_identity="forged"),
            "key": lambda r: r.update(claim_key="forged"),
            "dependency": lambda r: r["dependencies"].pop(),
            "claim_audit": lambda r: r["competing_claims"]["claim_artifact_ids"].append("forged"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                bad = self.mutate_record(proposal, mutate)
                self.assert_atomic(lambda bad=bad: self.accept(bad))

    def test_conflicting_p2a_and_p2b_and_observation_closures_abstain(self):
        for aid in (self.ids[1][0], self.ids[3], self.ids[2]):
            with self.subTest(aid=aid):
                saved = copy.deepcopy(self.store)
                original = self.artifacts.get(aid)
                data = json.loads(original.content)
                data["extra_conflicting_field"] = True
                different = self.artifacts.import_bytes(
                    canonical_bytes(data),
                    media_type=original.media_type,
                    kind=original.kind,
                    provenance=original.provenance,
                )
                accept_refs(self.store, different)
                self.assert_diagnostic("AMBIGUOUS_CLOSURE")
                self.store = saved

    def test_missing_closure_abstains_without_shortlist_fallback(self):
        # Preserve an authentic source-before-video history by branching at the
        # source revision and accepting all inputs except the required slot.
        for aid in (*self.ids[1], self.ids[2], self.ids[3]):
            with self.subTest(aid=aid):
                saved = copy.deepcopy(self.store)
                doc = self.store.get_document(self.store.head)
                self.store.checkout(self.produced.source_revision_id)
                snapshots = [
                    self.artifacts.resolve_reference(r)
                    for r in doc["references"]
                    if r["id"] != aid and r["id"] != self.source.artifact_id
                ]
                accept_refs(self.store, *snapshots)
                self.assert_diagnostic("INCOMPLETE_UNIVERSE")
                self.store = saved

    def test_changed_source_video_frame_and_p2a_bytes_reject(self):
        for aid in (
            self.source.artifact_id,
            self.video.frames[0].artifact_id,
            self.ids[1][0],
            json.loads(self.video.manifest.content)["source_video_reference"]["id"],
        ):
            original = self.artifacts._blobs[aid]
            self.artifacts._blobs[aid] = replace(original, content=original.content + b"tampered")
            self.assert_atomic(self.propose)
            self.artifacts._blobs[aid] = original

    def test_closed_world_authority_and_denied_attach_analysis(self):
        proposal = self.propose()
        authority = change_authority(proposal.transaction.changes[0])
        self.assertEqual(authority.actions, frozenset({"attach_analysis"}))
        self.assertIsNotNone(authority.artifact_verifier)
        self.assertEqual(
            authority.source_revision_resolver(proposal.transaction.changes[0]),
            proposal.base_revision_id,
        )

        class Unregistered(AttachMultipartSubjectEvidenceChange):
            pass

        self.assertIsNone(
            change_authority(Unregistered(**proposal.transaction.changes[0].__dict__))
        )
        # Put a real policy in a new trusted source history, preserving source-before-video.
        source_document = self.store.get_document(self.produced.source_revision_id)
        source_document["edit_permissions"].append(
            {
                "id": "permission:no-multipart",
                "actor": self.adapter.adapter_id,
                "effect": "deny",
                "actions": ["attach_analysis"],
                "targets": ["document"],
            }
        )
        current_refs = self.store.get_document(self.store.head)["references"]
        self.store = RevisionStore.create(source_document)
        accept_refs(
            self.store,
            *(
                self.artifacts.resolve_reference(r)
                for r in current_refs
                if r["id"] != self.source.artifact_id
            ),
        )
        denied = self.propose()
        with self.assertRaisesRegex(ProposalPolicyError, "denies"):
            self.accept(denied)
        self.assert_atomic(lambda: self.accept(denied))

    def test_stale_proposal_is_not_retargeted(self):
        proposal = self.propose()
        extra = self.artifacts.import_bytes(b"other", media_type="text/plain")
        accept_refs(self.store, extra)
        self.assert_atomic(lambda: self.accept(proposal))
        self.assert_atomic(lambda: self.accept(replace(proposal, base_revision_id=self.store.head)))

    def test_incompatible_subject_and_reused_observation_rules(self):
        record = self.record(self.propose())
        changed = copy.deepcopy(record)
        changed["subject"]["subject_id"] = "subject:another"
        with self.assertRaises(MultipartSubjectDiagnostic) as caught:
            _compare_claims(record, changed)
        self.assertEqual(caught.exception.reason_codes, ("INCOMPATIBLE_SUPPORTED_CLAIM",))
        changed = copy.deepcopy(record)
        changed["membership"][0]["part_key"] = "part-b"
        with self.assertRaises(MultipartSubjectDiagnostic) as caught:
            _compare_claims(record, changed)
        self.assertEqual(caught.exception.reason_codes, ("OBSERVATION_REUSED",))

    def test_forged_accepted_claim_is_not_authority(self):
        proposal = self.propose()
        bad = self.mutate_record(
            proposal, lambda r: r["subject"].update(subject_id="subject:forged")
        )
        ref = bad.transaction.changes[0].evidence_reference
        accept_refs(self.store, self.artifacts.resolve_reference(ref))
        self.assert_atomic(self.propose)

    def test_generically_appended_valid_evidence_is_not_accepted_authority(self):
        """Adversarial: byte-valid canonical evidence + wrong admission path.

        Spec76 §10/§13/§19 require the dedicated verifier-backed Change to be
        the only admission authority: valid bytes alone must not equal admitted
        Multipart Subject Evidence, and a generic appended claim must stay
        UNCERTAIN/rejected rather than become an equivalent applicable claim.
        """
        # A/B. Real base A; generate the normal canonical SUPPORTED candidate
        # but do not accept its dedicated proposal. C. Take the exact artifact.
        candidate = self.propose()
        reference = candidate.transaction.changes[0].evidence_reference
        record = self.record(candidate)
        self.assertEqual(record["claim_key"], claim_key(record))
        self.assertNotIn("status", record)
        self.assertNotIn("judgment", record)

        # D. Attach it through the ordinary registered AppendReferencesChange
        # acceptance path (real ProposalAcceptor, unmodified artifact bytes).
        generic = Proposal(
            proposal_id="proposal:test-generic-append",
            base_revision_id=self.store.head,
            generator=GeneratorProvenance("adapter:untrusted-generic-append", "0.1", "svm", "none"),
            transaction=Transaction(
                "transaction:test-generic-append",
                (AppendReferencesChange((reference,)),),
                "Generic attachment of byte-valid Spec76 evidence",
            ),
            required_artifact_ids=(reference["id"],),
        )
        try:
            ProposalAcceptor().accept(self.store, generic, self.artifacts)
        except (ValueError, ProposalArtifactError, ProposalConflictError, ProposalPolicyError):
            return  # Rejected before insertion: also a valid outcome.
        base_b = self.store.head
        self.assertNotEqual(candidate.base_revision_id, base_b)

        # E. The generically attached artifact must not become accepted authority.
        try:
            _, reuse = derive(base_b, collect_witnesses(self.store, base_b), self.artifacts)
        except MultipartSubjectDiagnostic:
            return  # Fail-closed diagnostic without reuse: also a valid outcome.
        self.assertIsNone(
            reuse,
            "valid bytes alone must not equal admitted evidence: the generically "
            f"appended artifact became an equivalent applicable claim ({reuse['id']})",
        )
        repeat = self.propose()
        self.assertNotEqual(
            repeat.transaction.changes[0].evidence_reference["id"],
            reference["id"],
            "the adapter must not reuse a generically appended artifact as admitted",
        )

    def test_stale_claim_from_other_branch_does_not_rebase_or_block(self):
        first = self.propose()
        snapshot = self.artifacts.get(first.preview_artifacts[0].artifact_id)
        doc = self.store.get_document(self.produced.source_revision_id)
        self.store = RevisionStore.create(doc, message="Separate source history")
        all_refs = self.fixture[1].get_document(self.fixture[1].head)["references"]
        accept_refs(
            self.store,
            *(
                self.artifacts.resolve_reference(r)
                for r in all_refs
                if r["id"] != self.source.artifact_id
            ),
            snapshot,
        )
        fresh = self.propose()
        self.assertNotEqual(
            first.preview_artifacts[0].artifact_id, fresh.preview_artifacts[0].artifact_id
        )
        self.assertEqual(self.record(first)["claim_key"], self.record(fresh)["claim_key"])
        self.assertEqual(self.artifacts.get(snapshot.artifact_id), snapshot)
        self.accept(fresh)

    def test_irrelevant_accepted_reference_changes_no_claim_facts(self):
        first = self.record(self.propose())
        extra = self.artifacts.import_bytes(b"unrelated data", media_type="text/plain")
        accept_refs(self.store, extra)
        second = self.record(self.propose())
        self.assertEqual(first["claim_key"], second["claim_key"])
        self.assertEqual(first["dependencies"], second["dependencies"])

    def test_current_applicable_claim_reuses_after_unrelated_revision(self):
        first = self.propose()
        self.accept(first)
        old = self.artifacts.get(first.preview_artifacts[0].artifact_id)
        accept_refs(self.store, self.artifacts.import_bytes(b"irrelevant", media_type="text/plain"))
        before = set(self.artifacts._blobs)
        repeat = self.propose()
        self.assertEqual(first.preview_artifacts, repeat.preview_artifacts)
        self.assertEqual(before, set(self.artifacts._blobs))
        self.accept(repeat)
        self.assertEqual(self.artifacts.get(old.artifact_id), old)

    def test_source_grammar_failures_cannot_be_admitted(self):
        for content in (
            self.source.content.replace(b"<g>", b'<g id="wrong-subject">'),
            self.source.content.replace(b'id="part-b"', b'id="part-c"'),
            self.source.content.replace(
                b"M 20 20 L 100 20 L 20 80 Z", b"M 20 20 L 24 20 L 20 23 Z"
            ),
        ):
            source = self.artifacts.import_bytes(content, media_type="image/svg+xml")
            source_document = self.store.get_document(self.produced.source_revision_id)
            source_document["references"] = [source.document_reference()]
            saved = self.store
            self.store = RevisionStore.create(source_document)
            current_refs = saved.get_document(saved.head)["references"]
            accept_refs(
                self.store,
                *(
                    self.artifacts.resolve_reference(r)
                    for r in current_refs
                    if r["id"] != self.source.artifact_id
                ),
            )
            self.assert_atomic(self.propose)
            self.store = saved

    def test_manifest_selection_cannot_trust_claimed_frame_ids(self):
        original = self.video.manifest
        payload = json.loads(original.content)
        payload["occurrences"][0]["raster_artifact_id"] = self.source.artifact_id
        payload["occurrences"][1]["raster_artifact_id"] = self.source.artifact_id
        fake = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        accept_refs(self.store, fake)
        self.assert_atomic(self.propose)

    def test_unrelated_valid_manifest_does_not_select_a_different_claim(self):
        from test_authored_raster_production import ROOT

        first = self.propose()
        self.accept(first)
        video = self.artifacts.import_bytes(
            (ROOT / "examples/038-controlled-video-ingestion/scene.avi").read_bytes(),
            media_type="video/x-msvideo",
        )
        other = ingest_video(
            self.artifacts, video.document_reference(), VideoSampling((0, 1), 12, (1, 1))
        )
        accept_refs(self.store, video, *other.frames, other.manifest)
        repeat = self.propose()
        self.assertEqual(first.preview_artifacts, repeat.preview_artifacts)
        self.accept(repeat)

    def test_two_independently_replayed_byte_different_subjects_conflict(self):
        first = self.record(self.propose())
        artifacts, store, *_ = pipeline(self.source.content + b"\n")
        second = self.adapter.propose(
            AdapterRequest.from_store(store, store.head, ("document",)),
            artifacts,
            witnesses=collect_witnesses(store, store.head),
        )
        second_record = json.loads(artifacts.get(second.preview_artifacts[0].artifact_id).content)
        self.assertNotEqual(first["subject"]["subject_id"], second_record["subject"]["subject_id"])
        with self.assertRaises(MultipartSubjectDiagnostic) as caught:
            _compare_claims(first, second_record)
        self.assertEqual(caught.exception.reason_codes, ("INCOMPATIBLE_SUPPORTED_CLAIM",))

    def test_swapped_and_reused_observations_reject_at_acceptance(self):
        proposal = self.propose()

        def reused(record):
            record["membership"][1]["observation_id"] = record["membership"][0]["observation_id"]

        with self.assertRaisesRegex(ProposalArtifactError, "OBSERVATION_REUSED"):
            self.accept(self.mutate_record(proposal, reused))

        def swapped(record):
            a, b = record["membership"][:2]
            a["observation_id"], b["observation_id"] = b["observation_id"], a["observation_id"]

        self.assert_atomic(lambda: self.accept(self.mutate_record(proposal, swapped)))

    def test_removing_unrelated_historical_reference_preserves_applicability(self):
        extra = self.artifacts.import_bytes(b"temporary unrelated input", media_type="text/plain")
        accept_refs(self.store, extra)
        first = self.propose()
        self.accept(first)

        class RemoveUnrelatedReference:
            def apply(inner, document):
                document["references"] = [
                    r for r in document["references"] if r["id"] != extra.artifact_id
                ]

        # Trusted host fixture mutation, not a registered Adapter acceptance primitive.
        self.store.commit(
            self.store.head,
            Transaction("transaction:remove-unrelated", (RemoveUnrelatedReference(),)),
        )
        self.artifacts._blobs.pop(extra.artifact_id)
        repeat = self.propose()
        self.assertEqual(first.preview_artifacts, repeat.preview_artifacts)
        self.accept(repeat)


if __name__ == "__main__":
    unittest.main()
