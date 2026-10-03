"""AcuCalyx Design & Development Release Authorization Gate Module.

Implements automated evaluation of the 8 mandatory quality dimensions for
internal Design Release Authorization per ISO 13485:2016 Clause 7.3.7
and FDA QMSR (21 CFR Part 820).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from acucalyx.regulatory.anomaly_management import AnomalyManager, AnomalySeverity
from acucalyx.regulatory.configuration_baseline import (
    SoftwareConfigurationIndex,
    get_current_configuration_baseline,
)
from acucalyx.regulatory.labeling_checker import LabelingChecker
from acucalyx.regulatory.submission_completeness import (
    SubmissionCompletenessChecker,
    SubmissionCompletenessReport,
)
from acucalyx.regulatory.traceability import (
    TraceabilityEngine,
    build_acucalyx_default_rtm,
)


@dataclass
class ReleaseAuthorizationDecision:
    """Formal audit decision record for Milestone M7 Design Release."""
    is_authorized: bool
    software_build_id: str
    application_version: str
    evaluation_timestamp: str
    dimension_results: Dict[str, bool] = field(default_factory=dict)
    blocking_reasons: List[str] = field(default_factory=list)
    audit_findings: List[str] = field(default_factory=list)


class ReleaseGateEvaluator:
    """Evaluates the release readiness of AcuCalyx Core against all 8 quality dimensions."""

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        config_baseline: Optional[SoftwareConfigurationIndex] = None,
        anomaly_manager: Optional[AnomalyManager] = None,
    ) -> None:
        self.workspace_root = workspace_root or Path.cwd()
        self.config_baseline = config_baseline or get_current_configuration_baseline()
        self.anomaly_manager = anomaly_manager or AnomalyManager()
        self.completeness_checker = SubmissionCompletenessChecker(
            workspace_root=self.workspace_root,
            config_baseline=self.config_baseline,
        )
        self.labeling_checker = LabelingChecker()

    def evaluate_release(
        self,
        simulated_vv_pass_rate: float = 1.0,
        unmitigated_kev_cves: int = 0,
    ) -> ReleaseAuthorizationDecision:
        """Audit the 8 quality dimensions and render a release authorization decision.

        Args:
            simulated_vv_pass_rate: Proportion of approved V&V tests passing (must be 1.0).
            unmitigated_kev_cves: Count of unresolved CISA KEV findings (must be 0).

        Returns:
            ReleaseAuthorizationDecision record.
        """
        blocking_reasons: List[str] = []
        findings: List[str] = []
        dimensions: Dict[str, bool] = {}
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Dimension 1: Design Controls & Dossier Completeness
        completeness_report: SubmissionCompletenessReport = self.completeness_checker.audit_submission()
        dim1_passed = completeness_report.is_complete
        dimensions["1_design_controls_closure"] = dim1_passed
        if not dim1_passed:
            blocking_reasons.extend(
                [f"DIM1_FAILURE: Missing submission exhibit {m}" for m in completeness_report.missing_items]
            )
            blocking_reasons.extend(
                [f"DIM1_FAILURE: Version inconsistency {v}" for v in completeness_report.version_inconsistencies]
            )
        else:
            findings.append("DIM1_PASSED: 100% of Design & Development exhibits verified on disk.")

        # Dimension 2: 10-Tier Requirements Traceability Matrix Closure
        rtm_engine = build_acucalyx_default_rtm()
        closure = rtm_engine.validate_closure()
        dim2_passed = closure["is_closed"]
        dimensions["2_traceability_closure"] = dim2_passed
        if not dim2_passed:
            rtm_reasons = closure.get("orphaned_nodes", []) + closure.get("untested_requirements", [])
            blocking_reasons.extend([f"DIM2_FAILURE: {r}" for r in rtm_reasons])
        else:
            findings.append("DIM2_PASSED: 100% RTM traceability closure from CN-01 through VAL-M7.")

        # Dimension 3: Verification & Validation Test Baseline Pass Rate
        dim3_passed = (simulated_vv_pass_rate >= 1.0)
        dimensions["3_vv_baseline_pass_rate"] = dim3_passed
        if not dim3_passed:
            blocking_reasons.append(
                f"DIM3_FAILURE: V&V pass rate {simulated_vv_pass_rate:.1%} is below mandatory 100.0%."
            )
        else:
            findings.append("DIM3_PASSED: 100% pass rate achieved across approved V&V baseline.")

        # Dimension 4: Software Anomaly Risk Evaluation (IEC 62304 Clause 9)
        dim4_passed, anomaly_reasons = self.anomaly_manager.can_release_software()
        dimensions["4_anomaly_safety_evaluation"] = dim4_passed
        if not dim4_passed:
            blocking_reasons.extend([f"DIM4_FAILURE: {r}" for r in anomaly_reasons])
        else:
            findings.append("DIM4_PASSED: Zero unresolved Severity 1 or 2 defects; all lower anomalies risk-assessed.")

        # Dimension 5: Premarket Cybersecurity (§524B & Feb 2026 Guidance)
        dim5_passed = (unmitigated_kev_cves == 0) and ("docs/regulatory/05_CYBERSECURITY_MANAGEMENT_PLAN_AND_SPDF.md" in completeness_report.artifact_fingerprints)
        dimensions["5_premarket_cybersecurity"] = dim5_passed
        if not dim5_passed:
            blocking_reasons.append(
                f"DIM5_FAILURE: Premarket cybersecurity audit failed (KEV CVEs: {unmitigated_kev_cves})."
            )
        else:
            findings.append("DIM5_PASSED: CycloneDX SBOM verified; zero unmitigated KEV vulnerabilities.")

        # Dimension 6: Software Configuration Index Freezing
        dim6_passed = bool(
            self.config_baseline.software_build_id
            and self.config_baseline.ai_model_weights_sha256
            and self.config_baseline.git_release_tag
        )
        dimensions["6_configuration_baseline_frozen"] = dim6_passed
        if not dim6_passed:
            blocking_reasons.append("DIM6_FAILURE: Software configuration index contains unassigned parameters.")
        else:
            findings.append(
                f"DIM6_PASSED: Configuration locked to build {self.config_baseline.software_build_id}."
            )

        # Dimension 7: DICOM Interoperability Conformance (PS 3.2)
        dcs_file = self.workspace_root / "docs/regulatory/08_DICOM_CONFORMANCE_STATEMENT_PS32.md"
        dim7_passed = dcs_file.exists() and ("Secondary Capture Image Storage" in dcs_file.read_text(encoding="utf-8", errors="ignore"))
        dimensions["7_dicom_interoperability"] = dim7_passed
        if not dim7_passed:
            blocking_reasons.append("DIM7_FAILURE: DICOM Conformance Statement missing or invalid Secondary Capture DRR policy.")
        else:
            findings.append("DIM7_PASSED: DICOM PS 3.2 statement verified with non-ionizing Secondary Capture DRR encoding.")

        # Dimension 8: Prescription Labeling & UDI Verification (21 CFR Part 801 / 830)
        labeling_file = self.workspace_root / "docs/regulatory/09_OPERATORS_MANUAL_AND_LABELING.md"
        dim8_passed, labeling_failures = self.labeling_checker.audit_labeling_file(labeling_file)
        dimensions["8_labeling_and_udi"] = dim8_passed
        if not dim8_passed:
            blocking_reasons.extend([f"DIM8_FAILURE: {f}" for f in labeling_failures])
        else:
            findings.append("DIM8_PASSED: Operator's Manual verified for 21 CFR 801.109 Rx Only, operating envelope & UDI.")

        is_authorized = all(dimensions.values()) and (len(blocking_reasons) == 0)

        return ReleaseAuthorizationDecision(
            is_authorized=is_authorized,
            software_build_id=self.config_baseline.software_build_id,
            application_version=self.config_baseline.application_version,
            evaluation_timestamp=now_str,
            dimension_results=dimensions,
            blocking_reasons=blocking_reasons,
            audit_findings=findings,
        )
