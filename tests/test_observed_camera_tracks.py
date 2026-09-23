from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from svm import (
    AddKeyframeChange,
    CreateCameraTransformTrackChange,
    MotionEvaluator,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalConflictError,
    RevisionStore,
    SetCameraTransformChange,
    Transaction,
)
from svm.adapters import ObservedCameraTracksAdapter, ObservedCameraTracksError
from svm.adapters.observed_camera_tracks import recover_camera_state
from svm.adapters.svg_geometry_observations import derive_svg_polygon_observations
from svm.renderers import SVGRenderer, SVGRenderOptions

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_synthetic_camera_compensation import (  # noqa: E402
    ANCHOR,
    FIXTURE,
    GROUND_TRUTH,
    TARGET,
    TICKS,
    bind_and_author,
    load,
    produce_compensated,
    request,
)

TOLERANCE = 2e-8


def camera_request(state, *, artifact_id=None, camera_target="presentation", tps=12):
    return request(
        state["store"],
        artifact_ids=(artifact_id or state["camera_id"],),
        options={"camera_target": camera_target, "ticks_per_second": tps},
    )


def author_camera(state):
    proposal = ObservedCameraTracksAdapter().propose(camera_request(state), state["artifacts"])
    ProposalAcceptor().accept(state["store"], proposal, state["artifacts"])
    return proposal, state["store"].get_document(state["store"].head)


def camera_matrix(position, rotation_degrees, scale):
    radians = math.radians(-rotation_degrees)
    a, b = scale * math.cos(radians), scale * math.sin(radians)
    c, d = -b, a
    x, y = position
    return [a, b, c, d, -a * x - c * y, -b * x - d * y]


