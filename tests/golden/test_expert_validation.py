"""
AcuCalyx Golden Clinical Tests: Multi-Expert Consensus & Benchmark Evaluation

Implements Step 3.08 of Phase 3 (M2 Milestone):
Evaluates AcuCalyx trajectory candidates against multi-expert clinical consensus
using the Five-Tier Real-Data Validation Harness.
"""

import numpy as np
import pytest

from acucalyx.planning.pareto_optimizer import CandidateTrajectory
from acucalyx.planning.target_candidates import CalyxGroup
from acucalyx.validation.challenge_set import CANONICAL_CHALLENGE_REGISTRY, ChallengeCategory
from acucalyx.validation.expert_annotations import (
    ExpertAccessPlan,
    compile_multi_expert_consensus,
)
from acucalyx.validation.harness import evaluate_clinical_case


def test_multi_expert_consensus_aggregation():
    """Verifies synthesis of independent expert access plans into an adjudicated consensus."""
    plan_uro_1 = ExpertAccessPlan(
        case_id="GOLDEN_CASE_EXP_01",
        assessor_id="EXP_URO_01",
        assessor_role="UROLOGIST",
        experience_years=15,
        patient_position_assumed="PRONE",
        target_visibility="DIRECT",
        preferred_calyx_group=CalyxGroup.POSTERIOR_LOWER,
        preferred_puncture_zone="ZONE_LOWER_INFUNDIBULUM",
        target_center_lps_mm=np.array([25.0, 10.0, 30.0]),
        target_normal_vector=np.array([0.0, -1.0, 0.0]),
        planned_skin_entry_lps_mm=np.array([25.0, 70.0, 30.0]),
        acceptable_calyx_groups=[CalyxGroup.POSTERIOR_LOWER, CalyxGroup.POSTERIOR_MIDDLE],
        acceptable_target_region={"radius_mm": 6.0},
        unacceptable_hazards=["COLON", "PLEURA"],
        confidence=0.95,
        rationale="Clear subcostal straight tract directly into stone-bearing lower pole papilla.",
        timestamp="2026-09-30T10:00:00Z"
    )

    plan_uro_2 = ExpertAccessPlan(
        case_id="GOLDEN_CASE_EXP_01",
        assessor_id="EXP_URO_02",
        assessor_role="UROLOGIST",
        experience_years=8,
        patient_position_assumed="PRONE",
        target_visibility="DIRECT",
        preferred_calyx_group=CalyxGroup.POSTERIOR_LOWER,
        preferred_puncture_zone="ZONE_LOWER_INFUNDIBULUM",
        target_center_lps_mm=np.array([26.0, 11.0, 31.0]),
        target_normal_vector=np.array([0.0, -1.0, 0.0]),
        planned_skin_entry_lps_mm=np.array([27.0, 72.0, 31.0]),
        acceptable_calyx_groups=[CalyxGroup.POSTERIOR_LOWER],
        acceptable_target_region={"radius_mm": 5.0},
        unacceptable_hazards=["COLON", "SPLEEN"],
        confidence=0.90,
        rationale="Posterior lower calyx offers direct optical access to renal pelvis.",
        timestamp="2026-09-30T10:15:00Z"
    )

    consensus = compile_multi_expert_consensus([plan_uro_1, plan_uro_2])
    assert consensus.inter_rater_concordance == 1.0  # 100% agreement on POSTERIOR_LOWER
    assert consensus.adjudicated_preferred_calyx == CalyxGroup.POSTERIOR_LOWER
    assert "COLON" in consensus.unacceptable_hazards
    assert "PLEURA" in consensus.unacceptable_hazards
    assert "SPLEEN" in consensus.unacceptable_hazards


