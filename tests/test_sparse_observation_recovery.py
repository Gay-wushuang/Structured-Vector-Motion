from __future__ import annotations

import copy
import json
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from test_camera_consensus import ANCHORS, propose_consensus
from test_camera_consensus import documents as dense_documents
from test_repeated_frame_occurrences import GROUP, TARGET, TICKS
from test_shared_camera_multi_object_recovery import observe_lineage, request

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
    SparseCameraCompensatedMotionAdapter,
    SparseTemporalIdentityPromotionAdapter,
    SVGGeometryOccurrenceAdapter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.camera_compensation import _compose, _interval_matrix, _inverse
from svm.adapters.sparse_camera_compensation import sparse_payloads
from svm.adapters.svg_geometry_observations import (
    OCCURRENCE_POLICY_IDENTITY,
    derive_svg_polygon_observations,
)
from svm.adapters.temporal_correspondence import OBSERVATION_MEDIA_TYPE
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.revisions import AppendReferencesChange, SetGroupTransformChange, Transaction
from svm.scene import _group_transform_matrix

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/034-sparse-observation-recovery"
VISIBLE = (0, 24, 36)


def documents():
    base, truth = dense_documents()
    for doc, suffix in ((base, "base"), (truth, "truth")):
        doc["document_id"] = "document:sparse-recovery-" + suffix
    for track in truth["animation"]["content"]:
        if "camera" in track["target"]:
            track["keyframes"][1]["value"] = {
                "position.x": 1,
                "position.y": -0.5,
                "rotation_degrees": 1,
                "scale": 1.01,
            }[track["target"]["property"]]
    return base, truth


def rendered_observations(truth):
    renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
    result = []
    for tick in TICKS:
        snapshot = copy.deepcopy(truth)
        if tick == 12:
            snapshot["presentation"]["render_stack"].remove(TARGET)
        result.append(renderer.render(MotionEvaluator(snapshot).evaluate(tick).scene).encode())
    return result


class ScheduledPromotion:
    def __init__(self):
        self.policy_id = None
        self.pending = None

    def propose(self, req, artifacts):
        if self.policy_id is None:
            proposal = SparseTemporalIdentityPromotionAdapter().propose(
                replace(
                    req,
                    options={
                        **req.options,
                        "expected_tick_schedule": list(TICKS),
                        "missing_tick": 12,
                    },
                ),
                artifacts,
            )
            self.policy_id = proposal.preview_artifacts[0].artifact_id
            self.pending = proposal
            return proposal
        return TemporalIdentityPromotionAdapter().propose(req, artifacts)


