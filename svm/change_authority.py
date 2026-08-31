from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .artifacts import ArtifactSnapshot
from .evaluator import canonical_bytes
from .revisions import (
    AppendReferencesChange,
    AppendSceneFragmentChange,
    ImportLayeredSceneChange,
    ImportRasterLayerEvidenceChange,
    PromoteComponentsChange,
    PromotedComponent,
    ReplaceSceneFragmentChange,
    SetKeyframeValueChange,
    SetOperationParameterChange,
    SplitEntityChange,
)

ArtifactVerifier = Callable[[Any, dict[str, ArtifactSnapshot]], None]
Intent = tuple[str, str, str | None]
IntentResolver = Callable[[Any], tuple[Intent, ...]]


@dataclass(frozen=True)
class ChangeAuthority:
    change_type: type[Any]
    actions: frozenset[str]
    intent_resolver: IntentResolver
    artifact_verifier: ArtifactVerifier | None = None


def _verify_layered(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    from .adapters.layerpeeler_output import verify_import_layered_scene_change

    verify_import_layered_scene_change(change, resolved)


def _verify_raster_layers(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    from .adapters.layerd_output import verify_import_raster_layer_evidence_change

    verify_import_raster_layer_evidence_change(change, resolved)


def _verify_promotion(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    if len(change.references) != 1:
        raise ValueError("Component promotion requires exactly one resolved analysis Artifact")
    artifact_id = change.references[0].get("id")
    if not isinstance(artifact_id, str) or artifact_id not in resolved:
        raise ValueError("Component promotion analysis Artifact was not resolved")
    snapshot = resolved[artifact_id]
    try:
        payload = json.loads(snapshot.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Component promotion analysis Artifact is not valid UTF-8 JSON") from exc
    if (
        not isinstance(payload, dict)
        or canonical_bytes(payload) != snapshot.content
        or payload.get("schema_version") != "svm-component-analysis-0.2"
        or not isinstance(payload.get("components"), list)
    ):
        raise ValueError("Component promotion requires canonical component-analysis v0.2")
    candidates: dict[str, dict[str, Any]] = {}
    for candidate in payload["components"]:
        if not isinstance(candidate, dict):
            raise ValueError("Component-analysis candidate is invalid")
        candidate_id = candidate.get("candidate_id")
        component_digest = candidate.get("component_digest")
        if not isinstance(candidate_id, str) or not isinstance(component_digest, str):
            raise ValueError("Component-analysis candidate identity is invalid")
        if candidate_id in candidates:
            raise ValueError("Component-analysis candidate IDs must be unique")
        candidates[candidate_id] = candidate
    for component in change.components:
        if type(component) is not PromotedComponent:
            raise ValueError("Component promotion accepts only PromotedComponent records")
        if component.artifact_id != snapshot.artifact_id:
            raise ValueError("Promoted component Artifact does not match resolved analysis")
        candidate = candidates.get(component.candidate_id)
        if candidate is None:
            raise ValueError(f"Promoted candidate {component.candidate_id} is absent from analysis")
        if component.component_digest != candidate.get("component_digest"):
            raise ValueError(
                f"Promoted candidate {component.candidate_id} digest does not match analysis"
            )
        if tuple(candidate.get("bounds", ())) != component.bounds:
            raise ValueError(
                f"Promoted candidate {component.candidate_id} bounds do not match analysis"
            )


def _single(action: str) -> IntentResolver:
    return lambda change: ((action, "document", None),)


def _set_parameter(change: Any) -> tuple[Intent, ...]:
    return (("set_parameter", change.operation_id, change.parameter),)


def _set_keyframe_value(change: Any) -> tuple[Intent, ...]:
    return (("set_keyframe_value", change.track_id, change.keyframe_id),)


def _replace_scene(change: Any) -> tuple[Intent, ...]:
    return (("reconcile_scene", "document", None),) + tuple(
        ("reconcile_scene", entity_id, None) for entity_id in change.existing_entity_ids
    )


def _split_entity(change: Any) -> tuple[Intent, ...]:
    return (("split_entity", change.source_entity_id, None),)


CHANGE_AUTHORITIES = {
    authority.change_type: authority
    for authority in (
        ChangeAuthority(SetOperationParameterChange, frozenset({"set_parameter"}), _set_parameter),
        ChangeAuthority(
            SetKeyframeValueChange, frozenset({"set_keyframe_value"}), _set_keyframe_value
        ),
        ChangeAuthority(
            AppendSceneFragmentChange, frozenset({"import_scene"}), _single("import_scene")
        ),
        ChangeAuthority(
            AppendReferencesChange, frozenset({"attach_analysis"}), _single("attach_analysis")
        ),
        ChangeAuthority(
            PromoteComponentsChange,
            frozenset({"promote_components"}),
            _single("promote_components"),
            _verify_promotion,
        ),
        ChangeAuthority(ReplaceSceneFragmentChange, frozenset({"reconcile_scene"}), _replace_scene),
        ChangeAuthority(SplitEntityChange, frozenset({"split_entity"}), _split_entity),
        ChangeAuthority(
            ImportLayeredSceneChange,
            frozenset({"import_scene"}),
            _single("import_scene"),
            _verify_layered,
        ),
        ChangeAuthority(
            ImportRasterLayerEvidenceChange,
            frozenset({"import_scene"}),
            _single("import_scene"),
            _verify_raster_layers,
        ),
    )
}


def change_authority(change: Any) -> ChangeAuthority | None:
    return CHANGE_AUTHORITIES.get(type(change))


def known_change_actions() -> frozenset[str]:
    return frozenset(
        action for authority in CHANGE_AUTHORITIES.values() for action in authority.actions
    )


def resolve_transaction_intents(transaction: Any) -> tuple[Intent, ...]:
    """Derive actual impact only from registered executable Change semantics."""
    intents: list[Intent] = []
    for change in transaction.changes:
        authority = change_authority(change)
        if authority is None:
            raise ValueError(f"Unregistered Change type {type(change).__name__}")
        resolved = authority.intent_resolver(change)
        undeclared = {action for action, _target, _parameter in resolved} - authority.actions
        if undeclared:
            raise ValueError(
                f"ChangeAuthority for {type(change).__name__} emitted undeclared actions "
                f"{sorted(undeclared)}"
            )
        intents.extend(resolved)
    return tuple(intents)
