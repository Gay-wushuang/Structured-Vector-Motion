"""S11C: explicit independent pixel lineages, shared Camera, ordinary authoring."""

import copy
import io
import json
import math
import re
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from test_raster_camera_recovery import ANCHORS, TICKS, consensus_proposal, lineage
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
    ObservedCameraSimilarityAdapter,
    ObservedCameraTracksAdapter,
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.camera_compensation import _compose, _point
from svm.adapters.raster_geometry_observations import RasterGeometryObservationAdapter
from svm.evaluator import DocumentError, canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

FIXTURE = Path(__file__).resolve().parents[1] / "examples/037-explicit-multi-object-raster-recovery"
TARGETS = ("entity:target-a", "entity:target-b")
GROUPS = ("group:" + "1" * 64, "group:" + "b" * 64)
ROLES = (*ANCHORS, *TARGETS)


def prepare(*, swap=False, disagreement=False, frame_sources=None):
    # No ground truth, generation, role inference, or source vector observations.
    store = RevisionStore.create(json.loads((FIXTURE / "recovery-base.svm.json").read_text()))
    artifacts = ArtifactStore()
    analyses = [
        analyze(
            store,
            artifacts,
            content=frame_sources[index]
            if frame_sources is not None
            else (
                FIXTURE / ("disagree_012.png" if disagreement and t == 12 else f"tick_{t:03}.png")
            ).read_bytes(),
        )[1]
        for index, t in enumerate(TICKS)
    ]
    selectors = json.loads((FIXTURE / "selectors.json").read_text())
    if swap:
        selectors["12"][TARGETS[0]], selectors["12"][TARGETS[1]] = (
            selectors["12"][TARGETS[1]],
            selectors["12"][TARGETS[0]],
        )
    lineages, cameras = {}, []
    for role in ROLES:
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
    # One accepted consensus, reused verbatim for both targets.
    state = (store, artifacts, lineages, cameras)
    consensus = consensus_proposal(state)
    ProposalAcceptor().accept(store, consensus, artifacts)
    cid = consensus.preview_artifacts[0].artifact_id
    targets = {}
    for role, group in zip(TARGETS, GROUPS, strict=True):
        item = lineages[role]
        compensation = accept(
            store,
            artifacts,
            CameraCompensatedMotionAdapter(),
            [cid, item["translation_id"], item["similarity_id"]],
            {
                "anchor_entity_ids": list(ANCHORS),
                "target_temporal_identity_id": item["identity_id"],
            },
        )
        binding = accept(
            store,
            artifacts,
            TemporalMotionTargetBindingAdapter(),
            options={"temporal_identity_id": item["identity_id"], "group_id": group},
        )
        targets[role] = {
            "compensation": compensation,
            "evidence_id": compensation.preview_artifacts[1].artifact_id,
            "binding_id": binding.preview.motion_target_bindings[0].binding_id,
        }
    return {
        "store": store,
        "artifacts": artifacts,
        "analyses": analyses,
        "lineages": lineages,
        "cameras": cameras,
        "consensus": consensus,
        "camera_id": cid,
        "targets": targets,
    }


def author_target(state, role):
    store, artifacts = state["store"], state["artifacts"]
    item = state["targets"][role]
    proposals = []
    for adapter in (
        GeometryTranslationTracksAdapter(),
        ObservedRotationTracksAdapter(),
        ObservedScaleTracksAdapter(),
    ):
        before = (store.head, store.get_document(store.head), len(store.revisions))
        p = adapter.propose(
            request(
                store,
                [item["evidence_id"]],
                {"motion_target_binding_id": item["binding_id"], "ticks_per_second": 12},
            ),
            artifacts,
        )
        if before != (store.head, store.get_document(store.head), len(store.revisions)):
            raise AssertionError("Preview mutated accepted state")
        ProposalAcceptor().accept(store, p, artifacts)
        proposals.append(p)
    return proposals


