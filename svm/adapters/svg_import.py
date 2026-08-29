from __future__ import annotations

import importlib.metadata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from svgpathtools import parse_path  # pyright: ignore[reportMissingImports]

from ..artifacts import ArtifactKind, ArtifactResolver, ArtifactSnapshot
from ..proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    Proposal,
)
from ..revisions import AppendSceneFragmentChange, Transaction

SVG_MEDIA_TYPES = {"image/svg+xml", "application/svg+xml"}
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_STYLE_ATTRIBUTES = {"fill", "stroke", "stroke-width"}
_LEAF_STYLE_ATTRIBUTES = _STYLE_ATTRIBUTES | {"opacity"}
_ALLOWED_ATTRIBUTES = {
    "svg": {"id", "viewBox"} | _STYLE_ATTRIBUTES,
    "g": {"id"} | _STYLE_ATTRIBUTES,
    "rect": {"id", "x", "y", "width", "height"} | _LEAF_STYLE_ATTRIBUTES,
    "ellipse": {"id", "cx", "cy", "rx", "ry"} | _LEAF_STYLE_ATTRIBUTES,
    "path": {"id", "d"} | _LEAF_STYLE_ATTRIBUTES,
    "title": set(),
    "desc": set(),
    "metadata": set(),
    "defs": set(),
}


class SVGImportError(ValueError):
    pass


@dataclass(frozen=True)
class _ImportedShape:
    entity: dict[str, Any]
    operation: dict[str, Any]
    binding: dict[str, Any]
    style: dict[str, Any]


