"""Real authority coexistence and separately labelled trusted-Change unit checks."""

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import jsonschema
import test_svg_group_construction as construction_tests
from test_svg_group_construction import ROOT, SOURCE

import tests.test_pop_group_candidates as qv1
from svm import (
    AdapterRequest,
    ArtifactKind,
    GeneratorProvenance,
    Proposal,
    ProposalAcceptor,
    RevisionStore,
    Transaction,
)
from svm.adapters import POPGroupCandidateAdapter, POPGroupPromotionAdapter
from svm.adapters.svg_group_construction import SVGGroupConstructionAdapter
from svm.adapters.svg_import import SVGImportAdapter
from svm.document import validate_document
from svm.evaluator import canonical_bytes
from svm.revisions import PromotedGroup, PromoteGroupsChange, SetGroupTransformChange


def deny(action, target="*"):
    return {
        "id": "permission:group-test",
        "actor": "*",
        "effect": "deny",
        "actions": [action],
        "targets": [target],
    }


def schema(document):
    jsonschema.validate(
        document, json.loads((ROOT / "schema/svm-document-v0.1.schema.json").read_text())
    )


class SourceSelectionTest(unittest.TestCase):
    def setUp(self):
        self.helper = construction_tests.SVGGroupConstructionTest()
        self.helper.setUp()

    def test_derived_svg_counts_do_not_select_sources(self):
        h = self.helper
        base = h.store.get_document(h.store.head)
        for count in (0, 1, 3):
            with self.subTest(count=count):
                doc = copy.deepcopy(base)
                for index in range(count):
                    artifact = h.artifacts.import_bytes(
                        b"<svg/>" + b" " * index,
                        media_type="image/svg+xml",
                        kind=ArtifactKind.DERIVED,
                    )
                    doc["references"].append(artifact.document_reference())
                h.rebase_document(doc)
                ProposalAcceptor().accept(h.store, h.propose(), h.artifacts)
                self.assertEqual(len(h.store.get_document(h.store.head)["groups"]), 1)

    def test_ambiguous_alias_and_descriptor_mismatch_reject(self):
        h = self.helper
        base = h.store.get_document(h.store.head)
        for mode in ("alias", "descriptor", "derived-only", "resolver-only"):
            with self.subTest(mode=mode):
                doc = copy.deepcopy(base)
                if mode == "alias":
                    a = h.artifacts.import_bytes(SOURCE + b" ", media_type="application/svg+xml")
                    doc["references"].append(a.document_reference())
                elif mode == "descriptor":
                    doc["references"][0]["import_metadata"]["provenance"] = {"fake": True}
                elif mode == "derived-only":
                    a = h.artifacts.import_bytes(
                        SOURCE, media_type="image/svg+xml", kind=ArtifactKind.DERIVED
                    )
                    doc["references"] = [a.document_reference()]
                else:
                    doc["references"] = []
                h.rebase_document(doc)
                with self.assertRaises(ValueError):
                    h.propose()

    def test_birth_policy_separation_for_construction(self):
        h = self.helper
        base = h.store.get_document(h.store.head)
        for action in ("promote_group", "establish_group"):
            doc = copy.deepcopy(base)
            doc["edit_permissions"] = [deny(action)]
            schema(doc)
            h.rebase_document(doc)
            proposal = h.propose()
            if action == "establish_group":
                h.unchanged(proposal)
            else:
                ProposalAcceptor().accept(h.store, proposal, h.artifacts)

    def test_existing_group_transform_policy_and_missing_target(self):
        h = self.helper
        ProposalAcceptor().accept(h.store, h.propose(), h.artifacts)
        doc = h.store.get_document(h.store.head)
        group = doc["groups"][0]
        doc["edit_permissions"] = [deny("set_group_transform", group["id"])]
        schema(doc)
        h.rebase_document(doc)
        transform = copy.deepcopy(group["transform"])
        transform["translate"] = [5, 0]
        proposal = Proposal(
            "proposal:policy",
            h.store.head,
            GeneratorProvenance("adapter:test", "1", "test", "1"),
            Transaction("transaction:policy", (SetGroupTransformChange(group["id"], transform),)),
        )
        h.unchanged(proposal)
        doc["edit_permissions"][0]["targets"] = ["group:" + "f" * 64]
        with self.assertRaisesRegex(ValueError, "missing targets"):
            validate_document(doc)


