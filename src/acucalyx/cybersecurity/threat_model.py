"""AcuCalyx STRIDE Cybersecurity Threat Evaluator & Active Security Defenses.

Governed by FDA Premarket Cybersecurity Guidance (Feb 2026), AAMI TIR57,
and FD&C Act §524B.
Implements the Trajectory Alteration Trap, Malformed DICOM Injection Handler,
and Role-Based Access Control (RBAC) privilege enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from acucalyx.regulatory.plan_integrity import CanonicalPlan, PlanIntegrityEngine, PlanTamperError


class ThreatCategory(str, Enum):
    """STRIDE Threat Model Categories."""

    SPOOFING = "SPOOFING"
    TAMPERING = "TAMPERING"
    REPUDIATION = "REPUDIATION"
    INFORMATION_DISCLOSURE = "INFORMATION_DISCLOSURE"
    DENIAL_OF_SERVICE = "DENIAL_OF_SERVICE"
    ELEVATION_OF_PRIVILEGE = "ELEVATION_OF_PRIVILEGE"


class SecurityRole(str, Enum):
    """Certified User Roles in the AcuCalyx Cockpit."""

    ANONYMOUS = "ANONYMOUS"
    TECHNICIAN = "TECHNICIAN"
    RESIDENT = "RESIDENT"
    ATTENDING_SURGEON = "ATTENDING_SURGEON"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class PrivilegeEscalationError(PermissionError):
    """Raised when an unauthorized role attempts a restricted clinical or admin action."""
    pass


class MalformedDicomError(ValueError):
    """Raised when an ingested DICOM file violates security bounds or syntax integrity."""
    pass


@dataclass
class SecurityControl:
    """Represents a validated cybersecurity mitigation."""

    control_id: str
    category: ThreatCategory
    name: str
    description: str
    is_active: bool = True
    mitigation_notes: str = ""


class STRIDEEvaluator:
    """Evaluates system resilience against STRIDE threats and enforces active security traps."""

    # Role-Permission mapping
    ROLE_PERMISSIONS: Dict[SecurityRole, Set[str]] = {
        SecurityRole.ANONYMOUS: set(),
        SecurityRole.TECHNICIAN: {"IMPORT_SCAN", "CALIBRATE_PHANTOM"},
        SecurityRole.RESIDENT: {"IMPORT_SCAN", "COMPUTE_PLAN", "REHEARSE_DRR"},
        SecurityRole.ATTENDING_SURGEON: {
            "IMPORT_SCAN",
            "COMPUTE_PLAN",
            "REHEARSE_DRR",
            "APPROVE_PLAN",
            "EXPORT_PLAN",
            "OVERRIDE_INTERLOCK",
            "VIEW_AUDIT_LOG",
        },
        SecurityRole.SYSTEM_ADMIN: {"VIEW_AUDIT_LOG", "UPDATE_SOUP", "AUDIT_SBOM"},
    }

    def __init__(self) -> None:
        self.controls: Dict[str, SecurityControl] = self._init_default_controls()

    def _init_default_controls(self) -> Dict[str, SecurityControl]:
        return {
            "SEC-01": SecurityControl(
                "SEC-01",
                ThreatCategory.SPOOFING,
                "Surgeon Authentication & mTLS",
                "Cryptographic role verification before plan approval.",
            ),
            "SEC-02": SecurityControl(
                "SEC-02",
                ThreatCategory.TAMPERING,
                "Canonical SHA-256 Plan Fingerprinting",
                "Zero-tolerance cryptographic binding of plan coordinates.",
            ),
            "SEC-03": SecurityControl(
                "SEC-03",
                ThreatCategory.REPUDIATION,
                "Cryptographic Audit Ledger",
                "Append-only log recording surgeon ID and plan hash.",
            ),
            "SEC-04": SecurityControl(
                "SEC-04",
                ThreatCategory.INFORMATION_DISCLOSURE,
                "DICOM PS 3.15 PHI Scrubber",
                "Automated stripping of direct identifiers per Annex E.",
            ),
            "SEC-05": SecurityControl(
                "SEC-05",
                ThreatCategory.DENIAL_OF_SERVICE,
                "DICOM Ingestion Buffer Guard",
                "Hard memory limits (2GB) and pixel dimension validation.",
            ),
            "SEC-06": SecurityControl(
                "SEC-06",
                ThreatCategory.ELEVATION_OF_PRIVILEGE,
                "Role-Based Access Control (RBAC)",
                "Strict restriction of plan approval to Attending Surgeon.",
            ),
        }

    def verify_role_permission(self, role: SecurityRole, action: str) -> bool:
        """Verify that the user's role possesses permission for the requested action."""
        allowed_actions = self.ROLE_PERMISSIONS.get(role, set())
        if action not in allowed_actions:
            raise PrivilegeEscalationError(
                f"ACCESS DENIED: Role '{role.value}' does not have permission for '{action}'. "
                f"Action '{action}' requires higher cryptographic credentials."
            )
        return True

    def validate_dicom_payload_security(self, raw_bytes: bytes, max_allowed_bytes: int = 2 * 1024 * 1024 * 1024) -> bool:
        """Inspect raw DICOM byte stream for decompression bombs and header corruption."""
        if len(raw_bytes) > max_allowed_bytes:
            raise MalformedDicomError(
                f"DICOM payload size ({len(raw_bytes)} bytes) exceeds maximum security buffer ({max_allowed_bytes} bytes). "
                f"Potential decompression bomb rejected."
            )

        # Basic check for minimum length (128 preamble + 4 magic DICM bytes)
        if len(raw_bytes) < 132:
            raise MalformedDicomError("DICOM payload too short to contain standard preamble and magic bytes.")

        magic = raw_bytes[128:132]
        if magic != b"DICM":
            raise MalformedDicomError(f"Invalid DICOM magic header: expected b'DICM', got {magic!r}.")

        return True

    def execute_trajectory_alteration_trap(
        self,
        approved_plan: CanonicalPlan,
        attack_tamper_delta: tuple[float, float, float] = (1.5, 0.0, 0.0),
    ) -> bool:
        """Active security test: Simulates an in-transit coordinate tampering attack

        and verifies that the PlanIntegrityEngine traps and halts execution.
        """
        # Ensure plan was sealed
        if not approved_plan.fingerprint:
            raise ValueError("Plan must be sealed with a fingerprint prior to executing trap test.")

        # Clone and tamper
        tampered_plan = CanonicalPlan(
            plan_id=approved_plan.plan_id,
            patient_id=approved_plan.patient_id,
            laterality=approved_plan.laterality,
            target_point_lps=approved_plan.target_point_lps,
            entry_point_lps=(
                approved_plan.entry_point_lps[0] + attack_tamper_delta[0],
                approved_plan.entry_point_lps[1] + attack_tamper_delta[1],
                approved_plan.entry_point_lps[2] + attack_tamper_delta[2],
            ),
            carm_bullseye_angles=approved_plan.carm_bullseye_angles,
            carm_progression_angles=approved_plan.carm_progression_angles,
            hazard_clearances_mm=approved_plan.hazard_clearances_mm,
            maximum_depth_mm=approved_plan.maximum_depth_mm,
            status=approved_plan.status,
            timestamp_utc=approved_plan.timestamp_utc,
            approved_by=approved_plan.approved_by,
            fingerprint=approved_plan.fingerprint,  # Retains original fingerprint!
        )

        try:
            PlanIntegrityEngine.verify_plan(tampered_plan)
            # If verify_plan didn't raise, the security trap failed!
            return False
        except PlanTamperError:
            # Trap successfully triggered!
            return True
