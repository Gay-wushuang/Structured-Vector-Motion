# D2 — Human-readable Phase 1 Showcase Packaging

Status: specification only, not implemented. D2 adds no recovery, inference,
Document, Change Authority, evaluation or rendering semantics. It consumes a
completed D1 evidence bundle and projects it into a human-readable showcase.

Governing input: `spec/60-phase1-d1-freeze.md` (D1 freeze record) and the frozen
Phase 1 chain it describes.

## Boundary

> **D2 is a projection of D1 evidence, not a new inference stage.**

D2 exists only to turn the deterministic D1 evidence bundle into something a
person can quickly understand. It must not:

- run recovery, ingestion, correspondence, compensation or Track authoring;
- invoke any recovery adapter or the D1 orchestrator;
- infer, measure or recompute any motion, geometry, transform or identity;
- create new semantic evidence;
- modify, rewrite or "clean up" any SVM Document;
- widen or reinterpret any D1 claim from `spec/60`.

Everything D2 shows already exists in the D1 bundle. If a value is not present
in the D1 artifacts, D2 shows nothing rather than deriving it.

## What a person must be able to see

1. **Input** — reach the authoritative input (`source/scene.avi`) and preview it
   in the browser through the existing canonical D1 PNG Frames.
2. **Recovered result** — the recovered Document's re-rendered Frames.
3. **Edited result** — the edited Document's re-rendered Frames.
4. **What the edit changed** — the exact Target, property, tick, before/after
   values and the two Revision identities.
5. **Why the recovered result is editable SVM, not baked video** — evidence that
   the result is an ordinary Document with Track/Keyframe structure, that one
   edit changed exactly one tick/property, and that unrelated Target and Camera
   state stayed identical.

## Presentation constraints

- **Static, offline, no server.** The showcase opens directly from the local
  filesystem and requires no network access, no CDN and no build step at view
  time.
- **Minimal stack.** Dependency-free HTML/CSS/JS, or the repository's existing
  minimal technology stack. No UI framework is assumed by this specification.
- **Consume the D1 bundle directly.** Reference D1 artifacts by relative path;
  do not copy their semantic content into a parallel authority.
- **No recovery, no re-inference, no Document mutation.** Generation may read
  D1 artifacts; it must not write to them.
- **No Ground Truth.** Ground Truth is never a showcase input or runtime
  dependency.
- **Deletion-safe.** Removing the showcase leaves the D1 bundle intact and
  re-generable.
- **Deterministic where practical.** The same D1 bundle produces an equivalent
  showcase on repeated generation; no wall-clock time, temporary path, random
  filename or random identifier is recorded.
- **No absolute machine paths.** All D1 references are relative, POSIX-style
  paths from the showcase root.

Because browsers restrict `fetch()`/XHR on `file://`, the showcase's runtime
data must not depend on those APIs. The projection index is embedded at
generation time (for example an inline JSON block in `index.html`); the browser
loads D1 media through ordinary relative references — `<img>` elements, or
`img.src` changes in JS, for the rendered SVG and PNG Frames, plus download
links for the Documents and the input video. No server, no `fetch()` and no
runtime API is introduced.

## Input media: authoritative source versus browser preview

### Authoritative input

`source/scene.avi` remains the original, authoritative D1 video artifact: it is
the recovery input and the D1 provenance anchor. The showcase must:

- provide a direct relative link to that file;
- display the already-recorded D1 metadata for it — container, codec and
  dimensions — read from `report.json` (`input.container`, `input.codec`,
  `input.width`, `input.height`, plus related `input.*` fields).

The original AVI is never replaced, transcoded or superseded as the source of
truth.

### Browser-visible input preview

Native browser playback of AVI/FFV1 is not a supported or reliable capability:
FFV1 is not a codec a general web browser can be depended on to decode. The
browser-visible input preview is therefore built only from D1 artifacts that
already exist:

- the canonical frames `frames/<sha256>.png`;
- the frame/tick relationship from `report.json` (`input.tick_mapping`) and the
  verified `source/video-manifest.json`.

The showcase presents these as a simple frame/tick selector or a frame-sequence
playback. The preview must not:

