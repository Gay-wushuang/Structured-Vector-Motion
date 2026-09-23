from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path

from test_repeated_frame_occurrences import ANCHOR, GROUP, TARGET, TICKS, sequence_documents
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
    MultiAnchorCameraConsensusAdapter,
    ObservedCameraSimilarityAdapter,
    ObservedCameraTracksAdapter,
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    SVGGeometryOccurrenceAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.camera_compensation import CameraCompensationError
from svm.adapters.camera_consensus import MEDIA_TYPE
from svm.adapters.svg_geometry_observations import (
    OCCURRENCE_POLICY_IDENTITY,
    derive_svg_polygon_observations,
)
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.revisions import (
    AddKeyframeChange,
    AppendReferencesChange,
    AttachCameraCompensationEvidenceChange,
    CreateStyleTrackChange,
    SetGroupTransformChange,
    Transaction,
)

ANCHOR_B = "entity:camera-anchor-b"
ANCHORS = (ANCHOR, ANCHOR_B)
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/033-multi-anchor-camera-consensus"


def documents():
    base, truth = sequence_documents(camera=True)
    for document, name in ((base, "recovery-base"), (truth, "ground-truth")):
        document["document_id"] = "document:multi-anchor-" + name
        document["entities"].append({"id": ANCHOR_B, "name": "Independent Anchor B"})
        document["construction"]["operations"].append(
            {
                "id": "op:camera-anchor-b",
                "type": "CreatePath",
                "inputs": {},
                "parameters": {
                    "d": "M 145 80 L 180 82 L 174 104 L 152 111 L 149 95 Z",
                    "bounds": [145, 80, 180, 111],
                },
            }
        )
        document["construction"]["output_bindings"].append(
            {"entity": ANCHOR_B, "property": "geometry", "slot": "op:camera-anchor-b.geometry"}
        )
        document["presentation"]["render_stack"].append(ANCHOR_B)
        document["presentation"]["styles"].append(
            {
                "entity": ANCHOR_B,
                "fill": "#3344AA",
                "stroke": "none",
                "stroke_width": 0,
                "opacity": 1,
            }
        )
    return base, truth


def frozen_frames(artifacts, truth):
    evaluator = MotionEvaluator(truth)
    renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
    return [
        artifacts.import_bytes(
            renderer.render(evaluator.evaluate(t).scene).encode(), media_type="image/svg+xml"
        )
        for t in TICKS
    ]


