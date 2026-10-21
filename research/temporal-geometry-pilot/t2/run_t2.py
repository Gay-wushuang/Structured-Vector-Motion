"""T2-P1 experiment runner: isolated B/C workers, offline GT evaluation, manifests.

The runner is the only place where the offline ground-truth path is known. It
writes Method B/C raw output first, then loads GT and computes metrics. Runtime
workers are separate processes launched from ``runtime.py`` and never receive a
GT path.

Usage:
    python research/temporal-geometry-pilot/t2/run_t2.py --all
    python research/temporal-geometry-pilot/t2/run_t2.py \
        --config research/temporal-geometry-pilot/t2/experiment-f1.json \
        --output research/temporal-geometry-pilot/t2/runs/t2-f1-translation-v1
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

T2_ROOT = Path(__file__).resolve().parent
PILOT_ROOT = T2_ROOT.parent
REPO_ROOT = T2_ROOT.parents[2]
sys.path.insert(0, str(T2_ROOT))
sys.path.insert(0, str(PILOT_ROOT))

import gt_eval  # noqa: E402
import run_experiment as t1  # noqa: E402
import runtime  # noqa: E402

RUN_MANIFEST_SCHEMA = "t2-group-anchor-run-manifest-0.1"
COSTS_SCHEMA = "t2-group-anchor-costs-0.1"
CANONICAL_SCHEMA = "t2-canonical-snapshot-manifest-0.1"

FIXTURES = (
    ("f1-translation", "experiment-f1.json", "t2-f1-translation-v1"),
    ("f2-rotation-scale", "experiment-f2.json", "t2-f2-rotation-scale-v1"),
    ("f3-low-texture", "experiment-f3.json", "t2-f3-low-texture-v1"),
    ("f4-occlusion", "experiment-f4.json", "t2-f4-occlusion-v1"),
    ("f5-conflicting-anchors", "experiment-f5.json", "t2-f5-conflicting-anchors-v1"),
)

T1_CANONICAL = (
    PILOT_ROOT / "runs" / "t1-controlled-raster-ab-v1-canonical" / "canonical-manifest.json"
)
T1_RUNNER = PILOT_ROOT / "run_experiment.py"
T1_CONFIG = PILOT_ROOT / "experiment.json"


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def repository_state(repo_root: Path) -> dict[str, Any]:
    dirty = bool(_git(repo_root, "status", "--porcelain"))
    return {
        "branch": _git(repo_root, "branch", "--show-current"),
        "checked_out_head": _git(repo_root, "rev-parse", "HEAD"),
        "worktree_dirty": dirty,
        "worktree_dirty_note": (
            "T2-P1 artifacts are new during the run; T1 canonical hashes are verified "
            "separately and no T1 path is written."
        ),
    }


def verify_t1_snapshot() -> dict[str, Any]:
    manifest = json.loads(T1_CANONICAL.read_text(encoding="utf-8"))
    root = T1_CANONICAL.parent
    mismatches = []
    verified = []
    for relative_path, expected in manifest["canonical_snapshot_contents"]["files"].items():
        actual = runtime.sha256_file(root / relative_path)
        verified.append({"path": relative_path, "expected": expected, "actual": actual})
        if actual != expected:
            mismatches.append(relative_path)
    return {
        "canonical_manifest": T1_CANONICAL.relative_to(REPO_ROOT).as_posix(),
        "canonical_manifest_sha256": runtime.sha256_file(T1_CANONICAL),
        "files": verified,
        "mismatches": mismatches,
        "passed": not mismatches,
        "status": "UNCHANGED" if not mismatches else "CHANGED",
    }


def _guard_output(path: Path, force: bool) -> Path:
    resolved = path.resolve()
    runs_root = (T2_ROOT / "runs").resolve()
    if resolved != runs_root and runs_root not in resolved.parents:
        raise runtime.T2Error(f"output must stay under {runs_root}: {resolved}")
    if "t1-" in resolved.name:
        raise runtime.T2Error("refusing to write a T1 run path")
    if resolved.exists() and any(resolved.iterdir()) and not force:
        raise runtime.T2Error(f"output already exists (use --force): {resolved}")
    if resolved.exists() and force:
        shutil.rmtree(resolved)
    return resolved


def _run_worker(
    method: str, config_path: Path, repo_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    completed = subprocess.run(
        [
            sys.executable,
            str(T2_ROOT / "runtime.py"),
            "--worker",
            method,
            "--config",
            str(config_path),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise runtime.T2Error(
            f"isolated worker {method} failed: {completed.stderr.decode('utf-8', 'replace')}"
        )
    payload = json.loads(completed.stdout)
    return payload["raw"], payload["cost"]


def _write_json(path: Path, value: Any) -> bytes:
    content = runtime.pretty_bytes(value)
    path.write_bytes(content)
    return content


def _input_paths(loaded: dict[str, Any]) -> list[tuple[str, Path]]:
    config = loaded["config"]
    items = []
    for entry in config["frames"]:
        items.append((f"frame:{entry['index']}", loaded["fixture_root"] / entry["path"]))
    items.append(("ground_truth", loaded["fixture_root"] / "ground-truth.json"))
    return items


def prepare_fixture(
    config_path: Path,
    output_dir: Path,
    repo_root: Path,
    force: bool,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    repo_root = repo_root.resolve()
    output_dir = _guard_output(output_dir, force)
    loaded = runtime.load_config(config_path, repo_root)
    frames = runtime.load_runtime_frames(loaded)

    raw_b, cost_b = _run_worker("B", config_path, repo_root)
    raw_c, cost_c = _run_worker("C", config_path, repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "raw").mkdir(parents=True, exist_ok=True)
    raw_b_bytes = _write_json(output_dir / "raw" / "method-b.json", raw_b)
    raw_c_bytes = _write_json(output_dir / "raw" / "method-c.json", raw_c)

    raw_b_second, cost_b_second = _run_worker("B", config_path, repo_root)
    raw_c_second, cost_c_second = _run_worker("C", config_path, repo_root)
    raw_b_second_bytes = runtime.pretty_bytes(raw_b_second)
    raw_c_second_bytes = runtime.pretty_bytes(raw_c_second)

    gt = gt_eval.load_ground_truth(loaded)
    gt_eval.verify_fixture_frames(gt, frames)
    metrics = gt_eval.build_metrics(raw_b, raw_c, frames, gt, loaded["config"])
    metrics_second = gt_eval.build_metrics(raw_b_second, raw_c_second, frames, gt, loaded["config"])
    metrics_identical = runtime.canonical_bytes(metrics) == runtime.canonical_bytes(metrics_second)
    fixture_id = Path(loaded["config"]["fixture_root"]).name
    evaluation = gt_eval.evaluate_fixture(fixture_id, metrics, runtime.FROZEN_DECISION_THRESHOLDS)
    metrics["fixture_evaluation"] = evaluation
    metrics_bytes = _write_json(output_dir / "metrics.json", metrics)

    downstream = gt_eval.verify_downstream_reproducibility(
        raw_b, raw_c, frames, gt, loaded["config"]
    )
    full_run = {
        "raw_method_b_byte_identical": raw_b_bytes == raw_b_second_bytes,
        "raw_method_c_byte_identical": raw_c_bytes == raw_c_second_bytes,
        "metrics_byte_identical": metrics_identical,
        "raw_method_b_sha256_run1": runtime.sha256_bytes(raw_b_bytes),
        "raw_method_b_sha256_run2": runtime.sha256_bytes(raw_b_second_bytes),
        "raw_method_c_sha256_run1": runtime.sha256_bytes(raw_c_bytes),
        "raw_method_c_sha256_run2": runtime.sha256_bytes(raw_c_second_bytes),
        "metrics_sha256_run1": runtime.sha256_bytes(metrics_bytes),
    }
    full_run["byte_identical"] = all(
        (
            full_run["raw_method_b_byte_identical"],
            full_run["raw_method_c_byte_identical"],
            full_run["metrics_byte_identical"],
        )
    )
    reproducibility = {
        "schema_version": gt_eval.REPRO_SCHEMA,
        "artifact_classification": runtime.CLASSIFICATION,
        "scope": (
            "full isolated B/C runs plus deterministic downstream metrics and comparison rendering"
        ),
        "downstream": downstream,
        "full_run": full_run,
        "passed": bool(downstream["passed"] and full_run["byte_identical"]),
    }
    _write_json(output_dir / "reproducibility.json", reproducibility)

    comparison_frames = gt_eval.render_comparison_frames(raw_b, raw_c, frames, gt)
    t1.write_video(output_dir / "comparison.avi", comparison_frames)

    costs = {
        "schema_version": COSTS_SCHEMA,
        "artifact_classification": runtime.CLASSIFICATION,
        "method_b": cost_b,
        "method_c": cost_c,
        "second_run_sanity": {
            "method_b_wall_time_seconds": cost_b_second["wall_time_seconds"],
            "method_c_wall_time_seconds": cost_c_second["wall_time_seconds"],
        },
        "cost_ratio_c_over_b": (
            float(cost_c["wall_time_seconds"]) / float(cost_b["wall_time_seconds"])
            if cost_b["wall_time_seconds"]
            else None
        ),
    }
    _write_json(output_dir / "costs.json", costs)
    return {
        "fixture_id": fixture_id,
        "experiment_id": loaded["config"]["experiment_id"],
        "config_path": config_path,
        "output_dir": output_dir,
        "loaded": loaded,
        "metrics": metrics,
        "evaluation": evaluation,
        "cost_b": cost_b,
        "cost_c": cost_c,
        "reproducibility": reproducibility,
        "determinism": {
            "full_run_byte_identical": full_run["byte_identical"],
            "downstream_passed": bool(downstream["passed"]),
            "raw_method_b_byte_identical": full_run["raw_method_b_byte_identical"],
            "raw_method_c_byte_identical": full_run["raw_method_c_byte_identical"],
            "metrics_byte_identical": full_run["metrics_byte_identical"],
        },
        "t1_snapshot": verify_t1_snapshot(),
    }


def _wheel_provenance() -> dict[str, Any]:
    manifest = json.loads(T1_CANONICAL.read_text(encoding="utf-8"))
    declared = manifest["declared_environment"]
    return {
        "numpy_wheel_sha256": declared["numpy_wheel_sha256"],
        "opencv_wheel_sha256": declared["opencv_wheel_sha256"],
        "provenance": (
            "T1.1 canonical manifest; both wheels were re-downloaded from the configured "
            "index, sha256-verified, and unpacked outside the repository for T2-P1"
        ),
    }


def build_manifest(
    result: dict[str, Any], decision: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    output_dir = result["output_dir"]
    loaded = result["loaded"]
    config_path = result["config_path"]
    output_names = [
        "raw/method-b.json",
        "raw/method-c.json",
        "metrics.json",
        "costs.json",
        "reproducibility.json",
        "comparison.avi",
    ]
    environment = runtime.environment_report()
    environment["wheel_provenance"] = _wheel_provenance()
    return {
        "schema_version": RUN_MANIFEST_SCHEMA,
        "artifact_classification": runtime.CLASSIFICATION,
        "experiment_id": result["experiment_id"],
        "runner_identity": runtime.RUNNER_IDENTITY,
        "repository": repository_state(repo_root),
        "environment": environment,
        "fixed_protocol": {
            "config_path": config_path.relative_to(repo_root).as_posix(),
            "config_sha256": runtime.sha256_file(config_path),
            "runtime_path": (T2_ROOT / "runtime.py").relative_to(repo_root).as_posix(),
            "runtime_sha256": runtime.sha256_file(T2_ROOT / "runtime.py"),
            "gt_eval_path": (T2_ROOT / "gt_eval.py").relative_to(repo_root).as_posix(),
            "gt_eval_sha256": runtime.sha256_file(T2_ROOT / "gt_eval.py"),
            "runner_path": (T2_ROOT / "run_t2.py").relative_to(repo_root).as_posix(),
            "runner_sha256": runtime.sha256_file(T2_ROOT / "run_t2.py"),
            "t1_runner_sha256": runtime.sha256_file(T1_RUNNER),
            "t1_config_sha256": runtime.sha256_file(T1_CONFIG),
            "thresholds_sha256": runtime.sha256_bytes(
                runtime.canonical_bytes(loaded["config"]["decision_thresholds"])
            ),
            "limits_sha256": runtime.sha256_bytes(
                runtime.canonical_bytes(loaded["config"]["group"]["limits"])
            ),
            "method_b_budget": loaded["config"]["method_b_budget"],
            "method_c_budget": loaded["config"]["method_c_budget"],
            "decision_thresholds": loaded["config"]["decision_thresholds"],
        },
        "inputs": [
            {
                "role": role,
                "path": path.relative_to(repo_root).as_posix(),
                "sha256": runtime.sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for role, path in _input_paths(loaded)
        ],
        "outputs": [
            {
                "path": name,
                "sha256": runtime.sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in output_names
        ],
        "cost_measurements": {
            "method_b": result["cost_b"],
            "method_c": result["cost_c"],
        },
        "determinism": result["determinism"],
        "fixture_evaluation": result["evaluation"],
        "t1_snapshot": result["t1_snapshot"],
        "decision": decision,
        "authority_statement": (
            "These are offline experimental outputs, not accepted SVM Evidence; no Document, "
            "Revision, Entity, Group, Track, Keyframe, TemporalIdentity, MotionTargetBinding, "
            "ChangeAuthority, schema, or frozen spec was modified."
        ),
    }


def _aggregate(
    results: list[dict[str, Any]], repo_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    evaluations = {result["fixture_id"]: result["evaluation"] for result in results}
    metrics_by_fixture = {result["fixture_id"]: result["metrics"] for result in results}
    costs = {
        result["fixture_id"]: {"B": result["cost_b"], "C": result["cost_c"]} for result in results
    }
    determinism = {
        "full_run_byte_identical": all(
            result["determinism"]["full_run_byte_identical"] for result in results
        ),
        "downstream_passed": all(result["determinism"]["downstream_passed"] for result in results),
    }
    decision = gt_eval.decide_overall(
        evaluations,
        metrics_by_fixture,
        costs,
        runtime.environment_report(),
        determinism,
    )
    return decision, determinism


def _write_manifests(
    results: list[dict[str, Any]], decision: dict[str, Any], repo_root: Path
) -> None:
    for result in results:
        manifest = build_manifest(result, decision, repo_root)
        _write_json(result["output_dir"] / "run-manifest.json", manifest)


def _copy_run_files(result: dict[str, Any], destination: Path) -> None:
    names = [
        "raw/method-b.json",
        "raw/method-c.json",
        "metrics.json",
        "costs.json",
        "reproducibility.json",
        "comparison.avi",
        "run-manifest.json",
    ]
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(result["output_dir"] / name, target)


def write_canonical_snapshot(
    results: list[dict[str, Any]],
    decision: dict[str, Any],
    repo_root: Path,
    canonical_root: Path,
    force: bool,
) -> dict[str, Any]:
    canonical_root = _guard_output(canonical_root, force)
    canonical_root.mkdir(parents=True, exist_ok=True)
    fixtures: dict[str, Any] = {}
    for result in results:
        run_name = result["output_dir"].name
        destination = canonical_root / run_name
        destination.mkdir(parents=True, exist_ok=True)
        _copy_run_files(result, destination)
        files = {}
        for name in (
            "raw/method-b.json",
            "raw/method-c.json",
            "metrics.json",
            "costs.json",
            "reproducibility.json",
            "comparison.avi",
            "run-manifest.json",
        ):
            files[name] = {
                "sha256": runtime.sha256_file(destination / name),
                "bytes": (destination / name).stat().st_size,
            }
        fixtures[result["fixture_id"]] = {
            "run_dir": f"runs/t2-canonical/{run_name}",
            "decision": {
                "quality": result["evaluation"].get("quality", {}).get("status"),
                "fail_closed": result["evaluation"].get("fail_closed", {}).get("status"),
            },
            "determinism": result["determinism"],
            "files": files,
        }
    limitations = []
    fixture_statuses = decision["fixture_statuses"]
    if fixture_statuses.get("f2-rotation-scale", {}).get("quality") == "STOP":
        limitations.append(
            "F2 B control abstained under the frozen median-LK-error gate; the aggregate is "
            "STOP and no C quality claim is made on F2."
        )
    if fixture_statuses.get("f3-low-texture", {}).get("fail_closed") == "INCONCLUSIVE":
        limitations.append(
            "F3 is INCONCLUSIVE because both B and C abstained on the hard frame; this is "
            "reported as an unresolved limit, not as a C success."
        )
    if fixture_statuses.get("f4-occlusion", {}).get("fail_closed") == "CONDITIONAL":
        limitations.append(
            "F4 C abstained fail-closed but with a reason other than the two accepted F4 "
            "reasons; the frozen protocol classifies it CONDITIONAL."
        )
    limitations.extend(
        [
            "T2-B is a new multi-member run; T1-B is a different single-primitive fixture and "
            "was not substituted.",
            "Method A was not re-run by T2-P0A; the T1-A numbers are historical context for a "
            "different fixture and are not an A/B/C comparison.",
            "No SVM Evidence, Group, Track, Keyframe, TemporalIdentity, MotionTargetBinding, "
            "or ChangeAuthority object is created or claimed.",
        ]
    )
    canonical_manifest = {
        "schema_version": CANONICAL_SCHEMA,
        "artifact_classification": runtime.CLASSIFICATION,
        "authority_statement": (
            "These are offline experimental outputs, not accepted SVM Evidence; no Document, "
            "Revision, Entity, Group, Track, Keyframe, TemporalIdentity, MotionTargetBinding, "
            "ChangeAuthority, schema, or frozen spec was modified."
        ),
        "purpose": (
            "T2-P1 Method C (author-anchored group similarity) versus Method B on five "
            "controlled multi-member fixtures under the T2-P0A frozen protocol."
        ),
        "source_commit": repository_state(repo_root)["checked_out_head"],
        "source_scope": {
            "t1_snapshot": verify_t1_snapshot(),
            "worktree_dirty": repository_state(repo_root)["worktree_dirty"],
        },
        "declared_environment": {
            **runtime.environment_report(),
            **_wheel_provenance(),
        },
        "protocol_documents": {
            "t2_p0": {
                "path": "research/temporal-geometry-pilot/T2-GROUP-ANCHOR-EXPERIMENT.md",
                "sha256": runtime.sha256_file(PILOT_ROOT / "T2-GROUP-ANCHOR-EXPERIMENT.md"),
            },
            "t2_p0a": {
                "path": "research/temporal-geometry-pilot/T2-P0A-PROTOCOL-FREEZE.md",
                "sha256": runtime.sha256_file(PILOT_ROOT / "T2-P0A-PROTOCOL-FREEZE.md"),
            },
        },
        "fixtures": fixtures,
        "aggregate_decision": decision,
        "limitations": limitations,
    }
    _write_json(canonical_root / "canonical-manifest.json", canonical_manifest)
    return canonical_manifest


def run_all(repo_root: Path, output_root: Path, force: bool) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    runs: list[tuple[str, Path, Path]] = []
    for fixture_id, config_name, run_name in FIXTURES:
        config_path = T2_ROOT / config_name
        output_dir = output_root / run_name
        runs.append((fixture_id, config_path, output_dir))
    if not force:
        for _fixture_id, _config_path, output_dir in runs:
            if output_dir.exists() and any(output_dir.iterdir()):
                raise runtime.T2Error(f"output already exists (use --force): {output_dir}")
        canonical_root = output_root / "t2-canonical"
        if canonical_root.exists() and any(canonical_root.iterdir()):
            raise runtime.T2Error(
                f"canonical output already exists (use --force): {canonical_root}"
            )
    results = [
        prepare_fixture(config_path, output_dir, repo_root, force)
        for _fixture_id, config_path, output_dir in runs
    ]
    decision, determinism = _aggregate(results, repo_root)
    _write_manifests(results, decision, repo_root)
    canonical = write_canonical_snapshot(
        results, decision, repo_root, output_root / "t2-canonical", force
    )
    return {
        "decision": decision,
        "determinism": determinism,
        "run_dirs": [result["output_dir"].as_posix() for result in results],
        "canonical_manifest": (output_root / "t2-canonical" / "canonical-manifest.json").as_posix(),
        "canonical_manifest_sha256": runtime.sha256_bytes(runtime.pretty_bytes(canonical)),
    }


def run_single(config_path: Path, output_dir: Path, repo_root: Path, force: bool) -> dict[str, Any]:
    result = prepare_fixture(config_path, output_dir, repo_root, force)
    decision, determinism = _aggregate([result], repo_root)
    decision["run_scope"] = "single-fixture"
    _write_manifests([result], decision, repo_root)
    return {
        "decision": decision,
        "determinism": determinism,
        "run_dir": result["output_dir"].as_posix(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the T2-P1 B/C experiment")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-root", type=Path, default=T2_ROOT / "runs")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.all:
            summary = run_all(args.repository_root, args.output_root, args.force)
        else:
            if args.config is None or args.output is None:
                raise runtime.T2Error("--config and --output are required without --all")
            summary = run_single(args.config, args.output, args.repository_root, args.force)
    except (runtime.T2Error, OSError, ValueError) as exc:
        print(f"T2 run failed closed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
