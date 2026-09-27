# P2A — Final Freeze

Status: **FINAL / FROZEN**. Documentation and status record only. It adds no
semantics, changes no contract, modifies no implementation or test code, and
begins no further Phase 2 slice.

Phase 2 first slice P2A, Raster Primitive Observation Proposal, is complete and
frozen. Phase 1 remains FINAL / FROZEN (`spec/62-phase1-final-freeze.md`).

## Frozen baseline

```text
bb3e4a8c7e6a9f1dde6a6896a2ee72df41926d02
```

Normative contract: `spec/64-p2a-raster-primitive-observation-proposal.md`.
Charter and slice selection: `spec/63-phase2-charter.md`.

P2A lineage (baseline includes all of it):

- `e527a74` — implement P2A raster observation proposal
- `420176e` — harden P2A normative semantics
- `e5392b3` — finalize P2A normative contract
- `01bdf11` — fix P2A test closure bindings
- `1765092` — align P2A with the normative contract
- `bb3e4a8` — complete P2A acceptance coverage

The baseline is the implementation commit above. Any later documentation-only
commit, including this freeze record, is not part of the implementation baseline
and does not change it.

## Frozen capability

```text
accepted video manifest
+ canonical raster frame
+ accepted OpenCV component analysis
+ accepted mask
-> verify full lineage
-> enumerate every detected component
-> deterministic evaluation
-> SUPPORTED / UNCERTAIN / REJECTED
-> candidate only for SUPPORTED / UNCERTAIN
-> evidence-only Proposal
-> explicit acceptance
-> new Revision
```

P2A removes the requirement for a caller-provided `component_id` for primitive
observation proposal: the caller no longer names the subject per frame.

P2A does **not** solve cross-frame identity. It never compares two frames and
never assigns identity.

## Frozen authority

P2A may know:

- the one exact accepted video-frame manifest selected by the caller;
- the verified occurrence of that manifest for the source frame;
- the manifest's source video / frame lineage;
- the accepted OpenCV component analysis;
- the canonical component ordering;
- the accepted binary mask;
- the frozen raster geometry thresholds.

P2A may not know:

- semantic object identity;
- role;
- anchor / target;
- temporal pairing;
- Group;
- Track;
- Camera;
- Ground Truth;
- a free (independently supplied) tick.

## Frozen deterministic semantics

- Frame-level flat-background / solid-foreground failure aborts the whole
  inference; it is not a per-component rejection reason.
- The component reason taxonomy has a fixed order:
  `NO_CONTOUR`, `HAS_HOLE`, `MULTIPLE_CONTOURS`, `DEGENERATE_CONTOUR`,
  `AREA_BELOW_256`, `CANONICALIZATION_FAILED`, `VERTEX_COUNT_OUT_OF_RANGE`,
  `MIN_EDGE_BELOW_8`; `AMBIGUOUS_LANDMARK_ORIGIN` is the sole `UNCERTAIN` reason
  and is emitted last.
- A `CANONICALIZATION_FAILED` does not fabricate later reasons; measurements made
  impossible by an earlier failure remain undefined.
- `REJECTED` components keep an evaluation entry but have no `candidate_id`
  (JSON `null`), and are absent from `proposed_candidates`.
- Candidate and evaluation identities use the full 64-hex SHA-256, and bind the
  complete occurrence authority including `source_timestamp`.
- Verification dependency references use the exact normative ordering and match
  the `ProposalAcceptor` artifact-set contract.
- Manifest authority semantics: exactly one selected accepted manifest supplies
  the timing; the tick is read from its verified occurrence, never supplied
  separately.
- Acceptance is evidence-only and re-derives the evidence at the acceptance
  boundary; it reuses the existing `attach_analysis` action.
- Accepting P2A creates a new Revision; existing revision-bound evidence may
  become STALE under the existing revision semantics.

## Golden P2A

Normative fixture `examples/040-raster-primitive-observation-proposal`:

- 320 × 240, 8-bit grayscale, background 255 / foreground 0, `LINE_8`;
- a 2-frame FFV1 AVI at `1/1`: frame 0 blank white, frame 1 the scene;
- sampling `frame_indices = (1,)`, `ticks_per_second = 12`, so the selected
  occurrence is `frame_index = 1`, `tick = 12`, `source_timestamp = [1, 1]`;
- exactly three components in canonical order:

| Component | Status | Reason |
| --- | --- | --- |
| A | `SUPPORTED` | — |
| B | `UNCERTAIN` | `AMBIGUOUS_LANDMARK_ORIGIN` |
| C | `REJECTED` | `AREA_BELOW_256` |

Adversarial variants (not extra pixel components) include the
duplicate-occurrence case: the independent `repeated.avi` fixture holds the same
scene in both frames, so sampling `(0, 1)` makes the same canonical PNG match two
distinct occurrences and P2A fails closed. Sampling either frame alone yields two
valid manifest authorities with different occurrence timing.

## Acceptance evidence

Focused coverage in `tests/test_raster_primitive_observation_proposal.py`
(21 tests) includes, confirmed against the current code and tests:

- deterministic candidate/evaluation ids and evidence bytes;
- exact evaluation and candidate status per component;
- forged analysis (digest / bytes / provenance / kind / media);
- forged mask (descriptor and bytes must reproduce);
- tampered manifest;
- wrong and duplicate matching occurrences;
- stale proposal;
- atomic transaction failure;
- malformed JSON payloads;
- `NaN`;
- `Infinity`;
- boolean-as-integer;
- canonicalization failure as a single rejected evaluation;
- frame-level flat/solid whole-frame rejection;
- an existing POP `GroupCandidate` that is promotable before P2A;
- the same candidate becoming STALE after the P2A Revision under existing
  semantics;
- landmark parity with the frozen `contour_landmarks` contract.

CI: the repository quality matrix (`.github/workflows/ci.yml`) runs Windows and
Ubuntu on Python 3.11 and 3.12, and includes `ruff format --check .`,
`ruff check .`, `pyright`, the controlled AVI/FFV1 ingestion test, the full
`unittest` suite and CLI smoke tests. Per the freeze decision this baseline
passes that matrix — **CI PASS**.

## Frozen non-goals

P2A does not do, and must not be described as doing:

- temporal correspondence;
- object identity;
- tracking;
- deletion inference;
- occlusion;
- hierarchy;
- grouping;
- semantic labels;
- Track authoring;
- Camera inference;
- unrestricted natural-video segmentation;
- arbitrary raster-to-vector reconstruction.

## Phase boundary

Any work that changes P2A's input authority, eligibility semantics, identity
semantics, acceptance authority, or candidate meaning is **not** "P2A polish".
It belongs to a later Phase 2 slice, introduced through new
evidence/provider/acceptance boundaries.

Only a genuine bug fix may reopen P2A.

## Change control

P2A is FINAL / FROZEN at the baseline above. After this freeze:

- the frozen Phase 1 contracts and the P2A adapter, policy/schema/media
  identities, reason taxonomy, identity semantics, verification-closure ordering
  and Golden fixture must not change silently;
- any change to P2A output must be an explicitly versioned slice with updated
  specifications, fixtures and tests, and must not weaken the frozen parity,
  the reason ordering, or the non-goals above.