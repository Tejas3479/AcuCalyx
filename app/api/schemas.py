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
    owner_doctor_id: Optional[str] = "DOC_ELENA_CHEN"
    owner_doctor_name: Optional[str] = "Dr. Elena Chen, MD, FACS"
    patient_id: Optional[str] = "PT-7821"
    patient_age: Optional[int] = 56
    patient_sex: Optional[str] = "M"
    clinical_indication: Optional[str] = "Complex lower pole calculus (GSS II)"
    scheduled_procedure_date: Optional[str] = None
    privacy_status: Optional[str] = "RESTRICTED_ATTENDING_ONLY"


class PlanGenerationRequest(BaseModel):
    target_side: str = Field(default="left", description="'left' or 'right'")
    coarse_step_mm: float = Field(default=15.0, description="Flank skin sampling step")
    monte_carlo_samples: int = Field(default=200, description="Stochastic perturbation iterations")
    allow_marginal: bool = Field(default=False, description="Proceed with marginal DICOM quality")
    segmentation_method: Optional[str] = Field(default=None, description="Explicit segmentation backend ('TOTALSEGMENTATOR' or 'HEURISTIC_DEMO')")
    allow_fallback_segmentation: bool = Field(default=False, description="Permits audited heuristic anatomical corridor segmentation if native TotalSegmentator weights are unmounted")
    allow_fallback_segmentation: bool = Field(default=False, description="Permits audited heuristic anatomical corridor segmentation if native TotalSegmentator weights are unmounted")


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


class MetricValue(BaseModel):
    """
    Typed metric result with explicit provenance, units, and uncertainty status.
    Prevents scalar-float forcing when anatomy is unobserved or not evaluable.
    """
    value: Optional[float] = None
    unit: str = "mm"
    status: str = "MEASURED"  # 'MEASURED', 'DERIVED', 'ESTIMATED', 'UNCERTAIN', 'NOT_EVALUABLE'
    confidence: str = "HIGH"  # 'HIGH', 'MEDIUM', 'LOW', 'UNASSESSED'
    reason: Optional[str] = None


class CandidateComparisonItem(BaseModel):
    """
    Side-by-side comparative record for a candidate PCNL access tract.
    Replaces prescriptive sizing dictations with descriptive trade-off considerations.
    """
    candidate_id: str
    target_calyx_id: str
    target_calyx_name: str
    entry_point_lps: List[float]
    target_point_lps: List[float]
    tract_length_mm: MetricValue
    puncture_angle_coronal_deg: MetricValue
    puncture_angle_sagittal_deg: MetricValue
    rib_relation: str
    pleural_clearance: MetricValue
    colon_clearance: MetricValue
    vascular_clearance: MetricValue
    intercostal_bundle_clearance: Optional[MetricValue] = None
    rigid_accessible_stone_volume_mm3: MetricValue
    rigid_accessible_stone_percent: MetricValue
    flexible_accessible_stone_volume_mm3: MetricValue
    flexible_accessible_stone_percent: MetricValue
    inaccessible_stone_volume_mm3: MetricValue
    caliber_suitability_considerations: str
    irrigation_pressure_risk: str
    uncertainty_flags: List[str] = []
    clinical_tradeoff_summary: str


class CandidateComparisonMatrixResponse(BaseModel):
    """
    Unified multi-tract comparative workbench model with clinical boundaries.
    """
    case_id: str
    imaging_modality: str
    patient_position_assumed: str
    total_stone_volume_mm3: MetricValue
    candidates: List[CandidateComparisonItem]
    active_candidate_id: Optional[str] = None
    provenance_hash: str
    disclaimer: str = (
        "PREOPERATIVE GEOMETRIC ESTIMATE ONLY — NOT AN INTRAOPERATIVE MAP. "
        "Candidate comparisons and clearance estimates are computational decision support, "
        "not guarantees of procedural safety, reachability, or stone-free status."
    )

