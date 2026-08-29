# Structured Vector Motion

SVM is an experimental, non-destructive 2D construction computation model.
The current v0.1 baseline contains the core specification and a deliberately
small reference evaluator.

Run the golden test with:

```powershell
python -m unittest discover -s tests -v
```

The evaluator currently implements enough operations to prove isolated DAG
invalidation, lazy reevaluation, immutable content-addressed outputs, and stable
entity identity. It is not yet an editor or production renderer.
