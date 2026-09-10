# Camera Punch Authoring Demo 003

This eight-second authored SVM shot reuses Demo 002's Groups, easing, held
palette cuts, opacity flashes, and overlays, then adds only the Camera Motion
Slice. Camera position, rotation, and positive scale form one outer view
transform; no primitive or Group state is baked or rewritten.

The shot uses punch-in overshoot, settle, held framing, counter-pan, flash, and
return to the original wide composition. It adds no mask, deformation, new
easing, motion-intent object, or video-recovery behavior.

Rebuild from the repository root:

```powershell
python demo/003-camera-punch/build_demo.py
```

Full frame sequences are ignored reproducible outputs. Git retains the source
Document, builder, MP4, and five representative frames.
