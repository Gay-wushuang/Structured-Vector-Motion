"""Bounded, research-only video preview. No SVM acceptance authority."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import tracemalloc
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

CLASSIFICATION = "experimental-only-not-svm-evidence"
MAX_FRAMES = 120
MAX_PIXELS = 1280 * 720
MAX_RAW_BYTES = 256 * 1024 * 1024


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak_process_rss() -> int | None:
    """Peak resident bytes of this worker, including native allocations, not children."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                *[
                    (name, ctypes.c_size_t)
                    for name in (
                        "PeakWorkingSetSize",
                        "WorkingSetSize",
                        "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage",
                        "PagefileUsage",
                        "PeakPagefileUsage",
                    )
                ],
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_memory.restype = wintypes.BOOL
        if get_memory(current(), ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize)
        return None
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if __import__("sys").platform == "darwin" else value * 1024)
    except (ImportError, OSError):
        return None


def run(command: list[str], data: bytes | None = None) -> bytes:
    result = subprocess.run(command, input=data, capture_output=True)
    if result.returncode:
        raise ValueError(
            f"command failed: {command[0]}: {result.stderr.decode(errors='replace')[-1500:]}"
        )
    return result.stdout


def probe(path: Path, max_pixels: int = MAX_PIXELS, max_raw_bytes: int = MAX_RAW_BYTES) -> dict:
    args = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-show_frames",
        "-select_streams",
        "v:0",
        "-of",
        "json",
        str(path),
    ]
    data = json.loads(run(args))
    streams = data.get("streams", [])
    if len(streams) != 1:
        raise ValueError("exactly one selected video stream is required")
    stream = streams[0]
    width, height = int(stream["width"]), int(stream["height"])
    if stream.get("pix_fmt") not in {
        "bgr0",
        "bgr24",
        "gbrp",
        "rgb24",
        "yuv420p",
        "yuv422p",
        "yuv444p",
        "yuvj420p",
        "yuvj444p",
    }:
        raise ValueError("only supported 8-bit opaque color pixel formats are accepted")
    if stream.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
        raise ValueError("HDR transfer functions are unsupported")
    frames = data.get("frames", [])
    fps = Fraction(stream["avg_frame_rate"])
    tb = Fraction(stream["time_base"])
    if not 0 < width * height <= max_pixels or width % 2 or height % 2:
        raise ValueError("dimensions must be even and within the pixel limit")
    if not 2 <= len(frames) <= MAX_FRAMES or len(frames) * width * height * 3 > max_raw_bytes:
        raise ValueError("video frame count or decoded byte limit exceeded")
    if fps <= 0 or tb <= 0:
        raise ValueError("invalid frame rate or time base")
    pts = []
    for frame in frames:
        if "best_effort_timestamp" not in frame:
            raise ValueError("missing frame PTS")
        pts.append(int(frame["best_effort_timestamp"]))
    if pts[0] != 0 or any(Fraction(p) * tb != Fraction(i, 1) / fps for i, p in enumerate(pts)):
        raise ValueError("only zero-start exact constant-frame-rate timestamps are supported")
    all_streams = json.loads(
        run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)])
    )["streams"]
    video_streams = [s for s in all_streams if s.get("codec_type") == "video"]
    if len(video_streams) != 1 or any(
        s.get("codec_type") not in {"video", "audio"} for s in all_streams
    ):
        raise ValueError("multiple video or non-audio auxiliary streams are unsupported")
    if stream.get("tags", {}).get("rotate") or any(
        "rotation" in s for s in stream.get("side_data_list", [])
    ):
        raise ValueError("rotation metadata is unsupported")
    return {
        "width": width,
        "height": height,
        "frame_count": len(frames),
        "fps": str(fps),
        "time_base": str(tb),
        "pts": pts,
        "codec": stream.get("codec_name"),
        "pixel_format": stream.get("pix_fmt"),
        "color_space": stream.get("color_space", "unspecified"),
        "color_primaries": stream.get("color_primaries", "unspecified"),
        "color_transfer": stream.get("color_transfer", "unspecified"),
        "color_range": stream.get("color_range", "unspecified"),
        "audio_streams": [
            {"index": s["index"], "codec": s.get("codec_name")}
            for s in all_streams
            if s.get("codec_type") == "audio"
        ],
    }


