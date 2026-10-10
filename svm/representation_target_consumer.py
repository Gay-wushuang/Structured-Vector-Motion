"""Spec81 B0-1: pure classification of independently replayed certified targets.

The base ID and complete Document must come from trusted host orchestration.
Hash-consistent caller history alone does not establish issuer trust. This module
creates no Proposal, Artifact, Change, binding or Revision in accepted state.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .adapters import representation_certification as spec80
from .adapters.multipart_subject_evidence import _references
from .adapters.subject_observation_bridge import _record
from .admission_history import CERT_AUTHORITY, CERT_CHANGE, CERT_CONTRACT, CERT_MEDIA
from .artifacts import ArtifactResolver, ArtifactSnapshot, ArtifactStore
from .evaluator import canonical_bytes
from .multipart_witness import RevisionSnapshotWitness, ancestors, authenticate_witnesses

POLICY_IDENTITY = "svm-representation-target-consumer@0.1"
REASON_NAMESPACE = "svm-representation-target-consumer-reasons@0.1"


class Status(StrEnum):
    SELECTED = "SELECTED"
    ABSTAIN = "ABSTAIN"
    REJECT = "REJECT"


class Reason(StrEnum):
    HISTORY_BROKEN = "HISTORY_BROKEN"
    UNREPLAYABLE_ASSOCIATION = "UNREPLAYABLE_ASSOCIATION"
    AMBIGUOUS_ASSOCIATION = "AMBIGUOUS_ASSOCIATION"
    COMPETING_ASSOCIATION = "COMPETING_ASSOCIATION"
    ALREADY_BOUND = "ALREADY_BOUND"
    TRACKED_REPRESENTATION = "TRACKED_REPRESENTATION"
    NO_ADMITTED_ASSOCIATION = "NO_ADMITTED_ASSOCIATION"
    NO_CERTIFICATION_FOR_IDENTITY = "NO_CERTIFICATION_FOR_IDENTITY"
    ZERO_SELECTED = "ZERO_SELECTED"


class Stage(StrEnum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    S7 = "S7"


@dataclass(frozen=True)
class IdentityEvaluation:
    temporal_identity_id: str
    status: Status
    reason: Reason | None
    stage: Stage
    group_id: str | None = None
    association_reference: dict[str, Any] | None = None
    existing_binding_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimAudit:
    reference: dict[str, Any]
    admitted: bool | None
    status: Status | None
    reason: Reason | None
    stage: Stage
    acceptance_revision_id: str | None = None
    subject_id: str | None = None
    temporal_identity_id: str | None = None
    group_id: str | None = None
    claim_key: str | None = None


@dataclass(frozen=True)
class CertifiedTargetResult:
    base_revision_id: str
    policy_identity: str
    reason_namespace: str
    stage: Stage
    rejection_reason: Reason | None
    abstention_reason: Reason | None
    evaluations: tuple[IdentityEvaluation, ...]
    selected_pairs: tuple[tuple[str, str], ...]
    claim_audits: tuple[ClaimAudit, ...]
    identity_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
    existing_bindings: tuple[dict[str, Any], ...]
    source_references: tuple[dict[str, Any], ...]

    @property
    def status(self) -> Status:
        if self.rejection_reason is not None:
            return Status.REJECT
        return Status.SELECTED if self.selected_pairs else Status.ABSTAIN

    @property
    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.evaluations),
            "selected": sum(item.status == Status.SELECTED for item in self.evaluations),
            "abstain": sum(item.status == Status.ABSTAIN for item in self.evaluations),
            "reject": sum(item.status == Status.REJECT for item in self.evaluations),
            "selected_pairs": len(self.selected_pairs),
        }


def _same(left: Any, right: Any) -> bool:
    return canonical_bytes(left) == canonical_bytes(right)


def _contains(document: dict[str, Any], reference: dict[str, Any]) -> bool:
    return any(_same(item, reference) for item in document.get("references", []))


def _raw_references(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    # Preserve distinct descriptors, even when their IDs conflict (S1 rejects).
    unique = {canonical_bytes(ref): ref for ref in document.get("references", [])}
    return tuple(sorted(unique.values(), key=lambda ref: (ref["id"], canonical_bytes(ref))))


def _audits(references: tuple[dict[str, Any], ...]) -> list[ClaimAudit]:
    return [
        ClaimAudit(copy.deepcopy(ref), None, None, None, Stage.S0)
        for ref in references
        if ref.get("media_type") == CERT_MEDIA
    ]


def _visible_records(document: dict[str, Any], field: str) -> tuple[dict[str, Any], ...]:
    entries = document.get(field, [])
    if type(entries) is not list:
        return ()
    return tuple(
        sorted(
            (item for item in entries if type(item) is dict and type(item.get("id")) is str),
            key=lambda item: item["id"],
        )
    )


def _untrusted_references(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Best-effort data visibility after authentication fails; no earlier validation."""
    try:
        return _raw_references(document)
    except Exception:
        entries = document.get("references", [])
        if type(entries) is not list:
            return ()
        return tuple(copy.deepcopy(ref) for ref in entries if type(ref) is dict)


