"""Spec82 G3: deterministic Producer for one explicit authored Group.

The Producer derives exactly one `AssembleAuthoredGroupChange` from a genuine
Base request and its complete Revision metadata. It holds no authority: the
registered G2 verifier and the ProposalAcceptor authenticate every field. No
Artifact, Evidence, preview Artifact or required Artifact ID is produced, and no
Entity, TemporalIdentity, MotionTargetBinding, Track, Render Stack entry or
Scene geometry is created, modified or inferred.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any, NoReturn

from ..artifacts import ArtifactRepository
from ..document import (
    AUTHORED_GROUP_AUTHORITY,
    AUTHORED_GROUP_TYPE,
    _validate_group_transform,
    authored_group_identity,
)
from ..evaluator import DocumentError, canonical_bytes
from ..proposals import AdapterRequest, GeneratorProvenance, Proposal
from ..revisions import (
    AdmittedRevision,
    AssembleAuthoredGroupChange,
    Revision,
    RevisionStore,
    Transaction,
)

ADAPTER_ID = "adapter:authored-group-assembly"
ADAPTER_VERSION = "0.1"
CHANGE_IDENTITY = "svm.revisions.AssembleAuthoredGroupChange@0.1"
ENGINE = "svm-authored-group-assembly"
TRANSACTION_MESSAGE = "Assemble explicitly authored Group"
_OPTION_KEYS = frozenset({"members", "transform"})


class AuthoredGroupAssemblyError(ValueError):
    """Producer-side rejection; never an acceptance or authority claim."""


def _fail(message: str) -> NoReturn:
    raise AuthoredGroupAssemblyError(message)


def _authenticate(change: AssembleAuthoredGroupChange) -> None:
    """Fail fast when the supplied metadata is not the real Base commitment.

    This mirrors the existing construction Adapters; it grants no authority and
    the registered verifier repeats the real check at acceptance time.
    """
    witness = change.base_revision
    if type(witness) not in {Revision, AdmittedRevision}:
        _fail("Authored assembly requires an existing-format Revision witness")
    reproduced = RevisionStore._make_revision(
        change.base_document_snapshot,
        witness.parent_ids,
        witness.transaction_id,
        witness.message,
        witness.admissions if type(witness) is AdmittedRevision else (),
    )
    if reproduced != witness or reproduced.revision_id != change.source_revision_id:
        _fail("Authored assembly Base Revision witness mismatch")


def _members(document: dict[str, Any], options: dict[str, Any]) -> tuple[str, ...]:
    raw = options["members"]
    if (
        type(raw) is not list
        or len(raw) < 2
        or any(type(member) is not str or not member.startswith("entity:") for member in raw)
    ):
        _fail("Authored assembly members must be >=2 existing Entity IDs")
    if len(set(raw)) != len(raw):
        _fail("Authored assembly members must be distinct, not silently deduplicated")
    accepted = {entity["id"] for entity in document.get("entities", [])}
    if any(member not in accepted for member in raw):
        _fail("Authored assembly member is absent from the accepted Base")
    return tuple(sorted(raw))


def _transform(options: dict[str, Any]) -> dict[str, Any] | None:
    value = options["transform"]
    if value is None:
        return None
    if type(value) is not dict:
        _fail("Authored assembly transform must be null or an exact transform object")
    try:
        _validate_group_transform(copy.deepcopy(value))
    except DocumentError as exc:
        raise AuthoredGroupAssemblyError(
            "Authored assembly transform is not a legal Group transform"
        ) from exc
    return copy.deepcopy(value)


def _derive(
    document: dict[str, Any],
    revision: Revision,
    members: tuple[str, ...],
    transform: dict[str, Any] | None,
) -> AssembleAuthoredGroupChange:
    group_id, membership_hash = authored_group_identity(list(members))
    group: dict[str, Any] = {
        "id": group_id,
        "kind": "explicit-group",
        "members": list(members),
        "provenance": {
            "type": AUTHORED_GROUP_TYPE,
            "authority_identity": AUTHORED_GROUP_AUTHORITY,
            "source_revision_id": revision.revision_id,
            "source_document_hash": revision.document_hash,
            "membership_hash": membership_hash,
        },
    }
    if transform is not None:
        group["transform"] = copy.deepcopy(transform)
    change = AssembleAuthoredGroupChange(
        revision.revision_id,
        AUTHORED_GROUP_AUTHORITY,
        copy.deepcopy(document),
        revision,
        members,
        copy.deepcopy(transform),
        group,
    )
    _authenticate(change)
    return change


def _proposal_digest(change: AssembleAuthoredGroupChange) -> str:
    """Spec82 §6 deterministic seed; a label, never an authority proof."""
    return hashlib.sha256(
        canonical_bytes(
            {
                "change_identity": CHANGE_IDENTITY,
                "source_revision_id": change.source_revision_id,
                "group": change.group,
            }
        )
    ).hexdigest()


class AuthoredGroupAssemblyAdapter:
    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def propose(
        self,
        request: AdapterRequest,
        artifacts: ArtifactRepository,
        *,
        base_revision: Revision,
    ) -> Proposal:
        """Derive one Change from a genuine Base request and its Revision metadata.

        ``artifacts`` is accepted to match the existing Adapter architecture but
        is never read: this authority consumes no Artifact bytes or Evidence.
        """
        if (
            type(request) is not AdapterRequest
            or type(request.scope) is not tuple
            or any(type(item) is not str for item in request.scope)
            or request.scope not in {(), ("document",)}
        ):
            _fail("Authored assembly accepts document scope and no selectors")
        if (
            type(request.options) is not dict
            or set(request.options) != _OPTION_KEYS
            or request.artifact_ids
        ):
            _fail("Authored assembly accepts exactly members and transform, with no Artifacts")
        if type(base_revision) not in {Revision, AdmittedRevision}:
            _fail("Authored assembly requires a complete Revision witness")
        if request.base_revision_id != base_revision.revision_id:
            _fail("Request base differs from the Revision witness")
        members = _members(request.document, request.options)
        transform = _transform(request.options)
        change = _derive(request.document, base_revision, members, transform)
        digest = _proposal_digest(change)
        return Proposal(
            proposal_id=f"proposal:authored-group-assembly:{digest}",
            base_revision_id=request.base_revision_id,
            generator=GeneratorProvenance(
                self.adapter_id,
                self.adapter_version,
                ENGINE,
                AUTHORED_GROUP_AUTHORITY,
                {
                    "authority_identity": AUTHORED_GROUP_AUTHORITY,
                    "members": list(members),
                    "transform": copy.deepcopy(transform),
                },
            ),
            transaction=Transaction(
                f"transaction:authored-group-assembly:{digest}", (change,), TRANSACTION_MESSAGE
            ),
            required_artifact_ids=(),
        )


def propose_from_store(
    store: RevisionStore,
    artifacts: ArtifactRepository,
    *,
    members: list[str],
    transform: dict[str, Any] | None = None,
) -> Proposal:
    """Host-only convenience: capture the real current HEAD and its Revision."""
    base = store.head
    if base is None:
        _fail("Authored assembly requires an accepted Base Revision")
    revision = copy.deepcopy(store.revisions[base])
    request = AdapterRequest.from_store(
        store,
        base,
        ("document",),
        options={"members": list(members), "transform": copy.deepcopy(transform)},
    )
    return AuthoredGroupAssemblyAdapter().propose(request, artifacts, base_revision=revision)
