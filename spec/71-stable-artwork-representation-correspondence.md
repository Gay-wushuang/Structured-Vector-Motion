# Stable Artwork Representation Correspondence — prerequisite contract

Status: **DESIGN CONTRACT / NOT IMPLEMENTED / NOT FROZEN**.

Repository evidence baseline: `f78da63852d8b0e5255d121e2f787ab6824a1192`.
This specifies the semantic prerequisite identified by the Temporal Structure
Audit. It does not implement P2D-B, admit a new evidence producer, register a
Change, or change frozen Phase 1, P2A/P2B/R0/P2C/R1 semantics. SHALL statements
constrain a future implementation; they do not describe existing capability.

The near-term objective is stable vector-animation stylization. Later video
restoration reuses the separation between persistent artwork and time-specific
evidence. Neither objective authorizes implicit target inference.

## 1. Executable findings and governing boundaries

| Repository authority | Executable fact | Consequence |
| --- | --- | --- |
| `revisions.py`: `promoted_component_entity_id`, `PromotedComponent.to_entity` | Identity includes analysis artifact, component candidate and digest; promotion creates a non-rendered Entity | Two independent analyses normally yield distinct evidence-backed Entities, even if the component's local digest is unchanged |
| `primitive_observation_assembly.py`: `_frame` | Observation identity records the producing P2A evidence, occurrence, frame index, tick and component digest | Observation identity is an occurrence identity, not artwork identity |
| `temporal_identity_selection.py`: `propose`, `verify_change`; `revisions.py`: `PromoteTemporalIdentityChange` | P2C selects ALL-SUPPORTED R0 pairs and delegates owner creation/reuse/conflicts to R1 | Accepted observation correspondence supplies no arbitrary artwork target ownership |
| `motion_target_binding_selection.py`: `_evaluate` | Different resolved Entities cause `CONTRADICTORY_PROVENANCE`, including within one Group | P2D-A implements a narrow common-source rule, not general cross-frame representation correspondence |
| `document.py`: `_validate_groups`; `revisions.py`: `PromoteGroupsChange` | Groups need at least two existing members and exact promotion provenance | A frame component cannot acquire a legal Group by inventing a second member or a provenance record |
| `scene.py`: `build_evaluated_scene`; `motion.py`: `sample_document` | Group transforms act on persistent member geometry; sampling does not select observation versions | Group membership is not a temporal-alternative mechanism |
| `proposals.py`: `_verify_artifact_bound_changes` | Artifact verifiers receive `(change, resolved_artifacts)`, not the accepted Document | Full Document completeness needs an authenticated base commitment, not a caller projection |

The real-producer case in `tests/test_motion_target_binding_selection.py`,
`test_real_p2a_p2b_ids_resolve_exact_evaluations_not_ordinals`, correctly exposes
the limitation. Its test Groups do not demonstrate accepted Group creation.
Two different frame analyses are not contradictory evidence merely because
their component-backed Entities differ.

The existing Core invariants remain governing: stable Entity identity is
independent of current geometry; structural creation allocates new identity;
sampling preserves identity; external evidence crosses explicit Proposal and
atomic acceptance boundaries. No implicit runtime target selection is added.

## 2. Semantic decision

Reuse **Entity** for persistent artwork identity and **Group** for a persistent
artwork assembly with a shared transform. Do not add a TemporalObject or
SceneObject hierarchy. An artwork representation is a role of existing
Document definitions, not a new Core object type.

Keep these distinctions normative:

```text
source observation identity != persistent SVM artwork identity
observation history         != Group structural membership
exact observation provenance != equality of all frame-local Entities
representation association  != Motion Target Binding != Animation Track
```

The missing fact is a **representation association**:

> Under a specified, accepted construction authority, this persistent artwork
> representation was established for this accepted observation identity.

This is neither a claim that all observations share one component source nor a
claim that the representation reproduces every observed contour. It establishes
which artwork is to represent an accepted observation subject, not that R0 has
proved the real-world object's identity beyond its recorded policy.

