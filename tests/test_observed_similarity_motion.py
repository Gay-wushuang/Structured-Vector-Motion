from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path
from typing import Any

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalConflictError,
    RevisionStore,
)
from svm.adapters import (
    ObservedSimilarityMotionAdapter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
)
from svm.adapters.temporal_correspondence import (
    OBSERVATION_MEDIA_TYPE,
    OBSERVATION_MEDIA_TYPE_V2,
)
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]


def transform_points(
    points: list[list[float]],
    *,
    angle: float = 0,
    scale: float = 1,
    translate: tuple[float, float] = (0, 0),
) -> list[list[float]]:
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    return [
        [
            translate[0] + scale * (cosine * x - sine * y),
            translate[1] + scale * (sine * x + cosine * y),
        ]
        for x, y in points
    ]


def primitive(
    observation_id: str,
    points: list[list[float]] | None,
    *,
    symmetry: str = "none",
    bounds: list[float] | None = None,
) -> dict[str, Any]:
    if bounds is None:
        assert points is not None
        bounds = [
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        ]
    result: dict[str, Any] = {
        "observation_id": observation_id,
        "primitive_type": "path",
        "bounds": bounds,
        "fill": "#FF0000",
    }
    if points is not None:
        result["geometry"] = {
            "type": "ordered-landmarks",
            "points": points,
            "rotation_symmetry": symmetry,
        }
    return result


