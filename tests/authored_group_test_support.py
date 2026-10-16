"""G2 test payloads and real upstream accepts; no production assembly Producer."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from svm import AdapterRequest, ArtifactStore, ProposalAcceptor, RevisionStore
from svm.adapters.component_promotion import ComponentPromotionAdapter
from svm.adapters.opencv_analysis import OpenCVAnalysisAdapter
from svm.document import DocumentDialect, validate_document
from svm.evaluator import canonical_bytes
from svm.proposals import GeneratorProvenance, Proposal
from svm.revisions import AssembleAuthoredGroupChange, Transaction

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = "svm-explicit-authored-group-assembly@0.1"
ACTOR = "adapter:authored-group-assembly"
EXTENSION = DocumentDialect.AUTHORED_GROUP_ASSEMBLY
NEUTRAL_TRANSFORM = {
    "translate": [0, 0],
    "rotation_degrees": 0,
    "scale": 1,
    "origin": [0, 0],
}


def make_accepted_base() -> tuple[RevisionStore, ArtifactStore]:
    """Four genuine promoted Entities from four ordinary Proposal accepts."""
    store = RevisionStore.create(
        json.loads((ROOT / "examples/005-empty-canvas.svm.json").read_bytes())
    )
    artifacts = ArtifactStore()
    for namespace, name in (
        ("authored-a", "006-opencv-analysis-source.png"),
        ("authored-b", "007-contained-components-source.png"),
    ):
        source = artifacts.import_bytes(
            (ROOT / "examples/assets" / name).read_bytes(), media_type="image/png"
        )
        analysis = OpenCVAnalysisAdapter().propose(
            AdapterRequest.from_store(
                store, store.head, ("document",), artifact_ids=(source.artifact_id,)
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, analysis, artifacts)
        evidence = artifacts.get(analysis.preview_artifacts[1].artifact_id)
        candidates = [c["candidate_id"] for c in json.loads(evidence.content)["components"]]
        promotion = ComponentPromotionAdapter().propose(
            AdapterRequest.from_store(
                store,
                store.head,
                ("document",),
                artifact_ids=(evidence.artifact_id,),
                options={"candidate_ids": candidates, "namespace": namespace},
            ),
            artifacts,
        )
        ProposalAcceptor().accept(store, promotion, artifacts)
    document = store.get_document(store.head)
    validate_document(document)
    if len(document["entities"]) != 4 or document.get("groups"):
        raise AssertionError("Expected four genuinely promoted inputs and no Group")
    store.upgrade_document_dialect(EXTENSION)
    return store, artifacts


def make_change(
    store: RevisionStore,
    members: tuple[str, ...] | list[str] | None = None,
    transform: dict[str, Any] | None = None,
) -> AssembleAuthoredGroupChange:
    """Derive the spec seed independently of production identity/verifier helpers."""
    document = store.get_document(store.head)
    selected = (
        tuple(sorted(e["id"] for e in document["entities"])[:2])
        if members is None
        else tuple(members)
    )
    witness = copy.deepcopy(store.revisions[store.head])
    digest = hashlib.sha256(
        canonical_bytes({"authority_identity": AUTHORITY, "members": list(selected)})
    ).hexdigest()
    group = {
        "id": "group:" + digest,
        "kind": "explicit-group",
        "members": list(selected),
        "provenance": {
            "type": "authored-group-assembly@0.1",
            "authority_identity": AUTHORITY,
            "source_revision_id": witness.revision_id,
            "source_document_hash": witness.document_hash,
            "membership_hash": "sha256:" + digest,
        },
    }
    if transform is not None:
        group["transform"] = copy.deepcopy(transform)
    return AssembleAuthoredGroupChange(
        witness.revision_id,
        AUTHORITY,
        copy.deepcopy(document),
        witness,
        selected,
        copy.deepcopy(transform),
        group,
    )


def make_proposal(store: RevisionStore, changes: tuple[Any, ...]) -> Proposal:
    """Test-built transport only; tests do not claim G3 Producer conformance."""
    changes = tuple(changes)
    # Keep transport construction independent of hostile nested test payloads.
    # G2 does not claim the future production Proposal ID algorithm.
    seed = {"base": store.head, "change_types": [type(c).__name__ for c in changes]}
    digest = hashlib.sha256(canonical_bytes(seed)).hexdigest()
    required = tuple(
        dict.fromkeys(ref["id"] for c in changes for ref in getattr(c, "references", ()))
    )
    return Proposal(
        "proposal:authored-g2-test:" + digest,
        store.head,
        GeneratorProvenance(ACTOR, "0.1", "G2 test payload", AUTHORITY),
        Transaction(
            "transaction:authored-g2-test:" + digest,
            changes,
            "G2 independent test-built assembly payload",
        ),
        required_artifact_ids=required,
    )


def snapshot(store: RevisionStore) -> RevisionStore:
    return copy.deepcopy(store)
