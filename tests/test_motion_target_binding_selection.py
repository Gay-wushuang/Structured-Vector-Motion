"""Pure P2D-A derivation tests, using frozen producers rather than claimed lineage."""

from __future__ import annotations

import copy
import json
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from svm import AdapterRequest, ArtifactStore
from svm.adapters.motion_target_binding_selection import (
    Abstention,
    MotionTargetBindingSelectionError,
    Reason,
)
from svm.adapters.motion_target_binding_selection import (
    derive_motion_target_binding_selection as derive,
)
from svm.adapters.opencv_analysis import OpenCVAnalysisAdapter
from svm.adapters.raster_geometry_observations import derive_raster_observations
from svm.adapters.svg_geometry_observations import SVGGeometryObservationAdapter
from svm.adapters.temporal_correspondence import (
    OBSERVATION_MEDIA_TYPE_V2,
    TemporalCorrespondenceAdapter,
)
from svm.adapters.temporal_identity_promotion import TemporalIdentityPromotionAdapter
from svm.evaluator import canonical_bytes
from svm.revisions import PromotedComponent

ROOT = Path(__file__).resolve().parents[1]
G1, G2 = "group:" + "1" * 64, "group:" + "2" * 64
TRANSFORM = {"translate": [0, 0], "rotation_degrees": 0, "scale": 1, "origin": [0, 0]}


def request(document, ids=(), options=None):
    return AdapterRequest(
        "revision:fixture", document, ("document",), artifact_ids=tuple(ids), options=options or {}
    )


def accept_reference(document, snapshot):
    reference = snapshot.document_reference()
    if reference not in document["references"]:
        document["references"].append(reference)


def promote_observation(document, artifacts, observation):
    accept_reference(document, observation)
    proposal = TemporalCorrespondenceAdapter().propose(
        request(document, [observation.artifact_id]), artifacts
    )
    evidence = artifacts.get(proposal.preview_artifacts[0].artifact_id)
    accept_reference(document, evidence)
    payload = json.loads(evidence.content)
    ids = [c["inference_id"] for c in payload["candidates"] if c["status"] == "SUPPORTED"]
    assert ids
    promotion = TemporalIdentityPromotionAdapter().propose(
        request(document, [evidence.artifact_id], {"inference_ids": ids}), artifacts
    )
    promotion.transaction.changes[0].apply(document)
    return evidence


def group(gid, entity):
    return {
        "id": gid,
        "kind": "explicit-group",
        "members": [entity, "entity:other-" + gid[-1]],
        "transform": copy.deepcopy(TRANSFORM),
    }


def raster_case(name="base", ticks=(0, 12)):
    artifacts = ArtifactStore()
    document = {
        "references": [],
        "entities": [],
        "groups": [],
        "presentation": {"render_stack": []},
    }
    source = artifacts.import_bytes(
        (ROOT / f"examples/035-controlled-raster-recovery/{name}.png").read_bytes(),
        media_type="image/png",
    )
    proposal = OpenCVAnalysisAdapter().propose(request(document, [source.artifact_id]), artifacts)
    mask, analysis = (artifacts.get(p.artifact_id) for p in proposal.preview_artifacts)
    for snapshot in (source, mask, analysis):
        accept_reference(document, snapshot)
    component = json.loads(analysis.content)["components"][0]
    occurrences = [
        {
            "analysis_artifact_id": analysis.artifact_id,
            "component_id": component["candidate_id"],
            "tick": t,
        }
        for t in ticks
    ]
    payload, provenance = derive_raster_observations(
        occurrences, {s.artifact_id: s for s in (source, mask, analysis)}
    )
    observation = artifacts.import_bytes(
        canonical_bytes(payload), media_type=OBSERVATION_MEDIA_TYPE_V2, provenance=provenance
    )
    evidence = promote_observation(document, artifacts, observation)
    entity = PromotedComponent(
        analysis.artifact_id,
        component["candidate_id"],
        component["component_digest"],
        tuple(component["bounds"]),
    ).to_entity("p2d-test")
    document["entities"] = [entity]
    document["groups"] = [group(G1, entity["id"])]
    return document, artifacts, observation, evidence


class MotionTargetBindingSelectionDerivationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = raster_case()
        cls.second = raster_case("translation", (24, 36))
        cls.repeat = raster_case("base", (24, 36))

    def setUp(self):
        self.document, self.artifacts, self.observation, self.evidence = copy.deepcopy(self.first)

    def combine(self, case, gid=G2):
        document, artifacts, _, _ = copy.deepcopy(case)
        for ref in document["references"]:
            s = artifacts.resolve_reference(ref)
            self.artifacts.import_bytes(
                s.content,
                media_type=s.media_type,
                kind=s.kind,
                provenance=s.provenance,
                locator=s.descriptor.locator,
            )
            accept_reference(self.document, s)
        self.document["temporal_identities"].extend(document["temporal_identities"])
        for entity in document["entities"]:
            if entity not in self.document["entities"]:
                self.document["entities"].append(entity)
        if gid != G1:
            self.document["groups"].append(group(gid, document["entities"][0]["id"]))
        return document["temporal_identities"][0]

    def bound(self, identity=None, gid=G1):
        identity = identity or self.document["temporal_identities"][0]
        binding = {
            "id": "motion-target-binding:" + "8" * 64,
            "temporal_identity_id": identity["id"],
            "target": {"kind": "group", "group_id": gid},
        }
        self.document["motion_target_bindings"] = [binding]
        return binding

    def test_real_raster_promoted_component_is_supported_without_pixel_reads(self):
        before = copy.deepcopy(self.document)
        with (
            patch(
                "svm.adapters.raster_geometry_observations.derive_raster_observations",
                side_effect=AssertionError("No producer rerun"),
            ),
            patch(
                "svm.adapters.opencv_analysis.analyze_png", side_effect=AssertionError("No pixels")
            ),
        ):
            result = derive(self.document, self.artifacts)
        self.assertEqual(self.document, before)
        self.assertEqual(result.evaluations[0].status, "SUPPORTED")
        self.assertEqual(result.selected_pairs[0].group_id, G1)
        self.assertIsNone(result.abstention)
        self.assertEqual(len(result.evaluations[0].paths), 2)
        self.assertEqual(
            [r["id"] for r in result.required_references],
            [self.evidence.artifact_id, self.observation.artifact_id],
        )
        for path in result.evaluations[0].paths:
            entity = self.document["entities"][0]
            self.assertEqual(
                (path.analysis_artifact_id, path.component_id, path.component_digest),
                tuple(
                    entity["provenance"][k]
                    for k in ("artifact_id", "candidate_id", "component_digest")
                ),
            )

    def test_two_groups_and_reversed_identity_order_select_all_canonically(self):
        self.combine(self.second)
        self.document["temporal_identities"].sort(key=lambda i: i["id"], reverse=True)
        result = derive(self.document, self.artifacts)
        self.assertEqual(len(result.selected_pairs), 2)
        self.assertEqual(
            [p.temporal_identity_id for p in result.selected_pairs],
            sorted(i["id"] for i in self.document["temporal_identities"]),
        )
        self.document["temporal_identities"].reverse()
        self.assertEqual(derive(self.document, self.artifacts), result)

    def test_partial_provenance_is_uncertain(self):
        record = copy.deepcopy(self.document["temporal_identities"][0]["provenance"][0])
        record["evidence_artifact_id"] = "artifact:" + "f" * 64
        self.document["temporal_identities"][0]["provenance"].append(record)
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.evaluations[0].reason_codes, (Reason.PARTIAL_PROVENANCE,))
        self.assertEqual(result.evaluations[0].status, "UNCERTAIN")
        self.assertFalse(result.selected_pairs)

    def test_conflicting_exact_entities_groups_are_uncertain(self):
        self.combine(self.second)
        left, right = self.document["temporal_identities"]
        left["provenance"].extend(right["provenance"])
        left["bindings"].extend(right["bindings"])
        self.document["temporal_identities"] = [left]
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.evaluations[0].status, "UNCERTAIN")
        self.assertEqual(result.evaluations[0].reason_codes, (Reason.CONTRADICTORY_PROVENANCE,))

    def test_no_transformed_group_and_no_geometric_fallback(self):
        self.document["groups"][0].pop("transform")
        self.document["groups"].append(group(G2, "entity:geometrically-identical"))
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.evaluations[0].reason_codes, (Reason.NO_ELIGIBLE_GROUP,))
        self.assertEqual(result.abstention, Abstention.ZERO_SUPPORTED)

    def test_already_bound_identity_is_evaluated_and_lineage_audited(self):
        binding = self.bound()
        result = derive(self.document, self.artifacts)
        evaluation = result.evaluations[0]
        self.assertEqual(
            (evaluation.status, evaluation.reason_codes), ("REJECTED", (Reason.ALREADY_BOUND,))
        )
        self.assertEqual(evaluation.existing_binding.binding_id, binding["id"])
        self.assertEqual(evaluation.existing_binding.group_id, G1)
        self.assertEqual(len(result.required_references), 2)

    def test_already_bound_precedes_missing_or_malformed_lineage(self):
        self.bound()
        for provenance in ([], None, [None], [{"evidence_artifact_id": "artifact:missing"}]):
            with self.subTest(provenance=provenance):
                self.document["temporal_identities"][0]["provenance"] = provenance
                result = derive(self.document, self.artifacts)
                self.assertEqual(result.evaluations[0].reason_codes, (Reason.ALREADY_BOUND,))
                self.assertEqual(result.counts.total, 1)

    def test_unbound_identity_resolving_to_bound_group_is_rejected(self):
        other = self.combine(self.repeat, G1)
        self.bound()
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.counts.rejected, 2)
        evaluation = next(e for e in result.evaluations if e.temporal_identity_id == other["id"])
        self.assertEqual(evaluation.reason_codes, (Reason.ALREADY_BOUND,))
        self.assertEqual(result.abstention, Abstention.ZERO_SUPPORTED)

    def test_bound_plus_supported_counts_include_both(self):
        self.bound()
        other = self.combine(self.second)
        result = derive(self.document, self.artifacts)
        self.assertEqual(
            (
                result.counts.total,
                result.counts.supported,
                result.counts.rejected,
                result.counts.selected,
            ),
            (2, 1, 1, 1),
        )
        self.assertEqual(result.selected_pairs[0].temporal_identity_id, other["id"])

    def test_group_contention_abstains_even_with_uncontended_supported_pair(self):
        self.combine(self.repeat, G1)
        self.combine(self.second)
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.abstention, Abstention.GROUP_CONTENTION)
        self.assertFalse(result.selected_pairs)
        self.assertEqual((result.counts.uncertain, result.counts.supported), (2, 1))
        self.assertEqual(
            sum(e.reason_codes == (Reason.GROUP_CONTENTION,) for e in result.evaluations), 2
        )

    def test_zero_identities_and_all_rejected_abstain(self):
        self.document["temporal_identities"] = []
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.counts.total, 0)
        self.assertEqual(result.abstention, Abstention.ZERO_SUPPORTED)
        self.document = copy.deepcopy(self.first[0])
        self.document["entities"] = []
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.counts.rejected, 1)
        self.assertEqual(result.abstention, Abstention.ZERO_SUPPORTED)

    def test_resolver_presence_without_accepted_reference_is_not_authority(self):
        for aid in (self.evidence.artifact_id, self.observation.artifact_id):
            with self.subTest(aid=aid):
                doc = copy.deepcopy(self.document)
                doc["references"] = [r for r in doc["references"] if r["id"] != aid]
                result = derive(doc, self.artifacts)
                self.assertFalse(result.selected_pairs)
                self.assertEqual(
                    result.evaluations[0].reason_codes, (Reason.MISSING_ACCEPTED_REFERENCE,)
                )
                self.assertNotIn(aid, [r["id"] for r in result.required_references])

    def test_wrong_accepted_descriptor_or_unavailable_bytes_fail_closed(self):
        doc = copy.deepcopy(self.document)
        next(r for r in doc["references"] if r["id"] == self.evidence.artifact_id)["media_type"] = (
            "application/json"
        )
        with self.assertRaises(MotionTargetBindingSelectionError):
            derive(doc, self.artifacts)
        with self.assertRaises(MotionTargetBindingSelectionError):
            derive(self.document, ArtifactStore())

    def test_determinism_no_writes_and_returned_closure_is_detached(self):
        class ReadOnly:
            def resolve_reference(inner, ref):
                return self.artifacts.resolve_reference(ref)

        before = copy.deepcopy(self.document)
        first = derive(self.document, ReadOnly())
        second = derive(self.document, ReadOnly())
        self.assertEqual(first, second)
        self.assertEqual(canonical_bytes(asdict(first)), canonical_bytes(asdict(second)))
        first.required_references[0]["import_metadata"]["provenance"].clear()
        self.assertEqual(self.document, before)
        self.assertEqual(derive(self.document, ReadOnly()), second)

    def test_duplicate_transformed_membership_and_bad_groups_fail_closed(self):
        self.document["groups"].append(group(G2, self.document["entities"][0]["id"]))
        with self.assertRaisesRegex(MotionTargetBindingSelectionError, "Multiple"):
            derive(self.document, self.artifacts)
        for field, value in (("kind", "fake"), ("id", "group:bad"), ("transform", {})):
            doc = copy.deepcopy(self.first[0])
            doc["groups"][0][field] = value
            with self.subTest(field=field), self.assertRaises(MotionTargetBindingSelectionError):
                derive(doc, self.artifacts)

    def test_wrong_r0_candidate_or_binding_is_not_a_provenance_path(self):
        for field in ("candidate_id", "inference_id", "promotion_policy_identity"):
            doc = copy.deepcopy(self.document)
            doc["temporal_identities"][0]["provenance"][0][field] = "forged"
            result = derive(doc, self.artifacts)
            self.assertEqual(result.evaluations[0].reason_codes, (Reason.INVALID_PROVENANCE,))
        self.document["temporal_identities"][0]["bindings"] = []
        self.assertFalse(derive(self.document, self.artifacts).selected_pairs)

    def test_exact_component_tuple_no_digest_prefix_or_bounds_match(self):
        for field in ("artifact_id", "candidate_id", "component_digest"):
            doc = copy.deepcopy(self.document)
            doc["entities"][0]["provenance"][field] += "0"
            self.assertFalse(derive(doc, self.artifacts).selected_pairs)

    def test_same_component_promoted_twice_is_not_arbitrarily_chosen(self):
        duplicate = copy.deepcopy(self.document["entities"][0])
        duplicate["id"] += "-duplicate"
        self.document["entities"].append(duplicate)
        self.document["groups"][0]["members"].append(duplicate["id"])
        result = derive(self.document, self.artifacts)
        self.assertEqual(result.evaluations[0].reason_codes, (Reason.CONTRADICTORY_PROVENANCE,))

    def test_svg_rendered_and_ordinary_path_are_indistinguishable_so_both_reject(self):
        from tests.test_svg_geometry_observations import rendered_entity_svg, svg

        for rendered in (True, False):
            document = {
                "references": [],
                "presentation": {"render_stack": []},
                "entities": [{"id": "entity:moving"}],
                "groups": [group(G1, "entity:moving")],
            }
            artifacts = ArtifactStore()
            content = (
                (rendered_entity_svg("1 0 0 1 0 0"), rendered_entity_svg("1 0 0 1 1 0"))
                if rendered
                else (
                    svg("M 20 20 L 60 20 L 48 34 L 28 50 Z", shape_id="entity:moving"),
                    svg("M 21 20 L 61 20 L 49 34 L 29 50 Z", shape_id="entity:moving"),
                )
            )
            sources = [artifacts.import_bytes(c, media_type="image/svg+xml") for c in content]
            proposal = SVGGeometryObservationAdapter().propose(
                request(
                    document,
                    [s.artifact_id for s in sources],
                    {
                        "source_svg_artifact_id": sources[0].artifact_id,
                        "target_svg_artifact_id": sources[1].artifact_id,
                        "source_tick": 0,
                        "target_tick": 12,
                        "shape_id": "entity:moving",
                    },
                ),
                artifacts,
            )
            observation = artifacts.get(proposal.preview_artifacts[0].artifact_id)
            promote_observation(document, artifacts, observation)
            with (
                self.subTest(rendered=rendered),
                patch(
                    "svm.adapters.svg_geometry_observations._extract_polygon",
                    side_effect=AssertionError("No SVG parse"),
                ),
            ):
                result = derive(document, artifacts)
                self.assertEqual(
                    result.evaluations[0].reason_codes, (Reason.UNPROVEN_RENDERED_ORIGIN,)
                )
                self.assertFalse(result.selected_pairs)

    def test_pop_producer_cannot_borrow_shape_id(self):
        from tests.test_pop_geometry_observations import POPGeometryObservationGoldenS41Test

        helper = POPGeometryObservationGoldenS41Test()
        helper.setUp()
        proposal, _, _ = helper.producer()
        observation = helper.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        document = helper.store.get_document(helper.store.head)
        promote_observation(document, helper.artifacts, observation)
        document["entities"] = [{"id": "entity:moving"}]
        document["groups"] = [group(G1, "entity:moving")]
        result = derive(document, helper.artifacts)
        self.assertEqual(result.evaluations[0].reason_codes, (Reason.NO_ALLOWED_PATH,))
        self.assertFalse(result.selected_pairs)


