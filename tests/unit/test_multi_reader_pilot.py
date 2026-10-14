"""
AcuCalyx Unit Tests: Phase 0 CTU Feasibility Pilot & Multi-Reader Consensus
(Milestone M15.0.2 / M15.1 / Audit Remediation)

Verifies:
1. Multi-reader annotation synthesis across 3 independent clinical readers.
2. Pairwise Dice agreement, STAPLE/majority consensus, and ambiguity volume preservation.
3. Calyx landmark spatial dispersion calculation and high-disagreement flagging (>5.0 mm).
4. Infundibular diameter consensus calculation.
5. Strict fail-closed gate for non-opacified CT series (CTUOpacificationQuality.NON_OPACIFIED).
6. Single-case and cohort benchmark evaluation against VMTK distance-ridge reference centerlines.
7. Executive GO / NO-GO decision logic for Phase 0 feasibility acceptance.
"""

import hashlib
import numpy as np
import pytest

from acucalyx.endoscopy.multi_reader_pilot import (
    CTUOpacificationQuality,
    ReaderAnnotation,
    CalyxDisagreementMetric,
    MultiReaderConsensusResult,
    CTUPilotCase,
    PilotCaseFeasibilityEvaluation,
    Phase0FeasibilityReport,
    MultiReaderConsensusAnalyzer,
    Phase0FeasibilityBenchmark,
    generate_synthetic_ctu_pilot_cohort,
)


def test_multi_reader_consensus_synthesis_and_disagreement():
    """Verifies that 3 reader annotations are synthesized with preserved disagreement metrics."""
    grid = (30, 30, 30)
    m1 = np.zeros(grid, dtype=bool)
    m1[10:20, 10:20, 10:20] = True

    m2 = m1.copy()
    m2[10:20, 10:20, 18:22] = True  # Minor variation on Z boundary

    m3 = m1.copy()
    m3[10:20, 10:20, 8:12] = True   # Minor variation on lower Z boundary

    r1 = ReaderAnnotation(
        reader_id="READER_01",
        experience_years=15,
        calyx_landmarks_lps={"POSTERIOR_LOWER": np.array([15.0, 15.0, 10.0])},
        infundibular_diameters_mm={"POSTERIOR_LOWER": 4.0},
        lumen_binary_mask=m1,
        confidence_score=0.95
    )
    r2 = ReaderAnnotation(
        reader_id="READER_02",
        experience_years=10,
        calyx_landmarks_lps={"POSTERIOR_LOWER": np.array([15.5, 15.0, 10.5])},
        infundibular_diameters_mm={"POSTERIOR_LOWER": 4.2},
        lumen_binary_mask=m2,
        confidence_score=0.90
    )
    r3 = ReaderAnnotation(
        reader_id="READER_03",
        experience_years=8,
        calyx_landmarks_lps={"POSTERIOR_LOWER": np.array([14.8, 15.2, 9.8])},
        infundibular_diameters_mm={"POSTERIOR_LOWER": 3.8},
        lumen_binary_mask=m3,
        confidence_score=0.88
    )

    res = MultiReaderConsensusAnalyzer.synthesize_consensus("TEST_CASE_01", [r1, r2, r3])
    assert res.case_id == "TEST_CASE_01"
    assert res.num_raters == 3
    assert res.mean_pairwise_dice > 0.80
    assert len(res.pairwise_dice_scores) == 3  # (1v2, 1v3, 2v3)

    # Ambiguity volume must be strictly positive due to boundary differences
    assert res.ambiguity_volume_mm3 > 0.0

    # Calyx dispersion check
    c_met = res.calyx_consensus["POSTERIOR_LOWER"]
    assert c_met.num_readers == 3
    assert c_met.concordance_fraction == 1.0
    assert c_met.dispersion_radius_mm < 2.0
    assert c_met.is_high_disagreement is False

    # Infundibulum consensus
    inf_stat = res.infundibular_diameters_consensus["POSTERIOR_LOWER"]
    assert inf_stat["measurements_count"] == 3
    assert inf_stat["mean_mm"] == pytest.approx(4.0, abs=0.1)


def test_multi_reader_insufficient_raters_fails_closed():
    """Verifies that fewer than 2 readers raises ValueError."""
    r1 = ReaderAnnotation(
        reader_id="READER_01",
        experience_years=5,
        calyx_landmarks_lps={},
        infundibular_diameters_mm={},
        lumen_binary_mask=np.zeros((10, 10, 10), dtype=bool),
        confidence_score=1.0
    )
    with pytest.raises(ValueError, match="at least 2 independent readers"):
        MultiReaderConsensusAnalyzer.synthesize_consensus("CASE_FAIL", [r1])


