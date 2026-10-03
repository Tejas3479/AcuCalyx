"""
AcuCalyx API: Usability Engineering & Human Factors Evaluation Routes (Phase 6 / M4)

Provides REST endpoints for:
- IEC 62366-1 Use Specification and Critical Task / URRA Traceability retrieval
- Runtime Safety Interlocks: Laterality Verification (U1), Position Confirmation (U2), Depth Alarms (U5)
- C-Arm Technologist Communication Card with Verbal Readback Protocol (U4)
- Automated C-Arm Angle Transposition Error Detection
- Psychometric Cognitive Workload (NASA-TLX RTLX) and System Usability Scale (SUS) Cohort Analytics
"""

from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import numpy as np

from acucalyx.fluoroscopy.carm_profile import PHILIPS_ZENITION_70, get_carm_profile
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
from acucalyx.research.human_factors.use_specification import STANDARD_USE_SPECIFICATION
from acucalyx.usability.or_protocol import (
    CarmCommunicationValidator,
    CarmProtocolGenerator,
)
from acucalyx.usability.safety_interlocks import (
    DepthBoundaryInterlock,
    LateralityVerificationInterlock,
    MULTIMODAL_CODE_REGISTRY,
    MultimodalCorridorStatus,
    SurgicalPositionInterlock,
)

router = APIRouter(prefix="/api/usability", tags=["human_factors_and_usability"])


# Pydantic Request Models
class LateralityConfirmRequest(BaseModel):
    clinician_selected_side: str  # 'LEFT' or 'RIGHT'
    ct_metadata_side: str
    landmark_checks: Dict[str, bool] = Field(default_factory=dict)
    is_two_step_confirmed: bool = True


class PositionConfirmRequest(BaseModel):
    ct_acquisition_position: str = "HFS"
    planned_operative_position: SurgicalPatientPosition = SurgicalPatientPosition.PRONE_STANDARD
    is_clinician_confirmed: bool = True


class DepthCheckRequest(BaseModel):
    planned_depth_mm: float
    current_penetration_mm: float
    calyx_luminal_depth_mm: float = 8.0
    metrology_uncertainty_u95_mm: float = 1.64


class CarmAngleEntryValidationRequest(BaseModel):
    intended_primary_deg: float
    intended_secondary_deg: float
    entered_primary_deg: float
    entered_secondary_deg: float
    tolerance_deg: float = 1.0


class NasaTlxItem(BaseModel):
    participant_id: str
    condition_id: str  # 'CONVENTIONAL_BASELINE' or 'ACUCALYX_COCKPIT'
    mental_demand: float = Field(..., ge=0.0, le=100.0)
    physical_demand: float = Field(..., ge=0.0, le=100.0)
    temporal_demand: float = Field(..., ge=0.0, le=100.0)
    performance: float = Field(..., ge=0.0, le=100.0)
    effort: float = Field(..., ge=0.0, le=100.0)
    frustration: float = Field(..., ge=0.0, le=100.0)


class PairedWorkloadRequest(BaseModel):
    baseline_cohort: List[NasaTlxItem]
    acucalyx_cohort: List[NasaTlxItem]


class SUSSubmissionItem(BaseModel):
    participant_id: str
    item_responses: List[int] = Field(..., min_length=10, max_length=10)


class SUSCohortRequest(BaseModel):
    submissions: List[SUSSubmissionItem]


# Endpoints
@router.get("/specification")
def get_use_specification():
    """Returns the formal IEC 62366-1 Use Specification and user population profiles."""
    spec = STANDARD_USE_SPECIFICATION
    users = {
        k: {
            "role": v.role_name,
            "education": v.education_level,
            "experience": v.pcnl_experience_level,
            "responsibilities": v.key_responsibilities
        }
        for k, v in spec.user_populations.items()
    }
    return {
        "intended_medical_indication": spec.intended_medical_indication,
        "scope_boundary_definition": spec.scope_boundary_definition,
        "clinician_authority_model": spec.clinician_authority_model,
        "user_populations": users
    }


