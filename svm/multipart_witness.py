"""Closed-world hash-linked revision evidence for Spec76, anchored by the Acceptor."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .admission_history import validate_admissions
from .revisions import AdmittedRevision, Revision, RevisionStore


@dataclass(frozen=True)
class RevisionSnapshotWitness:
    revision: Revision
    document: dict[str, Any]


def collect_witnesses(store: RevisionStore, base: str) -> tuple[RevisionSnapshotWitness, ...]:
    """Producer convenience only; verification never receives or reconstructs a store."""
    pending, found = [base], {}
    while pending:
        rid = pending.pop()
        if rid not in found:
            revision = store.revisions[rid]
            found[rid] = RevisionSnapshotWitness(revision, store.get_document(rid))
            pending.extend(revision.parent_ids)
    return tuple(found[rid] for rid in sorted(found))


def authenticate_witnesses(
    base: str, witnesses: tuple[RevisionSnapshotWitness, ...]
) -> dict[str, RevisionSnapshotWitness]:
    """Authenticate the complete ancestral DAG against the externally anchored base ID."""
    found = {}
    for item in witnesses:
        if type(item) is not RevisionSnapshotWitness or type(item.revision) not in {
            Revision,
            AdmittedRevision,
        }:
            raise ValueError("FORGED_BASE_OR_DEPENDENCY: invalid revision witness type")
        revision = item.revision
        expected = RevisionStore._make_revision(
            item.document,
            revision.parent_ids,
            revision.transaction_id,
            revision.message,
            getattr(revision, "admissions", ()),
        )
        if expected != revision or revision.revision_id in found:
            raise ValueError("FORGED_BASE_OR_DEPENDENCY: revision hash mismatch/duplicate")
        found[revision.revision_id] = copy.deepcopy(item)
    if tuple(found) != tuple(sorted(found)):
        raise ValueError("FORGED_BASE_OR_DEPENDENCY: noncanonical witness order")
    pending, reachable = [base], set()
    while pending:
        rid = pending.pop()
        if rid not in found:
            raise ValueError("FORGED_BASE_OR_DEPENDENCY: broken ancestry link")
        if rid not in reachable:
            reachable.add(rid)
            pending.extend(found[rid].revision.parent_ids)
    if reachable != set(found):
        raise ValueError("FORGED_BASE_OR_DEPENDENCY: unanchored witness")
    for item in found.values():
        parents = item.revision.parent_ids
        validate_admissions(
            item.revision, item.document, found[parents[0]].document if parents else None
        )
    return found


def ancestors(base: str, witnesses: dict[str, RevisionSnapshotWitness]) -> set[str]:
    pending, result = [base], set()
    while pending:
        rid = pending.pop()
        if rid not in result:
            result.add(rid)
            pending.extend(witnesses[rid].revision.parent_ids)
    return result
