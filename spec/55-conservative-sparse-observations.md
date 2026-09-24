# Conservative Sparse Observation / Short Occlusion v0 (S10D)

Status: normative, explicit one-internal-missing-occurrence recovery subset.

## Existing support and actual blocker

The frozen SVG occurrence producer, R0 correspondence, R1 promotion, S0/S4
evidence, and Group Track authoring already accept increasing non-adjacent ticks.
An ordered chain `0→24, 24→36` is contiguous at its observed endpoints. No
fixed sampling cadence is implicit in these contracts. Temporal Identity already
stores a sparse list of actual `(tick, observation_id)` bindings. MotionEvaluator
already supports different keyframe densities on different targets.

The blocker was the exact Camera/translation/similarity tick-pair equality in
`_compensated_payloads()` and the geometry-translation reader's use of that same
Camera segmentation. Existing S9B compensation retains this frozen contract.
S10D adds a versioned endpoint-span input to the same mathematical implementation;
it does not change R0 thresholds, SVG producers, identity schema, ArtifactStore,
Camera consensus, interpolation, or geometry-correct translation mathematics.

The governing invariants are explicit temporal identity/binding/authoring,
INV-REF-001/002, INV-PROP-001/002, INV-TXN-001 and INV-TIME-003/010/011.
Missing is not an observation, evidence is not authoring authority, and runtime
interpolation is not observed evidence.

## Explicit short-gap policy

`SparseTemporalIdentityPromotionAdapter` takes one accepted R0 Artifact, one
explicit inference ID, `expected_tick_schedule`, and `missing_tick`. The schedule
must be a strictly increasing list of non-negative integer ticks; the missing
tick must be exactly one internal member. No production constant encodes the
fixture's 12-tick spacing.

Policy identity: `svm-one-internal-missing-occurrence@0.1`.

Schema: `svm-sparse-observation-policy-0.1`.

Media: `application/vnd.svm.sparse-observation-policy+json;version=0.1`.

The recorded Artifact contains the explicit schedule, missing tick,
`max_missing_occurrences = 1`, planned observed ticks (schedule minus missing),
Temporal Identity, exact R0/inference and observation Artifact IDs, and actual
gap endpoint ticks/observation IDs. It is a policy record, not a missing-frame
observation or invented geometry. Absence is explicitly declared by the caller;
the policy does not discover visibility or infer why a shape is absent.

Only a SUPPORTED candidate connecting the immediate schedule neighbors of the
missing occurrence may be promoted. Its formal R0 inference is reproduced from
the recorded observation Artifact. The existing R1 adapter creates/extends the
ordinary identity. Promotion and policy attachment commit atomically through
registered Changes. UNCERTAIN, REJECTED, missing endpoints, two skipped schedule
occurrences, or a different gap policy for the same identity reject. No thresholds
are relaxed and no parallel occluded-identity type exists.

"Short" means one omitted occurrence in this explicit schedule, not a universal
wall-clock duration. A SUPPORTED `0→10000` pair does not itself establish a short
gap. At compensation, the entire schedule must equal the complete Camera chain,
and the actual target identity/evidence must cover exactly the planned observed
ticks. This rejects missing first/last observations, additional gaps, and attempts
to relabel an arbitrarily long jump within the recorded schedule.

Existing generic R1 promotion remains frozen; it does not claim short-occlusion
semantics. S10D requires this explicit policy path rather than silently treating
every generic non-adjacent correspondence as an occlusion bridge.

## Dense Camera and sparse Target

`SparseCameraCompensatedMotionAdapter` requires four already accepted Artifacts:
complete S10C consensus Camera evidence, target S0, target S4, and the sparse policy.
Anchor selection and target Temporal Identity remain explicit. All consensus
anchors are rechecked using the existing static-anchor subset. The Change captures
the current identity, anchors, Groups, animation and presentation for atomic
stale rejection. It grants evidence attachment authority only.

Target translation and similarity MUST have identical ordered intervals, matching
exactly the observed ticks in the policy. Their endpoint observation IDs and R1
provenance must match the current Temporal Identity. The gap must retain the
policy's exact R0/inference/geometry lineage. No binding may exist for the missing
tick. Camera consensus itself remains complete and unchanged.

