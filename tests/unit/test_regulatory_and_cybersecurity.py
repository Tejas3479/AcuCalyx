"""Unit and Integration Tests for AcuCalyx Regulatory Controls & Premarket Cybersecurity.

Governed by FDA QMSR, ISO 13485:2016, IEC 62304:2006+A1:2015, ISO 14971:2019,
and FDA Premarket Cybersecurity Guidance (Feb 2026) / FD&C Act §524B.
"""

from __future__ import annotations

import json
import pytest
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian

from acucalyx.regulatory.traceability import (
    TraceabilityEngine,
    TraceabilityNode,
    TraceabilityTier,
    build_acucalyx_default_rtm,
)
from acucalyx.regulatory.plan_integrity import (
    CanonicalPlan,
    PlanIntegrityEngine,
    PlanState,
    PlanTamperError,
    PlanStaleError,
)
from acucalyx.regulatory.safety_boundary import (
    SafetyBoundaryController,
    SoftwareSafetyClass,
    SafetyPartition,
    DataContractViolationError,
)
from acucalyx.regulatory.anomaly_management import (
    AnomalyManager,
    AnomalySeverity,
    AnomalyState,
)
from acucalyx.cybersecurity.sbom_generator import (
    SBOMGenerator,
    SBOMComponent,
    SBOMFormat,
)
from acucalyx.cybersecurity.phi_guard import (
    PHIGuard,
    DeIdentificationProfile,
    HMACPseudonymizer,
)
from acucalyx.cybersecurity.threat_model import (
    STRIDEEvaluator,
    ThreatCategory,
    SecurityRole,
    PrivilegeEscalationError,
    MalformedDicomError,
)
from acucalyx.cybersecurity.soup_register import (
    SOUPRegistry,
    SOUPRecord,
)


# ============================================================================
# 1. 10-Tier Requirements Traceability Matrix (RTM) Tests
# ============================================================================

def test_rtm_10_tier_traceability_closure() -> None:
    """Verify that default AcuCalyx RTM achieves 100% forward and backward closure."""
    rtm = build_acucalyx_default_rtm()
    closure = rtm.validate_closure()

    assert closure["is_closed"] is True, f"RTM closure failed: {closure}"
    assert len(closure["orphaned_nodes"]) == 0
    assert len(closure["unmitigated_hazards"]) == 0
    assert len(closure["untested_requirements"]) == 0
    assert closure["total_nodes"] >= 40

    # Test forward traversal from Clinical Need to Validation Evidence
    fwd_paths = rtm.forward_trace("CN-01")
    assert len(fwd_paths) > 0
    assert any("VAL-M1-CT" in path or "VAL-M2-CLINICAL" in path or "VAL-M3-PHANTOM" in path for path in fwd_paths)

    # Test backward traversal from Milestone M5 Regulatory Evidence to Root
    bwd_paths = rtm.backward_trace("VAL-M5-REGULATORY")
    assert len(bwd_paths) > 0
    assert any("CN-05" in path for path in bwd_paths)


def test_rtm_detects_orphaned_nodes_and_untested_requirements() -> None:
    """Verify RTM engine correctly catches orphaned nodes and unverified requirements."""
    rtm = build_acucalyx_default_rtm()

    # Add an unlinked rogue software requirement
    rogue_swrs = TraceabilityNode(
        id="SwRS-999",
        tier=TraceabilityTier.SOFTWARE_REQUIREMENT,
        title="Rogue Unverified Requirement",
        description="Testing orphan detection.",
    )
    rtm.add_node(rogue_swrs)

    closure = rtm.validate_closure()
    assert closure["is_closed"] is False
    assert "SwRS-999" in closure["orphaned_nodes"]
    assert "SwRS-999" in closure["untested_requirements"]


# ============================================================================
# 2. Cryptographic Plan Integrity & Anti-Tamper Tests
# ============================================================================

def _create_sample_plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="PLAN-2026-PCNL-001",
        patient_id="PAT-98421",
        laterality="RIGHT",
        target_point_lps=(42.5000, -112.3000, 85.0000),
        entry_point_lps=(88.2500, -165.7500, 72.1000),
        carm_bullseye_angles=(25.5, -12.0),
        carm_progression_angles=(-64.5, -12.0),
        hazard_clearances_mm={"colon": 18.5, "pleura": 14.2, "aorta": 32.0},
        maximum_depth_mm=124.5,
        status=PlanState.DRAFT,
        timestamp_utc="2026-09-30T12:00:00Z",
    )


