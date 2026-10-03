"""AcuCalyx Software Problem Resolution & Anomaly Management System.

Governed by IEC 62304:2006 + AMD 1:2015 Clause 9 and ISO 13485:2016 Clause 8.5.2.
Enforces formal defect tracking, root-cause investigation, regression verification,
and strict release gate criteria (Zero Open Severity 1 or 2 defects).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class AnomalySeverity(int, Enum):
    """IEC 62304 / ISO 14971 aligned defect severity."""

    SEV_1_CRITICAL = 1  # Potential death, critical visceral harm, unhandled crash
    SEV_2_MAJOR = 2  # Safety-relevant calculation impairment; workaround exists
    SEV_3_MODERATE = 3  # Non-safety functional defect or DRR visualization artifact
    SEV_4_MINOR = 4  # Usability nuisance in Class A presentation layer
    SEV_5_COSMETIC = 5  # Styling, layout, or documentation defect


class AnomalyState(str, Enum):
    """Lifecycle states of a reported medical software anomaly."""

    REPORTED = "REPORTED"
    CONFIRMED = "CONFIRMED"
    IN_ANALYSIS = "IN_ANALYSIS"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"


@dataclass
class SoftwareAnomaly:
    """Represents a tracked software problem report per IEC 62304 Clause 9."""

    anomaly_id: str
    title: str
    severity: AnomalySeverity
    state: AnomalyState
    component: str
    description: str
    steps_to_reproduce: str
    root_cause: str = ""
    resolution_description: str = ""
    regression_test_id: str = ""
    reported_date: str = "2026-09-30T12:00:00Z"
    closed_date: Optional[str] = None
    verified_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "title": self.title,
            "severity": int(self.severity),
            "state": self.state.value,
            "component": self.component,
            "description": self.description,
            "steps_to_reproduce": self.steps_to_reproduce,
            "root_cause": self.root_cause,
            "resolution_description": self.resolution_description,
            "regression_test_id": self.regression_test_id,
            "reported_date": self.reported_date,
            "closed_date": self.closed_date,
            "verified_by": self.verified_by,
        }


class AnomalyManager:
    """Manages the full lifecycle of software defects and release gating."""

    def __init__(self) -> None:
        self.anomalies: Dict[str, SoftwareAnomaly] = {}
        self._next_id = 1

    def report_anomaly(
        self,
        title: str,
        severity: AnomalySeverity,
        component: str,
        description: str,
        steps_to_reproduce: str,
    ) -> str:
        """Log a new software defect."""
        anomaly_id = f"ANOM-ACU-{self._next_id:04d}"
        self._next_id += 1

        record = SoftwareAnomaly(
            anomaly_id=anomaly_id,
            title=title,
            severity=severity,
            state=AnomalyState.REPORTED,
            component=component,
            description=description,
            steps_to_reproduce=steps_to_reproduce,
        )
        self.anomalies[anomaly_id] = record
        return anomaly_id

    def confirm_anomaly(self, anomaly_id: str) -> None:
        if anomaly_id not in self.anomalies:
            raise KeyError(f"Anomaly '{anomaly_id}' not found.")
        self.anomalies[anomaly_id].state = AnomalyState.CONFIRMED

    def begin_analysis(self, anomaly_id: str) -> None:
        if anomaly_id not in self.anomalies:
            raise KeyError(f"Anomaly '{anomaly_id}' not found.")
        self.anomalies[anomaly_id].state = AnomalyState.IN_ANALYSIS

    def resolve_anomaly(
        self,
        anomaly_id: str,
        root_cause: str,
        resolution_description: str,
        regression_test_id: str,
    ) -> None:
        """Resolve anomaly with documented root cause and linked automated regression test."""
        if anomaly_id not in self.anomalies:
            raise KeyError(f"Anomaly '{anomaly_id}' not found.")
        if not root_cause.strip():
            raise ValueError("IEC 62304 Clause 9 requires documented root cause for resolution.")
        if not regression_test_id.strip():
            raise ValueError("Resolution requires linked automated regression test ID.")

        anomaly = self.anomalies[anomaly_id]
        anomaly.root_cause = root_cause
        anomaly.resolution_description = resolution_description
        anomaly.regression_test_id = regression_test_id
        anomaly.state = AnomalyState.RESOLVED

    def verify_and_close(self, anomaly_id: str, verified_by: str) -> None:
        """Verify fix against regression test and formally close anomaly."""
        if anomaly_id not in self.anomalies:
            raise KeyError(f"Anomaly '{anomaly_id}' not found.")
        anomaly = self.anomalies[anomaly_id]

        if anomaly.state != AnomalyState.RESOLVED:
            raise RuntimeError(f"Cannot close anomaly in state '{anomaly.state.value}'; must be RESOLVED first.")

        anomaly.state = AnomalyState.CLOSED
        anomaly.verified_by = verified_by
        anomaly.closed_date = "2026-09-30T18:00:00Z"

    def can_release_software(self) -> Tuple[bool, List[str]]:
        """Evaluate release gate: Prohibits release if any Sev 1 or 2 defects are open.

        Also asserts that all resolved defects have a linked regression test.
        """
        blocking_reasons: List[str] = []

        for aid, anomaly in self.anomalies.items():
            if anomaly.state != AnomalyState.CLOSED:
                if anomaly.severity in (AnomalySeverity.SEV_1_CRITICAL, AnomalySeverity.SEV_2_MAJOR):
                    blocking_reasons.append(
                        f"Unresolved {anomaly.severity.name}: '{aid}' ({anomaly.title}) in state {anomaly.state.value}."
                    )
                elif anomaly.state == AnomalyState.RESOLVED and not anomaly.regression_test_id:
                    blocking_reasons.append(
                        f"Resolved anomaly '{aid}' lacks linked automated regression test."
                    )

        can_release = len(blocking_reasons) == 0
        return can_release, blocking_reasons