For the initial Group-target contract, one TemporalIdentity has at most one
active representation Group and one representation Group has at most one such
owner in a Document branch. This is not global identity across projects,
branches or independently imported sources. Conflicts SHALL NOT be merged.

## 3. What exact evidence must prove

An association must establish all three independent facts:

1. **Observation ownership:** every claimed `(tick, observation_id)` belongs to
   the identified TemporalIdentity in the exact base Document, through the
   accepted frozen correspondence/promotion evidence. All bindings and promotion
   records in that identity are accounted for, including unsupported paths.
2. **Artwork establishment:** an admitted construction derivation establishes
   the particular persistent representation for that identity. The derivation
   accounts for its Entity identities, construction/output bindings, Group
   membership and valid Group provenance. A supplied target ID is not proof.
3. **Current applicability:** the representation still exists, is structurally
   valid and uniquely eligible, and no accepted competing association or existing
   binding invalidates the proposed use in the authenticated base.

Exactness means reproducible agreement with these records and their versioned
authority, not equal analysis IDs, component digests, contours or bounds across
time. Pixel equality and hash equality cannot prove physical object identity.

For example, accepted observations A and B may originate in analyses X and Y,
with X != Y and different component digests. If R1 owns both under identity T
and a verified construction establishes representation G for T, both are
observations of T represented by G. Their component Entities need not be
members of G, and SHALL NOT become members merely through this association.

If only R1 ownership is known and no establishment proof exists, the outcome is
abstention. It is not permission to choose an existing Group.

## 4. Initial proof direction: establishment by construction

The smallest intended proof mode is **verified construction**, rather than
recognizing which arbitrary existing artwork resembles a frame.

A separately specified representation-construction profile must deterministically
produce a legal persistent representation for an accepted TemporalIdentity from
recorded accepted inputs. The target is an output of that derivation, never a
caller-selected existing Group. A later correspondence consumer may reuse that
target only by reproducing the establishment proof.

The profile must specify the complete source universe, eligibility/abstention,
baseline selection, coordinate frame, representation construction and identity
allocation. Caller-picked source samples or an arbitrary baseline cannot become
a concealed way of selecting a target. Once established, the representation is
not reallocated whenever a new observation changes the preferred baseline.

A conceptual **establishment receipt** records this proof. A receipt is an
evidence record, not a new Entity, scene node, geometry container or trusted
producer assertion. It must bind:

- the exact construction profile/version and its recorded parameters;
- the origin TemporalIdentity and complete origin binding/provenance snapshot;
- the exact accepted source descriptors and their deterministic dependency order;
- the source base commitment and the construction result it authorizes;
- the allocated Entity/Group identities and the exact initial representation;
- the correspondence claim and its explicit coverage/limitations.

These are semantic obligations, not a new JSON schema in this design pass.
No artifact media type, ID formula or dispatch registration is reserved here.
Existing ID constructors must be reused where applicable; a profile needing
different creation semantics requires a separate explicit contract.

Creation and its receipt must be accepted atomically through a registered
authority that independently reproduces the legal construction. A receipt
cannot certify its own creator. Merely appending it as an accepted reference,
reproducing its content hash, or recording an adapter name SHALL NOT admit it.
On later consumption the consumer must independently verify the admitted proof;
it cannot infer admission from Artifact presence or a `verified` flag.

For the initial mode, use **authenticated construction history** as the proof
direction. The origin pre-Document, admitted construction inputs and recipe must
reproduce the entire origin post-Document, including the receipt reference and
the legal newly allocated representation. The target must be absent before that
construction. An append-only receipt about an already existing arbitrary Group
cannot reproduce this transition. Receipt content binds the origin pre-base and
result definitions, but must not contain its own hash or the resulting Revision
ID; that would introduce a self-reference. The resulting Revision is verified
separately using the repository's existing Revision commitment.

