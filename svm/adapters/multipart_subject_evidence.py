"""Spec76's single closed-world ownership verifier and non-authoritative producer."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from typing import Any, NoReturn

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..authored_raster_production import POLICY as PRODUCTION_POLICY
from ..authored_raster_production import replay_snapshots, reproduce_source_snapshot
from ..evaluator import canonical_bytes
from ..multipart_witness import RevisionSnapshotWitness, ancestors, authenticate_witnesses
from ..proposals import AdapterRequest, GeneratorProvenance, PreviewArtifact, Proposal
from ..revisions import AttachMultipartSubjectEvidenceChange, Transaction
from ..video_ingestion import MANIFEST_MEDIA, verify_video_manifest
from .primitive_observation_assembly import MEDIA as P2B_MEDIA
from .raster_primitive_observation_proposal import MEDIA as P2A_MEDIA
from .temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2

PROFILE = "svm-authored-two-triangle-multipart-evidence@0.1"
SCHEMA = "svm-multipart-subject-evidence-0.1"
MEDIA = "application/vnd.svm.multipart-subject-evidence+json;version=0.1"
DOMAIN = "svm-multipart-subject-evidence@0.1"


class MultipartSubjectDiagnostic(ValueError):
    """A non-persisted outcome: never an evidence record or an accept-ready Proposal."""

    def __init__(self, status: str, reason: str):
        self.status = status
        self.reason_codes = (reason,)
        super().__init__(f"{status}: {reason}")


def _uncertain(reason: str) -> NoReturn:
    raise MultipartSubjectDiagnostic("UNCERTAIN", reason)


def _reject(reason: str) -> NoReturn:
    raise MultipartSubjectDiagnostic("REJECTED", reason)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def claim_key(record: dict[str, Any]) -> str:
    """Only call on independently reproduced facts, never as claim authentication."""
    return _hash(
        {
            "profile_identity": record["profile_identity"],
            "subject_id": record["subject"]["subject_id"],
            "parts": record["parts"],
            "universe": record["occurrences"],
            "membership": [
                {k: cell[k] for k in ("occurrence_id", "part_key", "observation_id")}
                for cell in record["membership"]
            ],
        }
    )


def _references(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    refs = {}
    for ref in document["references"]:
        if ref["id"] in refs and canonical_bytes(refs[ref["id"]]) != canonical_bytes(ref):
            _reject("FORGED_BASE_OR_DEPENDENCY")
        refs[ref["id"]] = ref
    return tuple(copy.deepcopy(refs[aid]) for aid in sorted(refs))


def _read(ref: dict[str, Any], artifacts: ArtifactRepository) -> dict[str, Any]:
    snapshot = artifacts.resolve_reference(ref)
    value = json.loads(snapshot.content)
    if type(value) is not dict:
        _reject("FORGED_BASE_OR_DEPENDENCY")
    return value


def _one(values: list[Any]) -> Any:
    if not values:
        _uncertain("INCOMPLETE_UNIVERSE")
    if len(values) != 1:
        _uncertain("AMBIGUOUS_CLOSURE")
    return values[0]


def _facts(
    base: str,
    witnesses: dict[str, RevisionSnapshotWitness],
    artifacts: ArtifactRepository,
    *,
    applicable_manifest: str | None = None,
) -> dict[str, Any]:
    document = witnesses[base].document
    references = _references(document)
    accepted = {r["id"]: r for r in references}
    sources = [
        r
        for r in references
        if r["media_type"] in {"image/svg+xml", "application/svg+xml"}
        and r["import_metadata"].get("artifact_kind") == ArtifactKind.REFERENCE
    ]
    if not sources:
        _uncertain("OWNERSHIP_UNPROVEN")
    source = _one(sources)
    produced = reproduce_source_snapshot(base, document, artifacts)
    expected_frames = {"artifact:" + hashlib.sha256(png).hexdigest() for png in produced.frames}
    all_manifests = [r for r in references if r["media_type"] == MANIFEST_MEDIA]
    manifests = []
    for ref in all_manifests:
        candidate = _read(ref, artifacts)
        closure = [
            candidate["source_video_reference"]["id"],
            *(o["raster_artifact_id"] for o in candidate["occurrences"]),
        ]
        if any(aid not in accepted for aid in closure):
            _uncertain("INCOMPLETE_UNIVERSE")
        # Applicability cannot be selected by unverified claimed frame hashes.
        verified = verify_video_manifest(artifacts, ref)
        if expected_frames.intersection(f.artifact_id for f in verified.frames):
            manifests.append(ref)
    if all_manifests and not manifests:
        _reject("PRODUCTION_PIXEL_MISMATCH")
    # Only an already authenticated historical claim may supply this internal
    # applicability target. Proposal requests never select a manifest or closure.
    if applicable_manifest is not None:
        manifests = [r for r in manifests if r["id"] == applicable_manifest]
    manifest = _one(manifests)
    data = _read(manifest, artifacts)
    occurrences = data["occurrences"]
    if len(occurrences) != 2 or data["source"]["frame_count"] != 2:
        _uncertain("INCOMPLETE_UNIVERSE")
    if len({o["occurrence_id"] for o in occurrences}) != 2:
        _reject("FORGED_BASE_OR_DEPENDENCY")
    video = data["source_video_reference"]
    if accepted.get(video["id"]) != video:
        _uncertain("INCOMPLETE_UNIVERSE")
    # Source revision choice is deterministic over the authenticated ancestry,
    # not a caller selector. Every candidate proves the same exact accepted source.
    eligible = []
    for rid in sorted(ancestors(base, witnesses)):
        refs = _references(witnesses[rid].document)
        if source in refs and not any(r["id"] == video["id"] for r in refs):
            svg = [
                r
                for r in refs
                if r["media_type"] in {"image/svg+xml", "application/svg+xml"}
                and r["import_metadata"].get("artifact_kind") == ArtifactKind.REFERENCE
            ]
            if svg == [source]:
                eligible.append(rid)
    if not eligible:
        _uncertain("OWNERSHIP_UNPROVEN")
    source_revision = eligible[0]
    p2a = []
    for ref in references:
        if ref["media_type"] == P2A_MEDIA:
            payload = _read(ref, artifacts)
            claimed = payload["occurrence_provenance"]
            declared = ref["import_metadata"].get("provenance", {})
            if manifest["id"] in (
                claimed.get("manifest_artifact_id"),
                declared.get("manifest_artifact_id"),
            ):
                p2a.append((ref, payload))
    ordered = []
    for occurrence in occurrences:
        ordered.append(
            _one(
                [
                    pair
                    for pair in p2a
                    if pair[1]["occurrence_provenance"]["occurrence_id"]
                    == occurrence["occurrence_id"]
                ]
            )
        )
    if len(p2a) != 2:
        _uncertain("AMBIGUOUS_CLOSURE")
    p2a_ids = tuple(pair[0]["id"] for pair in ordered)
    assemblies = []
    for ref in references:
        if ref["media_type"] == P2B_MEDIA:
            payload = _read(ref, artifacts)
            declared = ref["import_metadata"].get("provenance", {})
            if manifest["id"] in (
                payload.get("manifest_artifact_id"),
                declared.get("manifest_artifact_id"),
            ):
                assemblies.append((ref, payload))
    assembly, audit = _one(assemblies)
    if audit["source_p2a_evidence_artifact_ids"] != list(p2a_ids):
        _uncertain("INCOMPLETE_UNIVERSE")
    observation = accepted.get(audit["observation_artifact_id"])
    if observation is None:
        _uncertain("INCOMPLETE_UNIVERSE")
    applicable_observations = [
        r
        for r in references
        if r["media_type"] == OBSERVATION_MEDIA_TYPE_V2
        and r["import_metadata"].get("provenance", {}).get("manifest_artifact_id") == manifest["id"]
    ]
    if _one(applicable_observations) != observation:
        _uncertain("AMBIGUOUS_CLOSURE")
    dep_ids = [*p2a_ids, observation["id"], assembly["id"]]
    for _, payload in ordered:
        provenance = payload["occurrence_provenance"]
        dep_ids.extend(
            provenance[k]
            for k in ("analysis_artifact_id", "binary_mask_artifact_id", "source_png_artifact_id")
        )
    if any(aid not in accepted for aid in dep_ids):
        _uncertain("INCOMPLETE_UNIVERSE")
    if any(e["status"] != "SUPPORTED" for _, payload in ordered for e in payload["evaluations"]):
        _uncertain("MISSING_OBSERVATION")
    try:
        report, _ = replay_snapshots(
            base,
            document,
            source_revision,
            witnesses[source_revision].document,
            manifest["id"],
            (p2a_ids[0], p2a_ids[1]),
            observation["id"],
            assembly["id"],
            artifacts,
        )
    except ValueError as exc:
        raise MultipartSubjectDiagnostic("REJECTED", "PRODUCTION_PIXEL_MISMATCH") from exc
    subject_key = {
        "ownership_profile_identity": PROFILE,
        "ownership_root_artifact_id": source["id"],
        "canonical_source_subject_path": [0],
    }
    subject_id = "subject:multipart:" + _hash(
        {"identity_domain": DOMAIN, "source_subject_key": subject_key}
    )
    parts = [
        {
            "part_id": "part:multipart:"
            + _hash({"identity_domain": DOMAIN, "subject_id": subject_id, "source_part_key": key}),
            "part_key": key,
        }
        for key in ("part-a", "part-b")
    ]
    universe, membership = [], []
    for occurrence in report["occurrences"]:
        identity = {
            k: occurrence[k] for k in ("occurrence_id", "frame_index", "tick", "source_timestamp")
        }
        universe.append(identity)
        for part, matched in zip(parts, occurrence["parts"], strict=True):
            membership.append(
                {
                    "subject_id": subject_id,
                    **part,
                    **identity,
                    **{
                        k: matched[k]
                        for k in (
                            "component_id",
                            "evaluation_id",
                            "observation_id",
                            "contribution_artifact_id",
                        )
                    },
                    "full_canvas_label_identity": matched["contribution_artifact_id"].replace(
                        "artifact:", "sha256:"
                    ),
                }
            )
    if len({cell["observation_id"] for cell in membership}) != 4:
        _reject("OBSERVATION_REUSED")
    record = {
        "profile_identity": PROFILE,
        "source": {
            "artifact_id": source["id"],
            "content_hash": source["content_hash"],
            "media_type": source["media_type"],
            "source_revision_id": source_revision,
        },
        "subject": {
            "subject_id": subject_id,
            "ownership_root_artifact_id": source["id"],
            "canonical_source_subject_path": [0],
        },
        "parts": parts,
        "production_policy": PRODUCTION_POLICY,
        "video": {"artifact_id": video["id"], "content_hash": video["content_hash"]},
        "manifest": {"artifact_id": manifest["id"], "content_hash": manifest["content_hash"]},
        "occurrences": universe,
        "membership": membership,
        "dependencies": [accepted[aid] for aid in dict.fromkeys(dep_ids)],
    }
    record["claim_key"] = claim_key(record)
    return record


def _compare_claims(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    if claim_key(candidate) == claim_key(existing):
        return True
    overlap = {c["observation_id"] for c in candidate["membership"]} & {
        c["observation_id"] for c in existing["membership"]
    }
    if overlap:
        _reject(
            "INCOMPATIBLE_SUPPORTED_CLAIM"
            if candidate["subject"] != existing["subject"]
            else "OBSERVATION_REUSED"
        )
    return False


def _derive(
    base: str,
    witnesses: dict[str, RevisionSnapshotWitness],
    artifacts: ArtifactRepository,
    cache: dict[str, tuple[dict[str, Any] | None, dict[str, Any] | None]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if base in cache:
        return cache[base]
    facts = _facts(base, witnesses, artifacts)
    refs = _references(witnesses[base].document)
    current = {r["id"]: r for r in refs}
    applicable, equivalent = [], []
    for ref in refs:
        if ref["media_type"] != MEDIA:
            continue
        admissions = [
            event
            for rid in ancestors(base, witnesses)
            for event in getattr(witnesses[rid].revision, "admissions", ())
            if event.artifact_reference == ref
        ]
        if not admissions:
            continue  # Legacy/unproven bytes remain data, never admitted ownership.
        stored = _read(ref, artifacts)
        if stored.get("profile_identity") != PROFILE or stored.get("schema_version") != SCHEMA:
            _reject("UNKNOWN_PROFILE")
        if "status" in stored or "judgment" in stored:
            _reject("SELF_ATTESTED_STATUS")
        oldbase = stored["base"]["revision_id"]
        if not any(event.base_revision_id == oldbase for event in admissions):
            _reject("FORGED_BASE_OR_DEPENDENCY")
        if oldbase == base:
            _reject("FORGED_BASE_OR_DEPENDENCY")
        if oldbase not in ancestors(base, witnesses):
            continue  # Historical claim from another branch is not currently applicable.
        oldrefs = {r["id"]: r for r in _references(witnesses[oldbase].document)}
        required = [r["id"] for r in stored["dependencies"]]
        required += [stored[k]["artifact_id"] for k in ("source", "video", "manifest")]
        if any(aid not in oldrefs or current.get(aid) != oldrefs[aid] for aid in required):
            continue  # Immutable old claim remains historical; do not rebase it.
        # Authenticate the entire original record against its hash-linked historical
        # base, including its old competing-claim audit. Never trust a stored key.
        original, reused = _derive(oldbase, witnesses, artifacts, cache)
        if (
            reused is not None
            or original is None
            or canonical_bytes(original) != canonical_bytes(stored)
        ):
            _reject("FORGED_BASE_OR_DEPENDENCY")
        snapshot = artifacts.resolve_reference(ref)
        if snapshot.kind != ArtifactKind.DERIVED or snapshot.provenance != {
            "profile_identity": PROFILE
        }:
            _reject("FORGED_BASE_OR_DEPENDENCY")
        # Reproduce this claim's own complete current closure, including conflicting
        # P2A/P2B candidates, before treating it as applicable (even when disjoint).
        try:
            current_claim = (
                facts
                if original["manifest"] == facts["manifest"]
                else _facts(
                    base,
                    witnesses,
                    artifacts,
                    applicable_manifest=original["manifest"]["artifact_id"],
                )
            )
        except MultipartSubjectDiagnostic:
            continue
        if (
            claim_key(original) != claim_key(current_claim)
            or original["dependencies"] != current_claim["dependencies"]
        ):
            continue
        applicable.append(ref["id"])
        if _compare_claims(facts, original):
            equivalent.append(ref)
    if equivalent:
        result = (None, equivalent[0])
    else:
        # Only the NEW path constructs an admission record/base commitment.
        facts["schema_version"] = SCHEMA
        facts["base"] = {
            "revision_id": base,
            "document_hash": witnesses[base].revision.document_hash,
        }
        facts["competing_claims"] = {
            "claim_artifact_ids": applicable,
            "disposition": "NO_COMPETING_CLAIM",
        }
        result = (facts, None)
    cache[base] = result
    return result


def derive(
    base: str, witnesses: tuple[RevisionSnapshotWitness, ...], artifacts: ArtifactRepository
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    authenticated = authenticate_witnesses(base, witnesses)
    return _derive(base, authenticated, artifacts, {})


def verify_change(
    change: AttachMultipartSubjectEvidenceChange, resolved: dict[str, ArtifactSnapshot]
) -> None:
    if change.profile_identity != PROFILE:
        _reject("UNKNOWN_PROFILE")
    authenticated = authenticate_witnesses(change.source_revision_id, change.witnesses)
    base_document = authenticated[change.source_revision_id].document
    if canonical_bytes(base_document) != canonical_bytes(change.base_document_snapshot):
        _reject("FORGED_BASE_OR_DEPENDENCY")
    expected_refs = _references(base_document)
    if canonical_bytes(change.source_references) != canonical_bytes(expected_refs):
        _reject("FORGED_BASE_OR_DEPENDENCY")
    scratch = ArtifactStore()
    for ref in change.references:
        actual = resolved[ref["id"]]
        if canonical_bytes(actual.document_reference()) != canonical_bytes(ref):
            _reject("FORGED_BASE_OR_DEPENDENCY")
        scratch.import_bytes(
            actual.content,
            media_type=actual.media_type,
            kind=actual.kind,
            provenance=actual.provenance,
            locator=actual.descriptor.locator,
        )
    record, reuse = _derive(change.source_revision_id, authenticated, scratch, {})
    if reuse is not None:
        if canonical_bytes(reuse) != canonical_bytes(change.evidence_reference):
            _reject("FORGED_BASE_OR_DEPENDENCY")
        return
    actual = scratch.resolve_reference(change.evidence_reference)
    claimed = json.loads(actual.content)
    if claimed.get("profile_identity") != PROFILE or claimed.get("schema_version") != SCHEMA:
        _reject("UNKNOWN_PROFILE")
    if "status" in claimed or "judgment" in claimed:
        _reject("SELF_ATTESTED_STATUS")
    claimed_observations = [cell["observation_id"] for cell in claimed["membership"]]
    if len(set(claimed_observations)) != len(claimed_observations):
        _reject("OBSERVATION_REUSED")
    if (
        actual.content != canonical_bytes(record)
        or actual.media_type != MEDIA
        or actual.kind != ArtifactKind.DERIVED
        or actual.provenance != {"profile_identity": PROFILE}
    ):
        _reject("FORGED_BASE_OR_DEPENDENCY")


class MultipartSubjectEvidenceAdapter:
    adapter_id = "adapter:multipart-subject-evidence"

    def propose(
        self,
        request: AdapterRequest,
        artifacts: ArtifactRepository,
        *,
        witnesses: tuple[RevisionSnapshotWitness, ...],
    ) -> Proposal:
        if request.options or request.artifact_ids or request.scope not in {(), ("document",)}:
            _reject("FORGED_BASE_OR_DEPENDENCY")
        authenticated = authenticate_witnesses(request.base_revision_id, witnesses)
        if canonical_bytes(request.document) != canonical_bytes(
            authenticated[request.base_revision_id].document
        ):
            _reject("FORGED_BASE_OR_DEPENDENCY")
        record, reuse = _derive(request.base_revision_id, authenticated, artifacts, {})
        if reuse is None:
            artifact = artifacts.import_bytes(
                canonical_bytes(record),
                media_type=MEDIA,
                kind=ArtifactKind.DERIVED,
                provenance={"profile_identity": PROFILE},
            )
            reference = artifact.document_reference()
        else:
            reference = reuse
        change = AttachMultipartSubjectEvidenceChange(
            request.base_revision_id,
            copy.deepcopy(request.document),
            copy.deepcopy(witnesses),
            PROFILE,
            _references(request.document),
            reference,
        )
        digest = _hash(asdict(change))
        return Proposal(
            f"proposal:multipart:{digest}",
            request.base_revision_id,
            GeneratorProvenance(self.adapter_id, "0.1", "svm", PROFILE),
            Transaction(
                f"transaction:multipart:{digest}",
                (change,),
                "Attach verified multipart ownership evidence",
            ),
            preview_artifacts=(PreviewArtifact(reference["id"], reference["content_hash"], MEDIA),),
            required_artifact_ids=tuple(r["id"] for r in change.references),
            notes="Reuse existing verified claim"
            if reuse is not None
            else "New verified bounded claim",
        )
