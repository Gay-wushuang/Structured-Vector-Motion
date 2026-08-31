from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .change_authority import resolve_transaction_intents


class AnchoredRegenerationError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class ImpactTarget:
    """One exact ChangeAuthority intent eligible for deterministic comparison."""

    action: str
    target: str
    parameter: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action:
            raise AnchoredRegenerationError("Impact action must be a non-empty string")
        if not isinstance(self.target, str) or not self.target:
            raise AnchoredRegenerationError("Impact target must be a non-empty string")
        if self.parameter is not None and (
            not isinstance(self.parameter, str) or not self.parameter
        ):
            raise AnchoredRegenerationError("Impact parameter must be null or non-empty")


@dataclass(frozen=True)
class AnchoredRegenerationContract:
    base_revision_id: str
    anchor: tuple[ImpactTarget, ...]
    intent: tuple[ImpactTarget, ...]
    protection: tuple[ImpactTarget, ...]
    regeneration_scope: tuple[ImpactTarget, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.base_revision_id, str) or not self.base_revision_id.startswith(
            "revision:"
        ):
            raise AnchoredRegenerationError("Anchor requires a revision: base identity")
        for name in ("anchor", "intent", "protection", "regeneration_scope"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not values:
                raise AnchoredRegenerationError(f"Anchored regeneration {name} must be non-empty")
            if any(type(value) is not ImpactTarget for value in values):
                raise AnchoredRegenerationError(f"Anchored regeneration {name} must be typed")
            if len(values) != len(set(values)):
                raise AnchoredRegenerationError(f"Anchored regeneration {name} must be unique")
        if not set(self.anchor) <= set(self.protection):
            raise AnchoredRegenerationError("Every Anchor target must be protected")
        overlap = set(self.protection) & set(self.regeneration_scope)
        if overlap:
            raise AnchoredRegenerationError(
                f"Protected and allowed impacts overlap: {_describe(_sorted(overlap))}"
            )


def validate_anchored_proposal(
    contract: AnchoredRegenerationContract, proposal: Any
) -> tuple[ImpactTarget, ...]:
    if proposal.base_revision_id != contract.base_revision_id:
        raise AnchoredRegenerationError(
            "Proposal base Revision does not match Anchored Regeneration contract"
        )
    actual = tuple(
        ImpactTarget(action, target, parameter)
        for action, target, parameter in resolve_transaction_intents(proposal.transaction)
    )
    if not actual:
        raise AnchoredRegenerationError("Anchored Proposal must contain an actual Change impact")
    actual_set = set(actual)
    protected = actual_set & set(contract.protection)
    if protected:
        raise AnchoredRegenerationError(
            f"Proposal modifies protected impacts: {_describe(_sorted(protected))}"
        )
    outside = actual_set - set(contract.regeneration_scope)
    if outside:
        raise AnchoredRegenerationError(
            f"Proposal impacts are outside regeneration scope: {_describe(_sorted(outside))}"
        )
    return actual


def _describe(targets: list[ImpactTarget]) -> str:
    return ", ".join(
        f"{target.action}:{target.target}"
        + (f".{target.parameter}" if target.parameter is not None else "")
        for target in targets
    )


def _sorted(targets: set[ImpactTarget]) -> list[ImpactTarget]:
    return sorted(targets, key=lambda item: (item.action, item.target, item.parameter or ""))
