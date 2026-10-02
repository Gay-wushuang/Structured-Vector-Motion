# P2S-C — Explicit Two-Part SVG Group Construction

Status: **SPECIFIED / NOT IMPLEMENTED**. Not FINAL or FROZEN.
Evidence baseline: `3ced2f14f144bdd642601c6251738bc7c3109475`.

Profile identity: `svm-svg-two-part-group-construction@0.1`.
Authority: `svm-construction-derived-group@0.1` in [spec/72](72-construction-derived-group-authority.md).
Runtime admission requires authority and this profile implemented together,
followed by Golden/adversarial acceptance. P2D-B remains BLOCKED.

## 1. Evidence decision and meaning

The first positive source is a bounded **authored SVG assembly**, not video.
Its source subject is the sole explicit `g` container in accepted immutable SVG
bytes. Its two direct drawable children are the complete authored parts. This
proves source structural ownership, not recognition of a physical object, artist
intent beyond the recorded structure, or cross-time identity. A source author
can explicitly assemble artwork; the Proposal caller cannot substitute a member
list or group otherwise flat source shapes. A new source is a new accepted input,
not an override of a previous source's structure.

Executable evidence and rejected alternatives:

| Path | Established authority and limit |
| --- | --- |
| P2A / OpenCV component analysis | Verified occurrence/component eligibility and geometry; no multipart ownership |
| P2B | Reproduces complete supported primitive observations and lineage; same frame/analysis does not assemble subjects |
| R0 / P2C / R1 | Observation correspondence and persistent observation identity; neither joins different identities nor makes temporal alternatives simultaneous parts |
| Bitmap trace | Renderable components; hole/island topology belongs to a component, not independent assembly membership |
| Bitmap reconciliation | Existing geometric matching of components, not exact subject ownership; its scores are not admitted here |
| Structural relations | `derived-from` and AABB `bounds-contains` explicitly do not assert semantic hierarchy or Groups |
| LayerPeeler | Exact bundle/layer association and SVG reconstruction; source-layer co-origin alone does not assert one artwork subject |
| LayerD | Accepted raster-layer evidence and classification, not rendered vector parts or assembly ownership |
| SVG import | Retains accepted source bytes; parser/normalizer handles explicit nested `g` and leaves, but flattens output and does not itself create Groups |
| POP Q | Existing inference/promotion authority for its own domain; not transferable construction provenance |
| Manual SVM hierarchy | Structural validity alone is not this replayable source-construction authority |

Spec/10's accepted SVG syntax and `SVGNormalizer` provide the bounded geometry
construction semantics. This profile newly authorizes reproduction of a strict
subset of the source's explicit group structure. It does not claim that the
legacy flat importer already proved a persistent Group or a video association.
Unlike a research layer or SVG root canvas, an explicit `g` is the recorded
assembly being reproduced; no semantic grouping is inferred from co-occurrence.

## 2. Complete source selection and acceptance

From the authenticated full base Document in spec/72, enumerate all references
with SVG media type `image/svg+xml` or `application/svg+xml`. There must be
exactly one, and it must resolve under its exact accepted descriptor as a
ReferenceArtifact with media type **`image/svg+xml`**. Zero, multiple, Derived,
alternate-media or descriptor-mismatched candidates reject. Do not choose the
first eligible file, ignore a malformed second SVG, or accept a caller selector.
Other non-SVG references are unrelated base state, not construction dependencies.

Resolve and verify the full SHA-256 content identity of this reference. The
complete source dependency closure is exactly that one descriptor and its bytes:
the subset below has no external resources. Resolver-only sources reject. The
source must already be accepted before establishment; accepting its reference
does not itself endorse any Group. Prior SVG import is one existing way to
establish that reference. Its old Entities are not adopted, matched or modified.

All request options are empty. No caller namespace, source selector, members,
baseline, IDs, style, order, origin or profile parameters are accepted. The
manifest's profile parameters are exactly `{}`. Ineligible inputs fail closed
without a smaller fragment, fallback profile or repair.

## 3. Exact source subset

Source is at most 64 KiB of valid UTF-8 without BOM. It is well-formed XML with
the SVG namespace `http://www.w3.org/2000/svg`, unprefixed element names and the
sole default namespace declaration on the root. No XML declaration, DTD, entity
declaration/reference, processing instruction, comment or CDATA is accepted.
Only whitespace text between elements is allowed; no external resolution occurs.

The complete element tree is exactly:

```text
svg (no attributes beyond the default namespace)
  g (no attributes)
    rect (exact attributes: x, y, width, height; no children)
    ellipse (exact attributes: cx, cy, rx, ry; no children)
```

