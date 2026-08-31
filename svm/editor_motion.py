from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .evaluator import DocumentError, Quality, canonical_bytes
from .motion import MotionEvaluator, MotionRevisionDelta, canonical_motion_number
from .proposals import GeneratorProvenance, Proposal, ProposalAcceptor
from .renderers import SVGRenderer, SVGRenderOptions
from .revisions import RevisionStore, SetKeyframeValueChange, Transaction

EDITOR_IDENTITY = "svm-real-motion-editor@0.1"
EDITOR_ACTOR = "editor:motion-timeline"
REFERENCE_TICKS = (0, 250, 500, 750, 1000)


@dataclass(frozen=True)
class MotionEditTarget:
    track_id: str
    keyframe_id: str


class MotionEditorSession:
    """One trusted local Editor session backed entirely by accepted SVM Core APIs."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.store = RevisionStore.create(document, "Editor Vertical Slice 01 base")
        if self.store.head is None:
            raise DocumentError("Editor Revision Store did not create a head")
        self.base_revision_id = self.store.head
        self.motion = MotionEvaluator(self.store.get_document(self.store.head))
        self.target = self._middle_target(self.motion.document)
        self._revision_labels = {self.store.head: "R0"}
        self._preview_motion: MotionEvaluator | None = None
        self._preview_value: int | float | None = None
        self._preview_deltas: tuple[MotionRevisionDelta, ...] = ()
        self._transition_deltas: tuple[MotionRevisionDelta, ...] = ()
        self._prime_reference_frames(self.motion)
        self._renderer = SVGRenderer(
            SVGRenderOptions(width=900, height=300, view_box=(0, 0, 600, 120))
        )

    @property
    def head(self) -> str:
        if self.store.head is None:
            raise DocumentError("Editor Revision Store has no head")
        return self.store.head

    def state(self, tick: int) -> dict[str, Any]:
        runtime = self._preview_motion or self.motion
        return self._serialize(runtime, tick, preview=self._preview_motion is not None)

    def preview(self, value: int | float, tick: int) -> dict[str, Any]:
        value = canonical_motion_number(value)
        current = self._keyframe_value(self.motion.document, self.target)
        if value == current:
            self.clear_preview()
            return self.state(tick)
        transaction = self._transaction(self.head, value, prefix="preview")
        preview_document = transaction.apply(self.store.get_document(self.head))
        self._preview_motion, self._preview_deltas = self.motion.transition_to_revision(
            preview_document
        )
        self._preview_value = value
        return self.state(tick)

    def clear_preview(self) -> None:
        self._preview_motion = None
        self._preview_value = None
        self._preview_deltas = ()

    def commit(self, value: int | float, tick: int) -> dict[str, Any]:
        value = canonical_motion_number(value)
        transaction = self._transaction(self.head, value, prefix="commit")
        digest = transaction.transaction_id.rsplit(":", 1)[-1]
        proposal = Proposal(
            proposal_id=f"proposal:motion-editor:{digest}",
            base_revision_id=self.head,
            generator=GeneratorProvenance(
                adapter_id=EDITOR_ACTOR,
                adapter_version="0.1",
                engine="svm-core",
                engine_version=EDITOR_IDENTITY,
            ),
            transaction=transaction,
            notes="Explicit local Editor Keyframe commit",
        )
        previous_motion = self.motion
        revision = ProposalAcceptor().accept(self.store, proposal)
        self.motion, self._transition_deltas = previous_motion.transition_to_revision(
            self.store.get_document(revision.revision_id)
        )
        self._revision_labels[revision.revision_id] = f"R{len(self._revision_labels)}"
        self.clear_preview()
        return self.state(tick)

    def checkout_parent(self, tick: int) -> dict[str, Any]:
        revision = self.store.revisions[self.head]
        if not revision.parent_ids:
            raise DocumentError("Initial Editor Revision has no parent")
        previous_motion = self.motion
        document = self.store.checkout(revision.parent_ids[0])
        self.motion, self._transition_deltas = previous_motion.transition_to_revision(document)
        self.clear_preview()
        return self.state(tick)

    def _serialize(self, runtime: MotionEvaluator, tick: int, *, preview: bool) -> dict[str, Any]:
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < 0:
            raise DocumentError("Editor tick must be a non-negative integer")
        before = set(runtime.frame_cache)
        frame = runtime.evaluate(tick, Quality.FINAL)
        after = set(runtime.frame_cache)
        sampled = runtime.sample_document(tick)
        track = self._track(runtime.document, self.target.track_id)
        target = track["target"]
        operation = next(
            item
            for item in sampled["construction"]["operations"]
            if item["id"] == target["operation"]
        )
        deltas = self._preview_deltas if preview else self._transition_deltas
        invalidated = {
            value
            for delta in deltas
            for value in REFERENCE_TICKS
            if value >= delta.interval.start_tick
            and (delta.interval.end_tick is None or value <= delta.interval.end_tick)
        }
        cache = []
        for value in REFERENCE_TICKS:
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
        revision = self.store.revisions[self.head]
        seconds = Fraction(tick, runtime.ticks_per_second)
        return {
            "editor_identity": EDITOR_IDENTITY,
            "document_id": runtime.document["document_id"],
            "revision": {
                "id": self.head,
                "label": self._revision_labels[self.head],
                "parent_ids": list(revision.parent_ids),
                "can_checkout_parent": bool(revision.parent_ids),
            },
            "preview": {
                "active": preview,
                "base_revision_id": self.head,
                "value": self._preview_value,
            },
            "timebase": {"ticks_per_second": runtime.ticks_per_second},
            "structure": self._document_outline(runtime.document),
            "track": copy.deepcopy(track),
            "target": copy.deepcopy(self.target.__dict__),
            "frame": {
                "tick": tick,
                "seconds": {"numerator": seconds.numerator, "denominator": seconds.denominator},
                "sampled_value": operation["parameters"][target["parameter"]],
                "svg": self._renderer.render(frame.scene),
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
        }

    def _transaction(
        self, base_revision_id: str, value: int | float, *, prefix: str
    ) -> Transaction:
        payload = {
            "identity": EDITOR_IDENTITY,
            "base_revision_id": base_revision_id,
            "track_id": self.target.track_id,
            "keyframe_id": self.target.keyframe_id,
            "value": value,
        }
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        return Transaction(
            transaction_id=f"transaction:motion-editor:{prefix}:{digest}",
            changes=(
                SetKeyframeValueChange(
                    track_id=self.target.track_id,
                    keyframe_id=self.target.keyframe_id,
                    value=value,
                ),
            ),
            message="Set middle Motion Keyframe from Editor",
        )

    @staticmethod
    def _middle_target(document: dict[str, Any]) -> MotionEditTarget:
        tracks = document["animation"]["content"]
        if len(tracks) != 1 or len(tracks[0]["keyframes"]) != 3:
            raise DocumentError("Editor Vertical Slice 01 requires one three-Keyframe Track")
        return MotionEditTarget(tracks[0]["id"], tracks[0]["keyframes"][1]["id"])

    @staticmethod
    def _track(document: dict[str, Any], track_id: str) -> dict[str, Any]:
        return next(track for track in document["animation"]["content"] if track["id"] == track_id)

    @classmethod
    def _keyframe_value(cls, document: dict[str, Any], target: MotionEditTarget) -> int | float:
        track = cls._track(document, target.track_id)
        return next(
            keyframe["value"]
            for keyframe in track["keyframes"]
            if keyframe["id"] == target.keyframe_id
        )

    @staticmethod
    def _prime_reference_frames(motion: MotionEvaluator) -> None:
        for tick in REFERENCE_TICKS:
            motion.evaluate(tick, Quality.FINAL)

    @staticmethod
    def _document_outline(document: dict[str, Any]) -> list[dict[str, Any]]:
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
        tracks = document["animation"]["content"]
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
                    "style": copy.deepcopy(styles.get(entity["id"])),
                    "track_ids": operation_tracks,
                }
            )
        return outline