**No such construction profile is admitted by this document.** Existing P2A and
P2B produce observation evidence; Component Promotion produces non-rendered
regions; none of them supplies this establishment authority. This is a concrete
prerequisite, not an implementation presumed to exist behind the word "receipt".

Association of an arbitrary pre-existing Group is outside the initial mode.
Frozen S1 remains available for explicit artistic binding, but that choice SHALL
NOT be relabeled as independently proven automatic correspondence.

## 5. Group and rendering obligations

Group members SHALL be the persistent components of the artwork assembly.
Adding later observations SHALL NOT append their frame-local Entities to that
membership. Group transforms continue to compose outside member-local geometry.

A representation claimed to support vector rendering must have valid geometry
operations, output bindings and presentation definitions; a Group of geometry-free
PromotedComponents is not sufficient. Association acceptance alone creates no
geometry, Track, visibility schedule or render output.

The existing Group minimum of two real members and unique transformed membership
remain unchanged. Legacy promotion provenance remains unchanged; spec/72 specifies
an additive construction-origin authority and provenance branch, not yet
implemented. A construction profile must demonstrate legal creation through an
admitted origin authority. It SHALL NOT:

- add an invisible/dummy member just to satisfy cardinality;
- place successive frame alternatives into one Group;
- fabricate Q-v1 candidate evidence or repurpose unrelated Group provenance;
- introduce a direct Entity-transform target as an unreviewed workaround.

A single-component artwork with no legal Group construction is an explicit
unsupported case for this initial Group-target scope. Any expansion requires a
separate structural decision; it is not hidden inside correspondence verification.

## 6. Evidence lifetime and ownership

Three lifetimes SHALL remain distinct:

- **Persistent identity:** accepted artwork and TemporalIdentity IDs survive
  ordinary permitted edits and R1 extensions. They are not hashes of every new
  frame's geometry.
- **Establishment proof:** records the original legal creation and association.
  Its historical initial geometry is not an eternal equality constraint on
  editable artwork.
- **Selection evidence:** describes eligibility and complete observation coverage
  at one authenticated base. A new base requires fresh applicability verification.

When frozen R1 extends the same identity, existing owner IDs stay unchanged.
Fresh correspondence evidence must account for the entire current identity and
its accepted extension provenance. A receipt for a subset cannot silently certify
new observations. No resampling of a "better" frame may silently replace the
artwork or its target. Failure to verify new coverage produces abstention, not
identity deletion or reassignment.

Normal geometry/style/Track edits do not create a new object identity. New
selection is nevertheless base-bound and rechecks eligibility. Structural
replacement, missing targets, conflicting ownership or unprovable provenance
must block fresh selection; they SHALL NOT trigger automatic retargeting.

This contract does not retroactively revoke frozen S1 bindings: their existing
ID-based persistence remains authoritative. Repairing, rebinding, splitting or
merging an established representation is outside this scope. Evidence records
must not be destructively rewritten to conceal such a transition.

## 7. Acceptance and completeness boundary

Future selection must enumerate every Document TemporalIdentity in canonical
ID order and account for every relevant accepted association claim. Neither the
caller nor an evidence producer may provide the universe to be trusted. Missing
identity, source-closure or competing-association entries must not create a
selected-subset attack.

Only exact accepted Document reference descriptors may satisfy dependencies.
Resolvers provide bytes, not acceptance authority. Artifact hashes authenticate
bytes; producer attribution authenticates neither real-world truth nor target
ownership by itself. A signature, if a future profile uses one, cannot replace
the definition of what its issuer is authorized to attest.

The complete base Document must be authenticated independently of proposal data.
The full snapshot plus accepted-base Revision witness design in spec/70 §10.1
is a candidate mechanism compatible with the current two-argument artifact
verifier. A caller-computed projection hash or a self-consistent witness to an
invented revision is insufficient. An incoming-Document apply guard must also
prevent preceding Changes from substituting another selection universe.

