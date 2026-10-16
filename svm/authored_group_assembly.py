"""Spec82 G2: single-Base authored assembly verification, not a Producer.

Only the current committed Base authenticates membership. Artifact bytes and
ancestor history confer no authority here; the Acceptor pins the source Base.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from .artifacts import ArtifactSnapshot
from .document import (
    AUTHORED_GROUP_AUTHORITY,
    AUTHORED_GROUP_TYPE,
    DocumentDialect,
    authored_group_identity,
    validate_document,
)
from .evaluator import canonical_bytes
from .revisions import (
    AdmissionEvent,
    AdmittedRevision,
    AssembleAuthoredGroupChange,
    Revision,
    RevisionStore,
)

CHANGE_IDENTITY = "svm.revisions.AssembleAuthoredGroupChange@0.1"
_FIELDS = (
    "source_revision_id",
    "authority_identity",
    "base_document_snapshot",
    "base_revision",
    "member_ids",
    "initial_transform",
    "group",
)
_REVISION_FIELDS = {"revision_id", "parent_ids", "transaction_id", "document_hash", "message"}
_ADMISSION_FIELDS = {
    "contract",
    "change_identity",
    "authority_identity",
    "base_revision_id",
    "artifact_reference",
    "transition_hash",
}


class AuthoredGroupAssemblyError(ValueError):
    pass


def _fail(message: str) -> None:
    raise AuthoredGroupAssemblyError(message)


def _json_data(value: Any, active: set[int]) -> bool:
    """Reject executable subclasses and cycles before hashing or copying data."""
    if type(value) in {dict, list}:
        identity = id(value)
        if identity in active:
            return False
        active.add(identity)
        try:
            if type(value) is dict:
                return all(
                    type(key) is str and _json_data(item, active) for key, item in value.items()
                )
            return all(_json_data(item, active) for item in value)
        finally:
            active.remove(identity)
    if type(value) is float:
        return math.isfinite(value)
    return value is None or type(value) in {str, int, bool}


def _require_json_object(value: Any, label: str) -> None:
    if type(value) is not dict or not _json_data(value, set()):
        _fail(f"Authored assembly requires native finite JSON {label}")


def _record_fields(record: Any, expected: set[str]) -> bool:
    attributes = vars(record)
    return (
        type(attributes) is dict
        and all(type(key) is str for key in attributes)
        and set(attributes) == expected
    )


def _identifier(value: Any, prefix: str) -> bool:
    return type(value) is str and re.fullmatch(prefix + r":[0-9a-f]{64}", value) is not None


def _validate_revision(revision: Any) -> None:
    if type(revision) not in {Revision, AdmittedRevision} or not _record_fields(
        revision,
        _REVISION_FIELDS | ({"admissions"} if type(revision) is AdmittedRevision else set()),
    ):
        _fail("Authored assembly requires exact complete Revision fields")
    if (
        not _identifier(revision.revision_id, "revision")
        or not _identifier(revision.document_hash, "sha256")
        or type(revision.parent_ids) is not tuple
        or any(not _identifier(parent, "revision") for parent in revision.parent_ids)
        or type(revision.message) is not str
        or (revision.transaction_id is not None and type(revision.transaction_id) is not str)
    ):
        _fail("Authored assembly Revision metadata is invalid")
    if type(revision) is Revision:
        return
    if type(revision.admissions) is not tuple or not revision.admissions:
        _fail("Authored assembly AdmittedRevision requires complete admissions")
    for event in revision.admissions:
        if type(event) is not AdmissionEvent or not _record_fields(event, _ADMISSION_FIELDS):
            _fail("Authored assembly requires exact AdmissionEvent fields")
        if any(
            type(getattr(event, name)) is not str or not getattr(event, name)
            for name in _ADMISSION_FIELDS - {"artifact_reference"}
        ):
            _fail("Authored assembly AdmissionEvent metadata is invalid")
        _require_json_object(event.artifact_reference, "admission reference")


def _verified_group(change: Any) -> dict[str, Any]:
    if type(change) is not AssembleAuthoredGroupChange or any(
        not hasattr(change, name) for name in _FIELDS
    ):
        _fail("Authored assembly requires the exact closed Change type and fields")
    if (
        not _identifier(change.source_revision_id, "revision")
        or type(change.authority_identity) is not str
        or change.authority_identity != AUTHORED_GROUP_AUTHORITY
    ):
        _fail("Authored assembly source or authority identity is invalid")
    _require_json_object(change.base_document_snapshot, "Base snapshot")
    _require_json_object(change.group, "Group")
    if change.initial_transform is not None:
        _require_json_object(change.initial_transform, "initial transform")
    _validate_revision(change.base_revision)
    members = change.member_ids
    if (
        type(members) is not tuple
        or len(members) < 2
        or any(type(member) is not str or not member.startswith("entity:") for member in members)
        or members != tuple(sorted(set(members)))
    ):
        _fail("Authored assembly members must be sorted unique Entity IDs, at least two")

    revision = change.base_revision
    reconstructed = RevisionStore._make_revision(
        change.base_document_snapshot,
        revision.parent_ids,
        revision.transaction_id,
        revision.message,
        revision.admissions if type(revision) is AdmittedRevision else (),
    )
    if reconstructed != revision or reconstructed.revision_id != change.source_revision_id:
        _fail("Authored assembly complete Base Revision commitment mismatch")
    base = copy.deepcopy(change.base_document_snapshot)
    validate_document(base, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
    entity_ids = {entity["id"] for entity in base["entities"]}
    if any(member not in entity_ids for member in members):
        _fail("Authored assembly member is absent from the authenticated Base")
    group_id, membership_hash = authored_group_identity(list(members))
    if any(group["id"] == group_id for group in base.get("groups", [])):
        _fail("Authored assembly Group ID collision")
    group: dict[str, Any] = {
        "id": group_id,
        "kind": "explicit-group",
        "members": list(members),
        "provenance": {
            "type": AUTHORED_GROUP_TYPE,
            "authority_identity": AUTHORED_GROUP_AUTHORITY,
            "source_revision_id": reconstructed.revision_id,
            "source_document_hash": reconstructed.document_hash,
            "membership_hash": membership_hash,
        },
    }
    if change.initial_transform is not None:
        group["transform"] = copy.deepcopy(change.initial_transform)
    if canonical_bytes(group) != canonical_bytes(change.group):
        _fail("Authored assembly supplied Group differs from independent derivation")
    # Only this independently derived record is ever applied. Full validation
    # checks transform ownership, existing motion and canonical relations too.
    base.setdefault("groups", []).append(copy.deepcopy(group))
    validate_document(base, DocumentDialect.AUTHORED_GROUP_ASSEMBLY)
    return group


def verified_group(change: Any) -> dict[str, Any]:
    """Reconstruct without a live Store, Artifact lookup or cached trust flag."""
    try:
        return _verified_group(change)
    except (RecursionError, OverflowError, AttributeError) as exc:
        raise AuthoredGroupAssemblyError("Malformed authored assembly data") from exc


def verify_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    """Acceptor verifier; sibling Artifacts confer no membership authority."""
    verified_group(change)

