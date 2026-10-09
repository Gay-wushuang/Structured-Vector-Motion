"""Spec80 present-time association; origin replay proves structural conformity only.

Accepted companion bytes are data. Spec77 ownership and the separately admitted
current certification event, authenticated against the real base, grant authority.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict
from typing import Any, NoReturn

from ..admission_history import CERT_AUTHORITY, CERT_CHANGE, CERT_CONTRACT, CERT_MEDIA
from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..authored_raster_production import PART_KEYS
from ..evaluator import canonical_bytes
from ..multipart_witness import RevisionSnapshotWitness, ancestors, authenticate_witnesses
from ..proposals import AdapterRequest, GeneratorProvenance, Proposal
from ..revisions import CertifyArtworkRepresentationChange, Transaction
from .multipart_subject_evidence import _references
from .subject_observation_bridge import IDENTITY_MEDIA, _identity, _record
from .subject_observation_bridge import MEDIA as MEMBERSHIP_MEDIA
from .svg_group_construction import AUTHORITY
from .video_artwork_construction import PROFILE as CONSTRUCTION_PROFILE
from .video_artwork_construction import _derive as _construction
from .video_artwork_construction import _descriptor

PROFILE = "svm-source-backed-two-triangle-representation-certification@0.1"
SCHEMA = "svm-present-representation-certification-0.1"
MEDIA = CERT_MEDIA
PROOF_MODE = "PRESENT_TIME_CERTIFICATION@0.1"


class RepresentationCertificationError(ValueError):
    pass


def _fail(reason: str) -> NoReturn:
    raise RepresentationCertificationError(reason)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def claim_key(record: dict[str, Any]) -> str:
    """Complete logical proof equivalence, excluding present base/inventories only."""
    return _hash({k: v for k, v in record.items() if k not in {"base", "universe"}})


def _same(left: Any, right: Any) -> bool:
    return canonical_bytes(left) == canonical_bytes(right)


def _unique(document: dict[str, Any], field: str, identity: str) -> dict[str, Any] | None:
    matches = [item for item in document.get(field, []) if item["id"] == identity]
    if len(matches) > 1:
        _fail("Ambiguous accepted identity or Group definition")
    return matches[0] if matches else None


def _scratch(document: dict[str, Any], artifacts: ArtifactRepository) -> ArtifactStore:
    """Read accepted inputs; all derived replay outputs stay in a local repository."""
    scratch = ArtifactStore()
    for ref in _references(document):
        actual = artifacts.resolve_reference(ref)
        if not _same(actual.document_reference(), ref):
            _fail("Certification transported descriptor mismatch")
        scratch.import_bytes(
            actual.content,
            media_type=actual.media_type,
            kind=actual.kind,
            provenance=actual.provenance,
            locator=actual.descriptor.locator,
        )
    return scratch


class _Replay:
    """Per-call complete history replay with strictly ancestral claim recursion."""

    def __init__(
        self,
        base: str,
        witnesses: tuple[RevisionSnapshotWitness, ...],
        artifacts: ArtifactRepository,
    ) -> None:
        self.authenticated = authenticate_witnesses(base, witnesses)
        self.artifacts = artifacts
        self.facts_cache: dict[str, dict[str, Any]] = {}
        self.record_cache: dict[str, dict[str, Any]] = {}
        self.claims_cache: dict[
            str, tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]
        ] = {}
        self.active: set[str] = set()

    def witnesses(self, base: str) -> tuple[RevisionSnapshotWitness, ...]:
        return tuple(self.authenticated[rid] for rid in sorted(ancestors(base, self.authenticated)))

    def chain(self, base: str) -> list[str]:
        chain = []
        current = base
        while True:
            chain.append(current)
            parents = self.authenticated[current].revision.parent_ids
            if not parents:
                return list(reversed(chain))
            if len(parents) != 1:
                _fail("Certification profile requires single-parent origin and continuity history")
            current = parents[0]

    def facts(self, base: str) -> dict[str, Any]:
        if base in self.facts_cache:
            return self.facts_cache[base]
        document = self.authenticated[base].document
        chain = self.chain(base)
        current = _identity(base, self.witnesses(base), self.artifacts)
        current_record = _record(self.artifacts.resolve_reference(current.evidence_reference))
        definition = current_record["temporal_identity"]
        tid = definition["id"]
        if not _same(_unique(document, "temporal_identities", tid), definition):
            _fail("Exact independently reproduced whole-subject TemporalIdentity must be accepted")
        # The accepted Stage3 companion must itself replay at its original base.
        # A fresh unaccepted current-base companion is not that historical data.
        companions = []
        for ref in _references(document):
            if ref["media_type"] != IDENTITY_MEDIA:
                continue
            snapshot = self.artifacts.resolve_reference(ref)
            record = _record(snapshot)
            if _same(record.get("temporal_identity"), definition):
                companions.append((ref, snapshot, record))
        if len(companions) != 1:
            _fail("Exactly one accepted whole-subject identity companion is required")
        identity_ref, identity_snapshot, identity_record = companions[0]
        declared_base = identity_record.get("base")
        if type(declared_base) is not dict:
            _fail("Invalid accepted subject-identity companion base")
        identity_base = declared_base.get("revision_id")
        if type(identity_base) is not str or identity_base not in ancestors(
            base, self.authenticated
        ):
            _fail("Subject-identity companion base must be an authenticated ancestor")
        original = _identity(identity_base, self.witnesses(identity_base), self.artifacts)
        if (
            not _same(original.evidence_reference, identity_ref)
            or self.artifacts.resolve_reference(original.evidence_reference).content
            != identity_snapshot.content
            or not _same(identity_record["temporal_identity"], definition)
            or not _same(
                identity_record["subject_observation_evidence"],
                current_record["subject_observation_evidence"],
            )
            or not _same(identity_record["r0_evidence_reference"], current.r0_evidence_reference)
        ):
            _fail("Complete accepted subject-identity companion does not independently reproduce")
        ownership = identity_record["subject_observation_evidence"]
        membership_refs = [
            ref
            for ref in _references(document)
            if ref["media_type"] == MEMBERSHIP_MEDIA
            and _same(_record(self.artifacts.resolve_reference(ref)), ownership)
        ]
        if len(membership_refs) != 1:
            _fail("Exactly one reproduced accepted subject-membership companion is required")
        source_subject = {
            "source_artifact_id": ownership["subject"]["ownership_root_artifact_id"],
            "subject_path": [0],
        }
        # Exact existing Spec78 allocation domain, never a caller target choice.
        members = sorted(
            "entity:"
            + _hash(
                {
                    "authority_identity": AUTHORITY,
                    "profile_identity": CONSTRUCTION_PROFILE,
                    "subject": source_subject,
                    "part_key": part,
                    "record_kind": "entity",
                }
            )
            for part in PART_KEYS
        )
        gid = "group:" + _hash(
            {
                "authority_identity": AUTHORITY,
                "profile_identity": CONSTRUCTION_PROFILE,
                "members": members,
            }
        )
        # Inspect all Groups, including differently named aliases of these parts.
        relevant_groups = [
            item
            for item in document.get("groups", [])
            if item["id"] == gid or set(item["members"]) & set(members)
        ]
        if len(relevant_groups) != 1 or relevant_groups[0]["id"] != gid:
            _fail("Exactly one source-derived eligible artwork Group is required")
        births = [
            (before, after)
            for before, after in zip(chain, chain[1:], strict=False)
            if _unique(self.authenticated[before].document, "groups", gid) is None
            and _unique(self.authenticated[after].document, "groups", gid) is not None
        ]
        if len(births) != 1:
            _fail("Exactly one authenticated Group birth transition is required")
        pre, post = births[0]
        pre_document = self.authenticated[pre].document
        if not _same(_unique(pre_document, "temporal_identities", tid), definition) or not _same(
            _descriptor(pre_document, identity_ref["id"]), identity_ref
        ):
            _fail("Accepted source-backed whole identity must exist before Group birth")
        pre_identity = _identity(pre, self.witnesses(pre), self.artifacts)
        pre_record = _record(self.artifacts.resolve_reference(pre_identity.evidence_reference))
        if not _same(pre_record["subject_observation_evidence"], ownership) or not _same(
            pre_record["temporal_identity"], definition
        ):
            _fail("Whole identity source membership changed before construction")
        constructed = _construction(pre, self.witnesses(pre), self.artifacts)
        expected_post = copy.deepcopy(pre_document)
        constructed.apply(expected_post)
        if not _same(expected_post, self.authenticated[post].document):
            _fail("Complete construction birth post-Document does not independently reproduce")
        if constructed.group["id"] != gid or not _same(constructed.group["members"], members):
            _fail("Construction birth does not derive the unique current source Group")
        manifest_ref, receipt_ref = constructed.references[-2:]
        receipt = _record(self.artifacts.resolve_reference(receipt_ref))
        evidence = receipt["evidence"]
        if (
            not _same(evidence["reference"], ownership["admitted_evidence_reference"])
            or not _same(evidence["parts"], ownership["parts"])
            or not _same(evidence["membership"], ownership["membership"])
            or not _same(
                evidence["universe"],
                [
                    {
                        key: occurrence[key]
                        for key in ("occurrence_id", "frame_index", "tick", "source_timestamp")
                    }
                    for occurrence in ownership["occurrences"]
                ],
            )
            or evidence["subject_id"] != ownership["subject"]["subject_id"]
            or evidence["admission"]
            != {key: ownership["admission"][key] for key in ("base_revision_id", "transition_hash")}
            or receipt["representation_claim"] is not None
        ):
            _fail("Construction birth and whole identity do not prove identical complete ownership")
        expected_projection = {
            "entities": list(constructed.fragment.entities),
            "operations": list(constructed.fragment.operations),
            "output_bindings": list(constructed.fragment.output_bindings),
            "styles": list(constructed.fragment.styles),
            "render_entries": list(constructed.fragment.render_entries),
            "group": constructed.group,
            "temporal_identity": definition,
        }
        operations = {item["id"] for item in constructed.fragment.operations}
        required = (
            ownership["admitted_evidence_reference"],
            identity_ref,
            membership_refs[0],
            identity_record["r0_evidence_reference"],
            ownership["observation_reference"],
            *constructed.references,
            manifest_ref,
            receipt_ref,
        )
        for rid in chain[chain.index(post) :]:
            snapshot = self.authenticated[rid].document
            projection = {
                "entities": [e for e in snapshot["entities"] if e["id"] in members],
                "operations": [
                    o for o in snapshot["construction"]["operations"] if o["id"] in operations
                ],
                "output_bindings": [
                    b for b in snapshot["construction"]["output_bindings"] if b["entity"] in members
                ],
                "styles": [s for s in snapshot["presentation"]["styles"] if s["entity"] in members],
                "render_entries": [
                    e for e in snapshot["presentation"]["render_stack"] if e in members
                ],
                "group": _unique(snapshot, "groups", gid),
                "temporal_identity": _unique(snapshot, "temporal_identities", tid),
            }
            if not _same(projection, expected_projection):
                _fail(
                    "Bounded representation or identity continuity changed after construction birth"
                )
            for ref in required:
                if not _same(_descriptor(snapshot, ref["id"]), ref):
                    _fail("Required representation dependency descriptor continuity changed")
            for binding in snapshot.get("motion_target_bindings", []):
                if binding["temporal_identity_id"] == tid or binding["target"]["group_id"] == gid:
                    _fail("Already-bound identity or Group is ineligible for certification")
            for track in snapshot.get("animation", {}).get("content", []):
                target = track.get("target", {})
                if (
                    target.get("group") == gid
                    or target.get("entity") in members
                    or target.get("operation") in operations
                ):
                    _fail("Relevant sampled representation Track is unsupported by this profile")
        facts = {
            "schema_version": SCHEMA,
            "profile_identity": PROFILE,
            "proof_mode": PROOF_MODE,
            "ownership_evidence_reference": ownership["admitted_evidence_reference"],
            "ownership_admission": ownership["admission"],
            "subject_identity": {
                "identity_evidence_reference": identity_ref,
                "subject_observation_evidence": ownership,
                "r0_evidence_reference": identity_record["r0_evidence_reference"],
                "temporal_identity": definition,
            },
            "construction_birth": {
                "proof_kind": "STRUCTURAL_CONFORMITY_ONLY",
                "pre_revision_id": pre,
                "post_revision_id": post,
                "construction_reference": manifest_ref,
                "receipt_reference": receipt_ref,
            },
            "association": {
                "subject_id": ownership["subject"]["subject_id"],
                "temporal_identity_id": tid,
                "group_id": gid,
            },
            "representation": expected_projection,
        }
        self.facts_cache[base] = facts
        return facts

    def claims(self, base: str) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
        if base in self.claims_cache:
            return self.claims_cache[base]
        facts = self.facts(base)
        refs, applicable = [], []
        for ref in _references(self.authenticated[base].document):
            if ref["media_type"] != MEDIA:
                continue
            events = [
                event
                for rid in sorted(ancestors(base, self.authenticated))
                for event in getattr(self.authenticated[rid].revision, "admissions", ())
                if _same(event.artifact_reference, ref)
            ]
            if not events:
                continue  # Unadmitted canonical bytes remain DATA, without authority.
            if len(events) != 1:
                _fail("Multiple distinct representation certification admissions")
            event = events[0]
            if (event.contract, event.change_identity, event.authority_identity) != (
                CERT_CONTRACT,
                CERT_CHANGE,
                CERT_AUTHORITY,
            ):
                _fail("Unsupported representation certification admission authority")
            snapshot = self.artifacts.resolve_reference(ref)
            stored = _record(snapshot)
            oldbase = event.base_revision_id
            if oldbase == base or oldbase not in ancestors(base, self.authenticated):
                _fail("Association replay must follow strictly earlier authenticated bases")
            reproduced = self.record(oldbase)
            if (
                snapshot.content != canonical_bytes(reproduced)
                or snapshot.kind != ArtifactKind.DERIVED
                or snapshot.media_type != MEDIA
                or snapshot.provenance != {"profile_identity": PROFILE}
                or not _same(snapshot.document_reference(), ref)
            ):
                _fail("Complete admitted association does not reproduce at its recorded base")
            refs.append(ref)
            if claim_key(stored) == claim_key(facts):
                applicable.append(ref)
            elif (
                stored["association"]["temporal_identity_id"]
                == facts["association"]["temporal_identity_id"]
                or stored["association"]["group_id"] == facts["association"]["group_id"]
            ):
                _fail("Incompatible admitted representation ownership claim")
        if len(applicable) > 1:
            _fail("Duplicate equivalent admitted representation claims are ambiguous")
        result = (tuple(refs), tuple(applicable))
        self.claims_cache[base] = result
        return result

    def record(self, base: str) -> dict[str, Any]:
        if base in self.record_cache:
            return self.record_cache[base]
        if base in self.active:
            _fail("Cyclic representation certification history")
        self.active.add(base)
        try:
            claims, _ = self.claims(base)
            document = self.authenticated[base].document
            record = {
                **self.facts(base),
                "base": {
                    "revision_id": base,
                    "document_hash": self.authenticated[base].revision.document_hash,
                },
                "universe": {
                    "temporal_identities": sorted(
                        document.get("temporal_identities", []), key=lambda item: item["id"]
                    ),
                    "groups": sorted(document.get("groups", []), key=lambda item: item["id"]),
                    "association_references": list(claims),
                },
            }
            self.record_cache[base] = record
            return record
        finally:
            self.active.remove(base)


def admitted_associations(
    base: str,
    witnesses: tuple[RevisionSnapshotWitness, ...],
    artifacts: ArtifactRepository,
) -> tuple[dict[str, Any], ...]:
    """Read-only current consumption proof, requiring genuine event and full replay."""
    authenticated = authenticate_witnesses(base, witnesses)
    scratch = _scratch(authenticated[base].document, artifacts)
    return copy.deepcopy(_Replay(base, witnesses, scratch).claims(base)[1])


def _derive(
    base: str,
    witnesses: tuple[RevisionSnapshotWitness, ...],
    artifacts: ArtifactRepository,
) -> CertifyArtworkRepresentationChange:
    replay = _Replay(base, witnesses, artifacts)
    document = replay.authenticated[base].document
    _, applicable = replay.claims(base)
    if applicable:
        reference = applicable[0]
    else:
        reference = artifacts.import_bytes(
            canonical_bytes(replay.record(base)),
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"profile_identity": PROFILE},
        ).document_reference()
        if _descriptor(document, reference["id"]) is not None:
            _fail("An unadmitted reference cannot establish authority through idempotent reuse")
    return CertifyArtworkRepresentationChange(
        base,
        copy.deepcopy(document),
        witnesses,
        PROFILE,
        _references(document),
        copy.deepcopy(reference),
    )


def verify_change(
    change: CertifyArtworkRepresentationChange, resolved: dict[str, ArtifactSnapshot]
) -> None:
    if type(change) is not CertifyArtworkRepresentationChange or change.profile_identity != PROFILE:
        _fail("Unregistered representation certification Change or profile")
    authenticated = authenticate_witnesses(change.source_revision_id, change.witnesses)
    document = authenticated[change.source_revision_id].document
    if not _same(document, change.base_document_snapshot):
        _fail("Certification base snapshot mismatch")
    if not _same(_references(document), change.source_references):
        _fail(
            "Certification requires the independently enumerated complete base reference universe"
        )
    scratch = ArtifactStore()
    for ref in change.references:
        actual = resolved[ref["id"]]
        if not _same(actual.document_reference(), ref):
            _fail("Certification transported descriptor mismatch")
        scratch.import_bytes(
            actual.content,
            media_type=actual.media_type,
            kind=actual.kind,
            provenance=actual.provenance,
            locator=actual.descriptor.locator,
        )
    expected = _derive(change.source_revision_id, change.witnesses, scratch)
    if not _same(asdict(change), asdict(expected)):
        _fail("Certification output or complete transport does not independently reproduce")
    ref = expected.association_reference
    actual = resolved[ref["id"]]
    if actual.content != scratch.resolve_reference(ref).content or not _same(
        actual.document_reference(), ref
    ):
        _fail("Certification canonical bytes or output descriptor do not reproduce")


class RepresentationCertificationAdapter:
    adapter_id = "adapter:representation-certification"

    def propose(
        self,
        request: AdapterRequest,
        artifacts: ArtifactRepository,
        *,
        witnesses: tuple[RevisionSnapshotWitness, ...],
    ) -> Proposal:
        if request.options or request.artifact_ids or request.scope not in {(), ("document",)}:
            _fail("Certification accepts document scope and no selectors/options")
        authenticated = authenticate_witnesses(request.base_revision_id, witnesses)
        if not _same(authenticated[request.base_revision_id].document, request.document):
            _fail("Certification request base snapshot mismatch")
        scratch = _scratch(request.document, artifacts)
        change = _derive(request.base_revision_id, witnesses, scratch)
        output = scratch.resolve_reference(change.association_reference)
        artifacts.import_bytes(
            output.content,
            media_type=output.media_type,
            kind=output.kind,
            provenance=output.provenance,
            locator=output.descriptor.locator,
        )
        digest = _hash(asdict(change))
        return Proposal(
            f"proposal:representation-certification:{digest}",
            request.base_revision_id,
            GeneratorProvenance(self.adapter_id, "0.1", "svm", PROFILE),
            Transaction(
                f"transaction:representation-certification:{digest}",
                (change,),
                "Certify present source-backed artwork representation",
            ),
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
            notes=(
                "Present-time association admission; historical birth proves "
                "structural conformity only"
            ),
        )
