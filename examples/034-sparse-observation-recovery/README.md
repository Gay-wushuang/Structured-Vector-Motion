# S10D one missing target occurrence

Sample ticks: 0, 12, 24, 36 at 12 ticks/second; viewBox [0, 0, 200, 120].
Both static anchors remain visible. Target is genuinely absent from the frozen
tick-12 SVG. The fixture generator copies the authored Document, removes Target
from its formal static `presentation.render_stack` for that render input, then
uses MotionEvaluator and SVGRenderer. It does not edit SVG strings or add a
visibility system.

Camera positions are [0,0], [1,-0.5], [2,-1], [2,-1], rotations 0,1,3,3 degrees,
and scales 1,1.01,1.03,1.03. Thus both Camera intervals across the Target gap move,
and the final interval holds. Target retains fixed Group origin [37,43], rotation
10→25 degrees, scale 1→1.2, and translation [0,0]→[6,-2].

Recovery reads `recovery-base.svm.json` and frozen SVG files, explicitly promotes
the SUPPORTED 0→24 correspondence under the one-missing-occurrence policy, and
extends the same Temporal Identity to 36. S10C consensus remains dense. Its exact
absolute Camera endpoints compensate sparse Target intervals 0→24 and 24→36.

Recovered Group Tracks have keyframes only at 0,24,36; Camera Tracks have all
four ticks. Target sampling at 12 is runtime interpolation and is not compared
as observed recovery. The visibility omission is not inferred as an authored
visibility Track.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_sparse_observation_recovery.py -v
```

Tests verify these checked-in documents/SVGs, actual absence, formal abstention,
endpoint math, eight Tracks, identity/provenance, deterministic replay, atomic
rejection and formal reobserved geometry. Ground Truth is only a fixture generator
input and final assertion reference; recovery never reads hidden target poses.
