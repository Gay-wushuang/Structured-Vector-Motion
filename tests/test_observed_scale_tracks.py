from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from svm import (
    AdapterRequest,
    AppendReferencesChange,
    ArtifactKind,
    ArtifactStore,
    GeneratorProvenance,
    MotionEvaluator,
    Proposal,
    ProposalAcceptor,
    ProposalArtifactError,
    ReplaceObservedScaleTrackChange,
    RevisionStore,
    SetGroupTransformChange,
    SetKeyframeValueChange,
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
from svm.evaluator import DocumentError, canonical_bytes

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

    def accept_evidence_ratio(self, ratio: float, *, status: str = "SUPPORTED") -> str:
        original = self.artifacts.get(self.evidence_id)
        payload = json.loads(original.content)
        payload["intervals"][0]["scale"] = {"status": status, "value": ratio}
        artifact = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:accept-scale-evidence-fixture",
                (AppendReferencesChange((artifact.document_reference(),)),),
            ),
        )
        return artifact.artifact_id

    def replacement_proposal(self, evidence_id: str):
        return ObservedScaleTracksAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(evidence_id,),
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

    def test_owned_scale_track_is_explicitly_reauthored_from_static_baseline(self) -> None:
        created = self.proposal()
        ProposalAcceptor().accept(self.store, created, self.artifacts)
        old_track = self.store.get_document(self.store.head)["animation"]["content"][0]
        evidence = self.accept_evidence_ratio(0.5)
        before = self.store.get_document(self.store.head)
        proposal = self.replacement_proposal(evidence)
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(proposal.preview.mode, "REPLACE")
        self.assertEqual(proposal.preview.old.track_id, old_track["id"])
        self.assertEqual(proposal.preview.old.evidence_artifact_id, self.evidence_id)
        self.assertEqual(proposal.preview.new.evidence_artifact_id, evidence)
        self.assertNotEqual(proposal.preview.new.track_id, old_track["id"])
        self.assertEqual([item.value for item in proposal.preview.new.keyframes], [2, 1.0])
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(len(accepted["animation"]["content"]), 1)
        track = accepted["animation"]["content"][0]
        self.assertEqual(track["id"], proposal.preview.new.track_id)
        self.assertEqual(track["provenance"]["evidence_artifact_id"], evidence)
        self.assertEqual(
            MotionEvaluator(accepted).sample_document(24)["groups"][0]["transform"]["scale"], 1
        )

    def test_manual_and_malformed_owned_scale_tracks_are_never_replaced(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        evidence = self.accept_evidence_ratio(0.5)
        base = self.store.get_document(self.store.head)
        cases = (
            ("manual", None),
            ("type", "OtherTrack"),
            ("authoring_identity", "forged"),
            ("motion_target_binding_id", "motion-target-binding:" + "a" * 64),
            ("evidence_artifact_id", "bad"),
            ("source_revision_id", "bad"),
            ("target_group", "group:" + "b" * 64),
            ("target_property", "rotation_degrees"),
        )
        for field, value in cases:
            document = copy.deepcopy(base)
            provenance = document["animation"]["content"][0].get("provenance")
            if field == "manual":
                document["animation"]["content"][0].pop("provenance")
            elif field == "target_group":
                document["animation"]["content"][0]["target"]["group"] = value
            elif field == "target_property":
                document["animation"]["content"][0]["target"]["property"] = value
            else:
                provenance[field] = value
            request = AdapterRequest(
                self.store.head,
                document,
                ("document",),
                artifact_ids=(evidence,),
                options={"motion_target_binding_id": self.binding_id, "ticks_per_second": 24},
            )
            with self.subTest(field=field), self.assertRaises(ObservedScaleTracksError):
                ObservedScaleTracksAdapter().propose(request, self.artifacts)

    def test_replacement_rejects_unsupported_scale_component(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        for status in ("UNCERTAIN", "REJECTED"):
            evidence = self.accept_evidence_ratio(0.5, status=status)
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(
                    ObservedScaleTracksError, "supported ordered contiguous chain"
                ),
            ):
                self.replacement_proposal(evidence)

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

    def test_pending_replacement_is_stale_after_track_group_or_binding_change(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        evidence = self.accept_evidence_ratio(0.5)
        proposal = self.replacement_proposal(evidence)
        old_track = self.store.get_document(self.store.head)["animation"]["content"][0]
        edit = Transaction(
            "transaction:edit-old-scale-keyframe",
            (SetKeyframeValueChange(old_track["id"], old_track["keyframes"][-1]["id"], 9),),
        )
        self.store.commit(self.store.head, edit)
        edited = self.store.get_document(self.store.head)
        with self.assertRaisesRegex(Exception, "does not match head"):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        self.assertEqual(
            self.store.get_document(self.store.head)["animation"]["content"][0]["keyframes"][-1][
                "value"
            ],
            9,
        )

        for field, message in (("group", "STALE_GROUP"), ("binding", "STALE_MOTION_TARGET")):
            document = copy.deepcopy(edited)
            change = copy.deepcopy(proposal.transaction.changes[0])
            if field == "group":
                document["groups"][0]["transform"]["scale"] = 4
            else:
                document["motion_target_bindings"] = []
            with self.subTest(field=field), self.assertRaisesRegex(Exception, message):
                change.apply(document)

    def test_fresh_replacement_after_group_edit_uses_current_static_baseline(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        evidence = self.accept_evidence_ratio(0.5)
        transform = copy.deepcopy(
            self.store.get_document(self.store.head)["groups"][0]["transform"]
        )
        transform["scale"] = 4
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:legal-static-scale-edit",
                (SetGroupTransformChange(GROUP_ID, transform),),
            ),
        )
        document = self.store.get_document(self.store.head)
        self.assertEqual(document["motion_target_bindings"][0]["id"], self.binding_id)
        proposal = self.replacement_proposal(evidence)
        self.assertEqual(proposal.preview.mode, "REPLACE")
        self.assertEqual(proposal.preview.new.baseline_scale, 4)
        self.assertEqual([item.value for item in proposal.preview.new.keyframes], [4, 2.0])

    def test_forged_replacement_fields_fail_closed(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        evidence = self.accept_evidence_ratio(0.5)
        proposal = self.replacement_proposal(evidence)
        before = self.store.get_document(self.store.head)

        def mutate(field: str, change: Any) -> None:
            if field == "track_id":
                change.replacement_track["id"] = "track:observed-scale:" + "f" * 64
            elif field == "target":
                change.replacement_track["target"]["property"] = "rotation_degrees"
            elif field == "tick":
                change.replacement_track["keyframes"][-1]["tick"] = 48
            elif field == "value":
                change.replacement_track["keyframes"][-1]["value"] = 20
            elif field == "provenance":
                change.replacement_track["provenance"]["type"] = "ManualTrack"
            elif field == "binding":
                change.binding["id"] = "motion-target-binding:" + "e" * 64
            elif field == "baseline":
                change.group["transform"]["scale"] = 20
            elif field == "evidence":
                object.__setattr__(
                    change,
                    "evidence_reference",
                    copy.deepcopy(
                        next(
                            item for item in before["references"] if item["id"] == self.evidence_id
                        )
                    ),
                )

        for field in (
            "track_id",
            "target",
            "tick",
            "value",
            "provenance",
            "evidence",
            "binding",
            "baseline",
        ):
            forged = copy.deepcopy(proposal)
            mutate(field, forged.transaction.changes[0])
            with (
                self.subTest(field=field),
                self.assertRaises((ProposalArtifactError, DocumentError)),
            ):
                ProposalAcceptor().accept(self.store, forged, self.artifacts)
            self.assertEqual(self.store.get_document(self.store.head), before)

    def test_direct_core_replacement_rejects_manual_and_accepts_owned_track(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        evidence = self.accept_evidence_ratio(0.5)
        proposal = self.replacement_proposal(evidence)
        change = proposal.transaction.changes[0]
        self.assertIsInstance(change, ReplaceObservedScaleTrackChange)
        base = self.store.get_document(self.store.head)

        manual = copy.deepcopy(base)
        manual["animation"]["content"][0].pop("provenance")
        invalid = copy.deepcopy(change)
        object.__setattr__(invalid, "animation_before", copy.deepcopy(manual["animation"]))
        object.__setattr__(
            invalid, "existing_track", copy.deepcopy(manual["animation"]["content"][0])
        )
        with self.assertRaisesRegex(Exception, "ownership"):
            Transaction("transaction:manual-scale-replacement", (invalid,)).apply(manual)

        revision = self.store.commit(
            self.store.head,
            Transaction("transaction:direct-owned-scale-replacement", (copy.deepcopy(change),)),
        )
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(len(accepted["animation"]["content"]), 1)
        self.assertEqual(
            accepted["animation"]["content"][0]["provenance"]["evidence_artifact_id"],
            evidence,
        )

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

        _prefix, target_b = pop_frame(artifacts, width=20, height=10)
        producer_b = POPGeometryObservationAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(prefix.artifact_id, source.artifact_id, target_b.artifact_id),
                options={
                    "source_output_artifact_id": source.artifact_id,
                    "target_output_artifact_id": target_b.artifact_id,
                    "source_tick": 0,
                    "target_tick": 24,
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, producer_b, artifacts)
        observation_b = producer_b.preview_artifacts[0].artifact_id
        r0_b = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                store, store.head, ("document",), artifact_ids=(observation_b,)
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, r0_b, artifacts)
        r0_b_id = r0_b.preview_artifacts[0].artifact_id
        candidate_b = json.loads(artifacts.get(r0_b_id).content)["candidates"][0]
        r1_b = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(r0_b_id,),
                options={"inference_ids": [candidate_b["inference_id"]]},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, r1_b, artifacts)
        self.assertEqual(r1_b.preview.temporal_identities[0].stable_identity_id, identity_id)
        s4_b = ObservedSimilarityMotionAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(observation_b, r0_b_id),
                options={
                    "temporal_identity_id": identity_id,
                    "inference_ids": [candidate_b["inference_id"]],
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, s4_b, artifacts)
        replacement = ObservedScaleTracksAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(s4_b.preview_artifacts[0].artifact_id,),
                options={
                    "motion_target_binding_id": binding.preview.motion_target_bindings[
                        0
                    ].binding_id,
                    "ticks_per_second": 24,
                },
            ),
            artifacts,
        )
        self.assertEqual(replacement.preview.mode, "REPLACE")
        replaced_revision = ProposalAcceptor().accept(store, replacement, artifacts)
        replaced = store.get_document(replaced_revision.revision_id)
        self.assertEqual(len(replaced["animation"]["content"]), 1)
        self.assertEqual(
            [item["value"] for item in replaced["animation"]["content"][0]["keyframes"]],
            [2, 1.0],
        )
        self.assertEqual(
            MotionEvaluator(replaced).sample_document(24)["groups"][0]["transform"]["scale"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
