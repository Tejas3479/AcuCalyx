"""
Unit tests for AcuCalyx Phase 6 / Milestone M4 Usability Engineering & Human Factors.

Tests:
1. IEC 62366-1 Use Specification & Critical Tasks / URRA Traceability (C1-C6, U1-U6).
2. Multimodal 4-factor redundant visual code registry (avoiding color-alone coding).
3. Psychometrics Engine: NASA-TLX RTLX calculation and paired crossover cohort analyzer (Cohen's d, 95% CIs).
4. System Usability Scale (SUS) 10-item engine and exploratory benchmark evaluation (>= 80.0).
5. Interlock U1: Laterality multi-evidence verification gate and wrong-kidney rejection trap.
6. Interlock U2: 5-stage surgical orientation resolution and SE(3) transformation tracking.
7. Interlock U5: Case-derived depth boundary alarms and medial wall counter-puncture prevention.
8. Interlock U4: C-arm closed-loop verbal protocol generator and gantry angle transposition error detector.
9. FastAPI REST Usability Endpoints via TestClient.
"""

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.api.main import app
from acucalyx.fluoroscopy.carm_profile import PHILIPS_ZENITION_70
from acucalyx.fluoroscopy.surgical_pose import SurgicalPatientPosition
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.research.human_factors.psychometrics import (
    NasaTlxRtlxAssessment,
    PsychometricCohortAnalyzer,
    SystemUsabilityScaleAssessment,
)
from acucalyx.research.human_factors.task_analysis import (
    STANDARD_CRITICAL_TASKS,
    STANDARD_URRA_MATRIX,
)
from acucalyx.research.human_factors.use_specification import (
    STANDARD_USE_SPECIFICATION,
    UserRoleCategory,
)
from acucalyx.usability.or_protocol import (
    CarmCommunicationValidator,
    CarmProtocolGenerator,
    TranspositionErrorType,
)
from acucalyx.usability.safety_interlocks import (
    DepthAlarmStatus,
    DepthBoundaryInterlock,
    LateralityVerificationInterlock,
    MULTIMODAL_CODE_REGISTRY,
    MultimodalCorridorStatus,
    StalePlanInterlock,
    SurgicalPositionInterlock,
)

client = TestClient(app)


# ==============================================================================
# 1. Use Specification & Critical Task Analysis
# ==============================================================================

def test_use_specification_completeness():
    spec = STANDARD_USE_SPECIFICATION
    assert "PCNL" in spec.intended_medical_indication
    assert "preoperative" in spec.scope_boundary_definition.lower()
    assert spec.clinician_authority_model is not None
    
    # Check 4 distinct user populations
    assert len(spec.user_populations) == 4
    assert UserRoleCategory.ATTENDING_ENDOUROLOGIST in spec.user_populations
    assert UserRoleCategory.FELLOW_OR_RESIDENT in spec.user_populations
    assert UserRoleCategory.JUNIOR_RESIDENT in spec.user_populations
    assert UserRoleCategory.RADIOLOGIC_TECHNOLOGIST in spec.user_populations


def test_critical_tasks_and_urra_traceability():
    tasks = STANDARD_CRITICAL_TASKS
    assert len(tasks) >= 6
    task_keys = {"C1", "C2", "C3", "C4", "C5", "C6"}
    assert task_keys.issubset(set(tasks.keys()))

    # Check each critical task maps to a defined risk control in URRA matrix
    for t_id, task in tasks.items():
        assert task.associated_risk_control_id in STANDARD_URRA_MATRIX
        control = STANDARD_URRA_MATRIX[task.associated_risk_control_id]
        assert len(control.risk_control_type) > 0
        assert len(control.software_risk_control) > 0


def test_multimodal_visual_code_redundancy():
    """Verify that every trajectory corridor status uses 4 redundant factors: icon + text + outline + color."""
    for status, code in MULTIMODAL_CODE_REGISTRY.items():
        assert code.symbol_icon != ""
        assert code.text_label != ""
        assert code.outline_style in ("solid", "dashed", "dotted", "dashed-hash")
        assert code.primary_color_hex.startswith("#")
        assert len(code.clinical_rationale) > 10


