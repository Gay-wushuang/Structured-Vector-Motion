from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from ..scene import EvaluatedScene


class SVGRenderError(ValueError):
    pass


@dataclass(frozen=True)
class SVGRenderOptions:
    width: int = 1024
    height: int = 1024
    view_box: tuple[float, float, float, float] = (-2.0, -2.0, 4.0, 4.0)
    fill: str = "none"
    stroke: str = "#000000"
    stroke_width: float = 0.01


class SVGRenderer:
    """Deterministic renderer for the v0.1 evaluated geometry subset."""

    def __init__(self, options: SVGRenderOptions | None = None):
        self.options = options or SVGRenderOptions()
        self._clip_index = 0

    def render(self, scene: EvaluatedScene) -> str:
        self._clip_index = 0
        root = ET.Element(
            "svg",
            {
                "xmlns": "http://www.w3.org/2000/svg",
                "version": "1.1",
                "width": str(self.options.width),
                "height": str(self.options.height),
                "viewBox": " ".join(_number(value) for value in self.options.view_box),
                "data-svm-document": scene.document_id,
                "data-svm-quality": scene.quality.value,
            },
        )
        defs = ET.SubElement(root, "defs")
        content = ET.SubElement(root, "g", {"data-svm-role": "render-stack"})
        for entity in scene.entities:
            fill = entity.style.fill if entity.style else self.options.fill
            stroke = entity.style.stroke if entity.style else self.options.stroke
            stroke_width = entity.style.stroke_width if entity.style else self.options.stroke_width
            opacity = entity.style.opacity if entity.style else 1.0
            group = ET.SubElement(
                content,
                "g",
                {
                    "data-svm-entity": entity.entity_id,
                    "data-svm-name": entity.name,
                    "data-svm-value": entity.geometry_value_id,
                    "fill": fill,
                    "stroke": stroke,
                    "stroke-width": _number(stroke_width),
                    "opacity": _number(opacity),
                },
            )
            group.append(self._render_geometry(entity.geometry, defs))
        if len(defs) == 0:
            root.remove(defs)
        body = ET.tostring(root, encoding="unicode", short_empty_elements=True)
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'

    def _render_geometry(
        self,
        geometry: dict[str, Any],
        defs: ET.Element,
        *,
        force_path: bool = False,
    ) -> ET.Element:
        kind = geometry.get("kind")
        if kind == "ellipse":
            if force_path:
                return ET.Element("path", {"d": _ellipse_path(geometry)})
            return ET.Element(
                "ellipse",
                {
                    "cx": _number(geometry["cx"]),
                    "cy": _number(geometry["cy"]),
                    "rx": _number(geometry["rx"]),
                    "ry": _number(geometry["ry"]),
                },
            )
        if kind == "rectangle":
            if force_path:
                return ET.Element("path", {"d": _rectangle_path(geometry)})
            return ET.Element(
                "rect",
                {
                    "x": _number(geometry["x"]),
                    "y": _number(geometry["y"]),
                    "width": _number(geometry["width"]),
                    "height": _number(geometry["height"]),
                },
            )
        if kind == "transform":
            matrix = geometry["matrix"]
            group = ET.Element(
                "g", {"transform": f"matrix({' '.join(_number(value) for value in matrix)})"}
            )
            group.append(self._render_geometry(geometry["source"], defs, force_path=force_path))
            return group
        if kind in {"path", "refined_path"}:
            return self._render_geometry(geometry["source"], defs, force_path=True)
        if kind == "clip":
            clip_id = f"svm-clip-{self._clip_index}"
            self._clip_index += 1
            clip_path = ET.SubElement(defs, "clipPath", {"id": clip_id})
            clip_path.append(self._render_geometry(geometry["clip"], defs, force_path=True))
            group = ET.Element("g", {"clip-path": f"url(#{clip_id})"})
            group.append(self._render_geometry(geometry["content"], defs, force_path=force_path))
            return group
        if kind == "split_part":
            raise SVGRenderError(
                "SplitEntity selector geometry is not renderable until selector "
                "semantics are implemented"
            )
        raise SVGRenderError(f"Unsupported geometry kind: {kind!r}")


def _number(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SVGRenderError(f"Expected numeric SVG value, got {value!r}")
    if value == 0:
        return "0"
    return format(float(value), ".12g")


def _ellipse_path(geometry: dict[str, Any]) -> str:
    cx = float(geometry["cx"])
    cy = float(geometry["cy"])
    rx = float(geometry["rx"])
    ry = float(geometry["ry"])
    kappa = 0.5522847498307936
    ox = rx * kappa
    oy = ry * kappa
    return " ".join(
        (
            f"M {_number(cx - rx)} {_number(cy)}",
            f"C {_number(cx - rx)} {_number(cy - oy)} "
            f"{_number(cx - ox)} {_number(cy - ry)} {_number(cx)} {_number(cy - ry)}",
            f"C {_number(cx + ox)} {_number(cy - ry)} "
            f"{_number(cx + rx)} {_number(cy - oy)} {_number(cx + rx)} {_number(cy)}",
            f"C {_number(cx + rx)} {_number(cy + oy)} "
            f"{_number(cx + ox)} {_number(cy + ry)} {_number(cx)} {_number(cy + ry)}",
            f"C {_number(cx - ox)} {_number(cy + ry)} "
            f"{_number(cx - rx)} {_number(cy + oy)} {_number(cx - rx)} {_number(cy)}",
            "Z",
        )
    )


def _rectangle_path(geometry: dict[str, Any]) -> str:
    x = float(geometry["x"])
    y = float(geometry["y"])
    width = float(geometry["width"])
    height = float(geometry["height"])
    return (
        f"M {_number(x)} {_number(y)} "
        f"H {_number(x + width)} V {_number(y + height)} "
        f"H {_number(x)} Z"
    )
