import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import AdapterRequest, ProposalAcceptor, RevisionStore, Transaction
from svm.adapters.opencv_analysis import OpenCVAnalysisAdapter, OpenCVAnalysisOptions, analyze_png
from svm.adapters.raster_geometry_observations import contour_landmarks
from svm.adapters.raster_primitive_observation_proposal import (
    MEDIA,
    POLICY,
    SCHEMA,
    RasterPrimitiveObservationProposalAdapter,
    measure_component,
)
from svm.artifacts import ArtifactKind, ArtifactStore
from svm.evaluator import canonical_bytes
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.revisions import AppendReferencesChange, AttachRasterPrimitiveObservationProposalChange
from svm.video_ingestion import VideoSampling, canonical_frame_png, ingest_video

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/040-raster-primitive-observation-proposal/scene.avi"


class RasterPrimitiveObservationProposalTest(unittest.TestCase):
    def setUp(self):
        self.artifacts = ArtifactStore()
        self.source = self.artifacts.import_bytes(
            FIXTURE.read_bytes(), media_type="video/x-msvideo"
        )
        self.video = ingest_video(
            self.artifacts, self.source.document_reference(), VideoSampling((0,), 12)
        )
        document = json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        self.store = RevisionStore.create(document)
        self.accept_refs(self.source, *self.video.frames, self.video.manifest)
        self.analysis = self.analyze(self.video.frames[0])
        self.manifest = self.video.manifest
        self.adapter = RasterPrimitiveObservationProposalAdapter()

    def accept_refs(self, *snapshots):
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:fixture-references",
                (AppendReferencesChange(tuple(s.document_reference() for s in snapshots)),),
            ),
        )

    def analyze(self, frame):
        proposal = OpenCVAnalysisAdapter().propose(
            AdapterRequest.from_store(
                self.store, self.store.head, ("document",), artifact_ids=(frame.artifact_id,)
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        return self.artifacts.get(proposal.preview_artifacts[1].artifact_id)

    def propose(self, **kwargs):
        return self.adapter.propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(self.analysis.artifact_id, self.manifest.artifact_id),
                **kwargs,
            ),
            self.artifacts,
        )

    def state(self):
        return self.store.head, len(self.store.revisions), self.store.get_document(self.store.head)

    def fails_atomically(self, action):
        before = self.state()
        with self.assertRaises(
            (ValueError, ProposalArtifactError, ProposalConflictError, ProposalPolicyError)
        ):
            action()
        self.assertEqual(self.state(), before)

    def accept(self, proposal):
        return ProposalAcceptor().accept(self.store, proposal, self.artifacts)

    def snapshot(self, original, *, data=None, **kwargs):
        return self.artifacts.import_bytes(
            original.content if data is None else canonical_bytes(data),
            media_type=kwargs.get("media_type", original.media_type),
            kind=kwargs.get("kind", original.kind),
            provenance=kwargs.get("provenance", original.provenance),
        )

    def replace_accepted(self, original, altered):
        document = self.store.get_document(self.store.head)
        document["references"] = [
            altered.document_reference() if r["id"] == original.artifact_id else r
            for r in document["references"]
        ]
        self.store = RevisionStore.create(document)

    def with_change(self, proposal, change):
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(change,)),
            required_artifact_ids=tuple(r["id"] for r in change.references),
        )

    def test_golden_all_components_and_landmark_parity(self):
        import numpy as np

        proposal = self.propose()
        evidence = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        data = json.loads(evidence.content)
        self.assertEqual((evidence.kind, evidence.media_type), (ArtifactKind.DERIVED, MEDIA))
        self.assertEqual(data["schema_version"], SCHEMA)
        self.assertEqual(data["status_counts"], {"SUPPORTED": 1, "UNCERTAIN": 1, "REJECTED": 2})
        entries = data["evaluations"]
        self.assertEqual(
            [e["component_id"] for e in entries],
            [f"candidate:component-{i:04}" for i in range(1, 5)],
        )
        self.assertEqual(
            [e["status"] for e in entries], ["SUPPORTED", "UNCERTAIN", "REJECTED", "REJECTED"]
        )
        self.assertEqual(entries[0]["reason_codes"], [])
        self.assertEqual(entries[1]["reason_codes"], ["AMBIGUOUS_LANDMARK_ORIGIN"])
        self.assertEqual(entries[2]["reason_codes"], ["HAS_HOLE"])
        self.assertEqual(entries[3]["reason_codes"], ["AREA_BELOW_256"])
        self.assertEqual(data["proposed_candidates"], entries[:2])
        _, labels, _, _, _ = analyze_png(self.video.frames[0], OpenCVAnalysisOptions())
        selected = np.where(labels == labels[10, 10], 255, 0).astype(np.uint8)
        self.assertEqual(entries[0]["ordered_landmarks"], contour_landmarks(selected))
        self.assertEqual(
            entries[0]["ordered_landmarks"], [[25.0, 65.0], [90.0, 10.0], [10.0, 10.0]]
        )
        self.assertEqual(data["occurrence_provenance"]["tick"], 0)
        self.assertEqual(data["occurrence_provenance"]["source_timestamp"], [0, 1])

    def test_deterministic_ids_bytes_and_proposal(self):
        first, second = self.propose(), self.propose()
        self.assertEqual(first, second)
        a = self.artifacts.get(first.preview_artifacts[0].artifact_id)
        b = self.artifacts.get(second.preview_artifacts[0].artifact_id)
        self.assertEqual(a.content, b.content)
        for entry in json.loads(a.content)["evaluations"]:
            identity = {
                k: v
                for k, v in entry["provenance"].items()
                if k not in {"analysis_options", "source_timestamp"}
            }

            def digest(value):
                return hashlib.sha256(canonical_bytes(value)).hexdigest()[:32]

            if entry["status"] != "REJECTED":
                self.assertEqual(
                    entry["candidate_id"], "candidate:primitive-observation:" + digest(identity)
                )
            else:
                self.assertIsNone(entry["candidate_id"])
            self.assertEqual(
                entry["evaluation_id"],
                "evaluation:primitive-observation:"
                + digest(
                    {**identity, "status": entry["status"], "reason_codes": entry["reason_codes"]}
                ),
            )

    def test_preview_then_accept_only_appends_evidence(self):
        before = self.state()
        proposal = self.propose()
        preview = ProposalAcceptor().validate(self.store, proposal, self.artifacts)
        self.assertEqual(self.state(), before)
        self.accept(proposal)
        after = self.store.get_document(self.store.head)
        self.assertEqual(after, preview)
        self.assertEqual(len(self.store.revisions), before[1] + 1)
        self.assertEqual(after["references"][:-1], before[2]["references"])
        after["references"] = before[2]["references"]
        self.assertEqual(after, before[2])

    def test_forbidden_options(self):
        for key in (
            "component_id",
            "selector",
            "role",
            "anchor",
            "target",
            "identity",
            "pairing",
            "group",
            "track",
            "camera",
            "ground_truth",
            "tick",
        ):
            with self.subTest(key=key):
                self.fails_atomically(lambda: self.propose(options={key: "forbidden"}))

    def test_forged_analysis_digest_bytes_provenance_kind_media(self):
        original = self.analysis
        original_document = self.store.get_document(self.store.head)
        forged = json.loads(original.content)
        forged["components"][0]["component_digest"] = "sha256:" + "0" * 64
        different_bytes = json.loads(original.content)
        different_bytes["components"][0]["pixel_area"] += 1
        for kwargs in (
            {"data": forged},
            {"data": different_bytes},
            {"provenance": {}},
            {"kind": ArtifactKind.REFERENCE},
            {"media_type": "application/json"},
        ):
            with self.subTest(kwargs=kwargs):
                self.store = RevisionStore.create(original_document)
                self.analysis = self.snapshot(original, **kwargs)
                self.replace_accepted(original, self.analysis)
                self.fails_atomically(self.propose)

    def test_unaccepted_dependency_at_proposal_and_acceptance(self):
        proposal = self.propose()
        document = self.store.get_document(self.store.head)
        mask_id = json.loads(self.analysis.content)["binary_mask_artifact_id"]
        document["references"] = [r for r in document["references"] if r["id"] != mask_id]
        self.store = RevisionStore.create(document)
        self.fails_atomically(self.propose)
        proposal = replace(proposal, base_revision_id=self.store.head)
        self.fails_atomically(lambda: self.accept(proposal))

    def test_mask_descriptor_and_bytes_must_reproduce(self):
        analysis = self.analysis
        original = self.artifacts.get(json.loads(analysis.content)["binary_mask_artifact_id"])
        document = self.store.get_document(self.store.head)
        for kwargs in (
            {"provenance": {}},
            {"kind": ArtifactKind.REFERENCE},
            {"media_type": "application/octet-stream"},
            {"data": {"forged": "mask"}},
        ):
            with self.subTest(kwargs=kwargs):
                self.store = RevisionStore.create(document)
                altered = self.snapshot(original, **kwargs)
                self.replace_accepted(original, altered)
                if altered.artifact_id != original.artifact_id:
                    data = json.loads(analysis.content)
                    data["binary_mask_artifact_id"] = altered.artifact_id
                    self.analysis = self.snapshot(analysis, data=data)
                    self.replace_accepted(analysis, self.analysis)
                else:
                    self.analysis = analysis
                self.fails_atomically(self.propose)

    def test_acceptance_rechecks_forged_analysis_and_manifest_lineage(self):
        proposal = self.propose()
        original_document = self.store.get_document(self.store.head)
        change = proposal.transaction.changes[0]
        for original, field in (
            (self.analysis, "analysis_artifact_id"),
            (self.manifest, "manifest_artifact_id"),
        ):
            with self.subTest(field=field):
                self.store = RevisionStore.create(original_document)
                data = json.loads(original.content)
                if field == "analysis_artifact_id":
                    data["components"][0]["component_digest"] = "forged"
                else:
                    data["occurrences"][0]["tick"] = 999
                forged = self.snapshot(original, data=data)
                self.replace_accepted(original, forged)
                refs = tuple(
                    forged.document_reference() if r["id"] == original.artifact_id else r
                    for r in change.source_references
                )
                changed = replace(change, source_references=refs, **{field: forged.artifact_id})
                bad = replace(self.with_change(proposal, changed), base_revision_id=self.store.head)
                self.fails_atomically(lambda: self.accept(bad))

    def test_manifest_raster_and_tick_tampering(self):
        original = self.manifest
        document = self.store.get_document(self.store.head)
        for key, value in (("raster_artifact_id", self.analysis.artifact_id), ("tick", 99)):
            with self.subTest(key=key):
                self.store = RevisionStore.create(document)
                data = json.loads(original.content)
                data["occurrences"][0][key] = value
                self.manifest = self.snapshot(original, data=data)
                self.replace_accepted(original, self.manifest)
                self.fails_atomically(self.propose)

    def test_zero_matching_verified_occurrence(self):
        import cv2
        import numpy as np

        gray = cv2.imdecode(np.frombuffer(self.video.frames[0].content, np.uint8), 0)
        gray[90:101, 120:131] = 255
        frame = self.artifacts.import_bytes(canonical_frame_png(gray), media_type="image/png")
        self.accept_refs(frame)
        self.analysis = self.analyze(frame)
        self.fails_atomically(self.propose)

    def test_real_duplicate_matching_occurrences_rejected(self):
        video = ingest_video(
            self.artifacts, self.source.document_reference(), VideoSampling((0, 1), 12)
        )
        self.assertEqual(video.frames[0].artifact_id, video.frames[1].artifact_id)
        self.assertNotEqual(
            video.occurrences[0]["occurrence_id"], video.occurrences[1]["occurrence_id"]
        )
        self.accept_refs(video.manifest)
        self.manifest = video.manifest
        self.fails_atomically(self.propose)

    def test_tampered_evidence_rederived_at_acceptance(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        original = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        for field, value in (
            ("status", "REJECTED"),
            ("evaluation_id", "evaluation:forged"),
            ("candidate_id", "candidate:forged"),
            ("reason_codes", ["HAS_HOLE"]),
            ("ordered_landmarks", [[0, 0]]),
        ):
            with self.subTest(field=field):
                data = json.loads(original.content)
                data["evaluations"][0][field] = value
                altered = self.snapshot(original, data=data)
                forged = self.with_change(
                    proposal, replace(change, evidence_reference=altered.document_reference())
                )
                self.fails_atomically(lambda: self.accept(forged))
        for kwargs in (
            {"provenance": {}},
            {"media_type": "application/json"},
            {"kind": ArtifactKind.REFERENCE},
        ):
            altered = self.snapshot(original, **kwargs)
            forged = self.with_change(
                proposal, replace(change, evidence_reference=altered.document_reference())
            )
            self.fails_atomically(lambda: self.accept(forged))

    def test_wrong_policy_missing_dependency_and_unregistered_change(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]

        class Unregistered(AttachRasterPrimitiveObservationProposalChange):
            pass

        for bad in (
            replace(change, policy_identity=POLICY + "-forged"),
            replace(change, source_references=change.source_references[1:]),
            Unregistered(
                change.evidence_reference,
                change.source_references,
                change.analysis_artifact_id,
                change.manifest_artifact_id,
                change.policy_identity,
            ),
        ):
            self.fails_atomically(lambda: self.accept(self.with_change(proposal, bad)))

    def test_stale_proposal_and_multi_change_atomic_rejection(self):
        proposal = self.propose()
        extra = self.artifacts.import_bytes(b"unrelated", media_type="text/plain")
        bad = replace(proposal.transaction.changes[0], policy_identity="invalid")
        forged = replace(
            proposal,
            transaction=replace(
                proposal.transaction,
                changes=(AppendReferencesChange((extra.document_reference(),)), bad),
            ),
            required_artifact_ids=(*proposal.required_artifact_ids, extra.artifact_id),
        )
        self.fails_atomically(lambda: self.accept(forged))
        self.accept_refs(extra)
        self.fails_atomically(lambda: self.accept(proposal))

    def test_measurements_fail_closed_and_exact_area_edge_boundaries(self):
        import cv2
        import numpy as np

        def rectangle(width, height):
            mask = np.zeros((100, 100), np.uint8)
            cv2.rectangle(mask, (10, 10), (10 + width, 10 + height), 255, -1)
            return mask

        for width, height, status, reason in (
            (16, 16, "UNCERTAIN", "AMBIGUOUS_LANDMARK_ORIGIN"),
            (15, 17, "REJECTED", "AREA_BELOW_256"),
            (8, 40, "UNCERTAIN", "AMBIGUOUS_LANDMARK_ORIGIN"),
            (7, 40, "REJECTED", "MIN_EDGE_BELOW_8"),
        ):
            result = measure_component(rectangle(width, height), True)
            self.assertEqual((result["status"], result["reason_codes"]), (status, [reason]))
        self.assertIn(
            "NON_FLAT_SOLID_RASTER", measure_component(rectangle(20, 20), False)["reason_codes"]
        )
        empty = np.zeros((100, 100), np.uint8)
        self.assertEqual(measure_component(empty, True)["reason_codes"], ["NO_CONTOUR"])
        empty[5, 5] = 255
        self.assertIn("DEGENERATE_CONTOUR", measure_component(empty, True)["reason_codes"])
        cv2.rectangle(empty, (30, 30), (60, 60), 255, -1)
        self.assertIn("MULTIPLE_CONTOURS", measure_component(empty, True)["reason_codes"])
        # Scaled 5-12-13 triangles give exact margins of 4 and 5 pixels,
        # with every other eligibility condition valid.
        for scale, status in ((4, "UNCERTAIN"), (5, "SUPPORTED")):
            mask = np.zeros((100, 100), np.uint8)
            cv2.fillPoly(
                mask,
                [np.array([[10, 10], [10 + 5 * scale, 10], [10, 10 + 12 * scale]], np.int32)],
                255,
            )
            result = measure_component(mask, True)
            self.assertEqual(result["measurements"]["longest_edge_margin_pixels"], scale)
            self.assertEqual(result["status"], status)


if __name__ == "__main__":
    unittest.main()
