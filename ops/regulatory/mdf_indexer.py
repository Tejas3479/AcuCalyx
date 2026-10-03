"""AcuCalyx Medical Device File (MDF) Indexer & Commercial Baseline Auditor.

Compiles and audits the Medical Device File per ISO 13485:2016 Clause 4.2.3
and FDA QMSR (21 CFR Part 820), verifying manufacturing and servicing specifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class MedicalDeviceFileSection:
    """A required section of the Medical Device File under ISO 13485 Clause 4.2.3."""
    section_id: str
    title: str
    iso_clause: str
    referenced_documents: List[str]
    is_verified: bool = True


@dataclass
class MdfAuditReport:
    """Audit outcome for the Medical Device File."""
    is_mdf_complete: bool
    sections_verified: int
    missing_sections: List[str] = field(default_factory=list)
    audit_findings: List[str] = field(default_factory=list)


class MedicalDeviceFileIndexer:
    """Audits local workspace artifacts against ISO 13485 Clause 4.2.3 MDF requirements."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.workspace_root = workspace_root or Path.cwd()

    def audit_mdf(self) -> MdfAuditReport:
        """Verify that all mandatory MDF documentation exists on disk."""
        findings: List[str] = []
        missing: List[str] = []

        required_documents = [
            ("MDF-1.0", "General Description & Intended Use", "docs/regulatory/01_DESIGN_AND_DEVELOPMENT_INPUTS_SRS.md"),
            ("MDF-2.0", "Product Software Specification", "docs/regulatory/02_SOFTWARE_REQUIREMENTS_SPEC_SWRS.md"),
            ("MDF-2.1", "DICOM Conformance Statement", "docs/regulatory/08_DICOM_CONFORMANCE_STATEMENT_PS32.md"),
            ("MDF-3.0", "SOUP Management Register", "docs/regulatory/13_SOUP_MANAGEMENT_AND_OTS_EVALUATION.md"),
            ("MDF-3.1", "Cybersecurity SPDF & SBOM", "docs/regulatory/05_CYBERSECURITY_MANAGEMENT_PLAN_AND_SPDF.md"),
            ("MDF-4.0", "Device Labeling & Operator Manual", "docs/regulatory/09_OPERATORS_MANUAL_AND_LABELING.md"),
            ("MDF-5.0", "Postmarket Surveillance Plan", "docs/postmarket/05_POSTMARKET_SURVEILLANCE_AND_PMS_PROGRAM.md"),
            ("MDF-5.1", "Postmarket Cybersecurity SOP", "docs/postmarket/06_POSTMARKET_CYBERSECURITY_AND_PATCHING_SOP.md"),
            ("MDF-5.2", "Master MDF Index Specification", "docs/postmarket/02_MEDICAL_DEVICE_FILE_MDF_INDEX.md"),
        ]

        verified_count = 0
        for doc_id, title, rel_path in required_documents:
            target = self.workspace_root / rel_path
            if target.exists():
                verified_count += 1
                findings.append(f"VERIFIED: {doc_id} ({title}) at {rel_path}")
            else:
                missing.append(f"{doc_id}: {rel_path}")
                findings.append(f"MISSING: {doc_id} ({title}) at {rel_path}")

        is_complete = (len(missing) == 0)
        return MdfAuditReport(
            is_mdf_complete=is_complete,
            sections_verified=verified_count,
            missing_sections=missing,
            audit_findings=findings,
        )

    def validate_commercial_baseline_readiness(
        self,
        target_build_id: str,
        target_version: str,
    ) -> Tuple[bool, List[str]]:
        """Validate whether build ID and version satisfy commercial release naming rules."""
        errors: List[str] = []

        if not target_build_id.startswith("ACU-CORE-COMMERCIAL"):
            errors.append(f"INVALID_BUILD_NAME: Commercial build '{target_build_id}' must begin with 'ACU-CORE-COMMERCIAL'.")

        if "-RC" in target_version or "-beta" in target_version:
            errors.append(f"PREMARKET_TAG_PROHIBITED: Commercial release version '{target_version}' cannot contain pre-release tags.")

        is_ready = len(errors) == 0
        return is_ready, errors
