"""Phase 1 demonstrator: Controlled Video -> Editable SVM v0.

Packaging and orchestration only. This module owns no recovery semantics: it
calls S11D video ingestion, the frozen S11A/S11B/S11C adapters through
`svm.recovery_orchestration`, ordinary Document/Revision authoring, then
`MotionEvaluator` and `SVGRenderer`.

The demonstration proves three things:

1. a real checked-in AVI/FFV1 file is the recovery input;
2. recovery yields an ordinary editable SVM Document with twelve Tracks;
3. editing one recovered Keyframe changes the re-rendered result while the
   unrelated Target B and Camera state stays identical.

Ground Truth is never read here, so the demo command can run without it.
"""

from __future__ import annotations

import json
import shutil
import stat
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .motion import MotionEvaluator
from .recovery_orchestration import (
    CAMERA_TARGET,
    RecoveryConfig,
    author_recovered_document,
    recover_scene,
)
from .renderers import SVGRenderer, SVGRenderOptions
from .revisions import SetKeyframeValueChange, Transaction
from .video_ingestion import VideoSampling, ingest_video, verify_video_manifest

DEMO_NAME = "Controlled Video -> Editable SVM v0"
DEMO_SEMANTICS = "svm-phase1-demo@0.1"
TRACK_PROPERTIES = ("translate.x", "translate.y", "rotation_degrees", "scale")
CAMERA_PROPERTIES = ("position.x", "position.y", "rotation_degrees", "scale")
EXPECTED_TRACK_COUNT = 12
DEFAULT_CONFIG = "examples/039-controlled-video-editable-svm/config/phase1-demo.json"


class DemoError(ValueError):
    """Raised when the demo configuration or environment is not usable."""


@dataclass(frozen=True)
class DemoConfig:
    """Explicit demo inputs. Every field is declared, never inferred."""

    video_locator: str
    base_document_locator: str
    selectors_locator: str
    frame_indices: tuple[int, ...]
    ticks: tuple[int, ...]
    ticks_per_second: int
    anchors: tuple[str, ...]
    targets: tuple[str, ...]
    groups: tuple[str, ...]
    edit_role: str
    edit_property: str
    edit_tick: int
    edit_delta: float
    view_box: tuple[int, int, int, int]
    render_width: int
    render_height: int

    @classmethod
    def from_json(cls, text: str) -> DemoConfig:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DemoError("Demo configuration is not valid JSON") from exc
        try:
            edit = data["edit"]
            render = data["render"]
            return cls(
                video_locator=data["video"],
                base_document_locator=data["base_document"],
                selectors_locator=data["selectors"],
                frame_indices=tuple(data["frame_indices"]),
                ticks=tuple(data["ticks"]),
                ticks_per_second=data["ticks_per_second"],
                anchors=tuple(data["anchors"]),
                targets=tuple(data["targets"]),
                groups=tuple(data["groups"]),
                edit_role=edit["role"],
                edit_property=edit["property"],
                edit_tick=edit["tick"],
                edit_delta=edit["delta"],
                view_box=tuple(render["view_box"]),
                render_width=render["width"],
                render_height=render["height"],
            )
        except (KeyError, TypeError) as exc:
            raise DemoError(f"Demo configuration is incomplete: {exc}") from exc

    def recovery(self, selectors: dict[str, dict[str, str]]) -> RecoveryConfig:
        return RecoveryConfig(
            ticks=self.ticks,
            ticks_per_second=self.ticks_per_second,
            anchors=self.anchors,
            targets=self.targets,
            groups=self.groups,
            selectors=selectors,
        )

    def validate(self) -> None:
        if len(self.frame_indices) != len(self.ticks):
            raise DemoError("frame_indices and ticks must pair one to one")
        if len(self.targets) != len(self.groups):
            raise DemoError("Each Target requires exactly one explicit group")
        if self.edit_role not in self.targets:
            raise DemoError("The demo edit must target a declared Target role")
        if self.edit_property not in TRACK_PROPERTIES:
            raise DemoError("The demo edit must target a recovered Target property")
        if self.edit_tick not in self.ticks:
            raise DemoError("The demo edit must target an existing observed tick")
        if self.edit_delta == 0:
            raise DemoError("The demo edit delta must change the canonical value")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _track_properties(document: dict[str, Any], config: DemoConfig) -> dict[str, dict[str, Any]]:
    """Group the twelve recovered Tracks by explicit role."""
    summary: dict[str, dict[str, Any]] = {role: {} for role in (*config.targets, "camera")}
    for track in document["animation"]["content"]:
        target = track["target"]
        if target.get("property") not in (*TRACK_PROPERTIES, *CAMERA_PROPERTIES):
            continue
        if "group" in target:
            for role, group in zip(config.targets, config.groups, strict=True):
                if target["group"] == group:
                    summary[role][target["property"]] = [
                        {"tick": k["tick"], "value": k["value"]} for k in track["keyframes"]
                    ]
        elif target.get("camera") == CAMERA_TARGET:
            summary["camera"][target["property"]] = [
                {"tick": k["tick"], "value": k["value"]} for k in track["keyframes"]
            ]
    return summary


