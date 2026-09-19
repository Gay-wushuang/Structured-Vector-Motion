from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    GeneratorProvenance,
    MotionEvaluator,
    Proposal,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
    SetGroupTransformChange,
    Transaction,
)
from svm.adapters import (
    ObservedScaleTracksAdapter,
    ObservedScaleTracksError,
    ObservedSimilarityMotionAdapter,
    POPGeometryObservationAdapter,
    POPTokenExporter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.observed_scale_tracks import _absolute_samples
from svm.adapters.temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
GROUP_ID = "group:" + "1" * 64
COMMIT = "d5489b039d876839b58b61c512205713b3ab6909"
CHECKPOINT = "sha256:" + "4" * 64


def primitive(observation_id: str, points: list[list[float]]) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "primitive_type": "path",
        "bounds": [
            min(p[0] for p in points),
            min(p[1] for p in points),
            max(p[0] for p in points),
            max(p[1] for p in points),
        ],
        "fill": "#FF0000",
        "geometry": {
            "type": "ordered-landmarks",
            "points": points,
            "rotation_symmetry": "continuous",
        },
    }


def pop_row(x: float, y: float, angle: float, width: float, height: float, shape: int) -> list[int]:
    return [
        round(x * 2),
        512 + round(y * 2),
        1024 + round(angle * 3),
        1294 + round(width * 4),
        1806 + round(height * 4),
        2318 + shape + 1,
        2574 + 110,
        2702 + 20,
        2830 + 40,
    ]


def pop_frame(artifacts: ArtifactStore, *, width: float, height: float):
    background = pop_row(0, 0, 0, 100, 100, -1)
    shape = pop_row(100, 100, 0, width, height, 0)
    return POPTokenExporter().export(
        artifacts,
        background + shape,
        prefix_length=1,
        commit=COMMIT,
        model_id="fixture/s5a-pop",
        checkpoint_hash=CHECKPOINT,
        seed=7,
        decoding={
            "strategy": "field-aware-sampling",
            "target_steps": 2,
            "sampling_policy_identity": "pop/gpt-sampling-config@d5489b0",
            "configuration": {"schedule": "upstream-default"},
        },
    )


