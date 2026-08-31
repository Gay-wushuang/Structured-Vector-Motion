from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .document import validate_document
from .evaluator import DocumentError, canonical_bytes
from .structural_relations import (
    materialize_promoted_relations,
)

COMPONENT_PROMOTION_ADAPTER_VERSION = "0.5"
COMPONENT_PROMOTION_IDENTITY = f"svm-component-promotion@{COMPONENT_PROMOTION_ADAPTER_VERSION}"
PROMOTED_ENTITY_IDENTITY = "svm-component-promotion@0.4"


class Change(Protocol):
    def apply(self, document: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class SplitPart:
    entity_id: str
    name: str
    output_name: str
    selector: dict[str, Any]


@dataclass(frozen=True)
class SetOperationParameterChange:
    operation_id: str
    parameter: str
    value: Any

    def apply(self, document: dict[str, Any]) -> None:
        operations = {
            operation["id"]: operation for operation in document["construction"]["operations"]
        }
        if self.operation_id not in operations:
            raise DocumentError(f"Cannot mutate missing operation {self.operation_id}")
        operations[self.operation_id].setdefault("parameters", {})[self.parameter] = copy.deepcopy(
            self.value
        )


@dataclass(frozen=True)
class SetKeyframeValueChange:
    """Persist one numeric Keyframe edit without changing Track identity."""

    track_id: str
    keyframe_id: str
    value: int | float

    def apply(self, document: dict[str, Any]) -> None:
        from .motion import canonical_motion_number

        tracks = document.get("animation", {}).get("content", [])
        track = next((item for item in tracks if item.get("id") == self.track_id), None)
        if track is None:
            raise DocumentError(f"Cannot edit missing Animation Track {self.track_id}")
        keyframe = next(
            (item for item in track.get("keyframes", []) if item.get("id") == self.keyframe_id),
            None,
        )
        if keyframe is None:
            raise DocumentError(f"Cannot edit missing Keyframe {self.keyframe_id}")
        value = canonical_motion_number(self.value)
        if canonical_motion_number(keyframe.get("value")) == value:
            raise DocumentError("SetKeyframeValueChange must change the canonical value")
        keyframe["value"] = value


@dataclass(frozen=True)
class CreateTrackChange:
    """Create one empty numeric linear Track inside an atomic authoring Transaction."""

    track_id: str
    operation_id: str
    parameter: str
    ticks_per_second: int

    def apply(self, document: dict[str, Any]) -> None:
        from .motion import MOTION_SEMANTICS_IDENTITY
        from .operations import get_operation_registry

        if not isinstance(self.track_id, str) or not self.track_id.startswith("track:"):
            raise DocumentError("CreateTrackChange requires a track: ID")
        if (
            not isinstance(self.ticks_per_second, int)
            or isinstance(self.ticks_per_second, bool)
            or self.ticks_per_second <= 0
        ):
            raise DocumentError("CreateTrackChange requires a positive integer timebase")
        operations = {
            operation["id"]: operation for operation in document["construction"]["operations"]
        }
        operation = operations.get(self.operation_id)
        if operation is None:
            raise DocumentError(f"Cannot animate missing Operation {self.operation_id}")
        parameters = operation.get("parameters", {})
        if self.parameter not in parameters:
            raise DocumentError(
                f"Cannot animate missing parameter {self.operation_id}.{self.parameter}"
            )
        registry = get_operation_registry(document["semantics_version"])
        if self.parameter not in registry.animatable_parameters(operation):
            raise DocumentError(
                f"Operation parameter {self.operation_id}.{self.parameter} is not animatable"
            )
        if not isinstance(parameters[self.parameter], (int, float)) or isinstance(
            parameters[self.parameter], bool
        ):
            raise DocumentError("CreateTrackChange requires a numeric target parameter")
        animation = document["animation"]
        tracks = animation["content"]
        if any(track.get("id") == self.track_id for track in tracks):
            raise DocumentError(f"Animation Track already exists: {self.track_id}")
        if any(
            track.get("target") == {"operation": self.operation_id, "parameter": self.parameter}
            for track in tracks
        ):
            raise DocumentError(
                f"Animation Track already targets {self.operation_id}.{self.parameter}"
            )
        timebase = animation.get("timebase")
        if timebase is not None and timebase.get("ticks_per_second") != self.ticks_per_second:
            raise DocumentError("CreateTrackChange timebase conflicts with the Document")
        animation["semantics_version"] = MOTION_SEMANTICS_IDENTITY
        animation["timebase"] = {"ticks_per_second": self.ticks_per_second}
        tracks.append(
            {
                "id": self.track_id,
                "target": {"operation": self.operation_id, "parameter": self.parameter},
                "value_type": "number",
                "interpolation": "linear",
                "keyframes": [],
            }
        )


@dataclass(frozen=True)
class AddKeyframeChange:
    """Insert one stable numeric Keyframe into an existing or transaction-created Track."""

    track_id: str
    keyframe_id: str
    tick: int
    value: int | float

    def apply(self, document: dict[str, Any]) -> None:
        from .motion import canonical_motion_number

        tracks = document.get("animation", {}).get("content", [])
        track = next((item for item in tracks if item.get("id") == self.track_id), None)
        if track is None:
            raise DocumentError(f"Cannot add Keyframe to missing Track {self.track_id}")
        if not isinstance(self.keyframe_id, str) or not self.keyframe_id.startswith("keyframe:"):
            raise DocumentError("AddKeyframeChange requires a keyframe: ID")
        if not isinstance(self.tick, int) or isinstance(self.tick, bool) or self.tick < 0:
            raise DocumentError("AddKeyframeChange requires a non-negative integer tick")
        keyframes = track.get("keyframes", [])
        if any(item.get("id") == self.keyframe_id for item in keyframes):
            raise DocumentError(f"Keyframe already exists: {self.keyframe_id}")
        if any(item.get("tick") == self.tick for item in keyframes):
            raise DocumentError(f"Track {self.track_id} already has a Keyframe at {self.tick}")
        keyframes.append(
            {
                "id": self.keyframe_id,
                "tick": self.tick,
                "value": canonical_motion_number(self.value),
            }
        )
        keyframes.sort(key=lambda item: item["tick"])


@dataclass(frozen=True)
class AppendSceneFragmentChange:
    entities: tuple[dict[str, Any], ...]
    operations: tuple[dict[str, Any], ...]
    output_bindings: tuple[dict[str, Any], ...]
    render_entries: tuple[str, ...]
    styles: tuple[dict[str, Any], ...]
    references: tuple[dict[str, Any], ...] = ()

    def apply(self, document: dict[str, Any]) -> None:
        document["entities"].extend(copy.deepcopy(self.entities))
        document["construction"]["operations"].extend(copy.deepcopy(self.operations))
        document["construction"]["output_bindings"].extend(copy.deepcopy(self.output_bindings))
        document["presentation"]["render_stack"].extend(self.render_entries)
        document["presentation"]["styles"].extend(copy.deepcopy(self.styles))
        known_references = {reference["id"] for reference in document["references"]}
        for reference in self.references:
            if reference["id"] not in known_references:
                document["references"].append(copy.deepcopy(reference))
            known_references.add(reference["id"])


@dataclass(frozen=True)
class ImportLayeredSceneChange:
    """Core-owned primitive for a verifier-bound layered scene fragment."""

    fragment: AppendSceneFragmentChange
    namespace: str

    @property
    def references(self) -> tuple[dict[str, Any], ...]:
        return self.fragment.references

    def apply(self, document: dict[str, Any]) -> None:
        self.fragment.apply(document)


@dataclass(frozen=True)
class ImportPrimitiveSequenceChange:
    """Core-owned primitive for a verifier-bound ordered primitive scene."""

    fragment: AppendSceneFragmentChange
    namespace: str

    @property
    def references(self) -> tuple[dict[str, Any], ...]:
        return self.fragment.references

    def apply(self, document: dict[str, Any]) -> None:
        self.fragment.apply(document)


@dataclass(frozen=True)
class RasterLayerEvidence:
    bundle_artifact_id: str
    run_identity: str
    layer_id: str
    layer_artifact_id: str
    order_index: int

    def to_entity(self, namespace: str) -> dict[str, Any]:
        content = {
            "identity": "svm-layerd-entity@0.4",
            "bundle_artifact_id": self.bundle_artifact_id,
            "run_identity": self.run_identity,
            "layer_id": self.layer_id,
            "layer_artifact_id": self.layer_artifact_id,
            "order_index": self.order_index,
        }
        digest = hashlib.sha256(canonical_bytes(content)).hexdigest()[:16]
        suffix = self.layer_id.removeprefix("layer:")
        return {
            "id": f"entity:{namespace}-{digest}",
            "name": f"LayerD Region {suffix}",
            "semantic_tags": ["region", "research-layer", "layerd-output"],
            "source_layer": {
                "producer_family": "layerd",
                "bundle_artifact_id": self.bundle_artifact_id,
                "run_identity": self.run_identity,
                "layer_id": self.layer_id,
                "layer_artifact_id": self.layer_artifact_id,
                "order": {
                    "index": self.order_index,
                    "semantics": "svm-order:layerd-extraction@0.1",
                },
            },
        }


@dataclass(frozen=True)
class ImportRasterLayerEvidenceChange:
    """Core-owned primitive for verified raster decomposition evidence."""

    layers: tuple[RasterLayerEvidence, ...]
    references: tuple[dict[str, Any], ...]
    namespace: str

    def apply(self, document: dict[str, Any]) -> None:
        if not self.layers:
            raise DocumentError("Raster layer evidence requires at least one layer")
        if any(type(layer) is not RasterLayerEvidence for layer in self.layers):
            raise DocumentError("Raster layer evidence accepts only typed layer records")
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.namespace) is None:
            raise DocumentError("Raster layer evidence namespace is invalid")
        entities = [layer.to_entity(self.namespace) for layer in self.layers]
        entity_ids = {entity["id"] for entity in document["entities"]}
        new_ids = [entity["id"] for entity in entities]
        if len(new_ids) != len(set(new_ids)) or any(value in entity_ids for value in new_ids):
            raise DocumentError("Raster layer evidence Entity IDs must be new and unique")
        known_references = {reference["id"] for reference in document["references"]}
        for reference in self.references:
            if reference["id"] not in known_references:
                document["references"].append(copy.deepcopy(reference))
                known_references.add(reference["id"])
        document["entities"].extend(entities)


