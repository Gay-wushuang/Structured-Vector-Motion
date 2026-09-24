import copy
import json
import math
import re
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from test_raster_recovery_acceptance import accept, analyze, observation_request, payload, request

from svm import (
    ArtifactStore,
    MotionEvaluator,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
)
from svm.adapters import (
    CameraCompensatedMotionAdapter,
    GeometryTranslationTracksAdapter,
    MultiAnchorCameraConsensusAdapter,
    ObservedCameraSimilarityAdapter,
    ObservedCameraTracksAdapter,
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    ObservedTranslationMotionAdapter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.camera_compensation import _compose, _point
from svm.adapters.camera_consensus import MEASURED_POLICY
from svm.adapters.observed_similarity_motion import RasterObservedSimilarityMotionAdapter
from svm.adapters.raster_geometry_observations import RasterGeometryObservationAdapter
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

FIXTURE = Path(__file__).resolve().parents[1] / "examples/036-controlled-raster-camera-recovery"
TICKS = (0, 12, 24, 36)
ANCHORS = ("entity:anchor-a", "entity:anchor-b")
TARGET = "entity:recovery-target"
GROUP = "group:" + "1" * 64


def lineage(store, artifacts, analyses, role, selectors):
    geometries, correspondences, inferences = [], [], []
    for i in range(3):
        proposal = RasterGeometryObservationAdapter().propose(
            observation_request(
                store,
                analyses[i],
                analyses[i + 1],
                TICKS[i : i + 2],
                (selectors[str(TICKS[i])][role], selectors[str(TICKS[i + 1])][role]),
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        gid = proposal.preview_artifacts[0].artifact_id
        geometries.append(gid)
        r0 = accept(store, artifacts, TemporalCorrespondenceAdapter(), [gid])
        rid = r0.preview_artifacts[0].artifact_id
        correspondences.append(rid)
        candidate = payload(artifacts, r0)["candidates"][0]
        inferences.append(candidate["inference_id"])
        identity = accept(
            store,
            artifacts,
            TemporalIdentityPromotionAdapter(),
            [rid],
            {"inference_ids": [candidate["inference_id"]]},
        )
        identity_id = identity.preview.temporal_identities[0].stable_identity_id
    options = {"temporal_identity_id": identity_id, "inference_ids": inferences}
    s0 = accept(store, artifacts, ObservedTranslationMotionAdapter(), correspondences, options)
    s4 = accept(
        store,
        artifacts,
        RasterObservedSimilarityMotionAdapter(),
        [*geometries, *correspondences],
        options,
    )
    return {
        "geometry_ids": geometries,
        "correspondence_ids": correspondences,
        "identity_id": identity_id,
        "translation_id": s0.preview_artifacts[0].artifact_id,
        "similarity_id": s4.preview_artifacts[0].artifact_id,
    }


def hypotheses(*, disagreement=False, wrong_selector=False, repeated=False):
    store = RevisionStore.create(json.loads((FIXTURE / "recovery-base.svm.json").read_text()))
    artifacts = ArtifactStore()
    analyses = [
        analyze(
            store,
            artifacts,
            content=(
                FIXTURE
                / f"{'disagree' if disagreement else 'tick'}_{0 if repeated else tick:03}.png"
            ).read_bytes(),
        )[1]
        for tick in TICKS
    ]
    selectors = json.loads((FIXTURE / "selectors.json").read_text())
    if wrong_selector:
        selectors["24"][ANCHORS[0]] = selectors["24"][TARGET]
    lineages = {}
    cameras = []
    for role in (*ANCHORS, TARGET):
        lineages[role] = lineage(store, artifacts, analyses, role, selectors)
        if role in ANCHORS:
            p = accept(
                store,
                artifacts,
                ObservedCameraSimilarityAdapter(),
                [lineages[role]["similarity_id"]],
                {"anchor_entity_id": role},
            )
            cameras.append(p.preview_artifacts[0].artifact_id)
    return store, artifacts, lineages, cameras


def consensus_proposal(state, reverse=False, policy=MEASURED_POLICY):
    store, artifacts, _, cameras = state
    return MultiAnchorCameraConsensusAdapter().propose(
        request(
            store,
            cameras[::-1] if reverse else cameras,
            {
                "anchor_entity_ids": list(ANCHORS[::-1] if reverse else ANCHORS),
                "agreement_policy": policy,
            },
        ),
        artifacts,
    )


def recover(state, reverse=False):
    store, artifacts, lineages, _ = state
    consensus = consensus_proposal(state, reverse)
    ProposalAcceptor().accept(store, consensus, artifacts)
    camera_id = consensus.preview_artifacts[0].artifact_id
    target = lineages[TARGET]
    compensation = accept(
        store,
        artifacts,
        CameraCompensatedMotionAdapter(),
        [camera_id, target["translation_id"], target["similarity_id"]],
        {"anchor_entity_ids": list(ANCHORS), "target_temporal_identity_id": target["identity_id"]},
    )
    binding = accept(
        store,
        artifacts,
        TemporalMotionTargetBindingAdapter(),
        options={"temporal_identity_id": target["identity_id"], "group_id": GROUP},
    )
    binding_id = binding.preview.motion_target_bindings[0].binding_id
    for adapter in (
        GeometryTranslationTracksAdapter(),
        ObservedRotationTracksAdapter(),
        ObservedScaleTracksAdapter(),
    ):
        accept(
            store,
            artifacts,
            adapter,
            [compensation.preview_artifacts[1].artifact_id],
            {"motion_target_binding_id": binding_id, "ticks_per_second": 12},
        )
    accept(
        store,
        artifacts,
        ObservedCameraTracksAdapter(),
        [camera_id],
        {"camera_target": "presentation", "ticks_per_second": 12},
    )
    return store.get_document(store.head), consensus, compensation


class RasterCameraRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = hypotheses()

    def state(self):
        return copy.deepcopy(self.baseline)

    def assert_atomic(self, store, artifacts, proposal, error=ProposalArtifactError):
        before = (store.head, store.get_document(store.head), len(store.revisions))
        with self.assertRaises(error):
            ProposalAcceptor().accept(store, proposal, artifacts)
        self.assertEqual((store.head, store.get_document(store.head), len(store.revisions)), before)

    def test_full_pixel_recovery_geometry_and_determinism(self):
        state = self.state()
        store, artifacts, lineages, cameras = state
        before = store.head
        normal, reverse = consensus_proposal(state), consensus_proposal(state, True)
        self.assertEqual(normal, reverse)
        self.assertEqual(store.head, before)
        document, consensus, compensation = recover(state)
        second = hypotheses()
        other, second_consensus, second_compensation = recover(second, True)
        self.assertEqual(document, other)
        self.assertEqual(store.head, second[0].head)
        self.assertEqual(lineages, second[2])
        self.assertEqual(cameras, second[3])
        self.assertEqual(consensus.preview_artifacts, second_consensus.preview_artifacts)
        self.assertEqual(compensation.preview_artifacts, second_compensation.preview_artifacts)
        self.assertEqual(len({item["identity_id"] for item in lineages.values()}), 3)
        tracks = document["animation"]["content"]
        self.assertEqual(len(tracks), 8)
        self.assertEqual(
            {t["target"]["property"] for t in tracks if "group" in t["target"]},
            {"translate.x", "translate.y", "rotation_degrees", "scale"},
        )
        self.assertEqual(
            {t["target"]["property"] for t in tracks if "camera" in t["target"]},
            {"position.x", "position.y", "rotation_degrees", "scale"},
        )
        for track in tracks:
            source = track["provenance"]["evidence_artifact_id"]
            self.assertEqual(
                source,
                consensus.preview_artifacts[0].artifact_id
                if "camera" in track["target"]
                else compensation.preview_artifacts[1].artifact_id,
            )
        camera_payload = payload(artifacts, consensus)
        representative = json.loads(artifacts.get(cameras[0]).content)
        for consensus_interval, single in zip(
            camera_payload["intervals"], representative["intervals"], strict=True
        ):
            for key in (
                "relative_view_transform",
                "source_view_transform",
                "target_view_transform",
            ):
                self.assertEqual(consensus_interval[key], single[key])
        for role in ANCHORS:
            interval = json.loads(artifacts.get(lineages[role]["geometry_ids"][1]).content)[
                "frames"
            ]
            self.assertEqual(
                interval[0]["primitives"][0]["geometry"], interval[1]["primitives"][0]["geometry"]
            )
            self.assertNotEqual(
                interval[0]["primitives"][0]["observation_id"],
                interval[1]["primitives"][0]["observation_id"],
            )
        hold = camera_payload["intervals"][1]
        self.assertEqual(hold["relative_view_transform"], [1, 0, 0, 1, 0, 0])
        self.assertEqual(hold["source_view_transform"], hold["target_view_transform"])
        errors = numerical_errors(document, artifacts, lineages)
        for name, actual in errors.items():
            limit = {
                "target_position": 1.0,
                "target_rotation": 0.2,
                "target_scale": 0.005,
                "camera_position": 1.0,
                "camera_rotation": 0.2,
                "camera_scale": 0.003,
                "geometry": 2.0,
            }[name]
            self.assertLessEqual(actual, limit, (name, actual))
        print("S11B maximum errors:", errors)
        refs = {r["id"]: r for r in document["references"]}
        for role in (*ANCHORS, TARGET):
            for gid in lineages[role]["geometry_ids"]:
                geometry = artifacts.resolve_reference(refs[gid])
                for occurrence in geometry.provenance["source_occurrences"]:
                    analysis = json.loads(
                        artifacts.resolve_reference(
                            refs[occurrence["analysis_artifact_id"]]
                        ).content
                    )
                    self.assertEqual(
                        analysis["source_artifact_id"], occurrence["source_png_artifact_id"]
                    )
                    self.assertEqual(
                        analysis["binary_mask_artifact_id"], occurrence["mask_artifact_id"]
                    )
                    selected = next(
                        c
                        for c in analysis["components"]
                        if c["candidate_id"] == occurrence["component_id"]
                    )
                    self.assertEqual(selected["component_digest"], occurrence["component_digest"])

    def test_disagreement_and_wrong_component_fail_closed(self):
        state = hypotheses(disagreement=True)
        before = state[0].head
        with self.assertRaisesRegex(ValueError, "disagree"):
            consensus_proposal(state)
        self.assertEqual(state[0].head, before)
        with self.assertRaises(ValueError):
            hypotheses(wrong_selector=True)

    def test_policy_and_tolerance_forgery_reject_atomically(self):
        from svm.adapters.camera_consensus import POLICY

        state = self.state()
        store, artifacts, _, _ = state
        with self.assertRaisesRegex(ValueError, "policy"):
            consensus_proposal(state, policy=POLICY)
        proposal = consensus_proposal(state)
        change = proposal.transaction.changes[0]
        original = artifacts.get(proposal.preview_artifacts[0].artifact_id)
        for mutation in ("policy", "threshold", "representative", "matrix"):
            data = json.loads(original.content)
            if mutation == "policy":
                data["policy_identity"] = POLICY
            if mutation == "threshold":
                data["agreement_tolerances"]["position_pixels"] = 100
            if mutation == "representative":
                data["representative"] = data["supporting_hypotheses"][1]
            if mutation == "matrix":
                data["intervals"][0]["target_view_transform"][4] += 0.1
            forged = artifacts.import_bytes(
                canonical_bytes(data),
                media_type=original.media_type,
                kind=original.kind,
                provenance=original.provenance,
            )
            altered = replace(change, evidence_references=(forged.document_reference(),))
            invalid = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(altered,)),
                required_artifact_ids=(
                    forged.artifact_id,
                    *(r["id"] for r in change.source_references),
                ),
            )
            with self.subTest(mutation=mutation):
                self.assert_atomic(store, artifacts, invalid)

    def test_moving_anchor_and_animated_group_are_rejected(self):
        from svm.revisions import (
            AddKeyframeChange,
            CreateGroupTransformTrackChange,
            CreateStyleTrackChange,
            Transaction,
        )

        for parent in (False, True):
            state = self.state()
            store, artifacts, lineages, _ = state
            if parent:
                document = store.get_document(store.head)
                document["groups"][0]["members"].append(ANCHORS[1])
                document["groups"][0]["members"].sort()
                store = RevisionStore.create(document)
                create = CreateGroupTransformTrackChange(
                    "track:moving-anchor", GROUP, "translate.x", 12
                )
            else:
                create = CreateStyleTrackChange(
                    "track:moving-anchor", ANCHORS[1], "opacity", 12, "linear"
                )
            store.commit(
                store.head,
                Transaction(
                    "transaction:moving-anchor",
                    (
                        create,
                        AddKeyframeChange("track:moving-anchor", "keyframe:moving-anchor", 0, 1),
                    ),
                ),
            )
            before = store.head
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, "not static"):
                ObservedCameraSimilarityAdapter().propose(
                    request(
                        store,
                        [lineages[ANCHORS[1]]["similarity_id"]],
                        {"anchor_entity_id": ANCHORS[1]},
                    ),
                    artifacts,
                )
            self.assertEqual(store.head, before)

    def test_camera_side_pixel_lineage_tampering_is_atomic(self):
        store, artifacts, lineages, _ = self.state()
        proposal = ObservedCameraSimilarityAdapter().propose(
            request(
                store, [lineages[ANCHORS[0]]["similarity_id"]], {"anchor_entity_id": ANCHORS[0]}
            ),
            artifacts,
        )
        change = proposal.transaction.changes[0]
        gid = lineages[ANCHORS[0]]["geometry_ids"][0]
        original = artifacts.get(gid)
        metadata = copy.deepcopy(original.provenance)
        metadata["source_occurrences"][0]["component_digest"] = "sha256:" + "f" * 64
        fake = artifacts.import_bytes(
            original.content,
            media_type=original.media_type,
            kind=original.kind,
            provenance=metadata,
        )
        refs = tuple(
            fake.document_reference() if r["id"] == gid else r for r in change.source_references
        )
        invalid = replace(
            proposal,
            transaction=replace(
                proposal.transaction, changes=(replace(change, source_references=refs),)
            ),
        )
        self.assert_atomic(store, artifacts, invalid)
        # Omitting the PNG/mask dependencies cannot bypass the new Camera verifier.
        refs = tuple(r for r in change.source_references if r["media_type"] != "image/png")
        missing = replace(change, source_references=refs)
        invalid = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(missing,)),
            required_artifact_ids=tuple(r["id"] for r in missing.references),
        )
        self.assert_atomic(store, artifacts, invalid)

    def test_vector_evidence_relabelled_raster_cannot_enter_camera_consensus(self):
        from test_camera_consensus import ANCHORS as VECTOR_ANCHORS
        from test_camera_consensus import hypotheses as vector_hypotheses

        from svm.adapters.camera_compensation import MEASURED_CAMERA_POLICY, _camera_provenance
        from svm.adapters.observed_similarity_motion import RASTER_POLICY_IDENTITY
        from svm.revisions import AppendReferencesChange, Transaction

        store, artifacts, ids, _, _ = vector_hypotheses()
        refs = []
        forged_ids = []
        for aid in ids:
            original = artifacts.get(aid)
            camera = json.loads(original.content)
            similarity = artifacts.get(camera["source_similarity_artifact_id"])
            data = json.loads(similarity.content)
            data["policy_identity"] = RASTER_POLICY_IDENTITY
            provenance = {
                **similarity.provenance,
                "policy_identity": RASTER_POLICY_IDENTITY,
                "adapter_version": "0.2",
            }
            fake_similarity = artifacts.import_bytes(
                canonical_bytes(data),
                media_type=similarity.media_type,
                kind=similarity.kind,
                provenance=provenance,
            )
            camera.update(
                policy_identity=MEASURED_CAMERA_POLICY,
                measurement_policy_identity=RASTER_POLICY_IDENTITY,
                source_similarity_artifact_id=fake_similarity.artifact_id,
            )
            fake_camera = artifacts.import_bytes(
                canonical_bytes(camera),
                media_type=original.media_type,
                kind=original.kind,
                provenance=_camera_provenance(fake_similarity.artifact_id, MEASURED_CAMERA_POLICY),
            )
            refs.extend((fake_similarity.document_reference(), fake_camera.document_reference()))
            forged_ids.append(fake_camera.artifact_id)
        store.commit(
            store.head,
            Transaction("transaction:untrusted-vector", (AppendReferencesChange(tuple(refs)),)),
        )
        before = store.head
        with self.assertRaisesRegex(ValueError, "raster geometry policy"):
            MultiAnchorCameraConsensusAdapter().propose(
                request(
                    store,
                    forged_ids,
                    {
                        "anchor_entity_ids": list(VECTOR_ANCHORS),
                        "agreement_policy": MEASURED_POLICY,
                    },
                ),
                artifacts,
            )
        self.assertEqual(store.head, before)

    def test_one_lineage_cannot_claim_two_independent_anchors(self):
        state = self.state()
        store, artifacts, lineages, cameras = state
        wrong = accept(
            store,
            artifacts,
            ObservedCameraSimilarityAdapter(),
            [lineages[ANCHORS[0]]["similarity_id"]],
            {"anchor_entity_id": ANCHORS[1]},
        )
        cameras[1] = wrong.preview_artifacts[0].artifact_id
        with self.assertRaisesRegex(ValueError, "independent"):
            consensus_proposal(state)

    def test_repeated_png_has_distinct_occurrences_and_zero_camera_motion(self):
        state = hypotheses(repeated=True)
        document, consensus, _ = recover(state)
        store, artifacts, lineages, _ = state
        for role in ANCHORS:
            geometry = artifacts.get(lineages[role]["geometry_ids"][0])
            occurrences = geometry.provenance["source_occurrences"]
            self.assertEqual(
                occurrences[0]["source_png_artifact_id"], occurrences[1]["source_png_artifact_id"]
            )
            frames = json.loads(geometry.content)["frames"]
            self.assertNotEqual(
                frames[0]["primitives"][0]["observation_id"],
                frames[1]["primitives"][0]["observation_id"],
            )
            r0 = json.loads(artifacts.get(lineages[role]["correspondence_ids"][0]).content)[
                "candidates"
            ][0]
            self.assertEqual(r0["status"], "SUPPORTED")
            self.assertEqual(r0["displacement"], [0, 0])
        for interval in payload(artifacts, consensus)["intervals"]:
            self.assertEqual(interval["relative_view_transform"], [1, 0, 0, 1, 0, 0])
        evaluator = MotionEvaluator(document)
        for tick in TICKS:
            self.assertEqual(
                evaluator.sample_document(tick)["presentation"]["camera"],
                {"position": [0, 0], "rotation_degrees": 0, "scale": 1},
            )

    def test_agreement_checks_every_pair_and_each_physical_limit(self):
        from svm.adapters.camera_consensus import _verify_measured_agreement
        from svm.scene import _camera_transform_matrix

        identity = {"position": [0, 0], "rotation_degrees": 0, "scale": 1}
        for altered in (
            {**identity, "position": [2.6, 0]},
            {**identity, "rotation_degrees": 0.21},
            {**identity, "scale": 1.0031},
        ):
            with self.assertRaisesRegex(ValueError, "disagree"):
                _verify_measured_agreement(
                    [_camera_transform_matrix(identity), _camera_transform_matrix(altered)]
                )
        # Both extremes are near the middle, but not near one another.
        with self.assertRaisesRegex(ValueError, "disagree"):
            _verify_measured_agreement(
                [_camera_transform_matrix({**identity, "position": [x, 0]}) for x in (2, 0, 4)]
            )


