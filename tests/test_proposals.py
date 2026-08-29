import json
import unittest
from pathlib import Path

from svm import (
    AdapterRequest,
    GeneratorProvenance,
    Proposal,
    ProposalAcceptor,
    ProposalConflictError,
    RevisionStore,
)

from test_golden_b import split_transaction


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


if __name__ == "__main__":
    unittest.main()