# ==============================================================================
# 2. Psychometrics Engine (NASA-TLX RTLX and SUS)
# ==============================================================================

def test_nasa_tlx_rtlx_calculation():
    # Unweighted Raw TLX is arithmetic mean of 6 subscales
    sub = NasaTlxRtlxAssessment(
        participant_id="P01",
        condition_id="CONVENTIONAL_BASELINE",
        mental_demand=70.0,
        physical_demand=50.0,
        temporal_demand=60.0,
        performance=40.0,
        effort=65.0,
        frustration=55.0
    )
    expected_mean = (70.0 + 50.0 + 60.0 + 40.0 + 65.0 + 55.0) / 6.0
    assert pytest.approx(sub.raw_score, abs=1e-3) == expected_mean


def test_sus_scoring_and_exploratory_benchmark():
    # Perfect score: all odd items 5, all even items 1 -> 100
    perfect_responses = [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]
    sus_perf = SystemUsabilityScaleAssessment(participant_id="P01", item_responses=perfect_responses)
    assert pytest.approx(sus_perf.sus_score, abs=1e-2) == 100.0
    assert sus_perf.adjective_rating == "EXCELLENT"
    assert sus_perf.sus_score >= 80.0

    # Poor score: all odd items 1, all even items 5 -> 0
    poor_responses = [1, 5, 1, 5, 1, 5, 1, 5, 1, 5]
    sus_poor = SystemUsabilityScaleAssessment(participant_id="P02", item_responses=poor_responses)
    assert pytest.approx(sus_poor.sus_score, abs=1e-2) == 0.0
    assert sus_poor.adjective_rating == "UNACCEPTABLE"
    assert (sus_poor.sus_score >= 80.0) is False


def test_psychometric_paired_crossover_cohort_analysis():
    # Synthetic 5-participant paired cohort
    baseline = [
        NasaTlxRtlxAssessment("P1", "BASE", 75, 60, 70, 50, 70, 65),
        NasaTlxRtlxAssessment("P2", "BASE", 80, 65, 75, 45, 75, 70),
        NasaTlxRtlxAssessment("P3", "BASE", 70, 55, 65, 55, 65, 60),
        NasaTlxRtlxAssessment("P4", "BASE", 85, 70, 80, 40, 80, 75),
        NasaTlxRtlxAssessment("P5", "BASE", 72, 58, 68, 52, 68, 62),
    ]
    acuc = [
        NasaTlxRtlxAssessment("P1", "ACUC", 40, 35, 30, 80, 40, 25),
        NasaTlxRtlxAssessment("P2", "ACUC", 45, 40, 35, 75, 45, 30),
        NasaTlxRtlxAssessment("P3", "ACUC", 38, 30, 28, 85, 35, 20),
        NasaTlxRtlxAssessment("P4", "ACUC", 50, 45, 40, 70, 50, 35),
        NasaTlxRtlxAssessment("P5", "ACUC", 42, 36, 32, 82, 42, 28),
    ]

    result = PsychometricCohortAnalyzer.analyze_paired_workload(baseline, acuc)
    assert result.sample_size_n == 5
    assert result.mean_baseline_rtlx > result.mean_acucalyx_rtlx
    assert result.mean_paired_difference < -15.0
    assert result.cohens_d_effect_size < -1.0  # Large reduction effect size
    assert result.p_value_paired_t < 0.01
    assert result.is_workload_reduction_significant is True
    assert result.ci95_difference[1] < 0.0


# ==============================================================================
# 3. Clinical Runtime Safety Interlocks
# ==============================================================================

