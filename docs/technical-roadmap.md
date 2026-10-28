# SVM Technical Roadmap

Status: non-normative documentation
Audit baseline: `fd4cbd53f3c4d6de73d42ba3535af2bc5c281c43` on
`research/temporal-geometry-pilot` (2026-10-29)

This is the single repository overview for the current SVM technical roadmap.
It records verified repository state, research gates, candidate tools, and
product sequencing. It does not change Document meaning, freeze a specification,
accept experimental evidence, or authorize implementation.

If this overview conflicts with a normative source, the normative source wins.
Start with the [Core Model](../spec/00-svm-core-model.md),
[Invariants](../spec/01-invariants.md), and
[System Boundaries](../spec/05-system-boundaries.md). Working rules are in
[AGENTS.md](../AGENTS.md).

## Status vocabulary

External tools and integrations use only these roadmap labels:

- `IMPLEMENTED`: code exists on the audited branch, but verification may be
  pending or narrower than production readiness.
- `VERIFIED`: the stated bounded behavior has executable repository evidence.
- `RESEARCH`: an experiment or research adapter exists, without formal SVM
  capability admission.
- `CANDIDATE`: technically relevant, but not integrated or accepted.
- `BLOCKED`: a named technical, provenance, licensing, or evidence gate prevents
  the intended use.

Four decisions remain independent: documentation synchronization, roadmap
adoption, experiment acceptance, and formal capability admission. Formal
admission requires the applicable Spec, Change Authority, Revision, Golden, and
CI evidence. None of these decisions implies the next.

## Architecture boundary

SVM is a deterministic construction computation model. Its portable artifact is
the Document, not an SVG, editor scene graph, runtime cache, or research output.

