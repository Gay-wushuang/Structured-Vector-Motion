import json
import unittest
from dataclasses import replace

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    ProposalAcceptor,
    ProposalArtifactError,
    RevisionStore,
)
from svm.adapters import (
    SVGGeometryObservationAdapter,
    SVGGeometryObservationError,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    ObservedSimilarityMotionAdapter,
)
from svm.adapters.svg_geometry_observations import derive_svg_polygon_observations
from svm.evaluator import canonical_bytes


DOC = {
    "format": "svm-document@0.1",
    "entities": [],
    "references": [],
    "construction": {"operations": [], "output_bindings": []},
    "presentation": {"styles": [], "render_stack": []},
    "animation": {"content": []},
}


def svg(path: str, *, shape_id: str = "arrow", fill: str = "#CC3344") -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        f'<path id="{shape_id}" fill="{fill}" d="{path}"/></svg>'
    ).encode()


def transformed(points, angle_degrees, scale, tx, ty):
    import math

    radians = math.radians(angle_degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    cx = sum(point[0] for point in points) / len(points)
    cy = sum(point[1] for point in points) / len(points)
    return [
        (
            cx + tx + scale * (cosine * (x - cx) - sine * (y - cy)),
            cy + ty + scale * (sine * (x - cx) + cosine * (y - cy)),
        )
        for x, y in points
    ]


def path(points):
    return "M " + " ".join(
        [f"{x:.12f} {y:.12f}" for x, y in points]
    ) + " Z"


class SVGGeometryObservationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.revisions = RevisionStore.create(DOC)
        self.artifacts = ArtifactStore()

    def request(self, source, target, shape_id="arrow"):
        return AdapterRequest.from_store(
            self.revisions,
            self.revisions.head,
            ("document",),
            artifact_ids=(source.artifact_id, target.artifact_id),
            options={
                "source_svg_artifact_id": source.artifact_id,
                "target_svg_artifact_id": target.artifact_id,
                "source_tick": 0,
                "target_tick": 24,
                "shape_id": shape_id,
            },
        )

    def test_real_polygon_is_ordered_and_deterministic(self):
        source = self.artifacts.import_bytes(
            svg("M 10 10 L 50 10 L 35 25 L 20 40 Z"),
            media_type="image/svg+xml",
        )
        target = self.artifacts.import_bytes(
            svg("M 10 10 L 44.6410161514 30 L 22.8108891325 34.1506350946 L 0 34.6410161514 Z"),
            media_type="image/svg+xml",
        )
        first = SVGGeometryObservationAdapter().propose(self.request(source, target), self.artifacts)
        second = SVGGeometryObservationAdapter().propose(self.request(source, target), self.artifacts)
        self.assertEqual(first.preview_artifacts, second.preview_artifacts)
        payload = json.loads(self.artifacts.get(first.preview_artifacts[0].artifact_id).content)
        primitive = payload["frames"][0]["primitives"][0]
        self.assertEqual(primitive["geometry"]["points"], [[10.0, 10.0], [50.0, 10.0], [35.0, 25.0], [20.0, 40.0]])
        self.assertEqual(primitive["geometry"]["rotation_symmetry"], "none")
        self.assertEqual(primitive["primitive_type"], "svg-polygonal-path")
        before = self.revisions.head
        ProposalAcceptor().accept(self.revisions, first, self.artifacts)
        self.assertEqual(len(self.revisions.get_document(self.revisions.head)["entities"]), 0)
        self.assertNotEqual(before, self.revisions.head)

    def test_curves_and_symmetry_abstain(self):
        source = self.artifacts.import_bytes(svg("M 0 0 C 1 2 3 4 5 6 Z"), media_type="image/svg+xml")
        target = self.artifacts.import_bytes(svg("M 0 0 C 1 2 3 4 5 6 Z"), media_type="image/svg+xml")
        with self.assertRaises(SVGGeometryObservationError):
            derive_svg_polygon_observations(source, target, "arrow", 0, 1)
        square = self.artifacts.import_bytes(svg("M 10 10 L 30 10 L 30 30 L 10 30 Z"), media_type="image/svg+xml")
        with self.assertRaises(SVGGeometryObservationError):
            derive_svg_polygon_observations(square, square, "arrow", 0, 1)

    def test_topology_and_selector_mismatch_abstain(self):
        source = self.artifacts.import_bytes(svg("M 10 10 L 50 10 L 35 25 L 20 40 Z"), media_type="image/svg+xml")
        target = self.artifacts.import_bytes(svg("M 10 10 L 50 10 L 35 25 L 20 40 L 10 20 Z"), media_type="image/svg+xml")
        with self.assertRaises(SVGGeometryObservationError):
            derive_svg_polygon_observations(source, target, "arrow", 0, 1)
        other = self.artifacts.import_bytes(svg("M 10 10 L 50 10 L 35 25 L 20 40 Z", shape_id="other"), media_type="image/svg+xml")
        with self.assertRaises(SVGGeometryObservationError):
            derive_svg_polygon_observations(source, other, "arrow", 0, 1)

    def _s4(self, source_points, angle, scale, tx, ty):
        source = self.artifacts.import_bytes(svg(path(source_points)), media_type="image/svg+xml")
        target_points = transformed(source_points, angle, scale, tx, ty)
        target = self.artifacts.import_bytes(svg(path(target_points)), media_type="image/svg+xml")
        producer = SVGGeometryObservationAdapter().propose(
            self.request(source, target), self.artifacts
        )
        ProposalAcceptor().accept(self.revisions, producer, self.artifacts)
        observation_id = producer.preview_artifacts[0].artifact_id
        r0 = TemporalCorrespondenceAdapter().propose(
            AdapterRequest.from_store(
                self.revisions, self.revisions.head, ("document",), artifact_ids=(observation_id,)
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.revisions, r0, self.artifacts)
        r0_id = r0.preview_artifacts[0].artifact_id
        candidate = json.loads(self.artifacts.get(r0_id).content)["candidates"][0]
        self.assertEqual(candidate["status"], "SUPPORTED")
        r1 = TemporalIdentityPromotionAdapter().propose(
            AdapterRequest.from_store(
                self.revisions,
                self.revisions.head,
                ("document",),
                artifact_ids=(r0_id,),
                options={"inference_ids": [candidate["inference_id"]]},
            ),
            self.artifacts,
        )
        ProposalAcceptor().accept(self.revisions, r1, self.artifacts)
        identity_id = r1.preview.temporal_identities[0].stable_identity_id
        s4 = ObservedSimilarityMotionAdapter().propose(
            AdapterRequest.from_store(
                self.revisions,
                self.revisions.head,
                ("document",),
                artifact_ids=(observation_id, r0_id),
                options={
                    "temporal_identity_id": identity_id,
                    "inference_ids": [candidate["inference_id"]],
                },
            ),
            self.artifacts,
        )
        return s4

    def test_real_plus_30_degree_rotation_e2e_is_supported(self):
        points = [(40.0, 40.0), (80.0, 40.0), (65.0, 55.0), (50.0, 75.0)]
        s4 = self._s4(points, 30.0, 1.0, 5.0, 4.0)
        interval = json.loads(self.artifacts.get(s4.preview_artifacts[0].artifact_id).content)[
            "intervals"
        ][0]
        self.assertEqual(interval["rotation_degrees"]["status"], "SUPPORTED")
        self.assertAlmostEqual(interval["rotation_degrees"]["value"], 30.0, places=7)
        self.assertEqual(interval["scale"]["status"], "SUPPORTED")
        self.assertAlmostEqual(interval["scale"]["value"], 1.0, places=7)

    def test_real_minus_25_degree_scaled_e2e_is_supported(self):
        points = [(40.0, 40.0), (80.0, 40.0), (65.0, 55.0), (50.0, 75.0)]
        s4 = self._s4(points, -25.0, 1.4, 7.0, -3.0)
        interval = json.loads(self.artifacts.get(s4.preview_artifacts[0].artifact_id).content)[
            "intervals"
        ][0]
        self.assertEqual(interval["rotation_degrees"]["status"], "SUPPORTED")
        self.assertAlmostEqual(interval["rotation_degrees"]["value"], -25.0, places=7)
        self.assertEqual(interval["scale"]["status"], "SUPPORTED")
        self.assertAlmostEqual(interval["scale"]["value"], 1.4, places=7)

    def test_equilateral_triangle_is_rejected_as_symmetric(self):
        triangle = self.artifacts.import_bytes(
            svg("M 50 20 L 24.0192378865 65 L 75.9807621135 65 Z"),
            media_type="image/svg+xml",
        )
        with self.assertRaises(SVGGeometryObservationError):
            derive_svg_polygon_observations(triangle, triangle, "arrow", 0, 1)

    def _forged_proposal(self, proposal, payload=None, *, change=None):
        original = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        forged = self.artifacts.import_bytes(
            canonical_bytes(payload) if payload is not None else original.content,
            media_type=original.media_type,
            kind=original.kind,
            provenance=original.provenance,
        )
        original_change = change or proposal.transaction.changes[0]
        forged_change = replace(original_change, observation_reference=forged.document_reference())
        required = tuple(
            forged.artifact_id if item == original.artifact_id else item
            for item in proposal.required_artifact_ids
        )
        return replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(forged_change,)),
            required_artifact_ids=required,
        )

    def test_acceptance_rejects_forged_observation_fields_and_sources(self):
        points = [(40.0, 40.0), (80.0, 40.0), (65.0, 55.0), (50.0, 75.0)]
        source = self.artifacts.import_bytes(svg(path(points)), media_type="image/svg+xml")
        target = self.artifacts.import_bytes(
            svg(path(transformed(points, 30.0, 1.0, 5.0, 4.0))), media_type="image/svg+xml"
        )
        proposal = SVGGeometryObservationAdapter().propose(self.request(source, target), self.artifacts)
        original = self.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        for field in ("points", "bounds", "symmetry"):
            payload = json.loads(original.content)
            primitive = payload["frames"][0]["primitives"][0]
            if field == "points":
                primitive["geometry"]["points"][0][0] += 1
            elif field == "bounds":
                primitive["bounds"][0] += 1
            else:
                primitive["geometry"]["rotation_symmetry"] = "quarter-turn"
            with self.subTest(field=field), self.assertRaises(ProposalArtifactError):
                ProposalAcceptor().accept(
                    self.revisions, self._forged_proposal(proposal, payload), self.artifacts
                )
        alternate = self.artifacts.import_bytes(
            svg(path(transformed(points, 10.0, 1.0, 2.0, 1.0))), media_type="image/svg+xml"
        )
        change = replace(
            proposal.transaction.changes[0], target_svg_reference=alternate.document_reference()
        )
        forged = replace(
            proposal,
            transaction=replace(proposal.transaction, changes=(change,)),
            required_artifact_ids=tuple(
                alternate.artifact_id if item == target.artifact_id else item
                for item in proposal.required_artifact_ids
            ),
        )
        with self.assertRaises(ProposalArtifactError):
            ProposalAcceptor().accept(self.revisions, forged, self.artifacts)


if __name__ == "__main__":
    unittest.main()
