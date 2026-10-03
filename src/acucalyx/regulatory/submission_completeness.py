"""AcuCalyx Regulatory Submission Completeness & Evidence Auditor.

Audits Design & Development Files (DDF), Risk Files (RMF), Software V&V,
Cybersecurity, and Clinical Feasibility artifacts to verify 100% submission
completeness prior to loading into the official FDA eSTAR v7.1 dynamic PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from acucalyx.regulatory.artifact_integrity import ArtifactIntegrityAuditor
from acucalyx.regulatory.configuration_baseline import (
    SoftwareConfigurationIndex,
    get_current_configuration_baseline,
)
from acucalyx.regulatory.evidence_index import (
    EvidenceCategory,
    EvidenceItem,
    RegulatoryEvidenceCatalog,
)
from acucalyx.regulatory.traceability import (
    TraceabilityEngine,
    build_acucalyx_default_rtm,
)


@dataclass
class SubmissionCompletenessReport:
    """Comprehensive evaluation record of premarket submission completeness."""
    is_complete: bool
    total_items_checked: int
    missing_items: List[str] = field(default_factory=list)
    version_inconsistencies: List[str] = field(default_factory=list)
    rtm_closure_passed: bool = False
    estar_ready: bool = False
    findings: List[str] = field(default_factory=list)
    artifact_fingerprints: Dict[str, str] = field(default_factory=dict)


class SubmissionCompletenessChecker:
    """Audits local workspace artifacts against the controlled premarket evidence index."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        evidence_catalog: Optional[RegulatoryEvidenceCatalog] = None,
        config_baseline: Optional[SoftwareConfigurationIndex] = None,
    ) -> None:
        self.workspace_root = workspace_root or Path.cwd()
        self.catalog = evidence_catalog or RegulatoryEvidenceCatalog()
        self.config_baseline = config_baseline or get_current_configuration_baseline()
        self.auditor = ArtifactIntegrityAuditor(self.workspace_root)

    def audit_submission(self) -> SubmissionCompletenessReport:
        """Execute a comprehensive audit of all premarket submission artifacts.

        Returns:
            SubmissionCompletenessReport detailing readiness for official eSTAR loading.
        """
        missing_items: List[str] = []
        version_inconsistencies: List[str] = []
        fingerprints: Dict[str, str] = {}
        findings: List[str] = []

        all_items = self.catalog.list_all_items()
        total_items = len(all_items)

        # 1. Audit Document Existence & Cryptographic Fingerprints
        for item in all_items:
            target_path = self.workspace_root / item.relative_path
            if not target_path.exists():
                if item.is_mandatory_for_submission:
                    missing_items.append(f"{item.reference_id}: {item.relative_path}")
                findings.append(f"MISSING: {item.reference_id} ({item.title}) at {item.relative_path}")
            else:
                sha256 = self.auditor.compute_file_sha256(target_path)
                fingerprints[item.relative_path] = sha256
                findings.append(f"VERIFIED: {item.reference_id} [SHA256: {sha256[:12]}...]")

                # 2. Check Document Version Consistency for M7 documents
                if "08_DICOM" in item.relative_path or "09_OPERATORS" in item.relative_path or "11_DESIGN" in item.relative_path:
                    content = target_path.read_text(encoding="utf-8", errors="ignore")
                    if self.config_baseline.application_version not in content:
                        version_inconsistencies.append(
                            f"{item.relative_path} does not mention application version {self.config_baseline.application_version}"
                        )
                    if self.config_baseline.software_build_id not in content:
                        version_inconsistencies.append(
                            f"{item.relative_path} does not mention build ID {self.config_baseline.software_build_id}"
                        )

        # 3. Audit 10-Tier Requirements Traceability Matrix (RTM) Closure
        rtm_engine = build_acucalyx_default_rtm()
        closure = rtm_engine.validate_closure()
        rtm_passed = closure["is_closed"]
        if not rtm_passed:
            rtm_reasons = closure.get("orphaned_nodes", []) + closure.get("untested_requirements", [])
            findings.extend([f"RTM_ERROR: {r}" for r in rtm_reasons])
        else:
            findings.append("RTM_VERIFIED: 100% closure from CN-01 through VAL-M7 with zero orphaned nodes.")

        # 4. Synthesize Final Readiness
        is_complete = (len(missing_items) == 0) and rtm_passed and (len(version_inconsistencies) == 0)
        estar_ready = is_complete

        return SubmissionCompletenessReport(
            is_complete=is_complete,
            total_items_checked=total_items,
            missing_items=missing_items,
            version_inconsistencies=version_inconsistencies,
            rtm_closure_passed=rtm_passed,
            estar_ready=estar_ready,
            findings=findings,
            artifact_fingerprints=fingerprints,
        )