def _import_verified(
    scratch: ArtifactStore, reference: dict[str, Any], snapshot: ArtifactSnapshot
) -> None:
    digest = hashlib.sha256(snapshot.content).hexdigest()
    if (
        snapshot.artifact_id != f"artifact:{digest}"
        or snapshot.descriptor.artifact_id != snapshot.artifact_id
        or snapshot.content_hash != f"sha256:{digest}"
        or not _same(snapshot.document_reference(), reference)
    ):
        raise ValueError("Artifact bytes and exact accepted descriptor must agree")
    imported = scratch.import_bytes(
        snapshot.content,
        media_type=snapshot.media_type,
        kind=snapshot.kind,
        provenance=snapshot.provenance,
        locator=snapshot.descriptor.locator,
    )
    if not _same(imported.document_reference(), reference):
        raise ValueError("Scratch transport must preserve the exact descriptor")


def _birth(
    authenticated: dict[str, RevisionSnapshotWitness],
    reference: dict[str, Any],
    event_revision: str,
    event_base: str,
) -> str:
    births = []
    for rid, witness in sorted(authenticated.items()):
        parents = witness.revision.parent_ids
        if (
            len(parents) == 1
            and _contains(witness.document, reference)
            and not _contains(authenticated[parents[0]].document, reference)
        ):
            births.append(rid)
    if len(births) != 1 or births[0] != event_revision:
        raise ValueError("Exactly one authenticated certification reference birth is required")
    birth = births[0]
    if authenticated[birth].revision.parent_ids != (event_base,):
        raise ValueError("Certification birth must be bound to its exact admission base")
    expected = copy.deepcopy(authenticated[event_base].document)
    expected["references"].append(copy.deepcopy(reference))
    if not _same(expected, authenticated[birth].document):
        raise ValueError("Certification birth must be the complete evidence-only transition")
    return birth


