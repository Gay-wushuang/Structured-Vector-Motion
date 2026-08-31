from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .anchored_regeneration import (
    AnchoredRegenerationContract,
    ImpactTarget,
    validate_contract_against_document,
)
from .artifacts import ArtifactResolver
from .evaluator import DocumentError, Evaluator, Quality, canonical_bytes
from .motion import MotionEvaluator, MotionRevisionDelta, canonical_motion_number
from .operations import get_operation_registry
from .proposal_generators import AnchoredProposalProvider, DeterministicProposalProvider
from .proposals import AdapterRequest, GeneratorProvenance, Proposal, ProposalAcceptor
from .renderers import SVGRenderer, SVGRenderOptions
from .revisions import (
    AddKeyframeChange,
    CreateTrackChange,
    RevisionStore,
    SetKeyframeValueChange,
    SetOperationParameterChange,
    Transaction,
)
from .scene import EvaluatedScene, build_evaluated_scene

EDITOR_IDENTITY = "svm-document-editor@0.4"
EDITOR_ACTOR = "editor:motion-timeline"
SUPPORTED_OPERATION_TYPES = frozenset({"CreateRectangle", "CreateEllipse"})


@dataclass(frozen=True)
class MotionEditTarget:
    track_id: str
    keyframe_id: str


