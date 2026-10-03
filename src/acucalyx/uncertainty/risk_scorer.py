"""
AcuCalyx Uncertainty: Standalone Clinical Risk Scorer & Classification

Implements Step 10 of AcuCalyx v2.1:
- Aggregates empirical Monte Carlo collision probabilities and effective clearances
- Categorizes multi-organ hazard risks into standard clinical risk tiers:
  * CRITICAL: P(collision) > 5% or clearance <= 0mm
  * ELEVATED: P(collision) in (1%, 5%] or clearance in (0, 5mm]
  * MONITORED: P(collision) <= 1% with clearance in (5, 10mm]
  * ACCEPTABLE: P(collision) < 0.1% with clearance > 10mm
- Synthesizes explainable clinical safety classifications
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import numpy as np

from acucalyx.geometry.distance_fields import HazardClearanceResult
from acucalyx.uncertainty.monte_carlo import MonteCarloRiskAssessment


class HazardRiskTier(str, Enum):
    CRITICAL = "CRITICAL"        # Unsafe: high probability of perforation/injury
    ELEVATED = "ELEVATED"        # Caution: close proximity, within motion envelope
    MONITORED = "MONITORED"      # Feasible: adequate margin under standard respiration
    ACCEPTABLE = "ACCEPTABLE"    # Optimal: large safety buffer


@dataclass(frozen=True)
class TrajectoryRiskProfile:
    """Consolidated multi-hazard risk profile for a single needle trajectory."""
    candidate_id: str
    overall_safety_tier: HazardRiskTier
    is_clinically_acceptable: bool
    highest_risk_hazard: str
    max_collision_probability: float
    min_observed_clearance_mm: float
    min_effective_clearance_mm: float
    hazard_risk_details: Dict[str, HazardRiskTier]
    clinical_risk_narrative: str


def classify_hazard_risk(
    nominal_clearance_mm: float,
    effective_clearance_mm: float,
    collision_probability: float
) -> HazardRiskTier:
    """
    Classifies risk for a single anatomical hazard based on clearance and collision probability.
    """
    if effective_clearance_mm <= 0.0 or collision_probability >= 0.05:
        return HazardRiskTier.CRITICAL
    elif effective_clearance_mm < 5.0 or collision_probability >= 0.01:
        return HazardRiskTier.ELEVATED
    elif effective_clearance_mm < 10.0:
        return HazardRiskTier.MONITORED
    else:
        return HazardRiskTier.ACCEPTABLE


def score_trajectory_risk_profile(
    candidate_id: str,
    hazard_clearances: List[HazardClearanceResult],
    monte_carlo_assessments: Optional[List[MonteCarloRiskAssessment]] = None
) -> TrajectoryRiskProfile:
    """
    Evaluates multi-hazard risk across all adjacent anatomical structures.
    """
    mc_map = {m.hazard_name: m for m in (monte_carlo_assessments or [])}
    details: Dict[str, HazardRiskTier] = {}

    max_p_col = 0.0
    min_obs = float("inf")
    min_eff = float("inf")
    worst_tier = HazardRiskTier.ACCEPTABLE
    worst_hazard = "none"

    # Severity ordering for tier comparison
    severity_order = {
        HazardRiskTier.ACCEPTABLE: 0,
        HazardRiskTier.MONITORED: 1,
        HazardRiskTier.ELEVATED: 2,
        HazardRiskTier.CRITICAL: 3
    }

    for h in hazard_clearances:
        min_obs = min(min_obs, h.observed_clearance_mm)
        min_eff = min(min_eff, h.effective_clearance_mm)

        mc = mc_map.get(h.hazard_name)
        p_col = mc.collision_probability if mc else (1.0 if h.is_intersecting else 0.0)
        max_p_col = max(max_p_col, p_col)

        tier = classify_hazard_risk(
            nominal_clearance_mm=h.observed_clearance_mm,
            effective_clearance_mm=h.effective_clearance_mm,
            collision_probability=p_col
        )
        details[h.hazard_name] = tier

        if severity_order[tier] > severity_order[worst_tier]:
            worst_tier = tier
            worst_hazard = h.hazard_name

    if min_obs == float("inf"):
        min_obs = 50.0
        min_eff = 50.0

    is_ok = worst_tier not in (HazardRiskTier.CRITICAL,)

    narrative_parts = []
    for h_name, t in details.items():
        if t in (HazardRiskTier.CRITICAL, HazardRiskTier.ELEVATED):
            narrative_parts.append(f"{h_name.upper()} ({t.value})")

    if narrative_parts:
        narrative = f"Corridor flagged for proximity to: {', '.join(narrative_parts)}."
    else:
        narrative = f"All hazard clearances exceed safety envelopes (Min eff clearance: {min_eff:.1f} mm)."

    return TrajectoryRiskProfile(
        candidate_id=candidate_id,
        overall_safety_tier=worst_tier,
        is_clinically_acceptable=is_ok,
        highest_risk_hazard=worst_hazard,
        max_collision_probability=float(max_p_col),
        min_observed_clearance_mm=float(min_obs),
        min_effective_clearance_mm=float(min_eff),
        hazard_risk_details=details,
        clinical_risk_narrative=narrative
    )
