# Synthetic Camera Compensation v0

`ground-truth.svm.json` contains independent linear target and Camera Tracks.
`recovery-base.svm.json` contains the same construction, explicit target Group,
static anchor, and tick-zero Camera baseline, but no animation Tracks.

Run `python export_observations.py` to reproduce the four frozen renderer SVGs.
Recovery consumes only those bytes, ticks, the Recovery Document, explicit
anchor selection, and explicit target binding. Ground-truth Tracks are used
only to export observations and in final test assertions.
