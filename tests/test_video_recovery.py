"""Real container input into the frozen S11C orchestration, without PNG leakage."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_multi_object_raster_recovery import FIXTURE as RASTER_FIXTURE
from test_multi_object_raster_recovery import GROUPS, TICKS, author_all, measure, prepare
from test_video_ingestion import FIXTURE

from svm import ArtifactStore, MotionEvaluator
from svm.renderers import SVGRenderer, SVGRenderOptions
from svm.video_ingestion import (
    VideoSampling,
    canonical_reference_png,
    ingest_video,
    verify_video_manifest,
)


class VideoRecoveryTest(unittest.TestCase):
    def test_video_only_twelve_tracks_equivalence_and_complete_lineage(self):
        artifacts = ArtifactStore()
        source = artifacts.import_bytes(
            (FIXTURE / "scene.avi").read_bytes(), media_type="video/x-msvideo"
        )
        read_bytes, read_text = Path.read_bytes, Path.read_text

        def forbid_png(path):
            if path.suffix == ".png":
                raise AssertionError("Video recovery accessed reference PNG")
            return read_bytes(path)

        def forbid_truth(path, *args, **kwargs):
            if path.name in {"ground-truth.json", "verification.json"}:
                raise AssertionError("Video recovery accessed Ground Truth/expected IDs")
            return read_text(path, *args, **kwargs)

        with (
            patch.object(Path, "read_bytes", forbid_png),
            patch.object(Path, "read_text", forbid_truth),
        ):
            decoded = ingest_video(
                artifacts, source.document_reference(), VideoSampling((0, 1, 2, 3), 12)
            )
            self.assertEqual([o["tick"] for o in decoded.occurrences], list(TICKS))
            video = prepare(frame_sources=tuple(frame.content for frame in decoded.frames))
            document, proposals = author_all(video)
        self.assertEqual(len(document["animation"]["content"]), 12)
        # Reference data is first accessed AFTER the genuine video-only branch.
        canonical = tuple(
            canonical_reference_png((RASTER_FIXTURE / f"tick_{t:03}.png").read_bytes())
            for t in TICKS
        )
        normalized_reference = prepare(frame_sources=canonical)
        reference_document, reference_proposals = author_all(normalized_reference)
        self.assertEqual(document, reference_document)
        self.assertEqual(proposals, reference_proposals)
        for key in ("lineages", "cameras", "consensus", "camera_id", "targets"):
            self.assertEqual(video[key], normalized_reference[key])
        # Original compressed PNG bytes differ from the canonical stored-DEFLATE
        # encoding. Their IDs may differ; their formal sampled motion must not.
        original_reference = prepare()
        original_document, _ = author_all(original_reference)
        renderer = SVGRenderer(SVGRenderOptions(view_box=(0, 0, 1200, 900)))
        for tick in TICKS:
            actual = MotionEvaluator(document)
            expected = MotionEvaluator(original_document)
            a, b = actual.sample_document(tick), expected.sample_document(tick)
            self.assertEqual(a["presentation"]["camera"], b["presentation"]["camera"])
            for group in GROUPS:
                self.assertEqual(
                    next(g["transform"] for g in a["groups"] if g["id"] == group),
                    next(g["transform"] for g in b["groups"] if g["id"] == group),
                )
            self.assertEqual(
                renderer.render(actual.evaluate(tick).scene),
                renderer.render(expected.evaluate(tick).scene),
            )

        def properties(d):
            return [t["target"] for t in d["animation"]["content"]]

        self.assertEqual(properties(document), properties(original_document))
        errors, geometry = measure(document, video["artifacts"], video["lineages"])
        for role, values in errors.items():
            self.assertLessEqual(values["position"], 1)
            self.assertLessEqual(values["rotation"], 0.2)
            self.assertLessEqual(values["scale"], 0.003 if role == "camera" else 0.005)
        self.assertLessEqual(max(geometry.values()), 2)
        print("S11D video recovery errors:", errors, geometry)

        # Input processing owns an external manifest, not Document mutation.
        # Retain this input bundle alongside the recovered Document for video lineage.
        repository = video["artifacts"]
        for snapshot in (source, decoded.manifest):
            repository.import_bytes(
                snapshot.content,
                media_type=snapshot.media_type,
                kind=snapshot.kind,
                provenance=snapshot.provenance,
            )
        verified = verify_video_manifest(repository, decoded.manifest.document_reference())
        manifest = json.loads(verified.manifest.content)
        self.assertEqual(manifest["source_video_reference"], source.document_reference())
        by_tick = {o["tick"]: o for o in verified.occurrences}
        for lineage in video["lineages"].values():
            for gid in lineage["geometry_ids"]:
                snapshot = repository.get(gid)
                data = json.loads(snapshot.content)
                for frame, occurrence in zip(
                    data["frames"], snapshot.provenance["source_occurrences"], strict=True
                ):
                    video_occurrence = by_tick[frame["tick"]]
                    self.assertEqual(
                        occurrence["source_png_artifact_id"], video_occurrence["raster_artifact_id"]
                    )
        # Frozen S11C tests verify the remainder of Track -> binding -> compensated
        # evidence -> shared Camera/own lineage -> raster occurrence provenance.
        self.assertEqual(
            len([r for r in document["references"] if "camera-consensus+json" in r["media_type"]]),
            1,
        )
