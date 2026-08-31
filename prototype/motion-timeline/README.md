# Motion Timeline Prototype

This dependency-free prototype translates the closed Golden M and Golden N
semantics into a product interaction. Serve this directory and open `index.html`.

```powershell
python -m http.server 4174 --directory prototype/motion-timeline
```

## Product slice

- Scrubbing the playhead samples `op:moving-rectangle.x` at an integer tick.
- The three stable Keyframes use linear interpolation and held endpoints.
- Dragging the middle diamond vertically, or changing its value control,
  creates an immediate unsaved preview without changing the committed Revision.
- `Commit keyframe change` represents one `SetKeyframeValueChange` and creates a
  new Revision while preserving Track, Keyframe, Operation, and Entity identity.
- The cache strip exposes the Golden N invalidation result: ticks `0` and `1000`
  remain reusable; `250`, `500`, and `750` are invalidated and lazily evaluated.
- `Restore R0` returns to the immutable fixture baseline. It deliberately does
  not claim to model a future stepwise Undo/Redo stack.

This is an interaction fixture, not a second Motion runtime or a replacement
for Core acceptance. The values and invalidation interval deliberately mirror
`spec/21-motion-semantics.md` and `spec/22-motion-revisions.md`.

## State transitions

| From | Event | Required result |
| --- | --- | --- |
| R0 | scrub playhead | deterministic preview; no Revision change |
| R0 | drag middle Keyframe | Canvas previews; committed Revision remains R0 |
| preview | return value to 300 | preview clears; commit disabled |
| preview | commit | R1 created; Track and Keyframe identity unchanged |
| R1 | inspect cache | ticks 0/1000 reused; 250/500/750 invalidated |
| invalid tick | scrub to tick | that Frame becomes reevaluated lazily |
| R1 | restore R0 | exact R0 motion restored |
