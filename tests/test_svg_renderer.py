import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from test_cli import run_cli
from test_golden_b import split_transaction

from svm import Evaluator, RevisionStore, build_evaluated_scene
from svm.renderers import SVGRenderer

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "001-head-basic.svm.json"
SHOWCASE = ROOT / "examples" / "004-styled-character.svm.json"
SHOWCASE_SVG = ROOT / "examples" / "rendered" / "004-styled-character.svg"
SVG_NAMESPACE = {"svg": "http://www.w3.org/2000/svg"}


class SVGRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_evaluated_scene_follows_render_stack_and_final_quality(self) -> None:
        evaluator = Evaluator(self.document)
        scene = build_evaluated_scene(self.document, evaluator)

        self.assertEqual(
            [entity.entity_id for entity in scene.entities],
            ["entity:hair", "entity:head", "entity:shield"],
        )
        self.assertEqual(scene.quality.value, "FINAL")
        self.assertEqual(
            evaluator.runtime["op:head_refine"].evaluated_quality.value,
            "FINAL",
        )

    def test_svg_is_deterministic_and_contains_paths_clip_and_provenance(self) -> None:
        scene = build_evaluated_scene(self.document, Evaluator(self.document))
        renderer = SVGRenderer()
        first = renderer.render(scene)
        second = renderer.render(scene)
        self.assertEqual(first, second)

        root = ET.fromstring(first)
        self.assertEqual(root.attrib["data-svm-document"], "document:golden-a")
        self.assertEqual(root.attrib["data-svm-quality"], "FINAL")
        entity_groups = root.findall(".//svg:g[@data-svm-entity]", SVG_NAMESPACE)
        self.assertEqual(
            [group.attrib["data-svm-entity"] for group in entity_groups],
            ["entity:hair", "entity:head", "entity:shield"],
        )
        self.assertIsNotNone(root.find(".//svg:clipPath", SVG_NAMESPACE))
        self.assertGreaterEqual(len(root.findall(".//svg:path", SVG_NAMESPACE)), 2)
        self.assertIsNotNone(root.find(".//svg:rect", SVG_NAMESPACE))
        for group in entity_groups:
            self.assertTrue(group.attrib["data-svm-value"].startswith("sha256:"))
        styles = {group.attrib["data-svm-entity"]: group.attrib for group in entity_groups}
        self.assertEqual(styles["entity:hair"]["fill"], "#6D4C41")
        self.assertEqual(styles["entity:shield"]["opacity"], "1")

    def test_split_selector_materializes_renderable_clip_geometry(self) -> None:
        source = json.loads(
            (ROOT / "examples" / "003-split-head.svm.json").read_text(encoding="utf-8")
        )
        store = RevisionStore.create(source)
        self.assertIsNotNone(store.head)
        revision = store.commit(store.head, split_transaction())
        split_document = store.get_document(revision.revision_id)
        scene = build_evaluated_scene(split_document, Evaluator(split_document))

        svg = SVGRenderer().render(scene)
        root = ET.fromstring(svg)
        entity_groups = root.findall(".//svg:g[@data-svm-entity]", SVG_NAMESPACE)
        self.assertEqual(
            [group.attrib["data-svm-entity"] for group in entity_groups],
            ["entity:face", "entity:hair", "entity:shield"],
        )
        self.assertGreaterEqual(len(root.findall(".//svg:clipPath", SVG_NAMESPACE)), 2)

    def test_render_svg_cli_writes_parseable_svg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "scene.svg"
            completed = run_cli(
                "render-svg",
                str(EXAMPLE),
                "--output",
                str(output),
                "--width",
                "640",
                "--height",
                "480",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["quality"], "FINAL")
            self.assertEqual(summary["entities"], 3)
            root = ET.parse(output).getroot()
            self.assertEqual(root.attrib["width"], "640")
            self.assertEqual(root.attrib["height"], "480")

    def test_checked_in_showcase_matches_renderer_byte_for_byte(self) -> None:
        document = json.loads(SHOWCASE.read_text(encoding="utf-8"))
        scene = build_evaluated_scene(document, Evaluator(document))
        generated = SVGRenderer().render(scene)
        self.assertEqual(generated.encode("utf-8"), SHOWCASE_SVG.read_bytes())


if __name__ == "__main__":
    unittest.main()
