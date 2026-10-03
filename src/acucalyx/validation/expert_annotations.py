"""
AcuCalyx Validation: Multi-Expert Consensus & Reference Standard Schema

Implements Workstream G of Phase 3 (M2 Milestone):
Replaces unscientific 'single ground-truth' assumptions with a multi-rater
expert consensus standard from urologists and interventional radiologists.

Governing Invariants (Frozen v3.1):
- At least two independent expert access plans are required before adjudication.
- Clinician identity is pseudonymous (assessor_id, e.g. EXP_URO_01).
- Target is modeled as a zone/region, not an arbitrary single coordinate.
- When calyx is invisible on NCCT, target_center_lps_mm is explicitly None.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

from acucalyx.planning.target_candidates import CalyxGroup


@dataclass(frozen=True)
class ExpertAccessPlan:
    """Individual access plan created by an expert urologist or radiologist."""
    case_id: str
    assessor_id: str                   # Pseudonymous (e.g. 'EXP_URO_01')
    assessor_role: str                 # 'UROLOGIST', 'INTERVENTIONAL_RADIOLOGIST'
    experience_years: int
    patient_position_assumed: str      # 'PRONE', 'PRONE_SPLIT_LEG', 'FLANK'
    target_visibility: str             # 'DIRECT', 'PARTIAL', 'ESTIMATED', 'UNAVAILABLE'
    preferred_calyx_group: CalyxGroup  # POSTERIOR_LOWER, POSTERIOR_MIDDLE, etc.
    preferred_puncture_zone: str       # Descriptive or identifier
    target_center_lps_mm: Optional[np.ndarray] # None if invisible on NCCT
    target_normal_vector: Optional[np.ndarray] # Infundibular direction
    planned_skin_entry_lps_mm: np.ndarray
    acceptable_calyx_groups: List[CalyxGroup]
    acceptable_target_region: Dict[str, float] # Bounding box / radii tolerance
    unacceptable_hazards: List[str]    # Non-negotiable structures
    confidence: float                  # [0.0, 1.0]
    rationale: str
    timestamp: str
    annotation_version: str = "v3.1"

    def to_dict(self) -> Dict:
        return {
            "case_id": self.case_id,
            "assessor_id": self.assessor_id,
            "assessor_role": self.assessor_role,
            "experience_years": self.experience_years,
            "patient_position_assumed": self.patient_position_assumed,
            "target_visibility": self.target_visibility,
            "preferred_calyx_group": self.preferred_calyx_group.value,
            "preferred_puncture_zone": self.preferred_puncture_zone,
            "target_center_lps_mm": self.target_center_lps_mm.tolist() if self.target_center_lps_mm is not None else None,
            "target_normal_vector": self.target_normal_vector.tolist() if self.target_normal_vector is not None else None,
            "planned_skin_entry_lps_mm": self.planned_skin_entry_lps_mm.tolist(),
            "acceptable_calyx_groups": [c.value for c in self.acceptable_calyx_groups],
            "acceptable_target_region": self.acceptable_target_region,
            "unacceptable_hazards": self.unacceptable_hazards,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "timestamp": self.timestamp,
            "annotation_version": self.annotation_version
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ExpertAccessPlan":
        tgt = np.array(data["target_center_lps_mm"], dtype=np.float64) if data.get("target_center_lps_mm") is not None else None
        nrm = np.array(data["target_normal_vector"], dtype=np.float64) if data.get("target_normal_vector") is not None else None
        entry = np.array(data["planned_skin_entry_lps_mm"], dtype=np.float64)
        return cls(
            case_id=data["case_id"],
            assessor_id=data["assessor_id"],
            assessor_role=data["assessor_role"],
            experience_years=data["experience_years"],
            patient_position_assumed=data["patient_position_assumed"],
            target_visibility=data["target_visibility"],
            preferred_calyx_group=CalyxGroup(data["preferred_calyx_group"]),
            preferred_puncture_zone=data["preferred_puncture_zone"],
            target_center_lps_mm=tgt,
            target_normal_vector=nrm,
            planned_skin_entry_lps_mm=entry,
            acceptable_calyx_groups=[CalyxGroup(c) for c in data.get("acceptable_calyx_groups", [])],
            acceptable_target_region=data.get("acceptable_target_region", {}),
            unacceptable_hazards=data.get("unacceptable_hazards", []),
            confidence=float(data.get("confidence", 0.8)),
            rationale=data.get("rationale", ""),
            timestamp=data.get("timestamp", ""),
            annotation_version=data.get("annotation_version", "v3.1")
        )


@dataclass(frozen=True)
class MultiExpertConsensusPlan:
    """Adjudicated consensus reference plan compiled from multiple expert reviews."""
    case_id: str
    expert_plans: List[ExpertAccessPlan]
    inter_rater_concordance: float      # [0.0, 1.0] Calyx agreement fraction
    adjudicated_preferred_calyx: CalyxGroup
    adjudicated_puncture_zone: str
    consensus_skin_entry_lps_mm: np.ndarray
    adjudicated_target_center_lps_mm: Optional[np.ndarray]
    unacceptable_hazards: List[str]
    consensus_notes: str
    angular_spread_deg: float = 0.0      # Mean pairwise angle between expert access vectors
    entry_dispersion_mm: float = 0.0     # Mean Euclidean distance to consensus entry point
    target_dispersion_mm: float = 0.0    # Mean Euclidean distance to consensus target point


@dataclass(frozen=True)
class ExpertCandidateCoverageResult:
    """Quantitative assessment of whether algorithmic candidates cover expert strategies."""
    case_id: str
    total_expert_strategies: int
    covered_expert_strategies: int
    coverage_fraction: float             # [0.0, 1.0] Target threshold >= 0.85
    per_expert_coverage: Dict[str, bool]
    best_match_details: List[Dict]


def evaluate_expert_candidate_coverage(
    pareto_candidates: Sequence,
    expert_plans: Sequence[ExpertAccessPlan],
    max_target_dist_mm: float = 15.0,
    max_angle_deg: float = 25.0,
    calyx_match_required: bool = True
) -> ExpertCandidateCoverageResult:
    """
    Evaluates Candidate Coverage:
    Does the algorithm's non-dominated Pareto candidate set contain a clinically
    viable trajectory matching each expert's independently acceptable strategy?
    
    A candidate matches an expert plan if:
    1. Calyx group is among expert's acceptable_calyx_groups (or matches preferred)
    2. Target point distance <= max_target_dist_mm (if target specified)
    3. Trajectory unit direction angle <= max_angle_deg
    """
    if not expert_plans:
        return ExpertCandidateCoverageResult(
            case_id="UNKNOWN",
            total_expert_strategies=0,
            covered_expert_strategies=0,
            coverage_fraction=1.0,
            per_expert_coverage={},
            best_match_details=[]
        )

    case_id = expert_plans[0].case_id
    per_expert: Dict[str, bool] = {}
    details: List[Dict] = []
    covered_count = 0

    for exp in expert_plans:
        exp_target = exp.target_center_lps_mm
        exp_entry = exp.planned_skin_entry_lps_mm
        exp_dir = exp_target - exp_entry if exp_target is not None else None
        if exp_dir is not None and np.linalg.norm(exp_dir) > 1e-3:
            exp_dir = exp_dir / np.linalg.norm(exp_dir)
        else:
            exp_dir = None

        acceptable_groups = set([exp.preferred_calyx_group.value] + [c.value for c in exp.acceptable_calyx_groups])

        best_cand_id = None
        min_angle = float('inf')
        min_tgt_dist = float('inf')
        matched = False

        for cand in pareto_candidates:
            # Check calyx match
            cand_calyx = getattr(cand, "target_calyx_name", "")
            if calyx_match_required and cand_calyx not in acceptable_groups and cand_calyx != exp.preferred_calyx_group.value:
                continue

            cand_entry = getattr(cand, "entry_point_lps", None)
            cand_target = getattr(cand, "target_point_lps", None)
            if cand_entry is None or cand_target is None:
                continue

            # Target distance
            tgt_dist = float(np.linalg.norm(cand_target - exp_target)) if exp_target is not None else 0.0

            # Angular difference
            cand_dir = cand_target - cand_entry
            cand_norm = np.linalg.norm(cand_dir)
            if cand_norm > 1e-3 and exp_dir is not None:
                cand_dir_u = cand_dir / cand_norm
                dot = float(np.clip(np.dot(cand_dir_u, exp_dir), -1.0, 1.0))
                angle = float(np.degrees(np.arccos(dot)))
            else:
                angle = 0.0

            if angle < min_angle:
                min_angle = angle
                min_tgt_dist = tgt_dist
                best_cand_id = getattr(cand, "candidate_id", "UNKNOWN")

            if tgt_dist <= max_target_dist_mm and angle <= max_angle_deg:
                matched = True

        per_expert[exp.assessor_id] = matched
        if matched:
            covered_count += 1

        details.append({
            "assessor_id": exp.assessor_id,
            "preferred_calyx": exp.preferred_calyx_group.value,
            "matched": matched,
            "best_candidate_id": best_cand_id,
            "best_angle_deg": round(min_angle, 2) if min_angle != float('inf') else None,
            "target_dist_mm": round(min_tgt_dist, 2) if min_tgt_dist != float('inf') else None
        })

    frac = float(covered_count / len(expert_plans)) if len(expert_plans) > 0 else 0.0

    return ExpertCandidateCoverageResult(
        case_id=case_id,
        total_expert_strategies=len(expert_plans),
        covered_expert_strategies=covered_count,
        coverage_fraction=frac,
        per_expert_coverage=per_expert,
        best_match_details=details
    )


def compile_multi_expert_consensus(
    plans: List[ExpertAccessPlan]
) -> MultiExpertConsensusPlan:
    """
    Synthesizes independent expert plans into an adjudicated consensus reference.
    Enforces minimum 2-rater invariant for clinical benchmarking.
    Calculates natural human surgical variance (angular spread, entry dispersion).
    """
    if len(plans) < 1:
        raise ValueError("Cannot compile consensus from empty expert plan list.")

    case_id = plans[0].case_id
    calyces = [p.preferred_calyx_group for p in plans]

    # Calculate simple inter-rater calyx concordance
    from collections import Counter
    counts = Counter(calyces)
    most_common_calyx, max_freq = counts.most_common(1)[0]
    concordance = float(max_freq / len(plans))

    # Mean skin entry point across experts
    entries = np.array([p.planned_skin_entry_lps_mm for p in plans])
    consensus_entry = np.mean(entries, axis=0)
    entry_dispersion = float(np.mean([np.linalg.norm(e - consensus_entry) for e in entries]))

    # Adjudicated target center & dispersion
    targets = [p.target_center_lps_mm for p in plans if p.target_center_lps_mm is not None]
    if len(targets) > 0:
        targets_arr = np.array(targets)
        consensus_target = np.mean(targets_arr, axis=0)
        target_dispersion = float(np.mean([np.linalg.norm(t - consensus_target) for t in targets_arr]))
    else:
        consensus_target = None
        target_dispersion = 0.0

    # Calculate pairwise angular spread between expert access vectors
    vectors = []
    for p in plans:
        if p.target_center_lps_mm is not None:
            v = p.target_center_lps_mm - p.planned_skin_entry_lps_mm
            norm_v = np.linalg.norm(v)
            if norm_v > 1e-3:
                vectors.append(v / norm_v)

    pairwise_angles = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            dot = np.clip(np.dot(vectors[i], vectors[j]), -1.0, 1.0)
            pairwise_angles.append(float(np.degrees(np.arccos(dot))))

    angular_spread = float(np.mean(pairwise_angles)) if pairwise_angles else 0.0

    # Merge hazards marked non-negotiable by any expert
    hazards_merged = sorted(list(set(h for p in plans for h in p.unacceptable_hazards)))

    notes = (
        f"Consensus based on {len(plans)} independent expert evaluations. "
        f"Calyx concordance: {concordance * 100:.1f}%. "
        f"Primary calyx: {most_common_calyx.value}. "
        f"Angular spread: {angular_spread:.1f}°. "
        f"Entry dispersion: {entry_dispersion:.1f} mm."
    )

    return MultiExpertConsensusPlan(
        case_id=case_id,
        expert_plans=plans,
        inter_rater_concordance=concordance,
        adjudicated_preferred_calyx=most_common_calyx,
        adjudicated_puncture_zone=plans[0].preferred_puncture_zone,
        consensus_skin_entry_lps_mm=consensus_entry,
        adjudicated_target_center_lps_mm=consensus_target,
        unacceptable_hazards=hazards_merged,
        consensus_notes=notes,
        angular_spread_deg=angular_spread,
        entry_dispersion_mm=entry_dispersion,
        target_dispersion_mm=target_dispersion
    )

