from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from svm import (
    AdapterRequest,
    ArtifactStore,
    Evaluator,
    ProposalAcceptor,
    RevisionStore,
    build_evaluated_scene,
)
from svm.adapters import POPOutputAdapter, POPTokenExporter
from svm.evaluator import canonical_bytes
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "005-empty-canvas.svm.json"
REAL = ROOT / "examples" / "derived" / "020-pop-output" / "real"
OUTPUT_MEDIA_TYPE = "application/vnd.svm.pop-output+json"
PREFIX_MEDIA_TYPE = "application/vnd.svm.pop-token-prefix+json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class POPRealRunnerGoldenPTest(unittest.TestCase):
    def test_real_upstream_capture_replays_through_acceptance_and_rendering(self) -> None:
        manifest = json.loads((REAL / "run-manifest.json").read_text(encoding="utf-8"))
        payload = json.loads((REAL / "pop-output.json").read_text(encoding="utf-8"))
        prefix_payload = json.loads((REAL / "operation-prefix.json").read_text(encoding="utf-8"))
        producer = payload["producer"]

        self.assertEqual(
            manifest["upstream"]["commit"],
            "d5489b039d876839b58b61c512205713b3ab6909",
        )
        self.assertEqual(
            manifest["model"]["checkpoint_sha256"],
            "6492d34615b14e43ac9fc6b10496a490655bb28c31819b783cb6cb1e1fbd9f7b",
        )
        self.assertEqual(
            manifest["execution"]["sampling_policy_identity"],
            producer["decoding"]["sampling_policy_identity"],
        )
        self.assertEqual(len(payload["raw_tokens"]), 144 * 9)
        self.assertEqual(len(payload["primitives"]), 143)
        self.assertEqual(
            hashlib.sha256(canonical_bytes(payload["raw_tokens"])).hexdigest(),
            manifest["artifacts"]["raw_token_sha256"],
        )

        exported = ArtifactStore()
        prefix, output = POPTokenExporter().export(
            exported,
            payload["raw_tokens"],
            prefix_length=11,
            commit=producer["commit"],
            model_id=producer["model_id"],
            checkpoint_hash=producer["checkpoint_hash"],
            seed=producer["seed"],
            decoding=producer["decoding"],
            user_intent=payload["annotations"]["user_intent"],
        )
        self.assertEqual(prefix.content, canonical_bytes(prefix_payload))
        self.assertEqual(output.content, canonical_bytes(payload))
        self.assertEqual(prefix.artifact_id, manifest["artifacts"]["prefix_artifact_id"])
        self.assertEqual(output.artifact_id, manifest["artifacts"]["output_artifact_id"])

        document = json.loads(BASE.read_text(encoding="utf-8"))
        revisions = RevisionStore.create(document)
        request = AdapterRequest.from_store(
            revisions,
            revisions.head,
            ("document",),
            artifact_ids=(prefix.artifact_id, output.artifact_id),
            options={"namespace": "golden-p-real"},
        )
        proposal = POPOutputAdapter().propose(request, exported)
        self.assertEqual(proposal.proposal_id, manifest["artifacts"]["proposal_id"])
        self.assertEqual(proposal.report.metrics, {"primitives": 143.0})
        acceptor = ProposalAcceptor()
        dry_run = acceptor.validate(revisions, proposal, exported)
        revision = acceptor.accept(revisions, proposal, exported)
        accepted = revisions.get_document(revision.revision_id)
        self.assertEqual(accepted, dry_run)
        self.assertEqual(revision.revision_id, manifest["artifacts"]["accepted_revision_id"])

        evaluator = Evaluator(accepted)
        evaluator.evaluate_all()
        svg = SVGRenderer(
            SVGRenderOptions(width=256, height=256, view_box=(0, 0, 256, 256))
        ).render(build_evaluated_scene(accepted, evaluator))
        self.assertEqual(svg, (REAL / "svm.svg").read_text(encoding="utf-8"))
        self.assertEqual(_sha256(REAL / "svm.svg"), manifest["artifacts"]["svm_svg_sha256"])
        self.assertEqual(
            _sha256(REAL / "upstream.png"),
            manifest["artifacts"]["upstream_png_sha256"],
        )
        self.assertEqual(_sha256(REAL / "svm.png"), manifest["artifacts"]["svm_png_sha256"])

    def test_frozen_upstream_and_svm_rasters_meet_the_parity_contract(self) -> None:
        manifest = json.loads((REAL / "run-manifest.json").read_text(encoding="utf-8"))
        with (
            Image.open(REAL / "upstream.png") as upstream_source,
            Image.open(REAL / "svm.png") as svm_source,
        ):
            upstream = upstream_source.convert("RGB")
            svm = svm_source.convert("RGB")
            difference = ImageChops.difference(upstream, svm)
            statistics = ImageStat.Stat(difference)
            changed_pixels = sum(
                1 for pixel in difference.get_flattened_data() if pixel != (0, 0, 0)
            )
            metrics = {
                "width": upstream.width,
                "height": upstream.height,
                "changed_pixels": changed_pixels,
                "changed_fraction": changed_pixels / (upstream.width * upstream.height),
                "mean_absolute_error": sum(statistics.mean) / 3,
                "max_channel_error": max(channel[1] for channel in difference.getextrema()),
            }
        self.assertEqual(metrics, manifest["render_parity"])
        self.assertLess(metrics["mean_absolute_error"], 0.2)
        self.assertLessEqual(metrics["max_channel_error"], 33)


if __name__ == "__main__":
    unittest.main()
