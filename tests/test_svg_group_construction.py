import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

import jsonschema

from svm import AdapterRequest, ArtifactKind, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters.svg_group_construction import (
    SVGGroupConstructionAdapter,
    SVGGroupConstructionError,
)
from svm.adapters.svg_import import SVGImportAdapter
from svm.change_authority import resolve_transaction_intents
from svm.document import validate_document
from svm.evaluator import Evaluator, canonical_bytes
from svm.renderers import SVGRenderer
from svm.revisions import SetOperationParameterChange, Transaction
from svm.scene import build_evaluated_scene

ROOT = Path(__file__).resolve().parents[1]
SOURCE = b"""<svg xmlns="http://www.w3.org/2000/svg"><g>
<rect x="0" y="0" width="20" height="10"/>
<ellipse cx="30" cy="5" rx="5" ry="3"/>
</g></svg>"""


class SVGGroupConstructionTest(unittest.TestCase):
    def setUp(self):
        self.artifacts = ArtifactStore()
        self.store = RevisionStore.create(
            json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        )
        source = self.artifacts.import_bytes(SOURCE, media_type="image/svg+xml")
        request = AdapterRequest.from_store(
            self.store, self.store.head, ("document",), artifact_ids=(source.artifact_id,)
        )
        ProposalAcceptor().accept(
            self.store, SVGImportAdapter().propose(request, self.artifacts), self.artifacts
        )

    def propose(self):
        return SVGGroupConstructionAdapter().propose(
            AdapterRequest.from_store(self.store, self.store.head, ("document",)),
            self.artifacts,
            base_revision=self.store.revisions[self.store.head],
        )

    def unchanged(self, proposal):
        before = (
            self.store.head,
            len(self.store.revisions),
            self.store.get_document(self.store.head),
        )
        with self.assertRaises((ValueError, RuntimeError)):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        self.assertEqual(
            before,
            (self.store.head, len(self.store.revisions), self.store.get_document(self.store.head)),
        )

    def test_golden_preview_atomic_and_deterministic(self):
        before = self.store.get_document(self.store.head)
        proposal = self.propose()
        self.assertEqual(proposal, self.propose())
        candidate = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(len(candidate["entities"]), len(before["entities"]) + 2)
        self.assertEqual(candidate["entities"][:2], before["entities"])
        group = candidate["groups"][0]
        self.assertEqual(group["transform"]["origin"], [17.5, 5])
        self.assertEqual(len(group["members"]), 2)
        self.assertEqual(group["provenance"]["type"], "construction-established-group@0.1")
        self.assertNotIn("candidate_id", group["provenance"])
        jsonschema.validate(
            candidate, json.loads((ROOT / "schema/svm-document-v0.1.schema.json").read_text())
        )
        first_render = SVGRenderer().render(build_evaluated_scene(candidate, Evaluator(candidate)))
        self.assertEqual(
            first_render,
            SVGRenderer().render(build_evaluated_scene(candidate, Evaluator(candidate))),
        )
        self.assertEqual(len(build_evaluated_scene(candidate, Evaluator(candidate)).entities), 4)
        self.assertEqual(
            candidate["construction"]["operations"][:2], before["construction"]["operations"]
        )
        self.assertEqual(candidate["presentation"]["styles"][:2], before["presentation"]["styles"])
        self.assertFalse(candidate.get("motion_target_bindings"))
        receipt = json.loads(
            self.artifacts.resolve_reference(proposal.transaction.changes[0].references[-1]).content
        )
        self.assertIsNone(receipt["representation_claim"])
        count = len(self.store.revisions)
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        self.assertEqual(len(self.store.revisions), count + 1)
        self.assertEqual(
            canonical_bytes(self.store.get_document(self.store.head)), canonical_bytes(candidate)
        )

    def test_forged_fragment_and_snapshot_reject_atomically(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        for label in ("geometry", "snapshot"):
            with self.subTest(label=label):
                change = copy.deepcopy(original)
                if label == "geometry":
                    change.fragment.operations[0]["parameters"]["width"] = 99.0
                else:
                    change.base_document_snapshot["entities"] = []
                self.unchanged(
                    replace(proposal, transaction=replace(proposal.transaction, changes=(change,)))
                )

    def altered(self, proposal, change):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(change,)),
            required_artifact_ids=tuple(dict.fromkeys(r["id"] for r in change.references)),
        )

    def rebase_document(self, document):
        # Trusted test setup only; construction itself always crosses ProposalAcceptor.
        self.store = RevisionStore.create(document)

    def test_all_outputs_are_reproduced(self):
        proposal = self.propose()
        mutations = {
            "style": lambda c: c.fragment.styles[0].update(fill="#FFFFFF"),
            "id": lambda c: c.fragment.entities[0].update(id="entity:caller"),
            "binding": lambda c: c.fragment.output_bindings[0].update(slot="op:caller.geometry"),
            "origin": lambda c: c.group["transform"].update(origin=[0, 0]),
            "group": lambda c: c.group.update(id="group:" + "a" * 64),
            "omitted_member": lambda c: c.group["members"].pop(),
            "extra_member": lambda c: c.group["members"].append("entity:caller"),
            "reordered_members": lambda c: c.group["members"].reverse(),
            "mixed_origin": lambda c: c.group["provenance"].update(
                candidate_id="candidate:group:" + "a" * 64
            ),
            "bool_numeric": lambda c: c.fragment.operations[0]["parameters"].update(x=False),
            "nan": lambda c: c.fragment.operations[0]["parameters"].update(x=float("nan")),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                change = copy.deepcopy(proposal.transaction.changes[0])
                mutate(change)
                self.unchanged(self.altered(proposal, change))
        original = proposal.transaction.changes[0]
        for fragment in (
            replace(original.fragment, entities=original.fragment.entities[:1]),
            replace(
                original.fragment, render_entries=tuple(reversed(original.fragment.render_entries))
            ),
            replace(original.fragment, references=original.references),
        ):
            self.unchanged(self.altered(proposal, replace(original, fragment=fragment)))
        self.unchanged(self.altered(proposal, replace(original, profile_identity="unknown@1")))

    def test_revision_witness_source_hook_and_selected_subset_attack(self):
        proposal = self.propose()
        change = copy.deepcopy(proposal.transaction.changes[0])
        change.base_document_snapshot["references"] = []
        forged = RevisionStore._make_revision(change.base_document_snapshot, (), None, "invented")
        change = replace(change, base_revision=forged, source_revision_id=forged.revision_id)
        self.unchanged(self.altered(proposal, change))
        self.unchanged(
            self.altered(proposal, replace(change, source_revision_id=proposal.base_revision_id))
        )
        original = proposal.transaction.changes[0]
        self.unchanged(
            self.altered(
                proposal,
                replace(original, base_revision=replace(original.base_revision, message="forged")),
            )
        )

    def test_preceding_change_is_rejected_by_incoming_guard(self):
        proposal = self.propose()
        op = self.store.get_document(self.store.head)["construction"]["operations"][0]
        earlier = SetOperationParameterChange(op["id"], "width", 27.0)
        self.unchanged(
            replace(
                proposal,
                transaction=replace(
                    proposal.transaction, changes=(earlier, *proposal.transaction.changes)
                ),
            )
        )

    def test_stale_proposal_and_reproposal_identity(self):
        proposal = self.propose()
        op = self.store.get_document(self.store.head)["construction"]["operations"][0]
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:edit-old", (SetOperationParameterChange(op["id"], "width", 27.0),)
            ),
        )
        self.unchanged(proposal)
        reproposal = self.propose()
        a, b = proposal.transaction.changes[0], reproposal.transaction.changes[0]
        self.assertEqual(a.group["id"], b.group["id"])
        self.assertEqual(a.fragment, b.fragment)
        self.assertNotEqual(a.references[-1]["id"], b.references[-1]["id"])

    def test_each_policy_intent_denies_atomically(self):
        base = self.store.get_document(self.store.head)
        proposal = self.propose()
        intents = resolve_transaction_intents(proposal.transaction)
        self.assertEqual(
            {i[0] for i in intents},
            {"establish_group", "import_scene", "set_group_transform", "attach_analysis"},
        )
        self.assertNotIn("promote_group", {i[0] for i in intents})
        for action, target, _ in intents:
            with self.subTest(action=action):
                document = copy.deepcopy(base)
                document["edit_permissions"] = [
                    {
                        "id": "permission:deny",
                        "actor": "*",
                        "effect": "deny",
                        "actions": [action],
                        "targets": ["*" if action == "set_group_transform" else target],
                    }
                ]
                self.rebase_document(document)
                jsonschema.validate(
                    document,
                    json.loads((ROOT / "schema/svm-document-v0.1.schema.json").read_text()),
                )
                self.unchanged(self.propose())

    def test_source_selection_is_complete_and_accepted(self):
        base = self.store.get_document(self.store.head)
        for label in ("missing", "multiple", "alternate_media", "derived"):
            with self.subTest(label=label):
                document = copy.deepcopy(base)
                if label == "missing":
                    document["references"] = []
                elif label == "multiple":
                    other = self.artifacts.import_bytes(SOURCE + b" ", media_type="image/svg+xml")
                    document["references"].append(other.document_reference())
                else:
                    source = self.artifacts.import_bytes(
                        SOURCE,
                        media_type="application/svg+xml"
                        if label == "alternate_media"
                        else "image/svg+xml",
                        kind=ArtifactKind.DERIVED if label == "derived" else ArtifactKind.REFERENCE,
                    )
                    document["references"] = [source.document_reference()]
                self.rebase_document(document)
                before = self.store.get_document(self.store.head)
                with self.assertRaises(SVGGroupConstructionError):
                    self.propose()
                self.assertEqual(before, self.store.get_document(self.store.head))

    def test_source_subset_fail_closed(self):
        sources = [
            b"not XML",
            b"\xff",
            b"\xef\xbb\xbf" + SOURCE,
            b" " * 65537,
            b'<?xml version="1.0"?>' + SOURCE,
            b"<!--comment-->" + SOURCE,
            SOURCE.replace(b"<g>", b'<g id="caller">'),
            SOURCE.replace(b"<g>", b"").replace(b"</g>", b""),
            SOURCE.replace(b"<rect ", b"<path "),
            SOURCE.replace(b"</g>", b'<rect x="1" y="1" width="1" height="1"/></g>'),
            SOURCE.replace(b'width="20"', b'width="0"'),
            SOURCE.replace(b"<rect ", b'<rect opacity="0" '),
            SOURCE.replace(b"<g>", b'<g xmlns="http://www.w3.org/2000/svg">'),
            SOURCE.replace(b"<g>", b"<g>text"),
            SOURCE.replace(b'x="0"', b'x="&#48;"'),
            SOURCE.replace(b"<g>", b"<g><![CDATA[ ]] >"),
        ]
        sources += [
            SOURCE.replace(b'width="20"', f'width="{n}"'.encode())
            for n in ("NaN", "Infinity", "true", "01", "-0", "+1", "1e1", "1.0", "1000001", "-1")
        ]
        rect = b'<rect x="0" y="0" width="20" height="10"/>'
        ellipse = b'<ellipse cx="30" cy="5" rx="5" ry="3"/>'
        sources += [
            SOURCE.replace(rect, b""),
            SOURCE.replace(rect, b"TEMP").replace(ellipse, rect).replace(b"TEMP", ellipse),
        ]
        base = self.store.get_document(self.store.head)
        for i, content in enumerate(sources):
            with self.subTest(case=i):
                source = self.artifacts.import_bytes(content, media_type="image/svg+xml")
                document = copy.deepcopy(base)
                document["references"] = [source.document_reference()]
                self.rebase_document(document)
                with self.assertRaises(SVGGroupConstructionError):
                    self.propose()

    def test_no_request_overrides(self):
        request = AdapterRequest.from_store(self.store, self.store.head, ("document",))
        for name in ("members", "namespace", "source", "baseline", "style", "origin", "profile"):
            with self.subTest(name=name), self.assertRaises(SVGGroupConstructionError):
                SVGGroupConstructionAdapter().propose(
                    replace(request, options={name: "caller"}),
                    self.artifacts,
                    base_revision=self.store.revisions[self.store.head],
                )
        with self.assertRaises(SVGGroupConstructionError):
            SVGGroupConstructionAdapter().propose(
                replace(request, artifact_ids=("artifact:caller",)),
                self.artifacts,
                base_revision=self.store.revisions[self.store.head],
            )

    def test_evidence_forgery_cannot_self_attest(self):
        proposal = self.propose()
        original = proposal.transaction.changes[0]
        for index, field, value in (
            (1, "member_bounds", []),
            (2, "representation_claim", {"T": "G"}),
        ):
            with self.subTest(index=index):
                reference = original.references[index]
                snapshot = self.artifacts.resolve_reference(reference)
                payload = json.loads(snapshot.content)
                payload[field] = value
                forged = self.artifacts.import_bytes(
                    canonical_bytes(payload),
                    media_type=snapshot.media_type,
                    kind=snapshot.kind,
                    provenance=snapshot.provenance,
                )
                refs = list(original.references)
                refs[index] = forged.document_reference()
                change = replace(original, references=tuple(refs))
                self.unchanged(self.altered(proposal, change))
        for refs in (
            original.references[1:],
            original.references[:-1],
            original.references + (original.references[0],),
        ):
            self.unchanged(self.altered(proposal, replace(original, references=refs)))

    def test_distinct_source_subjects_do_not_alias(self):
        first = self.propose().transaction.changes[0]
        base = self.store.get_document(self.store.head)
        source = self.artifacts.import_bytes(SOURCE + b"\n", media_type="image/svg+xml")
        base["references"] = [source.document_reference()]
        self.rebase_document(base)
        second = self.propose().transaction.changes[0]
        self.assertNotEqual(first.group["id"], second.group["id"])
        self.assertTrue(set(first.group["members"]).isdisjoint(second.group["members"]))

    def test_repeated_creation_and_preexisting_target_collision(self):
        proposal = self.propose()
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        with self.assertRaises(ValueError):
            self.propose()
        document = self.store.get_document(self.store.head)
        group = document["groups"][0]
        before = copy.deepcopy(group)
        op = proposal.transaction.changes[0].fragment.operations[0]
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:editable", (SetOperationParameterChange(op["id"], "width", 22.0),)
            ),
        )
        self.assertEqual(before, self.store.get_document(self.store.head)["groups"][0])

    def test_structural_provenance_union_is_not_authority(self):
        proposal = self.propose()
        candidate = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        for mutation in (
            {"type": "unknown"},
            {"profile_identity": "unknown"},
            {"candidate_id": "candidate:fake"},
        ):
            with self.subTest(mutation=mutation):
                doc = copy.deepcopy(candidate)
                doc["groups"][0]["provenance"].update(mutation)
                with self.assertRaises(ValueError):
                    validate_document(doc)
        doc = copy.deepcopy(candidate)
        doc["groups"][0]["transform"]["origin"] = [1, 1]
        validate_document(doc)  # Structural validity permits ordinary post-birth editing.
        change = copy.deepcopy(proposal.transaction.changes[0])
        change.group["transform"]["origin"] = [1, 1]
        self.unchanged(self.altered(proposal, change))
