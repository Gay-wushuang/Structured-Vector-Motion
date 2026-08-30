# SVM Core Invariants v0.1

The words SHALL, SHALL NOT, SHOULD, and MAY are normative.

## Identity

**INV-ID-001** Entity identity SHALL NOT depend on current geometry, style,
render order, or evaluation result.

**INV-ID-002** Operation IDs and output-slot IDs SHALL be stable across
reevaluation.

**INV-ID-003** Immutable values SHALL be identified by canonical content hash.

**INV-ID-004** A structural operation that creates a distinct semantic object
SHALL allocate a new Entity ID and SHALL NOT silently transfer an existing ID.

**INV-ID-005** Historical deletion SHALL preserve enough tombstone information
to resolve prior references.

## Evaluation

**INV-EVAL-001** Operation evaluation SHALL NOT mutate input values.

**INV-EVAL-002** Equivalent operation type, inputs, parameters, quality,
semantics version, and engine implementation SHALL produce equivalent outputs.

**INV-EVAL-003** Unrecorded randomness, wall-clock time, UI state, and mutable
external resources SHALL NOT affect evaluation.

**INV-EVAL-004** Invalidating an operation SHALL invalidate only its transitive
dependants; unrelated graph components SHALL remain clean.

**INV-EVAL-005** A stale last-successful value MAY be displayed, but SHALL NOT
be represented as current or used for `FINAL` export.

**INV-EVAL-006** A failed or unavailable dependency SHALL block dependent
evaluation without invalidating unrelated graph components.

**INV-EVAL-007** Runtime cache and evaluation state SHALL be reconstructible and
SHALL NOT define document meaning.

## Document and resources

**INV-DOC-001** A Document SHALL declare both `schema_version` and
`semantics_version`.

**INV-DOC-002** Schema version describes representation; semantics version
describes operation meaning.

**INV-REF-001** An accepted external resource SHALL include a cryptographic
content hash and import metadata sufficient to detect source drift.

**INV-REF-002** An external path or URI SHALL be a locator, not the identity of
the accepted resource.

**INV-REF-003** A nondeterministic model result SHALL be snapshotted as a fixed
artifact before it becomes a formal construction input.

## Relations and time

**INV-REL-001** Semantic hierarchy, render order, and refinement stage SHALL be
represented as independent relations.

**INV-TIME-001** Construction dependency order SHALL NOT imply presentation
time.

**INV-TIME-002** Construction scheduling and content animation SHALL remain
distinct even when an editor displays them together.

**INV-TIME-003** Content animation SHALL use an explicit integer Timebase;
equivalent Track, Keyframe, and sampling tick semantics SHALL produce equivalent
sampled values and Frames.

**INV-TIME-004** Animation sampling SHALL NOT change Entity, Operation, Track,
or Keyframe identity.

**INV-TIME-005** Editing a Keyframe SHALL invalidate only cached sampling times
whose interpolated value may change.

**INV-TIME-006** Time SHALL NOT enter an Operation evaluation key unless that
Operation's accepted semantics explicitly consume time. Static subtrees SHALL
remain eligible for cross-time immutable Value cache reuse.

## Transactions, proposals, and control

**INV-TXN-001** One user-visible intent that changes multiple records SHALL
commit atomically.

**INV-PROP-001** A proposal SHALL target a base revision and SHALL NOT mutate
the accepted Document before explicit acceptance.

**INV-PROP-002** Proposal acceptance SHALL validate constraints, permissions,
and base-revision conflicts.

**INV-CTRL-001** Constraints, evaluation policies, and edit permissions SHALL
remain semantically distinct.

**INV-CTRL-002** Automatic actors SHALL respect property- and actor-scoped edit
permissions.
