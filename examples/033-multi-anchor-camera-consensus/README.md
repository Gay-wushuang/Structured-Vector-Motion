# S10C strict multi-anchor Camera consensus

`recovery-base.svm.json` contains two explicitly selected static anchors:
`entity:camera-anchor` and `entity:camera-anchor-b`. They have different asymmetric
polygon geometry at separated positions. The target Group retains origin [37, 43].

`ground-truth.svm.json` and `observations/tick_*.svg` define samples at 0, 12, 24,
36 ticks, with 12 ticks/second and viewBox [0, 0, 200, 120]. Camera position moves
from [0, 0] to [2, -1], rotation from 0 to 3 degrees, and scale from 1 to 1.03;
the first and last intervals hold. The target translates from [0, 0] to [6, -2],
rotates from 10 to 25 degrees, and scales from 1 to 1.2.

Recovery consumes the frozen SVG files, Recovery Document, ticks, explicit anchor
selections, and explicit target binding. Each anchor independently produces an
accepted S9B Camera hypothesis. S10C accepts only strict agreement, then its
consensus Artifact drives both Camera compensation and Camera Track creation.
The fixture never reads Ground Truth Tracks as recovery inputs.

Run from the repository root:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_camera_consensus.py -v
```

The test verifies checked-in snapshots, reversed input order, exact representative
selection, all eight recovered Tracks, and formal SVG geometry observations for
Anchor A, Anchor B, and Target at every sample. Numerical/geometry bounds are
`3e-8`; measured maxima are printed by the integration test.
