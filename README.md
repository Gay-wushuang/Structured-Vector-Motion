# Structured Vector Motion

SVM is an experimental, non-destructive 2D construction computation model.
The current Document Format v0.1 is a development draft, not a frozen
compatibility contract. Until the first public format freeze, its schema may
change while `schema_version` remains `0.1`; every such change must update the
schema, specification, fixtures, and tests atomically.

The current v0.1 draft baseline contains:

- the core model, invariants, and Document Format specification;
- a Draft 2020-12 JSON Schema;
- a deliberately small deterministic reference evaluator;
- atomic Transactions and content-addressed Revision snapshots;
- `SplitEntity` and Golden Tests A/B;
- an Adapter/Proposal boundary with optimistic base-revision acceptance.
- quality-aware evaluation keys and Golden Test A.1;
- fail-closed Proposal handling for unsupported constraints and permissions;
- an explicit invariant coverage matrix.
- a formal system-boundary specification separating Adapters, Artifacts,
  Backends, Evaluator, Renderer, and Exporter.
- a semantics-versioned Operation Registry with explicit static and dynamic
  input/output signatures.
- a capability-oriented Geometry Backend boundary with deterministic Shapely
  Boolean operations and canonical polygon Values.

Run the golden test with:

```powershell
python -m unittest discover -s tests -v
```

Use the reference CLI with:

```powershell
python -m svm validate examples/001-head-basic.svm.json
python -m svm inspect examples/001-head-basic.svm.json
python -m svm evaluate examples/001-head-basic.svm.json --quality FINAL
python -m svm reevaluate examples/001-head-basic.svm.json --set op:head_base.rx=0.42
python -m svm render-svg examples/001-head-basic.svm.json --output scene.svg
```

See `spec/07-minimal-cli.md` for the command contract.

The reference SVG path is:

```text
Document -> FINAL Evaluator -> Evaluated Scene -> SVGRenderer -> SVG
```

See `spec/08-svg-renderer.md` for supported geometry and explicit limitations.

## Rendered showcase

The styled character example exercises authored presentation styles, clipping,
paths, render ordering, provenance, and deterministic SVG generation:

- `examples/004-styled-character.svm.json`
- `examples/rendered/004-styled-character.svg`

The test suite regenerates the SVG in memory and compares it byte-for-byte with
the checked-in artifact.

## Deterministic SVG import

The first external Adapter integration imports a deliberately strict SVG subset
through the Artifact and Proposal boundary:

```powershell
svm import-svg examples/005-empty-canvas.svm.json `
  examples/assets/001-import-source.svg `
  --namespace golden `
  --output imported.svm.json
```

Review the complete golden chain:

- `examples/assets/001-import-source.svg`
- `examples/imported/006-imported-source.svm.json`
- `examples/rendered/006-imported-source.svg`

See `spec/10-svg-import-adapter.md` for the supported subset and rejection rules.

## Deterministic geometry backend

The second external capability executes an accepted `BooleanGeometry` Operation
through the capability-oriented `GeometryBackend` interface:

```powershell
svm render-svg examples/007-boolean-geometry.svm.json `
  --geometry-backend shapely `
  --output boolean.svg `
  --view-box 0 0 180 140
```

The current Shapely implementation intentionally supports rectangles and
canonical polygon sets only. Review the golden result at
`examples/rendered/007-boolean-geometry.svg` and the contract in
`spec/11-geometry-backend.md`.

## Path to planar geometry

The curve-to-filled-area boundary is an explicit registered Operation:

```text
CreatePath -> path_data
PathToPolygon(tolerance, fill_rule) -> polygon_set
BooleanGeometry -> polygon_set
```

`tolerance` is recorded in Document coordinate units; open subpaths and arcs
fail closed in the initial subset; self-intersections are interpreted through
the recorded fill rule. See `spec/12-path-to-planar-geometry.md`, Golden D in
`examples/008-golden-d.svm.json`, its byte-stable rendered SVG, and
`tests/test_path_to_polygon_contract.py`.

