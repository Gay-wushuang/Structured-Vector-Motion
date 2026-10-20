from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import escape
from typing import Any

from .svg_import import MAX_SVG_BYTES, SVG_NAMESPACE

NORMALIZATION_IDENTITY = "svm-fogleman-primitive-svg-normalization@0.1"
UPSTREAM_REPOSITORY = "https://github.com/fogleman/primitive"

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_GLOBAL_TRANSFORM = re.compile(rf"^scale\(({_NUMBER})\) translate\((0\.5) (0\.5)\)$")
_LOCAL_TRANSFORM = re.compile(
    rf"^translate\(({_NUMBER}) ({_NUMBER})\) rotate\(({_NUMBER})\) "
    rf"scale\(({_NUMBER}) ({_NUMBER})\)$"
)
_QUADRATIC_PATH = re.compile(
    rf"^M\s*({_NUMBER})\s+({_NUMBER})\s+Q\s*({_NUMBER})\s+({_NUMBER})\s*,?\s*"
    rf"({_NUMBER})\s+({_NUMBER})$"
)


class PrimitiveSVGError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedPrimitiveSVG:
    content: bytes
    width: float
    height: float
    shape_count: int


@dataclass(frozen=True)
class _Shape:
    tag: str
    attributes: tuple[tuple[str, str], ...]


