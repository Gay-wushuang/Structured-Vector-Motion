"""Static projection of a completed D1 bundle; no recovery or rendering authority."""

from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "svm-phase1-showcase@0.1"
GENERATOR_IDENTITY = "svm-phase1-showcase-generator@0.1"

INPUT_FIELDS = (
    "container",
    "codec",
    "width",
    "height",
    "frame_count",
    "selected_frames",
    "tick_mapping",
)
EDIT_FIELDS = (
    "role",
    "property",
    "tick",
    "track_id",
    "keyframe_id",
    "before",
    "after",
    "delta",
    "base_revision_id",
    "revision_id",
    "document_hash",
)
VALIDATION_FIELDS = (
    "track_count_expected",
    "track_count_observed",
    "edited_target",
    "edited_group",
    "edited_tick",
    "changed_ticks",
    "re_rendered_changed_ticks",
    "other_targets_unchanged",
    "camera_unchanged",
    "edited_target_other_properties_unchanged",
    "recovered_revision_id",
    "edited_revision_id",
)
RECOVERY_FIELDS = ("track_count", "track_ids", "scene_summary")
OUTPUT_FIELDS = (
    "source",
    "frames",
    "recovered_document",
    "edited_document",
    "recovered_rendered",
    "edited_rendered",
    "video_manifest",
)