There are no other elements, attributes, nested groups, IDs, metadata, viewBox,
transforms, masks, clips, styles, links or animation. Attribute order and
inter-element whitespace do not alter parsing; raw bytes still define Artifact
identity. Child order is normative: rectangle then ellipse. Reversal rejects,
not sorts. These are two authored leaves, not a decomposition of one contour.

Each numeric lexeme is a canonical decimal integer (`0` or an optional minus
followed by a nonzero digit and decimal digits), with absolute value <= 1,000,000.
No plus, leading zero, negative zero, exponent, fraction, unit, NaN or Infinity.
Width, height, rx and ry must be strictly positive. The deliberately narrower
integer subset avoids unrecorded numeric approximations; it is not a change to
the SVG importer. Both children render with opaque nonempty fill under §5.

No distance, overlap, containment, color, digest-prefix or render-order matching
establishes ownership. Child order only reproduces source presentation. This
contract does not certify visibility against arbitrary occlusion; two authored
parts may overlap. It cannot certify that an author never authored redundant art.
It does prohibit the constructor from inventing a second member, splitting a
leaf or manufacturing filler to reach Group cardinality.

## 4. Source subject and allocation

The exact subject object is:

```json
{"source_artifact_id":"artifact:<full digest>","subject_path":[0]}
```

`[0]` means the sole element child of the SVG root, verified to be `g`, not a
caller path. Logical part keys are exactly `rect:0` and `ellipse:1`. Identity is
snapshot-local source identity: byte-different SVGs are different source subjects,
even if they render identically. No cross-file continuity is claimed.

Let `H` be full lowercase SHA-256 of repository `canonical_bytes`. For each part:

```text
allocation = {
  authority_identity: "svm-construction-derived-group@0.1",
  profile_identity: "svm-svg-two-part-group-construction@0.1",
  subject: exact_subject_object,
  part_key: logical_part_key
}
Entity ID = "entity:" + H({**allocation, record_kind: "entity"})
Operation ID = "op:" + H({**allocation, record_kind: "operation", role: "geometry"})
```

These formulas do not use legacy SVG caller namespaces or truncated hashes.
Different subjects are separated even when part keys coincide. The two Entity
records contain exactly `id` and `name`; names are the fixed SVG normalizer
defaults `rect-1` and `ellipse-2`, never allocation inputs. No caller/source
display names, parent, semantic tags or Core `provenance` field are added.
Member lineage is profile-defined provenance
in the verified manifest's subject and complete fragment, not fabricated
`PromotedComponent` data. Current Entity provenance validation only admits that
frozen component type; no Entity schema extension is needed for this profile.

## 5. Reconstructed fragment

Reproduce existing SVG normalization geometry/style semantics for these leaves,
then apply the exact ID allocation above. No legacy namespace/collision suffix
behavior is inherited. Every numeric Operation parameter is the exact finite
float conversion used by SVG import for the bounded integer input.

- Rectangle: `CreateRectangle`, empty inputs, parameters x/y/width/height.
- Ellipse: `CreateEllipse`, empty inputs, parameters cx/cy/rx/ry.
- Each has one `geometry` binding to its own `Operation ID + ".geometry"`.
- Each style is exactly fill `#000000`, stroke `none`, stroke_width `1.0`,
  opacity `1.0`, with the corresponding Entity ID.
- Entity, Operation, binding and style arrays follow rectangle then ellipse.
  Append those two Entity IDs to the existing Render Stack in that order.

Coordinates are untransformed SVG user coordinates, used directly as Document
coordinates, before Group or Camera. There is no viewBox remapping. Existing
rectangle/ellipse Operation validation and geometry-bounds semantics apply.
No CreatePath/PathToPolygon conversion, backend, tracing or pixel inference is
needed. Existing unrelated construction and presentation remain unchanged.

Group members are the lexicographically sorted two reproduced Entity IDs;
presentation order is not membership order. Group ID/provenance follow spec/72.
Its Transform is neutral with the fixed union-geometry-bounds center from spec/72;
there is no origin option. Finite bounds and nondegenerate extents are required.

## 6. Manifest, receipt and acceptance

Spec/72's exact manifest fields apply. Its subject is §4, parameters are empty,
source descriptors are the singleton §2 closure, fragment is §5, and member
bounds are in fragment order. Reconstruct all fields independently from source
bytes and authenticated base. Claimed fragment geometry, style or IDs are never
replay inputs. A producer name or media type cannot substitute for the tree check.

The construction-only receipt has exactly these fields:

```text
schema_version = "svm-svg-two-part-group-establishment-0.1"
authority_identity, profile_identity
source_base_revision_id, source_base_document_hash
source_references = [exact accepted SVG descriptor]
subject = exact subject object
fragment = complete reconstructed fragment
construction_reference = exact derived manifest descriptor
group = complete Group definition including initial Transform
representation_claim = null
```