def test_validation_harness_concordant_case():
    """Verifies that an algorithmic candidate matching expert consensus achieves PLANNING_ELIGIBLE."""
    plan_uro = ExpertAccessPlan(
        case_id="CASE_VAL_01",
        assessor_id="EXP_URO_01",
        assessor_role="UROLOGIST",
        experience_years=12,
        patient_position_assumed="PRONE",
        target_visibility="DIRECT",
        preferred_calyx_group=CalyxGroup.POSTERIOR_LOWER,
        preferred_puncture_zone="ZONE_LOWER",
        target_center_lps_mm=np.array([20.0, 10.0, 30.0]),
        target_normal_vector=np.array([0.0, -1.0, 0.0]),
        planned_skin_entry_lps_mm=np.array([20.0, 65.0, 30.0]),
        acceptable_calyx_groups=[CalyxGroup.POSTERIOR_LOWER],
        acceptable_target_region={"radius_mm": 5.0},
        unacceptable_hazards=["COLON"],
        confidence=0.9,
        rationale="Ideal subcostal puncture.",
        timestamp="2026-09-30T11:00:00Z"
    )
    consensus = compile_multi_expert_consensus([plan_uro])

    # Algorithmic candidate matching consensus
    candidate = CandidateTrajectory(
        candidate_id="CAND_OPTIMAL",
        target_calyx_name="POSTERIOR_LOWER",
        entry_point_lps=np.array([21.0, 66.0, 30.0]), # ~1.4 mm entry deviation
        target_point_lps=np.array([20.5, 10.5, 30.0]), # ~0.7 mm target deviation
        tract_length_mm=55.5,
        min_effective_clearance_mm=18.0,               # Safe clearance
        hazard_evaluations=[],
        reachable_stone_fraction=1.0,
        required_scope_deflection_deg=0.0,
        access_rib_classification="SUBCOSTAL",
        is_pareto_optimal=True,
        confidence_tier="HIGH"
    )

    pred_masks = {"kidney": np.ones((10, 10, 10), dtype=bool)}
    ref_masks = {"kidney": np.ones((10, 10, 10), dtype=bool)}

    report = evaluate_clinical_case(
        case_id="CASE_VAL_01",
        predicted_masks=pred_masks,
        reference_masks=ref_masks,
        spacing_mm=(1.0, 1.0, 1.0),
        pareto_candidates=[candidate],
        consensus_plan=consensus,
        vendor="Siemens",
        phase="NCCT"
    )

    assert report.expert_calyx_concordance is True
    assert report.hazard_false_negative is False
    assert report.critical_hazard_breaches_observed == 0
    assert report.eligibility_status == "PLANNING_ELIGIBLE"
    assert report.skin_entry_error_mm < 5.0


def test_validation_harness_catches_hazard_breach():
    """Verifies that any algorithmic candidate breaching hazard clearance is flagged REJECTED."""
    plan_uro = ExpertAccessPlan(
        case_id="CASE_VAL_02",
        assessor_id="EXP_URO_01",
        assessor_role="UROLOGIST",
        experience_years=10,
        patient_position_assumed="PRONE",
        target_visibility="DIRECT",
        preferred_calyx_group=CalyxGroup.POSTERIOR_LOWER,
        preferred_puncture_zone="ZONE_LOWER",
        target_center_lps_mm=np.array([20.0, 10.0, 30.0]),
        target_normal_vector=np.array([0.0, -1.0, 0.0]),
        planned_skin_entry_lps_mm=np.array([20.0, 65.0, 30.0]),
        acceptable_calyx_groups=[CalyxGroup.POSTERIOR_LOWER],
        acceptable_target_region={},
        unacceptable_hazards=["COLON"],
        confidence=0.85,
        rationale="",
        timestamp=""
    )
    consensus = compile_multi_expert_consensus([plan_uro])

    # Unsafe candidate with zero clearance (breach)
    unsafe_candidate = CandidateTrajectory(
        candidate_id="CAND_BREACH",
        target_calyx_name="POSTERIOR_LOWER",
        entry_point_lps=np.array([20.0, 65.0, 30.0]),
        target_point_lps=np.array([20.0, 10.0, 30.0]),
        tract_length_mm=55.0,
        min_effective_clearance_mm=-2.0,  # Negative clearance = collision!
        hazard_evaluations=[],
        reachable_stone_fraction=1.0,
        required_scope_deflection_deg=0.0,
        access_rib_classification="SUBCOSTAL",
        is_pareto_optimal=True,
        confidence_tier="HIGH"
    )

    report = evaluate_clinical_case(
        case_id="CASE_VAL_02",
        predicted_masks={},
        reference_masks={},
        spacing_mm=(1.0, 1.0, 1.0),
        pareto_candidates=[unsafe_candidate],
        consensus_plan=consensus
    )

    assert report.critical_hazard_breaches_observed >= 1
    assert report.hazard_false_negative is True
    assert report.eligibility_status == "REJECTED_HAZARD_BREACH"


def test_challenge_case_registry_retrieval():
    """Verifies retrieval of dedicated PCNL challenge cases by category and vendor."""
    retrorenal_cases = CANONICAL_CHALLENGE_REGISTRY.get_cases_by_category(ChallengeCategory.RETRORENAL_COLON)
    assert len(retrorenal_cases) >= 1
    assert retrorenal_cases[0].case_id == "CHALLENGE_01_RETRORENAL"

    siemens_cases = CANONICAL_CHALLENGE_REGISTRY.get_cases_by_vendor("Siemens")
    assert any(c.case_id == "CHALLENGE_01_RETRORENAL" for c in siemens_cases)
