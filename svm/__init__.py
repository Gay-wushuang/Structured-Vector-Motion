"""Structured Vector Motion v0.1 reference core."""

from .artifacts import (
    ArtifactError,
    ArtifactKind,
    ArtifactResolver,
    ArtifactSnapshot,
    ArtifactStore,
)
from .evaluator import EvaluationState, Evaluator, Quality
from .operations import (
    OperationDefinition,
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
    "ArtifactKind",
    "ArtifactResolver",
    "ArtifactSnapshot",
    "ArtifactStore",
    "EvaluationState",
    "Quality",
    "OperationDefinition",
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
    "ProposalConflictError",
    "ProposalPolicyError",
    "ProposalProvider",
]
