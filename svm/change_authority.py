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
    return (("set_keyframe_value", change.track_id, None),)


def _replace_scene(change: Any) -> tuple[Intent, ...]:
    return (("reconcile_scene", "document", None),) + tuple(
        ("reconcile_scene", entity_id, None) for entity_id in change.existing_entity_ids
    )


def _split_entity(change: Any) -> tuple[Intent, ...]:
    return (("split_entity", change.source_entity_id, None),)


CHANGE_AUTHORITIES = {
    authority.change_type: authority
    for authority in (
        ChangeAuthority(SetOperationParameterChange, _set_parameter),
        ChangeAuthority(SetKeyframeValueChange, _set_keyframe_value),
        ChangeAuthority(AppendSceneFragmentChange, _single("import_scene")),
        ChangeAuthority(AppendReferencesChange, _single("attach_analysis")),
        ChangeAuthority(PromoteComponentsChange, _single("promote_components"), _verify_promotion),
        ChangeAuthority(ReplaceSceneFragmentChange, _replace_scene),
        ChangeAuthority(SplitEntityChange, _split_entity),
        ChangeAuthority(ImportLayeredSceneChange, _single("import_scene"), _verify_layered),
        ChangeAuthority(
            ImportRasterLayerEvidenceChange,
            _single("import_scene"),
            _verify_raster_layers,
        ),
    )
}


def change_authority(change: Any) -> ChangeAuthority | None:
    return CHANGE_AUTHORITIES.get(type(change))
