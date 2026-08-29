from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ValueType(StrEnum):
    GEOMETRY = "geometry"


class OperationValidationError(ValueError):
    pass


ParameterValidator = Callable[[Mapping[str, Any]], None]
OperationExecutor = Callable[[Mapping[str, Any], Mapping[str, Any], str], dict[str, Any]]
OutputResolver = Callable[[Mapping[str, Any]], Mapping[str, ValueType]]


def _require_exact_keys(values: Mapping[str, Any], required: set[str], context: str) -> None:
    actual = set(values)
    if actual != required:
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        raise OperationValidationError(
            f"{context} keys do not match signature; missing={missing}, extra={extra}"
        )


def _require_number(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OperationValidationError(f"Parameter {name} must be a number")


def _numeric_parameters(*names: str) -> ParameterValidator:
    required = set(names)

    def validate(parameters: Mapping[str, Any]) -> None:
        _require_exact_keys(parameters, required, "Parameter")
        for name in names:
            _require_number(parameters[name], name)

    return validate


def _no_parameters(parameters: Mapping[str, Any]) -> None:
    _require_exact_keys(parameters, set(), "Parameter")


def _transform_parameters(parameters: Mapping[str, Any]) -> None:
    _require_exact_keys(parameters, {"matrix"}, "Parameter")
    matrix = parameters["matrix"]
    if not isinstance(matrix, list) or len(matrix) != 6:
        raise OperationValidationError("Transform matrix must contain six numbers")
    for index, value in enumerate(matrix):
        _require_number(value, f"matrix[{index}]")


def _path_parameters(parameters: Mapping[str, Any]) -> None:
    _require_exact_keys(parameters, {"d", "bounds"}, "Parameter")
    if not isinstance(parameters["d"], str) or not parameters["d"].strip():
        raise OperationValidationError("CreatePath d must be a non-empty string")
    bounds = parameters["bounds"]
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise OperationValidationError("CreatePath bounds must contain four numbers")
    for index, value in enumerate(bounds):
        _require_number(value, f"bounds[{index}]")
    min_x, min_y, max_x, max_y = (float(value) for value in bounds)
    if min_x > max_x or min_y > max_y:
        raise OperationValidationError("CreatePath bounds must be ordered")


def _split_parameters(parameters: Mapping[str, Any]) -> None:
    _require_exact_keys(parameters, {"parts"}, "Parameter")
    parts = parameters["parts"]
    if not isinstance(parts, list) or not parts:
        raise OperationValidationError("SplitEntity parts must be a non-empty list")
    output_names: set[str] = set()
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise OperationValidationError(f"SplitEntity part {index} must be an object")
        _require_exact_keys(
            part, {"entity_id", "output_name", "selector"}, f"SplitEntity part {index}"
        )
        if not isinstance(part["entity_id"], str) or not part["entity_id"].startswith("entity:"):
            raise OperationValidationError(f"SplitEntity part {index} has invalid entity_id")
        output_name = part["output_name"]
        if not isinstance(output_name, str) or not output_name or "." in output_name:
            raise OperationValidationError(f"SplitEntity part {index} has invalid output_name")
        if output_name in output_names:
            raise OperationValidationError("SplitEntity output names must be unique")
        output_names.add(output_name)
        selector = part["selector"]
        if not isinstance(selector, dict):
            raise OperationValidationError(f"SplitEntity part {index} selector must be an object")
        _require_exact_keys(
            selector,
            {"type", "x", "y", "width", "height"},
            f"SplitEntity part {index} selector",
        )
        if selector["type"] != "bounds_fraction":
            raise OperationValidationError(
                f"SplitEntity part {index} selector type must be bounds_fraction"
            )
        for name in ("x", "y", "width", "height"):
            _require_number(selector[name], f"parts[{index}].selector.{name}")
        x = float(selector["x"])
        y = float(selector["y"])
        width = float(selector["width"])
        height = float(selector["height"])
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
            raise OperationValidationError(
                f"SplitEntity part {index} selector must lie inside normalized bounds"
            )


def _split_outputs(operation: Mapping[str, Any]) -> Mapping[str, ValueType]:
    return {part["output_name"]: ValueType.GEOMETRY for part in operation["parameters"]["parts"]}


@dataclass(frozen=True)
class OperationDefinition:
    type_name: str
    inputs: Mapping[str, ValueType]
    outputs: Mapping[str, ValueType] | OutputResolver
    validate_parameters: ParameterValidator
    executor: OperationExecutor
    quality_sensitive: bool = False

    def output_signature(self, operation: Mapping[str, Any]) -> Mapping[str, ValueType]:
        if callable(self.outputs):
            return dict(self.outputs(operation))
        return dict(self.outputs)

    def validate(self, operation: Mapping[str, Any]) -> None:
        _require_exact_keys(operation.get("inputs", {}), set(self.inputs), "Input")
        self.validate_parameters(operation.get("parameters", {}))
        outputs = self.output_signature(operation)
        if not outputs or any(not name for name in outputs):
            raise OperationValidationError(f"{self.type_name} must declare outputs")

    def evaluate(
        self,
        operation: Mapping[str, Any],
        inputs: Mapping[str, Any],
        quality: str,
    ) -> dict[str, Any]:
        result = self.executor(operation.get("parameters", {}), inputs, quality)
        expected = set(self.output_signature(operation))
        if set(result) != expected:
            raise OperationValidationError(
                f"{self.type_name} evaluator returned {sorted(result)}; expected {sorted(expected)}"
            )
        return result


class OperationRegistry:
    def __init__(self, semantics_version: str):
        self.semantics_version = semantics_version
        self._definitions: dict[str, OperationDefinition] = {}

    def register(self, definition: OperationDefinition) -> None:
        if definition.type_name in self._definitions:
            raise OperationValidationError(
                f"Operation type already registered: {definition.type_name}"
            )
        self._definitions[definition.type_name] = definition

    def definition(self, type_name: str) -> OperationDefinition:
        try:
            return self._definitions[type_name]
        except KeyError as exc:
            raise OperationValidationError(f"Unsupported operation type: {type_name}") from exc

    def validate(self, operation: Mapping[str, Any]) -> None:
        self.definition(operation.get("type", "")).validate(operation)

    def input_signature(self, operation: Mapping[str, Any]) -> Mapping[str, ValueType]:
        return dict(self.definition(operation["type"]).inputs)

    def output_signature(self, operation: Mapping[str, Any]) -> Mapping[str, ValueType]:
        return self.definition(operation["type"]).output_signature(operation)

    def evaluate(
        self,
        operation: Mapping[str, Any],
        inputs: Mapping[str, Any],
        quality: str,
    ) -> dict[str, Any]:
        return self.definition(operation["type"]).evaluate(operation, inputs, quality)

    @property
    def type_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))