def _find_track(
    document: dict[str, Any], config: DemoConfig, role: str, prop: str
) -> dict[str, Any]:
    group = config.groups[config.targets.index(role)]
    for track in document["animation"]["content"]:
        target = track["target"]
        if target.get("group") == group and target.get("property") == prop:
            return track
    raise DemoError(f"No recovered {prop} Track exists for {role}")


def _find_edit_track(document: dict[str, Any], config: DemoConfig) -> dict[str, Any]:
    return _find_track(document, config, config.edit_role, config.edit_property)


def _keyframes(track: dict[str, Any]) -> list[tuple[int, Any]]:
    return [(k["tick"], k["value"]) for k in track["keyframes"]]


def _motion_probe(document: dict[str, Any], ticks: tuple[int, ...]) -> dict[str, Any]:
    """Per-tick composed group and Camera presentation state.

    Evaluated Entity geometry_value_id identifies the source geometry, not the
    composed group/Camera transform, so a Track edit is observed through the
    sampled presentation instead.
    """
    evaluator = MotionEvaluator(document)
    probe: dict[str, Any] = {}
    for tick in ticks:
        sample = evaluator.sample_document(tick)
        probe[str(tick)] = {
            "groups": {g["id"]: g["transform"] for g in sample["groups"]},
            "camera": sample["presentation"]["camera"],
        }
    return probe


def _render_document(
    document: dict[str, Any], ticks: tuple[int, ...], config: DemoConfig
) -> dict[str, str]:
    evaluator = MotionEvaluator(document)
    renderer = SVGRenderer(
        SVGRenderOptions(
            width=config.render_width,
            height=config.render_height,
            view_box=config.view_box,
        )
    )
    return {str(tick): renderer.render(evaluator.evaluate(tick).scene) for tick in ticks}


def _resolved_output_path(path: Path) -> Path:
    """Reject links/reparse points before resolving, including existing ancestors."""
    try:
        absolute = path.absolute()
        for part in (absolute, *absolute.parents):
            try:
                info = part.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or (
                getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise DemoError("Demo output safety: links and reparse points are not allowed")
        return absolute.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, DemoError):
            raise
        raise DemoError("Demo output safety: cannot safely resolve path") from exc


def _contains_directory(parent: Path, child: Path) -> bool:
    """Canonical containment, including Windows namespace/drive aliases."""
    if child.is_relative_to(parent):
        return True
    try:
        parent.stat()
    except FileNotFoundError:
        return False
    for ancestor in (child, *child.parents):
        try:
            if parent.samefile(ancestor):
                return True
        except FileNotFoundError:
            continue
    return False


