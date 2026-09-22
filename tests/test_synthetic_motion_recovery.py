from __future__ import annotations

import copy
import json
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from svm import (
    AdapterRequest,
    AppendReferencesChange,
    ArtifactStore,
    MotionEvaluator,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalConflictError,
    RevisionStore,
    SetGroupTransformChange,
    Transaction,
)
from svm.adapters import (
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    ObservedSimilarityMotionAdapter,
    ObservedTranslationMotionAdapter,
    ObservedTranslationTracksAdapter,
    SVGGeometryObservationAdapter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.observed_rotation_tracks import ObservedRotationTracksError
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "028-synthetic-motion-recovery"
RECOVERY_BASE = FIXTURE / "recovery-base.svm.json"
GROUND_TRUTH = FIXTURE / "ground-truth.svm.json"
TICKS = (0, 12, 24, 36)
GROUP_ID = "group:" + "1" * 64
TARGET_ENTITY = "entity:recovery-target"
TOLERANCE = 1e-8


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def request(store, *, artifact_ids=(), options=None):
    return AdapterRequest.from_store(
        store,
        store.head,
        ("document",),
        artifact_ids=tuple(artifact_ids),
        options=options or {},
    )


def produce_evidence():
    store = RevisionStore.create(load(RECOVERY_BASE))
    artifacts = ArtifactStore()
    frames = [
        artifacts.import_bytes(
            (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_bytes(),
            media_type="image/svg+xml",
        )
        for tick in TICKS
    ]
    observation_ids = []
    correspondence_ids = []
    inference_ids = []
    identity_id = None
    for source, target, source_tick, target_tick in zip(
        frames[:-1], frames[1:], TICKS[:-1], TICKS[1:], strict=True
    ):
        geometry = SVGGeometryObservationAdapter().propose(
            request(
                store,
                artifact_ids=(source.artifact_id, target.artifact_id),
                options={
                    "source_svg_artifact_id": source.artifact_id,
                    "target_svg_artifact_id": target.artifact_id,
                    "source_tick": source_tick,
                    "target_tick": target_tick,
                    "shape_id": TARGET_ENTITY,
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, geometry, artifacts)
        observation_id = geometry.preview_artifacts[0].artifact_id
        observation_ids.append(observation_id)
        correspondence = TemporalCorrespondenceAdapter().propose(
            request(store, artifact_ids=(observation_id,)), artifacts
        )
        ProposalAcceptor().accept(store, correspondence, artifacts)
        correspondence_id = correspondence.preview_artifacts[0].artifact_id
        correspondence_ids.append(correspondence_id)
        candidate = json.loads(artifacts.get(correspondence_id).content)["candidates"][0]
        if candidate["status"] != "SUPPORTED":
            raise AssertionError("Synthetic correspondence must be SUPPORTED")
        inference_ids.append(candidate["inference_id"])
        identity = TemporalIdentityPromotionAdapter().propose(
            request(
                store,
                artifact_ids=(correspondence_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, identity, artifacts)
        promoted_id = identity.preview.temporal_identities[0].stable_identity_id
        identity_id = identity_id or promoted_id
        if promoted_id != identity_id:
            raise AssertionError("Synthetic observations must extend one temporal identity")

    translation = ObservedTranslationMotionAdapter().propose(
        request(
            store,
            artifact_ids=correspondence_ids,
            options={
                "temporal_identity_id": identity_id,
                "inference_ids": inference_ids,
            },
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, translation, artifacts)
    translation_evidence_id = translation.preview_artifacts[0].artifact_id
    similarity = ObservedSimilarityMotionAdapter().propose(
        request(
            store,
            artifact_ids=(*observation_ids, *correspondence_ids),
            options={
                "temporal_identity_id": identity_id,
                "inference_ids": inference_ids,
            },
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, similarity, artifacts)
    similarity_evidence_id = similarity.preview_artifacts[0].artifact_id
    return {
        "store": store,
        "artifacts": artifacts,
        "observation_ids": tuple(observation_ids),
        "correspondence_ids": tuple(correspondence_ids),
        "inference_ids": tuple(inference_ids),
        "identity_id": identity_id,
        "translation_evidence_id": translation_evidence_id,
        "similarity_evidence_id": similarity_evidence_id,
    }


def bind_and_author(state):
    store, artifacts = state["store"], state["artifacts"]
    binding = TemporalMotionTargetBindingAdapter().propose(
        request(
            store,
            options={"temporal_identity_id": state["identity_id"], "group_id": GROUP_ID},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, binding, artifacts)
    binding_id = binding.preview.motion_target_bindings[0].binding_id
    for adapter, evidence_id in (
        (ObservedTranslationTracksAdapter(), state["translation_evidence_id"]),
        (ObservedScaleTracksAdapter(), state["similarity_evidence_id"]),
        (ObservedRotationTracksAdapter(), state["similarity_evidence_id"]),
    ):
        proposal = adapter.propose(
            request(
                store,
                artifact_ids=(evidence_id,),
                options={
                    "motion_target_binding_id": binding_id,
                    "ticks_per_second": 12,
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
    state["binding_id"] = binding_id
    return store.get_document(store.head)


class SyntheticMotionRecoveryTest(unittest.TestCase):
    def test_full_formal_recovery_round_trip(self) -> None:
        state = produce_evidence()
        recovered = bind_and_author(state)
        ground_truth = load(GROUND_TRUTH)
        recovered_motion = MotionEvaluator(recovered)
        truth_motion = MotionEvaluator(ground_truth)
        for tick in TICKS:
            recovered_transform = recovered_motion.sample_document(tick)["groups"][0]["transform"]
            truth_transform = truth_motion.sample_document(tick)["groups"][0]["transform"]
            for actual, expected in zip(
                recovered_transform["translate"], truth_transform["translate"], strict=True
            ):
                self.assertAlmostEqual(actual, expected, delta=TOLERANCE)
            self.assertAlmostEqual(
                recovered_transform["rotation_degrees"],
                truth_transform["rotation_degrees"],
                delta=TOLERANCE,
            )
            self.assertAlmostEqual(
                recovered_transform["scale"], truth_transform["scale"], delta=TOLERANCE
            )
        tracks = recovered["animation"]["content"]
        self.assertEqual(
            {track["target"]["property"] for track in tracks},
            {"translate.x", "translate.y", "scale", "rotation_degrees"},
        )
        self.assertTrue(all(track["interpolation"] == "linear" for track in tracks))
        by_property = {track["target"]["property"]: track for track in tracks}
        for property_name in ("translate.x", "translate.y"):
            provenance = by_property[property_name]["provenance"]
            self.assertEqual(provenance["evidence_artifact_id"], state["translation_evidence_id"])
            self.assertEqual(provenance["motion_target_binding_id"], state["binding_id"])
        for property_name in ("scale", "rotation_degrees"):
            provenance = by_property[property_name]["provenance"]
            self.assertEqual(provenance["evidence_artifact_id"], state["similarity_evidence_id"])
            self.assertEqual(provenance["motion_target_binding_id"], state["binding_id"])

        renderer = SVGRenderer(SVGRenderOptions(width=800, height=480, view_box=(0, 0, 200, 120)))
        for tick in TICKS:
            svg = renderer.render(recovered_motion.evaluate(tick).scene)
            root = ET.fromstring(svg)
            self.assertEqual(root.attrib["data-svm-document"], recovered["document_id"])

    def test_recovery_is_deterministic_from_frozen_observations(self) -> None:
        first = produce_evidence()
        first_document = bind_and_author(first)
        second = produce_evidence()
        second_document = bind_and_author(second)
        self.assertEqual(first["observation_ids"], second["observation_ids"])
        self.assertEqual(first["correspondence_ids"], second["correspondence_ids"])
        self.assertEqual(first["translation_evidence_id"], second["translation_evidence_id"])
        self.assertEqual(first["similarity_evidence_id"], second["similarity_evidence_id"])
        self.assertEqual(first["binding_id"], second["binding_id"])
        self.assertEqual(first_document["animation"], second_document["animation"])

    def test_missing_binding_and_unsupported_rotation_reject(self) -> None:
        state = produce_evidence()
        store, artifacts = state["store"], state["artifacts"]
        with self.assertRaises(ObservedRotationTracksError):
            ObservedRotationTracksAdapter().propose(
                request(
                    store,
                    artifact_ids=(state["similarity_evidence_id"],),
                    options={
                        "motion_target_binding_id": "motion-target-binding:" + "f" * 64,
                        "ticks_per_second": 12,
                    },
                ),
                artifacts,
            )

        original = artifacts.get(state["similarity_evidence_id"])
        payload = json.loads(original.content)
        payload["intervals"][0]["rotation_degrees"] = {"status": "UNCERTAIN", "value": None}
        uncertain = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        store.commit(
            store.head,
            Transaction(
                "transaction:accept-uncertain-rotation-fixture",
                (AppendReferencesChange((uncertain.document_reference(),)),),
            ),
        )
        binding = TemporalMotionTargetBindingAdapter().propose(
            request(
                store,
                options={"temporal_identity_id": state["identity_id"], "group_id": GROUP_ID},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, binding, artifacts)
        binding_id = binding.preview.motion_target_bindings[0].binding_id
        with self.assertRaisesRegex(ObservedRotationTracksError, "supported ordered contiguous"):
            ObservedRotationTracksAdapter().propose(
                request(
                    store,
                    artifact_ids=(uncertain.artifact_id,),
                    options={
                        "motion_target_binding_id": binding_id,
                        "ticks_per_second": 12,
                    },
                ),
                artifacts,
            )

    def test_wrong_target_forgery_existing_track_and_stale_proposal_fail_atomically(self) -> None:
        state = produce_evidence()
        store, artifacts = state["store"], state["artifacts"]
        binding = TemporalMotionTargetBindingAdapter().propose(
            request(
                store,
                options={"temporal_identity_id": state["identity_id"], "group_id": GROUP_ID},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, binding, artifacts)
        binding_id = binding.preview.motion_target_bindings[0].binding_id
        proposal = ObservedRotationTracksAdapter().propose(
            request(
                store,
                artifact_ids=(state["similarity_evidence_id"],),
                options={
                    "motion_target_binding_id": binding_id,
                    "ticks_per_second": 12,
                },
            ),
            artifacts,
        )
        verifier = proposal.transaction.changes[-1]
        forged_track = copy.deepcopy(verifier.authored_track)
        forged_track["target"]["group"] = "group:" + "f" * 64
        forged_verifier = replace(verifier, authored_track=forged_track)
        forged = replace(
            proposal,
            transaction=replace(
                proposal.transaction,
                changes=(*proposal.transaction.changes[:-1], forged_verifier),
            ),
        )
        before_head = store.head
        before = store.get_document(before_head)
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(store, forged, artifacts)
        self.assertEqual(store.head, before_head)
        self.assertEqual(store.get_document(before_head), before)

        ProposalAcceptor().accept(store, proposal, artifacts)
        with self.assertRaisesRegex(ObservedRotationTracksError, "explicit re-authoring"):
            ObservedRotationTracksAdapter().propose(
                request(
                    store,
                    artifact_ids=(state["similarity_evidence_id"],),
                    options={
                        "motion_target_binding_id": binding_id,
                        "ticks_per_second": 12,
                    },
                ),
                artifacts,
            )

        stale_state = produce_evidence()
        stale_store, stale_artifacts = stale_state["store"], stale_state["artifacts"]
        stale_binding = TemporalMotionTargetBindingAdapter().propose(
            request(
                stale_store,
                options={
                    "temporal_identity_id": stale_state["identity_id"],
                    "group_id": GROUP_ID,
                },
            ),
            stale_artifacts,
        )
        ProposalAcceptor().accept(stale_store, stale_binding, stale_artifacts)
        stale_binding_id = stale_binding.preview.motion_target_bindings[0].binding_id
        stale = ObservedRotationTracksAdapter().propose(
            request(
                stale_store,
                artifact_ids=(stale_state["similarity_evidence_id"],),
                options={
                    "motion_target_binding_id": stale_binding_id,
                    "ticks_per_second": 12,
                },
            ),
            stale_artifacts,
        )
        document = stale_store.get_document(stale_store.head)
        transform = copy.deepcopy(document["groups"][0]["transform"])
        transform["rotation_degrees"] = 11
        stale_store.commit(
            stale_store.head,
            Transaction(
                "transaction:stale-recovery-baseline",
                (SetGroupTransformChange(GROUP_ID, transform),),
            ),
        )
        stale_before = stale_store.get_document(stale_store.head)
        stale_head = stale_store.head
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(stale_store, stale, stale_artifacts)
        self.assertEqual(stale_store.head, stale_head)
        self.assertEqual(stale_store.get_document(stale_head), stale_before)


if __name__ == "__main__":
    unittest.main()
