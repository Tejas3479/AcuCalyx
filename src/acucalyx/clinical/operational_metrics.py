"""AcuCalyx Clinical Site Quality & Operational Metrics Aggregator.

Governed by ISO 13485:2016 Clause 7.3 and ISO 14155:2026.
Monitors investigator compliance with runtime safety interlocks (U1 laterality,
U2 surgical position, U5 depth boundary), calculates plan adoption distributions,
and tracks procedural planning latency across investigational sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from acucalyx.clinical.source_export import ClinicalSourceRecord, PlanAdoptionCategory


@dataclass
class SiteOperationalSummary:
    """Summary metrics of investigator compliance and system adoption for a clinical site."""

    site_id: str
    total_cases_recorded: int
    plan_adoption_counts: Dict[str, int]
    adoption_rate_pct: float  # Percentage in Categories 1, 2, or 3
    rejection_rate_pct: float  # Percentage in Category 4
    laterality_compliance_pct: float  # Percentage passing Interlock U1
    position_compliance_pct: float  # Percentage passing Interlock U2
    depth_alarm_compliance_pct: float  # Percentage with certified depth bounds
    compliance_alerts: List[str]


class ClinicalMetricsAggregator:
    """Aggregates and audits clinical operational telemetry from exported source records."""

    def __init__(self) -> None:
        self.records: List[ClinicalSourceRecord] = []

    def ingest_record(self, record: ClinicalSourceRecord) -> None:
        """Ingest a validated Clinical Source Record."""
        self.records.append(record)

    def generate_site_summary(self, site_id: str) -> SiteOperationalSummary:
        """Generate clinical quality and adoption summary for a specific site."""
        site_records = [r for r in self.records if r.site_id == site_id]
        total = len(site_records)

        if total == 0:
            return SiteOperationalSummary(
                site_id=site_id,
                total_cases_recorded=0,
                plan_adoption_counts={cat.value: 0 for cat in PlanAdoptionCategory},
                adoption_rate_pct=0.0,
                rejection_rate_pct=0.0,
                laterality_compliance_pct=100.0,
                position_compliance_pct=100.0,
                depth_alarm_compliance_pct=100.0,
                compliance_alerts=["No clinical records logged for this site."],
            )

        counts = {cat.value: 0 for cat in PlanAdoptionCategory}
        u1_passes = 0
        u2_passes = 0
        u5_passes = 0

        for r in site_records:
            counts[r.plan_adoption_category.value] += 1
            if r.interlocks_status.get("U1_laterality") == "PASS":
                u1_passes += 1
            if r.interlocks_status.get("U2_position") == "PASS":
                u2_passes += 1
            if r.interlocks_status.get("U5_depth") == "PASS":
                u5_passes += 1

        adopted_count = (
            counts[PlanAdoptionCategory.ADOPTED_UNCHANGED.value] +
            counts[PlanAdoptionCategory.ALTERNATIVE_SELECTED.value] +
            counts[PlanAdoptionCategory.MANUALLY_ADJUSTED.value]
        )
        adoption_pct = (adopted_count / total) * 100.0
        rejection_pct = (counts[PlanAdoptionCategory.REJECTED.value] / total) * 100.0

        u1_pct = (u1_passes / total) * 100.0
        u2_pct = (u2_passes / total) * 100.0
        u5_pct = (u5_passes / total) * 100.0

        alerts: List[str] = []
        if u1_pct < 100.0:
            alerts.append(f"CRITICAL: Laterality Gate compliance ({u1_pct:.1f}%) is below mandatory 100%.")
        if u2_pct < 100.0:
            alerts.append(f"WARNING: Surgical Position compliance ({u2_pct:.1f}%) is below 100%.")
        if rejection_pct > 20.0:
            alerts.append(f"ADVISORY: Plan rejection rate ({rejection_pct:.1f}%) exceeds 20% review threshold.")

        return SiteOperationalSummary(
            site_id=site_id,
            total_cases_recorded=total,
            plan_adoption_counts=counts,
            adoption_rate_pct=round(adoption_pct, 1),
            rejection_rate_pct=round(rejection_pct, 1),
            laterality_compliance_pct=round(u1_pct, 1),
            position_compliance_pct=round(u2_pct, 1),
            depth_alarm_compliance_pct=round(u5_pct, 1),
            compliance_alerts=alerts,
        )
