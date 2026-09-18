from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    AttachPOPGeometryObservationsChange,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
)
from svm.adapters import (
    ObservedSimilarityMotionAdapter,
    POPGeometryObservationAdapter,
    POPGeometryObservationError,
    POPTokenExporter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
)
from svm.adapters.pop_geometry_observations import POLICY_IDENTITY, PRODUCER_IDENTITY
from svm.adapters.temporal_correspondence import (
    OBSERVATION_MEDIA_TYPE,
    OBSERVATION_MEDIA_TYPE_V2,
)
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "d5489b039d876839b58b61c512205713b3ab6909"
CHECKPOINT = "sha256:" + "4" * 64


def row(
    *,
    x: float,
    y: float,
    angle: float,
    width: float,
    height: float,
    shape: int,
    rgb: tuple[int, int, int],
) -> list[int]:
    return [
        round(x * 2),
        512 + round(y * 2),
        1024 + round(angle * 3),
        1294 + round(width * 4),
        1806 + round(height * 4),
        2318 + shape + 1,
        2574 + rgb[0] // 2,
        2702 + rgb[1] // 2,
        2830 + rgb[2] // 2,
    ]


def export_frame(
    artifacts: ArtifactStore,
    *,
    x: float,
    y: float,
    angle: float,
    width: float,
    height: float,
    shape: int = 0,
) -> tuple[Any, Any]:
    background = row(
        x=0,
        y=0,
        angle=0,
        width=100,
        height=100,
        shape=-1,
        rgb=(20, 20, 20),
    )
    primitive = row(
        x=x,
        y=y,
        angle=angle,
        width=width,
        height=height,
        shape=shape,
        rgb=(220, 40, 80),
    )
    return POPTokenExporter().export(
        artifacts,
        background + primitive,
        prefix_length=1,
        commit=COMMIT,
        model_id="fixture/pop-geometry",
        checkpoint_hash=CHECKPOINT,
        seed=7,
        decoding={
            "strategy": "field-aware-sampling",
            "target_steps": 2,
            "sampling_policy_identity": "pop/gpt-sampling-config@d5489b0",
            "configuration": {"schedule": "upstream-default"},
        },
    )