Receipt bytes are `canonical_bytes` with media type
`application/vnd.svm.svg-two-part-group-establishment+json;version=0.1`, kind
DerivedArtifact, descriptor provenance exactly `{authority_identity, profile_identity}`.
No own ID, result Revision/hash, baseline tick or temporal claim is included.
The snapshot/Revision witness authenticates the source base as spec/72 requires;
neither the receipt nor its declared base authenticates itself.

Accepted source -> subject/part keys -> allocated IDs -> fragment/bounds;
base + source + fragment -> manifest -> construction ID -> Group provenance;
IDs + profile -> Group ID; bounds -> Transform; complete Group + manifest
descriptor + fragment + pre-base -> receipt -> receipt ID -> post Document
references -> post hash/Revision. No identity depends on receipt or post-state.

One future registered composite applies spec/72's complete atomic state and
intent set, including distinct `establish_group`. Preview changes no accepted
state. Any rejection leaves HEAD, Revision count, Document and accepted references
unchanged. Every allocated ID collision rejects, including byte-identical output.
This is creation, not adoption or retry-as-update. Unrelated base edits stale an
existing Proposal; reproposal preserves allocation for the same source subject.

## 7. Temporal and product boundary

This profile has no temporal baseline and no representation correspondence.
`representation_claim` is always null; a supplied T-to-G claim rejects.
Its Group is structurally transformable, but its existence does not make it a
P2D candidate. Restricted P2D-A continues to abstain; P2D-B stays blocked.

Video construction requires a separate **VIDEO MULTIPART STRUCTURE EVIDENCE**
contract: accepted, versioned evidence of one exact subject with complete genuine
simultaneous part ownership, its source dependency closure, attributable producer
and independently verifiable admission, plus the distinct link to the complete
TemporalIdentity observation universe. P2C alone cannot provide that proof.
That prerequisite must state negative/ambiguous ownership and temporal coverage
rules before a video profile chooses an initial geometry baseline. No schema or
inference method is invented here. Heuristic producers may eventually propose
such evidence but do not bypass acceptance authority.

## 8. Future Golden and adversarial obligations

The first Golden input is a real independent authored source, never an SVG
rendered from expected SVM output:

```xml
<svg xmlns="http://www.w3.org/2000/svg">
  <g>
    <rect x="0" y="0" width="20" height="10"/>
    <ellipse cx="30" cy="5" rx="5" ry="3"/>
  </g>
</svg>
```

Accept its reference through an existing SVG import Proposal first. Preserve
that accepted base and its old artwork exactly; establish new profile-allocated
artwork without adopting old importer IDs. The independent source tree supplies
the ownership proof. Reproduce two Entities, two Operations, two bindings/styles,
complete source closure, Group and receipt. Bounds are `[0,0,20,10]` and
`[25,2,35,8]`; initial origin is `[17.5,5]`. Prove preview isolation, one atomic
Revision, repeatable manifest/receipt/Group identities on equivalent bases and
ordinary rendering. No motion binding or temporal evidence is expected.

Required negative cases (design obligations, no fixture implemented here):

| Input/attack | Required outcome |
| --- | --- |
| Unknown profile | Reject before dispatch |
| Missing accepted source / resolver-only source | Reject |
| Multiple SVG references / omitted candidate reference in snapshot | Reject by complete authenticated-base enumeration |
| Incomplete closure / external resource / altered descriptor | Reject |
| Changed subject or source bytes with old output | Replay mismatch rejects; genuinely new accepted source requires new Proposal/IDs |
| Omitted/extra part, flat two-shape root, nested or reordered children | Subset/complete-fragment check rejects |
| Caller members, IDs, namespace, order, origin, baseline or style | Options/output mismatch rejects |
| Stale or forged base / earlier Change mutates replay base | Base witness and incoming-base guard reject |
| Geometry/style mismatch, unsupported or non-finite number | Reject without normalization repair |
| Group/Entity/Operation collision or transformed ownership conflict | Entire transaction rejects; no pruning/auto-suffix |
| One leaf, dummy invisible leaf, artificial constructor split | Ineligible; never manufacture multipartness |
| Fake media/producer identity or receipt alone | Tree reconstruction and accepted closure still required |
| Missing or denied construction policy intent | Reject atomically |
| Temporal representation claim, including a failed claimed correspondence | Reject; this profile cannot supply correspondence |

All normal successes must preserve old artwork and unrelated state. Single-Entity
motion targeting, paths, general SVG assemblies, research-layer subject inference,
video ownership, geometry stabilization, deformation and style estimation remain
outside this profile. Group cardinality and frozen Phase 1/P2A/P2B/R0/P2C/R1/POP
semantics are unchanged.
