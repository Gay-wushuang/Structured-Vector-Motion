import json
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops, ImageStat

from svm import (
    AdapterRequest,
    ArtifactKind,
    ArtifactStore,
    Evaluator,
    ProposalPolicyError,
    RevisionStore,
    SetOperationParameterChange,
    Transaction,
)
from svm.adapters.fogleman_primitive_svg import (
    NORMALIZATION_IDENTITY,
    PrimitiveSVGError,
    normalize_primitive_svg,
)
from svm.adapters.svg_import import SVGImportAdapter, SVGImportError
from svm.change_authority import resolve_transaction_intents
from svm.external.fogleman_primitive import (
    PNG_SIGNATURE,
    PrimitiveExecution,
    PrimitiveRunConfig,
    PrimitiveToolError,
    run_primitive,
)
from svm.primitive_toolchain import (
    PrimitiveBundleError,
    replay_primitive_bundle,
    run_primitive_toolchain,
    write_primitive_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
EMPTY_DOCUMENT = ROOT / "examples" / "005-empty-canvas.svm.json"
GOLDEN = ROOT / "examples" / "047-fogleman-primitive-toolchain"
COMMIT = "0373c216458be1c4b40655b796a3aefedf8b7d23"
PNG = PNG_SIGNATURE + b"test-png-payload"
RAW_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="256" height="128">\n'
    b'<rect x="0" y="0" width="256" height="128" fill="#102030" />\n'
    b'<g transform="scale(2.000000) translate(0.5 0.5)">\n'
    b'<ellipse fill="#abcdef" fill-opacity="0.501961" '
    b'cx="10" cy="20" rx="3" ry="4" />\n'
    b'<polygon fill="#112233" fill-opacity="0.5" points="0,0 10,0 0,10" />\n'
    b'<g transform="translate(20 30) rotate(45) scale(8 4)">'
    b'<rect fill="#334455" fill-opacity="0.5" x="-0.5" y="-0.5" '
    b'width="1" height="1" /></g>\n'
    b'<g transform="translate(40.0 30.0) rotate(25.0) scale(8.0 4.0)">'
    b'<ellipse fill="#556677" fill-opacity="0.5" cx="0" cy="0" '
    b'rx="1" ry="1" /></g>\n'
    b'<path stroke="#778899" stroke-opacity="0.5" fill="none" '
    b'd="M 0.0 0.0 Q 5.0 10.0, 20.0 20.0" stroke-width="0.5" />\n'
    b"</g>\n</svg>"
)


class FoglemanPrimitiveSVGTest(unittest.TestCase):
    def test_pinned_output_vocabulary_lowers_to_existing_svg_import_subset(self) -> None:
        result = normalize_primitive_svg(RAW_SVG)
        self.assertEqual(result.width, 256)
        self.assertEqual(result.height, 128)
        self.assertEqual(result.shape_count, 6)
        root = ET.fromstring(result.content)
        self.assertEqual(root.attrib, {"viewBox": "0 0 256 128"})
        children = list(root)
        self.assertEqual(
            [element.tag.rsplit("}", 1)[-1] for element in children],
            ["rect", "ellipse", "path", "path", "path", "path"],
        )
        self.assertEqual(children[1].attrib["opacity"], "0.501961")
        self.assertNotIn("transform", result.content.decode("utf-8"))
        self.assertNotIn("fill-opacity", result.content.decode("utf-8"))

        document = json.loads(EMPTY_DOCUMENT.read_text(encoding="utf-8"))
        store = RevisionStore.create(document)
        artifacts = ArtifactStore()
        artifact = artifacts.import_bytes(
            result.content,
            media_type="image/svg+xml",
            kind=ArtifactKind.REFERENCE,
        )
        proposal = SVGImportAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(artifact.artifact_id,),
                options={"namespace": "primitive-test"},
            ),
            artifacts,
        )
        self.assertEqual(proposal.report.metrics["imported_shapes"], 6)
        self.assertEqual(
            resolve_transaction_intents(proposal.transaction),
            (("import_scene", "document", None),),
        )

    def test_raw_upstream_svg_is_rejected_by_core_import(self) -> None:
        document = json.loads(EMPTY_DOCUMENT.read_text(encoding="utf-8"))
        store = RevisionStore.create(document)
        artifacts = ArtifactStore()
        artifact = artifacts.import_bytes(RAW_SVG, media_type="image/svg+xml")
        request = AdapterRequest.from_store(
            store, store.head, ("document",), artifact_ids=(artifact.artifact_id,)
        )
        with self.assertRaisesRegex(SVGImportError, "height, version, width"):
            SVGImportAdapter().propose(request, artifacts)

    def test_unknown_or_drifted_producer_svg_fails_closed(self) -> None:
        cases = (
            (RAW_SVG.replace(b"scale(2.000000)", b"matrix(1 0 0 1 0 0)"), "global transform"),
            (RAW_SVG.replace(b"<ellipse fill=", b'<image href="x" fill='), "element"),
            (RAW_SVG.replace(b'fill-opacity="0.5"', b'fill-opacity="2"', 1), "opacity"),
        )
        for content, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(PrimitiveSVGError, message):
                    normalize_primitive_svg(content)


