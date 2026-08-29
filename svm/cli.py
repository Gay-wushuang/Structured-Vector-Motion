from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import sysconfig
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from .artifacts import ArtifactKind, ArtifactStore
from .document import validate_document
from .evaluator import DocumentError, Evaluator, Quality, canonical_bytes
from .proposals import AdapterRequest, ProposalAcceptor
from .renderers import SVGRenderer, SVGRenderOptions
from .revisions import RevisionStore, SetOperationParameterChange, Transaction
from .scene import build_evaluated_scene

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _schema_path() -> Path:
    source_path = REPOSITORY_ROOT / "schema" / "svm-document-v0.1.schema.json"
    installed_path = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "structured-vector-motion"
        / "schema"
        / "svm-document-v0.1.schema.json"
    )
    for candidate in (source_path, installed_path):
        if candidate.is_file():
            return candidate
    raise CliError("Cannot locate svm-document-v0.1.schema.json")


class CliError(ValueError):
    pass


def _write_json(value: Any, stream: TextIO) -> None:
    json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
    stream.write("\n")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"Cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def _validate_schema(document: Any) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise CliError("JSON Schema validation requires the 'jsonschema' package") from exc
    schema = _read_json(_schema_path())
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise CliError(f"Schema validation failed at {location}: {exc.message}") from exc


def load_and_validate(path: Path) -> dict[str, Any]:
    document = _read_json(path)
    _validate_schema(document)
    try:
        validate_document(document)
    except (DocumentError, KeyError, TypeError) as exc:
        raise CliError(f"Semantic validation failed: {exc}") from exc
    return document


def _quality(value: str) -> Quality:
    return Quality(value.upper())


def _geometry_backend(name: str | None) -> Any:
    if name is None:
        return None
    if name != "shapely":
        raise CliError(f"Unknown geometry backend {name!r}")
    try:
        from .backends.shapely_geometry import ShapelyGeometryBackend
    except ImportError as exc:
        raise CliError("Shapely geometry backend requires the 'geometry' extra") from exc
    return ShapelyGeometryBackend()


def _parse_assignment(expression: str) -> tuple[str, str, Any]:
    if "=" not in expression:
        raise CliError(
            f"Invalid assignment {expression!r}; expected op:<id>.<parameter>=<json-value>"
        )
    target, raw_value = expression.split("=", 1)
    if "." not in target:
        raise CliError(f"Invalid assignment target {target!r}; expected op:<id>.<parameter>")
    operation_id, parameter = target.rsplit(".", 1)
    if not operation_id.startswith("op:") or not parameter:
        raise CliError(f"Invalid assignment target {target!r}")
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise CliError(f"Assignment value must be JSON: {raw_value!r}") from exc
    return operation_id, parameter, value


def _runtime_report(evaluator: Evaluator, include_values: bool) -> dict[str, Any]:
    operations: dict[str, Any] = {}
    for operation_id in evaluator._topological_order():
        node = evaluator.runtime[operation_id]
        outputs: dict[str, Any] = {}
        for name, value in (node.outputs or {}).items():
            output = {"value_id": value.value_id}
            if include_values:
                output["payload"] = value.payload
            outputs[name] = output
        operations[operation_id] = {
            "state": node.state.value,
            "evaluated_quality": node.evaluated_quality.value if node.evaluated_quality else None,
            "backend_identity": node.backend_identity,
            "evaluation_key": node.evaluation_key,
            "outputs": outputs,
            "error": node.error,
        }
    return {"operations": operations}


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    document = load_and_validate(args.document)
    return {
        "valid": True,
        "document_id": document["document_id"],
        "schema_version": document["schema_version"],
        "semantics_version": document["semantics_version"],
    }


def command_inspect(args: argparse.Namespace) -> dict[str, Any]:
    document = load_and_validate(args.document)
    evaluator = Evaluator(document)
    operations = []
    for operation_id in evaluator._topological_order():
        operation = evaluator.operations[operation_id]
        definition = evaluator.registry.definition(operation["type"])
        operations.append(
            {
                "id": operation_id,
                "type": operation["type"],
                "dependencies": sorted(evaluator.dependencies[operation_id]),
                "inputs": {
                    name: value_type.value for name, value_type in definition.inputs.items()
                },
                "outputs": {
                    name: value_type.value
                    for name, value_type in definition.output_signature(operation).items()
                },
                "quality_sensitive": definition.quality_sensitive,
                "capability": definition.capability,
                "algorithm_identity": definition.algorithm_identity,
            }
        )
    return {
        "document_id": document["document_id"],
        "references": copy.deepcopy(document["references"]),
        "entities": copy.deepcopy(document["entities"]),
        "operations": operations,
        "output_bindings": copy.deepcopy(document["construction"]["output_bindings"]),
        "render_stack": copy.deepcopy(document["presentation"]["render_stack"]),
        "styles": copy.deepcopy(document["presentation"].get("styles", [])),
    }