def _create_ellipse(parameters: Mapping[str, Any], _: Mapping[str, Any], __: str) -> dict[str, Any]:
    return {
        "geometry": {
            "kind": "ellipse",
            "cx": parameters["cx"],
            "cy": parameters["cy"],
            "rx": parameters["rx"],
            "ry": parameters["ry"],
        }
    }


def _create_rectangle(
    parameters: Mapping[str, Any], _: Mapping[str, Any], __: str
) -> dict[str, Any]:
    return {"geometry": {"kind": "rectangle", **parameters}}


def _transform(parameters: Mapping[str, Any], inputs: Mapping[str, Any], _: str) -> dict[str, Any]:
    return {
        "geometry": {
            "kind": "transform",
            "source": inputs["geometry"],
            "matrix": parameters["matrix"],
        }
    }


def _convert_to_path(_: Mapping[str, Any], inputs: Mapping[str, Any], __: str) -> dict[str, Any]:
    return {"geometry": {"kind": "path", "source": inputs["geometry"]}}


def _create_path(parameters: Mapping[str, Any], _: Mapping[str, Any], __: str) -> dict[str, Any]:
    return {
        "geometry": {
            "kind": "path_data",
            "d": parameters["d"],
            "bounds": parameters["bounds"],
        }
    }


def _refine_bezier(
    parameters: Mapping[str, Any], inputs: Mapping[str, Any], quality: str
) -> dict[str, Any]:
    return {
        "geometry": {
            "kind": "refined_path",
            "source": inputs["geometry"],
            "tolerance": parameters["tolerance"],
            "quality": quality,
        }
    }


def _clip(_: Mapping[str, Any], inputs: Mapping[str, Any], __: str) -> dict[str, Any]:
    return {
        "geometry": {
            "kind": "clip",
            "content": inputs["content"],
            "clip": inputs["clip"],
        }
    }


