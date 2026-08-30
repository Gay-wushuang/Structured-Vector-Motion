from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class PolicyDefinitionError(ValueError):
    pass


class PolicyEnforcementError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChangeIntent:
    action: str
    target: str
    parameter: str | None = None


def validate_policy_definitions(document: dict[str, Any]) -> None:
    constraint_ids: set[str] = set()
    for constraint in document.get("constraints", []):
        _require_keys(
            constraint,
            {"id", "type", "operation", "parameter"},
            "PreserveParameter constraint",
        )
        if constraint["type"] != "PreserveParameter":
            raise PolicyDefinitionError(f"Unsupported constraint type {constraint['type']!r}")
        _require_unique_id(constraint["id"], "constraint:", constraint_ids)
        if not _operation_exists(document, constraint["operation"]):
            raise PolicyDefinitionError(
                f"Constraint references missing operation {constraint['operation']}"
            )
        if not isinstance(constraint["parameter"], str) or not constraint["parameter"]:
            raise PolicyDefinitionError("Constraint parameter must be a non-empty string")
        operation = next(
            operation
            for operation in document["construction"]["operations"]
            if operation["id"] == constraint["operation"]
        )
        if constraint["parameter"] not in operation.get("parameters", {}):
            raise PolicyDefinitionError(
                f"Constraint references missing parameter "
                f"{constraint['operation']}.{constraint['parameter']}"
            )

    permission_ids: set[str] = set()
    for permission in document.get("edit_permissions", []):
        _require_keys(
            permission,
            {"id", "actor", "effect", "actions", "targets"},
            "Edit Permission",
        )
        _require_unique_id(permission["id"], "permission:", permission_ids)
        if not isinstance(permission["actor"], str) or not permission["actor"]:
            raise PolicyDefinitionError("Edit Permission actor must be a non-empty string")
        if permission["effect"] != "deny":
            raise PolicyDefinitionError("v0.1 Edit Permission effect must be deny")
        actions = permission["actions"]
        if (
            not isinstance(actions, list)
            or not actions
            or any(
                action
                not in {
                    "set_parameter",
                    "split_entity",
                    "import_scene",
                    "reconcile_scene",
                    "attach_analysis",
                    "promote_components",
                }
                for action in actions
            )
        ):
            raise PolicyDefinitionError("Edit Permission contains unsupported actions")
        targets = permission["targets"]
        if (
            not isinstance(targets, list)
            or not targets
            or any(not isinstance(target, str) or not target for target in targets)
        ):
            raise PolicyDefinitionError("Edit Permission targets must be non-empty strings")
        known_targets = (
            {"document"}
            | {entity["id"] for entity in document["entities"]}
            | {operation["id"] for operation in document["construction"]["operations"]}
        )
        missing_targets = sorted(
            target for target in targets if target != "*" and target not in known_targets
        )
        if missing_targets:
            raise PolicyDefinitionError(
                f"Edit Permission references missing targets {missing_targets}"
            )


def enforce_transaction_policies(document: dict[str, Any], actor: str, transaction: Any) -> None:
    if not document.get("constraints") and not document.get("edit_permissions"):
        return
    intents = tuple(
        intent for change in transaction.changes for intent in _intents_for_change(change)
    )

    for constraint in document.get("constraints", []):
        if _reconciliation_changes_constraint(document, transaction, constraint):
            raise PolicyEnforcementError(
                f"Constraint {constraint['id']} preserves "
                f"{constraint['operation']}.{constraint['parameter']}"
            )
        for intent in intents:
            if (
                constraint["type"] == "PreserveParameter"
                and intent.action == "set_parameter"
                and intent.target == constraint["operation"]
                and intent.parameter == constraint["parameter"]
            ):
                raise PolicyEnforcementError(
                    f"Constraint {constraint['id']} preserves {intent.target}.{intent.parameter}"
                )

    for permission in document.get("edit_permissions", []):
        if permission["actor"] not in {"*", actor}:
            continue
        for intent in intents:
            if intent.action in permission["actions"] and (
                "*" in permission["targets"] or intent.target in permission["targets"]
            ):
                raise PolicyEnforcementError(
                    f"Edit Permission {permission['id']} denies {actor} "
                    f"from {intent.action} on {intent.target}"
                )


def _intents_for_change(change: Any) -> tuple[ChangeIntent, ...]:
    from .change_authority import change_authority

    authority = change_authority(change)
    if authority is None:
        raise PolicyEnforcementError(
            f"Cannot enforce policies for unsupported Change {type(change).__name__}"
        )
    return tuple(ChangeIntent(*intent) for intent in authority.intent_resolver(change))


def _reconciliation_changes_constraint(
    document: dict[str, Any], transaction: Any, constraint: dict[str, Any]
) -> bool:
    operation_id = constraint["operation"]
    parameter = constraint["parameter"]
    old_operation = next(
        operation
        for operation in document["construction"]["operations"]
        if operation["id"] == operation_id
    )
    for change in transaction.changes:
        owned = getattr(change, "owned_operation_ids", ())
        if operation_id not in owned:
            continue
        new_operation = next(
            (
                operation
                for operation in getattr(change, "operations", ())
                if operation["id"] == operation_id
            ),
            None,
        )
        if new_operation is None:
            return True
        return old_operation.get("parameters", {}).get(parameter) != new_operation.get(
            "parameters", {}
        ).get(parameter)
    return False


def _require_keys(value: Any, expected: set[str], context: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise PolicyDefinitionError(f"{context} must contain exactly {sorted(expected)}")


def _require_unique_id(value: Any, prefix: str, seen: set[str]) -> None:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise PolicyDefinitionError(f"Policy ID must start with {prefix}")
    if value in seen:
        raise PolicyDefinitionError(f"Duplicate policy ID {value}")
    seen.add(value)


def _operation_exists(document: dict[str, Any], operation_id: Any) -> bool:
    return isinstance(operation_id, str) and operation_id in {
        operation["id"] for operation in document["construction"]["operations"]
    }