def numerical_errors(document, artifacts, lineages):
    # Ground Truth is accessed only after complete recovery and authoring.
    truth = json.loads((FIXTURE / "ground-truth.json").read_text())["samples"]
    evaluator = MotionEvaluator(document)
    errors = {
        key: 0.0
        for key in (
            "target_position",
            "target_rotation",
            "target_scale",
            "camera_position",
            "camera_rotation",
            "camera_scale",
            "geometry",
        )
    }
    renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 1200, 900)))
    for tick in TICKS:
        sampled = evaluator.sample_document(tick)
        for name, actual, expected, position in (
            ("target", sampled["groups"][0]["transform"], truth[str(tick)]["target"], "translate"),
            ("camera", sampled["presentation"]["camera"], truth[str(tick)]["camera"], "position"),
        ):
            errors[name + "_position"] = max(
                errors[name + "_position"], math.dist(actual[position], expected[position])
            )
            for key, field in (("rotation", "rotation_degrees"), ("scale", "scale")):
                errors[name + "_" + key] = max(
                    errors[name + "_" + key], abs(actual[field] - expected[field])
                )
        root = ET.fromstring(renderer.render(evaluator.evaluate(tick).scene))
        ns = {"s": "http://www.w3.org/2000/svg"}
        stack = root.find("s:g[@data-svm-role='render-stack']", ns)

        def matrix(value):
            return (
                tuple(
                    float(x) for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", value)
                )
                if value
                else (1, 0, 0, 1, 0, 0)
            )

        camera = matrix(stack.get("transform"))
        for role in (*ANCHORS, TARGET):
            group = stack.find(f"s:g[@data-svm-entity='{role}']", ns)
            inner = group.find("s:g", ns)
            world = matrix(inner.get("transform")) if inner is not None else (1, 0, 0, 1, 0, 0)
            path = group.find(".//s:path", ns)
            numbers = [
                float(x)
                for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path.get("d"))
            ]
            rendered = [
                _point(_compose(camera, world), p)
                for p in zip(numbers[::2], numbers[1::2], strict=True)
            ]
            geometry_id = lineages[role]["geometry_ids"][min(TICKS.index(tick), 2)]
            frame = next(
                f
                for f in json.loads(artifacts.get(geometry_id).content)["frames"]
                if f["tick"] == tick
            )
            observed = frame["primitives"][0]["geometry"]["points"]
            if len(rendered) != len(observed):
                raise AssertionError("Raster/rendered landmark topology differs")
            error = max(
                max(min(math.dist(p, q) for q in observed) for p in rendered),
                max(min(math.dist(p, q) for q in rendered) for p in observed),
            )
            errors["geometry"] = max(errors["geometry"], error)
    return errors
