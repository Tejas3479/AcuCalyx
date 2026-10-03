"""AcuCalyx Decoupled Health Hazard Assessment (HHA) & Recall Support Module.

Provides quantitative risk prioritization for field anomalies and formats
Field Safety Notices (FSN) and 10-day FDA District Office reports per 21 CFR Part 806.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class HazardSeverity(str, Enum):
    """Clinical severity of software defect under ISO 14971."""
    CRITICAL_S1 = "CRITICAL_S1"  # Potential death, visceral organ perforation, severe bleeding
    MAJOR_S2 = "MAJOR_S2"        # Reversible injury, pneumothorax, minor pleural tear
    MINOR_S3 = "MINOR_S3"        # Minor procedural delay, transient visualization artifact


class HazardProbability(str, Enum):
    """Probability of occurrence in the clinical patient population."""
    HIGH_P1 = "HIGH_P1"          # Systematic flaw affecting standard geometries
    MEDIUM_P2 = "MEDIUM_P2"      # Occurs under specific anatomical permutations
    LOW_P3 = "LOW_P3"            # Rare corner case requiring compound user errors


class RiskPriorityLevel(str, Enum):
    """Internal manufacturer risk priority for corrective actions."""
    PRIORITY_URGENT_CORRECTION = "PRIORITY_URGENT_CORRECTION"
    PRIORITY_MONITORED_PATCH = "PRIORITY_MONITORED_PATCH"
    PRIORITY_ROUTINE_MAINTENANCE = "PRIORITY_ROUTINE_MAINTENANCE"


@dataclass
class HealthHazardRecord:
    """Intake record for a health hazard evaluation."""
    assessment_id: str
    anomaly_id: str
    defect_description: str
    clinical_hazard: str
    severity: HazardSeverity
    probability: HazardProbability
    units_distributed: int


class HealthHazardAssessor:
    """Decoupled regulatory operations engine for Health Hazard Evaluations (21 CFR Part 806)."""

    def evaluate_hazard(self, record: HealthHazardRecord) -> Tuple[RiskPriorityLevel, str]:
        """Compute internal manufacturer risk priority level.

        Note: The software assists internal risk prioritization. The FDA assigns
        the final official statutory recall classification (Class I, II, III).
        """
        # S1 with High or Medium probability -> Urgent Correction
        if record.severity == HazardSeverity.CRITICAL_S1 and record.probability in (
            HazardProbability.HIGH_P1,
            HazardProbability.MEDIUM_P2,
        ):
            priority = RiskPriorityLevel.PRIORITY_URGENT_CORRECTION
            rationale = (
                "Critical potential health hazard with non-negligible probability. "
                "Warrants urgent customer Field Safety Notice, voluntary field correction, "
                "and 10-day notification to FDA District Office per 21 CFR Part 806."
            )
        elif record.severity == HazardSeverity.CRITICAL_S1 or record.severity == HazardSeverity.MAJOR_S2:
            priority = RiskPriorityLevel.PRIORITY_MONITORED_PATCH
            rationale = (
                "Moderate health hazard risk. Warrants expedited software patch deployment "
                "and advisory customer communication."
            )
        else:
            priority = RiskPriorityLevel.PRIORITY_ROUTINE_MAINTENANCE
            rationale = (
                "Minor risk to health. Software anomaly can be addressed in scheduled maintenance update."
            )

        return priority, rationale

    def generate_field_safety_notice(
        self,
        record: HealthHazardRecord,
        priority: RiskPriorityLevel,
        interim_mitigation: str,
        patch_version: str,
    ) -> str:
        """Generate standardized customer Field Safety Notice (FSN) text."""
        notice_lines = [
            "=" * 78,
            "URGENT MEDICAL DEVICE SAFETY NOTICE: FIELD CORRECTION",
            f"COMMUNICATION ID: FSN-{record.assessment_id}",
            "TARGET RECIPIENT: Urology Department Chairs, Risk Managers, OR Directors",
            "=" * 78,
            f"DEVICE BRAND NAME: AcuCalyx™ Core",
            f"AFFECTED ANOMALY ID: {record.anomaly_id}",
            f"INTERNAL RISK PRIORITY: {priority.value}",
            f"AFFECTED SITES / UNITS: {record.units_distributed} active hospital installations",
            "",
            "1. DESCRIPTION OF SOFTWARE ISSUE:",
            f"   {record.defect_description}",
            "",
            "2. CLINICAL RISK TO PATIENT:",
            f"   {record.clinical_hazard}",
            "",
            "3. MANDATORY IMMEDIATE INTERIM ACTIONS FOR SURGICAL PERSONNEL:",
            f"   {interim_mitigation}",
            "",
            "4. SOFTWARE REMEDIATION & PATCH DEPLOYMENT:",
            f"   A validated cryptographic software update (Version {patch_version}) will be",
            "   dispatched to hospital systems administrators within the remediation SLA window.",
            "=" * 78,
        ]
        return "\n".join(notice_lines)

    def build_10_day_fda_district_report(
        self,
        record: HealthHazardRecord,
        priority: RiskPriorityLevel,
        fsn_text: str,
        contact_name: str = "Elena Rostova, RAC (Director Regulatory Affairs)",
    ) -> str:
        """Construct formal 10-day written notification to FDA District Office (21 CFR 806.10)."""
        report_lines = [
            "REPORT OF MEDICAL DEVICE CORRECTION OR REMOVAL (21 CFR 806.10)",
            f"REPORT REFERENCE: FDA-806-ACU-{record.assessment_id}",
            f"SUBMISSION DATE: 2026-10-15",
            f"MANUFACTURER CONTACT: {contact_name}",
            "",
            "1. DEVICE IDENTIFICATION:",
            "   Trade Name: AcuCalyx™ Core",
            "   Classification: System, Image Processing, Radiological (21 CFR 892.2050 / LLZ)",
            f"   Units in Distribution: {record.units_distributed}",
            "",
            "2. REASON FOR CORRECTION / REMOVAL:",
            f"   {record.defect_description}",
            "",
            "3. HEALTH HAZARD ASSESSMENT & RISK PRIORITY:",
            f"   Clinical Hazard: {record.clinical_hazard}",
            f"   Severity: {record.severity.value} | Probability: {record.probability.value}",
            f"   Internal Priority: {priority.value}",
            "",
            "4. CUSTOMER COMMUNICATION & MITIGATION:",
            "   Attached below is the Field Safety Notice dispatched to all active clinical sites:",
            "",
            fsn_text,
        ]
        return "\n".join(report_lines)
