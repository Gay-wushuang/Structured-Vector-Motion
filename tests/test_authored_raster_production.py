import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import AdapterRequest, ProposalAcceptor, RevisionStore, Transaction
from svm.adapters.opencv_analysis import OpenCVAnalysisAdapter
from svm.adapters.primitive_observation_assembly import PrimitiveObservationAssemblyAdapter
from svm.adapters.raster_primitive_observation_proposal import (
    RasterPrimitiveObservationProposalAdapter,
)
from svm.adapters.svg_import import SVGNormalizer
from svm.artifacts import ArtifactKind, ArtifactStore
from svm.authored_raster_production import (
    AuthoredRasterProductionError,
    publish_verified_production,
    reproduce_source,
    verify_production,
)
from svm.evaluator import canonical_bytes
from svm.revisions import AppendReferencesChange
from svm.video_ingestion import VideoSampling, canonical_frame_png, ingest_video

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/043-authored-raster-production"


def accept_refs(store, *snapshots):
    return store.commit(
        store.head,
        Transaction(
            "transaction:production-inputs",
            (AppendReferencesChange(tuple(s.document_reference() for s in snapshots)),),
        ),
    )


def pipeline(source_content=None):
    artifacts = ArtifactStore()
    store = RevisionStore.create(
        json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
    )
    source = artifacts.import_bytes(
        source_content or (FIXTURE / "source.svg").read_bytes(), media_type="image/svg+xml"
    )
    source_revision = accept_refs(store, source).revision_id
    produced = reproduce_source(store, source_revision, artifacts)
    video = artifacts.import_bytes(
        (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
    )
    accept_refs(store, video)
    decoded = ingest_video(artifacts, video.document_reference(), VideoSampling((0, 1), 12, (1, 1)))
    accept_refs(store, *decoded.frames, decoded.manifest)

    def accept(adapter, ids):
        proposal = adapter.propose(
            AdapterRequest.from_store(store, store.head, ("document",), artifact_ids=ids), artifacts
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        return proposal

    p2a_ids = []
    for frame in decoded.frames:
        analysis = accept(OpenCVAnalysisAdapter(), (frame.artifact_id,))
        p2a = accept(
            RasterPrimitiveObservationProposalAdapter(),
            (analysis.preview_artifacts[1].artifact_id, decoded.manifest.artifact_id),
        )
        p2a_ids.append(p2a.preview_artifacts[0].artifact_id)
    p2b = accept(PrimitiveObservationAssemblyAdapter(), tuple(p2a_ids))
    ids = (
        decoded.manifest.artifact_id,
        tuple(p2a_ids),
        p2b.preview_artifacts[0].artifact_id,
        p2b.preview_artifacts[1].artifact_id,
    )
    report = publish_verified_production(store, store.head, produced, *ids, artifacts)
    return artifacts, store, source, produced, decoded, ids, report


class AuthoredRasterProductionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = pipeline()

    def setUp(self):
        (
            self.artifacts,
            self.store,
            self.source,
            self.produced,
            self.decoded,
            self.ids,
            self.report,
        ) = copy.deepcopy(self.golden)

    def publish(self, produced=None, ids=None):
        return publish_verified_production(
            self.store,
            self.store.head,
            produced or self.produced,
            *(ids or self.ids),
            self.artifacts,
        )

    def verify(self, snapshot=None):
        verify_production(
            self.store,
            self.store.head,
            (snapshot or self.report).document_reference(),
            self.artifacts,
        )

    def snapshot(self, original, payload=None, **kwargs):
        return self.artifacts.import_bytes(
            original.content if payload is None else canonical_bytes(payload),
            media_type=kwargs.get("media_type", original.media_type),
            kind=kwargs.get("kind", original.kind),
            provenance=kwargs.get("provenance", original.provenance),
        )

    def assert_fails_without_revision(self, action):
        before = copy.deepcopy(self.store)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            action()
        self.assertEqual(self.store, before)

    def test_golden_full_replay_and_exact_recorded_ids(self):
        self.verify()
        self.assertEqual(self.publish(), self.report)
        expected = json.loads((FIXTURE / "golden.json").read_text())
        self.assertEqual(json.loads(self.report.content), expected["report"])
        self.assertEqual(self.report.content_hash, expected["report_hash"])
        self.assertEqual(tuple(f.content for f in self.decoded.frames), self.produced.frames)
        document = self.store.get_document(self.store.head)
        empty = json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        self.assertEqual(
            {k: v for k, v in document.items() if k != "references"},
            {k: v for k, v in empty.items() if k != "references"},
        )
        self.assertNotIn(self.report.artifact_id, [r["id"] for r in document["references"]])

    def test_source_is_existing_renderable_geometry(self):
        shapes = SVGNormalizer().normalize(self.source, "production-check")
        self.assertEqual([s.operation["type"] for s in shapes], ["CreatePath", "CreatePath"])
        self.assertEqual(
            [s.operation["parameters"]["bounds"] for s in shapes],
            [[20.0, 20.0, 100.0, 80.0], [140.0, 120.0, 212.0, 174.0]],
        )
        self.assertTrue(all(s.style["fill"] == "#000000" for s in shapes))

    def test_four_supported_measurements_and_bijection(self):
        payload = json.loads(self.report.content)
        landmarks = [
            [
                [[20.0, 79.0], [98.0, 20.0], [20.0, 20.0]],
                [[140.0, 173.0], [210.0, 120.0], [140.0, 120.0]],
            ],
            [
                [[28.0, 85.0], [106.0, 26.0], [28.0, 26.0]],
                [[148.0, 179.0], [218.0, 126.0], [148.0, 126.0]],
            ],
        ]
        for index, occurrence in enumerate(payload["occurrences"]):
            self.assertEqual(
                [p["ordered_landmarks"] for p in occurrence["parts"]], landmarks[index]
            )
            self.assertEqual([p["status"] for p in occurrence["parts"]], ["SUPPORTED"] * 2)
            self.assertEqual(
                [p["measurements"]["contour_area"] for p in occurrence["parts"]], [2291.5, 1846.5]
            )
            self.assertEqual(
                [p["measurements"]["simplified_vertex_count"] for p in occurrence["parts"]], [3, 3]
            )
            self.assertEqual(
                [p["measurements"]["minimum_edge_pixels"] for p in occurrence["parts"]],
                [59.0, 53.0],
            )
            self.assertEqual(
                [p["measurements"]["longest_edge_margin_pixels"] for p in occurrence["parts"]],
                [19.8008179924892, 17.80091115700337],
            )
            self.assertEqual(len({p["observation_id"] for p in occurrence["parts"]}), 2)
        observation = json.loads(self.artifacts.get(self.ids[2]).content)
        self.assertEqual([len(f["primitives"]) for f in observation["frames"]], [2, 2])

    def test_exact_mask_union_disjointness_and_polarity(self):
        import cv2
        import numpy as np

        for frame, contributions in zip(
            self.produced.frames, self.produced.contributions, strict=True
        ):

            def decode(png):
                return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)

            a, b = [decode(png) != 0 for png in contributions]
            self.assertFalse(np.any(a & b))
            self.assertTrue(np.array_equal(a | b, decode(frame) == 0))

    def source_variant(self, content, *, accepted=True, media_type="image/svg+xml"):
        artifacts = ArtifactStore()
        source = artifacts.import_bytes(content, media_type=media_type)
        store = RevisionStore.create(
            json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        )
        if accepted:
            accept_refs(store, source)
        return store, artifacts

    def test_missing_and_resolver_only_source(self):
        for accepted in (False,):
            store, artifacts = self.source_variant(self.source.content, accepted=accepted)
            with self.assertRaisesRegex(AuthoredRasterProductionError, "Exactly one accepted"):
                reproduce_source(store, store.head, artifacts)
            with self.assertRaises(AuthoredRasterProductionError):
                reproduce_source(store, store.head, ArtifactStore())

    def test_source_grammar_adversaries(self):
        text = self.source.content.decode()
        a = '<path id="part-a" d="M 20 20 L 100 20 L 20 80 Z"/>'
        b = '<path id="part-b" d="M 140 120 L 212 120 L 140 174 Z"/>'
        variants = {
            "omitted": text.replace(b, ""),
            "extra": text.replace(b, b + b),
            "reordered": text.replace(a, "TEMP").replace(b, a).replace("TEMP", b),
            "flat": text.replace("<g>", "").replace("</g>", ""),
            "nested": text.replace(a, "<g>" + a + "</g>"),
            "wrong_geometry": text.replace("L 100 20", "L 20 20"),
            "overlap": text.replace(
                "M 140 120 L 212 120 L 140 174 Z", "M 20 20 L 100 20 L 20 80 Z"
            ),
            "transform": text.replace("<g>", '<g transform="translate(1 0)">'),
            "style": text.replace('id="part-a"', 'id="part-a" opacity="0"'),
            "noncanonical": text.replace("M 20 20", "M 020 20"),
        }
        for name, value in variants.items():
            with self.subTest(name=name):
                store, artifacts = self.source_variant(value.encode())
                with self.assertRaises(AuthoredRasterProductionError):
                    reproduce_source(store, store.head, artifacts)

    def test_real_rejected_and_uncertain_parts_fail_closed(self):
        # Explicit adversarial inputs, never revisions to the positive source.
        for path in ("M 20 20 L 24 20 L 20 23 Z", "M 20 20 L 80 20 L 50 72 Z"):
            text = self.source.content.decode().replace("M 20 20 L 100 20 L 20 80 Z", path)
            store, artifacts = self.source_variant(text.encode())
            with self.assertRaisesRegex(
                AuthoredRasterProductionError, "AUTHORED_PARTS_NOT_P2A_ELIGIBLE"
            ):
                reproduce_source(store, store.head, artifacts)

    def test_fake_source_media_type(self):
        store, artifacts = self.source_variant(self.source.content, media_type="text/plain")
        with self.assertRaises(AuthoredRasterProductionError):
            reproduce_source(store, store.head, artifacts)

    def test_changed_accepted_source_bytes(self):
        changed = self.artifacts.import_bytes(
            self.source.content.replace(b"20 20", b"21 20"), media_type="image/svg+xml"
        )
        accept_refs(self.store, changed)
        self.assert_fails_without_revision(self.publish)

    def test_produced_frame_and_contribution_tampering(self):
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(self.produced.frames[0], np.uint8), cv2.IMREAD_UNCHANGED)
        frame[0, 0] = 0  # One unexplained foreground pixel.
        changed_frame = canonical_frame_png(frame)
        masks = self.produced.contributions
        changes = [
            replace(self.produced, frames=(changed_frame, self.produced.frames[1])),
            replace(self.produced, frames=self.produced.frames[:1]),
            replace(self.produced, contributions=((masks[0][1], masks[0][0]), masks[1])),
            replace(self.produced, contributions=((masks[0][0], masks[0][0]), masks[1])),
            replace(self.produced, contributions=((changed_frame, masks[0][1]), masks[1])),
        ]
        for produced in changes:
            with self.subTest(produced=hashlib.sha256(repr(produced).encode()).hexdigest()):
                self.assert_fails_without_revision(lambda produced=produced: self.publish(produced))

    def test_wrong_timing_and_omitted_occurrence_manifest(self):
        video = self.artifacts.resolve_reference(
            json.loads(self.decoded.manifest.content)["source_video_reference"]
        )
        for sampling in (VideoSampling((0,), 12, (1, 1)), VideoSampling((0, 1), 24, (1, 1))):
            decoded = ingest_video(self.artifacts, video.document_reference(), sampling)
            accept_refs(self.store, decoded.manifest)
            ids = (decoded.manifest.artifact_id, *self.ids[1:])
            self.assert_fails_without_revision(lambda ids=ids: self.publish(ids=ids))

    def test_wrong_video_and_manifest(self):
        wrong = self.artifacts.import_bytes(
            (ROOT / "examples/038-controlled-video-ingestion/scene.avi").read_bytes(),
            media_type="video/x-msvideo",
        )
        decoded = ingest_video(
            self.artifacts, wrong.document_reference(), VideoSampling((0, 1), 12, (1, 1))
        )
        accept_refs(self.store, wrong, *decoded.frames, decoded.manifest)
        self.assert_fails_without_revision(
            lambda: self.publish(ids=(decoded.manifest.artifact_id, *self.ids[1:]))
        )

    def test_p2b_incomplete_and_p2a_status_forgery(self):
        observed = self.artifacts.get(self.ids[2])
        payload = json.loads(observed.content)
        payload["frames"][0]["primitives"].pop()
        altered = self.snapshot(observed, payload)
        accept_refs(self.store, altered)
        self.assert_fails_without_revision(
            lambda: self.publish(ids=(*self.ids[:2], altered.artifact_id, self.ids[3]))
        )
        original = self.artifacts.get(self.ids[1][0])
        for status in ("REJECTED", "UNCERTAIN"):
            payload = json.loads(original.content)
            payload["evaluations"][0]["status"] = status
            altered = self.snapshot(original, payload)
            accept_refs(self.store, altered)
            self.assert_fails_without_revision(
                lambda altered=altered: self.publish(
                    ids=(self.ids[0], (altered.artifact_id, self.ids[1][1]), *self.ids[2:])
                )
            )

    def test_stale_base(self):
        base = self.store.head
        extra = self.artifacts.import_bytes(b"unrelated", media_type="text/plain")
        accept_refs(self.store, extra)
        self.assert_fails_without_revision(
            lambda: verify_production(
                self.store, base, self.report.document_reference(), self.artifacts
            )
        )

    def test_report_claims_cannot_self_attest(self):
        original = json.loads(self.report.content)
        variants = []
        for key, value in (
            ("policy_identity", "forged"),
            ("source_grammar", "forged"),
            ("subject", {"subject_path": [1]}),
            ("part_identities", []),
        ):
            payload = copy.deepcopy(original)
            payload[key] = value
            variants.append(payload)
        for field in ("contribution_artifact_id", "observation_id", "part_key"):
            payload = copy.deepcopy(original)
            payload["occurrences"][0]["parts"][0][field] = "forged"
            variants.append(payload)
        for payload in variants:
            self.assert_fails_without_revision(
                lambda payload=payload: self.verify(self.snapshot(self.report, payload))
            )
        for kwargs in (
            {"media_type": "text/plain"},
            {"kind": ArtifactKind.REFERENCE},
            {"provenance": {"policy_identity": "fake"}},
        ):
            self.assert_fails_without_revision(
                lambda kwargs=kwargs: self.verify(self.snapshot(self.report, **kwargs))
            )

    def test_source_revision_cannot_be_a_post_video_sidecar(self):
        late = reproduce_source(self.store, self.store.head, self.artifacts)
        self.assert_fails_without_revision(lambda: self.publish(late))

    def test_mapping_uses_pixels_not_source_or_component_order(self):
        # Same two already verified shapes and same complete video; only authored
        # names occupy opposite spatial positions in this independently accepted input.
        content = self.source.content.replace(b"M 20 20 L 100 20 L 20 80 Z", b"TEMP")
        content = content.replace(b"M 140 120 L 212 120 L 140 174 Z", b"M 20 20 L 100 20 L 20 80 Z")
        content = content.replace(b"TEMP", b"M 140 120 L 212 120 L 140 174 Z")
        artifacts, store, _, _, _, _, report = pipeline(content)
        verify_production(store, store.head, report.document_reference(), artifacts)
        for occurrence in json.loads(report.content)["occurrences"]:
            self.assertEqual([p["part_key"] for p in occurrence["parts"]], ["part-a", "part-b"])
            self.assertEqual(
                [p["component_id"] for p in occurrence["parts"]],
                ["candidate:component-0002", "candidate:component-0001"],
            )

    def test_substituted_source_blob_is_rejected(self):
        original = self.artifacts._blobs[self.source.artifact_id]
        self.artifacts._blobs[self.source.artifact_id] = replace(
            original, content=original.content + b" "
        )
        self.assert_fails_without_revision(self.publish)

    def test_missing_or_corrupt_contribution_artifact(self):
        aid = json.loads(self.report.content)["occurrences"][0]["parts"][0][
            "contribution_artifact_id"
        ]
        original = self.artifacts._blobs[aid]
        self.artifacts._blobs[aid] = replace(original, content=b"wrong pixels")
        self.assert_fails_without_revision(self.verify)
        del self.artifacts._blobs[aid]
        self.assert_fails_without_revision(self.verify)


if __name__ == "__main__":
    unittest.main()
