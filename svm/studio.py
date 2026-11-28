"""Local authoring surface for native SVM Documents."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib
import json
import math
import threading
import webbrowser
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .adapters.svg_import import SVGImportAdapter
from .anchored_regeneration import AnchoredRegenerationContract, ImpactTarget
from .artifacts import ArtifactStore
from .backends import GeometryBackend
from .cli import _validate_schema
from .editor_server import REPOSITORY_ROOT, MotionEditorHandler, _tick
from .evaluator import Evaluator, canonical_bytes
from .motion import MotionEvaluator, _sample_track
from .operations import _geometry_bounds, get_operation_registry
from .proposals import (
    AdapterRequest,
    GeneratorProvenance,
    Proposal,
    ProposalAcceptor,
    ProposalConflictError,
)
from .renderers import SVGRenderer, SVGRenderOptions
from .revisions import (
    AddKeyframeChange,
    AppendSceneFragmentChange,
    Change,
    CreateTrackChange,
    RevisionStore,
    SetKeyframeValueChange,
    SetOperationParameterChange,
    Transaction,
)
from .scene import EvaluatedScene, build_evaluated_scene
from .studio_reference import DOCUMENT_ID, FRAME_PREFIX, StudioReference

ASSETS = REPOSITORY_ROOT / "editor" / "studio"
MAX_BODY = 2 * 1024 * 1024
MAX_SEGMENT_REQUEST = 18 * 1024 * 1024
MAX_TICK = 1_000_000
DEFAULT_BOX = (0.0, 0.0, 800.0, 480.0)
DEFAULT_REFERENCE_BUNDLE = REPOSITORY_ROOT / "build" / "studio-controlled-video"
EXPECTED_SOURCE = REPOSITORY_ROOT / "examples" / "038-controlled-video-ingestion" / "scene.avi"
ACTOR = GeneratorProvenance("editor:studio", "0.1", "svm-core", "svm-studio@0.1")


def _digest(*values: Any) -> str:
    return hashlib.sha256(canonical_bytes(values)).hexdigest()[:24]


def _empty() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "semantics_version": "svm-core-0.1",
        "document_id": "document:untitled",
        "references": [],
        "entities": [],
        "construction": {"operations": [], "output_bindings": [], "refinement_stages": []},
        "presentation": {"render_stack": [], "styles": []},
        "constraints": [],
        "evaluation_policies": [],
        "edit_permissions": [],
        "animation": {"content": [], "construction_scheduling_hints": []},
    }


def _shape(
    identity: str,
    name: str,
    kind: str,
    params: dict[str, Any],
    fill: str,
    stroke: str = "none",
    stroke_width: float = 0,
) -> AppendSceneFragmentChange:
    entity, op = f"entity:{identity}", f"op:{identity}"
    return AppendSceneFragmentChange(
        ({"id": entity, "name": name},),
        ({"id": op, "type": kind, "parameters": params, "inputs": {}},),
        ({"entity": entity, "property": "geometry", "slot": f"{op}.geometry"},),
        (entity,),
        (
            {
                "entity": entity,
                "fill": fill,
                "stroke": stroke,
                "stroke_width": stroke_width,
                "opacity": 1,
            },
        ),
    )


def _position_parameters(kind: str) -> tuple[str, str]:
    if kind == "CreateRectangle":
        return "x", "y"
    if kind == "CreateEllipse":
        return "cx", "cy"
    raise ValueError("该图形不支持画布拖动")


def _demo() -> dict[str, Any]:
    document = _empty()
    document["document_id"] = "document:orbital-study"
    ellipses = [
        ("orbit-outer", "外侧轨道", 400, 240, 300, 152, "none", "#65747C", 1),
        ("orbit-inner", "内侧轨道", 400, 240, 234, 108, "none", "#74858A", 1),
        ("star-west", "左侧星点", 163, 162, 4, 4, "#9CC7B2", "none", 0),
        ("star-east", "右侧星点", 648, 308, 4, 4, "#F2DCBB", "none", 0),
        ("planet", "主行星", 400, 240, 87, 87, "#DE865E", "none", 0),
        ("shadow", "行星阴影", 420, 256, 62, 56, "#C96950", "none", 0),
        ("light", "行星高光", 374, 211, 28, 28, "#F0AC7E", "none", 0),
        ("satellite", "卫星", 582, 181, 17, 17, "#D7E6CE", "none", 0),
    ]
    for key, label, cx, cy, rx, ry, fill, stroke, width in ellipses:
        _shape(
            key,
            label,
            "CreateEllipse",
            {"cx": cx, "cy": cy, "rx": rx, "ry": ry},
            fill,
            stroke,
            width,
        ).apply(document)
    for prop, values in {"cx": (582, 630, 400, 170, 582), "cy": (181, 265, 346, 215, 181)}.items():
        track = f"track:satellite-{prop}"
        CreateTrackChange(track, "op:satellite", prop, 24).apply(document)
        for tick, value in zip((0, 24, 48, 72, 96), values, strict=True):
            AddKeyframeChange(track, f"keyframe:satellite-{prop}-{tick}", tick, value).apply(
                document
            )
    return document


def _scene(document: dict[str, Any], tick: int) -> EvaluatedScene:
    geometry: GeometryBackend | None = None
    if any(
        op["type"] in {"BooleanGeometry", "PathToPolygon"}
        for op in document["construction"]["operations"]
    ):
        try:
            from .backends.shapely_geometry import ShapelyGeometryBackend
        except ImportError as exc:
            raise ValueError("这个工程需要现有的 geometry 依赖（Shapely）") from exc

        geometry = ShapelyGeometryBackend()
    if document.get("animation", {}).get("content"):
        return MotionEvaluator(document, geometry_backend=geometry).evaluate(tick).scene
    return build_evaluated_scene(document, Evaluator(document, geometry_backend=geometry))


def _fit(scene: EvaluatedScene) -> tuple[float, float, float, float]:
    bounds = []
    for entity in scene.entities:
        geometry = entity.geometry
        if scene.camera_transform:
            geometry = {"kind": "transform", "source": geometry, "matrix": scene.camera_transform}
        bounds.append(_geometry_bounds(geometry))
    if not bounds:
        return DEFAULT_BOX
    left, top = min(b[0] for b in bounds), min(b[1] for b in bounds)
    right, bottom = max(b[2] for b in bounds), max(b[3] for b in bounds)
    width, height = max(right - left, 1), max(bottom - top, 1)
    pad = max(width, height) * 0.1
    return left - pad, top - pad, width + 2 * pad, height + 2 * pad


def _fit_authored_segment(
    document: dict[str, Any], opening_scene: EvaluatedScene
) -> tuple[float, float, float, float]:
    tracks = document["animation"]["content"]
    if not tracks:
        return _fit(opening_scene)
    if len(tracks) > 256 or not all(
        track["target"].get("parameter") in {"x", "y"} and track["interpolation"] == "linear"
        for track in tracks
    ):
        return _fit(opening_scene)
    ticks = {frame["tick"] for track in tracks for frame in track["keyframes"]}
    if len(ticks) > 120:
        return _fit(opening_scene)
    evaluator = MotionEvaluator(document)
    boxes = [_fit(evaluator.evaluate(tick).scene) for tick in sorted(ticks)]
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[0] + box[2] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    return left, top, right - left, bottom - top


class Studio:
    def __init__(self, reference_bundle: Path = DEFAULT_REFERENCE_BUNDLE) -> None:
        self.acceptor = ProposalAcceptor()
        self.redo: list[str] = []
        self.reference_bundle = reference_bundle
        self.reference: StudioReference | None = None
        self.comparing = False
        self.pending: tuple[AnchoredRegenerationContract, Proposal] | None = None
        self.pending_segment: Any = None
        self.guided_source: tuple[str, bytes, bytes | None] | None = None
        self._open(_demo(), DEFAULT_BOX)

    @property
    def head(self) -> str:
        assert self.store.head is not None
        return self.store.head

    def _open(
        self,
        document: dict[str, Any],
        box: tuple[float, float, float, float] | None,
        *,
        comparing: bool = False,
    ) -> None:
        # The frozen Phase 1 baseline uses runtime-validated records that its
        # generic interchange schema does not describe. Its loader verifies
        # the exact snapshot or a value-only descendant before this call.
        if not comparing:
            _validate_schema(document)
        store = RevisionStore.create(document)
        scene = _scene(document, 0)
        if box is not None:
            new_box = box
        elif document["document_id"].startswith("document:studio-authored-"):
            new_box = _fit_authored_segment(document, scene)
        else:
            new_box = _fit(scene)
        self._render(scene, new_box)
        self.box = new_box
        self.store = store
        self.artifacts = ArtifactStore()
        self.redo.clear()
        self.comparing = comparing
        self.pending = None
        self.pending_segment = None
        self.guided_source = None

    def _load_reference(self) -> StudioReference:
        if self.reference is None:
            self.reference = StudioReference.load(self.reference_bundle, EXPECTED_SOURCE)
        return self.reference

    def _prepare_reference(self) -> None:
        if self.reference_bundle != DEFAULT_REFERENCE_BUNDLE or self.reference_bundle.exists():
            return
        from .phase1_demo import load_config, run_demo

        try:
            run_demo(REPOSITORY_ROOT, load_config(REPOSITORY_ROOT), self.reference_bundle)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"生成视频示例失败，请检查项目的 analysis 依赖：{exc}") from exc

    @staticmethod
    def _render(scene: EvaluatedScene, box: tuple[float, float, float, float]) -> str:
        if not all(math.isfinite(value) for value in box):
            raise ValueError("画布范围包含无效坐标")
        width, height = box[2:]
        longest_edge = max(width, height)
        options = SVGRenderOptions(
            width=max(1, round(1024 * (width / longest_edge))),
            height=max(1, round(1024 * (height / longest_edge))),
            view_box=box,
        )
        return SVGRenderer(options).render(scene)

    def state(self, tick: int) -> dict[str, Any]:
        if not 0 <= tick <= MAX_TICK:
            raise ValueError("时间超出工作台范围")
        document = self.store.get_document(self.head)
        registry = get_operation_registry(document["semantics_version"])
        reference = self.reference if self.comparing else None
        tracks = document.get("animation", {}).get("content", [])
        preview = None
        if self.pending is not None:
            contract, proposal = self.pending
            candidate = self.acceptor.validate_anchored(
                self.store, proposal, contract, self.artifacts
            )
            preview = {
                "id": proposal.proposal_id,
                "svg": self._render(_scene(candidate, tick), self.box),
                "track": contract.regeneration_scope[0].target,
                "keyframe": contract.regeneration_scope[0].parameter,
            }
        return {
            "svg": self._render(_scene(document, tick), self.box),
            "tick": tick,
            "viewBox": self.box,
            "revision": self.head,
            "undo": bool(self.store.revisions[self.head].parent_ids),
            "redo": bool(self.redo),
            "document": document,
            "recoveryAvailable": (self.reference_bundle / "report.json").is_file(),
            "canPrepareRecovery": self.reference_bundle == DEFAULT_REFERENCE_BUNDLE
            and not self.reference_bundle.exists(),
            "source": reference.at(tick) if reference else None,
            "motionValues": {track["id"]: _sample_track(track, tick) for track in tracks},
            "authoredEndTick": max(
                (frame["tick"] for track in tracks for frame in track["keyframes"]), default=0
            )
            if document["document_id"].startswith("document:studio-authored-")
            else None,
            "preview": preview,
            "animatable": {
                op["id"]: sorted(registry.definition(op["type"]).animatable_parameters)
                for op in document["construction"]["operations"]
            },
        }

    def action(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["revision"] != self.head:
            raise ProposalConflictError("工程已有更新，请刷新后重试")
        tick, action = payload.get("tick", 0), payload["action"]
        if type(tick) is not int or not 0 <= tick <= MAX_TICK:
            raise ValueError("时间必须是工作台范围内的整数 tick")
        document = self.store.get_document(self.head)
        if action == "clear-preview":
            self.pending = None
            self.pending_segment = None
            return self.state(tick)
        if action in {"prepare-segment", "prepare-demo-segment"}:
            return self._prepare_segment(payload, tick)
        if action in {"inspect-guided-source", "analyze-guided-source", "prepare-guided-segment"}:
            try:
                return self._guided(payload, tick)
            except OSError as exc:
                raise ValueError(f"读取本机视频时失败：{exc}") from exc
        if action == "accept-segment":
            return self._accept_segment(payload)
        if action == "discard-segment":
            self.pending_segment = None
            self.guided_source = None
            return {"discarded": True}
        if action == "preview-keyframe":
            self._preview_keyframe(document, payload, tick)
            return self.state(tick)
        if action == "accept-preview":
            if self.pending is None:
                raise ValueError("没有待确认的修改")
            contract, proposal = self.pending
            if payload.get("preview") != proposal.proposal_id:
                raise ProposalConflictError("待确认的修改已有更新")
            self.acceptor.accept_anchored(self.store, proposal, contract, self.artifacts)
            self.pending = None
            self.redo.clear()
            return self.state(tick)
        if action == "recovery":
            self._prepare_reference()
            reference = self._load_reference()
            self._open(reference.document, reference.box, comparing=True)
            return self.state(reference.ticks[0])
        if action in {"new", "demo", "open"}:
            if action == "open":
                opened = payload["document"]
                if (
                    isinstance(opened, dict)
                    and opened.get("document_id") == DOCUMENT_ID
                    and (self.reference_bundle / "report.json").is_file()
                ):
                    reference = self._load_reference()
                    if reference.matches(opened):
                        self._open(opened, reference.box, comparing=True)
                        return self.state(reference.ticks[0])
                self._open(opened, None)
            else:
                self._open(_demo() if action == "demo" else _empty(), DEFAULT_BOX)
            return self.state(0)
        if action == "fit":
            scene = _scene(document, tick)
            new_box = self.reference.box if self.comparing and self.reference else _fit(scene)
            self._render(scene, new_box)
            self.box = new_box
            return self.state(tick)
        if action == "undo":
            parents = self.store.revisions[self.head].parent_ids
            if parents:
                self.redo.append(self.head)
                self.store.checkout(parents[0])
                self.pending = None
            return self.state(tick)
        if action == "redo":
            if self.redo:
                self.store.checkout(self.redo.pop())
                self.pending = None
            return self.state(tick)
        if self.comparing and action != "track-keyframe":
            raise ValueError("受控视频示例仅支持修改已有运动轨道的关键帧数值")
        if action == "import":
            svg = payload["svg"]
            if not isinstance(svg, str) or "<!DOCTYPE" in svg.upper():
                raise ValueError("SVG 不支持文档类型声明")
            artifact = self.artifacts.import_bytes(svg.encode("utf-8"), media_type="image/svg+xml")
            request = AdapterRequest.from_store(
                self.store,
                self.head,
                ("document",),
                artifact_ids=(artifact.artifact_id,),
                options={"namespace": f"studio-{_digest(self.head, artifact.artifact_id)}"},
            )
            try:
                proposal = SVGImportAdapter().propose(request, self.artifacts)
            except ImportError as exc:
                raise ValueError("当前 Python 缺少 SVG 解析所需的依赖，请使用启动脚本") from exc
        else:
            changes = self._changes(document, payload, tick)
            identity = _digest(self.head, payload)
            proposal = Proposal(
                f"proposal:studio:{identity}",
                self.head,
                ACTOR,
                Transaction(f"transaction:studio:{identity}", changes, f"Studio {action}"),
            )
        candidate = self.acceptor.validate(self.store, proposal, self.artifacts)
        scene = _scene(candidate, tick)
        new_box = _fit(scene) if action == "import" and not self.comparing else self.box
        self._render(scene, new_box)
        self.acceptor.accept(self.store, proposal, self.artifacts)
        self.pending = None
        self.box = new_box
        self.redo.clear()
        return self.state(tick)

    def _prepare_segment(self, payload: dict[str, Any], tick: int) -> dict[str, Any]:
        self.pending_segment = None
        demo = payload["action"] == "prepare-demo-segment"
        try:
            author = importlib.import_module(
                "research.studio-motion-reconstruction.author_translation"
            )
            if demo:
                prepared = author.prepare_demo()
            else:
                source = base64.b64decode(payload["source"], validate=True)
                candidate = base64.b64decode(payload["candidate"], validate=True)
                if (
                    not 0 < len(source) <= 8 * 1024 * 1024
                    or not 0 < len(candidate) <= 4 * 1024 * 1024
                ):
                    raise ValueError("研究片段超过 AVI 或观测文件上限")
                prepared = author.prepare(source, candidate, payload["selection"])
        except binascii.Error as exc:
            raise ValueError("研究片段输入编码无效") from exc
        except (ImportError, RuntimeError) as exc:
            raise ValueError(f"研究片段需要本机 analysis 环境：{exc}") from exc
        return self._present_segment(prepared, tick, synthetic=demo)

    def _guided(self, payload: dict[str, Any], tick: int) -> dict[str, Any]:
        try:
            author = importlib.import_module(
                "research.studio-motion-reconstruction.author_translation"
            )
        except ImportError as exc:
            raise ValueError("请安装现有的 analysis 依赖以分析本机视频") from exc
        action = payload["action"]
        self.pending_segment = None
        if action == "inspect-guided-source":
            self.guided_source = None
            source = base64.b64decode(payload["source"], validate=True)
            if not 0 < len(source) <= 8 * 1024 * 1024:
                raise ValueError("AVI 文件超过 8 MiB 上限或内容为空")
            info = author.inspect_source(source)
            self.guided_source = (self.head, source, None)
            return info
        if self.guided_source is None or self.guided_source[0] != self.head:
            raise ProposalConflictError("请重新读取原片首帧")
        _, source, candidate = self.guided_source
        if action == "analyze-guided-source":
            self.guided_source = (self.head, source, None)
            candidate, info = author.analyze_source(source, payload["x"], payload["y"])
            self.guided_source = (self.head, source, candidate)
            return info
        if candidate is None:
            raise ValueError("请先点选首帧对象并分析")
        prepared = author.prepare(
            source,
            candidate,
            {
                "subject": "subject",
                "start_tick": payload["start"],
                "end_tick": payload["end"],
                "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
            },
        )
        return self._present_segment(prepared, tick, synthetic=False)

    def _present_segment(self, prepared: Any, tick: int, *, synthetic: bool) -> dict[str, Any]:
        first = _scene(prepared.document, 0)
        box = _fit_authored_segment(prepared.document, first)
        start = 0
        stop = prepared.report["document_end_tick"]
        first_svg = self._render(first, box)
        last_svg = self._render(_scene(prepared.document, stop), box)
        self.pending_segment = (self.head, prepared, box)
        state = self.state(tick)
        return {
            **state,
            "segment": {
                "id": prepared.preview_id,
                "synthetic": synthetic,
                "report": prepared.report,
                "firstSvg": first_svg,
                "lastSvg": last_svg,
                "firstTick": start,
                "lastTick": stop,
            },
        }

    def _accept_segment(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.pending_segment is None:
            raise ValueError("请先验证研究片段")
        base, prepared, box = self.pending_segment
        if base != self.head or payload.get("preview") != prepared.preview_id:
            raise ProposalConflictError("工程或研究片段预览已有更新")
        author = importlib.import_module("research.studio-motion-reconstruction.author_translation")
        result = author.accept(prepared, prepared.preview_id)
        self.store = prepared.base
        self.artifacts = prepared.artifacts
        self.box = box
        self.comparing = False
        self.redo.clear()
        self.pending = None
        self.pending_segment = None
        self.guided_source = None
        return {**self.state(0), "segmentReceipt": result["report"]}

    def _preview_keyframe(
        self, document: dict[str, Any], payload: dict[str, Any], tick: int
    ) -> None:
        tracks = document.get("animation", {}).get("content", [])
        track = next((item for item in tracks if item["id"] == payload["track"]), None)
        if track is None or track["value_type"] != "number" or not track["target"].get("group"):
            raise ValueError("范围预览需要一个对象组的数值轨道")
        if track["target"]["property"] not in {"translate.x", "translate.y"}:
            raise ValueError("范围预览仅支持对象组位移")
        key = next((frame for frame in track["keyframes"] if frame["tick"] == tick), None)
        anchors = tuple(
            ImpactTarget("set_keyframe_value", track["id"], frame["id"])
            for frame in track["keyframes"]
            if frame["tick"] != tick
        )
        if key is None or not anchors:
            raise ValueError("请选择保留至少一个相邻关键帧的已有关键帧")
        impact = ImpactTarget("set_keyframe_value", track["id"], key["id"])
        contract = AnchoredRegenerationContract(self.head, anchors, anchors, anchors, (impact,))
        identity = _digest(self.head, payload)
        proposal = Proposal(
            f"proposal:studio-preview:{identity}",
            self.head,
            ACTOR,
            Transaction(
                f"transaction:studio-preview:{identity}",
                (SetKeyframeValueChange(track["id"], key["id"], payload["value"]),),
                "Studio scoped keyframe preview",
            ),
        )
        candidate = self.acceptor.validate_anchored(self.store, proposal, contract, self.artifacts)
        self._render(_scene(candidate, tick), self.box)
        self.pending = (contract, proposal)

    def _changes(
        self, document: dict[str, Any], payload: dict[str, Any], tick: int
    ) -> tuple[Change, ...]:
        action = payload["action"]
        if action == "track-keyframe":
            tracks = document.get("animation", {}).get("content", [])
            track = next((item for item in tracks if item["id"] == payload["track"]), None)
            if track is None or track["value_type"] != "number":
                raise ValueError("请选择数值轨道")
            if (
                self.comparing
                and track["target"].get("group")
                and track["target"].get("property") in {"translate.x", "translate.y"}
            ):
                raise ValueError("请先预览并确认对象位移修改")
            frame = next((item for item in track["keyframes"] if item["tick"] == tick), None)
            if frame is None:
                raise ValueError("请在时间轴选择一个已有关键帧")
            return (SetKeyframeValueChange(track["id"], frame["id"], payload["value"]),)
        if action == "shape":
            kind = payload["kind"]
            if kind not in {"CreateRectangle", "CreateEllipse"}:
                raise ValueError("未知图形")
            left, top, width, height = self.box
            x, y = left + width / 2, top + height / 2
            size = max(1, min(width, height)) / 8
            if kind == "CreateEllipse":
                params = {"cx": x, "cy": y, "rx": size, "ry": size}
            else:
                params = {"x": x - size, "y": y - size, "width": 2 * size, "height": 2 * size}
            return (
                _shape(
                    f"studio-{_digest(self.head, kind)}",
                    payload["name"],
                    kind,
                    params,
                    payload["fill"],
                ),
            )
        if action not in {"parameter", "keyframe", "move"}:
            raise ValueError("未知编辑操作")
        operation_id = payload["operation"]
        operation = next(
            (op for op in document["construction"]["operations"] if op["id"] == operation_id),
            None,
        )
        if operation is None:
            raise ValueError("该图层没有可编辑的构造操作")
        animation = document.get("animation", {})
        if action == "move":
            changes: tuple[Change, ...] = ()
            for prop, value in zip(
                _position_parameters(operation["type"]), (payload["x"], payload["y"]), strict=True
            ):
                target = {"operation": operation_id, "parameter": prop}
                animated = any(track["target"] == target for track in animation.get("content", []))
                changes += self._parameter(animation, operation, prop, value, tick, animated)
            return changes
        return self._parameter(
            animation, operation, payload["property"], payload["value"], tick, action == "keyframe"
        )

    @staticmethod
    def _parameter(
        animation: dict[str, Any],
        operation: dict[str, Any],
        prop: str,
        value: Any,
        tick: int,
        keyframe: bool,
    ) -> tuple[Change, ...]:
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ValueError("请输入有限数值")
        if type(operation["parameters"].get(prop)) not in {int, float}:
            raise ValueError("该属性不支持数值编辑")
        operation_id = operation["id"]
        if not keyframe:
            return (SetOperationParameterChange(operation_id, prop, value),)
        target = {"operation": operation_id, "parameter": prop}
        for track in animation.get("content", []):
            if track["target"] == target:
                for key in track["keyframes"]:
                    if key["tick"] == tick:
                        return (SetKeyframeValueChange(track["id"], key["id"], value),)
                return (
                    AddKeyframeChange(
                        track["id"], f"keyframe:studio-{_digest(track['id'], tick)}", tick, value
                    ),
                )
        track_id = f"track:studio-{_digest(operation_id, prop)}"
        timebase = animation.get("timebase", {}).get("ticks_per_second", 24)
        initial = value if tick == 0 else operation["parameters"][prop]
        changes: tuple[Change, ...] = (
            CreateTrackChange(track_id, operation_id, prop, timebase),
            AddKeyframeChange(track_id, f"keyframe:studio-{_digest(track_id, 0)}", 0, initial),
        )
        if tick:
            changes += (
                AddKeyframeChange(
                    track_id, f"keyframe:studio-{_digest(track_id, tick)}", tick, value
                ),
            )
        return changes


class StudioHandler(MotionEditorHandler):
    studio: Studio

    def do_GET(self) -> None:  # noqa: N802
        if not self._trusted_host():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._handle(lambda: self.studio.state(_tick(parsed.query)))
            return
        if parsed.path.startswith(FRAME_PREFIX):
            reference = self.studio.reference
            frame = reference.frames.get(parsed.path) if reference else None
            if frame is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._asset(frame, "image/png")
            return
        files = {
            "/": ("index.html", "text/html"),
            "/studio.css": ("studio.css", "text/css"),
            "/studio.js": ("studio.js", "text/javascript"),
        }
        if parsed.path not in files:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        name, mime = files[parsed.path]
        self._asset((ASSETS / name).read_bytes(), f"{mime}; charset=utf-8")

    def _asset(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-SVM-Studio", "1")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; "
            "style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def do_POST(self) -> None:  # noqa: N802
        if not self._trusted_host():
            return
        if self.path != "/api/action":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if self._trusted_mutation_request():
            self._handle(self._action)

    def _action(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_SEGMENT_REQUEST:
            raise ValueError("请求超过工作台上限或内容为空")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("无效的编辑请求")
        if length > MAX_BODY and payload.get("action") not in {
            "prepare-segment",
            "inspect-guided-source",
        }:
            raise ValueError("普通编辑请求超过 2 MiB 上限")
        return self.studio.action(payload)


def create_server(
    *, port: int = 4180, reference_bundle: Path = DEFAULT_REFERENCE_BUNDLE
) -> ThreadingHTTPServer:
    class Handler(StudioHandler):
        studio = Studio(reference_bundle)
        session_lock = threading.Lock()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def _running_studio(port: int) -> bool:
    connection = HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        return response.status == HTTPStatus.OK and response.getheader("X-SVM-Studio") == "1"
    except (OSError, HTTPException):
        return False
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the local SVM Studio")
    parser.add_argument("--port", type=int, default=4180)
    parser.add_argument("--open", action="store_true", help="Open the Studio in your browser")
    parser.add_argument("--reference-bundle", type=Path, default=DEFAULT_REFERENCE_BUNDLE)
    args = parser.parse_args()
    if (
        args.open
        and args.reference_bundle == DEFAULT_REFERENCE_BUNDLE
        and args.port
        and _running_studio(args.port)
    ):
        webbrowser.open(f"http://127.0.0.1:{args.port}/")
        return
    with create_server(port=args.port, reference_bundle=args.reference_bundle) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"SVM Studio  {url}", flush=True)
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