class ObservedCameraTracksTest(unittest.TestCase):
    def test_camera_matrix_inverse_math_and_rotation_unwrap(self) -> None:
        expected = {"position.x": 7.0, "position.y": -3.0, "rotation_degrees": 28.0, "scale": 1.2}
        actual = recover_camera_state(camera_matrix([7, -3], 28, 1.2))
        for key, value in expected.items():
            self.assertAlmostEqual(actual[key], value, delta=1e-10)

        first = recover_camera_state(camera_matrix([0, 0], 170, 1))["rotation_degrees"]
        second = recover_camera_state(camera_matrix([0, 0], 190, 1), first)["rotation_degrees"]
        self.assertAlmostEqual(first, 170, delta=1e-10)
        self.assertAlmostEqual(second, 190, delta=1e-10)

    def test_camera_tracks_create_atomically_and_match_ground_truth(self) -> None:
        state = produce_compensated()
        proposal, recovered = author_camera(state)
        self.assertEqual(proposal.preview.mode, "CREATE")
        self.assertEqual(proposal.preview.camera_target, "presentation")
        self.assertEqual(len(proposal.preview.tracks), 4)
        camera_tracks = [
            track
            for track in recovered["animation"]["content"]
            if track.get("target", {}).get("camera") == "presentation"
        ]
        self.assertEqual(
            {track["target"]["property"] for track in camera_tracks},
            {"position.x", "position.y", "rotation_degrees", "scale"},
        )
        self.assertEqual(len(camera_tracks), 4)
        for track in camera_tracks:
            self.assertEqual(
                track["provenance"],
                {
                    "type": "ObservedCameraTrack",
                    "authoring_identity": "svm-verified-observed-camera-authoring@0.1",
                    "evidence_artifact_id": state["camera_id"],
                    "source_revision_id": proposal.base_revision_id,
                    "camera_target": "presentation",
                    "property": track["target"]["property"],
                },
            )
        truth_motion = MotionEvaluator(load(GROUND_TRUTH))
        recovered_motion = MotionEvaluator(recovered)
        for tick in TICKS:
            actual = recovered_motion.sample_document(tick)["presentation"]["camera"]
            expected = truth_motion.sample_document(tick)["presentation"]["camera"]
            for left, right in zip(actual["position"], expected["position"], strict=True):
                self.assertAlmostEqual(left, right, delta=TOLERANCE)
            self.assertAlmostEqual(
                actual["rotation_degrees"], expected["rotation_degrees"], delta=TOLERANCE
            )
            self.assertAlmostEqual(actual["scale"], expected["scale"], delta=TOLERANCE)

    def test_full_object_and_camera_recovery_reproduces_observed_geometry(self) -> None:
        state = produce_compensated()
        recovered = bind_and_author(state)
        _, recovered = author_camera(state)
        renderer = SVGRenderer(SVGRenderOptions(width=800, height=480, view_box=(0, 0, 200, 120)))
        evaluator = MotionEvaluator(recovered)
        for tick in TICKS:
            rendered = state["artifacts"].import_bytes(
                renderer.render(evaluator.evaluate(tick).scene).encode(),
                media_type="image/svg+xml",
            )
            frozen = state["artifacts"].import_bytes(
                (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_bytes(),
                media_type="image/svg+xml",
            )
            for shape_id in (ANCHOR, TARGET):
                comparison = derive_svg_polygon_observations(
                    rendered, frozen, shape_id, tick, tick + 1
                )
                left, right = comparison["frames"]
                left_points = left["primitives"][0]["geometry"]["points"]
                right_points = right["primitives"][0]["geometry"]["points"]
                for left_point, right_point in zip(left_points, right_points, strict=True):
                    for left_value, right_value in zip(left_point, right_point, strict=True):
                        self.assertAlmostEqual(left_value, right_value, delta=TOLERANCE)

    def test_rejections_for_evidence_target_baseline_and_existing_track(self) -> None:
        state = produce_compensated()
        unaccepted = {
            **state,
            "store": RevisionStore.create(load(FIXTURE / "recovery-base.svm.json")),
        }
        with self.assertRaisesRegex(ObservedCameraTracksError, "already be accepted"):
            ObservedCameraTracksAdapter().propose(
                camera_request(unaccepted), unaccepted["artifacts"]
            )
        with self.assertRaisesRegex(ObservedCameraTracksError, "canonical S9B"):
            ObservedCameraTracksAdapter().propose(
                camera_request(state, artifact_id=state["target"]["similarity_id"]),
                state["artifacts"],
            )
        with self.assertRaisesRegex(ObservedCameraTracksError, "target must be presentation"):
            ObservedCameraTracksAdapter().propose(
                camera_request(state, camera_target="other"), state["artifacts"]
            )
        author_camera(state)
        with self.assertRaisesRegex(ObservedCameraTracksError, "existing target"):
            ObservedCameraTracksAdapter().propose(camera_request(state), state["artifacts"])

        nonidentity = produce_compensated()
        nonidentity["store"].commit(
            nonidentity["store"].head,
            Transaction(
                "transaction:nonidentity-camera",
                (
                    SetCameraTransformChange(
                        {"position": [1, 0], "rotation_degrees": 0, "scale": 1}
                    ),
                ),
            ),
        )
        with self.assertRaisesRegex(ObservedCameraTracksError, "identity static Camera"):
            ObservedCameraTracksAdapter().propose(
                camera_request(nonidentity), nonidentity["artifacts"]
            )

    def test_forged_track_and_stale_proposals_fail_atomically(self) -> None:
        state = produce_compensated()
        proposal = ObservedCameraTracksAdapter().propose(camera_request(state), state["artifacts"])
        before = state["store"].get_document(state["store"].head)
        verifier = proposal.transaction.changes[-1]
        mutations = []
        for field, value in (
            ("id", "track:forged"),
            ("target", {"camera": "presentation", "property": "scale"}),
            ("provenance", {"type": "forged"}),
        ):
            tracks = copy.deepcopy(verifier.authored_tracks)
            tracks[0][field] = value
            mutations.append(replace(verifier, authored_tracks=tracks))
        tracks = copy.deepcopy(verifier.authored_tracks)
        tracks[0]["keyframes"][0]["tick"] = 1
        mutations.append(replace(verifier, authored_tracks=tracks))
        tracks = copy.deepcopy(verifier.authored_tracks)
        tracks[0]["keyframes"][0]["value"] = 99
        mutations.append(replace(verifier, authored_tracks=tracks))
        for forged_verifier in mutations:
            forged = replace(
                proposal,
                transaction=replace(
                    proposal.transaction,
                    changes=(*proposal.transaction.changes[:-1], forged_verifier),
                ),
            )
            with self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(state["store"], forged, state["artifacts"])
            self.assertEqual(state["store"].get_document(state["store"].head), before)

        stale_camera = produce_compensated()
        stale_proposal = ObservedCameraTracksAdapter().propose(
            camera_request(stale_camera), stale_camera["artifacts"]
        )
        stale_camera["store"].commit(
            stale_camera["store"].head,
            Transaction(
                "transaction:stale-camera",
                (
                    SetCameraTransformChange(
                        {"position": [1, 0], "rotation_degrees": 0, "scale": 1}
                    ),
                ),
            ),
        )
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(
                stale_camera["store"], stale_proposal, stale_camera["artifacts"]
            )

        stale_animation = produce_compensated()
        animation_proposal = ObservedCameraTracksAdapter().propose(
            camera_request(stale_animation), stale_animation["artifacts"]
        )
        stale_animation["store"].commit(
            stale_animation["store"].head,
            Transaction(
                "transaction:stale-camera-animation",
                (
                    CreateCameraTransformTrackChange(
                        "track:manual-camera-position-x", "position.x", 12
                    ),
                    AddKeyframeChange(
                        "track:manual-camera-position-x",
                        "keyframe:manual-camera-position-x",
                        0,
                        0,
                    ),
                ),
            ),
        )
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(
                stale_animation["store"], animation_proposal, stale_animation["artifacts"]
            )

    def test_forged_camera_evidence_is_rejected_atomically(self) -> None:
        state = produce_compensated()
        proposal = ObservedCameraTracksAdapter().propose(camera_request(state), state["artifacts"])
        original = state["artifacts"].get(state["camera_id"])
        verifier = proposal.transaction.changes[-1]
        before = state["store"].get_document(state["store"].head)

        def forge_view(payload):
            payload["intervals"][0]["target_view_transform"][4] += 1

        def forge_tick(payload):
            payload["intervals"][0]["target_tick"] = 11

        cases = (
            forge_view,
            forge_tick,
            lambda payload: payload.update(anchor_entity_id="entity:forged-anchor"),
            lambda payload: payload.update(policy_identity="forged-policy"),
            lambda payload: payload.update(source_similarity_artifact_id="artifact:forged"),
        )
        for mutate in cases:
            payload = json.loads(original.content)
            mutate(payload)
            forged_snapshot = state["artifacts"].import_bytes(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
                media_type=original.media_type,
                kind=original.kind,
                provenance=original.provenance,
            )
            forged_verifier = replace(
                verifier, evidence_reference=forged_snapshot.document_reference()
            )
            forged = replace(
                proposal,
                transaction=replace(
                    proposal.transaction,
                    changes=(*proposal.transaction.changes[:-1], forged_verifier),
                ),
                required_artifact_ids=(forged_snapshot.artifact_id,),
            )
            with self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(state["store"], forged, state["artifacts"])
            self.assertEqual(state["store"].get_document(state["store"].head), before)

    def test_deterministic_proposal_and_track_ids(self) -> None:
        first, second = produce_compensated(), produce_compensated()
        first_proposal = ObservedCameraTracksAdapter().propose(
            camera_request(first), first["artifacts"]
        )
        second_proposal = ObservedCameraTracksAdapter().propose(
            camera_request(second), second["artifacts"]
        )
        self.assertEqual(first_proposal, second_proposal)


if __name__ == "__main__":
    unittest.main()