class ObservedSimilarityMotionGoldenS4Test(unittest.TestCase):
    def setUp(self) -> None:
        document = json.loads(
            (ROOT / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
        )
        self.store = RevisionStore.create(document)
        self.artifacts = ArtifactStore()
        self.source_points = [[20.0, 20.0], [30.0, 20.0], [22.0, 28.0]]

    def establish(
        self,
        source: dict[str, Any],
        target: dict[str, Any],
        *,
        version: int = 2,
        source_tick: int = 0,
        target_tick: int = 24,
    ) -> tuple[str, str, str, str]:
        payload = {
            "schema_version": f"svm-primitive-observations-0.{version}",
            "canvas": [400, 400],
            "frames": [
                {"tick": source_tick, "primitives": [source]},
                {"tick": target_tick, "primitives": [target]},
            ],
        }
        geometry = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=OBSERVATION_MEDIA_TYPE_V2 if version == 2 else OBSERVATION_MEDIA_TYPE,
            kind=ArtifactKind.REFERENCE,
            provenance={"provider": f"fixture-observed-geometry@0.{version}"},
        )
        correspondence = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(geometry.artifact_id,),
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, correspondence, self.artifacts)
        r0_id = correspondence.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(r0_id).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        promotion = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(r0_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.store, promotion, self.artifacts)
        return (
            geometry.artifact_id,
            r0_id,
            candidate["inference_id"],
            promotion.preview.temporal_identities[0].stable_identity_id,
        )

    def propose(self, geometry_id: str, r0_id: str, inference_id: str, identity_id: str):
        return ObservedSimilarityMotionAdapter().propose(
            AdapterRequest.from_store(
                self.store,
                self.store.head,
                ("document",),
                artifact_ids=(geometry_id, r0_id),
                options={
                    "temporal_identity_id": identity_id,
                    "inference_ids": [inference_id],
                },
            ),
            self.artifacts,
        )

    def interval_for(
        self,
        target_points: list[list[float]],
        *,
        symmetry: str = "none",
    ) -> tuple[dict[str, Any], Any]:
        geometry_id, r0_id, inference_id, identity_id = self.establish(
            primitive("observation:a", self.source_points, symmetry=symmetry),
            primitive("observation:b", target_points, symmetry=symmetry),
        )
        proposal = self.propose(geometry_id, r0_id, inference_id, identity_id)
        payload = json.loads(self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content)
        return payload["intervals"][0], proposal

    def test_supported_rotation_and_uniform_scale(self) -> None:
        rotation, _ = self.interval_for(
            transform_points(self.source_points, angle=30, translate=(15, -4))
        )
        self.assertEqual(rotation["status"], "SUPPORTED")
        self.assertAlmostEqual(rotation["rotation_degrees"]["value"], 30)
        self.assertAlmostEqual(rotation["scale"]["value"], 1)

        scale, _ = self.interval_for(
            transform_points(self.source_points, scale=1.75, translate=(5, 8))
        )
        self.assertEqual(scale["status"], "SUPPORTED")
        self.assertAlmostEqual(scale["rotation_degrees"]["value"], 0)
        self.assertAlmostEqual(scale["scale"]["value"], 1.75)

    def test_combined_similarity_recovers_transform_and_residual(self) -> None:
        interval, _ = self.interval_for(
            transform_points(self.source_points, angle=-42, scale=1.2, translate=(10, 30))
        )
        self.assertEqual(interval["status"], "SUPPORTED")
        self.assertAlmostEqual(interval["rotation_degrees"]["value"], -42)
        self.assertAlmostEqual(interval["scale"]["value"], 1.2)
        self.assertLessEqual(interval["fit"]["normalized_rms"], 1e-6)
        self.assertEqual(interval["origin"], [24.0, 22.6666666667])

    def test_symmetric_rotation_is_uncertain_without_losing_scale_evidence(self) -> None:
        interval, _ = self.interval_for(
            transform_points(self.source_points, angle=35, scale=1.2),
            symmetry="continuous",
        )
        self.assertEqual(interval["status"], "UNCERTAIN")
        self.assertEqual(interval["rotation_degrees"]["status"], "UNCERTAIN")
        self.assertIsNone(interval["rotation_degrees"]["value"])
        self.assertEqual(interval["rotation_degrees"]["ambiguity"], "rotation_symmetry")
        self.assertEqual(interval["scale"]["status"], "SUPPORTED")

    def test_v01_aabb_abstains_and_translation_pipeline_remains_compatible(self) -> None:
        geometry_id, r0_id, inference_id, identity_id = self.establish(
            primitive("observation:a", None, bounds=[10, 10, 20, 20]),
            primitive("observation:b", None, bounds=[30, 15, 40, 25]),
            version=1,
        )
        proposal = self.propose(geometry_id, r0_id, inference_id, identity_id)
        interval = json.loads(
            self.artifacts.get(proposal.preview_artifacts[0].artifact_id).content
        )["intervals"][0]
        self.assertEqual(interval["status"], "UNCERTAIN")
        self.assertEqual(interval["reason"], "insufficient_geometry")
        self.assertIsNone(interval["rotation_degrees"]["value"])
        self.assertIsNone(interval["scale"]["value"])

    def test_non_uniform_deformation_and_reflection_are_rejected(self) -> None:
        non_uniform = [[2 * x + 10, y - 3] for x, y in self.source_points]
        interval, _ = self.interval_for(non_uniform)
        self.assertEqual(interval["status"], "REJECTED")
        self.assertEqual(interval["reason"], "non_uniform_deformation")

        reflected = [[80 - x, y + 5] for x, y in self.source_points]
        interval, _ = self.interval_for(reflected)
        self.assertEqual(interval["status"], "REJECTED")
        self.assertEqual(interval["reason"], "reflection")

    def test_preview_is_pure_and_accept_is_evidence_only(self) -> None:
        geometry_id, r0_id, inference_id, identity_id = self.establish(
            primitive("observation:a", self.source_points),
            primitive(
                "observation:b",
                transform_points(self.source_points, angle=20, scale=1.1, translate=(8, 4)),
            ),
        )
        before = self.store.get_document(self.store.head)
        proposal = self.propose(geometry_id, r0_id, inference_id, identity_id)
        self.assertEqual(self.store.get_document(self.store.head), before)
        self.assertEqual(proposal.preview.intervals[0].status, "SUPPORTED")
        revision = ProposalAcceptor().accept(self.store, proposal, self.artifacts)
        after = self.store.get_document(revision.revision_id)
        for field in ("entities", "groups", "construction", "presentation", "animation"):
            self.assertEqual(after.get(field), before.get(field))
        self.assertEqual(len(after["references"]), len(before["references"]) + 1)
        self.assertEqual(after["animation"]["content"], [])

    def test_generation_is_deterministic_and_forged_fit_is_rejected(self) -> None:
        geometry_id, r0_id, inference_id, identity_id = self.establish(
            primitive("observation:a", self.source_points),
            primitive(
                "observation:b",
                transform_points(self.source_points, angle=20, scale=1.1, translate=(8, 4)),
            ),
        )
        first = self.propose(geometry_id, r0_id, inference_id, identity_id)
        second = self.propose(geometry_id, r0_id, inference_id, identity_id)
        self.assertEqual(first.preview_artifacts, second.preview_artifacts)
        original = self.artifacts.get(first.preview_artifacts[0].artifact_id)
        payload = json.loads(original.content)
        payload["intervals"][0]["scale"]["value"] = 99
        forged_artifact = self.artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=original.media_type,
            kind=ArtifactKind.DERIVED,
            provenance=original.provenance,
        )
        forged = copy.deepcopy(first)
        change = forged.transaction.changes[0]
        object.__setattr__(change, "evidence_reference", forged_artifact.document_reference())
        object.__setattr__(
            forged,
            "required_artifact_ids",
            (forged_artifact.artifact_id, *first.required_artifact_ids[1:]),
        )
        with self.assertRaisesRegex(ProposalArtifactError, "does not match frozen geometry"):
            ProposalAcceptor().accept(self.store, forged, self.artifacts)

    def test_stale_temporal_identity_proposal_is_rejected(self) -> None:
        geometry_id, r0_id, inference_id, identity_id = self.establish(
            primitive("observation:a", self.source_points),
            primitive("observation:b", transform_points(self.source_points, angle=10)),
        )
        proposal = self.propose(geometry_id, r0_id, inference_id, identity_id)
        self.establish(
            primitive("observation:b", transform_points(self.source_points, angle=10)),
            primitive("observation:c", transform_points(self.source_points, angle=15)),
            source_tick=24,
            target_tick=48,
        )
        with self.assertRaisesRegex(ProposalConflictError, "does not match head"):
            ProposalAcceptor().accept(self.store, proposal, self.artifacts)


if __name__ == "__main__":
    unittest.main()
