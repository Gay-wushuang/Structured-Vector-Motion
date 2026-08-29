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
class ArtifactSnapshot:
    artifact_id: str
    kind: ArtifactKind
    media_type: str
    content_hash: str
    content: bytes
    provenance: dict[str, Any] = field(default_factory=dict)

    def document_reference(self) -> dict[str, Any]:
        return {
            "id": self.artifact_id,
            "uri": self.artifact_id,
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


class ArtifactStore:
    """Small in-memory content-addressed store for Adapter inputs and evidence."""

    def __init__(self) -> None:
        self._artifacts: dict[str, ArtifactSnapshot] = {}

    def import_bytes(
        self,
        content: bytes,
        *,
        media_type: str,
        kind: ArtifactKind = ArtifactKind.REFERENCE,
        provenance: dict[str, Any] | None = None,
    ) -> ArtifactSnapshot:
        if not content:
            raise ArtifactError("Artifact content must not be empty")
        if not media_type:
            raise ArtifactError("Artifact media_type must not be empty")
        digest = hashlib.sha256(content).hexdigest()
        content_hash = f"sha256:{digest}"
        artifact_id = f"artifact:{digest}"
        snapshot = ArtifactSnapshot(
            artifact_id=artifact_id,
            kind=kind,
            media_type=media_type,
            content_hash=content_hash,
            content=bytes(content),
            provenance=copy.deepcopy(provenance or {}),
        )
        existing = self._artifacts.get(artifact_id)
        if existing is not None:
            if existing.content != snapshot.content:
                raise ArtifactError(f"Artifact identity collision for {artifact_id}")
            return existing
        self._artifacts[artifact_id] = snapshot
        return snapshot

    def get(self, artifact_id: str) -> ArtifactSnapshot:
        try:
            snapshot = self._artifacts[artifact_id]
        except KeyError as exc:
            raise ArtifactError(f"Unknown artifact {artifact_id}") from exc
        digest = hashlib.sha256(snapshot.content).hexdigest()
        if snapshot.content_hash != f"sha256:{digest}":
            raise ArtifactError(f"Artifact content hash mismatch for {artifact_id}")
        if snapshot.artifact_id != f"artifact:{digest}":
            raise ArtifactError(f"Artifact ID does not match content for {artifact_id}")
        return snapshot

    def snapshots(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        return tuple(self.get(artifact_id) for artifact_id in artifact_ids)

    def resolve(self, artifact_ids: tuple[str, ...]) -> tuple[ArtifactSnapshot, ...]:
        """Resolve only Store-held Artifacts and verify every content hash."""

        return self.snapshots(artifact_ids)