```text
SVM Project
|- Document          portable artistic intent
|- Revision Store    transactions, proposals, branches
|- Runtime State     evaluation state and caches
`- Editor State      selection, viewport, panels, temporary tools
```

External optimizers, generators, and research tools produce immutable Artifacts
and Proposals. They do not mutate accepted Documents directly. Only registered
closed-world Changes may cross the Change Authority boundary. SVG, raster, and
research-output adapters remain outside Core semantics.

Two long-term product routes may reuse that boundary: editable vector motion,
and structure-aware raster/video repair. They may share accepted Documents,
Entities, Groups, Tracks, Keyframes, Revisions, and Evidence, but neither route
may treat a raw mask, trajectory, label, layer, or research JSON file as formal
identity. General video reconstruction is not a present capability.

## Audited capability baseline

The native status language of each linked specification remains authoritative.

| Area | Current evidence | Roadmap reading |
| --- | --- | --- |
| Phase 1 | [Final Freeze](../spec/62-phase1-final-freeze.md) | Frozen baseline; preserve its contracts. |
| Phase 2A | [Charter](../spec/63-phase2-charter.md) and [final gate](../spec/65-p2a-final-freeze.md) | Accepted bounded Phase 2A scope. |
| Phase 2B | [Final gate](../spec/67-p2b-final-freeze.md) | Accepted bounded Phase 2B scope. |
| Phase 2C | [Final gate](../spec/69-p2c-final-freeze.md) | Accepted bounded Phase 2C scope. |
| P2D provenance binding | [Spec 70](../spec/70-p2d-exact-provenance-motion-target-binding.md) | Specified, not implemented. |
| Stable representation correspondence | [Spec 71](../spec/71-stable-artwork-representation-correspondence.md) | Design contract, not frozen. |
| First video-backed construction | [Spec 78](../spec/78-first-video-backed-artwork-construction-profile.md) | Implemented and Golden-verified, not frozen. |
| Present-time certification | [Spec 80](../spec/80-present-time-representation-certification.md) | Implemented, Golden-verified, and frozen for bounded v0.1. |
| P2D-B0 consumer | [Spec 81](../spec/81-versioned-representation-target-consumer-contract.md) | Implemented, Golden-verified, and frozen only for P2D-B0. General P2D-B remains open. |
| P2D-A formalization | [Spec 82](../spec/82-explicit-authored-group-assembly.md) | Design-only and blocked on this branch; other-branch work is not counted. |
| Primitive P0 toolchain | [Spec 83](../spec/83-fogleman-primitive-toolchain.md) and [Golden 047](../examples/047-fogleman-primitive-toolchain/README.md) | Real PNG to Primitive to restricted SVG to accepted Revision to deterministic render is implemented and Golden-verified. |

The controlled video examples prove only their recorded OpenCV/FFV1 subset.
They do not establish ordinary-video recovery, generic codec support, semantic
tracking, or completion of P2D-B.

## Temporal Geometry Pilot gates

The [Temporal Geometry Pilot](../research/temporal-geometry-pilot/README.md) is
research-only. Its gates are independent:

| Gate | Result | Meaning |
| --- | --- | --- |
| T1 original run | `CONDITIONAL` | Its manifest recorded an OpenCV runtime mismatch. This is historical research evidence, not accepted SVM evidence. |
| T1.1 declared-runtime rerun | `GO` within its own research protocol | The canonical rerun used the declared NumPy/OpenCV environment. It does not change the original T1 result or admit a capability. |
| T2-P0A | Frozen protocol | The protocol was frozen before execution; this is not an experiment result. |
| T2-P1 | `STOP` | The overall gate stopped because F2's control was invalid; F3 was inconclusive and F4 conditional. |

Canonical evidence and detailed failure reasons are linked from the Pilot
README. Later experiments require their own frozen protocol and decision.

## External technology inventory

Licenses are recorded against exact integrated or surveyed upstream versions.
This is an engineering audit aid, not legal advice. Weights, datasets, fonts,
hosted services, and transitive native libraries may carry separate terms.

| Technology and audited version | Status | Bounded role | License / unresolved gate |
| --- | --- | --- | --- |
| [OpenCV Python wheel `4.14.0.94`](https://pypi.org/project/opencv-python-headless/4.14.0.94/) | `VERIFIED` | Controlled raster analysis and recorded FFV1 decode through `CAP_FFMPEG`. | Apache-2.0 package metadata. FFmpeg licensing is build-dependent; inspect the shipped binary before distribution. |
| [Shapely `2.1.2`](https://pypi.org/project/shapely/2.1.2/) | `VERIFIED` | Optional deterministic planar geometry backend. | BSD-3-Clause; bundled GEOS is LGPL-2.1-or-later. |
| [svgpathtools `1.7.2`](https://pypi.org/project/svgpathtools/1.7.2/) | `VERIFIED` | Restricted SVG path parsing support. | MIT. |
| [potracer `0.0.4`](https://pypi.org/project/potracer/0.0.4/) | `VERIFIED` | Optional bitmap trace adapter engine. | GPL-2.0-or-later; original Potrace also offers commercial licensing. Distribution compatibility is a product gate. |
| [fogleman/primitive `0373c216458be1c4b40655b796a3aefedf8b7d23`](https://github.com/fogleman/primitive/blob/0373c216458be1c4b40655b796a3aefedf8b7d23/LICENSE.md) | `VERIFIED` | Golden 047 external geometry fitting executable. | MIT. Exact source and binary hashes are recorded by the example. |
| [POP `d5489b039d876839b58b61c512205713b3ab6909`](https://github.com/wonderfulearth/primitive-operation-painter/tree/d5489b039d876839b58b61c512205713b3ab6909) plus recorded checkpoint hash | `VERIFIED` | Snapshotted token-output adapter and accepted primitive scene. | Exact upstream code/checkpoint redistribution terms were not established; redistribution is `BLOCKED` pending review. |
| [VTracer `e71343fbcbf469b8a72a255030408a39939162eb`](https://github.com/visioncortex/vtracer/tree/e71343fbcbf469b8a72a255030408a39939162eb) (release line `1.0.0-alpha.4`) | `CANDIDATE` | Possible tracing comparison under a separate work order. | MIT OR Apache-2.0. No integration or experiment is authorized here. |
| [SAM 2 `2b90b9f5ceec907a1c18123530e92e794ad901a4d`](https://github.com/facebookresearch/sam2/blob/2b90b9f5ceec907a1c18123530e92e794ad901a4d/LICENSE) | `CANDIDATE` | Possible segmentation research input, outside Core. | Apache-2.0 for the audited repository/checkpoints; bundled assets may differ. No weights are part of SVM. |
| [RAFT `2888e15a51fa41140771d3f498ed8023cff098d1`](https://github.com/princeton-vl/RAFT/blob/2888e15a51fa41140771d3f498ed8023cff098d1/LICENSE) | `CANDIDATE` | Possible optical-flow research control. | BSD-3-Clause. No current-branch SVM evidence. |
| [CoTracker `82e02e8029753ad4ef13cf06be7f4fc5facdda4d`](https://github.com/facebookresearch/co-tracker/tree/82e02e8029753ad4ef13cf06be7f4fc5facdda4d) | `BLOCKED` | Possible point-tracking research control. | Main project license is CC-BY-NC; product use is blocked without a compatible grant. Subcomponents differ. |
| [diffvg `85802a71fbcc72d79cb75716eb4da4392fd09532`](https://github.com/BachiLi/diffvg/blob/85802a71fbcc72d79cb75716eb4da4392fd09532/LICENSE) | `CANDIDATE` | Possible differentiable-rendering research control. | Apache-2.0. Not an SVM runtime dependency. |
| [LayerPeeler `b75f2353011972f4c8c2dc748c1f0861ede2ee80`](https://github.com/kingnobro/layerpeeler/tree/b75f2353011972f4c8c2dc748c1f0861ede2ee80) | `BLOCKED` | SVM verifies only a manifest-bound snapshot consumer; upstream generation is not integrated. | No root license was found at the audited revision; the workflow also uses hosted services. Generation/redistribution remains blocked. |
| [LayerTracer `8e089f92795b4f32dcae8f7dbbd5ced20395dad7`](https://github.com/showlab/LayerTracer/blob/8e089f92795b4f32dcae8f7dbbd5ced20395dad7/LICENSE) | `CANDIDATE` | Possible layered-vectorization comparison. | MIT. No current-branch integration. |
| [layered-vectorization `1224d0a299015752a43ad5daacd40f460f04f0db`](https://github.com/SZUVIZ/layered_vectorization/tree/1224d0a299015752a43ad5daacd40f460f04f0db) | `BLOCKED` | Possible research comparison. | No root license was found at the audited revision; integration and redistribution remain blocked. |
| [NPA survey target](../research/npa/README.md) | `BLOCKED` | Proposed research-output adapter target. | No authentic official repository, checkpoint, and output bundle were established; nothing is admissible to integrate. |

Existing adapter boundaries remain in [Spec 13](../spec/13-bitmap-trace-adapter.md),
[Spec 16](../spec/16-opencv-artifact-analysis.md),
[Spec 19](../spec/19-layerpeeler-output-adapter.md),
[Spec 26](../spec/26-pop-output-adapter.md), and
[Spec 83](../spec/83-fogleman-primitive-toolchain.md).

## Product milestones M0-M4

M0-M4 are product-planning milestones. They are not aliases for repository
Phase numbers, Spec numbers, Golden numbers, or research gates.

| Milestone | Product outcome | Admission condition |
| --- | --- | --- |
| M0 — Deterministic construction kernel | Preserve the proven Document-to-evaluation, immutable-output, selective-invalidation, lazy-reevaluation, and identity loop. | Frozen invariants and Golden baselines remain green. |
| M1 — Trusted still-image ingestion | Turn bounded external still-image evidence into editable, revisioned construction without bypassing Change Authority. | Each adapter has a restricted subset, immutable provenance, rejection cases, Golden evidence, and license decision. |
| M2 — Evidence-backed structure | Promote only explicit, stale-safe component, relation, group, and observation evidence. | Promotion remains a separate accepted Change; abstention and conflicts are tested. |
| M3 — Authored deterministic motion | Author and revise declared motion targets with deterministic sampling and rendering. | Track ownership, re-authoring, sampling, invalidation, and revision behavior remain explicit. |
| M4 — Bounded temporal recovery | Admit narrow temporal recovery profiles only after independent research gates. | A frozen protocol passes, provenance is exact, controls are valid, and a dedicated Spec/Golden admits the bounded capability. Ordinary video recovery and general P2D-B are not presumed. |

## Execution gates

1. Preserve frozen Core, Revision, Change Authority, rendering, and identity
   semantics.
2. Complete small vertical slices against documented use cases and executable
   tests; do not generalize from one controlled fixture.
3. Keep external executors and conversion logic isolated. Unsupported input
   fails closed rather than expanding Core or the SVG subset.
4. Record engine and semantics versions, quality, randomness, and accepted
   Artifact hashes whenever they affect results.
5. Separate protocol freezing, execution, experiment acceptance, adapter
   implementation, and formal capability admission.
6. Treat license and redistribution review as a release gate independent of
   technical verification.

VTracer integration, T1 follow-up, AI segmentation, general video tracking, and
P2D-B expansion each require a separate work order and gate.

Any future comparison should freeze common input, resolution, color and time
contracts, evaluation code, optimization budget, and reference data. Report
geometry quality, temporal drift, flicker, occlusion, abstention, runtime,
memory, and editable complexity. Ground truth used to select a candidate must be
reported as an oracle upper bound. Manual baselines in established motion and
compositing tools remain valid product evidence; a technical integration alone
does not establish user value.

## Explicit non-claims

- This roadmap does not modify or freeze any specification.
- Temporal Pilot outputs are not Accepted SVM Evidence.
- Primitive P0 verifies one constrained real-tool chain, not arbitrary
  Primitive SVG or a general vector editor.
- Controlled FFV1/OpenCV fixtures do not prove ordinary-video ingestion.
- P2D-B0 does not mean general P2D-B is complete.
- Commits present only on other branches are not current-branch capabilities.
- Candidate tools are not dependencies, and no model weights are included.

## Navigation

- [Repository README](../README.md)
- [Core Model](../spec/00-svm-core-model.md)
- [System Boundaries](../spec/05-system-boundaries.md)
- [Operation Registry](../spec/06-operation-registry.md)
- [SVG Import Adapter](../spec/10-svg-import-adapter.md)
- [Phase 1 Final Freeze](../spec/62-phase1-final-freeze.md)
- [Phase 2 Charter](../spec/63-phase2-charter.md)
- [Temporal Geometry Pilot](../research/temporal-geometry-pilot/README.md)
- [Primitive P0 Golden evidence](../examples/047-fogleman-primitive-toolchain/README.md)
