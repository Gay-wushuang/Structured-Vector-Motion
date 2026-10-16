"""G2 registered assembly acceptance; no production Producer or new Golden."""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import asdict, replace

from authored_group_test_support import (
    EXTENSION,
    NEUTRAL_TRANSFORM,
    ROOT,
    make_accepted_base,
    make_change,
    make_proposal,
)

from svm import AdapterRequest, ArtifactStore, Evaluator, ProposalAcceptor, RevisionStore
from svm.adapters.svg_import import SVGImportAdapter
from svm.admission_history import dump_trusted_history, history_digest, load_trusted_history
from svm.document import validate_document
from svm.evaluator import canonical_bytes
from svm.proposals import ProposalArtifactError
from svm.renderers import SVGRenderer
from svm.revisions import AdmittedRevision, Revision, SetGroupTransformChange
from svm.scene import build_evaluated_scene


def render(document):
    return SVGRenderer().render(build_evaluated_scene(document, Evaluator(document)))


class AuthoredGroupAssemblyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = make_accepted_base()

    def setUp(self):
        self.store, self.artifacts = copy.deepcopy(self.fixture)
        self.base = self.store.get_document(self.store.head)
        self.members = tuple(sorted(e["id"] for e in self.base["entities"]))

    def accept(self, change, *, store=None):
        store = store or self.store
        return ProposalAcceptor().accept(store, make_proposal(store, (change,)))

    def reject(self, change):
        before = copy.deepcopy(self.store)
        with self.assertRaises(ProposalArtifactError):
            self.accept(change)
        self.assertEqual(self.store, before)

    def assert_only_group_append(self, before, after, group):
        expected = copy.deepcopy(before)
        expected.setdefault("groups", []).append(copy.deepcopy(group))
        self.assertEqual(canonical_bytes(after), canonical_bytes(expected))
        validate_document(after, EXTENSION)

    def test_real_promoted_inputs_have_full_accepted_origins(self):
        self.assertEqual(len(self.store.revisions), 5)
        self.assertEqual(len(self.members), 4)
        tuples = {
            tuple(e["provenance"][k] for k in ("artifact_id", "candidate_id", "component_digest"))
            for e in self.base["entities"]
        }
        self.assertEqual(len(tuples), 4)
        self.assertTrue(
            all(e["provenance"]["type"] == "PromotedComponent" for e in self.base["entities"])
        )
        self.assertFalse(self.base.get("groups"))
        self.assertTrue(self.base["structural_relations"])

    def test_null_neutral_and_non_neutral_accept_append_only_and_no_pixels(self):
        transforms = (
            None,
            NEUTRAL_TRANSFORM,
            {"translate": [2, 3], "rotation_degrees": 90, "scale": 2, "origin": [1, 1]},
        )
        for transform in transforms:
            with self.subTest(transform=transform):
                store = copy.deepcopy(self.store)
                old = copy.deepcopy(store)
                change = make_change(store, transform=transform)
                proposal = make_proposal(store, (change,))
                self.assertEqual(change.references, ())
                self.assertEqual(proposal.required_artifact_ids, ())
                preview = ProposalAcceptor().validate(store, proposal)
                self.assertEqual(store, old)
                revision = ProposalAcceptor().accept(store, proposal)
                after = store.get_document(revision.revision_id)
                self.assert_only_group_append(self.base, after, change.group)
                self.assertEqual(preview, after)
                self.assertEqual(len(store.revisions), len(old.revisions) + 1)
                self.assertIs(type(revision), Revision)
                self.assertEqual(render(after), render(self.base))
                self.assertEqual("transform" in change.group, transform is not None)
                for rid in old.revisions:
                    self.assertEqual(store.revisions[rid], old.revisions[rid])
                    self.assertEqual(store.get_document(rid), old.get_document(rid))

    def test_two_disjoint_groups_use_real_successive_bases(self):
        first = make_change(self.store, self.members[:2], NEUTRAL_TRANSFORM)
        first_revision = self.accept(first)
        first_document = self.store.get_document(self.store.head)
        second = make_change(self.store, self.members[2:], NEUTRAL_TRANSFORM)
        self.assertEqual(second.source_revision_id, first_revision.revision_id)
        self.assertEqual(second.base_document_snapshot, first_document)
        self.assertEqual(second.base_document_snapshot["groups"], [first.group])
        self.accept(second)
        self.assert_only_group_append(
            first_document, self.store.get_document(self.store.head), second.group
        )
        self.assertNotEqual(first.group["id"], second.group["id"])
        self.assertTrue(set(first.member_ids).isdisjoint(second.member_ids))

    def test_replay_and_trusted_history_preserve_content_and_revision(self):
        left, right = copy.deepcopy(self.store), copy.deepcopy(self.store)
        first, replay = make_change(left), make_change(right)
        self.assertEqual(first, replay)
        self.assertEqual(make_proposal(left, (first,)), make_proposal(right, (replay,)))
        lrev, rrev = self.accept(first, store=left), self.accept(replay, store=right)
        self.assertEqual(lrev, rrev)
        self.assertEqual(left, right)
        payload = dump_trusted_history(left)
        trusted_digest = history_digest(payload)
        restored = load_trusted_history(
            json.loads(json.dumps(payload)), trusted_history_hash=trusted_digest
        )
        self.assertEqual(restored, left)
        self.assertEqual(dump_trusted_history(restored), payload)

    def test_later_transform_preserves_birth_and_old_snapshot(self):
        change = make_change(self.store)
        birth = self.accept(change)
        birth_document = self.store.get_document(birth.revision_id)
        transform = SetGroupTransformChange(change.group["id"], copy.deepcopy(NEUTRAL_TRANSFORM))
        revision = ProposalAcceptor().accept(self.store, make_proposal(self.store, (transform,)))
        edited = self.store.get_document(revision.revision_id)["groups"][0]
        self.assertEqual({k: v for k, v in edited.items() if k != "transform"}, change.group)
        self.assertEqual(self.store.get_document(birth.revision_id), birth_document)

    def test_same_member_identity_ignores_base_and_existing_id_rejects(self):
        first = make_change(self.store)
        self.accept(first)
        later = make_change(self.store, first.member_ids)
        self.assertEqual(later.group["id"], first.group["id"])
        self.assertNotEqual(later.group["provenance"], first.group["provenance"])
        self.reject(later)

    def test_overlap_is_only_forbidden_when_both_groups_have_transforms(self):
        self.accept(make_change(self.store, self.members[:2], NEUTRAL_TRANSFORM))
        overlapping = (self.members[0], self.members[2])
        self.reject(make_change(self.store, overlapping, NEUTRAL_TRANSFORM))
        before = self.store.get_document(self.store.head)
        untransformed = make_change(self.store, overlapping)
        self.accept(untransformed)
        self.assert_only_group_append(
            before, self.store.get_document(self.store.head), untransformed.group
        )

    def test_member_domain_cardinality_duplicates_and_order_fail_atomically(self):
        for members in (
            (),
            self.members[:1],
            (self.members[0], self.members[0]),
            tuple(reversed(self.members[:2])),
            (self.members[0], "entity:unknown"),
            (self.members[0], "group:" + "a" * 64),
            (self.members[0], "malformed"),
        ):
            with self.subTest(members=members):
                self.reject(make_change(self.store, members))
        original = make_change(self.store)
        self.reject(replace(original, member_ids=list(original.member_ids)))

    def test_closed_change_field_types_fail_atomically(self):
        original = make_change(self.store)
        for fields in (
            {"authority_identity": "caller"},
            {"source_revision_id": "revision:" + "f" * 64},
            {"base_document_snapshot": []},
            {"base_revision": asdict(original.base_revision)},
            {"member_ids": None},
            {"group": []},
        ):
            with self.subTest(fields=fields):
                self.reject(replace(original, **fields))

    def test_group_and_provenance_payload_are_exact_not_self_authenticating(self):
        mutations = (
            lambda g: g.update(id="group:" + "f" * 64),
            lambda g: g.update(kind="caller-group"),
            lambda g: g.update(extra=True),
            lambda g: g.update(parent_id="group:" + "b" * 64),
            lambda g: g["members"].reverse(),
            lambda g: g["members"].append(self.members[2]),
            lambda g: g.pop("provenance"),
            lambda g: g["provenance"].update(type="authored-group-assembly@0.2"),
            lambda g: g["provenance"].update(authority_identity="caller"),
            lambda g: g["provenance"].update(membership_hash="sha256:" + "0" * 64),
            lambda g: g["provenance"].update(source_document_hash="sha256:" + "0" * 64),
            lambda g: g["provenance"].update(source_revision_id="revision:" + "0" * 64),
            lambda g: g["provenance"].update(inference_artifact_id="artifact:" + "0" * 64),
            lambda g: g.update(transform=None),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                change = make_change(self.store)
                mutate(change.group)
                self.reject(change)

    def test_transform_validation_rejects_bad_types_shape_and_numbers(self):
        transforms = [{}, {**NEUTRAL_TRANSFORM, "extra": 0}]
        for field, values in (
            ("scale", (0, -1, True, float("nan"), float("inf"), 10**400, "1")),
            ("rotation_degrees", (False, float("inf"), "0")),
            ("translate", ([0], [0, 0, 0], [True, 0], [float("nan"), 0], (0, 0))),
            ("origin", ([0], [False, 0], [0, float("inf")])),
        ):
            transforms.extend({**NEUTRAL_TRANSFORM, field: value} for value in values)
        for transform in transforms:
            with self.subTest(transform=transform):
                self.reject(make_change(self.store, transform=transform))

    def test_complete_snapshot_and_witness_fields_are_authenticated(self):
        original = make_change(self.store)
        for fields in (
            {"message": original.base_revision.message + " altered"},
            {"transaction_id": "transaction:other"},
            {"document_hash": "sha256:" + "0" * 64},
            {"revision_id": "revision:" + "0" * 64},
            {"parent_ids": ()},
            {"parent_ids": list(original.base_revision.parent_ids)},
        ):
            with self.subTest(fields=fields):
                self.reject(
                    replace(original, base_revision=replace(original.base_revision, **fields))
                )
        for mutate in (
            lambda d: d["entities"].pop(),
            lambda d: d["references"].pop(),
            lambda d: d["entities"][0].update(name="forged"),
            lambda d: d["structural_relations"].clear(),
        ):
            change = make_change(self.store)
            mutate(change.base_document_snapshot)
            self.reject(change)

    def test_rehashed_reduced_snapshot_cannot_change_real_proposal_base(self):
        change = make_change(self.store)
        reduced = copy.deepcopy(change.base_document_snapshot)
        reduced["entities"][0]["name"] += " forged"
        witness = RevisionStore._make_revision(
            reduced,
            change.base_revision.parent_ids,
            change.base_revision.transaction_id,
            change.base_revision.message,
        )
        forged = replace(
            change,
            source_revision_id=witness.revision_id,
            base_revision=witness,
            base_document_snapshot=reduced,
        )
        self.reject(forged)

    def test_nested_subclasses_cycles_and_extra_witness_hooks_never_execute(self):
        calls = []

        class HostileDict(dict):
            def __iter__(self):
                calls.append("iterate")
                raise AssertionError("Caller iteration must not run")

            def __deepcopy__(self, memo):
                calls.append("deepcopy")
                raise AssertionError("Caller deepcopy must not run")

        class HostileString(str):
            def __eq__(self, other):
                calls.append("equality")
                raise AssertionError("Caller equality must not run")

            def __deepcopy__(self, memo):
                calls.append("string deepcopy")
                raise AssertionError("Caller deepcopy must not run")

        for location in ("snapshot", "group", "transform", "source", "member"):
            with self.subTest(location=location):
                change = make_change(self.store)
                if location == "snapshot":
                    change.base_document_snapshot["entities"][0] = HostileDict(
                        change.base_document_snapshot["entities"][0]
                    )
                elif location == "group":
                    change.group["provenance"] = HostileDict(change.group["provenance"])
                elif location == "transform":
                    change = replace(change, initial_transform=HostileDict(NEUTRAL_TRANSFORM))
                elif location == "source":
                    change = replace(
                        change, source_revision_id=HostileString(change.source_revision_id)
                    )
                else:
                    change = replace(
                        change,
                        member_ids=(HostileString(change.member_ids[0]), change.member_ids[1]),
                    )
                self.reject(change)
                self.assertEqual(calls, [])

        for location in ("snapshot", "group"):
            change = make_change(self.store)
            target = change.base_document_snapshot if location == "snapshot" else change.group
            target["cycle"] = target
            self.reject(change)
            self.assertEqual(calls, [])

        change = make_change(self.store)

        def hostile_copy(memo):
            calls.append("witness deepcopy")
            raise AssertionError("Extra witness hook must not run")

        object.__setattr__(change.base_revision, "__deepcopy__", hostile_copy)
        self.reject(change)
        self.assertEqual(calls, [])

    def test_empty_admitted_witness_is_not_an_ordinary_revision(self):
        change = make_change(self.store)
        ordinary = change.base_revision
        empty_admitted = AdmittedRevision(
            ordinary.revision_id,
            ordinary.parent_ids,
            ordinary.transaction_id,
            ordinary.document_hash,
            ordinary.message,
            (),
        )
        self.reject(replace(change, base_revision=empty_admitted))


class AuthoredGroupRenderedAcceptanceTest(unittest.TestCase):
    def test_real_svg_import_members_keep_geometry_and_compose_static_transform(self):
        artifacts = ArtifactStore()
        store = RevisionStore.create(
            json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_bytes())
        )
        source = artifacts.import_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg"><rect id="a" x="0" y="0" width="2" height="3"/>'
            b'<ellipse id="b" cx="4" cy="1" rx="1" ry="2"/></svg>',
            media_type="image/svg+xml",
        )
        proposal = SVGImportAdapter().propose(
            AdapterRequest.from_store(
                store, store.head, ("document",), artifact_ids=(source.artifact_id,)
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        store.upgrade_document_dialect(EXTENSION)
        before = store.get_document(store.head)
        original_scene = build_evaluated_scene(before, Evaluator(before))
        for transform in (None, NEUTRAL_TRANSFORM, {**NEUTRAL_TRANSFORM, "translate": [3, 4]}):
            with self.subTest(transform=transform):
                branch = copy.deepcopy(store)
                change = make_change(branch, transform=transform)
                ProposalAcceptor().accept(branch, make_proposal(branch, (change,)))
                after = branch.get_document(branch.head)
                expected = copy.deepcopy(before)
                expected["groups"] = [change.group]
                self.assertEqual(after, expected)
                scene = build_evaluated_scene(after, Evaluator(after))
                for old, new in zip(original_scene.entities, scene.entities, strict=True):
                    self.assertEqual(old.entity_id, new.entity_id)
                    self.assertEqual(old.geometry_value_id, new.geometry_value_id)
                    if transform is None:
                        self.assertEqual(new, old)
                    else:
                        self.assertEqual(new.geometry["source"], old.geometry)
                        self.assertEqual(
                            new.geometry["matrix"], [1, 0, 0, 1, *transform["translate"]]
                        )
                if transform is None:
                    self.assertEqual(render(before), render(after))


class AuthoredGroupAdmittedBaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_representation_target_consumer import RepresentationTargetConsumerTest

        RepresentationTargetConsumerTest.setUpClass()
        cls.fixture = copy.deepcopy(RepresentationTargetConsumerTest.fixture["store"])
        cls.fixture.upgrade_document_dialect(EXTENSION)

    def test_real_spec80_admitted_witness_accepts_without_history_or_new_admission(self):
        store = copy.deepcopy(self.fixture)
        base = store.get_document(store.head)
        change = make_change(store)
        self.assertIs(type(change.base_revision), AdmittedRevision)
        self.assertTrue(change.base_revision.admissions)
        history = copy.deepcopy(store)
        revision = ProposalAcceptor().accept(store, make_proposal(store, (change,)))
        self.assertIs(type(revision), Revision)
        expected = copy.deepcopy(base)
        expected.setdefault("groups", []).append(change.group)
        self.assertEqual(store.get_document(store.head), expected)
        for rid in history.revisions:
            self.assertEqual(store.revisions[rid], history.revisions[rid])
            self.assertEqual(store.get_document(rid), history.get_document(rid))

    def test_omitted_or_tampered_real_admissions_reject_atomically(self):
        original = make_change(self.fixture)
        ordinary = Revision(
            **{k: v for k, v in asdict(original.base_revision).items() if k != "admissions"}
        )
        event = original.base_revision.admissions[0]
        witnesses = (
            ordinary,
            replace(original.base_revision, admissions=()),
            replace(
                original.base_revision, admissions=(replace(event, authority_identity="forged"),)
            ),
            replace(original.base_revision, admissions=list(original.base_revision.admissions)),
        )
        for witness in witnesses:
            with self.subTest(witness=witness):
                store = copy.deepcopy(self.fixture)
                before = copy.deepcopy(store)
                change = replace(make_change(store), base_revision=witness)
                with self.assertRaises(ProposalArtifactError):
                    ProposalAcceptor().accept(store, make_proposal(store, (change,)))
                self.assertEqual(store, before)


if __name__ == "__main__":
    unittest.main()