def _validate_output(root: Path, config: DemoConfig, output: Path, replace: bool) -> Path:
    output = _resolved_output_path(output)
    try:
        repository = root.resolve(strict=True)
        cwd = Path.cwd().resolve(strict=True)
        protected = [(repository / "examples").resolve(strict=True)]
        protected.extend(
            (root / locator).resolve(strict=True).parent
            for locator in (
                config.video_locator,
                config.base_document_locator,
                config.selectors_locator,
            )
        )
        if (
            output == Path(output.anchor)
            or _contains_directory(output, repository)
            or _contains_directory(output, cwd)
            or any(
                _contains_directory(p, output) or _contains_directory(output, p) for p in protected
            )
        ):
            raise DemoError("Demo output safety: protected directory")
        if output.exists():
            if not output.is_dir():
                raise DemoError("Demo output directory must be a directory")
            if not replace:
                raise DemoError("Demo output directory must not already exist")
    except (OSError, RuntimeError) as exc:
        raise DemoError("Demo output safety: cannot verify protected paths") from exc
    return output


def run_demo(
    root: Path, config: DemoConfig, output: Path, *, replace: bool = False
) -> dict[str, Any]:
    """Build privately, then publish with a same-parent rename/rollback boundary."""
    config.validate()
    output = _validate_output(root, config, output, replace)
    selectors = json.loads((root / config.selectors_locator).read_text(encoding="utf-8"))
    config.recovery(selectors).validate()
    json.loads((root / config.base_document_locator).read_text(encoding="utf-8"))
    VideoSampling(config.frame_indices, config.ticks_per_second).validate()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-staging-", dir=output.parent))
    pending, previous = staging / "bundle", staging / "previous"
    preserve_backup = False
    published = False
    try:
        report = _build_bundle(root, config, pending)
        # Recheck after the long-running build, before touching the old bundle.
        _validate_output(root, config, output, replace)
        try:
            if output.exists():
                output.rename(previous)
            pending.rename(output)
        except BaseException as exc:
            # Roll back interruptions as well as filesystem errors: cleanup must
            # never delete the only surviving copy of the previous bundle.
            if previous.exists():
                try:
                    previous.rename(output)
                except OSError as rollback_error:
                    preserve_backup = True
                    raise DemoError(
                        f"Demo publication rollback failed; original bundle retained at {previous}"
                    ) from rollback_error
            if isinstance(exc, OSError):
                raise DemoError("Demo publication failed; original output preserved") from exc
            raise
        published = True
        return report
    finally:
        if not published and previous.exists():
            preserve_backup = True
        if not preserve_backup:
            try:
                if _resolved_output_path(staging) != staging or staging.parent != output.parent:
                    raise DemoError("Demo output safety: cannot safely clean staging directory")
                shutil.rmtree(staging)
            except OSError:
                if not published:
                    raise
                # Publication has committed. A cleanup error must not masquerade
                # as failed recovery or destroy the successfully published output.
                warnings.warn("Demo published; staging cleanup requires attention", stacklevel=2)


