from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .artifacts import ArtifactError, ArtifactResolver, ArtifactSnapshot
from .evaluator import Quality, canonical_bytes
from .policies import PolicyEnforcementError, enforce_transaction_policies
from .revisions import (
    PromoteComponentsChange,
    PromotedComponent,
    Revision,
    RevisionStore,
    Transaction,
)


class ProposalConflictError(RuntimeError):
    pass


class ProposalPolicyError(RuntimeError):
    pass


class ProposalArtifactError(RuntimeError):
    pass


@runtime_checkable
class ArtifactBoundChange(Protocol):
    def verify_artifacts(self, resolved: dict[str, ArtifactSnapshot]) -> None: ...


@dataclass(frozen=True)
class GeneratorProvenance:
    adapter_id: str
    adapter_version: str
    engine: str
    engine_version: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationReport:
    metrics: dict[str, float] = field(default_factory=dict)
    constraint_violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreviewArtifact:
    artifact_id: str
    content_hash: str
    media_type: str
    uri: str | None = None


@dataclass(frozen=True)
class MatchScorePreview:
    iou: float
    centroid: float
    area: float
    contour: float
    composite: float


@dataclass(frozen=True)
class EntityDiffPreview:
    status: str
    entity_id: str | None
    proposed_entity_id: str | None
    match_score: MatchScorePreview | None = None
    before_bounds: tuple[float, float, float, float] | None = None
    after_bounds: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class StructuralCandidatePreview:
    candidate_id: str
    bounds: tuple[int, int, int, int]
    pixel_area: int
    centroid: tuple[float, float]
    component_digest: str


@dataclass(frozen=True)
class StructuralRelationPreview:
    relation_id: str
    relation_type: str
    status: str
    source: str
    target: str
    evidence_artifact_id: str


@dataclass(frozen=True)
class ProposalPreview:
    entity_diffs: tuple[EntityDiffPreview, ...] = ()
    proposed_render_stack: tuple[str, ...] = ()
    structural_candidates: tuple[StructuralCandidatePreview, ...] = ()
    structural_relations: tuple[StructuralRelationPreview, ...] = ()


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    base_revision_id: str
    generator: GeneratorProvenance
    transaction: Transaction
    report: EvaluationReport = field(default_factory=EvaluationReport)
    preview_artifacts: tuple[PreviewArtifact, ...] = ()
    preview: ProposalPreview | None = None
    required_artifact_ids: tuple[str, ...] = ()
    confidence: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class AdapterRequest:
    base_revision_id: str
    document: dict[str, Any]
    scope: tuple[str, ...]
    quality: Quality = Quality.PREVIEW
    artifact_ids: tuple[str, ...] = ()
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_store(
        cls,
        store: RevisionStore,
        revision_id: str,
        scope: tuple[str, ...],
        *,
        quality: Quality = Quality.PREVIEW,
        artifact_ids: tuple[str, ...] = (),
        options: dict[str, Any] | None = None,
    ) -> AdapterRequest:
        return cls(
            base_revision_id=revision_id,
            document=store.get_document(revision_id),
            scope=scope,
            quality=quality,
            artifact_ids=artifact_ids,
            options=copy.deepcopy(options or {}),
        )


class ProposalProvider(Protocol):
    def propose(self, request: AdapterRequest, artifacts: ArtifactResolver) -> Proposal: ...


