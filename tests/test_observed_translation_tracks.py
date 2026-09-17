from __future__ import annotations

import copy
import json
import unittest
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
    SetKeyframeValueChange,
    Transaction,
)
from svm.adapters import (
    ObservedTranslationMotionAdapter,
    ObservedTranslationTracksAdapter,
    ObservedTranslationTracksError,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.temporal_correspondence import OBSERVATION_MEDIA_TYPE
from svm.evaluator import DocumentError, canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
GROUP_ID = "group:" + "1" * 64


def primitive(observation_id: str, bounds: list[int]) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "primitive_type": "ellipse",
        "bounds": bounds,
        "fill": "#FF0000",
    }


class ObservedTranslationTracksGoldenS2Test(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "022-group-transform.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()
        observations = {
            "schema_version": "svm-primitive-observations-0.1",
            "canvas": [200, 200],
            "frames": [
                {"tick": 0, "primitives": [primitive("observation:a", [10, 10, 20, 20])]},
                {
                    "tick": 24,
                    "primitives": [primitive("observation:b", [30, 25, 40, 35])],
                },
            ],
        }
        source = self.artifacts.import_bytes(
            canonical_bytes(observations),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "fixture@0.1"},
        )
        correspondence = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(source.artifact_id,),
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, correspondence, self.artifacts)
        self.r0_artifact_id = correspondence.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(self.r0_artifact_id).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        promotion = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.r0_artifact_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, promotion, self.artifacts)
        self.identity_id = promotion.preview.temporal_identities[0].stable_identity_id
        observed = ObservedTranslationMotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.r0_artifact_id,),
                options={
                    "temporal_identity_id": self.identity_id,
                    "inference_ids": [candidate["inference_id"]],
                },
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, observed, self.artifacts)
        self.motion_artifact_id = observed.preview_artifacts[0].artifact_id
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
        return ObservedTranslationTracksAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.motion_artifact_id,),
                options={
                    "motion_target_binding_id": self.binding_id,
                    "ticks_per_second": 24,
                },
            ),
            self.artifacts,
        )

    def add_motion_evidence(
        self, source_tick: int, target_tick: int, source_bounds: list[int], target_bounds: list[int]
    ) -> str:
        observations = {
            "schema_version": "svm-primitive-observations-0.1",
            "canvas": [200, 200],
            "frames": [
                {"tick": source_tick, "primitives": [primitive("observation:b", source_bounds)]},
                {"tick": target_tick, "primitives": [primitive("observation:c", target_bounds)]},
            ],
        }
        source = self.artifacts.import_bytes(
            canonical_bytes(observations),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "fixture@0.1"},
        )
        correspondence = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store, self.store.head, ("document",), artifact_ids=(source.artifact_id,)
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, correspondence, self.artifacts)
        r0_id = correspondence.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(r0_id).content)["candidates"][0]
        promotion = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(r0_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, promotion, self.artifacts)
        observed = ObservedTranslationMotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(r0_id,),
                options={
                    "temporal_identity_id": self.identity_id,
                    "inference_ids": [candidate["inference_id"]],
                },
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, observed, self.artifacts)
        return observed.preview_artifacts[0].artifact_id

    def reauthor_proposal(self, artifact_id: str):
        return ObservedTranslationTracksAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(artifact_id,),
                options={
                    "motion_target_binding_id": self.binding_id,
                    "ticks_per_second": 24,
                },
            ),
            self.artifacts,
        )

    def test_happy_path_previews_accepts_and_samples_linear_translation(self) -> None:
        before = self.store.get_document(self.store.head)
        proposal = self.proposal()
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(proposal.preview.group_id, GROUP_ID)
        self.assertEqual(proposal.preview.binding_id, self.binding_id)
        self.assertEqual(
            [
                (track.property_name, [(key.tick, key.value) for key in track.keyframes])
                for track in proposal.preview.tracks
            ],
            [("translate.x", [(0, 2), (24, 22.0)]), ("translate.y", [(0, 3), (24, 18.0)])],
        )
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(len(accepted["animation"]["content"]), 2)
        self.assertEqual(proposal.preview.mode, "CREATE")
        self.assertTrue(
            all(
                track["provenance"]["type"] == "ObservedTranslationTrack"
                for track in accepted["animation"]["content"]
            )
        )
        motion = MotionEvaluator(accepted)
        self.assertEqual(motion.sample_document(0)["groups"][0]["transform"]["translate"], [2, 3])
        self.assertEqual(
            motion.sample_document(12)["groups"][0]["transform"]["translate"], [12, 10.5]
        )
        self.assertEqual(
            motion.sample_document(24)["groups"][0]["transform"]["translate"], [22, 18]
        )

    def test_missing_binding_and_non_s0_evidence_are_rejected(self) -> None:
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.motion_artifact_id,),
            options={
                "motion_target_binding_id": "motion-target-binding:" + "0" * 64,
                "ticks_per_second": 24,
            },
        )
        with self.assertRaisesRegex(ObservedTranslationTracksError, "Binding is required"):
            ObservedTranslationTracksAdapter().propose(request, self.artifacts)
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(self.r0_artifact_id,),
            options={"motion_target_binding_id": self.binding_id, "ticks_per_second": 24},
        )
        with self.assertRaisesRegex(ObservedTranslationTracksError, "canonical S0"):
            ObservedTranslationTracksAdapter().propose(request, self.artifacts)

    def test_bound_group_is_the_only_authored_target_and_forgery_fails(self) -> None:
        proposal = self.proposal()
        for change in proposal.transaction.changes:
            if hasattr(change, "group_id"):
                self.assertEqual(change.group_id, GROUP_ID)
        forged = copy.deepcopy(proposal)
        create = next(
            change for change in forged.transaction.changes if hasattr(change, "group_id")
        )
        object.__setattr__(create, "group_id", "group:" + "9" * 64)
        with self.assertRaisesRegex(DocumentError, "missing Group"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

        forged = copy.deepcopy(proposal)
        keyframe = next(
            change for change in forged.transaction.changes if hasattr(change, "keyframe_id")
        )
        object.__setattr__(keyframe, "value", 999)
        with self.assertRaisesRegex(DocumentError, "do not match verified evidence"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_binding_survives_group_edit_and_new_proposal_uses_current_baseline(self) -> None:
        transform = {
            "translate": [10, -5],
            "rotation_degrees": 90,
            "scale": 2,
            "origin": [0, 0],
        }
        edit = Proposal(
            "proposal:edit-bound-group-before-s2",
            self.store.head,
            GeneratorProvenance("editor:group-transform", "0.1", "svm-core", "0.1"),
            Transaction(
                "transaction:edit-bound-group-before-s2",
                (SetGroupTransformChange(GROUP_ID, transform),),
            ),
        )
        ProposalAcceptor().accept(self.store, edit)
        document = self.store.get_document(self.store.head)
        self.assertEqual(document["motion_target_bindings"][0]["id"], self.binding_id)
        proposal = self.proposal()
        values = [[key.value for key in track.keyframes] for track in proposal.preview.tracks]
        self.assertEqual(values, [[10, 30.0], [-5, 10.0]])

    def test_pending_proposal_rejects_binding_group_or_source_revision_forgery(self) -> None:
        for field, message in (
            ("binding", "STALE_MOTION_TARGET_BINDING"),
            ("group", "STALE_GROUP"),
        ):
            proposal = self.proposal()
            guard = proposal.transaction.changes[-1]
            changed = copy.deepcopy(getattr(guard, field))
            changed["forged"] = True
            object.__setattr__(guard, field, changed)
            with self.subTest(field=field), self.assertRaisesRegex(DocumentError, message):
                ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        proposal = self.proposal()
        object.__setattr__(
            proposal.transaction.changes[-1], "source_revision_id", "revision:" + "f" * 64
        )
        with self.assertRaisesRegex(ProposalArtifactError, "source revision"):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def test_reauthor_previews_and_atomically_replaces_owned_pair(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        old_document = self.store.get_document(self.store.head)
        old_ids = [track["id"] for track in old_document["animation"]["content"]]
        new_evidence = self.add_motion_evidence(24, 48, [30, 25, 40, 35], [45, 20, 55, 30])
        before = self.store.get_document(self.store.head)
        proposal = self.reauthor_proposal(new_evidence)
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(proposal.preview.mode, "REPLACE")
        self.assertEqual({track.old_track_id for track in proposal.preview.tracks}, set(old_ids))
        self.assertEqual(
            {track.old_evidence_artifact_id for track in proposal.preview.tracks},
            {self.motion_artifact_id},
        )
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        tracks = accepted["animation"]["content"]
        self.assertEqual(len(tracks), 2)
        self.assertTrue(set(old_ids).isdisjoint({track["id"] for track in tracks}))
        motion = MotionEvaluator(accepted)
        self.assertEqual(
            motion.sample_document(48)["groups"][0]["transform"]["translate"], [17, -2]
        )

    def test_manual_or_partial_ownership_is_never_replaced(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        new_evidence = self.add_motion_evidence(24, 48, [30, 25, 40, 35], [45, 20, 55, 30])

        class RemoveOwnership:
            def __init__(self, count: int) -> None:
                self.count = count

            def apply(inner_self, document):
                for track in document["animation"]["content"][: inner_self.count]:
                    track.pop("provenance", None)

        for count, message in ((2, "not owned"), (1, "not owned")):
            with self.subTest(count=count):
                base = self.store.get_document(self.store.head)
                isolated = RevisionStore.create(base)
                isolated.commit(
                    isolated.head,
                    Transaction(f"transaction:manual-{count}", (RemoveOwnership(count),)),
                )
                request = AdapterRequest.from_store(
                    isolated,
                    isolated.head,
                    ("document",),
                    artifact_ids=(new_evidence,),
                    options={
                        "motion_target_binding_id": self.binding_id,
                        "ticks_per_second": 24,
                    },
                )
                with self.assertRaisesRegex(ObservedTranslationTracksError, message):
                    ObservedTranslationTracksAdapter().propose(request, self.artifacts)

    def test_pending_replacement_rejects_track_group_binding_and_forgery_atomically(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        new_evidence = self.add_motion_evidence(24, 48, [30, 25, 40, 35], [45, 20, 55, 30])
        proposal = self.reauthor_proposal(new_evidence)
        change = proposal.transaction.changes[0]
        before = self.store.get_document(self.store.head)

        forged = copy.deepcopy(proposal)
        replacement = copy.deepcopy(forged.transaction.changes[0].replacement_tracks)
        replacement[0]["keyframes"][1]["value"] = 999
        object.__setattr__(forged.transaction.changes[0], "replacement_tracks", replacement)
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)
        self.assertEqual(self.store.get_document(self.store.head), before)

        stale = copy.deepcopy(before)
        stale["animation"]["content"][0]["keyframes"][0]["value"] += 1
        with self.assertRaisesRegex(DocumentError, "STALE_TRANSLATION_TRACKS"):
            change.apply(stale)
        stale = copy.deepcopy(before)
        stale["groups"][0]["transform"]["translate"][0] += 1
        with self.assertRaisesRegex(DocumentError, "STALE_GROUP"):
            change.apply(stale)
        stale = copy.deepcopy(before)
        stale["motion_target_bindings"][0]["policy_identity"] += "-changed"
        with self.assertRaisesRegex(DocumentError, "STALE_MOTION_TARGET_BINDING"):
            change.apply(stale)

    def test_user_keyframe_edit_makes_pending_replacement_stale(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        new_evidence = self.add_motion_evidence(24, 48, [30, 25, 40, 35], [45, 20, 55, 30])
        proposal = self.reauthor_proposal(new_evidence)
        track = self.store.get_document(self.store.head)["animation"]["content"][0]
        edit = Proposal(
            "proposal:edit-observed-track",
            self.store.head,
            GeneratorProvenance("editor:motion", "0.1", "svm-core", "0.1"),
            Transaction(
                "transaction:edit-observed-track",
                (SetKeyframeValueChange(track["id"], track["keyframes"][0]["id"], 9),),
            ),
        )
        ProposalAcceptor().accept(self.store, edit)
        with self.assertRaisesRegex(Exception, "does not match head"):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def test_reauthor_after_legal_group_edit_uses_current_baseline(self) -> None:
        ProposalAcceptor().accept(self.store, self.proposal(), self.artifacts)
        transform = {
            "translate": [10, -5],
            "rotation_degrees": 90,
            "scale": 2,
            "origin": [0, 0],
        }
        edit = Proposal(
            "proposal:edit-bound-group-before-s3",
            self.store.head,
            GeneratorProvenance("editor:group-transform", "0.1", "svm-core", "0.1"),
            Transaction(
                "transaction:edit-bound-group-before-s3",
                (SetGroupTransformChange(GROUP_ID, transform),),
            ),
        )
        ProposalAcceptor().accept(self.store, edit)
        self.assertEqual(
            self.store.get_document(self.store.head)["motion_target_bindings"][0]["id"],
            self.binding_id,
        )
        new_evidence = self.add_motion_evidence(24, 48, [30, 25, 40, 35], [45, 20, 55, 30])
        proposal = self.reauthor_proposal(new_evidence)
        self.assertEqual(
            [[key.value for key in track.keyframes] for track in proposal.preview.tracks],
            [[10, 25.0], [-5, -10.0]],
        )


if __name__ == "__main__":
    unittest.main()
