from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .anchored_regeneration import AnchoredRegenerationContract
from .artifacts import ArtifactResolver
from .evaluator import DocumentError, canonical_bytes
from .proposals import AdapterRequest, GeneratorProvenance, Proposal
from .revisions import SetOperationParameterChange, Transaction

DETERMINISTIC_PROVIDER_IDENTITY = "svm-deterministic-proposal-provider@0.1"
DETERMINISTIC_PROVIDER_ACTOR = "adapter:editor-deterministic-regenerator"


@dataclass(frozen=True)
class ProposalCandidate:
    candidate_id: str
    proposal: Proposal


class AnchoredProposalProvider(Protocol):
    """Replaceable capability that proposes candidate futures without authority to accept."""

    def generate(
        self,
        request: AdapterRequest,
        contract: AnchoredRegenerationContract,
        artifacts: ArtifactResolver | None = None,
    ) -> tuple[ProposalCandidate, ...]: ...


class DeterministicProposalProvider:
    """Fixture provider proving the generator boundary without a model dependency."""

    def generate(
        self,
        request: AdapterRequest,
        contract: AnchoredRegenerationContract,
        artifacts: ArtifactResolver | None = None,
    ) -> tuple[ProposalCandidate, ...]:
        del artifacts
        if request.base_revision_id != contract.base_revision_id:
            raise DocumentError("Proposal request and anchored contract bases must match")
        scope = tuple(request.scope)
        if not scope or len(scope) != len(set(scope)) or not set(scope) <= {"cx", "cy"}:
            raise DocumentError("Deterministic provider supports unique highlight cx/cy scope")
        variants = self._candidate_variants(scope, request.document)
        candidates = []
        for label, values in variants:
            changes = tuple(
                SetOperationParameterChange("op:eye-highlight", parameter, value)
                for parameter, value in values
            )
            identity = {
                "identity": DETERMINISTIC_PROVIDER_IDENTITY,
                "base_revision_id": request.base_revision_id,
                "contract": asdict(contract),
                "candidate": label,
                "values": list(values),
            }
            digest = hashlib.sha256(canonical_bytes(identity)).hexdigest()
            candidates.append(
                ProposalCandidate(
                    candidate_id=label,
                    proposal=Proposal(
                        proposal_id=f"proposal:editor-anchored:{digest}",
                        base_revision_id=request.base_revision_id,
                        generator=GeneratorProvenance(
                            adapter_id=DETERMINISTIC_PROVIDER_ACTOR,
                            adapter_version="0.1",
                            engine="deterministic-fixture",
                            engine_version=DETERMINISTIC_PROVIDER_IDENTITY,
                        ),
                        transaction=Transaction(
                            transaction_id=f"transaction:editor-anchored:{digest}",
                            changes=changes,
                            message=f"Editor anchored candidate {label}",
                        ),
                        notes="Deterministic Editor Vertical Slice 05 candidate",
                    ),
                )
            )
        return tuple(candidates)

    @staticmethod
    def _candidate_variants(
        scope: tuple[str, ...], document: dict[str, Any]
    ) -> tuple[tuple[str, tuple[tuple[str, float], ...]], ...]:
        operation = next(
            (
                item
                for item in document["construction"]["operations"]
                if item["id"] == "op:eye-highlight"
            ),
            None,
        )
        if operation is None:
            raise DocumentError("Deterministic provider requires op:eye-highlight")
        current_x = float(operation["parameters"]["cx"])
        current_y = float(operation["parameters"]["cy"])
        if set(scope) == {"cx", "cy"}:
            return (
                ("A", (("cx", current_x + 0.04),)),
                ("B", (("cy", current_y - 0.03),)),
                ("C", (("cx", current_x + 0.08), ("cy", current_y - 0.05))),
            )
        parameter = scope[0]
        base = current_x if parameter == "cx" else current_y
        offsets = (0.04, 0.06, 0.08) if parameter == "cx" else (-0.02, -0.03, -0.05)
        return tuple(
            (label, ((parameter, base + offset),))
            for label, offset in zip(("A", "B", "C"), offsets, strict=True)
        )
