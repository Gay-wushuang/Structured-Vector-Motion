from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image, ImageChops, ImageStat

UPSTREAM_COMMIT = "d5489b039d876839b58b61c512205713b3ab6909"
CHECKPOINT_SHA256 = "6492d34615b14e43ac9fc6b10496a490655bb28c31819b783cb6cb1e1fbd9f7b"
MODEL_ID = "doubixz/primitive-operation-painter-weight"
PREFIX_STEPS = 11
TARGET_STEPS = 144
TOKENS_PER_STEP = 9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the pinned upstream POP model and materialize Golden P evidence."
    )
    parser.add_argument("--upstream-dir", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--reuse-captured-output",
        type=Path,
        help="Resume after sampling from a canonical POP output captured by this runner.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def require_upstream(upstream_dir: Path, model_dir: Path) -> tuple[Path, Path]:
    upstream_dir = upstream_dir.resolve()
    model_dir = model_dir.resolve()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != UPSTREAM_COMMIT:
        raise RuntimeError(f"Expected upstream {UPSTREAM_COMMIT}, got {commit}")
    weights = model_dir / "model.safetensors"
    if sha256_file(weights) != CHECKPOINT_SHA256:
        raise RuntimeError("POP checkpoint SHA-256 does not match the pinned release")
    if not (model_dir / "config.json").is_file():
        raise RuntimeError("POP model config.json is missing")
    return upstream_dir, model_dir


def load_upstream(upstream_dir: Path) -> tuple[Any, Any, Any]:
    sys.path.insert(0, str(upstream_dir))
    example = importlib.import_module("example")
    pretrained = importlib.import_module("pretrained")
    visualize = importlib.import_module("visualize")
    return example, pretrained, visualize


def render_upstream(render_data: np.ndarray, canvas_size: int, output_path: Path) -> None:
    figure = plt.figure(figsize=(canvas_size / 100, canvas_size / 100), dpi=100)
    axis = figure.add_axes((0, 0, 1, 1))
    visualize = importlib.import_module("visualize")
    visualize.render_single_image(render_data, axis, canvas_size)
    figure.savefig(
        output_path,
        dpi=100,
        facecolor=axis.get_facecolor(),
        edgecolor="none",
        pad_inches=0,
    )
    plt.close(figure)


def rasterize_svg(svg_path: Path, png_path: Path) -> None:
    try:
        cairosvg = importlib.import_module("cairosvg")
    except (ImportError, OSError):
        browser = shutil.which("msedge") or shutil.which("chrome")
        if browser is None:
            candidates = (
                Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            )
            browser = next((str(path) for path in candidates if path.is_file()), None)
        if browser is None:
            raise RuntimeError("CairoSVG or a Chromium browser is required for parity") from None
        with tempfile.TemporaryDirectory(prefix="svm-pop-parity-") as profile:
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    f"--user-data-dir={profile}",
                    f"--screenshot={png_path}",
                    "--window-size=256,256",
                    svg_path.as_uri(),
                ],
                check=True,
                capture_output=True,
            )
        return
    cairosvg.svg2png(
        bytestring=svg_path.read_bytes(),
        write_to=str(png_path),
        output_width=256,
        output_height=256,
    )


def parity_metrics(upstream_png: Path, svm_png: Path) -> dict[str, int | float]:
    with Image.open(upstream_png) as upstream_source, Image.open(svm_png) as svm_source:
        upstream = upstream_source.convert("RGB")
        svm = svm_source.convert("RGB")
        if upstream.size != svm.size:
            raise RuntimeError("Parity images have different dimensions")
        difference = ImageChops.difference(upstream, svm)
        extrema = difference.getextrema()
        statistics = ImageStat.Stat(difference)
        changed_pixels = sum(1 for pixel in difference.get_flattened_data() if pixel != (0, 0, 0))
        return {
            "width": upstream.width,
            "height": upstream.height,
            "changed_pixels": changed_pixels,
            "changed_fraction": changed_pixels / (upstream.width * upstream.height),
            "mean_absolute_error": sum(statistics.mean) / 3,
            "max_channel_error": max(channel[1] for channel in extrema),
        }


