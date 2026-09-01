from __future__ import annotations

import hashlib
import json
from pathlib import Path

from svm import AdapterRequest, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters import (
    POPOutputAdapter,
    POPStructureAdapter,
    POPTokenExporter,
)
from svm.adapters.pop_structure import ANALYSIS_MEDIA_TYPE, MASK_BUNDLE_MEDIA_TYPE
from svm.evaluator import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_P = ROOT / "examples" / "derived" / "020-pop-output" / "real"
OUTPUT = ROOT / "examples" / "derived" / "021-pop-structure"


def main() -> None:
    pop_payload = json.loads((GOLDEN_P / "pop-output.json").read_text(encoding="utf-8"))
    producer = pop_payload["producer"]
    artifacts = ArtifactStore()
    prefix, output = POPTokenExporter().export(
        artifacts,
        pop_payload["raw_tokens"],
        prefix_length=pop_payload["generation_context"]["prefix_length"],
        commit=producer["commit"],
        model_id=producer["model_id"],
        checkpoint_hash=producer["checkpoint_hash"],
        seed=producer["seed"],
        decoding=producer["decoding"],
        user_intent=pop_payload["annotations"]["user_intent"],
    )
    document = json.loads(
        (ROOT / "examples" / "005-empty-canvas.svm.json").read_text(encoding="utf-8")
    )
    revisions = RevisionStore.create(document)
    pop_proposal = POPOutputAdapter().propose(
        AdapterRequest.from_store(
            revisions,
            revisions.head,
            ("document",),
            artifact_ids=(prefix.artifact_id, output.artifact_id),
            options={"namespace": "golden-p-real"},
        ),
        artifacts,
    )
    pop_revision = ProposalAcceptor().accept(revisions, pop_proposal, artifacts)
    structure = POPStructureAdapter().propose(
        AdapterRequest.from_store(
            revisions,
            pop_revision.revision_id,
            ("document",),
            artifact_ids=(prefix.artifact_id, output.artifact_id),
        ),
        artifacts,
    )
    dry_run = ProposalAcceptor().validate(revisions, structure, artifacts)
    accepted = ProposalAcceptor().accept(revisions, structure, artifacts)
    if dry_run != revisions.get_document(accepted.revision_id):
        raise RuntimeError("Golden Q dry-run differs from acceptance")

    snapshots = tuple(artifacts.get(item.artifact_id) for item in structure.preview_artifacts)
    by_type = {snapshot.media_type: snapshot for snapshot in snapshots}
    svg_snapshots = [snapshot for snapshot in snapshots if snapshot.media_type == "image/svg+xml"]
    normal = next(snapshot for snapshot in svg_snapshots if b'opacity="0.5"' in snapshot.content)
    xray = next(snapshot for snapshot in svg_snapshots if b'opacity="0.2"' in snapshot.content)
    files = {
        "normal.svg": normal,
        "xray.svg": xray,
        "coverage-masks.json": by_type[MASK_BUNDLE_MEDIA_TYPE],
        "topmost-coverage-analysis.json": by_type[ANALYSIS_MEDIA_TYPE],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, snapshot in files.items():
        (OUTPUT / filename).write_bytes(snapshot.content)
    manifest = {
        "schema_version": "svm-pop-golden-q-run-0.1",
        "source_revision_id": pop_revision.revision_id,
        "source_output_artifact_id": output.artifact_id,
        "proposal_id": structure.proposal_id,
        "accepted_revision_id": accepted.revision_id,
        "metrics": structure.report.metrics,
        "artifacts": {
            filename: {
                "artifact_id": snapshot.artifact_id,
                "content_hash": snapshot.content_hash,
                "byte_size": len(snapshot.content),
            }
            for filename, snapshot in files.items()
        },
        "accepted_document_sha256": hashlib.sha256(canonical_bytes(dry_run)).hexdigest(),
    }
    (OUTPUT / "run-manifest.json").write_bytes(canonical_bytes(manifest))
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
