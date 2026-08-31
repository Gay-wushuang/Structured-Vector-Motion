from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol

from .anchored_regeneration import (
    AnchoredRegenerationContract,
    AnchoredRegenerationError,
    validate_anchored_proposal,
    validate_contract_against_document,
)
from .artifacts import ArtifactError, ArtifactResolver, ArtifactSnapshot
from .change_authority import change_authority
from .evaluator import Quality
from .policies import PolicyEnforcementError, enforce_transaction_policies
from .revisions import Revision, RevisionStore, Transaction


class ProposalConflictError(RuntimeError):
    pass


class ProposalPolicyError(RuntimeError):
    pass


class ProposalArtifactError(RuntimeError):
    pass


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
        return self._accept(store, proposal, artifacts, require_head=True)

    def validate(
        self,
        store: RevisionStore,
        proposal: Proposal,
        artifacts: ArtifactResolver | None = None,
    ) -> dict[str, Any]:
        """Run the complete ordinary acceptance authority without committing."""
        return self._validate(store, proposal, artifacts, require_head=True)

    def accept_anchored(
        self,
        store: RevisionStore,
        proposal: Proposal,
        contract: AnchoredRegenerationContract,
        artifacts: ArtifactResolver | None = None,
    ) -> Revision:
        """Accept a scoped Proposal as a child of its immutable Anchor base."""
        return self._accept(
            store,
            proposal,
            artifacts,
            require_head=False,
            anchored_contract=contract,
        )

    def validate_anchored(
        self,
        store: RevisionStore,
        proposal: Proposal,
        contract: AnchoredRegenerationContract,
        artifacts: ArtifactResolver | None = None,
    ) -> dict[str, Any]:
        """Run the complete anchored acceptance authority without committing."""
        return self._validate(
            store,
            proposal,
            artifacts,
            require_head=False,
            anchored_contract=contract,
        )

    def _accept(
        self,
        store: RevisionStore,
        proposal: Proposal,
        artifacts: ArtifactResolver | None,
        *,
        require_head: bool,
        anchored_contract: AnchoredRegenerationContract | None = None,
    ) -> Revision:
        self._validate(
            store,
            proposal,
            artifacts,
            require_head=require_head,
            anchored_contract=anchored_contract,
        )
        return store.commit(proposal.base_revision_id, proposal.transaction)

    def _validate(
        self,
        store: RevisionStore,
        proposal: Proposal,
        artifacts: ArtifactResolver | None,
        *,
        require_head: bool,
        anchored_contract: AnchoredRegenerationContract | None = None,
    ) -> dict[str, Any]:
        if proposal.base_revision_id not in store.revisions:
            raise ProposalConflictError(f"Missing Proposal base {proposal.base_revision_id}")
        if require_head and store.head != proposal.base_revision_id:
            raise ProposalConflictError(
                f"Proposal base {proposal.base_revision_id} does not match head {store.head}"
            )
        if proposal.report.constraint_violations:
            raise ProposalPolicyError("Proposal has unresolved constraint violations")
        self._verify_trusted_change_types(proposal)
        document = store.get_document(proposal.base_revision_id)
        if anchored_contract is not None:
            try:
                validate_contract_against_document(anchored_contract, document)
                validate_anchored_proposal(anchored_contract, proposal)
            except AnchoredRegenerationError as exc:
                raise ProposalPolicyError(str(exc)) from exc
        resolved_artifacts = self._verify_artifacts(proposal, artifacts)
        self._verify_artifact_bound_changes(proposal, resolved_artifacts)
        try:
            enforce_transaction_policies(
                document, proposal.generator.adapter_id, proposal.transaction
            )
        except PolicyEnforcementError as exc:
            raise ProposalPolicyError(str(exc)) from exc
        return proposal.transaction.apply(document)

    @staticmethod
    def _verify_trusted_change_types(proposal: Proposal) -> None:
        for change in proposal.transaction.changes:
            if change_authority(change) is None:
                raise ProposalPolicyError(f"Unregistered Change type {type(change).__name__}")

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
        for change in proposal.transaction.changes:
            entities = getattr(change, "entities", ())
            if any(isinstance(entity, dict) and "source_layer" in entity for entity in entities):
                raise ProposalArtifactError(
                    "source_layer is reserved for a trusted Artifact-bound Change"
                )
            authority = change_authority(change)
            verifier = authority.artifact_verifier if authority is not None else None
            if verifier is not None:
                try:
                    verifier(change, resolved)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ProposalArtifactError(str(exc)) from exc
