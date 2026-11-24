"""Silent H.264 export and decoded-media verification via external tools."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .sequence import FPS, FRAME_COUNT, digest


class MediaError(ValueError):
    def __init__(self, message: str, *, exit_code: int = 6):
        super().__init__(message)
        self.exit_code = exit_code


def _tool(command: str) -> str:
    executable = shutil.which(command)
    if executable is None:
        raise MediaError(f"executable unavailable: {command}")
    return str(Path(executable).resolve())


def _run(arguments: list[str], output: Path, *, verify: bool = False) -> bytes:
    try:
        process = subprocess.run(
            arguments, cwd=output, capture_output=True, timeout=90, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaError(str(error), exit_code=7 if verify else 6) from error
    if process.returncode:
        raise MediaError(
            f"{Path(arguments[0]).name} exit {process.returncode}: "
            f"{process.stderr.decode(errors='replace').strip()}",
            exit_code=7 if verify else 6,
        )
    return process.stdout


def _verify(
    ffmpeg: str,
    ffprobe: str,
    path: str,
    output: Path,
    frames: np.ndarray,
    *,
    fps: int = FPS,
    frame_count: int = FRAME_COUNT,
) -> dict:
    probe_data = _run(
        [ffprobe, "-v", "error", "-show_streams", "-show_frames", "-of", "json", path],
        output,
        verify=True,
    )
    try:
        probe = json.loads(probe_data)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise MediaError(f"{path}: ffprobe returned invalid JSON", exit_code=7) from error
    if not isinstance(probe, dict):
        raise MediaError(f"{path}: ffprobe did not return a metadata object", exit_code=7)
    width = frames.shape[2]
    height = frames.shape[1]
    expected = {
        "codec_type": "video",
        "codec_name": "h264",
        "pix_fmt": "yuv420p",
        "width": width,
        "height": height,
        "r_frame_rate": f"{fps}/1",
        "avg_frame_rate": f"{fps}/1",
        "time_base": f"1/{fps}",
        "start_pts": 0,
        "duration_ts": frame_count,
        "nb_frames": str(frame_count),
        "color_range": "tv",
        "color_space": "bt709",
        "color_transfer": "bt709",
        "color_primaries": "bt709",
    }
    streams = probe.get("streams", [])
    if len(streams) != 1 or any(streams[0].get(key) != value for key, value in expected.items()):
        raise MediaError(f"{path}: ffprobe stream metadata mismatch: {streams}", exit_code=7)
    pts = [frame.get("best_effort_timestamp") for frame in probe.get("frames", [])]
    if pts != list(range(frame_count)):
        raise MediaError(
            f"{path}: expected contiguous decoded PTS 0..{frame_count - 1}, got {pts}",
            exit_code=7,
        )
    decoded = _run(
        [
            ffmpeg,
            "-v",
            "error",
            "-xerror",
            "-nostdin",
            "-i",
            path,
            "-map",
            "0:v:0",
            "-vf",
            "scale=in_color_matrix=bt709:in_range=tv:out_range=full,format=rgb24",
            "-fps_mode",
            "passthrough",
            "-c:v",
            "rawvideo",
            "-threads",
            "1",
            "-f",
            "rawvideo",
            "-",
        ],
        output,
        verify=True,
    )
    if len(decoded) != frames.size:
        raise MediaError(f"{path}: full RGB decode byte count mismatch", exit_code=7)
    rgb = np.frombuffer(decoded, dtype=np.uint8).reshape(frames.shape)
    per_frame = np.abs(rgb.astype(np.int16) - frames).mean(axis=(1, 2, 3))
    if per_frame.max() > 8:
        raise MediaError(f"{path}: decoded frame exceeds RGB MAE tolerance (8 DN)", exit_code=7)
    return {
        **expected,
        "decoded_frames": len(pts),
        "duration_seconds": frame_count / fps,
        "decoded_pixel_sha256": digest(decoded),
        "decoded_rgb_mae_dn": float(per_frame.mean()),
        "decoded_max_frame_rgb_mae_dn": float(per_frame.max()),
    }


def export_media(
    output: Path,
    original: np.ndarray,
    repaired: np.ndarray,
    ffmpeg_name: str,
    ffprobe_name: str,
    *,
    fps: int = FPS,
    frame_count: int = FRAME_COUNT,
    names: tuple[str, str, str] = ("original.mp4", "repaired.mp4", "comparison.mp4"),
) -> dict:
    ffmpeg, ffprobe = _tool(ffmpeg_name), _tool(ffprobe_name)
    versions = {
        name: _run([path, "-version"], output).decode(errors="replace").splitlines()[0]
        for name, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe))
    }
    convert = (
        "scale=in_range=full:out_range=tv:out_color_matrix=bt709,"
        "setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
    )
    profile = [
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "medium",
        "-crf",
        "16",
        "-g",
        str(fps),
        "-keyint_min",
        str(fps),
        "-sc_threshold",
        "0",
        "-threads",
        "1",
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-color_range",
        "tv",
        "-video_track_timescale",
        str(fps),
        "-movflags",
        "+faststart+write_colr",
    ]
    sources = [
        (names[0], ["frames-original"], original),
        (names[1], ["frames-repaired"], repaired),
        (
            names[2],
            ["frames-original", "frames-repaired"],
            np.concatenate((original, repaired), axis=2),
        ),
    ]
    media = {}
    with tempfile.TemporaryDirectory(prefix="media-", dir=output) as directory:
        staging = Path(directory)
        for name, directories, expected_frames in sources:
            relative_path = f"{staging.name}/{name}"
            arguments = [ffmpeg, "-v", "error", "-xerror", "-nostdin"]
            for source in directories:
                arguments += [
                    "-framerate",
                    str(fps),
                    "-start_number",
                    "0",
                    "-i",
                    f"{source}/%06d.png",
                ]
            if len(directories) == 2:
                arguments += [
                    "-filter_complex",
                    f"[0:v][1:v]hstack=inputs=2,{convert}[v]",
                    "-map",
                    "[v]",
                ]
            else:
                arguments += ["-vf", convert]
            arguments += [*profile, relative_path]
            _run(arguments, output)
            media[name] = {
                "encode_argv": ["ffmpeg", *arguments[1:-1], name],
                "sha256": digest((staging / name).read_bytes()),
                "verification": _verify(
                    ffmpeg,
                    ffprobe,
                    relative_path,
                    output,
                    expected_frames,
                    fps=fps,
                    frame_count=frame_count,
                ),
            }
        published = []
        try:
            for name in media:
                (staging / name).replace(output / name)
                published.append(name)
        except OSError as error:
            for name in published:
                (output / name).unlink()
            raise MediaError(str(error)) from error
    return {"status": "verified", "tools": versions, "files": media}
