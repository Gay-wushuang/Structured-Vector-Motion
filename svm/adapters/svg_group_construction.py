"""Closed-world Spec/73 replay. No temporal association or generic profile dispatch."""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import asdict
from typing import Any
from xml.parsers import expat

from ..artifacts import ArtifactKind, ArtifactRepository, ArtifactSnapshot, ArtifactStore
from ..evaluator import Evaluator, canonical_bytes
from ..operations import _geometry_bounds
from ..proposals import (
    AdapterRequest,
    ConstructionGroupDefinitionPreview,
    GeneratorProvenance,
    Proposal,
    ProposalPreview,
)
from ..revisions import (
    AppendSceneFragmentChange,
    EstablishSVGGroupChange,
    Revision,
    RevisionStore,
    Transaction,
)
from ..scene import _canonical_scene_number

AUTHORITY = "svm-construction-derived-group@0.1"
PROFILE = "svm-svg-two-part-group-construction@0.1"
ORIGIN = "construction-established-group@0.1"
MANIFEST_MEDIA = "application/vnd.svm.group-construction-manifest+json;version=0.1"
RECEIPT_MEDIA = "application/vnd.svm.svg-two-part-group-establishment+json;version=0.1"


class SVGGroupConstructionError(ValueError):
    pass


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _source_reference(document: dict[str, Any]) -> dict[str, Any]:
    sources = [
        ref
        for ref in document["references"]
        if ref["media_type"] in {"image/svg+xml", "application/svg+xml"}
        and ref["import_metadata"].get("artifact_kind") == ArtifactKind.REFERENCE
    ]
    if len(sources) != 1:
        raise SVGGroupConstructionError("Exactly one accepted SVG reference required")
    ref = sources[0]
    if (
        ref["media_type"] != "image/svg+xml"
        or ref["import_metadata"].get("artifact_kind") != ArtifactKind.REFERENCE
    ):
        raise SVGGroupConstructionError("Profile requires image/svg+xml ReferenceArtifact")
    return ref


def _parameters(content: bytes) -> tuple[dict[str, float], ...]:
    if len(content) > 65536 or content.startswith(b"\xef\xbb\xbf"):
        raise SVGGroupConstructionError("SVG exceeds profile byte limit or has BOM")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SVGGroupConstructionError("Profile requires UTF-8") from exc
    if any(token in text for token in ("<!", "<?", "&")):
        raise SVGGroupConstructionError("SVG declarations/references are outside profile")
    nodes: list[tuple[str, int, dict[str, str]]] = []
    depth = 0

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth
        if len(nodes) >= 4 or depth > 2:
            raise SVGGroupConstructionError("SVG tree is outside profile")
        nodes.append((name, depth, attrs))
        depth += 1

    def end(name: str) -> None:
        nonlocal depth
        depth -= 1

    def characters(data: str) -> None:
        if data.strip():
            raise SVGGroupConstructionError("SVG text is outside profile")

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = characters
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        raise SVGGroupConstructionError("Malformed profile SVG") from exc
    if [(name, level) for name, level, _ in nodes] != [
        ("svg", 0),
        ("g", 1),
        ("rect", 2),
        ("ellipse", 2),
    ]:
        raise SVGGroupConstructionError("Expected sole g with rect then ellipse")
    if nodes[0][2] != {"xmlns": "http://www.w3.org/2000/svg"} or nodes[1][2]:
        raise SVGGroupConstructionError("SVG root/group attributes are outside profile")
    result = []
    for (_, _, attrs), fields, positive in zip(
        nodes[2:],
        (("x", "y", "width", "height"), ("cx", "cy", "rx", "ry")),
        (("width", "height"), ("rx", "ry")),
        strict=True,
    ):
        if set(attrs) != set(fields):
            raise SVGGroupConstructionError("SVG leaf attributes are outside profile")
        values = {}
        for field in fields:
            raw = attrs[field]
            if re.fullmatch(r"(?:0|-?[1-9][0-9]{0,6})", raw) is None or abs(int(raw)) > 1_000_000:
                raise SVGGroupConstructionError("Noncanonical/out-of-range profile number")
            values[field] = float(raw)
        if any(values[field] <= 0 for field in positive):
            raise SVGGroupConstructionError("Degenerate profile geometry")
        result.append(values)
    return tuple(result)