- re-decode the AVI;
- transcode to MP4/WebM or any other video format;
- generate a new video derivative;
- invoke recovery or ingestion;
- infer anything from pixels;
- derive the PNG/tick relationship from anywhere except the existing D1
  report/manifest.

A `<video>` element pointed at the original AVI is permitted only as best-effort
native playback. It must never be a portability or acceptance guarantee: if the
browser cannot play FFV1, the showcase must remain fully usable through the PNG
frame preview.

## Proposed artifact layout

The D1 evidence bundle remains authoritative and is never modified. The
showcase is written as a disposable projection directory. The recommended
default places it inside the bundle root so the reference layout is fixed and
the bundle stays one transportable unit:

```text
<d1-bundle>/                         D1 authoritative evidence (unchanged, 18 files)
  config/phase1-demo.json
  source/scene.avi
  source/video-manifest.json
  frames/<sha256>.png
  documents/recovered.svm.json
  documents/edited.svm.json
  rendered/recovered/tick_000.svg
  rendered/recovered/tick_012.svg
  rendered/recovered/tick_024.svg
  rendered/recovered/tick_036.svg
  rendered/edited/tick_000.svg
  rendered/edited/tick_012.svg
  rendered/edited/tick_024.svg
  rendered/edited/tick_036.svg
  report.json

  showcase/                          D2 projection (regenerable, disposable)
    index.html                       static page + embedded projection data
    showcase.css
    showcase.js                      tick selection / before-after toggling only
    projection.json                  the same embedded projection, for review
```

An explicit separate output directory is also permitted; in that case the
generator records the D1 bundle's relative location and every reference remains
relative. The `showcase/` directory is not part of the D1 evidence manifest and
may be deleted at any time.

### Direct references versus derived content

| D1 file | D2 usage |
| --- | --- |
| `source/scene.avi` | **Direct reference** — authoritative input; direct relative link with D1 metadata, optional best-effort `<video>` playback, never a required preview. |
| `rendered/recovered/tick_0NN.svg` | **Direct reference** — recovered Frame images. |
| `rendered/edited/tick_0NN.svg` | **Direct reference** — edited Frame images. |
| `frames/<sha256>.png` | **Direct reference** — primary browser-visible input preview, joined to ticks via `report.json`/manifest. |
| `documents/recovered.svm.json` | **Direct reference** — optional inspect/download link; never modified. |
| `documents/edited.svm.json` | **Direct reference** — optional inspect/download link; never modified. |
| `report.json` | **Read at generation time** — the only source for the derived projection values below. |
| `config/phase1-demo.json` | **Direct reference** — provenance (configuration actually used). |
| `source/video-manifest.json` | **Direct reference** — provenance (Video occurrence join). |
| `showcase/projection.json` | **Derived** — projection index; contains no new semantics. |

Rules:

- `report.json` is the single machine-readable source for the projected values.
- Values are **copied verbatim** from `report.json` (or resolved by pure lookup
  in it). D2 must not recompute them from Documents, SVGs or pixels.
- The projection index must point back to the exact D1 files it was derived
  from, so a reader can always reach the authoritative artifact.
- No semantic content is duplicated into a second authority: the showcase is a
  view, and `report.json` plus the referenced artifacts stay authoritative.
- Ground Truth (`ground-truth.json`, `verification.json`) is never referenced,
  copied or required.

### Projection index (proposed minimal contents)

Every field is copied verbatim from `report.json` or resolved by pure lookup in
it, except the two explicitly marked D2 generator metadata items. No value is
inferred or recomputed.

D2 generator metadata (not present in `report.json`):

- generator identity and D2 `schema_version`;
- the D1 bundle's relative location and the D1 report identity.

Copied from `report.json`:

- input metadata and frame/tick mapping: `input.container`, `input.codec`,
  `input.width`, `input.height`, `input.frame_count`, `input.selected_frames`,
  `input.tick_mapping`;
- the edit record: `edit.role`, `edit.property`, `edit.tick`, `edit.track_id`,
  `edit.keyframe_id`, `edit.before`, `edit.after`, `edit.delta`,
  `edit.base_revision_id`, `edit.revision_id`, `edit.document_hash`;
