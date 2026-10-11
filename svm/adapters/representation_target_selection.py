"""Spec81 B0-3: deterministic production packaging of certified targets.

Trusted host orchestration calls ``propose_from_store`` at its current HEAD.
The pure Adapter receives detached snapshots only; it cannot commit a Revision.
Selection bytes are staged data until the registered Composite is accepted.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict, replace

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactStore
from ..evaluator import canonical_bytes
from ..multipart_witness import RevisionSnapshotWitness, authenticate_witnesses, collect_witnesses
from ..proposals import AdapterRequest, GeneratorProvenance, PreviewArtifact, Proposal
from ..representation_target_consumer import POLICY_IDENTITY, Reason, derive_certified_targets
from ..representation_target_selection import (
    MEDIA,
    RepresentationTargetSelectionError,
    _json_data,
    _record_fields,
    _revision_data,
    _snapshot,
    evidence_payload,
)
from ..revisions import (
    ApplyRepresentationTargetSelectionChange,
    BindTemporalMotionTargetChange,
    RevisionStore,
    Transaction,
)
from .temporal_motion_target_binding import TemporalMotionTargetBindingAdapter

ADAPTER_ID = "adapter:representation-target-selection"


class RepresentationTargetSelectionAdapter:
    """Propose the complete independently derived pair, with no caller selectors.

    Like the existing witness-backed Adapters, this immutable-base interface
    permits deterministic rebuilding at an old base. Ordinary acceptance still
    requires HEAD. Use the host entry point below to capture the current base.
    ABSTAIN/REJECT raise the existing selection error with the structured Reason;
    they create neither a Proposal, a binding Change nor a selection Artifact.
    """

    adapter_id = ADAPTER_ID

    def propose(
        self,
        request: AdapterRequest,
        artifacts: ArtifactRepository,
        *,
        witnesses: tuple[RevisionSnapshotWitness, ...],
    ) -> Proposal:
        if (
            type(request) is not AdapterRequest
            or type(request.scope) is not tuple
            or any(type(item) is not str for item in request.scope)
            or request.scope != ("document",)
            or type(request.options) is not dict
            or request.options
            or type(request.artifact_ids) is not tuple
            or request.artifact_ids
        ):
            raise RepresentationTargetSelectionError(
                "Selection requires document scope and no selectors/options"
            )
        # Reuse the verifier's portable-record boundary before copying or hashing
        # caller snapshots. S0 still precedes all Document/transport checks.
        try:
            if (
                type(request.base_revision_id) is not str
                or not request.base_revision_id
                or type(witnesses) is not tuple
                or any(
                    type(witness) is not RevisionSnapshotWitness
                    or not _record_fields(witness, {"revision", "document"})
                    or not _revision_data(witness.revision)
                    or type(witness.document) is not dict
                    or not _json_data(witness.document)
                    for witness in witnesses
                )
            ):
                raise ValueError
            authenticated = authenticate_witnesses(request.base_revision_id, witnesses)
        except Exception as exc:
            raise RepresentationTargetSelectionError(Reason.HISTORY_BROKEN.value) from exc
        if type(request.document) is not dict or not _json_data(request.document):
            raise RepresentationTargetSelectionError(Reason.UNREPLAYABLE_ASSOCIATION.value)
        document = copy.deepcopy(request.document)
        detached_witnesses = tuple(authenticated[rid] for rid in sorted(authenticated))
        result = derive_certified_targets(
            request.base_revision_id, document, detached_witnesses, artifacts
        )
        if result.rejection_reason is not None:
            raise RepresentationTargetSelectionError(result.rejection_reason.value)
        if not result.selected_pairs:
            raise RepresentationTargetSelectionError(
                (result.abstention_reason or Reason.ZERO_SELECTED).value
            )
        content = canonical_bytes(
            evidence_payload(result, authenticated[request.base_revision_id].revision.document_hash)
        )
        tid, gid = result.selected_pairs[0]
        frozen = TemporalMotionTargetBindingAdapter().propose(
            replace(
                request,
                document=document,
                options={"temporal_identity_id": tid, "group_id": gid},
            ),
            artifacts,
        )
        if len(frozen.transaction.changes) != 1:
            raise RepresentationTargetSelectionError("Exactly one frozen binding is required")
        bind = frozen.transaction.changes[0]
        if type(bind) is not BindTemporalMotionTargetChange:
            raise RepresentationTargetSelectionError("The exact frozen binding is required")
        # Build everything locally before the single caller-repository write.
        # This scratch output grants no admission or accepted Reference authority.
        output = ArtifactStore().import_bytes(
            content,
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"policy_identity": POLICY_IDENTITY},
            locator=None,
        )
        reference = output.document_reference()
        change = ApplyRepresentationTargetSelectionChange(
            source_revision_id=request.base_revision_id,
            base_document_snapshot=document,
            witnesses=detached_witnesses,
            policy_identity=POLICY_IDENTITY,
            source_references=result.source_references,
            selection_evidence_reference=reference,
            delegated_binds=(bind,),
            selected_pairs=result.selected_pairs,
        )
        generator = GeneratorProvenance(ADAPTER_ID, "0.1", "svm", POLICY_IDENTITY)
        message = "Apply certified representation target selection"
        digest = hashlib.sha256(
            canonical_bytes(
                {
                    "generator": asdict(generator),
                    "change": asdict(change),
                    "transaction_message": message,
                }
            )
        ).hexdigest()
        proposal = Proposal(
            f"proposal:representation-target-selection:{digest}",
            request.base_revision_id,
            generator,
            Transaction(
                f"transaction:representation-target-selection:{digest}", (change,), message
            ),
            preview_artifacts=(
                PreviewArtifact(output.artifact_id, output.content_hash, MEDIA, reference["uri"]),
            ),
            preview=frozen.preview,
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
        )
        staged = artifacts.import_bytes(
            content,
            media_type=MEDIA,
            kind=ArtifactKind.DERIVED,
            provenance={"policy_identity": POLICY_IDENTITY},
            locator=None,
        )
        _snapshot(staged, reference)
        return proposal


def propose_from_store(store: RevisionStore, artifacts: ArtifactRepository) -> Proposal:
    """Host-only preparation from one captured current, genuinely accepted HEAD.

    Issuer trust belongs to the host's RevisionStore, not to hash consistency of
    caller history. The Adapter receives no store capability. A concurrent HEAD
    move is handled by the existing Acceptor's stale-base check.
    """
    base = store.head
    if base is None:
        raise RepresentationTargetSelectionError(Reason.HISTORY_BROKEN.value)
    request = AdapterRequest.from_store(store, base, ("document",))
    witnesses = copy.deepcopy(collect_witnesses(store, base))
    return RepresentationTargetSelectionAdapter().propose(request, artifacts, witnesses=witnesses)