That witness proves the base commitment only. It does **not** prove that a
receipt's claimed historical construction was accepted. For §4's initial mode,
later consumption must authenticate a construction-history witness:

1. Anchor the current full snapshot/witness to the actual accepted Proposal base.
2. Follow an unbroken parent chain of existing-format Revision commitments back
   to the origin result and its pre-base; recompute each supplied Revision ID.
   Supplied historical IDs alone are not proof of ancestry. Initially require a
   single-parent chain; interpreting merges is outside this scope.
3. Reproduce the complete origin transition under the admitted construction
   profile and require equality to the authenticated origin result snapshot.
   A transaction ID or message is not a substitute for this reproduction.
4. Authenticate intervening snapshots against their Revision document hashes.
   Require continuity of the receipt, owner identity, target Group identity and
   membership, and the representation's member identities and birth provenance.
   Geometry/style/transform/Track values may change through existing semantics;
   deletion/recreation, member replacement, owner replacement or receipt removal
   is outside this initial continuity proof and blocks fresh selection.
5. Reverify the complete current TemporalIdentity and the exact current accepted
   dependency descriptors. Historical coverage does not certify current coverage.

The identity-bearing projection for continuity must be fixed by the admitted
profile, never supplied by the proposal. Full authenticated snapshots prove that
projection; no new independently trusted projection hash is introduced. Missing
history or required source bytes means the association cannot be newly consumed,
even if the current artwork still renders or an existing S1 binding persists.

This is proof data, not permission for an artifact verifier to read a mutable
RevisionStore. Existing Revision commitments can authenticate detached witnesses;
their actual packaging and bounded validation remain an implementation gate.
No change to Revision identity/hash semantics is authorized. No live history
lookup is needed by the evaluator or renderer.

After complete derivation, select ALL uniquely justified, currently available
pairs. Different frame sources are not a conflict; two justified incompatible
owners/targets are. Incomplete coverage abstains for that identity. If otherwise
selectable identities contend for a Group, do not choose a winner: the complete
selection abstains. Missing/corrupt bytes for an existing required accepted
reference are a verification failure, not grounds to hide an identity.

Already-bound identities remain visible and excluded according to frozen S1 and
spec/70's explicit enumeration boundary. No automatic correction of their binding
is authorized. A later P2D revision must version its reason vocabulary: it must
not silently change P2D-A's existing `CONTRADICTORY_PROVENANCE` interpretation.

Preview SHALL NOT mutate accepted state. Any eventual materialization of bindings
must delegate frozen S1 and commit all effects atomically through the existing
Proposal/ChangeAuthority boundary. This design adds no policy action and grants
no implementation permission to change that infrastructure.

## 8. Admitted evidence versus future producers

Heuristic/CV/AI systems may propose correspondence hypotheses, but SHALL NOT
silently grant ownership. Each future producer profile needs a versioned claim,
source scope, reproducible verifier or explicitly bounded attestation authority,
ambiguity rules and adversarial acceptance evidence. Unrecognized profiles fail
closed. Thresholds, model labels or confidence alone do not satisfy §3.

Nearest Entity/Group, centroid/bounds/IoU/color/shape similarity, component
ordinals, digest prefixes, render-order proximity and caller target choices
are not correspondence authority under this contract. Frozen R0 may continue
using its recorded signals for its own existing hypothesis semantics; this
document does not extend those signals into artwork ownership.

| Source | Observation identity/evidence | Artwork association requirement |
| --- | --- | --- |
| Ordinary or AI-generated video | Different analysis/component artifacts and accepted temporal correspondence | Independently verified representation establishment; neither source class gains privileged truth |
| SVG animation | Source object identifiers plus verifiable production history | Source IDs are namespaced evidence, not SVM Entity IDs; current frozen SVG metadata still lacks rendered-origin proof |
| Manual authoring | Existing persistent SVM artwork, possibly independently of observations | Needs no temporal evidence to render; attaching unrelated observations does not follow from a user-supplied target choice |
| Animated-3D-derived evidence | Namespaced node identity and recorded projection/occurrence evidence under a future profile | Prove the mapping to a separate SVM representation; no 3D scene, rig or editor semantics enter Core |

