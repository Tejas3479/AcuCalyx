"""
AcuCalyx Unit Tests: Milestone M12-V 12-Strata Challenge Benchmark Gate
Governed by ACU-M12V-M13-EXEC-PLAN-2026-V2.
"""

import pytest
from acucalyx.validation.challenge_benchmark import (
    calculate_clopper_pearson_1sided_upper,
    run_m12v_challenge_strata_benchmark
)
from acucalyx.validation.challenge_set import ChallengeCategory


def test_clopper_pearson_calculation_properties():
    """Verify exact 1-sided Clopper-Pearson upper bound calculation."""
    # Zero breaches in 12 trials at alpha=0.05:
    # Upper = 1 - 0.05^(1/12) ≈ 0.2212 (22.12%)
    upper_zero = calculate_clopper_pearson_1sided_upper(k=0, n=12, alpha=0.05)
    assert pytest.approx(upper_zero, 0.01) == 0.2212
    assert upper_zero < 0.25

    # Zero breaches in 100 trials:
    # Upper = 1 - 0.05^(1/100) ≈ 0.0295 (2.95%)
    upper_large = calculate_clopper_pearson_1sided_upper(k=0, n=100, alpha=0.05)
    assert upper_large < 0.03


def test_m12v_challenge_strata_benchmark_execution():
    """
    Executes full M12-V Planning Validation Gate across all 12 challenge strata.
    Verifies that all acceptance gates pass without exception.
    """
    report = run_m12v_challenge_strata_benchmark()

    # 1. Total strata evaluated
    assert report.total_strata_evaluated == 12
    assert report.strata_passed == 12

    # 2. Deterministic Hazard Filter Integrity: 100% on mathematical tests
    assert report.deterministic_hazard_filter_integrity_pct == 100.0

    # 3. Fail-Closed Robustness: 100% on unresolvable cases (collapsed PCS, motion blur)
    assert report.fail_closed_robustness_pct == 100.0

    # 4. Multi-Expert Candidate Coverage: >= 85.0%
    assert report.overall_expert_candidate_coverage_pct >= 85.0

    # 5. Critical Hazard Breaches: Exactly 0
    assert report.total_critical_hazard_breaches == 0

    # 6. Clopper-Pearson 95% 1-sided upper bound
    assert report.clopper_pearson_95_upper_bound < 0.25

    # 7. Interlock U6 Traceability & Superseding
    assert report.interlock_u6_superseding_verified is True

    # 8. Overall Gate Status
    assert report.gate_passed is True

    # Verify per-stratum entries
    strata_categories = [r.stratum_category for r in report.strata_results]
    for cat in ChallengeCategory:
        assert cat in strata_categories