def decode(path: Path, meta: dict) -> np.ndarray:
    raw = run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-",
        ]
    )
    expected = meta["frame_count"] * meta["height"] * meta["width"] * 3
    if len(raw) != expected:
        raise ValueError(f"decoded byte count mismatch: {len(raw)} != {expected}")
    return (
        np.frombuffer(raw, dtype=np.uint8)
        .reshape(meta["frame_count"], meta["height"], meta["width"], 3)
        .copy()
    )


def encode(path: Path, frames: np.ndarray, fps: str, *, lossless: bool = False) -> None:
    if path.exists():
        raise FileExistsError(path)
    height, width = frames.shape[1:3]
    codec = (
        ["-c:v", "ffv1", "-level", "3"]
        if lossless
        else ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
    )
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-n",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgr24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        fps,
        "-i",
        "-",
        "-map",
        "0:v:0",
        "-an",
        *codec,
        str(path),
    ]
    run(cmd, np.ascontiguousarray(frames).tobytes())


def alpha_mask(mask: np.ndarray, feather: float) -> np.ndarray:
    if mask.ndim != 2 or mask.dtype != np.uint8 or not set(np.unique(mask)).issubset({0, 255}):
        raise ValueError("mask must be a single-channel binary 0/255 PNG")
    if np.count_nonzero(mask) < 256 or feather <= 0:
        raise ValueError("mask too small or invalid feather")
    distance = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
    return np.minimum(distance / feather, 1.0).astype(np.float32)


def repair(
    frames: np.ndarray, mask: np.ndarray, radius: int, feather: float, max_gain: float, sigma: float
) -> tuple[dict[str, np.ndarray], dict]:
    if not 1 <= radius <= 8 or not 1.0 < max_gain <= 1.5 or not 1 <= sigma <= 32:
        raise ValueError("parameters outside supported bounds")
    if mask.shape != frames.shape[1:3]:
        raise ValueError("mask dimensions differ from video")
    alpha = alpha_mask(mask, feather)
    interior = alpha >= 0.99
    if np.count_nonzero(interior) < 128:
        raise ValueError("insufficient mask interior")
    lum = frames.astype(np.float32) @ np.array([0.114, 0.587, 0.299], dtype=np.float32)
    stats = np.array([np.median(x[interior]) for x in lum], dtype=np.float32)
    if np.any(stats < 8) or np.any(stats > 245):
        raise ValueError("ROI luminance too dark or clipped for reliable correction")
    # Abrupt global changes are treated as scene cuts, not flicker.
    small = [cv2.resize(x, (32, 32), interpolation=cv2.INTER_AREA) for x in lum]
    if any(float(np.mean(np.abs(a - b))) > 45 for a, b in zip(small, small[1:], strict=False)):
        raise ValueError("scene cut or excessive global motion detected")
    fields = np.stack([cv2.GaussianBlur(x, (0, 0), sigmaX=sigma) for x in lum])
    out_b, out_c, gains = [], [], []
    for i, frame in enumerate(frames):
        lo, hi = max(0, i - radius), min(len(frames), i + radius + 1)
        target = float(np.median(stats[lo:hi]))
        gain = float(np.clip(target / float(stats[i]), 1 / max_gain, max_gain))
        target_field = np.median(fields[lo:hi], axis=0)
        field_gain = np.clip(target_field / np.maximum(fields[i], 8), 1 / max_gain, max_gain)
        # Luminance-only gain retains channel ratios; never blend neighboring frames.
        base = frame.astype(np.float32)
        b = np.clip(np.rint(base * (1 + alpha[..., None] * (gain - 1))), 0, 255).astype(np.uint8)
        c = np.clip(
            np.rint(base * (1 + alpha[..., None] * (field_gain[..., None] - 1))), 0, 255
        ).astype(np.uint8)
        b[mask == 0] = frame[mask == 0]
        c[mask == 0] = frame[mask == 0]
        out_b.append(b)
        out_c.append(c)
        gains.append(gain)
    return {
        "A_noop": frames.copy(),
        "B_roi_normalization": np.stack(out_b),
        "C_low_frequency": np.stack(out_c),
    }, {"roi_median_luma": stats.tolist(), "b_gains": gains}


