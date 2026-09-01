# POP Structure Reconciliation v0.1

## Status

Golden Test Q is normative. It derives reviewable visibility and occlusion
evidence from an unchanged, accepted Golden P primitive scene. It does not infer
semantic hierarchy, grouping, object labels, or animation.

## Boundary

```text
accepted POP primitive Revision
        |
        +-> normal SVG
        +-> X-Ray SVG
        +-> full per-Entity masks
        +-> visible per-Entity masks
        `-> topmost occlusion evidence
                    |
                    v
              Proposal Preview
                    |
                    v
          AppendReferencesChange
                    |
                    v
        accepted evidence-only Revision
```

The Adapter identity is `adapter:pop-structure@0.1`. It accepts exactly the
unchanged scene reconstructed by `POPOutputAdapter v0.2` from the supplied
operation-prefix and output Artifacts. Edited, additional, missing, reordered,
or otherwise drifted Entities, Operations, bindings, Styles, or Render Stack
entries fail closed in v0.1. This deliberately narrow contract establishes the
analysis semantics before reconciliation is generalized to edited scenes.

The Adapter evaluates only accepted Core Operations. It does not reopen the POP
checkpoint, rerun sampling, or treat the POP Artifact as a Runtime Value.

## Pixel coverage

Golden Q fixes a 256×256 canvas and supports the accepted POP rectangle and
ellipse subset, with its accepted affine Transform. Coverage is evaluated at
pixel centers:

```text
sample(x, y) = (x + 0.5, y + 0.5)
```

After applying the inverse accepted Transform, both local sample coordinates
are canonicalized with Python's `.12g` representation before the primitive
predicate. This canonicalization is part of
`svm-pop-pixel-center-masks@0.1`; it prevents insignificant inverse-transform
floating drift from silently deciding a boundary pixel.

For each non-background Render Stack Entity:

- `full_mask` contains every covered pixel center without considering other
  Entities;
- `visible_mask` is `full_mask` minus the union of every later primitive's full
  mask;
- `occluded_pixels = full_pixels - visible_pixels`;
- `visibility_ratio = visible_pixels / full_pixels`.

These are geometric visibility masks, not alpha-contribution masks. POP's 0.5
opacity remains normal rendering semantics, but a later covered pixel is
geometrically occluded for structural analysis even though the earlier color
still contributes to the composited raster.

Masks use `svm-pop-pixel-center-masks@0.1` and canonical row runs
`[y, x_start, x_end_exclusive]`. Each record contains both full and visible
runs, counts, Entity ID, and Render Stack index.

## Occlusion attribution

Occlusion relation identity is `svm-pop-topmost-occlusion@0.1`. Every hidden
pixel of a lower primitive is attributed exactly once to the later primitive
whose visible mask contains that pixel. A recorded evidence edge therefore
means:

```text
occluder is later in Render Stack
AND
occluder is topmost at one or more full-mask pixels of occluded Entity
```

The analysis records overlap pixels and their fraction of the occluded
Entity's full mask. For every Entity the following conservation law MUST hold:

```text
full_pixels
= visible_pixels
+ sum(overlap_pixels for incoming topmost occlusion evidence)
```

An overlap edge is pixel evidence only. It does not imply parent/child,
same-object membership, containment, depth in physical space, or a request to
change Render Stack order.

## Renders and Artifacts

The four Derived Artifacts are:

1. normal SVG using `svm-svg-renderer/pop-256@0.1`;
2. X-Ray SVG using `svm-pop-xray-svg@0.1`;
3. canonical mask bundle JSON using `svm-pop-pixel-center-masks@0.1`;
4. canonical occlusion analysis JSON using
   `svm-pop-occlusion-analysis@0.1`.

X-Ray is an inspection view: the background is opaque near-black and all
primitives retain their color with 0.2 opacity and a 0.5-unit white stroke. It
is Editor evidence, not accepted presentation semantics.

All Artifacts record the exact source Revision ID and canonical Document hash.
The Proposal attaches their immutable references atomically through the
existing `attach_analysis` authority. Preview `occludes` relations remain
evidence previews and are not written into the v0.2 `structural_relations`
array, whose exact materialization contract is reserved for promoted component
relations.

## Golden Q

The real Golden P scene fixes the Golden Q expectations:

- 143 analyzed primitives;
- four deterministic Derived Artifacts;
- normal SVG content identical to the Golden P accepted SVM render;
- 783 topmost occlusion evidence edges;
- two fully geometrically occluded primitives;
- exact per-Entity visibility conservation;
- preview and acceptance do not change Entities, Operations, bindings, Styles,
  Render Stack order, or `structural_relations`;
- acceptance appends only the four evidence references in one Revision;
- repeated equivalent analysis produces identical Artifact and Proposal IDs;
- source drift, unsupported options, wrong Artifacts, and unsupported geometry
  fail closed.