@dataclass(frozen=True)
class AppendReferencesChange:
    references: tuple[dict[str, Any], ...]

    def apply(self, document: dict[str, Any]) -> None:
        if not self.references:
            raise DocumentError("AppendReferences requires at least one Artifact reference")
        known_references = {reference["id"] for reference in document["references"]}
        for reference in self.references:
            if reference["id"] not in known_references:
                document["references"].append(copy.deepcopy(reference))
                known_references.add(reference["id"])


@dataclass(frozen=True)
class PromotedComponent:
    artifact_id: str
    candidate_id: str
    component_digest: str
    bounds: tuple[int, int, int, int]

    def to_entity(self, namespace: str) -> dict[str, Any]:
        if re.fullmatch(r"artifact:[0-9a-f]{64}", self.artifact_id) is None:
            raise DocumentError("Promoted component Artifact ID is invalid")
        if re.fullmatch(r"candidate:component-[0-9]{4,}", self.candidate_id) is None:
            raise DocumentError("Promoted component candidate ID is invalid")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.component_digest) is None:
            raise DocumentError("Promoted component digest is invalid")
        if (
            not isinstance(self.bounds, tuple)
            or len(self.bounds) != 4
            or any(not isinstance(value, int) or isinstance(value, bool) for value in self.bounds)
            or not (0 <= self.bounds[0] < self.bounds[2])
            or not (0 <= self.bounds[1] < self.bounds[3])
        ):
            raise DocumentError("Promoted component bounds are invalid")
        return {
            "id": promoted_component_entity_id(namespace, self),
            "name": f"Region {self.candidate_id.rsplit('-', 1)[1]}",
            "semantic_tags": ["region", "promoted-component"],
            "provenance": {
                "type": "PromotedComponent",
                "artifact_id": self.artifact_id,
                "candidate_id": self.candidate_id,
                "component_digest": self.component_digest,
                "bounds": list(self.bounds),
            },
        }


