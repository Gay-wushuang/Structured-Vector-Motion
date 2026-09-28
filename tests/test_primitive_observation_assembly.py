import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from svm import AdapterRequest, ProposalAcceptor, RevisionStore, Transaction
from svm.adapters import (
    OpenCVAnalysisAdapter,
    TemporalCorrespondenceAdapter,
)
from svm.adapters.primitive_observation_assembly import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    MEDIA,
    POLICY,
    SCHEMA,
    PrimitiveObservationAssemblyAdapter,
)
from svm.adapters.raster_primitive_observation_proposal import (
    RasterPrimitiveObservationProposalAdapter,
)
from svm.adapters.temporal_correspondence import (
    OBSERVATION_MEDIA_TYPE_V2,
    read_primitive_observations,
)
from svm.artifacts import ArtifactKind, ArtifactStore
from svm.evaluator import canonical_bytes
from svm.proposals import ProposalArtifactError, ProposalConflictError, ProposalPolicyError
from svm.revisions import AppendReferencesChange
from svm.video_ingestion import VideoSampling, ingest_video

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/041-primitive-observation-assembly/scene.avi"
ZERO_SUPPORTED_FIXTURE = ROOT / "examples/041-primitive-observation-assembly/zero-supported.avi"


class PrimitiveObservationAssemblyTest(unittest.TestCase):
    def setUp(self):
        self.artifacts = ArtifactStore()
        self.source = self.artifacts.import_bytes(
            FIXTURE.read_bytes(), media_type="video/x-msvideo"
        )
        self.video = ingest_video(
            self.artifacts, self.source.document_reference(), VideoSampling((1, 2), 12)
        )
        document = json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_text())
        self.store = RevisionStore.create(document)
        self.accept_refs(self.source, *self.video.frames, self.video.manifest)
        self.analyses = tuple(self.analyze(frame) for frame in self.video.frames)
        p2a = []
        for analysis in self.analyses:
            proposal = self.propose_p2a(analysis)
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)
            p2a.append(proposal)
        self.p2a = tuple(p2a)
        self.evidence_ids = tuple(
            proposal.preview_artifacts[0].artifact_id for proposal in self.p2a
        )

    def accept_refs(self, *snapshots):
        self.store.commit(
            self.store.head,
            Transaction(
                "transaction:p2b-fixture-references",
                (AppendReferencesChange(tuple(item.document_reference() for item in snapshots)),),
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

    def propose_p2a(self, analysis, manifest=None):
        return RasterPrimitiveObservationProposalAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(analysis.artifact_id, (manifest or self.video.manifest).artifact_id),
            ),
            self.artifacts,
        )

    def propose(self, artifact_ids=None):
        return PrimitiveObservationAssemblyAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=artifact_ids or self.evidence_ids,
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

    def payloads(self, proposal):
        observation = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        evidence = self.artifacts.get(proposal.preview_artifacts[1].artifact_id)
        return observation, evidence, json.loads(observation.content), json.loads(evidence.content)

    def test_happy_path_preserves_supported_order_multiplicity_and_audit(self):
        first = self.propose()
        second = self.propose()
        self.assertEqual(first, second)
        observation, evidence, payload, audit = self.payloads(first)
        self.assertEqual(
            (observation.kind, observation.media_type),
            (ArtifactKind.REFERENCE, OBSERVATION_MEDIA_TYPE_V2),
        )
        self.assertEqual((evidence.kind, evidence.media_type), (ArtifactKind.DERIVED, MEDIA))
        self.assertEqual(audit["schema_version"], SCHEMA)
        self.assertEqual(payload["schema_version"], "svm-primitive-observations-0.2")
        self.assertEqual(payload["canvas"], [320, 240])
        self.assertEqual([frame["tick"] for frame in payload["frames"]], [12, 24])
        self.assertEqual([len(frame["primitives"]) for frame in payload["frames"]], [2, 2])
        p2a_payloads = [
            json.loads(self.artifacts.get(evidence_id).content) for evidence_id in self.evidence_ids
        ]
        for frame_index, (frame, source, audit_frame) in enumerate(
            zip(payload["frames"], p2a_payloads, audit["frames"], strict=True)
        ):
            supported = [item for item in source["evaluations"] if item["status"] == "SUPPORTED"]
            self.assertEqual(
                [item["candidate_id"] for item in audit_frame["included"]],
                [item["candidate_id"] for item in supported],
            )
            self.assertEqual(
                [item["geometry"]["points"] for item in frame["primitives"]],
                [item["ordered_landmarks"] for item in supported],
            )
            self.assertEqual([item["fill"] for item in frame["primitives"]], ["#000000"] * 2)
            self.assertEqual(len(audit_frame["excluded"]), 2)
            self.assertEqual(
                [item["status"] for item in audit_frame["excluded"]],
                ["UNCERTAIN", "REJECTED"],
            )
            self.assertEqual(
                audit_frame["counts"]["statuses"], {"SUPPORTED": 2, "UNCERTAIN": 1, "REJECTED": 1}
            )
            for primitive in frame["primitives"]:
                self.assertRegex(primitive["observation_id"], r"^observation:p2b:[0-9a-f]{64}$")
            for primitive, evaluation in zip(frame["primitives"], supported, strict=True):
                provenance = source["occurrence_provenance"]
                identity = {
                    "policy_identity": POLICY,
                    "adapter_id": ADAPTER_ID,
                    "adapter_version": ADAPTER_VERSION,
                    "source_p2a_evidence_artifact_id": self.evidence_ids[frame_index],
                    "p2a_candidate_id": evaluation["candidate_id"],
                    "manifest_artifact_id": provenance["manifest_artifact_id"],
                    "occurrence_id": provenance["occurrence_id"],
                    "frame_index": provenance["frame_index"],
                    "tick": provenance["tick"],
                    "component_digest": evaluation["component_digest"],
                }
                self.assertEqual(
                    primitive["observation_id"],
                    "observation:p2b:" + hashlib.sha256(canonical_bytes(identity)).hexdigest(),
                )
        self.assertEqual(payload["frames"][0]["primitives"][0]["bounds"], [30, 30, 101, 71])
        self.assertEqual(payload["frames"][1]["primitives"][0]["bounds"], [40, 30, 111, 71])
        self.assertNotEqual(
            payload["frames"][0]["primitives"][0]["observation_id"],
            payload["frames"][0]["primitives"][1]["observation_id"],
        )
        self.assertEqual(read_primitive_observations(observation.content), payload)

    def test_acceptance_appends_only_outputs_and_r0_consumes_observation(self):
        proposal = self.propose()
        before = self.store.get_document(self.store.head)
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        after = self.store.get_document(revision.revision_id)
        self.assertEqual(after["references"][:-2], before["references"])
        self.assertEqual(
            [item["id"] for item in after["references"][-2:]],
            [item.artifact_id for item in proposal.preview_artifacts],
        )
        r0 = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(proposal.preview_artifacts[0].artifact_id,),
            ),
            self.artifacts,
        )
        self.assertEqual(len(r0.preview_artifacts), 1)

    def test_reference_order_and_request_authority(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        manifest = json.loads(self.video.manifest.content)
        expected_sources = [
            *self.evidence_ids,
            self.video.manifest.artifact_id,
            self.source.artifact_id,
        ]
        expected_sources.extend(item["raster_artifact_id"] for item in manifest["occurrences"])
        for analysis in self.analyses:
            data = json.loads(analysis.content)
            expected_sources.extend((analysis.artifact_id, data["binary_mask_artifact_id"]))
        expected = (
            proposal.preview_artifacts[0].artifact_id,
            proposal.preview_artifacts[1].artifact_id,
            *dict.fromkeys(expected_sources),
        )
        self.assertEqual(tuple(ref["id"] for ref in change.references), expected)
        self.assertEqual(proposal.required_artifact_ids, expected)
        self.fails_atomically(lambda: self.propose((self.evidence_ids[0], self.evidence_ids[0])))
        self.fails_atomically(lambda: self.propose(tuple(reversed(self.evidence_ids))))

    def test_different_manifest_and_stale_proposal_reject(self):
        other = ingest_video(
            self.artifacts, self.source.document_reference(), VideoSampling((2,), 24)
        )
        self.accept_refs(other.manifest)
        other_p2a = self.propose_p2a(self.analyses[1], other.manifest)
        ProposalAcceptor().accept(self.store, other_p2a, self.artifacts)
        other_id = other_p2a.preview_artifacts[0].artifact_id
        self.fails_atomically(lambda: self.propose((self.evidence_ids[0], other_id)))
        stale = self.propose()
        extra = self.artifacts.import_bytes(b"stale", media_type="text/plain")
        self.accept_refs(extra)
        self.fails_atomically(lambda: ProposalAcceptor().accept(self.store, stale, self.artifacts))

    def test_zero_supported_frame_rejects_whole_assembly(self):
        source = self.artifacts.import_bytes(
            ZERO_SUPPORTED_FIXTURE.read_bytes(), media_type="video/x-msvideo"
        )
        video = ingest_video(self.artifacts, source.document_reference(), VideoSampling((1, 2), 12))
        self.accept_refs(source, *video.frames, video.manifest)
        evidence_ids = []
        for frame in video.frames:
            analysis = self.analyze(frame)
            p2a = self.propose_p2a(analysis, video.manifest)
            ProposalAcceptor().accept(self.store, p2a, self.artifacts)
            evidence_ids.append(p2a.preview_artifacts[0].artifact_id)
        self.fails_atomically(lambda: self.propose(tuple(evidence_ids)))

    def test_forged_p2a_candidate_landmarks_and_malformed_values_reject_at_acceptance(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        original = self.artifacts.get(self.evidence_ids[0])
        original_document = self.store.get_document(self.store.head)
        payload = json.loads(original.content)
        supported = next(item for item in payload["evaluations"] if item["status"] == "SUPPORTED")
        candidate = json.loads(original.content)
        next(item for item in candidate["evaluations"] if item["status"] == "SUPPORTED")[
            "candidate_id"
        ] = "candidate:primitive-observation:" + "0" * 64
        landmarks = json.loads(original.content)
        next(item for item in landmarks["evaluations"] if item["status"] == "SUPPORTED")[
            "ordered_landmarks"
        ][0][0] += 1
        nonfinite = json.loads(original.content)
        next(item for item in nonfinite["evaluations"] if item["status"] == "SUPPORTED")[
            "ordered_landmarks"
        ][0][0] = float("nan")
        self.assertIsNotNone(supported["candidate_id"])
        for content in (
            canonical_bytes(candidate),
            canonical_bytes(landmarks),
            canonical_bytes(nonfinite),
            b"{",
        ):
            with self.subTest(content=content):
                self.store = RevisionStore.create(original_document)
                altered = self.artifacts.import_bytes(
                    content,
                    media_type=original.media_type,
                    kind=original.kind,
                    provenance=original.provenance,
                )
                document = self.store.get_document(self.store.head)
                document["references"] = [
                    altered.document_reference() if ref["id"] == original.artifact_id else ref
                    for ref in document["references"]
                ]
                self.store = RevisionStore.create(document)
                sources = tuple(
                    altered.document_reference() if ref["id"] == original.artifact_id else ref
                    for ref in change.source_references
                )
                changed = replace(change, source_references=sources)
                forged = replace(
                    proposal,
                    base_revision_id=self.store.head,
                    transaction=replace(proposal.transaction, changes=(changed,)),
                    required_artifact_ids=tuple(ref["id"] for ref in changed.references),
                )
                self.fails_atomically(
                    lambda forged=forged: ProposalAcceptor().accept(
                        self.store, forged, self.artifacts
                    )
                )

    def test_forged_analysis_bounds_reject_at_acceptance(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        original_analysis = self.analyses[0]
        analysis_payload = json.loads(original_analysis.content)
        analysis_payload["components"][0]["bounds"][2] += 1
        forged_analysis = self.artifacts.import_bytes(
            canonical_bytes(analysis_payload),
            media_type=original_analysis.media_type,
            kind=original_analysis.kind,
            provenance=original_analysis.provenance,
        )
        original_evidence = self.artifacts.get(self.evidence_ids[0])
        evidence_payload = json.loads(original_evidence.content)
        evidence_payload["occurrence_provenance"]["analysis_artifact_id"] = (
            forged_analysis.artifact_id
        )
        for evaluation in evidence_payload["evaluations"]:
            evaluation["provenance"]["analysis_artifact_id"] = forged_analysis.artifact_id
        evidence_provenance = {
            **original_evidence.provenance,
            "analysis_artifact_id": forged_analysis.artifact_id,
        }
        forged_evidence = self.artifacts.import_bytes(
            canonical_bytes(evidence_payload),
            media_type=original_evidence.media_type,
            kind=original_evidence.kind,
            provenance=evidence_provenance,
        )
        document = self.store.get_document(self.store.head)
        replacements = {
            original_analysis.artifact_id: forged_analysis.document_reference(),
            original_evidence.artifact_id: forged_evidence.document_reference(),
        }
        document["references"] = [
            replacements.get(ref["id"], ref) for ref in document["references"]
        ]
        self.store = RevisionStore.create(document)
        sources = tuple(replacements.get(ref["id"], ref) for ref in change.source_references)
        changed = replace(change, source_references=sources)
        forged = replace(
            proposal,
            base_revision_id=self.store.head,
            transaction=replace(proposal.transaction, changes=(changed,)),
            required_artifact_ids=tuple(ref["id"] for ref in changed.references),
        )
        self.fails_atomically(lambda: ProposalAcceptor().accept(self.store, forged, self.artifacts))

    def test_tampered_outputs_wrong_policy_and_missing_dependency_reject_atomically(self):
        proposal = self.propose()
        change = proposal.transaction.changes[0]
        for index in (0, 1):
            original = self.artifacts.get(proposal.preview_artifacts[index].artifact_id)
            data = json.loads(original.content)
            if index == 0:
                data["frames"][0]["primitives"][0]["fill"] = "#FFFFFF"
            else:
                data["tampered"] = True
            altered = self.artifacts.import_bytes(
                canonical_bytes(data),
                media_type=original.media_type,
                kind=original.kind,
                provenance=original.provenance,
            )
            changed = replace(
                change,
                **{
                    "observation_reference"
                    if index == 0
                    else "evidence_reference": altered.document_reference()
                },
            )
            forged = replace(
                proposal,
                transaction=replace(proposal.transaction, changes=(changed,)),
                required_artifact_ids=tuple(ref["id"] for ref in changed.references),
            )
            self.fails_atomically(
                lambda forged=forged: ProposalAcceptor().accept(self.store, forged, self.artifacts)
            )
        wrong = replace(change, policy_identity=POLICY + "-wrong")
        forged = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(wrong,)),
            required_artifact_ids=tuple(ref["id"] for ref in wrong.references),
        )
        self.fails_atomically(lambda: ProposalAcceptor().accept(self.store, forged, self.artifacts))
        raster = next(ref for ref in change.source_references if ref["media_type"] == "image/png")
        forged_raster = json.loads(canonical_bytes(raster))
        forged_raster["import_metadata"]["provenance"] = {"forged": True}
        sources = tuple(
            forged_raster if ref["id"] == raster["id"] else ref for ref in change.source_references
        )
        changed = replace(change, source_references=sources)
        forged = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(changed,)),
            required_artifact_ids=tuple(ref["id"] for ref in changed.references),
        )
        self.fails_atomically(lambda: ProposalAcceptor().accept(self.store, forged, self.artifacts))
        document = self.store.get_document(self.store.head)
        missing = change.source_references[-1]["id"]
        document["references"] = [ref for ref in document["references"] if ref["id"] != missing]
        self.store = RevisionStore.create(document)
        self.fails_atomically(self.propose)


if __name__ == "__main__":
    unittest.main()
