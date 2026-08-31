# Editor Vertical Slice 03 — Motion Authoring

This is the first SVM Editor surface backed by the real Python Core rather than
a browser-side simulation.

```powershell
python -m svm.editor_server --port 4175
```

Open `http://127.0.0.1:4175/`.

Pass another compatible Document with `--document`:

```powershell
python -m svm.editor_server --document examples/018-anchored-regeneration.svm.json --port 4175
```

The Editor derives Structure, Inspector, Canvas, and Timeline state from the
loaded Document. The browser only supplies selection, an integer tick, or a
proposed Keyframe value. Core owns all semantic work:

```text
Simple SVM Document
  -> MotionEvaluator
  -> EvaluatedScene
  -> SVGRenderer
  -> Canvas

drag / value edit
  -> isolated Transaction.apply preview
  -> MotionEvaluator.transition_to_revision
  -> no Revision

Commit
  -> SetKeyframeValueChange
  -> Proposal
  -> ProposalAcceptor
  -> RevisionStore
  -> real child Revision
```

Checkout uses the real parent Revision snapshot. The Frame cache labels are
derived from actual retained and evaluated `MotionEvaluator.frame_cache` keys.
This slice supports `CreateRectangle`, `CreateEllipse`, and existing Motion v0.1
or v0.2 numeric Tracks. Static Documents render through the real Evaluator and show
`No Motion`; animated Documents render through `MotionEvaluator`. Unsupported
Operation types fail closed instead of being approximated by the Editor.
The Timeline lists every Track in the Document, including multiple Tracks that
target one Operation. Selecting a Track changes only disposable Editor State;
preview and commit still name the exact Track and Keyframe.

Vertical Slice 03 also authors Motion into an existing static Rectangle:

```text
select an untracked numeric parameter
-> CreateTrackChange + AddKeyframeChange @ tick 0
-> ProposalAcceptor -> Revision R1
-> AddKeyframeChange @ an explicit tick
-> ProposalAcceptor -> Revision R2
-> deterministic linear playback
```

The initial Track and Keyframe share one Transaction because accepted Motion
Documents do not admit an empty Track. New authoring records Motion v0.2; a
compatible v0.1 Document migrates explicitly in the successor Revision. The UI
defaults new static animation to 24 ticks/s and exposes an existing Document
timebase as read-only. Authoring choices come from the Operation Registry's
explicit `animatable_parameters`, not JavaScript numeric-type inference or
Operation-name conditionals.

The durable Shell has four long-lived regions:

- Project Toolbar identifies the loaded Document and real Revision hash.
- Structure lists real Entities in Render Stack order without treating that
  order as semantic hierarchy.
- Canvas renders the real SVG Frame and uses Editor-only selection highlighting.
- Inspector reads the selected Entity's accepted binding, Operation parameters,
  and Track association; Timeline retains the real Motion vertical slice.

Selection and panel layout are disposable Editor State. No Shell field is added
to the SVM Document interchange model.

## Untrusted Document boundary

All Document and API projection fields are inserted as DOM text nodes. Entity
names, IDs, Operation data, parameters, and Keyframes are never parsed as HTML.
The Core-rendered SVG is parsed as XML and rejected if it contains scripts,
`foreignObject`, event-handler attributes, or a non-SVG root. This is a
defensive layer for the current Core Renderer output subset, not a general SVG
sanitizer. If Renderer support grows to resource-bearing SVG, the Canvas must
adopt an explicit element and attribute allowlist. Non-rendered
Entities sort after Render Stack members instead of being treated as render
index zero. If a newly loaded projection no longer contains the selected Entity,
selection moves to the first available Entity or becomes empty.

## Local API trust boundary

The server binds to `127.0.0.1` by default. Every mutation endpoint also
requires the exact bound `Host`, an absent or exact same-origin `Origin`,
`Content-Type: application/json`, and `X-SVM-Editor-Request: 1`. The custom
header forces cross-origin browser scripts through a CORS preflight, which this
server does not authorize. Read-only state access does not confer mutation
authority. The public constant is a CSRF/preflight marker, not a secret local
capability; a production threat model that includes hostile local processes
must replace it with a random per-session capability.

`examples/019-editor-multitrack.svm.json` is the interaction fixture for two
Tracks targeting `x` and `y` on one Entity with a non-decimal 24 ticks/s
timebase. Tick 12 is displayed as `00:00.500`, while the exact tick remains
visible separately.
