import copy
import json
import math
import unittest
from dataclasses import replace
from pathlib import Path

from svm import (
    AdapterRequest,
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
    ObservedSimilarityMotionAdapter,
    SVGGeometryObservationAdapter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.observed_rotation_tracks import (
    ObservedRotationTracksError,
    _absolute_samples,
)

ROOT = Path(__file__).resolve().parents[1]
GROUP_ID = "group:" + "1" * 64


def _transform(points, angle_degrees):
    radians = math.radians(angle_degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    cx = sum(point[0] for point in points) / len(points)
    cy = sum(point[1] for point in points) / len(points)
    return [
        (
            cx + 5 + cosine * (x - cx) - sine * (y - cy),
            cy + 4 + sine * (x - cx) + cosine * (y - cy),
        )
        for x, y in points
    ]


def _svg(points):
    data = "M " + " ".join(f"{x:.12f} {y:.12f}" for x, y in points) + " Z"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">'
        f'<path id="arrow" fill="#CC3344" d="{data}"/></svg>'
    ).encode()


class ObservedRotationTrackMathTest(unittest.TestCase):
    def test_unwrapped_accumulation_crosses_wrap_boundary(self):
        samples = _absolute_samples(
            [
                {
                    "source_tick": 0,
                    "target_tick": 24,
                    "rotation_degrees": {"status": "SUPPORTED", "value": 20},
                },
                {
                    "source_tick": 24,
                    "target_tick": 48,
                    "rotation_degrees": {"status": "SUPPORTED", "value": 30},
                },
                {
                    "source_tick": 48,
                    "target_tick": 72,
                    "rotation_degrees": {"status": "SUPPORTED", "value": -15},
                },
            ],
            170,
        )
        self.assertEqual(
            [(tick, value) for tick, value, _ in samples],
            [(0, 170), (24, 190), (48, 220), (72, 205)],
        )

    def test_negative_delta_is_signed_and_discontinuous_chain_rejects(self):
        samples = _absolute_samples(
            [
                {
                    "source_tick": 0,
                    "target_tick": 24,
                    "rotation_degrees": {"status": "SUPPORTED", "value": -25},
                }
            ],
            -20,
        )
        self.assertEqual([(tick, value) for tick, value, _ in samples], [(0, -20), (24, -45)])
        with self.assertRaises(ObservedRotationTracksError):
            _absolute_samples(
                [
                    {
                        "source_tick": 0,
                        "target_tick": 24,
                        "rotation_degrees": {"status": "SUPPORTED", "value": 20},
                    },
                    {
                        "source_tick": 25,
                        "target_tick": 48,
                        "rotation_degrees": {"status": "SUPPORTED", "value": 10},
                    },
                ],
                0,
            )

    def test_rotation_component_is_independent_of_scale(self):
        samples = _absolute_samples(
            [
                {
                    "source_tick": 0,
                    "target_tick": 24,
                    "rotation_degrees": {"status": "SUPPORTED", "value": 30},
                    "scale": {"status": "UNCERTAIN", "value": None},
                }
            ],
            10,
        )
        self.assertEqual(samples[-1][1], 40)
        with self.assertRaises(ObservedRotationTracksError):
            _absolute_samples(
                [
                    {
                        "source_tick": 0,
                        "target_tick": 24,
                        "rotation_degrees": {"status": "UNCERTAIN", "value": None},
                        "scale": {"status": "SUPPORTED", "value": 1.2},
                    }
                ],
                10,
            )


class ObservedRotationTrackGoldenS6B1Test(unittest.TestCase):
    def setUp(self):
        self._initialize(30, 10)

    def _initialize(self, angle, baseline):
        document = json.loads(
            (ROOT / "examples" / "022-group-transform.svm.json").read_text(encoding="utf-8")
        )
        document["groups"][0]["transform"]["rotation_degrees"] = baseline
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()
        points = [(40.0, 40.0), (80.0, 40.0), (65.0, 55.0), (50.0, 75.0)]
        source = self.artifacts.import_bytes(_svg(points), media_type="image/svg+xml")
        target = self.artifacts.import_bytes(
            _svg(_transform(points, angle)), media_type="image/svg+xml"
        )
        geometry = SVGGeometryObservationAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(source.artifact_id, target.artifact_id),
                options={
                    "source_svg_artifact_id": source.artifact_id,
                    "target_svg_artifact_id": target.artifact_id,
                    "source_tick": 0,
                    "target_tick": 24,
                    "shape_id": "arrow",
                },
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, geometry, self.artifacts)
        self.geometry_id = geometry.preview_artifacts[0].artifact_id
        r0 = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.geometry_id,),
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, r0, self.artifacts)
        self.r0_id = r0.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(self.r0_id).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
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
                artifact_ids=(self.geometry_id, self.r0_id),
                options={
                    "temporal_identity_id": self.identity_id,
                    "inference_ids": [candidate["inference_id"]],
                },
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, s4, self.artifacts)
        self.evidence_id = s4.preview_artifacts[0].artifact_id
        self.binding_id = None

    def _bind(self):
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

    def _proposal(self):
        return ObservedRotationTracksAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.evidence_id,),
                options={
                    "motion_target_binding_id": self.binding_id,
                    "ticks_per_second": 24,
                },
            ),
            self.artifacts,
        )

    @staticmethod
    def _rotation(document, tick):
        sampled = MotionEvaluator(document).sample_document(tick)
        return sampled["groups"][0]["transform"]["rotation_degrees"]

    def test_real_svg_to_accepted_rotation_track_and_preview_purity(self):
        self._bind()
        before = self.store.get_document(self.store.head)
        proposal = self._proposal()
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(proposal.preview.baseline_rotation_degrees, 10)
        self.assertEqual(
            [(item.tick, item.value, item.source_delta) for item in proposal.preview.keyframes],
            [(0, 10, None), (24, 40, 30)],
        )
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        accepted = self.store.get_document(revision.revision_id)
        self.assertEqual(self._rotation(accepted, 0), 10)
        self.assertEqual(self._rotation(accepted, 12), 25)
        self.assertEqual(self._rotation(accepted, 24), 40)
        for field in ("groups", "entities", "construction", "presentation"):
            self.assertEqual(accepted[field], before[field])

    def test_no_binding_and_existing_track_reject(self):
        with self.assertRaises(ObservedRotationTracksError):
            self._proposal()
        self._bind()
        first = self._proposal()
        ProposalAcceptor().accept(self.store, first, self.artifacts)
        with self.assertRaisesRegex(
            ObservedRotationTracksError,
            "Existing Group rotation Track requires explicit re-authoring",
        ):
            self._proposal()

    def test_unwrapped_boundary_samples_midpoint_at_180(self):
        self._initialize(20, 170)
        self._bind()
        proposal = self._proposal()
        self.assertEqual(proposal.preview.keyframes[0].value, 170)
        self.assertAlmostEqual(proposal.preview.keyframes[1].value, 190, places=7)
        accepted = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        document = self.store.get_document(accepted.revision_id)
        self.assertAlmostEqual(self._rotation(document, 12), 180, places=7)

    def test_stale_baseline_rejects_but_binding_persists_for_fresh_proposal(self):
        self._bind()
        stale = self._proposal()
        document = self.store.get_document(self.store.head)
        transform = copy.deepcopy(document["groups"][0]["transform"])
        transform["rotation_degrees"] = 50
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:update-rotation-baseline",
                (SetGroupTransformChange(GROUP_ID, transform),),
            ),
        )
        with self.assertRaises(ProposalConflictError):
            ProposalAcceptor().accept(self.store, stale, self.artifacts)
        fresh = self._proposal()
        self.assertEqual([item.value for item in fresh.preview.keyframes], [50, 80])

    def test_wrong_binding_identity_and_forged_authoring_fail_atomically(self):
        self._bind()
        proposal = self._proposal()
        changes = list(proposal.transaction.changes)
        verifier = changes[-1]
        wrong_binding = copy.deepcopy(verifier.binding)
        wrong_binding["temporal_identity_id"] = "temporal-identity:" + "f" * 64
        forged_cases = []
        forged_cases.append(replace(verifier, binding=wrong_binding))
        wrong_group = copy.deepcopy(verifier.authored_track)
        wrong_group["target"]["group"] = "group:" + "f" * 64
        forged_cases.append(replace(verifier, authored_track=wrong_group))
        wrong_property = copy.deepcopy(verifier.authored_track)
        wrong_property["target"]["property"] = "scale"
        forged_cases.append(replace(verifier, authored_track=wrong_property))
        wrong_track_id = copy.deepcopy(verifier.authored_track)
        wrong_track_id["id"] += "x"
        forged_cases.append(replace(verifier, authored_track=wrong_track_id))
        for field, value in (("id", "keyframe:forged"), ("tick", 23), ("value", 500)):
            track = copy.deepcopy(verifier.authored_track)
            track["keyframes"][1][field] = value
            forged_cases.append(replace(verifier, authored_track=track))
        provenance = copy.deepcopy(verifier.authored_track)
        provenance["provenance"]["authoring_identity"] = "forged"
        forged_cases.append(replace(verifier, authored_track=provenance))
        forged_cases.append(replace(verifier, ticks_per_second=25))
        group = copy.deepcopy(verifier.group)
        group["transform"]["rotation_degrees"] = 20
        forged_cases.append(replace(verifier, group=group))
        evidence = copy.deepcopy(verifier.evidence_reference)
        evidence["id"] = "artifact:" + "f" * 64
        forged_cases.append(replace(verifier, evidence_reference=evidence))
        for forged_verifier in forged_cases:
            forged = replace(
                proposal,
                transaction=replace(
                    proposal.transaction,
                    changes=(*changes[:-1], forged_verifier),
                ),
            )
            before_head = self.store.head
            before = self.store.get_document(before_head)
            with self.assertRaises((ProposalArtifactError, ValueError)):
                ProposalAcceptor().accept(self.store, forged, self.artifacts)
            self.assertEqual(self.store.head, before_head)
            self.assertEqual(self.store.get_document(before_head), before)