`camera_view_state_by_tick()` validates the existing contiguous Camera chain and
reads its exact absolute matrices. For each target interval `s→t`, record a
Camera endpoint span containing:

* source/target ticks and exact `V_s`, `V_t`;
* relative transform `V_t × inverse(V_s)`;
* the original consensus Artifact ID and every covered Camera interval ID;
* a deterministic `camera-endpoint-span:` hash and sparse policy identity.

Spans are derived Camera inputs, not target observations and not replacement
Camera consensus intervals. No Camera state is interpolated, fitted, averaged,
or obtained by adding interval translations. Missing Camera endpoints reject.

The spans feed the unchanged `_compensated_payloads()` math:

```text
world_relative = inverse(V_t) × observed_target_relative × V_s
```

S10D outputs are explicitly versioned:

* `svm-camera-compensated-translation-motion-0.2`
* `svm-camera-compensated-similarity-motion-0.2`

Their existing media names carry `version=0.2`; identities carry `@0.2`.
Policy is `svm-sparse-camera-similarity-compensation@0.1`. They retain original
source IDs and target interval IDs, and add `sparse_observation_policy_artifact_id`
and the complete `camera_spans`. Acceptance reproduces payloads and provenance.
Legacy v0.1 outputs and exact-segmentation compensation are unchanged.

## Explicit authoring and interpolation

`GeometryTranslationTracksAdapter` resolves the new versioned inputs and
recomputes the same Camera spans before its frozen Group similarity accumulation
and fixed-origin decomposition. It does not author from S0 bounds displacement.
Existing rotation/scale CREATE adapters read the new verified similarity version.
Camera Track authoring continues to consume the original full S10C consensus.

For the fixture:

| Subject | Actual bindings / recovered keyframe ticks |
| --- | --- |
| Target Temporal Identity | 0, 24, 36 |
| Group translate.x/y, rotation, scale | 0, 24, 36 |
| Camera position.x/y, rotation, scale | 0, 12, 24, 36 |

At tick 12 the Target pose is linear runtime interpolation between recovered
endpoints. It has no observation ID, identity binding, keyframe, or observation
provenance. The authored Document does not infer a visibility Track. Evaluating
it may render this interpolated Target at tick 12; that is not a recovered
observation of the occluded pose.

Track provenance leads through the explicit binding and compensated evidence to
the policy, gap correspondence, actual occurrences, S0/S4 and full consensus
Camera. No lineage claims a target observation at the missing tick.

## Executable proof and freeze readiness

`examples/034-sparse-observation-recovery` freezes two distinct always-visible
anchors, an off-center-origin moving Target, and pan/rotation/uniform-scale
Camera motion. Both Camera intervals inside `0→24` move; `24→36` holds, producing
identical repeated SVGs. The tick-12 render input is a formal static Document
variation whose render stack omits the Target. The normal MotionEvaluator and
SVGRenderer produce the output: no string/regex SVG editing or special renderer.

Recovery reads only the Recovery Document, immutable SVGs, ticks, policy and
explicit selections. Ground Truth is used to generate those SVGs and for final
assertions, never as recovery input. Formal geometry observations compare both
anchors at all ticks and the Target at 0/24/36 within `3e-8`. Missing-tick Target
accuracy is not an acceptance requirement.

`tests/test_sparse_observation_recovery.py` covers sparse identity continuity,
real absence, exact Camera endpoint math, deterministic repeated runs, different
Track densities, runtime interpolation, formal ambiguous R0 abstention, long and
repeated gaps, missing endpoints, schedule/policy/evidence/identity tampering,
fake tick-12 lineage, stale binding and atomic failure. Prior recovery suites
retain the multi-object, repeated-frame, consensus and geometry-correct proofs.

Together these tests support Synthetic Scene Recovery v1 freeze readiness within
the stated subset. Final freeze approval remains a separate acceptance decision.
Noise, uncertain recovery, long/multiple occlusion, automatic association,
partially missing anchors, deformation, perspective and raster/video remain
unsupported. No further frontend or tracking work belongs to this slice.
