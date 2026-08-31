# Anchored Regeneration interaction prototype

This is a deliberately isolated product-experience prototype for Golden O. It
does not define SVM Document meaning and does not call an AI model.

Run it from the repository root:

```powershell
py -3.12 -m http.server 4173 --directory prototype/anchored-regeneration
```

Then open `http://127.0.0.1:4173/`.

The intended interaction is:

1. choose Orange to represent a strict deterministic R0 -> R1 edit;
2. choose exact downstream regeneration scopes;
3. generate deterministic A/B/C pending Proposals;
4. inspect a candidate and its actual impact summary;
5. accept it as a child Revision whose parent remains R1.

The prototype keeps Canvas state, selection, checkboxes, candidate previews,
and the illustrative branch graph entirely in browser memory. None of those are
portable SVM Document fields. The real authority semantics remain in
`svm/anchored_regeneration.py` and `ProposalAcceptor.accept_anchored()`.
