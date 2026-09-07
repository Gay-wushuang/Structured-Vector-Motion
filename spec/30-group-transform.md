# Group Transform v0.1

## Status

Golden Q v3 is normative. It adds static `translate`, `rotation_degrees`, and
positive uniform `scale` to an explicit Group Definition. The recorded `origin`
is the fixed composition pivot for rotation and scale; it is not an additional
deformation channel.

## Evaluation semantics

Group Transform is evaluation-time composition:

```text
effective_geometry(member)
= GroupTransform(group) x EntityLocalGeometry(member)
```

Changing a Group Transform SHALL NOT edit member Entities, construction
Operations, output bindings, local Transform geometry, Styles, Entity IDs, or
Render Stack order. The evaluated scene wraps each member's existing geometry
in one outer affine Transform. Thus an existing member-local transform remains
inside the Group Transform and composes independently.

The affine matrix for translation `(tx, ty)`, rotation `r`, uniform scale `s`,
and origin `(ox, oy)` is canonicalized to `.12g` and equals:

```text
T(tx, ty) x T(ox, oy) x R(r) x S(s) x T(-ox, -oy)
```

Floating-point residues with absolute magnitude below `1e-12` canonicalize to
zero, so exact quarter-turns do not leak trigonometric noise into output.

Group identity and member geometry Value IDs do not depend on the current Group
Transform. A member may belong to multiple evidence groups, but v0.1 fails
closed if more than one transformed Group contains the same Entity because no
group-composition order has yet been specified.

## Authoring boundary

`SetGroupTransformChange` is a closed-world Change with exact
`set_group_transform` intent targeting one Group ID. It commits one complete
transform atomically and rejects missing Groups, no-ops, non-finite values,
non-positive scale, and ambiguous transformed membership.

Group Transform Tracks, Keyframes, frame recovery, optical flow, and shape
deformation remain outside Golden Q v3.

`examples/022-group-transform.svm.json` is the minimal accepted Document for
this contract.