def test_canonical_plan_serialization_determinism() -> None:
    """Verify that canonical JSON serialization is deterministic and key-order independent."""
    plan1 = _create_sample_plan()
    plan2 = _create_sample_plan()

    # Even if internal dict keys vary, canonical serialization must match
    str1 = plan1.serialize_canonical_json()
    str2 = plan2.serialize_canonical_json()
    assert str1 == str2

    fp1 = PlanIntegrityEngine.compute_fingerprint(plan1)
    fp2 = PlanIntegrityEngine.compute_fingerprint(plan2)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex string


def test_cryptographic_plan_fingerprint_anti_tamper() -> None:
    """Verify that modifying coordinates triggers PLAN_HASH_MISMATCH and locks plan."""
    plan = _create_sample_plan()
    PlanIntegrityEngine.seal_plan(plan, approved_by="Dr. K. Patel, MD")

    # Verification on unmodified plan must pass
    assert PlanIntegrityEngine.verify_plan(plan) is True
    assert plan.status == PlanState.APPROVED

    # Attacker alters skin entry X by only +0.05 mm
    tampered = PlanIntegrityEngine.simulate_tampering_attack(plan, (0.05, 0.0, 0.0))

    with pytest.raises(PlanTamperError, match="PLAN_HASH_MISMATCH"):
        PlanIntegrityEngine.verify_plan(tampered)

    assert tampered.status == PlanState.TAMPERED_LOCK


def test_stale_plan_invalidation_prevents_verification() -> None:
    """Verify that superseded STALE plans cannot be verified or executed."""
    plan = _create_sample_plan()
    PlanIntegrityEngine.seal_plan(plan, approved_by="Dr. K. Patel, MD")
    plan.status = PlanState.STALE

    with pytest.raises(PlanStaleError, match="is marked STALE"):
        PlanIntegrityEngine.verify_plan(plan)


# ============================================================================
# 3. IEC 62304 Safety Boundary & Partitioning Tests
# ============================================================================

def test_iec62304_safety_boundary_mutation_guard() -> None:
    """Verify that Non-Safety UI (Class A) cannot mutate Safety Core (Class C)."""
    controller = SafetyBoundaryController()

    # Safety Core mutating itself is permitted
    assert controller.validate_mutation_permission(
        SafetyPartition.SAFETY_CORE, SafetyPartition.SAFETY_CORE
    ) is True

    # Non-Safety UI attempting to mutate Safety Core must be blocked
    with pytest.raises(DataContractViolationError, match="SAFETY BOUNDARY VIOLATION"):
        controller.validate_mutation_permission(
            SafetyPartition.NON_SAFETY_UI, SafetyPartition.SAFETY_CORE
        )


def test_safety_boundary_sanitizes_ui_payload() -> None:
    """Verify that dangerous planning overrides are stripped from non-safety UI payloads."""
    controller = SafetyBoundaryController()
    ui_payload = {
        "camera_zoom": 1.25,
        "mesh_color": "#00FFAA",
        "target_point_lps": (0.0, 0.0, 0.0),  # Forbidden override
        "hazard_clearances_mm": {"colon": 0.0},  # Forbidden override
        "viewport_width": 1920,
    }

    sanitized = controller.sanitize_ui_payload(ui_payload)
    assert "camera_zoom" in sanitized
    assert "mesh_color" in sanitized
    assert "target_point_lps" not in sanitized
    assert "hazard_clearances_mm" not in sanitized


def test_safety_boundary_enforces_fail_closed_contract() -> None:
    """Verify that safety controller returns fail-closed state on calculation error."""
    controller = SafetyBoundaryController()
    result = controller.enforce_fail_closed_contract(
        calculation_successful=False,
        error_code="ERR_HAZARD_COLON_VIOLATION",
    )

    assert result["status"] == "FAIL_CLOSED_NO_PLAN"
    assert result["feasible"] is False
    assert result["rehearsal_permitted"] is False
    assert result["trajectories"] == []


# ============================================================================
# 4. IEC 62304 Clause 9 Software Anomaly Management Tests
# ============================================================================

