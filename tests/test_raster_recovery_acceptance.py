import copy
import io
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
    RevisionStore,
)
from svm.adapters import (
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    ObservedSimilarityMotionAdapter,
    ObservedTranslationMotionAdapter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from svm.adapters.geometry_translation_tracks import GeometryTranslationTracksAdapter
from svm.adapters.observed_similarity_motion import RasterObservedSimilarityMotionAdapter
from svm.adapters.opencv_analysis import OpenCVAnalysisAdapter
from svm.adapters.raster_geometry_observations import RasterGeometryObservationAdapter
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer

FIXTURE = Path(__file__).resolve().parents[1] / "examples/035-controlled-raster-recovery"
GROUP = "group:" + "1" * 64
TRANSLATION_TOLERANCE = 1.0
ROTATION_TOLERANCE = 0.5
SCALE_TOLERANCE = 0.01
GEOMETRY_TOLERANCE = 1.5


def request(store, ids=(), options=None):
    return AdapterRequest.from_store(
        store, store.head, ("document",), artifact_ids=tuple(ids), options=options or {}
    )


def initial():
    return RevisionStore.create(
        json.loads((FIXTURE / "recovery-base.svm.json").read_text())
    ), ArtifactStore()


def accept(store, artifacts, adapter, ids=(), options=None):
    proposal = adapter.propose(request(store, ids, options), artifacts)
    ProposalAcceptor().accept(store, proposal, artifacts)
    return proposal


def analyze(store, artifacts, name=None, content=None):
    blob = artifacts.import_bytes(
        content if content is not None else (FIXTURE / f"{name}.png").read_bytes(),
        media_type="image/png",
    )
    proposal = accept(store, artifacts, OpenCVAnalysisAdapter(), [blob.artifact_id])
    return blob, proposal.preview_artifacts[1].artifact_id


def observation_request(store, left, right, ticks=(0, 12), selectors=None):
    return request(
        store,
        sorted({left, right}),
        {
            "occurrences": [
                {"analysis_artifact_id": aid, "tick": tick, "component_id": selector}
                for aid, tick, selector in zip(
                    (left, right),
                    ticks,
                    selectors or ("candidate:component-0001",) * 2,
                    strict=True,
                )
            ]
        },
    )


def payload(artifacts, proposal):
    return json.loads(artifacts.get(proposal.preview_artifacts[0].artifact_id).content)


def promote_geometry(store, artifacts, gid):
    r0 = accept(store, artifacts, TemporalCorrespondenceAdapter(), [gid])
    candidate = payload(artifacts, r0)["candidates"][0]
    rid = r0.preview_artifacts[0].artifact_id
    identity = accept(
        store,
        artifacts,
        TemporalIdentityPromotionAdapter(),
        [rid],
        {"inference_ids": [candidate["inference_id"]]},
    )
    return request(
        store,
        [gid, rid],
        {
            "temporal_identity_id": identity.preview.temporal_identities[0].stable_identity_id,
            "inference_ids": [candidate["inference_id"]],
        },
    )


def recover(names, author=False):
    """Only PNGs, ticks, recovery Document, explicit selection/binding enter inference."""
    store, artifacts = initial()
    analyses = [analyze(store, artifacts, name)[1] for name in names]
    gids, rids, inference_ids = [], [], []
    for i in range(len(names) - 1):
        proposal = RasterGeometryObservationAdapter().propose(
            observation_request(store, analyses[i], analyses[i + 1], (i * 12, (i + 1) * 12)),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        gid = proposal.preview_artifacts[0].artifact_id
        gids.append(gid)
        r0 = accept(store, artifacts, TemporalCorrespondenceAdapter(), [gid])
        rid = r0.preview_artifacts[0].artifact_id
        rids.append(rid)
        candidate = payload(artifacts, r0)["candidates"][0]
        if candidate["status"] != "SUPPORTED":
            raise AssertionError(candidate)
        inference_ids.append(candidate["inference_id"])
        identity = accept(
            store,
            artifacts,
            TemporalIdentityPromotionAdapter(),
            [rid],
            {"inference_ids": [candidate["inference_id"]]},
        )
        identity_id = identity.preview.temporal_identities[0].stable_identity_id
    options = {"temporal_identity_id": identity_id, "inference_ids": inference_ids}
    s0 = accept(store, artifacts, ObservedTranslationMotionAdapter(), rids, options)
    exact = ObservedSimilarityMotionAdapter().propose(
        request(store, (*gids, *rids), options), artifacts
    )
    s4 = accept(store, artifacts, RasterObservedSimilarityMotionAdapter(), (*gids, *rids), options)
    if author:
        binding = accept(
            store,
            artifacts,
            TemporalMotionTargetBindingAdapter(),
            options={"temporal_identity_id": identity_id, "group_id": GROUP},
        )
        binding_id = binding.preview.motion_target_bindings[0].binding_id
        for adapter in (
            GeometryTranslationTracksAdapter(),
            ObservedRotationTracksAdapter(),
            ObservedScaleTracksAdapter(),
        ):
            before = store.head
            proposal = adapter.propose(
                request(
                    store,
                    [s4.preview_artifacts[0].artifact_id],
                    {"motion_target_binding_id": binding_id, "ticks_per_second": 12},
                ),
                artifacts,
            )
            if store.head != before:
                raise AssertionError("Preview mutated revision")
            ProposalAcceptor().accept(store, proposal, artifacts)
    return store, artifacts, gids, rids, s0, s4, exact


def sample_errors(document, names):
    # Ground truth is read AFTER inference and Track authoring finish.
    truth = json.loads((FIXTURE / "ground-truth.json").read_text())
    errors = [0.0] * 4
    evaluator = MotionEvaluator(document)
    for i, name in enumerate(names):
        sampled = evaluator.sample_document(i * 12)["groups"][0]["transform"]
        expected = truth[name]
        scene = evaluator.evaluate(i * 12).scene
        entity = next(item for item in scene.entities if item.entity_id == "entity:recovery-target")
        a, b, c, d, e, f = entity.geometry["matrix"]
        actual = [[a * x + c * y + e, b * x + d * y + f] for x, y in truth["base"]["points"]]
        current = [
            math.dist(sampled["translate"], expected["translate"]),
            abs(sampled["rotation_degrees"] - expected["rotation_degrees"]),
            abs(sampled["scale"] - expected["scale"]),
            max(math.dist(p, q) for p, q in zip(actual, expected["points"], strict=True)),
        ]
        errors = [max(x, y) for x, y in zip(errors, current, strict=True)]
    return errors


class RasterRecoveryAcceptanceTest(unittest.TestCase):
    def test_vector_frontend_cannot_select_raster_policy(self):
        from svm.adapters.svg_geometry_observations import SVGGeometryOccurrenceAdapter

        store, artifacts = initial()
        svg = artifacts.import_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            b'<path id="shape" fill="#000000" d="M 10 10 L 60 12 L 45 60 L 20 40 Z"/></svg>',
            media_type="image/svg+xml",
        )
        p = accept(
            store,
            artifacts,
            SVGGeometryOccurrenceAdapter(),
            [svg.artifact_id],
            {
                "source_svg_artifact_id": svg.artifact_id,
                "target_svg_artifact_id": svg.artifact_id,
                "source_tick": 0,
                "target_tick": 12,
                "shape_id": "shape",
            },
        )
        req = promote_geometry(store, artifacts, p.preview_artifacts[0].artifact_id)
        before = store.head
        with self.assertRaises(ValueError):
            RasterObservedSimilarityMotionAdapter().propose(req, artifacts)
        self.assertEqual(store.head, before)
        exact = ObservedSimilarityMotionAdapter().propose(req, artifacts)
        self.assertEqual(
            payload(artifacts, exact)["policy_identity"],
            "svm-geometry-similarity-observation-policy@0.1",
        )
        self.assertEqual(payload(artifacts, exact)["intervals"][0]["status"], "SUPPORTED")
        ProposalAcceptor().accept(store, exact, artifacts)

    def test_forged_analysis_mask_and_png_references_reject_atomically(self):
        from PIL import Image

        store, artifacts = initial()
        _, left = analyze(store, artifacts, "base")
        _, right = analyze(store, artifacts, "rotation")
        proposal = RasterGeometryObservationAdapter().propose(
            observation_request(store, left, right), artifacts
        )
        original = proposal.transaction.changes[0]
        before, document = store.head, store.get_document(store.head)
        for mutation in ("analysis", "mask", "png"):
            change = original
            refs = {ref["id"]: ref for ref in change.source_references}
            source = artifacts.resolve_reference(refs[left])
            data = json.loads(source.content)
            if mutation == "analysis":
                data["components"][0]["centroid"][0] += 1
            else:
                key = "binary_mask_artifact_id" if mutation == "mask" else "source_artifact_id"
                old = artifacts.resolve_reference(refs[data[key]])
                image = Image.open(io.BytesIO(old.content)).copy()
                image.putpixel((0, 0), 128)
                output = io.BytesIO()
                image.save(output, format="PNG")
                forged = artifacts.import_bytes(
                    output.getvalue(),
                    media_type=old.media_type,
                    kind=old.kind,
                    provenance=old.provenance,
                )
                refs.pop(old.artifact_id)
                refs[forged.artifact_id] = forged.document_reference()
                data[key] = forged.artifact_id
                if mutation == "png":
                    data["source_content_hash"] = forged.content_hash
            forged_analysis = artifacts.import_bytes(
                canonical_bytes(data),
                media_type=source.media_type,
                kind=source.kind,
                provenance=source.provenance,
            )
            refs.pop(left)
            refs[forged_analysis.artifact_id] = forged_analysis.document_reference()
            occurrences = copy.deepcopy(change.occurrences)
            occurrences[0]["analysis_artifact_id"] = forged_analysis.artifact_id
            change = replace(
                change, source_references=tuple(refs.values()), occurrences=occurrences
            )
            invalid = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(change,)),
                required_artifact_ids=tuple(ref["id"] for ref in change.references),
            )
            with self.subTest(mutation=mutation), self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(store, invalid, artifacts)
            self.assertEqual(store.head, before)
            self.assertEqual(store.get_document(store.head), document)

    def test_similarity_policy_provenance_and_pixel_closure_tampering(self):
        from svm.revisions import AttachObservedSimilarityEvidenceChange

        store, artifacts, _, _, _, accepted, _ = recover(["base", "rotation"])
        original = accepted.transaction.changes[0]
        req = request(
            store,
            [
                ref["id"]
                for ref in (*original.geometry_references, *original.correspondence_references)
            ],
            {
                "temporal_identity_id": original.temporal_identity["id"],
                "inference_ids": list(original.inference_ids),
            },
        )
        proposal = RasterObservedSimilarityMotionAdapter().propose(req, artifacts)
        change = proposal.transaction.changes[0]
        snapshot = artifacts.resolve_reference(change.evidence_reference)
        before, document = store.head, store.get_document(store.head)
        for mutation in ("policy", "provenance", "missing_closure", "legacy_change"):
            modified = change
            if mutation in {"policy", "provenance"}:
                content = json.loads(snapshot.content)
                provenance = copy.deepcopy(snapshot.provenance)
                if mutation == "policy":
                    content["policy_identity"] = "svm-geometry-similarity-observation-policy@0.1"
                else:
                    provenance["adapter_version"] = "forged"
                fake = artifacts.import_bytes(
                    canonical_bytes(content),
                    media_type=snapshot.media_type,
                    kind=snapshot.kind,
                    provenance=provenance,
                )
                modified = replace(change, evidence_reference=fake.document_reference())
            elif mutation == "missing_closure":
                modified = replace(change, raster_source_references=())
            else:
                modified = AttachObservedSimilarityEvidenceChange(
                    change.evidence_reference,
                    change.correspondence_references,
                    change.geometry_references,
                    change.temporal_identity,
                    change.inference_ids,
                    change.source_revision_id,
                )
            invalid = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(modified,)),
                required_artifact_ids=tuple(ref["id"] for ref in modified.references),
            )
            with self.subTest(mutation=mutation), self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(store, invalid, artifacts)
            self.assertEqual(store.head, before)
            self.assertEqual(store.get_document(store.head), document)

    def test_raster_policy_rejects_relabelled_vector_geometry(self):
        from svm.revisions import AppendReferencesChange, Transaction

        store, artifacts = initial()
        _, aid = analyze(store, artifacts, "base")
        p = RasterGeometryObservationAdapter().propose(
            observation_request(store, aid, aid), artifacts
        )
        original = artifacts.get(p.preview_artifacts[0].artifact_id)
        data = json.loads(original.content)
        # Self-consistent exact vector landmarks, with copied raster labels/provenance.
        for frame in data["frames"]:
            for point in frame["primitives"][0]["geometry"]["points"]:
                point[0] += 0.25
        fake = artifacts.import_bytes(
            canonical_bytes(data),
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        store.commit(
            store.head,
            Transaction(
                "test:untrusted-reference", (AppendReferencesChange((fake.document_reference(),)),)
            ),
        )
        req = promote_geometry(store, artifacts, fake.artifact_id)
        before = store.head
        with self.assertRaises(ValueError):
            RasterObservedSimilarityMotionAdapter().propose(req, artifacts)
        self.assertEqual(store.head, before)

    def assert_errors(self, document, names):
        for actual, limit in zip(
            sample_errors(document, names),
            (TRANSLATION_TOLERANCE, ROTATION_TOLERANCE, SCALE_TOLERANCE, GEOMETRY_TOLERANCE),
            strict=True,
        ):
            self.assertLessEqual(actual, limit)

    def test_translation_rotation_scale_and_combined(self):
        for name in ("translation", "rotation", "scale", "combined"):
            with self.subTest(name=name):
                store, artifacts, _, rids, s0, s4, exact = recover(["base", name], author=True)
                self.assert_errors(store.get_document(store.head), ["base", name])
                self.assertEqual(payload(artifacts, s4)["intervals"][0]["status"], "SUPPORTED")
                if name in {"rotation", "combined"}:
                    self.assertEqual(
                        payload(artifacts, exact)["intervals"][0]["status"], "UNCERTAIN"
                    )
                r0 = json.loads(artifacts.get(rids[0]).content)["candidates"][0]
                observed = payload(artifacts, s0)["intervals"][0]
                self.assertEqual(
                    [observed["translation"]["dx"], observed["translation"]["dy"]],
                    r0["displacement"],
                )

    def test_sequence_recovers_tracks_visible_ticks_and_determinism(self):
        names = [f"tick_{tick:03}" for tick in (0, 12, 24, 36)]
        first, second = recover(names, author=True), recover(names, author=True)
        store, artifacts, gids, rids, s0, s4, _ = first
        document = store.get_document(store.head)
        self.assertEqual(store.head, second[0].head)
        self.assertEqual(document, second[0].get_document(second[0].head))
        for reference in document["references"]:
            if reference.get("import_metadata", {}).get("fixture"):
                continue
            self.assertEqual(
                artifacts.resolve_reference(reference), second[1].resolve_reference(reference)
            )
        baseline = json.loads((FIXTURE / "recovery-base.svm.json").read_text())
        for key in ("entities", "groups", "construction", "presentation"):
            self.assertEqual(document[key], baseline[key])
        self.assertEqual(len(document["animation"]["content"]), 4)
        self.assertEqual(
            {track["target"]["property"] for track in document["animation"]["content"]},
            {"translate.x", "translate.y", "rotation_degrees", "scale"},
        )
        binding = document["motion_target_bindings"][0]
        for track in document["animation"]["content"]:
            self.assertEqual(track["target"]["group"], GROUP)
            self.assertEqual(track["provenance"]["motion_target_binding_id"], binding["id"])
            self.assertEqual(
                track["provenance"]["evidence_artifact_id"], s4.preview_artifacts[0].artifact_id
            )
            if track["target"]["property"].startswith("translate"):
                self.assertEqual(
                    track["provenance"]["authoring_identity"],
                    "svm-geometry-correct-translation-authoring@0.1",
                )
        self.assertEqual(binding["temporal_identity_id"], document["temporal_identities"][0]["id"])
        self.assertEqual(len(document["temporal_identities"]), 1)
        self.assertEqual(len(document["temporal_identities"][0]["bindings"]), 4)
        refs = {ref["id"]: ref for ref in document["references"]}
        similarity = payload(artifacts, s4)
        for interval in similarity["intervals"]:
            geometry = artifacts.resolve_reference(refs[interval["source_geometry_artifact_id"]])
            correspondence = json.loads(
                artifacts.resolve_reference(
                    refs[interval["correspondence_evidence_artifact_id"]]
                ).content
            )
            self.assertEqual(correspondence["source_artifact_id"], geometry.artifact_id)
            for occurrence in geometry.provenance["source_occurrences"]:
                source = artifacts.resolve_reference(refs[occurrence["source_png_artifact_id"]])
                analysis = json.loads(
                    artifacts.resolve_reference(refs[occurrence["analysis_artifact_id"]]).content
                )
                self.assertEqual(source.media_type, "image/png")
                self.assertEqual(analysis["source_artifact_id"], source.artifact_id)
                self.assertEqual(
                    analysis["binary_mask_artifact_id"], occurrence["mask_artifact_id"]
                )
                self.assertEqual(
                    analysis["components"][0]["component_digest"], occurrence["component_digest"]
                )
        self.assert_errors(document, names)
        evaluator = MotionEvaluator(document)
        for tick in (0, 12, 24, 36):
            self.assertEqual(
                SVGRenderer().render(evaluator.evaluate(tick).scene),
                SVGRenderer().render(evaluator.evaluate(tick).scene),
            )

    def test_same_png_distinct_occurrences_zero_motion(self):
        store, artifacts, gids, rids, _, s4, _ = recover(["base", "base"], author=True)
        frames = json.loads(artifacts.get(gids[0]).content)["frames"]
        self.assertNotEqual(
            frames[0]["primitives"][0]["observation_id"],
            frames[1]["primitives"][0]["observation_id"],
        )
        lineage = artifacts.get(gids[0]).provenance["source_occurrences"]
        self.assertEqual(lineage[0]["source_png_artifact_id"], lineage[1]["source_png_artifact_id"])
        candidate = json.loads(artifacts.get(rids[0]).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        self.assertEqual(candidate["displacement"], [0, 0])
        interval = payload(artifacts, s4)["intervals"][0]
        self.assertEqual(interval["rotation_degrees"]["value"], 0)
        self.assertEqual(interval["scale"]["value"], 1)
        primitive = frames[0]["primitives"][0]
        self.assertEqual(primitive["bounds"], [160, 150, 326, 286])
        self.assertEqual(max(point[0] for point in primitive["geometry"]["points"]), 325)
        self.assertEqual(max(point[1] for point in primitive["geometry"]["points"]), 285)
        self.assertEqual(
            MotionEvaluator(store.get_document(store.head)).sample_document(12)["groups"][0][
                "transform"
            ]["translate"],
            [0, 0],
        )

    def test_preview_and_occurrence_tampering_reject_atomically(self):
        store, artifacts = initial()
        _, left = analyze(store, artifacts, "base")
        _, right = analyze(store, artifacts, "rotation")
        before, document = store.head, store.get_document(store.head)
        proposal = RasterGeometryObservationAdapter().propose(
            observation_request(store, left, right), artifacts
        )
        self.assertEqual(store.head, before)
        change = proposal.transaction.changes[0]
        original = artifacts.get(proposal.preview_artifacts[0].artifact_id)
        for mutation in ("tick", "geometry", "source", "component", "policy"):
            content = json.loads(original.content)
            provenance = copy.deepcopy(original.provenance)
            if mutation == "tick":
                content["frames"][0]["tick"] = 1
            if mutation == "geometry":
                content["frames"][0]["primitives"][0]["geometry"]["points"][0][0] += 1
            if mutation == "source":
                provenance["source_occurrences"][0]["source_png_artifact_id"] = (
                    "artifact:" + "f" * 64
                )
            if mutation == "component":
                provenance["source_occurrences"][0]["component_id"] = "candidate:component-0002"
            if mutation == "policy":
                provenance["geometry_observation_policy"] = "unknown"
            forged = artifacts.import_bytes(
                canonical_bytes(content),
                media_type=original.media_type,
                kind=original.kind,
                provenance=provenance,
            )
            altered = replace(change, observation_reference=forged.document_reference())
            invalid = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(altered,)),
                required_artifact_ids=tuple(dict.fromkeys(ref["id"] for ref in altered.references)),
            )
            with self.subTest(mutation=mutation), self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(store, invalid, artifacts)
            self.assertEqual(store.head, before)
            self.assertEqual(store.get_document(store.head), document)
        ProposalAcceptor().accept(store, proposal, artifacts)
        after = store.get_document(store.head)
        after["references"] = document["references"]
        self.assertEqual(after, document)

    def test_invalid_images_selection_absence_and_degeneracy(self):
        from PIL import Image

        store, artifacts = initial()
        _, aid = analyze(store, artifacts, "base")
        for selectors in (
            ("absent", "candidate:component-0001"),
            (["candidate:component-0001"], "candidate:component-0001"),
        ):
            before = store.head
            with self.assertRaises(ValueError):
                RasterGeometryObservationAdapter().propose(
                    observation_request(store, aid, aid, selectors=selectors), artifacts
                )
            self.assertEqual(store.head, before)
        for mode in ("RGB", "RGBA", "I;16"):
            output = io.BytesIO()
            Image.new(mode, (20, 20)).save(output, format="PNG")
            before = store.head
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                analyze(store, artifacts, content=output.getvalue())
            self.assertEqual(store.head, before)
        for size in (0, 1):
            image = Image.new("L", (20, 20), 255)
            if size:
                image.putpixel((5, 5), 0)
            output = io.BytesIO()
            image.save(output, format="PNG")
            _, invalid = analyze(store, artifacts, content=output.getvalue())
            before = store.head
            with self.assertRaises(ValueError):
                RasterGeometryObservationAdapter().propose(
                    observation_request(store, invalid, invalid), artifacts
                )
            self.assertEqual(store.head, before)