def _split_entity(
    parameters: Mapping[str, Any], inputs: Mapping[str, Any], _: str
) -> dict[str, Any]:
    source = inputs["geometry"]
    min_x, min_y, max_x, max_y = _geometry_bounds(source)
    source_width = max_x - min_x
    source_height = max_y - min_y
    return {
        part["output_name"]: {
            "kind": "clip",
            "content": source,
            "clip": {
                "kind": "rectangle",
                "x": min_x + source_width * float(part["selector"]["x"]),
                "y": min_y + source_height * float(part["selector"]["y"]),
                "width": source_width * float(part["selector"]["width"]),
                "height": source_height * float(part["selector"]["height"]),
            },
        }
        for part in parameters["parts"]
    }


def _geometry_bounds(geometry: Mapping[str, Any]) -> tuple[float, float, float, float]:
    kind = geometry.get("kind")
    if kind == "ellipse":
        cx = float(geometry["cx"])
        cy = float(geometry["cy"])
        rx = float(geometry["rx"])
        ry = float(geometry["ry"])
        return cx - rx, cy - ry, cx + rx, cy + ry
    if kind == "rectangle":
        x = float(geometry["x"])
        y = float(geometry["y"])
        return x, y, x + float(geometry["width"]), y + float(geometry["height"])
    if kind in {"path", "refined_path"}:
        return _geometry_bounds(geometry["source"])
    if kind == "path_data":
        min_x, min_y, max_x, max_y = (float(value) for value in geometry["bounds"])
        return min_x, min_y, max_x, max_y
    if kind == "transform":
        min_x, min_y, max_x, max_y = _geometry_bounds(geometry["source"])
        a, b, c, d, e, f = (float(value) for value in geometry["matrix"])
        transformed = tuple(
            (a * x + c * y + e, b * x + d * y + f)
            for x, y in ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))
        )
        return (
            min(point[0] for point in transformed),
            min(point[1] for point in transformed),
            max(point[0] for point in transformed),
            max(point[1] for point in transformed),
        )
    if kind == "clip":
        content = _geometry_bounds(geometry["content"])
        clip = _geometry_bounds(geometry["clip"])
        result = (
            max(content[0], clip[0]),
            max(content[1], clip[1]),
            min(content[2], clip[2]),
            min(content[3], clip[3]),
        )
        if result[0] > result[2] or result[1] > result[3]:
            raise OperationValidationError("Clip geometry has empty bounds")
        return result
    raise OperationValidationError(f"Cannot compute bounds for geometry kind {kind!r}")


def _build_core_registry() -> OperationRegistry:
    geometry = ValueType.GEOMETRY
    registry = OperationRegistry("svm-core-0.1")
    definitions = (
        OperationDefinition(
            "CreateEllipse",
            {},
            {"geometry": geometry},
            _numeric_parameters("cx", "cy", "rx", "ry"),
            _create_ellipse,
        ),
        OperationDefinition(
            "CreateRectangle",
            {},
            {"geometry": geometry},
            _numeric_parameters("x", "y", "width", "height"),
            _create_rectangle,
        ),
        OperationDefinition(
            "CreatePath",
            {},
            {"geometry": geometry},
            _path_parameters,
            _create_path,
        ),
        OperationDefinition(
            "Transform",
            {"geometry": geometry},
            {"geometry": geometry},
            _transform_parameters,
            _transform,
        ),
        OperationDefinition(
            "ConvertToPath",
            {"geometry": geometry},
            {"geometry": geometry},
            _no_parameters,
            _convert_to_path,
        ),
        OperationDefinition(
            "RefineBezier",
            {"geometry": geometry},
            {"geometry": geometry},
            _numeric_parameters("tolerance"),
            _refine_bezier,
            quality_sensitive=True,
        ),
        OperationDefinition(
            "Clip",
            {"content": geometry, "clip": geometry},
            {"geometry": geometry},
            _no_parameters,
            _clip,
        ),
        OperationDefinition(
            "SplitEntity",
            {"geometry": geometry},
            _split_outputs,
            _split_parameters,
            _split_entity,
        ),
    )
    for definition in definitions:
        registry.register(definition)
    return registry


_REGISTRIES = {"svm-core-0.1": _build_core_registry()}


def get_operation_registry(semantics_version: str) -> OperationRegistry:
    try:
        return _REGISTRIES[semantics_version]
    except KeyError as exc:
        raise OperationValidationError(
            f"Unsupported semantics version: {semantics_version}"
        ) from exc
