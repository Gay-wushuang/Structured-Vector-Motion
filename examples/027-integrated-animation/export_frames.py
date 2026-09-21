from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from svm import MotionEvaluator  # noqa: E402
from svm.renderers import SVGRenderer, SVGRenderOptions  # noqa: E402

DEMO_DIRECTORY = Path(__file__).resolve().parent
DOCUMENT = DEMO_DIRECTORY / "demo-002.svm.json"
FRAMES = DEMO_DIRECTORY / "frames"
SNAPSHOT_TICKS = (0, 12, 24, 36, 48, 60, 72)


def main() -> None:
    document = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    motion = MotionEvaluator(document)
    renderer = SVGRenderer(SVGRenderOptions(width=960, height=480, view_box=(-60, -40, 240, 120)))
    FRAMES.mkdir(exist_ok=True)
    for tick in SNAPSHOT_TICKS:
        svg = renderer.render(motion.evaluate(tick).scene)
        (FRAMES / f"frame_{tick:03d}.svg").write_text(svg, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
