from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from test_shared_camera_multi_object_recovery import observe_lineage, request
from test_svg_geometry_observations import svg

from svm import (
    ArtifactStore,
    MotionEvaluator,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalConflictError,
    RevisionStore,
)
from svm.adapters import (
    CameraCompensatedMotionAdapter,
    GeometryTranslationTracksAdapter,
    ObservedCameraSimilarityAdapter,
    ObservedCameraTracksAdapter,
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    SVGGeometryObservationAdapter,
    SVGGeometryObservationError,
    SVGGeometryOccurrenceAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.svg_geometry_observations import (
    OCCURRENCE_POLICY_IDENTITY,
    POLICY_IDENTITY,
    derive_svg_polygon_observations,
)
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
GROUP = "group:" + "1" * 64
TARGET = "entity:recovery-target"
ANCHOR = "entity:camera-anchor"
TICKS = (0, 12, 24, 36)


def sequence_documents(*, camera=False, static=False):
    base = json.loads(
        (ROOT / "examples/029-synthetic-camera-compensation/recovery-base.svm.json").read_text()
    )
    base["document_id"] = "document:repeated-frame-recovery-base"
    base["groups"][0]["transform"]["origin"] = [37, 43]
    truth = copy.deepcopy(base)
    truth["document_id"] = "document:repeated-frame-ground-truth"
    values = {
        "translate.x": (0, 0, 6, 6),
        "translate.y": (0, 0, -2, -2),
        "rotation_degrees": (10, 10, 25, 25),
        "scale": (1, 1, 1.2, 1.2),
    }
    targets = [("group", GROUP, p, vs) for p, vs in values.items()]
    if camera:
        targets += [
            ("camera", "presentation", p, vs)
            for p, vs in {
                "position.x": (0, 0, 2, 2),
                "position.y": (0, 0, -1, -1),
                "rotation_degrees": (0, 0, 3, 3),
                "scale": (1, 1, 1.03, 1.03),
            }.items()
        ]
    truth["animation"] = {
        "semantics_version": "svm-motion@0.6",
        "timebase": {"ticks_per_second": 12},
        "construction_scheduling_hints": [],
        "content": [
            {
                "id": f"track:hold-{kind}-{prop}",
                "target": {kind: target, "property": prop},
                "value_type": "number",
                "interpolation": "linear",
                "keyframes": [
                    {
                        "id": f"keyframe:hold-{kind}-{prop}-{tick}",
                        "tick": tick,
                        "value": vs[0] if static else value,
                    }
                    for tick, value in zip(TICKS, vs, strict=True)
                ],
            }
            for kind, target, prop, vs in targets
        ],
    }
    return base, truth


def recover_sequence(*, camera=False, static=False):
    base, truth = sequence_documents(camera=camera, static=static)
    store, artifacts = RevisionStore.create(base), ArtifactStore()
    evaluator = MotionEvaluator(truth)
    renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
    frames = [
        artifacts.import_bytes(
            renderer.render(evaluator.evaluate(t).scene).encode(), media_type="image/svg+xml"
        )
        for t in TICKS
    ]
    target = observe_lineage(
        store, artifacts, frames, TARGET, observation_adapter=SVGGeometryOccurrenceAdapter()
    )
    camera_id = None
    evidence_id = target["similarity_id"]
    if camera:
        anchor = observe_lineage(
            store, artifacts, frames, ANCHOR, observation_adapter=SVGGeometryOccurrenceAdapter()
        )
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
        evidence_id = proposal.preview_artifacts[1].artifact_id
    binding = TemporalMotionTargetBindingAdapter().propose(
        request(store, options={"temporal_identity_id": target["identity_id"], "group_id": GROUP}),
        artifacts,
    )
    ProposalAcceptor().accept(store, binding, artifacts)
    target["binding_id"] = binding.preview.motion_target_bindings[0].binding_id
    pending = GeometryTranslationTracksAdapter().propose(
        request(
            store,
            artifact_ids=(evidence_id,),
            options={"motion_target_binding_id": target["binding_id"], "ticks_per_second": 12},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, pending, artifacts)
    for adapter in (ObservedScaleTracksAdapter(), ObservedRotationTracksAdapter()):
        proposal = adapter.propose(
            request(
                store,
                artifact_ids=(evidence_id,),
                options={"motion_target_binding_id": target["binding_id"], "ticks_per_second": 12},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
    if camera_id:
        proposal = ObservedCameraTracksAdapter().propose(
            request(
                store,
                artifact_ids=(camera_id,),
                options={"camera_target": "presentation", "ticks_per_second": 12},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
    return store, artifacts, target, truth, frames, camera_id, pending


def observation_request(store, source, target, source_tick=0, target_tick=12, shape_id="arrow"):
    return request(
        store,
        artifact_ids=tuple(dict.fromkeys((source.artifact_id, target.artifact_id))),
        options={
            "source_svg_artifact_id": source.artifact_id,
            "target_svg_artifact_id": target.artifact_id,
            "source_tick": source_tick,
            "target_tick": target_tick,
            "shape_id": shape_id,
        },
    )


class RepeatedFrameOccurrenceTest(unittest.TestCase):
    def test_example_matches_executable_ground_truth(self):
        path = ROOT / "examples/032-repeated-frame-occurrences/ground-truth.svm.json"
        self.assertEqual(json.loads(path.read_text()), sequence_documents(camera=True)[1])

    def setUp(self):
        self.store = RevisionStore.create(
            json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        )
        self.artifacts = ArtifactStore()
        self.source = self.artifacts.import_bytes(
            svg("M 10 10 L 50 10 L 35 25 L 20 40 Z"), media_type="image/svg+xml"
        )

    def test_same_blob_different_occurrences(self):
        store = RevisionStore.create(
            json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        )
        artifacts = ArtifactStore()
        content = svg("M 10 10 L 50 10 L 35 25 L 20 40 Z")
        source = artifacts.import_bytes(content, media_type="image/svg+xml")
        target = artifacts.import_bytes(content, media_type="image/svg+xml")
        self.assertEqual(source.artifact_id, target.artifact_id)
        proposal = SVGGeometryOccurrenceAdapter().propose(
            observation_request(store, source, target), artifacts
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        payload = json.loads(artifacts.get(proposal.preview_artifacts[0].artifact_id).content)
        left, right = (frame["primitives"][0]["observation_id"] for frame in payload["frames"])
        self.assertNotEqual(left, right)
        self.assertEqual(len(proposal.required_artifact_ids), 2)

    def test_occurrence_hash_and_provenance_are_tick_scoped(self):
        adapter = SVGGeometryOccurrenceAdapter()
        proposals = [
            adapter.propose(
                observation_request(self.store, self.source, self.source, a, b), self.artifacts
            )
            for a, b in ((0, 12), (12, 24), (0, 12))
        ]
        snapshots = [self.artifacts.get(p.preview_artifacts[0].artifact_id) for p in proposals]
        payloads = [json.loads(s.content) for s in snapshots]
        self.assertEqual(snapshots[0], snapshots[2])
        self.assertEqual(payloads[0]["frames"][1], payloads[1]["frames"][0])
        for payload, snapshot in zip(payloads, snapshots, strict=True):
            for frame in payload["frames"]:
                expected = (
                    "observation:svg:"
                    + hashlib.sha256(
                        canonical_bytes(
                            {
                                "source_svg_artifact_id": self.source.artifact_id,
                                "tick": frame["tick"],
                                "shape_id": "arrow",
                                "policy_identity": OCCURRENCE_POLICY_IDENTITY,
                            }
                        )
                    ).hexdigest()
                )
                self.assertEqual(frame["primitives"][0]["observation_id"], expected)
            self.assertEqual(
                snapshot.provenance["source_occurrences"],
                [
                    {"source_svg_artifact_id": self.source.artifact_id, "tick": f["tick"]}
                    for f in payload["frames"]
                ],
            )

    def check_sequence(self, *, camera=False, static=False):
        state = recover_sequence(camera=camera, static=static)
        store, artifacts, target, truth, frames, camera_id, _ = state
        self.assertEqual(frames[0].content, frames[1].content)
        self.assertEqual(frames[0].artifact_id, frames[1].artifact_id)
        self.assertEqual(frames[2].artifact_id, frames[3].artifact_id)
        self.assertEqual(len({f.artifact_id for f in frames}), 1 if static else 2)
        document = store.get_document(store.head)
        identity = next(
            i for i in document["temporal_identities"] if i["id"] == target["identity_id"]
        )
        self.assertEqual([b["tick"] for b in identity["bindings"]], list(TICKS))
        self.assertEqual(len({b["observation_id"] for b in identity["bindings"]}), 4)
        self.assertEqual(len(identity["provenance"]), 3)
        for index in (0, 2):
            r0 = json.loads(artifacts.get(target["correspondence_ids"][index]).content)[
                "candidates"
            ][0]
            self.assertEqual(r0["status"], "SUPPORTED")
            self.assertEqual(r0["displacement"], [0, 0])
            s0 = json.loads(artifacts.get(target["translation_id"]).content)["intervals"][index]
            self.assertEqual(s0["translation"], {"dx": 0, "dy": 0})
            s4 = json.loads(artifacts.get(target["similarity_id"]).content)["intervals"][index]
            self.assertEqual(s4["status"], "SUPPORTED")
            self.assertEqual(s4["translation"], {"dx": 0, "dy": 0})
            self.assertEqual(s4["rotation_degrees"]["value"], 0)
            self.assertEqual(s4["scale"]["value"], 1)
        actual, expected = MotionEvaluator(document), MotionEvaluator(truth)
        renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
        for tick, frozen in zip(TICKS, frames, strict=True):
            left = actual.sample_document(tick)["groups"][0]["transform"]
            right = expected.sample_document(tick)["groups"][0]["transform"]
            for x, y in zip(
                (*left["translate"], left["rotation_degrees"], left["scale"]),
                (*right["translate"], right["rotation_degrees"], right["scale"]),
                strict=True,
            ):
                self.assertAlmostEqual(x, y, delta=3e-8)
            rendered = artifacts.import_bytes(
                renderer.render(actual.evaluate(tick).scene).encode(), media_type="image/svg+xml"
            )
            pair = derive_svg_polygon_observations(
                rendered, frozen, TARGET, tick, tick + 1, policy_identity=OCCURRENCE_POLICY_IDENTITY
            )["frames"]
            for p, q in zip(*(f["primitives"][0]["geometry"]["points"] for f in pair), strict=True):
                for x, y in zip(p, q, strict=True):
                    self.assertAlmostEqual(x, y, delta=3e-8)
        for track in document["animation"]["content"]:
            values = [k["value"] for k in track["keyframes"]]
            self.assertAlmostEqual(values[0], values[1], delta=3e-8)
            self.assertAlmostEqual(values[2], values[3], delta=3e-8)
            if static:
                self.assertTrue(all(abs(v - values[0]) < 3e-8 for v in values))
        if camera_id:
            intervals = json.loads(artifacts.get(camera_id).content)["intervals"]
            self.assertEqual(intervals[0]["relative_view_transform"], [1, 0, 0, 1, 0, 0])
            self.assertEqual(intervals[0]["target_view_transform"], [1, 0, 0, 1, 0, 0])
        return state

    def test_hold_move_hold_recovers_translation_rotation_and_scale(self):
        self.check_sequence()

    def test_whole_scene_static_creates_constant_tracks(self):
        self.check_sequence(static=True)

    def test_shared_camera_static_interval_and_compensated_recovery(self):
        self.check_sequence(camera=True)

    def test_all_static_camera_and_object(self):
        self.check_sequence(camera=True, static=True)

    def test_full_pipeline_determinism(self):
        first, second = recover_sequence(camera=True), recover_sequence(camera=True)
        self.assertEqual(first[2], second[2])
        self.assertEqual(first[5], second[5])
        self.assertEqual(first[0].head, second[0].head)
        self.assertEqual(
            first[0].get_document(first[0].head), second[0].get_document(second[0].head)
        )

    def test_invalid_ticks_and_exact_artifact_capability(self):
        adapter = SVGGeometryOccurrenceAdapter()
        for source_tick, target_tick in ((0, 0), (12, 0), (-1, 12), (False, 12)):
            with (
                self.subTest(ticks=(source_tick, target_tick)),
                self.assertRaises(SVGGeometryObservationError),
            ):
                adapter.propose(
                    observation_request(
                        self.store, self.source, self.source, source_tick, target_tick
                    ),
                    self.artifacts,
                )
        req = observation_request(self.store, self.source, self.source)
        other = self.artifacts.import_bytes(
            svg("M 11 10 L 51 10 L 36 25 L 21 40 Z"), media_type="image/svg+xml"
        )
        for ids in (
            (),
            (self.source.artifact_id, self.source.artifact_id),
            (self.source.artifact_id, other.artifact_id),
        ):
            with self.subTest(ids=ids), self.assertRaises(SVGGeometryObservationError):
                adapter.propose(replace(req, artifact_ids=ids), self.artifacts)

    def test_legacy_identity_and_policy_verification_remain_unchanged(self):
        target = self.artifacts.import_bytes(
            svg("M 11 10 L 51 10 L 36 25 L 21 40 Z"), media_type="image/svg+xml"
        )
        req = observation_request(self.store, self.source, target)
        old = SVGGeometryObservationAdapter().propose(req, self.artifacts)
        new = SVGGeometryOccurrenceAdapter().propose(req, self.artifacts)
        payload = json.loads(self.artifacts.get(old.preview_artifacts[0].artifact_id).content)
        expected = (
            "observation:svg:"
            + hashlib.sha256(
                canonical_bytes(
                    {
                        "source_svg_artifact_id": self.source.artifact_id,
                        "shape_id": "arrow",
                        "policy_identity": POLICY_IDENTITY,
                    }
                )
            ).hexdigest()
        )
        self.assertEqual(payload["frames"][0]["primitives"][0]["observation_id"], expected)
        self.assertNotEqual(
            old.preview_artifacts[0].artifact_id, new.preview_artifacts[0].artifact_id
        )
        wrong = replace(new.transaction.changes[0], producer_policy_identity=POLICY_IDENTITY)
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(
                self.store,
                replace(new, transaction=replace(new.transaction, changes=(wrong,))),
                self.artifacts,
            )
        ProposalAcceptor().accept(self.store, old, self.artifacts)
        with self.assertRaises(SVGGeometryObservationError):
            SVGGeometryObservationAdapter().propose(
                observation_request(self.store, self.source, self.source), self.artifacts
            )

    def test_forged_occurrence_tick_source_shape_and_payload_are_atomic(self):
        proposal = SVGGeometryOccurrenceAdapter().propose(
            observation_request(self.store, self.source, self.source), self.artifacts
        )
        change = proposal.transaction.changes[0]
        other = self.artifacts.import_bytes(
            svg("M 11 10 L 51 10 L 36 25 L 21 40 Z"), media_type="image/svg+xml"
        )
        wrongs = [
            replace(change, target_tick=24),
            replace(change, shape_id="other"),
            replace(change, target_svg_reference=other.document_reference()),
        ]
        snapshot = self.artifacts.get(change.observation_reference["id"])
        payload = json.loads(snapshot.content)
        payload["frames"][1]["tick"] = 24
        forged = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=snapshot.media_type,
            kind=snapshot.kind,
            provenance=snapshot.provenance,
        )
        wrongs.append(
            replace(change, observation_reference=forged.document_reference(), target_tick=24)
        )
        before, head = self.store.get_document(self.store.head), self.store.head
        for wrong in wrongs:
            with self.subTest(wrong=wrong), self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(
                    self.store,
                    replace(
                        proposal,
                        required_artifact_ids=tuple(
                            dict.fromkeys(r["id"] for r in wrong.references)
                        ),
                        transaction=replace(proposal.transaction, changes=(wrong,)),
                    ),
                    self.artifacts,
                )
            self.assertEqual(self.store.head, head)
            self.assertEqual(self.store.get_document(head), before)

    def test_downstream_stale_and_forged_authoring_still_reject(self):
        store, artifacts, _, _, _, _, pending = recover_sequence()
        head, before = store.head, store.get_document(store.head)
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(store, pending, artifacts)
        # Reuse the source revision to exercise verification beyond head checks.
        store.checkout(pending.base_revision_id)
        change = pending.transaction.changes[-1]
        tracks = copy.deepcopy(change.authored_tracks)
        tracks[0]["keyframes"][1]["value"] = 999
        forged = replace(
            pending,
            transaction=replace(
                pending.transaction,
                changes=(
                    *pending.transaction.changes[:-1],
                    replace(change, authored_tracks=tracks),
                ),
            ),
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(store, forged, artifacts)
        self.assertEqual(store.head, pending.base_revision_id)
        self.assertEqual(store.get_document(head), before)


if __name__ == "__main__":
    unittest.main()
