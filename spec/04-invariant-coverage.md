# SVM v0.1 Invariant Coverage

Status values:

- **covered** — exercised by an automated semantic test;
- **fail-closed** — positive functionality is pending, but unsupported input is
  rejected rather than accepted without enforcement;
- **specified** — normative behavior exists but does not yet have full runtime
  coverage.

| Invariant | Status | Coverage |
| --- | --- | --- |
| INV-ID-001 | covered | Golden A preserves Head identity across geometry reevaluation. |
| INV-ID-002 | covered | Golden A preserves Operation and Output Slot identity. |
| INV-ID-003 | covered | Repeated equivalent evaluation produces the same Value hash. |
| INV-ID-004 | covered | Golden B allocates new Face and Hair Entity IDs. |
| INV-ID-005 | specified | Revision snapshots preserve prior entities; explicit tombstone records are not implemented. |
| INV-EVAL-001 | covered | Evaluation produces new immutable payloads and never mutates inputs. |
| INV-EVAL-002 | covered | Golden A and A.1 cover deterministic context and Quality-sensitive reevaluation. |
| INV-EVAL-003 | specified | Current operations have no clock, network, UI, or unrecorded randomness access. |
| INV-EVAL-004 | covered | Golden A verifies isolated transitive invalidation. |
| INV-EVAL-005 | covered | Golden A preserves stale output separately; A.1 rejects PREVIEW equivalence for FINAL. |
| INV-EVAL-006 | specified | Runtime has BLOCKED state; explicit failure-chain test remains pending. |
| INV-EVAL-007 | covered | Evaluator runtime is reconstructed from the Document in tests. |
| INV-DOC-001 | covered | Validator requires both versions. |
| INV-DOC-002 | specified | Separate schema and semantics fields are defined. |
| INV-REF-001 | covered | Artifact Store and SVG Import tests verify byte-only SHA-256 identity, resolver verification, and accepted references. |
| INV-REF-002 | covered | Artifact tests keep content identity separate from URI/provenance locators. |
| INV-REF-003 | specified | Adapter boundary requires accepted fixed artifacts; model adapters are pending. |
| INV-REL-001 | covered | Example Documents keep hierarchy, render stack, and stages separate. |
| INV-TIME-001 | specified | Construction scheduling is separate from graph dependencies. |
| INV-TIME-002 | specified | Content and construction scheduling arrays are separate. |
| INV-TXN-001 | covered | Golden B verifies atomic success and failure. |
| INV-PROP-001 | covered | Adapter snapshot isolation and explicit acceptance are tested. |
| INV-PROP-002 | covered | Base conflicts plus supported Constraints and Edit Permissions are enforced by acceptance tests. |
| INV-CTRL-001 | covered | Document Schema stores the three control systems separately. |
| INV-CTRL-002 | covered | Actor/action/target deny rules are enforced; unsupported policy definitions fail validation. |

This file must be updated when an invariant gains, loses, or changes executable
coverage. A baseline may contain `specified` entries, but code must not claim
that all normative invariants are fully implemented while they remain.

Additional semantic validation coverage in `tests/test_operations.py` verifies
registered type dispatch, exact input signatures, parameter rules, static and
dynamic output signatures, Value-type compatibility, binding resolution, and
atomic parameter mutation.
