"""Research-only local flicker preview entry point; no Document or Revision writes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pipeline import CLASSIFICATION, sha


def run_child(args: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, "-B", str(Path(__file__).resolve()), *args], capture_output=True, text=True
    )
    if result.returncode:
        raise ValueError(f"worker failed ({result.returncode}): {result.stderr[-2000:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimental local flicker candidate preview")
    parser.add_argument("mode", choices=["synthetic", "preview", "_worker", "_evaluate"])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--gt", type=Path)
    parser.add_argument("--objects", type=Path)
    parser.add_argument(
        "--method",
        choices=["B_roi_normalization", "C_low_frequency"],
        default="B_roi_normalization",
    )
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--feather", type=float, default=6)
    parser.add_argument("--max-gain", type=float, default=1.3)
    parser.add_argument("--sigma", type=float, default=6)
    args = parser.parse_args()
    try:
        out = args.output.resolve()
        if args.mode == "_worker":
            if args.gt or args.objects or not args.input or not args.mask:
                raise ValueError("worker accepts source and mask only, never ground truth")
            from pipeline import worker

            worker(
                args.input.resolve(),
                args.mask.resolve(),
                out,
                args.method,
                args.radius,
                args.feather,
                args.max_gain,
                args.sigma,
            )
            return 0
        if args.mode == "_evaluate":
            if not args.mask:
                raise ValueError("evaluation requires mask")
            from evaluate import evaluate

            evaluate(
                out,
                args.mask.resolve(),
                args.gt.resolve() if args.gt else None,
                args.objects.resolve() if args.objects else None,
            )
            return 0
        if args.gt or args.objects:
            raise ValueError("GT options are reserved for the internal offline evaluator")
        if args.mode == "preview" and (not args.input or not args.mask):
            raise ValueError("preview requires --input and --mask")
        if args.mode == "synthetic" and (args.input or args.mask):
            raise ValueError("synthetic mode generates its own source and mask")
        # Atomic reservation prevents overwriting another run or an input path.
        out.mkdir(parents=False, exist_ok=False)
        if args.mode == "synthetic":
            from synthetic import generate

            fixture = out / "synthetic_fixture"
            generate(fixture)
            source, mask = fixture / "source.avi", fixture / "roi.png"
        else:
            source, mask = args.input.resolve(), args.mask.resolve()
        source_hash, mask_hash = sha(source), sha(mask)
        run_child(
            [
                "_worker",
                "--input",
                str(source),
                "--mask",
                str(mask),
                "--output",
                str(out),
                "--method",
                args.method,
                "--radius",
                str(args.radius),
                "--feather",
                str(args.feather),
                "--max-gain",
                str(args.max_gain),
                "--sigma",
                str(args.sigma),
            ]
        )
        if sha(source) != source_hash or sha(mask) != mask_hash:
            raise ValueError("source or mask changed during processing")
        evaluation = ["_evaluate", "--output", str(out), "--mask", str(mask)]
        if args.mode == "synthetic":
            evaluation += [
                "--gt",
                str(fixture / "ground_truth.npy"),
                "--objects",
                str(fixture / "object_masks.npy"),
            ]
        run_child(evaluation)
        manifest = json.loads((out / "runtime-manifest.json").read_text(encoding="utf-8"))
        script_root = Path(__file__).resolve().parent
        manifest.update(
            {
                "artifact_classification": CLASSIFICATION,
                "input_classification": "SYNTHETIC"
                if args.mode == "synthetic"
                else "USER_PROVIDED_UNVALIDATED",
                "real_video_validation": "NOT_RUN",
                "ground_truth_isolation": (
                    "worker receives source and mask only; evaluator runs after worker exits"
                ),
                "metrics_sha256": sha(out / "metrics.json"),
                "code_sha256": {
                    name: sha(script_root / name)
                    for name in ["main.py", "pipeline.py", "evaluate.py", "synthetic.py"]
                },
                "intermediate_sha256": {
                    name: sha(out / name)
                    for name in [
                        "input_frames.npy",
                        "A_noop.npy",
                        "B_roi_normalization.npy",
                        "C_low_frequency.npy",
                    ]
                },
            }
        )
        if args.mode == "synthetic":
            manifest["synthetic_fixture"] = {
                "seed": 20261111,
                "ground_truth_sha256": sha(fixture / "ground_truth.npy"),
                "object_masks_sha256": sha(fixture / "object_masks.npy"),
            }
        with (out / "experiment-manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
        print(
            json.dumps(
                {
                    "output": str(out),
                    "classification": CLASSIFICATION,
                    "input": manifest["input_classification"],
                    "svm_acceptance": "NOT_IMPLEMENTED",
                },
                indent=2,
            )
        )
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"preview failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
