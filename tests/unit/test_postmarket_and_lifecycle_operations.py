"""Unit tests for AcuCalyx Phase 10 (Milestones M7.5, M7.6 & M8).

Verifies eMDR decision-support triage, HL7 ICSR XML generation, Health Hazard
Assessments (HHA), Part 806 recall procedures, Postmarket Surveillance (PMS),
Medical Device File (MDF) indexing, and cryptographic patch verification with anti-downgrade.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from acucalyx.regulatory.patch_verifier import (
    PatchVerifier,
    SoftwarePatchPackage,
)
from ops.regulatory.emdr_icsr_builder import (
    ClinicalEventRecord,
    EmdrIcsrBuilder,
    ReportabilityCategory,
    ReportabilityTriageResult,
)
from ops.regulatory.health_hazard_assessor import (
    HazardProbability,
    HazardSeverity,
    HealthHazardAssessor,
    HealthHazardRecord,
    RiskPriorityLevel,
)
from ops.regulatory.mdf_indexer import (
    MdfAuditReport,
    MedicalDeviceFileIndexer,
)
from ops.regulatory.pms_analyzer import (
    PeriodicSafetySummary,
    PostmarketSurveillanceAnalyzer,
    TelemetryCaseEvent,
)


def test_emdr_decision_support_triage_and_statutory_deadlines():
    """Verify rule-based MDR triage logic across all statutory 21 CFR Part 803 scenarios."""
    builder = EmdrIcsrBuilder()

    # 1. 5-Day Emergency Remedial Action
    emergency_event = ClinicalEventRecord(
        event_id="EVT-2026-001",
        event_date="2026-10-15",
        patient_outcome="SERIOUS_INJURY",
        device_malfunction=True,
        malfunction_recurrence_risk=True,
        requires_emergency_remedial_action=True,
        event_description="Immediate remedial action mandated across hospital fleet.",
        patient_identifier="PAT-PMS-001",
    )
    triage_5day = builder.triage_event(emergency_event)
    assert triage_5day.category == ReportabilityCategory.MANDATORY_5_DAY_EMERGENCY
    assert triage_5day.is_reportable is True
    assert triage_5day.statutory_deadline_days == 5

    # 2. 30-Day Patient Death
    death_event = ClinicalEventRecord(
        event_id="EVT-2026-002",
        event_date="2026-10-15",
        patient_outcome="DEATH",
        device_malfunction=False,
        malfunction_recurrence_risk=False,
        requires_emergency_remedial_action=False,
        event_description="Fatal bleeding during percutaneous puncture.",
        patient_identifier="PAT-PMS-002",
    )
    triage_death = builder.triage_event(death_event)
    assert triage_death.category == ReportabilityCategory.MANDATORY_30_DAY_DEATH
    assert triage_death.is_reportable is True
    assert triage_death.statutory_deadline_days == 30

    # 3. 30-Day Serious Injury
    injury_event = ClinicalEventRecord(
        event_id="EVT-2026-003",
        event_date="2026-10-15",
        patient_outcome="SERIOUS_INJURY",
        device_malfunction=False,
        malfunction_recurrence_risk=False,
        requires_emergency_remedial_action=False,
        event_description="Retrorenal colon perforation requiring exploratory laparotomy.",
        patient_identifier="PAT-PMS-003",
    )
    triage_injury = builder.triage_event(injury_event)
    assert triage_injury.category == ReportabilityCategory.MANDATORY_30_DAY_SERIOUS_INJURY
    assert triage_injury.is_reportable is True
    assert triage_injury.statutory_deadline_days == 30

    # 4. 30-Day Reportable Malfunction
    malfunction_event = ClinicalEventRecord(
        event_id="EVT-2026-004",
        event_date="2026-10-15",
        patient_outcome="NO_INJURY",
        device_malfunction=True,
        malfunction_recurrence_risk=True,
        requires_emergency_remedial_action=False,
        event_description="Coordinate display inverted; caught by surgeon before puncture.",
        patient_identifier="PAT-PMS-004",
    )
    triage_malfunc = builder.triage_event(malfunction_event)
    assert triage_malfunc.category == ReportabilityCategory.MANDATORY_30_DAY_MALFUNCTION
    assert triage_malfunc.is_reportable is True
    assert triage_malfunc.statutory_deadline_days == 30

    # 5. Non-reportable complaint
    benign_event = ClinicalEventRecord(
        event_id="EVT-2026-005",
        event_date="2026-10-15",
        patient_outcome="NO_INJURY",
        device_malfunction=False,
        malfunction_recurrence_risk=False,
        requires_emergency_remedial_action=False,
        event_description="Clinician requested alternative color palette for display.",
        patient_identifier="PAT-PMS-005",
    )
    triage_benign = builder.triage_event(benign_event)
    assert triage_benign.category == ReportabilityCategory.NON_REPORTABLE_INTERNAL_COMPLAINT
    assert triage_benign.is_reportable is False
    assert triage_benign.statutory_deadline_days == 0


def test_emdr_hl7_icsr_xml_generation_completeness():
    """Verify HL7 ICSR XML generation conforming to Form FDA 3500A electronic submission standards."""
    builder = EmdrIcsrBuilder()

    record = ClinicalEventRecord(
        event_id="MDR-2026-0012",
        event_date="20261015",
        patient_outcome="SERIOUS_INJURY",
        device_malfunction=True,
        malfunction_recurrence_risk=True,
        requires_emergency_remedial_action=False,
        event_description="Pleural puncture requiring chest tube insertion.",
        patient_identifier="PAT-ANON-9812",
        udi_placeholder="(01)00860000000001",
        software_version="1.0.0",
        build_id="ACU-CORE-COMMERCIAL-20261015-BLD01",
        plan_signature="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    triage = builder.triage_event(record)
    assert triage.is_reportable is True

    xml_output = builder.build_hl7_icsr_xml(
        record=record,
        triage=triage,
        authorized_by="Elena Rostova, RAC (Director Regulatory Affairs)",
        signoff_notes="Reportability confirmed under 21 CFR 803. Serious injury with device involvement.",
    )

    # Validate structural XML markers
    assert '<?xml version="1.0" encoding="UTF-8"?>' in xml_output
    assert '<MCCI_IN200100UV01' in xml_output
    assert '<PORX_IN040006UV>' in xml_output
    assert 'extension="MDR-2026-0012"' in xml_output
    assert '(01)00860000000001' in xml_output
    assert 'Elena Rostova, RAC' in xml_output
    assert record.plan_signature in xml_output

    # Attempting to generate XML for non-reportable event must raise ValueError
    benign_record = ClinicalEventRecord(
        event_id="EVT-BENIGN",
        event_date="20261015",
        patient_outcome="NO_INJURY",
        device_malfunction=False,
        malfunction_recurrence_risk=False,
        requires_emergency_remedial_action=False,
        event_description="Cosmetic UI font feedback.",
        patient_identifier="PAT-000",
    )
    benign_triage = builder.triage_event(benign_record)
    with pytest.raises(ValueError, match="Cannot generate eMDR"):
        builder.build_hl7_icsr_xml(benign_record, benign_triage, "RA", "notes")


def test_health_hazard_assessor_risk_prioritization_and_fsn():
    """Verify quantitative Health Hazard Assessment (HHA), FSN generation, and 10-day FDA reports."""
    assessor = HealthHazardAssessor()

    # 1. Critical S1 + High P1 -> Urgent Correction
    crit_record = HealthHazardRecord(
        assessment_id="HHA-2026-01",
        anomaly_id="BUG-2026-CRIT-99",
        defect_description="Coordinate transform calculation sign inversion on rare DICOM series.",
        clinical_hazard="Potential incorrect needle entry trajectory leading to retroperitoneal hematoma.",
        severity=HazardSeverity.CRITICAL_S1,
        probability=HazardProbability.HIGH_P1,
        units_distributed=25,
    )
    priority_crit, rationale_crit = assessor.evaluate_hazard(crit_record)
    assert priority_crit == RiskPriorityLevel.PRIORITY_URGENT_CORRECTION
    assert "urgent customer Field Safety Notice" in rationale_crit

    # 2. Generate customer Field Safety Notice (FSN)
    fsn_text = assessor.generate_field_safety_notice(
        record=crit_record,
        priority=priority_crit,
        interim_mitigation="Surgeons must verify laterality landmarks under biplanar fluoroscopy before puncture.",
        patch_version="1.0.1",
    )
    assert "URGENT MEDICAL DEVICE SAFETY NOTICE: FIELD CORRECTION" in fsn_text
    assert "BUG-2026-CRIT-99" in fsn_text
    assert "25 active hospital installations" in fsn_text
    assert "Version 1.0.1" in fsn_text

    # 3. Generate 10-day written report to FDA District Office
    fda_report = assessor.build_10_day_fda_district_report(
        record=crit_record,
        priority=priority_crit,
        fsn_text=fsn_text,
    )
    assert "REPORT OF MEDICAL DEVICE CORRECTION OR REMOVAL (21 CFR 806.10)" in fda_report
    assert "Units in Distribution: 25" in fda_report
    assert "URGENT MEDICAL DEVICE SAFETY NOTICE" in fda_report

    # 4. Minor S3 + Low P3 -> Routine Maintenance
    minor_record = HealthHazardRecord(
        assessment_id="HHA-2026-02",
        anomaly_id="BUG-2026-MIN-01",
        defect_description="Display text clipping in secondary settings menu.",
        clinical_hazard="Zero clinical impact; cosmetic layout truncation.",
        severity=HazardSeverity.MINOR_S3,
        probability=HazardProbability.LOW_P3,
        units_distributed=25,
    )
    priority_minor, _ = assessor.evaluate_hazard(minor_record)
    assert priority_minor == RiskPriorityLevel.PRIORITY_ROUTINE_MAINTENANCE


def test_postmarket_surveillance_telemetry_and_complaint_signal_detection():
    """Verify PMS telemetry aggregation, complaint rate trending, and statistical signal detection."""
    pms = PostmarketSurveillanceAnalyzer()

    # 1. Ingest 1,000 clean clinical telemetry cases
    for i in range(1000):
        pms.ingest_event(
            TelemetryCaseEvent(
                case_id=f"CASE-PMS-{i:04d}",
                site_id="SITE-01",
                software_version="1.0.0",
                pipeline_success=True,
                qc_passed=True,
                clavien_dindo_grade=0,
            )
        )

    # Clean state: 0 complaints -> Acceptable
    summary_clean = pms.generate_periodic_safety_summary(complaint_rate_threshold_per_thousand=5.0)
    assert summary_clean.total_cases_processed == 1000
    assert summary_clean.pipeline_success_rate == 1.0
    assert summary_clean.complaint_rate_per_thousand == 0.0
    assert summary_clean.is_safety_profile_acceptable is True

    # 2. Log 8 complaints -> Complaint rate = 8.0 / 1,000 > threshold 5.0 / 1,000
    for c in range(8):
        pms.log_complaint(
            complaint_id=f"CMP-2026-{c:03d}",
            severity="MODERATE",
            description="DICOM PACS transfer timeout during peak hours.",
        )

    summary_spiked = pms.generate_periodic_safety_summary(complaint_rate_threshold_per_thousand=5.0)
    assert summary_spiked.total_complaints == 8
    assert summary_spiked.complaint_rate_per_thousand == 8.0
    assert summary_spiked.is_safety_profile_acceptable is False
    assert any("SIGNAL_DETECTED" in note for note in summary_spiked.trending_notes)


def test_medical_device_file_audit_and_commercial_baseline_validation():
    """Verify Medical Device File (MDF) indexing per ISO 13485 Clause 4.2.3 and release naming checks."""
    indexer = MedicalDeviceFileIndexer()

    # 1. Audit MDF files in workspace
    report: MdfAuditReport = indexer.audit_mdf()
    assert report.is_mdf_complete is True, f"MDF incomplete: {report.missing_sections}"
    assert report.sections_verified >= 9
    assert len(report.missing_sections) == 0

    # 2. Validate valid commercial baseline name
    ok_comm, errs_comm = indexer.validate_commercial_baseline_readiness(
        target_build_id="ACU-CORE-COMMERCIAL-20261015-BLD01",
        target_version="1.0.0",
    )
    assert ok_comm is True
    assert len(errs_comm) == 0

    # 3. Reject pre-release tags in commercial baseline
    bad_comm, bad_errs = indexer.validate_commercial_baseline_readiness(
        target_build_id="ACU-CORE-20261001-BLD01",
        target_version="1.0.0-RC1",
    )
    assert bad_comm is False
    assert any("INVALID_BUILD_NAME" in e for e in bad_errs)
    assert any("PREMARKET_TAG_PROHIBITED" in e for e in bad_errs)


def test_software_patch_verifier_signatures_digest_and_anti_downgrade():
    """Verify cryptographic patch signature checking, SHA-256 digest checks, and anti-downgrade guard."""
    verifier = PatchVerifier(current_installed_version="1.0.0")

    payload = b"VALID_PATCH_BINARY_CONTENTS_v1.0.1"
    build_id = "ACU-PATCH-20261101-BLD02"
    correct_digest = verifier.compute_sha256(payload)
    correct_sig = verifier.compute_signature(payload, build_id)

    # 1. Valid forward patch (1.0.1 >= 1.0.0)
    valid_patch = SoftwarePatchPackage(
        package_id="PATCH-001",
        target_version="1.0.1",
        build_id=build_id,
        payload_bytes=payload,
        sha256_digest=correct_digest,
        digital_signature=correct_sig,
    )
    res_valid = verifier.verify_patch(valid_patch)
    assert res_valid.is_valid is True
    assert res_valid.digest_verified is True
    assert res_valid.signature_verified is True
    assert res_valid.monotonicity_passed is True

    # 2. Corrupted payload (SHA-256 mismatch)
    corrupted_patch = SoftwarePatchPackage(
        package_id="PATCH-002",
        target_version="1.0.1",
        build_id=build_id,
        payload_bytes=payload + b"_CORRUPTED",
        sha256_digest=correct_digest,
        digital_signature=correct_sig,
    )
    res_corrupted = verifier.verify_patch(corrupted_patch)
    assert res_corrupted.is_valid is False
    assert res_corrupted.digest_verified is False
    assert any("DIGEST_MISMATCH" in r for r in res_corrupted.failure_reasons)

    # 3. Forged digital signature
    forged_patch = SoftwarePatchPackage(
        package_id="PATCH-003",
        target_version="1.0.1",
        build_id=build_id,
        payload_bytes=payload,
        sha256_digest=correct_digest,
        digital_signature="0000000000000000000000000000000000000000000000000000000000000000",
    )
    res_forged = verifier.verify_patch(forged_patch)
    assert res_forged.is_valid is False
    assert res_forged.signature_verified is False
    assert any("INVALID_SIGNATURE" in r for r in res_forged.failure_reasons)

    # 4. Anti-Downgrade Rollback Attack (0.9.0 < 1.0.0)
    downgrade_payload = b"OLD_VULNERABLE_BINARY_v0.9.0"
    downgrade_digest = verifier.compute_sha256(downgrade_payload)
    downgrade_sig = verifier.compute_signature(downgrade_payload, build_id)

    downgrade_patch = SoftwarePatchPackage(
        package_id="PATCH-004",
        target_version="0.9.0",
        build_id=build_id,
        payload_bytes=downgrade_payload,
        sha256_digest=downgrade_digest,
        digital_signature=downgrade_sig,
    )
    res_downgrade = verifier.verify_patch(downgrade_patch)
    assert res_downgrade.is_valid is False
    assert res_downgrade.monotonicity_passed is False
    assert any("DOWNGRADE_PROHIBITED" in r for r in res_downgrade.failure_reasons)
