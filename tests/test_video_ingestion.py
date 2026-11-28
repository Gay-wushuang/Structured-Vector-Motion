import copy
import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from svm.artifacts import ArtifactError, ArtifactKind, ArtifactStore
from svm.evaluator import canonical_bytes
from svm.video_ingestion import (
    VideoIngestionError,
    VideoSampling,
    canonical_frame_png,
    canonical_reference_png,
    ingest_video,
    verify_video_manifest,
)

FIXTURE = Path(__file__).resolve().parents[1] / "examples/038-controlled-video-ingestion"


class VideoIngestionTest(unittest.TestCase):
    def test_lossless_container_determinism_and_timing(self):
        store = ArtifactStore()
        source = store.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        options = VideoSampling((0, 1, 2, 3), 12)
        first = ingest_video(store, source.document_reference(), options)
        second = ingest_video(store, source.document_reference(), options)
        self.assertEqual(first, second)
        self.assertEqual([o["tick"] for o in first.occurrences], [0, 12, 24, 36])
        self.assertEqual(verify_video_manifest(store, first.manifest.document_reference()), first)

    def test_cross_platform_codec_and_canonical_bytes_contract(self):
        # Mandatory on every CI matrix entry: no platform/dependency skips.
        import cv2

        store = ArtifactStore()
        source = store.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        result = ingest_video(store, source.document_reference(), VideoSampling((0, 1, 2, 3), 12))
        reference = FIXTURE.parent / "037-explicit-multi-object-raster-recovery"
        for tick, frame, occurrence in zip(
            (0, 12, 24, 36), result.frames, result.occurrences, strict=True
        ):
            self.assertEqual(
                frame.content,
                canonical_reference_png((reference / f"tick_{tick:03}.png").read_bytes()),
            )
            self.assertEqual(occurrence["tick"], tick)
            self.assertEqual(occurrence["source_timestamp"], [tick // 12, 1])
            self.assertEqual(occurrence["raster_artifact_id"], frame.artifact_id)
        print(
            "S11D backend build:",
            "\n".join(
                line.strip()
                for line in cv2.getBuildInformation().splitlines()
                if any(
                    k in line for k in ("FFMPEG:", "avcodec:", "avformat:", "avutil:", "swscale:")
                )
            ),
        )
        print("S11D frame hashes:", [f.content_hash for f in result.frames])

    def test_exact_rational_fps_and_sampling_without_rounding(self):
        store = ArtifactStore()
        source = store.import_bytes(
            (FIXTURE / "fractional.avi").read_bytes(), media_type="video/x-msvideo"
        )
        # OpenCV's writer records 2997/100 here, not 30000/1001. Read the actual
        # integer AVI header, never guess a broadcast timebase from reported 29.97.
        result = ingest_video(
            store, source.document_reference(), VideoSampling((0, 1), 2997, (2997, 100))
        )
        self.assertEqual([o["tick"] for o in result.occurrences], [0, 100])
        self.assertEqual(result.occurrences[1]["source_timestamp"], [100, 2997])
        with self.assertRaisesRegex(VideoIngestionError, "exact integer"):
            ingest_video(store, source.document_reference(), VideoSampling((0, 1), 12))
        with self.assertRaisesRegex(VideoIngestionError, "disagrees"):
            ingest_video(
                store, source.document_reference(), VideoSampling((0, 1), 30000, (30000, 1001))
            )
        normal = store.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        selected = ingest_video(store, normal.document_reference(), VideoSampling((1, 3), 12))
        self.assertEqual([o["tick"] for o in selected.occurrences], [12, 36])

    def test_repeated_frame_blob_and_distinct_occurrences(self):
        from test_raster_recovery_acceptance import accept, observation_request, request

        from svm import RevisionStore
        from svm.adapters.opencv_analysis import OpenCVAnalysisAdapter
        from svm.adapters.raster_geometry_observations import RasterGeometryObservationAdapter

        artifacts = ArtifactStore()
        source = artifacts.import_bytes(
            (FIXTURE / "repeated.avi").read_bytes(), media_type="video/x-msvideo"
        )
        result = ingest_video(artifacts, source.document_reference(), VideoSampling((0, 1), 12))
        self.assertEqual(result.frames[0], result.frames[1])
        self.assertNotEqual(
            result.occurrences[0]["occurrence_id"], result.occurrences[1]["occurrence_id"]
        )
        base = FIXTURE.parent / "037-explicit-multi-object-raster-recovery/recovery-base.svm.json"
        store = RevisionStore.create(json.loads(base.read_text()))
        analysis = accept(store, artifacts, OpenCVAnalysisAdapter(), [result.frames[0].artifact_id])
        aid = analysis.preview_artifacts[1].artifact_id
        proposal = RasterGeometryObservationAdapter().propose(
            observation_request(store, aid, aid), artifacts
        )
        data = json.loads(artifacts.get(proposal.preview_artifacts[0].artifact_id).content)
        primitives = [f["primitives"][0] for f in data["frames"]]
        self.assertEqual(primitives[0]["geometry"], primitives[1]["geometry"])
        self.assertNotEqual(primitives[0]["observation_id"], primitives[1]["observation_id"])
        before = store.head
        with self.assertRaises(ValueError):
            RasterGeometryObservationAdapter().propose(
                request(
                    store,
                    [aid],
                    {
                        "occurrences": [
                            {
                                "analysis_artifact_id": aid,
                                "tick": t,
                                "component_id": "candidate:component-9999",
                            }
                            for t in (0, 12)
                        ]
                    },
                ),
                artifacts,
            )
        self.assertEqual(store.head, before)

    def test_invalid_sampling_and_forged_video_reference(self):
        store = ArtifactStore()
        source = store.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        for options in (
            VideoSampling((0, 0), 12),
            VideoSampling((1, 0), 12),
            VideoSampling((-1,), 12),
            VideoSampling((True,), 12),
            VideoSampling((), 12),
            VideoSampling((0,), 0),
            VideoSampling((0,), 12, (2997.0, 100)),
            VideoSampling((0,), 12, (2, 2)),
            VideoSampling((4,), 12),
        ):
            with self.subTest(options=options), self.assertRaises(VideoIngestionError):
                ingest_video(store, source.document_reference(), options)
        ref = source.document_reference()
        ref["content_hash"] = "sha256:" + "0" * 64
        with self.assertRaises(ArtifactError):
            ingest_video(store, ref, VideoSampling((0,), 12))

    def test_unsupported_corrupt_truncated_missing_and_dimensions_fail_closed(self):
        original = (FIXTURE / "scene.avi").read_bytes()
        corrupted = bytearray(original)
        pos = corrupted.index(b"00dc", corrupted.index(b"movi") + 4)
        size = struct.unpack_from("<I", corrupted, pos + 4)[0]
        corrupted[pos + 8 : pos + 8 + size] = b"\x00" * size
        bad_dimension = bytearray(original)
        struct.pack_into("<i", bad_dimension, bad_dimension.index(b"strf") + 12, 0)
        bad_timing = bytearray(original)
        struct.pack_into("<I", bad_timing, bad_timing.index(b"strh") + 28, 0)
        for content in (
            b"not a video",
            original[:-20],
            original.replace(b"FFV1", b"MJPG"),
            bytes(bad_dimension),
            bytes(bad_timing),
            bytes(corrupted),
        ):
            store = ArtifactStore()
            source = store.import_bytes(content, media_type="video/x-msvideo")
            with self.subTest(size=len(content)), self.assertRaises(VideoIngestionError):
                ingest_video(store, source.document_reference(), VideoSampling((0, 1, 2, 3), 12))

    def test_frame_domain_rejects_color_alpha_gray_and_invalid_storage(self):
        import numpy as np

        color = np.zeros((2, 2, 3), np.uint8)
        color[0, 0, 0] = 255
        for frame in (
            color,
            np.zeros((2, 2, 4), np.uint8),
            np.full((2, 2), 128, np.uint8),
            np.zeros((0, 2), np.uint8),
            np.zeros((2, 2), np.uint16),
            None,
        ):
            with (
                self.subTest(shape=getattr(frame, "shape", None)),
                self.assertRaises(VideoIngestionError),
            ):
                canonical_frame_png(frame)

    def test_manifest_index_timestamp_and_provenance_forgery_reject(self):
        store = ArtifactStore()
        source = store.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        result = ingest_video(store, source.document_reference(), VideoSampling((0, 1), 12))
        for mutation in ("index", "timestamp", "tick", "raster", "video", "provenance"):
            data = json.loads(result.manifest.content)
            provenance = copy.deepcopy(result.manifest.provenance)
            if mutation == "index":
                data["occurrences"][0]["frame_index"] = 1
            if mutation == "timestamp":
                data["occurrences"][0]["source_timestamp"] = [1, 1000]
            if mutation == "tick":
                data["occurrences"][1]["tick"] = 0
            if mutation == "raster":
                data["occurrences"][0]["raster_artifact_id"] = result.frames[1].artifact_id
            if mutation == "video":
                data["source_video_reference"]["content_hash"] = "sha256:" + "0" * 64
            if mutation == "provenance":
                provenance["source_video_artifact_id"] = result.frames[0].artifact_id
            forged = store.import_bytes(
                canonical_bytes(data),
                media_type=result.manifest.media_type,
                kind=ArtifactKind.DERIVED,
                provenance=provenance,
            )
            with (
                self.subTest(mutation=mutation),
                self.assertRaises((VideoIngestionError, ArtifactError)),
            ):
                verify_video_manifest(store, forged.document_reference())

    def test_failed_decode_never_duplicates_or_publishes_partial_outputs(self):
        import cv2

        store = ArtifactStore()
        source = store.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        original = cv2.VideoCapture

        class MissingFrame:
            def __init__(self, *args):
                self.capture = original(*args)
                self.reads = 0

            def __getattr__(self, name):
                return getattr(self.capture, name)

            def read(self):
                self.reads += 1
                return (False, None) if self.reads == 2 else self.capture.read()

        with (
            patch("cv2.VideoCapture", MissingFrame),
            patch.object(store, "import_bytes", wraps=store.import_bytes) as publish,
        ):
            with self.assertRaisesRegex(VideoIngestionError, "index 1"):
                ingest_video(store, source.document_reference(), VideoSampling((0, 1), 12))
            publish.assert_not_called()

    def test_forged_canonical_frame_descriptor_is_not_video_provenance(self):
        store = ArtifactStore()
        source = store.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        result = ingest_video(store, source.document_reference(), VideoSampling((0,), 12))
        forged_store = ArtifactStore()
        for snapshot in (source, result.manifest):
            forged_store.import_bytes(
                snapshot.content,
                media_type=snapshot.media_type,
                kind=snapshot.kind,
                provenance=snapshot.provenance,
            )
        forged_store.import_bytes(
            result.frames[0].content,
            media_type="image/png",
            provenance={"source_video_artifact_id": source.artifact_id, "frame_index": 99},
        )
        with self.assertRaisesRegex(VideoIngestionError, "provenance"):
            verify_video_manifest(forged_store, result.manifest.document_reference())

    def test_cli_exports_portable_input_bundle_without_document(self):
        from svm.cli import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "extracted"
            args = [
                "ingest-video",
                str(FIXTURE / "scene.avi"),
                "--frame-index",
                "0",
                "--frame-index",
                "3",
                "--ticks-per-second",
                "12",
                "--output-directory",
                str(output),
            ]
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(main(args), 0)
            data = json.loads((output / "frame-manifest.json").read_bytes())
            self.assertEqual([o["tick"] for o in data["occurrences"]], [0, 36])
            self.assertEqual(len(list(output.glob("*.png"))), 2)
            self.assertEqual(
                (output / "source.avi").read_bytes(), (FIXTURE / "scene.avi").read_bytes()
            )
            with redirect_stderr(stderr):
                self.assertEqual(main(args), 2)
