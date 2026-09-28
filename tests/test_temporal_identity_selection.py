from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import AdapterRequest, ArtifactKind, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters.temporal_correspondence import (
    EVIDENCE_MEDIA_TYPE,
    OBSERVATION_MEDIA_TYPE,
    TemporalCorrespondenceAdapter,
)
from svm.adapters.temporal_identity_promotion import (
    TemporalIdentityPromotionAdapter,
    TemporalIdentityPromotionError,
)
from svm.adapters.temporal_identity_selection import (
    ADAPTER_ID,
    MEDIA,
    POLICY,
    SCHEMA,
    TemporalIdentitySelectionAdapter,
    TemporalIdentitySelectionError,
)
from svm.change_authority import change_authority
from svm.evaluator import DocumentError, canonical_bytes
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.revisions import (
    AppendReferencesChange,
    ApplyTemporalIdentitySelectionChange,
    Transaction,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/042-temporal-identity-selection/observations.json"


class TemporalIdentitySelectionTest(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        self.store = RevisionStore.create(self.document)
        self.artifacts = ArtifactStore()
        self.observations = json.loads(FIXTURE.read_text())
        self.r0, self.payload = self.accept_r0(self.observations)
        self.supported = [c for c in self.payload["candidates"] if c["status"] == "SUPPORTED"]

    def request(self, artifact_id=None, **kwargs):
        return AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(artifact_id or self.r0.artifact_id,),
            **kwargs,
        )

    def accept_r0(self, observations):
        source = self.artifacts.import_bytes(
            canonical_bytes(observations), media_type=OBSERVATION_MEDIA_TYPE
        )
        proposal = TemporalCorrespondenceAdapter().propose(
            self.request(source.artifact_id), self.artifacts
        )
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        evidence = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        return evidence, json.loads(evidence.content)

    def propose(self):
        return TemporalIdentitySelectionAdapter().propose(self.request(), self.artifacts)

    def state(self):
        return self.store.head, len(self.store.revisions), self.store.get_document(self.store.head)

    def reject(self, action, exception=ProposalArtifactError, pattern=None):
        before = self.state()
        context = (
            self.assertRaisesRegex(exception, pattern) if pattern else self.assertRaises(exception)
        )
        with context:
            action()
        self.assertEqual(self.state(), before)

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def altered(self, proposal, **changes):
        change = replace(proposal.transaction.changes[0], **changes)
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(change,)),
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
        )

    def accept_reference(self, snapshot):
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:p2c-adversarial-reference",
                (AppendReferencesChange((snapshot.document_reference(),)),),
            ),
        )

    def pair(self, tick, source_id, target_tick, target_id):
        primitive = self.observations["frames"][0]["primitives"][0]
        observations = {
            **self.observations,
            "frames": [
                {"tick": tick, "primitives": [{**primitive, "observation_id": source_id}]},
                {"tick": target_tick, "primitives": [{**primitive, "observation_id": target_id}]},
            ],
        }
        evidence, payload = self.accept_r0(observations)
        return evidence, payload["candidates"][0]

    def promote_r1(self, evidence, candidate):
        proposal = TemporalIdentityPromotionAdapter().propose(
            self.request(
                evidence.artifact_id, options={"inference_ids": [candidate["inference_id"]]}
            ),
            self.artifacts,
        )
        self.accept(proposal)

    def test_golden_selects_both_with_exact_order_and_exclusion_audit(self):
        before = self.state()
        proposal = self.propose()
        self.assertEqual(proposal, self.propose())
        self.assertEqual(self.state(), before)
        self.assertEqual(len(self.supported), 2)
        self.assertEqual(
            {c["status"] for c in self.payload["candidates"]},
            {"SUPPORTED", "UNCERTAIN", "REJECTED"},
        )
        change = proposal.transaction.changes[0]
        self.assertEqual(len(proposal.transaction.changes), 1)
        self.assertIs(type(change), ApplyTemporalIdentitySelectionChange)
        ids = tuple(c["inference_id"] for c in self.supported)
        self.assertEqual(change.selected_inference_ids, ids)
        delegated = TemporalIdentityPromotionAdapter().propose(
            self.request(options={"inference_ids": list(ids)}), self.artifacts
        )
        self.assertEqual(change.delegated_promotion, delegated.transaction.changes[0])
        self.assertEqual(proposal.preview, delegated.preview)
        evidence = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        self.assertEqual(
            proposal.required_artifact_ids, (self.r0.artifact_id, evidence.artifact_id)
        )
        self.assertEqual(
            change.references, (self.r0.document_reference(), evidence.document_reference())
        )
        audit = json.loads(evidence.content)
        self.assertEqual((evidence.kind, evidence.media_type), (ArtifactKind.DERIVED, MEDIA))
        self.assertEqual(audit["schema_version"], SCHEMA)
        self.assertEqual(audit["policy_identity"], POLICY)
        self.assertEqual(audit["selected_inference_ids"], list(ids))
        self.assertEqual(
            audit["counts"],
            {"total": 12, "supported": 2, "uncertain": 4, "rejected": 6, "selected": 2},
        )
        self.assertEqual(
            audit["candidates"],
            [
                {k: c[k] for k in ("candidate_id", "inference_id", "status")}
                for c in self.payload["candidates"]
            ],
        )
        self.assertEqual(
            audit["excluded_candidates"],
            [c for c in audit["candidates"] if c["status"] != "SUPPORTED"],
        )
        previewed = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(self.state(), before)
        self.accept(proposal)
        after = self.state()[2]
        self.assertEqual(after, previewed)
        self.assertEqual(len(after["temporal_identities"]), 2)
        self.assertEqual(
            {p["inference_id"] for i in after["temporal_identities"] for p in i["provenance"]},
            set(ids),
        )
        self.assertIn(evidence.document_reference(), after["references"])
        for key in before[2]:
            if key not in ("references", "temporal_identities"):
                self.assertEqual(after[key], before[2][key])

    def test_zero_supported_uncertain_only_and_rejected_only_abstain(self):
        ambiguous = copy.deepcopy(self.observations)
        ambiguous["frames"][0]["primitives"] = ambiguous["frames"][0]["primitives"][2:]
        ambiguous["frames"][1]["primitives"] = ambiguous["frames"][1]["primitives"][2:]
        rejected = copy.deepcopy(self.observations)
        rejected["frames"][0]["primitives"] = rejected["frames"][0]["primitives"][:1]
        rejected["frames"][1]["primitives"] = rejected["frames"][1]["primitives"][2:3]
        for observations, status in ((ambiguous, "UNCERTAIN"), (rejected, "REJECTED")):
            with self.subTest(status=status):
                evidence, payload = self.accept_r0(observations)
                self.assertEqual({c["status"] for c in payload["candidates"]}, {status})
                self.reject(
                    lambda evidence=evidence: TemporalIdentitySelectionAdapter().propose(
                        self.request(evidence.artifact_id), self.artifacts
                    ),
                    TemporalIdentitySelectionError,
                    "zero SUPPORTED",
                )

    def test_one_supported_delegates_normally(self):
        evidence, _ = self.pair(2, "observation:x", 3, "observation:y")
        proposal = TemporalIdentitySelectionAdapter().propose(
            self.request(evidence.artifact_id), self.artifacts
        )
        self.assertEqual(proposal.report.metrics["selected_correspondences"], 1)
        self.accept(proposal)
        self.assertEqual(len(self.state()[2]["temporal_identities"]), 1)

    def test_independent_runs_have_identical_proposals_revisions_and_documents(self):
        proposal = self.propose()
        self.accept(proposal)
        expected = self.state()
        self.store = RevisionStore.create(self.document)
        evidence, _ = self.accept_r0(self.observations)
        self.assertEqual(evidence.artifact_id, self.r0.artifact_id)
        repeated = self.propose()
        self.assertEqual(repeated, proposal)
        self.accept(repeated)
        self.assertEqual(self.state(), expected)

    def test_forged_stable_id_is_rejected_by_frozen_r1_apply(self):
        proposal = self.propose()
        promotion = proposal.transaction.changes[0].delegated_promotion
        record = replace(
            promotion.correspondences[0], stable_identity_id="temporal-identity:forged"
        )
        forged = self.altered(
            proposal,
            delegated_promotion=replace(
                promotion, correspondences=(record, *promotion.correspondences[1:])
            ),
        )
        self.reject(lambda: self.accept(forged), DocumentError, "not canonical")

    def test_resolved_but_unaccepted_r0_rejects_at_acceptance(self):
        proposal = self.propose()
        self.store = RevisionStore.create(self.document)
        forged = replace(proposal, base_revision_id=self.store.head)
        self.reject(lambda: self.accept(forged), DocumentError, "already be accepted")

    def test_owner_reuse_and_same_owner_idempotency(self):
        candidate = self.supported[0]
        evidence, earlier = self.pair(0, candidate["source_observation_id"], 2, "observation:prior")
        self.promote_r1(evidence, earlier)
        owner = self.state()[2]["temporal_identities"][0]["id"]
        self.accept(self.propose())
        after = self.state()[2]
        reused = next(i for i in after["temporal_identities"] if i["id"] == owner)
        self.assertEqual(len(reused["bindings"]), 3)
        self.assertEqual(len(after["temporal_identities"]), 2)
        self.accept(self.propose())
        self.assertEqual(self.state()[2], after)

    def test_owner_conflict_at_proposal_and_acceptance_is_atomic(self):
        proposal = self.propose()
        candidate = self.supported[1]  # First delegated promotion succeeds on the transaction copy.
        first, left = self.pair(0, candidate["source_observation_id"], 2, "observation:left")
        self.promote_r1(first, left)
        second, right = self.pair(1, candidate["target_observation_id"], 3, "observation:right")
        self.promote_r1(second, right)
        self.reject(self.propose, TemporalIdentityPromotionError, "TEMPORAL_IDENTITY_CONFLICT")
        rebased = replace(proposal, base_revision_id=self.store.head)
        self.reject(lambda: self.accept(rebased), DocumentError, "TEMPORAL_IDENTITY_CONFLICT")
        self.assertNotIn(
            proposal.preview_artifacts[0].artifact_id,
            [r["id"] for r in self.state()[2]["references"]],
        )

    def test_primitive_permutation_preserves_r0_order_and_selected_identity_subjects(self):
        first = self.propose()
        permuted = copy.deepcopy(self.observations)
        for frame in permuted["frames"]:
            frame["primitives"].reverse()
        other, payload = self.accept_r0(permuted)
        proposal = TemporalIdentitySelectionAdapter().propose(
            self.request(other.artifact_id), self.artifacts
        )
        self.assertEqual(
            [c["candidate_id"] for c in self.payload["candidates"]],
            [c["candidate_id"] for c in payload["candidates"]],
        )
        self.assertEqual(
            [c["status"] for c in self.payload["candidates"]],
            [c["status"] for c in payload["candidates"]],
        )

        # Frozen R0 inference/R1 stable IDs bind exact source bytes; permutation changes them.
        def bindings(p):
            return {
                tuple((b["tick"], b["observation_id"]) for b in c.bindings())
                for c in p.transaction.changes[0].delegated_promotion.correspondences
            }

        self.assertEqual(bindings(first), bindings(proposal))
        self.accept(proposal)
        # Once owned, R1 reuses exactly the same stable identity set for original input order.
        original = self.propose()
        self.assertEqual(
            {i.stable_identity_id for i in original.preview.temporal_identities},
            {i.stable_identity_id for i in proposal.preview.temporal_identities},
        )

    def test_subset_extra_duplicate_and_reordered_promotions_reject(self):
        proposal = self.propose()
        promotion = proposal.transaction.changes[0].delegated_promotion
        records = promotion.correspondences
        for bad in (records[:1], records + records[:1], records[::-1]):
            with self.subTest(records=bad):
                forged = self.altered(
                    proposal, delegated_promotion=replace(promotion, correspondences=bad)
                )
                self.reject(lambda forged=forged: self.accept(forged))

    def test_subset_superset_duplicate_and_reordered_selected_ids_reject(self):
        proposal = self.propose()
        ids = proposal.transaction.changes[0].selected_inference_ids
        for bad in (ids[:1], ids[::-1], ids + ids[:1], ids + ("inference:extra",)):
            with self.subTest(ids=bad):
                self.reject(
                    lambda bad=bad: self.accept(self.altered(proposal, selected_inference_ids=bad))
                )

    def test_selection_evidence_tamper_rejects_exact_bytes_and_provenance(self):
        proposal = self.propose()
        evidence = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        original = json.loads(evidence.content)

        def altered_payload(field, value):
            payload = copy.deepcopy(original)
            payload[field] = value
            return canonical_bytes(payload)

        candidates = copy.deepcopy(original["candidates"])
        candidates[0]["status"] = "REJECTED"
        wrong_id = copy.deepcopy(original["candidates"])
        wrong_id[0]["candidate_id"] = "candidate:forged"
        variants = [
            altered_payload("selected_inference_ids", original["selected_inference_ids"][:1]),
            altered_payload("selected_inference_ids", original["selected_inference_ids"][::-1]),
            altered_payload("candidates", candidates),
            altered_payload("candidates", wrong_id),
            altered_payload("counts", {**original["counts"], "selected": 1}),
            b"{broken",
            json.dumps(original, indent=2).encode(),
        ]
        descriptors = [
            (content, MEDIA, ArtifactKind.DERIVED, evidence.provenance) for content in variants
        ]
        descriptors += [
            (evidence.content, media, kind, provenance)
            for media, kind, provenance in (
                (MEDIA, ArtifactKind.DERIVED, {}),
                ("application/json", ArtifactKind.DERIVED, evidence.provenance),
                (MEDIA, ArtifactKind.REFERENCE, evidence.provenance),
            )
        ]
        for content, media, kind, provenance in descriptors:
            with self.subTest(content=content[:50], media=media, kind=kind, provenance=provenance):
                bad = self.artifacts.import_bytes(
                    content, media_type=media, kind=kind, provenance=provenance
                )
                self.reject(
                    lambda bad=bad: self.accept(
                        self.altered(
                            proposal, selection_evidence_reference=bad.document_reference()
                        )
                    )
                )

    def test_wrong_policy_reference_and_delegated_type_reject(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        promotion = change.delegated_promotion
        variants = [
            dict(policy_identity="forged"),
            dict(delegated_promotion=AppendReferencesChange(())),
            dict(
                delegated_promotion=replace(
                    promotion, references=(change.selection_evidence_reference,)
                )
            ),
            dict(selection_evidence_reference=change.r0_evidence_reference),
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                self.reject(lambda changes=changes: self.accept(self.altered(proposal, **changes)))

    def test_exact_correspondence_fields_and_r1_record_type_are_bound(self):
        proposal = self.propose()
        promotion = proposal.transaction.changes[0].delegated_promotion
        for field, value in (
            ("candidate_id", "candidate:forged"),
            ("inference_id", "inference:forged"),
            ("source_tick", 8),
            ("target_tick", 9),
            ("source_observation_id", "observation:forged"),
            ("target_observation_id", "observation:forged"),
            ("evidence_artifact_id", "artifact:forged"),
            ("evidence_policy_identity", "forged"),
        ):
            with self.subTest(field=field):
                record = replace(promotion.correspondences[0], **{field: value})
                forged = replace(
                    promotion, correspondences=(record, *promotion.correspondences[1:])
                )
                self.reject(
                    lambda forged=forged: self.accept(
                        self.altered(proposal, delegated_promotion=forged)
                    )
                )
        forged = replace(promotion, correspondences=(object(), *promotion.correspondences[1:]))
        self.reject(
            lambda forged=forged: self.accept(self.altered(proposal, delegated_promotion=forged))
        )

    def test_malformed_r0_authority_fails_closed_at_proposal_and_acceptance(self):
        original = self.propose()
        variants = [
            (b"{broken", EVIDENCE_MEDIA_TYPE, ArtifactKind.DERIVED),
            (
                json.dumps(self.payload, indent=2).encode(),
                EVIDENCE_MEDIA_TYPE,
                ArtifactKind.DERIVED,
            ),
            (self.r0.content, "application/json", ArtifactKind.DERIVED),
            (self.r0.content, EVIDENCE_MEDIA_TYPE, ArtifactKind.REFERENCE),
        ]
        for field, value in (
            ("identity", "wrong"),
            ("policy_identity", "wrong"),
            ("candidates", self.payload["candidates"] + self.payload["candidates"][:1]),
        ):
            variants.append(
                (
                    canonical_bytes({**self.payload, field: value}),
                    EVIDENCE_MEDIA_TYPE,
                    ArtifactKind.DERIVED,
                )
            )
        for field, value in (("status", "SUPPORTED"), ("inference_id", "inference:forged")):
            payload = copy.deepcopy(self.payload)
            candidate = next(c for c in payload["candidates"] if c["status"] == "REJECTED")
            candidate[field] = value
            variants.append((canonical_bytes(payload), EVIDENCE_MEDIA_TYPE, ArtifactKind.DERIVED))
        for content, media, kind in variants:
            with self.subTest(content=content[:50], media=media, kind=kind):
                self.store = RevisionStore.create(self.document)
                bad = self.artifacts.import_bytes(content, media_type=media, kind=kind)
                self.accept_reference(bad)
                self.reject(
                    lambda bad=bad: TemporalIdentitySelectionAdapter().propose(
                        self.request(bad.artifact_id), self.artifacts
                    ),
                    TemporalIdentitySelectionError,
                )
                forged = self.altered(original, r0_evidence_reference=bad.document_reference())
                self.reject(
                    lambda forged=forged: self.accept(
                        replace(forged, base_revision_id=self.store.head)
                    )
                )

    def test_supported_disjointness_violation_fails_closed_without_tiebreak(self):
        payload = copy.deepcopy(self.payload)
        source = self.supported[0]["source_observation_id"]
        extra = next(
            c
            for c in payload["candidates"]
            if c["source_observation_id"] == source and c["status"] != "SUPPORTED"
        )
        extra["status"] = "SUPPORTED"
        extra["inference_id"] = (
            "inference:correspondence:"
            + hashlib.sha256(
                canonical_bytes({k: v for k, v in extra.items() if k != "inference_id"})
            ).hexdigest()
        )
        bad = self.artifacts.import_bytes(
            canonical_bytes(payload), media_type=EVIDENCE_MEDIA_TYPE, kind=ArtifactKind.DERIVED
        )
        self.accept_reference(bad)
        self.reject(
            lambda: TemporalIdentitySelectionAdapter().propose(
                self.request(bad.artifact_id), self.artifacts
            ),
            TemporalIdentitySelectionError,
            "disjoint",
        )

    def test_request_authority_and_unaccepted_r0_reject(self):
        request = self.request()
        for bad in (
            replace(request, scope=("entity:caller",)),
            replace(request, artifact_ids=()),
            replace(request, artifact_ids=request.artifact_ids * 2),
        ):
            self.reject(
                lambda bad=bad: TemporalIdentitySelectionAdapter().propose(bad, self.artifacts),
                TemporalIdentitySelectionError,
            )
        for key in (
            "inference_ids",
            "candidate_id",
            "observation_id",
            "pairing",
            "score",
            "thresholds",
            "temporal_identity_id",
            "role",
            "Entity",
            "Group",
            "Track",
            "Camera",
            "Ground Truth",
        ):
            self.reject(
                lambda key=key: TemporalIdentitySelectionAdapter().propose(
                    replace(request, options={key: "caller"}), self.artifacts
                ),
                TemporalIdentitySelectionError,
            )
        unaccepted = replace(request, document=self.document)
        self.reject(
            lambda: TemporalIdentitySelectionAdapter().propose(unaccepted, self.artifacts),
            TemporalIdentitySelectionError,
            "already be accepted",
        )

    def test_stale_base_rejects_without_mutation(self):
        proposal = self.propose()
        self.store.commit(self.store.head, Transaction("transaction:advance", ()))
        self.reject(lambda: self.accept(proposal), ProposalConflictError)

    def test_both_existing_policy_actions_are_enforced(self):
        proposal = self.propose()
        authority = change_authority(proposal.transaction.changes[0])
        self.assertEqual(
            authority.actions, frozenset({"promote_temporal_identity", "attach_analysis"})
        )
        for action in authority.actions:
            with self.subTest(action=action):
                document = self.state()[2]
                document["edit_permissions"] = [
                    {
                        "id": "permission:p2c-deny",
                        "actor": ADAPTER_ID,
                        "effect": "deny",
                        "actions": [action],
                        "targets": ["document"],
                    }
                ]
                self.store = RevisionStore.create(document)
                self.reject(lambda: self.accept(self.propose()), ProposalPolicyError)


if __name__ == "__main__":
    unittest.main()
