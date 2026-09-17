# POP Geometry Observation Producer v0.1

Status: normative Golden S4.1.

## Boundary

The producer converts two exact, independently frozen POP output Artifacts into
one `svm-primitive-observations-0.2` Reference Artifact. Both POP outputs and
their exact operation-prefix Artifacts are validated through the existing POP
token contract before geometry is read.

```text
POP prefix + source POP output + target POP output
-> deterministic geometry observation Proposal
-> explicit Accept
-> primitive observations v0.2 reference
```

It does not render pixels, infer contours, perform matching, or modify an
Entity, Group, Track, Presentation, or animation. R0 continues to score only
bounds, fill, and primitive type; v0.2 geometry is consumed only by S4.

## Supported geometry and landmark order

Policy `svm-pop-geometry-observation-policy@0.1` supports only the two shapes
proved by `svm-pop-output-0.2` tokens:

- A rotated rectangle records its four local corners in clockwise order:
  top-left, top-right, bottom-right, bottom-left. The frozen authored POP
  transform maps those real local corners into canvas coordinates.
- An ellipse records the four ordered local-axis boundary points: positive X,
  positive Y, negative X, negative Y. The frozen authored POP transform maps
  those real ellipse points into canvas coordinates.

Bounds are then computed from that real primitive geometry. Rectangle bounds
come from transformed corners. Rotated ellipse bounds use the exact analytic
ellipse extents. Bounds are never converted back into landmarks.

Landmark order follows the primitive's frozen local geometry, so index `i` has
the same meaning across frames. Numeric output uses the repository's canonical
12-significant-digit rounding and canonical JSON encoding.

## Visual rotation symmetry

Symmetry is determined by visible dimensions, never by authored rotation:

- equal-width/equal-height ellipse: `continuous`;
- other ellipse: `half-turn`;
- equal-width/equal-height rectangle: `quarter-turn`;
- other rectangle: `half-turn`.

Consequently this POP slice can provide supported uniform-scale evidence, but
does not claim a unique observed rotation for either supported shape. A POP
shape outside this closed set, invalid token geometry, or inconsistent frozen
provenance rejects production; no AABB corner substitute is emitted.

## Identity and provenance

Observation IDs bind the source POP Artifact ID, primitive draw-order index,
and geometry policy. Artifact provenance records producer identity/version,
the ordered source POP output IDs, their exact prefix IDs, POP output format
identity, POP adapter identity, and geometry policy identity.

Equal source Artifacts, ticks, and policy produce identical canonical bytes,
Artifact ID, bounds, landmark order, and symmetry. Acceptance attaches the
observation and exact source references only. Later R0, R1, and S4 remain
separate explicit Proposal boundaries.