def worker(
    input_path: Path,
    mask_path: Path,
    out: Path,
    method: str,
    radius: int,
    feather: float,
    max_gain: float,
    sigma: float,
) -> None:
    start = time.perf_counter()
    tracemalloc.start()
    meta = probe(input_path)
    frames = decode(input_path, meta)
    mask = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise ValueError("cannot read mask PNG")
    outputs, diagnostic = repair(frames, mask, radius, feather, max_gain, sigma)
    if method not in outputs:
        raise ValueError("unknown method")
    output_names = [
        "input_frames.npy",
        "A_noop.npy",
        "B_roi_normalization.npy",
        "C_low_frequency.npy",
        "original_preview.mp4",
        "candidate.mp4",
        "comparison.mp4",
        "mask_preview.png",
        "runtime-manifest.json",
    ]
    if any((out / name).exists() for name in output_names):
        raise FileExistsError("worker refuses to replace existing output files")
    for name, value in outputs.items():
        if np.any(value[:, mask == 0] != frames[:, mask == 0]):
            raise ValueError(f"{name}: outside-ROI pre-encode invariant violated")
        with (out / f"{name}.npy").open("xb") as stream:
            np.save(stream, value, allow_pickle=False)
    with (out / "input_frames.npy").open("xb") as stream:
        np.save(stream, frames, allow_pickle=False)
    encoded = {
        "original_preview.mp4": frames,
        "candidate.mp4": outputs[method],
        "comparison.mp4": np.concatenate([frames, outputs[method]], axis=2),
    }
    for name, value in encoded.items():
        encode(out / name, value, meta["fps"])
    ok, mask_png = cv2.imencode(".png", mask)
    if not ok:
        raise ValueError("cannot write mask preview")
    with (out / "mask_preview.png").open("xb") as stream:
        stream.write(mask_png.tobytes())
    decoded = {}
    for name, value in encoded.items():
        output_scale = 2 if name == "comparison.mp4" else 1
        output_meta = probe(out / name, MAX_PIXELS * output_scale, MAX_RAW_BYTES * output_scale)
        if output_meta["frame_count"] != meta["frame_count"] or output_meta["fps"] != meta["fps"]:
            raise ValueError("output frame count or FPS differs")
        input_times = [str(Fraction(p) * Fraction(meta["time_base"])) for p in meta["pts"]]
        output_times = [
            str(Fraction(p) * Fraction(output_meta["time_base"])) for p in output_meta["pts"]
        ]
        if input_times != output_times:
            raise ValueError("output timestamps differ from input")
        decoded_frames = decode(out / name, output_meta)
        decoded[name] = {
            "probe": output_meta,
            "mae_vs_preencode": float(
                np.mean(np.abs(decoded_frames.astype(np.int16) - value.astype(np.int16)))
            ),
        }
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("ffmpeg and ffprobe must be available on PATH")
    manifest = {
        "artifact_classification": CLASSIFICATION,
        "scope": "research-candidate-only",
        "svm_acceptance": "NOT_IMPLEMENTED",
        "real_video_validation": "NOT_RUN",
        "source_sha256": sha(input_path),
        "mask_sha256": sha(mask_path),
        "input": meta,
        "selected_method": method,
        "parameters": {
            "temporal_radius_frames": radius,
            "feather_pixels": feather,
            "max_gain": max_gain,
            "gaussian_sigma": sigma,
        },
        "methods": list(outputs),
        "audio_processing": "DROPPED: output is silent; source audio is not preserved",
        "timing_contract": "zero-start exact CFR; timestamps compared as rational seconds",
        "color_processing": (
            "FFmpeg decodes to BGR24; multiplicative gain is applied in encoded BGR space; "
            "previews are lossy H.264 yuv420p, CRF 18"
        ),
        "preencode_outside_roi_identical": True,
        "output_decode": decoded,
        "runtime_seconds": time.perf_counter() - start,
        "python_tracemalloc_peak_bytes": peak,
        "worker_peak_rss_bytes": peak_process_rss(),
        "memory_scope": (
            "worker peak RSS includes native allocations; excludes FFmpeg child processes"
        ),
        "runtime_versions": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "ffmpeg": run(["ffmpeg", "-version"]).decode(errors="replace").splitlines()[0],
            "ffprobe": run(["ffprobe", "-version"]).decode(errors="replace").splitlines()[0],
            "ffmpeg_executable_sha256": sha(Path(ffmpeg)),
            "ffprobe_executable_sha256": sha(Path(ffprobe)),
        },
        "diagnostics": diagnostic,
        "artifacts": {
            name: sha(out / name)
            for name in [
                "original_preview.mp4",
                "candidate.mp4",
                "comparison.mp4",
                "mask_preview.png",
            ]
        },
    }
    with (out / "runtime-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