def test_interlock_u1_laterality_verification():
    # 1. Matching laterality with confirmed landmarks passes
    res_pass = LateralityVerificationInterlock.verify_laterality(
        case_id="C_LAT_01",
        clinician_selected_side="LEFT",
        ct_metadata_side="LEFT",
        landmark_checks={"spleen_left_quadrant": True, "liver_right_quadrant": True},
        is_two_step_confirmed=True
    )
    assert res_pass.is_laterality_verified is True
    assert res_pass.confirmed_side == "LEFT"

    # 2. Mismatched laterality (e.g. wrong-side selection) is trapped and rejected
    res_mismatch = LateralityVerificationInterlock.verify_laterality(
        case_id="C_LAT_02",
        clinician_selected_side="RIGHT",
        ct_metadata_side="LEFT",
        landmark_checks={"spleen_left_quadrant": True, "liver_right_quadrant": True},
        is_two_step_confirmed=True
    )
    assert res_mismatch.is_laterality_verified is False
    assert "SAFETY INTERLOCK TRIPPED" in res_mismatch.error_message

    # 3. Missing two-step clinician confirmation fails-closed
    res_unconfirmed = LateralityVerificationInterlock.verify_laterality(
        case_id="C_LAT_03",
        clinician_selected_side="LEFT",
        ct_metadata_side="LEFT",
        landmark_checks={"spleen_left_quadrant": True, "liver_right_quadrant": True},
        is_two_step_confirmed=False
    )
    assert res_unconfirmed.is_laterality_verified is False


def test_interlock_u2_surgical_position_transform():
    # 1. Confirmed Prone Standard pose resolves valid 4x4 SE(3) matrix
    ok, t_mat, msg = SurgicalPositionInterlock.resolve_surgical_pose(
        ct_acquisition_position="HFS",
        planned_operative_position=SurgicalPatientPosition.PRONE_STANDARD,
        is_clinician_confirmed=True
    )
    assert ok is True
    assert t_mat.shape == (4, 4)
    # Pure rotation matrix determinant must be +1
    rot = t_mat[:3, :3]
    assert pytest.approx(np.linalg.det(rot), abs=1e-4) == 1.0

    # 2. Unconfirmed pose is trapped
    ok_fail, _, msg_fail = SurgicalPositionInterlock.resolve_surgical_pose(
        ct_acquisition_position="HFS",
        planned_operative_position=SurgicalPatientPosition.PRONE_STANDARD,
        is_clinician_confirmed=False
    )
    assert ok_fail is False
    assert "confirmed" in msg_fail.lower()


def test_interlock_u5_depth_boundary_and_counter_puncture_alarms():
    interlock = DepthBoundaryInterlock(
        planned_depth_mm=100.0,
        calyx_luminal_depth_mm=8.0,
        metrology_uncertainty_u95_mm=1.64
    )

    # State A: Normal advancement through flank tissue (depth 80 mm)
    st_a, tel_a = interlock.evaluate_penetration(80.0)
    assert st_a == DepthAlarmStatus.NORMAL
    assert tel_a["distance_to_medial_wall_mm"] == 28.0
    assert tel_a["audio_stop_trigger"] is False

    # State B: Target papilla zone engagement (depth 97 mm, >= 96 mm)
    st_b, tel_b = interlock.evaluate_penetration(97.0)
    assert st_b == DepthAlarmStatus.TARGET_PAPILLA_ZONE
    assert tel_b["visual_alarm"] == "EMERALD_ZONE"

    # State C: Luminal access zone (depth 101 mm)
    st_c, tel_c = interlock.evaluate_penetration(101.0)
    assert st_c == DepthAlarmStatus.LUMINAL_ACCESS
    assert tel_c["visual_alarm"] == "CYAN_TARGET"

    # State D: Medial wall warning (depth 106.1 mm, dist_to_medial 1.9 mm <= 2.0 mm, before critical stop 106.36)
    st_d, tel_d = interlock.evaluate_penetration(106.1)
    assert st_d == DepthAlarmStatus.MEDIAL_WALL_WARNING
    assert tel_d["visual_alarm"] == "AMBER_WARNING"

    # State E: Counter-puncture critical stop (depth 107.0 mm >= critical_stop_depth 106.36 mm)
    st_e, tel_e = interlock.evaluate_penetration(107.0)
    assert st_e == DepthAlarmStatus.COUNTER_PUNCTURE_CRITICAL_STOP
    assert tel_e["visual_alarm"] == "FLASHING_RED_STOP"
    assert tel_e["audio_stop_trigger"] is True


def test_interlock_u6_stale_plan_invalidation():
    # Active plan with no modifications is valid
    assert StalePlanInterlock.is_plan_valid(is_stale=False) is True
    # Once manual override is applied or geometry changed, plan is invalidated
    assert StalePlanInterlock.is_plan_valid(is_stale=True) is False


