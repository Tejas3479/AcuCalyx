"""Unit Tests for AcuCalyx Clinical Readiness, Source Export, Calibration Gate, and Plan Fidelity.

Governed by ISO 14155:2026, ASTM F2554, 21 CFR Part 812, and 21 CFR Part 11.
"""

from __future__ import annotations

import pytest

from acucalyx.regulatory.plan_integrity import CanonicalPlan, PlanIntegrityEngine, PlanState
from acucalyx.clinical.source_export import (
    ClinicalSourceExporter,
    ClinicalSourceRecord,
    PlanAdoptionCategory,
)
from acucalyx.clinical.calibration_gate import (
    SiteCalibrationGate,
    SiteCalibrationRecord,
    SiteCalibrationCertificate,
)
from acucalyx.clinical.fidelity_evaluator import (
    PlanFidelityEvaluator,
    PlanFidelityResult,
)
from acucalyx.clinical.operational_metrics import (
    ClinicalMetricsAggregator,
    SiteOperationalSummary,
)


def _build_test_plan() -> CanonicalPlan:
    plan = CanonicalPlan(
        plan_id="PLAN-ACU-CLIN-001",
        patient_id="PAT-RESEARCH-7788",
        laterality="RIGHT",
        target_point_lps=(35.0, -95.0, 60.0),
        entry_point_lps=(80.0, -150.0, 50.0),
        carm_bullseye_angles=(28.0, -10.0),
        carm_progression_angles=(-62.0, -10.0),
        hazard_clearances_mm={"colon": 22.0, "pleura": 16.5},
        maximum_depth_mm=115.0,
        status=PlanState.APPROVED,
        approved_by="Dr. K. Patel, MD",
    )
    return PlanIntegrityEngine.seal_plan(plan, approved_by="Dr. K. Patel, MD")


# ============================================================================
# 1. Clinical Source Record Export & Integrity Tests
# ============================================================================

def test_clinical_source_record_creation_and_integrity() -> None:
    """Verify creation, canonical serialization, and tamper detection for Clinical Source Records."""
    plan = _build_test_plan()
    record = ClinicalSourceExporter.create_source_record(
        plan=plan,
        site_id="SITE-01-METRO",
        investigator_id="INV-001",
        study_id="ACU-PILOT-2026-01",
        adoption_category=PlanAdoptionCategory.ADOPTED_UNCHANGED,
    )

    assert record.record_id == "CSR-ACU-PILOT-2026-01-PLAN-ACU-CLIN-001"
    assert record.plan_adoption_category == PlanAdoptionCategory.ADOPTED_UNCHANGED
    assert record.patient_mrn_pseudo.startswith("ACU-")
    assert record.record_signature is not None

    # Verification must succeed on pristine record
    assert ClinicalSourceExporter.verify_source_record(record) is True

    # Tampering: alter planned entry coordinate
    record.planned_entry_lps = (record.planned_entry_lps[0] + 0.5, 0.0, 0.0)
    assert ClinicalSourceExporter.verify_source_record(record) is False


def test_clinical_source_record_plan_rejection_mandates_rationale() -> None:
    """Verify ISO 14155 protocol mandate: Category 4 rejection requires clinical rationale."""
    plan = _build_test_plan()

    # Rejection without rationale must raise ValueError
    with pytest.raises(ValueError, match="Plan rejection .* requires a documented clinical rationale"):
        ClinicalSourceExporter.create_source_record(
            plan=plan,
            site_id="SITE-01",
            investigator_id="INV-001",
            adoption_category=PlanAdoptionCategory.REJECTED,
            rejection_rationale="",
        )

    # Rejection with valid rationale succeeds
    record = ClinicalSourceExporter.create_source_record(
        plan=plan,
        site_id="SITE-01",
        investigator_id="INV-001",
        adoption_category=PlanAdoptionCategory.REJECTED,
        rejection_rationale="Patient respiratory motion observed; surgeon opted for lower pole anterior calyx.",
    )
    assert record.plan_adoption_category == PlanAdoptionCategory.REJECTED
    assert "respiratory motion" in record.rejection_rationale