- the validation summary: `validation.track_count_expected`,
  `validation.track_count_observed`, `validation.edited_target`,
  `validation.edited_group`, `validation.edited_tick`,
  `validation.changed_ticks`, `validation.re_rendered_changed_ticks`,
  `validation.other_targets_unchanged`, `validation.camera_unchanged`,
  `validation.edited_target_other_properties_unchanged`,
  `validation.recovered_revision_id`, `validation.edited_revision_id`;
- the recovered Track count and summary: `recovery.track_count`,
  `recovery.track_ids`, `recovery.scene_summary`;
- relative artifact pointers from `outputs`: `recovered_document`,
  `edited_document`, `recovered_rendered`, `edited_rendered`, the source video and
  the canonical frames.

The D1 bundle contains exactly **two** ordinary SVM Documents
(`documents/recovered.svm.json` and `documents/edited.svm.json`); the config and
manifest are provenance sidecars, not Documents. There is no
`validation.track_count` field — the track counts are
`validation.track_count_expected`, `validation.track_count_observed` and
`recovery.track_count`.

## Acceptance criteria

D2 acceptance is minimal but strict. A D2 implementation is acceptable only if
all of the following hold.

1. **Bundle-only generation.** The showcase can be generated from a completed
   D1 bundle alone, using no other input.
2. **Authoritative source reachable.** `source/scene.avi` remains the
   authoritative input and is directly reachable from the showcase through a
   relative link, with its D1 metadata (container, codec, dimensions) displayed.
3. **Browser preview without FFV1 support.** The browser-visible input preview
   works using the existing canonical D1 PNG Frames joined to ticks through the
   D1 report/manifest. Browser support for AVI/FFV1 is **not** required, and the
   showcase stays fully usable when the browser cannot play FFV1.
4. **No transcoding or derivative video.** Generation produces no MP4/WebM or
   other video derivative and does not re-decode the AVI.
5. **No recovery or ingestion invoked.** Generating the showcase imports and
   calls no recovery adapter, ingestion or the D1 orchestrator. A test can assert
   this by patching those entry points to fail.
6. **No Ground Truth required.** Generation and viewing succeed with
   `ground-truth.json` and `verification.json` absent or forbidden.
7. **No Document mutation; D1 byte-identical.** The recovered and edited
   Documents, and every other declared D1 file, are byte-identical before and
   after generation.
8. **Derived from existing D1 artifacts.** Every displayed motion, transform and
   render value comes from an existing D1 artifact; nothing is recomputed.
9. **Recovered versus edited comparison.** A person can compare the recovered
   and edited rendered Frames for each tick, including a before/after toggle.
10. **Identifiable edit.** A person can visually identify the one edited tick and
    property, and confirm the before/after values.
11. **Unchanged subjects shown unchanged.** The unrelated Target B and the Camera
    are visibly presented as unchanged, consistent with the D1 validation
    summary.
12. **No absolute machine paths.** No generated file contains an absolute machine
    path.
13. **Deterministic output.** Repeated generation from the same D1 bundle
    produces equivalent, byte-identical output.
14. **Deletion-safe.** Deleting the showcase directory leaves the D1 bundle
    intact and still re-generable.

Browser automation is **not** required unless the repository already has
infrastructure for it; verifying the generated projection and referenced
artifacts is sufficient.

## Explicit non-goals

D2 does not add: recovery or inference of any kind, new evidence, Document or
Revision changes, a server, a runtime API, new dependencies, an alternate
renderer, or any Phase 2 capability. It does not change `MotionEvaluator`,
`SVGRenderer`, or any frozen Phase 1 adapter.

## Suggested minimal implementation slice

A smallest implementation that satisfies this specification:

```text
svm showcase-phase1 --bundle <completed-d1-bundle> --output <showcase-dir>
```

- one module (`svm/phase1_showcase.py`) that reads `report.json` and the
  referenced D1 files, writes `index.html`, `showcase.css`, `showcase.js` and
  `projection.json`, and enforces the relative-path and no-mutation rules;
- one CLI subcommand in `svm/cli.py`;
- one test (`tests/test_phase1_showcase.py`) that generates a D1 bundle through
  the existing demo entry point, generates the showcase, and asserts acceptance
  criteria 1–14 above without browser automation.

No implementation is part of this freeze step; D2 remains specification-only
until that slice is explicitly scheduled.