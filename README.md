# Structured Vector Motion

SVM is an experimental, non-destructive 2D construction computation model.
The current v0.1 baseline contains:

- the core model, invariants, and Document Format specification;
- a Draft 2020-12 JSON Schema;
- a deliberately small deterministic reference evaluator;
- atomic Transactions and content-addressed Revision snapshots;
- `SplitEntity` and Golden Tests A/B;
- an Adapter/Proposal boundary with optimistic base-revision acceptance.

Run the golden test with:

```powershell
python -m unittest discover -s tests -v
```

The implementation proves isolated DAG invalidation, lazy reevaluation,
immutable content-addressed outputs, stable and structural entity identity,
atomic revision creation, undo by parent revision, and Proposal isolation. It is
not yet an editor or production renderer.