def derive_certified_targets(
    base: str,
    document: dict[str, Any],
    witnesses: tuple[RevisionSnapshotWitness, ...],
    artifacts: ArtifactResolver,
    *,
    source_references: tuple[dict[str, Any], ...] | None = None,
) -> CertifiedTargetResult:
    """Return detached read-only S0–S7 classifications; never authorize acceptance.

    ``base`` must be the real host-supplied accepted Revision commitment. An
    explicit reference collection must equal the independently enumerated entire
    base universe; ``None`` derives that collection without requiring a selector.
    Resolver failures receive the generic reason, without inspecting messages.
    """
    inventory = copy.deepcopy(document)
    refs: tuple[dict[str, Any], ...] = ()
    audits: list[ClaimAudit] = []

    def finish(
        stage: Stage,
        *,
        rejection: Reason | None = None,
        abstention: Reason | None = None,
        evaluations: tuple[IdentityEvaluation, ...] | None = None,
        selected: tuple[tuple[str, str], ...] = (),
    ) -> CertifiedTargetResult:
        identities = tuple(
            item["id"] for item in _visible_records(inventory, "temporal_identities")
        )
        groups = tuple(item["id"] for item in _visible_records(inventory, "groups"))
        if evaluations is None:
            evaluations = tuple(
                IdentityEvaluation(
                    tid,
                    Status.REJECT if rejection is not None else Status.ABSTAIN,
                    rejection if rejection is not None else abstention,
                    stage,
                )
                for tid in identities
            )
        reported_audits = (
            tuple(
                item
                if item.admitted is False
                else replace(item, status=Status.REJECT, reason=rejection, stage=stage)
                for item in audits
            )
            if rejection is not None
            else tuple(audits)
        )
        return copy.deepcopy(
            CertifiedTargetResult(
                base,
                POLICY_IDENTITY,
                REASON_NAMESPACE,
                stage,
                rejection,
                abstention,
                evaluations,
                () if rejection is not None else selected,
                reported_audits,
                identities,
                groups,
                _visible_records(inventory, "motion_target_bindings"),
                refs,
            )
        )

    # S0: all witness and event predicates precede any transport/content check.
    try:
        authenticated = authenticate_witnesses(base, witnesses)
    except Exception:
        refs = _untrusted_references(inventory)
        audits = _audits(refs)
        return finish(Stage.S0, rejection=Reason.HISTORY_BROKEN)
    inventory = authenticated[base].document
    # S1: use the authenticated universe, including on a supplied-snapshot defect.
    try:
        refs = _raw_references(inventory)
        audits = _audits(refs)
        complete = _references(inventory)
        supplied = complete if source_references is None else source_references
        if not _same(document, inventory) or not _same(supplied, complete):
            raise ValueError("Complete authenticated Document/reference universe required")
        refs = complete
    except Exception:
        refs = _untrusted_references(inventory)
        audits = _audits(refs)
        return finish(Stage.S1, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
    # S2: descriptor/event inspection only. Data bytes need not exist or decode.
    candidates = []
    for index, audit in enumerate(audits):
        events = [
            (rid, event)
            for rid, witness in sorted(authenticated.items())
            for event in getattr(witness.revision, "admissions", ())
            if _same(event.artifact_reference, audit.reference)
        ]
        if not events:
            audits[index] = replace(
                audit,
                admitted=False,
                status=Status.ABSTAIN,
                reason=Reason.NO_ADMITTED_ASSOCIATION,
                stage=Stage.S2,
            )
            continue
        audits[index] = replace(audit, admitted=True, stage=Stage.S2)
        if len(events) != 1:
            return finish(Stage.S2, rejection=Reason.AMBIGUOUS_ASSOCIATION)
        rid, event = events[0]
        if (event.contract, event.change_identity, event.authority_identity) != (
            CERT_CONTRACT,
            CERT_CHANGE,
            CERT_AUTHORITY,
        ):
            return finish(Stage.S2, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
        candidates.append((index, rid, event))
    if not candidates:
        return finish(Stage.S2, abstention=Reason.NO_ADMITTED_ASSOCIATION)
    # S3: every CURRENT descriptor travels; historical extras are never fetched.
    scratch = ArtifactStore()
    try:
        for ref in refs:
            _import_verified(scratch, ref, artifacts.resolve_reference(ref))
        for index, event_revision, event in candidates:
            ref = audits[index].reference
            birth = _birth(authenticated, ref, event_revision, event.base_revision_id)
            subset = tuple(authenticated[rid] for rid in sorted(ancestors(birth, authenticated)))
            replayed = spec80.admitted_associations(birth, subset, scratch)
            if len(replayed) != 1 or not _same(replayed[0], ref):
                raise ValueError("Historical replay must return exactly this applicable Reference")
            # Endpoints are extracted only from a replayed Reference's verified bytes.
            snapshot = scratch.resolve_reference(replayed[0])
            _import_verified(scratch, replayed[0], snapshot)
            record = _record(snapshot)
            association = record["association"]
            if (
                type(association) is not dict
                or set(association) != {"subject_id", "temporal_identity_id", "group_id"}
                or any(type(value) is not str for value in association.values())
            ):
                raise ValueError(
                    "Replayed certification must expose exact subject/T/Group endpoints"
                )
            audits[index] = replace(
                audits[index],
                stage=Stage.S3,
                acceptance_revision_id=birth,
                subject_id=association["subject_id"],
                temporal_identity_id=association["temporal_identity_id"],
                group_id=association["group_id"],
                claim_key=spec80.claim_key(record),
            )
    except Exception:
        return finish(Stage.S3, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
    authenticated_claims = [audits[index] for index, _, _ in candidates]
    for i, claim in enumerate(authenticated_claims):
        for other in authenticated_claims[i + 1 :]:
            if claim.claim_key == other.claim_key:
                return finish(Stage.S3, rejection=Reason.AMBIGUOUS_ASSOCIATION)
            if (
                claim.temporal_identity_id == other.temporal_identity_id
                or claim.group_id == other.group_id
            ):
                return finish(Stage.S3, rejection=Reason.COMPETING_ASSOCIATION)
    # S4 and S5 are eligibility checks AFTER all historical claims authenticate.
    outcomes: dict[str, IdentityEvaluation] = {}
    unbound = []
    for index, _, _ in candidates:
        claim = audits[index]
        tid, gid = claim.temporal_identity_id, claim.group_id
        if tid is None or gid is None:
            return finish(Stage.S3, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
        bindings = tuple(
            sorted(
                b["id"]
                for b in inventory.get("motion_target_bindings", [])
                if b["temporal_identity_id"] == tid or b["target"]["group_id"] == gid
            )
        )
        if bindings:
            audits[index] = replace(
                claim, status=Status.REJECT, reason=Reason.ALREADY_BOUND, stage=Stage.S4
            )
            outcomes[tid] = IdentityEvaluation(
                tid, Status.REJECT, Reason.ALREADY_BOUND, Stage.S4, gid, claim.reference, bindings
            )
        else:
            unbound.append(index)
    eligible = []
    for index in unbound:
        claim = audits[index]
        group = next((g for g in inventory.get("groups", []) if g["id"] == claim.group_id), None)
        members = set(group["members"]) if group is not None else set()
        record = _record(scratch.resolve_reference(claim.reference))
        operations = {o["id"] for o in record["representation"]["operations"]}
        operations.update(
            b["slot"].rsplit(".", 1)[0]
            for b in inventory["construction"]["output_bindings"]
            if b["entity"] in members and b["property"] == "geometry"
        )
        tracked = any(
            track.get("target", {}).get("group") == claim.group_id
            or track.get("target", {}).get("entity") in members
            or track.get("target", {}).get("operation") in operations
            for track in inventory.get("animation", {}).get("content", [])
        )
        if tracked:
            audits[index] = replace(
                claim, status=Status.REJECT, reason=Reason.TRACKED_REPRESENTATION, stage=Stage.S5
            )
            tid = claim.temporal_identity_id
            if tid is None:
                return finish(Stage.S3, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
            outcomes[tid] = IdentityEvaluation(
                tid,
                Status.REJECT,
                Reason.TRACKED_REPRESENTATION,
                Stage.S5,
                claim.group_id,
                claim.reference,
            )
        else:
            eligible.append(index)
    # S6: bound/tracked endpoints never enter frozen current applicability replay.
    if eligible:
        try:
            replayed = spec80.admitted_associations(base, witnesses, scratch)
            expected = tuple(audits[index].reference for index in eligible)
            if len(replayed) != 1 or not _same(replayed, expected):
                raise ValueError("Current bounded replay must reproduce the entire eligible set")
            for index in eligible:
                claim = audits[index]
                if (
                    sum(
                        t["id"] == claim.temporal_identity_id
                        for t in inventory.get("temporal_identities", [])
                    )
                    != 1
                    or sum(g["id"] == claim.group_id for g in inventory.get("groups", [])) != 1
                ):
                    raise ValueError("Current certified endpoints must exist uniquely")
        except Exception:
            return finish(Stage.S6, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
    # S7: one complete report; no materialization or partial target selection.
    selected = []
    for index in eligible:
        claim = audits[index]
        tid, gid = claim.temporal_identity_id, claim.group_id
        if tid is None or gid is None:
            return finish(Stage.S6, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
        selected.append((tid, gid))
        audits[index] = replace(claim, status=Status.SELECTED, stage=Stage.S7)
        outcomes[tid] = IdentityEvaluation(
            tid, Status.SELECTED, None, Stage.S7, gid, claim.reference
        )
    if len(selected) > 1:
        return finish(Stage.S6, rejection=Reason.UNREPLAYABLE_ASSOCIATION)
    evaluations = tuple(
        outcomes.get(
            tid,
            IdentityEvaluation(tid, Status.ABSTAIN, Reason.NO_CERTIFICATION_FOR_IDENTITY, Stage.S7),
        )
        for tid in sorted(t["id"] for t in inventory.get("temporal_identities", []))
    )
    return finish(
        Stage.S7,
        abstention=None if selected else Reason.ZERO_SELECTED,
        evaluations=evaluations,
        selected=tuple(sorted(selected)),
    )