@router.get("/critical-tasks")
def get_critical_tasks_and_urra():
    """Returns safety-critical tasks C1-C6 and URRA risk control mappings U1-U6."""
    tasks = {
        k: {
            "task_id": v.task_id,
            "name": v.task_name,
            "severity": v.hazard_severity,
            "foreseeable_error": v.foreseeable_user_error,
            "clinical_harm": v.clinical_harm,
            "risk_control_id": v.associated_risk_control_id
        }
        for k, v in STANDARD_CRITICAL_TASKS.items()
    }
    urra = {
        k: {
            "interlock_id": v.interlock_id,
            "error_mechanism": v.error_mechanism,
            "risk_control": v.software_risk_control,
            "type": v.risk_control_type,
            "verification": v.verification_method
        }
        for k, v in STANDARD_URRA_MATRIX.items()
    }
    codes = {
        k.value: {
            "symbol": v.symbol_icon,
            "label": v.text_label,
            "outline": v.outline_style,
            "color": v.primary_color_hex,
            "rationale": v.clinical_rationale
        }
        for k, v in MULTIMODAL_CODE_REGISTRY.items()
    }
    return {
        "critical_tasks": tasks,
        "urra_matrix": urra,
        "multimodal_visual_codes": codes
    }


@router.post("/cases/{case_id}/laterality-confirm")
def confirm_laterality(case_id: str, request: LateralityConfirmRequest):
    """Interlock U1: Enforces multi-evidence laterality confirmation and blocks wrong-kidney planning."""
    result = LateralityVerificationInterlock.verify_laterality(
        case_id=case_id,
        clinician_selected_side=request.clinician_selected_side,
        ct_metadata_side=request.ct_metadata_side,
        landmark_checks=request.landmark_checks,
        is_two_step_confirmed=request.is_two_step_confirmed
    )
    if not result.is_laterality_verified:
        raise HTTPException(status_code=400, detail=result.error_message)
    return {
        "case_id": case_id,
        "verified": True,
        "confirmed_side": result.confirmed_side,
        "ct_metadata_side": result.ct_metadata_side
    }


@router.post("/cases/{case_id}/position-confirm")
def confirm_surgical_position(case_id: str, request: PositionConfirmRequest):
    """Interlock U2: Manages 5-stage surgical orientation and SE(3) transformation tracking."""
    ok, t_mat, msg = SurgicalPositionInterlock.resolve_surgical_pose(
        ct_acquisition_position=request.ct_acquisition_position,
        planned_operative_position=request.planned_operative_position,
        is_clinician_confirmed=request.is_clinician_confirmed
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "case_id": case_id,
        "confirmed": True,
        "operative_position": request.planned_operative_position.value,
        "message": msg,
        "transformation_matrix_4x4": t_mat.tolist() if t_mat is not None else None
    }


@router.post("/cases/{case_id}/depth-check")
def check_needle_depth(case_id: str, request: DepthCheckRequest):
    """Interlock U5: Enforces case-derived depth boundary and medial wall alarms."""
    interlock = DepthBoundaryInterlock(
        planned_depth_mm=request.planned_depth_mm,
        calyx_luminal_depth_mm=request.calyx_luminal_depth_mm,
        metrology_uncertainty_u95_mm=request.metrology_uncertainty_u95_mm
    )
    status, telemetry = interlock.evaluate_penetration(request.current_penetration_mm)
    return {
        "case_id": case_id,
        "telemetry": telemetry
    }


@router.get("/cases/{case_id}/verbal-card")
def get_verbal_communication_card(
    case_id: str,
    carm_model: str = Query("philips_zenition_70", description="C-arm hardware profile key")
):
    """Interlock U4: Generates standardized technician communication card and verbal readback scripts."""
    profile = get_carm_profile(carm_model)
    traj = LineSegment3D(
        start_point=np.array([25.0, -80.0, 35.0]),
        end_point=np.array([22.0, 15.0, 40.0])
    )
    card = CarmProtocolGenerator.generate_card(
        case_id=case_id,
        target_calyx_name="lower_pole_posterior",
        planned_trajectory=traj,
        carm_profile=profile
    )
    return {
        "case_id": card.case_id,
        "target_calyx": card.target_calyx_name,
        "carm_model": card.carm_model,
        "bullseye_angles": {
            "primary_deg": card.bullseye_primary_angle_deg,
            "secondary_deg": card.bullseye_secondary_angle_deg
        },
        "depth_angles": {
            "primary_deg": card.depth_primary_angle_deg,
            "secondary_deg": card.depth_secondary_angle_deg
        },
        "recommended_pulse_rate_pps": card.recommended_pulse_rate_pps,
        "collimation_size_cm": list(card.collimation_size_cm),
        "bullseye_verbal_script": {
            "directive": card.bullseye_verbal_script.step_1_directive,
            "readback": card.bullseye_verbal_script.step_2_readback,
            "confirmation": card.bullseye_verbal_script.step_3_confirmation,
            "verification": card.bullseye_verbal_script.step_4_verification
        },
        "depth_verbal_script": {
            "directive": card.depth_verbal_script.step_1_directive,
            "readback": card.depth_verbal_script.step_2_readback,
            "confirmation": card.depth_verbal_script.step_3_confirmation,
            "verification": card.depth_verbal_script.step_4_verification
        },
        "tube_direction_hint": card.gantry_physical_tube_direction_hint
    }


