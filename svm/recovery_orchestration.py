"""Thin production orchestration of the frozen Phase 1 recovery chain.

This module sequences existing production adapters only. It owns no inference:
no role discovery, no automatic component association, no camera estimation, no
raster tracking. Explicit component selectors, anchor/target identities and
Motion Target Bindings are configuration inputs, exactly as in the frozen
S11A/S11B/S11C path.

The sequence is the one already proven by the repository acceptance tests; this
module gives that sequence a production boundary so a demo, CLI or future
consumer does not have to reach into test helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .adapters import (
    CameraCompensatedMotionAdapter,
    GeometryTranslationTracksAdapter,
    MultiAnchorCameraConsensusAdapter,
    ObservedCameraSimilarityAdapter,
    ObservedCameraTracksAdapter,
    ObservedRotationTracksAdapter,
    ObservedScaleTracksAdapter,
    ObservedTranslationMotionAdapter,
    TemporalCorrespondenceAdapter,
    TemporalIdentityPromotionAdapter,
    TemporalMotionTargetBindingAdapter,
)
from .adapters.camera_consensus import MEASURED_POLICY
from .adapters.observed_similarity_motion import RasterObservedSimilarityMotionAdapter
from .adapters.opencv_analysis import OpenCVAnalysisAdapter
from .adapters.raster_geometry_observations import RasterGeometryObservationAdapter
from .adapters.temporal_identity_promotion import TemporalIdentityPromotionPreview
from .artifacts import ArtifactStore
from .proposals import AdapterRequest, Proposal, ProposalAcceptor
from .revisions import RevisionStore

CAMERA_TARGET = "presentation"


class RecoveryOrchestrationError(ValueError):
    """Raised when explicit recovery configuration is incomplete or inconsistent."""


@dataclass(frozen=True)
class RecoveryConfig:
    """Explicit recovery inputs. No field is inferred from pixels."""

    ticks: tuple[int, ...]
    ticks_per_second: int
    anchors: tuple[str, ...]
    targets: tuple[str, ...]
    groups: tuple[str, ...]
    selectors: dict[str, dict[str, str]]
    agreement_policy: str = MEASURED_POLICY

    def selector(self, tick: int, role: str) -> str:
        """Return the explicit component selector for one tick and role."""
        try:
            return self.selectors[str(tick)][role]
        except KeyError as exc:
            raise RecoveryOrchestrationError(
                f"Missing explicit selector for tick {tick} role {role}"
            ) from exc

    def validate(self) -> None:
        if len(self.ticks) < 2 or tuple(sorted(set(self.ticks))) != self.ticks:
            raise RecoveryOrchestrationError("Ticks must be increasing and unique")
        if self.ticks_per_second <= 0:
            raise RecoveryOrchestrationError("ticks_per_second must be positive")
        if not self.anchors or len(self.targets) != len(self.groups):
            raise RecoveryOrchestrationError(
                "Recovery requires anchors and one explicit group per target"
            )
        for tick in self.ticks:
            for role in (*self.anchors, *self.targets):
                self.selector(tick, role)


@dataclass
class RecoveryState:
    """Accepted intermediate evidence. Retained for provenance reporting."""

    store: RevisionStore
    artifacts: ArtifactStore
    analyses: list[str] = field(default_factory=list)
    lineages: dict[str, dict[str, Any]] = field(default_factory=dict)
    cameras: list[str] = field(default_factory=list)
    camera_consensus_id: str = ""
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)


def _head(store: RevisionStore) -> str:
    head = store.head
    if head is None:
        raise RecoveryOrchestrationError("Recovery requires an accepted Revision head")
    return head


def _preview(proposal: Proposal) -> Any:
    preview = proposal.preview
    if preview is None:
        raise RecoveryOrchestrationError("Accepted proposal produced no preview")
    return preview


def _request(
    store: RevisionStore,
    ids: tuple[str, ...] = (),
    options: dict[str, Any] | None = None,
) -> AdapterRequest:
    return AdapterRequest.from_store(
        store, _head(store), ("document",), artifact_ids=ids, options=options or {}
    )


def _accept(
    store: RevisionStore,
    artifacts: ArtifactStore,
    adapter: Any,
    ids: tuple[str, ...] = (),
    options: dict[str, Any] | None = None,
) -> Proposal:
    proposal = adapter.propose(_request(store, ids, options), artifacts)
    ProposalAcceptor().accept(store, proposal, artifacts)
    return proposal


def _payload(artifacts: ArtifactStore, proposal: Proposal) -> dict[str, Any]:
    return json.loads(artifacts.get(proposal.preview_artifacts[0].artifact_id).content)


def analyze_frames(
    store: RevisionStore, artifacts: ArtifactStore, frame_sources: tuple[bytes, ...]
) -> list[str]:
    """Import canonical raster frames and accept component analysis for each."""
    analyses = []
    for content in frame_sources:
        blob = artifacts.import_bytes(content, media_type="image/png")
        proposal = _accept(store, artifacts, OpenCVAnalysisAdapter(), (blob.artifact_id,))
        analyses.append(proposal.preview_artifacts[1].artifact_id)
    return analyses


def recover_role_lineage(
    store: RevisionStore,
    artifacts: ArtifactStore,
    analyses: list[str],
    role: str,
    config: RecoveryConfig,
) -> dict[str, Any]:
    """Build one independent pixel lineage for an explicit role."""
    geometries: list[str] = []
    correspondences: list[str] = []
    inferences: list[str] = []
    identity_id = ""
    for index in range(len(config.ticks) - 1):
        left, right = config.ticks[index], config.ticks[index + 1]
        proposal = RasterGeometryObservationAdapter().propose(
            _request(
                store,
                tuple(sorted({analyses[index], analyses[index + 1]})),
                {
                    "occurrences": [
                        {
                            "analysis_artifact_id": analyses[index],
                            "tick": left,
                            "component_id": config.selector(left, role),
                        },
                        {
                            "analysis_artifact_id": analyses[index + 1],
                            "tick": right,
                            "component_id": config.selector(right, role),
                        },
                    ]
                },
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, proposal, artifacts)
        geometry_id = proposal.preview_artifacts[0].artifact_id
        geometries.append(geometry_id)
        correspondence = _accept(store, artifacts, TemporalCorrespondenceAdapter(), (geometry_id,))
        correspondence_id = correspondence.preview_artifacts[0].artifact_id
        correspondences.append(correspondence_id)
        candidate = _payload(artifacts, correspondence)["candidates"][0]
        inferences.append(candidate["inference_id"])
        identity = _accept(
            store,
            artifacts,
            TemporalIdentityPromotionAdapter(),
            (correspondence_id,),
            {"inference_ids": [candidate["inference_id"]]},
        )
        identity_preview = _preview(identity)
        if not isinstance(identity_preview, TemporalIdentityPromotionPreview) or not (
            identity_preview.temporal_identities
        ):
            raise RecoveryOrchestrationError(
                "Identity promotion did not produce a stable temporal identity"
            )
        identity_id = identity_preview.temporal_identities[0].stable_identity_id
    options = {"temporal_identity_id": identity_id, "inference_ids": inferences}
    translation = _accept(
        store, artifacts, ObservedTranslationMotionAdapter(), tuple(correspondences), options
    )
    similarity = _accept(
        store,
        artifacts,
        RasterObservedSimilarityMotionAdapter(),
        (*geometries, *correspondences),
        options,
    )
    return {
        "geometry_ids": geometries,
        "correspondence_ids": correspondences,
        "identity_id": identity_id,
        "translation_id": translation.preview_artifacts[0].artifact_id,
        "similarity_id": similarity.preview_artifacts[0].artifact_id,
    }


def recover_scene(
    base_document: dict[str, Any],
    frame_sources: tuple[bytes, ...],
    config: RecoveryConfig,
) -> RecoveryState:
    """Run the frozen recovery chain up to accepted compensation/binding evidence."""
    config.validate()
    if len(frame_sources) != len(config.ticks):
        raise RecoveryOrchestrationError("One canonical raster frame is required per tick")
    store = RevisionStore.create(base_document)
    artifacts = ArtifactStore()
    state = RecoveryState(store=store, artifacts=artifacts)
    state.analyses = analyze_frames(store, artifacts, frame_sources)
    for role in (*config.anchors, *config.targets):
        state.lineages[role] = recover_role_lineage(store, artifacts, state.analyses, role, config)
        if role in config.anchors:
            anchor = _accept(
                store,
                artifacts,
                ObservedCameraSimilarityAdapter(),
                (state.lineages[role]["similarity_id"],),
                {"anchor_entity_id": role},
            )
            state.cameras.append(anchor.preview_artifacts[0].artifact_id)
    consensus = MultiAnchorCameraConsensusAdapter().propose(
        _request(
            store,
            tuple(state.cameras),
            {
                "anchor_entity_ids": list(config.anchors),
                "agreement_policy": config.agreement_policy,
            },
        ),
        artifacts,
    )
    ProposalAcceptor().accept(store, consensus, artifacts)
    state.camera_consensus_id = consensus.preview_artifacts[0].artifact_id
    for role, group in zip(config.targets, config.groups, strict=True):
        lineage = state.lineages[role]
        compensation = _accept(
            store,
            artifacts,
            CameraCompensatedMotionAdapter(),
            (
                state.camera_consensus_id,
                lineage["translation_id"],
                lineage["similarity_id"],
            ),
            {
                "anchor_entity_ids": list(config.anchors),
                "target_temporal_identity_id": lineage["identity_id"],
            },
        )
        binding = _accept(
            store,
            artifacts,
            TemporalMotionTargetBindingAdapter(),
            (),
            {"temporal_identity_id": lineage["identity_id"], "group_id": group},
        )
        binding_preview = _preview(binding)
        if not binding_preview.motion_target_bindings:
            raise RecoveryOrchestrationError("Target binding produced no Motion Target Binding")
        state.targets[role] = {
            "compensation": compensation,
            "evidence_id": compensation.preview_artifacts[1].artifact_id,
            "binding_id": binding_preview.motion_target_bindings[0].binding_id,
        }
    return state


def author_target_tracks(state: RecoveryState, role: str, config: RecoveryConfig) -> list[Proposal]:
    """Author the offered translation/rotation/scale Tracks for one explicit target."""
    target = state.targets[role]
    proposals = []
    for adapter in (
        GeometryTranslationTracksAdapter(),
        ObservedRotationTracksAdapter(),
        ObservedScaleTracksAdapter(),
    ):
        proposals.append(
            _accept(
                state.store,
                state.artifacts,
                adapter,
                (target["evidence_id"],),
                {
                    "motion_target_binding_id": target["binding_id"],
                    "ticks_per_second": config.ticks_per_second,
                },
            )
        )
    return proposals


def author_recovered_document(
    state: RecoveryState, config: RecoveryConfig
) -> tuple[dict[str, Any], list[Proposal]]:
    """Author all twelve Tracks: Target A, four Camera Tracks, Target B."""
    proposals = author_target_tracks(state, config.targets[0], config)
    proposals.append(
        _accept(
            state.store,
            state.artifacts,
            ObservedCameraTracksAdapter(),
            (state.camera_consensus_id,),
            {"camera_target": CAMERA_TARGET, "ticks_per_second": config.ticks_per_second},
        )
    )
    for role in config.targets[1:]:
        proposals.extend(author_target_tracks(state, role, config))
    document = state.store.get_document(_head(state.store))
    return document, proposals
