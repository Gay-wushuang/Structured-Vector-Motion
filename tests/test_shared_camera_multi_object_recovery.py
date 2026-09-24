from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import (
    ArtifactStore,
    MotionEvaluator,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
)
from svm.adapters import (
    CameraCompensatedMotionAdapter,
    CameraCompensationError,
    ObservedCameraSimilarityAdapter,
    ObservedCameraTracksAdapter,
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
from svm.adapters.observed_translation_tracks import ObservedTranslationTracksError
from svm.adapters.svg_geometry_observations import derive_svg_polygon_observations
from svm.evaluator import DocumentError, canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
BASE_FIXTURE = ROOT / "examples" / "029-synthetic-camera-compensation"
FIXTURE = ROOT / "examples" / "030-shared-camera-multi-object-recovery"
TICKS = (0, 12, 24, 36)
ANCHOR = "entity:shared-camera-anchor"
TARGET_A = "entity:shared-camera-target-a"
TARGET_B = "entity:shared-camera-target-b"
COMPANION_A = "entity:shared-camera-companion-a"
COMPANION_B = "entity:shared-camera-companion-b"
GROUP_A = "group:" + "a" * 64
GROUP_B = "group:" + "b" * 64
TOLERANCE = 3e-8


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _keyframes(prefix: str, values: tuple[int | float, ...]) -> list[dict]:
    return [
        {"id": f"keyframe:s10a-{prefix}-{tick:03d}", "tick": tick, "value": value}
        for tick, value in zip(TICKS, values, strict=True)
    ]


def _track(track_id: str, target: dict, values: tuple[int | float, ...]) -> dict:
    return {
        "id": f"track:s10a-{track_id}",
        "target": target,
        "value_type": "number",
        "interpolation": "linear",
        "keyframes": _keyframes(track_id, values),
    }


def documents() -> tuple[dict, dict]:
    base = load(BASE_FIXTURE / "recovery-base.svm.json")
    provenance_a = copy.deepcopy(base["groups"][0]["provenance"])
    provenance_b = {
        **provenance_a,
        "candidate_id": "candidate:group:" + "4" * 64,
        "inference_id": "inference:group:" + "5" * 64,
    }
    base["document_id"] = "document:shared-camera-multi-object-recovery-base"
    base["entities"] = [
        {"id": COMPANION_A, "name": "Target A Group Companion"},
        {"id": COMPANION_B, "name": "Target B Group Companion"},
        {"id": TARGET_A, "name": "Asymmetric Target A"},
        {"id": TARGET_B, "name": "Asymmetric Target B"},
        {"id": ANCHOR, "name": "Static Shared Camera Anchor"},
    ]
    base["groups"] = [
        {
            "id": GROUP_A,
            "kind": "explicit-group",
            "members": [COMPANION_A, TARGET_A],
            "transform": {
                "translate": [0, 0],
                "rotation_degrees": 10,
                "scale": 1,
                "origin": [50, 50],
            },
            "provenance": provenance_a,
        },
        {
            "id": GROUP_B,
            "kind": "explicit-group",
            "members": [COMPANION_B, TARGET_B],
            "transform": {
                "translate": [0, 0],
                "rotation_degrees": -5,
                "scale": 1,
                "origin": [145, 80],
            },
            "provenance": provenance_b,
        },
    ]
    base["construction"] = {
        "operations": [
            {
                "id": "op:s10a-target-a",
                "type": "CreatePath",
                "inputs": {},
                "parameters": {
                    "d": "M 30 30 L 70 30 L 70 70 L 50 60 L 30 70 Z",
                    "bounds": [30, 30, 70, 70],
                },
            },
            {
                "id": "op:s10a-target-b",
                "type": "CreatePath",
                "inputs": {},
                "parameters": {
                    "d": "M 120 60 L 170 60 L 170 100 L 142 91 L 120 100 Z",
                    "bounds": [120, 60, 170, 100],
                },
            },
            {
                "id": "op:s10a-anchor",
                "type": "CreatePath",
                "inputs": {},
                "parameters": {
                    "d": "M 86 18 L 112 21 L 108 42 L 97 34 L 82 39 Z",
                    "bounds": [82, 18, 112, 42],
                },
            },
            {
                "id": "op:s10a-companion-a",
                "type": "CreateEllipse",
                "inputs": {},
                "parameters": {"cx": 45, "cy": 45, "rx": 2, "ry": 2},
            },
            {
                "id": "op:s10a-companion-b",
                "type": "CreateEllipse",
                "inputs": {},
                "parameters": {"cx": 145, "cy": 78, "rx": 2, "ry": 2},
            },
        ],
        "output_bindings": [
            {"entity": TARGET_A, "property": "geometry", "slot": "op:s10a-target-a.geometry"},
            {"entity": TARGET_B, "property": "geometry", "slot": "op:s10a-target-b.geometry"},
            {"entity": ANCHOR, "property": "geometry", "slot": "op:s10a-anchor.geometry"},
            {
                "entity": COMPANION_A,
                "property": "geometry",
                "slot": "op:s10a-companion-a.geometry",
            },
            {
                "entity": COMPANION_B,
                "property": "geometry",
                "slot": "op:s10a-companion-b.geometry",
            },
        ],
        "refinement_stages": [],
    }
    base["presentation"] = {
        "render_stack": [TARGET_A, TARGET_B, ANCHOR],
        "styles": [
            {
                "entity": TARGET_A,
                "fill": "#CC3344",
                "stroke": "none",
                "stroke_width": 0,
                "opacity": 1,
            },
            {
                "entity": TARGET_B,
                "fill": "#4A69BD",
                "stroke": "none",
                "stroke_width": 0,
                "opacity": 1,
            },
            {
                "entity": ANCHOR,
                "fill": "#238A72",
                "stroke": "none",
                "stroke_width": 0,
                "opacity": 1,
            },
        ],
        "camera": {"position": [0, 0], "rotation_degrees": 0, "scale": 1},
    }
    base["animation"] = {"content": [], "construction_scheduling_hints": []}

    truth = copy.deepcopy(base)
    truth["document_id"] = "document:shared-camera-multi-object-ground-truth"
    truth["animation"] = {
        "semantics_version": "svm-motion@0.6",
        "timebase": {"ticks_per_second": 12},
        "content": [
            _track("a-x", {"group": GROUP_A, "property": "translate.x"}, (0, 10, 24, 35)),
            _track("a-y", {"group": GROUP_A, "property": "translate.y"}, (0, 3, -2, 4)),
            _track("a-r", {"group": GROUP_A, "property": "rotation_degrees"}, (10, 25, 40, 30)),
            _track("a-s", {"group": GROUP_A, "property": "scale"}, (1, 1.1, 1.2, 0.95)),
            _track("b-x", {"group": GROUP_B, "property": "translate.x"}, (0, -4, -8, -12)),
            _track("b-y", {"group": GROUP_B, "property": "translate.y"}, (0, 4, 7, 5)),
            _track("b-r", {"group": GROUP_B, "property": "rotation_degrees"}, (-5, -14, -23, -12)),
            _track("b-s", {"group": GROUP_B, "property": "scale"}, (1, 0.95, 1.03, 1.1)),
            _track("camera-x", {"camera": "presentation", "property": "position.x"}, (0, 2, 4, 6)),
            _track("camera-y", {"camera": "presentation", "property": "position.y"}, (0, -1, 1, 0)),
            _track(
                "camera-r",
                {"camera": "presentation", "property": "rotation_degrees"},
                (0, 3, -2, 4),
            ),
            _track(
                "camera-s", {"camera": "presentation", "property": "scale"}, (1, 1.03, 0.98, 1.04)
            ),
        ],
        "construction_scheduling_hints": [],
    }
    return base, truth


def request(store, *, artifact_ids=(), options=None):
    from svm import AdapterRequest

    return AdapterRequest.from_store(
        store,
        store.head,
        ("document",),
        artifact_ids=tuple(artifact_ids),
        options=options or {},
    )


def observe_lineage(
    store,
    artifacts,
    frames,
    shape_id,
    *,
    observation_adapter=None,
    ticks=TICKS,
    identity_adapter=None,
):
    geometry_ids, correspondence_ids, inference_ids = [], [], []
    identity_id = None
    for source, target, source_tick, target_tick in zip(
        frames[:-1], frames[1:], ticks[:-1], ticks[1:], strict=True
    ):
        geometry = (observation_adapter or SVGGeometryObservationAdapter()).propose(
            request(
                store,
                artifact_ids=tuple(dict.fromkeys((source.artifact_id, target.artifact_id))),
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
            raise AssertionError(f"S10A synthetic correspondence must be SUPPORTED: {candidate}")
        inference_ids.append(candidate["inference_id"])
        identity = (identity_adapter or TemporalIdentityPromotionAdapter()).propose(
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
            raise AssertionError("One target must extend one Temporal Identity")
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
        "geometry_ids": tuple(geometry_ids),
        "correspondence_ids": tuple(correspondence_ids),
        "identity_id": identity_id,
        "translation_id": translation.preview_artifacts[0].artifact_id,
        "similarity_id": similarity.preview_artifacts[0].artifact_id,
    }


def produce_recovery():
    recovery, _ = documents()
    store = RevisionStore.create(recovery)
    artifacts = ArtifactStore()
    frames = [
        artifacts.import_bytes(
            (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_bytes(),
            media_type="image/svg+xml",
        )
        for tick in TICKS
    ]
    anchor = observe_lineage(store, artifacts, frames, ANCHOR)
    targets = {
        "a": observe_lineage(store, artifacts, frames, TARGET_A),
        "b": observe_lineage(store, artifacts, frames, TARGET_B),
    }
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
    for target in targets.values():
        compensation = CameraCompensatedMotionAdapter().propose(
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
        ProposalAcceptor().accept(store, compensation, artifacts)
        target["compensated_translation_id"] = compensation.preview_artifacts[0].artifact_id
        target["compensated_similarity_id"] = compensation.preview_artifacts[1].artifact_id
    return {
        "store": store,
        "artifacts": artifacts,
        "anchor": anchor,
        "targets": targets,
        "camera_id": camera_id,
    }


def author_target(state, label, group_id):
    store, artifacts = state["store"], state["artifacts"]
    target = state["targets"][label]
    binding = TemporalMotionTargetBindingAdapter().propose(
        request(
            store,
            options={"temporal_identity_id": target["identity_id"], "group_id": group_id},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, binding, artifacts)
    binding_id = binding.preview.motion_target_bindings[0].binding_id
    target["binding_id"] = binding_id
    for adapter, evidence_id in (
        (ObservedTranslationTracksAdapter(), target["compensated_translation_id"]),
        (ObservedScaleTracksAdapter(), target["compensated_similarity_id"]),
        (ObservedRotationTracksAdapter(), target["compensated_similarity_id"]),
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


def author_all(state):
    author_target(state, "a", GROUP_A)
    document_after_a = state["store"].get_document(state["store"].head)
    a_tracks = [
        copy.deepcopy(track)
        for track in document_after_a["animation"]["content"]
        if track.get("target", {}).get("group") == GROUP_A
    ]
    author_target(state, "b", GROUP_B)
    after_b = state["store"].get_document(state["store"].head)
    if a_tracks != [
        track
        for track in after_b["animation"]["content"]
        if track.get("target", {}).get("group") == GROUP_A
    ]:
        raise AssertionError("Authoring Target B mutated Target A Tracks")
    camera = ObservedCameraTracksAdapter().propose(
        request(
            state["store"],
            artifact_ids=(state["camera_id"],),
            options={"camera_target": "presentation", "ticks_per_second": 12},
        ),
        state["artifacts"],
    )
    ProposalAcceptor().accept(state["store"], camera, state["artifacts"])
    state["camera_track_ids"] = tuple(track.track_id for track in camera.preview.tracks)
    return state["store"].get_document(state["store"].head)


class SharedCameraMultiObjectRecoveryTest(unittest.TestCase):
    def test_frozen_observations_come_from_ground_truth_renderer(self) -> None:
        _, truth = documents()
        evaluator = MotionEvaluator(truth)
        renderer = SVGRenderer(SVGRenderOptions(width=800, height=480, view_box=(0, 0, 200, 120)))
        for tick in TICKS:
            expected = (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_text(
                encoding="utf-8"
            )
            self.assertEqual(renderer.render(evaluator.evaluate(tick).scene), expected)

    def test_shared_camera_two_target_recovery_in_one_document(self) -> None:
        state = produce_recovery()
        recovery_base, truth = documents()
        recovered = author_all(state)
        self.assertEqual(recovered["entities"], recovery_base["entities"])
        self.assertEqual(recovered["groups"], recovery_base["groups"])
        self.assertEqual(recovered["construction"], recovery_base["construction"])
        self.assertEqual(recovered["presentation"], recovery_base["presentation"])
        self.assertNotEqual(
            state["targets"]["a"]["identity_id"], state["targets"]["b"]["identity_id"]
        )
        self.assertNotEqual(
            state["targets"]["a"]["binding_id"], state["targets"]["b"]["binding_id"]
        )
        self.assertNotEqual(
            state["targets"]["a"]["compensated_translation_id"],
            state["targets"]["b"]["compensated_translation_id"],
        )
        self.assertNotEqual(
            state["targets"]["a"]["compensated_similarity_id"],
            state["targets"]["b"]["compensated_similarity_id"],
        )
        tracks = recovered["animation"]["content"]
        self.assertEqual(len(tracks), 12)
        by_group = {
            group: [track for track in tracks if track.get("target", {}).get("group") == group]
            for group in (GROUP_A, GROUP_B)
        }
        self.assertEqual(len(by_group[GROUP_A]), 4)
        self.assertEqual(len(by_group[GROUP_B]), 4)
        self.assertTrue(
            {track["id"] for track in by_group[GROUP_A]}.isdisjoint(
                track["id"] for track in by_group[GROUP_B]
            )
        )
        camera_tracks = [
            track for track in tracks if track.get("target", {}).get("camera") == "presentation"
        ]
        self.assertEqual(len(camera_tracks), 4)
        self.assertEqual({track["id"] for track in camera_tracks}, set(state["camera_track_ids"]))

        actual_motion, truth_motion = MotionEvaluator(recovered), MotionEvaluator(truth)
        renderer = SVGRenderer(SVGRenderOptions(width=800, height=480, view_box=(0, 0, 200, 120)))
        for tick in TICKS:
            actual = actual_motion.sample_document(tick)
            expected = truth_motion.sample_document(tick)
            for group_id in (GROUP_A, GROUP_B):
                left = next(
                    group["transform"] for group in actual["groups"] if group["id"] == group_id
                )
                right = next(
                    group["transform"] for group in expected["groups"] if group["id"] == group_id
                )
                for left_value, right_value in zip(
                    (*left["translate"], left["rotation_degrees"], left["scale"]),
                    (*right["translate"], right["rotation_degrees"], right["scale"]),
                    strict=True,
                ):
                    self.assertAlmostEqual(left_value, right_value, delta=TOLERANCE)
            left_camera, right_camera = (
                actual["presentation"]["camera"],
                expected["presentation"]["camera"],
            )
            for left_value, right_value in zip(
                (*left_camera["position"], left_camera["rotation_degrees"], left_camera["scale"]),
                (
                    *right_camera["position"],
                    right_camera["rotation_degrees"],
                    right_camera["scale"],
                ),
                strict=True,
            ):
                self.assertAlmostEqual(left_value, right_value, delta=TOLERANCE)
            rendered = state["artifacts"].import_bytes(
                renderer.render(actual_motion.evaluate(tick).scene).encode(),
                media_type="image/svg+xml",
            )
            frozen = state["artifacts"].import_bytes(
                (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_bytes(),
                media_type="image/svg+xml",
            )
            for shape_id in (ANCHOR, TARGET_A, TARGET_B):
                comparison = derive_svg_polygon_observations(
                    rendered, frozen, shape_id, tick, tick + 1
                )
                left, right = comparison["frames"]
                left_points = left["primitives"][0]["geometry"]["points"]
                right_points = right["primitives"][0]["geometry"]["points"]
                for left_point, right_point in zip(left_points, right_points, strict=True):
                    for left_value, right_value in zip(left_point, right_point, strict=True):
                        self.assertAlmostEqual(left_value, right_value, delta=TOLERANCE)

        for label, group_id in (("a", GROUP_A), ("b", GROUP_B)):
            target = state["targets"][label]
            target_tracks = by_group[group_id]
            for track in target_tracks:
                provenance = track["provenance"]
                self.assertEqual(provenance["motion_target_binding_id"], target["binding_id"])
                expected_evidence = (
                    target["compensated_translation_id"]
                    if track["target"]["property"].startswith("translate.")
                    else target["compensated_similarity_id"]
                )
                self.assertEqual(provenance["evidence_artifact_id"], expected_evidence)
        self.assertTrue(
            all(
                track["provenance"]["evidence_artifact_id"] == state["camera_id"]
                for track in camera_tracks
            )
        )

    def test_determinism_and_shared_camera_lineage(self) -> None:
        first, second = produce_recovery(), produce_recovery()
        first_document, second_document = author_all(first), author_all(second)
        self.assertEqual(first["camera_id"], second["camera_id"])
        for label in ("a", "b"):
            for key in (
                "identity_id",
                "compensated_translation_id",
                "compensated_similarity_id",
                "binding_id",
            ):
                self.assertEqual(first["targets"][label][key], second["targets"][label][key])
        self.assertEqual(first_document["animation"], second_document["animation"])
        for label in ("a", "b"):
            target = first["targets"][label]
            for artifact_id in (
                target["compensated_translation_id"],
                target["compensated_similarity_id"],
            ):
                snapshot = first["artifacts"].get(artifact_id)
                payload = json.loads(snapshot.content)
                self.assertEqual(payload["temporal_identity_id"], target["identity_id"])
                self.assertIn(first["camera_id"], payload["source_artifact_ids"])
                self.assertEqual(
                    snapshot.provenance["source_artifact_ids"], payload["source_artifact_ids"]
                )

    def test_cross_wire_inputs_reject_without_mutation(self) -> None:
        state = produce_recovery()
        store, artifacts = state["store"], state["artifacts"]
        a, b = state["targets"]["a"], state["targets"]["b"]
        before = store.get_document(store.head)
        with self.assertRaisesRegex(CameraCompensationError, "temporal identity"):
            CameraCompensatedMotionAdapter().propose(
                request(
                    store,
                    artifact_ids=(state["camera_id"], a["translation_id"], b["similarity_id"]),
                    options={
                        "anchor_entity_id": ANCHOR,
                        "target_temporal_identity_id": a["identity_id"],
                    },
                ),
                artifacts,
            )
        self.assertEqual(store.get_document(store.head), before)

        compensation = CameraCompensatedMotionAdapter().propose(
            request(
                store,
                artifact_ids=(state["camera_id"], a["translation_id"], a["similarity_id"]),
                options={
                    "anchor_entity_id": ANCHOR,
                    "target_temporal_identity_id": a["identity_id"],
                },
            ),
            artifacts,
        )
        change = compensation.transaction.changes[0]
        original = artifacts.get(compensation.preview_artifacts[0].artifact_id)
        payload = json.loads(original.content)
        payload["temporal_identity_id"] = b["identity_id"]
        forged_snapshot = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        forged_change = replace(
            change,
            evidence_references=(
                forged_snapshot.document_reference(),
                change.evidence_references[1],
            ),
        )
        forged_compensation = replace(
            compensation,
            transaction=replace(compensation.transaction, changes=(forged_change,)),
            required_artifact_ids=tuple(
                forged_snapshot.artifact_id if item == original.artifact_id else item
                for item in compensation.required_artifact_ids
            ),
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(store, forged_compensation, artifacts)
        self.assertEqual(store.get_document(store.head), before)

        author_target(state, "a", GROUP_A)
        author_target(state, "b", GROUP_B)
        before = store.get_document(store.head)
        for evidence_id, binding_id in (
            (a["compensated_translation_id"], b["binding_id"]),
            (b["compensated_translation_id"], a["binding_id"]),
        ):
            with self.assertRaisesRegex(ObservedTranslationTracksError, "identity"):
                ObservedTranslationTracksAdapter().propose(
                    request(
                        store,
                        artifact_ids=(evidence_id,),
                        options={"motion_target_binding_id": binding_id, "ticks_per_second": 12},
                    ),
                    artifacts,
                )
        self.assertEqual(store.get_document(store.head), before)

        proposal = ObservedCameraTracksAdapter().propose(
            request(
                store,
                artifact_ids=(state["camera_id"],),
                options={"camera_target": "presentation", "ticks_per_second": 12},
            ),
            artifacts,
        )
        verifier = proposal.transaction.changes[-1]
        forged_tracks = copy.deepcopy(verifier.authored_tracks)
        forged_tracks[0]["id"] = next(
            track["id"]
            for track in before["animation"]["content"]
            if track["target"].get("group") == GROUP_B
        )
        forged = replace(
            proposal,
            transaction=replace(
                proposal.transaction,
                changes=(
                    *proposal.transaction.changes[:-1],
                    replace(verifier, authored_tracks=forged_tracks),
                ),
            ),
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(store, forged, artifacts)
        self.assertEqual(store.get_document(store.head), before)

    def test_duplicate_binding_and_cross_target_track_id_collision_are_atomic(self) -> None:
        state = produce_recovery()
        store, artifacts = state["store"], state["artifacts"]
        for label, group_id in (("a", GROUP_A), ("b", GROUP_B)):
            target = state["targets"][label]
            binding = TemporalMotionTargetBindingAdapter().propose(
                request(
                    store,
                    options={
                        "temporal_identity_id": target["identity_id"],
                        "group_id": group_id,
                    },
                ),
                artifacts,
            )
            ProposalAcceptor().accept(store, binding, artifacts)
            target["binding_id"] = binding.preview.motion_target_bindings[0].binding_id

        before = store.get_document(store.head)
        duplicate = TemporalMotionTargetBindingAdapter().propose(
            request(
                store,
                options={
                    "temporal_identity_id": state["targets"]["a"]["identity_id"],
                    "group_id": GROUP_B,
                },
            ),
            artifacts,
        )
        with self.assertRaisesRegex(DocumentError, "MOTION_TARGET_CONFLICT"):
            ProposalAcceptor().accept(store, duplicate, artifacts)
        self.assertEqual(store.get_document(store.head), before)

        b = state["targets"]["b"]
        b_proposal = ObservedTranslationTracksAdapter().propose(
            request(
                store,
                artifact_ids=(b["compensated_translation_id"],),
                options={"motion_target_binding_id": b["binding_id"], "ticks_per_second": 12},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, b_proposal, artifacts)
        b_track_id = next(
            track["id"]
            for track in store.get_document(store.head)["animation"]["content"]
            if track["target"] == {"group": GROUP_B, "property": "translate.x"}
        )
        a = state["targets"]["a"]
        a_proposal = ObservedTranslationTracksAdapter().propose(
            request(
                store,
                artifact_ids=(a["compensated_translation_id"],),
                options={"motion_target_binding_id": a["binding_id"], "ticks_per_second": 12},
            ),
            artifacts,
        )
        changes = list(a_proposal.transaction.changes)
        changes[0] = replace(changes[0], track_id=b_track_id)
        forged = replace(
            a_proposal,
            transaction=replace(a_proposal.transaction, changes=tuple(changes)),
        )
        before = store.get_document(store.head)
        with self.assertRaises(DocumentError):
            ProposalAcceptor().accept(store, forged, artifacts)
        self.assertEqual(store.get_document(store.head), before)


if __name__ == "__main__":
    unittest.main()