def normalize_primitive_svg(content: bytes) -> NormalizedPrimitiveSVG:
    """Lower only the exact SVG vocabulary emitted by fogleman/primitive."""

    if not content or len(content) > MAX_SVG_BYTES:
        raise PrimitiveSVGError("Primitive SVG must be non-empty and at most 5 MiB")
    upper_prefix = content[:1024].upper()
    if b"<!DOCTYPE" in upper_prefix or b"<!ENTITY" in upper_prefix:
        raise PrimitiveSVGError("Primitive SVG DTD and entity declarations are not supported")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise PrimitiveSVGError(f"Invalid Primitive SVG XML: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise PrimitiveSVGError("Primitive output root element must be svg")
    _whitespace_only(root)
    if set(root.attrib) != {"version", "width", "height"} or root.attrib["version"] != "1.1":
        raise PrimitiveSVGError("Primitive SVG root attributes do not match the pinned producer")
    width = _positive(root.attrib["width"], "root width")
    height = _positive(root.attrib["height"], "root height")
    children = list(root)
    if len(children) != 2:
        raise PrimitiveSVGError("Primitive SVG must contain one background and one shape group")

    background = _background(children[0], width, height)
    group = children[1]
    if _local_name(group.tag) != "g" or set(group.attrib) != {"transform"}:
        raise PrimitiveSVGError("Primitive SVG shape container is invalid")
    _whitespace_only(group)
    match = _GLOBAL_TRANSFORM.fullmatch(group.attrib["transform"])
    if match is None:
        raise PrimitiveSVGError("Unsupported Primitive global transform")
    scale = _positive(match.group(1), "global scale")

    shapes = [background]
    for element in group:
        _whitespace_only(element)
        shapes.append(_normalize_shape(element, scale))
    if len(shapes) == 1:
        raise PrimitiveSVGError("Primitive SVG contains no fitted shapes")

    named = [
        _Shape(shape.tag, (("id", f"primitive-{index:04d}"), *shape.attributes))
        for index, shape in enumerate(shapes)
    ]
    normalized = _serialize(width, height, named)
    return NormalizedPrimitiveSVG(normalized, width, height, len(shapes))


def _background(element: ET.Element, canvas_width: float, canvas_height: float) -> _Shape:
    if _local_name(element.tag) != "rect":
        raise PrimitiveSVGError("Primitive SVG first element must be its background rectangle")
    _whitespace_only(element)
    _no_children(element)
    _require_attributes(element, {"x", "y", "width", "height", "fill"}, "background")
    x = _number(element.attrib["x"], "background x")
    y = _number(element.attrib["y"], "background y")
    width = _positive(element.attrib["width"], "background width")
    height = _positive(element.attrib["height"], "background height")
    if x != 0 or y != 0 or width != canvas_width or height != canvas_height:
        raise PrimitiveSVGError("Primitive background must exactly cover the output canvas")
    return _Shape(
        "rect",
        (
            ("x", _format(x)),
            ("y", _format(y)),
            ("width", _format(width)),
            ("height", _format(height)),
            ("fill", _color(element.attrib["fill"])),
        ),
    )


def _normalize_shape(element: ET.Element, scale: float) -> _Shape:
    tag = _local_name(element.tag)
    if tag == "g":
        return _normalize_rotated_shape(element, scale)
    _no_children(element)
    if tag == "rect":
        geometry = {"x", "y", "width", "height"}
        _require_attributes(element, geometry | {"fill", "fill-opacity"}, "rectangle")
        x = _number(element.attrib["x"], "rectangle x")
        y = _number(element.attrib["y"], "rectangle y")
        width = _positive(element.attrib["width"], "rectangle width")
        height = _positive(element.attrib["height"], "rectangle height")
        return _Shape(
            "rect",
            (
                ("x", _format(scale * (x + 0.5))),
                ("y", _format(scale * (y + 0.5))),
                ("width", _format(scale * width)),
                ("height", _format(scale * height)),
                *_fill_style(element),
            ),
        )
    if tag == "ellipse":
        geometry = {"cx", "cy", "rx", "ry"}
        _require_attributes(element, geometry | {"fill", "fill-opacity"}, "ellipse")
        cx = _number(element.attrib["cx"], "ellipse cx")
        cy = _number(element.attrib["cy"], "ellipse cy")
        rx = _positive(element.attrib["rx"], "ellipse rx")
        ry = _positive(element.attrib["ry"], "ellipse ry")
        return _Shape(
            "ellipse",
            (
                ("cx", _format(scale * (cx + 0.5))),
                ("cy", _format(scale * (cy + 0.5))),
                ("rx", _format(scale * rx)),
                ("ry", _format(scale * ry)),
                *_fill_style(element),
            ),
        )
    if tag == "polygon":
        _require_attributes(element, {"points", "fill", "fill-opacity"}, "polygon")
        points = _points(element.attrib["points"])
        transformed = [(scale * (x + 0.5), scale * (y + 0.5)) for x, y in points]
        return _path_shape(_closed_path(transformed), _fill_style(element))
    if tag == "path":
        return _normalize_quadratic(element, scale)
    raise PrimitiveSVGError(f"Unsupported Primitive SVG element {tag!r}")


def _normalize_rotated_shape(element: ET.Element, global_scale: float) -> _Shape:
    _require_attributes(element, {"transform"}, "rotated shape group")
    children = list(element)
    if len(children) != 1:
        raise PrimitiveSVGError("Primitive rotated shape group must contain exactly one leaf")
    match = _LOCAL_TRANSFORM.fullmatch(element.attrib["transform"])
    if match is None:
        raise PrimitiveSVGError("Unsupported Primitive local transform")
    tx, ty, angle, sx, sy = (_number(value, "local transform") for value in match.groups())
    if sx <= 0 or sy <= 0:
        raise PrimitiveSVGError("Primitive local scale must be greater than zero")
    leaf = children[0]
    _whitespace_only(leaf)
    _no_children(leaf)
    tag = _local_name(leaf.tag)
    center = (global_scale * (tx + 0.5), global_scale * (ty + 0.5))
    if tag == "rect":
        _require_attributes(
            leaf,
            {"x", "y", "width", "height", "fill", "fill-opacity"},
            "rotated rectangle",
        )
        if (
            _number(leaf.attrib["x"], "rotated rectangle x") != -0.5
            or _number(leaf.attrib["y"], "rotated rectangle y") != -0.5
            or _number(leaf.attrib["width"], "rotated rectangle width") != 1
            or _number(leaf.attrib["height"], "rotated rectangle height") != 1
        ):
            raise PrimitiveSVGError("Primitive rotated rectangle leaf is not canonical")
        radians = math.radians(angle)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        points = []
        for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
            px = global_scale * (cosine * sx * x - sine * sy * y) + center[0]
            py = global_scale * (sine * sx * x + cosine * sy * y) + center[1]
            points.append((px, py))
        return _path_shape(_closed_path(points), _fill_style(leaf))
    if tag == "ellipse":
        _require_attributes(
            leaf,
            {"cx", "cy", "rx", "ry", "fill", "fill-opacity"},
            "rotated ellipse",
        )
        if any(
            _number(leaf.attrib[name], f"rotated ellipse {name}") != expected
            for name, expected in (("cx", 0), ("cy", 0), ("rx", 1), ("ry", 1))
        ):
            raise PrimitiveSVGError("Primitive rotated ellipse leaf is not canonical")
        rx = global_scale * sx
        ry = global_scale * sy
        radians = math.radians(angle)
        dx = rx * math.cos(radians)
        dy = rx * math.sin(radians)
        start = (center[0] + dx, center[1] + dy)
        opposite = (center[0] - dx, center[1] - dy)
        d = (
            f"M {_format(start[0])} {_format(start[1])} "
            f"A {_format(rx)} {_format(ry)} {_format(angle)} 1 0 "
            f"{_format(opposite[0])} {_format(opposite[1])} "
            f"A {_format(rx)} {_format(ry)} {_format(angle)} 1 0 "
            f"{_format(start[0])} {_format(start[1])} Z"
        )
        return _path_shape(d, _fill_style(leaf))
    raise PrimitiveSVGError(f"Unsupported Primitive rotated leaf {tag!r}")


def _normalize_quadratic(element: ET.Element, scale: float) -> _Shape:
    _require_attributes(
        element,
        {"stroke", "stroke-opacity", "fill", "d", "stroke-width"},
        "quadratic path",
    )
    if element.attrib["fill"] != "none":
        raise PrimitiveSVGError("Primitive quadratic path fill must be none")
    match = _QUADRATIC_PATH.fullmatch(element.attrib["d"].strip())
    if match is None:
        raise PrimitiveSVGError("Unsupported Primitive path data")
    values = [_number(value, "quadratic path coordinate") for value in match.groups()]
    values = [scale * (value + 0.5) for value in values]
    width = scale * _positive(element.attrib["stroke-width"], "quadratic stroke width")
    opacity = _opacity(element.attrib["stroke-opacity"])
    d = "M {} {} Q {} {} {} {}".format(*(_format(value) for value in values))
    return _Shape(
        "path",
        (
            ("d", d),
            ("fill", "none"),
            ("stroke", _color(element.attrib["stroke"])),
            ("stroke-width", _format(width)),
            ("opacity", _format(opacity)),
        ),
    )


def _fill_style(element: ET.Element) -> tuple[tuple[str, str], ...]:
    return (
        ("fill", _color(element.attrib["fill"])),
        ("opacity", _format(_opacity(element.attrib["fill-opacity"]))),
    )


def _path_shape(d: str, style: tuple[tuple[str, str], ...]) -> _Shape:
    return _Shape("path", (("d", d), *style))


def _closed_path(points: list[tuple[float, float]]) -> str:
    if len(points) < 3:
        raise PrimitiveSVGError("Primitive polygon requires at least three points")
    commands = [f"M {_format(points[0][0])} {_format(points[0][1])}"]
    commands.extend(f"L {_format(x)} {_format(y)}" for x, y in points[1:])
    commands.append("Z")
    return " ".join(commands)


def _points(value: str) -> list[tuple[float, float]]:
    tokens = value.replace(",", " ").split()
    if len(tokens) < 6 or len(tokens) % 2:
        raise PrimitiveSVGError("Primitive polygon points are invalid")
    numbers = [_number(token, "polygon coordinate") for token in tokens]
    return list(zip(numbers[::2], numbers[1::2], strict=True))


def _require_attributes(element: ET.Element, expected: set[str], context: str) -> None:
    if set(element.attrib) != expected:
        raise PrimitiveSVGError(f"Primitive {context} attributes do not match the pinned producer")


def _whitespace_only(element: ET.Element) -> None:
    if (element.text and element.text.strip()) or (element.tail and element.tail.strip()):
        raise PrimitiveSVGError("Primitive SVG text content is not supported")


def _no_children(element: ET.Element) -> None:
    if list(element):
        raise PrimitiveSVGError("Primitive SVG leaf elements must not contain children")


def _local_name(tag: Any) -> str:
    if not isinstance(tag, str):
        raise PrimitiveSVGError(
            "Primitive SVG comments and processing instructions are unsupported"
        )
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        if namespace != SVG_NAMESPACE:
            raise PrimitiveSVGError(f"Unsupported Primitive SVG namespace {namespace!r}")
        return local
    return tag


def _number(value: str, name: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise PrimitiveSVGError(f"Primitive {name} must be a number") from exc
    if not math.isfinite(number) or not -1e9 < number < 1e9:
        raise PrimitiveSVGError(f"Primitive {name} is outside the supported range")
    return number


def _positive(value: str, name: str) -> float:
    number = _number(value, name)
    if number <= 0:
        raise PrimitiveSVGError(f"Primitive {name} must be greater than zero")
    return number


def _opacity(value: str) -> float:
    opacity = _number(value, "opacity")
    if not 0 <= opacity <= 1:
        raise PrimitiveSVGError("Primitive opacity must be between zero and one")
    return opacity


def _color(value: str) -> str:
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise PrimitiveSVGError(f"Unsupported Primitive color {value!r}")
    return value.upper()


def _format(value: float) -> str:
    if value == 0:
        value = 0.0
    return format(value, ".12g")


def _serialize(width: float, height: float, shapes: list[_Shape]) -> bytes:
    lines = [f'<svg xmlns="{SVG_NAMESPACE}" viewBox="0 0 {_format(width)} {_format(height)}">']
    for shape in shapes:
        attributes = " ".join(
            f'{name}="{escape(value, quote=True)}"' for name, value in shape.attributes
        )
        lines.append(f"  <{shape.tag} {attributes} />")
    lines.append("</svg>")
    return ("\n".join(lines) + "\n").encode("utf-8")
