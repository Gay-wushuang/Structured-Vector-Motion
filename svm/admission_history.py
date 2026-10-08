"""Spec76 admission facts. Trust comes from Core acceptance, not serialized claims."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict
from typing import Any

from .document import validate_document
from .evaluator import canonical_bytes
from .revisions import (
    AdmissionEvent,
    AdmittedRevision,
    AttachMultipartSubjectEvidenceChange,
    Revision,
    RevisionStore,
    Transaction,
)

MEDIA = "application/vnd.svm.multipart-subject-evidence+json;version=0.1"
CONTRACT = "svm-spec76-admission@0.1"
CHANGE = "svm.revisions.AttachMultipartSubjectEvidenceChange@0.1"
AUTHORITY = "svm-spec76-independent-verifier@0.1"
REVISION_CONTRACT = "svm-revision-admission@0.1"


class AdmissionError(ValueError):
    pass


def transition_hash(
    document: dict[str, Any], parents: tuple[str, ...], transaction_id: str | None, message: str
) -> str:
    # The legacy revision hash already commits exactly this acyclic transition tuple.
    return RevisionStore._make_revision(document, parents, transaction_id, message).revision_id


def _reserved(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in document["references"] if r["media_type"] == MEDIA}


def apply_verified_transaction(
    document: dict[str, Any], transaction: Transaction
) -> dict[str, Any]:
    """After exact registry/verifier/policy checks, inspect each actual mutation."""
    candidate = copy.deepcopy(document)
    original = _reserved(document)
    dedicated_ids: set[str] = set()
    for change in transaction.changes:
        dedicated = type(change) is AttachMultipartSubjectEvidenceChange
        if dedicated:
            aid = change.evidence_reference["id"]
            if aid in dedicated_ids:
                raise AdmissionError("SPEC76_ADMISSION_REQUIRED: duplicate dedicated Change")
            dedicated_ids.add(aid)
        else:
            # Also disallow a generic no-op laundering a new reference after a
            # dedicated Change. Existing exact references remain ordinary inputs.
            for ref in getattr(change, "references", ()):
                if ref.get("media_type") == MEDIA and original.get(ref["id"]) != ref:
                    raise AdmissionError("SPEC76_ADMISSION_REQUIRED: generic attachment")
        before = _reserved(candidate)
        change.apply(candidate)
        after = _reserved(candidate)
        additions = {aid: ref for aid, ref in after.items() if before.get(aid) != ref}
        if any(after.get(aid) != ref for aid, ref in before.items()):
            raise AdmissionError("SPEC76_ADMISSION_REQUIRED: reserved reference replacement")
        allowed: dict[str, dict[str, Any]] = (
            {change.evidence_reference["id"]: change.evidence_reference} if dedicated else {}
        )
        if any(allowed.get(aid) != ref for aid, ref in additions.items()):
            raise AdmissionError("SPEC76_ADMISSION_REQUIRED: unauthorized actual addition")
    validate_document(candidate)
    return candidate


def admission_events(
    base: str, before: dict[str, Any], after: dict[str, Any], transaction: Transaction
) -> tuple[AdmissionEvent, ...]:
    """Core-only builder, called after all verification and transition checks succeed."""
    old = _reserved(before)
    commitment = transition_hash(after, (base,), transaction.transaction_id, transaction.message)
    return tuple(
        AdmissionEvent(
            CONTRACT, CHANGE, AUTHORITY, base, copy.deepcopy(change.evidence_reference), commitment
        )
        for change in transaction.changes
        if type(change) is AttachMultipartSubjectEvidenceChange
        and change.evidence_reference["id"] not in old
    )


def validate_admissions(
    revision: Revision, document: dict[str, Any], parent_document: dict[str, Any] | None
) -> None:
    """Consistency only. Caller must anchor the Revision in trusted store history."""
    if type(revision) is Revision:
        return
    if type(revision) is not AdmittedRevision or not revision.admissions:
        raise AdmissionError("Invalid admission revision contract")
    if len(revision.parent_ids) != 1 or parent_document is None:
        raise AdmissionError("Admission requires an exact parent transition")
    old, new = _reserved(parent_document), _reserved(document)
    seen = set()
    for event in revision.admissions:
        if type(event) is not AdmissionEvent or (
            event.contract != CONTRACT
            or event.change_identity != CHANGE
            or event.authority_identity != AUTHORITY
            or event.base_revision_id != revision.parent_ids[0]
            or event.transition_hash
            != transition_hash(
                document, revision.parent_ids, revision.transaction_id, revision.message
            )
        ):
            raise AdmissionError("Invalid admission event/transition")
        ref = event.artifact_reference
        if ref["id"] in seen or ref["id"] in old or new.get(ref["id"]) != ref:
            raise AdmissionError("Admission Artifact does not match new reference")
        seen.add(ref["id"])
    if seen != set(new) - set(old):
        raise AdmissionError("Admission events do not cover reserved additions")


def dump_trusted_history(store: RevisionStore) -> dict[str, Any]:
    """Host persistence, NOT an Adapter payload or portable Document authority."""
    records = []
    for rid, revision in sorted(store.revisions.items()):
        record = asdict(revision)
        if type(revision) is AdmittedRevision:
            record["revision_contract"] = REVISION_CONTRACT
        records.append({"revision": record, "document": store.get_document(rid)})
    return {"history_contract": "svm-trusted-history@0.1", "head": store.head, "records": records}


def history_digest(payload: dict[str, Any]) -> str:
    """Host records this commitment separately when persisting its trusted store."""
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def load_trusted_history(payload: dict[str, Any], *, trusted_history_hash: str) -> RevisionStore:
    """Restore from trusted host storage only. Hash checks are NOT issuer authentication.

    The host supplies a previously trusted, separately retained snapshot digest.
    Deriving that argument from the input being loaded does NOT establish trust.
    No public history interchange or signature issuer is provided by this contract.
    """
    if history_digest(payload) != trusted_history_hash:
        raise AdmissionError("Trusted history digest mismatch")
    if (
        set(payload) != {"history_contract", "head", "records"}
        or payload["history_contract"] != "svm-trusted-history@0.1"
    ):
        raise AdmissionError("Unknown trusted history format")
    store = RevisionStore()
    for item in payload["records"]:
        if set(item) != {"revision", "document"}:
            raise AdmissionError("Invalid history record")
        data = copy.deepcopy(item["revision"])
        version = data.pop("revision_contract", None)
        data["parent_ids"] = tuple(data["parent_ids"])
        if version is None:
            revision = Revision(**data)
        elif version == REVISION_CONTRACT:
            data["admissions"] = tuple(AdmissionEvent(**event) for event in data["admissions"])
            revision = AdmittedRevision(**data)
        else:
            raise AdmissionError("Unknown revision contract")
        document = copy.deepcopy(item["document"])
        validate_document(document)
        expected = RevisionStore._make_revision(
            document,
            revision.parent_ids,
            revision.transaction_id,
            revision.message,
            getattr(revision, "admissions", ()),
        )
        if expected != revision or revision.revision_id in store.revisions:
            raise AdmissionError("History revision hash mismatch/duplicate")
        store.revisions[revision.revision_id] = revision
        store._documents[revision.revision_id] = document
    if payload["head"] not in store.revisions:
        raise AdmissionError("Missing history head")
    for rid, revision in store.revisions.items():
        if any(parent not in store.revisions for parent in revision.parent_ids):
            raise AdmissionError("Missing history parent")
        validate_admissions(
            revision,
            store._documents[rid],
            store._documents[revision.parent_ids[0]] if revision.parent_ids else None,
        )
    store.head = payload["head"]
    return store