def main() -> None:
    args = parse_args()
    if args.seed < 0:
        raise ValueError("--seed must be non-negative")
    upstream_dir, model_dir = require_upstream(args.upstream_dir, args.model_dir)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    example, pretrained, visualize = load_upstream(upstream_dir)

    torch.manual_seed(args.seed)
    groups = example.load_example_groups(
        upstream_dir / "example" / "sequences" / "v1" / "data_part_1.csv"
    )
    image_name, group = groups[0]
    prompt = visualize.encode_image_group(group, PREFIX_STEPS).unsqueeze(0)
    if prompt.shape != (1, PREFIX_STEPS * TOKENS_PER_STEP):
        raise RuntimeError("Upstream example prefix did not encode to eleven operations")
    if args.reuse_captured_output is None:
        model, release_config, _ = pretrained.load_pretrained(model_dir, device="cpu")
        predicted = visualize.generate(model, prompt, TARGET_STEPS * TOKENS_PER_STEP)
        raw_tokens = [int(token) for token in predicted[0].cpu().tolist()]
    else:
        captured = json.loads(args.reuse_captured_output.read_text(encoding="utf-8"))
        producer = captured.get("producer", {})
        if (
            captured.get("schema_version") != "svm-pop-output-0.2"
            or producer.get("commit") != UPSTREAM_COMMIT
            or producer.get("checkpoint_hash") != f"sha256:{CHECKPOINT_SHA256}"
            or producer.get("seed") != args.seed
            or producer.get("decoding", {}).get("strategy") != "field-aware-sampling"
            or captured.get("generation_context", {}).get("prefix_length") != PREFIX_STEPS
            or captured.get("generation_context", {}).get("target_steps") != TARGET_STEPS
        ):
            raise RuntimeError("Captured POP output does not match this pinned execution")
        raw_tokens = captured["raw_tokens"]
        release_config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        predicted = torch.tensor([raw_tokens], dtype=torch.long)
    if len(raw_tokens) != TARGET_STEPS * TOKENS_PER_STEP:
        raise RuntimeError("Upstream generation did not produce 144 complete operations")
    if raw_tokens[: prompt.numel()] != [int(token) for token in prompt[0].tolist()]:
        raise RuntimeError("Upstream generation changed the operation prefix")

    from svm import (
        AdapterRequest,
        ArtifactStore,
        Evaluator,
        ProposalAcceptor,
        RevisionStore,
        build_evaluated_scene,
    )
    from svm.adapters import POPOutputAdapter, POPTokenExporter
    from svm.renderers import SVGRenderer, SVGRenderOptions

    decoding = {
        "strategy": "field-aware-sampling",
        "target_steps": TARGET_STEPS,
        "sampling_policy_identity": "pop/gpt-sampling-config@d5489b0",
        "configuration": {"schedule": "upstream-default"},
    }
    artifacts = ArtifactStore()
    prefix, output = POPTokenExporter().export(
        artifacts,
        raw_tokens,
        prefix_length=PREFIX_STEPS,
        commit=UPSTREAM_COMMIT,
        model_id=MODEL_ID,
        checkpoint_hash=f"sha256:{CHECKPOINT_SHA256}",
        seed=args.seed,
        decoding=decoding,
        user_intent="real upstream Golden P execution; annotation is not a model input",
    )
    (output_dir / "operation-prefix.json").write_bytes(prefix.content)
    (output_dir / "pop-output.json").write_bytes(output.content)

    root = Path(__file__).resolve().parents[1]
    base_document = json.loads(
        (root / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
    )
    revisions = RevisionStore.create(base_document)
    request = AdapterRequest.from_store(
        revisions,
        revisions.head,
        ("document",),
        artifact_ids=(prefix.artifact_id, output.artifact_id),
        options={"namespace": "golden-p-real"},
    )
    proposal = POPOutputAdapter().propose(request, artifacts)
    acceptor = ProposalAcceptor()
    dry_run = acceptor.validate(revisions, proposal, artifacts)
    accepted_revision = acceptor.accept(revisions, proposal, artifacts)
    accepted = revisions.get_document(accepted_revision.revision_id)
    if dry_run != accepted:
        raise RuntimeError("POP preview/dry-run did not equal accepted Document")
    (output_dir / "accepted.svm.json").write_bytes(canonical_bytes(accepted))

    evaluator = Evaluator(accepted)
    evaluator.evaluate_all()
    svg = SVGRenderer(SVGRenderOptions(width=256, height=256, view_box=(0, 0, 256, 256))).render(
        build_evaluated_scene(accepted, evaluator)
    )
    svg_path = output_dir / "svm.svg"
    svg_path.write_text(svg, encoding="utf-8", newline="\n")
    upstream_png = output_dir / "upstream.png"
    svm_png = output_dir / "svm.png"
    render_data = visualize.decode_tokens_to_render_data(predicted[0])
    render_upstream(render_data, int(release_config["canvas"]["canvas_size"]), upstream_png)
    rasterize_svg(svg_path, svm_png)

    manifest = {
        "schema_version": "svm-pop-golden-p-run-0.1",
        "upstream": {
            "repository": "https://github.com/wonderfulearth/primitive-operation-painter",
            "commit": UPSTREAM_COMMIT,
            "example_image_name": image_name,
        },
        "model": {
            "model_id": MODEL_ID,
            "checkpoint_sha256": CHECKPOINT_SHA256,
        },
        "execution": {
            "seed": args.seed,
            "device": "cpu",
            "python": platform.python_version(),
            "torch": str(torch.__version__),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
            "prefix_steps": PREFIX_STEPS,
            "target_steps": TARGET_STEPS,
            "sampling_policy_identity": "pop/gpt-sampling-config@d5489b0",
        },
        "artifacts": {
            "prefix_artifact_id": prefix.artifact_id,
            "output_artifact_id": output.artifact_id,
            "proposal_id": proposal.proposal_id,
            "accepted_revision_id": accepted_revision.revision_id,
            "raw_token_sha256": hashlib.sha256(canonical_bytes(raw_tokens)).hexdigest(),
            "upstream_png_sha256": sha256_file(upstream_png),
            "svm_svg_sha256": sha256_file(svg_path),
            "svm_png_sha256": sha256_file(svm_png),
        },
        "render_parity": parity_metrics(upstream_png, svm_png),
    }
    (output_dir / "run-manifest.json").write_bytes(canonical_bytes(manifest))
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
