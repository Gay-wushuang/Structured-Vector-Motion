"""Structured Vector Motion v0.1 reference core."""

from .artifacts import (
    ArtifactBlob,
    ArtifactDescriptor,
    ArtifactError,
    ArtifactKind,
    ArtifactResolver,
    ArtifactSnapshot,
    ArtifactStore,
)
from .backends import GeometryBackend, GeometryBackendError
from .evaluator import EvaluationState, Evaluator, Quality
from .operations import (
    OperationDefinition,
    OperationExecutionContext,
    OperationRegistry,
    OperationValidationError,
    ValueType,
    get_operation_registry,
)
from .proposals import (
    AdapterRequest,
    EvaluationReport,
    GeneratorProvenance,
    PreviewArtifact,
    Proposal,
    ProposalAcceptor,
    ProposalArtifactError,
    ProposalConflictError,
    ProposalPolicyError,
    ProposalProvider,
)
from .revisions import (
    AppendSceneFragmentChange,
    RevisionStore,
    SetOperationParameterChange,
    SplitEntityChange,
    SplitPart,
    Transaction,
)
from .scene import EvaluatedEntity, EvaluatedScene, EvaluatedStyle, build_evaluated_scene

__all__ = [
    "Evaluator",
    "ArtifactError",
    "ArtifactBlob",
    "ArtifactDescriptor",
    "ArtifactKind",
    "ArtifactResolver",
    "ArtifactSnapshot",
    "ArtifactStore",
    "GeometryBackend",
    "GeometryBackendError",
    "EvaluationState",
    "Quality",
    "OperationDefinition",
    "OperationExecutionContext",
    "OperationRegistry",
    "OperationValidationError",
    "ValueType",
    "get_operation_registry",
    "RevisionStore",
    "AppendSceneFragmentChange",
    "SetOperationParameterChange",
    "SplitEntityChange",
    "SplitPart",
    "Transaction",
    "EvaluatedEntity",
    "EvaluatedScene",
    "EvaluatedStyle",
    "build_evaluated_scene",
    "AdapterRequest",
    "EvaluationReport",
    "GeneratorProvenance",
    "PreviewArtifact",
    "Proposal",
    "ProposalAcceptor",
    "ProposalArtifactError",
    "ProposalConflictError",
    "ProposalPolicyError",
    "ProposalProvider",
]