def prepare(*, camera_ticks=TICKS):
    base = json.loads((FIXTURE / "recovery-base.svm.json").read_text())
    store, artifacts = RevisionStore.create(base), ArtifactStore()
    frames = [
        artifacts.import_bytes(
            (FIXTURE / "observations" / f"tick_{t:03d}.svg").read_bytes(),
            media_type="image/svg+xml",
        )
        for t in TICKS
    ]
    camera_ids = []
    for anchor in ANCHORS:
        lineage = observe_lineage(
            store,
            artifacts,
            frames,
            anchor,
            observation_adapter=SVGGeometryOccurrenceAdapter(),
            ticks=camera_ticks,
        )
        camera = ObservedCameraSimilarityAdapter().propose(
            request(
                store,
                artifact_ids=(lineage["similarity_id"],),
                options={"anchor_entity_id": anchor},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, camera, artifacts)
        camera_ids.append(camera.preview_artifacts[0].artifact_id)
    consensus = propose_consensus(store, artifacts, camera_ids)
    ProposalAcceptor().accept(store, consensus, artifacts)
    promotion = ScheduledPromotion()
    target = observe_lineage(
        store,
        artifacts,
        [frames[i] for i in (0, 2, 3)],
        TARGET,
        observation_adapter=SVGGeometryOccurrenceAdapter(),
        ticks=VISIBLE,
        identity_adapter=promotion,
    )
    camera_id = consensus.preview_artifacts[0].artifact_id
    inputs = (camera_id, target["translation_id"], target["similarity_id"], promotion.policy_id)
    options = {
        "anchor_entity_ids": list(ANCHORS),
        "target_temporal_identity_id": target["identity_id"],
    }
    compensation = SparseCameraCompensatedMotionAdapter().propose(
        request(store, artifact_ids=inputs, options=options), artifacts
    )
    return store, artifacts, frames, target, promotion, compensation, inputs, options


def author(state):
    store, artifacts, _, target, _, compensation, inputs, _ = state
    ProposalAcceptor().accept(store, compensation, artifacts)
    binding = TemporalMotionTargetBindingAdapter().propose(
        request(store, options={"temporal_identity_id": target["identity_id"], "group_id": GROUP}),
        artifacts,
    )
    ProposalAcceptor().accept(store, binding, artifacts)
    binding_id = binding.preview.motion_target_bindings[0].binding_id
    proposals = []
    for adapter in (
        GeometryTranslationTracksAdapter(),
        ObservedRotationTracksAdapter(),
        ObservedScaleTracksAdapter(),
    ):
        proposal = adapter.propose(
            request(
                store,
                artifact_ids=(compensation.preview_artifacts[1].artifact_id,),
                options={"motion_target_binding_id": binding_id, "ticks_per_second": 12},
            ),
            artifacts,
        )
        proposals.append(proposal)
        ProposalAcceptor().accept(store, proposal, artifacts)
    camera = ObservedCameraTracksAdapter().propose(
        request(
            store,
            artifact_ids=(inputs[0],),
            options={"camera_target": "presentation", "ticks_per_second": 12},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, camera, artifacts)
    return proposals


class SparseObservationRecoveryTest(unittest.TestCase):
    def assert_atomic_rejection(self, store, artifacts, proposal, error=ValueError):
        before = (store.head, store.get_document(store.head), len(store.revisions))
        with self.assertRaises(error):
            ProposalAcceptor().accept(store, proposal, artifacts)
        self.assertEqual((store.head, store.get_document(store.head), len(store.revisions)), before)

    def primitive_gap(self, *, target_tick=24, ambiguous=False, absent=False):
        base, _ = documents()
        store, artifacts = RevisionStore.create(base), ArtifactStore()
        primitive = {
            "observation_id": "observation:source",
            "primitive_type": "rectangle",
            "bounds": [40, 40, 50, 50],
            "fill": "#00FF00",
        }
        target = [{**primitive, "observation_id": "observation:target"}]
        if ambiguous:
            target.append({**primitive, "observation_id": "observation:other"})
        observation = artifacts.import_bytes(
            canonical_bytes(
                {
                    "schema_version": "svm-primitive-observations-0.1",
                    "canvas": [100, 100],
                    "frames": [
                        {"tick": 0, "primitives": [primitive]},
                        {"tick": target_tick, "primitives": [] if absent else target},
                    ],
                }
            ),
            media_type=OBSERVATION_MEDIA_TYPE,
        )
        store.commit(
            store.head,
            Transaction(
                "transaction:record-real-endpoints",
                (AppendReferencesChange((observation.document_reference(),)),),
            ),
        )
        proposal = TemporalCorrespondenceAdapter().propose(
            request(store, artifact_ids=(observation.artifact_id,)), artifacts
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        evidence = proposal.preview_artifacts[0].artifact_id
        candidates = json.loads(artifacts.get(evidence).content)["candidates"]
        inference = candidates[0]["inference_id"] if candidates else "inference:absent"
        return store, artifacts, evidence, candidates, inference

    def test_uncertain_ambiguous_reappearance_abstains_without_identity_or_tracks(self):
        store, artifacts, evidence, candidates, inference = self.primitive_gap(ambiguous=True)
        self.assertTrue(candidates)
        self.assertEqual({c["status"] for c in candidates}, {"UNCERTAIN"})
        head, before = store.head, store.get_document(store.head)
        with self.assertRaisesRegex(ValueError, "SUPPORTED"):
            SparseTemporalIdentityPromotionAdapter().propose(
                request(
                    store,
                    artifact_ids=(evidence,),
                    options={
                        "inference_ids": [inference],
                        "expected_tick_schedule": list(TICKS),
                        "missing_tick": 12,
                    },
                ),
                artifacts,
            )
        self.assertEqual(store.head, head)
        self.assertEqual(store.get_document(head), before)
        self.assertFalse(before.get("temporal_identities"))
        self.assertFalse(before["animation"]["content"])

    def test_long_gap_and_missing_endpoint_abstain(self):
        for target_tick, absent in ((36, False), (10000, False), (24, True)):
            store, artifacts, evidence, candidates, inference = self.primitive_gap(
                target_tick=target_tick, absent=absent
            )
            if not absent:
                self.assertEqual(candidates[0]["status"], "SUPPORTED")
            with self.subTest(tick=target_tick, absent=absent), self.assertRaises(ValueError):
                SparseTemporalIdentityPromotionAdapter().propose(
                    request(
                        store,
                        artifact_ids=(evidence,),
                        options={
                            "inference_ids": [inference],
                            "expected_tick_schedule": list(TICKS),
                            "missing_tick": 12,
                        },
                    ),
                    artifacts,
                )
            self.assertFalse(store.get_document(store.head).get("temporal_identities"))

    def test_schedule_is_explicit_and_not_twelve_tick_specific(self):
        store, artifacts, evidence, _, inference = self.primitive_gap(target_tick=14)
        for schedule, missing in (
            ([0, 7, 14, 21], 0),
            ([0, 7, 14, 21], 21),
            ([0, 7, 7, 14], 7),
            ([0, True, 14], True),
        ):
            with self.assertRaises(ValueError):
                SparseTemporalIdentityPromotionAdapter().propose(
                    request(
                        store,
                        artifact_ids=(evidence,),
                        options={
                            "inference_ids": [inference],
                            "expected_tick_schedule": schedule,
                            "missing_tick": missing,
                        },
                    ),
                    artifacts,
                )
        proposal = SparseTemporalIdentityPromotionAdapter().propose(
            request(
                store,
                artifact_ids=(evidence,),
                options={
                    "inference_ids": [inference],
                    "expected_tick_schedule": [0, 7, 14, 21],
                    "missing_tick": 7,
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        bindings = store.get_document(store.head)["temporal_identities"][0]["bindings"]
        self.assertEqual([b["tick"] for b in bindings], [0, 14])

    def test_second_occlusion_for_same_identity_rejects(self):
        store, artifacts, evidence, _, inference = self.primitive_gap()
        schedule = [0, 12, 24, 36, 48]
        first = SparseTemporalIdentityPromotionAdapter().propose(
            request(
                store,
                artifact_ids=(evidence,),
                options={
                    "inference_ids": [inference],
                    "expected_tick_schedule": schedule,
                    "missing_tick": 12,
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, first, artifacts)
        primitive = {
            "observation_id": "observation:target",
            "primitive_type": "rectangle",
            "bounds": [40, 40, 50, 50],
            "fill": "#00FF00",
        }
        source = artifacts.import_bytes(
            canonical_bytes(
                {
                    "schema_version": "svm-primitive-observations-0.1",
                    "canvas": [100, 100],
                    "frames": [
                        {"tick": 24, "primitives": [primitive]},
                        {
                            "tick": 48,
                            "primitives": [{**primitive, "observation_id": "observation:48"}],
                        },
                    ],
                }
            ),
            media_type=OBSERVATION_MEDIA_TYPE,
        )
        store.commit(
            store.head,
            Transaction(
                "transaction:second-gap-input",
                (AppendReferencesChange((source.document_reference(),)),),
            ),
        )
        r0 = TemporalCorrespondenceAdapter().propose(
            request(store, artifact_ids=(source.artifact_id,)), artifacts
        )
        ProposalAcceptor().accept(store, r0, artifacts)
        evidence = r0.preview_artifacts[0].artifact_id
        candidate = json.loads(artifacts.get(evidence).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        before = (store.head, store.get_document(store.head))
        with self.assertRaisesRegex(ValueError, "multiple gap"):
            SparseTemporalIdentityPromotionAdapter().propose(
                request(
                    store,
                    artifact_ids=(evidence,),
                    options={
                        "inference_ids": [candidate["inference_id"]],
                        "expected_tick_schedule": schedule,
                        "missing_tick": 36,
                    },
                ),
                artifacts,
            )
        self.assertEqual((store.head, store.get_document(store.head)), before)

    def test_missing_camera_endpoint_and_target_segmentation_mismatch_reject(self):
        with self.assertRaisesRegex(ValueError, "Camera chain"):
            prepare(camera_ticks=(0, 12, 25, 36))
        state = prepare()
        _, artifacts, _, _, _, proposal, inputs, _ = state
        sources = [artifacts.get(i) for i in inputs]
        original = sources[1]
        payload = json.loads(original.content)
        payload["intervals"][0]["target_tick"] = 12
        sources[1] = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        with self.assertRaisesRegex(ValueError, "exact observed sparse interval chain"):
            sparse_payloads(proposal.base_revision_id, tuple(sources))

    def test_forged_schedule_policy_identity_and_fake_occurrence_are_atomic(self):
        state = prepare()
        store, artifacts, _, _, scheduled, _, _, _ = state
        pending = scheduled.pending
        store.checkout(pending.base_revision_id)
        change = pending.transaction.changes[-1]
        original = artifacts.get(change.evidence_reference["id"])
        for mutate in (
            lambda p: p.update(expected_tick_schedule=[0, 12, 36]),
            lambda p: p.update(policy_identity="forged"),
            lambda p: p.update(missing_tick=24),
            lambda p: p.update(source_observation_id="observation:fake12"),
        ):
            payload = json.loads(original.content)
            mutate(payload)
            forged = artifacts.import_bytes(
                canonical_bytes(payload),
                media_type=original.media_type,
                kind=original.kind,
                provenance=original.provenance,
            )
            wrong = replace(change, evidence_reference=forged.document_reference())
            proposal = replace(
                pending,
                transaction=replace(
                    pending.transaction, changes=(*pending.transaction.changes[:-1], wrong)
                ),
                required_artifact_ids=tuple(
                    forged.artifact_id if i == original.artifact_id else i
                    for i in pending.required_artifact_ids
                ),
            )
            self.assert_atomic_rejection(store, artifacts, proposal, ProposalArtifactError)
        promotion = pending.transaction.changes[0]
        fake = replace(promotion.correspondences[0], target_tick=12)
        wrong = replace(promotion, correspondences=(fake,))
        self.assert_atomic_rejection(
            store,
            artifacts,
            replace(pending, transaction=replace(pending.transaction, changes=(wrong, change))),
            ProposalArtifactError,
        )

    def test_forged_sparse_evidence_and_temporal_identity_reject_atomically(self):
        store, artifacts, _, _, _, pending, _, _ = prepare()
        change = pending.transaction.changes[0]
        for output_index in (0, 1):
            original = artifacts.get(change.evidence_references[output_index]["id"])
            payload = json.loads(original.content)
            payload["camera_spans"][0]["target_view_transform"][4] += 2
            forged = artifacts.import_bytes(
                canonical_bytes(payload),
                media_type=original.media_type,
                kind=original.kind,
                provenance=original.provenance,
            )
            refs = list(change.evidence_references)
            refs[output_index] = forged.document_reference()
            wrong = replace(change, evidence_references=tuple(refs))
            proposal = replace(
                pending,
                transaction=replace(pending.transaction, changes=(wrong,)),
                required_artifact_ids=tuple(
                    forged.artifact_id if i == original.artifact_id else i
                    for i in pending.required_artifact_ids
                ),
            )
            self.assert_atomic_rejection(store, artifacts, proposal, ProposalArtifactError)
        for kind in ("fake_binding", "fake_identity", "fake_provenance"):
            identity = copy.deepcopy(change.temporal_identity)
            if kind == "fake_binding":
                identity["bindings"].insert(1, {"tick": 12, "observation_id": "observation:fake12"})
            elif kind == "fake_identity":
                identity["id"] = "temporal-identity:forged"
            else:
                identity["provenance"] = []
            wrong = replace(change, temporal_identity=identity)
            self.assert_atomic_rejection(
                store,
                artifacts,
                replace(pending, transaction=replace(pending.transaction, changes=(wrong,))),
                ProposalArtifactError,
            )

    def test_preview_stale_and_forged_binding_reject_atomically(self):
        state = prepare()
        store, artifacts, _, _, _, pending, inputs, options = state
        before = (store.head, store.get_document(store.head))
        repeated = SparseCameraCompensatedMotionAdapter().propose(
            request(store, artifact_ids=inputs, options=options), artifacts
        )
        self.assertEqual(pending, repeated)
        self.assertEqual((store.head, store.get_document(store.head)), before)
        translations = author(state)[0]
        self.assert_atomic_rejection(store, artifacts, translations, ProposalConflictError)
        store.checkout(translations.base_revision_id)
        before = store.get_document(store.head)
        change = translations.transaction.changes[-1]
        binding = copy.deepcopy(change.binding)
        binding["provenance"]["source_revision_id"] = "revision:stale"
        wrong = replace(change, binding=binding)
        self.assert_atomic_rejection(
            store,
            artifacts,
            replace(
                translations,
                transaction=replace(
                    translations.transaction,
                    changes=(*translations.transaction.changes[:-1], wrong),
                ),
            ),
        )
        self.assertEqual(store.get_document(store.head), before)
        transform = copy.deepcopy(before["groups"][0]["transform"])
        transform["translate"] = [1, 0]
        store.commit(
            store.head,
            Transaction("transaction:stale-sparse", (SetGroupTransformChange(GROUP, transform),)),
        )
        self.assert_atomic_rejection(store, artifacts, translations, ProposalConflictError)

    def test_fixture_has_real_absence_and_supported_sparse_lineage(self):
        base, truth = documents()
        self.assertEqual(json.loads((FIXTURE / "recovery-base.svm.json").read_text()), base)
        self.assertEqual(json.loads((FIXTURE / "ground-truth.svm.json").read_text()), truth)
        for t, content in zip(TICKS, rendered_observations(truth), strict=True):
            self.assertEqual((FIXTURE / "observations" / f"tick_{t:03d}.svg").read_bytes(), content)
        state = prepare()
        store, artifacts, frames, target, _, _, _, _ = state
        visible = {e.get("data-svm-entity") for e in ET.fromstring(frames[1].content).iter()}
        self.assertNotIn(TARGET, visible)
        self.assertTrue(set(ANCHORS) <= visible)
        with self.assertRaises(ValueError):
            derive_svg_polygon_observations(
                frames[0], frames[1], TARGET, 0, 12, policy_identity=OCCURRENCE_POLICY_IDENTITY
            )
        identity = next(
            i
            for i in store.get_document(store.head)["temporal_identities"]
            if i["id"] == target["identity_id"]
        )
        self.assertEqual([b["tick"] for b in identity["bindings"]], list(VISIBLE))
        self.assertEqual(len(identity["provenance"]), 2)
        for evidence_id in (target["translation_id"], target["similarity_id"]):
            payload = json.loads(artifacts.get(evidence_id).content)
            self.assertEqual(
                [(i["source_tick"], i["target_tick"]) for i in payload["intervals"]],
                [(0, 24), (24, 36)],
            )
        r0 = json.loads(artifacts.get(target["correspondence_ids"][0]).content)
        self.assertEqual(r0["frame_ticks"], [0, 24])
        self.assertEqual(r0["candidates"][0]["status"], "SUPPORTED")

    def test_full_recovery_determinism_and_runtime_interpolation(self):
        results = []
        max_numeric = max_geometry = 0.0
        for _ in range(2):
            state = prepare()
            store, artifacts, frames, target, policy, compensation, _, _ = state
            author(state)
            final = store.get_document(store.head)
            truth = json.loads((FIXTURE / "ground-truth.svm.json").read_text())
            actual, expected = MotionEvaluator(final), MotionEvaluator(truth)
            for track in final["animation"]["content"]:
                self.assertEqual(
                    [k["tick"] for k in track["keyframes"]],
                    list(TICKS if "camera" in track["target"] else VISIBLE),
                )
                if "group" in track["target"]:
                    at12 = actual.sample_document(12)["groups"][0]["transform"]
                    prop = track["target"]["property"]
                    sample = (
                        at12["translate"][0 if prop.endswith("x") else 1]
                        if prop.startswith("translate")
                        else at12[prop]
                    )
                    self.assertAlmostEqual(
                        sample,
                        (track["keyframes"][0]["value"] + track["keyframes"][1]["value"]) / 2,
                    )
            renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
            for tick, frozen in zip(TICKS, frames, strict=True):
                a, b = actual.sample_document(tick), expected.sample_document(tick)
                subjects = [(a["presentation"]["camera"], b["presentation"]["camera"], "position")]
                if tick in VISIBLE:
                    subjects.append(
                        (a["groups"][0]["transform"], b["groups"][0]["transform"], "translate")
                    )
                for left, right, prop in subjects:
                    max_numeric = max(
                        max_numeric,
                        *(
                            abs(x - y)
                            for x, y in zip(
                                (*left[prop], left["rotation_degrees"], left["scale"]),
                                (*right[prop], right["rotation_degrees"], right["scale"]),
                                strict=True,
                            )
                        ),
                    )
                rendered = artifacts.import_bytes(
                    renderer.render(actual.evaluate(tick).scene).encode(),
                    media_type="image/svg+xml",
                )
                for selector in (*ANCHORS, TARGET) if tick in VISIBLE else ANCHORS:
                    pair = derive_svg_polygon_observations(
                        rendered,
                        frozen,
                        selector,
                        tick,
                        tick + 1,
                        policy_identity=OCCURRENCE_POLICY_IDENTITY,
                    )["frames"]
                    for p, q in zip(
                        *(f["primitives"][0]["geometry"]["points"] for f in pair), strict=True
                    ):
                        max_geometry = max(
                            max_geometry, *(abs(x - y) for x, y in zip(p, q, strict=True))
                        )
            results.append((final, target, policy.policy_id, compensation, store.head))
        self.assertEqual(results[0], results[1])
        self.assertLess(max_numeric, 3e-8)
        self.assertLess(max_geometry, 3e-8)
        print(f"S10D numeric error={max_numeric:.12g}; observed geometry error={max_geometry:.12g}")

    def test_camera_gap_uses_both_absolute_endpoints_and_legacy_stays_strict(self):
        state = prepare()
        store, artifacts, _, target, _, proposal, inputs, options = state
        with self.assertRaisesRegex(ValueError, "intervals must match"):
            CameraCompensatedMotionAdapter().propose(
                request(store, artifact_ids=inputs[:3], options=options), artifacts
            )
        payload = json.loads(artifacts.get(proposal.preview_artifacts[1].artifact_id).content)
        dense = json.loads(artifacts.get(inputs[0]).content)["intervals"]
        span = payload["camera_spans"][0]
        self.assertEqual((span["source_tick"], span["target_tick"]), (0, 24))
        self.assertEqual(span["source_view_transform"], dense[0]["source_view_transform"])
        self.assertEqual(span["target_view_transform"], dense[1]["target_view_transform"])
        self.assertEqual(span["source_camera_interval_ids"], [i["interval_id"] for i in dense[:2]])
        observed = _interval_matrix(
            json.loads(artifacts.get(target["similarity_id"]).content)["intervals"][0], "target"
        )
        exact = _compose(
            _compose(_inverse(span["target_view_transform"]), observed),
            span["source_view_transform"],
        )
        truth = MotionEvaluator(json.loads((FIXTURE / "ground-truth.svm.json").read_text()))
        g0 = _group_transform_matrix(truth.sample_document(0)["groups"][0]["transform"])
        g24 = _group_transform_matrix(truth.sample_document(24)["groups"][0]["transform"])
        ground_truth_relative = _compose(g24, _inverse(g0))
        self.assertLess(
            max(abs(a - b) for a, b in zip(exact, ground_truth_relative, strict=True)), 3e-8
        )
        wrong = _compose(_inverse(dense[0]["target_view_transform"]), observed)
        self.assertGreater(max(abs(a - b) for a, b in zip(exact, wrong, strict=True)), 0.01)
        summed = [
            dense[0]["relative_view_transform"][k] + dense[1]["relative_view_transform"][k]
            for k in (4, 5)
        ]
        self.assertGreater(
            max(abs(a - b) for a, b in zip(summed, span["target_view_transform"][4:], strict=True)),
            0.001,
        )


if __name__ == "__main__":
    unittest.main()
