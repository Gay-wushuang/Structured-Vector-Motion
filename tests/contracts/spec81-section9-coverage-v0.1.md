# Spec81 §9 executable coverage matrix (B0-4A)

This matrix records the executable tests used by the B0-4A acceptance gate.
`Consumer`, `Verifier`, `Producer`, and `Acceptor` name the boundary actually
exercised. A row is covered only when the named test contains an assertion for
the required outcome; comments and fixture construction do not count.

| Case | Expected result | Executable test | Boundary | B0-4A result |
| --- | --- | --- | --- | --- |
| 1 | Data-only certification; S2 abstention; no parse | `test_byte_valid_and_malformed_reserved_references_without_events_are_data`; `test_zero_admitted_claim_and_legacy_certification_data_write_nothing` | Consumer, Producer | PASS |
| 2 | Genuine event plus bytes/descriptor tamper rejects at S3 | `test_missing_blob_hash_tampering_and_descriptor_conflict_fail_closed`; `test_received_snapshot_bytes_descriptor_identity_and_map_keys_are_verified` | Consumer, Verifier | PASS |
| 3 | Missing declared Artifact is `ProposalArtifactError` before verifier | `test_unresolved_artifact_stays_at_existing_acceptor_error_boundary` | Acceptor | PASS |
| 3b | Read-only missing Artifact fails closed at S3 | `test_missing_blob_hash_tampering_and_descriptor_conflict_fail_closed` | Consumer | PASS |
| 3c | Missing verifier-map id raises without a stable consumer reason | `test_missing_required_ids_and_received_map_cannot_omit_transport` | Verifier | PASS |
| 3d | Missing historical transport rejects at S3 | `test_current_representation_edit_and_missing_historical_dependency_fail_closed` | Verifier | PASS |
| 4 | Geometry, style, render order, transform changes reject at S6 | `test_current_group_geometry_and_identity_edits_fail_applicability` | Consumer | PASS |
| 5 | Identity extension/alias rejects at S6 | `test_current_group_geometry_and_identity_edits_fail_applicability` | Consumer | PASS |
| 6 | Dependency descriptor removed/changed rejects | `test_missing_dependency_and_remove_restore_history_never_recover_applicability` | Consumer | PASS |
| 7 | Current coverage incomplete rejects | `test_output_source_part_occurrence_membership_and_universe_tampering_reject`; `test_current_representation_edit_and_missing_historical_dependency_fail_closed` | Spec80, Verifier | PASS |
| 8 | Relevant Track yields `TRACKED_REPRESENTATION` | `test_legal_group_and_member_tracks_are_ineligible_without_current_replay` | Consumer | PASS |
| 9 | Two authenticated non-equivalent claims yield `COMPETING_ASSOCIATION` | `test_authenticated_claim_set_classifies_duplicate_and_competing_claims` | Consumer multi-claim boundary | PASS |
| 10 | Two authenticated equivalent claims yield `AMBIGUOUS_ASSOCIATION` | `test_authenticated_claim_set_classifies_duplicate_and_competing_claims` | Consumer multi-claim boundary | PASS |
| 11 | Valid existing binding authenticates first, then `ALREADY_BOUND` | `test_existing_legitimate_binding_preserves_authority_and_skips_current_replay` | Consumer | PASS |
| 12 | Broken history/evidence outranks `ALREADY_BOUND` | `test_bound_state_never_hides_history_transport_or_artifact_fraud` | Consumer | PASS |
| 13 | Missing/pruned/substituted/reordered/forged Witness rejects at S0 | `test_incomplete_reordered_substituted_and_forged_witnesses_reject` | Consumer | PASS |
| 14 | Base-only Witness is incomplete | `test_incomplete_reordered_substituted_and_forged_witnesses_reject` | Consumer | PASS |
| 14b | Witness defect precedes transport defect | `test_witness_defect_outranks_transport_and_snapshot_defects`; `test_witness_failures_precede_transport_defects` | Consumer, Verifier | PASS |
| 15 | Omitted identity/claim/artifact rejects incomplete universe | `test_supplied_snapshot_omission_rejects_with_complete_authenticated_inventory`; `test_base_snapshot_reference_universe_policy_and_source_are_bound` | Consumer, Verifier | PASS |
| 16 | Extra or substituted selected pair rejects exact comparison | `test_complete_pair_and_exact_delegated_record_are_independently_reproduced` | Verifier | PASS |
| 17 | Uncertified identity abstains without Group inference | `test_uncertified_whole_and_part_identities_all_abstain_without_resolution` | Consumer | PASS |
| 18 | Stale base rejects before verifier | `test_final_validation_failure_and_stale_base_do_not_publish` | Acceptor | PASS |
| 19 | Policy/delegated/final-validation failure is atomic | `test_denying_binding_or_evidence_intent_publishes_neither`; `test_direct_apply_rolls_back_failure_after_frozen_binding_mutation`; `test_final_validation_failure_and_stale_base_do_not_publish` | Acceptor, Composite | PASS |
| 20 | Replay/engine failure rejects wholly | `test_engine_exception_text_never_changes_error_classification`; `test_witness_snapshot_missing_bytes_and_current_edit_reject_before_writer` | Consumer, Producer | PASS |
| 21 | Post-accept rerun is `ALREADY_BOUND` / `ZERO_SELECTED`, no Revision | `test_real_production_rebuild_preview_acceptance_and_bound_rerun` | Producer, Acceptor | PASS |
| 22 | Same-base rebuild and reset/replay preserve all identities | `test_real_production_rebuild_preview_acceptance_and_bound_rerun` | Producer, Acceptor | PASS |
| 23 | Positive acceptance creates no Track | `test_real_production_rebuild_preview_acceptance_and_bound_rerun` and pinned Golden counts | Acceptor | PASS |
| 24 | Preview/validation does not mutate accepted state or admissions | `test_real_production_rebuild_preview_acceptance_and_bound_rerun` | Producer, Acceptor | PASS |
| 25 | Evidence bytes, id, descriptor rebuild identically | `test_same_base_rebuild_reuses_bytes_descriptor_and_required_transport`; `test_real_production_rebuild_preview_acceptance_and_bound_rerun` | Verifier, Producer | PASS |
| 26 | One selected pair and complete evidence counts/audits | `test_exact_evidence_envelope_complete_counts_and_explicit_nulls`; `test_real_production_rebuild_preview_acceptance_and_bound_rerun` | Verifier, Producer | PASS |
| 27 | Every identity and legacy reserved reference remains audited | `test_unadmitted_certification_audit_preserves_source_provenance_locator_and_nulls` | Verifier | PASS |
| 28 | Evidence counts/audits/order/canonical bytes/descriptor tamper rejects | `test_tampered_counts_arrays_field_sets_and_consumer_nulls_reject`; `test_noncanonical_and_nonobject_output_bytes_reject`; `test_output_descriptor_kind_media_provenance_and_locator_are_exact` | Verifier | PASS |
| 29 | Zero-selected/reject creates no Proposal or evidence | `test_zero_admitted_claim_and_legacy_certification_data_write_nothing`; `test_legal_existing_track_yields_zero_selected_without_output` | Producer | PASS |
| 30 | Missing selection-evidence Artifact remains Acceptor error | `test_unresolved_artifact_stays_at_existing_acceptor_error_boundary` | Acceptor | PASS |
| 31 | Generic evidence append has no selection authority | `test_generic_selection_evidence_attachment_is_data_not_dedicated_authority` | Acceptor, Consumer | PASS |
| 32 | Frozen binding id/snapshot/stale/conflict/ownership behavior unchanged | `test_frozen_s1_direct_acceptance_and_old_golden_bytes_remain_unchanged`; `test_complete_pair_and_exact_delegated_record_are_independently_reproduced` | Frozen delegate, Verifier | PASS |

Cases 9 and 10 use an isolated authenticated multi-claim consumer boundary:
the frozen Spec80 v0.1 profile independently rejects a second counterfeit
admission before it can reach that state. The stub supplies only the already
authenticated Reference selected by each known birth Revision; Artifact bytes,
claim decoding, equivalence, endpoint comparison, and classification remain the
real Consumer implementation.
