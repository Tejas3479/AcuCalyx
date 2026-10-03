"""
Unit tests for AcuCalyx Pareto frontier extraction and multi-objective optimization.
"""

import numpy as np
import pytest

from acucalyx.planning.pareto_optimizer import (
    CandidateTrajectory, extract_pareto_frontier, is_dominated
)


def test_is_dominated():
    """Verify domination condition: p2 dominates p1 if strictly better in at least one and not worse."""
    p_worse = np.array([100.0, 0.5, 0.3, 20.0, 1.0])
    p_better = np.array([80.0, 0.2, 0.1, 10.0, 0.0])
    assert is_dominated(p_worse, p_better) is True
    assert is_dominated(p_better, p_worse) is False


def test_extract_pareto_frontier():
    """Verify non-dominated candidates are correctly flagged."""
    # Candidate A: short tract (70mm), low clearance (3mm)
    cand_a = CandidateTrajectory(
        candidate_id="CAND_A",
        target_calyx_name="Lower_Posterior",
        entry_point_lps=np.zeros(3),
        target_point_lps=np.zeros(3),
        tract_length_mm=70.0,
        min_effective_clearance_mm=3.0,
        hazard_evaluations=[],
        reachable_stone_fraction=0.9,
        required_scope_deflection_deg=10.0,
        access_rib_classification="SUBCOSTAL",
        is_pareto_optimal=False,
        confidence_tier="HIGH"
    )

    # Candidate B: longer tract (95mm), huge clearance (25mm) -> Trade-off! Should also be Pareto optimal
    cand_b = CandidateTrajectory(
        candidate_id="CAND_B",
        target_calyx_name="Lower_Posterior",
        entry_point_lps=np.zeros(3),
        target_point_lps=np.zeros(3),
        tract_length_mm=95.0,
        min_effective_clearance_mm=25.0,
        hazard_evaluations=[],
        reachable_stone_fraction=0.9,
        required_scope_deflection_deg=10.0,
        access_rib_classification="SUBCOSTAL",
        is_pareto_optimal=False,
        confidence_tier="HIGH"
    )

    # Candidate C: strictly worse than A in every metric (longer tract 120mm, worse clearance 1mm, less reach)
    cand_c = CandidateTrajectory(
        candidate_id="CAND_C",
        target_calyx_name="Lower_Posterior",
        entry_point_lps=np.zeros(3),
        target_point_lps=np.zeros(3),
        tract_length_mm=120.0,
        min_effective_clearance_mm=1.0,
        hazard_evaluations=[],
        reachable_stone_fraction=0.5,
        required_scope_deflection_deg=35.0,
        access_rib_classification="SUPRACOSTAL_11",
        is_pareto_optimal=False,
        confidence_tier="LOW"
    )

    frontier = extract_pareto_frontier([cand_a, cand_b, cand_c])

    # A and B are trade-offs (both Pareto optimal); C is dominated
    cand_map = {c.candidate_id: c.is_pareto_optimal for c in frontier}
    assert cand_map["CAND_A"] is True
    assert cand_map["CAND_B"] is True
    assert cand_map["CAND_C"] is False
