from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from svm import MotionEvaluator  # noqa: E402
from svm.renderers import SVGRenderer, SVGRenderOptions  # noqa: E402

DIRECTORY = Path(__file__).resolve().parent
GROUND_TRUTH = DIRECTORY / "ground-truth.svm.json"
OBSERVATIONS = DIRECTORY / "observations"
TICKS = (0, 12, 24, 36)


def main() -> None:
    document = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    motion = MotionEvaluator(document)
    renderer = SVGRenderer(SVGRenderOptions(width=800, height=480, view_box=(0, 0, 200, 120)))
    OBSERVATIONS.mkdir(exist_ok=True)
    for tick in TICKS:
        svg = renderer.render(motion.evaluate(tick).scene)
        (OBSERVATIONS / f"tick_{tick:03d}.svg").write_text(svg, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