## Deterministic bitmap trace

Golden E proves the first bitmap-to-planar vertical slice:

```powershell
svm trace-bitmap examples/005-empty-canvas.svm.json `
  examples/assets/003-bitmap-trace-source.png `
  --namespace fixture `
  --output traced.svm.json
```

The Adapter proposes an explicit `CreatePath -> PathToPolygon` chain and never
mutates the base Revision. The reference `potracer` engine is GPL-2.0-or-later
and is isolated in the optional `trace` dependency; see
`spec/13-bitmap-trace-adapter.md` for recorded parameters and license boundary.

Disconnected filled components are emitted as independent Entities and
Operation chains; nested holes remain owned by their enclosing component.
Golden F is recorded in `examples/imported/010-structured-trace.svm.json` and
`examples/rendered/010-structured-trace.svg`. See
`spec/14-structured-trace-components.md` for deterministic ordering and the
explicit limit between topology and semantic recognition.

An accepted trace can be compared with a replacement bitmap without immediate
mutation. `svm retrace-bitmap` returns a structured Entity diff by default; add
`--accept --output <document>` to commit it. Golden G demonstrates unchanged,
changed, added, and removed components while preserving matched Entity and
Operation IDs. Every proposed match exposes IoU, centroid, filled-area,
normalized contour, and composite scores. See
`spec/15-entity-reconciliation.md`.

## OpenCV artifact analysis

OpenCV analysis is intentionally separate from vectorization:

```powershell
svm analyze-bitmap examples/005-empty-canvas.svm.json source.png `
  --threshold 128 --derived-dir analysis-output
```

The v0.2 input subset is intentionally limited to 8-bit opaque grayscale PNGs,
so threshold samples do not depend on an implicit color conversion. It emits a
provenance-free content-addressed binary mask, canonical connected-component
JSON, and previewable structural candidates containing half-open pixel bounds,
pixel area, centroid, and a canonical component pixel-set digest. It creates no
Entity or Operation. Add `--accept --output` only to attach the analysis
evidence to a new Revision. See Golden H and
`spec/16-opencv-artifact-analysis.md`.

Promote selected accepted evidence regions without rerunning image analysis:

```powershell
svm promote-components examples/imported/012-opencv-analysis.svm.json `
  examples/derived/012-opencv-analysis/component-analysis.json `
  --candidate candidate:component-0001 `
  --candidate candidate:component-0002