class FoglemanPrimitiveRunnerTest(unittest.TestCase):
    def test_runner_uses_argument_vector_and_snapshots_both_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            executable = root / "primitive.exe"
            source = root / "source.png"
            executable.write_bytes(b"binary")
            source.write_bytes(PNG)

            def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess:
                self.assertFalse(kwargs.get("shell", False))
                Path(command[4]).write_bytes(RAW_SVG)
                Path(command[6]).write_bytes(PNG)
                return subprocess.CompletedProcess(command, 0, b"", b"real log")

            with patch("svm.external.fogleman_primitive.subprocess.run", side_effect=fake_run):
                execution = run_primitive(
                    executable,
                    source,
                    COMMIT,
                    PrimitiveRunConfig(shape_count=3, mode="ellipse", workers=1),
                )
        self.assertEqual(execution.raw_svg, RAW_SVG)
        self.assertEqual(execution.preview_png, PNG)
        self.assertEqual(execution.engine_commit, COMMIT)
        self.assertEqual(
            execution.command[0:7],
            (
                "primitive",
                "-i",
                "source.png",
                "-o",
                "primitive.svg",
                "-o",
                "primitive.png",
            ),
        )
        self.assertEqual(execution.parameters["mode_id"], 3)

    def test_runner_rejects_unpinned_commit_and_non_png_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            executable = root / "primitive.exe"
            source = root / "source.png"
            executable.write_bytes(b"binary")
            source.write_bytes(b"not-png")
            with self.assertRaisesRegex(PrimitiveToolError, "engine_commit"):
                run_primitive(executable, source, "main", PrimitiveRunConfig())
            with self.assertRaisesRegex(PrimitiveToolError, "PNG"):
                run_primitive(executable, source, COMMIT, PrimitiveRunConfig())


class FoglemanPrimitiveBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(EMPTY_DOCUMENT.read_text(encoding="utf-8"))
        self.execution = PrimitiveExecution(
            raw_svg=RAW_SVG,
            preview_png=PNG,
            executable_sha256="sha256:" + "1" * 64,
            engine_commit=COMMIT,
            parameters=PrimitiveRunConfig(shape_count=5).recorded_parameters(),
            command=("primitive", "-i", "source.png", "-o", "primitive.svg"),
            elapsed_seconds=1.25,
            stdout="",
            stderr="",
        )

    def test_bundle_accepts_one_revision_and_replays_without_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "input.png"
            source.write_bytes(PNG)
            with patch("svm.primitive_toolchain.run_primitive", return_value=self.execution):
                bundle = run_primitive_toolchain(
                    self.document,
                    source,
                    root / "unused.exe",
                    COMMIT,
                    PrimitiveRunConfig(shape_count=5),
                    "golden",
                )
            output = root / "bundle"
            write_primitive_bundle(bundle, output)
            replay = replay_primitive_bundle(self.document, output)

            manifest = json.loads((output / "run-manifest.json").read_bytes())
            accepted = json.loads((output / "accepted.svm.json").read_text(encoding="utf-8"))
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["revision_id"], manifest["acceptance"]["revision_id"])
            self.assertEqual(manifest["normalization_identity"], NORMALIZATION_IDENTITY)
            self.assertEqual(manifest["acceptance"]["imported_entities"], 6)
            self.assertEqual(len(accepted["entities"]), 6)
            self.assertEqual(len(accepted["references"]), 1)
            self.assertEqual(
                accepted["references"][0]["import_metadata"]["provenance"]["producer"]["commit"],
                COMMIT,
            )

    def test_replay_rejects_tampered_frozen_svg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "input.png"
            source.write_bytes(PNG)
            with patch("svm.primitive_toolchain.run_primitive", return_value=self.execution):
                bundle = run_primitive_toolchain(
                    self.document,
                    source,
                    root / "unused.exe",
                    COMMIT,
                    PrimitiveRunConfig(shape_count=5),
                    "golden",
                )
            output = root / "bundle"
            write_primitive_bundle(bundle, output)
            (output / "primitive.svg").write_bytes(RAW_SVG + b"\n")
            with self.assertRaisesRegex(PrimitiveBundleError, "hash mismatch"):
                replay_primitive_bundle(self.document, output)

    def test_svg_import_permission_denial_blocks_the_toolchain(self) -> None:
        protected = json.loads(EMPTY_DOCUMENT.read_text(encoding="utf-8"))
        protected["edit_permissions"].append(
            {
                "id": "permission:no-primitive-import",
                "actor": "adapter:svg-import",
                "effect": "deny",
                "actions": ["import_scene"],
                "targets": ["document"],
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "input.png"
            source.write_bytes(PNG)
            with (
                patch("svm.primitive_toolchain.run_primitive", return_value=self.execution),
                self.assertRaisesRegex(ProposalPolicyError, "denies adapter:svg-import"),
            ):
                run_primitive_toolchain(
                    protected,
                    source,
                    root / "unused.exe",
                    COMMIT,
                    PrimitiveRunConfig(shape_count=5),
                    "denied",
                )

    def test_checked_in_real_run_replays_and_has_visual_parity(self) -> None:
        replay = replay_primitive_bundle(self.document, GOLDEN)
        self.assertEqual(
            replay["revision_id"],
            "revision:b421afd62c1fd52d7d95e0fd0a0ee69404dfa70cc2829e24aa2eac589d645f02",
        )
        accepted = json.loads((GOLDEN / "accepted.svm.json").read_text(encoding="utf-8"))
        self.assertEqual(len(accepted["entities"]), 13)
        self.assertEqual(len(accepted["construction"]["operations"]), 13)
        self.assertEqual(len(accepted["presentation"]["render_stack"]), 13)
        self.assertEqual(
            {operation["type"] for operation in accepted["construction"]["operations"]},
            {"CreateEllipse", "CreatePath", "CreateRectangle"},
        )

        store = RevisionStore.create(accepted)
        before = Evaluator(accepted)
        before.evaluate_all()
        ellipse = next(
            operation
            for operation in accepted["construction"]["operations"]
            if operation["type"] == "CreateEllipse"
        )
        edited_revision = store.commit(
            store.head,
            Transaction(
                "transaction:edit-primitive-ellipse",
                (
                    SetOperationParameterChange(
                        ellipse["id"], "cx", ellipse["parameters"]["cx"] + 1
                    ),
                ),
                "Edit one imported Primitive ellipse",
            ),
        )
        edited = store.get_document(edited_revision.revision_id)
        after = Evaluator(edited)
        after.evaluate_all()
        changed = {
            operation_id
            for operation_id in before.runtime
            if before.runtime[operation_id].outputs != after.runtime[operation_id].outputs
        }
        self.assertEqual(changed, {ellipse["id"]})
        self.assertEqual(
            [entity["id"] for entity in accepted["entities"]],
            [entity["id"] for entity in edited["entities"]],
        )

        with (
            Image.open(GOLDEN / "primitive.png") as native,
            Image.open(GOLDEN / "svm.png") as rendered,
        ):
            difference = ImageChops.difference(native.convert("RGBA"), rendered.convert("RGBA"))
        statistics = ImageStat.Stat(difference)
        self.assertLess(max(statistics.mean[:3]), 0.34)
        self.assertLessEqual(max(channel[1] for channel in difference.getextrema()[:3]), 77)


if __name__ == "__main__":
    unittest.main()
