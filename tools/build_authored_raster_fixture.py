"""Offline spec/75 fixture encoding. Encoder bytes are never verification authority."""

from __future__ import annotations

import json
from pathlib import Path

from svm.artifacts import ArtifactStore
from svm.authored_raster_production import reproduce_source
from svm.revisions import AppendReferencesChange, RevisionStore, Transaction
from svm.video_ingestion import VideoSampling, ingest_video


def main() -> None:
    import cv2
    import numpy as np

    root = Path(__file__).resolve().parents[1]
    directory = root / "examples/043-authored-raster-production"
    artifacts = ArtifactStore()
    source = artifacts.import_bytes(
        (directory / "source.svg").read_bytes(), media_type="image/svg+xml"
    )
    store = RevisionStore.create(
        json.loads((root / "examples/005-empty-canvas.svm.json").read_text())
    )
    revision = store.commit(
        store.head,
        Transaction(
            "transaction:authored-source", (AppendReferencesChange((source.document_reference(),)),)
        ),
    )
    produced = reproduce_source(store, revision.revision_id, artifacts)
    target = directory / "scene.avi"
    writer = cv2.VideoWriter(
        str(target), cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"FFV1"), 1, (256, 256), False
    )
    try:
        if not writer.isOpened() or writer.getBackendName() != "FFMPEG":
            raise RuntimeError("Pinned FFV1 encoder unavailable")
        for png in produced.frames:
            writer.write(cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED))
    finally:
        writer.release()
    video = artifacts.import_bytes(target.read_bytes(), media_type="video/x-msvideo")
    decoded = ingest_video(artifacts, video.document_reference(), VideoSampling((0, 1), 12, (1, 1)))
    if tuple(frame.content for frame in decoded.frames) != produced.frames:
        raise RuntimeError("Encoded video failed exact independent decode comparison")
    print(
        json.dumps(
            {
                "source": source.content_hash,
                "video": video.content_hash,
                "frames": [frame.content_hash for frame in decoded.frames],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