```

The command previews deterministic neutral Region Entities. Add `--accept
--output promoted.svm.json` to create a Revision. Promotion reads only the
accepted canonical analysis JSON; it does not open the PNG, call OpenCV, create
vector geometry, or claim real-world semantic classes. See Golden I and
`spec/17-component-promotion.md`.

Accepted Promotion also materializes an independent Structural Relations graph.
Every Region gets an evidence-backed `derived-from` edge; candidates from the
same analysis get `bounds-contains` only for immediate nesting of their unequal
half-open bounds. These edges do not claim filled-region containment and do not
modify `parent_id`, Render Stack order,
construction, or animation. See Golden J and
`spec/18-structural-relations.md`.

## LayerPeeler research output

Golden K consumes a fixed, content-addressed snapshot of an external LayerPeeler
run. Its canonical manifest records the upstream commit, model identity,
checkpoint hash, seed, source Artifact, SVG hashes, and back-to-front layer
order. The Adapter never imports or executes the research model; accepted SVG
shapes are normalized through the existing SVG subset into ordinary Entities,
Operations, Styles, and Render Stack entries. See
`spec/19-layerpeeler-output-adapter.md` and
`tests/test_layerpeeler_output_adapter.py`.

## LayerD raster layer evidence

Golden L consumes a manifest-bound snapshot of LayerD's different output shape:
RGBA PNG layers plus canonical layer-analysis evidence. The Adapter records the
background/extraction sequence as evidence, not Render Stack order. It promotes
only neutral, non-rendered Region Entities; text/vector/image classifications
remain reviewable candidates in the Artifact and Proposal notes. Acceptance
reconstructs the exact Change from resolved bytes through the same Change
Authority Registry used by Golden K, without adding a LayerD branch to
`ProposalAcceptor`. See `spec/20-layerd-output-adapter.md` and
`tests/test_layerd_output_adapter.py`.

## Motion Semantics

Golden M is the first content-motion slice. A versioned Track animates
`op:moving-rectangle.x` over an integer 1000-tick-per-second Timebase, producing
checked-in deterministic SVG Frames at 0, 0.5, and 1 second. Entity, Operation,
Track, and Keyframe identity stay stable; editing the middle Keyframe invalidates
only affected sampling ticks, while an independent static rectangle reuses the
same immutable Value across time. See `spec/21-motion-semantics.md`,
`examples/017-motion-rectangle.svm.json`, and `tests/test_motion.py`.

Golden N connects Motion to persistent editing. `SetKeyframeValueChange` commits
one numeric Keyframe value as an atomic Revision without changing Track,
Keyframe, Operation, or Entity identity. Revision transition keeps unaffected
Frames and shared immutable Values, invalidates only the changed interpolation
domain, and leaves the prior Revision independently evaluable and recoverable by
Undo. See `spec/22-motion-revisions.md` and `tests/test_motion_revision.py`.

Editor Vertical Slice 02 turns this closed Core behavior into a small generic
Document inspector. `svm-motion-editor` opens a server-selected simple SVM
Document, derives Structure and Inspector projections from it, renders static
Documents through `Evaluator` and animated Documents through `MotionEvaluator`,
and displays `No Motion` when no content Track exists. Motion edits preview an
isolated `Transaction.apply()` snapshot and commit untrusted UI intent through
`ProposalAcceptor` into `RevisionStore`. Parent checkout restores the prior
accepted Document and Canvas. Run the default Motion example with:

```powershell
svm-motion-editor --port 4175
```

Or inspect a compatible static Document:

```powershell
svm-motion-editor --document examples/018-anchored-regeneration.svm.json --port 4175
```

The implementation lives in `svm/editor_motion.py`, `svm/editor_server.py`, and
`editor/motion-timeline/`; its vertical-slice contract is exercised by
`tests/test_editor_motion.py`. The durable Shell adds Project, Structure,
Canvas, Inspector, and Timeline regions. Entity selection remains disposable
Editor State while bindings, parameters, Render Stack order, and Track links
are read from the real Document. The current fail-closed compatibility subset is
`CreateRectangle`, `CreateEllipse`, and existing Motion v0.1/v0.2 numeric Tracks.
The Timeline exposes all Tracks, including multiple parameters on one Operation;
`examples/019-editor-multitrack.svm.json` covers independent `x`/`y` editing at
24 ticks/s. Local mutation endpoints require the exact bound Host, same-origin
or absent Origin, JSON media type, and an Editor preflight-marker header. The
public marker is browser cross-site protection, not a secret local capability.

Editor Vertical Slice 03 adds the first real authoring path. A static Rectangle
parameter can become a numeric linear Track through an atomic
`CreateTrackChange + AddKeyframeChange` Transaction, then receive further
Keyframes as accepted child Revisions. See `spec/24-motion-authoring.md` and
`tests/test_motion_authoring.py`. The active Operation Definition explicitly
declares eligible parameters; numeric parameters are non-animatable by default.
This stricter contract is recorded as `svm-motion@0.2`; legacy
`svm-motion@0.1` Documents retain their original finite-numeric target rule.
Compatible v0.1 authoring migrates in the new Revision; incompatible legacy
targets make that migration fail atomically.

## Anchored Regeneration

Golden O treats a Proposal as a candidate future rather than accepted history.
An `AnchoredRegenerationContract` binds candidates to one immutable base
Revision, protects exact ChangeAuthority targets, and allowlists exact downstream
impacts. Core computes impact from the executable registered Changes instead of
trusting generator metadata. Multiple accepted candidates can therefore become
sibling Revision children without mutating their common base or each other. See
`spec/23-anchored-regeneration.md`,
`examples/018-anchored-regeneration.svm.json`, and
`tests/test_anchored_regeneration.py`.

Contracts are validated against their exact base snapshot. Registered actions,
Operation parameters, Entities, Tracks, and Keyframes must exist. Motion impact
uses `(set_keyframe_value, Track ID, Keyframe ID)`, allowing one Keyframe without
implicitly authorizing every Keyframe on the Track.

The first user-facing Golden O interaction study lives in
`prototype/anchored-regeneration/`. It demonstrates a strict red-to-orange edit,
locked geometry/face targets, exact Highlight and Shadow regeneration scope,
deterministic A/B/C pending candidates, impact inspection, and acceptance into a
visible child Revision. The prototype is browser-only Editor State and does not
add UI fields to the SVM Document or invoke an AI model.

Editor Vertical Slice 04 moves that interaction into the durable Editor Shell.
With `examples/018-anchored-regeneration.svm.json`, the UI constructs a real
`AnchoredRegenerationContract`, exposes deterministic A/B/C as pending
Proposals, renders isolated Proposal previews, and accepts A and B through
`ProposalAcceptor.accept_anchored()` as sibling Revisions. The generator remains
a deterministic fixture; replacing it with an AI does not widen acceptance
authority. See `spec/25-editor-anchored-regeneration.md` and
`tests/test_editor_motion.py`.

## Phase 1 — FINAL / FROZEN

Phase 1 is final and frozen at the implementation baseline
`0caae5b8061bfd12901bdb0898f171d4ad5d48a4`.

The Phase 1 demonstrator packages the proven recovery chain into one reproducible
command:

```text
real AVI/FFV1
-> deterministic video ingestion
-> explicit raster observations -> temporal identity evidence
-> observed translation / similarity evidence
-> multi-anchor Camera consensus -> camera compensation
-> explicit Motion Target Binding -> 12 ordinary editable SVM Tracks
-> ordinary Revision / Transaction Keyframe edit
-> MotionEvaluator -> SVG re-render
```

```powershell
svm demo-phase1 --output-directory build/phase1-demo
```

It adds no recovery semantics: it calls S11D ingestion, the frozen S11A/S11B/S11C
adapters, ordinary Document/Revision authoring, `MotionEvaluator` and
`SVGRenderer`. It requires no Ground Truth at run time, yields one ordinary
12-Track Document, and proves that one explicit edit changes only its intended
Target/tick while the unrelated Target B and the Camera stay unchanged. See
`examples/039-controlled-video-editable-svm/README.md`.

- `spec/60-phase1-d1-freeze.md` — the D1 freeze record: guarantees, non-claims
  and change control.
- `spec/61-d2-showcase-packaging.md` — the D2 showcase specification (a
  projection of D1 evidence, not a new inference stage). The minimal static,
  offline projection is available through `svm showcase-phase1`.
- `spec/62-phase1-final-freeze.md` — the Phase 1 final freeze record:
  implementation baseline, verified pipeline, D1/D2 acceptance, and the
  conservative Phase 1 non-claims.

Phase 2: `spec/63-phase2-charter.md` (charter). P2A, Raster Primitive Observation
Proposal, is **FINAL / FROZEN** —
`spec/64-p2a-raster-primitive-observation-proposal.md` (normative contract),
`spec/65-p2a-final-freeze.md` (freeze record). P2B, Primitive Observation
Assembly, is **FINAL / FROZEN** —
`spec/66-p2b-primitive-observation-assembly.md` (normative contract),
`spec/67-p2b-final-freeze.md` (freeze record). P2C, Temporal Identity Selection,
is **FINAL / FROZEN** —
`spec/68-p2c-temporal-identity-selection.md` (normative contract),
`spec/69-p2c-final-freeze.md` (freeze record).
It selects all existing SUPPORTED candidates from one accepted R0 artifact,
delegates promotion to frozen R1, and atomically binds the selection evidence to
that exact promotion. See
[Golden P2C](examples/042-temporal-identity-selection/README.md).
The adapter uses a direct module import; CLI preview/accept packaging remains
a non-semantic follow-up.

P2D, Exact-Provenance Motion Target Binding Selection, is
**SPECIFIED / NOT IMPLEMENTED** —
`spec/70-p2d-exact-provenance-motion-target-binding.md` (normative contract). It
defines an exact structural / provenance correspondence from an accepted temporal
identity to an existing Document Group, with no geometric inference, full
delegation to the frozen Motion Target Binding Change, and abstention whenever no
exact provenance path exists. P2D-A's pure derivation and focused tests exist;
there is no executable P2D Proposal/Change registration or Golden fixture.
Its common-source rule does not cover ordinary cross-frame component identity.
P2D-B is blocked on the [stable artwork representation correspondence contract](spec/71-stable-artwork-representation-correspondence.md),
which reuses Entity/Group and separates frame-local evidence from persistent
artwork. That prerequisite is **DESIGN CONTRACT / NOT IMPLEMENTED / NOT FROZEN**;
its temporal construction and proof-admission profiles remain unresolved.
P2S-A identified **GROUP_CONSTRUCTION_AUTHORITY_BLOCKER** — a historical finding
at its inspected baseline. P2S-B
[Construction-Derived Group Authority](spec/72-construction-derived-group-authority.md)
is **IMPLEMENTED FOR FIRST BOUNDED PROFILE / NOT FROZEN**, with atomic
construction replay and a distinct provenance branch preserving legacy POP
Groups. P2S-C
[Explicit Two-Part SVG Group Construction](spec/73-svg-two-part-group-construction.md)
is **IMPLEMENTED / GOLDEN VERIFIED / NOT FROZEN**. P2S-D stabilized the first
executable authority/profile slice and verified mixed-origin coexistence:
legacy inference Groups and construction Groups coexist, `promote_group` and
`establish_group` remain distinct policy authorities, and old POP evidence stays
stale after Document mutation. The implemented profile is the exact bounded
rect + ellipse SVG subset only; arbitrary SVG Groups, arbitrary source profiles
and video sources are not supported. Remaining: video multipart subject
ownership evidence is required, the Stable Artwork Representation
Correspondence temporal profile is not implemented, video vector stylization and
video repair are not addressed, P2D-B remains **BLOCKED**, and Single-Entity
Motion Target remains an **OPEN SEPARATE ARCHITECTURAL QUESTION**.

P2S-E0's [video multipart subject evidence audit](spec/74-video-multipart-subject-evidence.md)
identified the missing authored ownership and source-to-video bridge.
[P2S-E1A](spec/75-authored-multipart-raster-production.md) supplies the bounded
production capability with unchanged P2A/P2B gates.

[P2S-E1B](spec/76-first-bounded-multipart-subject-evidence-profile.md) now implements
the first bounded Multipart Subject Evidence runtime: **IMPLEMENTED / GOLDEN
VERIFIED / NOT FROZEN**. Its dedicated `attach_analysis` Change authenticates
Revision witnesses against the proposal base and independently replays the
complete two-part/two-occurrence closure. Only reproduced SUPPORTED evidence is
appended. UNCERTAIN/REJECTED results remain diagnostics; applicable equivalent
claims reuse their Artifact, and incompatible supported ownership claims reject.
The Spec75 report supplies no authority.

Ordinary-video ownership inference is **NOT SOLVED**; arbitrary-video whole-subject
TemporalIdentity is **OPEN**; Stable Representation Correspondence is the
**NEXT GATE**; P2D-B remains **BLOCKED**; Single-Entity Motion Target remains
**OPEN**. E1 is **CLOSED for its bounded authored-source profile** and is not
generally frozen. Entity/Group semantics are unchanged.
[P2S-E1C](spec/77-trusted-spec76-admission-history.md) extends Core
acceptance with versioned trusted admission events: generic attachment cannot
establish Spec76 authority, and legacy unproven references remain historical
data until a fresh dedicated proposal is independently verified and accepted.
[P2S-F0](spec/78-first-video-backed-artwork-construction-profile.md) implements
the first video-backed artwork construction profile: **IMPLEMENTED / GOLDEN
VERIFIED / NOT FROZEN**. It consumes only genuinely admitted Spec76 evidence,
authenticated through Spec77 history, and atomically establishes two renderable
path Entities plus one construction-origin Group with a neutral initial
Transform. It creates no TemporalIdentity, Track or MotionTargetBinding;
Stable Representation Correspondence remains the **NEXT GATE**; P2D-B remains
**BLOCKED**.

[P2S-F1A](spec/79-source-backed-whole-subject-observation-bridge.md) adds the bounded
source-backed whole-subject observation bridge for the existing two-triangle,
two-occurrence Spec75/76 fixture. Genuine Spec77 admission and complete Spec76
replay produce one bounds-only subject observation per occurrence in the existing
v0.1 observation envelope. The actual frozen R0 derives correspondence; a dedicated
verifier replays the original membership and complete R0 output before delegating
to unchanged R1. The [Golden](examples/045-subject-observation-bridge/README.md)
pins one new whole-subject TemporalIdentity distinct from both preserved part
identities. Companions remain recomputable data; consumers must independently
verify source-backed meaning. Landmark geometry, artwork correspondence, motion
target binding and P2D-B remain separate gates.

[P2S-F1B](spec/80-present-time-representation-certification.md) adds one bounded
present-time representation certification mode to Spec71, now **FROZEN FOR ITS
BOUNDED V0.1 PROFILE** after an independent Gate **PASS** (36 focused and 706
full-suite tests, GitHub CI 4/4). Its independent
verifier authenticates Spec76/77 ownership, reproduces the accepted Spec79 whole
identity and the complete historical Spec78 birth, then certifies the unchanged
current T-to-G relationship through a distinct trusted admission event. Birth
replay proves structural conformity; it does not claim that a dedicated F0
verifier or association existed at birth. [Golden 046](examples/046-representation-certification/README.md)
retains the original Group, Entity and TemporalIdentity IDs and the null-claim
F0 receipt. Generic canonical bytes and low-level commit without an event remain
data. Ordinary artwork editing remains legal; this initial profile requires
unchanged representation definitions for fresh applicability verification.
It creates no motion binding or animation and does not implement P2D-B or close
the broader Spec71 correspondence gates. The freeze covers only the bounded
present-time certification v0.1 semantics; Spec71's original atomic
construction-for-T mode stays a design contract.
[Spec/81](spec/81-versioned-representation-target-consumer-contract.md) is a
**DESIGN ONLY / NOT IMPLEMENTED** P2D-B0 consumer contract draft; P2D-B remains
**BLOCKED** and is not ready.

## Development

Install the project and development tools in editable mode:

```powershell
python -m pip install -e ".[dev,geometry,svg,trace,analysis]"
```

Run the same checks used by CI:

```powershell
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m unittest discover -s tests -v
svm validate examples/001-head-basic.svm.json
```

CI runs this sequence on Windows and Linux with Python 3.11 and 3.12.

The implementation proves isolated DAG invalidation, lazy reevaluation,
immutable content-addressed outputs, stable and structural entity identity,
atomic revision creation, undo by parent revision, and Proposal isolation. It is
not yet an editor or production renderer.

See `spec/04-invariant-coverage.md` for the distinction between implemented,
fail-closed, and specification-only normative behavior.

### Local environment note

Phase 1 is verified against an isolated project-local Python environment. The
ignored, machine-local `.venv` can be contaminated — for example, resolving part
of the Python standard library through a separate installation — and then fail to
import `pyexpat` with a Windows DLL access error, which makes every
XML-dependent test error. That is a local interpreter/environment issue, not a
Phase 1 product defect; use the isolated project-local environment to reproduce
the full-suite result.