# ==============================================================================
# 4. C-Arm Communication Protocol & Transposition Error Detector
# ==============================================================================

def test_carm_protocol_generation_and_verbal_script():
    traj = LineSegment3D(
        start_point=np.array([30.0, -90.0, 40.0]),
        end_point=np.array([25.0, 10.0, 45.0])
    )
    card = CarmProtocolGenerator.generate_card(
        case_id="CASE_PROTOCOL_01",
        target_calyx_name="lower_pole_posterior",
        planned_trajectory=traj,
        carm_profile=PHILIPS_ZENITION_70
    )
    assert card.case_id == "CASE_PROTOCOL_01"
    assert card.recommended_pulse_rate_pps == 8
    # Check 4-step closed loop script fields
    assert "Surgeon" in card.bullseye_verbal_script.step_1_directive
    assert "Technician" in card.bullseye_verbal_script.step_2_readback
    assert "Confirmed" in card.bullseye_verbal_script.step_3_confirmation
    assert "locked" in card.bullseye_verbal_script.step_4_verification


def test_carm_transposition_error_detection():
    # Intended: Primary +20.0 (RAO 20), Secondary -10.0 (CAUD 10)
    # 1. Exact match within tolerance
    res_ok = CarmCommunicationValidator.evaluate_technician_entry(
        intended_primary_deg=20.0, intended_secondary_deg=-10.0,
        entered_primary_deg=20.5, entered_secondary_deg=-10.2,
        tolerance_deg=1.0
    )
    assert res_ok.is_correct is True
    assert res_ok.transposition_error_type == TranspositionErrorType.NONE

    # 2. Primary axis transposition (RAO entered as LAO, -20.0)
    res_lao_rao = CarmCommunicationValidator.evaluate_technician_entry(
        intended_primary_deg=20.0, intended_secondary_deg=-10.0,
        entered_primary_deg=-20.0, entered_secondary_deg=-10.0,
        tolerance_deg=1.0
    )
    assert res_lao_rao.is_correct is False
    assert res_lao_rao.transposition_error_type == TranspositionErrorType.PRIMARY_ORBITAL_SIGN_INVERSION

    # 3. Secondary axis transposition (CAUD entered as CRAN, +10.0)
    res_cran_caud = CarmCommunicationValidator.evaluate_technician_entry(
        intended_primary_deg=20.0, intended_secondary_deg=-10.0,
        entered_primary_deg=20.0, entered_secondary_deg=10.0,
        tolerance_deg=1.0
    )
    assert res_cran_caud.is_correct is False
    assert res_cran_caud.transposition_error_type == TranspositionErrorType.SECONDARY_ANGULATION_SIGN_INVERSION

    # 4. Axes swapped (Primary entered in Secondary, Secondary entered in Primary)
    res_swapped = CarmCommunicationValidator.evaluate_technician_entry(
        intended_primary_deg=20.0, intended_secondary_deg=-10.0,
        entered_primary_deg=-10.0, entered_secondary_deg=20.0,
        tolerance_deg=1.0
    )
    assert res_swapped.is_correct is False
    assert res_swapped.transposition_error_type == TranspositionErrorType.PRIMARY_SECONDARY_AXES_SWAPPED


# ==============================================================================
# 5. FastAPI Usability REST API Endpoints
# ==============================================================================

def test_api_usability_specification_endpoints():
    res = client.get("/api/usability/specification")
    assert res.status_code == 200
    data = res.json()
    assert "user_populations" in data
    assert len(data["user_populations"]) == 4

    tasks_res = client.get("/api/usability/critical-tasks")
    assert tasks_res.status_code == 200
    t_data = tasks_res.json()
    assert "critical_tasks" in t_data
    assert "C1" in t_data["critical_tasks"]
    assert "urra_matrix" in t_data
    assert "multimodal_visual_codes" in t_data


