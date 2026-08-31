import copy
import json
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from svm import (
    AnchoredRegenerationContract,
    AnchoredRegenerationError,
    GeneratorProvenance,
    ImpactTarget,
    Proposal,
    ProposalAcceptor,
    ProposalPolicyError,
    RevisionStore,
    SetKeyframeValueChange,
    SetOperationParameterChange,
    Transaction,
)
from svm.document import validate_document

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "examples" / "018-anchored-regeneration.svm.json"
GOLDEN_M = ROOT / "examples" / "017-motion-rectangle.svm.json"
ACTOR = "adapter:deterministic-regenerator"


def parameter(document: dict[str, Any], operation_id: str, name: str) -> Any:
    operation = next(
        item for item in document["construction"]["operations"] if item["id"] == operation_id
    )
    return operation["parameters"][name]


@dataclass(frozen=True)
class DelegatingChange:
    change: SetOperationParameterChange

    def apply(self, document: dict[str, Any]) -> None:
        self.change.apply(document)


class AnchoredRegenerationGoldenOTest(unittest.TestCase):
    def setUp(self) -> None:
        self.initial = json.loads(GOLDEN.read_text(encoding="utf-8"))
        validate_document(self.initial)
        self.store, self.r0, self.r1 = self._strict_edit_store(self.initial)
        self.contract = self._contract(self.r1)

    @staticmethod
    def _strict_edit_store(
        document: dict[str, Any],
    ) -> tuple[RevisionStore, str, str]:
        store = RevisionStore.create(document, "Golden O red-eye baseline")
        assert store.head is not None
        r0 = store.head
        strict_edit = Transaction(
            transaction_id="transaction:golden-o-strict-edit",
            changes=(SetOperationParameterChange("op:eye-frame", "rx", 0.45),),
            message="Confirmed deterministic eye-frame edit",
        )
        r1 = store.commit(r0, strict_edit).revision_id
        return store, r0, r1

    @staticmethod
    def _contract(base_revision_id: str) -> AnchoredRegenerationContract:
        eye_frame = ImpactTarget("set_parameter", "op:eye-frame", "rx")
        return AnchoredRegenerationContract(
            base_revision_id=base_revision_id,
            anchor=(eye_frame,),
            intent=(eye_frame,),
            protection=(
                eye_frame,
                ImpactTarget("set_parameter", "op:unrelated", "x"),
            ),
            regeneration_scope=(
                ImpactTarget("set_parameter", "op:eye-highlight", "cx"),
                ImpactTarget("set_parameter", "op:eye-highlight", "cy"),
            ),
        )

    @staticmethod
    def _proposal(
        base_revision_id: str,
        name: str,
        changes: tuple[Any, ...],
        *,
        notes: str = "",
    ) -> Proposal:
        return Proposal(
            proposal_id=f"proposal:golden-o-{name}",
            base_revision_id=base_revision_id,
            generator=GeneratorProvenance(
                adapter_id=ACTOR,
                adapter_version="0.1",
                engine="deterministic-fixture",
                engine_version="1",
            ),
            transaction=Transaction(
                transaction_id=f"transaction:golden-o-{name}",
                changes=changes,
                message=f"Golden O candidate {name}",
            ),
            notes=notes,
        )

    def test_golden_o_accepts_sibling_proposals_as_real_revision_branches(self) -> None:
        proposal_a = self._proposal(
            self.r1,
            "highlight-x",
            (SetOperationParameterChange("op:eye-highlight", "cx", 0.16),),
        )
        proposal_b = self._proposal(
            self.r1,
            "highlight-xy",
            (
                SetOperationParameterChange("op:eye-highlight", "cx", 0.18),
                SetOperationParameterChange("op:eye-highlight", "cy", -0.08),
            ),
        )
        before_proposals = len(self.store.revisions)
        base_snapshot = self.store.get_document(self.r1)
        self.assertEqual(before_proposals, 2)
        self.assertEqual(self.store.get_document(self.r1), base_snapshot)

        acceptor = ProposalAcceptor()
        r2 = acceptor.accept_anchored(self.store, proposal_a, self.contract)
        r3 = acceptor.accept_anchored(self.store, proposal_b, self.contract)

        self.assertEqual(self.store.revisions[self.r1].parent_ids, (self.r0,))
        self.assertEqual(r2.parent_ids, (self.r1,))
        self.assertEqual(r3.parent_ids, (self.r1,))
        self.assertNotEqual(r2.revision_id, r3.revision_id)
        self.assertEqual(len(self.store.revisions), 4)

        documents = {
            revision_id: self.store.get_document(revision_id)
            for revision_id in (self.r0, self.r1, r2.revision_id, r3.revision_id)
        }
        for document in documents.values():
            validate_document(document)
        self.assertEqual(parameter(documents[self.r0], "op:eye-frame", "rx"), 0.4)
        self.assertEqual(parameter(documents[self.r1], "op:eye-frame", "rx"), 0.45)
        self.assertEqual(parameter(documents[r2.revision_id], "op:eye-highlight", "cx"), 0.16)
        self.assertEqual(parameter(documents[r2.revision_id], "op:eye-highlight", "cy"), -0.05)
        self.assertEqual(parameter(documents[r3.revision_id], "op:eye-highlight", "cx"), 0.18)
        self.assertEqual(parameter(documents[r3.revision_id], "op:eye-highlight", "cy"), -0.08)
        self.assertEqual(self.store.get_document(self.r1), base_snapshot)

        identities = [
            (
                tuple(entity["id"] for entity in document["entities"]),
                tuple(operation["id"] for operation in document["construction"]["operations"]),
            )
            for document in documents.values()
        ]
        self.assertEqual(len(set(identities)), 1)

    def test_scope_is_computed_from_actual_changes_and_fails_atomically(self) -> None:
        attacks = (
            (
                "protected",
                (SetOperationParameterChange("op:eye-frame", "rx", 0.5),),
                "protected impacts",
            ),
            (
                "outside",
                (SetOperationParameterChange("op:unrelated", "width", 0.3),),
                "outside regeneration scope",
            ),
            (
                "mixed",
                (
                    SetOperationParameterChange("op:eye-highlight", "cx", 0.2),
                    SetOperationParameterChange("op:unrelated", "width", 0.3),
                ),
                "outside regeneration scope",
            ),
        )
        baseline = self.store.get_document(self.r1)
        revision_count = len(self.store.revisions)
        for name, changes, error in attacks:
            with self.subTest(name=name):
                proposal = self._proposal(
                    self.r1,
                    name,
                    changes,
                    notes="Generator claims only op:eye-highlight.cx changes",
                )
                with self.assertRaisesRegex(ProposalPolicyError, error):
                    ProposalAcceptor().accept_anchored(self.store, proposal, self.contract)
                self.assertEqual(len(self.store.revisions), revision_count)
                self.assertEqual(self.store.get_document(self.r1), baseline)

    def test_unregistered_wrapper_cannot_claim_anchored_authority(self) -> None:
        proposal = self._proposal(
            self.r1,
            "wrapped",
            (DelegatingChange(SetOperationParameterChange("op:eye-highlight", "cx", 0.2)),),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "Unregistered Change type"):
            ProposalAcceptor().accept_anchored(self.store, proposal, self.contract)
        self.assertEqual(len(self.store.revisions), 2)

    def test_existing_actor_policy_remains_an_additional_gate(self) -> None:
        protected = copy.deepcopy(self.initial)
        protected["edit_permissions"].append(
            {
                "id": "permission:no-regenerator-parameters",
                "actor": ACTOR,
                "effect": "deny",
                "actions": ["set_parameter"],
                "targets": ["op:eye-highlight"],
            }
        )
        store, _r0, r1 = self._strict_edit_store(protected)
        proposal = self._proposal(
            r1,
            "policy-denied",
            (SetOperationParameterChange("op:eye-highlight", "cx", 0.16),),
        )
        acceptor = ProposalAcceptor()
        with self.assertRaisesRegex(ProposalPolicyError, "denies"):
            acceptor.validate_anchored(store, proposal, self._contract(r1))
        with self.assertRaisesRegex(ProposalPolicyError, "denies"):
            acceptor.accept_anchored(store, proposal, self._contract(r1))
        self.assertEqual(len(store.revisions), 2)

    def test_anchored_dry_run_matches_acceptance_without_committing(self) -> None:
        proposal = self._proposal(
            self.r1,
            "dry-run",
            (SetOperationParameterChange("op:eye-highlight", "cx", 0.16),),
        )
        acceptor = ProposalAcceptor()
        revision_count = len(self.store.revisions)
        candidate = acceptor.validate_anchored(self.store, proposal, self.contract)
        self.assertEqual(len(self.store.revisions), revision_count)
        self.assertEqual(parameter(candidate, "op:eye-highlight", "cx"), 0.16)

        revision = acceptor.accept_anchored(self.store, proposal, self.contract)
        self.assertEqual(self.store.get_document(revision.revision_id), candidate)

    def test_contract_base_and_deterministic_branch_identity(self) -> None:
        wrong_contract = self._contract(self.r0)
        proposal = self._proposal(
            self.r1,
            "deterministic",
            (SetOperationParameterChange("op:eye-highlight", "cx", 0.16),),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "does not match"):
            ProposalAcceptor().accept_anchored(self.store, proposal, wrong_contract)

        other_store, _other_r0, other_r1 = self._strict_edit_store(self.initial)
        self.assertEqual(other_r1, self.r1)
        first = ProposalAcceptor().accept_anchored(self.store, proposal, self.contract)
        second = ProposalAcceptor().accept_anchored(
            other_store,
            self._proposal(
                other_r1,
                "deterministic",
                (SetOperationParameterChange("op:eye-highlight", "cx", 0.16),),
            ),
            self._contract(other_r1),
        )
        self.assertEqual(first.revision_id, second.revision_id)
        self.assertEqual(first.document_hash, second.document_hash)

    def test_invalid_contract_and_empty_proposal_never_create_revision(self) -> None:
        eye_frame = ImpactTarget("set_parameter", "op:eye-frame", "rx")
        with self.assertRaisesRegex(AnchoredRegenerationError, "must be protected"):
            AnchoredRegenerationContract(
                base_revision_id=self.r1,
                anchor=(eye_frame,),
                intent=(eye_frame,),
                protection=(ImpactTarget("set_parameter", "op:unrelated", "x"),),
                regeneration_scope=(ImpactTarget("set_parameter", "op:eye-highlight", "cx"),),
            )
        proposal = self._proposal(self.r1, "empty", ())
        with self.assertRaisesRegex(ProposalPolicyError, "actual Change impact"):
            ProposalAcceptor().accept_anchored(self.store, proposal, self.contract)
        self.assertEqual(len(self.store.revisions), 2)

    def test_contract_targets_are_validated_against_base_revision(self) -> None:
        typo = ImpactTarget("set_paramter", "op:eye-frame", "rx")
        typo_contract = AnchoredRegenerationContract(
            base_revision_id=self.r1,
            anchor=(typo,),
            intent=(typo,),
            protection=(typo,),
            regeneration_scope=(ImpactTarget("set_parameter", "op:eye-highlight", "cx"),),
        )
        proposal = self._proposal(
            self.r1,
            "typo-contract",
            (SetOperationParameterChange("op:eye-highlight", "cx", 0.16),),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "Unknown ChangeAuthority action"):
            ProposalAcceptor().accept_anchored(self.store, proposal, typo_contract)

        missing_parameter = ImpactTarget("set_parameter", "op:eye-highlight", "missing")
        invalid_scope = AnchoredRegenerationContract(
            base_revision_id=self.r1,
            anchor=self.contract.anchor,
            intent=self.contract.intent,
            protection=self.contract.protection,
            regeneration_scope=(missing_parameter,),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "Missing Operation parameter"):
            ProposalAcceptor().accept_anchored(self.store, proposal, invalid_scope)
        self.assertEqual(len(self.store.revisions), 2)

    def test_motion_scope_is_exact_to_keyframe_identity(self) -> None:
        motion_document = json.loads(GOLDEN_M.read_text(encoding="utf-8"))
        store = RevisionStore.create(motion_document)
        assert store.head is not None
        start = ImpactTarget(
            "set_keyframe_value", "track:moving-rectangle-x", "keyframe:moving-x-0000"
        )
        middle = ImpactTarget(
            "set_keyframe_value", "track:moving-rectangle-x", "keyframe:moving-x-0500"
        )
        contract = AnchoredRegenerationContract(
            base_revision_id=store.head,
            anchor=(start,),
            intent=(start,),
            protection=(start,),
            regeneration_scope=(middle,),
        )
        forbidden = self._proposal(
            store.head,
            "wrong-keyframe",
            (SetKeyframeValueChange("track:moving-rectangle-x", "keyframe:moving-x-1000", 550),),
        )
        with self.assertRaisesRegex(ProposalPolicyError, "outside regeneration scope"):
            ProposalAcceptor().accept_anchored(store, forbidden, contract)
        self.assertEqual(len(store.revisions), 1)

        allowed = self._proposal(
            store.head,
            "allowed-keyframe",
            (SetKeyframeValueChange("track:moving-rectangle-x", "keyframe:moving-x-0500", 350),),
        )
        revision = ProposalAcceptor().accept_anchored(store, allowed, contract)
        self.assertEqual(revision.parent_ids, (contract.base_revision_id,))


if __name__ == "__main__":
    unittest.main()