class SVGImportAdapter:
    adapter_id = "adapter:svg-import"
    adapter_version = "0.1"

    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal:
        artifact = self._select_artifact(
            artifacts.resolve_as(
                request.artifact_ids,
                kind=ArtifactKind.REFERENCE,
                media_types=frozenset(SVG_MEDIA_TYPES),
            )
        )
        root = self._parse_svg(artifact)
        namespace = self._namespace(request, artifact)
        shapes = self._extract_shapes(root, namespace)
        if not shapes:
            raise SVGImportError("SVG contains no supported renderable shapes")

        reference = artifact.document_reference()
        view_box = root.attrib.get("viewBox")
        if view_box is not None:
            reference["import_metadata"]["svg_view_box"] = _view_box(view_box)
        change = AppendSceneFragmentChange(
            entities=tuple(shape.entity for shape in shapes),
            operations=tuple(shape.operation for shape in shapes),
            output_bindings=tuple(shape.binding for shape in shapes),
            render_entries=tuple(shape.entity["id"] for shape in shapes),
            styles=tuple(shape.style for shape in shapes),
            references=(reference,),
        )
        transaction_id = f"transaction:svg-import:{namespace}"
        proposal_id = f"proposal:svg-import:{namespace}"
        return Proposal(
            proposal_id=proposal_id,
            base_revision_id=request.base_revision_id,
            generator=GeneratorProvenance(
                adapter_id=self.adapter_id,
                adapter_version=self.adapter_version,
                engine="svgpathtools",
                engine_version=importlib.metadata.version("svgpathtools"),
                parameters={"namespace": namespace},
            ),
            transaction=Transaction(
                transaction_id=transaction_id,
                changes=(change,),
                message=f"Import {len(shapes)} shapes from SVG artifact",
            ),
            report=EvaluationReport(
                metrics={"imported_shapes": float(len(shapes))},
            ),
            required_artifact_ids=(artifact.artifact_id,),
            confidence=1.0,
            notes="Deterministic flat SVG shape import",
        )

    @staticmethod
    def _select_artifact(artifacts: tuple[ArtifactSnapshot, ...]) -> ArtifactSnapshot:
        if len(artifacts) != 1:
            raise SVGImportError("SVG Import requires exactly one Artifact snapshot")
        artifact = artifacts[0]
        if artifact.kind != ArtifactKind.REFERENCE:
            raise SVGImportError("SVG Import requires a ReferenceArtifact")
        if artifact.media_type not in SVG_MEDIA_TYPES:
            raise SVGImportError(f"Unsupported SVG media type {artifact.media_type!r}")
        if len(artifact.content) > 5 * 1024 * 1024:
            raise SVGImportError("SVG Artifact exceeds the 5 MiB import limit")
        return artifact

    @staticmethod
    def _parse_svg(artifact: ArtifactSnapshot) -> ET.Element:
        upper_prefix = artifact.content[:1024].upper()
        if b"<!DOCTYPE" in upper_prefix or b"<!ENTITY" in upper_prefix:
            raise SVGImportError("SVG DTD and entity declarations are not supported")
        try:
            root = ET.fromstring(artifact.content)
        except ET.ParseError as exc:
            raise SVGImportError(f"Invalid SVG XML: {exc}") from exc
        if _local_name(root.tag) != "svg":
            raise SVGImportError("Artifact root element must be svg")
        return root

    @staticmethod
    def _namespace(request: AdapterRequest, artifact: ArtifactSnapshot) -> str:
        requested = request.options.get("namespace")
        if requested is not None:
            if not isinstance(requested, str) or not requested.replace("-", "").isalnum():
                raise SVGImportError("Import namespace must contain letters, digits, or hyphens")
            base = requested
        else:
            base = artifact.content_hash.removeprefix("sha256:")[:12]
        entity_ids = {entity["id"] for entity in request.document["entities"]}
        if not any(entity_id.startswith(f"entity:svg-{base}-") for entity_id in entity_ids):
            return base
        suffix = 2
        while any(entity_id.startswith(f"entity:svg-{base}{suffix}-") for entity_id in entity_ids):
            suffix += 1
        return f"{base}{suffix}"

    def _extract_shapes(self, root: ET.Element, namespace: str) -> list[_ImportedShape]:
        shapes: list[_ImportedShape] = []

        def walk(element: ET.Element, inherited_style: dict[str, Any]) -> None:
            tag = _local_name(element.tag)
            _validate_attributes(element, tag)
            style = _resolved_style(element, inherited_style, allow_opacity=tag not in {"svg", "g"})
            if tag in {"svg", "g"}:
                for child in element:
                    walk(child, style)
                return
            if tag in {"title", "desc", "metadata", "defs"}:
                return
            if tag not in {"rect", "ellipse", "path"}:
                raise SVGImportError(f"Unsupported SVG element {tag!r}")
            index = len(shapes)
            shapes.append(self._shape(element, tag, style, namespace, index))

        walk(root, _default_style())
        return shapes

    def _shape(
        self,
        element: ET.Element,
        tag: str,
        style: dict[str, Any],
        namespace: str,
        index: int,
    ) -> _ImportedShape:
        suffix = f"{index:04d}"
        entity_id = f"entity:svg-{namespace}-{suffix}"
        operation_id = f"op:svg-{namespace}-{suffix}"
        name = element.attrib.get("id") or f"{tag}-{index + 1}"
        if tag == "rect":
            if "rx" in element.attrib or "ry" in element.attrib:
                raise SVGImportError("Rounded rectangles are not supported")
            operation_type = "CreateRectangle"
            parameters = {
                "x": _number_attribute(element, "x", default=0.0),
                "y": _number_attribute(element, "y", default=0.0),
                "width": _number_attribute(element, "width"),
                "height": _number_attribute(element, "height"),
            }
            _require_positive(parameters["width"], "width", "rect")
            _require_positive(parameters["height"], "height", "rect")
        elif tag == "ellipse":
            operation_type = "CreateEllipse"
            parameters = {
                "cx": _number_attribute(element, "cx", default=0.0),
                "cy": _number_attribute(element, "cy", default=0.0),
                "rx": _number_attribute(element, "rx"),
                "ry": _number_attribute(element, "ry"),
            }
            _require_positive(parameters["rx"], "rx", "ellipse")
            _require_positive(parameters["ry"], "ry", "ellipse")
        else:
            d = element.attrib.get("d", "").strip()
            if not d:
                raise SVGImportError("SVG path requires a non-empty d attribute")
            try:
                path = parse_path(d)
                min_x, max_x, min_y, max_y = path.bbox()
            except (ValueError, TypeError, ZeroDivisionError) as exc:
                raise SVGImportError(f"Invalid SVG path data: {exc}") from exc
            operation_type = "CreatePath"
            parameters = {
                "d": d,
                "bounds": [float(min_x), float(min_y), float(max_x), float(max_y)],
            }
        return _ImportedShape(
            entity={"id": entity_id, "name": name},
            operation={
                "id": operation_id,
                "type": operation_type,
                "inputs": {},
                "parameters": parameters,
            },
            binding={
                "entity": entity_id,
                "property": "geometry",
                "slot": f"{operation_id}.geometry",
            },
            style={"entity": entity_id, **style},
        )


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        if namespace and namespace != SVG_NAMESPACE:
            raise SVGImportError(f"Unsupported XML namespace {namespace!r}")
        return local
    return tag


