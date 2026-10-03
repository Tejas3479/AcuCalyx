"""AcuCalyx Decoupled Postmarket Surveillance (PMS) Telemetry Analyzer.

Aggregates real-world clinical performance data, tracks complaint trending,
and compiles periodic safety summaries per ISO 13485:2016 Clause 8.2.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TelemetryCaseEvent:
    """Anonymized real-world case event received from a clinical site."""
    case_id: str  # Pseudonymized format: CASE-PMS-xxxx
    site_id: str
    software_version: str
    pipeline_success: bool
    qc_passed: bool
    interlock_u1_overrides: int = 0
    interlock_u5_alarms: int = 0
    clinician_reported_success: Optional[bool] = None
    clinician_puncture_attempts: Optional[int] = None
    fluoroscopy_time_seconds: Optional[float] = None
    clavien_dindo_grade: int = 0  # 0 = none; 1-5


@dataclass
class PeriodicSafetySummary:
    """Periodic postmarket safety and complaint trending summary."""
    total_cases_processed: int
    pipeline_success_rate: float
    qc_pass_rate: float
    total_complaints: int
    complaint_rate_per_thousand: float
    serious_adverse_events: int  # Clavien-Dindo >= 3
    is_safety_profile_acceptable: bool
    trending_notes: List[str] = field(default_factory=list)


class PostmarketSurveillanceAnalyzer:
    """Decoupled regulatory operations engine for PMS telemetry and complaint trending."""

    def __init__(self) -> None:
        self.events: List[TelemetryCaseEvent] = []
        self.complaints: List[Dict[str, str]] = []

    def ingest_event(self, event: TelemetryCaseEvent) -> None:
        """Ingest a case telemetry record."""
        self.events.append(event)

    def log_complaint(self, complaint_id: str, severity: str, description: str) -> None:
        """Record a formal customer complaint."""
        self.complaints.append({
            "complaint_id": complaint_id,
            "severity": severity,
            "description": description,
        })

    def generate_periodic_safety_summary(
        self,
        complaint_rate_threshold_per_thousand: float = 5.0,
    ) -> PeriodicSafetySummary:
        """Compile periodic postmarket safety summary and statistical trends."""
        total_cases = len(self.events)
        if total_cases == 0:
            return PeriodicSafetySummary(
                total_cases_processed=0,
                pipeline_success_rate=1.0,
                qc_pass_rate=1.0,
                total_complaints=len(self.complaints),
                complaint_rate_per_thousand=0.0,
                serious_adverse_events=0,
                is_safety_profile_acceptable=True,
                trending_notes=["No telemetry events recorded during period."],
            )

        successful_pipelines = sum(1 for e in self.events if e.pipeline_success)
        passed_qcs = sum(1 for e in self.events if e.qc_passed)
        serious_events = sum(1 for e in self.events if e.clavien_dindo_grade >= 3)

        pipeline_rate = successful_pipelines / total_cases
        qc_rate = passed_qcs / total_cases

        total_complaints = len(self.complaints)
        complaint_rate_per_k = (total_complaints / total_cases) * 1000.0

        notes: List[str] = []
        is_acceptable = True

        if complaint_rate_per_k > complaint_rate_threshold_per_thousand:
            is_acceptable = False
            notes.append(
                f"SIGNAL_DETECTED: Complaint rate {complaint_rate_per_k:.2f}/k exceeds "
                f"threshold {complaint_rate_threshold_per_thousand:.2f}/k."
            )
        else:
            notes.append(f"Complaint rate {complaint_rate_per_k:.2f}/k within acceptable limits.")

        if serious_events > 0:
            notes.append(f"Noted {serious_events} serious adverse events (Clavien-Dindo >= 3); requires clinical review.")

        return PeriodicSafetySummary(
            total_cases_processed=total_cases,
            pipeline_success_rate=pipeline_rate,
            qc_pass_rate=qc_rate,
            total_complaints=total_complaints,
            complaint_rate_per_thousand=complaint_rate_per_k,
            serious_adverse_events=serious_events,
            is_safety_profile_acceptable=is_acceptable,
            trending_notes=notes,
        )
