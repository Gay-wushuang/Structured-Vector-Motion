"""Spec79: source-backed whole-subject data, full R0 replay and frozen R1 promotion.

The companion Artifacts are reproducible data, never admission authority. Only
authenticated Spec77 history and independently replayed Spec76 grant membership.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from typing import Any, NoReturn

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..evaluator import canonical_bytes
from ..multipart_witness import RevisionSnapshotWitness, ancestors, authenticate_witnesses
from ..proposals import AdapterRequest, GeneratorProvenance, Proposal
from ..revisions import (
    AppendReferencesChange,
    ApplySubjectIdentityBridgeChange,
    AttachSubjectObservationsChange,
    PromoteTemporalIdentityChange,
    Transaction,
    temporal_identity_id,
)
from .multipart_subject_evidence import _references, derive
from .temporal_correspondence import (
    EVIDENCE_MEDIA_TYPE,
    OBSERVATION_MEDIA_TYPE,
    OBSERVATION_MEDIA_TYPE_V2,
    TemporalCorrespondenceAdapter,
    read_primitive_observations,
)
from .temporal_identity_promotion import TemporalIdentityPromotionAdapter
from .video_artwork_construction import _descriptor, _enumerate

PROFILE = "svm-source-backed-two-triangle-subject-observation@0.1"
PRIMITIVE_TYPE = "source-backed-multipart-subject-bounds@0.1"
SCHEMA = "svm-subject-observation-bridge-0.1"
MEDIA = "application/vnd.svm.subject-observation-bridge+json;version=0.1"
IDENTITY_SCHEMA = "svm-subject-identity-bridge-0.1"
IDENTITY_MEDIA = "application/vnd.svm.subject-identity-bridge+json;version=0.1"


class SubjectObservationBridgeError(ValueError):
    pass


def _fail(reason: str) -> NoReturn:
    raise SubjectObservationBridgeError(reason)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _record(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    try:
        value = json.loads(snapshot.content)
        if type(value) is not dict or canonical_bytes(value) != snapshot.content:
            _fail("Accepted bridge/R0 record must be a canonical JSON object")
    except (UnicodeDecodeError, TypeError, ValueError) as exc:
        raise SubjectObservationBridgeError("Invalid accepted bridge/R0 record") from exc
    return value


def _publish(
    payload: dict[str, Any], media: str, kind: ArtifactKind, artifacts: ArtifactRepository
) -> dict[str, Any]:
    return artifacts.import_bytes(
        canonical_bytes(payload),
        media_type=media,
        kind=kind,
        provenance={"profile_identity": PROFILE},
    ).document_reference()


def _subject(
    base: str, witnesses: tuple[RevisionSnapshotWitness, ...], artifacts: ArtifactRepository
) -> tuple[AttachSubjectObservationsChange, dict[str, Any]]:
    authenticated = authenticate_witnesses(base, witnesses)
    document = authenticated[base].document
    source_refs = _references(document)
    # Enumeration checks exact historical/current descriptors and genuine events.
    # Full Spec76 replay additionally checks original and CURRENT pixel/P2A/P2B
    # closure, complete membership and competing ownership. Neither check alone
    # is a substitute for the other.
    evidence, record, event, _ = _enumerate(base, authenticated, artifacts)
    new, reused = derive(base, witnesses, artifacts)
    if new is not None or canonical_bytes(reused) != canonical_bytes(evidence):
        _fail("A currently applicable independently replayed Spec76 admission is required")
    observation_refs = [
        r for r in record["dependencies"] if r["media_type"] == OBSERVATION_MEDIA_TYPE_V2
    ]
    if len(observation_refs) != 1:
        _fail("Exactly one verified part-observation universe is required")
    observed = read_primitive_observations(artifacts.resolve_reference(observation_refs[0]).content)
    part_lookup = {
        (frame["tick"], part["observation_id"]): part
        for frame in observed["frames"]
        for part in frame["primitives"]
    }
    frames, occurrences = [], []
    for occurrence in record["occurrences"]:
        cells = [
            c for c in record["membership"] if c["occurrence_id"] == occurrence["occurrence_id"]
        ]
        if (
            len(cells) != 2
            or [{k: c[k] for k in ("part_id", "part_key")} for c in cells] != record["parts"]
            or any(any(c[k] != occurrence[k] for k in occurrence) for c in cells)
        ):
            _fail("Incomplete authenticated subject membership")
        parts = [part_lookup[(occurrence["tick"], c["observation_id"])] for c in cells]
        if len({p["fill"] for p in parts}) != 1:
            _fail("Whole-subject bounds-only profile requires one verified uniform RGB fill")
        # P2B's half-open raster bounds have been independently reproduced by
        # Spec75/76. The bounding box of their exhaustive disjoint mask union is
        # exactly the coordinate-wise union; no synthetic polygon/landmarks.
        bounds = [min(p["bounds"][i] for p in parts) for i in (0, 1)] + [
            max(p["bounds"][i] for p in parts) for i in (2, 3)
        ]
        oid = "observation:subject:" + _hash(
            {
                "profile_identity": PROFILE,
                "subject_id": record["subject"]["subject_id"],
                "occurrence": occurrence,
                "membership": cells,
            }
        )
        primitive = {
            "observation_id": oid,
            "primitive_type": PRIMITIVE_TYPE,
            "bounds": bounds,
            "fill": parts[0]["fill"],
        }
        frames.append({"tick": occurrence["tick"], "primitives": [primitive]})
        occurrences.append(
            {**occurrence, "observation_id": oid, "bounds": bounds, "fill": parts[0]["fill"]}
        )
    payload = {
        "schema_version": "svm-primitive-observations-0.1",
        "canvas": observed["canvas"],
        "frames": frames,
    }
    read_primitive_observations(canonical_bytes(payload))  # Actual frozen R0 grammar.
    observation = _publish(payload, OBSERVATION_MEDIA_TYPE, ArtifactKind.REFERENCE, artifacts)
    accepted_observation = _descriptor(document, observation["id"])
    if accepted_observation is not None and canonical_bytes(
        accepted_observation
    ) != canonical_bytes(observation):
        _fail("Accepted whole-observation descriptor conflicts with reproduced output")
    companion = {
        "schema_version": SCHEMA,
        "profile_identity": PROFILE,
        "base": {"revision_id": base, "document_hash": authenticated[base].revision.document_hash},
        "admitted_evidence_reference": evidence,
        "admission": asdict(event),
        "subject": record["subject"],
        "parts": record["parts"],
        "occurrences": occurrences,
        "membership": record["membership"],
        "observation_reference": observation,
    }
    proof = _publish(companion, MEDIA, ArtifactKind.DERIVED, artifacts)
    return AttachSubjectObservationsChange(
        base, copy.deepcopy(document), witnesses, PROFILE, source_refs, observation, proof
    ), companion


def _identity(
    base: str, witnesses: tuple[RevisionSnapshotWitness, ...], artifacts: ArtifactRepository
) -> ApplySubjectIdentityBridgeChange:
    subject_change, companion = _subject(base, witnesses, artifacts)
    authenticated = authenticate_witnesses(base, witnesses)
    document = authenticated[base].document
    observation = subject_change.observation_reference
    if canonical_bytes(_descriptor(document, observation["id"])) != canonical_bytes(observation):
        _fail("Whole-subject observation must already be accepted with its exact descriptor")
    # Inspect EVERY accepted R0 descriptor; no request-selected evidence subset.
    matches = []
    for ref in subject_change.source_references:
        if ref["media_type"] != EVIDENCE_MEDIA_TYPE:
            continue
        snapshot = artifacts.resolve_reference(ref)
        value = _record(snapshot)
        if value.get("source_artifact_id") == observation["id"]:
            matches.append((ref, snapshot, value))
    if len(matches) != 1:
        _fail("Exactly one accepted whole-subject R0 evidence Artifact is required")
    r0_ref, actual, recorded = matches[0]
    r0_base = recorded.get("source_revision_id")
    if type(r0_base) is not str or r0_base not in ancestors(base, authenticated):
        _fail("R0 source revision must be an authenticated ancestor")
    historical_document = authenticated[r0_base].document
    if canonical_bytes(_descriptor(historical_document, observation["id"])) != canonical_bytes(
        observation
    ):
        _fail("R0 source observation must already be accepted at its recorded source base")
    # The preceding stage must be concrete accepted data at R0's real creation
    # base. Its media/provenance does NOT grant authority: replay its complete
    # record at an authenticated production base and compare current membership.
    companions = []
    for ref in subject_change.source_references:
        if ref["media_type"] != MEDIA:
            continue
        snapshot = artifacts.resolve_reference(ref)
        value = _record(snapshot)
        declared_observation = value.get("observation_reference")
        if type(declared_observation) is not dict:
            _fail("Invalid accepted subject-observation companion descriptor")
        if declared_observation.get("id") == observation["id"] and canonical_bytes(
            _descriptor(historical_document, ref["id"])
        ) == canonical_bytes(ref):
            companions.append((ref, snapshot, value))
    if len(companions) != 1:
        _fail(
            "Exactly one accepted subject-observation companion at the R0 source base is required"
        )
    companion_ref, stored_companion, original_companion = companions[0]
    declared_base = original_companion.get("base")
    if type(declared_base) is not dict:
        _fail("Invalid subject-observation production base")
    producer_base = declared_base.get("revision_id")
    if type(producer_base) is not str or producer_base not in ancestors(r0_base, authenticated):
        _fail("Subject-observation production base must be an authenticated R0 ancestor")
    producer_witnesses = tuple(
        authenticated[rid] for rid in sorted(ancestors(producer_base, authenticated))
    )
    original_change, reproduced_companion = _subject(producer_base, producer_witnesses, artifacts)
    if (
        stored_companion.content != canonical_bytes(reproduced_companion)
        or canonical_bytes(companion_ref) != canonical_bytes(original_change.evidence_reference)
        or canonical_bytes(original_change.observation_reference) != canonical_bytes(observation)
        or any(
            canonical_bytes(original_companion[k]) != canonical_bytes(companion[k])
            for k in (
                "admitted_evidence_reference",
                "admission",
                "subject",
                "parts",
                "occurrences",
                "membership",
            )
        )
    ):
        _fail("Complete historical subject-observation companion does not independently reproduce")
    reproduced = TemporalCorrespondenceAdapter().propose(
        AdapterRequest(
            r0_base, historical_document, ("document",), artifact_ids=(observation["id"],)
        ),
        artifacts,
    )
    reproduced_change = reproduced.transaction.changes[0]
    if type(reproduced_change) is not AppendReferencesChange:
        _fail("Exact frozen R0 evidence attachment Change required")
    expected_ref = reproduced_change.references[0]
    expected = artifacts.resolve_reference(expected_ref)
    if actual.content != expected.content or canonical_bytes(r0_ref) != canonical_bytes(
        expected_ref
    ):
        _fail("Complete frozen R0 evidence/descriptor does not independently reproduce")
    candidates = recorded["candidates"]
    if len(candidates) != 1 or candidates[0]["status"] != "SUPPORTED":
        _fail("Whole-subject R0 must contain exactly one independently SUPPORTED candidate")
    candidate = candidates[0]
    canonical_id = temporal_identity_id(r0_ref["id"], candidate["candidate_id"])
    part_keys = {(cell["tick"], cell["observation_id"]) for cell in companion["membership"]}
    whole_keys = {(o["tick"], o["observation_id"]) for o in companion["occurrences"]}
    part_owners = {
        item["id"]
        for item in document.get("temporal_identities", [])
        if any((b["tick"], b["observation_id"]) in part_keys for b in item["bindings"])
    }
    for item in document.get("temporal_identities", []):
        if any((b["tick"], b["observation_id"]) in whole_keys for b in item["bindings"]):
            if item["id"] in part_owners or item["id"] != canonical_id:
                _fail("Whole-subject endpoints cannot reuse a part or unrelated identity")
    promotion = TemporalIdentityPromotionAdapter().propose(
        AdapterRequest(
            base,
            document,
            ("document",),
            artifact_ids=(r0_ref["id"],),
            options={"inference_ids": [candidate["inference_id"]]},
        ),
        artifacts,
    )
    delegated = promotion.transaction.changes[0]
    if type(delegated) is not PromoteTemporalIdentityChange:
        _fail("Exact frozen R1 promotion Change required")
    promoted = delegated.correspondences[0]
    definition = {
        "id": canonical_id,
        "bindings": list(promoted.bindings()),
        "provenance": [promoted.provenance()],
    }
    for item in document.get("temporal_identities", []):
        if item["id"] == canonical_id and canonical_bytes(item) != canonical_bytes(definition):
            _fail("Existing whole identity must have exactly the replayed bindings/provenance")
    if promoted.stable_identity_id != canonical_id or canonical_id in part_owners:
        _fail("Whole-subject identity must be independent of part identities")
    proof = _publish(
        {
            "schema_version": IDENTITY_SCHEMA,
            "profile_identity": PROFILE,
            "base": companion["base"],
            "subject_observation_evidence": original_companion,
            "r0_evidence_reference": r0_ref,
            "temporal_identity": definition,
        },
        IDENTITY_MEDIA,
        ArtifactKind.DERIVED,
        artifacts,
    )
    return ApplySubjectIdentityBridgeChange(
        base,
        copy.deepcopy(document),
        witnesses,
        PROFILE,
        subject_change.source_references,
        observation,
        r0_ref,
        delegated,
        proof,
    )


def verify_change(
    change: AttachSubjectObservationsChange | ApplySubjectIdentityBridgeChange,
    resolved: dict[str, ArtifactSnapshot],
) -> None:
    if change.profile_identity != PROFILE:
        _fail("Unknown subject-observation profile")
    authenticated = authenticate_witnesses(change.source_revision_id, change.witnesses)
    document = authenticated[change.source_revision_id].document
    if canonical_bytes(document) != canonical_bytes(change.base_document_snapshot):
        _fail("Subject bridge base snapshot mismatch")
    if canonical_bytes(_references(document)) != canonical_bytes(change.source_references):
        _fail(
            "Subject bridge requires the independently enumerated complete base reference universe"
        )
    scratch = ArtifactStore()
    for ref in change.references:
        actual = resolved[ref["id"]]
        if canonical_bytes(actual.document_reference()) != canonical_bytes(ref):
            _fail("Subject bridge transported descriptor mismatch")
        scratch.import_bytes(
            actual.content,
            media_type=actual.media_type,
            kind=actual.kind,
            provenance=actual.provenance,
            locator=actual.descriptor.locator,
        )
    if type(change) is AttachSubjectObservationsChange:
        expected, _ = _subject(change.source_revision_id, change.witnesses, scratch)
        outputs = (expected.observation_reference, expected.evidence_reference)
    elif type(change) is ApplySubjectIdentityBridgeChange:
        expected = _identity(change.source_revision_id, change.witnesses, scratch)
        outputs = (expected.evidence_reference,)
    else:
        _fail("Unregistered subject bridge Change")
    if canonical_bytes(asdict(change)) != canonical_bytes(asdict(expected)):
        _fail("Subject bridge output/delegation/transport does not reproduce")
    for ref in outputs:
        actual = resolved[ref["id"]]
        if actual.content != scratch.resolve_reference(ref).content or canonical_bytes(
            actual.document_reference()
        ) != canonical_bytes(ref):
            _fail("Subject bridge output bytes/descriptor do not reproduce")


class SubjectObservationAdapter:
    adapter_id = "adapter:subject-observation"

    def propose(
        self,
        request: AdapterRequest,
        artifacts: ArtifactRepository,
        *,
        witnesses: tuple[RevisionSnapshotWitness, ...],
    ) -> Proposal:
        return _propose(request, artifacts, witnesses, self.adapter_id, identity=False)


class SubjectIdentityBridgeAdapter:
    adapter_id = "adapter:subject-identity-bridge"

    def propose(
        self,
        request: AdapterRequest,
        artifacts: ArtifactRepository,
        *,
        witnesses: tuple[RevisionSnapshotWitness, ...],
    ) -> Proposal:
        return _propose(request, artifacts, witnesses, self.adapter_id, identity=True)


def _propose(
    request: AdapterRequest,
    artifacts: ArtifactRepository,
    witnesses: tuple[RevisionSnapshotWitness, ...],
    adapter_id: str,
    *,
    identity: bool,
) -> Proposal:
    if request.options or request.artifact_ids or request.scope not in {(), ("document",)}:
        _fail("Subject bridge accepts document scope and no selectors/options")
    authenticated = authenticate_witnesses(request.base_revision_id, witnesses)
    if canonical_bytes(authenticated[request.base_revision_id].document) != canonical_bytes(
        request.document
    ):
        _fail("Subject bridge request base snapshot mismatch")
    change = (
        _identity(request.base_revision_id, witnesses, artifacts)
        if identity
        else _subject(request.base_revision_id, witnesses, artifacts)[0]
    )
    digest = _hash(asdict(change))
    return Proposal(
        f"proposal:subject-bridge:{digest}",
        request.base_revision_id,
        GeneratorProvenance(adapter_id, "0.1", "svm", PROFILE),
        Transaction(
            f"transaction:subject-bridge:{digest}",
            (change,),
            "Promote source-backed whole-subject identity"
            if identity
            else "Attach source-backed whole-subject observations",
        ),
        required_artifact_ids=tuple(ref["id"] for ref in change.references),
        notes=(
            "Membership authority requires genuine Spec77 history and full Spec76 replay; "
            "companion bytes are data only"
        ),
    )