def author_all(state):
    store, artifacts = state["store"], state["artifacts"]
    proposals = author_target(state, TARGETS[0])
    proposals.append(
        accept(
            store,
            artifacts,
            ObservedCameraTracksAdapter(),
            [state["camera_id"]],
            {"camera_target": "presentation", "ticks_per_second": 12},
        )
    )
    before = store.get_document(store.head)["animation"]["content"]
    if len(before) != 8 or any(t["target"].get("group") == GROUPS[1] for t in before):
        raise AssertionError("Target B authored implicitly")
    proposals.extend(author_target(state, TARGETS[1]))
    document = store.get_document(store.head)
    retained = [
        t for t in document["animation"]["content"] if t["target"].get("group") != GROUPS[1]
    ]
    if retained != before:
        raise AssertionError("Authoring B modified A or rebuilt Camera Tracks")
    return document, proposals


def measure(document, artifacts, lineages):
    # First truth access: all twelve Tracks have already been accepted.
    truth = json.loads((FIXTURE / "ground-truth.json").read_text())["samples"]
    evaluator = MotionEvaluator(document)
    errors = {r: {k: 0.0 for k in ("position", "rotation", "scale")} for r in (*TARGETS, "camera")}
    geometry_errors = dict.fromkeys(ROLES, 0.0)
    renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 1200, 900)))
    number = r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?"

    def matrix(value):
        return tuple(map(float, re.findall(number, value))) if value else (1, 0, 0, 1, 0, 0)

    for tick in TICKS:
        sampled = evaluator.sample_document(tick)
        comparisons = [
            (
                r,
                next(g["transform"] for g in sampled["groups"] if g["id"] == group),
                truth[str(tick)]["targets"][r],
                "translate",
            )
            for r, group in zip(TARGETS, GROUPS, strict=True)
        ]
        comparisons.append(
            ("camera", sampled["presentation"]["camera"], truth[str(tick)]["camera"], "position")
        )
        for role, actual, expected, position in comparisons:
            errors[role]["position"] = max(
                errors[role]["position"], math.dist(actual[position], expected[position])
            )
            for key, field in (("rotation", "rotation_degrees"), ("scale", "scale")):
                errors[role][key] = max(errors[role][key], abs(actual[field] - expected[field]))
        ns = {"s": "http://www.w3.org/2000/svg"}
        stack = ET.fromstring(renderer.render(evaluator.evaluate(tick).scene)).find(
            "s:g[@data-svm-role='render-stack']", ns
        )
        camera = matrix(stack.get("transform"))
        for role in ROLES:
            node = stack.find(f"s:g[@data-svm-entity='{role}']", ns)
            inner = node.find("s:g", ns)
            world = matrix(inner.get("transform")) if inner is not None else (1, 0, 0, 1, 0, 0)
            numbers = list(map(float, re.findall(number, node.find(".//s:path", ns).get("d"))))
            rendered = [
                _point(_compose(camera, world), p)
                for p in zip(numbers[::2], numbers[1::2], strict=True)
            ]
            gid = lineages[role]["geometry_ids"][min(TICKS.index(tick), 2)]
            frame = next(
                f for f in json.loads(artifacts.get(gid).content)["frames"] if f["tick"] == tick
            )
            observed = frame["primitives"][0]["geometry"]["points"]
            if len(rendered) != len(observed):
                raise AssertionError((role, tick, "Raster/rendered landmark topology differs"))
            geometry_errors[role] = max(
                geometry_errors[role],
                max(min(math.dist(p, q) for q in observed) for p in rendered),
                max(min(math.dist(p, q) for q in rendered) for p in observed),
            )
    return errors, geometry_errors


class MultiObjectRasterRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = prepare()

    def state(self):
        return copy.deepcopy(self.baseline)

    def test_frozen_pixels_explicit_selection_and_static_baseline(self):
        from PIL import Image

        selectors = json.loads((FIXTURE / "selectors.json").read_text())
        for tick, analysis_id in zip(TICKS, self.baseline["analyses"], strict=True):
            image = Image.open(io.BytesIO((FIXTURE / f"tick_{tick:03}.png").read_bytes()))
            self.assertEqual(image.mode, "L")
            self.assertEqual(image.size, (1200, 900))
            self.assertEqual({value for _, value in image.getcolors()}, {0, 255})
            components = json.loads(self.baseline["artifacts"].get(analysis_id).content)[
                "components"
            ]
            self.assertEqual(len(components), 4)
            self.assertEqual(set(selectors[str(tick)]), set(ROLES))
            self.assertEqual(
                set(selectors[str(tick)].values()), {c["candidate_id"] for c in components}
            )
        self.assertNotEqual(selectors["0"][TARGETS[0]], selectors["12"][TARGETS[0]])
        document = json.loads((FIXTURE / "recovery-base.svm.json").read_text())
        self.assertEqual(document["animation"]["content"], [])
        for group in document["groups"]:
            self.assertTrue(set(group["members"]).isdisjoint(ANCHORS))
            target = next(r for r in TARGETS if r in group["members"])
            slot = next(
                b["slot"]
                for b in document["construction"]["output_bindings"]
                if b["entity"] == target
            )
            bounds = next(
                o["parameters"]["bounds"]
                for o in document["construction"]["operations"]
                if slot == o["id"] + ".geometry"
            )
            self.assertNotEqual(
                group["transform"]["origin"],
                [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2],
            )

    def assert_atomic(self, state, proposal, error=ProposalArtifactError):
        store = state["store"]
        before = (store.head, store.get_document(store.head), len(store.revisions))
        with self.assertRaises(error):
            ProposalAcceptor().accept(store, proposal, state["artifacts"])
        self.assertEqual((store.head, store.get_document(store.head), len(store.revisions)), before)

    def test_full_recovery_numerics_geometry_isolation_and_determinism(self):
        state = self.state()
        document, proposals = author_all(state)
        second = prepare()
        other, other_proposals = author_all(second)
        self.assertEqual(document, other)
        self.assertEqual(proposals, other_proposals)
        for key in ("lineages", "cameras", "consensus", "camera_id", "targets"):
            self.assertEqual(state[key], second[key])
        self.assertEqual(state["store"].head, second["store"].head)
        for tick in TICKS:
            self.assertEqual(
                MotionEvaluator(document).sample_document(tick),
                MotionEvaluator(other).sample_document(tick),
            )
        self.assertEqual(len({i["identity_id"] for i in state["lineages"].values()}), 4)
        tracks = document["animation"]["content"]
        self.assertEqual(len(tracks), 12)
        self.assertEqual(len({t["id"] for t in tracks}), 12)
        for group in GROUPS:
            selected = [t for t in tracks if t["target"].get("group") == group]
            self.assertEqual(
                {t["target"]["property"] for t in selected},
                {"translate.x", "translate.y", "rotation_degrees", "scale"},
            )
            self.assertEqual(len(selected), 4)
        camera = [t for t in tracks if "camera" in t["target"]]
        self.assertEqual(
            {t["target"]["property"] for t in camera},
            {"position.x", "position.y", "rotation_degrees", "scale"},
        )
        errors, geometry = measure(document, state["artifacts"], state["lineages"])
        print("S11C maximum errors:", errors, "geometry:", geometry)
        for role, values in errors.items():
            for key, limit in {
                "position": 1.0,
                "rotation": 0.2,
                "scale": 0.003 if role == "camera" else 0.005,
            }.items():
                self.assertLessEqual(values[key], limit, (role, key, values[key]))
        for role, error in geometry.items():
            self.assertLessEqual(error, 2.0, role)

    def test_cross_wired_compensation_and_bindings_reject(self):
        state = self.state()
        store, artifacts = state["store"], state["artifacts"]
        a, b = (state["lineages"][r] for r in TARGETS)
        before = (store.head, store.get_document(store.head))
        with self.assertRaisesRegex(ValueError, "identity"):
            CameraCompensatedMotionAdapter().propose(
                request(
                    store,
                    [state["camera_id"], a["translation_id"], b["similarity_id"]],
                    {
                        "anchor_entity_ids": list(ANCHORS),
                        "target_temporal_identity_id": a["identity_id"],
                    },
                ),
                artifacts,
            )
        for left, right in (TARGETS, TARGETS[::-1]):
            for adapter in (
                GeometryTranslationTracksAdapter(),
                ObservedRotationTracksAdapter(),
                ObservedScaleTracksAdapter(),
            ):
                with (
                    self.subTest(left=left, adapter=type(adapter).__name__),
                    self.assertRaisesRegex(ValueError, "identity"),
                ):
                    adapter.propose(
                        request(
                            store,
                            [state["targets"][left]["evidence_id"]],
                            {
                                "motion_target_binding_id": state["targets"][right]["binding_id"],
                                "ticks_per_second": 12,
                            },
                        ),
                        artifacts,
                    )
        self.assertEqual((store.head, store.get_document(store.head)), before)

    def test_provenance_shared_camera_hold_and_legacy_displacement(self):
        state = self.state()
        document, _ = author_all(state)
        artifacts, lineages = state["artifacts"], state["lineages"]
        refs = {r["id"]: r for r in document["references"]}
        consensus = payload(artifacts, state["consensus"])
        self.assertEqual(consensus["intervals"][1]["relative_view_transform"], [1, 0, 0, 1, 0, 0])
        self.assertEqual(
            consensus["intervals"][1]["source_view_transform"],
            consensus["intervals"][1]["target_view_transform"],
        )
        self.assertEqual(
            len([r for r in refs.values() if "camera-consensus+json" in r["media_type"]]), 1
        )
        all_occurrences = {}
        for role in ROLES:
            item = lineages[role]
            all_occurrences[role] = set()
            for gid, rid in zip(item["geometry_ids"], item["correspondence_ids"], strict=True):
                geometry = artifacts.resolve_reference(refs[gid])
                frames = json.loads(geometry.content)["frames"]
                for frame, occurrence in zip(
                    frames, geometry.provenance["source_occurrences"], strict=True
                ):
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
                    all_occurrences[role].add(frame["primitives"][0]["observation_id"])
                candidate = json.loads(artifacts.get(rid).content)["candidates"][0]
                centers = [
                    [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
                    for b in (f["primitives"][0]["bounds"] for f in frames)
                ]
                self.assertEqual(
                    candidate["displacement"], [centers[1][i] - centers[0][i] for i in range(2)]
                )
            similarity = json.loads(artifacts.get(item["similarity_id"]).content)
            self.assertEqual(similarity["temporal_identity_id"], item["identity_id"])
            self.assertEqual(
                {i["source_geometry_artifact_id"] for i in similarity["intervals"]},
                set(item["geometry_ids"]),
            )
            self.assertEqual(
                {i["correspondence_evidence_artifact_id"] for i in similarity["intervals"]},
                set(item["correspondence_ids"]),
            )
            for interval in similarity["intervals"]:
                self.assertEqual(
                    interval["similarity_observation_policy_identity"],
                    "svm-controlled-raster-similarity-policy@0.1",
                )
        for i, role in enumerate(ROLES):
            for other in ROLES[i + 1 :]:
                self.assertTrue(all_occurrences[role].isdisjoint(all_occurrences[other]))
        for role, camera_id in zip(ANCHORS, state["cameras"], strict=True):
            camera = json.loads(artifacts.get(camera_id).content)
            self.assertEqual(
                lineages[role]["similarity_id"], camera["source_similarity_artifact_id"]
            )
            self.assertIn(camera_id, consensus["source_camera_evidence_artifact_ids"])
            hold = json.loads(artifacts.get(lineages[role]["geometry_ids"][1]).content)["frames"]
            self.assertEqual(
                hold[0]["primitives"][0]["geometry"], hold[1]["primitives"][0]["geometry"]
            )
        self.assertNotEqual(
            state["targets"][TARGETS[0]]["evidence_id"], state["targets"][TARGETS[1]]["evidence_id"]
        )
        self.assertNotEqual(
            state["targets"][TARGETS[0]]["binding_id"], state["targets"][TARGETS[1]]["binding_id"]
        )
        evaluator = MotionEvaluator(document)
        for role, group in zip(TARGETS, GROUPS, strict=True):
            item, target = lineages[role], state["targets"][role]
            for ref in target["compensation"].preview_artifacts:
                snapshot = artifacts.get(ref.artifact_id)
                data = json.loads(snapshot.content)
                self.assertEqual(
                    set(data["source_artifact_ids"]),
                    {state["camera_id"], item["translation_id"], item["similarity_id"]},
                )
                self.assertEqual(
                    snapshot.provenance["source_artifact_ids"], data["source_artifact_ids"]
                )
                self.assertEqual(data["temporal_identity_id"], item["identity_id"])
            for track in document["animation"]["content"]:
                if track["target"].get("group") == group:
                    self.assertEqual(
                        track["provenance"]["motion_target_binding_id"], target["binding_id"]
                    )
                    self.assertEqual(
                        track["provenance"]["evidence_artifact_id"], target["evidence_id"]
                    )
                elif "camera" in track["target"]:
                    self.assertEqual(
                        track["provenance"]["evidence_artifact_id"], state["camera_id"]
                    )
            transforms = [
                next(
                    g["transform"]
                    for g in evaluator.sample_document(t)["groups"]
                    if g["id"] == group
                )
                for t in (12, 24)
            ]
            self.assertNotEqual(transforms[0]["translate"], transforms[1]["translate"])
            self.assertNotEqual(
                transforms[0]["rotation_degrees"], transforms[1]["rotation_degrees"]
            )
            legacy = json.loads(artifacts.get(item["correspondence_ids"][0]).content)["candidates"][
                0
            ]["displacement"]
            self.assertGreater(math.dist(legacy, transforms[0]["translate"]), 5)
        self.assertEqual(
            evaluator.sample_document(12)["presentation"]["camera"],
            evaluator.sample_document(24)["presentation"]["camera"],
        )

    def test_moving_anchor_and_disagreement_remain_closed(self):
        from svm.revisions import AddKeyframeChange, CreateGroupTransformTrackChange, Transaction

        state = self.state()
        document = state["store"].get_document(state["store"].head)
        document["groups"][0]["members"].append(ANCHORS[1])
        document["groups"][0]["members"].sort()
        store = RevisionStore.create(document)
        store.commit(
            store.head,
            Transaction(
                "transaction:moving-anchor",
                (
                    CreateGroupTransformTrackChange(
                        "track:moving-anchor", GROUPS[0], "translate.x", 12
                    ),
                    AddKeyframeChange("track:moving-anchor", "keyframe:anchor-zero", 0, 0),
                    AddKeyframeChange("track:moving-anchor", "keyframe:anchor-moving", 12, 10),
                ),
            ),
        )
        before = (store.head, store.get_document(store.head))
        with self.assertRaisesRegex(ValueError, "not static"):
            ObservedCameraSimilarityAdapter().propose(
                request(
                    store,
                    [state["lineages"][ANCHORS[1]]["similarity_id"]],
                    {"anchor_entity_id": ANCHORS[1]},
                ),
                state["artifacts"],
            )
        self.assertEqual((store.head, store.get_document(store.head)), before)
        with self.assertRaisesRegex(ValueError, "disagree"):
            prepare(disagreement=True)

    def test_forged_compensated_identity_is_atomic(self):
        state = self.state()
        store, artifacts = state["store"], state["artifacts"]
        a = state["lineages"][TARGETS[0]]
        p = CameraCompensatedMotionAdapter().propose(
            request(
                store,
                [state["camera_id"], a["translation_id"], a["similarity_id"]],
                {
                    "anchor_entity_ids": list(ANCHORS),
                    "target_temporal_identity_id": a["identity_id"],
                },
            ),
            artifacts,
        )
        for index in (0, 1):
            original = artifacts.get(p.preview_artifacts[index].artifact_id)
            data = json.loads(original.content)
            data["temporal_identity_id"] = state["lineages"][TARGETS[1]]["identity_id"]
            forged = artifacts.import_bytes(
                canonical_bytes(data),
                media_type=original.media_type,
                kind=original.kind,
                provenance=original.provenance,
            )
            refs = list(p.transaction.changes[0].evidence_references)
            refs[index] = forged.document_reference()
            invalid = replace(
                p,
                transaction=replace(
                    p.transaction,
                    changes=(replace(p.transaction.changes[0], evidence_references=tuple(refs)),),
                ),
                required_artifact_ids=tuple(
                    forged.artifact_id if x == original.artifact_id else x
                    for x in p.required_artifact_ids
                ),
            )
            self.assert_atomic(state, invalid)

    def test_one_tick_selector_swap_fails_closed(self):
        with self.assertRaises(ValueError):
            prepare(swap=True)

    def test_cross_target_track_collision_is_atomic(self):
        state = self.state()
        author_target(state, TARGETS[1])
        store, artifacts = state["store"], state["artifacts"]
        b_track = next(
            t["id"]
            for t in store.get_document(store.head)["animation"]["content"]
            if t["target"]["property"] == "translate.x"
        )
        a = state["targets"][TARGETS[0]]
        p = GeometryTranslationTracksAdapter().propose(
            request(
                store,
                [a["evidence_id"]],
                {"motion_target_binding_id": a["binding_id"], "ticks_per_second": 12},
            ),
            artifacts,
        )
        changes = list(p.transaction.changes)
        changes[0] = replace(changes[0], track_id=b_track)
        self.assert_atomic(
            state,
            replace(p, transaction=replace(p.transaction, changes=tuple(changes))),
            DocumentError,
        )

    def test_cross_target_occurrence_and_source_png_forgery_is_atomic(self):
        for role in TARGETS:
            state = self.state()
            store, artifacts = state["store"], state["artifacts"]
            selectors = json.loads((FIXTURE / "selectors.json").read_text())
            p = RasterGeometryObservationAdapter().propose(
                observation_request(
                    store,
                    *state["analyses"][:2],
                    selectors=tuple(selectors[str(t)][role] for t in TICKS[:2]),
                ),
                artifacts,
            )
            original = artifacts.get(p.preview_artifacts[0].artifact_id)
            provenance = copy.deepcopy(original.provenance)
            if role == TARGETS[0]:
                other = artifacts.get(state["lineages"][TARGETS[1]]["geometry_ids"][0])
                provenance["source_occurrences"][0] = copy.deepcopy(
                    other.provenance["source_occurrences"][0]
                )
            else:
                other = artifacts.get(state["lineages"][role]["geometry_ids"][2])
                provenance["source_occurrences"][0]["source_png_artifact_id"] = other.provenance[
                    "source_occurrences"
                ][1]["source_png_artifact_id"]
            forged = artifacts.import_bytes(
                original.content,
                media_type=original.media_type,
                kind=original.kind,
                provenance=provenance,
            )
            change = replace(
                p.transaction.changes[0], observation_reference=forged.document_reference()
            )
            invalid = replace(
                p,
                transaction=replace(p.transaction, changes=(change,)),
                required_artifact_ids=tuple(dict.fromkeys(ref["id"] for ref in change.references)),
            )
            self.assert_atomic(state, invalid)
