"""
AcuCalyx Planning: Three-Tier Multi-Objective Pareto Trajectory Optimizer

Governed by Version 2.0 Architectural Baseline:
- Tier 1: Hard Constraint Filter Gate (Critical hazard collision, instrument physical envelope, evidence state)
- Tier 2: Multi-Objective Pareto Candidate Generator (Non-dominated sorting across robust clearance, stone coverage, scope reach, tract length)
- Tier 3: Descriptive Clinical Metadata (GSS, S.T.O.N.E., decoupled rib/pleural/diaphragmatic relations)
- Fail-Safe Output State Machine: Emits explicit "NO PLAN" states when anatomy, evidence, or safety envelopes fail.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np

from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.geometry.distance_fields import HazardClearanceResult
from acucalyx.planning.scope_model import InstrumentProfile, STANDARD_RIGID_NEPHROSCOPE


class PlanStatus(str, Enum):
    """Fail-safe planning status state machine."""
    PLAN_AVAILABLE = "PLAN_AVAILABLE"
    NO_PLAN_INSUFFICIENT_EVIDENCE = "NO_PLAN_INSUFFICIENT_EVIDENCE"
    NO_PLAN_CRITICAL_HAZARD = "NO_PLAN_CRITICAL_HAZARD"
    NO_PLAN_UNSUPPORTED_ANATOMY = "NO_PLAN_UNSUPPORTED_ANATOMY"
    NO_PLAN_TARGET_UNIDENTIFIABLE = "NO_PLAN_TARGET_UNIDENTIFIABLE"
    NO_PLAN_UNCERTAINTY_EXCEEDED = "NO_PLAN_UNCERTAINTY_EXCEEDED"


class RibClassification(str, Enum):
    """Physical costal margin relation."""
    SUBCOSTAL = "SUBCOSTAL"
    INTERCOSTAL_11_12 = "INTERCOSTAL_11_12"
    SUPRACOSTAL_11 = "SUPRACOSTAL_11"
    SUPRACOSTAL_10 = "SUPRACOSTAL_10"


class PleuralRelation(str, Enum):
    """Pleural reflection envelope relation (independent of ribs)."""
    NO_INTERSECTION = "NO_INTERSECTION"
    MARGINAL_CLEARANCE = "MARGINAL_CLEARANCE"
    DIRECT_INTERSECTION = "DIRECT_INTERSECTION"


class DiaphragmRelation(str, Enum):
    """Diaphragm dome transit relation."""
    SUBDIAPHRAGMATIC = "SUBDIAPHRAGMATIC"
    TRANSDIAPHRAGMATIC = "TRANSDIAPHRAGMATIC"


@dataclass(frozen=True)
class CandidateTrajectory:
    """A candidate needle trajectory evaluated across all three planning tiers."""
    candidate_id: str
    target_calyx_name: str
    entry_point_lps: np.ndarray      # [x, y, z] on skin in mm
    target_point_lps: np.ndarray     # [x, y, z] calyx target in mm
    tract_length_mm: float           # Skin to calyx depth in mm
    min_effective_clearance_mm: float # Smallest effective clearance across all hazards
    hazard_evaluations: List[HazardClearanceResult]
    reachable_stone_fraction: float  # [0.0, 1.0]
    required_scope_deflection_deg: float
    access_rib_classification: str   # 'SUBCOSTAL', 'INTERCOSTAL_11_12', etc.
    is_pareto_optimal: bool = False
    confidence_tier: str = "MODERATE" # 'HIGH', 'MODERATE', 'LOW'
    pleural_relation: str = "NO_INTERSECTION"
    diaphragm_relation: str = "SUBDIAPHRAGMATIC"
    is_hard_constraint_satisfied: bool = True
    hard_constraint_violation_reason: Optional[str] = None
    nephrolithometry_metadata: Optional[Dict] = None


@dataclass(frozen=True)
class PlanEvaluationResult:
    """Complete multi-tier planning evaluation result presented to clinician."""
    status: PlanStatus
    pareto_candidates: List[CandidateTrajectory]
    rejected_candidates: List[CandidateTrajectory]
    status_message: str
    summary_metadata: Dict = field(default_factory=dict)

    @property
    def has_viable_plan(self) -> bool:
        return self.status == PlanStatus.PLAN_AVAILABLE and len(self.pareto_candidates) > 0


def is_dominated(p1: np.ndarray, p2: np.ndarray) -> bool:
    """
    Returns True if p2 dominates p1 in minimization:
    p2 is <= p1 in all objectives and strictly < in at least one.
    """
    all_less_equal = np.all(p2 <= p1)
    any_strictly_less = np.any(p2 < p1)
    return bool(all_less_equal and any_strictly_less)


def extract_pareto_frontier(
    candidates: List[CandidateTrajectory],
    include_rib_penalty: bool = False
) -> List[CandidateTrajectory]:
    """
    Identifies Pareto-efficient candidates across continuous physical objectives.
    
    Objectives to minimize:
    1. Tract length (L_tract)
    2. Hazard risk: 1.0 / (1.0 + max(0.0, min_effective_clearance))
    3. Unreached stone fraction: (1.0 - reachable_stone_fraction)
    4. Required scope deflection (E_scope)
    5. [Optional legacy] Rib access penalty if include_rib_penalty=True
    """
    if not candidates:
        return []

    rib_penalties = {
        'SUBCOSTAL': 0.0,
        'INTERCOSTAL_11_12': 1.0,
        'SUPRACOSTAL_11': 2.0,
        'SUPRACOSTAL_10': 3.0
    }

    n_obj = 5 if include_rib_penalty else 4
    obj_matrix = np.zeros((len(candidates), n_obj), dtype=np.float64)

    for i, c in enumerate(candidates):
        hazard_risk = 1.0 / (1.0 + max(0.0, c.min_effective_clearance_mm))
        unreached_stone = 1.0 - c.reachable_stone_fraction
        
        if include_rib_penalty:
            rib_cost = rib_penalties.get(c.access_rib_classification, 1.0)
            obj_matrix[i, :] = [
                c.tract_length_mm,
                hazard_risk,
                unreached_stone,
                c.required_scope_deflection_deg,
                rib_cost
            ]
        else:
            obj_matrix[i, :] = [
                c.tract_length_mm,
                hazard_risk,
                unreached_stone,
                c.required_scope_deflection_deg
            ]

    n_candidates = len(candidates)
    pareto_flags = [True] * n_candidates

    for i in range(n_candidates):
        for j in range(n_candidates):
            if i != j and pareto_flags[i]:
                if is_dominated(obj_matrix[i], obj_matrix[j]):
                    pareto_flags[i] = False
                    break

    # Reconstruct with updated pareto flags
    updated: List[CandidateTrajectory] = []
    for c, flag in zip(candidates, pareto_flags):
        updated.append(CandidateTrajectory(
            candidate_id=c.candidate_id,
            target_calyx_name=c.target_calyx_name,
            entry_point_lps=c.entry_point_lps,
            target_point_lps=c.target_point_lps,
            tract_length_mm=c.tract_length_mm,
            min_effective_clearance_mm=c.min_effective_clearance_mm,
            hazard_evaluations=c.hazard_evaluations,
            reachable_stone_fraction=c.reachable_stone_fraction,
            required_scope_deflection_deg=c.required_scope_deflection_deg,
            access_rib_classification=c.access_rib_classification,
            is_pareto_optimal=flag,
            confidence_tier=c.confidence_tier,
            pleural_relation=c.pleural_relation,
            diaphragm_relation=c.diaphragm_relation,
            is_hard_constraint_satisfied=c.is_hard_constraint_satisfied,
            hard_constraint_violation_reason=c.hard_constraint_violation_reason,
            nephrolithometry_metadata=c.nephrolithometry_metadata
        ))

    return updated


def optimize_pcnl_access_candidates(
    candidates: List[CandidateTrajectory],
    instrument_profile: Optional[InstrumentProfile] = None,
    min_clearance_threshold_mm: float = 0.0,
    evidence_valid: bool = True,
    anatomy_supported: bool = True,
    target_identifiable: bool = True,
    uncertainty_exceeded: bool = False
) -> PlanEvaluationResult:
    """
    Executes the Three-Tier PCNL Access Planning Optimization Pipeline:
    1. Pre-condition checks (Fail-Safe "NO PLAN" State Machine)
    2. Tier 1 Hard Constraint Filtering (Clearance, working length, mechanical torque)
    3. Tier 2 Multi-Objective Pareto Frontier Extraction
    4. Tier 3 Descriptive Metadata Enrichment
    """
    # Pre-condition validation
    if not evidence_valid:
        return PlanEvaluationResult(
            status=PlanStatus.NO_PLAN_INSUFFICIENT_EVIDENCE,
            pareto_candidates=[],
            rejected_candidates=candidates,
            status_message="Image quality or segmentation evidence insufficient for safe PCNL access planning."
        )

    if not anatomy_supported:
        return PlanEvaluationResult(
            status=PlanStatus.NO_PLAN_UNSUPPORTED_ANATOMY,
            pareto_candidates=[],
            rejected_candidates=candidates,
            status_message="Anatomical anomaly exceeds validated algorithm envelope; manual urological planning required."
        )

    if not target_identifiable:
        return PlanEvaluationResult(
            status=PlanStatus.NO_PLAN_TARGET_UNIDENTIFIABLE,
            pareto_candidates=[],
            rejected_candidates=candidates,
            status_message="Target calyx/fornix cannot be localized with clinical certainty."
        )

    if uncertainty_exceeded:
        return PlanEvaluationResult(
            status=PlanStatus.NO_PLAN_UNCERTAINTY_EXCEEDED,
            pareto_candidates=[],
            rejected_candidates=candidates,
            status_message="Combined motion/segmentation uncertainty envelope exceeds safe clinical tolerance."
        )

    if not candidates:
        return PlanEvaluationResult(
            status=PlanStatus.NO_PLAN_CRITICAL_HAZARD,
            pareto_candidates=[],
            rejected_candidates=[],
            status_message="No feasible candidate access trajectories could be generated."
        )

    # Tier 1: Hard Constraints Filter Gate
    inst = instrument_profile or STANDARD_RIGID_NEPHROSCOPE
    surviving: List[CandidateTrajectory] = []
    rejected: List[CandidateTrajectory] = []

    for c in candidates:
        violation_reason = None

        # Check 1: Critical hazard intersection with conservative envelope
        if c.min_effective_clearance_mm < min_clearance_threshold_mm:
            violation_reason = f"Critical hazard clearance {c.min_effective_clearance_mm:.1f} mm below threshold {min_clearance_threshold_mm:.1f} mm"
        
        # Check 2: Instrument working length exceeded
        elif c.tract_length_mm > inst.working_length_mm:
            violation_reason = f"Tract length {c.tract_length_mm:.1f} mm exceeds instrument working length {inst.working_length_mm:.1f} mm"

        # Check 3: Instrument mechanical torque exceeded
        elif c.required_scope_deflection_deg > inst.max_deflection_deg:
            violation_reason = f"Required deflection {c.required_scope_deflection_deg:.1f}° exceeds instrument limit {inst.max_deflection_deg:.1f}°"

        if violation_reason is not None:
            updated_c = CandidateTrajectory(
                candidate_id=c.candidate_id,
                target_calyx_name=c.target_calyx_name,
                entry_point_lps=c.entry_point_lps,
                target_point_lps=c.target_point_lps,
                tract_length_mm=c.tract_length_mm,
                min_effective_clearance_mm=c.min_effective_clearance_mm,
                hazard_evaluations=c.hazard_evaluations,
                reachable_stone_fraction=c.reachable_stone_fraction,
                required_scope_deflection_deg=c.required_scope_deflection_deg,
                access_rib_classification=c.access_rib_classification,
                is_pareto_optimal=False,
                confidence_tier=c.confidence_tier,
                pleural_relation=c.pleural_relation,
                diaphragm_relation=c.diaphragm_relation,
                is_hard_constraint_satisfied=False,
                hard_constraint_violation_reason=violation_reason,
                nephrolithometry_metadata=c.nephrolithometry_metadata
            )
            rejected.append(updated_c)
        else:
            surviving.append(c)

    # If all candidates fail hard constraints
    if not surviving:
        return PlanEvaluationResult(
            status=PlanStatus.NO_PLAN_CRITICAL_HAZARD,
            pareto_candidates=[],
            rejected_candidates=rejected,
            status_message=f"All {len(candidates)} candidate trajectories violated hard clinical safety constraints."
        )

    # Tier 2: Multi-Objective Pareto Frontier Extraction
    pareto_evaluated = extract_pareto_frontier(surviving, include_rib_penalty=False)
    pareto_candidates = [c for c in pareto_evaluated if c.is_pareto_optimal]

    return PlanEvaluationResult(
        status=PlanStatus.PLAN_AVAILABLE,
        pareto_candidates=pareto_candidates,
        rejected_candidates=rejected,
        status_message=f"Identified {len(pareto_candidates)} Pareto-efficient candidate access trajectories for clinician review.",
        summary_metadata={
            "total_evaluated": len(candidates),
            "survived_hard_constraints": len(surviving),
            "pareto_efficient_count": len(pareto_candidates),
            "instrument_profile_used": inst.name
        }
    )