def _authenticate(change: EstablishSVGGroupChange) -> None:
    witness = change.base_revision
    if type(witness) is not Revision:
        raise SVGGroupConstructionError("Construction requires an existing-format Revision witness")
    reproduced = RevisionStore._make_revision(
        change.base_document_snapshot, witness.parent_ids, witness.transaction_id, witness.message
    )
    if reproduced != witness or reproduced.revision_id != change.source_revision_id:
        raise SVGGroupConstructionError("Construction base Revision witness mismatch")


def _derive(
    document: dict[str, Any],
    revision: Revision,
    source: ArtifactSnapshot,
    artifacts: ArtifactRepository,
) -> EstablishSVGGroupChange:
    reference = _source_reference(document)
    digest = hashlib.sha256(source.content).hexdigest()
    if (
        source.artifact_id != f"artifact:{digest}"
        or source.content_hash != f"sha256:{digest}"
        or canonical_bytes(source.document_reference()) != canonical_bytes(reference)
    ):
        raise SVGGroupConstructionError("Source bytes/descriptor mismatch")
    parameters = _parameters(source.content)
    subject = {"source_artifact_id": source.artifact_id, "subject_path": [0]}
    entities, operations, bindings, styles = [], [], [], []
    for key, name, operation_type, params in zip(
        ("rect:0", "ellipse:1"),
        ("rect-1", "ellipse-2"),
        ("CreateRectangle", "CreateEllipse"),
        parameters,
        strict=True,
    ):
        allocation = {
            "authority_identity": AUTHORITY,
            "profile_identity": PROFILE,
            "subject": subject,
            "part_key": key,
        }
        eid = "entity:" + _hash({**allocation, "record_kind": "entity"})
        oid = "op:" + _hash({**allocation, "record_kind": "operation", "role": "geometry"})
        entities.append({"id": eid, "name": name})
        operations.append({"id": oid, "type": operation_type, "inputs": {}, "parameters": params})
        bindings.append({"entity": eid, "property": "geometry", "slot": f"{oid}.geometry"})
        styles.append(
            {
                "entity": eid,
                "fill": "#000000",
                "stroke": "none",
                "stroke_width": 1.0,
                "opacity": 1.0,
            }
        )
    fragment = AppendSceneFragmentChange(
        tuple(entities),
        tuple(operations),
        tuple(bindings),
        tuple(e["id"] for e in entities),
        tuple(styles),
    )
    # Use ordinary registered Operation evaluation and geometry bounds, not a second model.
    geometry_document = copy.deepcopy(document)
    fragment.apply(geometry_document)
    evaluator = Evaluator(geometry_document)
    bounds = []
    for operation in operations:
        evaluator.evaluate(operation["id"])
        outputs = evaluator.runtime[operation["id"]].outputs
        if outputs is None:
            raise SVGGroupConstructionError("Constructed geometry did not evaluate")
        bounds.append(list(_geometry_bounds(outputs["geometry"].payload)))
    manifest = {
        "schema_version": "svm-group-construction-manifest-0.1",
        "authority_identity": AUTHORITY,
        "profile_identity": PROFILE,
        "source_base_revision_id": revision.revision_id,
        "source_base_document_hash": revision.document_hash,
        "subject": subject,
        "parameters": {},
        "source_references": [reference],
        "fragment": asdict(fragment),
        "member_bounds": bounds,
    }
    provenance = {"authority_identity": AUTHORITY, "profile_identity": PROFILE}
    construction = artifacts.import_bytes(
        canonical_bytes(manifest),
        media_type=MANIFEST_MEDIA,
        kind=ArtifactKind.DERIVED,
        provenance=provenance,
    )
    members = sorted(e["id"] for e in entities)
    group = {
        "id": "group:" + _hash({**provenance, "members": members}),
        "kind": "explicit-group",
        "members": members,
        "provenance": {
            "type": ORIGIN,
            **provenance,
            "construction_artifact_id": construction.artifact_id,
        },
        "transform": {
            "translate": [0, 0],
            "rotation_degrees": 0,
            "scale": 1,
            "origin": [
                _canonical_scene_number(
                    (min(b[i] for b in bounds) + max(b[i + 2] for b in bounds)) / 2
                )
                for i in (0, 1)
            ],
        },
    }
    receipt = artifacts.import_bytes(
        canonical_bytes(
            {
                "schema_version": "svm-svg-two-part-group-establishment-0.1",
                **provenance,
                "source_base_revision_id": revision.revision_id,
                "source_base_document_hash": revision.document_hash,
                "source_references": [reference],
                "subject": subject,
                "fragment": asdict(fragment),
                "construction_reference": construction.document_reference(),
                "group": group,
                "representation_claim": None,
            }
        ),
        media_type=RECEIPT_MEDIA,
        kind=ArtifactKind.DERIVED,
        provenance=provenance,
    )
    change = EstablishSVGGroupChange(
        revision.revision_id,
        copy.deepcopy(document),
        revision,
        PROFILE,
        fragment,
        group,
        (copy.deepcopy(reference), construction.document_reference(), receipt.document_reference()),
    )
    _authenticate(change)
    change.apply(copy.deepcopy(document))
    return change


