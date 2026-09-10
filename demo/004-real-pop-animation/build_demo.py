from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from svm import AdapterRequest, ArtifactStore, MotionEvaluator, ProposalAcceptor, RevisionStore
from svm.adapters import POPOutputAdapter, POPTokenExporter
from svm.document import validate_document
from svm.renderers import SVGRenderer, SVGRenderOptions

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REAL = ROOT / "examples" / "derived" / "020-pop-output" / "real"
BASE = ROOT / "examples" / "005-empty-canvas.svm.json"
FRAMES, PNG_FRAMES, PREVIEWS = HERE / "frames", HERE / "frames-png", HERE / "previews"
FPS, END = 24, 168


def track(
    target: dict[str, str],
    slug: str,
    values: list[tuple[int, int | float]],
    interpolation: str = "ease-in-out",
) -> dict[str, Any]:
    return {
        "id": f"track:{slug}",
        "target": target,
        "value_type": "number",
        "interpolation": interpolation,
        "keyframes": [
            {"id": f"keyframe:{slug}-{tick:04d}", "tick": tick, "value": value}
            for tick, value in values
        ],
    }


def fill_track(entity: str, values: list[tuple[int, str]]) -> dict[str, Any]:
    return {
        "id": "track:pop-accent-fill",
        "target": {"entity": entity, "property": "fill"},
        "value_type": "color",
        "interpolation": "hold",
        "keyframes": [
            {"id": f"keyframe:pop-accent-fill-{tick:04d}", "tick": tick, "value": value}
            for tick, value in values
        ],
    }


def accepted_pop_document() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((REAL / "run-manifest.json").read_text())
    payload = json.loads((REAL / "pop-output.json").read_text())
    producer = payload["producer"]
    artifacts = ArtifactStore()
    prefix, output = POPTokenExporter().export(
        artifacts,
        payload["raw_tokens"],
        prefix_length=11,
        commit=producer["commit"],
        model_id=producer["model_id"],
        checkpoint_hash=producer["checkpoint_hash"],
        seed=producer["seed"],
        decoding=producer["decoding"],
        user_intent=payload["annotations"]["user_intent"],
    )
    revisions = RevisionStore.create(json.loads(BASE.read_text()))
    request = AdapterRequest.from_store(
        revisions,
        revisions.head,
        ("document",),
        artifact_ids=(prefix.artifact_id, output.artifact_id),
        options={"namespace": "golden-p-real"},
    )
    revision = ProposalAcceptor().accept(
        revisions, POPOutputAdapter().propose(request, artifacts), artifacts
    )
    if revision.revision_id != manifest["artifacts"]["accepted_revision_id"]:
        raise RuntimeError("Frozen Golden P acceptance identity changed")
    return revisions.get_document(revision.revision_id), manifest


