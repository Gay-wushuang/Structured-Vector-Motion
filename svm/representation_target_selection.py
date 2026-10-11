"""Spec81 B0-2: independent selection verification and pure evidence projection.

This module receives only transported snapshots and authenticated witnesses. It
creates no Proposal, accepted Artifact, RevisionStore or admission authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .adapters.multipart_subject_evidence import _references
from .adapters.temporal_motion_target_binding import _binding
from .artifacts import ArtifactBlob, ArtifactDescriptor, ArtifactKind, ArtifactSnapshot
from .evaluator import canonical_bytes
from .multipart_witness import RevisionSnapshotWitness, authenticate_witnesses
from .representation_target_consumer import (
    POLICY_IDENTITY,
    REASON_NAMESPACE,
    CertifiedTargetResult,
    Reason,
    Stage,
    Status,
    derive_certified_targets,
)
from .revisions import AdmissionEvent, AdmittedRevision, BindTemporalMotionTargetChange, Revision

SCHEMA = "svm-representation-target-selection-evidence-0.1"
MEDIA = "application/vnd.svm.representation-target-selection-evidence+json;version=0.1"
CHANGE_IDENTITY = "svm.revisions.ApplyRepresentationTargetSelectionChange@0.1"


class RepresentationTargetSelectionError(ValueError):
    pass


def _fail(message: str) -> None:
    raise RepresentationTargetSelectionError(message)


def _same(left: Any, right: Any) -> bool:
    return canonical_bytes(left) == canonical_bytes(right)


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        _fail(f"Selection evidence requires exact {label} fields")
    return value


def _string(value: Any) -> bool:
    return type(value) is str and bool(value)


def _json_data(value: Any) -> bool:
    """Portable records must not carry behavior through Python subclasses."""
    if type(value) is dict:
        return all(type(key) is str and _json_data(item) for key, item in value.items())
    if type(value) is list:
        return all(_json_data(item) for item in value)
    return value is None or type(value) in {str, int, float, bool}


def _record_fields(value: Any, fields: set[str]) -> bool:
    # Exact dataclass types alone do not exclude instance-level behavior hooks.
    attributes = vars(value)
    return (
        type(attributes) is dict
        and all(type(key) is str for key in attributes)
        and set(attributes) == fields
    )


def _revision_data(revision: Any) -> bool:
    """Hashing and traversal must consume the same native revision metadata."""
    if (
        type(revision) not in {Revision, AdmittedRevision}
        or not _record_fields(
            revision,
            {"revision_id", "document_hash", "parent_ids", "transaction_id", "message"}
            | ({"admissions"} if type(revision) is AdmittedRevision else set()),
        )
        or not _string(revision.revision_id)
        or not _string(revision.document_hash)
        or type(revision.message) is not str
        or (revision.transaction_id is not None and type(revision.transaction_id) is not str)
        or type(revision.parent_ids) is not tuple
        or any(not _string(parent) for parent in revision.parent_ids)
    ):
        return False
    if type(revision) is Revision:
        return True
    return type(revision.admissions) is tuple and all(
        type(event) is AdmissionEvent
        and _record_fields(
            event,
            {
                "contract",
                "change_identity",
                "authority_identity",
                "base_revision_id",
                "artifact_reference",
                "transition_hash",
            },
        )
        and all(
            _string(value)
            for value in (
                event.contract,
                event.change_identity,
                event.authority_identity,
                event.base_revision_id,
                event.transition_hash,
            )
        )
        and type(event.artifact_reference) is dict
        and _json_data(event.artifact_reference)
        for event in revision.admissions
    )


def _strings(value: Any, label: str) -> list[str]:
    if (
        type(value) is not list
        or any(not _string(item) for item in value)
        or value != sorted(set(value))
    ):
        _fail(f"Selection evidence requires canonical {label}")
    return value


def _reference(value: Any) -> None:
    ref = _object(
        value, {"id", "uri", "content_hash", "media_type", "import_metadata"}, "Reference"
    )
    if not _json_data(ref) or any(
        not _string(ref[key]) for key in ("id", "uri", "content_hash", "media_type")
    ):
        _fail("Selection evidence Reference fields must be strings")
    metadata = _object(ref["import_metadata"], {"artifact_kind", "provenance"}, "import metadata")
    if (
        type(metadata["artifact_kind"]) is not str
        or metadata["artifact_kind"] not in {kind.value for kind in ArtifactKind}
        or type(metadata["provenance"]) is not dict
    ):
        _fail("Selection evidence requires an exact Artifact descriptor")
    # Source provenance and locators are verbatim data, including nested nulls.


def _validate_payload(payload: Any) -> None:
    payload = _object(
        payload,
        {
            "schema_version",
            "policy_identity",
            "reason_namespace",
            "base",
            "result",
            "evaluations",
            "identity_ids",
            "group_ids",
            "existing_bindings",
            "selected_pairs",
            "claim_audits",
            "counts",
        },
        "payload",
    )
    if (
        payload["schema_version"] != SCHEMA
        or payload["policy_identity"] != POLICY_IDENTITY
        or payload["reason_namespace"] != REASON_NAMESPACE
    ):
        _fail("Selection evidence schema or policy mismatch")
    base = _object(payload["base"], {"revision_id", "document_hash"}, "base")
    if any(not _string(value) for value in base.values()):
        _fail("Selection evidence base commitments must be strings")
    result = _object(
        payload["result"], {"stage", "status", "rejection_reason", "abstention_reason"}, "result"
    )
    if result != {
        "stage": "S7",
        "status": "SELECTED",
        "rejection_reason": None,
        "abstention_reason": None,
    }:
        _fail("Selection evidence requires a SELECTED S7 result")
    identity_ids = _strings(payload["identity_ids"], "identity IDs")
    _strings(payload["group_ids"], "Group IDs")
    evaluations = payload["evaluations"]
    if type(evaluations) is not list:
        _fail("Selection evidence evaluations must be an array")
    statuses = {item.value for item in Status}
    reasons = {item.value for item in Reason}
    stages = {item.value for item in Stage}
    for value in evaluations:
        item = _object(
            value,
            {
                "temporal_identity_id",
                "status",
                "reason",
                "stage",
                "group_id",
                "association_reference",
                "existing_binding_ids",
            },
            "evaluation",
        )
        if (
            not _string(item["temporal_identity_id"])
            or not _string(item["status"])
            or item["status"] not in statuses
            or not _string(item["stage"])
            or item["stage"] not in stages
            or (item["reason"] is None) != (item["status"] == "SELECTED")
            or (
                item["reason"] is not None
                and (not _string(item["reason"]) or item["reason"] not in reasons)
            )
            or (item["group_id"] is not None and not _string(item["group_id"]))
        ):
            _fail("Selection evidence evaluation types or enum values are invalid")
        if item["association_reference"] is not None:
            _reference(item["association_reference"])
        _strings(item["existing_binding_ids"], "existing binding IDs")
    if [item["temporal_identity_id"] for item in evaluations] != identity_ids:
        _fail("Selection evidence evaluations must cover every identity exactly once")
    bindings = payload["existing_bindings"]
    if type(bindings) is not list or any(
        type(item) is not dict or not _json_data(item) or not _string(item.get("id"))
        for item in bindings
    ):
        _fail("Selection evidence existing bindings must be complete records")
    _strings([item["id"] for item in bindings], "existing binding record order")
    pairs = payload["selected_pairs"]
    if type(pairs) is not list or len(pairs) != 1:
        _fail("Selection evidence requires exactly one selected pair")
    pair = _object(pairs[0], {"temporal_identity_id", "group_id"}, "selected pair")
    if any(not _string(value) for value in pair.values()):
        _fail("Selection evidence selected endpoints must be strings")
    audits = payload["claim_audits"]
    if type(audits) is not list:
        _fail("Selection evidence claim audits must be an array")
    claim_fields = (
        "acceptance_revision_id",
        "subject_id",
        "temporal_identity_id",
        "group_id",
        "claim_key",
    )
    for value in audits:
        item = _object(
            value,
            {"reference", "admitted", "status", "reason", "stage", *claim_fields},
            "claim audit",
        )
        _reference(item["reference"])
        if type(item["admitted"]) is not bool:
            _fail("Selection evidence audit admission must be a boolean")
        if item["admitted"]:
            if (
                item["status"] != "SELECTED"
                or item["reason"] is not None
                or item["stage"] != "S7"
                or any(not _string(item[field]) for field in claim_fields)
            ):
                _fail("Selection evidence admitted audit must be the selected replayed claim")
        elif (
            item["status"] != "ABSTAIN"
            or item["reason"] != "NO_ADMITTED_ASSOCIATION"
            or item["stage"] != "S2"
            or any(item[field] is not None for field in claim_fields)
        ):
            _fail("Selection evidence data audit must carry no claim authority")
    _strings([item["reference"]["id"] for item in audits], "claim audit order")
    if sum(item["admitted"] for item in audits) != 1:
        _fail("Selection evidence requires exactly one admitted claim")
    counts = _object(
        payload["counts"], {"total", "selected", "abstain", "reject", "selected_pairs"}, "counts"
    )
    expected_counts = {
        "total": len(evaluations),
        "selected": sum(item["status"] == "SELECTED" for item in evaluations),
        "abstain": sum(item["status"] == "ABSTAIN" for item in evaluations),
        "reject": sum(item["status"] == "REJECT" for item in evaluations),
        "selected_pairs": len(pairs),
    }
    if (
        any(type(value) is not int for value in counts.values())
        or counts != expected_counts
        or counts["total"] < 1
        or counts["selected"] != 1
    ):
        _fail("Selection evidence counts must be exact JSON integers")


def evidence_payload(result: CertifiedTargetResult, document_hash: str) -> dict[str, Any]:
    """Explicit, detached §7.7 projection; never creates or imports an Artifact."""
    if (
        type(result) is not CertifiedTargetResult
        or result.status != Status.SELECTED
        or result.stage != Stage.S7
        or result.rejection_reason is not None
        or result.abstention_reason is not None
        or result.policy_identity != POLICY_IDENTITY
        or result.reason_namespace != REASON_NAMESPACE
    ):
        _fail("Selection evidence requires a complete SELECTED derivation")
    payload = {
        "schema_version": SCHEMA,
        "policy_identity": POLICY_IDENTITY,
        "reason_namespace": REASON_NAMESPACE,
        "base": {"revision_id": result.base_revision_id, "document_hash": document_hash},
        "result": {
            "stage": str(result.stage),
            "status": str(result.status),
            "rejection_reason": None,
            "abstention_reason": None,
        },
        "evaluations": [
            {
                "temporal_identity_id": item.temporal_identity_id,
                "status": str(item.status),
                "reason": None if item.reason is None else str(item.reason),
                "stage": str(item.stage),
                "group_id": item.group_id,
                "association_reference": copy.deepcopy(item.association_reference),
                "existing_binding_ids": list(item.existing_binding_ids),
            }
            for item in result.evaluations
        ],
        "identity_ids": list(result.identity_ids),
        "group_ids": list(result.group_ids),
        "existing_bindings": copy.deepcopy(list(result.existing_bindings)),
        "selected_pairs": [
            {"temporal_identity_id": tid, "group_id": gid} for tid, gid in result.selected_pairs
        ],
        "claim_audits": [
            {
                "reference": copy.deepcopy(item.reference),
                "admitted": item.admitted,
                "status": None if item.status is None else str(item.status),
                "reason": None if item.reason is None else str(item.reason),
                "stage": str(item.stage),
                "acceptance_revision_id": item.acceptance_revision_id,
                "subject_id": item.subject_id,
                "temporal_identity_id": item.temporal_identity_id,
                "group_id": item.group_id,
                "claim_key": item.claim_key,
            }
            for item in result.claim_audits
        ],
        "counts": {
            "total": len(result.evaluations),
            "selected": sum(item.status == Status.SELECTED for item in result.evaluations),
            "abstain": sum(item.status == Status.ABSTAIN for item in result.evaluations),
            "reject": sum(item.status == Status.REJECT for item in result.evaluations),
            "selected_pairs": len(result.selected_pairs),
        },
    }
    _validate_payload(payload)
    return payload


def _snapshot(snapshot: ArtifactSnapshot, reference: dict[str, Any] | None = None) -> None:
    if (
        type(snapshot) is not ArtifactSnapshot
        or not _record_fields(snapshot, {"blob", "descriptor"})
        or type(snapshot.blob) is not ArtifactBlob
        or not _record_fields(snapshot.blob, {"artifact_id", "content_hash", "content"})
        or type(snapshot.descriptor) is not ArtifactDescriptor
        or not _record_fields(
            snapshot.descriptor, {"artifact_id", "kind", "media_type", "provenance", "locator"}
        )
        or type(snapshot.content) is not bytes
        or type(snapshot.kind) is not ArtifactKind
        or not _string(snapshot.artifact_id)
        or not _string(snapshot.content_hash)
        or not _string(snapshot.descriptor.artifact_id)
        or not _string(snapshot.media_type)
        or type(snapshot.provenance) is not dict
        or not _json_data(snapshot.provenance)
        or (snapshot.descriptor.locator is not None and not _string(snapshot.descriptor.locator))
    ):
        _fail("Selection requires exact transported Artifact snapshots")
    digest = hashlib.sha256(snapshot.content).hexdigest()
    if (
        snapshot.artifact_id != f"artifact:{digest}"
        or snapshot.descriptor.artifact_id != snapshot.artifact_id
        or snapshot.content_hash != f"sha256:{digest}"
        or (reference is not None and not _same(snapshot.document_reference(), reference))
    ):
        _fail("Selection transported bytes or exact descriptor mismatch")


class _ResolvedArtifacts:
    """Read-only capability restricted to the verifier's received snapshot map."""

    def __init__(self, resolved: dict[str, ArtifactSnapshot]) -> None:
        self._resolved = resolved

    def resolve(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        snapshots = tuple(self._resolved[aid] for aid in artifact_ids)
        for aid, snapshot in zip(artifact_ids, snapshots, strict=True):
            _snapshot(snapshot)
            if snapshot.artifact_id != aid:
                _fail("Selection resolved map key differs from Artifact identity")
        return snapshots

    def resolve_as(
        self, artifact_ids: tuple[str, ...], *, kind: ArtifactKind, media_types: frozenset[str]
    ) -> tuple[ArtifactSnapshot, ...]:
        snapshots = self.resolve(artifact_ids)
        if any(item.kind != kind or item.media_type not in media_types for item in snapshots):
            _fail("Selection transported Artifact kind or media mismatch")
        return snapshots

    def resolve_reference(self, reference: dict[str, Any]) -> ArtifactSnapshot:
        snapshot = self._resolved[reference["id"]]
        _snapshot(snapshot, reference)
        return snapshot


def _bind_record(change: BindTemporalMotionTargetChange) -> dict[str, Any]:
    return {
        "binding": change.binding,
        "temporal_identity": change.temporal_identity,
        "group": change.group,
        "source_revision_id": change.source_revision_id,
    }


def verify_change(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    """Independently replay selection, evidence bytes and exact frozen delegation."""
    from .revisions import ApplyRepresentationTargetSelectionChange

    if type(change) is not ApplyRepresentationTargetSelectionChange:
        _fail("Unregistered representation target selection Change")
    # S0 remains first, even when a supplied snapshot or descriptor is malformed.
    try:
        if (
            not _string(change.source_revision_id)
            or type(change.witnesses) is not tuple
            or any(
                type(witness) is not RevisionSnapshotWitness
                or not _record_fields(witness, {"revision", "document"})
                or not _revision_data(witness.revision)
                or type(witness.document) is not dict
                or not _json_data(witness.document)
                for witness in change.witnesses
            )
        ):
            raise ValueError
        authenticated = authenticate_witnesses(change.source_revision_id, change.witnesses)
    except Exception as exc:
        raise RepresentationTargetSelectionError(Reason.HISTORY_BROKEN.value) from exc
    document = authenticated[change.source_revision_id].document
    try:
        complete = _references(document)
        if (
            type(change.base_document_snapshot) is not dict
            or not _json_data(change.base_document_snapshot)
            or not _same(document, change.base_document_snapshot)
            or type(change.source_references) is not tuple
            or any(type(ref) is not dict or not _json_data(ref) for ref in change.source_references)
            or not _same(complete, change.source_references)
        ):
            raise ValueError
    except Exception as exc:
        raise RepresentationTargetSelectionError(Reason.UNREPLAYABLE_ASSOCIATION.value) from exc
    if type(change.policy_identity) is not str or change.policy_identity != POLICY_IDENTITY:
        _fail("Selection Change policy mismatch")
    _reference(change.selection_evidence_reference)
    evidence_ref = change.selection_evidence_reference
    if evidence_ref["id"] in {ref["id"] for ref in complete}:
        _fail("Selection evidence must not collide with a base reference")
    declared = tuple(sorted((*complete, evidence_ref), key=lambda ref: ref["id"]))
    if not _same(change.references, declared):
        _fail("Selection requires exact complete transport without duplicate references")
    if type(resolved) is not dict or any(type(aid) is not str for aid in resolved):
        _fail("Selection resolved map requires native Artifact ID strings")
    if any(ref["id"] not in resolved for ref in declared):
        _fail("Selection declared Artifact is absent from the resolved map")
    if set(resolved) != {ref["id"] for ref in declared}:
        _fail("Selection resolved map must contain exactly the declared Artifact IDs")
    resolver = _ResolvedArtifacts(resolved)
    result = derive_certified_targets(
        change.source_revision_id,
        change.base_document_snapshot,
        change.witnesses,
        resolver,
        source_references=change.source_references,
    )
    if result.rejection_reason is not None:
        _fail(result.rejection_reason.value)
    if not result.selected_pairs:
        _fail((result.abstention_reason or Reason.ZERO_SELECTED).value)
    regenerated = canonical_bytes(
        evidence_payload(result, authenticated[change.source_revision_id].revision.document_hash)
    )
    evidence = resolver.resolve_reference(evidence_ref)
    if (
        evidence.kind != ArtifactKind.DERIVED
        or evidence.media_type != MEDIA
        or evidence.provenance != {"policy_identity": POLICY_IDENTITY}
        or evidence.descriptor.locator is not None
        or evidence_ref["uri"] != evidence.artifact_id
    ):
        _fail("Selection evidence kind, media, provenance or locator mismatch")
    try:
        payload = json.loads(evidence.content)
        _validate_payload(payload)
        if canonical_bytes(payload) != evidence.content or evidence.content != regenerated:
            _fail("Selection evidence bytes do not independently reproduce")
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise RepresentationTargetSelectionError(
            "Selection evidence is not canonical JSON"
        ) from exc
    if (
        type(change.selected_pairs) is not tuple
        or len(change.selected_pairs) != 1
        or any(
            type(pair) is not tuple or len(pair) != 2 or any(not _string(item) for item in pair)
            for pair in change.selected_pairs
        )
        or not _same(change.selected_pairs, result.selected_pairs)
    ):
        _fail("Selection complete selected pairs do not independently reproduce")
    if type(change.delegated_binds) is not tuple or len(change.delegated_binds) != 1:
        _fail("Selection requires exactly one frozen delegated binding")
    for delegated, (tid, gid) in zip(change.delegated_binds, result.selected_pairs, strict=True):
        if type(delegated) is not BindTemporalMotionTargetChange:
            _fail("Selection requires the exact frozen binding Change")
        if not _record_fields(
            delegated, {"binding", "temporal_identity", "group", "source_revision_id"}
        ):
            _fail("Selection frozen delegated Change fields must be exact")
        if not _string(delegated.source_revision_id) or any(
            type(record) is not dict or not _json_data(record)
            for record in (delegated.binding, delegated.temporal_identity, delegated.group)
        ):
            _fail("Selection frozen delegated records must be portable JSON data")
        identity = next(item for item in document["temporal_identities"] if item["id"] == tid)
        group = next(item for item in document["groups"] if item["id"] == gid)
        expected = BindTemporalMotionTargetChange(
            _binding(change.source_revision_id, identity, group),
            identity,
            group,
            change.source_revision_id,
        )
        if not _same(_bind_record(delegated), _bind_record(expected)):
            _fail("Selection frozen delegated binding does not independently reproduce")