# ============================================================================
# 2. Site C-Arm Calibration Gate Tests (ASTM F2554)
# ============================================================================

def test_site_calibration_gate_passing_dry_run() -> None:
    """Verify Site Calibration Gate certifies site when errors are within ASTM tolerances."""
    records = [
        SiteCalibrationRecord(
            trial_index=1,
            commanded_lao_rao_deg=25.0,
            measured_lao_rao_deg=25.4,
            commanded_cra_cau_deg=-10.0,
            measured_cra_cau_deg=-10.3,
            ground_truth_target_lps=(30.0, -80.0, 50.0),
            measured_target_lps=(30.5, -80.4, 50.2),
        ),
        SiteCalibrationRecord(
            trial_index=2,
            commanded_lao_rao_deg=-30.0,
            measured_lao_rao_deg=-29.6,
            commanded_cra_cau_deg=15.0,
            measured_cra_cau_deg=15.2,
            ground_truth_target_lps=(30.0, -80.0, 50.0),
            measured_target_lps=(30.2, -79.8, 50.3),
        ),
        SiteCalibrationRecord(
            trial_index=3,
            commanded_lao_rao_deg=0.0,
            measured_lao_rao_deg=0.2,
            commanded_cra_cau_deg=0.0,
            measured_cra_cau_deg=-0.1,
            ground_truth_target_lps=(30.0, -80.0, 50.0),
            measured_target_lps=(29.8, -80.1, 49.9),
        ),
    ]

    cert = SiteCalibrationGate.evaluate_site_calibration(
        site_id="SITE-01",
        carm_model="Siemens Cios Spin",
        records=records,
    )

    assert cert.is_certified is True
    assert cert.status == "CERTIFIED_PASS"
    assert cert.mean_angular_error_deg <= 2.0
    assert cert.mean_spatial_error_mm <= 2.0
    assert len(cert.reasons) == 0


def test_site_calibration_gate_rejects_excessive_errors() -> None:
    """Verify Site Calibration Gate rejects certification if angular or spatial errors exceed tolerance."""
    records = [
        SiteCalibrationRecord(
            trial_index=1,
            commanded_lao_rao_deg=25.0,
            measured_lao_rao_deg=28.5,  # 3.5 deg error
            commanded_cra_cau_deg=-10.0,
            measured_cra_cau_deg=-11.0,
            ground_truth_target_lps=(30.0, -80.0, 50.0),
            measured_target_lps=(33.0, -82.0, 50.0),  # >3.5 mm error
        ),
        SiteCalibrationRecord(
            trial_index=2,
            commanded_lao_rao_deg=25.0,
            measured_lao_rao_deg=28.0,
            commanded_cra_cau_deg=-10.0,
            measured_cra_cau_deg=-10.5,
            ground_truth_target_lps=(30.0, -80.0, 50.0),
            measured_target_lps=(32.5, -81.5, 50.0),
        ),
        SiteCalibrationRecord(
            trial_index=3,
            commanded_lao_rao_deg=25.0,
            measured_lao_rao_deg=27.5,
            commanded_cra_cau_deg=-10.0,
            measured_cra_cau_deg=-10.5,
            ground_truth_target_lps=(30.0, -80.0, 50.0),
            measured_target_lps=(32.0, -81.5, 50.0),
        ),
    ]

    cert = SiteCalibrationGate.evaluate_site_calibration(
        site_id="SITE-02",
        carm_model="Uncalibrated Unit",
        records=records,
    )

    assert cert.is_certified is False
    assert cert.status == "CALIBRATION_FAILED"
    assert any("angular error" in r for r in cert.reasons)
    assert any("spatial error" in r for r in cert.reasons)


def test_site_calibration_gate_requires_minimum_trials() -> None:
    """Verify Gate requires at least 3 distinct trials."""
    records = [
        SiteCalibrationRecord(
            trial_index=1,
            commanded_lao_rao_deg=0.0,
            measured_lao_rao_deg=0.0,
            commanded_cra_cau_deg=0.0,
            measured_cra_cau_deg=0.0,
            ground_truth_target_lps=(0.0, 0.0, 0.0),
            measured_target_lps=(0.0, 0.0, 0.0),
        )
    ]
    with pytest.raises(ValueError, match="requires at least 3"):
        SiteCalibrationGate.evaluate_site_calibration("SITE-01", "Model", records)