def test_iec62304_anomaly_management_lifecycle_and_release_gate() -> None:
    """Verify anomaly lifecycle and prohibition of release with open Sev 1/2 defects."""
    mgr = AnomalyManager()

    # Initially no defects; release permitted
    can_rel, reasons = mgr.can_release_software()
    assert can_rel is True

    # Report a Sev 1 Critical defect
    aid = mgr.report_anomaly(
        title="Colonic Distance Field Boundary Flaw",
        severity=AnomalySeverity.SEV_1_CRITICAL,
        component="acucalyx.geometry.hazard_zones",
        description="Edge case under-segmentation in retrorenal fat.",
        steps_to_reproduce="Run on challenge case 09.",
    )

    # Release must now be blocked
    can_rel, reasons = mgr.can_release_software()
    assert can_rel is False
    assert any("SEV_1_CRITICAL" in r for r in reasons)

    # Progress anomaly through workflow
    mgr.confirm_anomaly(aid)
    mgr.begin_analysis(aid)
    mgr.resolve_anomaly(
        anomaly_id=aid,
        root_cause="Voxel spacing scaling omitted in EDT border lookup.",
        resolution_description="Applied anisotropic affine correction factor.",
        regression_test_id="test_hazard_clearance_and_intersection",
    )

    # Close anomaly after verification
    mgr.verify_and_close(aid, verified_by="Lead QA Engineer")

    # Release is now permitted
    can_rel, reasons = mgr.can_release_software()
    assert can_rel is True


def test_anomaly_resolution_requires_root_cause_and_regression_test() -> None:
    """Verify IEC 62304 Clause 9 mandates root cause and regression test for resolution."""
    mgr = AnomalyManager()
    aid = mgr.report_anomaly(
        title="Test Defect",
        severity=AnomalySeverity.SEV_2_MAJOR,
        component="test",
        description="Desc",
        steps_to_reproduce="Steps",
    )

    with pytest.raises(ValueError, match="requires documented root cause"):
        mgr.resolve_anomaly(aid, root_cause="", resolution_description="Fix", regression_test_id="T1")

    with pytest.raises(ValueError, match="requires linked automated regression test ID"):
        mgr.resolve_anomaly(aid, root_cause="Known bug", resolution_description="Fix", regression_test_id="")


# ============================================================================
# 5. Premarket Cybersecurity & SBOM Generator Tests
# ============================================================================

def test_ntia_compliant_sbom_generation() -> None:
    """Verify CycloneDX and SPDX SBOM outputs contain all NTIA minimum elements."""
    gen = SBOMGenerator()

    # Test CycloneDX JSON
    cdx = gen.generate_cyclonedx_json()
    assert cdx["bomFormat"] == "CycloneDX"
    assert cdx["specVersion"] == "1.5"
    assert len(cdx["components"]) >= 5
    for comp in cdx["components"]:
        assert "supplier" in comp
        assert "name" in comp
        assert "version" in comp
        assert "hashes" in comp
        assert "licenses" in comp

    # Test SPDX JSON
    spdx = gen.generate_spdx_json()
    assert spdx["spdxVersion"] == "SPDX-2.3"
    assert len(spdx["packages"]) >= 5
    for pkg in spdx["packages"]:
        assert "name" in pkg
        assert "versionInfo" in pkg
        assert "supplier" in pkg
        assert "checksums" in pkg


def test_cisa_kev_vulnerability_auditor() -> None:
    """Verify scanning flags components in CISA KEV or high-severity CVE databases."""
    gen = SBOMGenerator()

    # Clean scan
    clean_audit = gen.audit_vulnerabilities()
    assert clean_audit["compliant"] is True
    assert clean_audit["vulnerabilities_found"] == 0

    # Simulated component with CISA KEV listing
    custom_cve_db = {
        "torch@2.2.2": {
            "cve_id": "CVE-2026-SIMULATED",
            "cvss_score": 9.1,
            "is_kev": True,
            "summary": "Simulated critical flaw for testing.",
        }
    }
    flagged_audit = gen.audit_vulnerabilities(custom_cve_database=custom_cve_db)
    assert flagged_audit["compliant"] is False
    assert flagged_audit["vulnerabilities_found"] == 1
    assert flagged_audit["flagged_components"][0]["action_required"] == "EMERGENCY_PATCH_14_DAYS"


# ============================================================================
# 6. DICOM PS 3.15 Annex E PHI De-Identification Tests
# ============================================================================

