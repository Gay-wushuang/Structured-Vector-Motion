from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from svm import AdapterRequest, ArtifactKind, ArtifactStore, ProposalAcceptor, RevisionStore
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