class RealCoexistenceTest(unittest.TestCase):
    def build_pop(self, policy=None):
        create = RevisionStore.create

        def initial(doc, message="Initial revision"):
            doc = copy.deepcopy(doc)
            if policy:
                doc["edit_permissions"] = [policy]
            return create(doc, message)

        with patch.object(RevisionStore, "create", side_effect=initial):
            setup = qv1.POPGroupCandidatesGoldenQv1Test()
            setup.setUp()
        store, artifacts = setup.store, setup.artifacts
        inference = POPGroupCandidateAdapter().propose(setup.request(), artifacts)
        ProposalAcceptor().accept(store, inference, artifacts)
        aid = inference.preview_artifacts[0].artifact_id
        payload = json.loads(artifacts.get(aid).content)
        candidate = next(c for c in payload["candidates"] if c["status"] == "SUPPORTED")
        request = AdapterRequest.from_store(
            store,
            store.head,
            ("document",),
            artifact_ids=(aid,),
            options={"candidate_ids": [candidate["candidate_id"]]},
        )
        proposal = POPGroupPromotionAdapter().propose(request, artifacts)
        return store, artifacts, proposal

    def test_real_pop_then_spec73_and_old_candidate_stays_stale(self):
        store, artifacts, legacy = self.build_pop()
        accept = ProposalAcceptor()
        accept.accept(store, legacy, artifacts)
        old_group = copy.deepcopy(store.get_document(store.head)["groups"][0])
        source = artifacts.import_bytes(SOURCE, media_type="image/svg+xml")
        request = AdapterRequest.from_store(
            store, store.head, ("document",), artifact_ids=(source.artifact_id,)
        )
        accept.accept(store, SVGImportAdapter().propose(request, artifacts), artifacts)
        doc = store.get_document(store.head)
        self.assertEqual(
            sum(
                r["media_type"] == "image/svg+xml"
                and r["import_metadata"]["artifact_kind"] == "DerivedArtifact"
                for r in doc["references"]
            ),
            2,
        )
        request = AdapterRequest.from_store(store, store.head, ("document",))
        construction = SVGGroupConstructionAdapter().propose(
            request, artifacts, base_revision=store.revisions[store.head]
        )
        count, head = len(store.revisions), store.head
        accept.validate(store, construction, artifacts)
        self.assertEqual(store.head, head)
        result = accept.accept(store, construction, artifacts)
        self.assertEqual(result.parent_ids, (head,))
        self.assertEqual(len(store.revisions), count + 1)
        final = store.get_document(store.head)
        self.assertEqual(canonical_bytes(final["groups"][0]), canonical_bytes(old_group))
        self.assertEqual(len({g["id"] for g in final["groups"]}), 2)
        new = final["groups"][1]
        self.assertEqual(
            set(new["provenance"]),
            {"type", "authority_identity", "profile_identity", "construction_artifact_id"},
        )
        validate_document(final)
        schema(final)
        # Retargeting the envelope cannot turn old evidence into current authority.
        with self.assertRaisesRegex(ValueError, "STALE_CANDIDATE"):
            accept.accept(store, replace(legacy, base_revision_id=store.head), artifacts)
        self.assertEqual(final, store.get_document(store.head))

    def test_real_legacy_policy_separation(self):
        for action in ("promote_group", "establish_group"):
            with self.subTest(action=action):
                store, artifacts, proposal = self.build_pop(deny(action))
                schema(store.get_document(store.head))
                before = (store.head, len(store.revisions))
                if action == "promote_group":
                    with self.assertRaisesRegex(RuntimeError, "denies"):
                        ProposalAcceptor().accept(store, proposal, artifacts)
                    self.assertEqual(before, (store.head, len(store.revisions)))
                else:
                    ProposalAcceptor().accept(store, proposal, artifacts)
                    self.assertEqual(len(store.get_document(store.head)["groups"]), 1)


class MixedOriginApplyUnitTest(unittest.TestCase):
    """Trusted apply compatibility ONLY; these records do not prove POP authority."""

    def setUp(self):
        h = construction_tests.SVGGroupConstructionTest()
        h.setUp()
        ProposalAcceptor().accept(h.store, h.propose(), h.artifacts)
        self.document = h.store.get_document(h.store.head)
        self.construction = copy.deepcopy(self.document["groups"][0])
        a = h.artifacts.import_bytes(
            b"unit inference placeholder",
            media_type="application/vnd.svm.pop-group-candidates+json",
            kind=ArtifactKind.DERIVED,
        )
        self.reference = a.document_reference()
        self.document["references"].append(self.reference)
        self.members = tuple(sorted(e["id"] for e in self.document["entities"][:2]))
        self.document["groups"].append(self.record("1").to_definition())
        validate_document(self.document)

    def record(self, digit):
        source = copy.deepcopy(self.document)
        source["references"] = [r for r in source["references"] if r["id"] != self.reference["id"]]
        return PromotedGroup(
            self.reference["id"],
            "candidate:group:" + digit * 64,
            "inference:group:" + digit * 64,
            self.members,
            "sha256:" + hashlib.sha256(canonical_bytes(source)).hexdigest(),
        )

    def test_append_dedup_and_global_collision(self):
        record = self.record("2")
        PromoteGroupsChange((record,), (self.reference,)).apply(self.document)
        self.assertEqual(self.document["groups"][0], self.construction)
        self.assertEqual(self.document["groups"][-1], record.to_definition())
        validate_document(self.document)
        with self.assertRaisesRegex(ValueError, "already promoted"):
            PromoteGroupsChange((self.record("2"),), (self.reference,)).apply(self.document)
        next_record = self.record("3")
        self.document["groups"][0]["id"] = next_record.group_id()
        with self.assertRaisesRegex(ValueError, "ID collision"):
            PromoteGroupsChange((self.record("3"),), (self.reference,)).apply(self.document)

    def test_transformed_membership_remains_enforced(self):
        record = self.record("2")
        PromoteGroupsChange((record,), (self.reference,)).apply(self.document)
        self.document["groups"][-1]["members"] = list(self.construction["members"])
        self.document["groups"][-1]["transform"] = copy.deepcopy(self.construction["transform"])
        with self.assertRaisesRegex(ValueError, "multiple transformed"):
            validate_document(self.document)
