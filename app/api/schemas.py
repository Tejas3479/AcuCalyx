"""
AcuCalyx API Schemas: Pydantic Data Contracts for Clinical Decision Support

Defines strict request/response models for:
- Case workflow state machine transitions
- Fail-closed quality gate summaries
- Quantitative calculus volumetry & attenuation profiling
- Multi-objective Pareto access trajectories and safety badges
- Virtual fluoroscopic projection parameters
- Clinician overrides and auditable decision logging
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class CaseState(str, Enum):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    ANATOMY_REVIEW = "ANATOMY_REVIEW"
    PLAN_GENERATED = "PLAN_GENERATED"
    CLINICIAN_REVIEW = "CLINICIAN_REVIEW"
    FINALIZED = "FINALIZED"
    REJECTED = "REJECTED"


class QualityGateSummary(BaseModel):
    is_acceptable: bool
    critical_errors: List[str] = []
    warnings: List[str] = []
    slice_count: int
    mean_slice_thickness_mm: float
    mean_inter_slice_spacing_mm: float
    slice_spacing_std_mm: float
    gantry_tilt_degrees: float
    is_helical: bool


class StoneMetricItem(BaseModel):
    stone_id: int
    volume_mm3: float
    max_feret_diameter_mm: float
    centroid_lps_mm: List[float]
    bounding_box_span_mm: List[float]
    tier: str
    mean_hu: float
    peak_hu: float
    fraction_high_over_1000hu: float
    composition_inference: str


class HazardClearanceItem(BaseModel):
    hazard_name: str
    observed_clearance_mm: float
    effective_clearance_mm: float
    is_intersecting: bool
    confidence_level: str


class MonteCarloItem(BaseModel):
    hazard_name: str
    collision_probability: float
    nominal_clearance_mm: float
    percentile_5th_clearance_mm: float
    mean_perturbed_clearance_mm: float
    risk_category: str


class CandidateTrajectoryItem(BaseModel):
    candidate_id: str
    target_calyx: str
    entry_point_lps: List[float]
    target_point_lps: List[float]
    tract_length_mm: float
    min_effective_clearance_mm: float
    reachable_stone_fraction: float
    required_scope_deflection_deg: float
    access_rib_classification: str
    confidence_tier: str
    is_pareto_optimal: bool
    safety_badge: str  # 'PREFERRED', 'CONDITIONAL', 'REJECTED'
    hazards: List[HazardClearanceItem] = []
    uncertainty: List[MonteCarloItem] = []


class FluoroscopyViewData(BaseModel):
    view_type: str  # 'BULLS_EYE' or 'PROGRESSION'
    source_position_lps: List[float]
    detector_position_lps: List[float]
    optical_axis_unit: List[float]
    projected_entry_2d_mm: List[float]
    projected_target_2d_mm: List[float]
    projected_needle_length_2d_mm: float
    alignment_angle_deg: float


class CaseSummaryResponse(BaseModel):
    case_id: str
    state: CaseState
    created_at: str
    updated_at: str
    target_side: str
    is_stale: bool = False
    active_candidate_id: Optional[str] = None
    quality: Optional[QualityGateSummary] = None
    stone_count: int = 0
    candidate_count: int = 0
    clinical_notice: str = ""


class PlanGenerationRequest(BaseModel):
    target_side: str = Field(default="left", description="'left' or 'right'")
    coarse_step_mm: float = Field(default=15.0, description="Flank skin sampling step")
    monte_carlo_samples: int = Field(default=200, description="Stochastic perturbation iterations")
    allow_marginal: bool = Field(default=False, description="Proceed with marginal DICOM quality")


class TrajectorySelectionRequest(BaseModel):
    candidate_id: str
    clinician_id: str = "Surgeon_01"
    clinical_rationale: Optional[str] = "Selected optimal lower pole infundibular corridor avoiding pleural reflection."


class ManualOverrideRequest(BaseModel):
    override_type: str = Field(..., description="'CALYX_TARGET', 'MASK_ADJUSTMENT', or 'HAZARD_BUFFER'")
    target_calyx_id: Optional[str] = None
    modified_coordinates_lps: Optional[List[float]] = None
    reason: str
    clinician_id: str = "Surgeon_01"


class CaseUploadResponse(BaseModel):
    case_id: str
    state: CaseState
    message: str
    input_file_count: int
