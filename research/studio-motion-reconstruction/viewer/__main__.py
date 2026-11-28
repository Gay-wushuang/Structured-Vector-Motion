"""Build an offline, read-only preview of one Studio reconstruction candidate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import sys
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import cv2

from svm.video_ingestion import _avi_metadata

from ..run import CLASSIFICATION, MAX_SOURCE_BYTES, PROFILE, bounded_read, digest, frames

ASSETS = Path(__file__).resolve().parent
MAX_PNG_BYTES = 24 * 1024 * 1024


def load_view(input_path: Path, candidate_path: Path, *, synthetic: bool = False) -> dict[str, Any]:
    source = bounded_read(input_path, MAX_SOURCE_BYTES)
    candidate_bytes = bounded_read(candidate_path, 4 * 1024 * 1024)
    candidate = json.loads(candidate_bytes)
    if candidate["artifact_classification"] != CLASSIFICATION or candidate["profile"] != PROFILE:
        raise ValueError("Expected an experimental Studio flat-color translation candidate")
    meta = _avi_metadata(source)
    expected = {**meta, "sha256": digest(source), "byte_length": len(source)}
    if any(candidate["source"].get(key) != value for key, value in expected.items()):
        raise ValueError("Candidate source data does not match the supplied AVI")
    fps = Fraction(*meta["source_fps"])
    tick_rate = candidate["settings"]["ticks_per_second"]
    if type(tick_rate) is not int or not 1 <= tick_rate <= 100000:
        raise ValueError("Candidate has an invalid tick rate")
    decoded = frames(source, meta)
    previews = []
    size = 0
    try:
        for index, (record, frame) in enumerate(zip(candidate["frames"], decoded, strict=True)):
            if record["source_index"] != index or record["bgr24_sha256"] != digest(frame.tobytes()):
                raise ValueError(f"Decoded batch differs from candidate at frame {index}")
            seconds = index / fps
            if (
                record["time_seconds"] != [seconds.numerator, seconds.denominator]
                or record["tick"] != seconds * tick_rate
            ):
                raise ValueError(f"Candidate clock differs from the source at frame {index}")
            encoded, png = cv2.imencode(".png", frame)
            if not encoded:
                raise ValueError(f"Could not encode preview frame {index}")
            size += png.nbytes
            if size > MAX_PNG_BYTES:
                raise ValueError("Decoded previews exceeded the 24 MiB PNG budget")
            previews.append(base64.b64encode(png).decode("ascii"))
    finally:
        decoded.close()
    return {
        "candidate": candidate,
        "candidateSha256": digest(candidate_bytes),
        "sourcePngBase64": previews,
        "synthetic": synthetic,
    }


def build_html(data: dict[str, Any]) -> str:
    css = (ASSETS / "viewer.css").read_text(encoding="utf-8")
    script = (ASSETS / "viewer.js").read_text(encoding="utf-8")
    tokens = []
    for source in (script, css):
        value = base64.b64encode(hashlib.sha256(source.encode()).digest()).decode()
        tokens.append(f"'sha256-{value}'")
    csp = html.escape(
        f"default-src 'none'; script-src {tokens[0]}; style-src {tokens[1]}; "
        "img-src data:; base-uri 'none'; form-action 'none'",
        quote=True,
    )
    payload = json.dumps(data, allow_nan=False, ensure_ascii=True).replace("<", r"\u003c")
    template = (ASSETS / "viewer.html").read_text(encoding="utf-8")
    return (
        template.replace("{{CSP}}", csp)
        .replace("{{STYLE}}", css)
        .replace("{{SCRIPT}}", script)
        .replace("{{DATA}}", payload)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Original AVI/FFV1 source")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New .html file")
    parser.add_argument("--synthetic", action="store_true", help="Label the source as synthetic")
    args = parser.parse_args()
    try:
        if args.output.suffix.lower() != ".html":
            raise ValueError("Output must have an .html extension")
        if args.output.exists():
            raise ValueError("Output already exists")
        rendered = build_html(load_view(args.input, args.candidate, synthetic=args.synthetic))
        with TemporaryDirectory(prefix=".viewer-", dir=args.output.parent) as directory:
            staged = Path(directory) / "viewer.html"
            staged.write_bytes(rendered.encode("utf-8"))
            os.link(staged, args.output)
    except (ValueError, KeyError, TypeError, OSError, cv2.error) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
