"""Two bounded admission families; trust comes from Core acceptance, not bytes."""

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
    CertifyArtworkRepresentationChange,
    Revision,
    RevisionStore,
    Transaction,
)

MEDIA = "application/vnd.svm.multipart-subject-evidence+json;version=0.1"
CONTRACT = "svm-spec76-admission@0.1"
CHANGE = "svm.revisions.AttachMultipartSubjectEvidenceChange@0.1"
AUTHORITY = "svm-spec76-independent-verifier@0.1"
CERT_MEDIA = "application/vnd.svm.representation-certification+json;version=0.1"
CERT_CONTRACT = "svm-present-representation-certification-admission@0.1"
CERT_CHANGE = "svm.revisions.CertifyArtworkRepresentationChange@0.1"
CERT_AUTHORITY = "svm-present-representation-independent-verifier@0.1"
REVISION_CONTRACT = "svm-revision-admission@0.1"


class AdmissionError(ValueError):
    pass


def transition_hash(
    document: dict[str, Any], parents: tuple[str, ...], transaction_id: str | None, message: str
) -> str:
    # The legacy revision hash already commits exactly this acyclic transition tuple.
    return RevisionStore._make_revision(document, parents, transaction_id, message).revision_id


def _reserved(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in document["references"] if r["media_type"] in {MEDIA, CERT_MEDIA}}


def _dedicated_reference(change: Any) -> tuple[str, dict[str, Any]] | None:
    if type(change) is AttachMultipartSubjectEvidenceChange:
        media, ref = MEDIA, change.evidence_reference
    elif type(change) is CertifyArtworkRepresentationChange:
        media, ref = CERT_MEDIA, change.association_reference
    else:
        return None
    if type(ref) is not dict or ref.get("media_type") != media:
        _reject(media, "dedicated reference has wrong media type")
    return media, ref


def _identity(media: str) -> tuple[str, str, str] | None:
    if media == MEDIA:
        return CONTRACT, CHANGE, AUTHORITY
    if media == CERT_MEDIA:
        return CERT_CONTRACT, CERT_CHANGE, CERT_AUTHORITY
    return None


def _reject(media: str, detail: str) -> None:
    prefix = "SPEC76_ADMISSION_REQUIRED" if media == MEDIA else "CERTIFICATION_ADMISSION_REQUIRED"
    raise AdmissionError(f"{prefix}: {detail}")


def apply_verified_transaction(
    document: dict[str, Any], transaction: Transaction
) -> dict[str, Any]:
    """After exact registry/verifier/policy checks, inspect each actual mutation."""
    if len(transaction.changes) != 1 and any(
        type(change) is CertifyArtworkRepresentationChange for change in transaction.changes
    ):
        _reject(CERT_MEDIA, "certification requires one dedicated Change")
    candidate = copy.deepcopy(document)
    original = _reserved(document)
    dedicated_ids: set[str] = set()
    for change in transaction.changes:
        dedicated = _dedicated_reference(change)
        allowed: dict[str, dict[str, Any]] = {}
        if dedicated is not None:
            media, ref = dedicated
            aid = ref["id"]
            if aid in dedicated_ids:
                _reject(media, "duplicate dedicated Change")
            dedicated_ids.add(aid)
            allowed[aid] = ref
        # Compare every declared input with the original base, including the
        # other dedicated family. An earlier addition cannot launder a no-op.
        for ref in getattr(change, "references", ()):
            if (
                ref.get("media_type") in {MEDIA, CERT_MEDIA}
                and original.get(ref["id"]) != ref
                and allowed.get(ref["id"]) != ref
            ):
                _reject(ref["media_type"], "generic attachment")
        before = copy.deepcopy(_reserved(candidate))
        change.apply(candidate)
        after = _reserved(candidate)
        additions = {aid: ref for aid, ref in after.items() if before.get(aid) != ref}
        for aid, ref in before.items():
            if after.get(aid) != ref:
                _reject(ref["media_type"], "reserved reference replacement")
        for aid, ref in additions.items():
            if allowed.get(aid) != ref:
                _reject(ref["media_type"], "unauthorized actual addition")
    validate_document(candidate)
    return candidate


def admission_events(
    base: str, before: dict[str, Any], after: dict[str, Any], transaction: Transaction
) -> tuple[AdmissionEvent, ...]:
    """Core-only builder, called after all verification and transition checks succeed."""
    old, new = _reserved(before), _reserved(after)
    commitment = transition_hash(after, (base,), transaction.transaction_id, transaction.message)
    events = []
    for change in transaction.changes:
        dedicated = _dedicated_reference(change)
        if dedicated is None:
            continue
        media, ref = dedicated
        if new.get(ref["id"]) != ref:
            _reject(media, "dedicated output is not the final accepted descriptor")
        if ref["id"] in old:
            continue
        identity = _identity(media)
        if identity is None:
            raise AdmissionError("Unknown admission family")
        events.append(AdmissionEvent(*identity, base, copy.deepcopy(ref), commitment))
    if {event.artifact_reference["id"] for event in events} != set(new) - set(old):
        raise AdmissionError("Admission events do not cover reserved additions")
    return tuple(events)


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
    if any(new.get(aid) != ref for aid, ref in old.items()):
        raise AdmissionError("Admission transition changes an existing reserved reference")
    commitment = transition_hash(
        document, revision.parent_ids, revision.transaction_id, revision.message
    )
    seen = set()
    certification_id: str | None = None
    for event in revision.admissions:
        if type(event) is not AdmissionEvent or type(event.artifact_reference) is not dict:
            raise AdmissionError("Invalid admission event/transition")
        ref = event.artifact_reference
        media = ref.get("media_type")
        identity = _identity(media) if isinstance(media, str) else None
        if (
            identity is None
            or (event.contract, event.change_identity, event.authority_identity) != identity
            or event.base_revision_id != revision.parent_ids[0]
            or event.transition_hash != commitment
        ):
            raise AdmissionError("Invalid admission event/transition")
        aid = ref.get("id")
        if not isinstance(aid, str) or aid in seen or aid in old or new.get(aid) != ref:
            raise AdmissionError("Admission Artifact does not match new reference")
        seen.add(aid)
        if media == CERT_MEDIA:
            certification_id = aid
    if seen != set(new) - set(old):
        raise AdmissionError("Admission events do not cover reserved additions")
    if certification_id is not None:
        if len(revision.admissions) != 1:
            raise AdmissionError("Certification transition requires exactly one admission event")
        expected = copy.deepcopy(parent_document)
        expected["references"].append(copy.deepcopy(new[certification_id]))
        if canonical_bytes(expected) != canonical_bytes(document):
            raise AdmissionError("Certification transition must only append its exact reference")


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