def _default_style() -> dict[str, Any]:
    return {
        "fill": "#000000",
        "stroke": "none",
        "stroke_width": 1.0,
        "opacity": 1.0,
    }


def _validate_attributes(element: ET.Element, tag: str) -> None:
    if tag in {"svg", "g"} and "opacity" in element.attrib:
        raise SVGImportError("SVG group opacity is not supported")
    allowed = _ALLOWED_ATTRIBUTES.get(tag)
    if allowed is None:
        return
    unsupported = sorted(set(element.attrib) - allowed)
    if unsupported:
        names = ", ".join(unsupported)
        raise SVGImportError(f"Unsupported SVG {tag} attribute(s): {names}")


def _resolved_style(
    element: ET.Element, inherited: dict[str, Any], *, allow_opacity: bool
) -> dict[str, Any]:
    style = dict(inherited)
    if "fill" in element.attrib:
        style["fill"] = _color(element.attrib["fill"])
    if "stroke" in element.attrib:
        style["stroke"] = _color(element.attrib["stroke"])
    if "stroke-width" in element.attrib:
        style["stroke_width"] = _plain_number(element.attrib["stroke-width"], "stroke-width")
    if "opacity" in element.attrib:
        if not allow_opacity:
            raise SVGImportError("SVG group opacity is not supported")
        opacity = _plain_number(element.attrib["opacity"], "opacity")
        if not 0 <= opacity <= 1:
            raise SVGImportError("SVG opacity must be between 0 and 1")
        style["opacity"] = opacity
    return style


def _color(value: str) -> str:
    if value == "none":
        return value
    if (
        len(value) in {7, 9}
        and value.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in value[1:])
    ):
        return value.upper()
    raise SVGImportError(f"Unsupported SVG color {value!r}")


def _number_attribute(element: ET.Element, name: str, default: float | None = None) -> float:
    value = element.attrib.get(name)
    if value is None:
        if default is not None:
            return default
        raise SVGImportError(f"SVG {_local_name(element.tag)} requires {name}")
    return _plain_number(value, name)


def _plain_number(value: str, name: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise SVGImportError(f"SVG {name} must be a unitless number") from exc
    if not (-1e12 < number < 1e12):
        raise SVGImportError(f"SVG {name} is outside supported numeric range")
    return number


def _require_positive(value: float, name: str, tag: str) -> None:
    if value <= 0:
        raise SVGImportError(f"SVG {tag} {name} must be greater than zero")


def _view_box(value: str) -> list[float]:
    parts = value.replace(",", " ").split()
    if len(parts) != 4:
        raise SVGImportError("SVG viewBox must contain four unitless numbers")
    result = [_plain_number(part, "viewBox") for part in parts]
    if result[2] <= 0 or result[3] <= 0:
        raise SVGImportError("SVG viewBox width and height must be greater than zero")
    return result