class ShowcaseError(ValueError):
    """Raised when a D1 bundle cannot be safely projected."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ShowcaseError(f"Cannot read required {label}: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ShowcaseError(f"Required {label} is not valid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ShowcaseError(f"Required {label} must be a JSON object")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShowcaseError(f"D1 report field {label} must be an object")
    return value


def _copy_fields(source: dict[str, Any], fields: tuple[str, ...], label: str) -> dict[str, Any]:
    missing = [field for field in fields if field not in source]
    if missing:
        raise ShowcaseError(f"D1 report {label} is missing: {', '.join(missing)}")
    return {field: source[field] for field in fields}


def _artifact(bundle: Path, value: Any, label: str) -> tuple[str, Path]:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ShowcaseError(f"D1 artifact pointer {label} must be a POSIX relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or Path(value).is_absolute() or ".." in relative.parts:
        raise ShowcaseError(
            f"D1 artifact pointer {label} must not be absolute or escape the bundle"
        )
    if relative.as_posix() != value or "." in relative.parts:
        raise ShowcaseError(f"D1 artifact pointer {label} is not canonical")
    try:
        resolved = (bundle / Path(*relative.parts)).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ShowcaseError(f"D1 artifact pointer {label} does not name a readable file") from exc
    if not resolved.is_relative_to(bundle) or not resolved.is_file():
        raise ShowcaseError(f"D1 artifact pointer {label} escapes the bundle or is not a file")
    return value, resolved


def _artifact_list(bundle: Path, value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ShowcaseError(f"D1 report field {label} must be a nonempty list")
    return [_artifact(bundle, item, f"{label}[{index}]")[0] for index, item in enumerate(value)]


def _relative_bundle(bundle: Path, output: Path) -> str:
    try:
        relative = os.path.relpath(bundle, start=output)
    except ValueError as exc:
        raise ShowcaseError(
            "D1 bundle and showcase output require a relative path on one drive"
        ) from exc
    result = Path(relative).as_posix()
    if Path(relative).is_absolute():
        raise ShowcaseError("D1 bundle reference must remain relative")
    return result


def _asset_reference(bundle_relative: str, artifact: str) -> str:
    if bundle_relative == ".":
        return artifact
    return f"{bundle_relative.rstrip('/')}/{artifact}"


def _validate_and_project(bundle: Path, output: Path) -> tuple[dict[str, Any], bytes]:
    try:
        bundle = bundle.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ShowcaseError("D1 bundle cannot be resolved") from exc
    if not bundle.is_dir():
        raise ShowcaseError("D1 bundle must be a directory")

    _, report_path = _artifact(bundle, "report.json", "report")
    try:
        report_bytes = report_path.read_bytes()
    except OSError as exc:
        raise ShowcaseError("Cannot read required D1 report bytes") from exc
    report = _read_json(report_path, "D1 report")
    input_data = _copy_fields(_object(report.get("input"), "input"), INPUT_FIELDS, "input")
    edit = _copy_fields(_object(report.get("edit"), "edit"), EDIT_FIELDS, "edit")
    validation = _copy_fields(
        _object(report.get("validation"), "validation"), VALIDATION_FIELDS, "validation"
    )
    recovery = _copy_fields(
        _object(report.get("recovery"), "recovery"), RECOVERY_FIELDS, "recovery"
    )
    reported_outputs = _copy_fields(
        _object(report.get("outputs"), "outputs"), OUTPUT_FIELDS, "outputs"
    )

    outputs: dict[str, Any] = {}
    for field in ("source", "recovered_document", "edited_document", "video_manifest"):
        outputs[field] = _artifact(bundle, reported_outputs[field], f"outputs.{field}")[0]
    for field in ("frames", "recovered_rendered", "edited_rendered"):
        outputs[field] = _artifact_list(bundle, reported_outputs[field], f"outputs.{field}")

    expected = {
        "source": "source/scene.avi",
        "video_manifest": "source/video-manifest.json",
        "recovered_document": "documents/recovered.svm.json",
        "edited_document": "documents/edited.svm.json",
    }
    for field, path in expected.items():
        if outputs[field] != path:
            raise ShowcaseError(f"D1 report outputs.{field} must reference {path}")

    mappings = input_data["tick_mapping"]
    selected = input_data["selected_frames"]
    if (
        not isinstance(mappings, list)
        or not mappings
        or not isinstance(selected, list)
        or len(mappings) != len(outputs["frames"])
        or len(mappings) != len(outputs["recovered_rendered"])
        or len(mappings) != len(outputs["edited_rendered"])
    ):
        raise ShowcaseError("D1 frame/tick and rendered output ordering is incomplete")
    for index, mapping in enumerate(mappings):
        if (
            not isinstance(mapping, dict)
            or set(mapping) != {"frame_index", "tick"}
            or mapping["frame_index"] != selected[index]
        ):
            raise ShowcaseError("D1 input.tick_mapping does not match selected frame ordering")

    manifest_path = _artifact(bundle, outputs["video_manifest"], "outputs.video_manifest")[1]
    manifest = _read_json(manifest_path, "D1 video manifest")
    occurrences = manifest.get("occurrences")
    if not isinstance(occurrences, list) or len(occurrences) != len(mappings):
        raise ShowcaseError("D1 video manifest occurrence ordering is incomplete")
    for index, (mapping, occurrence, frame) in enumerate(
        zip(mappings, occurrences, outputs["frames"], strict=True)
    ):
        expected_artifact = f"artifact:{PurePosixPath(frame).stem}"
        if (
            not isinstance(occurrence, dict)
            or occurrence.get("frame_index") != mapping["frame_index"]
            or occurrence.get("tick") != mapping["tick"]
            or occurrence.get("raster_artifact_id") != expected_artifact
        ):
            raise ShowcaseError(f"D1 manifest/report frame ordering disagrees at index {index}")

    bundle_relative = _relative_bundle(bundle, output)
    projection = {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "identity": GENERATOR_IDENTITY,
            "bundle_relative": bundle_relative,
            "report_reference": _asset_reference(bundle_relative, "report.json"),
            "report_sha256": f"sha256:{hashlib.sha256(report_bytes).hexdigest()}",
        },
        "input": input_data,
        "edit": edit,
        "validation": validation,
        "recovery": recovery,
        "outputs": outputs,
    }
    return projection, report_bytes


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _embedded_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


def _html(projection: dict[str, Any]) -> bytes:
    source = _asset_reference(
        projection["generator"]["bundle_relative"], projection["outputs"]["source"]
    )
    content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Controlled Video -&gt; Editable SVM v0</title>
  <link rel="stylesheet" href="showcase.css">
</head>
<body>
  <main>
    <h1>Controlled Video -&gt; Editable SVM v0</h1>
    <p>D2 is a projection of D1 evidence, not a new inference stage.</p>
    <section>
      <h2>Input</h2>
      <p id="input-metadata"></p>
      <p><a id="source-link" href="{html.escape(source, quote=True)}">
        Authoritative AVI/FFV1 source</a></p>
      <label>Frame / tick <select id="tick-selector"></select></label>
      <img id="input-frame" alt="Canonical D1 input frame">
    </section>
    <section>
      <h2>Recovered / Edited</h2>
      <button id="show-recovered" type="button">Recovered</button>
      <button id="show-edited" type="button">Edited</button>
      <p id="render-mode"></p>
      <img id="rendered-frame" alt="D1 rendered frame">
    </section>
    <section>
      <h2>Edit Evidence</h2>
      <dl id="edit-evidence"></dl>
    </section>
    <section>
      <h2>Editability Evidence</h2>
      <p>This is recovered editable Track data. One Keyframe edit was committed and re-rendered.</p>
      <dl id="editability-evidence"></dl>
      <details><summary>Track IDs</summary><ul id="track-ids"></ul></details>
      <p><a id="recovered-document">Recovered SVM Document</a> ·
      <a id="edited-document">Edited SVM Document</a></p>
    </section>
  </main>
  <script id="projection-data" type="application/json">{_embedded_json(projection)}</script>
  <script src="showcase.js"></script>
</body>
</html>
"""
    return content.encode()