def hypotheses(*, disagreement=False, ticks_b=TICKS):
    base = json.loads((FIXTURE / "recovery-base.svm.json").read_text())
    truth = json.loads((FIXTURE / "ground-truth.svm.json").read_text())
    store, artifacts = RevisionStore.create(base), ArtifactStore()
    frames = [
        artifacts.import_bytes(
            (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_bytes(),
            media_type="image/svg+xml",
        )
        for tick in TICKS
    ]
    camera_ids = []
    for anchor in ANCHORS:
        selected_frames = frames
        if disagreement and anchor == ANCHOR_B:
            altered = copy.deepcopy(truth)
            for track in altered["animation"]["content"]:
                if track["target"] == {"camera": "presentation", "property": "rotation_degrees"}:
                    for keyframe in track["keyframes"][2:]:
                        keyframe["value"] = 6
            selected_frames = frozen_frames(artifacts, altered)
        lineage = observe_lineage(
            store,
            artifacts,
            selected_frames,
            anchor,
            observation_adapter=SVGGeometryOccurrenceAdapter(),
            ticks=ticks_b if anchor == ANCHOR_B else TICKS,
        )
        proposal = ObservedCameraSimilarityAdapter().propose(
            request(
                store,
                artifact_ids=(lineage["similarity_id"],),
                options={"anchor_entity_id": anchor},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        camera_ids.append(proposal.preview_artifacts[0].artifact_id)
    return store, artifacts, tuple(camera_ids), frames, truth


def propose_consensus(store, artifacts, ids, anchors=ANCHORS):
    return MultiAnchorCameraConsensusAdapter().propose(
        request(store, artifact_ids=ids, options={"anchor_entity_ids": list(anchors)}), artifacts
    )


def recover(state, *, reverse=False, verify_compensation=None):
    store, artifacts, ids, frames, _ = state
    consensus = propose_consensus(
        store, artifacts, ids[::-1] if reverse else ids, ANCHORS[::-1] if reverse else ANCHORS
    )
    ProposalAcceptor().accept(store, consensus, artifacts)
    camera_id = consensus.preview_artifacts[0].artifact_id
    target = observe_lineage(
        store, artifacts, frames, TARGET, observation_adapter=SVGGeometryOccurrenceAdapter()
    )
    compensation = CameraCompensatedMotionAdapter().propose(
        request(
            store,
            artifact_ids=(camera_id, target["translation_id"], target["similarity_id"]),
            options={
                "anchor_entity_ids": list(ANCHORS),
                "target_temporal_identity_id": target["identity_id"],
            },
        ),
        artifacts,
    )
    if verify_compensation is not None:
        verify_compensation(compensation)
    ProposalAcceptor().accept(store, compensation, artifacts)
    similarity_id = compensation.preview_artifacts[1].artifact_id
    binding = TemporalMotionTargetBindingAdapter().propose(
        request(store, options={"temporal_identity_id": target["identity_id"], "group_id": GROUP}),
        artifacts,
    )
    ProposalAcceptor().accept(store, binding, artifacts)
    binding_id = binding.preview.motion_target_bindings[0].binding_id
    for adapter in (
        GeometryTranslationTracksAdapter(),
        ObservedRotationTracksAdapter(),
        ObservedScaleTracksAdapter(),
    ):
        proposal = adapter.propose(
            request(
                store,
                artifact_ids=(similarity_id,),
                options={"motion_target_binding_id": binding_id, "ticks_per_second": 12},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
    tracks = ObservedCameraTracksAdapter().propose(
        request(
            store,
            artifact_ids=(camera_id,),
            options={"camera_target": "presentation", "ticks_per_second": 12},
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, tracks, artifacts)
    return consensus, tracks


class CameraConsensusTest(unittest.TestCase):
    def assert_atomic_rejection(self, store, artifacts, proposal, error=ProposalArtifactError):
        head, before, count = store.head, store.get_document(store.head), len(store.revisions)
        with self.assertRaises(error):
            ProposalAcceptor().accept(store, proposal, artifacts)
        self.assertEqual(
            (store.head, store.get_document(store.head), len(store.revisions)),
            (head, before, count),
        )

    def test_consensus_compensation_cannot_use_single_anchor_change(self):
        state = hypotheses()
        store, artifacts, _, _, _ = state

        def check(proposal):
            change = proposal.transaction.changes[0]
            singular = AttachCameraCompensationEvidenceChange(
                change.evidence_references,
                change.source_references,
                change.anchor_entities[0],
                change.animation_before,
                change.source_revision_id,
            )
            forged = replace(
                proposal, transaction=replace(proposal.transaction, changes=(singular,))
            )
            self.assert_atomic_rejection(store, artifacts, forged)

        recover(state, verify_compensation=check)

    def test_fixture_matches_executable_documents(self):
        for name, document in zip(("recovery-base", "ground-truth"), documents(), strict=True):
            self.assertEqual(json.loads((FIXTURE / (name + ".svm.json")).read_text()), document)
        for tick, frame in zip(TICKS, frozen_frames(ArtifactStore(), documents()[1]), strict=True):
            self.assertEqual(
                (FIXTURE / "observations" / f"tick_{tick:03d}.svg").read_bytes(), frame.content
            )

    def test_full_recovery_and_reversed_order(self):
        results = []
        max_numeric = max_geometry = 0.0
        for reverse in (False, True):
            state = hypotheses()
            store, artifacts, ids, frames, truth = state
            self.assertNotEqual(*ids)
            self.assertEqual(frames[0].artifact_id, frames[1].artifact_id)
            consensus, tracks = recover(state, reverse=reverse)
            snapshot = artifacts.get(consensus.preview_artifacts[0].artifact_id)
            payload = json.loads(snapshot.content)
            representative = json.loads(artifacts.get(ids[0]).content)
            for actual_interval, source_interval in zip(
                payload["intervals"], representative["intervals"], strict=True
            ):
                for key in (
                    "relative_view_transform",
                    "source_view_transform",
                    "target_view_transform",
                ):
                    self.assertEqual(actual_interval[key], source_interval[key])
            self.assertEqual(payload["anchor_entity_ids"], list(ANCHORS))
            self.assertEqual(payload["source_camera_evidence_artifact_ids"], list(ids))
            self.assertEqual(payload["intervals"][0]["relative_view_transform"], [1, 0, 0, 1, 0, 0])
            final = store.get_document(store.head)
            actual, expected = MotionEvaluator(final), MotionEvaluator(truth)
            renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 200, 120)))
            for tick, frozen in zip(TICKS, frames, strict=True):
                a, b = actual.sample_document(tick), expected.sample_document(tick)
                for kind in ("group", "camera"):
                    left = (
                        a["groups"][0]["transform"]
                        if kind == "group"
                        else a["presentation"]["camera"]
                    )
                    right = (
                        b["groups"][0]["transform"]
                        if kind == "group"
                        else b["presentation"]["camera"]
                    )
                    prop = "translate" if kind == "group" else "position"
                    for x, y in zip(
                        (*left[prop], left["rotation_degrees"], left["scale"]),
                        (*right[prop], right["rotation_degrees"], right["scale"]),
                        strict=True,
                    ):
                        max_numeric = max(max_numeric, abs(x - y))
                rendered = artifacts.import_bytes(
                    renderer.render(actual.evaluate(tick).scene).encode(),
                    media_type="image/svg+xml",
                )
                for selector in (*ANCHORS, TARGET):
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
            self.assertEqual(len(final["animation"]["content"]), 8)
            for track in final["animation"]["content"]:
                if track["target"].get("camera"):
                    self.assertEqual(
                        track["provenance"]["evidence_artifact_id"], snapshot.artifact_id
                    )
            results.append((consensus, tracks, snapshot, final))
        self.assertEqual(results[0], results[1])
        self.assertLess(max_numeric, 3e-8)
        self.assertLess(max_geometry, 3e-8)
        print(f"S10C maximum numeric error={max_numeric:.12g}; geometry error={max_geometry:.12g}")

    def test_preview_does_not_author_or_attach(self):
        store, artifacts, ids, _, _ = hypotheses()
        head, before = store.head, store.get_document(store.head)
        proposal = propose_consensus(store, artifacts, ids)
        self.assertEqual(store.head, head)
        self.assertEqual(store.get_document(head), before)
        ProposalAcceptor().accept(store, proposal, artifacts)
        after = store.get_document(store.head)
        before.pop("references")
        after.pop("references")
        self.assertEqual(before, after)

    def test_reject_single_duplicate_and_wrong_anchors(self):
        store, artifacts, ids, _, _ = hypotheses()
        for evidence, anchors in (
            (ids[:1], ANCHORS[:1]),
            (ids, (ANCHOR, ANCHOR)),
            ((ids[0], ids[0]), ANCHORS),
            (ids, (ANCHOR, TARGET)),
        ):
            with self.subTest(evidence=evidence, anchors=anchors), self.assertRaises(ValueError):
                propose_consensus(store, artifacts, evidence, anchors)

    def test_disagreement_rejects_without_output(self):
        store, artifacts, ids, _, _ = hypotheses(disagreement=True)
        head = store.head
        with self.assertRaisesRegex(CameraCompensationError, "disagree"):
            propose_consensus(store, artifacts, ids)
        self.assertEqual(store.head, head)

    def test_mismatched_tick_chains_reject(self):
        store, artifacts, ids, _, _ = hypotheses(ticks_b=(0, 12, 25, 36))
        with self.assertRaisesRegex(CameraCompensationError, "chains"):
            propose_consensus(store, artifacts, ids)

    def test_two_evidence_artifacts_from_same_anchor_reject(self):
        store, artifacts, ids, _, _ = hypotheses()
        source = json.loads(artifacts.get(ids[0]).content)["source_similarity_artifact_id"]
        another = ObservedCameraSimilarityAdapter().propose(
            request(store, artifact_ids=(source,), options={"anchor_entity_id": ANCHOR}), artifacts
        )
        ProposalAcceptor().accept(store, another, artifacts)
        other_id = another.preview_artifacts[0].artifact_id
        self.assertNotEqual(ids[0], other_id)
        with self.assertRaisesRegex(ValueError, "distinct selected anchors"):
            propose_consensus(store, artifacts, (ids[0], other_id))

    def test_forged_source_camera_rederives_single_anchor_evidence(self):
        store, artifacts, ids, _, _ = hypotheses()
        original = artifacts.get(ids[0])
        payload = json.loads(original.content)
        payload["intervals"][1]["relative_view_transform"][4] += 0.1
        forged = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        # Trusted fixture injection models a corrupted accepted reference; the producer
        # must still rederive the hypothesis from its accepted S4 and geometry lineage.
        store.commit(
            store.head,
            Transaction(
                "transaction:inject-corrupted-camera",
                (AppendReferencesChange((forged.document_reference(),)),),
            ),
        )
        with self.assertRaisesRegex(ValueError, "static-anchor observations"):
            propose_consensus(store, artifacts, (forged.artifact_id, ids[1]))

    def test_forged_consensus_fields_reject_atomically(self):
        store, artifacts, ids, _, _ = hypotheses()
        proposal = propose_consensus(store, artifacts, ids)
        change = proposal.transaction.changes[0]
        original = artifacts.get(proposal.preview_artifacts[0].artifact_id)
        mutations = (
            lambda p: p["anchor_entity_ids"].__setitem__(1, TARGET),
            lambda p: p["source_camera_evidence_artifact_ids"].reverse(),
            lambda p: p["intervals"][1]["target_view_transform"].__setitem__(4, 42),
            lambda p: p["intervals"][0].update(interval_id="forged"),
            lambda p: p.update(policy_identity="forged"),
            lambda p: p.update(agreement_absolute_tolerance=0.5),
            lambda p: p.update(representative=p["supporting_hypotheses"][1]),
        )
        for mutate in mutations:
            payload = json.loads(original.content)
            mutate(payload)
            forged = artifacts.import_bytes(
                canonical_bytes(payload),
                media_type=MEDIA_TYPE,
                kind=original.kind,
                provenance=original.provenance,
            )
            wrong = replace(change, evidence_references=(forged.document_reference(),))
            pending = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(wrong,)),
                required_artifact_ids=tuple(
                    forged.artifact_id if i == original.artifact_id else i
                    for i in proposal.required_artifact_ids
                ),
            )
            self.assert_atomic_rejection(store, artifacts, pending)

    def test_current_anchor_motion_and_stale_animation_reject(self):
        store, artifacts, ids, _, _ = hypotheses()
        pending = propose_consensus(store, artifacts, ids)
        animate = (
            CreateStyleTrackChange("track:anchor-opacity", ANCHOR_B, "opacity", 12, "linear"),
            AddKeyframeChange("track:anchor-opacity", "keyframe:anchor-opacity", 0, 1),
        )
        injected = replace(
            pending,
            transaction=replace(
                pending.transaction, changes=(*animate, *pending.transaction.changes)
            ),
        )
        self.assert_atomic_rejection(store, artifacts, injected, ValueError)
        store.commit(
            store.head,
            Transaction(
                "transaction:animate-anchor",
                (
                    CreateStyleTrackChange(
                        "track:anchor-opacity", ANCHOR_B, "opacity", 12, "linear"
                    ),
                    AddKeyframeChange("track:anchor-opacity", "keyframe:anchor-opacity", 0, 1),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "not static"):
            propose_consensus(store, artifacts, ids)
        self.assert_atomic_rejection(store, artifacts, pending, ProposalConflictError)
        # Updating a forged proposal's base and snapshots cannot bypass static checks.
        change = pending.transaction.changes[0]
        current = store.get_document(store.head)
        rebased = replace(
            change, source_revision_id=store.head, animation_before=current["animation"]
        )
        wrong = replace(
            pending,
            base_revision_id=store.head,
            transaction=replace(pending.transaction, changes=(rebased,)),
        )
        self.assert_atomic_rejection(store, artifacts, wrong)

    def test_stale_camera_track_proposal_and_forged_track_are_atomic(self):
        store, artifacts, ids, _, _ = hypotheses()
        consensus = propose_consensus(store, artifacts, ids)
        ProposalAcceptor().accept(store, consensus, artifacts)
        pending = ObservedCameraTracksAdapter().propose(
            request(
                store,
                artifact_ids=(consensus.preview_artifacts[0].artifact_id,),
                options={"camera_target": "presentation", "ticks_per_second": 12},
            ),
            artifacts,
        )
        change = pending.transaction.changes[-1]
        authored = copy.deepcopy(change.authored_tracks)
        authored[0]["keyframes"][1]["value"] = 999
        forged = replace(
            pending,
            transaction=replace(
                pending.transaction,
                changes=(
                    *pending.transaction.changes[:-1],
                    replace(change, authored_tracks=authored),
                ),
            ),
        )
        self.assert_atomic_rejection(store, artifacts, forged)
        injected = replace(
            pending,
            transaction=replace(
                pending.transaction,
                changes=(
                    CreateStyleTrackChange(
                        "track:anchor-opacity", ANCHOR_B, "opacity", 12, "linear"
                    ),
                    AddKeyframeChange("track:anchor-opacity", "keyframe:anchor-opacity", 0, 1),
                    *pending.transaction.changes,
                ),
            ),
        )
        self.assert_atomic_rejection(store, artifacts, injected, ValueError)
        transform = copy.deepcopy(store.get_document(store.head)["groups"][0]["transform"])
        transform["translate"] = [1, 0]
        store.commit(
            store.head,
            Transaction(
                "transaction:stale-authoring", (SetGroupTransformChange(GROUP, transform),)
            ),
        )
        self.assert_atomic_rejection(store, artifacts, pending, ProposalConflictError)


if __name__ == "__main__":
    unittest.main()