class POPGeometryObservationGoldenS41Test(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()

    def producer(self, *, square: bool = False):
        prefix, source = export_frame(
            self.artifacts, x=100, y=100, angle=0, width=40, height=40 if square else 20
        )
        _same_prefix, target = export_frame(
            self.artifacts,
            x=105,
            y=103,
            angle=30,
            width=60,
            height=60 if square else 30,
        )
        request = AdapterRequest.from_store(
            self.store,
            self.store.head,
            ("document",),
            artifact_ids=(prefix.artifact_id, source.artifact_id, target.artifact_id),
            options={
                "source_output_artifact_id": source.artifact_id,
                "target_output_artifact_id": target.artifact_id,
                "source_tick": 0,
                "target_tick": 24,
            },
        )
        return POPGeometryObservationAdapter().propose(request, self.artifacts), source, target

    def forge_observation(self, proposal: Any, *, payload=None, provenance=None):
        original = self.artifacts.resolve_reference(
            proposal.transaction.changes[0].observation_reference
        )
        forged = self.artifacts.import_bytes(
            canonical_bytes(payload) if payload is not None else original.content,
            media_type=original.media_type,
            kind=original.kind,
            provenance=provenance if provenance is not None else original.provenance,
        )
        change = proposal.transaction.changes[0]
        forged_change = replace(change, observation_reference=forged.document_reference())
        required = tuple(
            forged.artifact_id if item == original.artifact_id else item
            for item in proposal.required_artifact_ids
        )
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(forged_change,)),
            required_artifact_ids=required,
        )

    def test_real_pop_producer_emits_deterministic_v02_geometry_and_provenance(self) -> None:
        first, source, target = self.producer()
        second = POPGeometryObservationAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=tuple(first.required_artifact_ids[1:]),
                options={
                    "source_output_artifact_id": source.artifact_id,
                    "target_output_artifact_id": target.artifact_id,
                    "source_tick": 0,
                    "target_tick": 24,
                },
            ),
            self.artifacts,
        )
        self.assertEqual(first.preview_artifacts, second.preview_artifacts)
        observation = self.artifacts.get(first.preview_artifacts[0].artifact_id)
        payload = json.loads(observation.content)
        self.assertEqual(payload["schema_version"], "svm-primitive-observations-0.2")
        geometry = payload["frames"][0]["primitives"][0]["geometry"]
        self.assertEqual(
            geometry["points"], [[80.0, 90.0], [120.0, 90.0], [120.0, 110.0], [80.0, 110.0]]
        )
        self.assertEqual(geometry["rotation_symmetry"], "half-turn")
        self.assertEqual(observation.media_type, OBSERVATION_MEDIA_TYPE_V2)
        self.assertEqual(observation.provenance["producer_identity"], PRODUCER_IDENTITY)
        self.assertEqual(observation.provenance["geometry_observation_policy"], POLICY_IDENTITY)
        self.assertEqual(
            observation.provenance["source_artifact_ids"],
            [source.artifact_id, target.artifact_id],
        )
        self.assertIsInstance(first.transaction.changes[0], AttachPOPGeometryObservationsChange)
        before = self.store.get_document(self.store.head)
        revision = ProposalAcceptor().accept(self.store, first, self.artifacts)
        after = self.store.get_document(revision.revision_id)
        for field in ("entities", "groups", "construction", "presentation", "animation"):
            self.assertEqual(after.get(field), before.get(field))
        self.assertEqual(
            {item["id"] for item in after["references"]}
            - {item["id"] for item in before["references"]},
            set(first.required_artifact_ids),
        )

    def test_acceptor_rejects_forged_points_symmetry_and_bounds(self) -> None:
        proposal, _source, _target = self.producer()
        original = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        for mutation in ("points", "symmetry", "bounds"):
            payload = json.loads(original.content)
            primitive = payload["frames"][0]["primitives"][0]
            if mutation == "points":
                primitive["geometry"]["points"][0][0] += 1
            elif mutation == "symmetry":
                primitive["geometry"]["rotation_symmetry"] = "none"
            else:
                primitive["bounds"][0] += 1
            forged = self.forge_observation(proposal, payload=payload)
            with self.subTest(mutation=mutation), self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_acceptor_rejects_every_forged_observation_provenance_field(self) -> None:
        proposal, _source, _target = self.producer()
        original = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        for field in (
            "source_artifact_ids",
            "source_prefix_artifact_ids",
            "source_format_identity",
            "source_adapter_identity",
            "geometry_observation_policy",
            "producer_identity",
            "producer_version",
        ):
            provenance = copy.deepcopy(original.provenance)
            provenance[field] = (
                ["artifact:" + "0" * 64] if isinstance(provenance[field], list) else "forged"
            )
            forged = self.forge_observation(proposal, provenance=provenance)
            with self.subTest(field=field), self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_acceptor_rejects_source_swap_tick_forgery_and_invalid_pop_provenance(self) -> None:
        proposal, source, target = self.producer()
        change = proposal.transaction.changes[0]
        prefix_id = json.loads(source.content)["generation_context"]["prefix_artifact_id"]
        _prefix, alternate = export_frame(
            self.artifacts, x=110, y=105, angle=45, width=70, height=35
        )
        swapped_change = replace(change, target_output_reference=alternate.document_reference())
        swapped_required = tuple(
            alternate.artifact_id if item == target.artifact_id else item
            for item in proposal.required_artifact_ids
        )
        swapped = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(swapped_change,)),
            required_artifact_ids=swapped_required,
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.store, swapped, self.artifacts)

        tick_change = replace(change, target_tick=25)
        tick_forgery = replace(
            proposal, transaction=replace(proposal.transaction, changes=(tick_change,))
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.store, tick_forgery, self.artifacts)

        forged_provenance = copy.deepcopy(source.provenance)
        forged_provenance["decoder_identity"] = "forged"
        forged_source = self.artifacts.import_bytes(
            source.content,
            media_type=source.media_type,
            kind=source.kind,
            provenance=forged_provenance,
        )
        invalid_source_change = replace(
            change, source_output_reference=forged_source.document_reference()
        )
        invalid_source = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(invalid_source_change,)),
        )
        self.assertIn(prefix_id, proposal.required_artifact_ids)
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.store, invalid_source, self.artifacts)

        broken_tokens = json.loads(source.content)
        broken_tokens["raw_tokens"][9] += 2
        broken_source = self.artifacts.import_bytes(
            canonical_bytes(broken_tokens),
            media_type=source.media_type,
            kind=source.kind,
            provenance=source.provenance,
        )
        broken_change = replace(change, source_output_reference=broken_source.document_reference())
        broken_required = tuple(
            broken_source.artifact_id if item == source.artifact_id else item
            for item in proposal.required_artifact_ids
        )
        broken_proposal = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(broken_change,)),
            required_artifact_ids=broken_required,
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.store, broken_proposal, self.artifacts)

    def test_r0_v01_v02_parity_and_square_symmetry(self) -> None:
        proposal, _source, _target = self.producer(square=True)
        v2 = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        payload = json.loads(v2.content)
        self.assertEqual(
            payload["frames"][0]["primitives"][0]["geometry"]["rotation_symmetry"],
            "quarter-turn",
        )
        v1_payload = copy.deepcopy(payload)
        v1_payload["schema_version"] = "svm-primitive-observations-0.1"
        for frame in v1_payload["frames"]:
            for primitive in frame["primitives"]:
                primitive.pop("geometry")
        v1 = self.artifacts.import_bytes(
            canonical_bytes(v1_payload),
            media_type=OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": "v0.1-compatibility-fixture"},
        )
        candidates = []
        for artifact in (v1, v2):
            result = TemporalCorrespondenceAdapter().propose(
                AdapterRequest.from_store(
                    self.store,
                    self.store.head,
                    ("document",),
                    artifact_ids=(artifact.artifact_id,),
                ),
                self.artifacts,
            )
            evidence = json.loads(
                self.artifacts.get(result.preview_artifacts[0].artifact_id).content
            )
            candidates.append(evidence["candidates"][0])
        for field in ("status", "support_score", "conflict_score", "displacement", "evidence"):
            self.assertEqual(candidates[0][field], candidates[1][field])

    def test_real_pop_to_r0_r1_s4_recovers_scale_and_accepts_evidence_only(self) -> None:
        producer, _source, _target = self.producer()
        ProposalAcceptor().accept(self.store, producer, self.artifacts)
        observation_id = producer.preview_artifacts[0].artifact_id
        r0 = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(observation_id,),
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, r0, self.artifacts)
        r0_id = r0.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(r0_id).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        r1 = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(r0_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, r1, self.artifacts)
        identity_id = r1.preview.temporal_identities[0].stable_identity_id
        before = self.store.get_document(self.store.head)
        s4 = ObservedSimilarityMotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(observation_id, r0_id),
                options={
                    "temporal_identity_id": identity_id,
                    "inference_ids": [candidate["inference_id"]],
                },
            ),
            self.artifacts,
        )
        interval = json.loads(self.artifacts.get(s4.preview_artifacts[0].artifact_id).content)[
            "intervals"
        ][0]
        self.assertEqual(interval["scale"]["status"], "SUPPORTED")
        self.assertAlmostEqual(interval["scale"]["value"], 1.5, places=9)
        self.assertEqual(interval["rotation_degrees"]["status"], "UNCERTAIN")
        self.assertEqual(interval["rotation_degrees"]["ambiguity"], "rotation_symmetry")
        accepted = ProposalAcceptor().accept(self.store, s4, self.artifacts)
        after = self.store.get_document(accepted.revision_id)
        for field in ("entities", "groups", "construction", "presentation", "animation"):
            self.assertEqual(after.get(field), before.get(field))

    def test_forged_or_unsupported_pop_source_is_rejected(self) -> None:
        producer, source, target = self.producer()
        prefix_id = json.loads(source.content)["generation_context"]["prefix_artifact_id"]
        prefix = self.artifacts.get(prefix_id)
        for mutate in ("provenance", "shape"):
            forged_store = ArtifactStore()
            forged_prefix = forged_store.import_bytes(
                prefix.content,
                media_type=prefix.media_type,
                kind=prefix.kind,
                provenance=prefix.provenance,
            )
            source_provenance = copy.deepcopy(source.provenance)
            source_content = source.content
            if mutate == "provenance":
                source_provenance["output_identity"] = "forged"
            else:
                value = json.loads(source_content)
                value["primitives"][0]["shape_type"] = "path"
                source_content = canonical_bytes(value)
            forged_source = forged_store.import_bytes(
                source_content,
                media_type=source.media_type,
                kind=source.kind,
                provenance=source_provenance,
            )
            forged_target = forged_store.import_bytes(
                target.content,
                media_type=target.media_type,
                kind=target.kind,
                provenance=target.provenance,
            )
            request = AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(
                    forged_prefix.artifact_id,
                    forged_source.artifact_id,
                    forged_target.artifact_id,
                ),
                options={
                    "source_output_artifact_id": forged_source.artifact_id,
                    "target_output_artifact_id": forged_target.artifact_id,
                    "source_tick": 0,
                    "target_tick": 24,
                },
            )
            with self.assertRaises(POPGeometryObservationError):
                POPGeometryObservationAdapter().propose(request, forged_store)


if __name__ == "__main__":
    unittest.main()
