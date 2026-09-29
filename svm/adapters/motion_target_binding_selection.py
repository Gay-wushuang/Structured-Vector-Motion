"""P2D-A pure derivation only; no Proposal provider or acceptance authority."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from ..artifacts import ArtifactError, ArtifactKind, ArtifactResolver, ArtifactSnapshot
from ..document import _validate_group_transform
from ..evaluator import canonical_bytes
from ..revisions import TEMPORAL_IDENTITY_PROMOTION_IDENTITY
from . import primitive_observation_assembly as p2b
from . import raster_geometry_observations as raster
from . import raster_primitive_observation_proposal as p2a
from . import svg_geometry_observations as svg
from .temporal_correspondence import OBSERVATION_MEDIA_TYPE_V2, POLICY_IDENTITY
from .temporal_identity_selection import _read_r0

ADAPTER_ID = "adapter:motion-target-binding-selection"
ADAPTER_VERSION = "0.1"
POLICY = "svm-motion-target-binding-selection@0.1"
SCHEMA = "svm-motion-target-binding-selection-0.1"
MEDIA = "application/vnd.svm.motion-target-binding-selection+json;version=0.1"


class Reason(StrEnum):
    ALREADY_BOUND = "ALREADY_BOUND"
    GROUP_CONTENTION = "GROUP_CONTENTION"
    NO_ALLOWED_PATH = "NO_ALLOWED_PATH"
    UNPROVEN_RENDERED_ORIGIN = "UNPROVEN_RENDERED_ORIGIN"
    MISSING_ACCEPTED_REFERENCE = "MISSING_ACCEPTED_REFERENCE"
    INVALID_PROVENANCE = "INVALID_PROVENANCE"
    INVALID_ENDPOINT = "INVALID_ENDPOINT"
    NO_ELIGIBLE_GROUP = "NO_ELIGIBLE_GROUP"
    PARTIAL_PROVENANCE = "PARTIAL_PROVENANCE"
    CONTRADICTORY_PROVENANCE = "CONTRADICTORY_PROVENANCE"


class Abstention(StrEnum):
    GROUP_CONTENTION = "GROUP_CONTENTION"
    ZERO_SUPPORTED = "ZERO_SUPPORTED"


class MotionTargetBindingSelectionError(RuntimeError):
    """Malformed Document structure or unavailable/corrupt accepted artifact."""


class _Unresolved(ValueError):
    def __init__(self, reason: Reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SelectedPair:
    temporal_identity_id: str
    group_id: str


@dataclass(frozen=True)
class ExistingBinding:
    binding_id: str
    group_id: str


@dataclass(frozen=True)
class ProvenancePath:
    evidence_artifact_id: str | None = None
    observation_artifact_id: str | None = None
    tick: int | None = None
    observation_id: str | None = None
    producer_identity: str | None = None
    shape_id: str | None = None
    p2a_evidence_artifact_id: str | None = None
    analysis_artifact_id: str | None = None
    component_id: str | None = None
    component_digest: str | None = None
    entity_id: str | None = None
    group_id: str | None = None
    reason: Reason | None = None


@dataclass(frozen=True)
class IdentityEvaluation:
    temporal_identity_id: str
    status: str
    reason_codes: tuple[Reason, ...]
    paths: tuple[ProvenancePath, ...]
    existing_binding: ExistingBinding | None = None


@dataclass(frozen=True)
class SelectionCounts:
    total: int
    supported: int
    uncertain: int
    rejected: int
    selected: int


@dataclass(frozen=True)
class SelectionDerivation:
    evaluations: tuple[IdentityEvaluation, ...]
    selected_pairs: tuple[SelectedPair, ...]
    counts: SelectionCounts
    required_references: tuple[dict[str, Any], ...]
    abstention: Abstention | None


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _json(snapshot: ArtifactSnapshot) -> dict[str, Any]:
    value = json.loads(snapshot.content)
    if not isinstance(value, dict) or canonical_bytes(value) != snapshot.content:
        raise _Unresolved(Reason.INVALID_PROVENANCE)
    return value


def _records(document: dict[str, Any], field: str) -> list[dict[str, Any]]:
    values = document.get(field, [])
    if (
        not isinstance(values, list)
        or any(not isinstance(v, dict) or not isinstance(v.get("id"), str) for v in values)
        or len({v["id"] for v in values}) != len(values)
    ):
        raise MotionTargetBindingSelectionError(f"Invalid or duplicate {field}")
    return sorted(values, key=lambda v: v["id"])


class _Context:
    def __init__(self, document: dict[str, Any], artifacts: ArtifactResolver):
        self.artifacts = artifacts
        self.references = {r["id"]: r for r in _records(document, "references")}
        self.resolved: dict[str, ArtifactSnapshot] = {}
        self.closure: list[dict[str, Any]] = []
        self.entities = _records(document, "entities")
        self.groups = _records(document, "groups")
        self.group_for: dict[str, str] = {}
        for group in self.groups:
            if group.get("transform") is None:
                continue
            members = group.get("members")
            if (
                group.get("kind") != "explicit-group"
                or re.fullmatch(r"group:[0-9a-f]{64}", group["id"]) is None
                or not isinstance(members, list)
                or any(not isinstance(m, str) for m in members)
            ):
                raise MotionTargetBindingSelectionError("Invalid transformed Group")
            try:
                _validate_group_transform(group["transform"])
            except ValueError as exc:
                raise MotionTargetBindingSelectionError("Invalid Group transform") from exc
            for member in members:
                if member in self.group_for:
                    raise MotionTargetBindingSelectionError(
                        "Multiple transformed Groups for Entity"
                    )
                self.group_for[member] = group["id"]
        self.by_identity: dict[str, ExistingBinding] = {}
        self.by_group: dict[str, ExistingBinding] = {}
        for binding in _records(document, "motion_target_bindings"):
            try:
                identity_id = binding["temporal_identity_id"]
                group_id = binding["target"]["group_id"]
                if (
                    not isinstance(identity_id, str)
                    or not isinstance(group_id, str)
                    or binding["target"]["kind"] != "group"
                    or identity_id in self.by_identity
                    or group_id in self.by_group
                ):
                    raise ValueError("Invalid binding")
            except (KeyError, TypeError, ValueError) as exc:
                raise MotionTargetBindingSelectionError("Invalid existing binding state") from exc
            existing = ExistingBinding(binding["id"], group_id)
            self.by_identity[identity_id] = existing
            self.by_group[group_id] = existing

    def resolve(self, artifact_id: str) -> ArtifactSnapshot:
        if artifact_id not in self.references:
            raise _Unresolved(Reason.MISSING_ACCEPTED_REFERENCE)
        if artifact_id not in self.resolved:
            reference = self.references[artifact_id]
            try:
                snapshot = self.artifacts.resolve_reference(copy.deepcopy(reference))
                if snapshot.document_reference() != reference:
                    raise ArtifactError("Resolved descriptor differs from accepted reference")
            except (ArtifactError, KeyError, TypeError, ValueError) as exc:
                raise MotionTargetBindingSelectionError(
                    "Cannot verify required accepted artifact"
                ) from exc
            self.resolved[artifact_id] = snapshot
            self.closure.append(copy.deepcopy(reference))
        return self.resolved[artifact_id]

    def endpoint(
        self, path: ProvenancePath, entities: list[dict[str, Any]]
    ) -> list[ProvenancePath]:
        if not entities:
            return [replace(path, reason=Reason.INVALID_ENDPOINT)]
        return [
            replace(
                path,
                entity_id=e["id"],
                group_id=self.group_for.get(e["id"]),
                reason=None if e["id"] in self.group_for else Reason.NO_ELIGIBLE_GROUP,
            )
            for e in entities
        ]

    def component(self, path: ProvenancePath, lineage: dict[str, Any]) -> list[ProvenancePath]:
        aid, cid, digest = (
            lineage[k] for k in ("analysis_artifact_id", "component_id", "component_digest")
        )
        if any(not isinstance(v, str) for v in (aid, cid, digest)):
            raise _Unresolved(Reason.INVALID_PROVENANCE)
        path = replace(path, analysis_artifact_id=aid, component_id=cid, component_digest=digest)
        # The tuple is already recorded by a verified producer. Analysis pixels are not reopened.
        entities = [
            e
            for e in self.entities
            if isinstance(e.get("provenance"), dict)
            and e["provenance"].get("type") == "PromotedComponent"
            and (
                e["provenance"].get("artifact_id"),
                e["provenance"].get("candidate_id"),
                e["provenance"].get("component_digest"),
            )
            == (aid, cid, digest)
        ]
        return self.endpoint(path, entities)


def _p2b_lineage(
    ctx: _Context, snapshot: ArtifactSnapshot, path: ProvenancePath
) -> list[ProvenancePath]:
    provenance = snapshot.provenance
    if (
        provenance.get("adapter_id") != p2b.ADAPTER_ID
        or provenance.get("adapter_version") != p2b.ADAPTER_VERSION
    ):
        raise _Unresolved(Reason.INVALID_PROVENANCE)
    ids = provenance["source_p2a_evidence_artifact_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) != 2
        or any(not isinstance(i, str) for i in ids)
        or len(set(ids)) != 2
    ):
        raise _Unresolved(Reason.INVALID_PROVENANCE)
    matches = []
    missing = False
    for aid in ids:  # Recorded producer order, never ordinal correspondence.
        try:
            evidence = ctx.resolve(aid)
        except _Unresolved:
            missing = True
            continue
        payload = _json(evidence)
        if (
            evidence.kind != ArtifactKind.DERIVED
            or evidence.media_type != p2a.MEDIA
            or payload.get("schema_version") != p2a.SCHEMA
            or payload.get("policy_identity") != p2a.POLICY
            or payload.get("adapter_id") != p2a.ADAPTER_ID
            or payload.get("adapter_version") != p2a.ADAPTER_VERSION
        ):
            raise _Unresolved(Reason.INVALID_PROVENANCE)
        occurrence = payload["occurrence_provenance"]
        if (
            evidence.provenance != occurrence
            or occurrence["manifest_artifact_id"] != provenance["manifest_artifact_id"]
        ):
            raise _Unresolved(Reason.INVALID_PROVENANCE)
        for evaluation in payload["evaluations"]:
            if evaluation["status"] != "SUPPORTED":
                continue
            identity = {
                "policy_identity": p2b.POLICY,
                "adapter_id": p2b.ADAPTER_ID,
                "adapter_version": p2b.ADAPTER_VERSION,
                "source_p2a_evidence_artifact_id": aid,
                "p2a_candidate_id": evaluation["candidate_id"],
                "manifest_artifact_id": occurrence["manifest_artifact_id"],
                "occurrence_id": occurrence["occurrence_id"],
                "frame_index": occurrence["frame_index"],
                "tick": occurrence["tick"],
                "component_digest": evaluation["component_digest"],
            }
            if path.tick == occurrence[
                "tick"
            ] and path.observation_id == "observation:p2b:" + _hash(identity):
                expected = {
                    **occurrence,
                    "component_id": evaluation["component_id"],
                    "component_digest": evaluation["component_digest"],
                }
                if evaluation["provenance"] != expected:
                    raise _Unresolved(Reason.INVALID_PROVENANCE)
                matches.append((aid, evaluation["provenance"]))
    if missing:
        raise _Unresolved(Reason.MISSING_ACCEPTED_REFERENCE)
    if len(matches) != 1:
        raise _Unresolved(Reason.INVALID_PROVENANCE)
    aid, lineage = matches[0]
    return ctx.component(replace(path, p2a_evidence_artifact_id=aid), lineage)


def _raster_lineage(
    ctx: _Context, snapshot: ArtifactSnapshot, path: ProvenancePath
) -> list[ProvenancePath]:
    provenance = snapshot.provenance
    if provenance.get("geometry_observation_policy") != raster.POLICY_IDENTITY:
        raise _Unresolved(Reason.INVALID_PROVENANCE)
    matches = []
    for occurrence in provenance["source_occurrences"]:
        identity = {
            k: occurrence[k]
            for k in (
                "source_png_artifact_id",
                "tick",
                "component_id",
                "policy_identity",
                "analysis_policy",
            )
        }
        if (
            occurrence["policy_identity"] == raster.POLICY_IDENTITY
            and occurrence["tick"] == path.tick
            and path.observation_id == "observation:raster:" + _hash(identity)
        ):
            matches.append(occurrence)
    if len(matches) != 1:
        raise _Unresolved(Reason.INVALID_PROVENANCE)
    return ctx.component(path, matches[0])


def _svg_lineage(
    ctx: _Context, snapshot: ArtifactSnapshot, path: ProvenancePath
) -> list[ProvenancePath]:
    # Frozen SVG metadata does not distinguish rendered Entity selection from ordinary path IDs.
    # Never infer rendered origin from a coincidentally matching shape_id.
    raise _Unresolved(Reason.UNPROVEN_RENDERED_ORIGIN)


def _record(ctx: _Context, identity: dict[str, Any], record: Any) -> list[ProvenancePath]:
    path = ProvenancePath()
    try:
        if not isinstance(record, dict):
            raise _Unresolved(Reason.INVALID_PROVENANCE)
        if not isinstance(record.get("evidence_artifact_id"), str):
            raise _Unresolved(Reason.INVALID_PROVENANCE)
        path = replace(path, evidence_artifact_id=record["evidence_artifact_id"])
        evidence = ctx.resolve(record["evidence_artifact_id"])
        payload = _read_r0(evidence)
        candidates = [
            c for c in payload["candidates"] if c["inference_id"] == record["inference_id"]
        ]
        if (
            len(candidates) != 1
            or candidates[0]["status"] != "SUPPORTED"
            or candidates[0]["candidate_id"] != record["candidate_id"]
            or record["evidence_policy_identity"] != POLICY_IDENTITY
            or record["promotion_policy_identity"] != TEMPORAL_IDENTITY_PROMOTION_IDENTITY
        ):
            raise _Unresolved(Reason.INVALID_PROVENANCE)
        candidate = candidates[0]
        path = replace(path, observation_artifact_id=payload["source_artifact_id"])
        observation = ctx.resolve(payload["source_artifact_id"])
        if (
            observation.kind != ArtifactKind.REFERENCE
            or observation.media_type != OBSERVATION_MEDIA_TYPE_V2
        ):
            raise _Unresolved(Reason.NO_ALLOWED_PATH)
        observations = _json(observation)
        if observations.get("schema_version") != "svm-primitive-observations-0.2":
            raise _Unresolved(Reason.INVALID_PROVENANCE)
        producer = observation.provenance.get("producer_identity")
        path = replace(path, producer_identity=producer if isinstance(producer, str) else None)
        handler = {
            p2b.POLICY: _p2b_lineage,
            raster.POLICY_IDENTITY: _raster_lineage,
            svg.PRODUCER_IDENTITY: _svg_lineage,
            svg.OCCURRENCE_PRODUCER_IDENTITY: _svg_lineage,
        }.get(producer if isinstance(producer, str) else "")
        if handler is None:
            raise _Unresolved(Reason.NO_ALLOWED_PATH)
        results = []
        for side in ("source", "target"):
            endpoint = replace(
                path,
                tick=candidate[f"{side}_tick"],
                observation_id=candidate[f"{side}_observation_id"],
            )
            try:
                binding = {"tick": endpoint.tick, "observation_id": endpoint.observation_id}
                matches = [
                    p
                    for f in observations["frames"]
                    if f["tick"] == endpoint.tick
                    for p in f["primitives"]
                    if p["observation_id"] == endpoint.observation_id
                ]
                if binding not in identity["bindings"] or len(matches) != 1:
                    raise _Unresolved(Reason.INVALID_PROVENANCE)
                results.extend(handler(ctx, observation, endpoint))
            except (ValueError, KeyError, TypeError) as exc:
                reason = exc.reason if isinstance(exc, _Unresolved) else Reason.INVALID_PROVENANCE
                results.append(replace(endpoint, reason=reason))
        return results
    except (ValueError, KeyError, TypeError) as exc:
        reason = exc.reason if isinstance(exc, _Unresolved) else Reason.INVALID_PROVENANCE
        return [replace(path, reason=reason)]


def _evaluate(ctx: _Context, identity: dict[str, Any]) -> IdentityEvaluation:
    records = identity.get("provenance")
    paths = (
        tuple(p for r in records for p in _record(ctx, identity, r))
        if isinstance(records, list) and records
        else (ProvenancePath(reason=Reason.INVALID_PROVENANCE),)
    )
    existing = ctx.by_identity.get(identity["id"])
    if existing:
        return IdentityEvaluation(
            identity["id"], "REJECTED", (Reason.ALREADY_BOUND,), paths, existing
        )
    entities = {p.entity_id for p in paths if p.entity_id is not None}
    groups = {p.group_id for p in paths if p.group_id is not None}
    reasons = tuple(sorted({p.reason for p in paths if p.reason is not None}))
    if len(entities) > 1 or len(groups) > 1:
        status, reasons = "UNCERTAIN", (Reason.CONTRADICTORY_PROVENANCE,)
    elif groups and reasons:
        status, reasons = "UNCERTAIN", (Reason.PARTIAL_PROVENANCE,)
    elif not groups:
        status = "REJECTED"
    else:
        group_id = next(iter(groups))
        existing = ctx.by_group.get(group_id)
        status, reasons = ("REJECTED", (Reason.ALREADY_BOUND,)) if existing else ("SUPPORTED", ())
    return IdentityEvaluation(identity["id"], status, reasons, paths, existing)


def derive_motion_target_binding_selection(
    document: dict[str, Any], artifacts: ArtifactResolver
) -> SelectionDerivation:
    """Derive from base-shaped input; authentication/acceptance belongs to future P2D-B.

    Only exact accepted references are read. No artifacts or Document records are written.
    The same function is intended for proposal construction and authenticated-snapshot verification.
    """
    ctx = _Context(document, artifacts)
    evaluations = tuple(_evaluate(ctx, i) for i in _records(document, "temporal_identities"))
    candidates = [
        SelectedPair(e.temporal_identity_id, e.paths[0].group_id)
        for e in evaluations
        if e.status == "SUPPORTED" and e.paths[0].group_id is not None
    ]
    contested = {
        p.group_id for p in candidates if sum(q.group_id == p.group_id for q in candidates) > 1
    }
    if contested:
        contenders = {p.temporal_identity_id for p in candidates if p.group_id in contested}
        evaluations = tuple(
            replace(e, status="UNCERTAIN", reason_codes=(Reason.GROUP_CONTENTION,))
            if e.temporal_identity_id in contenders
            else e
            for e in evaluations
        )
        pairs: tuple[SelectedPair, ...] = ()
        abstention = Abstention.GROUP_CONTENTION
    else:
        pairs = tuple(candidates)
        abstention = None if pairs else Abstention.ZERO_SUPPORTED
    return SelectionDerivation(
        evaluations,
        pairs,
        SelectionCounts(
            total=len(evaluations),
            supported=sum(e.status == "SUPPORTED" for e in evaluations),
            uncertain=sum(e.status == "UNCERTAIN" for e in evaluations),
            rejected=sum(e.status == "REJECTED" for e in evaluations),
            selected=len(pairs),
        ),
        tuple(ctx.closure),
        abstention,
    )