def _build_bundle(root: Path, config: DemoConfig, output: Path) -> dict[str, Any]:
    """Build only inside the private staging directory; no publication authority."""

    video_path = root / config.video_locator
    base_document = json.loads((root / config.base_document_locator).read_text(encoding="utf-8"))
    selectors = json.loads((root / config.selectors_locator).read_text(encoding="utf-8"))

    # 1. A real checked-in AVI/FFV1 container is the recovery input.
    ingestion = ArtifactStore()
    source = ingestion.import_bytes(video_path.read_bytes(), media_type="video/x-msvideo")
    decoded = ingest_video(
        ingestion,
        source.document_reference(),
        VideoSampling(config.frame_indices, config.ticks_per_second),
    )
    observed = tuple(o["tick"] for o in decoded.occurrences)
    if observed != config.ticks:
        raise DemoError(
            f"Declared ticks {config.ticks} disagree with decoded occurrences {observed}"
        )

    # 2. Recovery through the frozen production adapters.
    recovery_config = config.recovery(selectors)
    state = recover_scene(base_document, tuple(f.content for f in decoded.frames), recovery_config)
    recovered_document, _ = author_recovered_document(state, recovery_config)
    tracks = recovered_document["animation"]["content"]
    if len(tracks) != EXPECTED_TRACK_COUNT:
        raise DemoError(f"Recovery produced {len(tracks)} Tracks, expected {EXPECTED_TRACK_COUNT}")

    # Retain the complete input bundle; the manifest joins PNG identity to tick.
    for snapshot in (source, decoded.manifest):
        state.artifacts.import_bytes(
            snapshot.content,
            media_type=snapshot.media_type,
            kind=snapshot.kind,
            provenance=snapshot.provenance,
        )
    verified = verify_video_manifest(state.artifacts, decoded.manifest.document_reference())
    manifest = json.loads(verified.manifest.content)

    # 3. One explicit Keyframe edit through ordinary Document/Revision authoring.
    recovery_revision = state.store.head
    if recovery_revision is None:
        raise DemoError("Recovery produced no accepted Revision")
    track = _find_edit_track(recovered_document, config)
    keyframe = next((k for k in track["keyframes"] if k["tick"] == config.edit_tick), None)
    if keyframe is None:
        raise DemoError(f"The edited Track has no Keyframe at tick {config.edit_tick}")
    before = keyframe["value"]
    after = before + config.edit_delta
    transaction = Transaction(
        transaction_id="transaction:phase1-demo-edit",
        changes=(SetKeyframeValueChange(track["id"], keyframe["id"], after),),
        message=f"Demo edit: {config.edit_property} at tick {config.edit_tick}",
    )
    edited_revision = state.store.commit(recovery_revision, transaction)
    edited_document = state.store.get_document(edited_revision.revision_id)

    # 4. Re-render both states through MotionEvaluator and SVGRenderer.
    recovered_probe = _motion_probe(recovered_document, config.ticks)
    edited_probe = _motion_probe(edited_document, config.ticks)
    recovered_svg = _render_document(recovered_document, config.ticks, config)
    edited_svg = _render_document(edited_document, config.ticks, config)

    edited_entity = config.edit_role
    edited_group = config.groups[config.targets.index(edited_entity)]
    changed_ticks = [
        str(t) for t in config.ticks if recovered_probe[str(t)] != edited_probe[str(t)]
    ]
    if str(config.edit_tick) not in changed_ticks:
        raise DemoError(f"The demo edit did not change tick {config.edit_tick}")
    rendered_ticks = [str(t) for t in config.ticks if recovered_svg[str(t)] != edited_svg[str(t)]]
    if str(config.edit_tick) not in rendered_ticks:
        raise DemoError("The demo edit did not change the re-rendered SVG")
    other_groups = [
        group
        for role, group in zip(config.targets, config.groups, strict=True)
        if role != edited_entity
    ]
    unchanged_targets = all(
        recovered_probe[str(t)]["groups"][group] == edited_probe[str(t)]["groups"][group]
        for t in config.ticks
        for group in other_groups
    )
    unchanged_camera = all(
        recovered_probe[str(t)]["camera"] == edited_probe[str(t)]["camera"] for t in config.ticks
    )
    unchanged_properties = all(
        _keyframes(_find_track(recovered_document, config, edited_entity, prop))
        == _keyframes(_find_track(edited_document, config, edited_entity, prop))
        for prop in TRACK_PROPERTIES
        if prop != config.edit_property
    )
    if not (unchanged_targets and unchanged_camera and unchanged_properties):
        raise DemoError("The demo edit changed unrelated Target B or Camera state")

    # 5. Write the bundle. No machine-specific absolute path is recorded.
    _write_bytes(output / "source" / "scene.avi", source.content)
    _write_bytes(output / "source" / "video-manifest.json", verified.manifest.content)
    for frame in verified.frames:
        _write_bytes(
            output / "frames" / f"{frame.content_hash.removeprefix('sha256:')}.png",
            frame.content,
        )
    _write_json(output / "config" / "phase1-demo.json", _config_payload(config))
    _write_json(output / "documents" / "recovered.svm.json", recovered_document)
    _write_json(output / "documents" / "edited.svm.json", edited_document)
    for tick, svg in recovered_svg.items():
        _write_bytes(
            output / "rendered" / "recovered" / f"tick_{int(tick):03d}.svg", svg.encode("utf-8")
        )
    for tick, svg in edited_svg.items():
        _write_bytes(
            output / "rendered" / "edited" / f"tick_{int(tick):03d}.svg", svg.encode("utf-8")
        )

    report = {
        "schema_version": DEMO_SEMANTICS,
        "demo": DEMO_NAME,
        "input": {
            "video_locator": config.video_locator,
            "video_reference": source.document_reference(),
            "container": manifest["source"]["container"],
            "codec": manifest["source"]["codec"],
            "width": manifest["source"]["width"],
            "height": manifest["source"]["height"],
            "frame_count": manifest["source"]["frame_count"],
            "source_fps": manifest["source"]["source_fps"],
            "selected_frames": list(config.frame_indices),
            "tick_mapping": [
                {"frame_index": index, "tick": tick}
                for index, tick in zip(config.frame_indices, config.ticks, strict=True)
            ],
            "decoder": manifest["decoder"],
            "manifest_artifact_id": verified.manifest.artifact_id,
        },
        "recovery": {
            "policy_identity": manifest["policy_identity"],
            "anchors": [
                {"role": role, "identity_id": state.lineages[role]["identity_id"]}
                for role in config.anchors
            ],
            "targets": [
                {
                    "role": role,
                    "identity_id": state.lineages[role]["identity_id"],
                    "binding_id": state.targets[role]["binding_id"],
                }
                for role in config.targets
            ],
            "camera_consensus": {"artifact_id": state.camera_consensus_id},
            "track_count": len(tracks),
            "track_ids": [track["id"] for track in tracks],
            "scene_summary": _track_properties(recovered_document, config),
        },
        "edit": {
            "role": config.edit_role,
            "property": config.edit_property,
            "tick": config.edit_tick,
            "track_id": track["id"],
            "keyframe_id": keyframe["id"],
            "before": before,
            "after": after,
            "delta": config.edit_delta,
            "base_revision_id": recovery_revision,
            "revision_id": edited_revision.revision_id,
            "document_hash": edited_revision.document_hash,
        },
        "outputs": {
            "source": "source/scene.avi",
            "video_manifest": "source/video-manifest.json",
            "frames": [
                f"frames/{f.content_hash.removeprefix('sha256:')}.png" for f in verified.frames
            ],
            "config": "config/phase1-demo.json",
            "recovered_document": "documents/recovered.svm.json",
            "edited_document": "documents/edited.svm.json",
            "recovered_rendered": [f"rendered/recovered/tick_{t:03d}.svg" for t in config.ticks],
            "edited_rendered": [f"rendered/edited/tick_{t:03d}.svg" for t in config.ticks],
        },
        "validation": {
            "track_count_expected": EXPECTED_TRACK_COUNT,
            "track_count_observed": len(tracks),
            "edited_target": edited_entity,
            "edited_group": edited_group,
            "edited_tick": config.edit_tick,
            "changed_ticks": changed_ticks,
            "re_rendered_changed_ticks": rendered_ticks,
            "other_targets_unchanged": unchanged_targets,
            "camera_unchanged": unchanged_camera,
            "edited_target_other_properties_unchanged": unchanged_properties,
            "recovered_revision_id": recovery_revision,
            "edited_revision_id": edited_revision.revision_id,
        },
    }
    _write_json(output / "report.json", report)
    return report


def _config_payload(config: DemoConfig) -> dict[str, Any]:
    return {
        "video": config.video_locator,
        "base_document": config.base_document_locator,
        "selectors": config.selectors_locator,
        "frame_indices": list(config.frame_indices),
        "ticks": list(config.ticks),
        "ticks_per_second": config.ticks_per_second,
        "anchors": list(config.anchors),
        "targets": list(config.targets),
        "groups": list(config.groups),
        "edit": {
            "role": config.edit_role,
            "property": config.edit_property,
            "tick": config.edit_tick,
            "delta": config.edit_delta,
        },
        "render": {
            "view_box": list(config.view_box),
            "width": config.render_width,
            "height": config.render_height,
        },
    }


def load_config(root: Path, locator: str | None = None) -> DemoConfig:
    path = root / (locator or DEFAULT_CONFIG)
    if not path.is_file():
        raise DemoError(f"Demo configuration not found: {locator or DEFAULT_CONFIG}")
    return DemoConfig.from_json(path.read_text(encoding="utf-8"))
