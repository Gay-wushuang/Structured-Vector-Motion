"""Author a user-selected continuous translation segment from a research replay."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import cv2

from svm.artifacts import ArtifactStore
from svm.cli import _validate_schema
from svm.evaluator import canonical_bytes
from svm.motion import MotionEvaluator
from svm.proposals import GeneratorProvenance, Proposal, ProposalAcceptor
from svm.revisions import (
    AddKeyframeChange,
    AppendReferencesChange,
    Change,
    CreateTrackChange,
    RevisionStore,
    Transaction,
)
from svm.studio import _empty, _shape
from svm.video_ingestion import _avi_metadata

from .anchors import review
from .fixture import FPS, FRAME_COUNT, TICK_RATE, make
from .run import (
    CLASSIFICATION,
    MAX_SOURCE_BYTES,
    bounded_read,
    digest,
    frames,
    json_bytes,
    observe,
    read_settings,
)

PROFILE = "studio-manually-authored-translation-segment@0.1"
MAX_CANDIDATE_BYTES = 4 * 1024 * 1024
MAX_EDITABLE_KEYS = 2_048


@dataclass(frozen=True)
class Prepared:
    preview_id: str
    base: RevisionStore
    proposal: Proposal
    document: dict[str, Any]
    report: dict[str, Any]
    artifacts: ArtifactStore


def _replay(source: bytes, candidate_bytes: bytes) -> dict[str, Any]:
    candidate = json.loads(candidate_bytes)
    if candidate.get("artifact_classification") != CLASSIFICATION:
        raise ValueError("Expected a research trajectory candidate")
    try:
        raw = json_bytes(observe(source, candidate["settings"]))
    except cv2.error as exc:
        raise ValueError("OpenCV failed while replaying the source video") from exc
    identity = candidate.get("identity_review")
    if identity is not None:
        decisions = {
            "candidate_sha256": identity["raw_candidate_sha256"],
            "reanchors": identity["reanchors"],
        }
        raw = json_bytes(review(raw, decisions))
    if raw != candidate_bytes:
        raise ValueError("Candidate does not replay byte for byte from the selected source")
    return candidate


def prepare(source_bytes: bytes, candidate_bytes: bytes, request: dict[str, Any]) -> Prepared:
    if set(request) != {"subject", "start_tick", "end_tick", "candidate_sha256"}:
        raise ValueError("Select a subject, start tick, end tick, and exact candidate digest")
    subject, start, end = request["subject"], request["start_tick"], request["end_tick"]
    if (
        not isinstance(subject, str)
        or type(start) is not int
        or type(end) is not int
        or start >= end
    ):
        raise ValueError("Select one subject and an increasing range of source ticks")
    if request["candidate_sha256"] != digest(candidate_bytes):
        raise ValueError("Selection must reference the exact candidate hash")
    candidate = _replay(source_bytes, candidate_bytes)
    geometry = next((item for item in candidate["geometry"] if item["id"] == subject), None)
    if geometry is None:
        raise ValueError("The selected subject does not exist")

    # Re-evaluate all earlier observations so a range cannot start just after
    # an unreviewed gap. Continuous evidence starts at a click or user re-anchor.
    frames = candidate["frames"]
    active = False
    selected = []
    for frame in frames:
        tick = frame["tick"]
        if tick > end:
            break
        observation = frame["subjects"][subject]
        association = observation.get("association")
        if observation["status"] != "OBSERVED" or association == "exact_shape_after_gap":
            active = False
        if association in {"first_frame_click", "user_reanchor"}:
            active = True
        if tick >= start:
            if not active:
                raise ValueError("Selected interval crosses an unknown or unreviewed evidence gap")
            selected.append((tick, observation["translation_xy"]))
    if len(selected) < 2 or selected[0][0] != start or selected[-1][0] != end:
        raise ValueError("Both endpoints must be exact observed source ticks")

    identity = digest(
        canonical_bytes(
            {
                "profile": PROFILE,
                "implementation_sha256": digest(Path(__file__).read_bytes()),
                "selection": request,
            }
        )
    )
    document = _empty()
    document["document_id"] = f"document:studio-authored-{identity[:24]}"
    base = RevisionStore.create(document)
    base_id = base.head
    assert base_id is not None
    tick_rate = candidate["settings"]["ticks_per_second"]
    origin_x, origin_y, _, _ = geometry["anchor_bounds_xywh"]
    fill = "#" + bytes(reversed(geometry["bgr24"])).hex()
    first_x, first_y = selected[0][1]
    rectangles = geometry["geometry_rectangles_xywh"]
    artifacts = ArtifactStore()
    source = artifacts.import_bytes(source_bytes, media_type="video/x-msvideo")
    changes: list[Change] = [AppendReferencesChange((source.document_reference(),))]
    for index, (x, y, width, height) in enumerate(rectangles):
        part = f"part-{identity[:24]}-{index}"
        parameters = {"x": x + origin_x, "y": y + origin_y, "width": width, "height": height}
        changes.append(
            _shape(
                part,
                f"{subject} · {index + 1}",
                "CreateRectangle",
                {**parameters, "x": parameters["x"] + first_x, "y": parameters["y"] + first_y},
                fill,
            )
        )
        for axis, parameter in enumerate(("x", "y")):
            values = [
                (tick - start, parameters[parameter] + sample[axis]) for tick, sample in selected
            ]
            if len({value for _, value in values}) == 1:
                continue
            track = f"track:{part}-{parameter}"
            changes.append(CreateTrackChange(track, f"op:{part}", parameter, tick_rate))
            changes.extend(
                AddKeyframeChange(track, f"keyframe:{part}-{parameter}-{tick}", tick, value)
                for tick, value in _linear_keys(values)
            )
    if all(value == selected[0][1] for _, value in selected):
        # Keep the exact duration and timebase for a stationary observed segment.
        part = f"part-{identity[:24]}-0"
        track = f"track:{part}-x"
        x = rectangles[0][0] + origin_x + first_x
        changes.extend(
            (
                CreateTrackChange(track, f"op:{part}", "x", tick_rate),
                AddKeyframeChange(track, f"keyframe:{part}-x-0", 0, x),
                AddKeyframeChange(track, f"keyframe:{part}-x-{end - start}", end - start, x),
            )
        )
    proposal = Proposal(
        f"proposal:studio-author:{identity}",
        base_id,
        GeneratorProvenance("editor:studio-segment", "0.1", "svm-core", PROFILE),
        Transaction(
            f"transaction:studio-author:{identity}", tuple(changes), "Author selected segment"
        ),
        required_artifact_ids=(source.artifact_id,),
        notes="Human selected translation samples; no formal temporal identity asserted.",
    )
    if sum(isinstance(change, AddKeyframeChange) for change in changes) > MAX_EDITABLE_KEYS:
        raise ValueError("Select a shorter or simpler segment with at most 2048 editable keyframes")
    authored = ProposalAcceptor().validate(base, proposal, artifacts)
    _validate_schema(authored)
    if authored["animation"]["content"]:
        evaluator = MotionEvaluator(authored)
        for tick, _ in selected:
            evaluator.evaluate(tick - start)
    return Prepared(
        identity,
        base,
        proposal,
        authored,
        {
            "profile": PROFILE,
            "candidate_classification": CLASSIFICATION,
            "source_sha256": digest(source_bytes),
            "source_artifact_id": source.artifact_id,
            "selection": request,
            "ticks_per_second": tick_rate,
            "source_ticks": [tick for tick, _ in selected],
            "document_start_tick": 0,
            "document_end_tick": end - start,
            "rectangle_count": len(rectangles),
            "track_count": len(authored["animation"]["content"]),
            "reviewed_unknown_intervals": candidate["unknown_tick_intervals_inclusive"],
        },
        artifacts,
    )


def _linear_keys(values: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result = [values[0]]
    for left, middle, right in zip(values, values[1:], values[2:], strict=False):
        if (middle[1] - left[1]) * (right[0] - middle[0]) != (right[1] - middle[1]) * (
            middle[0] - left[0]
        ):
            result.append(middle)
    result.append(values[-1])
    return result


def accept(prepared: Prepared, preview_id: str) -> dict[str, Any]:
    if preview_id != prepared.preview_id:
        raise ValueError("Confirmation must match the exact prepared preview")
    revision = ProposalAcceptor().accept(prepared.base, prepared.proposal, prepared.artifacts)
    return {
        "document": prepared.base.get_document(revision.revision_id),
        "revision": revision.revision_id,
        "report": {
            **prepared.report,
            "preview_id": preview_id,
            "proposal_id": prepared.proposal.proposal_id,
            "base_revision": prepared.proposal.base_revision_id,
            "revision": revision.revision_id,
            "document_hash": revision.document_hash,
        },
    }


def prepare_demo() -> Prepared:
    with TemporaryDirectory(prefix="studio-translation-demo-") as directory:
        fixture = Path(directory) / "fixture"
        make(fixture)
        source = bounded_read(fixture / "synthetic.avi", MAX_SOURCE_BYTES)
        candidate = json_bytes(observe(source, read_settings(fixture / "seeds.json")))
    return prepare(
        source,
        candidate,
        {
            "subject": "teal",
            "start_tick": 0,
            "end_tick": (FRAME_COUNT - 1) * TICK_RATE // FPS,
            "candidate_sha256": digest(candidate),
        },
    )


def inspect_source(source: bytes) -> dict[str, Any]:
    meta = _avi_metadata(source)
    rate = Fraction(*meta["source_fps"])
    decoded = frames(source, meta)
    try:
        first = next(decoded)
        success, png = cv2.imencode(".png", first)
    except cv2.error as exc:
        raise ValueError("Cannot decode the first FFV1 frame") from exc
    finally:
        decoded.close()
    if not success:
        raise ValueError("Cannot render the first frame")
    return {
        "width": meta["width"],
        "height": meta["height"],
        "frameCount": meta["frame_count"],
        "fps": [rate.numerator, rate.denominator],
        "image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
    }


def analyze_source(source: bytes, x: int, y: int) -> tuple[bytes, dict[str, Any]]:
    meta = _avi_metadata(source)
    tick_rate = meta["source_fps"][0]
    settings = {
        "ticks_per_second": tick_rate,
        "max_translation_px_per_frame": 32,
        "subjects": [{"id": "subject", "point_xy": [x, y]}],
    }
    try:
        result = observe(source, settings)
    except cv2.error as exc:
        raise ValueError("Cannot analyze the selected FFV1 clip") from exc
    possible = []
    for from_start in result["frames"]:
        frame = from_start["subjects"]["subject"]
        if frame["status"] != "OBSERVED" or frame.get("association") == "exact_shape_after_gap":
            break
        possible.append(from_start["tick"])
    return json_bytes(result), {
        "observedTicks": possible,
        "sampleCount": len(result["frames"]),
        "unknown": result["unknown_tick_intervals_inclusive"]["subject"],
    }


def _publish(output: Path, result: dict[str, Any]) -> None:
    with TemporaryDirectory(prefix=".author-translation-", dir=output.parent) as directory:
        staged = Path(directory) / "segment"
        staged.mkdir()
        receipt = "receipt.json"
        document = "authored.svm.json"
        (staged / document).write_bytes(json_bytes(result["document"]))
        (staged / receipt).write_bytes(json_bytes(result["report"]))
        output.mkdir()
        try:
            os.link(staged / receipt, output / receipt)
            # Publish the native document only when its receipt is present.
            os.link(staged / document, output / document)
        except OSError:
            (output / receipt).unlink(missing_ok=True)
            output.rmdir()
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--accept", help="Exact preview ID previously shown")
    parser.add_argument(
        "--output", type=Path, help="Fresh output directory for the accepted project"
    )
    args = parser.parse_args()
    try:
        if (args.accept is None) != (args.output is None):
            raise ValueError("Provide both --accept and --output to create an authored project")
        source = bounded_read(args.input, MAX_SOURCE_BYTES)
        candidate = bounded_read(args.candidate, MAX_CANDIDATE_BYTES)
        request = json.loads(bounded_read(args.selection, 4096))
        prepared = prepare(source, candidate, request)
        if args.accept is None:
            print(json_bytes({**prepared.report, "preview_id": prepared.preview_id}).decode())
            return 0
        result = accept(prepared, args.accept)
        _publish(args.output, result)
        print(json_bytes(result["report"]).decode())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