class ProposalAcceptor:
    """Single authority that turns an accepted Proposal into a Revision."""

    def accept(
        self,
        store: RevisionStore,
        proposal: Proposal,
        artifacts: ArtifactResolver | None = None,
    ) -> Revision:
        if store.head != proposal.base_revision_id:
            raise ProposalConflictError(
                f"Proposal base {proposal.base_revision_id} does not match head {store.head}"
            )
        if proposal.report.constraint_violations:
            raise ProposalPolicyError("Proposal has unresolved constraint violations")
        resolved_artifacts = self._verify_artifacts(proposal, artifacts)
        self._verify_artifact_bound_changes(proposal, resolved_artifacts)
        document = store.get_document(proposal.base_revision_id)
        try:
            enforce_transaction_policies(
                document, proposal.generator.adapter_id, proposal.transaction
            )
        except PolicyEnforcementError as exc:
            raise ProposalPolicyError(str(exc)) from exc
        return store.commit(proposal.base_revision_id, proposal.transaction)

    @staticmethod
    def _verify_artifacts(
        proposal: Proposal, artifacts: ArtifactResolver | None
    ) -> dict[str, ArtifactSnapshot]:
        references = tuple(
            reference
            for change in proposal.transaction.changes
            for reference in getattr(change, "references", ())
        )
        referenced_ids = tuple(reference.get("id") for reference in references)
        required_ids = proposal.required_artifact_ids
        if len(required_ids) != len(set(required_ids)):
            raise ProposalArtifactError("Proposal required Artifact IDs must be unique")
        if set(referenced_ids) != set(required_ids):
            raise ProposalArtifactError(
                "Proposal required Artifact IDs do not match Transaction references"
            )
        if not required_ids:
            return {}
        if artifacts is None:
            raise ProposalArtifactError("Proposal acceptance requires an Artifact resolver")
        try:
            resolved: dict[str, ArtifactSnapshot] = {}
            for reference in references:
                snapshot = artifacts.resolve_reference(reference)
                resolved[snapshot.artifact_id] = snapshot
        except ArtifactError as exc:
            raise ProposalArtifactError(str(exc)) from exc
        return resolved

    @staticmethod
    def _verify_artifact_bound_changes(
        proposal: Proposal, resolved: dict[str, ArtifactSnapshot]
    ) -> None:
        from .adapters.layerpeeler_output import ImportLayeredSceneChange

        trusted_verifiers: dict[type[Any], Any] = {
            ImportLayeredSceneChange: lambda change: change.verify_artifacts(resolved),
        }
        for change in proposal.transaction.changes:
            entities = getattr(change, "entities", ())
            if any(isinstance(entity, dict) and "source_layer" in entity for entity in entities):
                raise ProposalArtifactError(
                    "source_layer is reserved for a trusted Artifact-bound Change"
                )
            verifier = trusted_verifiers.get(type(change))
            if verifier is not None:
                try:
                    verifier(change)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ProposalArtifactError(str(exc)) from exc
            elif isinstance(change, ArtifactBoundChange):
                raise ProposalArtifactError(
                    f"Unregistered Artifact-bound Change type {type(change).__name__}"
                )
            if not isinstance(change, PromoteComponentsChange):
                continue
            if len(change.references) != 1:
                raise ProposalArtifactError(
                    "Component promotion requires exactly one resolved analysis Artifact"
                )
            artifact_id = change.references[0].get("id")
            if not isinstance(artifact_id, str):
                raise ProposalArtifactError(
                    "Component promotion analysis reference requires an Artifact ID"
                )
            snapshot = resolved.get(artifact_id)
            if snapshot is None:
                raise ProposalArtifactError(
                    "Component promotion analysis Artifact was not resolved"
                )
            try:
                payload = json.loads(snapshot.content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProposalArtifactError(
                    "Component promotion analysis Artifact is not valid UTF-8 JSON"
                ) from exc
            if (
                not isinstance(payload, dict)
                or canonical_bytes(payload) != snapshot.content
                or payload.get("schema_version") != "svm-component-analysis-0.2"
                or not isinstance(payload.get("components"), list)
            ):
                raise ProposalArtifactError(
                    "Component promotion requires canonical component-analysis v0.2"
                )
            candidates: dict[str, dict[str, Any]] = {}
            for candidate in payload["components"]:
                if not isinstance(candidate, dict):
                    raise ProposalArtifactError("Component-analysis candidate is invalid")
                candidate_id = candidate.get("candidate_id")
                component_digest = candidate.get("component_digest")
                if not isinstance(candidate_id, str) or not isinstance(component_digest, str):
                    raise ProposalArtifactError("Component-analysis candidate identity is invalid")
                if candidate_id in candidates:
                    raise ProposalArtifactError("Component-analysis candidate IDs must be unique")
                candidates[candidate_id] = candidate
            for component in change.components:
                if type(component) is not PromotedComponent:
                    raise ProposalArtifactError(
                        "Component promotion accepts only PromotedComponent records"
                    )
                if component.artifact_id != snapshot.artifact_id:
                    raise ProposalArtifactError(
                        "Promoted component Artifact does not match resolved analysis"
                    )
                candidate = candidates.get(component.candidate_id)
                if candidate is None:
                    raise ProposalArtifactError(
                        f"Promoted candidate {component.candidate_id} is absent from analysis"
                    )
                if component.component_digest != candidate["component_digest"]:
                    raise ProposalArtifactError(
                        f"Promoted candidate {component.candidate_id} digest "
                        "does not match analysis"
                    )
                if tuple(candidate.get("bounds", ())) != component.bounds:
                    raise ProposalArtifactError(
                        f"Promoted candidate {component.candidate_id} bounds do not match analysis"
                    )
