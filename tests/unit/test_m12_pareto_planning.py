"""
AcuCalyx Unit Tests: Milestone M11.5 & M12 Planning Refinement & Validation Gate
Governed by ACU-M12-EXEC-PLAN-2026-V2.
"""

import numpy as np
import pytest

from acucalyx.collecting_system.visibility_gate import PCSVisibilityState
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.distance_fields import DistanceField, HazardClearanceResult
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.planning.pareto_optimizer import (
    CandidateTrajectory,
    DiaphragmRelation,
    PlanEvaluationResult,
    PlanStatus,
    PleuralRelation,
    RibClassification,
    extract_pareto_frontier,
    is_dominated,
    optimize_pcnl_access_candidates
)
from acucalyx.planning.scope_model import (
    FLEXIBLE_CYSTONEPHROSCOPE,
    InstrumentProfile,
    STANDARD_RIGID_NEPHROSCOPE
)
from acucalyx.planning.target_candidates import (
    CalyxGroup,
    PapillaryTargetZone,
    generate_papillary_target_zones
)
from acucalyx.regulatory.plan_integrity import (
    CanonicalPlan,
    PlanAuditEvent,
    PlanIntegrityEngine,
    PlanState
)
from acucalyx.validation.challenge_set import (
    CANONICAL_CHALLENGE_REGISTRY,
    ChallengeCategory
)
from acucalyx.validation.expert_annotations import (
    ExpertAccessPlan,
    MultiExpertConsensusPlan,
    compile_multi_expert_consensus,
    evaluate_expert_candidate_coverage
)


# ==============================================================================
# 1. Milestone M11.5: Multi-Expert Consensus & Candidate Coverage Tests
# ==============================================================================

def test_multi_expert_consensus_and_surgical_variance():
    """Verify calculation of concordance, angular spread, and entry dispersion across experts."""
    # Expert 1: Lower pole access, entry at [100, 150, -50]
    p1 = ExpertAccessPlan(
        case_id="CASE_REF_01",
        assessor_id="EXP_URO_01",
        assessor_role="UROLOGIST",
        experience_years=15,
        patient_position_assumed="PRONE",
        target_visibility="DIRECT",
        preferred_calyx_group=CalyxGroup.POSTERIOR_LOWER,
        preferred_puncture_zone="ZONE_POSTERIOR_LOWER",
        target_center_lps_mm=np.array([40.0, 50.0, -40.0]),
        target_normal_vector=np.array([0.5, -0.6, 0.4]),
        planned_skin_entry_lps_mm=np.array([100.0, 150.0, -50.0]),
        acceptable_calyx_groups=[CalyxGroup.POSTERIOR_LOWER, CalyxGroup.POSTERIOR_MIDDLE],
        acceptable_target_region={"radius_mm": 8.0},
        unacceptable_hazards=["colon", "pleura"],
        confidence=0.95,
        rationale="Clear subcostal window into lower pole",
        timestamp="2026-10-01T10:00:00Z"
    )

    # Expert 2: Lower pole access, entry slightly displaced at [104, 152, -48]
    p2 = ExpertAccessPlan(
        case_id="CASE_REF_01",
        assessor_id="EXP_URO_02",
        assessor_role="UROLOGIST",
        experience_years=20,
        patient_position_assumed="PRONE",
        target_visibility="DIRECT",
        preferred_calyx_group=CalyxGroup.POSTERIOR_LOWER,
        preferred_puncture_zone="ZONE_POSTERIOR_LOWER",
        target_center_lps_mm=np.array([41.0, 51.0, -41.0]),
        target_normal_vector=np.array([0.52, -0.58, 0.4]),
        planned_skin_entry_lps_mm=np.array([104.0, 152.0, -48.0]),
        acceptable_calyx_groups=[CalyxGroup.POSTERIOR_LOWER],
        acceptable_target_region={"radius_mm": 10.0},
        unacceptable_hazards=["colon"],
        confidence=0.90,
        rationale="Posterior calyx fornix target",
        timestamp="2026-10-01T10:30:00Z"
    )

    consensus = compile_multi_expert_consensus([p1, p2])

    assert consensus.case_id == "CASE_REF_01"
    assert consensus.inter_rater_concordance == 1.0
    assert consensus.adjudicated_preferred_calyx == CalyxGroup.POSTERIOR_LOWER
    assert consensus.angular_spread_deg >= 0.0
    assert consensus.entry_dispersion_mm > 0.0
    assert "colon" in consensus.unacceptable_hazards
    assert "pleura" in consensus.unacceptable_hazards


