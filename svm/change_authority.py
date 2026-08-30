from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .artifacts import ArtifactSnapshot
from .revisions import (
    AppendReferencesChange,
    AppendSceneFragmentChange,
    ImportLayeredSceneChange,
    PromoteComponentsChange,
    ReplaceSceneFragmentChange,
    SetOperationParameterChange,
    SplitEntityChange,
)

ArtifactVerifier = Callable[[Any, dict[str, ArtifactSnapshot]], None]


@dataclass(frozen=True)
class ChangeAuthority:
    change_type: type[Any]
    policy_semantics: str
    artifact_verifier: ArtifactVerifier | None = None


def _verify_layered(change: Any, resolved: dict[str, ArtifactSnapshot]) -> None:
    from .adapters.layerpeeler_output import verify_import_layered_scene_change

    verify_import_layered_scene_change(change, resolved)


CHANGE_AUTHORITIES = {
    authority.change_type: authority
    for authority in (
        ChangeAuthority(SetOperationParameterChange, "set_parameter"),
        ChangeAuthority(AppendSceneFragmentChange, "import_scene"),
        ChangeAuthority(AppendReferencesChange, "attach_analysis"),
        ChangeAuthority(PromoteComponentsChange, "promote_components", None),
        ChangeAuthority(ReplaceSceneFragmentChange, "reconcile_scene"),
        ChangeAuthority(SplitEntityChange, "split_entity"),
        ChangeAuthority(ImportLayeredSceneChange, "import_scene", _verify_layered),
    )
}


def change_authority(change: Any) -> ChangeAuthority | None:
    return CHANGE_AUTHORITIES.get(type(change))