@dataclass(frozen=True)
class PromoteComponentsChange:
    """Promote accepted analysis evidence into addressable, non-rendered Entities."""

    components: tuple[PromotedComponent, ...]
    references: tuple[dict[str, Any], ...]
    namespace: str = "region"

    def apply(self, document: dict[str, Any]) -> None:
        if not self.components:
            raise DocumentError("Component promotion requires at least one component")
        if any(type(component) is not PromotedComponent for component in self.components):
            raise DocumentError("Component promotion accepts only PromotedComponent records")
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.namespace) is None:
            raise DocumentError("Component promotion namespace is invalid")
        if len(self.references) != 1:
            raise DocumentError("Component promotion requires one analysis Artifact reference")
        accepted_references = {reference["id"]: reference for reference in document["references"]}
        reference = self.references[0]
        if accepted_references.get(reference["id"]) != reference:
            raise DocumentError(
                "Component promotion source must already be an accepted Artifact reference"
            )
        metadata = reference.get("import_metadata", {})
        provenance = metadata.get("provenance", {})
        parameters = provenance.get("parameters", {})
        if (
            reference.get("media_type") != "application/vnd.svm.component-analysis+json"
            or metadata.get("artifact_kind") != "DerivedArtifact"
            or provenance.get("derived_type") != "component-analysis"
            or parameters.get("analysis_identity") != "svm-opencv-components@0.2"
        ):
            raise DocumentError("Component promotion reference is not accepted analysis v0.2")
        candidate_ids = [component.candidate_id for component in self.components]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise DocumentError("Component promotion candidate IDs must be unique")
        if any(component.artifact_id != reference["id"] for component in self.components):
            raise DocumentError("Promoted component Artifact must match the promotion reference")
        promoted_keys = {
            (entity_provenance.get("artifact_id"), entity_provenance.get("candidate_id"))
            for entity in document["entities"]
            if isinstance((entity_provenance := entity.get("provenance")), dict)
            and entity_provenance.get("type") == "PromotedComponent"
        }
        if any(
            (component.artifact_id, component.candidate_id) in promoted_keys
            for component in self.components
        ):
            raise DocumentError("Component promotion candidate is already promoted")
        entities = [component.to_entity(self.namespace) for component in self.components]
        entity_ids = {entity["id"] for entity in document["entities"]}
        new_ids = [entity["id"] for entity in entities]
        if len(new_ids) != len(set(new_ids)) or any(
            entity_id in entity_ids for entity_id in new_ids
        ):
            raise DocumentError("Promoted component Entity IDs must be new and unique")
        document["entities"].extend(entities)
        document["structural_relations"] = materialize_promoted_relations(document["entities"])

    def proposed_relations(self, document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        entities = [component.to_entity(self.namespace) for component in self.components]
        return tuple(materialize_promoted_relations(document["entities"] + entities))


def promoted_component_entity_id(namespace: str, component: PromotedComponent) -> str:
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", namespace) is None:
        raise DocumentError("Component promotion namespace is invalid")
    digest = hashlib.sha256(
        canonical_bytes(
            {
                "promotion_identity": PROMOTED_ENTITY_IDENTITY,
                "artifact_id": component.artifact_id,
                "candidate_id": component.candidate_id,
                "component_digest": component.component_digest,
            }
        )
    ).hexdigest()[:16]
    return f"entity:{namespace}-{digest}"


@dataclass(frozen=True)
class ReplaceSceneFragmentChange:
    """Atomically replace an explicitly scoped, self-contained scene fragment."""

    existing_entity_ids: tuple[str, ...]
    owned_operation_ids: tuple[str, ...]
    entities: tuple[dict[str, Any], ...]
    operations: tuple[dict[str, Any], ...]
    output_bindings: tuple[dict[str, Any], ...]
    render_entries: tuple[str, ...]
    styles: tuple[dict[str, Any], ...]
    references: tuple[dict[str, Any], ...] = ()

    def apply(self, document: dict[str, Any]) -> None:
        scoped_entities = set(self.existing_entity_ids)
        owned_operations = set(self.owned_operation_ids)
        if len(scoped_entities) != len(self.existing_entity_ids) or not scoped_entities:
            raise DocumentError("Reconciliation Entity scope must be non-empty and unique")
        if len(owned_operations) != len(self.owned_operation_ids) or not owned_operations:
            raise DocumentError("Reconciliation Operation ownership must be non-empty and unique")
        known_entities = {entity["id"] for entity in document["entities"]}
        known_operations = {operation["id"] for operation in document["construction"]["operations"]}
        if not scoped_entities <= known_entities:
            raise DocumentError("Reconciliation scope contains missing Entities")
        if not owned_operations <= known_operations:
            raise DocumentError("Reconciliation owns missing Operations")
        for entity in document["entities"]:
            if entity["id"] not in scoped_entities and entity.get("parent_id") in scoped_entities:
                raise DocumentError(
                    f"Cannot reconcile Entity {entity['parent_id']}; "
                    f"it owns external child {entity['id']}"
                )

        for operation in document["construction"]["operations"]:
            if operation["id"] in owned_operations:
                continue
            for slot in operation.get("inputs", {}).values():
                if slot.rsplit(".", 1)[0] in owned_operations:
                    raise DocumentError(
                        f"Cannot reconcile Operation {slot.rsplit('.', 1)[0]}; "
                        f"it is used by external Operation {operation['id']}"
                    )
        for binding in document["construction"]["output_bindings"]:
            if binding["entity"] in scoped_entities and binding["property"] != "geometry":
                raise DocumentError(
                    f"Cannot reconcile Entity {binding['entity']}; "
                    f"unsupported scoped binding property {binding['property']!r}"
                )
            operation_id = binding["slot"].rsplit(".", 1)[0]
            if operation_id in owned_operations and binding["entity"] not in scoped_entities:
                raise DocumentError(f"Cannot reconcile shared Operation {operation_id}")

        entity_index = _first_index(
            document["entities"], lambda item: item["id"] in scoped_entities
        )
        operation_index = _first_index(
            document["construction"]["operations"],
            lambda item: item["id"] in owned_operations,
        )
        binding_index = _first_index(
            document["construction"]["output_bindings"],
            lambda item: item["entity"] in scoped_entities,
        )
        style_index = _first_index(
            document["presentation"]["styles"],
            lambda item: item["entity"] in scoped_entities,
        )
        render_stack = document["presentation"]["render_stack"]
        render_indices = [
            index for index, entity_id in enumerate(render_stack) if entity_id in scoped_entities
        ]
        if len(render_indices) != len(scoped_entities) or render_indices != list(
            range(render_indices[0], render_indices[0] + len(render_indices))
        ):
            raise DocumentError(
                "Reconciliation scope must form one contiguous Render Stack fragment"
            )
        render_index = render_indices[0]

        document["entities"][:] = [
            entity for entity in document["entities"] if entity["id"] not in scoped_entities
        ]
        document["construction"]["operations"][:] = [
            operation
            for operation in document["construction"]["operations"]
            if operation["id"] not in owned_operations
        ]
        document["construction"]["output_bindings"][:] = [
            binding
            for binding in document["construction"]["output_bindings"]
            if binding["entity"] not in scoped_entities
        ]
        document["presentation"]["styles"][:] = [
            style
            for style in document["presentation"]["styles"]
            if style["entity"] not in scoped_entities
        ]
        render_stack[:] = [
            entity_id for entity_id in render_stack if entity_id not in scoped_entities
        ]

        document["entities"][entity_index:entity_index] = copy.deepcopy(self.entities)
        document["construction"]["operations"][operation_index:operation_index] = copy.deepcopy(
            self.operations
        )
        document["construction"]["output_bindings"][binding_index:binding_index] = copy.deepcopy(
            self.output_bindings
        )
        document["presentation"]["styles"][style_index:style_index] = copy.deepcopy(self.styles)
        render_stack[render_index:render_index] = self.render_entries

        known_references = {reference["id"] for reference in document["references"]}
        for reference in self.references:
            if reference["id"] not in known_references:
                document["references"].append(copy.deepcopy(reference))
                known_references.add(reference["id"])


def _first_index(values: list[dict[str, Any]], predicate: Any) -> int:
    return next((index for index, value in enumerate(values) if predicate(value)), len(values))


@dataclass(frozen=True)
class SplitEntityChange:
    source_entity_id: str
    operation_id: str
    parts: tuple[SplitPart, ...]

    def apply(self, document: dict[str, Any]) -> None:
        entities = document["entities"]
        entity_by_id = {entity["id"]: entity for entity in entities}
        if self.source_entity_id not in entity_by_id:
            raise DocumentError(f"Cannot split missing entity {self.source_entity_id}")
        if self.operation_id in {op["id"] for op in document["construction"]["operations"]}:
            raise DocumentError(f"Operation already exists: {self.operation_id}")
        if not self.parts:
            raise DocumentError("SplitEntity requires at least one part")

        new_ids = [part.entity_id for part in self.parts]
        if len(new_ids) != len(set(new_ids)) or set(new_ids).intersection(entity_by_id):
            raise DocumentError("SplitEntity child IDs must be new and unique")
        output_names = [part.output_name for part in self.parts]
        if len(output_names) != len(set(output_names)):
            raise DocumentError("SplitEntity output names must be unique")

        source_bindings = [
            binding
            for binding in document["construction"]["output_bindings"]
            if binding["entity"] == self.source_entity_id and binding["property"] == "geometry"
        ]
        if len(source_bindings) != 1:
            raise DocumentError("SplitEntity source requires exactly one geometry binding")

        for part in self.parts:
            entities.append(
                {"id": part.entity_id, "name": part.name, "parent_id": self.source_entity_id}
            )

        styles = document["presentation"].setdefault("styles", [])
        source_style = next(
            (style for style in styles if style["entity"] == self.source_entity_id), None
        )
        if source_style is not None:
            for part in self.parts:
                inherited_style = copy.deepcopy(source_style)
                inherited_style["entity"] = part.entity_id
                styles.append(inherited_style)

        document["construction"]["operations"].append(
            {
                "id": self.operation_id,
                "type": "SplitEntity",
                "inputs": {"geometry": source_bindings[0]["slot"]},
                "parameters": {
                    "parts": [
                        {
                            "entity_id": part.entity_id,
                            "output_name": part.output_name,
                            "selector": copy.deepcopy(part.selector),
                        }
                        for part in self.parts
                    ]
                },
            }
        )
        for part in self.parts:
            document["construction"]["output_bindings"].append(
                {
                    "entity": part.entity_id,
                    "property": "geometry",
                    "slot": f"{self.operation_id}.{part.output_name}",
                }
            )

        render_stack = document["presentation"]["render_stack"]
        try:
            source_index = render_stack.index(self.source_entity_id)
        except ValueError as exc:
            raise DocumentError("SplitEntity source must occur in the render stack") from exc
        render_stack[source_index : source_index + 1] = new_ids


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    changes: tuple[Change, ...]
    message: str = ""

    def apply(self, base_document: dict[str, Any]) -> dict[str, Any]:
        candidate = copy.deepcopy(base_document)
        for change in self.changes:
            change.apply(candidate)
        validate_document(candidate)
        return candidate


@dataclass(frozen=True)
class Revision:
    revision_id: str
    parent_ids: tuple[str, ...]
    transaction_id: str | None
    document_hash: str
    message: str = ""


@dataclass
class RevisionStore:
    revisions: dict[str, Revision] = field(default_factory=dict)
    _documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    head: str | None = None

    @classmethod
    def create(cls, document: dict[str, Any], message: str = "Initial revision") -> RevisionStore:
        validate_document(document)
        store = cls()
        revision = store._make_revision(document, (), None, message)
        store.revisions[revision.revision_id] = revision
        store._documents[revision.revision_id] = copy.deepcopy(document)
        store.head = revision.revision_id
        return store

    def commit(self, base_revision_id: str, transaction: Transaction) -> Revision:
        if base_revision_id not in self.revisions:
            raise KeyError(base_revision_id)
        candidate = transaction.apply(self._documents[base_revision_id])
        revision = self._make_revision(
            candidate, (base_revision_id,), transaction.transaction_id, transaction.message
        )
        self.revisions[revision.revision_id] = revision
        self._documents[revision.revision_id] = copy.deepcopy(candidate)
        self.head = revision.revision_id
        return revision

    def checkout(self, revision_id: str) -> dict[str, Any]:
        if revision_id not in self._documents:
            raise KeyError(revision_id)
        self.head = revision_id
        return copy.deepcopy(self._documents[revision_id])

    def get_document(self, revision_id: str) -> dict[str, Any]:
        """Return an isolated snapshot without changing the active head."""
        if revision_id not in self._documents:
            raise KeyError(revision_id)
        return copy.deepcopy(self._documents[revision_id])

    def undo(self, revision_id: str | None = None) -> dict[str, Any]:
        current_id = revision_id or self.head
        if current_id is None or current_id not in self.revisions:
            raise KeyError(current_id)
        parents = self.revisions[current_id].parent_ids
        if not parents:
            raise DocumentError("Initial revision cannot be undone")
        return self.checkout(parents[0])

    @staticmethod
    def _make_revision(
        document: dict[str, Any],
        parent_ids: tuple[str, ...],
        transaction_id: str | None,
        message: str,
    ) -> Revision:
        document_hash = f"sha256:{hashlib.sha256(canonical_bytes(document)).hexdigest()}"
        revision_payload = {
            "document_hash": document_hash,
            "parent_ids": parent_ids,
            "transaction_id": transaction_id,
            "message": message,
        }
        revision_id = f"revision:{hashlib.sha256(canonical_bytes(revision_payload)).hexdigest()}"
        return Revision(revision_id, parent_ids, transaction_id, document_hash, message)