def test_expert_candidate_coverage_evaluation():
    """Verify that Candidate Coverage metric evaluates whether Pareto candidates cover expert strategies."""
    expert = ExpertAccessPlan(
        case_id="CASE_COV_01",
        assessor_id="EXP_URO_01",
        assessor_role="UROLOGIST",
        experience_years=12,
        patient_position_assumed="PRONE",
        target_visibility="DIRECT",
        preferred_calyx_group=CalyxGroup.POSTERIOR_LOWER,
        preferred_puncture_zone="ZONE_POSTERIOR_LOWER",
        target_center_lps_mm=np.array([40.0, 50.0, -40.0]),
        target_normal_vector=None,
        planned_skin_entry_lps_mm=np.array([100.0, 150.0, -50.0]),
        acceptable_calyx_groups=[CalyxGroup.POSTERIOR_LOWER],
        acceptable_target_region={},
        unacceptable_hazards=[],
        confidence=0.9,
        rationale="",
        timestamp=""
    )

    # Candidate 1 matches expert target and entry trajectory closely
    cand_matching = CandidateTrajectory(
        candidate_id="CAND_01",
        target_calyx_name=CalyxGroup.POSTERIOR_LOWER.value,
        entry_point_lps=np.array([102.0, 151.0, -49.0]),
        target_point_lps=np.array([40.5, 50.2, -40.1]),
        tract_length_mm=117.0,
        min_effective_clearance_mm=12.0,
        hazard_evaluations=[],
        reachable_stone_fraction=1.0,
        required_scope_deflection_deg=5.0,
        access_rib_classification="SUBCOSTAL",
        is_pareto_optimal=True
    )

    # Candidate 2 targets middle calyx
    cand_different = CandidateTrajectory(
        candidate_id="CAND_02",
        target_calyx_name=CalyxGroup.POSTERIOR_MIDDLE.value,
        entry_point_lps=np.array([110.0, 160.0, 0.0]),
        target_point_lps=np.array([40.0, 50.0, 0.0]),
        tract_length_mm=130.0,
        min_effective_clearance_mm=8.0,
        hazard_evaluations=[],
        reachable_stone_fraction=0.7,
        required_scope_deflection_deg=10.0,
        access_rib_classification="INTERCOSTAL_11_12",
        is_pareto_optimal=True
    )

    res = evaluate_expert_candidate_coverage(
        pareto_candidates=[cand_matching, cand_different],
        expert_plans=[expert]
    )

    assert res.total_expert_strategies == 1
    assert res.covered_expert_strategies == 1
    assert res.coverage_fraction == 1.0
    assert res.per_expert_coverage["EXP_URO_01"] is True


# ==============================================================================
# 2. Target Zone Geometry: Separation of Access Vector vs. Working Axis
# ==============================================================================

def test_papillary_target_zone_separation_of_vectors():
    """Verify that PapillaryTargetZone separates access vector from instrument working axis."""
    zone = PapillaryTargetZone(
        zone_id="ZONE_TEST_LOWER",
        calyx_group=CalyxGroup.POSTERIOR_LOWER,
        centroid_lps_mm=np.array([30.0, 40.0, -50.0]),
        infundibular_axis_unit=np.array([0.0, -1.0, 0.0]), # Points anteriorly towards pelvis
        morphological_radii_mm=np.array([4.0, 4.0, 5.0]),
        visibility_state=PCSVisibilityState.DIRECTLY_OPACIFIED,
        confidence_score=0.9
    )

    # Entry point directly posterior to papilla (skin at [30, 140, -50])
    # Access vector: Skin -> Papilla = [0, -100, 0] / 100 = [0, -1, 0]
    # Perfectly aligned with infundibular axis!
    skin_aligned = np.array([30.0, 140.0, -50.0])
    tract_len, angle_deg, is_feasible = zone.evaluate_access_alignment(
        skin_entry_lps_mm=skin_aligned,
        instrument_max_torque_angle_deg=15.0
    )

    assert pytest.approx(tract_len, 0.1) == 100.0
    assert pytest.approx(angle_deg, 0.1) == 0.0
    assert is_feasible is True

    # Oblique entry point at [100, 140, -50]
    skin_oblique = np.array([100.0, 140.0, -50.0])
    _, angle_oblique, is_feasible_oblique = zone.evaluate_access_alignment(
        skin_entry_lps_mm=skin_oblique,
        instrument_max_torque_angle_deg=20.0
    )
    assert angle_oblique > 25.0
    assert is_feasible_oblique is False