@router.post("/carm-entry-validate")
def validate_carm_technician_entry(request: CarmAngleEntryValidationRequest):
    """Detects gantry angle transposition errors (LAO/RAO or CRAN/CAUD swap)."""
    res = CarmCommunicationValidator.evaluate_technician_entry(
        intended_primary_deg=request.intended_primary_deg,
        intended_secondary_deg=request.intended_secondary_deg,
        entered_primary_deg=request.entered_primary_deg,
        entered_secondary_deg=request.entered_secondary_deg,
        tolerance_deg=request.tolerance_deg
    )
    return {
        "is_correct": res.is_correct,
        "transposition_error_type": res.transposition_error_type.value,
        "primary_error_deg": res.primary_error_deg,
        "secondary_error_deg": res.secondary_error_deg,
        "total_angular_error_deg": res.total_angular_error_deg,
        "error_description": res.error_description
    }


@router.post("/psychometrics/workload-cohort")
def analyze_workload_cohort(request: PairedWorkloadRequest):
    """Conducts paired statistical analysis of NASA-TLX RTLX scores across study arms."""
    base_objs = [
        NasaTlxRtlxAssessment(
            participant_id=x.participant_id,
            condition_id=x.condition_id,
            mental_demand=x.mental_demand,
            physical_demand=x.physical_demand,
            temporal_demand=x.temporal_demand,
            performance=x.performance,
            effort=x.effort,
            frustration=x.frustration
        )
        for x in request.baseline_cohort
    ]
    acuc_objs = [
        NasaTlxRtlxAssessment(
            participant_id=x.participant_id,
            condition_id=x.condition_id,
            mental_demand=x.mental_demand,
            physical_demand=x.physical_demand,
            temporal_demand=x.temporal_demand,
            performance=x.performance,
            effort=x.effort,
            frustration=x.frustration
        )
        for x in request.acucalyx_cohort
    ]
    res = PsychometricCohortAnalyzer.analyze_paired_workload(base_objs, acuc_objs)
    return {
        "sample_size_n": int(res.sample_size_n),
        "mean_baseline_rtlx": float(res.mean_baseline_rtlx),
        "mean_acucalyx_rtlx": float(res.mean_acucalyx_rtlx),
        "mean_paired_difference": float(res.mean_paired_difference),
        "ci95_difference": [float(x) for x in res.ci95_difference],
        "p_value_paired_t": float(res.p_value_paired_t),
        "cohens_d_effect_size": float(res.cohens_d_effect_size),
        "is_workload_reduction_significant": bool(res.is_workload_reduction_significant),
        "subscale_mean_differences": {str(k): float(v) for k, v in res.subscale_mean_differences.items()}
    }


@router.post("/psychometrics/sus-cohort")
def analyze_sus_cohort(request: SUSCohortRequest):
    """Evaluates SUS scores across study cohort against exploratory benchmark (>= 80.0)."""
    objs = [
        SystemUsabilityScaleAssessment(
            participant_id=x.participant_id,
            item_responses=x.item_responses
        )
        for x in request.submissions
    ]
    res = PsychometricCohortAnalyzer.analyze_sus_cohort(objs)
    return {
        "sample_size_n": int(res.sample_size_n),
        "mean_sus": float(res.mean_sus),
        "sd_sus": float(res.sd_sus),
        "median_sus": float(res.median_sus),
        "proportion_meeting_benchmark_80_pct": float(res.proportion_meeting_benchmark_80_pct),
        "adjective_distribution": {str(k): int(v) for k, v in res.adjective_distribution.items()}
    }