class DocumentEditorSession:
    """Inspect a simple accepted Document and edit supported Motion Keyframes."""

    def __init__(
        self,
        document: dict[str, Any],
        proposal_provider: AnchoredProposalProvider | None = None,
        artifacts: ArtifactResolver | None = None,
    ) -> None:
        self._validate_editor_subset(document)
        self.store = RevisionStore.create(document, "Editor Vertical Slice 04 base")
        if self.store.head is None:
            raise DocumentError("Editor Revision Store did not create a head")
        self.base_revision_id = self.store.head
        self.proposal_provider = proposal_provider or DeterministicProposalProvider()
        self.artifacts = artifacts
        self._revision_labels = {self.store.head: "R0"}
        self.motion: MotionEvaluator | None = None
        self.static_evaluator: Evaluator | None = None
        self.static_scene: EvaluatedScene | None = None
        self._preview_motion: MotionEvaluator | None = None
        self._preview_value: int | float | None = None
        self._preview_target: MotionEditTarget | None = None
        self._preview_deltas: tuple[MotionRevisionDelta, ...] = ()
        self._transition_deltas: tuple[MotionRevisionDelta, ...] = ()
        self._anchored_contract: AnchoredRegenerationContract | None = None
        self._anchored_proposals: dict[str, Proposal] = {}
        self._anchored_preview_document: dict[str, Any] | None = None
        self._anchored_preview_id: str | None = None
        self._accepted_candidates: dict[str, str] = {}
        self.reference_ticks: tuple[int, ...] = ()
        self.view_box: tuple[float, float, float, float] = (-1, -1, 2, 2)
        self._load_runtime(self.store.get_document(self.store.head))

    @property
    def head(self) -> str:
        if self.store.head is None:
            raise DocumentError("Editor Revision Store has no head")
        return self.store.head

    @property
    def document(self) -> dict[str, Any]:
        if self.motion is not None:
            return self.motion.document
        if self.static_evaluator is None:
            raise DocumentError("Editor runtime is unavailable")
        return self.static_evaluator.document

    def state(self, tick: int) -> dict[str, Any]:
        if self._anchored_preview_document is not None:
            return self._serialize_anchored_preview(self._anchored_preview_document, tick)
        if self.motion is None:
            return self._serialize_static()
        runtime = self._preview_motion or self.motion
        return self._serialize_motion(runtime, tick, preview=self._preview_motion is not None)

    def preview(
        self, track_id: str, keyframe_id: str, value: int | float, tick: int
    ) -> dict[str, Any]:
        motion = self._require_motion()
        target = self._target(motion.document, track_id, keyframe_id)
        value = canonical_motion_number(value)
        current = self._keyframe_value(motion.document, target)
        if value == current:
            self.clear_preview()
            return self.state(tick)
        transaction = self._transaction(self.head, target, value, prefix="preview")
        preview_document = transaction.apply(self.store.get_document(self.head))
        self._preview_motion, self._preview_deltas = motion.transition_to_revision(preview_document)
        self._preview_target = target
        self._preview_value = value
        return self.state(tick)

    def clear_preview(self) -> None:
        self._preview_motion = None
        self._preview_target = None
        self._preview_value = None
        self._preview_deltas = ()
        self._anchored_preview_document = None
        self._anchored_preview_id = None

    def generate_anchored_candidates(
        self, scope_parameters: list[str], tick: int = 0
    ) -> dict[str, Any]:
        """Create deterministic pending Proposals from one immutable base Revision."""
        self._require_anchored_fixture()
        if not isinstance(scope_parameters, list) or not scope_parameters:
            raise DocumentError("Anchored regeneration requires a non-empty scope")
        if any(type(value) is not str for value in scope_parameters):
            raise DocumentError("Anchored regeneration scope must contain parameter names")
        scope = tuple(dict.fromkeys(scope_parameters))
        if len(scope) != len(scope_parameters) or not set(scope) <= {"cx", "cy"}:
            raise DocumentError("Anchored regeneration scope supports only highlight cx/cy")

        base_revision_id = self.head
        eye_frame = ImpactTarget("set_parameter", "op:eye-frame", "rx")
        contract = AnchoredRegenerationContract(
            base_revision_id=base_revision_id,
            anchor=(eye_frame,),
            intent=(eye_frame,),
            protection=(
                eye_frame,
                ImpactTarget("set_parameter", "op:unrelated", "x"),
            ),
            regeneration_scope=tuple(
                ImpactTarget("set_parameter", "op:eye-highlight", parameter) for parameter in scope
            ),
        )
        base_document = self.store.get_document(base_revision_id)
        validate_contract_against_document(contract, base_document)
        request = AdapterRequest(
            base_revision_id=base_revision_id,
            document=base_document,
            scope=scope,
            options={
                "protection": [target.__dict__ for target in contract.protection],
                "regeneration_scope": [target.__dict__ for target in contract.regeneration_scope],
            },
        )
        generated = self.proposal_provider.generate(request, contract, self.artifacts)
        if not generated:
            raise DocumentError("Proposal provider returned no anchored candidates")
        proposals = {candidate.candidate_id: candidate.proposal for candidate in generated}
        if len(proposals) != len(generated):
            raise DocumentError("Proposal provider candidate IDs must be unique")
        acceptor = ProposalAcceptor()
        for proposal in proposals.values():
            acceptor.validate_anchored(self.store, proposal, contract, self.artifacts)
        self._anchored_contract = contract
        self._anchored_proposals = proposals
        self.clear_preview()
        return self.state(tick)

    def clear_anchored_candidates(self, tick: int = 0) -> dict[str, Any]:
        self.clear_preview()
        self._anchored_contract = None
        self._anchored_proposals = {}
        return self.state(tick)

    def preview_anchored_candidate(self, candidate_id: str, tick: int = 0) -> dict[str, Any]:
        contract, proposal = self._anchored_candidate(candidate_id)
        preview_document = ProposalAcceptor().validate_anchored(
            self.store, proposal, contract, self.artifacts
        )
        self.clear_preview()
        self._anchored_preview_document = preview_document
        self._anchored_preview_id = candidate_id
        return self.state(tick)

    def accept_anchored_candidate(self, candidate_id: str, tick: int = 0) -> dict[str, Any]:
        contract, proposal = self._anchored_candidate(candidate_id)
        if any(
            accepted_id == candidate_id
            and self.store.revisions[revision_id].parent_ids == (contract.base_revision_id,)
            for revision_id, accepted_id in self._accepted_candidates.items()
        ):
            raise DocumentError(f"Anchored candidate {candidate_id} is already accepted")
        revision = ProposalAcceptor().accept_anchored(
            self.store, proposal, contract, self.artifacts
        )
        if revision.revision_id not in self._revision_labels:
            self._revision_labels[revision.revision_id] = f"R{len(self._revision_labels)}"
        self._accepted_candidates[revision.revision_id] = candidate_id
        self.clear_preview()
        self._transition_deltas = ()
        self._load_runtime(self.store.get_document(revision.revision_id))
        return self.state(tick)

    def commit(
        self, track_id: str, keyframe_id: str, value: int | float, tick: int
    ) -> dict[str, Any]:
        motion = self._require_motion()
        target = self._target(motion.document, track_id, keyframe_id)
        value = canonical_motion_number(value)
        transaction = self._transaction(self.head, target, value, prefix="commit")
        digest = transaction.transaction_id.rsplit(":", 1)[-1]
        proposal = Proposal(
            proposal_id=f"proposal:motion-editor:{digest}",
            base_revision_id=self.head,
            generator=GeneratorProvenance(
                adapter_id=EDITOR_ACTOR,
                adapter_version="0.4",
                engine="svm-core",
                engine_version=EDITOR_IDENTITY,
            ),
            transaction=transaction,
            notes="Explicit local Editor Keyframe commit",
        )
        revision = ProposalAcceptor().accept(self.store, proposal)
        self.motion, self._transition_deltas = motion.transition_to_revision(
            self.store.get_document(revision.revision_id)
        )
        self._revision_labels[revision.revision_id] = f"R{len(self._revision_labels)}"
        self.clear_preview()
        return self.state(tick)

    def checkout_parent(self, tick: int) -> dict[str, Any]:
        revision = self.store.revisions[self.head]
        if not revision.parent_ids:
            raise DocumentError("Initial Editor Revision has no parent")
        document = self.store.checkout(revision.parent_ids[0])
        self.clear_preview()
        self._transition_deltas = ()
        self._load_runtime(document)
        return self.state(tick)

    def create_track(
        self,
        operation_id: str,
        parameter: str,
        ticks_per_second: int,
        tick: int = 0,
    ) -> dict[str, Any]:
        if tick != 0:
            raise DocumentError("Editor Motion authoring creates the initial Keyframe at tick 0")
        operation = next(
            (
                item
                for item in self.document["construction"]["operations"]
                if item["id"] == operation_id
            ),
            None,
        )
        if operation is None or parameter not in operation.get("parameters", {}):
            raise DocumentError(f"Missing authoring target {operation_id}.{parameter}")
        value = canonical_motion_number(operation["parameters"][parameter])
        identity = self._authoring_identity(operation_id, parameter)
        track_id = f"track:editor-{identity}"
        keyframe_id = self._keyframe_identity(track_id, tick)
        changes = (
            CreateTrackChange(track_id, operation_id, parameter, ticks_per_second),
            AddKeyframeChange(track_id, keyframe_id, tick, value),
        )
        return self._commit_structural_authoring(
            changes,
            tick,
            "create-track",
            {
                "operation_id": operation_id,
                "parameter": parameter,
                "ticks_per_second": ticks_per_second,
                "track_id": track_id,
                "keyframe_id": keyframe_id,
                "tick": tick,
                "value": value,
            },
        )

    def add_keyframe(self, track_id: str, tick: int, value: int | float) -> dict[str, Any]:
        self._track(self.document, track_id)
        keyframe_id = self._keyframe_identity(track_id, tick)
        return self._commit_structural_authoring(
            (AddKeyframeChange(track_id, keyframe_id, tick, value),),
            tick,
            "add-keyframe",
            {"track_id": track_id, "keyframe_id": keyframe_id, "value": value},
        )

    def _commit_structural_authoring(
        self,
        changes: tuple[CreateTrackChange | AddKeyframeChange, ...],
        tick: int,
        prefix: str,
        identity_payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "identity": EDITOR_IDENTITY,
            "base_revision_id": self.head,
            **identity_payload,
        }
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        transaction = Transaction(
            f"transaction:motion-editor:{prefix}:{digest}",
            changes,
            "Author Motion from Editor",
        )
        proposal = Proposal(
            f"proposal:motion-editor:{digest}",
            self.head,
            GeneratorProvenance(
                EDITOR_ACTOR,
                "0.4",
                "svm-core",
                EDITOR_IDENTITY,
            ),
            transaction,
            notes="Explicit local Editor Motion authoring",
        )
        revision = ProposalAcceptor().accept(self.store, proposal)
        self._revision_labels[revision.revision_id] = f"R{len(self._revision_labels)}"
        self.clear_preview()
        self._transition_deltas = ()
        self._load_runtime(self.store.get_document(revision.revision_id))
        return self.state(tick)

    def _load_runtime(self, document: dict[str, Any]) -> None:
        tracks = document.get("animation", {}).get("content", [])
        if tracks:
            self.motion = MotionEvaluator(document)
            self.reference_ticks = self._reference_ticks(tracks)
            scenes = []
            for tick in self.reference_ticks:
                scenes.append(self.motion.evaluate(tick, Quality.FINAL).scene)
            self.view_box = self._scenes_view_box(scenes)
            self.static_evaluator = None
            self.static_scene = None
            return
        self.motion = None
        self.reference_ticks = ()
        self.static_evaluator = Evaluator(document)
        self.static_scene = build_evaluated_scene(document, self.static_evaluator, Quality.FINAL)
        self.view_box = self._scenes_view_box([self.static_scene])

    def _serialize_static(self) -> dict[str, Any]:
        if self.static_scene is None:
            raise DocumentError("Static Editor scene is unavailable")
        return self._base_payload(
            document=self.document,
            sampled_document=self.document,
            scene=self.static_scene,
            tick=0,
            seconds=Fraction(0),
            preview=False,
            cache=[],
            deltas=(),
        )

    def _serialize_anchored_preview(self, document: dict[str, Any], tick: int) -> dict[str, Any]:
        if tick != 0:
            raise DocumentError("Static anchored preview requires tick 0")
        evaluator = Evaluator(document)
        scene = build_evaluated_scene(document, evaluator, Quality.FINAL)
        return self._base_payload(
            document=document,
            sampled_document=document,
            scene=scene,
            tick=0,
            seconds=Fraction(0),
            preview=True,
            cache=[],
            deltas=(),
        )

    def _serialize_motion(
        self, runtime: MotionEvaluator, tick: int, *, preview: bool
    ) -> dict[str, Any]:
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            raise DocumentError("Editor tick must be a non-negative integer")
        before = set(runtime.frame_cache)
        frame = runtime.evaluate(tick, Quality.FINAL)
        sampled_document = runtime.sample_document(tick)
        after = set(runtime.frame_cache)
        deltas = self._preview_deltas if preview else self._transition_deltas
        invalidated = {
            value
            for delta in deltas
            for value in self.reference_ticks
            if value >= delta.interval.start_tick
            and (delta.interval.end_tick is None or value <= delta.interval.end_tick)
        }
        cache = []
        for value in self.reference_ticks:
            key = (value, Quality.FINAL)
            if key in before:
                status = "reused"
            elif key in after:
                status = "reevaluated"
            elif value in invalidated:
                status = "invalidated"
            else:
                status = "clean"
            cache.append({"tick": value, "status": status})
        return self._base_payload(
            document=runtime.document,
            sampled_document=sampled_document,
            scene=frame.scene,
            tick=tick,
            seconds=frame.seconds,
            preview=preview,
            cache=cache,
            deltas=deltas,
        )

    def _base_payload(
        self,
        *,
        document: dict[str, Any],
        sampled_document: dict[str, Any],
        scene: EvaluatedScene,
        tick: int,
        seconds: Fraction,
        preview: bool,
        cache: list[dict[str, Any]],
        deltas: tuple[MotionRevisionDelta, ...],
    ) -> dict[str, Any]:
        revision = self.store.revisions[self.head]
        tracks = copy.deepcopy(document.get("animation", {}).get("content", []))
        renderer = SVGRenderer(SVGRenderOptions(width=900, height=300, view_box=self.view_box))
        return {
            "editor_identity": EDITOR_IDENTITY,
            "document_id": document["document_id"],
            "revision": {
                "id": self.head,
                "label": self._revision_labels[self.head],
                "parent_ids": list(revision.parent_ids),
                "can_checkout_parent": bool(revision.parent_ids),
            },
            "preview": {
                "active": preview,
                "kind": "anchored"
                if self._anchored_preview_id is not None
                else ("motion" if preview else None),
                "base_revision_id": (
                    self._anchored_contract.base_revision_id
                    if self._anchored_preview_id is not None and self._anchored_contract is not None
                    else self.head
                ),
                "value": self._preview_value,
                "candidate_id": self._anchored_preview_id,
                "target": copy.deepcopy(
                    self._preview_target.__dict__ if self._preview_target is not None else None
                ),
            },
            "timebase": copy.deepcopy(document.get("animation", {}).get("timebase")),
            "structure": self._document_outline(document),
            "tracks": tracks,
            "frame": {
                "tick": tick,
                "seconds": {"numerator": seconds.numerator, "denominator": seconds.denominator},
                "effective_parameters": {
                    operation["id"]: copy.deepcopy(operation.get("parameters", {}))
                    for operation in sampled_document["construction"]["operations"]
                },
                "svg": renderer.render(scene),
            },
            "temporal_deltas": [
                {
                    "track_id": delta.track_id,
                    "keyframe_id": delta.keyframe_id,
                    "start_tick": delta.interval.start_tick,
                    "end_tick": delta.interval.end_tick,
                }
                for delta in deltas
            ],
            "cache": cache,
            "anchored_regeneration": self._anchored_payload(document),
            "revision_graph": self._revision_graph(),
        }

    def _anchored_payload(self, document: dict[str, Any]) -> dict[str, Any]:
        available = self._has_anchored_fixture(document)
        contract = self._anchored_contract
        candidates = []
        for candidate_id, proposal in self._anchored_proposals.items():
            impacts = [
                {
                    "operation": change.operation_id,
                    "parameter": change.parameter,
                    "value": change.value,
                }
                for change in proposal.transaction.changes
                if type(change) is SetOperationParameterChange
            ]
            accepted = next(
                (
                    revision_id
                    for revision_id, accepted_id in self._accepted_candidates.items()
                    if accepted_id == candidate_id
                    and contract is not None
                    and self.store.revisions[revision_id].parent_ids == (contract.base_revision_id,)
                ),
                None,
            )
            candidates.append(
                {
                    "id": candidate_id,
                    "proposal_id": proposal.proposal_id,
                    "impacts": impacts,
                    "accepted_revision_id": accepted,
                }
            )
        return {
            "available": available,
            "base_revision_id": contract.base_revision_id if contract is not None else None,
            "selected_candidate_id": self._anchored_preview_id,
            "scope": [impact.parameter for impact in contract.regeneration_scope]
            if contract is not None
            else [],
            "protection": [
                {"target": impact.target, "parameter": impact.parameter}
                for impact in contract.protection
            ]
            if contract is not None
            else [],
            "candidates": candidates,
        }

    def _revision_graph(self) -> list[dict[str, Any]]:
        return [
            {
                "id": revision_id,
                "label": self._revision_labels.get(revision_id, revision_id[:12]),
                "parent_ids": list(revision.parent_ids),
                "current": revision_id == self.head,
                "candidate_id": self._accepted_candidates.get(revision_id),
            }
            for revision_id, revision in self.store.revisions.items()
        ]

    def _anchored_candidate(
        self, candidate_id: str
    ) -> tuple[AnchoredRegenerationContract, Proposal]:
        if self._anchored_contract is None:
            raise DocumentError("Generate anchored candidates before preview or acceptance")
        proposal = self._anchored_proposals.get(candidate_id)
        if proposal is None:
            raise DocumentError(f"Unknown anchored candidate {candidate_id}")
        return self._anchored_contract, proposal

    def _require_anchored_fixture(self) -> None:
        if not self._has_anchored_fixture(self.document):
            raise DocumentError("This Document does not expose the Vertical Slice 04 anchor")

    @staticmethod
    def _has_anchored_fixture(document: dict[str, Any]) -> bool:
        operations = {
            operation.get("id"): operation
            for operation in document.get("construction", {}).get("operations", [])
        }
        return (
            operations.get("op:eye-frame", {}).get("type") == "CreateEllipse"
            and operations.get("op:eye-highlight", {}).get("type") == "CreateEllipse"
            and operations.get("op:unrelated", {}).get("type") == "CreateRectangle"
        )

    def _transaction(
        self,
        base_revision_id: str,
        target: MotionEditTarget,
        value: int | float,
        *,
        prefix: str,
    ) -> Transaction:
        payload = {
            "identity": EDITOR_IDENTITY,
            "base_revision_id": base_revision_id,
            "track_id": target.track_id,
            "keyframe_id": target.keyframe_id,
            "value": value,
        }
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        return Transaction(
            transaction_id=f"transaction:motion-editor:{prefix}:{digest}",
            changes=(SetKeyframeValueChange(target.track_id, target.keyframe_id, value),),
            message="Set Motion Keyframe from Editor",
        )

    def _authoring_identity(self, operation_id: str, parameter: str) -> str:
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "identity": EDITOR_IDENTITY,
                    "document_id": self.document["document_id"],
                    "operation_id": operation_id,
                    "parameter": parameter,
                }
            )
        ).hexdigest()
        return digest[:16]

    @staticmethod
    def _keyframe_identity(track_id: str, tick: int) -> str:
        digest = hashlib.sha256(
            canonical_bytes({"identity": EDITOR_IDENTITY, "track_id": track_id, "tick": tick})
        ).hexdigest()
        return f"keyframe:editor-{digest[:16]}"

    def _require_motion(self) -> MotionEvaluator:
        if self.motion is None:
            raise DocumentError("This Document has no editable Motion Track")
        return self.motion

    @classmethod
    def _target(cls, document: dict[str, Any], track_id: str, keyframe_id: str) -> MotionEditTarget:
        track = cls._track(document, track_id)
        if not any(keyframe["id"] == keyframe_id for keyframe in track["keyframes"]):
            raise DocumentError(f"Missing Keyframe {keyframe_id}")
        return MotionEditTarget(track_id, keyframe_id)

    @staticmethod
    def _track(document: dict[str, Any], track_id: str) -> dict[str, Any]:
        track = next(
            (
                item
                for item in document.get("animation", {}).get("content", [])
                if item["id"] == track_id
            ),
            None,
        )
        if track is None:
            raise DocumentError(f"Missing Animation Track {track_id}")
        return track

    @classmethod
    def _keyframe_value(cls, document: dict[str, Any], target: MotionEditTarget) -> int | float:
        track = cls._track(document, target.track_id)
        return next(
            keyframe["value"]
            for keyframe in track["keyframes"]
            if keyframe["id"] == target.keyframe_id
        )

    @staticmethod
    def _reference_ticks(tracks: list[dict[str, Any]]) -> tuple[int, ...]:
        ticks: set[int] = set()
        for track in tracks:
            track_ticks = [keyframe["tick"] for keyframe in track["keyframes"]]
            ticks.update(track_ticks)
            ticks.update(
                (left + right) // 2
                for left, right in zip(track_ticks, track_ticks[1:], strict=False)
            )
        return tuple(sorted(ticks))

    @staticmethod
    def _validate_editor_subset(document: dict[str, Any]) -> None:
        unsupported = sorted(
            {
                operation["type"]
                for operation in document.get("construction", {}).get("operations", [])
                if operation["type"] not in SUPPORTED_OPERATION_TYPES
            }
        )
        if unsupported:
            raise DocumentError(
                "Editor Vertical Slice 04 supports only CreateRectangle/CreateEllipse; "
                f"found {', '.join(unsupported)}"
            )

    @staticmethod
    def _scenes_view_box(scenes: list[EvaluatedScene]) -> tuple[float, float, float, float]:
        bounds: list[tuple[float, float, float, float]] = []
        for scene in scenes:
            for entity in scene.entities:
                geometry = entity.geometry
                if geometry["kind"] == "rectangle":
                    x = float(geometry["x"])
                    y = float(geometry["y"])
                    bounds.append(
                        (x, y, x + float(geometry["width"]), y + float(geometry["height"]))
                    )
                elif geometry["kind"] == "ellipse":
                    cx = float(geometry["cx"])
                    cy = float(geometry["cy"])
                    rx = float(geometry["rx"])
                    ry = float(geometry["ry"])
                    bounds.append((cx - rx, cy - ry, cx + rx, cy + ry))
                else:
                    raise DocumentError(
                        f"Editor Vertical Slice 04 cannot frame geometry {geometry['kind']!r}"
                    )
        if not bounds:
            return (-1, -1, 2, 2)
        min_x = min(value[0] for value in bounds)
        min_y = min(value[1] for value in bounds)
        max_x = max(value[2] for value in bounds)
        max_y = max(value[3] for value in bounds)
        width = max(max_x - min_x, 1e-6)
        height = max(max_y - min_y, 1e-6)
        padding = max(width, height) * 0.08
        return (min_x - padding, min_y - padding, width + 2 * padding, height + 2 * padding)

    @staticmethod
    def _document_outline(document: dict[str, Any]) -> list[dict[str, Any]]:
        registry = get_operation_registry(document["semantics_version"])
        operations = {
            operation["id"]: operation for operation in document["construction"]["operations"]
        }
        bindings = {
            binding["entity"]: binding
            for binding in document["construction"]["output_bindings"]
            if binding["property"] == "geometry"
        }
        styles = {style["entity"]: style for style in document["presentation"].get("styles", [])}
        render_stack = document["presentation"]["render_stack"]
        tracks = document.get("animation", {}).get("content", [])
        outline: list[dict[str, Any]] = []
        for entity in document["entities"]:
            binding = bindings.get(entity["id"])
            operation = None
            if binding is not None:
                operation_id = binding["slot"].rsplit(".", 1)[0]
                operation = operations.get(operation_id)
            operation_tracks = (
                [track["id"] for track in tracks if track["target"]["operation"] == operation["id"]]
                if operation is not None
                else []
            )
            outline.append(
                {
                    "id": entity["id"],
                    "name": entity["name"],
                    "render_index": (
                        render_stack.index(entity["id"]) if entity["id"] in render_stack else None
                    ),
                    "binding": copy.deepcopy(binding),
                    "operation": copy.deepcopy(operation),
                    "animatable_parameters": (
                        sorted(registry.animatable_parameters(operation))
                        if operation is not None
                        else []
                    ),
                    "style": copy.deepcopy(styles.get(entity["id"])),
                    "track_ids": operation_tracks,
                }
            )
        return outline


MotionEditorSession = DocumentEditorSession
