from __future__ import annotations

import copy
import json
import unittest
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
    CameraCompensatedMotionAdapter,
    CameraCompensationError,
    ObservedCameraSimilarityAdapter,
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
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "029-synthetic-camera-compensation"
GROUND_TRUTH = FIXTURE / "ground-truth.svm.json"
RECOVERY_BASE = FIXTURE / "recovery-base.svm.json"
TICKS = (0, 12, 24, 36)
ANCHOR = "entity:camera-anchor"
TARGET = "entity:recovery-target"
GROUP = "group:" + "1" * 64
TOLERANCE = 2e-8


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


def observe_lineage(store, artifacts, frames, shape_id):
    geometry_ids, correspondence_ids, inference_ids = [], [], []
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
                    "shape_id": shape_id,
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, geometry, artifacts)
        geometry_id = geometry.preview_artifacts[0].artifact_id
        geometry_ids.append(geometry_id)
        correspondence = TemporalCorrespondenceAdapter().propose(
            request(store, artifact_ids=(geometry_id,)), artifacts
        )
        ProposalAcceptor().accept(store, correspondence, artifacts)
        correspondence_id = correspondence.preview_artifacts[0].artifact_id
        correspondence_ids.append(correspondence_id)
        candidate = json.loads(artifacts.get(correspondence_id).content)["candidates"][0]
        if candidate["status"] != "SUPPORTED":
            raise AssertionError("Synthetic camera correspondence must be SUPPORTED")
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
        promoted = identity.preview.temporal_identities[0].stable_identity_id
        identity_id = identity_id or promoted
        if promoted != identity_id:
            raise AssertionError("One shape must extend one temporal identity")
    translation = ObservedTranslationMotionAdapter().propose(
        request(
            store,
            artifact_ids=correspondence_ids,
            options={"temporal_identity_id": identity_id, "inference_ids": inference_ids},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, translation, artifacts)
    similarity = ObservedSimilarityMotionAdapter().propose(
        request(
            store,
            artifact_ids=(*geometry_ids, *correspondence_ids),
            options={"temporal_identity_id": identity_id, "inference_ids": inference_ids},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, similarity, artifacts)
    return {
        "identity_id": identity_id,
        "translation_id": translation.preview_artifacts[0].artifact_id,
        "similarity_id": similarity.preview_artifacts[0].artifact_id,
    }


def produce_compensated(*, accept_compensation: bool = True):
    store = RevisionStore.create(load(RECOVERY_BASE))
    artifacts = ArtifactStore()
    frames = [
        artifacts.import_bytes(
            (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_bytes(),
            media_type="image/svg+xml",
        )
        for tick in TICKS
    ]
    anchor = observe_lineage(store, artifacts, frames, ANCHOR)
    target = observe_lineage(store, artifacts, frames, TARGET)
    camera = ObservedCameraSimilarityAdapter().propose(
        request(
            store,
            artifact_ids=(anchor["similarity_id"],),
            options={"anchor_entity_id": ANCHOR},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, camera, artifacts)
    camera_id = camera.preview_artifacts[0].artifact_id
    compensation = CameraCompensatedMotionAdapter().propose(
        request(
            store,
            artifact_ids=(
                camera_id,
                target["translation_id"],
                target["similarity_id"],
            ),
            options={
                "anchor_entity_id": ANCHOR,
                "target_temporal_identity_id": target["identity_id"],
            },
        ),
        artifacts,
    )
    if accept_compensation:
        ProposalAcceptor().accept(store, compensation, artifacts)
    return {
        "store": store,
        "artifacts": artifacts,
        "anchor": anchor,
        "target": target,
        "camera_id": camera_id,
        "camera_proposal": camera,
        "compensation_proposal": compensation,
        "translation_id": compensation.preview_artifacts[0].artifact_id,
        "similarity_id": compensation.preview_artifacts[1].artifact_id,
    }


def bind_and_author(state):
    store, artifacts = state["store"], state["artifacts"]
    binding = TemporalMotionTargetBindingAdapter().propose(
        request(
            store,
            options={"temporal_identity_id": state["target"]["identity_id"], "group_id": GROUP},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, binding, artifacts)
    binding_id = binding.preview.motion_target_bindings[0].binding_id
    for adapter, evidence_id in (
        (ObservedTranslationTracksAdapter(), state["translation_id"]),
        (ObservedScaleTracksAdapter(), state["similarity_id"]),
        (ObservedRotationTracksAdapter(), state["similarity_id"]),
    ):
        proposal = adapter.propose(
            request(
                store,
                artifact_ids=(evidence_id,),
                options={"motion_target_binding_id": binding_id, "ticks_per_second": 12},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
    state["binding_id"] = binding_id
    return store.get_document(store.head)


class SyntheticCameraCompensationTest(unittest.TestCase):
    def test_frozen_observations_come_from_formal_renderer(self) -> None:
        truth = load(GROUND_TRUTH)
        evaluator = MotionEvaluator(truth)
        renderer = SVGRenderer(SVGRenderOptions(width=800, height=480, view_box=(0, 0, 200, 120)))
        for tick in TICKS:
            expected = (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_text(
                encoding="utf-8"
            )
            self.assertEqual(renderer.render(evaluator.evaluate(tick).scene), expected)

    def test_world_to_view_convention_and_formal_recovery(self) -> None:
        state = produce_compensated()
        recovered = bind_and_author(state)
        truth = load(GROUND_TRUTH)
        recovered_motion = MotionEvaluator(recovered)
        truth_motion = MotionEvaluator(truth)
        maximum_error = 0.0
        for tick in TICKS:
            actual = recovered_motion.sample_document(tick)["groups"][0]["transform"]
            expected = truth_motion.sample_document(tick)["groups"][0]["transform"]
            values = (
                (*actual["translate"], actual["rotation_degrees"], actual["scale"]),
                (*expected["translate"], expected["rotation_degrees"], expected["scale"]),
            )
            for left, right in zip(*values, strict=True):
                maximum_error = max(maximum_error, abs(left - right))
                self.assertAlmostEqual(left, right, delta=TOLERANCE)
        self.assertLess(maximum_error, TOLERANCE)
        camera_payload = json.loads(state["artifacts"].get(state["camera_id"]).content)
        self.assertEqual(camera_payload["anchor_entity_id"], ANCHOR)
        self.assertEqual(len(camera_payload["intervals"]), 3)
        for track in recovered["animation"]["content"]:
            self.assertIn(
                track["provenance"]["evidence_artifact_id"],
                {state["translation_id"], state["similarity_id"]},
            )

    def test_determinism(self) -> None:
        first, second = produce_compensated(), produce_compensated()
        first_document, second_document = bind_and_author(first), bind_and_author(second)
        self.assertEqual(first["camera_id"], second["camera_id"])
        self.assertEqual(first["translation_id"], second["translation_id"])
        self.assertEqual(first["similarity_id"], second["similarity_id"])
        self.assertEqual(first_document["animation"], second_document["animation"])

    def test_missing_or_moving_anchor_and_mismatched_sources_reject(self) -> None:
        state = produce_compensated()
        with self.assertRaisesRegex(CameraCompensationError, "anchor Entity is missing"):
            ObservedCameraSimilarityAdapter().propose(
                request(
                    state["store"],
                    artifact_ids=(state["anchor"]["similarity_id"],),
                    options={"anchor_entity_id": "entity:missing"},
                ),
                state["artifacts"],
            )
        moving = load(RECOVERY_BASE)
        moving["animation"] = {
            "semantics_version": "svm-motion@0.6",
            "timebase": {"ticks_per_second": 12},
            "content": [
                {
                    "id": "track:moving-anchor-opacity",
                    "target": {"entity": ANCHOR, "property": "opacity"},
                    "value_type": "number",
                    "interpolation": "linear",
                    "keyframes": [{"id": "keyframe:moving-anchor", "tick": 0, "value": 1}],
                }
            ],
            "construction_scheduling_hints": [],
        }
        moving_store = RevisionStore.create(moving)
        with self.assertRaisesRegex(CameraCompensationError, "not static"):
            ObservedCameraSimilarityAdapter().propose(
                request(
                    moving_store,
                    artifact_ids=(state["anchor"]["similarity_id"],),
                    options={"anchor_entity_id": ANCHOR},
                ),
                state["artifacts"],
            )
        with self.assertRaisesRegex(CameraCompensationError, "temporal identity"):
            CameraCompensatedMotionAdapter().propose(
                request(
                    state["store"],
                    artifact_ids=(
                        state["camera_id"],
                        state["target"]["translation_id"],
                        state["anchor"]["similarity_id"],
                    ),
                    options={
                        "anchor_entity_id": ANCHOR,
                        "target_temporal_identity_id": state["target"]["identity_id"],
                    },
                ),
                state["artifacts"],
            )
        with self.assertRaisesRegex(CameraCompensationError, "another anchor"):
            ObservedCameraSimilarityAdapter().propose(
                request(
                    state["store"],
                    artifact_ids=(state["target"]["similarity_id"],),
                    options={"anchor_entity_id": ANCHOR},
                ),
                state["artifacts"],
            )

    def test_unsupported_anchor_and_tick_mismatch_reject(self) -> None:
        state = produce_compensated()
        artifacts, store = state["artifacts"], state["store"]
        anchor_source = artifacts.get(state["anchor"]["similarity_id"])
        unsupported_payload = json.loads(anchor_source.content)
        unsupported_payload["intervals"][0]["rotation_degrees"] = {
            "status": "UNCERTAIN",
            "value": None,
            "ambiguity": "rotation_symmetry",
        }
        unsupported = artifacts.import_bytes(
            canonical_bytes(unsupported_payload),
            media_type=anchor_source.media_type,
            kind=anchor_source.kind,
            provenance=anchor_source.provenance,
        )
        store.commit(
            store.head,
            Transaction(
                "transaction:accept-unsupported-anchor-fixture",
                (AppendReferencesChange((unsupported.document_reference(),)),),
            ),
        )
        with self.assertRaisesRegex(CameraCompensationError, "must support"):
            ObservedCameraSimilarityAdapter().propose(
                request(
                    store,
                    artifact_ids=(unsupported.artifact_id,),
                    options={"anchor_entity_id": ANCHOR},
                ),
                artifacts,
            )

        translation_source = artifacts.get(state["target"]["translation_id"])
        short_payload = json.loads(translation_source.content)
        short_payload["intervals"].pop()
        shortened = artifacts.import_bytes(
            canonical_bytes(short_payload),
            media_type=translation_source.media_type,
            kind=translation_source.kind,
            provenance=translation_source.provenance,
        )
        store.commit(
            store.head,
            Transaction(
                "transaction:accept-short-target-fixture",
                (AppendReferencesChange((shortened.document_reference(),)),),
            ),
        )
        with self.assertRaisesRegex(CameraCompensationError, "intervals must match"):
            CameraCompensatedMotionAdapter().propose(
                request(
                    store,
                    artifact_ids=(
                        state["camera_id"],
                        shortened.artifact_id,
                        state["target"]["similarity_id"],
                    ),
                    options={
                        "anchor_entity_id": ANCHOR,
                        "target_temporal_identity_id": state["target"]["identity_id"],
                    },
                ),
                artifacts,
            )

    def test_forgery_missing_binding_and_stale_state_fail_atomically(self) -> None:
        state = produce_compensated(accept_compensation=False)
        with self.assertRaisesRegex(Exception, "Binding"):
            ObservedRotationTracksAdapter().propose(
                request(
                    state["store"],
                    artifact_ids=(state["similarity_id"],),
                    options={"motion_target_binding_id": "binding:missing", "ticks_per_second": 12},
                ),
                state["artifacts"],
            )
        proposal = state["compensation_proposal"]
        change = proposal.transaction.changes[0]
        original = state["artifacts"].get(state["translation_id"])
        forged_payload = json.loads(original.content)
        forged_payload["intervals"][0]["translation"]["dx"] += 1
        forged = state["artifacts"].import_bytes(
            canonical_bytes(forged_payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        forged_change = replace(
            change,
            evidence_references=(
                forged.document_reference(),
                change.evidence_references[1],
            ),
        )
        forged_proposal = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(forged_change,)),
            required_artifact_ids=tuple(
                forged.artifact_id if item == original.artifact_id else item
                for item in proposal.required_artifact_ids
            ),
        )
        before = state["store"].get_document(state["store"].head)
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(state["store"], forged_proposal, state["artifacts"])
        self.assertEqual(state["store"].get_document(state["store"].head), before)

        mutation_cases = (
            (0, lambda payload: payload.update(policy_identity="forged-policy")),
            (0, lambda payload: payload.update(temporal_identity_id="temporal-identity:forged")),
            (0, lambda payload: payload["source_artifact_ids"].pop()),
            (0, lambda payload: payload["intervals"][0].update(camera_interval_id="forged")),
            (
                1,
                lambda payload: payload["intervals"][0]["rotation_degrees"].update(value=99),
            ),
            (1, lambda payload: payload["intervals"][0]["scale"].update(value=9)),
        )
        for output_index, mutate in mutation_cases:
            original_reference = change.evidence_references[output_index]
            original_snapshot = state["artifacts"].get(original_reference["id"])
            payload = json.loads(original_snapshot.content)
            mutate(payload)
            forged_snapshot = state["artifacts"].import_bytes(
                canonical_bytes(payload),
                media_type=original_snapshot.media_type,
                kind=original_snapshot.kind,
                provenance=original_snapshot.provenance,
            )
            references = list(change.evidence_references)
            references[output_index] = forged_snapshot.document_reference()
            forged_change = replace(change, evidence_references=tuple(references))
            forged_proposal = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(forged_change,)),
                required_artifact_ids=tuple(
                    forged_snapshot.artifact_id if item == original_snapshot.artifact_id else item
                    for item in proposal.required_artifact_ids
                ),
            )
            with self.subTest(output=output_index, payload=payload):
                with self.assertRaises(ProposalArtifactError):
                    ProposalAcceptor().accept(state["store"], forged_proposal, state["artifacts"])
                self.assertEqual(state["store"].get_document(state["store"].head), before)

        fresh = produce_compensated(accept_compensation=False)
        pending = fresh["compensation_proposal"]
        group = next(
            item
            for item in fresh["store"].get_document(fresh["store"].head)["groups"]
            if item["id"] == GROUP
        )
        changed = copy.deepcopy(group["transform"])
        changed["translate"] = [3, 0]
        fresh["store"].commit(
            fresh["store"].head,
            Transaction(
                "transaction:stale-camera-recovery", (SetGroupTransformChange(GROUP, changed),)
            ),
        )
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(fresh["store"], pending, fresh["artifacts"])


if __name__ == "__main__":
    unittest.main()