def test_target_generation_supports_anterior_calyces():
    """Verify that target generator produces anterior calyces for individualized planning."""
    zones = generate_papillary_target_zones(
        kidney_center_lps=np.array([0.0, 0.0, 0.0]),
        kidney_radii_lps=np.array([30.0, 20.0, 50.0]),
        pcs_visibility=PCSVisibilityState.HYDRONEPHROTIC_DISTENDED,
        is_malrotated=True
    )

    calyx_groups = [z.calyx_group for z in zones]
    assert CalyxGroup.POSTERIOR_LOWER in calyx_groups
    assert CalyxGroup.POSTERIOR_MIDDLE in calyx_groups
    assert CalyxGroup.ANTERIOR_LOWER in calyx_groups


# ==============================================================================
# 3. Minkowski Geometric Uncertainty Envelope
# ==============================================================================

def test_minkowski_geometric_clearance():
    """Verify Minkowski quadratic uncertainty dilation on synthetic distance field."""
    # 50x50x50 grid with a hazard ball at center [25, 25, 25] with radius 10 mm
    mask = np.zeros((50, 50, 50), dtype=bool)
    Y, X, Z = np.ogrid[:50, :50, :50]
    mask[(X - 25)**2 + (Y - 25)**2 + (Z - 25)**2 <= 100] = True

    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        image_position_patient=[0.0, 0.0, 0.0],
        pixel_spacing=[1.0, 1.0],
        slice_spacing=1.0
    )
    df = DistanceField(binary_mask=mask, spatial_orientation=spatial)

    # Trajectory passing at X = 25, Y = 40 (15 mm from center -> 5 mm from surface)
    traj = LineSegment3D(
        start_point=np.array([25.0, 40.0, 0.0]),
        end_point=np.array([25.0, 40.0, 50.0])
    )

    # Observed clearance is 5.0 mm.
    # With uncertainties U_geom = 2.0, U_seg = 3.0, U_motion = 4.0:
    # Minkowski delta = sqrt(4 + 9 + 16) = sqrt(29) ≈ 5.385 mm
    # C_effective = 5.0 - 5.385 = -0.385 mm (< 0: penetrates conservative envelope!)
    res = df.evaluate_minkowski_clearance(
        trajectory=traj,
        hazard_name="colon",
        uncertainty_geometry=2.0,
        uncertainty_segmentation=3.0,
        uncertainty_motion=4.0
    )

    assert pytest.approx(res.observed_clearance_mm, 0.5) == 5.0
    assert res.effective_clearance_mm < 0.0
    assert res.is_intersecting is True


# ==============================================================================
# 4. Three-Tier Pareto Trajectory Optimizer & Fail-Safe "NO PLAN" State Machine
# ==============================================================================

def test_pareto_optimizer_fail_safe_no_plan_insufficient_evidence():
    """Verify fail-safe state emission when evidence is insufficient."""
    res = optimize_pcnl_access_candidates(
        candidates=[],
        evidence_valid=False
    )
    assert res.status == PlanStatus.NO_PLAN_INSUFFICIENT_EVIDENCE
    assert res.has_viable_plan is False