class ObservedScaleTracksGoldenS5ATest(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "022-group-transform.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()
        source_points = [[20.0, 20.0], [30.0, 20.0], [22.0, 28.0]]
        target_points = [[30.0, 30.0], [45.0, 30.0], [33.0, 42.0]]
        observations = {
            "schema_version": "svm-primitive-observations-0.2",
            "canvas": [200, 200],
            "frames": [
                {"tick": 0, "primitives": [primitive("observation:a", source_points)]},
                {"tick": 24, "primitives": [primitive("observation:b", target_points)]},
            ],
        }
        source = self.artifacts.import_bytes(
            canonical_bytes(observations),
            media_type=OBSERVATION_MEDIA_TYPE_V2,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "s5a-fixture@0.1"},
        )
        r0 = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store, self.store.head, ("document",), artifact_ids=(source.artifact_id,)
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, r0, self.artifacts)
        self.r0_id = r0.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(self.r0_id).content)["candidates"][0]
        r1 = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.r0_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, r1, self.artifacts)
        self.identity_id = r1.preview.temporal_identities[0].stable_identity_id
        s4 = ObservedSimilarityMotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(source.artifact_id, self.r0_id),
                options={
                    "temporal_identity_id": self.identity_id,
                    "inference_ids": [candidate["inference_id"]],
                },
            ),
            self.artifacts,
        )
        interval = json.loads(self.artifacts.get(s4.preview_artifacts[0].artifact_id).content)[
            "intervals"
        ][0]
        self.assertEqual(interval["status"], "UNCERTAIN")
        self.assertEqual(interval["rotation_degrees"]["status"], "UNCERTAIN")
        self.assertEqual(interval["scale"]["status"], "SUPPORTED")
        ProposalAcceptor().accept(self.store, s4, self.artifacts)
        self.evidence_id = s4.preview_artifacts[0].artifact_id
        binding = TemporalMotionTargetBindingAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                options={"temporal_identity_id": self.identity_id, "group_id": GROUP_ID},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, binding, self.artifacts)
        self.binding_id = binding.preview.motion_target_bindings[0].binding_id

    def proposal(self):
        return ObservedScaleTracksAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.evidence_id,),
                options={"motion_target_binding_id": self.binding_id, "ticks_per_second": 24},
            ),
            self.artifacts,
        )

    def test_uncertain_overall_supported_scale_authors_absolute_track(self) -> None:
        before = self.store.get_document(self.store.head)
        proposal = self.proposal()
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(proposal.preview.baseline_scale, 2)
        self.assertEqual(
            [(k.tick, k.value, k.source_ratio) for k in proposal.preview.keyframes],
            [(0, 2, None), (24, 3.0, 1.5)],
        )
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        track = accepted["animation"]["content"][0]
        self.assertEqual(track["target"], {"group": GROUP_ID, "property": "scale"})
        self.assertEqual(track["provenance"]["type"], "ObservedScaleTrack")
        motion = MotionEvaluator(accepted)
        self.assertEqual(motion.sample_document(0)["groups"][0]["transform"]["scale"], 2)
        self.assertEqual(motion.sample_document(12)["groups"][0]["transform"]["scale"], 2.5)
        self.assertEqual(motion.sample_document(24)["groups"][0]["transform"]["scale"], 3)

    def test_existing_scale_track_fails_closed(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        with self.assertRaisesRegex(ObservedScaleTracksError, "explicit re-authoring"):
            self.proposal()

    def test_no_binding_fails_closed(self) -> None:
        document = self.store.get_document(self.store.head)
        document["motion_target_bindings"] = []
        isolated = RevisionStore.create(document)
        with self.assertRaisesRegex(ObservedScaleTracksError, "Binding"):
            ObservedScaleTracksAdapter().propose(
                AdapterRequest.from_store(
                    isolated,
                    isolated.head,
                    ("document",),
                    artifact_ids=(self.evidence_id,),
                    options={"motion_target_binding_id": self.binding_id, "ticks_per_second": 24},
                ),
                self.artifacts,
            )

    def test_forged_track_and_keyframe_fields_are_rejected_atomically(self) -> None:
        def mutate_target(track):
            track["target"]["property"] = "rotation_degrees"

        def mutate_id(track):
            track["id"] = "track:forged"

        def mutate_tick(track):
            track["keyframes"][-1]["tick"] = 48

        def mutate_value(track):
            track["keyframes"][-1]["value"] = 30

        for label, mutate in (
            ("target", mutate_target),
            ("track_id", mutate_id),
            ("tick", mutate_tick),
            ("value", mutate_value),
        ):
            proposal = self.proposal()
            guard = proposal.transaction.changes[-1]
            forged_track = copy.deepcopy(guard.authored_track)
            mutate(forged_track)
            forged_guard = replace(guard, authored_track=forged_track)
            forged = replace(
                proposal,
                transaction=replace(
                    proposal.transaction,
                    changes=(*proposal.transaction.changes[:-1], forged_guard),
                ),
            )
            before = self.store.get_document(self.store.head)
            with (
                self.subTest(label=label),
                self.assertRaisesRegex(ProposalArtifactError, "does not match evidence"),
            ):
                ProposalAcceptor().accept(self.store, forged, self.artifacts)
            self.assertEqual(self.store.get_document(self.store.head), before)

    def test_pending_proposal_is_stale_after_group_scale_edit(self) -> None:
        proposal = self.proposal()
        transform = copy.deepcopy(
            self.store.get_document(self.store.head)["groups"][0]["transform"]
        )
        transform["scale"] = 4
        edit = Proposal(
            "proposal:edit-scale",
            self.store.head,
            GeneratorProvenance("editor:group-transform", "0.1", "svm-core", "0.1"),
            Transaction("transaction:edit-scale", (SetGroupTransformChange(GROUP_ID, transform),)),
        )
        ProposalAcceptor().accept(self.store, edit)
        with self.assertRaisesRegex(Exception, "does not match head"):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        fresh = self.proposal()
        self.assertEqual([k.value for k in fresh.preview.keyframes], [4, 6.0])

    def test_multiple_interval_accumulation_and_invalid_component_status(self) -> None:
        intervals = [
            {"source_tick": 0, "target_tick": 24, "scale": {"status": "SUPPORTED", "value": 1.5}},
            {"source_tick": 24, "target_tick": 48, "scale": {"status": "SUPPORTED", "value": 0.5}},
        ]
        self.assertEqual(
            _absolute_samples(intervals, 2), ((0, 2, None), (24, 3.0, 1.5), (48, 1.5, 0.5))
        )
        for status in ("UNCERTAIN", "REJECTED"):
            invalid = copy.deepcopy(intervals)
            invalid[0]["scale"]["status"] = status
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(
                    ObservedScaleTracksError, "supported ordered contiguous chain"
                ),
            ):
                _absolute_samples(invalid, 2)

    def test_wrong_binding_identity_is_rejected(self) -> None:
        document = self.store.get_document(self.store.head)
        original = self.artifacts.get(self.evidence_id)
        payload = json.loads(original.content)
        payload["temporal_identity_id"] = "temporal-identity:wrong"
        wrong = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        document["references"].append(wrong.document_reference())
        isolated = RevisionStore.create(document)
        with self.assertRaisesRegex(ObservedScaleTracksError, "identity does not match"):
            ObservedScaleTracksAdapter().propose(
                AdapterRequest.from_store(
                    isolated,
                    isolated.head,
                    ("document",),
                    artifact_ids=(wrong.artifact_id,),
                    options={
                        "motion_target_binding_id": self.binding_id,
                        "ticks_per_second": 24,
                    },
                ),
                self.artifacts,
            )

    def test_real_pop_to_s4_to_s5a(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "022-group-transform.svm.json").read_text(encoding="utf-8")
        )
        store = RevisionStore.create(document)
        artifacts = ArtifactStore()
        prefix, source = pop_frame(artifacts, width=40, height=20)
        _prefix, target = pop_frame(artifacts, width=60, height=30)
        producer = POPGeometryObservationAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(prefix.artifact_id, source.artifact_id, target.artifact_id),
                options={
                    "source_output_artifact_id": source.artifact_id,
                    "target_output_artifact_id": target.artifact_id,
                    "source_tick": 0,
                    "target_tick": 24,
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, producer, artifacts)
        observation_id = producer.preview_artifacts[0].artifact_id
        r0 = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                store, store.head, ("document",), artifact_ids=(observation_id,)
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, r0, artifacts)
        r0_id = r0.preview_artifacts[0].artifact_id
        candidate = json.loads(artifacts.get(r0_id).content)["candidates"][0]
        r1 = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(r0_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, r1, artifacts)
        identity_id = r1.preview.temporal_identities[0].stable_identity_id
        s4 = ObservedSimilarityMotionAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(observation_id, r0_id),
                options={
                    "temporal_identity_id": identity_id,
                    "inference_ids": [candidate["inference_id"]],
                },
            ),
            artifacts,
        )
        interval = json.loads(artifacts.get(s4.preview_artifacts[0].artifact_id).content)[
            "intervals"
        ][0]
        self.assertEqual(interval["status"], "UNCERTAIN")
        self.assertEqual(interval["rotation_degrees"]["status"], "UNCERTAIN")
        self.assertEqual(interval["scale"]["status"], "SUPPORTED")
        ProposalAcceptor().accept(store, s4, artifacts)
        binding = TemporalMotionTargetBindingAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                options={"temporal_identity_id": identity_id, "group_id": GROUP_ID},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, binding, artifacts)
        s5a = ObservedScaleTracksAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(s4.preview_artifacts[0].artifact_id,),
                options={
                    "motion_target_binding_id": binding.preview.motion_target_bindings[
                        0
                    ].binding_id,
                    "ticks_per_second": 24,
                },
            ),
            artifacts,
        )
        revision = ProposalAcceptor().accept(store, s5a, artifacts)
        accepted = store.get_document(revision.revision_id)
        self.assertEqual(
            [keyframe["value"] for keyframe in accepted["animation"]["content"][0]["keyframes"]],
            [2, 3.0],
        )


if __name__ == "__main__":
    unittest.main()