These are semantic compatibility requirements, not claims that all frontends
are implemented. A stable source ID does not prove source fidelity, visibility,
contour stability or the choice of a particular SVM target.

## 9. Motion, stylization and restoration boundary

Once a stable representation exists, existing accepted motion evidence and S1
bindings can drive ordinary Group translation/rotation/scale Tracks. Sampling
moves the same artwork instead of switching between per-frame silhouettes.
Different observed contours remain evidence; they do not automatically mutate
the artwork or become deformation Tracks.

This enables identity stability and, where motion evidence and interpolation
support it, transform continuity. It does not itself prove flicker removal,
shape fidelity, deformation recovery, occlusion handling or physically correct
motion. Deterministic replay is not a guarantee of temporal visual quality.
Legitimate shape changes require separately accepted shape/appearance semantics;
they must not be erased by arbitrary smoothing or misreported as similarity motion.

Original pixel/appearance evidence SHALL remain independently addressable. Later
restoration can distinguish intentional appearance changes from temporal noise
without redefining artwork identity or treating stylized geometry as ground
truth. Geometry stabilization and appearance repair are separate authorities.

## 10. Required acceptance evidence for a future slice

Before declaring this prerequisite implemented, demonstrate:

1. Two independently analyzed frames with different analysis IDs and changed
   geometry/digests, one accepted TemporalIdentity, a legally constructed stable
   representation and one reproducible target association. No reused analysis
   substitute and no manually injected target mapping count as this positive case.
2. Adding a supported third observation preserves artwork IDs; complete coverage
   is reverified, with no automatic Group membership or geometry replacement.
3. A stationary component whose surrounding frame changes does not require a new
   artwork identity solely because its analysis artifact changed.
4. A forged receipt, generic appended receipt, arbitrary existing target,
   fabricated source identity or source namespace collision fails verification.
5. Omitted identities, endpoints, competing associations or artifact closures
   cannot shrink the verified universe; conflicting claims cannot choose a winner.
6. Wrong accepted descriptors, corrupt artifacts, stale bases, invented base
   witnesses and preceding-Change substitution reject atomically.
7. Permitted artwork edits preserve identity; historical establishment and current
   eligibility are distinguished. Unproven ownership changes cannot pass as edits.
8. A legal target renders through existing output bindings and Group transforms;
   no frame-local alternatives appear simultaneously as a correspondence side effect.
9. Preview, deterministic replay and isolated-target behavior hold; failures leave
   HEAD, Revision count and accepted Document unchanged.

These are future acceptance obligations, not new tests or fixtures in this pass.

## 11. Readiness and relationship to P2D

P2D-A remains a correct implementation of spec/70's limited common-source rule.
It is not expanded by this contract. That rule must not be frozen as the general
ordinary-video representation model. P2D-B remains blocked on this prerequisite.

The chosen direction is a narrow correspondence proof with existing artwork
concepts. The following are **unresolved implementation gates**, not permission
to improvise in an adapter:

- one bounded representation-construction profile, including legal Group creation
  and baseline/coordinate semantics, with no fake members or frozen-provenance reuse;
- a bounded, adversarially verified realization of the construction-history and
  current-coverage proof above, including authentic origin after edits; a
  hash-addressed claim is not enough;
- a versioned P2D consumer contract and exact acceptance schema completing the
  full-base, complete-universe and atomic delegation obligations above.

The next design/implementation slice must discharge the first two gates before
P2D-B. If existing Group construction cannot express its minimal representation,
report that structural blocker for a separate normative decision. Do not weaken
frozen validators or invent an Entity motion target inside the correspondence code.

