"""Review identity evidence gaps without altering the raw geometry observations."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .run import CLASSIFICATION, PROFILE, bounded_read, digest, json_bytes, unknown_intervals

REVIEW_PROFILE = "studio-explicit-identity-reanchor@0.1"


def review(candidate_bytes: bytes, approvals: dict[str, Any]) -> dict[str, Any]:
    replay = json.loads(candidate_bytes)
    candidate_digest = digest(candidate_bytes)
    if replay.get("profile") != PROFILE or replay.get("artifact_classification") != CLASSIFICATION:
        raise ValueError("Expected the raw translation research candidate")
    if approvals.get("candidate_sha256") != candidate_digest:
        raise ValueError("Re-anchor decisions must reference the exact candidate hash")
    source_frames = replay["frames"]
    subjects = [item["id"] for item in replay["geometry"]]
    decisions = approvals.get("reanchors")
    if not isinstance(decisions, list):
        raise ValueError("Re-anchor decisions must be a list")
    by_tick = {}
    for item in decisions:
        if not isinstance(item, dict) or set(item) != {"subject", "tick", "point_xy"}:
            raise ValueError("Each re-anchor needs a subject, exact tick and point")
        key = (item["subject"], item["tick"])
        point = item["point_xy"]
        if (
            item["subject"] not in subjects
            or type(item["tick"]) is not int
            or key in by_tick
            or not isinstance(point, list)
            or len(point) != 2
            or any(type(value) is not int for value in point)
        ):
            raise ValueError("Invalid or duplicate re-anchor")
        by_tick[key] = point

    geometry = {item["id"]: item for item in replay["geometry"]}
    needs_anchor = set()
    used = set()
    output = copy.deepcopy(replay)
    for before, after in zip(source_frames, output["frames"], strict=True):
        for subject in subjects:
            entry = before["subjects"][subject]
            key = (subject, before["tick"])
            if entry["status"] == "UNKNOWN":
                needs_anchor.add(subject)
                continue
            if subject not in needs_anchor:
                continue
            if key not in by_tick:
                after["subjects"][subject] = {"status": "UNKNOWN", "reason": "needs_reanchor"}
                continue
            x, y = by_tick[key]
            left, top, _, _ = entry["bounds_xywh"]
            if not any(
                left + rx <= x < left + rx + width and top + ry <= y < top + ry + height
                for rx, ry, width, height in geometry[subject]["geometry_rectangles_xywh"]
            ):
                raise ValueError(f"Re-anchor point is outside observed subject {subject}")
            used.add(key)
            needs_anchor.remove(subject)
            after["subjects"][subject]["association"] = "user_reanchor"

    if used != set(by_tick):
        raise ValueError("Every re-anchor must select observable geometry after an evidence gap")
    output["unknown_tick_intervals_inclusive"] = {
        subject: unknown_intervals(output["frames"], subject) for subject in subjects
    }
    output["identity_review"] = {
        "profile": REVIEW_PROFILE,
        "raw_candidate_sha256": candidate_digest,
        "reanchors": decisions,
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reanchors", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        candidate = bounded_read(args.candidate, 4 * 1024 * 1024)
        approvals = (
            json.loads(bounded_read(args.reanchors, 16_384))
            if args.reanchors
            else {"candidate_sha256": digest(candidate), "reanchors": []}
        )
        rendered = json_bytes(review(candidate, approvals))
        with TemporaryDirectory(prefix=".identity-review-", dir=args.output.parent) as directory:
            staged = Path(directory) / "reviewed.json"
            staged.write_bytes(rendered)
            os.link(staged, args.output)
        print(digest(rendered))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