def verify_change(change: EstablishSVGGroupChange, resolved: dict[str, ArtifactSnapshot]) -> None:
    if change.profile_identity != PROFILE or type(change.fragment) is not AppendSceneFragmentChange:
        raise SVGGroupConstructionError("Unknown construction profile or fragment type")
    _authenticate(change)
    source_ref = _source_reference(change.base_document_snapshot)
    scratch = ArtifactStore()
    expected = _derive(
        change.base_document_snapshot, change.base_revision, resolved[source_ref["id"]], scratch
    )
    if canonical_bytes(asdict(change)) != canonical_bytes(asdict(expected)):
        raise SVGGroupConstructionError("Construction output does not reproduce")
    for reference in expected.references[1:]:
        actual = resolved[reference["id"]]
        wanted = scratch.resolve_reference(reference)
        if actual.content != wanted.content or canonical_bytes(
            actual.document_reference()
        ) != canonical_bytes(reference):
            raise SVGGroupConstructionError("Construction evidence does not reproduce")


class SVGGroupConstructionAdapter:
    adapter_id = "adapter:svg-group-construction"

    def propose(
        self, request: AdapterRequest, artifacts: ArtifactRepository, *, base_revision: Revision
    ) -> Proposal:
        if request.options or request.artifact_ids or request.scope not in {(), ("document",)}:
            raise SVGGroupConstructionError(
                "Construction accepts document scope and no selectors/options"
            )
        if request.base_revision_id != base_revision.revision_id:
            raise SVGGroupConstructionError("Request base differs from Revision witness")
        reference = _source_reference(request.document)
        change = _derive(
            request.document, base_revision, artifacts.resolve_reference(reference), artifacts
        )
        digest = _hash(asdict(change))
        return Proposal(
            proposal_id=f"proposal:svg-group:{digest}",
            base_revision_id=request.base_revision_id,
            generator=GeneratorProvenance(self.adapter_id, "0.1", "svm", PROFILE),
            transaction=Transaction(
                f"transaction:svg-group:{digest}", (change,), "Establish SVG artwork Group"
            ),
            required_artifact_ids=tuple(ref["id"] for ref in change.references),
            preview=ProposalPreview(
                proposed_render_stack=tuple(request.document["presentation"]["render_stack"])
                + change.fragment.render_entries,
                group_definitions=(
                    ConstructionGroupDefinitionPreview(
                        change.group["id"],
                        tuple(change.group["members"]),
                        "explicit-group",
                        copy.deepcopy(change.group["provenance"]),
                        copy.deepcopy(change.group["transform"]),
                    ),
                ),
            ),
        )