class P2BMotionTargetLineageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from svm import ProposalAcceptor
        from tests.test_primitive_observation_assembly import PrimitiveObservationAssemblyTest

        helper = PrimitiveObservationAssemblyTest()
        helper.setUp()
        proposal = helper.propose()
        ProposalAcceptor().accept(helper.store, proposal, helper.artifacts)
        cls.document = helper.store.get_document(helper.store.head)
        cls.artifacts = helper.artifacts
        cls.observation = cls.artifacts.get(proposal.preview_artifacts[0].artifact_id)
        cls.r0 = promote_observation(cls.document, cls.artifacts, cls.observation)
        cls.p2a_ids = helper.evidence_ids
        cls.expected = set()
        for frame_index, analysis in enumerate(helper.analyses):
            for component_index, component in enumerate(json.loads(analysis.content)["components"]):
                entity = PromotedComponent(
                    analysis.artifact_id,
                    component["candidate_id"],
                    component["component_digest"],
                    tuple(component["bounds"]),
                ).to_entity("p2d-test")
                cls.document["entities"].append(entity)
                gid = "group:" + f"{frame_index * 10 + component_index:064x}"
                cls.document.setdefault("groups", []).append(group(gid, entity["id"]))
                cls.expected.add(
                    (
                        analysis.artifact_id,
                        component["candidate_id"],
                        component["component_digest"],
                        entity["id"],
                    )
                )

    def test_real_p2a_p2b_ids_resolve_exact_evaluations_not_ordinals(self):
        with (
            patch(
                "svm.adapters.primitive_observation_assembly.derive",
                side_effect=AssertionError("No P2B rerun"),
            ),
            patch(
                "svm.adapters.raster_primitive_observation_proposal.derive",
                side_effect=AssertionError("No P2A rerun"),
            ),
        ):
            result = derive(self.document, self.artifacts)
        self.assertEqual(result.counts.total, 2)
        for evaluation in result.evaluations:
            self.assertEqual(len(evaluation.paths), 2)
            # Different analysis artifacts resolve to distinct PromotedComponent Entities;
            # P2D does not silently merge those frame-local Entity identities.
            self.assertEqual(evaluation.reason_codes, (Reason.CONTRADICTORY_PROVENANCE,))
            for path in evaluation.paths:
                self.assertIsNone(path.reason)
                self.assertIn(
                    (
                        path.analysis_artifact_id,
                        path.component_id,
                        path.component_digest,
                        path.entity_id,
                    ),
                    self.expected,
                )
                self.assertIn(path.p2a_evidence_artifact_id, self.p2a_ids)
        self.assertEqual(
            [r["id"] for r in result.required_references],
            [self.r0.artifact_id, self.observation.artifact_id, *self.p2a_ids],
        )

    def test_missing_accepted_p2a_cannot_be_replaced_by_resolver_presence(self):
        document = copy.deepcopy(self.document)
        document["references"] = [r for r in document["references"] if r["id"] != self.p2a_ids[0]]
        result = derive(document, self.artifacts)
        self.assertFalse(result.selected_pairs)
        self.assertTrue(
            all(e.reason_codes == (Reason.MISSING_ACCEPTED_REFERENCE,) for e in result.evaluations)
        )

    def test_observation_digest_prefix_is_not_a_p2a_match(self):
        document = copy.deepcopy(self.document)
        artifacts = copy.deepcopy(self.artifacts)
        payload = json.loads(self.observation.content)
        for frame in payload["frames"]:
            for primitive in frame["primitives"]:
                primitive["observation_id"] += "0"
        observation = artifacts.import_bytes(
            canonical_bytes(payload),
            media_type=self.observation.media_type,
            provenance=self.observation.provenance,
        )
        document["temporal_identities"] = []
        promote_observation(document, artifacts, observation)
        result = derive(document, artifacts)
        self.assertFalse(result.selected_pairs)
        self.assertTrue(
            all(e.reason_codes == (Reason.INVALID_PROVENANCE,) for e in result.evaluations)
        )


if __name__ == "__main__":
    unittest.main()