CSS = b"""body { font-family: sans-serif; margin: 2rem; max-width: 72rem; }
section { border-top: 1px solid #999; margin-top: 2rem; padding-top: 1rem; }
img { display: block; margin-top: 1rem; max-height: 32rem; max-width: 100%; }
dt { font-weight: bold; margin-top: .5rem; }
dd { margin-left: 0; overflow-wrap: anywhere; }
button, select { font: inherit; margin-right: .5rem; }
"""

JS = rb""""use strict";
const projection = JSON.parse(document.getElementById("projection-data").textContent);
const byId = (id) => document.getElementById(id);
const asset = (path) => projection.generator.bundle_relative === "."
  ? path : `${projection.generator.bundle_relative.replace(/\/$/, "")}/${path}`;
const addEvidence = (root, label, value) => {
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = Array.isArray(value) ? value.join(", ") : String(value);
  root.append(term, detail);
};

byId("input-metadata").textContent =
  `${projection.input.container} / ${projection.input.codec} / ` +
  `${projection.input.width} x ${projection.input.height} / ${projection.input.frame_count} frames`;
byId("recovered-document").href = asset(projection.outputs.recovered_document);
byId("edited-document").href = asset(projection.outputs.edited_document);

const selector = byId("tick-selector");
projection.input.tick_mapping.forEach((mapping, index) => {
  const option = document.createElement("option");
  option.value = String(index);
  option.textContent = `frame ${mapping.frame_index} / tick ${mapping.tick}`;
  selector.append(option);
});

let mode = "recovered";
const render = () => {
  const index = Number(selector.value || 0);
  const mapping = projection.input.tick_mapping[index];
  byId("input-frame").src = asset(projection.outputs.frames[index]);
  const paths = mode === "recovered"
    ? projection.outputs.recovered_rendered : projection.outputs.edited_rendered;
  byId("rendered-frame").src = asset(paths[index]);
  byId("render-mode").textContent = `${mode} at tick ${mapping.tick}`;
};
selector.addEventListener("change", render);
byId("show-recovered").addEventListener("click", () => { mode = "recovered"; render(); });
byId("show-edited").addEventListener("click", () => { mode = "edited"; render(); });

const edit = byId("edit-evidence");
for (const field of ["role", "property", "tick", "before", "after", "delta", "track_id",
                     "keyframe_id", "base_revision_id", "revision_id"]) {
  addEvidence(edit, field, projection.edit[field]);
}
const validation = byId("editability-evidence");
addEvidence(validation, "Observed Track count", projection.validation.track_count_observed);
addEvidence(validation, "Changed ticks", projection.validation.changed_ticks);
addEvidence(validation, "Re-rendered changed ticks",
            projection.validation.re_rendered_changed_ticks);
addEvidence(validation, "Target B unchanged", projection.validation.other_targets_unchanged);
addEvidence(validation, "Camera unchanged", projection.validation.camera_unchanged);
addEvidence(validation, "Edited target other properties unchanged",
            projection.validation.edited_target_other_properties_unchanged);
for (const id of projection.recovery.track_ids) {
  const item = document.createElement("li");
  item.textContent = id;
  byId("track-ids").append(item);
}
render();
"""


def generate_showcase(bundle: Path, output: Path) -> dict[str, Any]:
    """Validate one completed D1 bundle and write a deterministic static projection."""
    try:
        output = output.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ShowcaseError("Showcase output path cannot be resolved") from exc
    if output.exists():
        raise ShowcaseError("Showcase output directory must not already exist")
    projection, _ = _validate_and_project(bundle, output)
    try:
        output.mkdir()
        (output / "projection.json").write_bytes(_json_bytes(projection))
        (output / "index.html").write_bytes(_html(projection))
        (output / "showcase.css").write_bytes(CSS)
        (output / "showcase.js").write_bytes(JS)
    except OSError as exc:
        raise ShowcaseError(f"Cannot write showcase output: {exc}") from exc
    return projection
