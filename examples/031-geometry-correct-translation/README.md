# Geometry-correct Group translation

The recovery base has two explicit Groups and an identity Camera. Target A is
an asymmetric polygon with fixed origin `[37, 43]`, different from its bounds
center `[50, 50]`.

- `ground-truth.svm.json`: A rotates and scales with zero translation.
- `camera-ground-truth.svm.json`: A also translates while the shared Camera
  moves. Target B moves independently in both Documents.

The integration test renders these definitions into frozen in-memory SVG
Artifacts and runs observation, R0, R1, S0, S4, binding, and authoring through
ProposalAcceptor. Recovery never reads Ground Truth Tracks. The test compares
sampled translation and rerendered target landmarks at ticks 0, 12, 24, and 36.
It separately asserts that legacy bounds displacement produces false Group
translation for the first case and that those observation semantics are unchanged.

Run from the repository root:

```powershell
python -m unittest discover -s tests -p test_geometry_correct_translation.py -v
```

The no-target-motion test leaves B moving so frame bytes differ. This does not
claim to fix repeated-frame observation identity. See spec 52 for the new
CREATE-only authoring contract and its initial-registration restriction.