def build_document() -> dict[str, Any]:
    document, manifest = accepted_pop_document()
    payload = json.loads((REAL / "pop-output.json").read_text())
    buckets: list[list[str]] = [[], [], []]
    for primitive in payload["primitives"]:
        bucket = 0 if primitive["x"] < 96 else 1 if primitive["x"] < 176 else 2
        buckets[bucket].append(f"entity:golden-p-real-primitive-{primitive['index']:04d}")
    artifact_id = manifest["artifacts"]["output_artifact_id"]
    groups = []
    for index, members in enumerate(buckets, 1):
        digit = format(index, "x")
        groups.append(
            {
                "id": "group:" + digit * 64,
                "kind": "explicit-group",
                "members": sorted(members),
                "transform": {
                    "translate": [0, 0],
                    "rotation_degrees": 0,
                    "scale": 1,
                    "origin": [128, 128],
                },
                "provenance": {
                    "candidate_id": "candidate:group:" + digit * 64,
                    "inference_id": "inference:group:" + digit * 64,
                    "inference_artifact_id": artifact_id,
                },
            }
        )
    document["document_id"] = "document:real-pop-authored-animation-demo-004"
    document["groups"] = groups
    document["presentation"]["camera"] = {"position": [128, 128], "rotation_degrees": 0, "scale": 1}
    content = []
    motions = [
        ([0, 0, 10, 14, 10, 10, -5, -8, -5, -5, 0], [0, -3, 2, 2, 0, 0, 3, 3, 0, 0, 0]),
        ([0, 0, -8, -12, -8, -8, 6, 9, 6, 6, 0], [0, 2, -2, -2, 0, 0, -3, -3, 0, 0, 0]),
        ([0, 0, -12, -17, -12, -12, 8, 12, 8, 8, 0], [0, 4, -3, -3, 0, 0, 4, 4, 0, 0, 0]),
    ]
    ticks = [0, 20, 38, 44, 52, 68, 92, 98, 106, 128, 168]
    for group, (xs, ys) in zip(groups, motions, strict=True):
        gid, slug = group["id"], group["id"][-1]
        content.extend(
            [
                track(
                    {"group": gid, "property": "translate.x"},
                    f"pop-{slug}-x",
                    list(zip(ticks, xs, strict=True)),
                ),
                track(
                    {"group": gid, "property": "translate.y"},
                    f"pop-{slug}-y",
                    list(zip(ticks, ys, strict=True)),
                ),
                track(
                    {"group": gid, "property": "rotation_degrees"},
                    f"pop-{slug}-rotation",
                    [
                        (0, 0),
                        (38, 0),
                        (44, (-1) ** int(slug) * 3),
                        (52, 0),
                        (92, 0),
                        (98, (-1) ** (int(slug) + 1) * 4),
                        (106, 0),
                        (168, 0),
                    ],
                ),
                track(
                    {"group": gid, "property": "scale"},
                    f"pop-{slug}-scale",
                    [
                        (0, 1),
                        (38, 1),
                        (44, 1.08),
                        (52, 1.03),
                        (68, 1.03),
                        (92, 1),
                        (98, 1.1),
                        (106, 1.04),
                        (128, 1.04),
                        (168, 1),
                    ],
                ),
            ]
        )
    content.extend(
        [
            track(
                {"camera": "presentation", "property": "scale"},
                "pop-camera-scale",
                [
                    (0, 1),
                    (38, 1),
                    (44, 1.35),
                    (52, 1.24),
                    (68, 1.24),
                    (92, 1),
                    (98, 1.42),
                    (106, 1.28),
                    (128, 1.28),
                    (156, 0.98),
                    (168, 1),
                ],
            ),
            track(
                {"camera": "presentation", "property": "rotation_degrees"},
                "pop-camera-rotation",
                [
                    (0, 0),
                    (38, 0),
                    (44, 2),
                    (52, 0.8),
                    (92, -1),
                    (98, -2.5),
                    (106, -0.8),
                    (128, -0.8),
                    (168, 0),
                ],
            ),
        ]
    )
    accent = "entity:golden-p-real-primitive-0142"
    content.extend(
        [
            fill_track(
                accent,
                [
                    (0, "#F8E080"),
                    (44, "#FF5A9D"),
                    (92, "#68E0B8"),
                    (98, "#FFFFFF"),
                    (106, "#F8E080"),
                ],
            ),
            track(
                {"entity": accent, "property": "opacity"},
                "pop-accent-opacity",
                [
                    (0, 0.5),
                    (38, 0.5),
                    (44, 1),
                    (52, 0.5),
                    (92, 0.5),
                    (98, 1),
                    (106, 0.5),
                    (168, 0.5),
                ],
            ),
        ]
    )
    document["animation"] = {
        "semantics_version": "svm-motion@0.6",
        "timebase": {"ticks_per_second": FPS},
        "content": content,
        "construction_scheduling_hints": [],
    }
    validate_document(document)
    return document


def main() -> None:
    document = build_document()
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "scene.svm.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    FRAMES.mkdir(parents=True, exist_ok=True)
    motion, renderer = (
        MotionEvaluator(document),
        SVGRenderer(SVGRenderOptions(width=768, height=768, view_box=(-128, -128, 256, 256))),
    )
    for tick in range(END + 1):
        (FRAMES / f"frame-{tick:04d}.svg").write_text(
            renderer.render(motion.evaluate(tick).scene), encoding="utf-8"
        )
    browser = next(
        path
        for path in (
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        )
        if path.is_file()
    )
    PNG_FRAMES.mkdir(parents=True, exist_ok=True)
    for tick in range(END + 1):
        subprocess.run(
            [
                str(browser),
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--window-size=768,768",
                f"--screenshot={PNG_FRAMES / f'frame-{tick:04d}.png'}",
                (FRAMES / f"frame-{tick:04d}.svg").resolve().as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            str(PNG_FRAMES / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(HERE / "demo.mp4"),
        ],
        check=True,
    )
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for tick in (0, 44, 92, 98, 168):
        shutil.copyfile(PNG_FRAMES / f"frame-{tick:04d}.png", PREVIEWS / f"frame-{tick:04d}.png")


if __name__ == "__main__":
    main()