def test_pareto_optimizer_fail_safe_no_plan_critical_hazard():
    """Verify that when all candidates penetrate conservative hazards, NO_PLAN_CRITICAL_HAZARD is emitted."""
    hazardous_cand = CandidateTrajectory(
        candidate_id="HAZARD_01",
        target_calyx_name="Lower_Posterior",
        entry_point_lps=np.zeros(3),
        target_point_lps=np.zeros(3),
        tract_length_mm=80.0,
        min_effective_clearance_mm=-1.5,  # Violates hazard boundary
        hazard_evaluations=[],
        reachable_stone_fraction=1.0,
        required_scope_deflection_deg=10.0,
        access_rib_classification="SUBCOSTAL"
    )

    res = optimize_pcnl_access_candidates(
        candidates=[hazardous_cand],
        min_clearance_threshold_mm=0.0
    )

    assert res.status == PlanStatus.NO_PLAN_CRITICAL_HAZARD
    assert res.has_viable_plan is False
    assert len(res.rejected_candidates) == 1
    assert "Critical hazard clearance" in res.rejected_candidates[0].hard_constraint_violation_reason


def test_pareto_optimizer_instrument_profile_torque_limit():
    """Verify that candidates exceeding instrument deflection limit fail Tier 1 hard constraints."""
    cand_high_torque = CandidateTrajectory(
        candidate_id="CAND_TORQUE",
        target_calyx_name="Lower_Posterior",
        entry_point_lps=np.zeros(3),
        target_point_lps=np.zeros(3),
        tract_length_mm=80.0,
        min_effective_clearance_mm=10.0,
        hazard_evaluations=[],
        reachable_stone_fraction=1.0,
        required_scope_deflection_deg=25.0, # Exceeds rigid 15° limit
        access_rib_classification="SUBCOSTAL"
    )

    # Standard rigid scope with 15° limit
    res_rigid = optimize_pcnl_access_candidates(
        candidates=[cand_high_torque],
        instrument_profile=STANDARD_RIGID_NEPHROSCOPE
    )
    assert res_rigid.status == PlanStatus.NO_PLAN_CRITICAL_HAZARD
    assert "exceeds instrument limit" in res_rigid.rejected_candidates[0].hard_constraint_violation_reason

    # Flexible scope with 210° deflection capacity -> Succeeds!
    res_flexible = optimize_pcnl_access_candidates(
        candidates=[cand_high_torque],
        instrument_profile=FLEXIBLE_CYSTONEPHROSCOPE
    )
    assert res_flexible.status == PlanStatus.PLAN_AVAILABLE
    assert len(res_flexible.pareto_candidates) == 1


# ==============================================================================
# 5. Plan Superseding & Tamper-Evident Chaining (Interlock U6)
# ==============================================================================

def test_plan_superseding_and_tamper_evident_chain():
    """Verify that modifying a plan marks previous baseline as SUPERSEDED in tamper-evident chain."""
    plan_v1 = CanonicalPlan(
        plan_id="PLAN-v1",
        patient_id="PAT_001",
        laterality="LEFT",
        target_point_lps=(30.0, 40.0, -50.0),
        entry_point_lps=(100.0, 150.0, -50.0),
        carm_bullseye_angles=(15.0, 0.0),
        carm_progression_angles=(0.0, 30.0),
        hazard_clearances_mm={"colon": 15.0},
        maximum_depth_mm=120.0
    )

    sealed_v1 = PlanIntegrityEngine.seal_plan(plan_v1, approved_by="DR_SURGEON")
    assert sealed_v1.status == PlanState.APPROVED

    # Surgeon modifies trajectory: Old plan is superseded rather than deleted/overwritten
    superseded_plan, audit_event = PlanIntegrityEngine.supersede_plan(
        prior_plan=sealed_v1,
        actor_id="DR_SURGEON",
        reason="Clinician shifted skin entry point 5mm medial"
    )

    assert superseded_plan.status == PlanState.SUPERSEDED
    assert audit_event.plan_id == "PLAN-v1"
    assert "SUPERSEDED" in audit_event.action
    assert len(audit_event.event_hash) == 64


# ==============================================================================
# 6. Canonical 12-Cohort PCNL Challenge Registry Completeness
# ==============================================================================

def test_canonical_12_challenge_registry_coverage():
    """Verify that all 12 clinical challenge categories are registered with complete test specifications."""
    all_cases = CANONICAL_CHALLENGE_REGISTRY.all_cases
    assert len(all_cases) >= 12

    registered_categories = set()
    for c in all_cases:
        for cat in c.categories:
            registered_categories.add(cat)

    for cat in ChallengeCategory:
        assert cat in registered_categories, f"ChallengeCategory {cat} missing from registry"
