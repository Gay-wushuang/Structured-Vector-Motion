import json
import unittest
from pathlib import Path

from test_golden_b import split_transaction

from svm import (
    AdapterRequest,
    GeneratorProvenance,
    Proposal,
    ProposalAcceptor,
    ProposalConflictError,
    ProposalPolicyError,
    RevisionStore,
    SetOperationParameterChange,
    Transaction,
)

ROOT = Path(__file__).resolve().parents[1]


class ProposalBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "003-split-head.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.base = self.store.head

    def make_proposal(self) -> Proposal:
        return Proposal(
            proposal_id="proposal:split-head",
            base_revision_id=self.base,
            generator=GeneratorProvenance(
                adapter_id="adapter:test",
                adapter_version="0.1",
                engine="fixture",
                engine_version="1",
            ),
            transaction=split_transaction(),
        )

    def parameter_proposal(self, store: RevisionStore) -> Proposal:
        return Proposal(
            proposal_id="proposal:resize-head",
            base_revision_id=store.head,
            generator=GeneratorProvenance(
                adapter_id="adapter:test",
                adapter_version="0.1",
                engine="fixture",
                engine_version="1",
            ),
            transaction=Transaction(
                transaction_id="transaction:resize-head",
                changes=(SetOperationParameterChange("op:head_base", "rx", 0.42),),
            ),
        )

    def test_adapter_request_is_an_isolated_snapshot(self) -> None:
        request = AdapterRequest.from_store(self.store, self.base, ("entity:head",))
        request.document["entities"][0]["name"] = "Adapter mutation"
        self.assertEqual(self.store.get_document(self.base)["entities"][0]["name"], "Head")

    def test_acceptance_commits_once_and_stale_proposal_conflicts(self) -> None:
        proposal = self.make_proposal()
        revision = ProposalAcceptor().accept(self.store, proposal)
        self.assertEqual(revision.parent_ids, (self.base,))
        self.assertEqual(revision.transaction_id, "transaction:split-head")

        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(self.store, proposal)

    def test_preserve_parameter_constraint_rejects_matching_change(self) -> None:
        constrained = self.store.get_document(self.base)
        constrained["constraints"].append(
            {
                "id": "constraint:head-radius",
                "type": "PreserveParameter",
                "operation": "op:head_base",
                "parameter": "rx",
            }
        )
        constrained_store = RevisionStore.create(constrained)
        proposal = self.parameter_proposal(constrained_store)
        revision_count = len(constrained_store.revisions)

        with self.assertRaisesRegex(ProposalPolicyError, "preserves op:head_base.rx"):
            ProposalAcceptor().accept(constrained_store, proposal)

        self.assertEqual(len(constrained_store.revisions), revision_count)

    def test_constraint_allows_unrelated_change(self) -> None:
        constrained = self.store.get_document(self.base)
        constrained["constraints"].append(
            {
                "id": "constraint:shield-width",
                "type": "PreserveParameter",
                "operation": "op:shield",
                "parameter": "width",
            }
        )
        constrained_store = RevisionStore.create(constrained)
        proposal = self.make_proposal()
        proposal = Proposal(
            proposal_id=proposal.proposal_id,
            base_revision_id=constrained_store.head,
            generator=proposal.generator,
            transaction=proposal.transaction,
        )

        revision = ProposalAcceptor().accept(constrained_store, proposal)
        self.assertEqual(revision.transaction_id, "transaction:split-head")

    def test_edit_permission_denies_matching_actor_action_and_target(self) -> None:
        protected = self.store.get_document(self.base)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-adapter-head-split",
                "actor": "adapter:test",
                "effect": "deny",
                "actions": ["split_entity"],
                "targets": ["entity:head"],
            }
        )
        protected_store = RevisionStore.create(protected)
        proposal = self.make_proposal()
        proposal = Proposal(
            proposal_id=proposal.proposal_id,
            base_revision_id=protected_store.head,
            generator=proposal.generator,
            transaction=proposal.transaction,
        )

        with self.assertRaisesRegex(ProposalPolicyError, "denies adapter:test"):
            ProposalAcceptor().accept(protected_store, proposal)

    def test_edit_permission_for_other_actor_does_not_block(self) -> None:
        protected = self.store.get_document(self.base)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-other-adapter",
                "actor": "adapter:other",
                "effect": "deny",
                "actions": ["split_entity"],
                "targets": ["entity:head"],
            }
        )
        protected_store = RevisionStore.create(protected)
        proposal = self.make_proposal()
        proposal = Proposal(
            proposal_id=proposal.proposal_id,
            base_revision_id=protected_store.head,
            generator=proposal.generator,
            transaction=proposal.transaction,
        )

        revision = ProposalAcceptor().accept(protected_store, proposal)
        self.assertEqual(revision.transaction_id, "transaction:split-head")


if __name__ == "__main__":
    unittest.main()