### P2S-A feasibility finding (historical baseline)

Inspection at `e828c28fd3fb9e745430baa8cea5fd964b8f95fa` establishes
**GROUP_CONSTRUCTION_AUTHORITY_BLOCKER**. No first construction profile is
admitted, and no new profile specification is created by this finding.

Core can express bounded polygon artwork through `CreatePath`, exact canonical
path bounds, geometry output bindings and ordinary presentation. P2A/P2B's
verified controlled-polygon landmarks supply useful source geometry; converting
them to initial artwork still needs a versioned construction policy. Lack of a
general polygon rendering primitive is not the structural blocker.

The only existing Group candidate producer consumes frozen POP Q-v0 evidence.
`POPStructureAdapter._validate_exact_pop_scene` reconstructs the complete scene
from genuine POP prefix/output artifacts and requires exact equality of Entities,
operations, bindings, styles and render stack. It is not a general scene-analysis
service for newly constructed SVG/path artwork. Q-v1 promotion then requires
accepted SUPPORTED inference evidence and the matching source Document hash.
Fabricating Q-v0/Q-v1 payloads or encoding video geometry as a purported captured
POP run merely to obtain Group provenance is not reuse of that authority.

Genuine multipart POP artwork can already be grouped. This does not establish
an observation-to-artwork construction path for video evidence. Separate P2B
primitives also do not prove that their TemporalIdentities constitute one object;
R1 neither creates that assembly nor merges their owners. Selecting a spatially
plausible pair cannot supply the missing establishment proof.

A single silhouette has the additional cardinality limitation: a renderable
Entity alone cannot receive frozen S1 observed motion, whose target is only a
transformed Group with at least two real members. Existing Operation-parameter
animation does not supply an Entity MotionTargetBinding. Splitting geometry or
adding background solely to meet cardinality is not a justified object assembly.

Thus even choosing multipart-only scope does not discharge the Group creation
authority gate for the proposed video-derived profile. A separate normative
decision must establish a legitimate construction-derived Group authority (and
its provenance compatibility), or deliberately reconsider minimum motion-target
semantics. Neither correction is authorized here. The frozen POP path remains
valid for its own source domain; its provenance SHALL NOT be repurposed.

No baseline rule, receipt schema, identity-allocation formula or positive
establishment fixture is admitted while this gate remains unresolved. Sections
3–10 remain requirements, not a claim of an executable or fully specified
profile. P2D-B remains blocked.

### P2S-B design dependency

[Spec/72](72-construction-derived-group-authority.md) specifies
**Construction-Derived Group Authority — SPECIFIED / NOT IMPLEMENTED**.
It resolves the authority design question through one atomic replayed fragment
construction and a disjoint construction-origin provenance branch. Existing
inference-origin Groups and cardinality remain unchanged. The P2S-A blocker is
not an implemented capability merely because this design now exists.

Profile specification does not require authority runtime to exist first.
[Spec/73](73-svg-two-part-group-construction.md) specifies the first bounded,
non-temporal **Explicit Two-Part SVG Group Construction** profile; it is
**SPECIFIED / NOT IMPLEMENTED**. Runtime profile admission/execution is blocked
on authority and profile implementation together, followed by Golden/adversarial
acceptance. No generic profile-less interpreter may precede that implementation.
The SVG profile proves authored assembly ownership, not video subject ownership
or TemporalIdentity correspondence; a video multipart evidence prerequisite
remains. No temporal construction/correspondence profile is admitted here.
For a representation establishment, its correspondence proof and the new
Group/fragment authority must both succeed in one atomic transaction. The
historical/current-coverage obligations above remain for later consumption.
P2D-B stays **BLOCKED**. Single-Entity Motion Target remains an **OPEN SEPARATE
ARCHITECTURAL QUESTION**. No runtime behavior or frozen rule changes in this pass.

Decision: **PREREQUISITE_STRUCTURAL_PHASE_REQUIRED**.
