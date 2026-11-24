"""Authored 8-second SVM Motion ground-truth scene for the R1-002 video repair path.

The scene is deliberately conservative: a fixed camera, a static textured
background, and two explicitly grouped character clusters that translate,
rotate, and uniformly scale. Nothing here is inferred from video; the Document
is authored and then sampled through the real ``MotionEvaluator``.
"""

from __future__ import annotations

from typing import Any

WIDTH = 640
HEIGHT = 360
FPS = 12
FRAME_COUNT = 96
DURATION_TICKS = FRAME_COUNT
VIEW_BOX = (-2.0, -1.125, 4.0, 2.25)

ROI_XYXY = (88, 44, 552, 348)
STABLE_XYXY = (8, 4, 80, 40)
DEFECT_XYXY = (102, 324, 118, 338)
STATIC_SCORING_XYXY = (504, 60, 540, 84)

DEFECT_FRAMES = (8, 9, 10, 30, 31, 32, 55, 56, 57, 80, 81, 82)
DEFECT_RGB = (45, 26, 116)
DEFECT_NOISE = 5
FLICKER_OFFSETS = (-8, 6, -6, 8, 0, 4, -4, 0) * (FRAME_COUNT // 8)
GHOST_NUMERATOR = 2
GHOST_DENOMINATOR = 5
GHOST_PROTECTION_RADIUS = 2

MOVING_ENTITIES = (
    "entity:a-body",
    "entity:a-face",
    "entity:a-mark",
    "entity:b-body",
    "entity:b-face",
    "entity:b-mark",
)
ARTIFACT_ID = "artifact:" + "c" * 64

PRIMITIVES = (
    (
        "entity:background",
        "CreateRectangle",
        {"x": -2, "y": -1.125, "width": 4, "height": 2.25},
        "#2B3550",
    ),
    (
        "entity:band-top",
        "CreateRectangle",
        {"x": -2, "y": -1.125, "width": 4, "height": 0.12},
        "#3A4668",
    ),
    (
        "entity:band-bottom",
        "CreateRectangle",
        {"x": -2, "y": 1.005, "width": 4, "height": 0.12},
        "#3A4668",
    ),
    (
        "entity:static-nw",
        "CreateRectangle",
        {"x": -1.88, "y": -0.98, "width": 0.30, "height": 0.16},
        "#5A6E96",
    ),
    (
        "entity:static-nw-small",
        "CreateRectangle",
        {"x": -1.88, "y": -0.78, "width": 0.18, "height": 0.10},
        "#7C90B8",
    ),
    (
        "entity:static-ne",
        "CreateRectangle",
        {"x": 1.55, "y": -0.98, "width": 0.34, "height": 0.14},
        "#5A6E96",
    ),
    (
        "entity:static-ne-dot",
        "CreateEllipse",
        {"cx": 1.72, "cy": -0.55, "rx": 0.10, "ry": 0.10},
        "#7C90B8",
    ),
    (
        "entity:static-sw",
        "CreateRectangle",
        {"x": -1.90, "y": 0.80, "width": 0.30, "height": 0.12},
        "#4E6288",
    ),
    (
        "entity:static-se",
        "CreateRectangle",
        {"x": 1.50, "y": 0.82, "width": 0.40, "height": 0.14},
        "#4E6288",
    ),
    (
        "entity:static-west-dot",
        "CreateEllipse",
        {"cx": -1.55, "cy": 0.62, "rx": 0.08, "ry": 0.08},
        "#6B7FA6",
    ),
    (
        "entity:a-body",
        "CreateEllipse",
        {"cx": -0.55, "cy": 0.05, "rx": 0.26, "ry": 0.40},
        "#7452E8",
    ),
    (
        "entity:a-face",
        "CreateEllipse",
        {"cx": -0.55, "cy": -0.28, "rx": 0.18, "ry": 0.15},
        "#EEE6C8",
    ),
    (
        "entity:a-mark",
        "CreateRectangle",
        {"x": -0.69, "y": -0.32, "width": 0.27, "height": 0.065},
        "#2B3550",
    ),
    (
        "entity:b-body",
        "CreateEllipse",
        {"cx": 0.75, "cy": 0.45, "rx": 0.22, "ry": 0.22},
        "#56C596",
    ),
    (
        "entity:b-face",
        "CreateEllipse",
        {"cx": 0.75, "cy": 0.38, "rx": 0.14, "ry": 0.11},
        "#16202F",
    ),
    (
        "entity:b-mark",
        "CreateRectangle",
        {"x": 0.63, "y": 0.36, "width": 0.23, "height": 0.055},
        "#EEC040",
    ),
)


def _primitive_records(
    entity_id: str,
    operation_type: str,
    parameters: dict[str, int | float],
    fill: str,
) -> tuple[dict[str, Any], ...]:
    operation_id = entity_id.replace("entity:", "op:")
    return (
        {"id": entity_id, "name": entity_id.removeprefix("entity:").replace("-", " ").title()},
        {"id": operation_id, "type": operation_type, "inputs": {}, "parameters": parameters},
        {"entity": entity_id, "property": "geometry", "slot": f"{operation_id}.geometry"},
        {
            "entity": entity_id,
            "fill": fill,
            "stroke": "none",
            "stroke_width": 0,
            "opacity": 1,
        },
    )


def _group(digit: str, members: list[str], origin: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": "group:" + digit * 64,
        "kind": "explicit-group",
        "members": sorted(members),
        "transform": {
            "translate": [0, 0],
            "rotation_degrees": 0,
            "scale": 1,
            "origin": list(origin),
        },
        "provenance": {
            "candidate_id": "candidate:group:" + digit * 64,
            "inference_id": "inference:group:" + digit * 64,
            "inference_artifact_id": ARTIFACT_ID,
        },
    }


def _track(
    group_id: str,
    property_name: str,
    tick_values: list[tuple[int, int | float]],
) -> dict[str, Any]:
    slug = f"g{group_id[-1]}-{property_name}".replace(".", "-").replace("_", "-")
    return {
        "id": f"track:{slug}",
        "target": {"group": group_id, "property": property_name},
        "value_type": "number",
        "interpolation": "ease-in-out",
        "keyframes": [
            {"id": f"keyframe:{slug}-{tick:04d}", "tick": tick, "value": value}
            for tick, value in tick_values
        ],
    }


def build_document() -> dict[str, Any]:
    """Return one valid authored Document with an 8-second content animation."""
    records = [_primitive_records(*primitive) for primitive in PRIMITIVES]
    entities, operations, bindings, styles = (list(items) for items in zip(*records, strict=True))
    groups = [
        _group("1", list(MOVING_ENTITIES[:3]), (-0.55, 0.05)),
        _group("2", list(MOVING_ENTITIES[3:]), (0.75, 0.45)),
    ]
    animation = [
        _track(
            groups[0]["id"],
            "translate.x",
            [
                (0, 0),
                (10, 0),
                (20, 1.10),
                (30, 1.15),
                (42, 0.25),
                (54, -0.15),
                (66, 0.0),
                (80, 0.50),
                (96, 0),
            ],
        ),
        _track(
            groups[0]["id"],
            "translate.y",
            [(0, 0), (24, -0.20), (48, 0.15), (72, -0.10), (96, 0)],
        ),
        _track(
            groups[0]["id"],
            "rotation_degrees",
            [(0, 0), (18, -6), (36, 4), (54, -3), (72, 5), (96, 0)],
        ),
        _track(
            groups[0]["id"],
            "scale",
            [(0, 1), (24, 1.12), (36, 1.05), (60, 0.94), (84, 1.03), (96, 1)],
        ),
        _track(
            groups[1]["id"],
            "translate.x",
            [
                (0, 0),
                (10, 0),
                (24, -0.95),
                (36, -1.00),
                (48, -0.55),
                (64, 0.10),
                (80, 0.0),
                (96, 0),
            ],
        ),
        _track(
            groups[1]["id"],
            "translate.y",
            [(0, 0), (24, 0.12), (48, -0.06), (72, 0.10), (96, 0)],
        ),
        _track(
            groups[1]["id"],
            "rotation_degrees",
            [(0, 0), (24, 8), (48, -6), (72, 4), (96, 0)],
        ),
        _track(
            groups[1]["id"],
            "scale",
            [(0, 1), (16, 1), (32, 1.15), (48, 1.00), (72, 1.08), (96, 1)],
        ),
    ]
    return {
        "schema_version": "0.1",
        "semantics_version": "svm-core-0.1",
        "document_id": "document:video-repair-motion-ground-truth",
        "references": [
            {
                "id": ARTIFACT_ID,
                "uri": ARTIFACT_ID.replace(":", "://", 1),
                "content_hash": "sha256:" + "c" * 64,
                "media_type": "application/vnd.svm.pop-group-candidates+json;version=0.1",
                "import_metadata": {"fixture": "video-repair-motion-scene"},
            }
        ],
        "entities": entities,
        "groups": groups,
        "construction": {
            "operations": operations,
            "output_bindings": bindings,
            "refinement_stages": [],
        },
        "presentation": {"render_stack": [item["id"] for item in entities], "styles": styles},
        "constraints": [],
        "evaluation_policies": [],
        "edit_permissions": [],
        "animation": {
            "semantics_version": "svm-motion@0.4",
            "timebase": {"ticks_per_second": FPS},
            "content": animation,
            "construction_scheduling_hints": [],
        },
    }
