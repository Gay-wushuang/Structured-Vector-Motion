from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from test_shared_camera_multi_object_recovery import (
    ANCHOR,
    GROUP_A,
    GROUP_B,
    TARGET_A,
    TARGET_B,
    TICKS,
    documents,
    observe_lineage,
    request,
)

from svm import (
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
    GeometryTranslationTracksAdapter,
    ObservedCameraSimilarityAdapter,
    ObservedCameraTracksAdapter,
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    ObservedTranslationTracksAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.geometry_translation_tracks import POLICY_IDENTITY
from svm.adapters.observed_translation_tracks import ObservedTranslationTracksError
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.revisions import AddKeyframeChange


def case_documents(
    *,
    camera=False,
    rotation=True,
    scale=True,
    translation=False,
    baseline_translation=(0, 0),
    baseline_scale=1,
):
    base, truth = documents()
    for document in (base, truth):
        document["groups"][0]["transform"]["origin"] = [37, 43]
        document["groups"][0]["transform"]["translate"] = list(baseline_translation)
        document["groups"][0]["transform"]["scale"] = baseline_scale
        document["construction"]["operations"][0]["parameters"] = {
            "d": "M 30 30 L 70 33 L 63 70 L 46 57 L 30 61 Z",
            "bounds": [30, 30, 70, 70],
        }
    values = {
        "translate.x": (0, 3, 6, 4) if translation else (0, 0, 0, 0),
        "translate.y": (0, -2, 1, 3) if translation else (0, 0, 0, 0),
        "rotation_degrees": (10, 18, 26, 15) if rotation else (10, 10, 10, 10),
        "scale": (1, 1.08, 0.97, 1.03) if scale else (1, 1, 1, 1),
    }
    for track in truth["animation"]["content"]:
        if track["target"].get("group") == GROUP_A:
            for keyframe, value in zip(
                track["keyframes"], values[track["target"]["property"]], strict=True
            ):
                if track["target"]["property"].startswith("translate."):
                    value += baseline_translation[
                        0 if track["target"]["property"].endswith("x") else 1
                    ]
                elif track["target"]["property"] == "scale":
                    value *= baseline_scale
                keyframe["value"] = value
    if not camera:
        truth["animation"]["content"] = [
            track for track in truth["animation"]["content"] if "camera" not in track["target"]
        ]
    return base, truth


def recovery_case(**options):
    base, truth = case_documents(**options)
    store, artifacts = RevisionStore.create(base), ArtifactStore()
    renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
    evaluator = MotionEvaluator(truth)
    frames = [
        artifacts.import_bytes(
            renderer.render(evaluator.evaluate(t).scene).encode(), media_type="image/svg+xml"
        )
        for t in TICKS
    ]
    target = observe_lineage(store, artifacts, frames, TARGET_A)
    target["frames"] = frames
    target["raw_translation_id"] = target["translation_id"]
    camera_id = None
    if options.get("camera"):
        anchor = observe_lineage(store, artifacts, frames, ANCHOR)
        proposal = ObservedCameraSimilarityAdapter().propose(
            request(
                store, artifact_ids=(anchor["similarity_id"],), options={"anchor_entity_id": ANCHOR}
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        camera_id = proposal.preview_artifacts[0].artifact_id
        proposal = CameraCompensatedMotionAdapter().propose(
            request(
                store,
                artifact_ids=(camera_id, target["translation_id"], target["similarity_id"]),
                options={
                    "anchor_entity_id": ANCHOR,
                    "target_temporal_identity_id": target["identity_id"],
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        target["translation_id"] = proposal.preview_artifacts[0].artifact_id
        target["similarity_id"] = proposal.preview_artifacts[1].artifact_id
    binding = TemporalMotionTargetBindingAdapter().propose(
        request(
            store, options={"temporal_identity_id": target["identity_id"], "group_id": GROUP_A}
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, binding, artifacts)
    target["binding_id"] = binding.preview.motion_target_bindings[0].binding_id
    return store, artifacts, target, truth, camera_id


def translation_proposal(store, artifacts, target):
    return GeometryTranslationTracksAdapter().propose(
        request(
            store,
            artifact_ids=(target["similarity_id"],),
            options={"motion_target_binding_id": target["binding_id"], "ticks_per_second": 12},
        ),
        artifacts,
    )


class GeometryCorrectTranslationTest(unittest.TestCase):
    def check_recovery(self, **options):
        store, artifacts, target, truth, camera_id = recovery_case(**options)
        before = copy.deepcopy(store.get_document(store.head))
        proposal = translation_proposal(store, artifacts, target)
        self.assertEqual(store.get_document(store.head), before)
        self.assertEqual(len(proposal.preview.tracks), 2)
        ProposalAcceptor().accept(store, proposal, artifacts)
        after = store.get_document(store.head)
        for field in (
            "entities",
            "groups",
            "construction",
            "presentation",
            "references",
            "temporal_identities",
            "motion_target_bindings",
        ):
            self.assertEqual(before[field], after[field])
        for adapter in (ObservedScaleTracksAdapter(), ObservedRotationTracksAdapter()):
            p = adapter.propose(
                request(
                    store,
                    artifact_ids=(target["similarity_id"],),
                    options={
                        "motion_target_binding_id": target["binding_id"],
                        "ticks_per_second": 12,
                    },
                ),
                artifacts,
            )
            ProposalAcceptor().accept(store, p, artifacts)
        if camera_id:
            p = ObservedCameraTracksAdapter().propose(
                request(
                    store,
                    artifact_ids=(camera_id,),
                    options={"camera_target": "presentation", "ticks_per_second": 12},
                ),
                artifacts,
            )
            ProposalAcceptor().accept(store, p, artifacts)
        actual = MotionEvaluator(store.get_document(store.head))
        expected = MotionEvaluator(truth)
        for tick in TICKS:
            left = actual.sample_document(tick)["groups"][0]["transform"]["translate"]
            right = expected.sample_document(tick)["groups"][0]["transform"]["translate"]
            for a, b in zip(left, right, strict=True):
                self.assertAlmostEqual(a, b, delta=3e-8)
            # Re-render and re-observe the target, testing composition as well as channel values.
            from svm.adapters.svg_geometry_observations import derive_svg_polygon_observations

            renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
            frames = [
                artifacts.import_bytes(
                    renderer.render(e.evaluate(tick).scene).encode(), media_type="image/svg+xml"
                )
                for e in (actual, expected)
            ]
            pair = derive_svg_polygon_observations(*frames, TARGET_A, tick, tick + 1)["frames"]
            points = [f["primitives"][0]["geometry"]["points"] for f in pair]
            for p, q in zip(*points, strict=True):
                for a, b in zip(p, q, strict=True):
                    self.assertAlmostEqual(a, b, delta=3e-8)

    def test_arbitrary_pivot_combined_zero_translation(self):
        self.check_recovery()

    def test_known_translation_with_moving_camera(self):
        self.check_recovery(camera=True, translation=True)

    def test_rotation_only_arbitrary_pivot(self):
        self.check_recovery(scale=False)

    def test_scale_only_arbitrary_pivot(self):
        self.check_recovery(rotation=False)

    def test_known_translation_and_nonidentity_baseline(self):
        self.check_recovery(translation=True, baseline_translation=(3, -2), baseline_scale=1.2)

    def test_no_motion_preserves_baseline(self):
        # Target B moves, so SVG snapshots differ; repeated-frame identity is out of scope.
        self.check_recovery(
            rotation=False, scale=False, baseline_translation=(3, -2), baseline_scale=1.2
        )

    def test_legacy_displacement_unchanged_and_not_group_translation(self):
        store, artifacts, target, _, _ = recovery_case()
        evidence = artifacts.get(target["raw_translation_id"])
        original_bytes = evidence.content
        payload = json.loads(original_bytes)
        for interval in payload["intervals"]:
            correspondence = json.loads(
                artifacts.get(interval["correspondence_evidence_artifact_id"]).content
            )
            candidate = next(
                c
                for c in correspondence["candidates"]
                if c["inference_id"] == interval["correspondence_inference_id"]
            )
            self.assertEqual(list(interval["translation"].values()), candidate["displacement"])
        old = ObservedTranslationTracksAdapter().propose(
            request(
                store,
                artifact_ids=(target["translation_id"],),
                options={"motion_target_binding_id": target["binding_id"], "ticks_per_second": 12},
            ),
            artifacts,
        )
        self.assertTrue(any(abs(k.value) > 0.01 for t in old.preview.tracks for k in t.keyframes))
        new = translation_proposal(store, artifacts, target)
        self.assertTrue(all(abs(k.value) < 3e-8 for t in new.preview.tracks for k in t.keyframes))
        ProposalAcceptor().accept(store, new, artifacts)
        self.assertEqual(artifacts.get(evidence.artifact_id).content, original_bytes)

    def test_determinism_and_preview(self):
        first, second = (
            recovery_case(camera=True, translation=True),
            recovery_case(camera=True, translation=True),
        )
        proposals = []
        for store, artifacts, target, _, _ in (first, second):
            before, head = store.get_document(store.head), store.head
            proposal = translation_proposal(store, artifacts, target)
            self.assertEqual(store.head, head)
            self.assertEqual(store.get_document(head), before)
            self.assertEqual(proposal, translation_proposal(store, artifacts, target))
            ProposalAcceptor().accept(store, proposal, artifacts)
            proposals.append(proposal)
            for track in store.get_document(store.head)["animation"]["content"]:
                self.assertEqual(track["provenance"]["authoring_identity"], POLICY_IDENTITY)
        self.assertEqual(first[2]["similarity_id"], second[2]["similarity_id"])
        self.assertEqual(proposals[0], proposals[1])
        self.assertEqual(first[0].head, second[0].head)

    def test_unrelated_target_tracks_are_unchanged_with_shared_camera(self):
        store, artifacts, target, _, camera_id = recovery_case(camera=True, translation=True)
        other = observe_lineage(store, artifacts, target["frames"], TARGET_B)
        compensation = CameraCompensatedMotionAdapter().propose(
            request(
                store,
                artifact_ids=(camera_id, other["translation_id"], other["similarity_id"]),
                options={
                    "anchor_entity_id": ANCHOR,
                    "target_temporal_identity_id": other["identity_id"],
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, compensation, artifacts)
        other["similarity_id"] = compensation.preview_artifacts[1].artifact_id
        binding = TemporalMotionTargetBindingAdapter().propose(
            request(
                store, options={"temporal_identity_id": other["identity_id"], "group_id": GROUP_B}
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, binding, artifacts)
        other["binding_id"] = binding.preview.motion_target_bindings[0].binding_id
        ProposalAcceptor().accept(store, translation_proposal(store, artifacts, other), artifacts)
        before = canonical_bytes(store.get_document(store.head)["animation"]["content"])
        ProposalAcceptor().accept(store, translation_proposal(store, artifacts, target), artifacts)
        after = [
            t
            for t in store.get_document(store.head)["animation"]["content"]
            if t["target"]["group"] == GROUP_B
        ]
        self.assertEqual(before, canonical_bytes(after))

    def test_forged_keyframe_and_compensation_sources_reject_atomically(self):
        store, artifacts, target, _, _ = recovery_case(camera=True)
        proposal = translation_proposal(store, artifacts, target)
        changes = list(proposal.transaction.changes)
        i = next(i for i, c in enumerate(changes) if isinstance(c, AddKeyframeChange))
        changes[i] = replace(changes[i], value=999)
        forged = replace(
            proposal, transaction=replace(proposal.transaction, changes=tuple(changes))
        )
        head, before, count = store.head, store.get_document(store.head), len(store.revisions)
        with self.assertRaises(ValueError):
            ProposalAcceptor().accept(store, forged, artifacts)
        verification = proposal.transaction.changes[-1]
        missing = replace(verification, source_references=verification.source_references[:-1])
        forged = replace(
            proposal,
            transaction=replace(
                proposal.transaction, changes=(*proposal.transaction.changes[:-1], missing)
            ),
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(store, forged, artifacts)
        forged_group = copy.deepcopy(verification.group)
        forged_group["id"] = GROUP_B
        wrong = replace(verification, group=forged_group)
        forged = replace(
            proposal,
            transaction=replace(
                proposal.transaction, changes=(*proposal.transaction.changes[:-1], wrong)
            ),
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(store, forged, artifacts)
        self.assertEqual((store.head, len(store.revisions)), (head, count))
        self.assertEqual(store.get_document(head), before)

    def test_stale_pivot_and_existing_target_reject(self):
        store, artifacts, target, _, _ = recovery_case()
        proposal = translation_proposal(store, artifacts, target)
        transform = copy.deepcopy(store.get_document(store.head)["groups"][0]["transform"])
        transform["origin"] = [12, 17]
        store.commit(
            store.head,
            Transaction(
                "transaction:changed-pivot", (SetGroupTransformChange(GROUP_A, transform),)
            ),
        )
        head = store.head
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(store, proposal, artifacts)
        self.assertEqual(store.head, head)
        fresh = translation_proposal(store, artifacts, target)
        self.assertNotEqual(proposal.preview.tracks[0].track_id, fresh.preview.tracks[0].track_id)
        ProposalAcceptor().accept(store, fresh, artifacts)
        with self.assertRaises(ObservedTranslationTracksError):
            translation_proposal(store, artifacts, target)
        # Legacy replacement cannot claim ownership of this new authoring policy.
        with self.assertRaises(ObservedTranslationTracksError):
            ObservedTranslationTracksAdapter().propose(
                request(
                    store,
                    artifact_ids=(target["translation_id"],),
                    options={
                        "motion_target_binding_id": target["binding_id"],
                        "ticks_per_second": 12,
                    },
                ),
                artifacts,
            )

    def test_checked_in_counterexamples(self):
        fixture = (
            Path(__file__).resolve().parents[1] / "examples" / "031-geometry-correct-translation"
        )
        for name, options in (
            ("ground-truth", {}),
            ("camera-ground-truth", {"camera": True, "translation": True}),
        ):
            base, truth = case_documents(**options)
            self.assertEqual(json.loads((fixture / f"{name}.svm.json").read_text()), truth)
            self.assertEqual(json.loads((fixture / "recovery-base.svm.json").read_text()), base)

    def test_missing_binding_and_legacy_displacement_input_reject(self):
        store, artifacts, target, _, _ = recovery_case()
        head = store.head
        for binding_id, evidence_id in (
            ("motion-target-binding:missing", target["similarity_id"]),
            (target["binding_id"], target["translation_id"]),
        ):
            with (
                self.subTest(binding=binding_id, evidence=evidence_id),
                self.assertRaises(ValueError),
            ):
                GeometryTranslationTracksAdapter().propose(
                    request(
                        store,
                        artifact_ids=(evidence_id,),
                        options={"motion_target_binding_id": binding_id, "ticks_per_second": 12},
                    ),
                    artifacts,
                )
        self.assertEqual(store.head, head)

    def test_unsupported_rotation_is_not_authoring_authority(self):
        from test_observed_similarity_motion import primitive

        from svm.adapters import (
            ObservedSimilarityMotionAdapter,
            TemporalCorrespondenceAdapter,
            TemporalIdentityPromotionAdapter,
        )
        from svm.adapters.temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2

        base, _ = case_documents()
        store, artifacts = RevisionStore.create(base), ArtifactStore()
        points = [[30, 30], [70, 33], [63, 70], [46, 57], [30, 61]]
        observation = artifacts.import_bytes(
            canonical_bytes(
                {
                    "schema_version": "svm-primitive-observations-0.2",
                    "canvas": [200, 120],
                    "frames": [
                        {
                            "tick": t,
                            "primitives": [
                                primitive(f"observation:{t}", points, symmetry="half-turn")
                            ],
                        }
                        for t in (0, 12)
                    ],
                }
            ),
            media_type=OBSERVATION_MEDIA_TYPE_V2,
        )
        r0 = TemporalCorrespondenceAdapter().propose(
            request(store, artifact_ids=(observation.artifact_id,)), artifacts
        )
        ProposalAcceptor().accept(store, r0, artifacts)
        r0_id = r0.preview_artifacts[0].artifact_id
        inference = json.loads(artifacts.get(r0_id).content)["candidates"][0]["inference_id"]
        r1 = TemporalIdentityPromotionAdapter().propose(
            request(store, artifact_ids=(r0_id,), options={"inference_ids": [inference]}), artifacts
        )
        ProposalAcceptor().accept(store, r1, artifacts)
        identity = r1.preview.temporal_identities[0].stable_identity_id
        s4 = ObservedSimilarityMotionAdapter().propose(
            request(
                store,
                artifact_ids=(r0_id, observation.artifact_id),
                options={"temporal_identity_id": identity, "inference_ids": [inference]},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, s4, artifacts)
        binding = TemporalMotionTargetBindingAdapter().propose(
            request(store, options={"temporal_identity_id": identity, "group_id": GROUP_A}),
            artifacts,
        )
        ProposalAcceptor().accept(store, binding, artifacts)
        head = store.head
        with self.assertRaises(ValueError):
            translation_proposal(
                store,
                artifacts,
                {
                    "similarity_id": s4.preview_artifacts[0].artifact_id,
                    "binding_id": binding.preview.motion_target_bindings[0].binding_id,
                },
            )
        self.assertEqual(store.head, head)


if __name__ == "__main__":
    unittest.main()