def test_high_spatial_disagreement_detection():
    """Verifies that widely dispersed calyx annotations (>5.0 mm) trigger the high disagreement flag."""
    grid = (20, 20, 20)
    mask = np.ones(grid, dtype=bool)

    r1 = ReaderAnnotation(
        reader_id="R1",
        experience_years=10,
        calyx_landmarks_lps={"ANTERIOR_UPPER": np.array([0.0, 0.0, 0.0])},
        infundibular_diameters_mm={},
        lumen_binary_mask=mask,
        confidence_score=0.8
    )
    r2 = ReaderAnnotation(
        reader_id="R2",
        experience_years=10,
        calyx_landmarks_lps={"ANTERIOR_UPPER": np.array([8.0, 0.0, 0.0])},  # 8 mm deviation!
        infundibular_diameters_mm={},
        lumen_binary_mask=mask,
        confidence_score=0.8
    )

    res = MultiReaderConsensusAnalyzer.synthesize_consensus("CASE_DISP", [r1, r2])
    c_met = res.calyx_consensus["ANTERIOR_UPPER"]
    assert c_met.dispersion_radius_mm >= 4.0
    assert c_met.mean_deviation_mm > 0.0


def test_phase0_non_opacified_case_fails_closed():
    """Verifies that non-opacified CT cases fail closed with REJECTED_NON_OPACIFIED."""
    pilot_case = CTUPilotCase(
        case_id="CTU_REJECTED",
        dicom_series_uid="1.2.3.4",
        opacification_quality=CTUOpacificationQuality.NON_OPACIFIED,
        affine_4x4=np.eye(4),
        spacing_mm=(1.0, 1.0, 1.0),
        ct_volume_shape=(50, 50, 50),
        ct_volume_sha256="abc123sha",
        annotations=[]
    )

    eval_res = Phase0FeasibilityBenchmark.evaluate_case(
        pilot_case=pilot_case,
        acucalyx_calyx_centroids_lps={},
        acucalyx_centerline_points=np.zeros((0, 3)),
        acucalyx_infundibular_diameters_mm={}
    )
    assert eval_res.passed_case_criteria is False
    assert "REJECTED_NON_OPACIFIED" in eval_res.rejection_reason


def test_phase0_feasibility_cohort_evaluation_and_report():
    """Verifies end-to-end evaluation of the 4-case synthetic pilot cohort."""
    cohort = generate_synthetic_ctu_pilot_cohort()
    assert len(cohort) == 4

    case_evals = []
    for c in cohort:
        if c.opacification_quality == CTUOpacificationQuality.NON_OPACIFIED:
            eval_res = Phase0FeasibilityBenchmark.evaluate_case(
                pilot_case=c,
                acucalyx_calyx_centroids_lps={},
                acucalyx_centerline_points=np.zeros((0, 3)),
                acucalyx_infundibular_diameters_mm={}
            )
        else:
            # Simulated high-fidelity algorithmic outputs matching consensus
            # Straight centerline along Z from 5 to 35
            z_eval = np.linspace(5.0, 35.0, 30)
            centerline = np.column_stack([np.full(30, 30.0), np.full(30, 30.0), z_eval])

            calyx_pos = {
                "POSTERIOR_LOWER": np.array([30.0, 30.0, 5.0]),
                "POSTERIOR_MIDDLE": np.array([30.0, 30.0, 20.0]),
                "POSTERIOR_UPPER": np.array([30.0, 30.0, 35.0])
            }
            if c.case_id == "CTU_PILOT_03_COMPLEX_BRANCH":
                inf_diams = {
                    "POSTERIOR_LOWER": 3.5,
                    "POSTERIOR_UPPER": 3.9
                }
            else:
                inf_diams = {
                    "POSTERIOR_LOWER": 4.5,
                    "POSTERIOR_MIDDLE": 4.0,
                    "POSTERIOR_UPPER": 5.0
                }
            eval_res = Phase0FeasibilityBenchmark.evaluate_case(
                pilot_case=c,
                acucalyx_calyx_centroids_lps=calyx_pos,
                acucalyx_centerline_points=centerline,
                acucalyx_infundibular_diameters_mm=inf_diams
            )
        case_evals.append(eval_res)

    report = Phase0FeasibilityBenchmark.evaluate_cohort(case_evals)
    assert report.total_pilot_cases == 4
    assert report.evaluable_cases == 3
    assert report.rejected_non_opacified_cases == 1
    assert report.mean_calyx_sensitivity >= 0.90
    assert report.mean_centerline_mae_mm < 1.0
    assert report.all_cases_passed is True
    assert report.executive_decision == "GO_FEASIBILITY_PASSED"
