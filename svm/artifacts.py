from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ArtifactKind(StrEnum):
    REFERENCE = "ReferenceArtifact"
    DERIVED = "DerivedArtifact"


class ArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactBlob:
    artifact_id: str
    content_hash: str
    content: bytes


@dataclass(frozen=True)
class ArtifactDescriptor:
    artifact_id: str
    kind: ArtifactKind
    media_type: str
    provenance: dict[str, Any] = field(default_factory=dict)
    locator: str | None = None


@dataclass(frozen=True)
class ArtifactSnapshot:
    blob: ArtifactBlob
    descriptor: ArtifactDescriptor

    @property
    def artifact_id(self) -> str:
        return self.blob.artifact_id

    @property
    def content_hash(self) -> str:
        return self.blob.content_hash

    @property
    def content(self) -> bytes:
        return self.blob.content

    @property
    def kind(self) -> ArtifactKind:
        return self.descriptor.kind

    @property
    def media_type(self) -> str:
        return self.descriptor.media_type

    @property
    def provenance(self) -> dict[str, Any]:
        return self.descriptor.provenance

    def document_reference(self) -> dict[str, Any]:
        return {
            "id": self.artifact_id,
            "uri": self.descriptor.locator or self.artifact_id,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
            "import_metadata": {
                "artifact_kind": self.kind.value,
                "provenance": copy.deepcopy(self.provenance),
            },
        }


class ArtifactResolver(Protocol):
    """Capability that resolves and verifies accepted content-addressed bytes."""

    def resolve(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]: ...

    def resolve_as(
        self,
        artifact_ids: tuple[str, ...],
        *,
        kind: ArtifactKind,
        media_types: frozenset[str],
    ) -> tuple[ArtifactSnapshot, ...]: ...

    def resolve_reference(self, reference: dict[str, Any]) -> ArtifactSnapshot: ...


class ArtifactStore:
    """Small in-memory content-addressed store for Adapter inputs and evidence."""

    def __init__(self) -> None:
        self._blobs: dict[str, ArtifactBlob] = {}
        self._descriptors: dict[str, list[ArtifactDescriptor]] = {}

    def import_bytes(
        self,
        content: bytes,
        *,
        media_type: str,
        kind: ArtifactKind = ArtifactKind.REFERENCE,
        provenance: dict[str, Any] | None = None,
        locator: str | None = None,
    ) -> ArtifactSnapshot:
        if not content:
            raise ArtifactError("Artifact content must not be empty")
        if not media_type:
            raise ArtifactError("Artifact media_type must not be empty")
        digest = hashlib.sha256(content).hexdigest()
        content_hash = f"sha256:{digest}"
        artifact_id = f"artifact:{digest}"
        blob = ArtifactBlob(
            artifact_id=artifact_id,
            content_hash=content_hash,
            content=bytes(content),
        )
        descriptor = ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=kind,
            media_type=media_type,
            provenance=copy.deepcopy(provenance or {}),
            locator=locator,
        )
        existing = self._blobs.get(artifact_id)
        if existing is not None:
            if existing.content != blob.content:
                raise ArtifactError(f"Artifact identity collision for {artifact_id}")
            blob = existing
        else:
            self._blobs[artifact_id] = blob
        descriptors = self._descriptors.setdefault(artifact_id, [])
        if descriptor not in descriptors:
            descriptors.append(descriptor)
        return ArtifactSnapshot(blob, descriptor)

    def get(self, artifact_id: str) -> ArtifactSnapshot:
        try:
            blob = self._blobs[artifact_id]
        except KeyError as exc:
            raise ArtifactError(f"Unknown artifact {artifact_id}") from exc
        self._verify_blob(blob)
        descriptors = self._descriptors[artifact_id]
        if len(descriptors) != 1:
            raise ArtifactError(f"Artifact {artifact_id} has multiple interpretations")
        return ArtifactSnapshot(blob, descriptors[0])

    def snapshots(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        return tuple(self.get(artifact_id) for artifact_id in artifact_ids)

    def resolve(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        """Resolve only Store-held Artifacts and verify every content hash."""

        return self.snapshots(artifact_ids)

    def resolve_as(
        self,
        artifact_ids: tuple[str, ...],
        *,
        kind: ArtifactKind,
        media_types: frozenset[str],
    ) -> tuple[ArtifactSnapshot, ...]:
        snapshots: list[ArtifactSnapshot] = []
        for artifact_id in artifact_ids:
            try:
                blob = self._blobs[artifact_id]
            except KeyError as exc:
                raise ArtifactError(f"Unknown artifact {artifact_id}") from exc
            self._verify_blob(blob)
            matches = [
                descriptor
                for descriptor in self._descriptors[artifact_id]
                if descriptor.kind == kind and descriptor.media_type in media_types
            ]
            if len(matches) != 1:
                raise ArtifactError(
                    f"Artifact {artifact_id} does not have exactly one matching interpretation"
                )
            snapshots.append(ArtifactSnapshot(blob, matches[0]))
        return tuple(snapshots)

    def resolve_reference(self, reference: dict[str, Any]) -> ArtifactSnapshot:
        artifact_id = reference.get("id")
        if not isinstance(artifact_id, str):
            raise ArtifactError("Document Artifact reference requires an ID")
        try:
            blob = self._blobs[artifact_id]
        except KeyError as exc:
            raise ArtifactError(f"Unknown artifact {artifact_id}") from exc
        self._verify_blob(blob)
        if reference.get("content_hash") != blob.content_hash:
            raise ArtifactError(f"Artifact content hash mismatch for {artifact_id}")
        metadata = reference.get("import_metadata", {})
        expected = ArtifactDescriptor(
            artifact_id=artifact_id,
            kind=self._kind(metadata.get("artifact_kind")),
            media_type=reference.get("media_type", ""),
            provenance=copy.deepcopy(metadata.get("provenance", {})),
            locator=None if reference.get("uri") == artifact_id else reference.get("uri"),
        )
        if expected not in self._descriptors[artifact_id]:
            raise ArtifactError(f"Artifact descriptor mismatch for {artifact_id}")
        return ArtifactSnapshot(blob, expected)

    @staticmethod
    def _kind(value: Any) -> ArtifactKind:
        try:
            return ArtifactKind(value)
        except (TypeError, ValueError) as exc:
            raise ArtifactError(f"Unknown Artifact kind {value!r}") from exc

    @staticmethod
    def _verify_blob(blob: ArtifactBlob) -> None:
        digest = hashlib.sha256(blob.content).hexdigest()
        if blob.content_hash != f"sha256:{digest}":
            raise ArtifactError(f"Artifact content hash mismatch for {blob.artifact_id}")
        if blob.artifact_id != f"artifact:{digest}":
            raise ArtifactError(f"Artifact ID does not match content for {blob.artifact_id}")