def command_evaluate(args: argparse.Namespace) -> dict[str, Any]:
    document = load_and_validate(args.document)
    evaluator = Evaluator(document, geometry_backend=_geometry_backend(args.geometry_backend))
    evaluator.evaluate_all(args.quality)
    report = _runtime_report(evaluator, args.include_values)
    report.update(
        {
            "document_id": document["document_id"],
            "quality": args.quality.value,
        }
    )
    return report


def command_mutate(args: argparse.Namespace) -> dict[str, Any]:
    document = load_and_validate(args.document)
    assignments = [_parse_assignment(expression) for expression in args.set_values]
    changes = tuple(
        SetOperationParameterChange(operation_id, parameter, value)
        for operation_id, parameter, value in assignments
    )
    transaction_digest = hashlib.sha256(canonical_bytes(assignments)).hexdigest()[:16]
    transaction = Transaction(
        transaction_id=f"transaction:cli-mutate:{transaction_digest}",
        changes=changes,
        message="CLI parameter mutation",
    )
    store = RevisionStore.create(document)
    base_revision_id = store.head
    if base_revision_id is None:
        raise CliError("Revision Store did not create an initial head")
    revision = store.commit(base_revision_id, transaction)
    mutated = store.get_document(revision.revision_id)
    if args.output:
        args.output.write_text(
            json.dumps(mutated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "written": str(args.output),
            "base_revision_id": base_revision_id,
            "revision_id": revision.revision_id,
            "transaction_id": transaction.transaction_id,
        }
    return mutated


def command_reevaluate(args: argparse.Namespace) -> dict[str, Any]:
    document = load_and_validate(args.document)
    assignments = [_parse_assignment(expression) for expression in args.set_values]
    if not assignments and not args.invalidate:
        raise CliError("reevaluate requires at least one --set or --invalidate")

    # Validate the entire prospective mutation before touching the live runtime.
    candidate = Evaluator(copy.deepcopy(document))
    for operation_id, parameter, value in assignments:
        candidate.set_parameter(operation_id, parameter, value)

    evaluator = Evaluator(document, geometry_backend=_geometry_backend(args.geometry_backend))
    evaluator.evaluate_all(args.from_quality)
    before = {
        operation_id: {name: value.value_id for name, value in (node.outputs or {}).items()}
        for operation_id, node in evaluator.runtime.items()
    }
    invalidated: set[str] = set()
    for operation_id, parameter, value in assignments:
        invalidated.update(evaluator.set_parameter(operation_id, parameter, value))
    for operation_id in args.invalidate:
        invalidated.update(evaluator.invalidate(operation_id))

    evaluator.evaluate_all(args.quality)
    after = {
        operation_id: {name: value.value_id for name, value in (node.outputs or {}).items()}
        for operation_id, node in evaluator.runtime.items()
    }
    changed = sorted(
        operation_id
        for operation_id in evaluator.operations
        if before[operation_id] != after[operation_id]
    )
    report = _runtime_report(evaluator, args.include_values)
    report.update(
        {
            "document_id": document["document_id"],
            "from_quality": args.from_quality.value,
            "quality": args.quality.value,
            "invalidated": sorted(invalidated),
            "changed_values": changed,
        }
    )
    return report


def command_render_svg(args: argparse.Namespace) -> dict[str, Any]:
    document = load_and_validate(args.document)
    evaluator = Evaluator(document, geometry_backend=_geometry_backend(args.geometry_backend))
    scene = build_evaluated_scene(document, evaluator, Quality.FINAL)
    options = SVGRenderOptions(
        width=args.width,
        height=args.height,
        view_box=tuple(args.view_box),
        fill=args.fill,
        stroke=args.stroke,
        stroke_width=args.stroke_width,
    )
    svg = SVGRenderer(options).render(scene)
    svg_bytes = svg.encode("utf-8")
    args.output.write_bytes(svg_bytes)
    return {
        "written": str(args.output),
        "document_id": document["document_id"],
        "quality": Quality.FINAL.value,
        "entities": len(scene.entities),
        "bytes": len(svg_bytes),
    }


def command_import_svg(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from .adapters import SVGImportAdapter
    except ImportError as exc:
        raise CliError("SVG import requires the 'svg' optional dependency") from exc
    document = load_and_validate(args.document)
    try:
        source_bytes = args.svg.read_bytes()
    except OSError as exc:
        raise CliError(f"Cannot read {args.svg}: {exc}") from exc
    artifact_store = ArtifactStore()
    artifact = artifact_store.import_bytes(
        source_bytes,
        media_type="image/svg+xml",
        kind=ArtifactKind.REFERENCE,
        provenance={"source_name": args.svg.name},
    )
    store = RevisionStore.create(document)
    base_revision_id = store.head
    if base_revision_id is None:
        raise CliError("Revision Store did not create an initial head")
    request = AdapterRequest.from_store(
        store,
        base_revision_id,
        ("document",),
        artifact_ids=(artifact.artifact_id,),
        options={"namespace": args.namespace} if args.namespace else {},
    )
    proposal = SVGImportAdapter().propose(request, artifact_store)
    revision = ProposalAcceptor().accept(store, proposal, artifact_store)
    imported = store.get_document(revision.revision_id)
    output_bytes = (
        json.dumps(imported, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    args.output.write_bytes(output_bytes)
    return {
        "written": str(args.output),
        "artifact_id": artifact.artifact_id,
        "proposal_id": proposal.proposal_id,
        "revision_id": revision.revision_id,
        "imported_entities": len(imported["entities"]) - len(document["entities"]),
        "bytes": len(output_bytes),
    }


def command_trace_bitmap(args: argparse.Namespace) -> dict[str, Any]:
    from .adapters import BitmapTraceAdapter

    document = load_and_validate(args.document)
    try:
        source_bytes = args.bitmap.read_bytes()
    except OSError as exc:
        raise CliError(f"Cannot read {args.bitmap}: {exc}") from exc
    artifact_store = ArtifactStore()
    artifact = artifact_store.import_bytes(
        source_bytes,
        media_type="image/png",
        kind=ArtifactKind.REFERENCE,
        provenance={"source_name": args.bitmap.name},
    )
    store = RevisionStore.create(document)
    base_revision_id = store.head
    if base_revision_id is None:
        raise CliError("Revision Store did not create an initial head")
    options = {
        "threshold": args.threshold,
        "invert": args.invert,
        "turd_size": args.turd_size,
        "turn_policy": args.turn_policy,
        "alpha_max": args.alpha_max,
        "optimize_curve": not args.no_optimize_curve,
        "optimization_tolerance": args.optimization_tolerance,
        "path_tolerance": args.path_tolerance,
        "fill_rule": args.fill_rule,
    }
    if args.namespace:
        options["namespace"] = args.namespace
    request = AdapterRequest.from_store(
        store,
        base_revision_id,
        ("document",),
        artifact_ids=(artifact.artifact_id,),
        options=options,
    )
    proposal = BitmapTraceAdapter().propose(request, artifact_store)
    revision = ProposalAcceptor().accept(store, proposal, artifact_store)
    traced = store.get_document(revision.revision_id)
    output_bytes = (json.dumps(traced, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    args.output.write_bytes(output_bytes)
    return {
        "written": str(args.output),
        "artifact_id": artifact.artifact_id,
        "proposal_id": proposal.proposal_id,
        "revision_id": revision.revision_id,
        "traced_paths": proposal.report.metrics["traced_paths"],
        "structured_entities": proposal.report.metrics["structured_entities"],
        "bytes": len(output_bytes),
    }


def command_retrace_bitmap(args: argparse.Namespace) -> dict[str, Any]:
    from .adapters import BitmapReconcileAdapter

    document = load_and_validate(args.document)
    try:
        source_bytes = args.bitmap.read_bytes()
    except OSError as exc:
        raise CliError(f"Cannot read {args.bitmap}: {exc}") from exc
    artifact_store = ArtifactStore()
    artifact = artifact_store.import_bytes(
        source_bytes,
        media_type="image/png",
        kind=ArtifactKind.REFERENCE,
        provenance={"source_name": args.bitmap.name},
    )
    store = RevisionStore.create(document)
    base_revision_id = store.head
    if base_revision_id is None:
        raise CliError("Revision Store did not create an initial head")
    options = {
        "namespace": args.namespace,
        "match_score_threshold": args.match_score_threshold,
        "threshold": args.threshold,
        "invert": args.invert,
        "turd_size": args.turd_size,
        "turn_policy": args.turn_policy,
        "alpha_max": args.alpha_max,
        "optimize_curve": not args.no_optimize_curve,
        "optimization_tolerance": args.optimization_tolerance,
        "path_tolerance": args.path_tolerance,
        "fill_rule": args.fill_rule,
    }
    request = AdapterRequest.from_store(
        store,
        base_revision_id,
        tuple(args.entity),
        artifact_ids=(artifact.artifact_id,),
        options=options,
    )
    proposal = BitmapReconcileAdapter().propose(request, artifact_store)
    if proposal.preview is None:
        raise CliError("Reconciliation Adapter did not produce a preview")
    result: dict[str, Any] = {
        "accepted": False,
        "artifact_id": artifact.artifact_id,
        "proposal_id": proposal.proposal_id,
        "base_revision_id": proposal.base_revision_id,
        "metrics": proposal.report.metrics,
        "preview": {
            "entity_diffs": [
                {
                    "status": item.status,
                    "entity_id": item.entity_id,
                    "proposed_entity_id": item.proposed_entity_id,
                    "match_score": (
                        {
                            "iou": item.match_score.iou,
                            "centroid": item.match_score.centroid,
                            "area": item.match_score.area,
                            "contour": item.match_score.contour,
                            "composite": item.match_score.composite,
                        }
                        if item.match_score is not None
                        else None
                    ),
                    "before_bounds": item.before_bounds,
                    "after_bounds": item.after_bounds,
                }
                for item in proposal.preview.entity_diffs
            ],
            "proposed_render_stack": proposal.preview.proposed_render_stack,
        },
    }
    if args.accept:
        if args.output is None:
            raise CliError("retrace-bitmap --accept requires --output")
        revision = ProposalAcceptor().accept(store, proposal, artifact_store)
        reconciled = store.get_document(revision.revision_id)
        args.output.write_text(
            json.dumps(reconciled, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result.update(
            {
                "accepted": True,
                "revision_id": revision.revision_id,
                "written": str(args.output),
            }
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="svm", description="SVM v0.1 reference CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate schema and semantics")
    validate.add_argument("document", type=Path)
    validate.set_defaults(handler=command_validate)

    inspect = subparsers.add_parser("inspect", help="inspect entities and Operation signatures")
    inspect.add_argument("document", type=Path)
    inspect.set_defaults(handler=command_inspect)

    evaluate = subparsers.add_parser("evaluate", help="evaluate all Operations")
    evaluate.add_argument("document", type=Path)
    evaluate.add_argument("--quality", type=_quality, default=Quality.PREVIEW)
    evaluate.add_argument("--include-values", action="store_true")
    evaluate.add_argument("--geometry-backend", choices=("shapely",))
    evaluate.set_defaults(handler=command_evaluate)

    mutate = subparsers.add_parser("mutate", help="atomically change Operation parameters")
    mutate.add_argument("document", type=Path)
    mutate.add_argument("--set", dest="set_values", action="append", required=True)
    mutate.add_argument("--output", type=Path)
    mutate.set_defaults(handler=command_mutate)

    reevaluate = subparsers.add_parser(
        "reevaluate", help="evaluate, invalidate or mutate, then reevaluate"
    )
    reevaluate.add_argument("document", type=Path)
    reevaluate.add_argument("--set", dest="set_values", action="append", default=[])
    reevaluate.add_argument("--invalidate", action="append", default=[])
    reevaluate.add_argument("--from-quality", type=_quality, default=Quality.PREVIEW)
    reevaluate.add_argument("--quality", type=_quality, default=Quality.PREVIEW)
    reevaluate.add_argument("--include-values", action="store_true")
    reevaluate.add_argument("--geometry-backend", choices=("shapely",))
    reevaluate.set_defaults(handler=command_reevaluate)

    render_svg = subparsers.add_parser(
        "render-svg", help="evaluate at FINAL quality and render an SVG"
    )
    render_svg.add_argument("document", type=Path)
    render_svg.add_argument("--output", type=Path, required=True)
    render_svg.add_argument("--width", type=int, default=1024)
    render_svg.add_argument("--height", type=int, default=1024)
    render_svg.add_argument(
        "--view-box",
        type=float,
        nargs=4,
        metavar=("MIN_X", "MIN_Y", "WIDTH", "HEIGHT"),
        default=(-2.0, -2.0, 4.0, 4.0),
    )
    render_svg.add_argument("--fill", default="none")
    render_svg.add_argument("--stroke", default="#000000")
    render_svg.add_argument("--stroke-width", type=float, default=0.01)
    render_svg.add_argument("--geometry-backend", choices=("shapely",))
    render_svg.set_defaults(handler=command_render_svg)

    import_svg = subparsers.add_parser(
        "import-svg", help="import a deterministic flat SVG through the Adapter boundary"
    )
    import_svg.add_argument("document", type=Path, help="base SVM Document")
    import_svg.add_argument("svg", type=Path, help="source SVG Artifact")
    import_svg.add_argument("--output", type=Path, required=True)
    import_svg.add_argument("--namespace")
    import_svg.set_defaults(handler=command_import_svg)

    trace_bitmap = subparsers.add_parser(
        "trace-bitmap", help="trace a PNG through the deterministic Adapter boundary"
    )
    trace_bitmap.add_argument("document", type=Path, help="base SVM Document")
    trace_bitmap.add_argument("bitmap", type=Path, help="source PNG Artifact")
    trace_bitmap.add_argument("--output", type=Path, required=True)
    trace_bitmap.add_argument("--namespace")
    trace_bitmap.add_argument("--threshold", type=int, default=128)
    trace_bitmap.add_argument("--invert", action="store_true")
    trace_bitmap.add_argument("--turd-size", type=int, default=2)
    trace_bitmap.add_argument(
        "--turn-policy",
        choices=("black", "white", "left", "right", "minority", "majority"),
        default="minority",
    )
    trace_bitmap.add_argument("--alpha-max", type=float, default=1.0)
    trace_bitmap.add_argument("--no-optimize-curve", action="store_true")
    trace_bitmap.add_argument("--optimization-tolerance", type=float, default=0.2)
    trace_bitmap.add_argument("--path-tolerance", type=float, default=0.25)
    trace_bitmap.add_argument("--fill-rule", choices=("nonzero", "evenodd"), default="nonzero")
    trace_bitmap.set_defaults(handler=command_trace_bitmap)

    retrace_bitmap = subparsers.add_parser(
        "retrace-bitmap", help="preview and optionally accept trace Entity reconciliation"
    )
    retrace_bitmap.add_argument("document", type=Path, help="accepted SVM Document")
    retrace_bitmap.add_argument("bitmap", type=Path, help="replacement PNG Artifact")
    retrace_bitmap.add_argument("--entity", action="append", required=True)
    retrace_bitmap.add_argument("--namespace", default="reconciled")
    retrace_bitmap.add_argument(
        "--match-score-threshold",
        "--match-iou-threshold",
        dest="match_score_threshold",
        type=float,
        default=0.65,
        help="minimum composite match score; old option name remains an alias",
    )
    retrace_bitmap.add_argument("--accept", action="store_true")
    retrace_bitmap.add_argument("--output", type=Path)
    retrace_bitmap.add_argument("--threshold", type=int, default=128)
    retrace_bitmap.add_argument("--invert", action="store_true")
    retrace_bitmap.add_argument("--turd-size", type=int, default=2)
    retrace_bitmap.add_argument(
        "--turn-policy",
        choices=("black", "white", "left", "right", "minority", "majority"),
        default="minority",
    )
    retrace_bitmap.add_argument("--alpha-max", type=float, default=1.0)
    retrace_bitmap.add_argument("--no-optimize-curve", action="store_true")
    retrace_bitmap.add_argument("--optimization-tolerance", type=float, default=0.2)
    retrace_bitmap.add_argument("--path-tolerance", type=float, default=0.25)
    retrace_bitmap.add_argument("--fill-rule", choices=("nonzero", "evenodd"), default="nonzero")
    retrace_bitmap.set_defaults(handler=command_retrace_bitmap)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = args.handler(args)
        _write_json(result, sys.stdout)
        return 0
    except (CliError, DocumentError, KeyError, OSError, ValueError) as exc:
        _write_json({"error": str(exc), "type": type(exc).__name__}, sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
