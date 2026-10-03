"""Unit tests for AcuCalyx Milestone M7 (Premarket Regulatory Submission & Design Release Gate).

Verifies evidence catalog completeness, artifact cryptographic integrity,
configuration baseline plan fingerprinting, submission completeness auditing,
controlled labeling verification, DICOM PS 3.2 interoperability contracts,
and the ISO 13485 / QMSR Design & Development Release Authorization gate.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from acucalyx.dicom.interoperability_harness import (
    DicomDatasetMetadata,
    DicomInteroperabilityHarness,
    SOP_UID_CT_IMAGE_STORAGE,
    SOP_UID_ENHANCED_CT_STORAGE,
    SOP_UID_SECONDARY_CAPTURE_STORAGE,
    SOP_UID_XRAY_ANGIOGRAPHIC_STORAGE,
    TS_EXPLICIT_VR_LITTLE_ENDIAN,
    TS_IMPLICIT_VR_LITTLE_ENDIAN,
)
from acucalyx.regulatory.anomaly_management import (
    AnomalyManager,
    AnomalySeverity,
    AnomalyState,
    SoftwareAnomaly,
)
from acucalyx.regulatory.artifact_integrity import (
    ArtifactFingerprint,
    ArtifactIntegrityAuditor,
)
from acucalyx.regulatory.configuration_baseline import (
    SoftwareConfigurationIndex,
    get_current_configuration_baseline,
)
from acucalyx.regulatory.evidence_index import (
    EvidenceCategory,
    EvidenceItem,
    RegulatoryEvidenceCatalog,
)
from acucalyx.regulatory.labeling_checker import LabelingChecker
from acucalyx.regulatory.release_gate import (
    ReleaseAuthorizationDecision,
    ReleaseGateEvaluator,
)
from acucalyx.regulatory.submission_completeness import (
    SubmissionCompletenessChecker,
    SubmissionCompletenessReport,
)


def test_regulatory_evidence_catalog_completeness():
    """Verify evidence catalog registers all required premarket submission items across 14 categories."""
    catalog = RegulatoryEvidenceCatalog()
    items = catalog.list_all_items()

    # Must contain at least 20 primary evidence records
    assert len(items) >= 20

    # Verify key evidence deliverables exist in the catalog
    ref_ids = {item.reference_id for item in items}
    assert "DOC-REG-08" in ref_ids  # DICOM PS 3.2 Conformance Statement
    assert "DOC-REG-09" in ref_ids  # Operator's Manual & 21 CFR 801 Labeling
    assert "DOC-REG-10" in ref_ids  # Internal Evidence Dossier Map for eSTAR v7.1
    assert "DOC-REG-11" in ref_ids  # Design Release Authorization Record
    assert "DOC-REG-12" in ref_ids  # AI/ML System Inventory & PCCP
    assert "DOC-REG-13" in ref_ids  # SOUP Management Register
    assert "DOC-REG-14" in ref_ids  # Postmarket Surveillance & MDR Plan
    assert "DOC-CLN-01" in ref_ids  # ACU-PILOT-01 CIP

    # Verify all categories have at least one registered item
    for category in EvidenceCategory:
        category_items = catalog.get_items_by_category(category)
        assert len(category_items) > 0, f"Evidence category {category} has no registered items."


def test_artifact_integrity_auditor_hashing_and_tamper_detection(tmp_path: Path):
    """Verify SHA-256 hashing, missing file detection, and manifest tamper detection."""
    auditor = ArtifactIntegrityAuditor(workspace_root=tmp_path)

    # 1. Create a controlled artifact
    test_file = tmp_path / "test_artifact.md"
    test_file.write_text("Controlled Content Baseline v1.0", encoding="utf-8")

    fp = auditor.inspect_artifact("test_artifact.md")
    assert fp.exists is True
    assert len(fp.sha256_hash) == 64
    assert fp.byte_size > 0

    # 2. Audit valid manifest
    manifest = {"test_artifact.md": fp.sha256_hash}
    passed, reasons = auditor.audit_manifest(manifest)
    assert passed is True
    assert len(reasons) == 0

    # 3. Detect file tampering
    tampered_manifest = {"test_artifact.md": "0000000000000000000000000000000000000000000000000000000000000000"}
    passed_tamper, reasons_tamper = auditor.audit_manifest(tampered_manifest)
    assert passed_tamper is False
    assert any("HASH_MISMATCH" in r for r in reasons_tamper)

    # 4. Detect missing file
    missing_manifest = {"nonexistent_file.md": fp.sha256_hash}
    passed_missing, reasons_missing = auditor.audit_manifest(missing_manifest)
    assert passed_missing is False
    assert any("MISSING_ARTIFACT" in r for r in reasons_missing)


def test_software_configuration_baseline_immutability_and_fingerprinting():
    """Verify configuration baseline parameters and cryptographic case-plan binding."""
    baseline = get_current_configuration_baseline()

    assert baseline.application_version == "1.0.0-RC1"
    assert baseline.software_build_id == "ACU-CORE-20261001-BLD01"
    assert baseline.git_release_tag == "release/v1.0.0-submission"
    assert len(baseline.ai_model_weights_sha256) == 64
    assert baseline.cyclonedx_format_version == "1.5"

    case_uuid = "CASE-2026-PCNL-001"
    target_lps = (25.4, -142.1, 88.0)
    entry_lps = (78.2, -185.3, 72.5)
    carm_profile = "GE_OEC_9900"

    # Compute plan signature
    sig1 = baseline.compute_case_plan_fingerprint(
        case_uuid=case_uuid,
        target_coords_lps=target_lps,
        entry_coords_lps=entry_lps,
        carm_profile_id=carm_profile,
    )
    assert len(sig1) == 64

    # Verify signature
    assert baseline.verify_plan_fingerprint(
        case_uuid=case_uuid,
        target_coords_lps=target_lps,
        entry_coords_lps=entry_lps,
        carm_profile_id=carm_profile,
        claimed_signature=sig1,
    ) is True

    # Tampering with target coords must invalidate signature
    tampered_target = (25.5, -142.1, 88.0)
    assert baseline.verify_plan_fingerprint(
        case_uuid=case_uuid,
        target_coords_lps=tampered_target,
        entry_coords_lps=entry_lps,
        carm_profile_id=carm_profile,
        claimed_signature=sig1,
    ) is False

    # Verify JSON export
    json_str = baseline.to_json()
    assert "ACU-CORE-20261001-BLD01" in json_str


def test_submission_completeness_checker_against_repository():
    """Verify submission completeness auditor against the active repository."""
    checker = SubmissionCompletenessChecker()
    report: SubmissionCompletenessReport = checker.audit_submission()

    assert report.total_items_checked >= 20
    assert len(report.missing_items) == 0, f"Missing submission deliverables: {report.missing_items}"
    assert len(report.version_inconsistencies) == 0, f"Version mismatches: {report.version_inconsistencies}"
    assert report.rtm_closure_passed is True
    assert report.estar_ready is True
    assert report.is_complete is True


def test_labeling_checker_validation_rules():
    """Verify labeling checker on controlled document, valid splash, and malformed texts."""
    checker = LabelingChecker()

    # 1. Audit actual Operator's Manual file
    ops_manual = Path("docs/regulatory/09_OPERATORS_MANUAL_AND_LABELING.md")
    assert ops_manual.exists()
    passed, failures = checker.audit_labeling_file(ops_manual)
    assert passed is True, f"Operator's manual labeling audit failed: {failures}"

    # 2. Audit UI splash payload
    valid_payload = {
        "trade_name": "AcuCalyx™ Core",
        "version": "1.0.0-RC1",
        "rx_notice": "CAUTION: Federal law (USA) restricts this device to sale by or on the order of a licensed physician (Rx Only).",
    }
    ui_passed, ui_failures = checker.audit_ui_splash_payload(valid_payload)
    assert ui_passed is True

    # 3. Detect missing Rx notice in UI payload
    invalid_payload = {
        "trade_name": "AcuCalyx™ Core",
        "version": "1.0.0-RC1",
        "rx_notice": "For research use only",
    }
    ui_fail_passed, ui_fail_reasons = checker.audit_ui_splash_payload(invalid_payload)
    assert ui_fail_passed is False
    assert any("UI_MISSING_RX" in r for r in ui_fail_reasons)

    # 4. Audit planning card export
    valid_card = (
        "AcuCalyx™ Core Sterile Planning Card | Rx Only\n"
        "Attending surgeon retains sole clinical authority over needle puncture."
    )
    card_passed, card_failures = checker.audit_export_planning_card(valid_card)
    assert card_passed is True


def test_dicom_interoperability_harness_contracts():
    """Verify DICOM PS 3.2 conformance, Secondary Capture DRR semantics, and operating envelope rules."""
    harness = DicomInteroperabilityHarness(ae_title="ACUCALYX_AE")

    # 1. Valid axial CT within operating envelope
    valid_ct = DicomDatasetMetadata(
        sop_class_uid=SOP_UID_CT_IMAGE_STORAGE,
        transfer_syntax_uid=TS_EXPLICIT_VR_LITTLE_ENDIAN,
        patient_id="PATIENT_001",
        patient_name="DOE^JOHN",
        gantry_tilt=0.0,
        slice_thickness=1.25,
    )
    ok, err = harness.evaluate_ct_ingestion_eligibility(valid_ct)
    assert ok is True
    assert err is None

    # 2. Ingestion rejection: Non-zero gantry tilt
    tilted_ct = DicomDatasetMetadata(
        sop_class_uid=SOP_UID_CT_IMAGE_STORAGE,
        transfer_syntax_uid=TS_EXPLICIT_VR_LITTLE_ENDIAN,
        patient_id="PATIENT_002",
        patient_name="DOE^JANE",
        gantry_tilt=12.5,
        slice_thickness=1.25,
    )
    ok_tilt, err_tilt = harness.evaluate_ct_ingestion_eligibility(tilted_ct)
    assert ok_tilt is False
    assert "ERR_INPUT_REJECTED_GANTRY_TILT" in err_tilt

    # 3. Ingestion rejection: Excessive slice thickness (> 2.5 mm)
    thick_ct = DicomDatasetMetadata(
        sop_class_uid=SOP_UID_CT_IMAGE_STORAGE,
        transfer_syntax_uid=TS_EXPLICIT_VR_LITTLE_ENDIAN,
        patient_id="PATIENT_003",
        patient_name="SMITH^BOB",
        gantry_tilt=0.0,
        slice_thickness=3.75,
    )
    ok_thick, err_thick = harness.evaluate_ct_ingestion_eligibility(thick_ct)
    assert ok_thick is False
    assert "ERR_INPUT_REJECTED_SLICE_THICKNESS" in err_thick

    # 4. Valid Secondary Capture DRR Export
    drr_meta = harness.create_drr_secondary_capture_metadata(
        carm_angles_desc="CRA 15°, LAO 20°, SID 1000mm",
        patient_id="PATIENT_001",
        patient_name="DOE^JOHN",
    )
    assert drr_meta.sop_class_uid == SOP_UID_SECONDARY_CAPTURE_STORAGE
    assert drr_meta.conversion_type == "SYN"
    valid_drr, drr_err = harness.validate_drr_export_semantics(drr_meta)
    assert valid_drr is True
    assert drr_err is None

    # 5. Semantic DRR violation: Encoding synthetic DRR as live XA acquisition
    illegal_xa_drr = DicomDatasetMetadata(
        sop_class_uid=SOP_UID_XRAY_ANGIOGRAPHIC_STORAGE,
        transfer_syntax_uid=TS_EXPLICIT_VR_LITTLE_ENDIAN,
        patient_id="PATIENT_001",
        patient_name="DOE^JOHN",
        gantry_tilt=0.0,
        slice_thickness=0.0,
        conversion_type="SYN",
        modality="XA",
    )
    illegal_ok, illegal_err = harness.validate_drr_export_semantics(illegal_xa_drr)
    assert illegal_ok is False
    assert "SEMANTIC_VIOLATION" in illegal_err

    # 6. DICOM PS 3.15 De-Identification
    anon_meta = harness.apply_ps315_deidentification(valid_ct)
    assert anon_meta.patient_name == "ANONYMIZED^PATIENT"
    assert anon_meta.patient_id.startswith("ANON_")
    assert anon_meta.patient_id != valid_ct.patient_id


def test_design_release_authorization_gate_execution():
    """Verify ISO 13485 Clause 7.3.7 Design & Development Release Authorization gate."""
    evaluator = ReleaseGateEvaluator()

    # 1. Full release evaluation on clean repository baseline
    decision: ReleaseAuthorizationDecision = evaluator.evaluate_release(
        simulated_vv_pass_rate=1.0,
        unmitigated_kev_cves=0,
    )

    assert decision.is_authorized is True, f"Release blocked: {decision.blocking_reasons}"
    assert decision.software_build_id == "ACU-CORE-20261001-BLD01"
    assert decision.application_version == "1.0.0-RC1"
    assert len(decision.blocking_reasons) == 0

    # Verify all 8 dimensions passed
    assert len(decision.dimension_results) == 8
    for dim_name, passed in decision.dimension_results.items():
        assert passed is True, f"Dimension {dim_name} failed release audit."

    # 2. Verify release gate blocks on open Severity 1 anomaly
    blocked_anomaly_manager = AnomalyManager()
    blocked_anomaly_manager.report_anomaly(
        title="Critical Hilum Boundary Segmentation Glitch",
        severity=AnomalySeverity.SEV_1_CRITICAL,
        component="AnatomicalSegmentation",
        description="Rare hilum boundary clipping under severe streak.",
        steps_to_reproduce="Run on high streak CT.",
    )
    blocked_evaluator = ReleaseGateEvaluator(anomaly_manager=blocked_anomaly_manager)
    blocked_decision = blocked_evaluator.evaluate_release()

    assert blocked_decision.is_authorized is False
    assert any("DIM4_FAILURE" in r for r in blocked_decision.blocking_reasons)

    # 3. Verify release gate blocks on V&V pass rate < 1.0
    failed_vv_decision = evaluator.evaluate_release(simulated_vv_pass_rate=0.98)
    assert failed_vv_decision.is_authorized is False
    assert any("DIM3_FAILURE" in r for r in failed_vv_decision.blocking_reasons)
