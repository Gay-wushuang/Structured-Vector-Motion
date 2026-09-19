import json
import unittest

from svm import AdapterRequest, ArtifactKind, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters import SVGGeometryObservationAdapter, SVGGeometryObservationError
from svm.adapters.svg_geometry_observations import derive_svg_polygon_observations


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


if __name__ == "__main__":
    unittest.main()