def test_api_usability_runtime_interlock_endpoints():
    # 1. Laterality confirm pass
    lat_res = client.post(
        "/api/usability/cases/CASE_API_01/laterality-confirm",
        json={
            "clinician_selected_side": "LEFT",
            "ct_metadata_side": "LEFT",
            "landmark_checks": {"liver_right": True},
            "is_two_step_confirmed": True
        }
    )
    assert lat_res.status_code == 200
    assert lat_res.json()["verified"] is True

    # Laterality conflict fail
    lat_fail = client.post(
        "/api/usability/cases/CASE_API_01/laterality-confirm",
        json={
            "clinician_selected_side": "RIGHT",
            "ct_metadata_side": "LEFT",
            "landmark_checks": {},
            "is_two_step_confirmed": True
        }
    )
    assert lat_fail.status_code == 400

    # 2. Position confirm
    pos_res = client.post(
        "/api/usability/cases/CASE_API_01/position-confirm",
        json={
            "ct_acquisition_position": "HFS",
            "planned_operative_position": "PRONE_STANDARD",
            "is_clinician_confirmed": True
        }
    )
    assert pos_res.status_code == 200
    assert pos_res.json()["confirmed"] is True

    # 3. Depth check
    depth_res = client.post(
        "/api/usability/cases/CASE_API_01/depth-check",
        json={
            "planned_depth_mm": 90.0,
            "current_penetration_mm": 88.0,
            "calyx_luminal_depth_mm": 8.0,
            "metrology_uncertainty_u95_mm": 1.64
        }
    )
    assert depth_res.status_code == 200
    assert depth_res.json()["telemetry"]["status"] == "TARGET_PAPILLA_ZONE"

    # 4. Verbal communication card
    card_res = client.get("/api/usability/cases/CASE_API_01/verbal-card?carm_model=philips_zenition_70")
    assert card_res.status_code == 200
    card_data = card_res.json()
    assert "bullseye_verbal_script" in card_data

    # 5. C-arm entry transposition validate
    val_res = client.post(
        "/api/usability/carm-entry-validate",
        json={
            "intended_primary_deg": 25.0,
            "intended_secondary_deg": -15.0,
            "entered_primary_deg": -25.0,
            "entered_secondary_deg": -15.0,
            "tolerance_deg": 1.0
        }
    )
    assert val_res.status_code == 200
    assert val_res.json()["is_correct"] is False
    assert val_res.json()["transposition_error_type"] == "PRIMARY_ORBITAL_SIGN_INVERSION"


def test_api_usability_psychometric_analytics():
    # 1. Paired workload cohort endpoint
    workload_res = client.post(
        "/api/usability/psychometrics/workload-cohort",
        json={
            "baseline_cohort": [
                {"participant_id": "P1", "condition_id": "BASE", "mental_demand": 80, "physical_demand": 60, "temporal_demand": 70, "performance": 40, "effort": 75, "frustration": 70},
                {"participant_id": "P2", "condition_id": "BASE", "mental_demand": 75, "physical_demand": 65, "temporal_demand": 75, "performance": 45, "effort": 70, "frustration": 65},
            ],
            "acucalyx_cohort": [
                {"participant_id": "P1", "condition_id": "ACUC", "mental_demand": 40, "physical_demand": 35, "temporal_demand": 30, "performance": 80, "effort": 40, "frustration": 25},
                {"participant_id": "P2", "condition_id": "ACUC", "mental_demand": 45, "physical_demand": 40, "temporal_demand": 35, "performance": 75, "effort": 45, "frustration": 30},
            ]
        }
    )
    assert workload_res.status_code == 200
    wl_data = workload_res.json()
    assert wl_data["sample_size_n"] == 2
    assert wl_data["mean_paired_difference"] < 0.0
    assert wl_data["is_workload_reduction_significant"] is True

    # 2. SUS cohort endpoint
    sus_res = client.post(
        "/api/usability/psychometrics/sus-cohort",
        json={
            "submissions": [
                {"participant_id": "P1", "item_responses": [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]},
                {"participant_id": "P2", "item_responses": [4, 2, 4, 2, 4, 2, 4, 2, 4, 2]}
            ]
        }
    )
    assert sus_res.status_code == 200
    sus_data = sus_res.json()
    assert sus_data["sample_size_n"] == 2
    assert sus_data["mean_sus"] >= 75.0
