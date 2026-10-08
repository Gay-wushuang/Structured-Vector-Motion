"""Spec78: authenticated admitted ownership to source-fixed path artwork, CREATE only."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from typing import Any, NoReturn

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..authored_raster_production import PART_KEYS, POLICY, _triangles
from ..evaluator import Evaluator, canonical_bytes
from ..multipart_witness import RevisionSnapshotWitness, ancestors, authenticate_witnesses
from ..operations import _geometry_bounds
from ..path_bounds import canonical_path_bounds
from ..proposals import (
    AdapterRequest,
    ConstructionGroupDefinitionPreview,
    GeneratorProvenance,
    Proposal,
    ProposalPreview,
)
from ..revisions import (
    AdmissionEvent,
    AppendSceneFragmentChange,
    EstablishVideoArtworkGroupChange,
    Transaction,
)
from ..scene import _canonical_scene_number
from .multipart_subject_evidence import DOMAIN, claim_key
from .multipart_subject_evidence import MEDIA as EVIDENCE_MEDIA
from .multipart_subject_evidence import PROFILE as EVIDENCE_PROFILE
from .multipart_subject_evidence import SCHEMA as EVIDENCE_SCHEMA
from .svg_group_construction import AUTHORITY, MANIFEST_MEDIA, ORIGIN

PROFILE = "svm-video-two-part-group-construction@0.1"
RECEIPT_SCHEMA = "svm-video-two-part-group-establishment-0.1"
RECEIPT_MEDIA = "application/vnd.svm.video-two-part-group-establishment+json;version=0.1"


class VideoArtworkConstructionError(ValueError):
    pass


def _fail(reason: str) -> NoReturn:
    raise VideoArtworkConstructionError(reason)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _descriptor(document: dict[str, Any], aid: str) -> dict[str, Any] | None:
    matches = {canonical_bytes(r): r for r in document["references"] if r["id"] == aid}
    if len(matches) > 1:
        _fail("Ambiguous dependency descriptor")
    return next(iter(matches.values()), None)


def _events(
    base: str, witnesses: dict[str, RevisionSnapshotWitness], ref: dict[str, Any]
) -> list[AdmissionEvent]:
    return [
        event
        for rid in sorted(ancestors(base, witnesses))
        for event in getattr(witnesses[rid].revision, "admissions", ())
        if canonical_bytes(event.artifact_reference) == canonical_bytes(ref)
    ]


def _record(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    record = json.loads(snapshot.content, parse_constant=_fail)
    fields = {
        "schema_version",
        "profile_identity",
        "base",
        "source",
        "subject",
        "parts",
        "production_policy",
        "video",
        "manifest",
        "occurrences",
        "membership",
        "claim_key",
        "dependencies",
        "competing_claims",
    }
    if (
        type(record) is not dict
        or set(record) != fields
        or canonical_bytes(record) != snapshot.content
        or record["schema_version"] != EVIDENCE_SCHEMA
        or record["profile_identity"] != EVIDENCE_PROFILE
        or record["production_policy"] != POLICY
        or snapshot.kind != ArtifactKind.DERIVED
        or snapshot.media_type != EVIDENCE_MEDIA
        or snapshot.provenance != {"profile_identity": EVIDENCE_PROFILE}
    ):
        _fail("Invalid admitted evidence schema/descriptor")
    for key, keys in (
        ("base", {"revision_id", "document_hash"}),
        ("source", {"artifact_id", "content_hash", "media_type", "source_revision_id"}),
        ("subject", {"subject_id", "ownership_root_artifact_id", "canonical_source_subject_path"}),
        ("video", {"artifact_id", "content_hash"}),
        ("manifest", {"artifact_id", "content_hash"}),
        ("competing_claims", {"claim_artifact_ids", "disposition"}),
    ):
        if type(record[key]) is not dict or set(record[key]) != keys:
            _fail("Invalid admitted evidence fields")
    occurrence_keys = {"occurrence_id", "frame_index", "tick", "source_timestamp"}
    part_keys = {"part_id", "part_key"}
    membership_keys = (
        occurrence_keys
        | part_keys
        | {
            "subject_id",
            "component_id",
            "evaluation_id",
            "observation_id",
            "contribution_artifact_id",
            "full_canvas_label_identity",
        }
    )
    for key, length, keys in (
        ("parts", 2, part_keys),
        ("occurrences", 2, occurrence_keys),
        ("membership", 4, membership_keys),
    ):
        if (
            type(record[key]) is not list
            or len(record[key]) != length
            or any(type(item) is not dict or set(item) != keys for item in record[key])
        ):
            _fail("Invalid admitted evidence universe")
    if type(record["dependencies"]) is not list or not record["dependencies"]:
        _fail("Invalid admitted evidence dependencies")
    audit = record["competing_claims"]
    claims = audit["claim_artifact_ids"]
    if (
        audit["disposition"] != "NO_COMPETING_CLAIM"
        or type(claims) is not list
        or any(type(aid) is not str for aid in claims)
        or claims != sorted(set(claims))
    ):
        _fail("Invalid admitted competing claim audit")
    for item in (*record["occurrences"], *record["membership"]):
        timestamp = item["source_timestamp"]
        if (
            type(item["frame_index"]) is not int
            or type(item["tick"]) is not int
            or type(timestamp) is not list
            or len(timestamp) != 2
            or any(type(number) is not int for number in timestamp)
            or timestamp[1] <= 0
        ):
            _fail("Invalid admitted evidence timing")
    if record["claim_key"] != claim_key(record):
        _fail("Admitted claim key mismatch")
    return record


def _enumerate(
    base: str, witnesses: dict[str, RevisionSnapshotWitness], artifacts: ArtifactRepository
) -> tuple[dict[str, Any], dict[str, Any], AdmissionEvent, tuple[dict[str, Any], ...]]:
    document = witnesses[base].document
    references = {
        canonical_bytes(r): r for r in document["references"] if r["media_type"] == EVIDENCE_MEDIA
    }
    transport: dict[str, dict[str, Any]] = {}
    eligible = []

    def include(ref: dict[str, Any]) -> None:
        if ref["id"] in transport and canonical_bytes(transport[ref["id"]]) != canonical_bytes(ref):
            _fail("Conflicting transported descriptors")
        actual = artifacts.resolve_reference(ref)
        if canonical_bytes(actual.document_reference()) != canonical_bytes(ref):
            _fail("Transport descriptor mismatch")
        transport[ref["id"]] = ref

    for ref in sorted(references.values(), key=lambda r: (r["id"], canonical_bytes(r))):
        events = _events(base, witnesses, ref)
        if not events:
            continue  # Legacy bytes are neither required nor read nor authority.
        if len(events) != 1:
            _fail("Multiple distinct evidence admission transitions")
        include(ref)  # Even an inapplicable admitted candidate cannot be shortlisted away.
        record = _record(artifacts.resolve_reference(ref))
        oldbase = record["base"]["revision_id"]
        if (
            events[0].base_revision_id != oldbase
            or oldbase not in ancestors(base, witnesses)
            or record["base"]["document_hash"] != witnesses[oldbase].revision.document_hash
        ):
            _fail("Evidence admission/base commitment mismatch")
        required = []
        for key in ("source", "video", "manifest"):
            summary = record[key]
            oldref = _descriptor(witnesses[oldbase].document, summary["artifact_id"])
            if oldref is None or any(summary[k] != oldref[k] for k in ("content_hash",)):
                _fail("Evidence summary does not match its authenticated base descriptor")
            if key == "source" and summary["media_type"] != oldref["media_type"]:
                _fail("Source summary media mismatch")
            required.append(oldref)
        for dep in record["dependencies"]:
            if canonical_bytes(
                _descriptor(witnesses[oldbase].document, dep["id"])
            ) != canonical_bytes(dep):
                _fail("Evidence dependency does not match its authenticated base")
            required.append(dep)
        applicable = record["source"]["source_revision_id"] in ancestors(base, witnesses)
        for dep in required:
            current = _descriptor(document, dep["id"])
            if current is None or canonical_bytes(current) != canonical_bytes(dep):
                applicable = False
            else:
                include(dep)
        if applicable:
            eligible.append((ref, record, events[0]))
    if len(eligible) != 1:
        _fail("Exactly one eligible admitted evidence claim required")
    ref, record, event = eligible[0]
    return ref, record, event, tuple(copy.deepcopy(transport[aid]) for aid in sorted(transport))


def _derive(
    base: str, witnesses: tuple[RevisionSnapshotWitness, ...], artifacts: ArtifactRepository
) -> EstablishVideoArtworkGroupChange:
    authenticated = authenticate_witnesses(base, witnesses)
    document = authenticated[base].document
    evidence, record, event, transport = _enumerate(base, authenticated, artifacts)
    source_ref = _descriptor(document, record["source"]["artifact_id"])
    if source_ref is None:
        _fail("Missing accepted source")
    source = artifacts.resolve_reference(source_ref)
    if source.kind != ArtifactKind.REFERENCE or source.media_type != "image/svg+xml":
        _fail("Construction requires accepted image/svg+xml ReferenceArtifact")
    triangles = _triangles(source.content)  # The actual Spec75 parser; no second grammar.
    subject = {"source_artifact_id": source.artifact_id, "subject_path": [0]}
    subject_key = {
        "ownership_profile_identity": EVIDENCE_PROFILE,
        "ownership_root_artifact_id": source.artifact_id,
        "canonical_source_subject_path": [0],
    }
    sid = "subject:multipart:" + _hash(
        {"identity_domain": DOMAIN, "source_subject_key": subject_key}
    )
    parts = [
        {
            "part_id": "part:multipart:"
            + _hash({"identity_domain": DOMAIN, "subject_id": sid, "source_part_key": key}),
            "part_key": key,
        }
        for key in PART_KEYS
    ]
    if canonical_bytes(record["subject"]) != canonical_bytes(
        {
            "subject_id": sid,
            "ownership_root_artifact_id": source.artifact_id,
            "canonical_source_subject_path": [0],
        }
    ) or canonical_bytes(record["parts"]) != canonical_bytes(parts):
        _fail("Source subject/parts disagree with admitted evidence")
    entities, operations, bindings, styles = [], [], [], []
    for key, triangle in zip(PART_KEYS, triangles, strict=True):
        allocation = {
            "authority_identity": AUTHORITY,
            "profile_identity": PROFILE,
            "subject": subject,
            "part_key": key,
        }
        eid = "entity:" + _hash({**allocation, "record_kind": "entity"})
        oid = "op:" + _hash({**allocation, "record_kind": "operation", "role": "geometry"})
        # Spec75's canonical lexemes are losslessly reconstructed from its integers.
        a, b, c = triangle
        path = f"M {a[0]} {a[1]} L {b[0]} {b[1]} L {c[0]} {c[1]} Z"
        params = {"d": path, "bounds": list(canonical_path_bounds(path))}
        entities.append({"id": eid, "name": key})
        operations.append({"id": oid, "type": "CreatePath", "inputs": {}, "parameters": params})
        bindings.append({"entity": eid, "property": "geometry", "slot": f"{oid}.geometry"})
        styles.append(
            {
                "entity": eid,
                "fill": "#000000",
                "stroke": "none",
                "stroke_width": 1.0,
                "opacity": 1.0,
            }
        )
    fragment = AppendSceneFragmentChange(
        tuple(entities),
        tuple(operations),
        tuple(bindings),
        tuple(e["id"] for e in entities),
        tuple(styles),
    )
    geometry_document = copy.deepcopy(document)
    fragment.apply(geometry_document)
    evaluator = Evaluator(geometry_document)
    bounds = []
    for operation in operations:
        evaluator.evaluate(operation["id"])
        outputs = evaluator.runtime[operation["id"]].outputs
        if outputs is None:
            _fail("Constructed geometry did not evaluate")
        measured = list(_geometry_bounds(outputs["geometry"].payload))
        if measured != operation["parameters"]["bounds"]:
            _fail("Constructed path bounds disagree")
        bounds.append(measured)
    provenance = {"authority_identity": AUTHORITY, "profile_identity": PROFILE}
    common = {
        "authority_identity": AUTHORITY,
        "profile_identity": PROFILE,
        "source_base_revision_id": base,
        "source_base_document_hash": authenticated[base].revision.document_hash,
        "subject": subject,
        "source_references": [evidence, source_ref],
        "fragment": asdict(fragment),
    }
    construction = artifacts.import_bytes(
        canonical_bytes(
            {
                "schema_version": "svm-group-construction-manifest-0.1",
                **common,
                "parameters": {},
                "member_bounds": bounds,
            }
        ),
        media_type=MANIFEST_MEDIA,
        kind=ArtifactKind.DERIVED,
        provenance=provenance,
    )
    members = sorted(e["id"] for e in entities)
    group = {
        "id": "group:" + _hash({**provenance, "members": members}),
        "kind": "explicit-group",
        "members": members,
        "provenance": {
            "type": ORIGIN,
            **provenance,
            "construction_artifact_id": construction.artifact_id,
        },
        "transform": {
            "translate": [0, 0],
            "rotation_degrees": 0,
            "scale": 1,
            "origin": [
                _canonical_scene_number(
                    (min(b[i] for b in bounds) + max(b[i + 2] for b in bounds)) / 2
                )
                for i in (0, 1)
            ],
        },
    }
    receipt = artifacts.import_bytes(
        canonical_bytes(
            {
                "schema_version": RECEIPT_SCHEMA,
                **common,
                "evidence": {
                    "reference": evidence,
                    "admission": {
                        "base_revision_id": event.base_revision_id,
                        "transition_hash": event.transition_hash,
                    },
                    "claim_key": record["claim_key"],
                    "subject_id": sid,
                    "parts": record["parts"],
                    "universe": record["occurrences"],
                    "membership": record["membership"],
                },
                "construction_reference": construction.document_reference(),
                "group": group,
                "representation_claim": None,
            }
        ),
        media_type=RECEIPT_MEDIA,
        kind=ArtifactKind.DERIVED,
        provenance=provenance,
    )
    change = EstablishVideoArtworkGroupChange(
        base,
        copy.deepcopy(document),
        copy.deepcopy(witnesses),
        PROFILE,
        copy.deepcopy(evidence),
        fragment,
        group,
        (*transport, construction.document_reference(), receipt.document_reference()),
    )
    change.apply(copy.deepcopy(document))
    return change


def verify_change(
    change: EstablishVideoArtworkGroupChange, resolved: dict[str, ArtifactSnapshot]
) -> None:
    if (
        change.profile_identity != PROFILE
        or type(change.fragment) is not AppendSceneFragmentChange
        or change.fragment.references
    ):
        _fail("Unknown construction profile or fragment type")
    authenticated = authenticate_witnesses(change.source_revision_id, change.witnesses)
    if canonical_bytes(authenticated[change.source_revision_id].document) != canonical_bytes(
        change.base_document_snapshot
    ):
        _fail("Construction base snapshot mismatch")
    scratch = ArtifactStore()
    for ref in change.references:
        actual = resolved[ref["id"]]
        if canonical_bytes(actual.document_reference()) != canonical_bytes(ref):
            _fail("Construction transport descriptor mismatch")
        scratch.import_bytes(
            actual.content,
            media_type=actual.media_type,
            kind=actual.kind,
            provenance=actual.provenance,
            locator=actual.descriptor.locator,
        )
    expected = _derive(change.source_revision_id, change.witnesses, scratch)
    if canonical_bytes(asdict(expected)) != canonical_bytes(asdict(change)):
        _fail("Construction output/transport does not reproduce")
    for ref in expected.references[-2:]:
        actual, wanted = resolved[ref["id"]], scratch.resolve_reference(ref)
        if actual.content != wanted.content or canonical_bytes(
            actual.document_reference()
        ) != canonical_bytes(ref):
            _fail("Construction manifest/receipt does not reproduce")


class VideoArtworkConstructionAdapter:
    adapter_id = "adapter:video-artwork-construction"

    def propose(
        self,
        request: AdapterRequest,
        artifacts: ArtifactRepository,
        *,
        witnesses: tuple[RevisionSnapshotWitness, ...],
    ) -> Proposal:
        if request.options or request.artifact_ids or request.scope not in {(), ("document",)}:
            _fail("Construction accepts document scope and no selectors/options")
        authenticated = authenticate_witnesses(request.base_revision_id, witnesses)
        if canonical_bytes(authenticated[request.base_revision_id].document) != canonical_bytes(
            request.document
        ):
            _fail("Request base snapshot mismatch")
        change = _derive(request.base_revision_id, witnesses, artifacts)
        digest = _hash(asdict(change))
        return Proposal(
            f"proposal:video-artwork:{digest}",
            request.base_revision_id,
            GeneratorProvenance(self.adapter_id, "0.1", "svm", PROFILE),
            Transaction(
                f"transaction:video-artwork:{digest}", (change,), "Establish video artwork Group"
            ),
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
            preview=ProposalPreview(
                proposed_render_stack=tuple(request.document["presentation"]["render_stack"])
                + change.fragment.render_entries,
                group_definitions=(
                    ConstructionGroupDefinitionPreview(
                        change.group["id"],
                        tuple(change.group["members"]),
                        "explicit-group",
                        copy.deepcopy(change.group["provenance"]),
                        copy.deepcopy(change.group["transform"]),
                    ),
                ),
            ),
        )
