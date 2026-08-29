from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol

from .artifacts import ArtifactError, ArtifactResolver
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
class Proposal:
    proposal_id: str
    base_revision_id: str
    generator: GeneratorProvenance
    transaction: Transaction
    report: EvaluationReport = field(default_factory=EvaluationReport)
    preview_artifacts: tuple[PreviewArtifact, ...] = ()
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
        self._verify_artifacts(proposal, artifacts)
        document = store.get_document(proposal.base_revision_id)
        try:
            enforce_transaction_policies(
                document, proposal.generator.adapter_id, proposal.transaction
            )
        except PolicyEnforcementError as exc:
            raise ProposalPolicyError(str(exc)) from exc
        return store.commit(proposal.base_revision_id, proposal.transaction)

    @staticmethod
    def _verify_artifacts(proposal: Proposal, artifacts: ArtifactResolver | None) -> None:
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
            return
        if artifacts is None:
            raise ProposalArtifactError("Proposal acceptance requires an Artifact resolver")
        try:
            for reference in references:
                artifacts.resolve_reference(reference)
        except ArtifactError as exc:
            raise ProposalArtifactError(str(exc)) from exc
