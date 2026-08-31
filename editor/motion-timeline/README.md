# Editor Shell v0.1 — Real Motion Editing

This is the first SVM Editor surface backed by the real Python Core rather than
a browser-side simulation.

```powershell
python -m svm.editor_server --port 4175
```

Open `http://127.0.0.1:4175/`.

The browser only supplies an integer tick or a proposed Keyframe value. Core
owns all semantic work:

```text
Golden M Document
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
This slice intentionally supports only the one three-Keyframe Track in
`examples/017-motion-rectangle.svm.json`.

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
`foreignObject`, event-handler attributes, or a non-SVG root. Non-rendered
Entities sort after Render Stack members instead of being treated as render
index zero. If a newly loaded projection no longer contains the selected Entity,
selection moves to the first available Entity or becomes empty.