# ============================================================================
# 3. Plan-Execution Fidelity Evaluator Tests
# ============================================================================

def test_plan_fidelity_evaluator_concordant_trajectory() -> None:
    """Verify plan fidelity calculates accurate angles and confirms forniceal containment."""
    planned_entry = (100.0, -150.0, 50.0)
    planned_target = (50.0, -100.0, 50.0)

    # Actual needle tract closely matching planned (tip within 1.0 mm, angle < 2 deg)
    actual_entry = (101.0, -150.5, 50.2)
    actual_tip = (50.5, -99.8, 50.1)

    result = PlanFidelityEvaluator.evaluate_fidelity(
        case_id="CASE-001",
        planned_entry_lps=planned_entry,
        planned_target_lps=planned_target,
        actual_entry_lps=actual_entry,
        actual_tip_lps=actual_tip,
        forniceal_radius_mm=3.0,
    )

    assert result.target_zone_contained is True
    assert result.target_tip_error_mm <= 1.0
    assert result.angular_deviation_deg <= 2.0
    assert result.entry_deviation_mm <= 2.0
    assert result.is_concordant is True


def test_plan_fidelity_evaluator_detects_non_concordant_deviation() -> None:
    """Verify fidelity evaluator flags trajectory exceeding angular or target boundaries."""
    planned_entry = (100.0, -150.0, 50.0)
    planned_target = (50.0, -100.0, 50.0)

    # Needle tip misses target by 6 mm (outside 3 mm fornix zone)
    actual_entry = (100.0, -150.0, 50.0)
    actual_tip = (56.0, -100.0, 50.0)

    result = PlanFidelityEvaluator.evaluate_fidelity(
        case_id="CASE-002",
        planned_entry_lps=planned_entry,
        planned_target_lps=planned_target,
        actual_entry_lps=actual_entry,
        actual_tip_lps=actual_tip,
        forniceal_radius_mm=3.0,
    )

    assert result.target_zone_contained is False
    assert result.target_tip_error_mm >= 5.5
    assert result.is_concordant is False


# ============================================================================
# 4. Clinical Site Operational Metrics Aggregator Tests
# ============================================================================

def test_clinical_metrics_aggregator_site_summary() -> None:
    """Verify aggregation of clinical records into adoption metrics and compliance alerts."""
    plan = _build_test_plan()
    aggregator = ClinicalMetricsAggregator()

    # Ingest 3 records for SITE-01 (2 accepted, 1 modified)
    r1 = ClinicalSourceExporter.create_source_record(
        plan=plan,
        site_id="SITE-01",
        investigator_id="INV-01",
        adoption_category=PlanAdoptionCategory.ADOPTED_UNCHANGED,
    )
    r2 = ClinicalSourceExporter.create_source_record(
        plan=plan,
        site_id="SITE-01",
        investigator_id="INV-01",
        adoption_category=PlanAdoptionCategory.ALTERNATIVE_SELECTED,
    )
    r3 = ClinicalSourceExporter.create_source_record(
        plan=plan,
        site_id="SITE-01",
        investigator_id="INV-02",
        adoption_category=PlanAdoptionCategory.MANUALLY_ADJUSTED,
        interlocks_status={"U1_laterality": "FAIL", "U2_position": "PASS", "U5_depth": "PASS"},  # Trigger alert
    )

    aggregator.ingest_record(r1)
    aggregator.ingest_record(r2)
    aggregator.ingest_record(r3)

    summary = aggregator.generate_site_summary("SITE-01")

    assert summary.total_cases_recorded == 3
    assert summary.adoption_rate_pct == 100.0
    assert summary.rejection_rate_pct == 0.0
    assert summary.laterality_compliance_pct == 66.7  # 2 of 3 passed
    assert any("Laterality Gate compliance" in alert for alert in summary.compliance_alerts)
