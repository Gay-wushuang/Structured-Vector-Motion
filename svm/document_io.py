from __future__ import annotations

import copy
import json
import sysconfig
from pathlib import Path
from typing import Any

from .document import AUTHORED_GROUP_TYPE, DocumentDialect, validate_document
from .evaluator import DocumentError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def select_document_dialect(document: Any) -> DocumentDialect:
    """Select only the versioned authored extension; all other input stays baseline."""
    if not isinstance(document, dict):
        return DocumentDialect.BASELINE
    groups = document.get("groups", [])
    if isinstance(groups, list) and any(
        isinstance(group, dict)
        and isinstance(group.get("provenance"), dict)
        and group["provenance"].get("type") == AUTHORED_GROUP_TYPE
        for group in groups
    ):
        return DocumentDialect.AUTHORED_GROUP_ASSEMBLY
    return DocumentDialect.BASELINE


def schema_path(dialect: DocumentDialect) -> Path:
    if not isinstance(dialect, DocumentDialect):
        raise DocumentError("Unsupported Document dialect")
    filename = {
        DocumentDialect.BASELINE: "svm-document-v0.1.schema.json",
        DocumentDialect.AUTHORED_GROUP_ASSEMBLY: (
            "svm-document-v0.1-authored-group-assembly-v0.1.schema.json"
        ),
    }[dialect]
    source = REPOSITORY_ROOT / "schema" / filename
    installed = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "structured-vector-motion"
        / "schema"
        / filename
    )
    for candidate in (source, installed):
        if candidate.is_file():
            return candidate
    raise DocumentError(f"Cannot locate Document schema {filename}")


def validate_document_schema(document: Any, dialect: DocumentDialect) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise DocumentError("JSON Schema validation requires the 'jsonschema' package") from exc
    schema = json.loads(schema_path(dialect).read_text(encoding="utf-8"))
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        raise DocumentError(f"Schema validation failed at {location}: {exc.message}") from exc


def read_document(
    path: Path, *, dialect: DocumentDialect | None = None
) -> tuple[dict[str, Any], DocumentDialect]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentError(f"Cannot read Document {path}: {exc}") from exc
    selected = select_document_dialect(document) if dialect is None else dialect
    validate_document_schema(document, selected)
    validate_document(document, selected)
    return copy.deepcopy(document), selected


def write_document(
    path: Path,
    document: dict[str, Any],
    *,
    dialect: DocumentDialect | None = None,
) -> DocumentDialect:
    selected = select_document_dialect(document) if dialect is None else dialect
    validate_document_schema(document, selected)
    validate_document(document, selected)
    try:
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise DocumentError(f"Cannot write Document {path}: {exc}") from exc
    return selected
