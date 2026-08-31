# Editor Vertical Slice 01 — Real Motion Editing

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
