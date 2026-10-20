from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from ..adapters.fogleman_primitive_svg import UPSTREAM_REPOSITORY

RUNNER_IDENTITY = "svm-fogleman-primitive-runner@0.1"
PRIMITIVE_MODES = {
    "combo": 0,
    "triangle": 1,
    "rectangle": 2,
    "ellipse": 3,
    "circle": 4,
    "rotated-rectangle": 5,
    "quadratic": 6,
    "rotated-ellipse": 7,
    "polygon": 8,
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_CAPTURE_BYTES = 1024 * 1024
MAX_PREVIEW_BYTES = 64 * 1024 * 1024


class PrimitiveToolError(ValueError):
    pass


@dataclass(frozen=True)
class PrimitiveRunConfig:
    shape_count: int = 50
    mode: str = "combo"
    alpha: int = 128
    input_size: int = 256
    output_size: int = 1024
    workers: int = 1
    timeout_seconds: float = 300.0

    def validate(self) -> None:
        if not isinstance(self.shape_count, int) or not 1 <= self.shape_count <= 512:
            raise PrimitiveToolError("Primitive shape_count must be an integer from 1 to 512")
        if self.mode not in PRIMITIVE_MODES:
            raise PrimitiveToolError(f"Unsupported Primitive mode {self.mode!r}")
        if not isinstance(self.alpha, int) or not 0 <= self.alpha <= 255:
            raise PrimitiveToolError("Primitive alpha must be an integer from 0 to 255")
        for name, value in (
            ("input_size", self.input_size),
            ("output_size", self.output_size),
            ("workers", self.workers),
        ):
            if not isinstance(value, int) or value <= 0:
                raise PrimitiveToolError(f"Primitive {name} must be a positive integer")
        if self.workers > 64:
            raise PrimitiveToolError("Primitive workers must not exceed 64")
        if not 0 < self.timeout_seconds <= 3600:
            raise PrimitiveToolError("Primitive timeout_seconds must be in (0, 3600]")

    def recorded_parameters(self) -> dict[str, int | str]:
        return {
            "shape_count": self.shape_count,
            "mode": self.mode,
            "mode_id": PRIMITIVE_MODES[self.mode],
            "alpha": self.alpha,
            "input_size": self.input_size,
            "output_size": self.output_size,
            "workers": self.workers,
        }


@dataclass(frozen=True)
class PrimitiveExecution:
    raw_svg: bytes
    preview_png: bytes
    executable_sha256: str
    engine_commit: str
    parameters: dict[str, int | str]
    command: tuple[str, ...]
    elapsed_seconds: float
    stdout: str
    stderr: str


def run_primitive(
    executable: Path,
    source_png: Path,
    engine_commit: str,
    config: PrimitiveRunConfig,
) -> PrimitiveExecution:
    """Execute fogleman/primitive without granting it any Document authority."""

    config.validate()
    if re.fullmatch(r"[0-9a-f]{40}", engine_commit) is None:
        raise PrimitiveToolError("Primitive engine_commit must be a lowercase 40-hex Git commit")
    try:
        executable = executable.resolve(strict=True)
        source_png = source_png.resolve(strict=True)
    except OSError as exc:
        raise PrimitiveToolError(f"Cannot resolve Primitive input: {exc}") from exc
    if not executable.is_file():
        raise PrimitiveToolError("Primitive executable must be a file")
    if not source_png.is_file():
        raise PrimitiveToolError("Primitive source PNG must be a file")
    source_header = source_png.read_bytes()[: len(PNG_SIGNATURE)]
    if source_header != PNG_SIGNATURE:
        raise PrimitiveToolError("Primitive source must be a PNG file")

    executable_sha256 = _sha256_file(executable)
    with tempfile.TemporaryDirectory(prefix="svm-primitive-") as temporary_directory:
        temporary = Path(temporary_directory)
        raw_svg = temporary / "primitive.svg"
        preview_png = temporary / "primitive.png"
        command = (
            str(executable),
            "-i",
            str(source_png),
            "-o",
            str(raw_svg),
            "-o",
            str(preview_png),
            "-n",
            str(config.shape_count),
            "-m",
            str(PRIMITIVE_MODES[config.mode]),
            "-a",
            str(config.alpha),
            "-r",
            str(config.input_size),
            "-s",
            str(config.output_size),
            "-j",
            str(config.workers),
            "-v",
        )
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise PrimitiveToolError(
                f"Primitive execution exceeded {config.timeout_seconds:g} seconds"
            ) from exc
        except OSError as exc:
            raise PrimitiveToolError(f"Cannot execute Primitive: {exc}") from exc
        elapsed = time.perf_counter() - started
        stdout = _captured_text(completed.stdout, "stdout")
        stderr = _captured_text(completed.stderr, "stderr")
        if completed.returncode != 0:
            detail = stderr.strip() or stdout.strip() or "no diagnostic output"
            raise PrimitiveToolError(
                f"Primitive exited with status {completed.returncode}: {detail}"
            )
        try:
            svg_bytes = raw_svg.read_bytes()
            png_bytes = preview_png.read_bytes()
        except OSError as exc:
            raise PrimitiveToolError(
                f"Primitive did not produce both requested outputs: {exc}"
            ) from exc
        if not svg_bytes:
            raise PrimitiveToolError("Primitive produced an empty SVG")
        if len(png_bytes) > MAX_PREVIEW_BYTES or not png_bytes.startswith(PNG_SIGNATURE):
            raise PrimitiveToolError("Primitive produced an invalid or oversized PNG preview")

    recorded_command = (
        "primitive",
        "-i",
        "source.png",
        "-o",
        "primitive.svg",
        "-o",
        "primitive.png",
        *command[7:],
    )
    return PrimitiveExecution(
        raw_svg=svg_bytes,
        preview_png=png_bytes,
        executable_sha256=f"sha256:{executable_sha256}",
        engine_commit=engine_commit,
        parameters=config.recorded_parameters(),
        command=recorded_command,
        elapsed_seconds=elapsed,
        stdout=stdout,
        stderr=stderr,
    )


def producer_record(execution: PrimitiveExecution) -> dict[str, str]:
    return {
        "repository": UPSTREAM_REPOSITORY,
        "commit": execution.engine_commit,
        "executable_sha256": execution.executable_sha256,
        "randomness": "clock-seeded-no-upstream-seed-control",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _captured_text(content: bytes, name: str) -> str:
    if len(content) > MAX_CAPTURE_BYTES:
        raise PrimitiveToolError(f"Primitive {name} exceeded the 1 MiB capture limit")
    return content.decode("utf-8", errors="replace")
