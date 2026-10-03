"""AcuCalyx Decoupled eMDR Decision-Support & HL7 ICSR Builder.

Evaluates clinical complaints and adverse events against 21 CFR Part 803 criteria
and formats HL7 Individual Case Safety Report (ICSR) XML payloads for the FDA ESG.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ReportabilityCategory(str, Enum):
    """Statutory reporting categories under 21 CFR Part 803."""
    MANDATORY_5_DAY_EMERGENCY = "MANDATORY_5_DAY_EMERGENCY"
    MANDATORY_30_DAY_DEATH = "MANDATORY_30_DAY_DEATH"
    MANDATORY_30_DAY_SERIOUS_INJURY = "MANDATORY_30_DAY_SERIOUS_INJURY"
    MANDATORY_30_DAY_MALFUNCTION = "MANDATORY_30_DAY_MALFUNCTION"
    NON_REPORTABLE_INTERNAL_COMPLAINT = "NON_REPORTABLE_INTERNAL_COMPLAINT"


@dataclass
class ClinicalEventRecord:
    """Clinical adverse event or complaint intake record."""
    event_id: str
    event_date: str
    patient_outcome: str  # "DEATH", "SERIOUS_INJURY", "MINOR_INJURY", "NO_INJURY"
    device_malfunction: bool
    malfunction_recurrence_risk: bool  # Likely to cause death/serious injury if recurred
    requires_emergency_remedial_action: bool
    event_description: str
    patient_identifier: str  # Pseudonymized
    udi_placeholder: str = "(01)00860000000001"
    software_version: str = "1.0.0"
    build_id: str = "ACU-CORE-COMMERCIAL-20261015-BLD01"
    plan_signature: str = ""


@dataclass
class ReportabilityTriageResult:
    """Decision-support recommendation requiring human QA/RA determination."""
    category: ReportabilityCategory
    is_reportable: bool
    statutory_deadline_days: int
    triage_rationale: str
    requires_human_ra_signoff: bool = True


class EmdrIcsrBuilder:
    """Decoupled regulatory operations engine for eMDR triage and HL7 ICSR generation."""

    def triage_event(self, record: ClinicalEventRecord) -> ReportabilityTriageResult:
        """Execute rule-based decision-support evaluation under 21 CFR Part 803."""
        # 1. Check 5-Day Emergency Remedial Action
        if record.requires_emergency_remedial_action:
            return ReportabilityTriageResult(
                category=ReportabilityCategory.MANDATORY_5_DAY_EMERGENCY,
                is_reportable=True,
                statutory_deadline_days=5,
                triage_rationale="Event necessitates immediate remedial action to prevent unreasonable risk of substantial harm.",
            )

        # 2. Check 30-Day Patient Death
        if record.patient_outcome == "DEATH":
            return ReportabilityTriageResult(
                category=ReportabilityCategory.MANDATORY_30_DAY_DEATH,
                is_reportable=True,
                statutory_deadline_days=30,
                triage_rationale="Statutory reportability triggered by patient death.",
            )

        # 3. Check 30-Day Serious Injury
        if record.patient_outcome == "SERIOUS_INJURY":
            return ReportabilityTriageResult(
                category=ReportabilityCategory.MANDATORY_30_DAY_SERIOUS_INJURY,
                is_reportable=True,
                statutory_deadline_days=30,
                triage_rationale="Statutory reportability triggered by serious injury requiring medical/surgical intervention.",
            )

        # 4. Check 30-Day Reportable Malfunction
        if record.device_malfunction and record.malfunction_recurrence_risk:
            return ReportabilityTriageResult(
                category=ReportabilityCategory.MANDATORY_30_DAY_MALFUNCTION,
                is_reportable=True,
                statutory_deadline_days=30,
                triage_rationale="Device malfunction occurred that would be likely to cause death/serious injury if it recurred.",
            )

        # 5. Non-reportable complaint
        return ReportabilityTriageResult(
            category=ReportabilityCategory.NON_REPORTABLE_INTERNAL_COMPLAINT,
            is_reportable=False,
            statutory_deadline_days=0,
            triage_rationale="Event does not meet statutory criteria for mandatory MDR submission; log in internal complaint file.",
        )

    def build_hl7_icsr_xml(
        self,
        record: ClinicalEventRecord,
        triage: ReportabilityTriageResult,
        authorized_by: str,
        signoff_notes: str,
    ) -> str:
        """Construct compliant HL7 ICSR XML corresponding to Form FDA 3500A."""
        if not triage.is_reportable:
            raise ValueError("Cannot generate eMDR HL7 ICSR XML for non-reportable event.")

        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<MCCI_IN200100UV01 xmlns="urn:hl7-org:v3" ITSVersion="XML_1.0">',
            f'  <id root="2.16.840.1.113883.3.987" extension="{record.event_id}"/>',
            f'  <creationTime value="{timestamp_str}"/>',
            '  <interactionId root="2.16.840.1.113883.1.6" extension="MCCI_IN200100UV01"/>',
            '  <processingCode code="P"/>',
            '  <processingModeCode code="T"/>',
            '  <acceptAckCode code="AL"/>',
            '  <PORX_IN040006UV>',
            '    <subject>',
            '      <investigationEvent classCode="INVSTG" moodCode="EVN">',
            f'        <id root="2.16.840.1.113883.4.9" extension="{record.event_id}"/>',
            f'        <code code="{triage.category.value}" codeSystem="2.16.840.1.113883.6.96"/>',
            f'        <text>{record.event_description}</text>',
            f'        <effectiveTime value="{record.event_date}"/>',
            '        <!-- Subject: Suspect Medical Device (Section D) -->',
            '        <subjectOf typeCode="SUBJ">',
            '          <deviceInstance classCode="DEV" moodCode="INSTANCE">',
            '            <code code="LLZ" codeSystem="2.16.840.1.113883.6.96" displayName="System, Image Processing, Radiological"/>',
            f'            <id root="2.16.840.1.113883.4.814" extension="{record.udi_placeholder}"/>',
            '            <manufacturerModelName>AcuCalyx Core</manufacturerModelName>',
            f'            <softwareVersionNumber>{record.software_version}</softwareVersionNumber>',
            f'            <lotNumberText>{record.build_id}</lotNumberText>',
            f'            <signatureText>{record.plan_signature}</signatureText>',
            '          </deviceInstance>',
            '        </subjectOf>',
            '        <!-- Regulatory Sign-Off Authority -->',
            '        <authorizer typeCode="AUT">',
            f'          <assignedPerson><name>{authorized_by}</name></assignedPerson>',
            f'          <signatureText>{signoff_notes}</signatureText>',
            '        </authorizer>',
            '      </investigationEvent>',
            '    </subject>',
            '  </PORX_IN040006UV>',
            '</MCCI_IN200100UV01>',
        ]
        return "\n".join(xml_lines)
