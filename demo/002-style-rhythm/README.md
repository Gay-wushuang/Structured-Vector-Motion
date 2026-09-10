# Style Rhythm Authoring Demo 002

This is an eight-second hand-authored SVM animation that applies the frozen
authoring slices to a more deliberate music-video-style composition.

It combines:

- two persistent character Groups using eased translate, rotate, and scale;
- repeated-value pauses plus authored overshoot and settle poses;
- an eased signal and overlay rhythm;
- held palette cuts on the background, characters, and overlay bars;
- eased halo pulses and three short opacity flashes;
- a fixed Camera and only primitive geometry.

There is no Mask, Camera animation, Shape deformation, video recovery, RGB
color interpolation, or additional easing type.

## Rebuild

From the repository root:

```powershell
python demo/002-style-rhythm/build_demo.py
```

The script writes the canonical `scene.svm.json`, samples ticks `0..192` at 24
fps, renders SVG and PNG frame sequences, encodes `demo.mp4`, and copies five
representative PNGs into `previews/`. Full frame directories are reproducible
build output and intentionally ignored by Git.

## Authoring questions answered by this demo

1. Easing removes the hard velocity corners that dominated Demo 001.
2. Held color changes and brief opacity accents establish a visible rhythm
   without requiring continuous color interpolation.
3. Rigid Groups remain useful across palette cuts and flashes because visual
   presentation changes do not disturb primitive or Group identity.
4. Pauses and overshoot can be authored entirely with ordinary Keyframes: no
   numeric hold interpolation or new curve semantics are needed for this shot.

The next Core capability should be chosen by viewing this result. This demo
does not pre-authorize Camera, Mask, Clip, or Shape deformation work.