def test_dicom_ps315_phi_deidentification() -> None:
    """Verify that direct PHI is scrubbed per PS 3.15 Annex E while spatial tags are preserved."""
    ds = Dataset()
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    # Add direct PHI
    ds.PatientName = "DOE^JOHN^A"
    ds.PatientID = "MRN-55443322"
    ds.PatientBirthDate = "19750512"
    ds.PatientSex = "M"
    ds.InstitutionName = "Metropolitan General Hospital"
    ds.AccessionNumber = "ACC-998877"

    # Add mandatory spatial geometry tags
    ds.PixelSpacing = [0.75, 0.75]
    ds.SliceThickness = 1.5
    ds.ImagePositionPatient = [-150.0, -120.0, 50.0]
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.Rows = 512
    ds.Columns = 512
    ds.Modality = "CT"

    guard = PHIGuard()
    deid_ds = guard.deidentify(ds)

    # Check PHI scrubbed
    assert deid_ds.PatientName == "ANONYMIZED^PCNL"
    assert deid_ds.PatientID.startswith("ACU-")
    assert "DOE" not in deid_ds.PatientID
    assert deid_ds.PatientBirthDate == ""
    assert (0x0008, 0x0080) not in deid_ds  # InstitutionName deleted

    # Check spatial tags preserved 100%
    assert list(deid_ds.PixelSpacing) == [0.75, 0.75]
    assert float(deid_ds.SliceThickness) == 1.5
    assert [float(x) for x in deid_ds.ImagePositionPatient] == [-150.0, -120.0, 50.0]
    assert [float(x) for x in deid_ds.ImageOrientationPatient] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]

    compliant, violations = guard.verify_compliance(deid_ds)
    assert compliant is True, f"Compliance check failed: {violations}"


def test_hmac_pseudonymization_determinism_and_irreversibility() -> None:
    """Verify that HMAC pseudonymization is deterministic across runs but irreversible."""
    key = b"TEST_KEY_2026_FDA_VERIFICATION"
    pseudo = HMACPseudonymizer(key)

    mrn = "MRN-12345678"
    token1 = pseudo.pseudonymize_id(mrn)
    token2 = pseudo.pseudonymize_id(mrn)
    assert token1 == token2
    assert mrn not in token1
    assert token1.startswith("ACU-")

    # Different key produces different token
    pseudo2 = HMACPseudonymizer(b"DIFFERENT_KEY_XYZ")
    token_diff = pseudo2.pseudonymize_id(mrn)
    assert token1 != token_diff


# ============================================================================
# 7. STRIDE Active Threat Defenses & RBAC Tests
# ============================================================================

def test_stride_trajectory_alteration_trap() -> None:
    """Verify the active Trajectory Alteration Trap catches in-transit tampering attacks."""
    evaluator = STRIDEEvaluator()
    plan = _create_sample_plan()
    PlanIntegrityEngine.seal_plan(plan, approved_by="Dr. K. Patel, MD")

    trap_success = evaluator.execute_trajectory_alteration_trap(
        approved_plan=plan,
        attack_tamper_delta=(2.0, 0.0, 0.0),
    )
    assert trap_success is True


def test_malformed_dicom_injection_rejection() -> None:
    """Verify that buffer guard rejects corrupted headers and oversized payloads."""
    evaluator = STRIDEEvaluator()

    # Valid mock byte stream with DICM magic
    valid_bytes = b"\x00" * 128 + b"DICM" + b"\x00" * 100
    assert evaluator.validate_dicom_payload_security(valid_bytes) is True

    # Invalid magic bytes
    bad_bytes = b"\x00" * 128 + b"EVIL" + b"\x00" * 100
    with pytest.raises(MalformedDicomError, match="Invalid DICOM magic header"):
        evaluator.validate_dicom_payload_security(bad_bytes)

    # Payload exceeding buffer limit
    with pytest.raises(MalformedDicomError, match="exceeds maximum security buffer"):
        evaluator.validate_dicom_payload_security(valid_bytes, max_allowed_bytes=50)


def test_rbac_privilege_enforcement() -> None:
    """Verify Role-Based Access Control blocks unauthorized clinical actions."""
    evaluator = STRIDEEvaluator()

    # Attending surgeon is permitted to approve plan
    assert evaluator.verify_role_permission(SecurityRole.ATTENDING_SURGEON, "APPROVE_PLAN") is True

    # Technician is denied plan approval
    with pytest.raises(PrivilegeEscalationError, match="ACCESS DENIED"):
        evaluator.verify_role_permission(SecurityRole.TECHNICIAN, "APPROVE_PLAN")

    # Resident is denied interlock override
    with pytest.raises(PrivilegeEscalationError, match="ACCESS DENIED"):
        evaluator.verify_role_permission(SecurityRole.RESIDENT, "OVERRIDE_INTERLOCK")


# ============================================================================
# 8. SOUP Safety Test Coverage Audit
# ============================================================================

def test_soup_registry_safety_test_coverage() -> None:
    """Verify that 100% of Class C SOUP dependencies have verified automated test coverage."""
    registry = SOUPRegistry()
    audit = registry.audit_safety_coverage()

    assert audit["is_covered"] is True, f"SOUP safety coverage incomplete: {audit}"
    assert len(audit["uncovered_class_c_records"]) == 0
    assert audit["total_soup_records"] >= 7
