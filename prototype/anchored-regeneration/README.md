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

The UI distinguishes three states explicitly:

- `baseRevision`: the immutable R1 anchor used by every candidate;
- `committedRevision`: the accepted Revision currently recorded as current;
- `previewCandidate`: an optional, unsaved Proposal shown on Canvas.

Selecting a candidate marks Canvas as `PREVIEW · NOT SAVED` without changing the
committed Revision. Changing regeneration scope clears stale preview state and
returns Canvas to the R1 Anchor Base before producing replacement candidates.
An empty scope additionally clears the entire pending candidate set, hides the
candidate panel, removes pending A/B/C from the branch graph, and disables
acceptance.

## State transition table

These transitions are the prototype's minimum UI-state contract:

| From | Event | Required result |
| --- | --- | --- |
| R0 | choose Orange | committed R1; Canvas shows Anchor Base R1 |
| R1 | generate candidates | A/B/C pending; no preview selected |
| R1 | select A | preview A; committed remains R1 |
| preview A | accept A | committed R2; preview cleared |
| R2 | select B | preview B; committed remains R2 |
| preview B | change non-empty scope | preview cleared; replacement candidates; Canvas shows Anchor Base R1 |
| preview B | make scope empty | preview and candidates cleared; Canvas shows Anchor Base R1; Accept disabled |

The prototype keeps Canvas state, selection, checkboxes, candidate previews,
and the illustrative branch graph entirely in browser memory. None of those are
portable SVM Document fields. The real authority semantics remain in
`svm/anchored_regeneration.py` and `ProposalAcceptor.accept_anchored()`.
